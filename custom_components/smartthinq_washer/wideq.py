import requests
from urllib.parse import urljoin, urlencode, urlparse, parse_qs
import uuid
import base64
import json
import hashlib
import hmac
import datetime
from collections import namedtuple
import enum
import time

GATEWAY_URL = 'https://kic.lgthinq.com:46030/api/common/gatewayUriList'
APP_KEY = 'wideq'
SECURITY_KEY = 'nuts_securitykey'
DATA_ROOT = 'lgedmRoot'
DEFAULT_COUNTRY = 'IT'
DEFAULT_LANGUAGE = 'it-IT'
SVC_CODE = 'SVC202'
CLIENT_ID = 'LGAO221A02'
OAUTH_SECRET_KEY = 'c053c2a6ddeb7ad97cb0eed0dcb31cf8'
OAUTH_CLIENT_KEY = 'LGAO221A02'
DATE_FORMAT = '%a, %d %b %Y %H:%M:%S +0000'

DEFAULT_TIMEOUT = 10 # seconds
DEFAULT_REFRESH_TIMEOUT = 20 # seconds

"""WASHER STATE"""
STATE_OPTIONITEM_ON = 'On'
STATE_OPTIONITEM_OFF = 'Off'

STATE_WASHER_POWER_OFF = 'Off'
STATE_WASHER_INITIAL = 'Select Course'
STATE_WASHER_PAUSE = 'Paused'
STATE_WASHER_ERROR_AUTO_OFF = 'Automatic Poweroff Error'
STATE_WASHER_RESERVE = 'Reserved'
STATE_WASHER_DETECTING = 'Detecting'
STATE_WASHER_ADD_DRAIN = 'ADD_DRAIN'
STATE_WASHER_DETERGENT_AMOUT = 'Detergent Amount'
STATE_WASHER_RUNNING = 'Washing'
STATE_WASHER_PREWASH = 'Pre-Wash'
STATE_WASHER_RINSING = 'Rinsing'
STATE_WASHER_RINSE_HOLD = 'Rinsing [On Hold]'
STATE_WASHER_SPINNING = 'Spinning'
STATE_WASHER_DRYING = 'Drying'
STATE_WASHER_END = 'End'
STATE_WASHER_REFRESHWITHSTEAM = 'Refreshing with steam'
STATE_WASHER_COOLDOWN = 'Cooldown'
STATE_WASHER_STEAMSOFTENING = 'Using softener with steam'
STATE_WASHER_ERRORSTATE = 'An error occured'
STATE_WASHER_TCL_ALARM_NORMAL = 'Pipe Clogged'
STATE_WASHER_FROZEN_PREVENT_INITIAL = 'Error during initialization'
STATE_WASHER_FROZEN_PREVENT_RUNNING = 'Unfreezing system, please wait'
STATE_WASHER_FROZEN_PREVENT_PAUSE = 'System is being unfrozen, you cannot pause this operation.'
STATE_WASHER_ERROR = 'Error'

STATE_WASHER_WATERTEMP_COLD = 'Cold'
STATE_WASHER_WATERTEMP_20 = '20℃'
STATE_WASHER_WATERTEMP_30 = '30℃'
STATE_WASHER_WATERTEMP_40 = '40℃'
STATE_WASHER_WATERTEMP_60 = '60℃'
STATE_WASHER_WATERTEMP_95 = '95℃'

STATE_WASHER_SPINSPEED_NOSPIN = 'No Spin'
STATE_WASHER_SPINSPEED_400 = '400 RPM'
STATE_WASHER_SPINSPEED_800 = '800 RPM'
STATE_WASHER_SPINSPEED_1000 = '1000 RPM'
STATE_WASHER_SPINSPEED_1200 = '1200 RPM'
STATE_WASHER_SPINSPEED_1400 = '1400 RPM'

STATE_WASHER_NO_ERROR = 'Normal'
STATE_WASHER_ERROR_dE2 = 'Door open - Please close the door'
STATE_WASHER_ERROR_IE = 'No water - Please make sure the water has enough pressure to reach the washer.'
STATE_WASHER_ERROR_OE = 'Drain error - Please make sure the pipe is not clogged/frozen'
STATE_WASHER_ERROR_UE = 'Laundry trim'
STATE_WASHER_ERROR_FE = 'FE - Contact Service Center'
STATE_WASHER_ERROR_PE = 'PE - Contact Service Center'
STATE_WASHER_ERROR_LE = 'LE - Contact Service Center'
STATE_WASHER_ERROR_tE = 'tE - Contact Service Center'
STATE_WASHER_ERROR_dHE = 'dHE - Contact Service Center'
STATE_WASHER_ERROR_CE = 'CE - Contact Service Center'
STATE_WASHER_ERROR_PF = 'PF - Contact Service Center'
STATE_WASHER_ERROR_FF = 'The washer is frozen, please warm up the surrounding area.'
STATE_WASHER_ERROR_dCE = 'dCE - Contact Service Center'
STATE_WASHER_ERROR_EE = 'EE - Contact Service Center'
STATE_WASHER_ERROR_PS = 'PS - Contact Service Center'
STATE_WASHER_ERROR_dE1 = 'Door open - Please close the door'
STATE_WASHER_ERROR_LOE = 'Detergent door is open - Please close the detergent door'
STATE_NO_ERROR = 'Normal'

