"""------------------for AC"""
import enum
import logging

from typing import Optional

from .device import (
    Device,
    DeviceStatus,
)

PROPERTY_TARGET_TEMPERATURE = "target_temperature"
PROPERTY_OPERATION_MODE = "operation_mode"
PROPERTY_FAN_SPEED = "fan_speed"
PROPERTY_VANE_HORIZONTAL = "vane_horizontal"
PROPERTY_VANE_VERTICAL = "vane_vertical"

AC_FLAG_ON = "@ON"
AC_FLAG_OFF = "@OFF"

AC_CTRL_BASIC = "basicCtrl"
AC_CTRL_SETTING = "settingInfo"
AC_CTRL_WIND_DIRECTION = "wDirCtrl"
# AC_CTRL_WIND_MODE = "wModeCtrl"

SUPPORT_AC_OPERATION_MODE = ["SupportOpMode", "support.airState.opMode"]
SUPPORT_AC_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]
AC_STATE_OPERATION = ["Operation", "airState.operation"]
AC_STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
AC_STATE_CURRENT_TEMP = ["TempCur", "airState.tempState.current"]
AC_STATE_TARGET_TEMP = ["TempCfg", "airState.tempState.target"]
AC_STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]
AC_STATE_WDIR_HSTEP = ["WDirHStep", "airState.wDir.hStep"]
AC_STATE_WDIR_VSTEP = ["WDirVStep", "airState.wDir.vStep"]

AC_STATE_WIND_UP_DOWN_V2 = "airState.wDir.upDown"
AC_STATE_WIND_LEFT_RIGHT_V2 = "airState.wDir.leftRight"

AC_STATE_CURRENT_HUMIDITY_V2 = "airState.humidity.current"
AC_STATE_AUTODRY_MODE_V2 = "airState.miscFuncState.autoDry"
AC_STATE_AIRCLEAN_MODE_V2 = "airState.wMode.airClean"
AC_STATE_FILTER_MAX_TIME_V2 = "airState.filterMngStates.maxTime"
AC_STATE_FILTER_REMAIN_TIME_V2 = "airState.filterMngStates.useTime"

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


class AirConditionerDevice(Device):
    """A higher-level interface for a AC."""

    def __init__(self, client, device):
        super().__init__(client, device, AirConditionerStatus(self, None))
        self._supported_operation = None
        self._supported_op_modes = None
        self._supported_fan_speeds = None
        self._temperature_range = None

    def _get_supported_operations(self):
        """Get a list of the ACOp Operations the device supports."""

        if not self._supported_operation:
            key = AC_STATE_OPERATION[1 if self.model_info.is_info_v2 else 0]
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
        if not self._temperature_range:
            key = AC_STATE_TARGET_TEMP[1 if self.model_info.is_info_v2 else 0]
            range_info = self.model_info.value(key)
            if not range_info:
                return None
            self._temperature_range = [range_info.min, range_info.max]
        return self._temperature_range

    @property
    def op_modes(self):
        if not self._supported_op_modes:
            key = SUPPORT_AC_OPERATION_MODE[1 if self.model_info.is_info_v2 else 0]
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in ACMode]
            self._supported_op_modes = [ACMode(o).name for o in mapping.values() if o in mode_list]
        return self._supported_op_modes

    @property
    def fan_speeds(self):
        if not self._supported_fan_speeds:
            key = SUPPORT_AC_WIND_STRENGTH[1 if self.model_info.is_info_v2 else 0]
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in ACFanSpeed]
            self._supported_fan_speeds = [ACFanSpeed(o).name for o in mapping.values() if o in mode_list]
        return self._supported_fan_speeds

    @property
    def target_temperature_step(self):
        return 1

    @property
    def target_temperature_min(self):
        temp_range = self._get_temperature_range()
        if not temp_range:
            return None
        return temp_range[0]

    @property
    def target_temperature_max(self):
        temp_range = self._get_temperature_range()
        if not temp_range:
            return None
        return temp_range[1]

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = self._supported_on_operation() if turn_on else ACOp.OFF
        key = AC_STATE_OPERATION[1 if self.model_info.is_info_v2 else 0]
        op_value = self.model_info.enum_value(key, op.value)
        await self.async_set(key, op_value, AC_CTRL_BASIC)

    async def set_op_mode(self, mode):
        """Set the device's operating mode to an `OpMode` value."""

        if mode not in self.op_modes:
            raise ValueError(f"Invalid operating mode: {mode}")
        key = AC_STATE_OPERATION_MODE[1 if self.model_info.is_info_v2 else 0]
        mode_value = self.model_info.enum_value(key, ACMode[mode].value)
        await self.async_set(key, mode_value, AC_CTRL_BASIC)

    async def set_fan_speed(self, speed):
        """Set the fan speed to a value from the `ACFanSpeed` enum."""

        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        key = AC_STATE_WIND_STRENGTH[1 if self.model_info.is_info_v2 else 0]
        speed_value = self.model_info.enum_value(key, ACFanSpeed[speed].value)
        await self.async_set(key, speed_value, AC_CTRL_BASIC)

    async def set_target_temp(self, temp):
        """Set the device's target temperature in Celsius degrees."""

        range_info = self._get_temperature_range()
        if range_info and not (range_info[0] <= temp <= range_info[1]):
            raise ValueError(f"Target temperature out of range: {temp}")
        key = AC_STATE_TARGET_TEMP[1 if self.model_info.is_info_v2 else 0]
        await self.async_set(key, temp, AC_CTRL_BASIC)

    def reset_status(self):
        self._status = AirConditionerStatus(self, None)
        return self._status

    def poll(self) -> Optional["AirConditionerStatus"]:
        """Poll the device's current state."""

        res = self.device_poll()
        if not res:
            return None

        self._status = AirConditionerStatus(self, res)
        return self._status


class AirConditionerStatus(DeviceStatus):
    """Higher-level information about a AC's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(self, device, data):
        super().__init__(device, data)

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
        else:
            return f

    def _get_operation(self):
        key = AC_STATE_OPERATION[1 if self.is_info_v2 else 0]
        try:
            return ACOp(self.lookup_enum(key, True))
        except ValueError:
            return None

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
        key = AC_STATE_OPERATION_MODE[1 if self.is_info_v2 else 0]
        try:
            return ACMode(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def fan_speed(self):
        key = AC_STATE_WIND_STRENGTH[1 if self.is_info_v2 else 0]
        try:
            return ACFanSpeed(self.lookup_enum(key, True)).name
        except ValueError:
            return None

    @property
    def current_temp(self):
        key = AC_STATE_CURRENT_TEMP[1 if self.is_info_v2 else 0]
        return self._str_to_num(self._data.get(key))

    @property
    def target_temp(self):
        key = AC_STATE_TARGET_TEMP[1 if self.is_info_v2 else 0]
        return self._str_to_num(self._data.get(key))

    def _update_features(self):
        return
