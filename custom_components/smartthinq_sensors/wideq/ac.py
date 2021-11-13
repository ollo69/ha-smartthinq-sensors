"""------------------for AC"""
import enum
import logging

from typing import Optional

from .device import (
    UNIT_TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT,
    Device,
    DeviceStatus,
)
from . import (
    FEAT_ENERGY_CURRENT,
    FEAT_HUMIDITY,
    FEAT_HOT_WATER_TEMP,
    FEAT_IN_WATER_TEMP,
    FEAT_OUT_WATER_TEMP,
)

from .core_exceptions import InvalidRequestError


LABEL_VANE_HSTEP = "@AC_MAIN_WIND_DIRECTION_STEP_LEFT_RIGHT_W"
LABEL_VANE_VSTEP = "@AC_MAIN_WIND_DIRECTION_STEP_UP_DOWN_W"
LABEL_VANE_HSWING = "@AC_MAIN_WIND_DIRECTION_SWING_LEFT_RIGHT_W"
LABEL_VANE_VSWING = "@AC_MAIN_WIND_DIRECTION_SWING_UP_DOWN_W"
LABEL_VANE_SWIRL = "@AC_MAIN_WIND_DIRECTION_SWIRL_W"

AC_CTRL_BASIC = ["Control", "basicCtrl"]
AC_CTRL_WIND_DIRECTION = ["Control", "wDirCtrl"]
AC_CTRL_MISC = ["Control", "miscCtrl"]
# AC_CTRL_SETTING = "settingInfo"
# AC_CTRL_WIND_MODE = "wModeCtrl"
AC_DUCT_ZONE_V1 = "DuctZone"
AC_STATE_POWER_V1 = "InOutInstantPower"

SUPPORT_AC_OPERATION_MODE = ["SupportOpMode", "support.airState.opMode"]
SUPPORT_AC_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]
SUPPORT_AC_RAC_SUBMODE = ["SupportRACSubMode", "support.racSubMode"]
AC_STATE_OPERATION = ["Operation", "airState.operation"]
AC_STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
AC_STATE_CURRENT_TEMP = ["TempCur", "airState.tempState.current"]
AC_STATE_HOT_WATER_TEMP = ["HotWaterTempCur", "airState.tempState.hotWaterCurrent"]
AC_STATE_IN_WATER_TEMP = ["WaterInTempCur", "airState.tempState.inWaterCurrent"]
AC_STATE_OUT_WATER_TEMP = ["WaterTempCur", "airState.tempState.outWaterCurrent"]
AC_STATE_TARGET_TEMP = ["TempCfg", "airState.tempState.target"]
AC_STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]
AC_STATE_WDIR_HSTEP = ["WDirHStep", "airState.wDir.hStep"]
AC_STATE_WDIR_VSTEP = ["WDirVStep", "airState.wDir.vStep"]
AC_STATE_WDIR_HSWING = ["WDirLeftRight", "airState.wDir.leftRight"]
AC_STATE_WDIR_VSWING = ["WDirUpDown", "airState.wDir.upDown"]
AC_STATE_POWER = [AC_STATE_POWER_V1, "airState.energy.onCurrent"]
AC_STATE_HUMIDITY = ["SensorHumidity", "airState.humidity.current"]
AC_STATE_DUCT_ZONE = ["DuctZoneType", "airState.ductZone.state"]

CMD_STATE_OPERATION = [AC_CTRL_BASIC, "Set", AC_STATE_OPERATION]
CMD_STATE_OP_MODE = [AC_CTRL_BASIC, "Set", AC_STATE_OPERATION_MODE]
CMD_STATE_TARGET_TEMP = [AC_CTRL_BASIC, "Set", AC_STATE_TARGET_TEMP]
CMD_STATE_WIND_STRENGTH = [AC_CTRL_BASIC, "Set", AC_STATE_WIND_STRENGTH]
CMD_STATE_WDIR_HSTEP = [AC_CTRL_WIND_DIRECTION, "Set", AC_STATE_WDIR_HSTEP]
CMD_STATE_WDIR_VSTEP = [AC_CTRL_WIND_DIRECTION, "Set", AC_STATE_WDIR_VSTEP]
CMD_STATE_WDIR_HSWING = [AC_CTRL_WIND_DIRECTION, "Set", AC_STATE_WDIR_HSWING]
CMD_STATE_WDIR_VSWING = [AC_CTRL_WIND_DIRECTION, "Set", AC_STATE_WDIR_VSWING]
CMD_STATE_DUCT_ZONES = [
    AC_CTRL_MISC, "Set", [AC_DUCT_ZONE_V1, "airState.ductZone.control"]
]