STATE_WASHER_SMARTCOURSE_SILENT = 'Silent'
STATE_WASHER_SMARTCOURSE_SMALL_LOAD = 'Small Load'
STATE_WASHER_SMARTCOURSE_SKIN_CARE = 'Skin Care'
STATE_WASHER_SMARTCOURSE_RAINY_SEASON = 'Rainy Season'
STATE_WASHER_SMARTCOURSE_SWEAT_STAIN = 'Sweat/Stains Removal'
STATE_WASHER_SMARTCOURSE_SINGLE_GARMENT = 'Single Garment'
STATE_WASHER_SMARTCOURSE_SCHOOL_UNIFORM = 'School Uniform'
STATE_WASHER_SMARTCOURSE_STATIC_REMOVAL = 'Static Removal'
STATE_WASHER_SMARTCOURSE_COLOR_CARE = 'Color Care'
STATE_WASHER_SMARTCOURSE_SPIN_ONLY = 'Spin Only'
STATE_WASHER_SMARTCOURSE_DEODORIZATION = 'Deodorization'
STATE_WASHER_SMARTCOURSE_BEDDING_CARE = 'Bedding Care'
STATE_WASHER_SMARTCOURSE_CLOTH_CARE = 'Cloth Care'
STATE_WASHER_SMARTCOURSE_SMART_RINSE = 'Smart Rinse'
STATE_WASHER_SMARTCOURSE_ECO_WASH = 'Economy Wash'

STATE_WASHER_TERM_NO_SELECT = 'Nothing selected yet'

STATE_WASHER_OPTIONITEM_ON = 'On'
STATE_WASHER_OPTIONITEM_OFF = 'Off'

RUNSTATES = {
    'OFF': STATE_WASHER_POWER_OFF,
    'INITIAL': STATE_WASHER_INITIAL,
    'PAUSE': STATE_WASHER_PAUSE,
    'ERROR_AUTO_OFF': STATE_WASHER_ERROR_AUTO_OFF,
    'RESERVE': STATE_WASHER_RESERVE,
    'DETECTING': STATE_WASHER_DETECTING,
    'ADD_DRAIN': STATE_WASHER_ADD_DRAIN,
    'DETERGENT_AMOUNT': STATE_WASHER_DETERGENT_AMOUT,
    'RUNNING': STATE_WASHER_RUNNING,
    'PREWASH': STATE_WASHER_PREWASH,
    'RINSING': STATE_WASHER_RINSING,
    'RINSE_HOLD': STATE_WASHER_RINSE_HOLD,
    'SPINNING': STATE_WASHER_SPINNING,
    'DRYING': STATE_WASHER_DRYING,
    'END': STATE_WASHER_END,
    'REFRESHWITHSTEAM': STATE_WASHER_REFRESHWITHSTEAM,
    'COOLDOWN': STATE_WASHER_COOLDOWN,
    'STEAMSOFTENING': STATE_WASHER_STEAMSOFTENING,
    'ERRORSTATE': STATE_WASHER_ERRORSTATE,
    'TCL_ALARM_NORMAL': STATE_WASHER_TCL_ALARM_NORMAL,
    'FROZEN_PREVENT_INITIAL': STATE_WASHER_FROZEN_PREVENT_INITIAL,
    'FROZEN_PREVENT_RUNNING': STATE_WASHER_FROZEN_PREVENT_RUNNING,
    'FROZEN_PREVENT_PAUSE': STATE_WASHER_FROZEN_PREVENT_PAUSE,
    'ERROR': STATE_WASHER_ERROR,
}

WATERTEMPSTATES = {
    'NO_SELECT': STATE_WASHER_TERM_NO_SELECT,
    'COLD' : STATE_WASHER_WATERTEMP_COLD,
    'TWENTY' : STATE_WASHER_WATERTEMP_20,
    'THIRTY' : STATE_WASHER_WATERTEMP_30,
    'FOURTY' : STATE_WASHER_WATERTEMP_40,
    'SIXTY': STATE_WASHER_WATERTEMP_60,
    'NINTYFIVE': STATE_WASHER_WATERTEMP_95,
    'OFF': STATE_WASHER_POWER_OFF,

}

