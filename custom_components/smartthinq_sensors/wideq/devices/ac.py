"""------------------for AC"""

from __future__ import annotations

from enum import Enum
import logging

from ..backports.functools import cached_property
from ..const import AirConditionerFeatures, TemperatureUnit
from ..core_async import ClientAsync
from ..core_exceptions import InvalidRequestError
from ..core_util import TempUnitConversion
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo
from ..model_info import TYPE_RANGE

AWHP_MODEL_TYPE = ["AWHP", "SAC_AWHP"]

SUPPORT_AIR_POLUTION = ["SupportAirPolution", "support.airPolution"]
SUPPORT_OPERATION_MODE = ["SupportOpMode", "support.airState.opMode"]
SUPPORT_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]
SUPPORT_DUCT_ZONE = ["SupportDuctZoneType", "support.airState.ductZone.type"]
SUPPORT_LIGHT = ["SupportLight", "support.light"]
SUPPORT_PAC_MODE = ["SupportPACMode", "support.pacMode"]
SUPPORT_RAC_MODE = ["SupportRACMode", "support.racMode"]
SUPPORT_RAC_SUBMODE = ["SupportRACSubMode", "support.racSubMode"]

SUPPORT_VANE_HSTEP = [SUPPORT_RAC_SUBMODE, "@AC_MAIN_WIND_DIRECTION_STEP_LEFT_RIGHT_W"]
SUPPORT_VANE_VSTEP = [SUPPORT_RAC_SUBMODE, "@AC_MAIN_WIND_DIRECTION_STEP_UP_DOWN_W"]
SUPPORT_VANE_HSWING = [
    SUPPORT_RAC_SUBMODE,
    "@AC_MAIN_WIND_DIRECTION_SWING_LEFT_RIGHT_W",
]
SUPPORT_VANE_VSWING = [SUPPORT_RAC_SUBMODE, "@AC_MAIN_WIND_DIRECTION_SWING_UP_DOWN_W"]
SUPPORT_JET_COOL = [SUPPORT_RAC_SUBMODE, "@AC_MAIN_WIND_MODE_COOL_JET_W"]
SUPPORT_JET_HEAT = [SUPPORT_RAC_SUBMODE, "@AC_MAIN_WIND_MODE_HEAT_JET_W"]
SUPPORT_AIRCLEAN = [SUPPORT_RAC_MODE, "@AIRCLEAN"]
SUPPORT_HOT_WATER = [SUPPORT_PAC_MODE, ["@HOTWATER", "@HOTWATER_ONLY"]]
SUPPORT_LIGHT_SWITCH = [SUPPORT_LIGHT, "@RAC_88_DISPLAY_CONTROL"]
SUPPORT_LIGHT_INV_SWITCH = [SUPPORT_LIGHT, "@BRIGHTNESS_CONTROL"]
SUPPORT_PM = [
    SUPPORT_AIR_POLUTION,
    ["@PM1_0_SUPPORT", "@PM2_5_SUPPORT", "@PM10_SUPPORT"],
]

CTRL_BASIC = ["Control", "basicCtrl"]
CTRL_WIND_DIRECTION = ["Control", "wDirCtrl"]
CTRL_MISC = ["Control", "miscCtrl"]

CTRL_FILTER_V2 = "filterMngStateCtrl"
# CTRL_SETTING = "settingInfo"
# CTRL_WIND_MODE = "wModeCtrl"

DUCT_ZONE_V1 = "DuctZone"
DUCT_ZONE_V1_TYPE = "DuctZoneType"
STATE_FILTER_V1 = "Filter"
STATE_FILTER_V1_MAX = "FilterMax"
STATE_FILTER_V1_USE = "FilterUse"
STATE_POWER_V1 = "InOutInstantPower"

# AC Section
STATE_OPERATION = ["Operation", "airState.operation"]
STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
STATE_CURRENT_TEMP = ["TempCur", "airState.tempState.current"]
STATE_TARGET_TEMP = ["TempCfg", "airState.tempState.target"]
STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]
STATE_WDIR_HSTEP = ["WDirHStep", "airState.wDir.hStep"]
STATE_WDIR_VSTEP = ["WDirVStep", "airState.wDir.vStep"]
STATE_WDIR_HSWING = ["WDirLeftRight", "airState.wDir.leftRight"]
STATE_WDIR_VSWING = ["WDirUpDown", "airState.wDir.upDown"]
STATE_DUCT_ZONE = ["ZoneControl", "airState.ductZone.state"]
STATE_POWER = [STATE_POWER_V1, "airState.energy.onCurrent"]
STATE_HUMIDITY = ["SensorHumidity", "airState.humidity.current"]
STATE_MODE_AIRCLEAN = ["AirClean", "airState.wMode.airClean"]
STATE_MODE_JET = ["Jet", "airState.wMode.jet"]
STATE_LIGHTING_DISPLAY = ["DisplayControl", "airState.lightingState.displayControl"]
STATE_AIRSENSORMON = ["SensorMon", "airState.quality.sensorMon"]
STATE_PM1 = ["SensorPM1", "airState.quality.PM1"]
STATE_PM10 = ["SensorPM10", "airState.quality.PM10"]
STATE_PM25 = ["SensorPM2", "airState.quality.PM2"]
STATE_RESERVATION_SLEEP_TIME = ["SleepTime", "airState.reservation.sleepTime"]

FILTER_TYPES = [
    [
        [
            AirConditionerFeatures.FILTER_MAIN_LIFE,
            AirConditionerFeatures.FILTER_MAIN_USE,
            AirConditionerFeatures.FILTER_MAIN_MAX,
        ],
        [STATE_FILTER_V1_USE, "airState.filterMngStates.useTime"],
        [STATE_FILTER_V1_MAX, "airState.filterMngStates.maxTime"],
        None,
    ],
]

CMD_STATE_OPERATION = [CTRL_BASIC, "Set", STATE_OPERATION]
CMD_STATE_OP_MODE = [CTRL_BASIC, "Set", STATE_OPERATION_MODE]
CMD_STATE_TARGET_TEMP = [CTRL_BASIC, "Set", STATE_TARGET_TEMP]
CMD_STATE_WIND_STRENGTH = [CTRL_BASIC, "Set", STATE_WIND_STRENGTH]
CMD_STATE_WDIR_HSTEP = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_HSTEP]
CMD_STATE_WDIR_VSTEP = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_VSTEP]
CMD_STATE_WDIR_HSWING = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_HSWING]
CMD_STATE_WDIR_VSWING = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_VSWING]
CMD_STATE_DUCT_ZONES = [CTRL_MISC, "Set", [DUCT_ZONE_V1, "airState.ductZone.control"]]
CMD_STATE_MODE_AIRCLEAN = [CTRL_BASIC, "Set", STATE_MODE_AIRCLEAN]
CMD_STATE_MODE_JET = [CTRL_BASIC, "Set", STATE_MODE_JET]
CMD_STATE_LIGHTING_DISPLAY = [CTRL_BASIC, "Set", STATE_LIGHTING_DISPLAY]
CMD_RESERVATION_SLEEP_TIME = [CTRL_BASIC, "Set", STATE_RESERVATION_SLEEP_TIME]

