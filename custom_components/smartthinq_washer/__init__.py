"""
Support for LG SmartThinQ device.
"""
# REQUIREMENTS = ['wideq']

import asyncio
import logging
import time

from .wideq.core import Client
from .wideq.core_v2 import ClientV2

from .wideq.core_exceptions import (
    NotConnectedError,
    NotLoggedInError,
    TokenError,
)

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType

from homeassistant.const import CONF_REGION, CONF_TOKEN, STATE_ON, STATE_OFF

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
)

MAX_RETRIES = 3
MAX_CONN_RETRIES = 2
MAX_LOOP_WARN = 3

SMARTTHINQ_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Required(CONF_REGION): str,
        vol.Required(CONF_LANGUAGE): str,
    }
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: SMARTTHINQ_SCHEMA}, extra=vol.ALLOW_EXTRA)

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
        except:
            pass

        return login_url

    def getOAuthInfoFromUrl(self, callback_url) -> str:

        oauth_info = None
        try:
            if self._use_api_v2:
                oauth_info = ClientV2.oauthinfo_from_url(callback_url)
            else:
                oauth_info = Client.oauthinfo_from_url(callback_url)
        except Exception as ex:
            _LOGGER.error(ex)
            pass

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
        except Exception as ex:
            _LOGGER.error(ex)
            pass

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

    _LOGGER.info(
        "Initializing smartthinq platform with region: %s - language: %s",
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
        _LOGGER.warning("Connection not available. SmartthinQ platform not ready.")
        raise ConfigEntryNotReady()

    if not client.hasdevices:
        _LOGGER.error("No SmartThinQ devices found. Component setup aborted.")
        return False

    hass.data.setdefault(DOMAIN, {}).update({CLIENT: client})
    _LOGGER.info("Smartthinq client connected.")

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


class LGEDevice(Entity):
    def __init__(self, device, name):
        """initialize a LGE Device."""

        self._device = device
        self._name = name
        self._device_id = device.device_info.id
        self._mac = device.device_info.macaddress
        self._firmware = device.device_info.firmware

        self._model = device.device_info.model_name + "-" + device.model_info.model_type
        self._id = "%s:%s" % (device.type, self._device_id)

        self._state = None

        self._retry_count = 0
        self._disconnected = True
        self._not_logged = False

    @property
    def available(self):
        return True

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self) -> bool:
        # This sensors must be polled. We leave this task to the HomeAssistant engine
        return True

    @property
    def unique_id(self) -> str:
        return self._id

    @property
    def device_info(self):
        data = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._name,
            "manufacturer": "LG",
            "model": "%s (%s)" % (self._model, self._device.type),
        }
        if self._firmware:
            data["sw_version"] = self._firmware

        return data

    @property
    def state(self):
        if self._state:
            if self._state.is_on:
                return STATE_ON
        return STATE_OFF

    def _restart_monitor(self):
        """Restart the device monitor"""

        try:
            if self._not_logged:
                self._device.client.refresh()
                self._not_logged = False
                self._disconnected = True

            self._device.monitor_start()
            # self._device.delete_permission()
            self._disconnected = False

        except NotConnectedError:
            _LOGGER.debug("Device not connected. Status not available.")
            self._disconnected = True
            # self._state = None

        except NotLoggedInError:
            _LOGGER.info("Session expired. Refreshing.")
            # self._client.refresh()
            self._not_logged = True

        except Exception as ex:
            self._not_logged = True
            raise ex

    def update(self):
        """Update device state"""
        _LOGGER.debug("Updating smartthinq device %s.", self.name)

        for iteration in range(MAX_RETRIES):
            _LOGGER.debug("Polling...")

            if self._disconnected or self._not_logged:
                if iteration >= MAX_CONN_RETRIES and iteration > 0:
                    _LOGGER.debug("Connection not available. Status update failed.")
                    return

                self._retry_count = 0
                self._restart_monitor()

            if self._disconnected:
                return

            if not (self._disconnected or self._not_logged):
                try:
                    state = self._device.poll()

                except NotLoggedInError:
                    # self._client.refresh()
                    # self._restart_monitor()
                    self._not_logged = True

                except NotConnectedError:
                    self._disconnected = True
                    return
                    # time.sleep(1)

                except Exception as ex:
                    self._not_logged = True
                    raise ex

                else:
                    if state:
                        _LOGGER.debug("Status updated: %s", state.run_state)
                        # l = dir(state)
                        # _LOGGER.debug('Status attributes: %s', l)

                        self._retry_count = 0
                        self._state = state

                        return
                    else:
                        _LOGGER.debug("No status available yet.")

            # time.sleep(2 ** iteration)
            time.sleep(1)

        # We tried several times but got no result. This might happen
        # when the monitoring request gets into a bad state, so we
        # restart the task.
        if self._retry_count >= MAX_LOOP_WARN:
            self._retry_count = 0
            _LOGGER.warn("Status update failed.")
        else:
            self._retry_count += 1
            _LOGGER.debug("Status update failed.")
