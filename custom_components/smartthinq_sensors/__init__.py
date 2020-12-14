"""
Support for LG SmartThinQ device.
"""
# REQUIREMENTS = ['wideq']

import asyncio
import logging
import time
from datetime import timedelta
from requests import exceptions as reqExc
from typing import Dict

from .wideq.core import Client
from .wideq.core_v2 import ClientV2
from .wideq.device import DeviceType
from .wideq.dishwasher import DishWasherDevice
from .wideq.dryer import DryerDevice
from .wideq.washer import WasherDevice
from .wideq.refrigerator import RefrigeratorDevice

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
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import Throttle

from homeassistant.const import CONF_REGION, CONF_TOKEN

from .const import (
    ATTR_CONFIG,
    CLIENT,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_OAUTH_USER_NUM,
    CONF_USE_API_V2,
    DOMAIN,
    LGE_DEVICES,
    SMARTTHINQ_COMPONENTS,
    STARTUP,
)

ATTR_MODEL = "model"
ATTR_MAC_ADDRESS = "mac_address"

MAX_RETRIES = 3
MAX_CONN_RETRIES = 2
MAX_LOOP_WARN = 3
MAX_UPDATE_FAIL_ALLOWED = 10
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

        client = None
        try:
            if self._use_api_v2:
                client = ClientV2.from_token(
                    oauth_url, token, oauth_user_num, self._region, self._language
                )
            else:
                client = Client.from_token(token, self._region, self._language)
        except Exception:
            _LOGGER.exception("Error connecting to ThinQ")

        return client


async def async_setup_entry(hass: HomeAssistantType, config_entry):
    """
    This class is called by the HomeAssistant framework when a configuration entry is provided.
    """

    refresh_token = config_entry.data.get(CONF_TOKEN)
    region = config_entry.data.get(CONF_REGION)
    language = config_entry.data.get(CONF_LANGUAGE)
    use_apiv2 = config_entry.data.get(CONF_USE_API_V2, False)
    oauth_url = config_entry.data.get(CONF_OAUTH_URL)
    oauth_user_num = config_entry.data.get(CONF_OAUTH_USER_NUM)

    _LOGGER.info(STARTUP)
    _LOGGER.info(
        "Initializing SmartThinQ platform with region: %s - language: %s",
        region,
        language,
    )

    hass.data.setdefault(DOMAIN, {})[LGE_DEVICES] = {}

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lgeauth = LGEAuthentication(region, language, use_apiv2)
    client = await hass.async_add_executor_job(
        lgeauth.createClientFromToken, refresh_token, oauth_url, oauth_user_num
    )
    if not client:
        _LOGGER.warning("Connection not available. SmartThinQ platform not ready")
        raise ConfigEntryNotReady()

    if not client.hasdevices:
        _LOGGER.error("No SmartThinQ devices found. Component setup aborted")
        return False

    _LOGGER.info("SmartThinQ client connected")

    try:
        lge_devices = await lge_devices_setup(hass, client)
    except Exception:
        _LOGGER.warning(
            "Connection not available. SmartThinQ platform not ready", exc_info=True,
        )
        raise ConfigEntryNotReady()

    if not use_apiv2:
        _LOGGER.warning(
            "Integration configuration is using ThinQ APIv1 that is obsolete"
            " and not able to manage all ThinQ devices."
            " Please remove and re-add integration from HA user interface to"
            " enable the use of ThinQ APIv2"
        )

    hass.data.setdefault(DOMAIN, {}).update(
        {CLIENT: client, LGE_DEVICES: lge_devices,}
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


async def async_setup(hass, config):
    """
    This method gets called if HomeAssistant has a valid configuration entry within
    configurations.yaml.

    Thus, in this method we simply trigger the creation of a config entry.

    :return:
    """
    conf = config.get(DOMAIN)
    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][ATTR_CONFIG] = conf

    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=conf
            )
        )

    return True


