"""LG SmartThinQ constants."""
from .core_enum import StrEnum

# default core settings
DEFAULT_COUNTRY = "US"
DEFAULT_LANGUAGE = "en-US"
DEFAULT_TIMEOUT = 10  # seconds

# bit status
BIT_OFF = "OFF"
BIT_ON = "ON"

# state options
STATE_OPTIONITEM_OFF = "off"
STATE_OPTIONITEM_ON = "on"
STATE_OPTIONITEM_NONE = "-"
STATE_OPTIONITEM_UNKNOWN = "unknown"

# unit temp
UNIT_TEMP_CELSIUS = "celsius"
UNIT_TEMP_FAHRENHEIT = "fahrenheit"


class AirConditionerFeatures(StrEnum):
    """Features for LG Air Conditioner devices."""

    ENERGY_CURRENT = "energy_current"
    HOT_WATER_TEMP = "hot_water_temperature"
    HUMIDITY = "humidity"
    FILTER_MAIN_LIFE = "filter_main_life"
    FILTER_MAIN_MAX = "filter_main_max"
    FILTER_MAIN_USE = "filter_main_use"
    LIGHTING_DISPLAY = "lighting_display"
    MODE_AIRCLEAN = "mode_airclean"
    MODE_AWHP_SILENT = "mode_awhp_silent"
    MODE_JET = "mode_jet"
    ROOM_TEMP = "room_temperature"
    WATER_IN_TEMP = "water_in_temperature"
    WATER_OUT_TEMP = "water_out_temperature"


class AirPurifierFeatures(StrEnum):
    """Features for LG Air Purifier devices."""

    FILTER_BOTTOM_LIFE = "filter_bottom_life"
    FILTER_BOTTOM_MAX = "filter_bottom_max"
    FILTER_BOTTOM_USE = "filter_bottom_use"
    FILTER_DUST_LIFE = "filter_dust_life"
    FILTER_DUST_MAX = "filter_dust_max"
    FILTER_DUST_USE = "filter_dust_use"
    FILTER_MAIN_LIFE = "filter_main_life"
    FILTER_MAIN_MAX = "filter_main_max"
    FILTER_MAIN_USE = "filter_main_use"
    FILTER_MID_LIFE = "filter_mid_life"
    FILTER_MID_MAX = "filter_mid_max"
    FILTER_MID_USE = "filter_mid_use"
    FILTER_TOP_LIFE = "filter_top_life"
    FILTER_TOP_MAX = "filter_top_max"
    FILTER_TOP_USE = "filter_top_use"
    HUMIDITY = "humidity"
    PM1 = "pm1"
    PM10 = "pm10"
    PM25 = "pm25"


class DehumidifierFeatures(StrEnum):
    """Features for LG Dehumidifier devices."""

    HUMIDITY = "humidity"
    TARGET_HUMIDITY = "target_humidity"
    WATER_TANK_FULL = "water_tank_full"


class RangeFeatures(StrEnum):
    """Features for LG Range devices."""

    COOKTOP_LEFT_FRONT_STATE = "cooktop_left_front_state"
    COOKTOP_LEFT_REAR_STATE = "cooktop_left_rear_state"
    COOKTOP_CENTER_STATE = "cooktop_center_state"
    COOKTOP_RIGHT_FRONT_STATE = "cooktop_right_front_state"
    COOKTOP_RIGHT_REAR_STATE = "cooktop_right_rear_state"
    OVEN_LOWER_CURRENT_TEMP = "oven_lower_current_temp"
    OVEN_LOWER_STATE = "oven_lower_state"
    OVEN_UPPER_CURRENT_TEMP = "oven_upper_current_temp"
    OVEN_UPPER_STATE = "oven_upper_state"


class WaterHeaterFeatures(StrEnum):
    """Features for LG Water Heater devices."""

    ENERGY_CURRENT = "energy_current"
    HOT_WATER_TEMP = "hot_water_temperature"


# wash devices features
FEAT_DRYLEVEL = "dry_level"
FEAT_ERROR_MSG = "error_message"
FEAT_PRE_STATE = "pre_state"
FEAT_PROCESS_STATE = "process_state"
FEAT_RINSEMODE = "rinse_mode"
FEAT_RUN_STATE = "run_state"
FEAT_SPINSPEED = "spin_speed"
FEAT_TEMPCONTROL = "temp_control"
FEAT_TIMEDRY = "time_dry"
FEAT_TUBCLEAN_COUNT = "tubclean_count"
FEAT_WATERTEMP = "water_temp"

FEAT_AUTODOOR = "auto_door"
FEAT_CHILDLOCK = "child_lock"
FEAT_CREASECARE = "crease_care"
FEAT_DELAYSTART = "delay_start"
FEAT_DETERGENT = "detergent"
FEAT_DOORCLOSE = "door_close"
FEAT_DOORLOCK = "door_lock"
FEAT_DOOROPEN = "door_open"
FEAT_DUALZONE = "dual_zone"
FEAT_ENERGYSAVER = "energy_saver"
FEAT_EXTRADRY = "extra_dry"
FEAT_HALFLOAD = "half_load"
FEAT_HIGHTEMP = "high_temp"
FEAT_MEDICRINSE = "medic_rinse"
FEAT_NIGHTDRY = "night_dry"
FEAT_PREWASH = "pre_wash"
FEAT_REMOTESTART = "remote_start"
FEAT_RINSEREFILL = "rinse_refill"
FEAT_SALTREFILL = "salt_refill"
FEAT_SOFTENER = "softener"
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
