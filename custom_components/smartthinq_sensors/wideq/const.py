"""LG SmartThinQ constants."""

from .backports.enum import StrEnum

# default core settings
DEFAULT_COUNTRY = "US"
DEFAULT_LANGUAGE = "en-US"
DEFAULT_TIMEOUT = 15  # seconds

# bit status
BIT_OFF = "OFF"
BIT_ON = "ON"


class TemperatureUnit(StrEnum):
    """LG ThinQ valid temperature unit."""

    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"


class StateOptions(StrEnum):
    """LG ThinQ valid states."""

    NONE = "-"
    OFF = "off"
    ON = "on"
    UNKNOWN = "unknown"


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
    PM1 = "pm1"
    PM10 = "pm10"
    PM25 = "pm25"
    RESERVATION_SLEEP_TIME = "reservation_sleep_time"
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

    COOKTOP_CENTER_STATE = "cooktop_center_state"
    COOKTOP_LEFT_FRONT_STATE = "cooktop_left_front_state"
    COOKTOP_LEFT_REAR_STATE = "cooktop_left_rear_state"
    COOKTOP_RIGHT_FRONT_STATE = "cooktop_right_front_state"
    COOKTOP_RIGHT_REAR_STATE = "cooktop_right_rear_state"
    OVEN_LOWER_CURRENT_TEMP = "oven_lower_current_temp"
    OVEN_LOWER_MODE = "oven_lower_mode"
    OVEN_LOWER_STATE = "oven_lower_state"
    OVEN_UPPER_CURRENT_TEMP = "oven_upper_current_temp"
    OVEN_UPPER_MODE = "oven_upper_mode"
    OVEN_UPPER_STATE = "oven_upper_state"


class RefrigeratorFeatures(StrEnum):
    """Features for LG Refrigerator devices."""

    ECOFRIENDLY = "eco_friendly"
    EXPRESSMODE = "express_mode"
    EXPRESSFRIDGE = "express_fridge"
    FRESHAIRFILTER = "fresh_air_filter"
    ICEPLUS = "ice_plus"
    SMARTSAVINGMODE = "smart_saving_mode"
    WATERFILTERUSED_MONTH = "water_filter_used_month"


class WashDeviceFeatures(StrEnum):
    """Features for LG Wash devices."""

    ANTICREASE = "anti_crease"
    AUTODOOR = "auto_door"
    CHILDLOCK = "child_lock"
    CREASECARE = "crease_care"
    DAMPDRYBEEP = "damp_dry_beep"
    DELAYSTART = "delay_start"
    DETERGENT = "detergent"
    DETERGENTLOW = "detergent_low"
    DOORLOCK = "door_lock"
    DOOROPEN = "door_open"
    DRYLEVEL = "dry_level"
    DUALZONE = "dual_zone"
    ECOHYBRID = "eco_hybrid"
    ENERGYSAVER = "energy_saver"
    ERROR_MSG = "error_message"
    EXTRADRY = "extra_dry"
    HALFLOAD = "half_load"
    HANDIRON = "hand_iron"
    HIGHTEMP = "high_temp"
    MEDICRINSE = "medic_rinse"
    NIGHTDRY = "night_dry"
    PRESTEAM = "pre_steam"
    PREWASH = "pre_wash"
    PRE_STATE = "pre_state"
    PROCESS_STATE = "process_state"
    REMOTESTART = "remote_start"
    RESERVATION = "reservation"
    RINSEMODE = "rinse_mode"
    RINSEREFILL = "rinse_refill"
    RUN_STATE = "run_state"
    SALTREFILL = "salt_refill"
    SELFCLEAN = "self_clean"
    SOFTENER = "softener"
    SOFTENERLOW = "softener_low"
    SPINSPEED = "spin_speed"
    STANDBY = "standby"
    STEAM = "steam"
    STEAMSOFTENER = "steam_softener"
    TEMPCONTROL = "temp_control"
    TIMEDRY = "time_dry"
    TUBCLEAN_COUNT = "tubclean_count"
    TURBOWASH = "turbo_wash"
    WATERTEMP = "water_temp"


class WaterHeaterFeatures(StrEnum):
    """Features for LG Water Heater devices."""

    ENERGY_CURRENT = "energy_current"
    HOT_WATER_TEMP = "hot_water_temperature"


class MicroWaveFeatures(StrEnum):
    """Features for LG MicroWave devices."""

    CLOCK_DISPLAY = "clock_display"
    DISPLAY_SCROLL_SPEED = "display_scroll_speed"
    LIGHT_MODE = "light_mode"
    OVEN_UPPER_STATE = "oven_upper_state"
    OVEN_UPPER_MODE = "oven_upper_mode"
    SOUND = "sound"
    VENT_SPEED = "vent_speed"
    WEIGHT_UNIT = "weight_unit"


class HoodFeatures(StrEnum):
    """Features for LG Hood devices."""

    LIGHT_MODE = "light_mode"
    HOOD_STATE = "hood_state"
    VENT_SPEED = "vent_speed"
