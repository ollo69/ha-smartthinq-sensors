"""Config flow for LG SmartThinQ."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

from pycountry import countries as py_countries, languages as py_languages
import voluptuous as vol

from homeassistant.config_entries import (
    CONN_CLASS_CLOUD_POLL,
    SOURCE_REAUTH,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import (
    CONF_BASE,
    CONF_CLIENT_ID,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_TOKEN,
    CONF_USERNAME,
    __version__,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import LGEAuthentication, is_valid_ha_version
from .const import (
    CONF_LANGUAGE,
    CONF_OAUTH2_URL,
    CONF_USE_API_V2,
    CONF_USE_HA_SESSION,
    CONF_USE_REDIRECT,
    DOMAIN,
    __min_ha_version__,
)
from .wideq.core_exceptions import AuthenticationError, InvalidCredentialError

CONF_LOGIN = "login_url"
CONF_REAUTH_CRED = "reauth_cred"
CONF_URL = "callback_url"

RESULT_SUCCESS = 0
RESULT_FAIL = 1
RESULT_NO_DEV = 2
RESULT_CRED_FAIL = 3

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


class SmartThinQFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle SmartThinQ config flow."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize flow."""
        self._region: str | None = None
        self._language: str | None = None
        self._token: str | None = None
        self._client_id: str | None = None
        self._oauth2_url: str | None = None
        self._use_ha_session = False

        self._user_lang: str | None = None
        self._login_url: str | None = None
        self._error: str | None = None
        self._is_import = False

    @staticmethod
    def _validate_region_language(region: str, language: str) -> str | None:
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

    def _get_hass_region_lang(self) -> None:
        """Get the hass configured region and language."""
        if self._region and self._user_lang:
            return
        # This works starting from HA 2022.12
        ha_conf = self.hass.config
        if not self._region and hasattr(ha_conf, "country"):
            country = ha_conf.country
            if country and country in COUNTRIES:
                self._region = country
        if not self._user_lang and hasattr(ha_conf, "language"):
            language = ha_conf.language
            if language and language[0:2] in LANGUAGES:
                self._user_lang = language[0:2]

    async def async_step_import(
        self, import_config: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import a config entry."""
        self._is_import = True
        self._region = import_config.get(CONF_REGION)
        if language := import_config.get(CONF_LANGUAGE):
            self._user_lang = language[0:2]
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user interface"""

        if not is_valid_ha_version():
            return self.async_abort(
                reason="unsupported_version",
                description_placeholders={
                    "req_ver": __min_ha_version__,
                    "run_ver": __version__,
                },
            )

        if self._is_import:
            self._error = "invalid_config"
        elif entries := self._async_current_entries():
            entry = entries[0]
            if entry.state == ConfigEntryState.LOADED:
                return self.async_abort(reason="single_instance_allowed")
            if not self._region:
                self._region = entry.data.get(CONF_REGION)
            if not self._user_lang:
                if language := entry.data.get(CONF_LANGUAGE):
                    self._user_lang = language[0:2]

        if not user_input:
            self._get_hass_region_lang()
            return self._show_form()

        username = user_input.get(CONF_USERNAME)
        password = user_input.get(CONF_PASSWORD)
        region = user_input[CONF_REGION]
        language = user_input[CONF_LANGUAGE]
        use_redirect = user_input[CONF_USE_REDIRECT]
        self._use_ha_session = user_input.get(CONF_USE_HA_SESSION, False)

        if error := self._validate_region_language(region, language):
            return self._show_form(errors=error)
        self._region = region
        self._user_lang = language
        self._language = language
        if len(language) == 2:
            self._language += f"-{region}"

        if not use_redirect and not (username and password):
            if self.source == SOURCE_REAUTH and not (username or password):
                return await self.async_step_reauth_confirm()
            return self._show_form(errors="no_user_info")

        lge_auth = LGEAuthentication(
            self.hass, self._region, self._language, self._use_ha_session
        )
        if not use_redirect:
            oauth_info = await lge_auth.get_oauth_info_from_login(username, password)
            if not oauth_info:
                return await self._manage_error(RESULT_CRED_FAIL, True)

            self._token = oauth_info["refresh_token"]
            self._oauth2_url = oauth_info.get("oauth_url")
            result = await self._check_connection(lge_auth)
            if result != RESULT_SUCCESS:
                return await self._manage_error(result, True)
            return self._save_config_entry()

        self._login_url = await lge_auth.get_login_url()
        if not self._login_url:
            return self._show_form("error_url")

        return await self.async_step_url()

    async def async_step_url(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Parse the response url for oauth data and submit for save."""
        if not user_input:
            return self._show_form(step_id="url")

        url = user_input[CONF_URL]
        lge_auth = LGEAuthentication(
            self.hass, self._region, self._language, self._use_ha_session
        )
        oauth_info = await lge_auth.get_oauth_info_from_url(url)
        if not oauth_info:
            return self._show_form(errors="invalid_url", step_id="url")

        self._token = oauth_info["refresh_token"]
        self._oauth2_url = oauth_info.get("oauth_url")
        result = await self._check_connection(lge_auth)
        if result != RESULT_SUCCESS:
            return await self._manage_error(result)
        return self._save_config_entry()

    async def _check_connection(self, lge_auth: LGEAuthentication) -> int:
        """Test the connection to ThinQ."""

        try:
            client = await lge_auth.create_client_from_token(
                self._token, self._oauth2_url
            )
        except (AuthenticationError, InvalidCredentialError) as exc:
            msg = (
                "Invalid ThinQ credential error. Please use the LG App on your"
                " mobile device to verify if there are Term of Service to accept."
                " Account based on social network are not supported and in most"
                " case do not work with this integration."
            )
            _LOGGER.exception(msg, exc_info=exc)
            return RESULT_CRED_FAIL
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("Error connecting to ThinQ", exc_info=exc)
            return RESULT_FAIL

        if not client:
            return RESULT_NO_DEV

        await client.close()
        if not client.has_devices:
            return RESULT_NO_DEV

        self._client_id = client.client_id
        return RESULT_SUCCESS

    async def _manage_error(
        self, error_code: int, is_user_step=False
    ) -> ConfigFlowResult:
        """Manage the error result."""
        if error_code == RESULT_NO_DEV:
            return self.async_abort(reason="no_smartthinq_devices")

        self._error = "unknown"
        if error_code == RESULT_FAIL:
            self._error = "error_connect"
        elif error_code == RESULT_CRED_FAIL:
            self._error = "invalid_credentials"

        if is_user_step:
            return self._show_form()
        return await self.async_step_user()

    @callback
    def _save_config_entry(self) -> ConfigFlowResult:
        """Save the entry."""

        data = {
            CONF_REGION: self._region,
            CONF_LANGUAGE: self._language,
            CONF_TOKEN: self._token,
            CONF_USE_API_V2: True,
        }
        if self._client_id:
            data[CONF_CLIENT_ID] = self._client_id
        if self._oauth2_url:
            data[CONF_OAUTH2_URL] = self._oauth2_url
        if self._use_ha_session:
            data[CONF_USE_HA_SESSION] = True

        # if an entry exists, we are reconfiguring
        if entries := self._async_current_entries():
            entry = entries[0]
            return self.async_update_reload_and_abort(
                entry=entry,
                data=data,
            )

        return self.async_create_entry(title="LGE Devices", data=data)

    @callback
    def _prepare_form_schema(self, step_id="user") -> vol.Schema:
        """Prepare the user forms schema."""
        if step_id == "url":
            return vol.Schema(
                {
                    vol.Required(CONF_LOGIN, default=self._login_url): TextSelector(
                        config=TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                    vol.Required(CONF_URL): TextSelector(
                        config=TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                }
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Required(CONF_REGION, default=self._region or ""): SelectSelector(
                    _dict_to_select(COUNTRIES)
                ),
                vol.Required(
                    CONF_LANGUAGE, default=self._user_lang or ""
                ): SelectSelector(_dict_to_select(LANGUAGES)),
                vol.Required(CONF_USE_REDIRECT, default=False): bool,
            }
        )
        if self.show_advanced_options:
            schema = schema.extend(
                {vol.Required(CONF_USE_HA_SESSION, default=False): bool}
            )

        return schema

    @callback
    def _show_form(self, errors: str | None = None, step_id="user") -> ConfigFlowResult:
        """Show the form to the user."""
        base_err = errors or self._error
        self._error = None
        schema = self._prepare_form_schema(step_id)

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors={CONF_BASE: base_err} if base_err else None,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {vol.Required(CONF_REAUTH_CRED, default=False): bool}
                ),
            )

        if user_input[CONF_REAUTH_CRED] is True:
            return await self.async_step_user()
        entries = self._async_current_entries()
        return self.async_update_reload_and_abort(entries[0])


def _dict_to_select(opt_dict: dict) -> SelectSelectorConfig:
    """Covert a dict to a SelectSelectorConfig."""
    return SelectSelectorConfig(
        options=[SelectOptionDict(value=str(k), label=v) for k, v in opt_dict.items()],
        mode=SelectSelectorMode.DROPDOWN,
    )