SPINSPEEDSTATES = {
    'NOSPIN': STATE_WASHER_SPINSPEED_NOSPIN,
    'SPIN_400' : STATE_WASHER_SPINSPEED_400,
    'SPIN_800' : STATE_WASHER_SPINSPEED_800,
    'SPIN_1000' : STATE_WASHER_SPINSPEED_1000,
    'SPIN_1200': STATE_WASHER_SPINSPEED_1200,
    'SPIN_1400': STATE_WASHER_SPINSPEED_1400,
    'OFF': STATE_WASHER_POWER_OFF,
}

ERRORS = {
    'ERROR_dE2' : STATE_WASHER_ERROR_dE2,
    'ERROR_IE' : STATE_WASHER_ERROR_IE,
    'ERROR_OE' : STATE_WASHER_ERROR_OE,
    'ERROR_UE' : STATE_WASHER_ERROR_UE,
    'ERROR_FE' : STATE_WASHER_ERROR_FE,
    'ERROR_PE' : STATE_WASHER_ERROR_PE,
    'ERROR_tE' : STATE_WASHER_ERROR_tE,
    'ERROR_LE' : STATE_WASHER_ERROR_LE,
    'ERROR_CE' : STATE_WASHER_ERROR_CE,
    'ERROR_PF' : STATE_WASHER_ERROR_PF,
    'ERROR_FF' : STATE_WASHER_ERROR_FF,
    'ERROR_dCE' : STATE_WASHER_ERROR_dCE,
    'ERROR_EE' : STATE_WASHER_ERROR_EE,
    'ERROR_PS' : STATE_WASHER_ERROR_PS,
    'ERROR_dE1' : STATE_WASHER_ERROR_dE1,
    'ERROR_LOE' : STATE_WASHER_ERROR_LOE,
    'NO_ERROR' : STATE_NO_ERROR,
    'OFF': STATE_WASHER_POWER_OFF,
}

OPTIONITEMMODES = {
    'ON': STATE_OPTIONITEM_ON,
    'OFF': STATE_OPTIONITEM_OFF,
}

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


def as_list(obj):
    """Wrap non-lists in lists.

    If `obj` is a list, return it unchanged. Otherwise, return a
    single-element list containing it.
    """

    if isinstance(obj, list):
        return obj
    else:
        return [obj]


class APIError(Exception):
    """An error reported by the API."""

    def __init__(self, code, message):
        self.code = code
        self.message = message


class NotLoggedInError(APIError):
    """The session is not valid or expired."""

    def __init__(self):
        pass


class TokenError(APIError):
    """An authentication token was rejected."""

    def __init__(self):
        pass


class MonitorError(APIError):
    """Monitoring a device failed, possibly because the monitoring
    session failed and needs to be restarted.
    """

    def __init__(self, device_id, code):
        self.device_id = device_id
        self.code = code

class NotConnectError(APIError):
    """The session is not valid or expired."""

    def __init__(self):
        pass


def lgedm_post(url, data=None, access_token=None, session_id=None):
    """Make an HTTP request in the format used by the API servers.

    In this format, the request POST data sent as JSON under a special
    key; authentication sent in headers. Return the JSON data extracted
    from the response.

    The `access_token` and `session_id` are required for most normal,
    authenticated requests. They are not required, for example, to load
    the gateway server data or to start a session.
    """

    headers = {
        'x-thinq-application-key': APP_KEY,
        'x-thinq-security-key': SECURITY_KEY,
        'Accept': 'application/json',
    }
    if access_token:
        headers['x-thinq-token'] = access_token
    if session_id:
        headers['x-thinq-jsessionId'] = session_id

    res = requests.post(url, json={DATA_ROOT: data}, headers=headers, timeout = DEFAULT_TIMEOUT)
    out = res.json()[DATA_ROOT]

    # Check for API errors.
    if 'returnCd' in out:
        code = out['returnCd']
        if code != '0000':
            message = out['returnMsg']
            if code == "0102":
                raise NotLoggedInError()
            elif code == "0106":
                raise NotConnectError()
            else:
                raise APIError(code, message)


    return out


