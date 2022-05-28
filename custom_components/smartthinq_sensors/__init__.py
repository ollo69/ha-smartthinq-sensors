"""
Support for LG SmartThinQ device.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from .wideq import (
    UNIT_TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT,
    DeviceInfo as LGDeviceInfo,
    DeviceType,
    get_lge_device,
)
from .wideq.core_async import ClientAsync
from .wideq.core_exceptions import (
    InvalidCredentialError,
    MonitorRefreshError,
    MonitorUnavailableError,
    NotConnectedError,
)

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_REGION,
    CONF_TOKEN,
    MAJOR_VERSION,
    MINOR_VERSION,
    TEMP_CELSIUS,
    Platform,
    __version__,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CLIENT,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_USE_API_V2,
    DOMAIN,
    MIN_HA_MAJ_VER,
    MIN_HA_MIN_VER,
    LGE_DEVICES,
    STARTUP,
    __min_ha_version__,
)

SMARTTHINQ_PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.HUMIDIFIER,
    Platform.SENSOR,
    Platform.SWITCH
]

MAX_DISC_COUNT = 4
UNSUPPORTED_DEVICES = "unsupported_devices"

SCAN_INTERVAL = timedelta(seconds=30)
_LOGGER = logging.getLogger(__name__)


class LGEAuthentication:
    """Class to authenticate connection with LG ThinQ."""

    def __init__(self, region: str, language: str) -> None:
        """Initialize the class."""
        self._region = region
        self._language = language

    async def get_login_url(self, hass: HomeAssistant) -> str | None:
        """Get an url to login in browser."""
        session = async_get_clientsession(hass)
        try:
            return await ClientAsync.get_oauth_url(
                self._region, self._language, aiohttp_session=session
            )
        except Exception as exc:
            _LOGGER.exception("Error retrieving login URL from ThinQ", exc_info=exc)

        return None

    @staticmethod
    async def get_auth_info_from_url(hass: HomeAssistant, callback_url: str) -> dict[str, str] | None:
        """Retrieve auth info from redirect url."""
        session = async_get_clientsession(hass)
        try:
            return await ClientAsync.oauth_info_from_url(callback_url, aiohttp_session=session)
        except Exception as exc:
            _LOGGER.exception("Error retrieving OAuth info from ThinQ", exc_info=exc)

        return None

    async def create_client_from_login(self, hass: HomeAssistant, username: str, password: str) -> ClientAsync:
        """Create a new client using username and password."""
        session = async_get_clientsession(hass)
        return await ClientAsync.from_login(
            username,
            password,
            country=self._region,
            language=self._language,
            aiohttp_session=session,
        )

    async def create_client_from_token(
            self, hass: HomeAssistant, token: str, oauth_url: str | None = None
    ) -> ClientAsync:
        """Create a new client using refresh token."""
        session = async_get_clientsession(hass)
        return await ClientAsync.from_token(
            token,
            oauth_url,
            country=self._region,
            language=self._language,
            aiohttp_session=session,
            # enable_emulation=True,
        )


def is_valid_ha_version() -> bool:
    """Check if HA version is valid for this integration."""
    return (
        MAJOR_VERSION > MIN_HA_MAJ_VER or
        (MAJOR_VERSION == MIN_HA_MAJ_VER and MINOR_VERSION >= MIN_HA_MIN_VER)
    )


def _notify_error(hass, notification_id, title, message) -> None:
    """Notify user with persistent notification"""
    hass.async_create_task(
        hass.services.async_call(
            domain='persistent_notification', service='create', service_data={
                'title': title,
                'message': message,
                'notification_id': f"{DOMAIN}.{notification_id}"
            }
        )
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartThinQ integration from a config entry."""

    if not is_valid_ha_version():
        msg = "This integration require at least HomeAssistant version " \
              f" {__min_ha_version__}, you are running version {__version__}." \
              " Please upgrade HomeAssistant to continue use this integration."
        _notify_error(hass, "inv_ha_version", "SmartThinQ Sensors", msg)
        _LOGGER.warning(msg)
        return False

    refresh_token = entry.data[CONF_TOKEN]
    region = entry.data[CONF_REGION]
    language = entry.data[CONF_LANGUAGE]
    oauth_url = entry.data.get(CONF_OAUTH_URL)
    use_api_v2 = entry.data.get(CONF_USE_API_V2, False)

    if not use_api_v2:
        _LOGGER.warning(
            "Integration configuration is using ThinQ APIv1 that is unsupported. Please reconfigure"
        )
        # Launch config entries setup
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=entry.data
            )
        )
        return False

    _LOGGER.info(STARTUP)
    _LOGGER.info(
        "Initializing ThinQ platform with region: %s - language: %s",
        region,
        language,
    )

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lge_auth = LGEAuthentication(region, language)
    try:
        client = await lge_auth.create_client_from_token(hass, refresh_token, oauth_url)

    except InvalidCredentialError:
        msg = "Invalid ThinQ credential error, integration setup aborted." \
              " Please use the LG App on your mobile device to ensure your" \
              " credentials are correct, then restart HomeAssistant." \
              " If your credential changed, you must reconfigure integration"
        _notify_error(hass, "inv_credential", "SmartThinQ Sensors", msg)
        _LOGGER.error(msg)
        return False

    except Exception as exc:
        _LOGGER.warning(
            "Connection not available. ThinQ platform not ready", exc_info=True
        )
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    if not client.has_devices:
        _LOGGER.error("No ThinQ devices found. Component setup aborted")
        return False

    _LOGGER.info("ThinQ client connected")

    try:
        lge_devices, unsupported_devices = await lge_devices_setup(hass, client)
    except Exception as exc:
        _LOGGER.warning(
            "Connection not available. ThinQ platform not ready", exc_info=True
        )
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    # remove device not available anymore
    cleanup_orphan_lge_devices(hass, entry.entry_id, client)

    hass.data[DOMAIN] = {
        CLIENT: client,
        LGE_DEVICES: lge_devices,
        UNSUPPORTED_DEVICES: unsupported_devices,
    }
    hass.config_entries.async_setup_platforms(entry, SMARTTHINQ_PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, SMARTTHINQ_PLATFORMS
    ):
        hass.data.pop(DOMAIN)

    return unload_ok


