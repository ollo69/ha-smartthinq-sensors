"""------------------for AC"""
import logging
from typing import Optional
from numbers import Number

from .device import (
    Device,
    DeviceStatus,
    STATE_OPTIONITEM_NONE,
    UNITTEMPMODES,
)

STATE_AC_OPERATION_OFF = "@AC_MAIN_OPERATION_OFF_W"
STATE_AC_OPERATION_MODE = [
    "@NON",
    "@AC_MAIN_OPERATION_MODE_COOL_W",
    "@AC_MAIN_OPERATION_MODE_DRY_W",
    "@AC_MAIN_OPERATION_MODE_FAN_W",
    "@AC_MAIN_OPERATION_MODE_AI_W",
]

STATE_AC_POWER_OFF = "@WM_STATE_POWER_OFF_W"
STATE_AC_END = [
    "@WM_STATE_END_W",
    "@WM_STATE_COMPLETE_W",
]
STATE_AC_ERROR_OFF = "OFF"
STATE_AC_ERROR_NO_ERROR = [
    "ERROR_NOERROR",
    "ERROR_NOERROR_TITLE",
    "No Error",
    "No_Error",
]

STATE_AC_WIND_STRENGTH = [
    #"@AC_MAIN_WIND_STRENGTH_SLOW_W",
    "@AC_MAIN_WIND_STRENGTH_SLOW_LOW_W",
    "@AC_MAIN_WIND_STRENGTH_LOW_W",
    #"@AC_MAIN_WIND_STRENGTH_LOW_MID_W",
    "@AC_MAIN_WIND_STRENGTH_MID_W",
    #"@AC_MAIN_WIND_STRENGTH_MID_HIGH_W",
    "@AC_MAIN_WIND_STRENGTH_HIGH_W",
    "@AC_MAIN_WIND_STRENGTH_POWER_W",
    "@AC_MAIN_WIND_STRENGTH_AUTO_W",
]

STATE_AC_OPERATION_MODE = [
    "@AC_MAIN_OPERATION_MODE_COOL_W",
    "@AC_MAIN_OPERATION_MODE_DRY_W",
    "@AC_MAIN_OPERATION_MODE_FAN_W",
    "@AC_MAIN_OPERATION_MODE_AI_W",
]

#AC_CONTROL_COMMAND = "basicCtrl"
AC_STATE_OPERATION = "airState.operation"
AC_STATE_OPERATION_MODE = "airState.opMode"
AC_STATE_CURRENT_TEMP = "airState.tempState.current"
AC_STATE_TARGET_TEMP = "airState.tempState.target"
AC_STATE_CURRENT_HUMIDITY = "airState.humidity.current"
AC_STATE_WIND_STRENGTH = "airState.windStrength"

class AirConditionerDevice(Device):
    """A higher-level interface for a AC."""

    def __init__(self, client, device):
        super().__init__(client, device, AirConditionerStatus(self, None))

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
        self._run_state = None
        self._pre_state = None
        self._error = None

    def lookup_enum(self, key):
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        return self._device.model_info.enum_name(
            curr_key, self.int_or_none(self._data[curr_key])
        )

    def _get_run_state(self):
        if not self._run_state:
            state = self.lookup_enum(AC_STATE_OPERATION)
            if not state:
                self._run_state = STATE_WASHER_POWER_OFF
            else:
                self._run_state = state
        return self._run_state

    #def _get_error(self):
    #    if not self._error:
    #        error = self.lookup_reference(["Error", "error"], ref_key="title")
    #        if not error:
    #            self._error = STATE_WASHER_ERROR_OFF
    #        else:
    #            self._error = error
    #    return self._error

    def _get_number_value(self, key):
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        value = self._data[curr_key]
        if not isinstance(value, Number):
            return None
        return value

    @property
    def is_on(self):
        run_state = self._get_run_state()
        return run_state != STATE_AC_OPERATION_OFF

    @property
    def current_temp(self):
        return self._get_number_value(AC_STATE_CURRENT_TEMP)

    @property
    def target_temp(self):
        return self._get_number_value(AC_STATE_TARGET_TEMP)

    @property
    def current_humidity(self):
        val = self._get_number_value(AC_STATE_CURRENT_HUMIDITY)
        if not val:
            return None
        return val / 10

    @property
    def windstrength(self):
        strength = self.lookup_enum(AC_STATE_WIND_STRENGTH)
        return strength

    @property
    def operation_mode(self):
        opmode = self.lookup_enum(AC_STATE_OPERATION_MODE)
        return opmode
