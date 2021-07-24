"""A low-level, general abstraction for the LG SmartThinQ API.
"""
import base64
import hashlib
import hmac
import logging
import requests

from datetime import datetime
from urllib.parse import urljoin, urlencode, urlparse, parse_qs
from typing import Any, Dict, Generator, Optional

from . import(
    as_list,
    gen_uuid,
    AuthHTTPAdapter,
    CoreVersion,
    DATA_ROOT,
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
)
from . import core_exceptions as exc
from .device import DeviceInfo, DEFAULT_TIMEOUT, DEFAULT_REFRESH_TIMEOUT

CORE_VERSION = CoreVersion.CoreV1

GATEWAY_URL = "https://kic.lgthinq.com:46030/api/common/gatewayUriList"
APP_KEY = "wideq"
SECURITY_KEY = "nuts_securitykey"
SVC_CODE = "SVC202"
CLIENT_ID = "LGAO221A02"
OAUTH_SECRET_KEY = "c053c2a6ddeb7ad97cb0eed0dcb31cf8"
OAUTH_CLIENT_KEY = "LGAO221A02"
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S +0000"

API_ERRORS = {
    "0102": exc.NotLoggedInError,
    "0106": exc.NotConnectedError,
    "0100": exc.FailedRequestError,
    "0110": exc.InvalidCredentialError,
    9000: exc.InvalidRequestError,  # Surprisingly, an integer (not a string).
}

_LOGGER = logging.getLogger(__name__)


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


def lgedm_post(url, data=None, access_token=None, session_id=None, use_tlsv1=True):
    """Make an HTTP request in the format used by the API servers.

    In this format, the request POST data sent as JSON under a special
    key; authentication sent in headers. Return the JSON data extracted
    from the response.

    The `access_token` and `session_id` are required for most normal,
    authenticated requests. They are not required, for example, to load
    the gateway server data or to start a session.
    """

    _LOGGER.debug("lgedm_post before: %s", url)

    headers = {
        "x-thinq-application-key": APP_KEY,
        "x-thinq-security-key": SECURITY_KEY,
        "Accept": "application/json",
    }
    if access_token:
        headers["x-thinq-token"] = access_token
    if session_id:
        headers["x-thinq-jsessionId"] = session_id

    s = requests.Session()
    s.mount(url, AuthHTTPAdapter(use_tls_v1=use_tlsv1, exclude_dh=True))
    res = s.post(url, json={DATA_ROOT: data}, headers=headers, timeout=DEFAULT_TIMEOUT)

    out = res.json()
    _LOGGER.debug("lgedm_post after: %s", out)

    msg = out.get(DATA_ROOT)
    if not msg:
        raise exc.APIError("-1", out)

    # Check for API errors.
    if "returnCd" in msg:
        code = msg["returnCd"]
        if code != "0000":
            message = msg["returnMsg"]
            if code in API_ERRORS:
                raise API_ERRORS[code]()
            raise exc.APIError(code, message)

    return msg


def gateway_info(country, language):
    """Load information about the hosts to use for API interaction.

    `country` and `language` are codes, like "US" and "en-US,"
    respectively.
    """

    return lgedm_post(GATEWAY_URL, {"countryCode": country, "langCode": language},)


def oauth_url(auth_base, country, language):
    """Construct the URL for users to log in (in a browser) to start an
    authenticated session.
    """

    url = urljoin(auth_base, "login/sign_in")
    query = urlencode(
        {
            "country": country,
            "language": language,
            "svcCode": SVC_CODE,
            "authSvr": "oauth2",
            "client_id": CLIENT_ID,
            "division": "ha",
            "grant_type": "password",
        }
    )
    return "{}?{}".format(url, query)


def parse_oauth_callback(url):
    """Parse the URL to which an OAuth login redirected to obtain two
    tokens: an access token for API credentials, and a refresh token for
    getting updated access tokens.
    """

    params = parse_qs(urlparse(url).query)
    return params["access_token"][0], params["refresh_token"][0]


def login(api_root, access_token, country, language):
    """Use an access token to log into the API and obtain a session and
    return information about the session.
    """

    url = urljoin(api_root + "/", "member/login")
    data = {
        "countryCode": country,
        "langCode": language,
        "loginType": "EMP",
        "token": access_token,
    }
    return lgedm_post(url, data)


def refresh_auth(oauth_root, refresh_token, use_tlsv1=True):
    """Get a new access_token using a refresh_token.

    May raise a `TokenError`.
    """

    token_url = urljoin(oauth_root, "/oauth2/token")
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    # The timestamp for labeling OAuth requests can be obtained
    # through a request to the date/time endpoint:
    # https://us.lgeapi.com/datetime
    # But we can also just generate a timestamp.
    timestamp = datetime.utcnow().strftime(DATE_FORMAT)

    # The signature for the requests is on a string consisting of two
    # parts: (1) a fake request URL containing the refresh token, and (2)
    # the timestamp.
    req_url = "/oauth2/token?grant_type=refresh_token&refresh_token=" + refresh_token
    sig = oauth2_signature("{}\n{}".format(req_url, timestamp), OAUTH_SECRET_KEY)

    headers = {
        "lgemp-x-app-key": OAUTH_CLIENT_KEY,
        "lgemp-x-signature": sig,
        "lgemp-x-date": timestamp,
        "Accept": "application/json",
    }

    s = requests.Session()
    s.mount(token_url, AuthHTTPAdapter(use_tls_v1=use_tlsv1, exclude_dh=True))
    res = s.post(token_url, data=data, headers=headers, timeout=DEFAULT_REFRESH_TIMEOUT)

    res_data = res.json()
    _LOGGER.debug(res_data)

    if res_data["status"] != 1:
        raise exc.TokenError()
    return res_data["access_token"]