class LGEDevice:

    def __init__(self, device, hass):
        """initialize a LGE Device."""

        self._device = device
        self._hass = hass
        self._name = device.device_info.name
        self._device_id = device.device_info.id
        self._type = device.device_info.type
        self._mac = device.device_info.macaddress
        self._firmware = device.device_info.firmware

        self._model = f"{device.device_info.model_name}"
        self._id = f"{self._type.name}:{self._device_id}"

        self._state = None
        self._coordinator = None
        self._disc_count = 0
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._available and self._disc_count >= MAX_DISC_COUNT

    @property
    def device(self):
        """The device instance"""
        return self._device

    @property
    def name(self) -> str:
        """The device name"""
        return self._name

    @property
    def type(self) -> DeviceType:
        """The device type"""
        return self._type

    @property
    def unique_id(self) -> str:
        """Device unique ID"""
        return self._id

    @property
    def state(self):
        """Current device state"""
        return self._state

    @property
    def available_features(self) -> dict:
        return self._device.available_features

    @property
    def device_info(self) -> DeviceInfo:
        data = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._name,
            manufacturer="LG",
            model=f"{self._model} ({self._type.name})",
        )
        if self._firmware:
            data["sw_version"] = self._firmware
        if self._mac:
            data["connections"] = {(dr.CONNECTION_NETWORK_MAC, self._mac)}

        return data

    @property
    def coordinator(self) -> DataUpdateCoordinator | None:
        return self._coordinator

    async def init_device(self) -> bool:
        """Init the device status and start coordinator."""
        if not await self._device.init_device_info():
            return False
        self._state = self._device.status
        self._model = f"{self._model}-{self._device.model_info.model_type}"

        # Create status update coordinator
        await self._create_coordinator()

        # Initialize device features
        _ = self._state.device_features

        return True

    async def _create_coordinator(self) -> None:
        """Get the coordinator for a specific device."""
        coordinator = DataUpdateCoordinator(
            self._hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._name}",
            update_method=self._async_update,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=SCAN_INTERVAL
        )
        await coordinator.async_refresh()
        self._coordinator = coordinator

    async def _async_update(self):
        """Async update used by coordinator."""
        await self._async_state_update()
        return self._state

    async def _async_state_update(self):
        """Update device state."""
        _LOGGER.debug("Updating ThinQ device %s", self._name)
        if self._disc_count < MAX_DISC_COUNT:
            self._disc_count += 1

        try:
            # method poll should return None if status is not yet available
            # or due to temporary connection failure that will be restored
            state = await self._device.poll()

        except (MonitorRefreshError, NotConnectedError):
            # These exceptions are raised when device is not connected (turned off)
            # or unreachable due to network or API errors
            # If device status is "on" we reset the status, otherwise we just
            # ignore and use previous known state
            state = None
            if self._state.is_on and self._disc_count >= MAX_DISC_COUNT:
                _LOGGER.warning(
                    "Status for device %s was reset because disconnected or unreachable",
                    self._name,
                )
                self._state = self._device.reset_status()

        except MonitorUnavailableError:
            # This exception is raised when issue with ThinQ persist
            # In this case available is set to false and device status
            # is reset to avoid confusion when connection is restored
            if not self._available:
                return
            _LOGGER.warning(
                "Status for device %s was reset because ThinQ connection not available",
                self._name,
            )
            self._available = False
            self._state = self._device.reset_status()
            return

        self._available = True
        if state:
            _LOGGER.debug("ThinQ status updated")
            # l = dir(state)
            # _LOGGER.debug('Status attributes: %s', l)
            self._disc_count = 0
            self._state = state