def gateway_info(country, language):
    """Load information about the hosts to use for API interaction.

    `country` and `language` are codes, like "US" and "en-US,"
    respectively.
    """

    # this code to avoid ssl error with DH
    requests.packages.urllib3.disable_warnings()
    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += 'HIGH:!DH:!aNULL'
    try:
        requests.packages.urllib3.contrib.pyopenssl.DEFAULT_SSL_CIPHER_LIST += 'HIGH:!DH:!aNULL'
    except AttributeError:
        # no pyopenssl support used / needed / available
        pass        
    # this code to avoid ssl error with DH

    return lgedm_post(
        GATEWAY_URL,
        {'countryCode': country, 'langCode': language},
    )


def oauth_url(auth_base, country, language):
    """Construct the URL for users to log in (in a browser) to start an
    authenticated session.
    """

    url = urljoin(auth_base, 'login/sign_in')
    query = urlencode({
        'country': country,
        'language': language,
        'svcCode': SVC_CODE,
        'authSvr': 'oauth2',
        'client_id': CLIENT_ID,
        'division': 'ha',
        'grant_type': 'password',
    })
    return '{}?{}'.format(url, query)


def parse_oauth_callback(url):
    """Parse the URL to which an OAuth login redirected to obtain two
    tokens: an access token for API credentials, and a refresh token for
    getting updated access tokens.
    """

    params = parse_qs(urlparse(url).query)
    return params['access_token'][0], params['refresh_token'][0]


def login(api_root, access_token, country, language):
    """Use an access token to log into the API and obtain a session and
    return information about the session.
    """

    url = urljoin(api_root + '/', 'member/login')
    data = {
        'countryCode': country,
        'langCode': language,
        'loginType': 'EMP',
        'token': access_token,
    }
    return lgedm_post(url, data)


def refresh_auth(oauth_root, refresh_token):
    """Get a new access_token using a refresh_token.

    May raise a `TokenError`.
    """

    token_url = urljoin(oauth_root, '/oauth2/token')
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }

    # The timestamp for labeling OAuth requests can be obtained
    # through a request to the date/time endpoint:
    # https://us.lgeapi.com/datetime
    # But we can also just generate a timestamp.
    timestamp = datetime.datetime.utcnow().strftime(DATE_FORMAT)

    # The signature for the requests is on a string consisting of two
    # parts: (1) a fake request URL containing the refresh token, and (2)
    # the timestamp.
    req_url = ('/oauth2/token?grant_type=refresh_token&refresh_token=' +
               refresh_token)
    sig = oauth2_signature('{}\n{}'.format(req_url, timestamp),
                           OAUTH_SECRET_KEY)

    headers = {
        'lgemp-x-app-key': OAUTH_CLIENT_KEY,
        'lgemp-x-signature': sig,
        'lgemp-x-date': timestamp,
        'Accept': 'application/json',
    }

    res = requests.post(token_url, data=data, headers=headers, timeout = DEFAULT_REFRESH_TIMEOUT)
    res_data = res.json()

    if res_data['status'] != 1:
        raise TokenError()
    return res_data['access_token']


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
        return cls(gw['empUri'], gw['thinqUri'], gw['oauthUri'],
                   country, language)

    def oauth_url(self):
        return oauth_url(self.auth_base, self.country, self.language)


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

        session_info = login(self.gateway.api_root, self.access_token,
                             self.gateway.country, self.gateway.language)
        session_id = session_info['jsessionId']
        return Session(self, session_id), as_list(session_info['item'])

    def refresh(self):
        """Refresh the authentication, returning a new Auth object.
        """

        new_access_token = refresh_auth(self.gateway.oauth_root,
                                        self.refresh_token)
        return Auth(self.gateway, new_access_token, self.refresh_token)


class Session(object):
    def __init__(self, auth, session_id):
        self.auth = auth
        self.session_id = session_id

    def post(self, path, data=None):
        """Make a POST request to the API server.

        This is like `lgedm_post`, but it pulls the context for the
        request from an active Session.
        """

        url = urljoin(self.auth.gateway.api_root + '/', path)
        return lgedm_post(url, data, self.auth.access_token, self.session_id)

    def get_devices(self):
        """Get a list of devices associated with the user's account.

        Return a list of dicts with information about the devices.
        """

        return as_list(self.post('device/deviceList')['item'])

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

        # The return data may or may not be present, depending on the
        # monitoring task status.
        if 'returnData' in res:
            # The main response payload is base64-encoded binary data in
            # the `returnData` field. This sometimes contains JSON data
            # and sometimes other binary data.
            return base64.b64decode(res['returnData'])
        else:
            return None
         # Check for errors.
        code = res.get('returnCode')  # returnCode can be missing.
        if code != '0000':
            raise MonitorError(device_id, code)


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

    def delete_permission(self, device_id):
        self.post('rti/delControlPermission', {
            'deviceId': device_id,
        })

