"""A low-level, general abstraction for the LG SmartThinQ API.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import requests
import uuid

from datetime import datetime
from threading import Lock
from typing import Any, Dict, Generator, Optional
from urllib.parse import urljoin, urlencode, urlparse, parse_qs

from . import(
    as_list,
    gen_uuid,
    AuthHTTPAdapter,
    CoreVersion,
    DATA_ROOT,
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
)
from . import EMULATION, core_exceptions as exc
from .device import DeviceInfo, DEFAULT_TIMEOUT

CORE_VERSION = CoreVersion.CoreV2

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
OAUTH_REDIRECT_URI = "https://kr.m.lgaccount.com/login/iabClose"

# orig
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
    9000: exc.InvalidRequestError,  # Surprisingly, an integer (not a string).
}

LOG_AUTH_INFO = False
MIN_TIME_BETWEEN_UPDATE = 25  # seconds

_LOGGER = logging.getLogger(__name__)


class CoreV2HttpAdapter:

    http_adapter = None

    @staticmethod
    def init_http_adapter(use_tls_v1=False, exclude_dh=False):
        if not (use_tls_v1 or exclude_dh):
            CoreV2HttpAdapter.http_adapter = None
            return
        CoreV2HttpAdapter.http_adapter = AuthHTTPAdapter(
            use_tls_v1=use_tls_v1, exclude_dh=exclude_dh
        )


def oauth2_signature(message, secret):
    """Get the base64-encoded SHA-1 HMAC digest of a string, as used in
    OAauth2 request signatures.

    Both the `secret` and `message` are given as text strings. We use
    their UTF-8 equivalents.
    """

    secret_bytes = secret.encode("utf8")
    hashed = hmac.new(secret_bytes, message.encode("utf8"), hashlib.sha1)
    digest = hashed.digest()
    return base64.b64encode(digest)


def thinq2_headers(
    extra_headers={},
    access_token=None,
    user_number=None,
    country=DEFAULT_COUNTRY,
    language=DEFAULT_LANGUAGE,
):
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

    return {**headers, **extra_headers}


def thinq2_get(
    url,
    access_token=None,
    user_number=None,
    headers={},
    country=DEFAULT_COUNTRY,
    language=DEFAULT_LANGUAGE,
):
    """Make an HTTP request in the format used by the API2 servers."""

    _LOGGER.debug("thinq2_get before: %s", url)

    s = requests.Session()
    if CoreV2HttpAdapter.http_adapter:
        s.mount(url, CoreV2HttpAdapter.http_adapter)

    res = s.get(
        url,
        headers=thinq2_headers(
            access_token=access_token,
            user_number=user_number,
            extra_headers=headers,
            country=country,
            language=language,
        ),
        timeout=DEFAULT_TIMEOUT,
    )

    out = res.json()
    _LOGGER.debug("thinq2_get after: %s", out)

    if "resultCode" not in out:
        raise exc.APIError("-1", out)

    manage_lge_result(out, True)
    return out["result"]


def lgedm2_post(
    url,
    data=None,
    access_token=None,
    user_number=None,
    headers={},
    country=DEFAULT_COUNTRY,
    language=DEFAULT_LANGUAGE,
    is_api_v2=False,
):
    """Make an HTTP request in the format used by the API servers."""

    _LOGGER.debug("lgedm2_post before: %s", url)

    s = requests.Session()
    if CoreV2HttpAdapter.http_adapter:
        s.mount(url, CoreV2HttpAdapter.http_adapter)

    res = s.post(
        url,
        json=data if is_api_v2 else {DATA_ROOT: data},
        headers=thinq2_headers(
            access_token=access_token,
            user_number=user_number,
            extra_headers=headers,
            country=country,
            language=language,
        ),
        timeout=DEFAULT_TIMEOUT,
    )

    out = res.json()
    _LOGGER.debug("lgedm2_post after: %s", out)

    return manage_lge_result(out, is_api_v2)


def manage_lge_result(result, is_api_v2=False):
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


def gateway_info(country, language):
    """ TODO
    """
    return thinq2_get(V2_GATEWAY_URL, country=country, language=language)


def parse_oauth_callback(url):
    """Parse the URL to which an OAuth login redirected to obtain two
    tokens: an access token for API credentials, and a refresh token for
    getting updated access tokens.
    """

    params = parse_qs(urlparse(url).query)
    return params["oauth2_backend_url"][0], params["code"][0], params["user_number"][0]


def auth_request(oauth_url, data, *, log_auth_info=False):
    """Use an auth code to log into the v2 API and obtain an access token 
    and refresh token.
    """
    url = urljoin(oauth_url, V2_AUTH_PATH)
    timestamp = datetime.utcnow().strftime(DATE_FORMAT)
    req_url = "{}?{}".format(V2_AUTH_PATH, urlencode(data))
    sig = oauth2_signature("{}\n{}".format(req_url, timestamp), OAUTH_SECRET_KEY)

    headers = {
        "x-lge-appkey": CLIENT_ID,
        "x-lge-oauth-signature": sig,
        "x-lge-oauth-date": timestamp,
        "Accept": "application/json",
    }

    s = requests.Session()
    if CoreV2HttpAdapter.http_adapter:
        s.mount(url, CoreV2HttpAdapter.http_adapter)

    res = s.post(url, headers=headers, data=data, timeout=DEFAULT_TIMEOUT)

    if res.status_code != 200:
        raise exc.TokenError()

    res_data = res.json()
    if log_auth_info:
        _LOGGER.debug(res_data)
    else:
        _LOGGER.debug("Authorization request successful")

    return res_data


def login(oauth_url, auth_code):
    """Get a new access_token using an authorization_code
    
    May raise a `tokenError`.
    """

    out = auth_request(
        oauth_url,
        {
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": OAUTH_REDIRECT_URI,
        },
        log_auth_info=LOG_AUTH_INFO,
    )

    return out["access_token"], out["refresh_token"]


def refresh_auth(oauth_root, refresh_token):
    """Get a new access_token using a refresh_token.

    May raise a `TokenError`.
    """
    out = auth_request(
        oauth_root,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        log_auth_info=LOG_AUTH_INFO,
    )

    return out["access_token"]


class Gateway(object):
    def __init__(self, auth_base, api_root, api2_root, country, language):
        self.auth_base = auth_base
        self.api_root = api_root
        self.api2_root = api2_root
        self.country = country
        self.language = language

    @classmethod
    def discover(cls, country, language):
        gw = gateway_info(country, language)
        return cls(gw["empUri"], gw["thinq1Uri"], gw["thinq2Uri"], country, language)

    def oauth_url(self, *, redirect_uri=None, state=None):
        """Construct the URL for users to log in (in a browser) to start an
        authenticated session.
        """

        url = urljoin(self.auth_base, "spx/login/signIn")
        query = urlencode(
            {
                "country": self.country,
                "language": self.language,
                "svc_list": SVC_CODE,
                "client_id": CLIENT_ID,
                "division": "ha",
                "redirect_uri": redirect_uri or OAUTH_REDIRECT_URI,
                "state": state or uuid.uuid1().hex,
                "show_thirdparty_login": "GGL,AMZ,FBK",
            }
        )
        return "{}?{}".format(url, query)

    def dump(self):
        return {
            "auth_base": self.auth_base,
            "api_root": self.api_root,
            "api2_root": self.api2_root,
            "country": self.country,
            "language": self.language,
        }


class Auth(object):
    def __init__(self, gateway, oauth_url, access_token, refresh_token, user_number):
        self.gateway = gateway
        self.oauth_url = oauth_url
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.user_number = user_number

    @classmethod
    def from_url(cls, gateway, url):
        """Create an authentication using an OAuth callback URL.
        """
        oauth_url, auth_code, user_number = parse_oauth_callback(url)
        access_token, refresh_token = login(oauth_url, auth_code)

        return cls(gateway, oauth_url, access_token, refresh_token, user_number)

    def start_session(self):
        """Start an API session for the logged-in user. Return the
        Session object and a list of the user's devices.
        """
        return Session(self)

    def refresh(self):
        """Refresh the authentication, returning a new Auth object.
        """

        new_access_token = refresh_auth(self.oauth_url, self.refresh_token)
        return Auth(
            self.gateway,
            self.oauth_url,
            new_access_token,
            self.refresh_token,
            self.user_number,
        )

    def refresh_gateway(self, gateway):
        """Refresh the gateway.
        """
        self.gateway = gateway

    def dump(self):
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "oauth_url": self.oauth_url,
            "user_number": self.user_number,
        }

    @classmethod
    def load(cls, gateway, data):
        return cls(
            gateway,
            data["oauth_url"],
            data["access_token"],
            data["refresh_token"],
            data["user_number"],
        )


class Session(object):
    def __init__(self, auth, session_id=None):
        self.auth = auth
        self.session_id = session_id
        self._common_lang_pack_url = None

    @property
    def common_lang_pack_url(self):
        return self._common_lang_pack_url

    def post(self, path, data=None):
        """Make a POST request to the APIv1 server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """

        url = urljoin(self.auth.gateway.api_root + "/", path)
        return lgedm2_post(
            url,
            data,
            self.auth.access_token,
            self.auth.user_number,
            country=self.auth.gateway.country,
            language=self.auth.gateway.language,
            is_api_v2=False,
        )

    def post2(self, path, data=None):
        """Make a POST request to the APIv2 server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """
        url = urljoin(self.auth.gateway.api2_root + "/", path)
        return lgedm2_post(
            url,
            data,
            self.auth.access_token,
            self.auth.user_number,
            country=self.auth.gateway.country,
            language=self.auth.gateway.language,
            is_api_v2=True,
        )

    def get(self, path):
        """Make a GET request to the APIv1 server."""

        url = urljoin(self.auth.gateway.api_root + "/", path)
        return thinq2_get(
            url,
            self.auth.access_token,
            self.auth.user_number,
            country=self.auth.gateway.country,
            language=self.auth.gateway.language,
        )

    def get2(self, path):
        """Make a GET request to the APIv2 server."""

        url = urljoin(self.auth.gateway.api2_root + "/", path)
        return thinq2_get(
            url,
            self.auth.access_token,
            self.auth.user_number,
            country=self.auth.gateway.country,
            language=self.auth.gateway.language,
        )

    def get_devices(self):
        """Get a list of devices associated with the user's account.

        Return a list of dicts with information about the devices.
        """
        dashboard = self.get2("service/application/dashboard")
        if self._common_lang_pack_url is None:
            self._common_lang_pack_url = dashboard.get("langPackCommonUri")
        return as_list(dashboard.get("item", []))

    def monitor_start(self, device_id):
        """Begin monitoring a device's status.

        Return a "work ID" that can be used to retrieve the result of
        monitoring.
        """

        res = self.post(
            "rti/rtiMon",
            {
                "cmd": "Mon",
                "cmdOpt": "Start",
                "deviceId": device_id,
                "workId": gen_uuid(),
            },
        )
        return res["workId"]

    def monitor_poll(self, device_id, work_id):
        """Get the result of a monitoring task.

        `work_id` is a string ID retrieved from `monitor_start`. Return
        a status result, which is a bytestring, or None if the
        monitoring is not yet ready.

        May raise a `MonitorError`, in which case the right course of
        action is probably to restart the monitoring task.
        """

        work_list = [{"deviceId": device_id, "workId": work_id}]
        res = self.post("rti/rtiResult", {"workList": work_list})["workList"]

        # When monitoring first starts, it usually takes a few
        # iterations before data becomes available. In the initial
        # "warmup" phase, `returnCode` is missing from the response.
        if "returnCode" not in res:
            return None

        # Check for errors.
        code = res.get("returnCode")  # returnCode can be missing.
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

    def monitor_stop(self, device_id, work_id):
        """Stop monitoring a device."""

        self.post(
            "rti/rtiMon",
            {"cmd": "Mon", "cmdOpt": "Stop", "deviceId": device_id, "workId": work_id},
        )

    def set_device_controls(
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
            res = self.post("rti/rtiControl", payload)
            _LOGGER.debug("Set V1 result: %s", str(res))

        return res

    def set_device_v2_controls(
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
            res = self.post2(cmd_path, payload)
            _LOGGER.debug("Set V2 result: %s", str(res))

        return res

    def get_device_config(self, device_id, key, category="Config"):
        """Get a device configuration option.

        The `category` string should probably either be "Config" or
        "Control"; the right choice appears to depend on the key.
        """

        res = self.post(
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

    def get_device_v2_settings(self, device_id):
        """Get a device's settings based on api V2."""
        return self.get2(f"service/devices/{device_id}")

    def delete_permission(self, device_id):
        """Delete permission on V1 device after a control command"""
        self.post("rti/delControlPermission", {"deviceId": device_id})


