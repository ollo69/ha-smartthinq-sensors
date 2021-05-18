"""
Support for LG SmartThinQ device.
"""
# REQUIREMENTS = ['wideq']

import asyncio
import logging
import time
from datetime import datetime, timedelta
from requests import exceptions as reqExc
from threading import Lock
from typing import Dict

from .wideq.core import Client
from .wideq.core_v2 import ClientV2, CoreV2HttpAdapter
from .wideq.device import UNIT_TEMP_CELSIUS, UNIT_TEMP_FAHRENHEIT, DeviceType
from .wideq.ac import AirConditionerDevice
from .wideq.dishwasher import DishWasherDevice
from .wideq.dryer import DryerDevice
from .wideq.range import RangeDevice
from .wideq.refrigerator import RefrigeratorDevice
from .wideq.styler import StylerDevice
from .wideq.washer import WasherDevice

from .wideq.core_exceptions import (
    InvalidCredentialError,
    NotConnectedError,
    NotLoggedInError,
    TokenError,
)

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import Throttle

from homeassistant.const import CONF_REGION, CONF_TOKEN, TEMP_CELSIUS

from .const import (
    CLIENT,
    CONF_EXCLUDE_DH,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_OAUTH_USER_NUM,
    CONF_USE_API_V2,
    CONF_USE_TLS_V1,
    DOMAIN,
    LGE_DEVICES,
    SMARTTHINQ_COMPONENTS,
    STARTUP,
)

ATTR_MODEL = "model"
ATTR_MAC_ADDRESS = "mac_address"

CLIMATE_DEVICE_TYPES = [
    DeviceType.AC,
]

MAX_RETRIES = 3
MAX_UPDATE_FAIL_ALLOWED = 10
MIN_TIME_BETWEEN_CLI_REFRESH = 10
# not stress to match cloud if multiple call
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

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

    def initHttpAdapter(self, use_tls_v1, exclude_dh):
        if self._use_api_v2:
            CoreV2HttpAdapter.init_http_adapter(use_tls_v1, exclude_dh)

    def getLoginUrl(self) -> str:

        login_url = None
        client = self._create_client()

        try:
            login_url = client.gateway.oauth_url()
        except Exception:
            _LOGGER.exception("Error retrieving login URL from ThinQ")

        return login_url

    def getOAuthInfoFromUrl(self, callback_url) -> Dict[str, str]:

        oauth_info = None
        try:
            if self._use_api_v2:
                oauth_info = ClientV2.oauthinfo_from_url(callback_url)
            else:
                oauth_info = Client.oauthinfo_from_url(callback_url)
        except Exception:
            _LOGGER.exception("Error retrieving OAuth info from ThinQ")

        return oauth_info

    def createClientFromToken(self, token, oauth_url=None, oauth_user_num=None):

        if self._use_api_v2:
            client = ClientV2.from_token(
                oauth_url, token, oauth_user_num, self._region, self._language
            )
        else:
            client = Client.from_token(token, self._region, self._language)

        return client


async def async_setup(hass, config):
    """
    This method gets called if HomeAssistant has a valid configuration entry within
    configurations.yaml.

    Thus, in this method we simply trigger the creation of a config entry.

    :return:
    """
    conf = config.get(DOMAIN)
    hass.data[DOMAIN] = {}

    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=conf
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry):
    """
    This class is called by the HomeAssistant framework when a configuration entry is provided.
    """

    refresh_token = config_entry.data.get(CONF_TOKEN)
    region = config_entry.data.get(CONF_REGION)
    language = config_entry.data.get(CONF_LANGUAGE)
    use_api_v2 = config_entry.data.get(CONF_USE_API_V2, False)
    oauth_url = config_entry.data.get(CONF_OAUTH_URL)
    oauth_user_num = config_entry.data.get(CONF_OAUTH_USER_NUM)
    use_tls_v1 = config_entry.data.get(CONF_USE_TLS_V1, False)
    exclude_dh = config_entry.data.get(CONF_EXCLUDE_DH, False)

    _LOGGER.info(STARTUP)
    _LOGGER.info(
        "Initializing ThinQ platform with region: %s - language: %s",
        region,
        language,
    )

    hass.data.setdefault(DOMAIN, {})[LGE_DEVICES] = {}

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lgeauth = LGEAuthentication(region, language, use_api_v2)
    lgeauth.initHttpAdapter(use_tls_v1, exclude_dh)
    try:
        client = await hass.async_add_executor_job(
            lgeauth.createClientFromToken, refresh_token, oauth_url, oauth_user_num
        )
    except InvalidCredentialError:
        _LOGGER.error("Invalid ThinQ credential error. Component setup aborted")
        return False

    except Exception:
        _LOGGER.warning(
            "Connection not available. ThinQ platform not ready", exc_info=True
        )
        raise ConfigEntryNotReady()

    if not client.hasdevices:
        _LOGGER.error("No ThinQ devices found. Component setup aborted")
        return False

    _LOGGER.info("ThinQ client connected")

    try:
        lge_devices = await lge_devices_setup(hass, client)
    except Exception:
        _LOGGER.warning(
            "Connection not available. ThinQ platform not ready", exc_info=True
        )
        raise ConfigEntryNotReady()

    if not use_api_v2:
        _LOGGER.warning(
            "Integration configuration is using ThinQ APIv1 that is obsolete"
            " and not able to manage all ThinQ devices."
            " Please remove and re-add integration from HA user interface to"
            " enable the use of ThinQ APIv2"
        )

    hass.data.setdefault(DOMAIN, {}).update(
        {CLIENT: client, LGE_DEVICES: lge_devices}
    )

    for platform in SMARTTHINQ_COMPONENTS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    return True


