"""Config flow for TP-Link."""
import logging
import re
from pycountry import countries as py_countries, languages as py_languages

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_REGION, CONF_TOKEN, __version__

from .const import (
    DOMAIN,
    CONF_EXCLUDE_DH,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_OAUTH_USER_NUM,
    CONF_USE_API_V2,
    CONF_USE_TLS_V1,
    __min_ha_version__,
)
from . import LGEAuthentication, is_valid_ha_version

CONF_LOGIN = "login_url"
CONF_URL = "callback_url"

RESULT_SUCCESS = 0
RESULT_FAIL = 1
RESULT_NO_DEV = 2

_LOGGER = logging.getLogger(__name__)


def _countries_list():
    """Returns a list of countries, suitable for use in a multiple choice field."""
    countries = {}
    for country in sorted(py_countries, key=lambda x: x.name):
        countries[country.alpha_2] = f"{country.name} - {country.alpha_2}"
    return countries


def _languages_list():
    """Returns a list of languages, suitable for use in a multiple choice field."""
    languages = {}
    for language in sorted(py_languages, key=lambda x: x.name):
        if hasattr(language, "alpha_2"):
            languages[language.alpha_2] = f"{language.name} - {language.alpha_2}"
    return languages


INIT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION): vol.In(_countries_list()),
        vol.Required(CONF_LANGUAGE): vol.In(_languages_list()),
        # vol.Optional(CONF_TOKEN): str,
        # vol.Required(CONF_USE_API_V2, default=True): bool,
    }
)


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
        self._use_tls_v1 = False
        self._exclude_dh = False

        self._loginurl = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user interface"""

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if not is_valid_ha_version():
            return self.async_abort(
                reason="unsupported_version",
                description_placeholders={
                    "req_ver": __min_ha_version__, "run_ver": __version__
                },
            )

        if not user_input:
            return self._show_form()

        region = user_input[CONF_REGION]
        language = user_input[CONF_LANGUAGE]
        self._use_tls_v1 = user_input.get(CONF_USE_TLS_V1, False)
        self._exclude_dh = user_input.get(CONF_EXCLUDE_DH, False)

        region_regex = re.compile(r"^[A-Z]{2,3}$")
        if not region_regex.match(region):
            return self._show_form(errors={"base": "invalid_region"})

        if len(language) == 2:
            language_regex = re.compile(r"^[a-z]{2,3}$")
        else:
            language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
        if not language_regex.match(language):
            return self._show_form(errors={"base": "invalid_language"})

        self._region = region
        self._language = language
        if len(language) == 2:
            self._language += "-" + region

        lgauth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        lgauth.initHttpAdapter(self._use_tls_v1, self._exclude_dh)
        self._loginurl = await self.hass.async_add_executor_job(lgauth.getLoginUrl)
        if not self._loginurl:
            return self._show_form(errors={"base": "error_url"})
        return self._show_form(errors=None, step_id="url")

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
            result = await self._check_connection()
            if result != RESULT_SUCCESS:
                return self._manage_error(result)
            return self._save_config_entry()

        return self._show_form(errors=None, step_id="token")

    async def async_step_token(self, user_input=None):
        """Show result token and submit for save."""
        self._token = user_input[CONF_TOKEN]
        result = await self._check_connection()
        if result != RESULT_SUCCESS:
            return self._manage_error(result)
        return self._save_config_entry()

    async def _check_connection(self):
        """Test the connection to ThinQ."""

        lgauth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        try:
            client = await self.hass.async_add_executor_job(
                lgauth.createClientFromToken,
                self._token,
                self._oauth_url,
                self._oauth_user_num,
            )
        except Exception as ex:
            _LOGGER.error("Error connecting to ThinQ: %s", ex)
            return RESULT_FAIL

        if not client.hasdevices:
            return RESULT_NO_DEV

        return RESULT_SUCCESS

    @callback
    def _manage_error(self, error_code):
        """Manage the error result."""
        if error_code == RESULT_FAIL:
            _LOGGER.error("LGE ThinQ: Invalid Login info!")
            return self._show_form({"base": "invalid_credentials"})

        if error_code == RESULT_NO_DEV:
            _LOGGER.error("No SmartThinQ devices found. Component setup aborted.")
            return self.async_abort(reason="no_smartthinq_devices")

    @callback
    def _save_config_entry(self):
        """Save the entry."""

        data = {
            CONF_TOKEN: self._token,
            CONF_REGION: self._region,
            CONF_LANGUAGE: self._language,
            CONF_USE_API_V2: self._use_api_v2,
            CONF_USE_TLS_V1: self._use_tls_v1,
            CONF_EXCLUDE_DH: self._exclude_dh,
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
        schema = None
        if step_id == "user":
            schema = INIT_SCHEMA
            if self.show_advanced_options:
                schema = schema.extend(
                    {
                        vol.Optional(CONF_USE_TLS_V1, default=False): bool,
                        vol.Optional(CONF_EXCLUDE_DH, default=False): bool,
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
