"""
Support for LG SmartThinQ device.
"""
# REQUIREMENTS = ['wideq']

import logging
import voluptuous as vol

from datetime import timedelta
from typing import Dict

from .wideq.core import Client
from .wideq.core_v2 import ClientV2, CoreV2HttpAdapter
from .wideq.device import UNIT_TEMP_CELSIUS, UNIT_TEMP_FAHRENHEIT, DeviceType
from .wideq.factory import get_lge_device
from .wideq.core_exceptions import (
    InvalidCredentialError,
    MonitorRefreshError,
    MonitorUnavailableError,
    NotConnectedError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_SW_VERSION,
    CONF_REGION,
    CONF_TOKEN,
    MAJOR_VERSION,
    MINOR_VERSION,
    TEMP_CELSIUS,
    __version__,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CLIENT,
    CONF_EXCLUDE_DH,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_OAUTH_USER_NUM,
    CONF_USE_API_V2,
    CONF_USE_TLS_V1,
    DOMAIN,
    MIN_HA_MAJ_VER,
    MIN_HA_MIN_VER,
    LGE_DEVICES,
    STARTUP,
    __min_ha_version__,
)


SMARTTHINQ_PLATFORMS = [
    "sensor", "binary_sensor", "climate", "switch"
]

SMARTTHINQ_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Required(CONF_REGION): str,
        vol.Required(CONF_LANGUAGE): str,
    }
)

CONFIG_SCHEMA = vol.Schema(
    vol.All(cv.deprecated(DOMAIN), {DOMAIN: SMARTTHINQ_SCHEMA},), extra=vol.ALLOW_EXTRA,
)

MAX_DISC_COUNT = 4
UNSUPPORTED_DEVICES = "unsupported_devices"

SCAN_INTERVAL = timedelta(seconds=30)
_LOGGER = logging.getLogger(__name__)


class LGEAuthentication:
    def __init__(self, region, language, use_api_v2=True):
        self._region = region
        self._language = language
        self._use_api_v2 = use_api_v2

    def _create_client(self):
        if self._use_api_v2:
            client = ClientV2(country=self._region, language=self._language)
        else:
            client = Client(country=self._region, language=self._language)

        return client

    def init_http_adapter(self, use_tls_v1, exclude_dh):
        if self._use_api_v2:
            CoreV2HttpAdapter.init_http_adapter(use_tls_v1, exclude_dh)

    def get_login_url(self) -> str:

        login_url = None
        client = self._create_client()

        try:
            login_url = client.gateway.oauth_url()
        except Exception:
            _LOGGER.exception("Error retrieving login URL from ThinQ")

        return login_url

    def get_auth_info_from_url(self, callback_url) -> Dict[str, str]:

        oauth_info = None
        try:
            if self._use_api_v2:
                oauth_info = ClientV2.oauthinfo_from_url(callback_url)
            else:
                oauth_info = Client.oauthinfo_from_url(callback_url)
        except Exception:
            _LOGGER.exception("Error retrieving OAuth info from ThinQ")

        return oauth_info

    def create_client_from_login(self, username, password):
        """Create a new client using username and password."""
        if not self._use_api_v2:
            return None
        return ClientV2.from_login(username, password, self._region, self._language)

    def create_client_from_token(self, token, oauth_url=None, oauth_user_num=None):
        """Create a new client using refresh token."""
        if self._use_api_v2:
            client = ClientV2.from_token(
                token, oauth_url, oauth_user_num, self._region, self._language
            )
        else:
            client = Client.from_token(token, self._region, self._language)

        return client


def is_valid_ha_version():
    return (
        MAJOR_VERSION > MIN_HA_MAJ_VER or
        (MAJOR_VERSION == MIN_HA_MAJ_VER and MINOR_VERSION >= MIN_HA_MIN_VER)
    )


def _notify_error(hass, notification_id, title, message):
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

    refresh_token = entry.data.get(CONF_TOKEN)
    region = entry.data.get(CONF_REGION)
    language = entry.data.get(CONF_LANGUAGE)
    use_api_v2 = entry.data.get(CONF_USE_API_V2, False)
    oauth_url = entry.data.get(CONF_OAUTH_URL)
    # oauth_user_num = entry.data.get(CONF_OAUTH_USER_NUM)
    use_tls_v1 = entry.data.get(CONF_USE_TLS_V1, False)
    exclude_dh = entry.data.get(CONF_EXCLUDE_DH, False)

    _LOGGER.info(STARTUP)
    _LOGGER.info(
        "Initializing ThinQ platform with region: %s - language: %s",
        region,
        language,
    )

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lge_auth = LGEAuthentication(region, language, use_api_v2)
    lge_auth.init_http_adapter(use_tls_v1, exclude_dh)
    try:
        client = await hass.async_add_executor_job(
            lge_auth.create_client_from_token, refresh_token, oauth_url
        )
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

    if not client.hasdevices:
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

    if not use_api_v2:
        _LOGGER.warning(
            "Integration configuration is using ThinQ APIv1 that is obsolete"
            " and not able to manage all ThinQ devices."
            " Please remove and re-add integration from HA user interface to"
            " enable the use of ThinQ APIv2"
        )

    # remove device not available anymore
    await cleanup_orphan_lge_devices(hass, entry.entry_id, client)

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
    def available_features(self) -> Dict:
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
            data[ATTR_SW_VERSION] = self._firmware
        if self._mac:
            data["connections"] = {(CONNECTION_NETWORK_MAC, self._mac)}

        return data

    @property
    def coordinator(self):
        return self._coordinator

    async def init_device(self):
        """Init the device status and start coordinator."""
        result = await self._hass.async_add_executor_job(
            self._device.init_device_info
        )
        if not result:
            return False
        self._state = self._device.status
        self._model = f"{self._model}-{self._device.model_info.model_type}"

        # Create status update coordinator
        await self._create_coordinator()

        # Initialize device features
        _ = self._state.device_features

        return True

    async def _create_coordinator(self):
        """Get the coordinator for a specific device."""
        coordinator = DataUpdateCoordinator(
            self._hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._name}",
            update_method=self.async_device_update,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=SCAN_INTERVAL
        )
        await coordinator.async_refresh()
        self._coordinator = coordinator

    async def async_device_update(self):
        """Async Update device state"""
        await self._hass.async_add_executor_job(self._device_update)
        return self._state

    def _device_update(self):
        """Update device state"""
        _LOGGER.debug("Updating ThinQ device %s", self._name)
        if self._disc_count < MAX_DISC_COUNT:
            self._disc_count += 1

        try:
            # method poll should return None if status is not yet available
            # or due to temporary connection failure that will be restored
            state = self._device.poll()

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


async def lge_devices_setup(hass, client):
    """Query connected devices from LG ThinQ."""
    _LOGGER.info("Starting LGE ThinQ devices...")

    wrapped_devices = {}
    unsupported_devices = {}
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


async def cleanup_orphan_lge_devices(hass, entry_id, client):
    """Delete devices that are not registered in LG client app"""

    # Load lg devices from registry
    device_registry = await hass.helpers.device_registry.async_get_registry()
    all_lg_dev_entries = (
        hass.helpers.device_registry.async_entries_for_config_entry(
            device_registry, entry_id
        )
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
