"""A low-level, general abstraction for the LG SmartThinQ API.
"""
import base64
import uuid
from urllib.parse import urljoin, urlencode, urlparse, parse_qs, quote
import hashlib
import hmac
import datetime
import requests

from . import core_exceptions as exc
from . import core
from .device import DeviceInfo, ModelInfo, DEFAULT_TIMEOUT

#v2
V2_API_KEY = 'VGhpblEyLjAgU0VSVklDRQ=='
V2_CLIENT_ID = '65260af7e8e6547b51fdccf930097c51eb9885a508d3fddfa9ee6cdec22ae1bd'
V2_MESSAGE_ID = 'wideq'
V2_SVC_PHASE = 'OP'
V2_APP_LEVEL = 'PRD'
V2_APP_OS = 'LINUX'
V2_APP_TYPE = 'NUTS'
V2_APP_VER = '3.0.1700'
V2_DATA_ROOT = 'result'

# new
V2_GATEWAY_URL = 'https://route.lgthinq.com:46030/v1/service/application/gateway-uri'
OAUTH_REDIRECT_URI = 'https://kr.m.lgaccount.com/login/iabClose'

# orig
SECURITY_KEY = 'nuts_securitykey'
SVC_CODE = 'SVC202'
CLIENT_ID = 'LGAO221A02'
OAUTH_SECRET_KEY = 'c053c2a6ddeb7ad97cb0eed0dcb31cf8'
DATE_FORMAT = '%a, %d %b %Y %H:%M:%S +0000'


def gen_uuid():
    return str(uuid.uuid4())


def oauth2_signature(message, secret):
    """Get the base64-encoded SHA-1 HMAC digest of a string, as used in
    OAauth2 request signatures.

    Both the `secret` and `message` are given as text strings. We use
    their UTF-8 equivalents.
    """

    secret_bytes = secret.encode('utf8')
    hashed = hmac.new(secret_bytes, message.encode('utf8'), hashlib.sha1)
    digest = hashed.digest()
    return base64.b64encode(digest)


def get_list(obj, key):
    """Look up a list using a key from an object.

    If `obj[key]` is a list, return it unchanged. If is something else,
    return a single-element list containing it. If the key does not
    exist, return an empty list.
    """
    try:
        val = obj[key]
    except KeyError:
        return []

    if isinstance(val, list):
        return val
    else:
        return [val]


def thinq2_headers(extra_headers={}, access_token=None, user_number=None, country="US", language="en-US"):
    
    headers = {
        'Accept': 'application/json',
        'Content-type': 'application/json;charset=UTF-8',
        'x-api-key': V2_API_KEY,
        'x-client-id': V2_CLIENT_ID,
        'x-country-code': country,
        'x-language-code': language,
        'x-message-id': V2_MESSAGE_ID,
        'x-service-code': SVC_CODE,
        'x-service-phase': V2_SVC_PHASE,
        'x-thinq-app-level': V2_APP_LEVEL,
        'x-thinq-app-os': V2_APP_OS,
        'x-thinq-app-type': V2_APP_TYPE,
        'x-thinq-app-ver': V2_APP_VER,
        'x-thinq-security-key': SECURITY_KEY,
    }

    if access_token:
        headers['x-emp-token'] = access_token
   
    if user_number:
        headers['x-user-no'] = user_number

    return { **headers, **extra_headers }

def thinq2_get(url, access_token=None, user_number=None, headers={}, country="US", language="en-US"):
    
    res = requests.get(
        url,
        headers=thinq2_headers(
            access_token=access_token, user_number=user_number, extra_headers=headers, country=country, language=language
        ),
        timeout = DEFAULT_TIMEOUT
    )

    out = res.json()

    if 'resultCode' in out:
        code = out['resultCode']
        if code != '0000':
            if code == "0102":
                raise exc.NotLoggedInError()
            elif code == "0106":
                raise exc.NotConnectedError()
            else:
                raise exc.APIError(code, "error")
    
    return out['result']

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
    return params['oauth2_backend_url'][0], params['code'][0], params['user_number'][0]

def auth_request(oauth_url, data):
    """Use an auth code to log into the v2 API and obtain an access token 
    and refresh token.
    """
    auth_path = '/oauth/1.0/oauth2/token'
    url = urljoin(oauth_url, '/oauth/1.0/oauth2/token')
    timestamp = datetime.datetime.utcnow().strftime(DATE_FORMAT)
    req_url = '{}?{}'.format(auth_path, urlencode(data))
    sig = oauth2_signature('{}\n{}'.format(req_url, timestamp), OAUTH_SECRET_KEY)

    headers = {
        'x-lge-appkey': CLIENT_ID,
        'x-lge-oauth-signature': sig,
        'x-lge-oauth-date': timestamp,
        'Accept': 'application/json'
    }

    res = requests.post(url, headers=headers, data=data, timeout = DEFAULT_TIMEOUT)

    if res.status_code != 200:
        raise exc.TokenError()

    return res.json()

