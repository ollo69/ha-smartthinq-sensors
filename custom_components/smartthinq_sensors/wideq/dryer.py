"""------------------for Dryer"""
import logging
from typing import Optional

from .device import (
    Device,
    DeviceStatus,
    STATE_OPTIONITEM_NONE,
)

STATE_DRYER_POWER_OFF = "@WM_STATE_POWER_OFF_W"
STATE_DRYER_END = "@WM_STATE_END_W"
STATE_DRYER_ERROR_NO_ERROR = "ERROR_NOERROR_TITLE"
STATE_DRYER_ERROR_OFF = "OFF"

_LOGGER = logging.getLogger(__name__)


class DryerDevice(Device):
    """A higher-level interface for a dryer."""
    def __init__(self, client, device):
        super().__init__(client, device, DryerStatus(self, None))

    def poll(self) -> Optional["DryerStatus"]:
        """Poll the device's current state."""

        res = self.device_poll("washerDryer")
        if not res:
            return None

        self._status = DryerStatus(self, res)
        return self._status


class DryerStatus(DeviceStatus):
    """Higher-level information about a dryer's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """
    def __init__(self, device, data):
        super().__init__(device, data)
        self._run_state = None
        self._pre_state = None
        self._error = None

    def _get_run_state(self):
        if not self._run_state:
            state = self.lookup_enum(["State", "state"])
            if not state:
                return STATE_DRYER_POWER_OFF
            self._run_state = state
        return self._run_state

    def _get_pre_state(self):
        if not self._pre_state:
            state = self.lookup_enum(["PreState", "preState"])
            if not state:
                return STATE_DRYER_POWER_OFF
            self._pre_state = state
        return self._pre_state

    def _get_error(self):
        if not self._error:
            error = self.lookup_reference(["Error", "error"], ref_key="title")
            if not error:
                return STATE_DRYER_ERROR_OFF
            self._error = error
        return self._error

    @property
    def is_on(self):
        run_state = self._get_run_state()
        return run_state != STATE_DRYER_POWER_OFF

    @property
    def is_run_completed(self):
        run_state = self._get_run_state()
        pre_state = self._get_pre_state()
        if run_state == STATE_DRYER_END or (
            run_state == STATE_DRYER_POWER_OFF and pre_state == STATE_DRYER_END
        ):
            return True
        return False

    @property
    def is_error(self):
        error = self._get_error()
        if error != STATE_DRYER_ERROR_NO_ERROR and error != STATE_DRYER_ERROR_OFF:
            return True
        return False

    @property
    def run_state(self):
        run_state = self._get_run_state()
        if run_state == STATE_DRYER_POWER_OFF:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(run_state)

    @property
    def pre_state(self):
        pre_state = self._get_pre_state()
        if pre_state == STATE_DRYER_POWER_OFF:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(pre_state)

    @property
    def error_state(self):
        if not self.is_on:
            return STATE_OPTIONITEM_NONE
        error = self._get_error()
        if error == STATE_DRYER_ERROR_NO_ERROR:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(error)

    @property
    def current_course(self):
        if self.is_info_v2:
            course_key = self._device.model_info.config_value(
                "courseType"
            )
        else:
            course_key = ["APCourse", "Course"]
        course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(course)

    @property
    def current_smartcourse(self):
        if self.is_info_v2:
            course_key = self._device.model_info.config_value(
                "smartCourseType"
            )
        else:
            course_key = "SmartCourse"
        smart_course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(smart_course)

    @property
    def remaintime_hour(self):
        if self.is_info_v2:
            return DeviceStatus.int_or_none(self._data.get("remainTimeHour"))
        return self._data.get("Remain_Time_H")

    @property
    def remaintime_min(self):
        if self.is_info_v2:
            return DeviceStatus.int_or_none(self._data.get("remainTimeMinute"))
        return self._data.get("Remain_Time_M")

    @property
    def initialtime_hour(self):
        if self.is_info_v2:
            return DeviceStatus.int_or_none(self._data.get("initialTimeHour"))
        return self._data.get("Initial_Time_H")

    @property
    def initialtime_min(self):
        if self.is_info_v2:
            return DeviceStatus.int_or_none(self._data.get("initialTimeMinute"))
        return self._data.get("Initial_Time_M")

    @property
    def reservetime_hour(self):
        if self.is_info_v2:
            return DeviceStatus.int_or_none(self._data.get("reserveTimeHour"))
        return self._data.get("Reserve_Time_H")

    @property
    def reservetime_min(self):
        if self.is_info_v2:
            return DeviceStatus.int_or_none(self._data.get("reserveTimeMinute"))
        return self._data.get("Reserve_Time_M")

    @property
    def temp_control_option_state(self):
        temp_control = self.lookup_enum(["TempControl", "tempControl", "temp"])
        if not temp_control:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(temp_control)

    @property
    def dry_level_option_state(self):
        dry_level = self.lookup_enum(["DryLevel", "dryLevel"])
        if not dry_level:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(dry_level)

    @property
    def time_dry_option_state(self):
        """Get the time dry setting."""
        time_dry = self.lookup_enum("TimeDry")
        if not time_dry:
            return STATE_OPTIONITEM_NONE
        return time_dry

    @property
    def doorlock_state(self):
        if self.is_info_v2:
            return self.lookup_bit("doorLock")
        return self.lookup_bit("DoorLock")

    @property
    def childlock_state(self):
        if self.is_info_v2:
            return self.lookup_bit("childLock")
        return self.lookup_bit("ChildLock")