class LGEDevice:
    def __init__(self, device, name):
        """initialize a LGE Device."""

        self._device = device
        self._name = name
        self._device_id = device.device_info.id
        self._type = device.device_info.type
        self._mac = device.device_info.macaddress
        self._firmware = device.device_info.firmware

        self._model = f"{device.device_info.model_name}"
        self._id = f"{self._type.name}:{self._device_id}"

        self._state = None
        self._retry_count = 0
        self._disconnected = True
        self._not_logged = False
        self._update_fail_count = 0
        self._not_logged_count = 0
        self._refresh_gateway = False

    @property
    def available(self) -> bool:
        return self._not_logged_count <= MAX_UPDATE_FAIL_ALLOWED

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self.available and self._disconnected

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

    def init_device(self):
        if self._device.init_device_info():
            self._state = self._device.status
            self._model = f"{self._model}-{self._device.model_info.model_type}"
            return True
        return False

    def _critical_status(self):
        return self._not_logged_count == MAX_UPDATE_FAIL_ALLOWED or (
            self._not_logged_count > 0 and self._not_logged_count % 60 == 0
        )

    def _log_error(self, msg, *args, **kwargs):
        if self._critical_status():
            _LOGGER.error(msg, *args, **kwargs)
        else:
            _LOGGER.debug(msg, *args, **kwargs)

    def _restart_monitor(self):
        """Restart the device monitor"""

        refresh_gateway = False
        if self._refresh_gateway:
            refresh_gateway = True
            self._refresh_gateway = False

        try:
            if self._not_logged:
                self._device.client.refresh(refresh_gateway)
                self._not_logged = False
                self._disconnected = True

            self._device.monitor_start()
            self._disconnected = False

        except NotConnectedError:
            self._log_error("Device not connected. Status not available")
            self._disconnected = True

        except NotLoggedInError:
            self._log_error("ThinQ Session expired. Refreshing")
            self._not_logged = True

        except InvalidCredentialError:
            self._log_error("Connection to ThinQ failed. Check your login credential")
            self._not_logged = True

        except (reqExc.ConnectionError, reqExc.ConnectTimeout, reqExc.ReadTimeout):
            self._log_error("Connection to ThinQ failed. Network connection error")
            self._disconnected = True
            self._not_logged = True

        except Exception:
            self._log_error("ThinQ error while updating device status", exc_info=True)
            self._not_logged = True

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def device_update(self):
        """Update device state"""
        _LOGGER.debug("Updating smartthinq device %s", self.name)

        if self._disconnected or self._not_logged:
            if self._update_fail_count < MAX_UPDATE_FAIL_ALLOWED:
                self._update_fail_count += 1
            if self._not_logged:
                self._not_logged_count += 1
            else:
                self._not_logged_count = 0

        for iteration in range(MAX_RETRIES):
            _LOGGER.debug("Polling...")

            if self._disconnected or self._not_logged:
                if iteration >= MAX_CONN_RETRIES and iteration > 0:
                    _LOGGER.debug("Connection not available. Status update failed")
                    return

                self._retry_count = 0
                self._restart_monitor()

            if self._disconnected or self._not_logged:
                if self._update_fail_count >= MAX_UPDATE_FAIL_ALLOWED:

                    if self._critical_status():
                        _LOGGER.error(
                            "Connection to ThinQ for device %s is not available. Connection will be retried",
                            self.name,
                        )
                        if self._not_logged_count >= 60:
                            self._refresh_gateway = True
                        self._not_logged_count += 1

                    if self._state.is_on:
                        self._state = self._device.reset_status()
                        return

            if self._disconnected:
                return

            if not (self._disconnected or self._not_logged):

                try:
                    state = self._device.poll()

                except NotLoggedInError:
                    self._not_logged = True

                except NotConnectedError:
                    self._disconnected = True
                    return
                    # time.sleep(1)

                except InvalidCredentialError:
                    self._log_error(
                        "Connection to ThinQ failed. Check your login credential"
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
                        self._not_logged_count = 0
                        self._retry_count = 0
                        self._state = state

                        return
                    else:
                        _LOGGER.debug("No status available yet")

            # time.sleep(2 ** iteration)
            time.sleep(1)

        # We tried several times but got no result. This might happen
        # when the monitoring request gets into a bad state, so we
        # restart the task.
        if self._retry_count >= MAX_LOOP_WARN:
            self._retry_count = 0
            _LOGGER.warning("Status update failed")
        else:
            self._retry_count += 1
            _LOGGER.debug("Status update failed")


async def lge_devices_setup(hass, client) -> dict:
    """Query connected devices from LG ThinQ."""
    _LOGGER.info("Starting LGE ThinQ devices...")

    wrapped_devices = {}
    device_count = 0

    for device in client.devices:
        device_id = device.id
        device_name = device.name
        device_type = device.type
        device_mac = device.macaddress
        model_name = device.model_name
        dev = None
        result = False
        device_count += 1

        if device_type in [DeviceType.WASHER, DeviceType.TOWER_WASHER]:
            dev = LGEDevice(WasherDevice(client, device), device_name)
        elif device_type in [DeviceType.DRYER, DeviceType.TOWER_DRYER]:
            dev = LGEDevice(DryerDevice(client, device), device_name)
        elif device_type == DeviceType.DISHWASHER:
            dev = LGEDevice(DishWasherDevice(client, device), device_name)
        elif device_type == DeviceType.REFRIGERATOR:
            dev = LGEDevice(RefrigeratorDevice(client, device), device_name)

        if dev:
            result = await hass.async_add_executor_job(dev.init_device)

        if not result:
            _LOGGER.info(
                "Found unsupported LGE Device. Name: %s - Type: %s - InfoUrl: %s",
                device_name,
                device_type.name,
                device.model_info_url,
            )
            continue

        wrapped_devices.setdefault(device_type, []).append(dev)
        _LOGGER.info(
            "LGE Device added. Name: %s - Type: %s - Model: %s - Mac: %s - ID: %s",
            device_name,
            device_type.name,
            model_name,
            device_mac,
            device_id,
        )

    _LOGGER.info("Founds %s LGE device(s)", str(device_count))
    return wrapped_devices
