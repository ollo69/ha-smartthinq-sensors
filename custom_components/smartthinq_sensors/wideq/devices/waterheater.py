"""------------------for WATER HEATER"""

from __future__ import annotations

from enum import Enum

from ..backports.functools import cached_property
from ..const import TemperatureUnit, WaterHeaterFeatures
from ..core_async import ClientAsync
from ..core_exceptions import InvalidRequestError
from ..core_util import TempUnitConversion
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

CTRL_BASIC = ["Control", "basicCtrl"]

STATE_POWER_V1 = "InOutInstantPower"

SUPPORT_OPERATION_MODE = ["SupportOpModeExt2", "support.airState.opModeExt2"]

# AC Section
STATE_OPERATION = ["Operation", "airState.operation"]
STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
STATE_CURRENT_TEMP = ["TempCur", "airState.tempState.hotWaterCurrent"]
STATE_TARGET_TEMP = ["TempCfg", "airState.tempState.hotWaterTarget"]
STATE_POWER = [STATE_POWER_V1, "airState.energy.onCurrent"]

CMD_STATE_OP_MODE = [CTRL_BASIC, "Set", STATE_OPERATION_MODE]
CMD_STATE_TARGET_TEMP = [CTRL_BASIC, "Set", STATE_TARGET_TEMP]

CMD_ENABLE_EVENT_V2 = ["allEventEnable", "Set", "airState.mon.timeout"]

DEFAULT_MIN_TEMP = 35
DEFAULT_MAX_TEMP = 60

TEMP_STEP_WHOLE = 1.0
TEMP_STEP_HALF = 0.5

ADD_FEAT_POLL_INTERVAL = 300  # 5 minutes


class ACOp(Enum):
    """Whether a device is on or off."""

    OFF = "@AC_MAIN_OPERATION_OFF_W"
    ON = "@AC_MAIN_OPERATION_ON_W"
    RIGHT_ON = "@AC_MAIN_OPERATION_RIGHT_ON_W"  # Right fan only.
    LEFT_ON = "@AC_MAIN_OPERATION_LEFT_ON_W"  # Left fan only.
    ALL_ON = "@AC_MAIN_OPERATION_ALL_ON_W"  # Both fans (or only fan) on.


class WHMode(Enum):
    """The operation mode for an WH device."""

    HEAT_PUMP = "@WH_MODE_HEAT_PUMP_W"
    AUTO = "@WH_MODE_AUTO_W"
    TURBO = "@WH_MODE_TURBO_W"
    VACATION = "@WH_MODE_VACATION_W"


class WaterHeaterDevice(Device):
    """A higher-level interface for a Water Heater."""

    def __init__(
        self,
        client: ClientAsync,
        device_info: DeviceInfo,
        temp_unit=TemperatureUnit.CELSIUS,
    ):
        """Initialize WaterHeaterDevice object."""
        super().__init__(client, device_info, WaterHeaterStatus(self))
        self._temperature_unit = (
            TemperatureUnit.FAHRENHEIT
            if temp_unit == TemperatureUnit.FAHRENHEIT
            else TemperatureUnit.CELSIUS
        )

        self._current_power = 0
        self._current_power_supported = True

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

    @cached_property
    def _temperature_range(self):
        """Get valid temperature range for model."""
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
    def op_modes(self):
        """Return a list of available operation modes."""
        return self._get_property_values(SUPPORT_OPERATION_MODE, WHMode)

    @property
    def temperature_unit(self):
        """Return the unit used for temperature."""
        return self._temperature_unit

    @property
    def target_temperature_step(self):
        """Return target temperature step used."""
        return TEMP_STEP_WHOLE

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

    async def set_op_mode(self, mode):
        """Set the device's operating mode to an `OpMode` value."""
        if mode not in self.op_modes:
            raise ValueError(f"Invalid operating mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_OP_MODE)
        mode_value = self.model_info.enum_value(keys[2], WHMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=mode_value)

    async def set_target_temp(self, temp):
        """Set the device's target temperature in Celsius degrees."""
        range_info = self._temperature_range
        conv_temp = self._f2c(temp)
        if range_info and not (range_info[0] <= conv_temp <= range_info[1]):
            raise ValueError(f"Target temperature out of range: {temp}")
        keys = self._get_cmd_keys(CMD_STATE_TARGET_TEMP)
        await self.set(keys[0], keys[1], key=keys[2], value=conv_temp)

    async def get_power(self):
        """Get the instant power usage in watts of the whole unit."""
        if not self._current_power_supported:
            return 0
        try:
            value = await self._get_config(STATE_POWER_V1)
            return value[STATE_POWER_V1]
        except (ValueError, InvalidRequestError):
            # Device does not support whole unit instant power usage
            self._current_power_supported = False
            return 0

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
        self._status = WaterHeaterStatus(self)
        return self._status

    # async def _get_device_info(self):
    #    """
    #    Call additional method to get device information for API v1.
    #    Called by 'device_poll' method using a lower poll rate.
    #    """
    #    # this command is to get power usage on V1 device
    #    self._current_power = await self.get_power()

    async def _pre_update_v2(self):
        """Call additional methods before data update for v2 API."""
        # this command is to get power and temp info on V2 device
        keys = self._get_cmd_keys(CMD_ENABLE_EVENT_V2)
        await self.set(keys[0], keys[1], key=keys[2], value="70", ctrl_path="control")

    async def poll(self) -> WaterHeaterStatus | None:
        """Poll the device's current state."""
        res = await self._device_poll(
            # additional_poll_interval_v1=ADD_FEAT_POLL_INTERVAL,
            thinq2_query_device=True,
        )
        if not res:
            return None
        # if self._should_poll:
        #    res[STATE_POWER_V1] = self._current_power

        self._status = WaterHeaterStatus(self, res)

        return self._status


class WaterHeaterStatus(DeviceStatus):
    """Higher-level information about a Water Heater's current status."""

    _device: WaterHeaterDevice

    def __init__(self, device: WaterHeaterDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._operation = None

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
            return WHMode(value).name
        except ValueError:
            return None

    @property
    def current_temp(self):
        """Return current temperature."""
        key = self._get_state_key(STATE_CURRENT_TEMP)
        value = self._str_to_temp(self._data.get(key))
        return self._update_feature(WaterHeaterFeatures.HOT_WATER_TEMP, value, False)

    @property
    def target_temp(self):
        """Return target temperature."""
        key = self._get_state_key(STATE_TARGET_TEMP)
        return self._str_to_temp(self._data.get(key))

    @property
    def energy_current(self):
        """Return current energy usage."""
        key = self._get_state_key(STATE_POWER)
        if (value := self.to_int_or_none(self._data.get(key))) is None:
            return None
        if value <= 50:
            # decrease power for devices that always return 50 when standby
            value = 5
        return self._update_feature(WaterHeaterFeatures.ENERGY_CURRENT, value, False)

    def _update_features(self):
        _ = [
            self.current_temp,
            self.energy_current,
        ]
