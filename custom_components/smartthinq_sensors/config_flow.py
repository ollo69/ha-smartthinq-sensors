"""Config flow for TP-Link."""
import logging
import pycountry
import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_REGION, CONF_TOKEN

from .const import (
    DOMAIN,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_OAUTH_USER_NUM,
    CONF_USE_API_V2,
)
from . import LGEAuthentication

CONF_LOGIN = "login_url"
CONF_URL = "callback_url"

INIT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION): str,
        vol.Required(CONF_LANGUAGE): str,
        # vol.Optional(CONF_TOKEN): str,
        # vol.Required(CONF_USE_API_V2, default=True): bool,
    }
)

_LOGGER = logging.getLogger(__name__)


def _countries_list():
    """Returns a list of countries, suitable for use in a multiple choice field."""
    countries = {}
    for country in sorted(pycountry.countries, key=lambda x: x.name):
        countries[country.alpha_2] = f"{country.name} - {country.alpha_2}"
    return countries


def _languages_list():
    """Returns a list of languages, suitable for use in a multiple choice field."""
    languages = {}
    for language in sorted(pycountry.languages, key=lambda x: x.name):
        if hasattr(language, "alpha_2"):
            languages[language.alpha_2] = f"{language.name} - {language.alpha_2}"
    return languages


class SmartThinQFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle SmartThinQ config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize flow."""
        self._region = None
        self._language = None
        self._token = None
        self._oauth_url = None
        self._oauth_user_num = None
        self._use_api_v2 = True

        self._loginurl = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user interface"""

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if not user_input:
            return self._show_form()

        region = user_input[CONF_REGION]
        language = user_input[CONF_LANGUAGE]
        refresh_token = user_input.get(CONF_TOKEN, "")
        # self._use_api_v2 = user_input.get(CONF_USE_API_V2, False)

        if self._use_api_v2:
            refresh_token = ""

        region_regex = re.compile(r"^[A-Z]{2,3}$")
        if not region_regex.match(region):
            return self._show_form({"base": "invalid_region"})

        if len(language) == 2:
            language_regex = re.compile(r"^[a-z]{2,3}$")
        else:
            language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
        if not language_regex.match(language):
            return self._show_form({"base": "invalid_language"})

        self._region = region
        self._language = language
        if len(language) == 2:
            self._language += "-" + region
        self._token = refresh_token

        if not self._token:
            lgauth = LGEAuthentication(self._region, self._language, self._use_api_v2)
            self._loginurl = await self.hass.async_add_executor_job(lgauth.getLoginUrl)
            return self._show_form(errors=None, step_id="url")

        return await self._save_config_entry()

    async def async_step_url(self, user_input=None):
        """Parse the response url for oauth data and submit for save."""

        lgauth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        url = user_input[CONF_URL]
        oauth_info = await self.hass.async_add_executor_job(
            lgauth.getOAuthInfoFromUrl, url
        )
        if not oauth_info:
            return self._show_form(errors={"base": "invalid_url"}, step_id="url")

        self._token = oauth_info["refresh_token"]
        self._oauth_url = oauth_info.get("oauth_url")
        self._oauth_user_num = oauth_info.get("user_number")

        if self._use_api_v2:
            return await self._save_config_entry()

        return self._show_form(errors=None, step_id="token")

    async def async_step_token(self, user_input=None):
        """Show result token and submit for save."""
        self._token = user_input[CONF_TOKEN]
        return await self._save_config_entry()

    async def _save_config_entry(self):
        """Test the connection to the SmartThinQ and save the entry."""

        lgauth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        client = await self.hass.async_add_executor_job(
            lgauth.createClientFromToken,
            self._token,
            self._oauth_url,
            self._oauth_user_num,
        )

        if not client:
            _LOGGER.error("LGE ThinQ: Invalid Login info!")
            return self._show_form({"base": "invalid_credentials"})

        if not client.hasdevices:
            _LOGGER.error("No SmartThinQ devices found. Component setup aborted.")
            return self.async_abort(reason="no_smartthinq_devices")

        data = {
            CONF_TOKEN: self._token,
            CONF_REGION: self._region,
            CONF_LANGUAGE: self._language,
            CONF_USE_API_V2: self._use_api_v2,
        }
        if self._use_api_v2:
            data.update(
                {
                    CONF_OAUTH_URL: self._oauth_url,
                    CONF_OAUTH_USER_NUM: self._oauth_user_num,
                }
            )

        return self.async_create_entry(title="LGE Devices", data=data,)

    @callback
    def _show_form(self, errors=None, step_id="user"):
        """Show the form to the user."""
        schema = INIT_SCHEMA

        if step_id == "user":
            schema = vol.Schema(
                {
                    # vol.Required(CONF_REGION): str,
                    vol.Required(CONF_REGION): vol.In(_countries_list()),
                    # vol.Required(CONF_LANGUAGE): str,
                    vol.Required(CONF_LANGUAGE): vol.In(_languages_list()),
                }
            )
        elif step_id == "url":
            schema = vol.Schema(
                {
                    vol.Required(CONF_LOGIN, default=self._loginurl): str,
                    vol.Required(CONF_URL): str,
                }
            )
        elif step_id == "token":
            schema = vol.Schema({vol.Required(CONF_TOKEN, default=self._token): str})

        return self.async_show_form(
            step_id=step_id, data_schema=schema, errors=errors if errors else {},
        )

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        if self._async_current_entries():
            _LOGGER.debug("SmartThinQ configuration already present / imported.")
            return self.async_abort(reason="single_instance_allowed")

        _LOGGER.warning(
            "Integration configuration using configuration.yaml is not supported."
            " Please configure integration from HA user interface"
        )
        return self.async_abort(reason="single_instance_allowed")

        # self._use_api_v2 = False
        # return await self.async_step_user(import_config)
