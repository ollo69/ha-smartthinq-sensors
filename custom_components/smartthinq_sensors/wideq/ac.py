"""------------------for AC"""
import logging
from typing import Optional
from numbers import Number

from .device import (
    Device,
    DeviceStatus,
    UNITTEMPMODES,
)

AC_TEMP_UNIT = {
    "@C": UNITTEMPMODES.Celsius,
    "@F": UNITTEMPMODES.Fahrenheit,
}

AC_FLAG_ON = "@ON"
AC_FLAG_OFF = "@OFF"

STATE_AC_OPERATION_OFF = "@AC_MAIN_OPERATION_OFF_W"

AC_CTRL_BASIC = "basicCtrl"
AC_CTRL_SETTING = "settingInfo"
AC_CTRL_WIND_DIRECTION = "wDirCtrl"

SUPPORT_AC_OPERATION_MODE = "support.airState.opMode"
SUPPORT_AC_WIND_STRENGTH = "support.airState.windStrength"
AC_STATE_OPERATION = "airState.operation"
AC_STATE_OPERATION_MODE = "airState.opMode"
AC_STATE_CURRENT_TEMP = "airState.tempState.current"
AC_STATE_TARGET_TEMP = "airState.tempState.target"
AC_STATE_CURRENT_HUMIDITY = "airState.humidity.current"
AC_STATE_WIND_STRENGTH = "airState.windStrength"
AC_STATE_TEMP_UNIT = "airState.tempState.unit"

AC_STATE_AUTODRY_MODE = "airState.miscFuncState.autoDry"
AC_STATE_FILTER_MAX_TIME = "airState.filterMngStates.maxTime"
AC_STATE_FILTER_REMAIN_TIME = "airState.filterMngStates.useTime"

AC_STATE_WIND_UP_DOWN = "airState.wDir.upDown"
AC_STATE_WIND_LEFT_RIGHT = "airState.wDir.leftRight"
AC_STATE_WIND_VSTEP = "airState.wDir.vStep"

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

    def set_state(self, ctrl, key, value):
        path = "/v1/service/devices/" + self._device_info.id + "/control-sync"
        data = dict(ctrlKey=ctrl, command="Set", dataKey=key, dataValue=value)
        self._client.session.post2(path, data)


class AirConditionerStatus(DeviceStatus):
    """Higher-level information about a AC's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(self, device, data):
        super().__init__(device, data)

    def lookup_enum(self, key):
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        return self._device.model_info.enum_name(
            curr_key, self.int_or_none(self._data[curr_key])
        )

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
        return self.operation != STATE_AC_OPERATION_OFF

    @property
    def current_temp(self):
        return self._get_number_value(AC_STATE_CURRENT_TEMP)

    @property
    def target_temp(self):
        return self._get_number_value(AC_STATE_TARGET_TEMP)

    @target_temp.setter
    def target_temp(self, temp):
        range_info = self._device.model_info.value(AC_STATE_TARGET_TEMP)
        if range_info.min <= temp <= range_info.max:
            return self._device.set_state(AC_CTRL_BASIC, AC_STATE_TARGET_TEMP, temp)

    @property
    def current_humidity(self):
        val = self._get_number_value(AC_STATE_CURRENT_HUMIDITY)
        if not val:
            return None
        return val / 10

    @property
    def windstrength(self):
        return self.lookup_enum(AC_STATE_WIND_STRENGTH)

    @windstrength.setter
    def windstrength(self, strength):
        try:
            self._device._model_info.enum_value(SUPPORT_AC_WIND_STRENGTH, op)
        except KeyError:
            return
        val = self._device.model_info.enum_value(AC_STATE_WIND_STRENGTH, op)
        return self._device.set_state(AC_CTRL_BASIC, AC_STATE_WIND_STRENGTH, val)

    @property
    def operation(self):
        return self.lookup_enum(AC_STATE_OPERATION)

    @operation.setter
    def operation(self, op):
        val = self._device.model_info.enum_value(AC_STATE_OPERATION, op)
        return self._device.set_state(AC_CTRL_BASIC, AC_STATE_OPERATION, val)

    @property
    def operation_mode(self):
        return self.lookup_enum(AC_STATE_OPERATION_MODE)

    @operation_mode.setter
    def operation_mode(self, mode):
        try:
            self._device._model_info.enum_value(SUPPORT_AC_OPERATION_MODE, mode)
        except KeyError:
            return
        val = self._device.model_info.enum_value(AC_STATE_OPERATION_MODE, mode)
        return self._device.set_state(AC_CTRL_BASIC, AC_STATE_OPERATION_MODE, val)

    @property
    def temp_unit(self):
        unit = self.lookup_enum(AC_STATE_TEMP_UNIT)
        return AC_TEMP_UNIT[unit]

    @property
    def autodry_mode(self):
        return self.lookup_enum(AC_STATE_AUTODRY_MODE) == AC_FLAG_ON

    @autodry_mode.setter
    def autodry_mode(self, use):
        flag = AC_FLAG_ON if use else AC_FLAG_OFF
        try:
            val = self._device._model_info.enum_value(AC_STATE_AUTODRY_MODE, flag)
        except KeyError:
            return
        return self._device.set_state(AC_CTRL_SETTING, AC_STATE_AUTODRY_MODE, val)

    @property
    def filter_remain(self):
        maxlife = self._get_number_value(AC_STATE_FILTER_MAX_TIME)
        remain = self._get_number_value(AC_STATE_FILTER_REMAIN_TIME)
        return remain / maxlife * 100

    @property
    def wind_up_down(self):
        return self.lookup_enum(AC_STATE_WIND_UP_DOWN) == AC_FLAG_ON

    @wind_up_down.setter
    def wind_up_down(self, use):
        flag = AC_FLAG_ON if use else AC_FLAG_OFF
        try:
            val = self._device._model_info.enum_value(AC_STATE_WIND_UP_DOWN, flag)
        except KeyError:
            return
        return self._device.set_state(AC_CTRL_WIND_DIRECTION, AC_STATE_WIND_UP_DOWN, val)

    @property
    def wind_left_right(self):
        return self.lookup_enum(AC_STATE_WIND_LEFT_RIGHT) == AC_FLAG_ON

    @wind_left_right.setter
    def wind_left_right(self, use):
        flag = AC_FLAG_ON if use else AC_FLAG_OFF
        try:
            val = self._device._model_info.enum_value(AC_STATE_WIND_LEFT_RIGHT, flag)
        except KeyError:
            return
        return self._device.set_state(AC_CTRL_WIND_DIRECTION, AC_STATE_WIND_LEFT_RIGHT, val)

    @property
    def wind_vstep(self):
        # should check with another AC devices
        return int(self._get_number_value(AC_STATE_WIND_VSTEP)) & 0xF

    @wind_vstep.setter
    def wind_vstep(self, step):
        step &= 0xF
        return self._device.set_state(AC_CTRL_WIND_DIRECTION, AC_STATE_WIND_VSTEP, step);