class Monitor(object):
    """A monitoring task for a device.
        
        This task is robust to some API-level failures. If the monitoring
        task expires, it attempts to start a new one automatically. This
        makes one `Monitor` object suitable for long-term monitoring.
        """
    
    def __init__(self, session, device_id):
        self.session = session
        self.device_id = device_id
    
    def start(self):
        self.work_id = self.session.monitor_start(self.device_id)
    
    def stop(self):
        self.session.monitor_stop(self.device_id, self.work_id)
    
    def poll(self):
        """Get the current status data (a bytestring) or None if the
            device is not yet ready.
            """
        self.work_id = self.session.monitor_start(self.device_id)
        try:
            return self.session.monitor_poll(self.device_id, self.work_id)
        except MonitorError:
            # Try to restart the task.
            self.stop()
            self.start()
            return None


    @staticmethod
    def decode_json(data):
        """Decode a bytestring that encodes JSON status data."""
        
        return json.loads(data.decode('utf8'))
    
    def poll_json(self):
        """For devices where status is reported via JSON data, get the
            decoded status result (or None if status is not available).
            """
        
        data = self.poll()
        return self.decode_json(data) if data else None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, type, value, tb):
        self.stop()


class Client(object):
    """A higher-level API wrapper that provides a session more easily
        and allows serialization of state.
        """
    
    def __init__(self, gateway=None, auth=None, session=None,
                 country=DEFAULT_COUNTRY, language=DEFAULT_LANGUAGE):
        # The three steps required to get access to call the API.
        self._gateway = gateway
        self._auth = auth
        self._session = session
        
        # The last list of devices we got from the server. This is the
        # raw JSON list data describing the devices.
        self._devices = None
        
        # Cached model info data. This is a mapping from URLs to JSON
        # responses.
        self._model_info = {}

        # Locale information used to discover a gateway, if necessary.
        self._country = country
        self._language = language
        
    @property
    def gateway(self):
        if not self._gateway:
            self._gateway = Gateway.discover(
                self._country, self._language
            )
        return self._gateway
    
    @property
    def auth(self):
        if not self._auth:
            assert False, "unauthenticated"
        return self._auth
    
    @property
    def session(self):
        if not self._session:
            self._session, self._devices = self.auth.start_session()
        return self._session
    
    @property
    def devices(self):
        """DeviceInfo objects describing the user's devices.
            """
        
        if not self._devices:
            self._devices = self.session.get_devices()
        return (DeviceInfo(d) for d in self._devices)
    
    def get_device(self, device_id):
        """Look up a DeviceInfo object by device ID.
            
            Return None if the device does not exist.
            """
        
        for device in self.devices:
            if device.id == device_id:
                return device
        return None
    
    @classmethod
    def load(cls, state):
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

    def dump(self):
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
    
    def refresh(self):
        self._auth = self.auth.refresh()
        self._session, self._devices = self.auth.start_session()
    
    @classmethod
    def from_token(cls, refresh_token, country=None, language=None):
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
    
    def model_info(self, device):
        """For a DeviceInfo object, get a ModelInfo object describing
            the model's capabilities.
            """
        url = device.model_info_url
        if url not in self._model_info:
            self._model_info[url] = device.load_model_info()
        return ModelInfo(self._model_info[url])


class DeviceType(enum.Enum):
    """The category of device."""
    
    WASHER = 201


class DeviceInfo(object):
    """Details about a user's device.
        
    This is populated from a JSON dictionary provided by the API.
    """
    
    def __init__(self, data):
        self.data = data
    
    @property
    def model_id(self):
        return self.data['modelNm']
    
    @property
    def id(self):
        return self.data['deviceId']
    
    @property
    def model_info_url(self):
        return self.data['modelJsonUrl']
    
    @property
    def name(self):
        return self.data['alias']

    @property
    def macaddress(self):
        return self.data['macAddress']

    @property
    def model_name(self):
        return self.data['modelNm']
    
    @property
    def type(self):
        """The kind of device, as a `DeviceType` value."""
        
        return DeviceType(self.data['deviceType'])
    
    def load_model_info(self):
        """Load JSON data describing the model's capabilities.
        """

        return requests.get(self.model_info_url, timeout = DEFAULT_TIMEOUT).json()


EnumValue = namedtuple('EnumValue', ['options'])
RangeValue = namedtuple('RangeValue', ['min', 'max', 'step'])
BitValue = namedtuple('BitValue', ['options'])
ReferenceValue = namedtuple('ReferenceValue', ['reference'])


