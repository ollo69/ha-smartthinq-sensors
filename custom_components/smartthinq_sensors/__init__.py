"""
Support for LG SmartThinQ device.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    AuthenticationError,
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
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CLIENT,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_USE_API_V2,
    CONF_USE_HA_SESSION,
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
SIGNAL_RELOAD_ENTRY = f"{DOMAIN}_reload_entry"
UNSUPPORTED_DEVICES = "unsupported_devices"

SCAN_INTERVAL = timedelta(seconds=30)
_LOGGER = logging.getLogger(__name__)


class LGEAuthentication:
    """Class to authenticate connection with LG ThinQ."""

    def __init__(
        self, hass: HomeAssistant, region: str, language: str, use_ha_session=False
    ) -> None:
        """Initialize the class."""
        self._region = region
        self._language = language
        self._client_session = None
        if use_ha_session:
            self._client_session = async_get_clientsession(hass)

    async def get_login_url(self) -> str | None:
        """Get an url to login in browser."""
        try:
            return await ClientAsync.get_oauth_url(
                self._region, self._language, aiohttp_session=self._client_session
            )
        except Exception as exc:
            _LOGGER.exception("Error retrieving login URL from ThinQ", exc_info=exc)

        return None

    async def get_auth_info_from_url(self, callback_url: str) -> dict[str, str] | None:
        """Retrieve auth info from redirect url."""
        try:
            return await ClientAsync.oauth_info_from_url(
                callback_url, aiohttp_session=self._client_session
            )
        except Exception as exc:
            _LOGGER.exception("Error retrieving OAuth info from ThinQ", exc_info=exc)

        return None

    async def create_client_from_login(self, username: str, password: str) -> ClientAsync:
        """Create a new client using username and password."""
        return await ClientAsync.from_login(
            username,
            password,
            country=self._region,
            language=self._language,
            aiohttp_session=self._client_session,
        )

    async def create_client_from_token(self, token: str, oauth_url: str | None = None) -> ClientAsync:
        """Create a new client using refresh token."""
        return await ClientAsync.from_token(
            token,
            oauth_url,
            country=self._region,
            language=self._language,
            aiohttp_session=self._client_session,
            # enable_emulation=True,
        )


def is_min_ha_version(min_ha_major_ver: int, min_ha_minor_ver: int) -> bool:
    """Check if HA version at least a specific version."""
    return (
        MAJOR_VERSION > min_ha_major_ver or
        (MAJOR_VERSION == min_ha_major_ver and MINOR_VERSION >= min_ha_minor_ver)
    )


async def async_setup_entity_platforms(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    platforms: Iterable[Platform | str],
) -> None:
    """Set up entity platforms using new method from HA version 2022.8."""
    if is_min_ha_version(2022, 8):
        await hass.config_entries.async_forward_entry_setups(config_entry, platforms)
    else:
        hass.config_entries.async_setup_platforms(config_entry, platforms)


def is_valid_ha_version() -> bool:
    """Check if HA version is valid for this integration."""
    return is_min_ha_version(MIN_HA_MAJ_VER, MIN_HA_MIN_VER)


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
    use_ha_session = entry.data.get(CONF_USE_HA_SESSION, False)

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

    log_info: bool = hass.data.get(DOMAIN, {}).get(SIGNAL_RELOAD_ENTRY, 0) < 2
    if log_info:
        hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: 2}
        _LOGGER.info(STARTUP)
        _LOGGER.info(
            "Initializing ThinQ platform with region: %s - language: %s",
            region,
            language,
        )

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lge_auth = LGEAuthentication(hass, region, language, use_ha_session)
    try:
        client = await lge_auth.create_client_from_token(refresh_token, oauth_url)

    except (AuthenticationError, InvalidCredentialError) as exc:
        msg = "Invalid ThinQ credential error, integration setup aborted." \
              " Please use the LG App on your mobile device to ensure your" \
              " credentials are correct or there are new Term of Service to accept." \
              " If your credential changed, you must reconfigure integration." \
              " Account based on social network are not supported and in most" \
              " case do not work with this integration."
        _notify_error(hass, "inv_credential", "SmartThinQ Sensors", msg)
        if log_info:
            _LOGGER.warning(msg, exc_info=True)
        msg2 = "Invalid ThinQ credential error, integration setup aborted." \
               " Please use the LG App on your mobile device to verify credential."
        raise ConfigEntryNotReady(msg2) from exc

    except Exception as exc:
        if log_info:
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
        if log_info:
            _LOGGER.warning(
                "Connection not available. ThinQ platform not ready", exc_info=True
            )
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    # remove device not available anymore
    cleanup_orphan_lge_devices(hass, entry.entry_id, client)

    async def _async_call_reload_entry():
        """Reload current entry."""
        if SIGNAL_RELOAD_ENTRY in hass.data[DOMAIN]:
            return
        hass.data[DOMAIN][SIGNAL_RELOAD_ENTRY] = 1
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_RELOAD_ENTRY, _async_call_reload_entry)
    )

    hass.data[DOMAIN] = {
        CLIENT: client,
        LGE_DEVICES: lge_devices,
        UNSUPPORTED_DEVICES: unsupported_devices,
    }
    await async_setup_entity_platforms(hass, entry, SMARTTHINQ_PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, SMARTTHINQ_PLATFORMS
    ):
        data = hass.data.pop(DOMAIN)
        reload = data.get(SIGNAL_RELOAD_ENTRY, 0)
        if reload > 0:
            hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: reload}
        await data[CLIENT].close()
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

        except InvalidCredentialError:
            # If we receive invalid credential, we reload integration
            # to provide proper notification
            async_dispatcher_send(self._hass, SIGNAL_RELOAD_ENTRY)
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