def login(oauth_url, auth_code):
    """Get a new access_token using an authorization_code
    
    May raise a `tokenError`.
    """

    out = auth_request(oauth_url, {
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': OAUTH_REDIRECT_URI
    })
    
    return out['access_token'], out['refresh_token']

def refresh_auth(oauth_root, refresh_token):
    """Get a new access_token using a refresh_token.

    May raise a `TokenError`.
    """
    out = auth_request(oauth_root, {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    })

    return out['access_token']

class Gateway(core.Gateway):
    @classmethod
    def discover(cls, country, language):
        gw = gateway_info(country, language)
        return cls(gw['empUri'], gw['thinq2Uri'], gw['empUri'],
                   country, language)
    
    def oauth_url(self):
        """Construct the URL for users to log in (in a browser) to start an
        authenticated session.
        """

        url = urljoin(self.auth_base, 'spx/login/signIn')
        query = urlencode({
            'country': self.country,
            'language': self.language,
            'svc_list': SVC_CODE,
            'client_id': CLIENT_ID,
            'division': 'ha',
            'redirect_uri': OAUTH_REDIRECT_URI,
            'state': uuid.uuid1().hex,
            'show_thirdparty_login': 'GGL,AMZ,FBK'
        })
        return '{}?{}'.format(url, query)

    def dump(self):
        return {
            'auth_base': self.auth_base,
            'api_root': self.api_root,
            'oauth_root': self.oauth_root,
            'country': self.country,
            'language': self.language
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

    def start_session(self, api_version=1):
        """Start an API session for the logged-in user. Return the
        Session object and a list of the user's devices.
        """
        #access_token, refresh_token = login(self.oauth_url, self.auth_code,
        #                     self.gateway.country, self.gateway.language)
        #session_id = session_info['jsessionId']
        return Session(self), []
        #return Session(self, session_id), get_list(session_info, 'item')

    def refresh(self):
        """Refresh the authentication, returning a new Auth object.
        """

        new_access_token = refresh_auth(self.oauth_url,
                                        self.refresh_token)
        return Auth(self.gateway, self.oauth_url, new_access_token, self.refresh_token, self.user_number)

    def dump(self):
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'oauth_url': self.oauth_url,
            'user_number': self.user_number
        }

    @classmethod
    def load(cls, gateway, data):
      return cls(gateway, data['oauth_url'], data['access_token'], data['refresh_token'], data['user_number'])

class Session(object):
    def __init__(self, auth, session_id=None):
        self.auth = auth
        self.session_id = session_id

    def post(self, path, data=None):
        """Make a POST request to the API server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """

        url = urljoin(self.auth.gateway.api_root + '/', path)
        return lgedm_post(url, data, self.auth.access_token, self.session_id)

    def post2(self, path, data=None):
        url = urljoin(self.auth.gateway.api_root + '/', path)
        return lgedm_post(url, data, self.auth.access_token, self.session_id)

    def get2(self, path):
        url = urljoin(self.auth.gateway.api_root + '/', path)
        return thinq2_get(url, self.auth.access_token, self.auth.user_number, country=self.auth.gateway.country, language=self.auth.gateway.language)

    def get_devices(self):
        """Get a list of devices associated with the user's account.

        Return a list of dicts with information about the devices.
        """
        return get_list(self.get2('service/application/dashboard'), 'item')

    def monitor_start(self, device_id):
        """Begin monitoring a device's status.

        Return a "work ID" that can be used to retrieve the result of
        monitoring.
        """

        res = self.post('rti/rtiMon', {
            'cmd': 'Mon',
            'cmdOpt': 'Start',
            'deviceId': device_id,
            'workId': gen_uuid(),
        })
        return res['workId']

    def monitor_poll(self, device_id, work_id):
        """Get the result of a monitoring task.

        `work_id` is a string ID retrieved from `monitor_start`. Return
        a status result, which is a bytestring, or None if the
        monitoring is not yet ready.

        May raise a `MonitorError`, in which case the right course of
        action is probably to restart the monitoring task.
        """

        work_list = [{'deviceId': device_id, 'workId': work_id}]
        res = self.post('rti/rtiResult', {'workList': work_list})['workList']

        # When monitoring first starts, it usually takes a few
        # iterations before data becomes available. In the initial
        # "warmup" phase, `returnCode` is missing from the response.
        if 'returnCode' not in res:
            return None

        # Check for errors.
        code = res.get('returnCode')  # returnCode can be missing.
        if code != '0000':
            raise exc.MonitorError(device_id, code)

        # The return data may or may not be present, depending on the
        # monitoring task status.
        if 'returnData' in res:
            # The main response payload is base64-encoded binary data in
            # the `returnData` field. This sometimes contains JSON data
            # and sometimes other binary data.
            return base64.b64decode(res['returnData'])
        else:
            return None

    def monitor_stop(self, device_id, work_id):
        """Stop monitoring a device."""

        self.post('rti/rtiMon', {
            'cmd': 'Mon',
            'cmdOpt': 'Stop',
            'deviceId': device_id,
            'workId': work_id,
        })

    def set_device_controls(self, device_id, values):
        """Control a device's settings.

        `values` is a key/value map containing the settings to update.
        """

        return self.post('rti/rtiControl', {
            'cmd': 'Control',
            'cmdOpt': 'Set',
            'value': values,
            'deviceId': device_id,
            'workId': gen_uuid(),
            'data': '',
        })

    def get_device_config(self, device_id, key, category='Config'):
        """Get a device configuration option.

        The `category` string should probably either be "Config" or
        "Control"; the right choice appears to depend on the key.
        """

        res = self.post('rti/rtiControl', {
            'cmd': category,
            'cmdOpt': 'Get',
            'value': key,
            'deviceId': device_id,
            'workId': gen_uuid(),
            'data': '',
        })
        return res['returnData']


