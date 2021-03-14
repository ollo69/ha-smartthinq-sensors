"""------------------for Dryer"""
import logging
from typing import Optional

from . import (
    FEAT_CHILDLOCK,
    FEAT_DOORLOCK,
    FEAT_DRYLEVEL,
    FEAT_ERROR_MSG,
    FEAT_PRE_STATE,
    FEAT_RUN_STATE,
    FEAT_TEMPCONTROL,
    FEAT_TIMEDRY,
)

from .device import (
    Device,
    DeviceStatus,
    STATE_OPTIONITEM_NONE,
)

STATE_DRYER_POWER_OFF = "@WM_STATE_POWER_OFF_W"
STATE_DRYER_END = [
    "@WM_STATE_END_W",
    "@WM_STATE_COMPLETE_W",
]
STATE_DRYER_ERROR_OFF = "OFF"
STATE_DRYER_ERROR_NO_ERROR = [
    "ERROR_NOERROR",
    "ERROR_NOERROR_TITLE",
    "No Error",
    "No_Error",
]

_LOGGER = logging.getLogger(__name__)


class DryerDevice(Device):
    """A higher-level interface for a dryer."""
    def __init__(self, client, device):
        super().__init__(client, device, DryerStatus(self, None))

    def reset_status(self):
        self._status = DryerStatus(self, None)
        return self._status

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
                self._run_state = STATE_DRYER_POWER_OFF
            else:
                self._run_state = state
        return self._run_state

    def _get_pre_state(self):
        if not self._pre_state:
            state = self.lookup_enum(["PreState", "preState"])
            if not state:
                self._pre_state = STATE_DRYER_POWER_OFF
            else:
                self._pre_state = state
        return self._pre_state

    def _get_error(self):
        if not self._error:
            error = self.lookup_reference(["Error", "error"], ref_key="title")
            if not error:
                self._error = STATE_DRYER_ERROR_OFF
            else:
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
        if run_state in STATE_DRYER_END or (
            run_state == STATE_DRYER_POWER_OFF and pre_state in STATE_DRYER_END
        ):
            return True
        return False

    @property
    def is_error(self):
        if not self.is_on:
            return False
        error = self._get_error()
        if error in STATE_DRYER_ERROR_NO_ERROR or error == STATE_DRYER_ERROR_OFF:
            return False
        return True

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
    def run_state(self):
        run_state = self._get_run_state()
        if run_state == STATE_DRYER_POWER_OFF:
            run_state = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_RUN_STATE, run_state
        )

    @property
    def pre_state(self):
        pre_state = self._get_pre_state()
        if pre_state == STATE_DRYER_POWER_OFF:
            pre_state = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_PRE_STATE, pre_state
        )

    @property
    def temp_control_option_state(self):
        temp_control = self.lookup_enum(["TempControl", "tempControl", "temp"])
        if not temp_control:
            temp_control = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_TEMPCONTROL, temp_control
        )

    @property
    def dry_level_option_state(self):
        dry_level = self.lookup_enum(["DryLevel", "dryLevel"])
        if not dry_level:
            dry_level = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_DRYLEVEL, dry_level
        )

    @property
    def time_dry_option_state(self):
        """Get the time dry setting."""
        time_dry = self.lookup_enum("TimeDry")
        if not time_dry:
            time_dry = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_TIMEDRY, time_dry, False
        )

    @property
    def error_msg(self):
        if not self.is_error:
            error = STATE_OPTIONITEM_NONE
        else:
            error = self._get_error()
        return self._update_feature(
            FEAT_ERROR_MSG, error
        )

    @property
    def doorlock_state(self):
        status = self.lookup_bit(
            "doorLock" if self.is_info_v2 else "DoorLock"
        )
        return self._update_feature(
            FEAT_DOORLOCK, status, False
        )

    @property
    def childlock_state(self):
        status = self.lookup_bit(
            "childLock" if self.is_info_v2 else "ChildLock"
        )
        return self._update_feature(
            FEAT_CHILDLOCK, status, False
        )

    def _update_features(self):
        result = [
            self.run_state,
            self.pre_state,
            self.temp_control_option_state,
            self.dry_level_option_state,
            # self.time_dry_option_state,
            self.error_msg,
            self.doorlock_state,
            self.childlock_state,
        ]
