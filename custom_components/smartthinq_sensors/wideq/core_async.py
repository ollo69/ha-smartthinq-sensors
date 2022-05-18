"""A low-level, general abstraction for the LG SmartThinQ API.
"""
from __future__ import annotations

import aiohttp
import asyncio
import base64
import chardet
import hashlib
import hmac
import json
import logging
import os
import uuid
import xmltodict

from datetime import datetime
from typing import Any, Dict, Generator, Optional
from urllib.parse import urljoin, urlencode, urlparse, parse_qs, quote

from . import core_exceptions as exc
from .const import DEFAULT_COUNTRY, DEFAULT_LANGUAGE, DEFAULT_TIMEOUT
from .core_util import add_end_slash, as_list, gen_uuid
from .device_info import DeviceInfo

# The core version
CORE_VERSION = "coreAsync"

# enable logging of auth information
LOG_AUTH_INFO = False

# v2
V2_API_KEY = "VGhpblEyLjAgU0VSVklDRQ=="
V2_CLIENT_ID = "65260af7e8e6547b51fdccf930097c51eb9885a508d3fddfa9ee6cdec22ae1bd"
V2_SVC_PHASE = "OP"
V2_APP_LEVEL = "PRD"
V2_APP_OS = "LINUX"
V2_APP_TYPE = "NUTS"
V2_APP_VER = "3.0.1700"

# new
V2_GATEWAY_URL = "https://route.lgthinq.com:46030/v1/service/application/gateway-uri"
V2_AUTH_PATH = "/oauth/1.0/oauth2/token"
V2_USER_INFO = "/users/profile"
V2_EMP_SESS_URL = "https://emp-oauth.lgecloud.com/emp/oauth2/token/empsession"
OAUTH_REDIRECT_URI = "https://kr.m.lgaccount.com/login/iabClose"
APPLICATION_KEY = "6V1V8H2BN5P9ZQGOI5DAQ92YZBDO3EK9"  # for spx login
OAUTH_CLIENT_KEY = 'LGAO722A02'

# orig
DATA_ROOT = "lgedmRoot"
GATEWAY_URL = "https://kic.lgthinq.com:46030/api/common/gatewayUriList"
SECURITY_KEY = "nuts_securitykey"
SVC_CODE = "SVC202"
CLIENT_ID = "LGAO221A02"
OAUTH_SECRET_KEY = "c053c2a6ddeb7ad97cb0eed0dcb31cf8"
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S +0000"

API2_ERRORS = {
    "0101": exc.DeviceNotFound,
    "0102": exc.NotLoggedInError,
    "0106": exc.NotConnectedError,
    "0100": exc.FailedRequestError,
    "0110": exc.InvalidCredentialError,
    "9999": exc.NotConnectedError,  # This come as "other errors", we manage as not connected.
    9000: exc.InvalidRequestError,  # Surprisingly, an integer (not a string).
}

DEFAULT_TOKEN_VALIDITY = 3600  # seconds
TOKEN_EXP_LIMIT = 60  # will expire within 60 seconds

# minimum time between 2 consecutive call for device snapshot updates (in seconds)
MIN_TIME_BETWEEN_UPDATE = 25

_LOGGER = logging.getLogger(__name__)


def parse_oauth_callback(url: str):
    """Parse the URL to which an OAuth login redirected to obtain two
    tokens: an access token for API credentials, and a refresh token for
    getting updated access tokens.
    """

    params = parse_qs(urlparse(url).query)
    return {k: v[0] for k, v in params.items()}


def oauth_info_from_url(url: str) -> dict:
    """Return authentication info using an OAuth callback URL."""
    parsed_info = parse_oauth_callback(url)

    result = {
        "oauth_url": parsed_info["oauth2_backend_url"],
        "user_number": None,
    }
    if "refresh_token" in parsed_info:
        result["access_token"] = parsed_info.get("access_token")
        result["token_validity"] = str(DEFAULT_TOKEN_VALIDITY)
        result["refresh_token"] = parsed_info["refresh_token"]
    elif "code" in parsed_info:
        result["user_number"] = parsed_info.get("user_number")
        result["auth_code"] = parsed_info["code"]
    else:
        return {}

    return result