CMD_ENABLE_EVENT_V2 = ["allEventEnable", "Set", "airState.mon.timeout"]

# AC_STATE_CURRENT_HUMIDITY_V2 = "airState.humidity.current"
# AC_STATE_AUTODRY_MODE_V2 = "airState.miscFuncState.autoDry"
# AC_STATE_AIRCLEAN_MODE_V2 = "airState.wMode.airClean"
# AC_STATE_FILTER_MAX_TIME_V2 = "airState.filterMngStates.maxTime"
# AC_STATE_FILTER_REMAIN_TIME_V2 = "airState.filterMngStates.useTime"

DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 30
MIN_AWHP_TEMP = 5
MAX_AWHP_TEMP = 80

TEMP_STEP_WHOLE = 1.0
TEMP_STEP_HALF = 0.5

ADD_FEAT_POLL_INTERVAL = 300  # 5 minutes

ZONE_OFF = "0"
ZONE_ON = "1"
ZONE_ST_CUR = "current"
ZONE_ST_NEW = "new"

_LOGGER = logging.getLogger(__name__)


class ACOp(enum.Enum):
    """Whether a device is on or off."""

    OFF = "@AC_MAIN_OPERATION_OFF_W"
    ON = "@AC_MAIN_OPERATION_ON_W"
    RIGHT_ON = "@AC_MAIN_OPERATION_RIGHT_ON_W"  # Right fan only.
    LEFT_ON = "@AC_MAIN_OPERATION_LEFT_ON_W"  # Left fan only.
    ALL_ON = "@AC_MAIN_OPERATION_ALL_ON_W"  # Both fans (or only fan) on.


class ACMode(enum.Enum):
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


class ACFanSpeed(enum.Enum):
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


class ACVStepMode(enum.Enum):
    """The vertical step mode for an AC/HVAC device.

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


class ACHStepMode(enum.Enum):
    """The horizontal step mode for an AC/HVAC device.
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


class ACSwingMode(enum.Enum):
    """The swing mode for an AC/HVAC device."""

    SwingOff = "@OFF"
    SwingOn = "@ON"


