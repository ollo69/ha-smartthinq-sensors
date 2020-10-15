"""
Support to interface with LGE ThinQ Devices.
"""

__version__ = "0.5.10"
PROJECT_URL = "https://github.com/ollo69/ha-smartthinq-sensors/"
ISSUE_URL = "{}issues".format(PROJECT_URL)

DOMAIN = "smartthinq_sensors"

CONF_LANGUAGE = "language"
CONF_OAUTH_URL = "outh_url"
CONF_OAUTH_USER_NUM = "outh_user_num"
CONF_USE_API_V2 = "use_api_v2"

ATTR_CONFIG = "config"
CLIENT = "client"
LGE_DEVICES = "lge_devices"

SMARTTHINQ_COMPONENTS = [
    "sensor", "binary_sensor"
]

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