# AWHP Section
STATE_AWHP_TEMP_MODE = ["AwhpTempSwitch", "airState.miscFuncState.awhpTempSwitch"]
STATE_WATER_IN_TEMP = ["WaterInTempCur", "airState.tempState.inWaterCurrent"]
STATE_WATER_OUT_TEMP = ["WaterTempCur", "airState.tempState.outWaterCurrent"]
STATE_WATER_MIN_TEMP = ["WaterTempCoolMin", "airState.tempState.waterTempCoolMin"]
STATE_WATER_MAX_TEMP = ["WaterTempHeatMax", "airState.tempState.waterTempHeatMax"]
STATE_HOT_WATER_TEMP = ["HotWaterTempCur", "airState.tempState.hotWaterCurrent"]
STATE_HOT_WATER_TARGET_TEMP = ["HotWaterTempCfg", "airState.tempState.hotWaterTarget"]
STATE_HOT_WATER_MIN_TEMP = ["HotWaterTempMin", "airState.tempState.hotWaterTempMin"]
STATE_HOT_WATER_MAX_TEMP = ["HotWaterTempMax", "airState.tempState.hotWaterTempMax"]
STATE_HOT_WATER_MODE = ["HotWater", "airState.miscFuncState.hotWater"]
STATE_MODE_AWHP_SILENT = ["SilentMode", "airState.miscFuncState.silentAWHP"]

CMD_STATE_HOT_WATER_MODE = [CTRL_BASIC, "Set", STATE_HOT_WATER_MODE]
CMD_STATE_HOT_WATER_TARGET_TEMP = [CTRL_BASIC, "Set", STATE_HOT_WATER_TARGET_TEMP]
CMD_STATE_MODE_AWHP_SILENT = [CTRL_BASIC, "Set", STATE_MODE_AWHP_SILENT]

CMD_ENABLE_EVENT_V2 = ["allEventEnable", "Set", "airState.mon.timeout"]

# STATE_AUTODRY_MODE_V2 = "airState.miscFuncState.autoDry"
# STATE_AIRCLEAN_MODE_V2 = "airState.wMode.airClean"
# STATE_FILTER_MAX_TIME_V2 = "airState.filterMngStates.maxTime"
# STATE_FILTER_REMAIN_TIME_V2 = "airState.filterMngStates.useTime"

DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 30
AWHP_MIN_TEMP = 5
AWHP_MAX_TEMP = 80

TEMP_STEP_WHOLE = 1.0
TEMP_STEP_HALF = 0.5

ADD_FEAT_POLL_INTERVAL = 300  # 5 minutes

LIGHT_DISPLAY_OFF = ["@RAC_LED_OFF", "@AC_LED_OFF_W"]
LIGHT_DISPLAY_ON = ["@RAC_LED_ON", "@AC_LED_ON_W"]
LIGHT_DISPLAY_INV_OFF = ["@RAC_LED_ON", "@AC_LED_OFF_W"]
LIGHT_DISPLAY_INV_ON = ["@RAC_LED_OFF", "@AC_LED_ON_W"]

MODE_OFF = "@OFF"
MODE_ON = "@ON"

MODE_AIRCLEAN_OFF = "@AC_MAIN_AIRCLEAN_OFF_W"
MODE_AIRCLEAN_ON = "@AC_MAIN_AIRCLEAN_ON_W"

AWHP_MODE_AIR = "@AIR"
AWHP_MODE_WATER = "@WATER"

ZONE_OFF = "0"
ZONE_ON = "1"
ZONE_ST_CUR = "current"
ZONE_ST_NEW = "new"

FILTER_STATUS_MAP = {
    STATE_FILTER_V1_USE: "UseTime",
    STATE_FILTER_V1_MAX: "ChangePeriod",
}

_LOGGER = logging.getLogger(__name__)


class ACOp(Enum):
    """Whether a device is on or off."""

    OFF = "@AC_MAIN_OPERATION_OFF_W"
    ON = "@AC_MAIN_OPERATION_ON_W"
    RIGHT_ON = "@AC_MAIN_OPERATION_RIGHT_ON_W"  # Right fan only.
    LEFT_ON = "@AC_MAIN_OPERATION_LEFT_ON_W"  # Left fan only.
    ALL_ON = "@AC_MAIN_OPERATION_ALL_ON_W"  # Both fans (or only fan) on.


class ACMode(Enum):
    """The operation mode for an AC/HVAC device."""

    COOL = "@AC_MAIN_OPERATION_MODE_COOL_W"
    DRY = "@AC_MAIN_OPERATION_MODE_DRY_W"
    FAN = "@AC_MAIN_OPERATION_MODE_FAN_W"
    HEAT = "@AC_MAIN_OPERATION_MODE_HEAT_W"
    ACO = "@AC_MAIN_OPERATION_MODE_ACO_W"
    AI = "@AC_MAIN_OPERATION_MODE_AI_W"
    AIRCLEAN = "@AC_MAIN_OPERATION_MODE_AIRCLEAN_W"
    AROMA = "@AC_MAIN_OPERATION_MODE_AROMA_W"
    ENERGY_SAVING = "@AC_MAIN_OPERATION_MODE_ENERGY_SAVING_W"
    ENERGY_SAVER = "@AC_MAIN_OPERATION_MODE_ENERGY_SAVER_W"