class ModelInfo(object):
    """A description of a device model's capabilities.
        """
    
    def __init__(self, data):
        self.data = data

    @property
    def model_type(self):
        return self.data['Info']['modelType']
    
    def value_type(self, name):
        if name in self.data['Value']:
            return self.data['Value'][name]['type']
        else:
            return None

    def value(self, name):
        """Look up information about a value.
        
        Return either an `EnumValue` or a `RangeValue`.
        """
        d = self.data['Value'][name]
        if d['type'] in ('Enum', 'enum'):
            return EnumValue(d['option'])
        elif d['type'] == 'Range':
            return RangeValue(d['option']['min'], d['option']['max'], d['option']['step'])
        elif d['type'] == 'Bit':
            bit_values = {}
            for bit in d['option']:
                bit_values[bit['startbit']] = {
                'value' : bit['value'],
                'length' : bit['length'],
                }
            return BitValue(
                    bit_values
                    )
        elif d['type'] == 'Reference':
            ref =  d['option'][0]
            return ReferenceValue(
                    self.data[ref]
                    )
        elif d['type'] == 'Boolean':
            return EnumValue({'0': 'False', '1' : 'True'})
        elif d['type'] == 'String':
            pass 
        else:
            assert False, "unsupported value type {}".format(d['type'])


    def default(self, name):
        """Get the default value, if it exists, for a given value.
        """
            
        return self.data['Value'][name]['default']
        
    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name.
        """
        
        options = self.value(key).options
        options_inv = {v: k for k, v in options.items()}  # Invert the map.
        return options_inv[name]

    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value.
        """
        if not self.value_type(key):
            return str(value)
                
        options = self.value(key).options
        return options[value]

    def range_name(self, key):
        """Look up the value of a RangeValue.  Not very useful other than for comprehension
        """
            
        return key
        
    def bit_name(self, key, bit_index, value):
        """Look up the friendly name for an encoded bit value
        """
        if not self.value_type(key):
            return str(value)
        
        options = self.value(key).options
        
        if not self.value_type(options[bit_index]['value']):
            return str(value)
        
        enum_options = self.value(options[bit_index]['value']).options
        return enum_options[value]

    def reference_name(self, key, value):
        """Look up the friendly name for an encoded reference value
        """
        value = str(value)
        if not self.value_type(key):
            return value
                
        reference = self.value(key).reference
                    
        if value in reference:
            comment = reference[value]['_comment']
            return comment if comment else reference[value]['label']
        else:
            return '-'

    @property
    def binary_monitor_data(self):
        """Check that type of monitoring is BINARY(BYTE).
        """
        
        return self.data['Monitoring']['type'] == 'BINARY(BYTE)'
    
    def decode_monitor_binary(self, data):
        """Decode binary encoded status data.
        """
        
        decoded = {}
        for item in self.data['Monitoring']['protocol']:
            key = item['value']
            value = 0
            for v in data[item['startByte']:item['startByte'] + item['length']]:
                value = (value << 8) + v
            decoded[key] = str(value)
        return decoded
    
    def decode_monitor_json(self, data):
        """Decode a bytestring that encodes JSON status data."""
        
        return json.loads(data.decode('utf8'))
    
    def decode_monitor(self, data):
        """Decode  status data."""
        
        if self.binary_monitor_data:
            return self.decode_monitor_binary(data)
        else:
            return self.decode_monitor_json(data)

class Device(object):
    """A higher-level interface to a specific device.
        
    Unlike `DeviceInfo`, which just stores data *about* a device,
    `Device` objects refer to their client and can perform operations
    regarding the device.
    """

    def __init__(self, client, device):
        """Create a wrapper for a `DeviceInfo` object associated with a
        `Client`.
        """
        
        self.client = client
        self.device = device
        self.model = client.model_info(device)

    def _set_control(self, key, value):
        """Set a device's control for `key` to `value`.
        """
        
        self.client.session.set_device_controls(
            self.device.id,
            {key: value},
            )
    
    def _get_config(self, key):
        """Look up a device's configuration for a given value.
            
        The response is parsed as base64-encoded JSON.
        """
        
        data = self.client.session.get_device_config(
               self.device.id,
               key,
        )
        return json.loads(base64.b64decode(data).decode('utf8'))
    
    def _get_control(self, key):
        """Look up a device's control value.
            """
        
        data = self.client.session.get_device_config(
               self.device.id,
                key,
               'Control',
        )

            # The response comes in a funky key/value format: "(key:value)".
        _, value = data[1:-1].split(':')
        return value


    def _delete_permission(self):
        self.client.session.delete_permission(
            self.device.id,
        )

"""------------------for Washer"""