async def async_unload_entry(hass, config_entry):
    """Unload a config entry."""
    await asyncio.gather(
        *[
            hass.config_entries.async_forward_entry_unload(config_entry, platform)
            for platform in SMARTTHINQ_COMPONENTS
        ]
    )

    hass.data.pop(DOMAIN)

    return True


class LGEDevice:

    _client_lock = Lock()
    _client_connected = True
    _last_client_refresh = datetime.min

    def __init__(self, device, hass):
        """initialize a LGE Device."""

        self._device = device
        self._hass = hass
        self._name = device.device_info.name
        self._device_id = device.device_info.id
        self._type = device.device_info.type
        self._mac = device.device_info.macaddress or "N/A"
        self._firmware = device.device_info.firmware

        self._model = f"{device.device_info.model_name}"
        self._id = f"{self._type.name}:{self._device_id}"

        self._state = None
        self._coordinator = None
        self._disconnected = True
        self._not_logged = False
        self._available = True
        self._was_unavailable = False
        self._update_fail_count = 0
        self._not_logged_count = 0
        self._refresh_gateway = False

    @property
    def available(self) -> bool:
        return self._available

    @property
    def was_unavailable(self) -> bool:
        return self._was_unavailable

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._available and self._disconnected

    @property
    def device(self):
        return self._device

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> DeviceType:
        return self._type

    @property
    def unique_id(self) -> str:
        return self._id

    @property
    def state(self):
        return self._state

    @property
    def available_features(self) -> Dict:
        return self._device.available_features

    @property
    def state_attributes(self):
        """Return the optional state attributes."""
        data = {
            ATTR_MODEL: self._model,
            ATTR_MAC_ADDRESS: self._mac,
        }
        return data

    @property
    def device_info(self):
        data = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._name,
            "manufacturer": "LG",
            "model": f"{self._model} ({self._type.name})",
        }
        if self._firmware:
            data["sw_version"] = self._firmware

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
        features = self._state.device_features

        return True

    async def _create_coordinator(self):
        """Get the coordinator for a specific device."""
        should_poll = self._type not in CLIMATE_DEVICE_TYPES
        coordinator = DataUpdateCoordinator(
            self._hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._name}",
            update_method=self.async_device_update,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=SCAN_INTERVAL if should_poll else None,
        )
        await coordinator.async_refresh()
        self._coordinator = coordinator

    async def async_device_update(self):
        """Async Update device state"""
        await self._hass.async_add_executor_job(self._device_update)
        return self._state

    def _critical_status(self):
        return self._not_logged_count == MAX_UPDATE_FAIL_ALLOWED or (
            self._not_logged_count > 0 and self._not_logged_count % 60 == 0
        )

    def _set_available(self):
        """Set the available status."""
        if self._not_logged:
            self._not_logged_count += 1
        else:
            self._not_logged_count = 0
        available = self._not_logged_count <= MAX_UPDATE_FAIL_ALLOWED
        self._was_unavailable = available and not self._available
        self._available = available

    def _log_error(self, msg, *args, **kwargs):
        if self._critical_status():
            _LOGGER.error(msg, *args, **kwargs)
        else:
            _LOGGER.debug(msg, *args, **kwargs)

    def _refresh_client(self, refresh_gateway=False):
        """Refresh the devices shared client"""
        with LGEDevice._client_lock:
            call_time = datetime.now()
            difference = (call_time - LGEDevice._last_client_refresh).total_seconds()
            if difference <= MIN_TIME_BETWEEN_CLI_REFRESH:
                return LGEDevice._client_connected

            LGEDevice._last_client_refresh = datetime.now()
            LGEDevice._client_connected = False
            _LOGGER.debug("ThinQ session not connected. Trying to reconnect....")
            self._device.client.refresh(refresh_gateway)
            _LOGGER.debug("ThinQ session reconnected")
            LGEDevice._client_connected = True
            return True

    def _restart_monitor(self):
        """Restart the device monitor"""
        if not (self._disconnected or self._not_logged):
            return

        refresh_gateway = False
        if self._refresh_gateway:
            refresh_gateway = True
            self._refresh_gateway = False

        try:
            if self._not_logged:
                if not self._refresh_client(refresh_gateway):
                    return

                self._not_logged = False
                self._disconnected = True

            self._device.monitor_start()
            self._disconnected = False

        except NotConnectedError:
            self._log_error("Device %s not connected. Status not available", self._name)
            self._disconnected = True

        except NotLoggedInError:
            _LOGGER.warning("Connection to ThinQ not available, will be retried")
            self._not_logged = True

        except InvalidCredentialError:
            _LOGGER.error(
                "Invalid credential connecting to ThinQ. Reconfigure integration with valid login credential"
            )
            self._not_logged = True

        except (reqExc.ConnectionError, reqExc.ConnectTimeout, reqExc.ReadTimeout):
            self._log_error("Connection to ThinQ failed. Network connection error")
            self._disconnected = True
            self._not_logged = True

        except Exception:
            self._log_error("ThinQ error while updating device status", exc_info=True)
            self._not_logged = True

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def _device_update(self):
        """Update device state"""
        _LOGGER.debug("Updating ThinQ device %s", self._name)

        if self._disconnected or self._not_logged:
            if self._update_fail_count < MAX_UPDATE_FAIL_ALLOWED:
                self._update_fail_count += 1
            self._set_available()

        for iteration in range(MAX_RETRIES):
            _LOGGER.debug("Polling...")

            # Wait one second between iteration
            if iteration > 0:
                time.sleep(1)

            # Try to restart monitor
            self._restart_monitor()

            if self._disconnected or self._not_logged:
                if self._update_fail_count >= MAX_UPDATE_FAIL_ALLOWED:

                    if self._critical_status():
                        _LOGGER.error(
                            "Connection to ThinQ for device %s is not available. Connection will be retried",
                            self._name,
                        )
                        if self._not_logged_count >= 60:
                            self._refresh_gateway = True
                        self._set_available()

                    if self._state.is_on:
                        _LOGGER.warning(
                            "Status for device %s was reset because not connected",
                            self._name
                        )
                        self._state = self._device.reset_status()
                        return

                _LOGGER.debug("Connection not available. Status update failed")
                return

            try:
                state = self._device.poll()

            except NotLoggedInError:
                self._not_logged = True
                continue

            except NotConnectedError:
                self._disconnected = True
                return

            except InvalidCredentialError:
                _LOGGER.error(
                    "Invalid credential connecting to ThinQ. Reconfigure integration with valid login credential"
                )
                self._not_logged = True
                return

            except (
                reqExc.ConnectionError,
                reqExc.ConnectTimeout,
                reqExc.ReadTimeout,
            ):
                self._log_error(
                    "Connection to ThinQ failed. Network connection error"
                )
                self._not_logged = True
                return

            except Exception:
                self._log_error(
                    "ThinQ error while updating device status", exc_info=True
                )
                self._not_logged = True
                return

            else:
                if state:
                    _LOGGER.debug("ThinQ status updated")
                    # l = dir(state)
                    # _LOGGER.debug('Status attributes: %s', l)

                    self._update_fail_count = 0
                    self._set_available()
                    self._state = state

                    return
                else:
                    _LOGGER.debug("No status available yet")