class ClientV2(object):
    """A higher-level API wrapper that provides a session more easily
        and allows serialization of state.
        """

    def __init__(
        self,
        gateway: Optional[Gateway] = None,
        auth: Optional[Auth] = None,
        session: Optional[Session] = None,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        # The three steps required to get access to call the API.
        self._gateway: Optional[Gateway] = gateway
        self._auth: Optional[Auth] = auth
        self._session: Optional[Session] = session
        self._last_device_update = datetime.now()
        self._lock = Lock()

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

    def _inject_thinq2_device(self):
        """This is used only for debug"""
        data_file = os.path.dirname(os.path.realpath(__file__)) + "/deviceV2.txt"
        try:
            with open(data_file, "r") as f:
                device_v2 = json.load(f)
        except FileNotFoundError:
            return
        for d in device_v2:
            self._devices.append(d)
            _LOGGER.debug("Injected debug device: %s", d)

    def _load_devices(self, force_update: bool = False):
        if self._session and (self._devices is None or force_update):
            self._devices = self._session.get_devices()
            if EMULATION:
                # for debug
                self._inject_thinq2_device()

    @property
    def api_version(self):
        """Return core API version"""
        return CORE_VERSION

    @property
    def gateway(self) -> Gateway:
        if not self._gateway:
            self._gateway = Gateway.discover(self._country, self._language)
        return self._gateway

    @property
    def auth(self) -> Auth:
        if not self._auth:
            assert False, "unauthenticated"
        return self._auth

    @property
    def session(self) -> Session:
        if not self._session:
            self._session = self.auth.start_session()
            self._load_devices()
        return self._session

    @property
    def hasdevices(self) -> bool:
        return True if self._devices else False

    @property
    def devices(self) -> Generator["DeviceInfo", None, None]:
        """DeviceInfo objects describing the user's devices.
            """
        if self._devices is None:
            self._load_devices()
        return (DeviceInfo(d) for d in self._devices)

    def refresh_devices(self):
        """Refresh the devices information for this client"""
        with self._lock:
            call_time = datetime.now()
            difference = (call_time - self._last_device_update).total_seconds()
            if difference <= MIN_TIME_BETWEEN_UPDATE:
                return
            self._load_devices(True)
            self._last_device_update = call_time

    def get_device(self, device_id) -> Optional["DeviceInfo"]:
        """Look up a DeviceInfo object by device ID.
            
        Return None if the device does not exist.
        """
        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    @classmethod
    def load(cls, state: Dict[str, Any]) -> "ClientV2":
        """Load a client from serialized state.
            """

        client = cls()

        if "gateway" in state:
            data = state["gateway"]
            client._gateway = Gateway(
                data["auth_base"],
                data["api_root"],
                data["api2_root"],
                data.get("country", DEFAULT_COUNTRY),
                data.get("language", DEFAULT_LANGUAGE),
            )

        if "auth" in state:
            data = state["auth"]
            client._auth = Auth.load(client._gateway, data)

        if "session" in state:
            client._session = Session(client.auth, state["session"])

        if "model_info" in state:
            client._model_info = state["model_info"]

        if "country" in state:
            client._country = state["country"]

        if "language" in state:
            client._language = state["language"]

        return client

    def dump(self) -> Dict[str, Any]:
        """Serialize the client state."""

        out = {
            "model_url_info": self._model_url_info,
        }

        if self._gateway:
            out["gateway"] = {
                "auth_base": self._gateway.auth_base,
                "api_root": self._gateway.api_root,
                "api2_root": self._gateway.api2_root,
                "country": self._gateway.country,
                "language": self._gateway.language,
            }

        if self._auth:
            out["auth"] = {
                "access_token": self._auth.access_token,
                "refresh_token": self._auth.refresh_token,
            }

        if self._session:
            out["session"] = self._session.session_id

        out["country"] = self._country
        out["language"] = self._language

        return out

    def refresh(self, refresh_gateway=False) -> None:
        if refresh_gateway:
            self._gateway = None
        if not self._gateway:
            self._auth.refresh_gateway(self.gateway)
        self._auth = self.auth.refresh()
        self._session = self.auth.start_session()
        # self._device = None
        self._load_devices()

    @classmethod
    def from_token(
        cls, oauth_url, refresh_token, user_number, country=None, language=None
    ) -> "ClientV2":
        """Construct a client using just a refresh token.
            
            This allows simpler state storage (e.g., for human-written
            configuration) but it is a little less efficient because we need
            to reload the gateway servers and restart the session.
            """

        client = cls(
            country=country or DEFAULT_COUNTRY,
            language=language or DEFAULT_LANGUAGE,
        )
        client._auth = Auth(client.gateway, oauth_url, None, refresh_token, user_number)
        client.refresh()
        return client

    @classmethod
    def oauthinfo_from_url(cls, url):
        """Create an authentication using an OAuth callback URL.
        """
        oauth_url, auth_code, user_number = parse_oauth_callback(url)
        access_token, refresh_token = login(oauth_url, auth_code)

        return {
            "oauth_url": oauth_url,
            "user_number": user_number,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    @staticmethod
    def _load_json_info(info_url):
        """Load JSON data from specific url.
        """
        if not info_url:
            return {}
        resp = requests.get(info_url, timeout=DEFAULT_TIMEOUT).text
        enc_resp = resp.encode()
        return json.loads(enc_resp)

    def common_lang_pack(self):
        """Load JSON common lang pack from specific url.
        """
        if self._devices is None:
            return {}
        if self._common_lang_pack is None and self._session:
            self._common_lang_pack = self._load_json_info(
                self._session.common_lang_pack_url
            ).get("pack", {})
        return self._common_lang_pack

    def model_url_info(self, url, device=None):
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
            self._model_url_info[url] = self._load_json_info(url)
        return self._model_url_info[url]
