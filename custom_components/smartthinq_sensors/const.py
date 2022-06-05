"""
Support to interface with LGE ThinQ Devices.
"""

__version__ = "0.23.0"
PROJECT_URL = "https://github.com/ollo69/ha-smartthinq-sensors/"
ISSUE_URL = "{}issues".format(PROJECT_URL)

DOMAIN = "smartthinq_sensors"

MIN_HA_MAJ_VER = 2022
MIN_HA_MIN_VER = 5
__min_ha_version__ = f"{MIN_HA_MAJ_VER}.{MIN_HA_MIN_VER}.0"

CONF_LANGUAGE = "language"
CONF_OAUTH_URL = "outh_url"
CONF_USE_API_V2 = "use_api_v2"

CLIENT = "client"
LGE_DEVICES = "lge_devices"

DEFAULT_ICON = "def_icon"
DEFAULT_SENSOR = "default"

STARTUP = """
-------------------------------------------------------------------
{}
Version: {}
This is a custom component
If you have any issues with this you need to open an issue here:
{}
-------------------------------------------------------------------
""".format(
    DOMAIN, __version__, ISSUE_URL
)