async def lge_devices_setup(hass, client) -> dict:
    """Query connected devices from LG ThinQ."""
    _LOGGER.info("Starting LGE ThinQ devices...")

    wrapped_devices = {}
    device_count = 0
    temp_unit = UNIT_TEMP_CELSIUS
    if hass.config.units.temperature_unit != TEMP_CELSIUS:
        temp_unit = UNIT_TEMP_FAHRENHEIT

    for device in client.devices:
        device_id = device.id
        device_name = device.name
        device_type = device.type
        model_name = device.model_name
        device_count += 1

        dev = None
        if device_type in [DeviceType.WASHER, DeviceType.TOWER_WASHER]:
            dev = LGEDevice(WasherDevice(client, device), hass)
        elif device_type in [DeviceType.DRYER, DeviceType.TOWER_DRYER]:
            dev = LGEDevice(DryerDevice(client, device), hass)
        elif device_type == DeviceType.STYLER:
            dev = LGEDevice(StylerDevice(client, device), hass)
        elif device_type == DeviceType.DISHWASHER:
            dev = LGEDevice(DishWasherDevice(client, device), hass)
        elif device_type == DeviceType.REFRIGERATOR:
            dev = LGEDevice(RefrigeratorDevice(client, device), hass)
        elif device_type == DeviceType.AC:
            dev = LGEDevice(AirConditionerDevice(client, device, temp_unit), hass)
        elif device_type == DeviceType.RANGE:
            dev = LGEDevice(RangeDevice(client, device), hass)

        if not dev:
            _LOGGER.info(
                "Found unsupported LGE Device. Name: %s - Type: %s - InfoUrl: %s",
                device_name,
                device_type.name,
                device.model_info_url,
            )
            continue

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
    return wrapped_devices