class Gateway(object):
    def __init__(self, auth_base, api_root, oauth_root, country, language):
        self.auth_base = auth_base
        self.api_root = api_root
        self.oauth_root = oauth_root
        self.country = country
        self.language = language

    @classmethod
    def discover(cls, country, language):
        gw = gateway_info(country, language)
        return cls(gw["empUri"], gw["thinqUri"], gw["oauthUri"], country, language)

    def get_tokens(self, url):
        """Create an authentication using an OAuth callback URL.
        """
        access_token, refresh_token = parse_oauth_callback(url)
        return {"access_token": access_token, "refresh_token": refresh_token}

    def oauth_url(self):
        return oauth_url(self.auth_base, self.country, self.language)

    def dump(self):
        return {
            "auth_base": self.auth_base,
            "api_root": self.api_root,
            "oauth_root": self.oauth_root,
            "country": self.country,
            "language": self.language,
        }


class Auth(object):
    def __init__(self, gateway, access_token, refresh_token):
        self.gateway = gateway
        self.access_token = access_token
        self.refresh_token = refresh_token

    @classmethod
    def from_url(cls, gateway, url):
        """Create an authentication using an OAuth callback URL.
        """

        access_token, refresh_token = parse_oauth_callback(url)
        return cls(gateway, access_token, refresh_token)

    def start_session(self):
        """Start an API session for the logged-in user. Return the
        Session object and a list of the user's devices.
        """

        session_info = login(
            self.gateway.api_root,
            self.access_token,
            self.gateway.country,
            self.gateway.language,
        )
        session_id = session_info["jsessionId"]
        devices = session_info.get("item", [])
        return Session(self, session_id), as_list(devices)

    def refresh(self):
        """Refresh the authentication, returning a new Auth object.
        """

        new_access_token = refresh_auth(self.gateway.oauth_root, self.refresh_token)
        return Auth(self.gateway, new_access_token, self.refresh_token)

    def refresh_gateway(self, gateway):
        """Refresh the gateway.
        """
        self.gateway = gateway

    def dump(self):
        return {"access_token": self.access_token, "refresh_token": self.refresh_token}


class Session(object):
    def __init__(self, auth, session_id):
        self.auth = auth
        self.session_id = session_id
        self._common_lang_pack_url = None

    @property
    def common_lang_pack_url(self):
        return self._common_lang_pack_url

    def post(self, path, data=None):
        """Make a POST request to the API server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """

        url = urljoin(self.auth.gateway.api_root + "/", path)
        return lgedm_post(url, data, self.auth.access_token, self.session_id)

    def get_devices(self):
        """Get a list of devices associated with the user's account.

        Return a list of dicts with information about the devices.
        """

        devices = self.post("device/deviceList")
        if self._common_lang_pack_url is None:
            self._common_lang_pack_url = devices.get("langPackCommonUri")
        return as_list(devices.get("item", []))

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

    def set_device_controls(self, device_id, ctrl_key, command=None, value=None, data=None):
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

    def delete_permission(self, device_id):
        self.post("rti/delControlPermission", {"deviceId": device_id})


class Client(object):
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
            self._session, self._devices = self.auth.start_session()
        return self._session

    @property
    def hasdevices(self) -> bool:
        return True if self._devices else False

    @property
    def devices(self) -> Generator["DeviceInfo", None, None]:
        """DeviceInfo objects describing the user's devices.
            """

        if self._devices is None:
            self._devices = self.session.get_devices()
        return (DeviceInfo(d) for d in self._devices)

    def refresh_devices(self):
        return

    def get_device(self, device_id) -> Optional["DeviceInfo"]:
        """Look up a DeviceInfo object by device ID.
            Return None if the device does not exist.
            """

        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    @classmethod
    def load(cls, state: Dict[str, Any]) -> "Client":
        """Load a client from serialized state.
            """

        client = cls()

        if "gateway" in state:
            data = state["gateway"]
            client._gateway = Gateway(
                data["auth_base"],
                data["api_root"],
                data["oauth_root"],
                data.get("country", DEFAULT_COUNTRY),
                data.get("language", DEFAULT_LANGUAGE),
            )

        if "auth" in state:
            data = state["auth"]
            client._auth = Auth(
                client.gateway, data["access_token"], data["refresh_token"]
            )

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
                "oauth_root": self._gateway.oauth_root,
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
        self._session, self._devices = self.auth.start_session()

    @classmethod
    def from_token(cls, refresh_token, country=None, language=None) -> "Client":
        """Construct a client using just a refresh token.
            
            This allows simpler state storage (e.g., for human-written
            configuration) but it is a little less efficient because we need
            to reload the gateway servers and restart the session.
            """

        client = cls(
            country=country or DEFAULT_COUNTRY, language=language or DEFAULT_LANGUAGE,
        )
        client._auth = Auth(client.gateway, None, refresh_token)
        client.refresh()
        return client

    @classmethod
    def oauthinfo_from_url(cls, url):
        """Create an authentication using an OAuth callback URL.
        """
        access_token, refresh_token = parse_oauth_callback(url)
        return {"access_token": access_token, "refresh_token": refresh_token}

    @staticmethod
    def _load_json_info(info_url):
        """Load JSON data from specific url.
        """
        if not info_url:
            return {}
        return requests.get(info_url, timeout=DEFAULT_TIMEOUT).json()

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
