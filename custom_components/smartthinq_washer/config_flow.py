"""Config flow for TP-Link."""
import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_REGION, CONF_TOKEN
from .const import DOMAIN, CONF_LANGUAGE 
from . import LGEAuthentication

CONF_LOGIN = "login_url"
CONF_URL = "callback_url"

INIT_SCHEMA = vol.Schema({
    vol.Required(CONF_REGION): str,
    vol.Required(CONF_LANGUAGE): str,
    vol.Optional(CONF_TOKEN): str,
})

_LOGGER = logging.getLogger(__name__)

class SmartThinQFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle SmartThinQ config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize flow."""
        self._region = None
        self._language = None
        self._token = None
        self._loginurl = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user interface"""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if not user_input:
            return self._show_form()

        region = user_input[CONF_REGION]
        language = user_input[CONF_LANGUAGE]
        refresh_token = user_input.get(CONF_TOKEN, "")

        region_regex = re.compile(r"^[A-Z]{2,3}$")
        if not region_regex.match(region):
            return self._show_form({"base": "invalid_region"})
            
        language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
        if not language_regex.match(language):
            return self._show_form({"base": "invalid_language"})
        
        self._region = region
        self._language = language
        self._token = refresh_token

        if not self._token:
            lgauth = LGEAuthentication(self._region, self._language)
            self._loginurl = await self.hass.async_add_executor_job(
                    lgauth.getLoginUrl
                )
            return self._show_form(errors=None, step_id="url")

        return await self._save_config_entry()

    async def async_step_url(self, user_input=None):

        lgauth = LGEAuthentication(self._region, self._language)
        url = user_input[CONF_URL]
        token = await self.hass.async_add_executor_job(
                lgauth.getTokenFromUrl, url
            )
        if not token:
            return self._show_form(errors={"base": "invalid_url"}, step_id="url")

        self._token = token
        return self._show_form(errors=None, step_id="token")

    async def async_step_token(self, user_input=None):
        self._token = user_input[CONF_TOKEN]
        return await self._save_config_entry()

    async def _save_config_entry(self):
        # Test the connection to the SmartThinQ.
        lgauth = LGEAuthentication(self._region, self._language)
        client = await self.hass.async_add_executor_job(
                        lgauth.createClientFromToken, self._token
            )
            
        if not client:
            _LOGGER.error("LGE Washer: Invalid Login info!")
            return self._show_form({"base": "invalid_credentials"})

        if not client.hasdevices:
            _LOGGER.error("No SmartThinQ devices found. Component setup aborted.")
            return self.async_abort(reason="no_smartthinq_devices")

        return self.async_create_entry(
            title="LGE Washers",
            data={
                CONF_TOKEN: self._token,
                CONF_REGION: self._region,
                CONF_LANGUAGE: self._language
            }
        )

    @callback
    def _show_form(self, errors=None, step_id="user"):
        """Show the form to the user."""
        schema = INIT_SCHEMA

        if step_id == "url":
            schema = vol.Schema({
                vol.Required(CONF_LOGIN, default=self._loginurl): str,
                vol.Required(CONF_URL): str,
            })
        elif step_id == "token":
            schema = vol.Schema({
                vol.Required(CONF_TOKEN, default=self._token): str,
            })

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors if errors else {},
        )

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        if self._async_current_entries():
            _LOGGER.debug("SmartThinQ configuration already present / imported.")
            return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_user(import_config)



