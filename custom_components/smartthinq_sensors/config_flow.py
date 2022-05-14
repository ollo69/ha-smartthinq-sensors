"""Config flow for LG SmartThinQ."""
from __future__ import annotations

import logging
import re
from pycountry import countries as py_countries, languages as py_languages

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_BASE,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_TOKEN,
    CONF_USERNAME,
    __version__,
)

from .const import (
    DOMAIN,
    CONF_EXCLUDE_DH,
    CONF_LANGUAGE,
    CONF_OAUTH_URL,
    CONF_USE_API_V2,
    CONF_USE_TLS_V1,
    __min_ha_version__,
)
from . import LGEAuthentication, is_valid_ha_version

CONF_LOGIN = "login_url"
CONF_URL = "callback_url"
CONF_USE_REDIRECT = "use_redirect"

RESULT_SUCCESS = 0
RESULT_FAIL = 1
RESULT_NO_DEV = 2

_LOGGER = logging.getLogger(__name__)

COUNTRIES = {
    country.alpha_2: f"{country.name} - {country.alpha_2}"
    for country in sorted(py_countries, key=lambda x: x.name)
}

LANGUAGES = {
    language.alpha_2: f"{language.name} - {language.alpha_2}"
    for language in sorted(py_languages, key=lambda x: x.name)
    if hasattr(language, "alpha_2")
}


class SmartThinQFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle SmartThinQ config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize flow."""
        self._region: str | None = None
        self._language: str | None = None
        self._token: str | None = None
        self._oauth_url: str | None = None
        self._use_api_v2 = True
        self._use_tls_v1 = False
        self._exclude_dh = False

        self._user_lang: str | None = None
        self._login_url: str | None = None
        self._error: str | None = None

    @staticmethod
    def _validate_region_language(region, language):
        """Validate format of region and language."""
        region_regex = re.compile(r"^[A-Z]{2,3}$")
        if not region_regex.match(region):
            return "invalid_region"

        if len(language) == 2:
            language_regex = re.compile(r"^[a-z]{2,3}$")
        else:
            language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
        if not language_regex.match(language):
            return "invalid_language"

        return None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user interface"""

        if not is_valid_ha_version():
            return self.async_abort(
                reason="unsupported_version",
                description_placeholders={
                    "req_ver": __min_ha_version__, "run_ver": __version__
                },
            )

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if not user_input:
            return self._show_form()

        username = user_input.get(CONF_USERNAME)
        password = user_input.get(CONF_PASSWORD)
        region = user_input[CONF_REGION]
        language = user_input[CONF_LANGUAGE]
        use_redirect = user_input[CONF_USE_REDIRECT]
        self._use_api_v2 = user_input.get(CONF_USE_API_V2, True)
        self._use_tls_v1 = user_input.get(CONF_USE_TLS_V1, False)
        self._exclude_dh = user_input.get(CONF_EXCLUDE_DH, False)

        if not self._use_api_v2:
            use_redirect = True

        if error := self._validate_region_language(region, language):
            return self._show_form(errors=error)
        self._region = region
        self._user_lang = language
        self._language = language
        if len(language) == 2:
            self._language += f"-{region}"

        if not use_redirect and not (username and password):
            return self._show_form(errors="no_user_info")

        lge_auth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        lge_auth.init_http_adapter(self._use_tls_v1, self._exclude_dh)
        if not use_redirect:
            client, result = await self._check_connection(username, password)
            if result != RESULT_SUCCESS:
                return await self._manage_error(result, True)
            auth_info = client.oauth_info
            self._token = auth_info["refresh_token"]
            self._oauth_url = auth_info["oauth_url"]
            return self._save_config_entry()

        self._login_url = await self.hass.async_add_executor_job(lge_auth.get_login_url)
        if not self._login_url:
            return self._show_form(errors="error_url")
        return await self.async_step_url()

    async def async_step_url(self, user_input=None):
        """Parse the response url for oauth data and submit for save."""
        if not user_input:
            return self._show_form(step_id="url")

        lge_auth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        url = user_input[CONF_URL]
        oauth_info = await self.hass.async_add_executor_job(
            lge_auth.get_auth_info_from_url, url
        )
        if not oauth_info:
            return self._show_form(errors="invalid_url", step_id="url")

        self._token = oauth_info["refresh_token"]
        self._oauth_url = oauth_info.get("oauth_url")

        if not self._oauth_url and self._use_api_v2:
            return self._show_form(errors="invalid_url", step_id="url")
        _, result = await self._check_connection()
        if result != RESULT_SUCCESS:
            return await self._manage_error(result)
        return self._save_config_entry()

    async def _check_connection(self, username=None, password=None):
        """Test the connection to ThinQ."""

        lge_auth = LGEAuthentication(self._region, self._language, self._use_api_v2)
        try:
            if username and password:
                client = await self.hass.async_add_executor_job(
                    lge_auth.create_client_from_login,
                    username,
                    password,
                )
            else:
                client = await self.hass.async_add_executor_job(
                    lge_auth.create_client_from_token,
                    self._token,
                    self._oauth_url,
                )
        except Exception as exc:
            _LOGGER.exception("Error connecting to ThinQ", exc_info=exc)
            return None, RESULT_FAIL

        if not client:
            return None, RESULT_NO_DEV

        if not client.has_devices:
            return None, RESULT_NO_DEV

        return client, RESULT_SUCCESS

    async def _manage_error(self, error_code, is_user_step=False):
        """Manage the error result."""
        if error_code == RESULT_NO_DEV:
            return self.async_abort(reason="no_smartthinq_devices")

        self._error = "unknown"
        if error_code == RESULT_FAIL:
            self._error = "invalid_credentials"

        if is_user_step:
            return self._show_form()
        return await self.async_step_user()

    @callback
    def _save_config_entry(self):
        """Save the entry."""

        data = {
            CONF_REGION: self._region,
            CONF_LANGUAGE: self._language,
            CONF_TOKEN: self._token,
            CONF_USE_API_V2: self._use_api_v2,
            CONF_USE_TLS_V1: self._use_tls_v1,
            CONF_EXCLUDE_DH: self._exclude_dh,
        }
        if self._use_api_v2:
            data[CONF_OAUTH_URL] = self._oauth_url

        return self.async_create_entry(title="LGE Devices", data=data)

    @callback
    def _prepare_form_schema(self, step_id="user"):
        """Prepare the user forms schema."""
        if step_id == "url":
            return vol.Schema(
                {
                    vol.Required(CONF_LOGIN, default=self._login_url): str,
                    vol.Required(CONF_URL): str,
                }
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Required(CONF_REGION, default=self._region or ""): vol.In(COUNTRIES),
                vol.Required(CONF_LANGUAGE, default=self._user_lang or ""): vol.In(LANGUAGES),
                vol.Required(CONF_USE_REDIRECT, default=False): bool,
                # vol.Required(CONF_USE_API_V2, default=self._use_api_v2): bool,
            }
        )
        if self.show_advanced_options:
            schema = schema.extend(
                {
                    vol.Optional(CONF_USE_TLS_V1, default=False): bool,
                    vol.Optional(CONF_EXCLUDE_DH, default=False): bool,
                }
            )

        return schema

    @callback
    def _show_form(self, errors: str | None = None, step_id="user"):
        """Show the form to the user."""
        base_err = errors or self._error
        self._error = None
        schema = self._prepare_form_schema(step_id)

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors={CONF_BASE: base_err} if base_err else None,
        )
