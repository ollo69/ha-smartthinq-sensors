"""Config flow for TP-Link."""
import logging
import re

import voluptuous as vol
from aiohttp import web
from yarl import URL
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers import config_entry_oauth2_flow as oauth2_flow

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
AUTH_CALLBACK_PATH = "/auth/external/thinq/callback"

INIT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION): str,
        vol.Required(CONF_LANGUAGE): str,
        vol.Optional(CONF_TOKEN): str,
        vol.Required(CONF_USE_API_V2, default=True): bool,
    }
)

_LOGGER = logging.getLogger(__name__)


class ThinQOAuth2Implementation(oauth2_flow.AbstractOAuth2Implementation):
    """Thinq OAuth2 implementation."""

    def __init__(
        self, hass: HomeAssistant, domain: str, authorize_url: str,
    ):
        """Initialize local auth implementation."""
        self.hass = hass
        self._domain = domain
        self.authorize_url = authorize_url

    @property
    def name(self) -> str:
        """Name of the implementation."""
        return "ThinQOAuth2"

    @property
    def domain(self) -> str:
        """Domain providing the implementation."""
        return self._domain

    @property
    def redirect_uri(self) -> str:
        """Return the redirect uri."""
        return f"{self.hass.config.api.base_url}{AUTH_CALLBACK_PATH}"  # type: ignore

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Generate a url for the user to authorize."""
        ori_url = URL(self.authorize_url)
        _LOGGER.info("ori url parameters: %s", str(ori_url.query))

        url = str(
            URL(self.authorize_url).update_query(
                {
                    # "show_select_country": "Y",
                    "callbackUrl": self.redirect_uri,
                    "oauth2State": oauth2_flow._encode_jwt(
                        self.hass, {"flow_id": flow_id}
                    ),
                }
            )
        )

        _LOGGER.info("authorize_url: %s", url)
        return url

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Resolve the authorization code to tokens."""
        _LOGGER.info("external_data: %s", str(external_data))
        return {
            "expires_in": 365,
            "refresh_token": external_data,
        }

    async def _async_refresh_token(self, token: dict) -> dict:
        """Refresh tokens."""
        return

    async def _token_request(self, data: dict) -> dict:
        """Make a token request."""
        return


@config_entries.HANDLERS.register(DOMAIN)
class SmartThinQFlowHandler(oauth2_flow.AbstractOAuth2FlowHandler):
    """Handle SmartThinQ config flow."""

    DOMAIN = DOMAIN
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize flow."""
        self._region = None
        self._language = None
        self._token = None
        self._oauth_url = None
        self._oauth_user_num = None
        self._use_api_v2 = False

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
        self._use_api_v2 = user_input.get(CONF_USE_API_V2, False)

        if self._use_api_v2:
            refresh_token = ""

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
            lgauth = LGEAuthentication(self._region, self._language, self._use_api_v2)
            self._loginurl = await self.hass.async_add_executor_job(lgauth.getLoginUrl)

            use_oauth2 = False  # force not use
            url_scheme = URL(self.hass.config.api.base_url).scheme
            if use_oauth2 and url_scheme == "https":
                flow_impl = ThinQOAuth2Implementation(self.hass, DOMAIN, self._loginurl)
                async_register_implementation(self.hass, DOMAIN, flow_impl)
                return await super().async_step_user()
            else:
                return self._show_form(errors=None, step_id="url")

        return await self._save_config_entry()

    async def async_oauth_create_entry(self, data: dict) -> dict:
        """Create new entry from oauth2 callback data."""

        _LOGGER.info(data)
        token = data.get("refresh_token", None)
        if not token:
            return self._show_form(errors={"base": "invalid_credentials"})

        self._token = token
        return self._show_form(errors=None, step_id="token")

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

        if step_id == "url":
            schema = vol.Schema(
                {
                    vol.Required(CONF_LOGIN, default=self._loginurl): str,
                    vol.Required(CONF_URL): str,
                }
            )
        elif step_id == "token":
            schema = vol.Schema({vol.Required(CONF_TOKEN, default=self._token): str,})

        return self.async_show_form(
            step_id=step_id, data_schema=schema, errors=errors if errors else {},
        )

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        if self._async_current_entries():
            _LOGGER.debug("SmartThinQ configuration already present / imported.")
            return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_user(import_config)


@callback
def async_register_implementation(
    hass: HomeAssistant,
    domain: str,
    implementation: oauth2_flow.AbstractOAuth2Implementation,
) -> None:
    """Register an OAuth2 flow implementation for an integration."""
    if isinstance(
        implementation, ThinQOAuth2Implementation
    ) and not hass.data.setdefault(domain, {}).get(
        oauth2_flow.DATA_VIEW_REGISTERED, False
    ):
        hass.http.register_view(ThinQAuthorizeCallbackView())  # type: ignore
        hass.data.setdefault(domain, {})[oauth2_flow.DATA_VIEW_REGISTERED] = True

    implementations = hass.data.setdefault(oauth2_flow.DATA_IMPLEMENTATIONS, {})
    implementations.setdefault(domain, {})[implementation.domain] = implementation


class ThinQAuthorizeCallbackView(HomeAssistantView):
    """ThinQ Authorization Callback View."""

    requires_auth = False
    url = AUTH_CALLBACK_PATH
    name = "auth:external:callback"

    async def get(self, request: web.Request) -> web.Response:
        """Receive authorization code."""
        if "oauth2State" not in request.query or "refresh_token" not in request.query:
            return web.Response(
                text=f"Missing token or state parameter in {request.url}"
            )

        hass = request.app["hass"]

        state = oauth2_flow._decode_jwt(hass, request.query["oauth2State"])

        if state is None:
            return web.Response(text=f"Invalid state")

        await hass.config_entries.flow.async_configure(
            flow_id=state["flow_id"], user_input=request.query["refresh_token"]
        )

        return web.Response(
            headers={"content-type": "text/html"},
            text="<script>window.close()</script>",
        )