class WASHERSTATE(enum.Enum):
    
    OFF = "@WM_STATE_POWER_OFF_W"
    INITIAL = "@WM_STATE_INITIAL_W"
    PAUSE = "@WM_STATE_PAUSE_W"
    ERROR_AUTO_OFF = "@WM_STATE_ERROR_AUTO_OFF_W"
    RESERVE = "@WM_STATE_RESERVE_W"
    DETECTING = "@WM_STATE_DETECTING_W"
    ADD_DRAIN = "WM_STATE_ADD_DRAIN_W"
    DETERGENT_AMOUNT = "@WM_STATE_DETERGENT_AMOUNT_W"
    RUNNING = "@WM_STATE_RUNNING_W"
    PREWASH = "@WM_STATE_PREWASH_W"
    RINSING = "@WM_STATE_RINSING_W"
    RINSE_HOLD = "@WM_STATE_RINSEHOLD_W"
    SPINNING = "@WM_STATE_SPINNING_W"
    DRYING = "@WM_STATE_DRYING_W"
    END = "@WM_STATE_END_W"
    REFRESHWITHSTEAM = "@WM_STATE_REFRESHING_W"
    STEAMSOFTENING = "@WM_STATE_STEAMSOFTENING_W"
    COOLDOWN = "@WM_STATE_COOLDOWN_W"
    ERRORSTATE = "@WM_STATE_ERROR_W"
    TCL_ALARM_NORMAL = "TCL_ALARM_NORMAL"
    FROZEN_PREVENT_INITIAL = "@WM_STATE_FROZEN_PREVENT_INITIAL_W"
    FROZEN_PREVENT_RUNNING = "@WM_STATE_FROZEN_PREVENT_RUNNING_W"
    FROZEN_PREVENT_PAUSE = "@WM_STATE_FROZEN_PREVENT_PAUSE_W"

    
class WASHERWATERTEMP(enum.Enum):
    
    NO_SELECT = "@WM_TERM_NO_SELECT_W"
    COLD = "@WM_TITAN2_OPTION_TEMP_COLD_W"
    TWENTY = "@WM_TITAN2_OPTION_TEMP_20_W"
    THIRTY = "@WM_TITAN2_OPTION_TEMP_30_W"
    FOURTY = "@WM_TITAN2_OPTION_TEMP_40_W"
    SIXTY = "@WM_TITAN2_OPTION_TEMP_60_W"
    NINTYFIVE = "@WM_TITAN2_OPTION_TEMP_95_W"

class WASHERSPINSPEED(enum.Enum):
    
    NOSPIN = "@WM_TITAN2_OPTION_SPIN_NO_SPIN_W"
    SPIN_400 = "@WM_TITAN2_OPTION_SPIN_400_W"
    SPIN_800 = "@WM_TITAN2_OPTION_SPIN_800_W"
    SPIN_1000 = "@WM_TITAN2_OPTION_SPIN_1000_W"
    SPIN_1200 = "@WM_TITAN2_OPTION_SPIN_1200_W"
    SPIN_1400 = "@WM_TITAN2_OPTION_SPIN_1400_W"

class WASHERERROR(enum.Enum):
    
    ERROR_dE2 = "@WM_WW_FL_ERROR_DE2_W"
    ERROR_IE = "@WM_WW_FL_ERROR_IE_W"
    ERROR_OE = "@WM_WW_FL_ERROR_OE_W"
    ERROR_UE = "@WM_WW_FL_ERROR_UE_W"
    ERROR_FE = "@WM_WW_FL_ERROR_FE_W"
    ERROR_PE = "@WM_WW_FL_ERROR_PE_W"
    ERROR_tE = "@WM_WW_FL_ERROR_TE_W"
    ERROR_LE = "@WM_WW_FL_ERROR_LE_W"
    ERROR_CE = "@WM_WW_FL_ERROR_CE_W"
    ERROR_dHE = "@WM_WW_FL_ERROR_DHE_W"
    ERROR_PF = "@WM_WW_FL_ERROR_PF_W"
    ERROR_FF = "@WM_WW_FL_ERROR_FF_W"
    ERROR_dCE = "@WM_WW_FL_ERROR_DCE_W"
    ERROR_EE = "@WM_WW_FL_ERROR_EE_W"
    ERROR_PS = "@WM_WW_FL_ERROR_PS_W"
    ERROR_dE1 = "@WM_WW_FL_ERROR_DE1_W"
    ERROR_LOE = "@WM_WW_FL_ERROR_LOE_W"