class ClientV2(object):
    """A higher-level API wrapper that provides a session more easily
        and allows serialization of state.
        """
    
    def __init__(self, 
                 gateway: Optional[Gateway] = None,
                 auth: Optional[Auth] = None,
                 session: Optional[Session] = None,
                 country: str = DEFAULT_COUNTRY,
                 language: str = DEFAULT_LANGUAGE) -> None:
        # The three steps required to get access to call the API.
        self._gateway: Optional[Gateway] = gateway
        self._auth: Optional[Auth] = auth
        self._session: Optional[Session] = session
        
        # The last list of devices we got from the server. This is the
        # raw JSON list data describing the devices.
        self._devices = None
        
        # Cached model info data. This is a mapping from URLs to JSON
        # responses.
        self._model_info: Dict[str, Any] = {}

        # Locale information used to discover a gateway, if necessary.
        self._country = country
        self._language = language
        
    @property
    def gateway(self) -> Gateway:
        if not self._gateway:
            self._gateway = Gateway.discover(
                self._country, self._language
            )
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
    def devices(self) -> Generator['DeviceInfo', None, None]:
        """DeviceInfo objects describing the user's devices.
            """
        
        if self._devices is None:
            self._devices = self.session.get_devices()
        return (DeviceInfo(d) for d in self._devices)
    
    def get_device(self, device_id) -> Optional['DeviceInfo']:
        """Look up a DeviceInfo object by device ID.
            
            Return None if the device does not exist.
            """
        
        for device in self.devices:
            if device.id == device_id:
                return device
        return None
    
    @classmethod
    def load(cls, state: Dict[str, Any]) -> 'Client':
        """Load a client from serialized state.
            """
        
        client = cls()
        
        if 'gateway' in state:
            data = state['gateway']
            client._gateway = Gateway(
                data['auth_base'], data['api_root'], data['oauth_root'],
                data.get('country', DEFAULT_COUNTRY),
                data.get('language', DEFAULT_LANGUAGE),
            )
        
        if 'auth' in state:
            data = state['auth']
            client._auth = Auth(
            client.gateway, data['access_token'], data['refresh_token']
            )
        
        if 'session' in state:
            client._session = Session(client.auth, state['session'])
                
        if 'model_info' in state:
            client._model_info = state['model_info']

        if 'country' in state:
            client._country = state['country']

        if 'language' in state:
            client._language = state['language']
            
        return client

    def dump(self) -> Dict[str, Any]:
        """Serialize the client state."""
        
        out = {
            'model_info': self._model_info,
        }
        
        if self._gateway:
            out['gateway'] = {
                'auth_base': self._gateway.auth_base,
                'api_root': self._gateway.api_root,
                'oauth_root': self._gateway.oauth_root,
                'country': self._gateway.country,
                'language': self._gateway.language,
        }
        
        if self._auth:
            out['auth'] = {
                'access_token': self._auth.access_token,
                'refresh_token': self._auth.refresh_token,
        }

        if self._session:
            out['session'] = self._session.session_id

        out['country'] = self._country
        out['language'] = self._language
            
        return out
    
    def refresh(self) -> None:
        self._auth = self.auth.refresh()
        self._session, self._devices = self.auth.start_session()
    
    @classmethod
    def from_token(cls, refresh_token, country=None, language=None) -> 'Client':
        """Construct a client using just a refresh token.
            
            This allows simpler state storage (e.g., for human-written
            configuration) but it is a little less efficient because we need
            to reload the gateway servers and restart the session.
            """
        
        client = cls(
            country=country or DEFAULT_COUNTRY,
            language=language or DEFAULT_LANGUAGE,
        )
        client._auth = Auth(client.gateway, None, refresh_token)
        client.refresh()
        return client
    
    def model_info(self, device) -> 'ModelInfo':
        """For a DeviceInfo object, get a ModelInfo object describing
            the model's capabilities.
            """
        url = device.model_info_url
        if url not in self._model_info:
            self._model_info[url] = device.load_model_info()
        return ModelInfo(self._model_info[url])