class CoreAsync:
    """Class for Core SmartThinQ Api async calls."""

    def __init__(
        self,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        session: aiohttp.ClientSession | None = None,
    ):
        """
        Create the CoreAsync object

        Parameters:
            country: ThinQ account country
            language: ThinQ account language
            timeout: the http timeout (default = 10 sec.)
            session: the AioHttp session to use (if None a new session is created)
        """

        self._country = country
        self._language = language
        self._timeout = timeout

        if session:
            self._session = session
            self._managed_session = False
        else:
            self._session = aiohttp.ClientSession()
            self._managed_session = True

    @property
    def country(self):
        """Return the used country."""
        return self._country

    @property
    def language(self):
        """Return the used language."""
        return self._language

    async def close(self):
        """Close the managed session on exit."""
        if self._managed_session:
            await self._session.close()

    @staticmethod
    async def _get_json_resp(response: aiohttp.ClientResponse) -> dict:
        """Try to get the json content from request response."""

        # first, we try to get the response json content
        try:
            return await response.json()
        except ValueError as ex:
            resp_text = await response.text(errors='replace')
            _LOGGER.debug("Error decoding json response %s: %s", resp_text, ex)

        # if fails, we try to convert text from xml to json
        try:
            return xmltodict.parse(resp_text)
        except Exception:
            raise exc.InvalidResponseError(resp_text) from None

    @staticmethod
    def _oauth2_signature(message: str, secret: str) -> str:
        """Get the base64-encoded SHA-1 HMAC digest of a string, as used in
        OAauth2 request signatures.

        Both the `secret` and `message` are given as text strings. We use
        their UTF-8 equivalents.
        """

        secret_bytes = secret.encode("utf8")
        hashed = hmac.new(secret_bytes, message.encode("utf8"), hashlib.sha1)
        digest = hashed.digest()
        return base64.b64encode(digest).decode("utf8")

    @staticmethod
    def _thinq2_headers(
        extra_headers: dict | None = None,
        access_token: str | None = None,
        user_number: str | None = None,
        country=DEFAULT_COUNTRY,
        language=DEFAULT_LANGUAGE,
    ) -> dict:
        """Prepare API2 header."""

        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "x-api-key": V2_API_KEY,
            "x-client-id": V2_CLIENT_ID,
            "x-country-code": country,
            "x-language-code": language,
            "x-message-id": gen_uuid(),
            "x-service-code": SVC_CODE,
            "x-service-phase": V2_SVC_PHASE,
            "x-thinq-app-level": V2_APP_LEVEL,
            "x-thinq-app-os": V2_APP_OS,
            "x-thinq-app-type": V2_APP_TYPE,
            "x-thinq-app-ver": V2_APP_VER,
            "x-thinq-security-key": SECURITY_KEY,
        }

        if access_token:
            headers["x-emp-token"] = access_token

        if user_number:
            headers["x-user-no"] = user_number

        add_headers = extra_headers or {}
        return {**headers, **add_headers}

    async def http_get_bytes(
        self,
        url: str,
    ) -> bytes:
        """Make a generic HTTP request."""
        async with self._session.get(
            url=url,
        ) as resp:
            result = await resp.content.read()

        return result

    async def thinq2_get(
        self,
        url: str,
        access_token: str | None = None,
        user_number: str | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Make an HTTP request in the format used by the API2 servers."""

        _LOGGER.debug("thinq2_get before: %s", url)

        async with self._session.get(
            url=url,
            headers=self._thinq2_headers(
                access_token=access_token,
                user_number=user_number,
                extra_headers=headers or {},
                country=self._country,
                language=self._language,
            ),
            timeout=self._timeout,
            raise_for_status=False,
        ) as resp:
            out = await self._get_json_resp(resp)

        _LOGGER.debug("thinq2_get after: %s", out)

        if "resultCode" not in out:
            raise exc.APIError("-1", out)

        res = self._manage_lge_result(out, True)
        return res["result"]

    async def lgedm2_post(
        self,
        url: str,
        data: dict | None = None,
        access_token: str | None = None,
        user_number: str | None = None,
        headers: dict | None = None,
        is_api_v2=False,
    ) -> dict:
        """Make an HTTP request in the format used by the API servers."""

        _LOGGER.debug("lgedm2_post before: %s", url)

        async with self._session.post(
            url=url,
            json=data if is_api_v2 else {DATA_ROOT: data},
            headers=self._thinq2_headers(
                access_token=access_token,
                user_number=user_number,
                extra_headers=headers or {},
                country=self._country,
                language=self._language,
            ),
            timeout=self._timeout,
            raise_for_status=False,
        ) as resp:
            out = await self._get_json_resp(resp)

        _LOGGER.debug("lgedm2_post after: %s", out)

        return self._manage_lge_result(out, is_api_v2)

    @staticmethod
    def _manage_lge_result(result: dict, is_api_v2=False) -> dict:
        """Manage the result from a get or a post to lge server."""

        if is_api_v2:
            if "resultCode" in result:
                code = result["resultCode"]
                if code != "0000":
                    if code in API2_ERRORS:
                        raise API2_ERRORS[code]()
                    message = result.get("result", "error")
                    raise exc.APIError(code, message)

            return result

        msg = result.get(DATA_ROOT)
        if not msg:
            raise exc.APIError("-1", result)

        if "returnCd" in msg:
            code = msg["returnCd"]
            if code != "0000":
                if code in API2_ERRORS:
                    raise API2_ERRORS[code]()
                message = msg["returnMsg"]
                raise exc.APIError(code, message)

        return msg

    async def gateway_info(self):
        """Return ThinQ gateway information."""
        return await self.thinq2_get(V2_GATEWAY_URL)

    async def auth_user_login(
        self, login_base_url, emp_base_url, username, encrypted_pwd
    ):
        """Perform a login with username and password.
           password must be encrypted using hashlib with hash512 algorythm.
        """

        _LOGGER.debug("auth_user_login - Enter")

        headers = {
            "Accept": "application/json",
            "X-Application-Key": APPLICATION_KEY,
            "X-Client-App-Key": CLIENT_ID,
            "X-Lge-Svccode": "SVC709",
            "X-Device-Type": "M01",
            "X-Device-Platform": "ADR",
            "X-Device-Language-Type": "IETF",
            "X-Device-Publish-Flag": "Y",
            "X-Device-Country": self._country,
            "X-Device-Language": self._language,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Access-Control-Allow-Origin": "*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
        }

        url = urljoin(login_base_url, "preLogin")
        pre_login_data = {
          "user_auth2": encrypted_pwd,
          "log_param": f"login request / user_id : {username} / third_party : null / svc_list : SVC202,SVC710 / 3rd_service : ",
        }

        async with self._session.post(
            url=url, data=pre_login_data, headers=headers, timeout=self._timeout, raise_for_status=False
        ) as resp:
            pre_login = await resp.json()

        _LOGGER.debug("auth_user_login - preLogin data: %s", pre_login)
        headers["X-Signature"] = pre_login["signature"]
        headers["X-Timestamp"] = pre_login["tStamp"]

        # try login with username and hashed password
        _LOGGER.debug("auth_user_login - getting account_data")
        data = {
          "user_auth2": pre_login["encrypted_pw"],
          "password_hash_prameter_flag": "Y",
          "svc_list": "SVC202,SVC710",  # SVC202=LG SmartHome, SVC710=EMP OAuth
        }
        emp_login_url = urljoin(emp_base_url, 'emp/v2.0/account/session/' + quote(username))

        async with self._session.post(
            url=emp_login_url, data=data, headers=headers, timeout=self._timeout, raise_for_status=False
        ) as resp:
            account_data = await resp.json()

        _LOGGER.debug("auth_user_login - account_data: %s", account_data)
        account = account_data["account"]

        #  const {code, message} = err.response.data.error;
        #  if (code === 'MS.001.03') {
        #    throw new AuthenticationError('Your account was already used to registered in '+ message +'.');
        #  }

        # dynamic get secret key for emp signature
        _LOGGER.debug("auth_user_login - getting secret_data")
        emp_search_key_url = urljoin(login_base_url, "searchKey?key_name=OAUTH_SECRETKEY&sever_type=OP")

        async with self._session.get(
            url=emp_search_key_url, timeout=self._timeout, raise_for_status=False
        ) as resp:
            secret_data = json.loads(await resp.text())  # this return data as plain/text

        _LOGGER.debug("auth_user_login - secret_data: %s", secret_data)
        secret_key = secret_data["returnData"]

        # get token data
        _LOGGER.debug("auth_user_login - getting token_data")
        emp_data = {
          "account_type": account["userIDType"],
          "client_id": CLIENT_ID,
          "country_code": account["country"],
          "username": account["userID"],
        }

        parse_url = urlparse(V2_EMP_SESS_URL)
        timestamp = datetime.utcnow().strftime(DATE_FORMAT)
        req_url = f"{parse_url.path}?{urlencode(emp_data)}"
        signature = self._oauth2_signature(f"{req_url}\n{timestamp}", secret_key)

        emp_headers = {
          "lgemp-x-app-key": OAUTH_CLIENT_KEY,
          "lgemp-x-date": timestamp,
          "lgemp-x-session-key": account["loginSessionID"],
          "lgemp-x-signature": signature,
          "Accept": "application/json",
          "X-Device-Type": "M01",
          "X-Device-Platform": "ADR",
          "Content-Type": "application/x-www-form-urlencoded",
          "Access-Control-Allow-Origin": "*",
          "Accept-Encoding": "gzip, deflate, br",
          "Accept-Language": "en-US,en;q=0.9",
          "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36 Edg/93.0.961.44",
        }

        async with self._session.post(
            url=V2_EMP_SESS_URL, headers=emp_headers, data=emp_data, timeout=self._timeout, raise_for_status=False
        ) as resp:
            token_data = await resp.json()

        if LOG_AUTH_INFO:
            _LOGGER.debug("auth_user_login - token_data: %s", token_data)
        _LOGGER.debug("auth_user_login - token_data retrieved")

        if token_data["status"] != 1:
            raise exc.TokenError()

        _LOGGER.debug("auth_user_login - Exit")
        return token_data

    async def get_oauth_url(self):
        """Return url used for oauth2 authentication."""

        headers = {
          "Accept": "application/json",
          "x-thinq-application-key": "wideq",
          "x-thinq-security-key": SECURITY_KEY,
        },

        async with self._session.post(
            url=GATEWAY_URL,
            json={DATA_ROOT: {"countryCode": self._country, "langCode": self._language}},
            headers=headers,
            timeout=self._timeout,
            raise_for_status=False,
        ) as resp:
            out = await resp.json()

        gateway = self._manage_lge_result(out)
        return gateway["oauthUri"]

    async def get_user_number(self, oauth_url, access_token):
        """Get the user number used by API requests based on access token."""

        url = urljoin(oauth_url, V2_USER_INFO)
        timestamp = datetime.utcnow().strftime(DATE_FORMAT)
        sig = self._oauth2_signature(f"{V2_USER_INFO}\n{timestamp}", OAUTH_SECRET_KEY)

        headers = {
          "Accept": "application/json",
          "Authorization": f"Bearer {access_token}",
          "X-Lge-Svccode": SVC_CODE,
          "X-Application-Key": APPLICATION_KEY,
          "lgemp-x-app-key": CLIENT_ID,
          "X-Device-Type": "M01",
          "X-Device-Platform": "ADR",
          "x-lge-oauth-date": timestamp,
          "x-lge-oauth-signature": sig,
        }

        try:
            async with self._session.get(
                url=url, headers=headers, timeout=self._timeout, raise_for_status=False
            ) as resp:
                res_data = await resp.json()
        except Exception as ex:
            raise exc.AuthenticationError() from ex

        if res_data["status"] != 1:
            raise exc.AuthenticationError("Failed to retrieve User Number")
        if LOG_AUTH_INFO:
            _LOGGER.debug(res_data)

        return res_data["account"]["userNo"]

    async def _auth_request(self, oauth_url, data, *, log_auth_info=False):
        """Use an auth code to log into the v2 API and obtain an access token
        and refresh token.
        """
        url = urljoin(oauth_url, V2_AUTH_PATH)
        timestamp = datetime.utcnow().strftime(DATE_FORMAT)
        req_url = f"{V2_AUTH_PATH}?{urlencode(data)}"
        sig = self._oauth2_signature(f"{req_url}\n{timestamp}", OAUTH_SECRET_KEY)

        headers = {
            "x-lge-appkey": CLIENT_ID,
            "x-lge-oauth-signature": sig,
            "x-lge-oauth-date": timestamp,
            "Accept": "application/json",
        }

        async with self._session.post(
            url=url, headers=headers, data=data, timeout=self._timeout, raise_for_status=False
        ) as resp:
            if resp.status != 200:
                raise exc.TokenError()
            res_data = await resp.json()

        if log_auth_info:
            _LOGGER.debug("Auth request result: %s", res_data)
        else:
            _LOGGER.debug("Authorization request completed successfully")

        return res_data

    async def auth_code_login(self, oauth_url, auth_code):
        """Get a new access_token using an authorization_code

        May raise a `tokenError`.
        """

        out = await self._auth_request(
            oauth_url,
            {
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": OAUTH_REDIRECT_URI,
            },
            log_auth_info=LOG_AUTH_INFO,
        )

        return out["access_token"], out.get("expires_in"), out["refresh_token"]

    async def refresh_auth(self, oauth_root, refresh_token):
        """Get a new access_token using a refresh_token.

        May raise a `TokenError`.
        """
        out = await self._auth_request(
            oauth_root,
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            log_auth_info=LOG_AUTH_INFO,
        )

        return out["access_token"], out["expires_in"]


class Gateway(object):
    def __init__(self, gw_info: dict, core: CoreAsync) -> None:
        self.auth_base = add_end_slash(gw_info["empUri"])
        self.emp_base_uri = add_end_slash(gw_info["empTermsUri"])
        self.login_base_uri = add_end_slash(gw_info["empSpxUri"])
        self.thinq1_uri = add_end_slash(gw_info["thinq1Uri"])
        self.thinq2_uri = add_end_slash(gw_info["thinq2Uri"])
        self._core = core

    @property
    def core(self) -> CoreAsync:
        """Return the API core."""
        return self._core

    @property
    def country(self) -> str:
        """Return the API core used country."""
        return self._core.country

    @property
    def language(self) -> str:
        """Return the API core used language."""
        return self._core.language

    async def close(self):
        """Close the core aiohttp session."""
        await self._core.close()

    @classmethod
    async def discover(cls, core: CoreAsync) -> Gateway:
        """Return an instance of gateway class."""
        gw_info = await core.gateway_info()
        return cls(gw_info, core)

    def oauth_url(self, *, redirect_uri=None, state=None, use_oauth2=True) -> str:
        """Construct the URL for users to log in (in a browser) to start an
        authenticated session.
        """

        url = urljoin(self.login_base_uri, "login/signIn")

        state_param = "oauth2State" if use_oauth2 else "state"
        query = {
            "country": self.country,
            "language": self.language,
            "client_id": CLIENT_ID,
            "svc_list": SVC_CODE,
            "svc_integrated": "Y",
            "show_thirdparty_login": "LGE,MYLG,GGL,AMZ,FBK,APPL",
            "division": "ha:T20",
            state_param: state or uuid.uuid1().hex,
            "show_select_country": "N",
        }
        if redirect_uri or not use_oauth2:
            query["redirect_uri"] = redirect_uri or OAUTH_REDIRECT_URI

        url_query = urlencode(query)
        return f"{url}?{url_query}"

    def dump(self) -> dict:
        return {
            "empUri": self.auth_base,
            "empTermsUri": self.emp_base_uri,
            "empSpxUri": self.login_base_uri,
            "thinq1Uri": self.thinq1_uri,
            "thinq2Uri": self.thinq2_uri,
            "country": self.country,
            "language": self.language,
        }


class Auth(object):
    """ThinQ authentication object"""

    def __init__(
        self,
        gateway: Gateway,
        refresh_token: str,
        oauth_url: str | None = None,
        access_token: str | None = None,
        token_validity: str | None = None,
        user_number: str | None = None,
    ) -> None:
        """Initialize ThinQ authentication"""
        self._gateway: Gateway = gateway
        self.refresh_token = refresh_token
        self.oauth_url = oauth_url
        self.access_token = access_token
        self.token_validity = int(token_validity) if token_validity else DEFAULT_TOKEN_VALIDITY
        self.user_number = user_number
        self._token_created_on = datetime.utcnow() if access_token else datetime.min

    @property
    def gateway(self) -> Gateway:
        """Return Gateway instance for this Auth."""
        return self._gateway

    @staticmethod
    async def oauth_info_from_url(url: str, core: CoreAsync) -> dict:
        """Return authentication info using an OAuth callback URL."""
        result = oauth_info_from_url(url)

        if auth_code := result.pop("auth_code", None):
            access_token, token_validity, refresh_token = await core.auth_code_login(
                result["oauth_url"], auth_code
            )
            return {
                **result,
                "access_token": access_token,
                "token_validity": token_validity,
                "refresh_token": refresh_token,
            }

        return result

    @classmethod
    async def from_url(cls, gateway: Gateway, url: str) -> Auth | None:
        """Create an authentication using an OAuth callback URL."""
        oauth_info = await cls.oauth_info_from_url(url, gateway.core)
        if not oauth_info:
            return None

        return cls(
            gateway,
            oauth_info["refresh_token"],
            oauth_info["oauth_url"],
            oauth_info["access_token"],
            oauth_info["token_validity"],
            oauth_info["user_number"],
        )

    @classmethod
    async def from_user_login(
        cls, gateway: Gateway, username: str, password: str
    ) -> Auth:
        """Perform authentication, returning a new Auth object."""
        hash_pwd = hashlib.sha512()
        hash_pwd.update(password.encode("utf8"))
        try:
            token_info = await gateway.core.auth_user_login(
                gateway.login_base_uri,
                gateway.emp_base_uri,
                username,
                hash_pwd.hexdigest(),
            )
        except Exception as ex:
            raise exc.AuthenticationError() from ex

        refresh_token = token_info["refresh_token"]
        oauth_url = token_info["oauth2_backend_url"]
        access_token = token_info["access_token"]
        token_validity = token_info["expires_in"]
        user_number = await gateway.core.get_user_number(oauth_url, access_token)

        return cls(
            gateway, refresh_token, oauth_url, access_token, token_validity, user_number
        )

    def start_session(self):
        """Start an API session for the logged-in user. Return the
        Session object and a list of the user's devices.
        """
        return Session(self)

    async def refresh(self, force_refresh=False) -> Auth:
        """Refresh the authentication token, returning a new Auth object."""

        access_token = self.access_token

        if not self.oauth_url:
            self.oauth_url = await self._gateway.core.get_oauth_url()

        get_new_token: bool = force_refresh or (access_token is None)
        if not get_new_token:
            diff = (datetime.utcnow() - self._token_created_on).total_seconds()
            if (self.token_validity - diff) <= TOKEN_EXP_LIMIT:
                get_new_token = True

        if get_new_token:
            _LOGGER.debug("Request new access token")
            access_token, token_validity = await self._gateway.core.refresh_auth(
                self.oauth_url, self.refresh_token
            )
        else:
            token_validity = str(self.token_validity)

        if not self.user_number:
            self.user_number = await self._gateway.core.get_user_number(
                self.oauth_url, access_token
            )

        if not get_new_token:
            return self

        return Auth(
            self._gateway,
            self.refresh_token,
            self.oauth_url,
            access_token,
            token_validity,
            self.user_number,
        )

    def refresh_gateway(self, gateway: Gateway) -> None:
        """Refresh the gateway."""
        self._gateway = gateway

    def dump(self) -> dict:
        """Return a dict of dumped Auth class."""
        return {
            "refresh_token": self.refresh_token,
            "oauth_url": self.oauth_url,
            "access_token": self.access_token,
            "expires_in": self.token_validity,
            "user_number": self.user_number,
        }

    @classmethod
    def load(cls, gateway: Gateway, data: dict) -> Auth:
        """Return an Auth class."""
        return cls(
            gateway,
            data["refresh_token"],
            data["oauth_url"],
            data.get("access_token"),
            data.get("expires_in"),
            data["user_number"],
        )


class Session(object):
    def __init__(self, auth: Auth, session_id=0) -> None:
        self._auth = auth
        self.session_id = session_id
        self._common_lang_pack_url = None

    @property
    def common_lang_pack_url(self):
        return self._common_lang_pack_url

    async def refresh_auth(self) -> Auth:
        """Refresh associated authentication"""
        self._auth = await self._auth.refresh()
        return self._auth

    async def post(self, path: str, data: dict | None = None) -> dict:
        """Make a POST request to the APIv1 server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """

        url = urljoin(self._auth.gateway.thinq1_uri, path)
        return await self._auth.gateway.core.lgedm2_post(
            url,
            data,
            self._auth.access_token,
            self._auth.user_number,
            is_api_v2=False,
        )

    async def post2(self, path: str, data: dict | None = None) -> dict:
        """Make a POST request to the APIv2 server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """
        url = urljoin(self._auth.gateway.thinq2_uri, path)
        return await self._auth.gateway.core.lgedm2_post(
            url,
            data,
            self._auth.access_token,
            self._auth.user_number,
            is_api_v2=True,
        )

    async def get(self, path: str) -> dict:
        """Make a GET request to the APIv1 server."""

        url = urljoin(self._auth.gateway.thinq1_uri, path)
        return await self._auth.gateway.core.thinq2_get(
            url,
            self._auth.access_token,
            self._auth.user_number,
        )

    async def get2(self, path: str) -> dict:
        """Make a GET request to the APIv2 server."""

        url = urljoin(self._auth.gateway.thinq2_uri, path)
        return await self._auth.gateway.core.thinq2_get(
            url,
            self._auth.access_token,
            self._auth.user_number,
        )

    async def get_devices(self):
        """Get a list of devices associated with the user's account.

        Return a list of dicts with information about the devices.
        """
        dashboard = await self.get2("service/application/dashboard")
        if self._common_lang_pack_url is None:
            self._common_lang_pack_url = dashboard.get("langPackCommonUri")
        return as_list(dashboard.get("item", []))

    async def monitor_start(self, device_id):
        """Begin monitoring a device's status.

        Return a "work ID" that can be used to retrieve the result of
        monitoring.
        """

        res = await self.post(
            "rti/rtiMon",
            {
                "cmd": "Mon",
                "cmdOpt": "Start",
                "deviceId": device_id,
                "workId": gen_uuid(),
            },
        )
        return res["workId"]

    async def monitor_poll(self, device_id, work_id):
        """Get the result of a monitoring task.

        `work_id` is a string ID retrieved from `monitor_start`. Return
        a status result, which is a bytestring, or None if the
        monitoring is not yet ready.

        May raise a `MonitorError`, in which case the right course of
        action is probably to restart the monitoring task.
        """

        work_list = [{"deviceId": device_id, "workId": work_id}]
        res = (await self.post("rti/rtiResult", {"workList": work_list}))["workList"]

        # When monitoring first starts, it usually takes a few
        # iterations before data becomes available. In the initial
        # "warmup" phase, `returnCode` is missing from the response.
        if "returnCode" not in res:
            return None

        # Check for errors.
        code = res["returnCode"]
        if code != "0000":
            raise exc.MonitorError(device_id, code)

        # The return data may or may not be present, depending on the
        # monitoring task status.
        if "returnData" in res:
            # The main response payload is base64-encoded binary data in
            # the `returnData` field. This sometimes contains JSON data
            # and sometimes other binary data.
            return base64.b64decode(res["returnData"])

        return None

    async def monitor_stop(self, device_id, work_id):
        """Stop monitoring a device."""

        await self.post(
            "rti/rtiMon",
            {"cmd": "Mon", "cmdOpt": "Stop", "deviceId": device_id, "workId": work_id},
        )

    async def set_device_controls(
            self,
            device_id,
            ctrl_key,
            command=None,
            value=None,
            data=None,
    ):
        """Control a device's settings.

        `values` is a key/value map containing the settings to update.
        """
        res = {}
        payload = None
        if isinstance(ctrl_key, dict):
            payload = ctrl_key
        elif command is not None:
            payload = {
                "cmd": ctrl_key,
                "cmdOpt": command,
                "value": value or "",
                "data": data or "",
            }

        if payload:
            payload.update({
                "deviceId": device_id,
                "workId": gen_uuid(),
            })
            res = await self.post("rti/rtiControl", payload)
            _LOGGER.debug("Set V1 result: %s", str(res))

        return res

    async def set_device_v2_controls(
            self,
            device_id,
            ctrl_key,
            command=None,
            key=None,
            value=None,
            *,
            ctrl_path=None,
    ):
        """Control a device's settings based on api V2."""

        res = {}
        payload = None
        path = ctrl_path or "control-sync"
        cmd_path = f"service/devices/{device_id}/{path}"
        if isinstance(ctrl_key, dict):
            payload = ctrl_key
        elif command is not None:
            payload = {
                "ctrlKey": ctrl_key,
                "command": command,
                "dataKey": key or "",
                "dataValue": value or "",
            }

        if payload:
            res = await self.post2(cmd_path, payload)
            _LOGGER.debug("Set V2 result: %s", str(res))

        return res

    async def get_device_config(self, device_id, key, category="Config"):
        """Get a device configuration option.

        The `category` string should probably either be "Config" or
        "Control"; the right choice appears to depend on the key.
        """

        res = await self.post(
            "rti/rtiControl",
            {
                "cmd": category,
                "cmdOpt": "Get",
                "value": key,
                "deviceId": device_id,
                "workId": gen_uuid(),
                "data": "",
            },
        )
        return res["returnData"]

    async def get_device_v2_settings(self, device_id):
        """Get a device's settings based on api V2."""
        return await self.get2(f"service/devices/{device_id}")

    async def delete_permission(self, device_id):
        """Delete permission on V1 device after a control command"""
        await self.post("rti/delControlPermission", {"deviceId": device_id})


class ClientAsync(object):
    """A higher-level API wrapper that provides a session more easily
        and allows serialization of state.
        """

    def __init__(
        self,
        auth: Auth,
        session: Optional[Session] = None,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        *,
        enable_emulation: bool = False
    ) -> None:
        """Initialize the client."""
        # The three steps required to get access to call the API.
        self._auth: Auth = auth
        self._session: Optional[Session] = session
        self._last_device_update = datetime.utcnow()
        self._lock = asyncio.Lock()
        # The last list of devices we got from the server. This is the
        # raw JSON list data describing the devices.
        self._devices = None

        # Cached model info data. This is a mapping from URLs to JSON
        # responses.
        self._model_url_info: Dict[str, Any] = {}
        self._common_lang_pack = None

        # Locale information used to discover a gateway, if necessary.
        self._country = country
        self._language = language

        # enable emulation mode for debug / test
        self._emulation = enable_emulation

    def _inject_thinq2_device(self):
        """This is used only for debug"""
        data_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "deviceV2.txt"
        )
        try:
            with open(data_file, "r") as f:
                device_v2 = json.load(f)
        except FileNotFoundError:
            return
        for d in device_v2:
            self._devices.append(d)
            _LOGGER.debug("Injected debug device: %s", d)

    async def _load_devices(self, force_update: bool = False):
        """Load dict with available devices."""
        if self._session and (self._devices is None or force_update):
            self._devices = await self._session.get_devices()
            if self.emulation:
                # for debug
                self._inject_thinq2_device()

    @property
    def api_version(self):
        """Return core API version."""
        return CORE_VERSION

    @property
    def auth(self) -> Auth:
        """Return the Auth object associated to this client."""
        if not self._auth:
            assert False, "unauthenticated"
        return self._auth

    @property
    def session(self) -> Session:
        """Return the Session object associated to this client."""
        if not self._session:
            self._session = self.auth.start_session()
        return self._session

    @property
    def has_devices(self) -> bool:
        """Return True if there are devices associated."""
        return True if self._devices else False

    @property
    def devices(self) -> Generator[DeviceInfo, None, None] | None:
        """DeviceInfo objects describing the user's devices."""
        if self._devices is None:
            return None
        return (DeviceInfo(d) for d in self._devices)

    @property
    def emulation(self) -> bool:
        """Return if emulation is enabled."""
        return self._emulation

    @property
    def oauth_info(self) -> dict:
        """Return current auth info."""
        return {
            "refresh_token": self.auth.refresh_token,
            "oauth_url": self.auth.oauth_url,
            "access_token": self.auth.access_token,
            "user_number": self.auth.user_number,
        }

    async def close(self):
        """Close the active managed core http session."""
        await self._auth.gateway.close()

    async def refresh_devices(self):
        """Refresh the devices' information for this client"""
        async with self._lock:
            call_time = datetime.utcnow()
            difference = (call_time - self._last_device_update).total_seconds()
            if difference <= MIN_TIME_BETWEEN_UPDATE:
                return
            await self._load_devices(True)
            self._last_device_update = call_time

    def get_device(self, device_id) -> DeviceInfo | None:
        """Look up a DeviceInfo object by device ID.
            
        Return None if the device does not exist.
        """
        if not self._devices:
            return None
        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    async def refresh(self, refresh_gateway=False) -> None:
        """Refresh client connection."""
        if refresh_gateway:
            gateway = await Gateway.discover(self.auth.gateway.core)
            self.auth.refresh_gateway(gateway)
        self._auth = await self.auth.refresh(True)
        self._session = self.auth.start_session()
        await self._load_devices()

    async def refresh_auth(self) -> None:
        """Refresh auth token if requested."""
        if self._session:
            self._auth = await self._session.refresh_auth()
        else:
            await self.refresh()

    @classmethod
    async def from_login(
        cls,
        username: str,
        password: str,
        *,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        aiohttp_session: aiohttp.ClientSession | None = None,
        enable_emulation: bool = False,
    ) -> ClientAsync:
        """Construct a client using username and password.

            This allows simpler state storage (e.g., for human-written
            configuration) but it is a little less efficient because we need
            to reload the gateway servers and restart the session.
            """

        gateway = await Gateway.discover(
            CoreAsync(country, language, session=aiohttp_session)
        )
        auth = await Auth.from_user_login(gateway, username, password)
        client = cls(auth=auth, country=country, language=language, enable_emulation=enable_emulation)
        client._session = auth.start_session()
        await client._load_devices()
        return client

    @classmethod
    async def from_token(
        cls,
        refresh_token: str,
        oauth_url: str | None = None,
        *,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        aiohttp_session: aiohttp.ClientSession | None = None,
        enable_emulation: bool = False,
    ) -> ClientAsync:
        """Construct a client using just a refresh token.
            
            This allows simpler state storage (e.g., for human-written
            configuration) but it is a little less efficient because we need
            to reload the gateway servers and restart the session.
            """

        gateway = await Gateway.discover(
            CoreAsync(country, language, session=aiohttp_session)
        )
        auth = Auth(gateway, refresh_token, oauth_url)
        client = cls(auth=auth, country=country, language=language, enable_emulation=enable_emulation)
        await client.refresh()
        return client

    @staticmethod
    async def get_oauth_url(
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
        *,
        aiohttp_session: aiohttp.ClientSession | None = None,
    ) -> str:
        """Return an url to use to login in a browser."""
        gateway = await Gateway.discover(
            CoreAsync(country, language, session=aiohttp_session)
        )
        await gateway.close()
        return gateway.oauth_url()

    @staticmethod
    async def oauth_info_from_url(
        url: str, aiohttp_session: aiohttp.ClientSession | None = None
    ) -> dict:
        """Return authentication info from an OAuth callback URL."""
        core = CoreAsync(session=aiohttp_session)
        result = await Auth.oauth_info_from_url(url, core)
        await core.close()
        return result

    async def _load_json_info(self, info_url: str):
        """Load JSON data from specific url."""
        if not info_url:
            return {}

        content = await self._auth.gateway.core.http_get_bytes(info_url)

        # we use chardet to detect correct encoding and convert to unicode string
        encoding = chardet.detect(content)['encoding']
        try:
            str_content = str(content, encoding, errors='replace')
        except (LookupError, TypeError):
            # A LookupError is raised if the encoding was not found which could
            # indicate a misspelling or similar mistake.
            #
            # A TypeError can be raised if encoding is None
            #
            # So we try blindly encoding.
            str_content = str(content, errors='replace')

        enc_resp = str_content.encode()
        return json.loads(enc_resp)

    async def common_lang_pack(self):
        """Load JSON common lang pack from specific url."""
        if self._devices is None:
            return {}
        if self._common_lang_pack is None and self._session:
            self._common_lang_pack = (
                await self._load_json_info(self._session.common_lang_pack_url)
            ).get("pack", {})
        return self._common_lang_pack

    async def model_url_info(self, url, device=None):
        """For a DeviceInfo object, get a ModelInfo object describing
            the model's capabilities.
            """
        if not url:
            return {}
        if url not in self._model_url_info:
            if device:
                _LOGGER.info(
                    "Loading model info for %s. Model: %s, Url: %s",
                    device.name,
                    device.model_name,
                    url,
                )
            self._model_url_info[url] = await self._load_json_info(url)
        return self._model_url_info[url]

    def dump(self) -> Dict[str, Any]:
        """Serialize the client state."""

        out = {
            "model_url_info": self._model_url_info,
        }

        if self._auth:
            out["auth"] = self._auth.dump()
            out["gateway"] = self._auth.gateway.dump()

        if self._session:
            out["session"] = self._session.session_id

        out["country"] = self._country
        out["language"] = self._language

        return out

    @classmethod
    def load(cls, state: Dict[str, Any]) -> ClientAsync | None:
        """Load a client from serialized state."""

        auth = None
        gateway = None
        if "gateway" in state:
            data = state["gateway"]
            gateway = Gateway(
                data,
                CoreAsync(
                    data.get("country", DEFAULT_COUNTRY),
                    data.get("language", DEFAULT_LANGUAGE),
                )
            )

        if "auth" in state and gateway:
            data = state["auth"]
            auth = Auth.load(gateway, data)

        if not auth:
            return None

        client = cls(auth)

        if "session" in state:
            client._session = Session(client.auth, state["session"])

        if "model_info" in state:
            client._model_info = state["model_info"]

        if "country" in state:
            client._country = state["country"]

        if "language" in state:
            client._language = state["language"]

        return client