class WASHREFERROR(enum.Enum):
    
    ERROR_dE2 = "DE2 Error"
    ERROR_IE = "IE Error"
    ERROR_OE = "OE Error"
    ERROR_UE = "UE Error"
    ERROR_FE = "FE Error"
    ERROR_PE = "PE Error"
    ERROR_tE = "TE Error"
    ERROR_LE = "LE Error"
    ERROR_CE = "CE Error"
    ERROR_dHE = "DHE Error"
    ERROR_PF = "PF Error"
    ERROR_FF = "FF Error"
    ERROR_dCE = "DCE Error"
    ERROR_EE = "EE Error"
    ERROR_PS = "PS Error"
    ERROR_dE1 = "DE1 Error"
    ERROR_LOE = "LOE Error"
    NO_ERROR = "No Error"
    OFF = "-"


class WasherDevice(Device):
    
    def monitor_start(self):
        """Start monitoring the device's status."""
        
        self.mon = Monitor(self.client.session, self.device.id)
        self.mon.start()
    
    def monitor_stop(self):
        """Stop monitoring the device's status."""
        
        self.mon.stop()
    
    def delete_permission(self):
        self._delete_permission()
    
    def poll(self):
        """Poll the device's current state.
        
        Monitoring must be started first with `monitor_start`. Return
        either an `ACStatus` object or `None` if the status is not yet
        available.
        """
        
        data = self.mon.poll()
        if data:
            res = self.model.decode_monitor(data)
            """
            with open('/config/wideq/washer_polled_data.json','w', encoding="utf-8") as dumpfile:
                json.dump(res, dumpfile, ensure_ascii=False, indent="\t")
            """
            return WasherStatus(self, res)
        
        else:
            return None

class WasherStatus(object):
    
    def __init__(self, washer, data):
        self.washer = washer
        self.data = data
    
    def lookup_enum(self, key):
        return self.washer.model.enum_name(key, self.data[key])
    
    def lookup_reference(self, key):
        return self.washer.model.reference_name(key, self.data[key])
    
    def lookup_bit(self, key, index):
        bit_value = int(self.data[key])
        bit_index = 2 ** index
        mode = bin(bit_value & bit_index)
        if mode == bin(0):
            return 'OFF'
        else:
            return 'ON'

    @property
    def is_on(self):
        run_state = WASHERSTATE(self.lookup_enum('State'))
        return run_state != WASHERSTATE.OFF
        
    @property
    def run_state(self):
        return WASHERSTATE(self.lookup_enum('State'))

    @property
    def pre_state(self):
        return WASHERSTATE(self.lookup_enum('PreState'))
    
    @property
    def remaintime_hour(self):
        return self.data['Remain_Time_H']
    
    @property
    def remaintime_min(self):
        return self.data['Remain_Time_M']
    
    @property
    def initialtime_hour(self):
        return self.data['Initial_Time_H']
    
    @property
    def initialtime_min(self):
        return self.data['Initial_Time_M']

    @property
    def reservetime_hour(self):
        return self.data['Reserve_Time_H']
    
    @property
    def reservetime_min(self):
        return self.data['Reserve_Time_M']

    @property
    def current_course(self):
        course = self.lookup_reference('Course')
        if course == '-':
            return 'OFF'
        else:
            return course

    @property
    def error_state(self):
        return WASHREFERROR(self.lookup_reference('Error'))
    #    error = self.lookup_reference('Error')
    #    if error == '-':
    #        return 'OFF'
    #    elif error == 'No Error':
    #        return 'NO_ERROR'
    #    else:
    #        return WASHERERROR(error)
    
    @property
    def spin_option_state(self):
        spinspeed = self.lookup_enum('SpinSpeed')
        if spinspeed == '-':
            return 'OFF'
        return WASHERSPINSPEED(spinspeed)

    @property
    def water_temp_option_state(self):
        water_temp = self.lookup_enum('WaterTemp')
        if water_temp == '-':
            return 'OFF'
        return WASHERWATERTEMP(water_temp)
   
    @property
    def current_smartcourse(self):
        smartcourse = self.lookup_reference('SmartCourse')
        if smartcourse == '-':
            return 'OFF'
        else:
            return smartcourse

    @property
    def creasecare_state(self):
        return self.lookup_bit('Option1', 1)

    @property
    def childlock_state(self):
        return self.lookup_bit('Option2', 7)

    @property
    def steam_state(self):
        return self.lookup_bit('Option1', 7)

    @property
    def steam_softener_state(self):
        return self.lookup_bit('Option1', 2)

    @property
    def doorlock_state(self):
        return self.lookup_bit('Option2', 6)

    @property
    def prewash_state(self):
        return self.lookup_bit('Option1', 6)

    @property
    def remotestart_state(self):
        return self.lookup_bit('Option2', 1)

    @property
    def turbowash_state(self):
        return self.lookup_bit('Option1', 0)

    @property
    def tubclean_count(self):
        return self.data['TCLCount']