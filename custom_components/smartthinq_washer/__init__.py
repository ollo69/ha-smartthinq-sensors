"""
Support for LG Smartthinq washer device.
"""
#REQUIREMENTS = ['wideq']

import asyncio
import logging

from .wideq.core import Client
from .wideq.core_v2 import ClientV2

from .wideq.core_exceptions import(
    NotConnectedError,
    TokenError,
)

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.exceptions import ConfigEntryNotReady

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
)

SMARTTHINQ_SCHEMA = vol.Schema({
    vol.Required(CONF_TOKEN): str,
    vol.Required(CONF_REGION): str,
    vol.Required(CONF_LANGUAGE): str,
})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: SMARTTHINQ_SCHEMA
    }, 
    extra=vol.ALLOW_EXTRA
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
        except:
            pass
            
        return login_url

    def getOAuthInfoFromUrl(self, callback_url) -> str:

        refresh_token = None
        client = self._create_client()

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
        
    def createClientFromToken(self, token, oauth_url = None, oauth_user_num = None):

        client = None
        try:
            if self._use_api_v2:
                client = ClientV2.from_token(oauth_url, token, oauth_user_num, self._region, self._language)
            else:
                client = Client.from_token(token, self._region, self._language)
        except Exception as ex:
            _LOGGER.error(ex)
            pass

        return client


async def async_setup_entry(hass: HomeAssistantType, config_entry):
    """
    This class is called by the HomeAssistant framework when a configuration entry is provided.
    For us, the configuration entry is the username-password credentials that the user
    needs to access the Meross cloud.
    """

    refresh_token = config_entry.data.get(CONF_TOKEN)
    region = config_entry.data.get(CONF_REGION)
    language = config_entry.data.get(CONF_LANGUAGE)
    use_apiv2 = config_entry.data.get(CONF_USE_API_V2, False)
    oauth_url = config_entry.data.get(CONF_OAUTH_URL)
    oauth_user_num = config_entry.data.get(CONF_OAUTH_USER_NUM)

    _LOGGER.info("Initializing smartthinq platform with region: %s - language: %s", region, language)

    hass.data.setdefault(DOMAIN, {})[LGE_DEVICES] = {}

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lgeauth = LGEAuthentication(region, language, use_apiv2)
    client = await hass.async_add_executor_job(
            lgeauth.createClientFromToken, refresh_token, oauth_url, oauth_user_num
        )
    if not client:
        _LOGGER.warning('Connection not available. SmartthinQ platform not ready.')
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
    This method gets called if HomeAssistant has a valid meross_cloud: configuration entry within
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
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT},
                data=conf
            )
        )

    return True

class LGEDevice(Entity):

    def __init__(self, client, device):
        self._client = client
        self._device = device
        
    @property
    def name(self):
        return self._device.name

    @property
    def available(self):
        return True