async def lge_devices_setup(
    hass: HomeAssistant, client: ClientAsync
) -> tuple[dict[DeviceType, list[LGEDevice]], dict[DeviceType, list[LGDeviceInfo]]]:
    """Query connected devices from LG ThinQ."""
    _LOGGER.info("Starting LGE ThinQ devices...")

    wrapped_devices: dict[DeviceType, list[LGEDevice]] = {}
    unsupported_devices: dict[DeviceType, list[LGDeviceInfo]] = {}
    device_count = 0
    temp_unit = UNIT_TEMP_CELSIUS
    if hass.config.units.temperature_unit != TEMP_CELSIUS:
        temp_unit = UNIT_TEMP_FAHRENHEIT

    for device in client.devices:
        device_id = device.id
        device_name = device.name
        device_type = device.type
        network_type = device.network_type
        model_name = device.model_name
        device_count += 1

        lge_dev = get_lge_device(client, device, temp_unit)
        if not lge_dev:
            _LOGGER.info(
                "Found unsupported LGE Device. Name: %s - Type: %s - NetworkType: %s - InfoUrl: %s",
                device_name,
                device_type.name,
                network_type.name,
                device.model_info_url,
            )
            unsupported_devices.setdefault(device_type, []).append(device)
            continue

        dev = LGEDevice(lge_dev, hass)
        if not await dev.init_device():
            _LOGGER.error(
                "Error initializing LGE Device. Name: %s - Type: %s - InfoUrl: %s",
                device_name,
                device_type.name,
                device.model_info_url,
            )
            continue

        wrapped_devices.setdefault(device_type, []).append(dev)
        _LOGGER.info(
            "LGE Device added. Name: %s - Type: %s - Model: %s - ID: %s",
            device_name,
            device_type.name,
            model_name,
            device_id,
        )

    _LOGGER.info("Founds %s LGE device(s)", str(device_count))
    return wrapped_devices, unsupported_devices


@callback
def cleanup_orphan_lge_devices(
    hass: HomeAssistant, entry_id: str, client: ClientAsync
) -> None:
    """Delete devices that are not registered in LG client app"""

    # Load lg devices from registry
    device_registry = dr.async_get(hass)
    all_lg_dev_entries = dr.async_entries_for_config_entry(
        device_registry, entry_id
    )

    # get list of valid devices
    valid_lg_dev_ids = []
    for device in client.devices:
        dev = device_registry.async_get_device({(DOMAIN, device.id)})
        if dev is not None:
            valid_lg_dev_ids.append(dev.id)

    # clean-up invalid devices
    for dev_entry in all_lg_dev_entries:
        dev_id = dev_entry.id
        if dev_id in valid_lg_dev_ids:
            continue
        device_registry.async_remove_device(dev_id)
