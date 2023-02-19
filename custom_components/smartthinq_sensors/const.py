"""Constants for LGE ThinQ custom component."""

__version__ = "0.31.4"
PROJECT_URL = "https://github.com/ollo69/ha-smartthinq-sensors/"
ISSUE_URL = f"{PROJECT_URL}issues"

DOMAIN = "smartthinq_sensors"

MIN_HA_MAJ_VER = 2022
MIN_HA_MIN_VER = 11
__min_ha_version__ = f"{MIN_HA_MAJ_VER}.{MIN_HA_MIN_VER}.0"

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
