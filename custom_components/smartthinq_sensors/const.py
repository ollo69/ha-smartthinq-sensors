"""Constants for LGE ThinQ custom component."""

__version__ = "0.39.0"
PROJECT_URL = "https://github.com/ollo69/ha-smartthinq-sensors/"
ISSUE_URL = f"{PROJECT_URL}issues"

DOMAIN = "smartthinq_sensors"

MIN_HA_MAJ_VER = 2024
MIN_HA_MIN_VER = 2
__min_ha_version__ = f"{MIN_HA_MAJ_VER}.{MIN_HA_MIN_VER}.0"

# general sensor attributes
ATTR_CURRENT_COURSE = "current_course"
ATTR_ERROR_STATE = "error_state"
ATTR_INITIAL_TIME = "initial_time"
ATTR_REMAIN_TIME = "remain_time"
ATTR_RESERVE_TIME = "reserve_time"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_RUN_COMPLETED = "run_completed"

# refrigerator sensor attributes
ATTR_DOOR_OPEN = "door_open"
ATTR_FRIDGE_TEMP = "fridge_temp"
ATTR_FREEZER_TEMP = "freezer_temp"
ATTR_TEMP_UNIT = "temp_unit"

# range sensor attributes
ATTR_OVEN_LOWER_TARGET_TEMP = "oven_lower_target_temp"
ATTR_OVEN_UPPER_TARGET_TEMP = "oven_upper_target_temp"
ATTR_OVEN_TEMP_UNIT = "oven_temp_unit"

# configuration
CONF_LANGUAGE = "language"
CONF_OAUTH2_URL = "oauth2_url"
CONF_USE_API_V2 = "use_api_v2"
CONF_USE_HA_SESSION = "use_ha_session"
CONF_USE_REDIRECT = "use_redirect"

CLIENT = "client"
LGE_DEVICES = "lge_devices"

LGE_DISCOVERY_NEW = f"{DOMAIN}_discovery_new"

DEFAULT_ICON = "def_icon"
DEFAULT_SENSOR = "default"

STARTUP = f"""
-------------------------------------------------------------------
{DOMAIN}
Version: {__version__}
This is a custom component
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
