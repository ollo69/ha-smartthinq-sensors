"""
Support for LG Smartthinq device.
"""
from logging import DEBUG, INFO
import ssl
import uuid

from enum import Enum
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import DEFAULT_CIPHERS
from requests.adapters import HTTPAdapter

DATA_ROOT = "lgedmRoot"
DEFAULT_COUNTRY = "US"
DEFAULT_LANGUAGE = "en-US"

# ac devices features
FEAT_ENERGY_CURRENT = "energy_current"
FEAT_HUMIDITY = "humidity"
FEAT_HOT_WATER_TEMP = "hot_water_temperature"
FEAT_IN_WATER_TEMP = "in_water_temperature"
FEAT_OUT_WATER_TEMP = "out_water_temperature"

# wash devices features
FEAT_DRYLEVEL = "dry_level"
FEAT_ERROR_MSG = "error_message"
FEAT_PRE_STATE = "pre_state"
FEAT_PROCESS_STATE = "process_state"
FEAT_RUN_STATE = "run_state"
FEAT_SPINSPEED = "spin_speed"
FEAT_TEMPCONTROL = "temp_control"
FEAT_TIMEDRY = "time_dry"
FEAT_TUBCLEAN_COUNT = "tubclean_count"
FEAT_WATERTEMP = "water_temp"

FEAT_CHILDLOCK = "child_lock"
FEAT_CREASECARE = "crease_care"
FEAT_DELAYSTART = "delay_start"
FEAT_DOORCLOSE = "door_close"
FEAT_DOORLOCK = "door_lock"
FEAT_DOOROPEN = "door_open"
FEAT_DUALZONE = "dual_zone"
FEAT_ENERGYSAVER = "energy_saver"
FEAT_HALFLOAD = "half_load"
FEAT_MEDICRINSE = "medic_rinse"
FEAT_NIGHTDRY = "night_dry"
FEAT_PREWASH = "pre_wash"
FEAT_REMOTESTART = "remote_start"
FEAT_RINSEREFILL = "rinse_refill"
FEAT_SALTREFILL = "salt_refill"
FEAT_STANDBY = "standby"
FEAT_STEAM = "steam"
FEAT_STEAMSOFTENER = "steam_softener"
FEAT_TURBOWASH = "turbo_wash"

# SPECIALS GTI
FEAT_ANTICREASE = "anti_crease"
FEAT_DAMPDRYBEEP = "damp_dry_beep"
FEAT_ECOHYBRID = "eco_hybrid"
FEAT_HANDIRON = "hand_iron"
FEAT_RESERVATION = "reservation"
FEAT_SELFCLEAN = "self_clean"

# refrigerator device features
FEAT_ECOFRIENDLY = "eco_friendly"
FEAT_EXPRESSMODE = "express_mode"
FEAT_EXPRESSFRIDGE = "express_fridge"
FEAT_FRESHAIRFILTER = "fresh_air_filter"
FEAT_ICEPLUS = "ice_plus"
FEAT_SMARTSAVINGMODE = "smart_saving_mode"
# FEAT_SMARTSAVING_STATE = "smart_saving_state"
FEAT_WATERFILTERUSED_MONTH = "water_filter_used_month"

# range device features
FEAT_COOKTOP_LEFT_FRONT_STATE = "cooktop_left_front_state"
FEAT_COOKTOP_LEFT_REAR_STATE = "cooktop_left_rear_state"
FEAT_COOKTOP_CENTER_STATE = "cooktop_center_state"
FEAT_COOKTOP_RIGHT_FRONT_STATE = "cooktop_right_front_state"
FEAT_COOKTOP_RIGHT_REAR_STATE = "cooktop_right_rear_state"
FEAT_OVEN_LOWER_CURRENT_TEMP = "oven_lower_current_temp"
FEAT_OVEN_LOWER_STATE = "oven_lower_state"
FEAT_OVEN_UPPER_CURRENT_TEMP = "oven_upper_current_temp"
FEAT_OVEN_UPPER_STATE = "oven_upper_state"

# air purifier device features
FEAT_LOWER_FILTER_LIFE = "lower_filter_life"
FEAT_UPPER_FILTER_LIFE = "upper_filter_life"

# request ciphers settings
CIPHERS = ":HIGH:!DH:!aNULL"

# enable emulation mode for debug / test
EMULATION = False


def as_list(obj):
    """Wrap non-lists in lists.

    If `obj` is a list, return it unchanged. Otherwise, return a
    single-element list containing it.
    """

    if isinstance(obj, list):
        return obj
    else:
        return [obj]


def gen_uuid():
    return str(uuid.uuid4())


def wideq_log_level():
    return INFO if EMULATION else DEBUG


class CoreVersion(Enum):
    """The version of the core API."""

    CoreV1 = "coreV1"
    CoreV2 = "coreV2"


class AuthHTTPAdapter(HTTPAdapter):
    def __init__(self, use_tls_v1=False, exclude_dh=False):
        self._use_tls_v1 = use_tls_v1
        self._exclude_dh = exclude_dh
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        """
        Secure settings adding required ciphers
        """
        context = ssl.create_default_context()  # SSLContext()
        ciphers = DEFAULT_CIPHERS
        if self._exclude_dh:
            ciphers += CIPHERS

        context.set_ciphers(ciphers)
        self.poolmanager = PoolManager(
            *args,
            ssl_context=context,
            ssl_version=ssl.PROTOCOL_TLSv1 if self._use_tls_v1 else None,
            **kwargs,
        )