class AirConditionerDevice(Device):
    """A higher-level interface for a AC."""

    def __init__(self, client, device, temp_unit=UNIT_TEMP_CELSIUS):
        super().__init__(client, device, AirConditionerStatus(self, None))
        self._temperature_unit = (
            UNIT_TEMP_FAHRENHEIT if temp_unit == UNIT_TEMP_FAHRENHEIT else UNIT_TEMP_CELSIUS
        )
        self._is_air_to_water = None
        self._supported_operation = None
        self._supported_op_modes = None
        self._supported_fan_speeds = None
        self._supported_horizontal_steps = None
        self._supported_horizontal_swings = None
        self._supported_vertical_steps = None
        self._supported_vertical_swings = None
        self._temperature_range = None
        self._temperature_step = TEMP_STEP_WHOLE
        self._duct_zones = {}

        self._current_power = 0
        self._current_power_supported = True

        self._f2c_map = None
        self._c2f_map = None

    def _f2c(self, value):
        """Get a dictionary mapping Fahrenheit to Celsius temperatures for
        this device.

        Unbelievably, SmartThinQ devices have their own lookup tables
        for mapping the two temperature scales. You can get *close* by
        using a real conversion between the two temperature scales, but
        precise control requires using the custom LUT.
        """
        if self._temperature_unit == UNIT_TEMP_CELSIUS:
            return value

        if self._f2c_map is None:
            mapping = self.model_info.value("TempFahToCel").options
            self._f2c_map = {int(f): c for f, c in mapping.items()}
        return self._f2c_map.get(value, value)

    def conv_temp_unit(self, value):
        """Get an inverse mapping from Celsius to Fahrenheit.

        Just as unbelievably, this is not exactly the inverse of the
        `f2c` map. There are a few values in this reverse mapping that
        are not in the other.
        """
        if self._temperature_unit == UNIT_TEMP_CELSIUS:
            return float(value)

        if self._c2f_map is None:
            mapping = self.model_info.value("TempCelToFah").options
            out = {}
            for c, f in mapping.items():
                try:
                    c_num = int(c)
                except ValueError:
                    c_num = float(c)
                out[c_num] = f
            self._c2f_map = out
        return self._c2f_map.get(value, value)

    def _adjust_temperature_step(self, target_temp):
        if self._temperature_step != TEMP_STEP_WHOLE:
            return
        if target_temp is None:
            return
        if int(target_temp) != target_temp:
            self._temperature_step = TEMP_STEP_HALF

    def _get_supported_operations(self):
        """Get a list of the ACOp Operations the device supports."""

        if not self._supported_operation:
            key = self._get_state_key(AC_STATE_OPERATION)
            mapping = self.model_info.value(key).options
            self._supported_operation = [ACOp(o) for o in mapping.values()]
        return self._supported_operation

    def _supported_on_operation(self):
        """Get the most correct "On" operation the device supports.
        :raises ValueError: If ALL_ON is not supported, but there are
            multiple supported ON operations. If a model raises this,
            its behaviour needs to be determined so this function can
            make a better decision.
        """

        operations = self._get_supported_operations().copy()
        operations.remove(ACOp.OFF)

        # This ON operation appears to be supported in newer AC models
        if ACOp.ALL_ON in operations:
            return ACOp.ALL_ON

        # This ON operation appears to be supported in V2 AC models, to check
        if ACOp.ON in operations:
            return ACOp.ON

        # Older models, or possibly just the LP1419IVSM, do not support ALL_ON,
        # instead advertising only a single operation of RIGHT_ON.
        # Thus, if there's only one ON operation, we use that.
        if len(operations) == 1:
            return operations[0]

        # Hypothetically, the API could return multiple ON operations, neither
        # of which are ALL_ON. This will raise in that case, as we don't know
        # what that model will expect us to do to turn everything on.
        # Or, this code will never actually be reached! We can only hope. :)
        raise ValueError(
            f"could not determine correct 'on' operation:"
            f" too many reported operations: '{str(operations)}'"
        )

    def _get_temperature_range(self):
        """Get valid temperature range for model."""

        if not self._temperature_range:
            if not self.model_info:
                return None

            if self.is_air_to_water:
                min_temp = MIN_AWHP_TEMP
                max_temp = MAX_AWHP_TEMP
            else:
                key = self._get_state_key(AC_STATE_TARGET_TEMP)
                range_info = self.model_info.value(key)
                if not range_info:
                    min_temp = DEFAULT_MIN_TEMP
                    max_temp = DEFAULT_MAX_TEMP
                else:
                    min_temp = min(range_info.min, DEFAULT_MIN_TEMP)
                    max_temp = max(range_info.max, DEFAULT_MAX_TEMP)
            self._temperature_range = [min_temp, max_temp]
        return self._temperature_range

    def _is_vane_mode_supported(self, mode):
        """Check if a specific vane mode is supported."""
        supp_key = self._get_state_key(SUPPORT_AC_RAC_SUBMODE)
        if not self.model_info.enum_value(supp_key, mode):
            return False
        return True

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
        return [key for key in self._duct_zones]

    def update_duct_zones(self):
        """Update the current duct zones status."""
        states = self._get_duct_zones()
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
            self._set_duct_zones(duct_zones)

    def _get_duct_zones(self) -> dict:
        """Get the status of the zones (for ThinQ1 only zone configured).

        return value is a dict with this format:
        - key: The zone index. A string containing a number
        - value: another dict with:
            - key: "current"
            - value: "1" if zone is ON else "0"
        """

        # first check if duct is supported
        if not self._status:
            return {}
        duct_state = self._status.duct_zones_state
        if not duct_state:
            return {}

        # get real duct zones states
        """
        For ThinQ2 we transform the value in the status in binary
        and than we create the result. We always have 8 duct zone.
        """
        if not self._should_poll:
            bin_arr = [x for x in reversed(f"{duct_state:08b}")]
            return {
                str(v+1): {ZONE_ST_CUR: k} for v, k in enumerate(bin_arr)
            }

        """
        For ThinQ1 devices result is a list of dicts with these keys:
        - "No": The zone index. A string containing a number,
          starting from 1.
        - "Cfg": Whether the zone is enabled. A string, either "1" or
          "0".
        - "State": Whether the zone is open. Also "1" or "0".
        """
        zones = self._get_config(AC_DUCT_ZONE_V1)
        return {
            zone["No"]: {ZONE_ST_CUR: zone["State"]}
            for zone in zones
            if zone["Cfg"] == "1"
        }

    def _set_duct_zones(self, zones: dict):
        """Turn off or on the device's zones.

        The `zones` parameter is the same returned by _get_duct_zones()
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
        self.set(keys[0], keys[1], key=keys[2], value=zone_cmd)

    @property
    def is_air_to_water(self):
        """Return if is a Air To Water device."""
        if self._is_air_to_water is None:
            if not self.model_info:
                return False
            self._is_air_to_water = self.model_info.model_type == "AWHP"
        return self._is_air_to_water

    @property
    def op_modes(self):
        """Return a list of available operation modes."""
        if self._supported_op_modes is None:
            key = self._get_state_key(SUPPORT_AC_OPERATION_MODE)
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in ACMode]
            self._supported_op_modes = [ACMode(o).name for o in mapping.values() if o in mode_list]
        return self._supported_op_modes

    @property
    def fan_speeds(self):
        """Return a list of available fan speeds."""
        if self._supported_fan_speeds is None:
            key = self._get_state_key(SUPPORT_AC_WIND_STRENGTH)
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in ACFanSpeed]
            self._supported_fan_speeds = [ACFanSpeed(o).name for o in mapping.values() if o in mode_list]
        return self._supported_fan_speeds

    @property
    def horizontal_step_modes(self):
        """Return a list of available horizontal step modes."""
        if self._supported_horizontal_steps is None:
            self._supported_horizontal_steps = []
            if not self._is_vane_mode_supported(LABEL_VANE_HSTEP):
                return []

            key = self._get_state_key(AC_STATE_WDIR_HSTEP)
            values = self.model_info.value(key)
            if not hasattr(values, "options"):
                return []

            mapping = values.options
            mode_list = [e.value for e in ACHStepMode]
            self._supported_horizontal_steps = [
                ACHStepMode(o).name for o in mapping.values() if o in mode_list
            ]
        return self._supported_horizontal_steps

    @property
    def horizontal_swing_modes(self):
        """Return a list of available horizontal swing modes."""
        if self._supported_horizontal_swings is None:
            self._supported_horizontal_swings = []
            if len(self.horizontal_step_modes) > 0:
                return []
            if not self._is_vane_mode_supported(LABEL_VANE_HSWING):
                return []

            self._supported_horizontal_swings = [e.name for e in ACSwingMode]
        return self._supported_horizontal_swings

    @property
    def vertical_step_modes(self):
        """Return a list of available vertical step modes."""
        if self._supported_vertical_steps is None:
            self._supported_vertical_steps = []
            if not self._is_vane_mode_supported(LABEL_VANE_VSTEP):
                return []

            key = self._get_state_key(AC_STATE_WDIR_VSTEP)
            values = self.model_info.value(key)
            if not hasattr(values, "options"):
                return []

            mapping = values.options
            mode_list = [e.value for e in ACVStepMode]
            self._supported_vertical_steps = [
                ACVStepMode(o).name for o in mapping.values() if o in mode_list
            ]
        return self._supported_vertical_steps

    @property
    def vertical_swing_modes(self):
        """Return a list of available vertical swing modes."""
        if self._supported_vertical_swings is None:
            self._supported_vertical_swings = []
            if len(self.vertical_step_modes) > 0:
                return []
            if not self._is_vane_mode_supported(LABEL_VANE_VSWING):
                return []

            self._supported_vertical_swings = [e.name for e in ACSwingMode]
        return self._supported_vertical_swings

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
        temp_range = self._get_temperature_range()
        if not temp_range:
            return None
        return self.conv_temp_unit(temp_range[0])

    @property
    def target_temperature_max(self):
        """Return maximum value for target temperature."""
        temp_range = self._get_temperature_range()
        if not temp_range:
            return None
        return self.conv_temp_unit(temp_range[1])

    def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = self._supported_on_operation() if turn_on else ACOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op.value)
        self.set(keys[0], keys[1], key=keys[2], value=op_value)

    def set_op_mode(self, mode):
        """Set the device's operating mode to an `OpMode` value."""

        if mode not in self.op_modes:
            raise ValueError(f"Invalid operating mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_OP_MODE)
        mode_value = self.model_info.enum_value(keys[2], ACMode[mode].value)
        self.set(keys[0], keys[1], key=keys[2], value=mode_value)

    def set_fan_speed(self, speed):
        """Set the fan speed to a value from the `ACFanSpeed` enum."""

        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], ACFanSpeed[speed].value)
        self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    def set_horizontal_step_mode(self, mode):
        """Set the horizontal step to a value from the `ACHStepMode` enum."""

        if mode not in self.horizontal_step_modes:
            raise ValueError(f"Invalid horizontal step mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_HSTEP)
        step_mode = self.model_info.enum_value(keys[2], ACHStepMode[mode].value)
        self.set(keys[0], keys[1], key=keys[2], value=step_mode)

    def set_horizontal_swing_mode(self, mode):
        """Set the horizontal swing to a value from the `ACSwingMode` enum."""

        if mode not in self.horizontal_swing_modes:
            raise ValueError(f"Invalid horizontal swing mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_HSWING)
        swing_mode = self.model_info.enum_value(keys[2], ACSwingMode[mode].value)
        self.set(keys[0], keys[1], key=keys[2], value=swing_mode)

    def set_vertical_step_mode(self, mode):
        """Set the vertical step to a value from the `ACVStepMode` enum."""

        if mode not in self.vertical_step_modes:
            raise ValueError(f"Invalid vertical step mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_VSTEP)
        step_mode = self.model_info.enum_value(keys[2], ACVStepMode[mode].value)
        self.set(keys[0], keys[1], key=keys[2], value=step_mode)

    def set_vertical_swing_mode(self, mode):
        """Set the vertical swing to a value from the `ACSwingMode` enum."""

        if mode not in self.vertical_swing_modes:
            raise ValueError(f"Invalid vertical swing mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_VSWING)
        swing_mode = self.model_info.enum_value(keys[2], ACSwingMode[mode].value)
        self.set(keys[0], keys[1], key=keys[2], value=swing_mode)

    def set_target_temp(self, temp):
        """Set the device's target temperature in Celsius degrees."""

        range_info = self._get_temperature_range()
        conv_temp = self._f2c(temp)
        if range_info and not (range_info[0] <= conv_temp <= range_info[1]):
            raise ValueError(f"Target temperature out of range: {temp}")
        keys = self._get_cmd_keys(CMD_STATE_TARGET_TEMP)
        self.set(keys[0], keys[1], key=keys[2], value=conv_temp)

    def get_power(self):
        """Get the instant power usage in watts of the whole unit"""
        if not self._current_power_supported:
            return 0

        try:
            value = self._get_config(AC_STATE_POWER_V1)
            return value[AC_STATE_POWER_V1]
        except (ValueError, InvalidRequestError):
            # Device does not support whole unit instant power usage
            self._current_power_supported = False
            return 0

    def set(self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None):
        """Set a device's control for `key` to `value`."""
        super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = AirConditionerStatus(self, None)
        return self._status

    def _get_device_info(self):
        """Call additional method to get device information for API v1.

        Called by 'device_poll' method using a lower poll rate
        """
        # this command is to get power usage on V1 device
        if not self.is_air_to_water:
            self._current_power = self.get_power()

    def _pre_update_v2(self):
        """Call additional methods before data update for v2 API."""
        # this command is to get power and temp info on V2 device
        keys = self._get_cmd_keys(CMD_ENABLE_EVENT_V2)
        self.set(keys[0], keys[1], key=keys[2], value="70", ctrl_path="control")

    def poll(self) -> Optional["AirConditionerStatus"]:
        """Poll the device's current state."""

        res = self.device_poll(
            thinq1_additional_poll=ADD_FEAT_POLL_INTERVAL,
            thinq2_query_device=True,
        )
        if not res:
            return None
        if self._should_poll and not self.is_air_to_water:
            res[AC_STATE_POWER_V1] = self._current_power

        self._status = AirConditionerStatus(self, res)
        if self._temperature_step == TEMP_STEP_WHOLE:
            self._adjust_temperature_step(self._status.target_temp)

        # manage duct devices, if not ducted do nothing
        try:
            self.update_duct_zones()
        except Exception as ex:
            _LOGGER.exception("Duct zone control failed", exc_info=ex)

        return self._status


class AirConditionerStatus(DeviceStatus):
    """Higher-level information about a AC's current status."""

    def __init__(self, device, data):
        super().__init__(device, data)
        self._operation = None

    @staticmethod
    def _str_to_num(s):
        """Convert a string to either an `int` or a `float`.

        Troublingly, the API likes values like "18", without a trailing
        ".0", for whole numbers. So we use `int`s for integers and
        `float`s for non-whole numbers.
        """
        if not s:
            return None

        f = float(s)
        if f == int(f):
            return int(f)
        return f

    def _str_to_temp(self, s):
        """Convert a string to either an `int` or a `float` temperature."""
        temp = self._str_to_num(s)
        if not temp:  # value 0 return None!!!
            return None
        return self._device.conv_temp_unit(temp)

    def _get_state_key(self, key_name):
        if isinstance(key_name, list):
            return key_name[1 if self.is_info_v2 else 0]
        return key_name

    def _get_operation(self):
        if self._operation is None:
            key = self._get_state_key(AC_STATE_OPERATION)
            self._operation = self.lookup_enum(key, True)
        try:
            return ACOp(self._operation)
        except ValueError:
            return None

    def update_status(self, key, value):
        if not super().update_status(key, value):
            return False
        if key in AC_STATE_OPERATION:
            self._operation = None
        return True

    @property
    def is_on(self):
        op = self._get_operation()
        if not op:
            return False
        return op != ACOp.OFF

    @property
    def operation(self):
        op = self._get_operation()
        if not op:
            return None
        return op.name

    @property
    def operation_mode(self):
        key = self._get_state_key(AC_STATE_OPERATION_MODE)
        try:
            return ACMode(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def fan_speed(self):
        key = self._get_state_key(AC_STATE_WIND_STRENGTH)
        try:
            return ACFanSpeed(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def horizontal_step_mode(self):
        key = self._get_state_key(AC_STATE_WDIR_HSTEP)
        try:
            return ACHStepMode(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def horizontal_swing_mode(self):
        key = self._get_state_key(AC_STATE_WDIR_HSWING)
        try:
            return ACSwingMode(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def vertical_step_mode(self):
        key = self._get_state_key(AC_STATE_WDIR_VSTEP)
        try:
            return ACVStepMode(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def vertical_swing_mode(self):
        key = self._get_state_key(AC_STATE_WDIR_VSWING)
        try:
            return ACSwingMode(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def current_temp(self):
        key = self._get_state_key(AC_STATE_CURRENT_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def target_temp(self):
        key = self._get_state_key(AC_STATE_TARGET_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def hot_water_current_temp(self):
        if not self.is_info_v2:
            return None
        key = self._get_state_key(AC_STATE_HOT_WATER_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(
            FEAT_HOT_WATER_TEMP, value, False
        )

    @property
    def in_water_current_temp(self):
        if not self.is_info_v2:
            return None
        key = self._get_state_key(AC_STATE_IN_WATER_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(
            FEAT_IN_WATER_TEMP, value, False
        )

    @property
    def out_water_current_temp(self):
        if not self.is_info_v2:
            return None
        key = self._get_state_key(AC_STATE_OUT_WATER_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(
            FEAT_OUT_WATER_TEMP, value, False
        )

    @property
    def energy_current(self):
        key = self._get_state_key(AC_STATE_POWER)
        value = self._data.get(key)
        if value is not None and self.is_info_v2 and not self.is_on:
            # decrease power for V2 device that always return 50 when standby
            new_value = self.to_int_or_none(value)
            if new_value and new_value <= 50:
                value = 5.0
        return self._update_feature(
            FEAT_ENERGY_CURRENT, value, False
        )

    @property
    def humidity(self):
        value = self.to_int_or_none(
            self.lookup_range(AC_STATE_HUMIDITY)
        )
        if value is None:
            return None
        return self._update_feature(
            FEAT_HUMIDITY, value/10, False
        )

    @property
    def duct_zones_state(self):
        key = self._get_state_key(AC_STATE_DUCT_ZONE)
        return self.to_int_or_none(self._data.get(key))

    def _update_features(self):
        result = [
            self.hot_water_current_temp,
            self.in_water_current_temp,
            self.out_water_current_temp,
            self.energy_current,
            self.humidity,
        ]