class ACFanSpeed(Enum):
    """The fan speed for an AC/HVAC device."""

    SLOW = "@AC_MAIN_WIND_STRENGTH_SLOW_W"
    SLOW_LOW = "@AC_MAIN_WIND_STRENGTH_SLOW_LOW_W"
    LOW = "@AC_MAIN_WIND_STRENGTH_LOW_W"
    LOW_MID = "@AC_MAIN_WIND_STRENGTH_LOW_MID_W"
    MID = "@AC_MAIN_WIND_STRENGTH_MID_W"
    MID_HIGH = "@AC_MAIN_WIND_STRENGTH_MID_HIGH_W"
    HIGH = "@AC_MAIN_WIND_STRENGTH_HIGH_W"
    POWER = "@AC_MAIN_WIND_STRENGTH_POWER_W"
    AUTO = "@AC_MAIN_WIND_STRENGTH_AUTO_W"
    NATURE = "@AC_MAIN_WIND_STRENGTH_NATURE_W"
    R_LOW = "@AC_MAIN_WIND_STRENGTH_LOW_RIGHT_W"
    R_MID = "@AC_MAIN_WIND_STRENGTH_MID_RIGHT_W"
    R_HIGH = "@AC_MAIN_WIND_STRENGTH_HIGH_RIGHT_W"
    L_LOW = "@AC_MAIN_WIND_STRENGTH_LOW_LEFT_W"
    L_MID = "@AC_MAIN_WIND_STRENGTH_MID_LEFT_W"
    L_HIGH = "@AC_MAIN_WIND_STRENGTH_HIGH_LEFT_W"


class ACVStepMode(Enum):
    """
    The vertical step mode for an AC/HVAC device.

    Blades are numbered vertically from 1 (topmost)
    to 6.

    All is 100.
    """

    Off = "@OFF"
    Top = "@1"
    MiddleTop1 = "@2"
    MiddleTop2 = "@3"
    MiddleBottom2 = "@4"
    MiddleBottom1 = "@5"
    Bottom = "@6"
    Swing = "@100"


class ACHStepMode(Enum):
    """
    The horizontal step mode for an AC/HVAC device.
    Blades are numbered horizontally from 1 (leftmost)
    to 5.
    Left half goes from 1-3, and right half goes from
    3-5.
    All is 100.
    """

    Off = "@OFF"
    Left = "@1"
    MiddleLeft = "@2"
    Center = "@3"
    MiddleRight = "@4"
    Right = "@5"
    LeftHalf = "@13"
    RightHalf = "@35"
    Swing = "@100"


class JetMode(Enum):
    """Possible JET modes."""

    OFF = MODE_OFF
    COOL = "@COOL_JET"
    HEAT = "@HEAT_JET"
    DRY = "@DRY_JET_W"
    HIMALAYAS = "@HIMALAYAS_COOL"


class JetModeSupport(Enum):
    """Supported JET modes."""

    NONE = 0
    COOL = 1
    HEAT = 2
    BOTH = 3


class AirConditionerDevice(Device):
    """A higher-level interface for a AC."""

    def __init__(
        self,
        client: ClientAsync,
        device_info: DeviceInfo,
        temp_unit=TemperatureUnit.CELSIUS,
    ):
        """Initialize AirConditionerDevice object."""
        super().__init__(client, device_info, AirConditionerStatus(self))
        self._temperature_unit = (
            TemperatureUnit.FAHRENHEIT
            if temp_unit == TemperatureUnit.FAHRENHEIT
            else TemperatureUnit.CELSIUS
        )

        self._temperature_step = TEMP_STEP_WHOLE
        self._duct_zones = {}

        self._current_power = None
        self._current_power_supported = True

        self._filter_status = None
        self._filter_status_supported = True

        self._unit_conv = TempUnitConversion()

    def _f2c(self, value):
        """Convert Fahrenheit to Celsius temperatures for this device if required."""
        if self._temperature_unit == TemperatureUnit.CELSIUS:
            return value
        return self._unit_conv.f2c(value, self.model_info)

    def conv_temp_unit(self, value):
        """Convert Celsius to Fahrenheit temperatures for this device if required."""
        if self._temperature_unit == TemperatureUnit.CELSIUS:
            return float(value)
        return self._unit_conv.c2f(value, self.model_info)

    def _adjust_temperature_step(self, target_temp):
        if self._temperature_step != TEMP_STEP_WHOLE:
            return
        if target_temp is None:
            return
        if int(target_temp) != target_temp:
            self._temperature_step = TEMP_STEP_HALF

    def _is_mode_supported(self, key):
        """Check if a specific mode for support key is supported."""
        if not isinstance(key, list):
            return False

        supp_key = self._get_state_key(key[0])
        if isinstance(key[1], list):
            return [self.model_info.enum_value(supp_key, k) is not None for k in key[1]]
        return self.model_info.enum_value(supp_key, key[1]) is not None

    def _get_supported_operations(self):
        """Return the list of the ACOp Operations the device supports."""

        key = self._get_state_key(STATE_OPERATION)
        mapping = self.model_info.value(key).options
        return [ACOp(o) for o in mapping.values()]

    @cached_property
    def _supported_on_operation(self):
        """
        Get the most correct "On" operation the device supports.
        :raises ValueError: If ALL_ON is not supported, but there are
            multiple supported ON operations. If a model raises this,
            its behaviour needs to be determined so this function can
            make a better decision.
        """

        operations = self._get_supported_operations()

        # This ON operation appears to be supported in newer AC models
        if ACOp.ALL_ON in operations:
            return ACOp.ALL_ON

        # This ON operation appears to be supported in V2 AC models, to check
        if ACOp.ON in operations:
            return ACOp.ON

        # Older models, or possibly just the LP1419IVSM, do not support ALL_ON,
        # instead advertising only a single operation of RIGHT_ON.
        # Thus, if there's only one ON operation, we use that.
        single_op = [op for op in operations if op != ACOp.OFF]
        if len(single_op) == 1:
            return single_op[0]

        # Hypothetically, the API could return multiple ON operations, neither
        # of which are ALL_ON. This will raise in that case, as we don't know
        # what that model will expect us to do to turn everything on.
        # Or, this code will never actually be reached! We can only hope. :)
        raise ValueError(
            f"could not determine correct 'on' operation:"
            f" too many reported operations: '{str(operations)}'"
        )

    @cached_property
    def _temperature_range(self):
        """Get valid temperature range for model."""

        temp_mode = self._status.awhp_temp_mode
        if temp_mode and temp_mode == AWHP_MODE_WATER:
            min_temp = self._status.water_target_min_temp or AWHP_MIN_TEMP
            max_temp = self._status.water_target_max_temp or AWHP_MAX_TEMP
        else:
            key = self._get_state_key(STATE_TARGET_TEMP)
            range_info = self.model_info.value(key)
            if not range_info:
                min_temp = DEFAULT_MIN_TEMP
                max_temp = DEFAULT_MAX_TEMP
            else:
                min_temp = min(range_info.min, DEFAULT_MIN_TEMP)
                max_temp = max(range_info.max, DEFAULT_MAX_TEMP)
        return [min_temp, max_temp]

    @cached_property
    def _hot_water_temperature_range(self):
        """Get valid hot water temperature range for model."""

        if not self.is_water_heater_supported:
            return None

        min_temp = self._status.hot_water_target_min_temp
        max_temp = self._status.hot_water_target_max_temp
        if min_temp is None or max_temp is None:
            return [AWHP_MIN_TEMP, AWHP_MAX_TEMP]
        return [min_temp, max_temp]

    @cached_property
    def is_duct_zones_supported(self):
        """Check if device support duct zones."""
        supp_key = self._get_state_key(SUPPORT_DUCT_ZONE)
        if not self.model_info.is_enum_type(supp_key):
            return False
        mapping = self.model_info.value(supp_key).options
        zones = [key for key in mapping.keys() if key != "0"]
        return len(zones) > 0

    def is_duct_zone_enabled(self, zone: str) -> bool:
        """Get if a specific zone is enabled"""
        return zone in self._duct_zones

    def get_duct_zone(self, zone: str) -> bool:
        """Get the status for a specific zone"""
        if zone not in self._duct_zones:
            return False
        cur_zone = self._duct_zones[zone]
        if ZONE_ST_NEW in cur_zone:
            return cur_zone[ZONE_ST_NEW] == ZONE_ON
        return cur_zone[ZONE_ST_CUR] == ZONE_ON

    def set_duct_zone(self, zone: str, status: bool):
        """Set the status for a specific zone"""
        if zone not in self._duct_zones:
            return
        self._duct_zones[zone][ZONE_ST_NEW] = ZONE_ON if status else ZONE_OFF

    @property
    def duct_zones(self) -> list:
        """Return a list of available duct zones"""
        return list(self._duct_zones)

    async def update_duct_zones(self):
        """Update the current duct zones status."""
        states = await self._get_duct_zones()
        if not states:
            return

        duct_zones = {}
        send_update = False
        for zone, state in states.items():
            cur_status = state[ZONE_ST_CUR]
            new_status = None
            if zone in self._duct_zones:
                new_status = self._duct_zones[zone].get(ZONE_ST_NEW)
                if new_status and new_status != cur_status:
                    send_update = True
            duct_zones[zone] = {ZONE_ST_CUR: new_status or cur_status}

        self._duct_zones = duct_zones
        if send_update:
            await self._set_duct_zones(duct_zones)

    async def _get_duct_zones(self) -> dict:
        """Get the status of the zones (for ThinQ1 only zone configured).

        return value is a dict with this format:
        - key: The zone index. A string containing a number
        - value: another dict with:
            - key: "current"
            - value: "1" if zone is ON else "0"
        """

        # first check if duct is supported
        if not (self.is_duct_zones_supported and self._status):
            return {}

        duct_state = -1
        # duct zone type is available only for some ThinQ1 devices
        if not self._status.duct_zones_type:
            duct_state = self._status.duct_zones_state
        if not duct_state:
            return {}

        # get real duct zones states

        # For device that provide duct_state in payload we transform
        # the value in the status in binary and than we create the result.
        # We always have 8 duct zone.

        if duct_state > 0:
            bin_arr = list(reversed(f"{duct_state:08b}"))
            return {str(v + 1): {ZONE_ST_CUR: k} for v, k in enumerate(bin_arr)}

        # For ThinQ1 devices result is a list of dicts with these keys:
        # - "No": The zone index. A string containing a number,
        #   starting from 1.
        # - "Cfg": Whether the zone is enabled. A string, either "1" or
        #   "0".
        # - "State": Whether the zone is open. Also "1" or "0".

        zones = await self._get_config(DUCT_ZONE_V1)
        return {
            zone["No"]: {ZONE_ST_CUR: zone["State"]}
            for zone in zones
            if zone["Cfg"] == "1"
        }

    async def _set_duct_zones(self, zones: dict):
        """
        Turn off or on the device's zones.
        The `zones` parameter is the same returned by _get_duct_zones().
        """

        # Ensure at least one zone is enabled: we can't turn all zones
        # off simultaneously.
        on_count = sum(int(zone[ZONE_ST_CUR]) for zone in zones.values())
        if on_count == 0:
            _LOGGER.warning("Turn off all duct zones is not allowed")
            return

        zone_cmd = "/".join(
            f"{key}_{value[ZONE_ST_CUR]}" for key, value in zones.items()
        )
        keys = self._get_cmd_keys(CMD_STATE_DUCT_ZONES)
        await self.set(keys[0], keys[1], key=keys[2], value=zone_cmd)

    @cached_property
    def is_air_to_water(self):
        """Return if is a Air To Water device."""
        return self.model_info.model_type in AWHP_MODEL_TYPE

    @cached_property
    def is_water_heater_supported(self):
        """Return if Water Heater is supported."""
        if not self.is_air_to_water:
            return False
        return any(self._is_mode_supported(SUPPORT_HOT_WATER))

    @cached_property
    def op_modes(self):
        """Return a list of available operation modes."""
        return self._get_property_values(SUPPORT_OPERATION_MODE, ACMode)

    @cached_property
    def fan_speeds(self):
        """Return a list of available fan speeds."""
        return self._get_property_values(SUPPORT_WIND_STRENGTH, ACFanSpeed)

    @cached_property
    def horizontal_step_modes(self):
        """Return a list of available horizontal step modes."""
        if not self._is_mode_supported(SUPPORT_VANE_HSTEP):
            return []
        return self._get_property_values(STATE_WDIR_HSTEP, ACHStepMode)

    @cached_property
    def vertical_step_modes(self):
        """Return a list of available vertical step modes."""
        if not self._is_mode_supported(SUPPORT_VANE_VSTEP):
            return []
        return self._get_property_values(STATE_WDIR_VSTEP, ACVStepMode)

    @property
    def temperature_unit(self):
        """Return the unit used for temperature."""
        return self._temperature_unit

    @property
    def target_temperature_step(self):
        """Return target temperature step used."""
        return self._temperature_step

    @property
    def target_temperature_min(self):
        """Return minimum value for target temperature."""
        temp_range = self._temperature_range
        return self.conv_temp_unit(temp_range[0])

    @property
    def target_temperature_max(self):
        """Return maximum value for target temperature."""
        temp_range = self._temperature_range
        return self.conv_temp_unit(temp_range[1])

    @cached_property
    def is_mode_airclean_supported(self):
        """Return if AirClean mode is supported."""
        return self._is_mode_supported(SUPPORT_AIRCLEAN)

    @cached_property
    def supported_ligth_modes(self):
        """Return light switch modes supported."""
        if self._is_mode_supported(SUPPORT_LIGHT_SWITCH):
            return {MODE_OFF: LIGHT_DISPLAY_OFF, MODE_ON: LIGHT_DISPLAY_ON}
        if self._is_mode_supported(SUPPORT_LIGHT_INV_SWITCH):
            return {MODE_OFF: LIGHT_DISPLAY_INV_OFF, MODE_ON: LIGHT_DISPLAY_INV_ON}
        return None

    @cached_property
    def supported_mode_jet(self):
        """Return if Jet mode is supported."""
        supported = JetModeSupport.NONE
        if self._is_mode_supported(SUPPORT_JET_COOL):
            supported = JetModeSupport.COOL
        if self._is_mode_supported(SUPPORT_JET_HEAT):
            if supported == JetModeSupport.COOL:
                return JetModeSupport.BOTH
            return JetModeSupport.HEAT
        return supported

    @property
    def is_mode_jet_available(self):
        """Return if JET mode is available."""
        if (supported := self.supported_mode_jet) == JetModeSupport.NONE:
            return False
        if not self._status.is_on:
            return False
        if (curr_op_mode := self._status.operation_mode) is None:
            return False
        if curr_op_mode == ACMode.HEAT.name and supported in (
            JetModeSupport.HEAT,
            JetModeSupport.BOTH,
        ):
            return True
        if curr_op_mode in (ACMode.COOL.name, ACMode.DRY.name) and supported in (
            JetModeSupport.COOL,
            JetModeSupport.BOTH,
        ):
            return True
        return False

    @cached_property
    def _is_pm_supported(self):
        """Return if PM sensors are supported."""
        return self._is_mode_supported(SUPPORT_PM)

    @property
    def is_pm1_supported(self):
        """Return if PM1 sensor is supported."""
        return self._is_pm_supported[0]

    @property
    def is_pm25_supported(self):
        """Return if PM2.5 sensor is supported."""
        return self._is_pm_supported[1]

    @property
    def is_pm10_supported(self):
        """Return if PM10 sensor is supported."""
        return self._is_pm_supported[2]

    @property
    def hot_water_target_temperature_step(self):
        """Return target temperature step used for hot water."""
        return TEMP_STEP_WHOLE

    @property
    def hot_water_target_temperature_min(self):
        """Return minimum value for hot water target temperature."""
        temp_range = self._hot_water_temperature_range
        if not temp_range:
            return None
        return self.conv_temp_unit(temp_range[0])

    @property
    def hot_water_target_temperature_max(self):
        """Return maximum value for hot water target temperature."""
        temp_range = self._hot_water_temperature_range
        if not temp_range:
            return None
        return self.conv_temp_unit(temp_range[1])

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""
        operation = self._supported_on_operation if turn_on else ACOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], operation.value)
        await self.set(keys[0], keys[1], key=keys[2], value=op_value)

    async def set_op_mode(self, mode):
        """Set the device's operating mode to an `OpMode` value."""
        if mode not in self.op_modes:
            raise ValueError(f"Invalid operating mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_OP_MODE)
        mode_value = self.model_info.enum_value(keys[2], ACMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=mode_value)

    async def set_fan_speed(self, speed):
        """Set the fan speed to a value from the `ACFanSpeed` enum."""
        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], ACFanSpeed[speed].value)
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set_horizontal_step_mode(self, mode):
        """Set the horizontal step to a value from the `ACHStepMode` enum."""
        if mode not in self.horizontal_step_modes:
            raise ValueError(f"Invalid horizontal step mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_HSTEP)
        step_mode = self.model_info.enum_value(keys[2], ACHStepMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=step_mode)

    async def horizontal_swing_mode(self, value: bool):
        """Set the horizontal swing on or off."""
        if not self._is_mode_supported(SUPPORT_VANE_HSWING):
            raise ValueError("Horizontal swing mode not supported")
        mode = MODE_ON if value else MODE_OFF
        keys = self._get_cmd_keys(CMD_STATE_WDIR_HSWING)
        if (swing_mode := self.model_info.enum_value(keys[2], mode)) is None:
            raise ValueError(f"Invalid horizontal swing mode: {mode}")
        await self.set(keys[0], keys[1], key=keys[2], value=swing_mode)

    async def set_vertical_step_mode(self, mode):
        """Set the vertical step to a value from the `ACVStepMode` enum."""
        if mode not in self.vertical_step_modes:
            raise ValueError(f"Invalid vertical step mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_VSTEP)
        step_mode = self.model_info.enum_value(keys[2], ACVStepMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=step_mode)

    async def vertical_swing_mode(self, value: bool):
        """Set the vertical swing on or off."""
        if not self._is_mode_supported(SUPPORT_VANE_VSWING):
            raise ValueError("Vertical swing mode not supported")
        mode = MODE_ON if value else MODE_OFF
        keys = self._get_cmd_keys(CMD_STATE_WDIR_VSWING)
        if (swing_mode := self.model_info.enum_value(keys[2], mode)) is None:
            raise ValueError(f"Invalid vertical swing mode: {mode}")
        await self.set(keys[0], keys[1], key=keys[2], value=swing_mode)

    async def set_target_temp(self, temp):
        """Set the device's target temperature in Celsius degrees."""
        range_info = self._temperature_range
        conv_temp = self._f2c(temp)
        if range_info and not (range_info[0] <= conv_temp <= range_info[1]):
            raise ValueError(f"Target temperature out of range: {temp}")
        keys = self._get_cmd_keys(CMD_STATE_TARGET_TEMP)
        await self.set(keys[0], keys[1], key=keys[2], value=conv_temp)

    async def set_mode_airclean(self, status: bool):
        """Set the Airclean mode on or off."""
        if not self.is_mode_airclean_supported:
            raise ValueError("Airclean mode not supported")

        keys = self._get_cmd_keys(CMD_STATE_MODE_AIRCLEAN)
        mode_key = MODE_AIRCLEAN_ON if status else MODE_AIRCLEAN_OFF
        mode = self.model_info.enum_value(keys[2], mode_key)
        await self.set(keys[0], keys[1], key=keys[2], value=mode)

    async def set_mode_jet(self, status: bool):
        """Set the Jet mode on or off."""
        if self.supported_mode_jet == JetModeSupport.NONE:
            raise ValueError("Jet mode not supported")
        if not self.is_mode_jet_available:
            raise ValueError("Invalid device status for jet mode")

        if status:
            if self._status.operation_mode == ACMode.HEAT.name:
                jet_key = JetMode.HEAT
            else:
                jet_key = JetMode.COOL
        else:
            jet_key = JetMode.OFF
        keys = self._get_cmd_keys(CMD_STATE_MODE_JET)
        jet = self.model_info.enum_value(keys[2], jet_key.value)
        await self.set(keys[0], keys[1], key=keys[2], value=jet)

    async def set_lighting_display(self, status: bool):
        """Set the lighting display on or off."""
        if not (supp_modes := self.supported_ligth_modes):
            raise ValueError("Light switching not supported")

        keys = self._get_cmd_keys(CMD_STATE_LIGHTING_DISPLAY)
        modes = supp_modes[MODE_ON] if status else supp_modes[MODE_OFF]
        for mode in modes:
            if (lighting := self.model_info.enum_value(keys[2], mode)) is not None:
                break
        if lighting is None:
            raise ValueError("Not possible to determinate a valid light mode")
        await self.set(keys[0], keys[1], key=keys[2], value=lighting)

    async def set_mode_awhp_silent(self, value: bool):
        """Set the AWHP silent mode on or off."""
        if not self.is_air_to_water:
            raise ValueError("AWHP silent mode not supported")
        mode = MODE_ON if value else MODE_OFF
        keys = self._get_cmd_keys(CMD_STATE_MODE_AWHP_SILENT)
        if (silent_mode := self.model_info.enum_value(keys[2], mode)) is None:
            raise ValueError(f"Invalid AWHP silent mode: {mode}")
        await self.set(keys[0], keys[1], key=keys[2], value=silent_mode)

    async def hot_water_mode(self, value: bool):
        """Set the device hot water mode on or off."""
        if not self.is_water_heater_supported:
            raise ValueError("Hot water mode not supported")
        mode = MODE_ON if value else MODE_OFF
        keys = self._get_cmd_keys(CMD_STATE_HOT_WATER_MODE)
        if (hot_water_mode := self.model_info.enum_value(keys[2], mode)) is None:
            raise ValueError(f"Invalid hot water mode: {mode}")
        await self.set(keys[0], keys[1], key=keys[2], value=hot_water_mode)

    async def set_hot_water_target_temp(self, temp):
        """Set the device hot water target temperature in Celsius degrees."""
        if not self.is_water_heater_supported:
            raise ValueError("Hot water mode not supported")
        range_info = self._hot_water_temperature_range
        conv_temp = self._f2c(temp)
        if range_info and not (range_info[0] <= conv_temp <= range_info[1]):
            raise ValueError(f"Target temperature out of range: {temp}")
        keys = self._get_cmd_keys(CMD_STATE_HOT_WATER_TARGET_TEMP)
        await self.set(keys[0], keys[1], key=keys[2], value=conv_temp)

    async def get_power(self):
        """Get the instant power usage in watts of the whole unit."""
        if not self._current_power_supported:
            return None
        try:
            value = await self._get_config(STATE_POWER_V1)
            return value[STATE_POWER_V1]
        except (ValueError, InvalidRequestError) as exc:
            # Device does not support whole unit instant power usage
            _LOGGER.debug("Error calling get_power methods: %s", exc)
            self._current_power_supported = False
            return None

    async def get_filter_state(self):
        """Get information about the filter."""
        if not self._filter_status_supported:
            return None
        try:
            return await self._get_config(STATE_FILTER_V1)
        except (ValueError, InvalidRequestError) as exc:
            # Device does not support filter status
            _LOGGER.debug("Error calling get_filter_state methods: %s", exc)
            self._filter_status_supported = False
            return None

    async def get_filter_state_v2(self):
        """Get information about the filter."""
        if not self._filter_status_supported:
            return None
        try:
            return await self._get_config_v2(CTRL_FILTER_V2, "Get")
        except (ValueError, InvalidRequestError) as exc:
            # Device does not support filter status
            _LOGGER.debug("Error calling get_filter_state_v2 methods: %s", exc)
            self._filter_status_supported = False
            return None

    @cached_property
    def sleep_time_range(self) -> list[int]:
        """Return valid range for sleep time."""
        key = self._get_state_key(STATE_RESERVATION_SLEEP_TIME)
        if (range_val := self.model_info.value(key, TYPE_RANGE)) is None:
            return [0, 420]
        return [range_val.min, range_val.max]

    @property
    def is_reservation_sleep_time_available(self) -> bool:
        """Return if reservation sleep time is available."""
        if (status := self._status) is None:
            return False
        if (
            status.device_features.get(AirConditionerFeatures.RESERVATION_SLEEP_TIME)
            is None
        ):
            return False
        return status.is_on and (
            status.operation_mode
            in [ACMode.ACO.name, ACMode.FAN.name, ACMode.COOL.name, ACMode.DRY.name]
        )

    async def set_reservation_sleep_time(self, value: int):
        """Set the device sleep time reservation in minutes."""
        if not self.is_reservation_sleep_time_available:
            raise ValueError("Reservation sleep time is not available")
        valid_range = self.sleep_time_range
        if not (valid_range[0] <= value <= valid_range[1]):
            raise ValueError(
                f"Invalid sleep time value. Valid range: {valid_range[0]} - {valid_range[1]}"
            )
        keys = self._get_cmd_keys(CMD_RESERVATION_SLEEP_TIME)
        await self.set(keys[0], keys[1], key=keys[2], value=str(value))

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        """Reset the device's status"""
        self._status = AirConditionerStatus(self)
        return self._status

    async def _pre_update_v2(self):
        """Call additional methods before data update for v2 API."""
        # this command is to get power and temp info on V2 device
        keys = self._get_cmd_keys(CMD_ENABLE_EVENT_V2)
        await self.set(keys[0], keys[1], key=keys[2], value="70", ctrl_path="control")

    async def _get_device_info(self):
        """
        Call additional method to get device information for API v1.
        Called by 'device_poll' method using a lower poll rate.
        """
        # this commands is to get power usage and filter status on V1 device
        if not self.is_air_to_water:
            self._current_power = await self.get_power()
            if filter_status := await self.get_filter_state():
                self._filter_status = {
                    k: filter_status.get(v, 0) for k, v in FILTER_STATUS_MAP.items()
                }

    async def _get_device_info_v2(self):
        """
        Call additional method to get device information for V2 API.
        Override in specific device to call requested methods.
        """
        # this commands is to get filter status on V2 device
        if not self.is_air_to_water:
            self._filter_status = await self.get_filter_state_v2()

    async def poll(self) -> AirConditionerStatus | None:
        """Poll the device's current state."""
        res = await self._device_poll(
            additional_poll_interval_v1=ADD_FEAT_POLL_INTERVAL,
            additional_poll_interval_v2=ADD_FEAT_POLL_INTERVAL,
            thinq2_query_device=True,
        )
        if not res:
            return None

        # update power for ACv1
        if self._should_poll and not self.is_air_to_water:
            if self._current_power is not None:
                res[STATE_POWER_V1] = self._current_power

        self._status = AirConditionerStatus(self, res)
        # adjust temperature step
        if self._temperature_step == TEMP_STEP_WHOLE:
            self._adjust_temperature_step(self._status.target_temp)
        # update filter status
        if self._filter_status:
            if not self._status.update_filter_status(self._filter_status):
                self._filter_status = None
                self._filter_status_supported = False

        # manage duct devices, does nothing if not ducted
        try:
            await self.update_duct_zones()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Duct zone control failed", exc_info=ex)

        return self._status


class AirConditionerStatus(DeviceStatus):
    """Higher-level information about a AC's current status."""

    _device: AirConditionerDevice

    def __init__(self, device: AirConditionerDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._operation = None
        self._airmon_on = None
        self._filter_use_time_inverted = True
        self._current_temp = None

    def _str_to_temp(self, str_temp):
        """Convert a string to either an `int` or a `float` temperature."""
        temp = self._str_to_num(str_temp)
        if not temp:  # value 0 return None!!!
            return None
        return self._device.conv_temp_unit(temp)

    def _get_operation(self):
        """Get current operation."""
        if self._operation is None:
            key = self._get_state_key(STATE_OPERATION)
            operation = self.lookup_enum(key, True)
            if not operation:
                return None
            self._operation = operation
        try:
            return ACOp(self._operation)
        except ValueError:
            return None

    def update_filter_status(self, values: dict) -> bool:
        """Update device filter status."""
        self._filter_use_time_inverted = False

        if not self.is_info_v2:
            self._data.update(values)
            return True

        # ACv2 could return filter value in the payload
        # if max_time key is in the payload <> 0, we don't update
        updated = False
        for filters in FILTER_TYPES:
            max_key = self._get_state_key(filters[2])  # this is the max_time key
            cur_val = self.to_int_or_none(self._data.get(max_key, 0))
            if cur_val:
                continue
            for index in range(1, 3):
                upd_key = self._get_state_key(filters[index])
                if upd_key in values:
                    self._data[upd_key] = values[upd_key]
                    updated = True

        # for models that return use_time directly in the payload,
        # the value actually represent remaining time
        self._filter_use_time_inverted = not updated

        return updated

    def update_status(self, key, value):
        """Update device status."""
        if not super().update_status(key, value):
            return False
        if key in STATE_OPERATION:
            self._operation = None
        return True

    @property
    def is_on(self):
        """Return if device is on."""
        if not (operation := self._get_operation()):
            return False
        return operation != ACOp.OFF

    @property
    def operation(self):
        """Return current device operation."""
        if not (operation := self._get_operation()):
            return None
        return operation.name

    @property
    def operation_mode(self):
        """Return current device operation mode."""
        key = self._get_state_key(STATE_OPERATION_MODE)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return ACMode(value).name
        except ValueError:
            return None

    @property
    def is_hot_water_on(self):
        """Return if hot water is on."""
        key = self._get_state_key(STATE_HOT_WATER_MODE)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        return value == MODE_ON

    @property
    def fan_speed(self):
        """Return current fan speed."""
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return ACFanSpeed(value).name
        except ValueError:
            return None

    @property
    def horizontal_step_mode(self):
        """Return current horizontal step mode."""
        key = self._get_state_key(STATE_WDIR_HSTEP)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return ACHStepMode(value).name
        except ValueError:
            return None

    @property
    def is_horizontal_swing_on(self):
        """Return current horizontal swing mode."""
        key = self._get_state_key(STATE_WDIR_HSWING)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        return value == MODE_ON

    @property
    def vertical_step_mode(self):
        """Return current vertical step mode."""
        key = self._get_state_key(STATE_WDIR_VSTEP)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return ACVStepMode(value).name
        except ValueError:
            return None

    @property
    def is_vertical_swing_on(self):
        """Return current vertical swing mode."""
        key = self._get_state_key(STATE_WDIR_VSWING)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        return value == MODE_ON

    @property
    def room_temp(self):
        """Return room temperature."""
        key = self._get_state_key(STATE_CURRENT_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(AirConditionerFeatures.ROOM_TEMP, value, False)

    @property
    def current_temp(self):
        """Return current temperature."""
        if self._current_temp is None:
            curr_temp = None
            mode = self.awhp_temp_mode
            if mode and mode == AWHP_MODE_WATER:
                curr_temp = self.water_out_current_temp
            if curr_temp is None:
                curr_temp = self.room_temp
            self._current_temp = curr_temp
        return self._current_temp

    @property
    def target_temp(self):
        """Return target temperature."""
        key = self._get_state_key(STATE_TARGET_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def duct_zones_state(self):
        """Return current state for duct zones."""
        key = self._get_state_key(STATE_DUCT_ZONE)
        return self.to_int_or_none(self._data.get(key))

    @property
    def duct_zones_type(self):
        """Return the type of configured duct zones (for V1 devices)."""
        if self.is_info_v2:
            return None
        return self.to_int_or_none(self._data.get(DUCT_ZONE_V1_TYPE))

    @property
    def energy_current(self):
        """Return current energy usage."""
        key = self._get_state_key(STATE_POWER)
        if (value := self.to_int_or_none(self._data.get(key))) is None:
            return None
        if value <= 50 and not self.is_on:
            # decrease power for devices that always return 50 when standby
            value = 5
        return self._update_feature(AirConditionerFeatures.ENERGY_CURRENT, value, False)

    @property
    def humidity(self):
        """Return current humidity."""
        key = self._get_state_key(STATE_HUMIDITY)
        if (value := self.to_int_or_none(self.lookup_range(key))) is None:
            return None
        # some V1 device return humidity with value = 0
        # when humidity sensor is not available
        if not self.is_info_v2 and value == 0:
            return None
        if value >= 100:
            value = value / 10
        return self._update_feature(AirConditionerFeatures.HUMIDITY, value, False)

    @property
    def mode_airclean(self):
        """Return AirClean Mode status."""
        if not self._device.is_mode_airclean_supported:
            return None
        key = self._get_state_key(STATE_MODE_AIRCLEAN)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        status = value == MODE_AIRCLEAN_ON
        return self._update_feature(AirConditionerFeatures.MODE_AIRCLEAN, status, False)

    @property
    def mode_jet(self):
        """Return Jet Mode status."""
        if self._device.supported_mode_jet == JetModeSupport.NONE:
            return None
        key = self._get_state_key(STATE_MODE_JET)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            status = JetMode(value) != JetMode.OFF
        except ValueError:
            status = False
        return self._update_feature(AirConditionerFeatures.MODE_JET, status, False)

    @property
    def lighting_display(self):
        """Return display lighting status."""
        if not (supp_modes := self._device.supported_ligth_modes):
            return None
        key = self._get_state_key(STATE_LIGHTING_DISPLAY)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        return self._update_feature(
            AirConditionerFeatures.LIGHTING_DISPLAY, value in supp_modes[MODE_ON], False
        )

    @property
    def filters_life(self):
        """Return percentage status for all filters."""
        result = {}

        for filter_def in FILTER_TYPES:
            status = self._get_filter_life(
                filter_def[1],
                filter_def[2],
                use_time_inverted=self._filter_use_time_inverted,
            )
            if status is not None:
                for index, feat in enumerate(filter_def[0]):
                    if index >= len(status):
                        break
                    self._update_feature(feat, status[index], False)
                    result[feat] = status[index]

        return result

    @property
    def airmon_on(self):
        """Return if AirMon sensor is on."""
        if self._airmon_on is None:
            self._airmon_on = False
            key = self._get_state_key(STATE_AIRSENSORMON)
            if (value := self.lookup_enum(key, True)) is not None:
                self._airmon_on = value == MODE_ON
        return self._airmon_on

    @property
    def pm1(self):
        """Return Air PM1 value."""
        if not self._device.is_pm1_supported:
            return None
        key = self._get_state_key(STATE_PM1)
        if (value := self.lookup_range(key)) is None:
            return None
        if not (self.is_on or self.airmon_on):
            value = None
        return self._update_feature(
            AirConditionerFeatures.PM1, value, False, allow_none=True
        )

    @property
    def pm10(self):
        """Return Air PM10 value."""
        if not self._device.is_pm10_supported:
            return None
        key = self._get_state_key(STATE_PM10)
        if (value := self.lookup_range(key)) is None:
            return None
        if not (self.is_on or self.airmon_on):
            value = None
        return self._update_feature(
            AirConditionerFeatures.PM10, value, False, allow_none=True
        )

    @property
    def pm25(self):
        """Return Air PM2.5 value."""
        if not self._device.is_pm25_supported:
            return None
        key = self._get_state_key(STATE_PM25)
        if (value := self.lookup_range(key)) is None:
            return None
        if not (self.is_on or self.airmon_on):
            value = None
        return self._update_feature(
            AirConditionerFeatures.PM25, value, False, allow_none=True
        )

    @property
    def awhp_temp_mode(self):
        """Return if AWHP is set in air or water mode."""
        if not self._device.is_air_to_water:
            return None
        key = self._get_state_key(STATE_AWHP_TEMP_MODE)
        if (value := self.lookup_enum(key, True)) is not None:
            if value == AWHP_MODE_AIR:
                return AWHP_MODE_AIR
        return AWHP_MODE_WATER

    @property
    def water_in_current_temp(self):
        """Return AWHP in water current temperature."""
        if not self._device.is_air_to_water:
            return None
        key = self._get_state_key(STATE_WATER_IN_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(AirConditionerFeatures.WATER_IN_TEMP, value, False)

    @property
    def water_out_current_temp(self):
        """Return AWHP out water current temperature."""
        if not self._device.is_air_to_water:
            return None
        key = self._get_state_key(STATE_WATER_OUT_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(AirConditionerFeatures.WATER_OUT_TEMP, value, False)

    @property
    def water_target_min_temp(self):
        """Return AWHP water target minimum allowed temperature."""
        if not self._device.is_air_to_water:
            return None
        key = self._get_state_key(STATE_WATER_MIN_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def water_target_max_temp(self):
        """Return AWHP water target maximun allowed temperature."""
        if not self._device.is_air_to_water:
            return None
        key = self._get_state_key(STATE_WATER_MAX_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def mode_awhp_silent(self):
        """Return AWHP silent mode status."""
        if not (self._device.is_air_to_water and self.is_info_v2):
            return None
        key = self._get_state_key(STATE_MODE_AWHP_SILENT)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        status = value == MODE_ON
        return self._update_feature(
            AirConditionerFeatures.MODE_AWHP_SILENT, status, False
        )

    @property
    def hot_water_current_temp(self):
        """Return AWHP hot water current temperature."""
        if not self._device.is_water_heater_supported:
            return None
        key = self._get_state_key(STATE_HOT_WATER_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(AirConditionerFeatures.HOT_WATER_TEMP, value, False)

    @property
    def hot_water_target_temp(self):
        """Return AWHP hot water target temperature."""
        if not self._device.is_water_heater_supported:
            return None
        key = self._get_state_key(STATE_HOT_WATER_TARGET_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def hot_water_target_min_temp(self):
        """Return AWHP hot water target minimum allowed temperature."""
        if not self._device.is_water_heater_supported:
            return None
        key = self._get_state_key(STATE_HOT_WATER_MIN_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def hot_water_target_max_temp(self):
        """Return AWHP hot water target maximum allowed temperature."""
        if not self._device.is_water_heater_supported:
            return None
        key = self._get_state_key(STATE_HOT_WATER_MAX_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def reservation_sleep_time(self):
        """Return reservation sleep time in minutes."""
        key = self._get_state_key(STATE_RESERVATION_SLEEP_TIME)
        if (value := self.to_int_or_none(self.lookup_range(key))) is None:
            return None
        return self._update_feature(
            AirConditionerFeatures.RESERVATION_SLEEP_TIME, value, False
        )

    def _update_features(self):
        _ = [
            self.room_temp,
            self.energy_current,
            self.filters_life,
            self.humidity,
            self.pm10,
            self.pm25,
            self.pm1,
            self.mode_airclean,
            self.mode_jet,
            self.lighting_display,
            self.water_in_current_temp,
            self.water_out_current_temp,
            self.mode_awhp_silent,
            self.hot_water_current_temp,
            self.reservation_sleep_time,
        ]
