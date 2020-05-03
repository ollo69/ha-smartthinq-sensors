"""------------------for DishWasher"""
import logging
from typing import Optional

from .device import (
    Device,
    DeviceStatus,
    STATE_OPTIONITEM_NONE,
)

from .dishwasher_states import (
    STATE_DISHWASHER,
    STATE_DISHWASHER_PROCESS,
    STATE_DISHWASHER_ERROR,
    DISHWASHERSTATES,
    DISHWASHERPROCESS,
    DISHWASHERHALFLOAD,
    DISHWASHERERRORS,
)

_LOGGER = logging.getLogger(__name__)


class DishWasherDevice(Device):
    """A higher-level interface for a dishwasher."""
    def __init__(self, client, device):
        super().__init__(client, device, DishWasherStatus(self, None))

    def poll(self) -> Optional["DishWasherStatus"]:
        """Poll the device's current state."""

        res = self.device_poll("dishwasher")
        if not res:
            return None

        self._status = DishWasherStatus(self, res)
        return self._status


class DishWasherStatus(DeviceStatus):
    """Higher-level information about a dishwasher's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """
    def __init__(self, device, data):
        super().__init__(device, data)
        self._run_state = None
        self._process = None
        self._error = None

    def _get_run_state(self):
        if not self._run_state:
            state = self.lookup_enum(["State", "state"])
            if not state:
                return STATE_DISHWASHER.POWER_OFF
            self._run_state = self._set_unknown(
                state=DISHWASHERSTATES.get(state, None), key=state, type="state"
            )
        return self._run_state

    def _get_process(self):
        if not self._process:
            process = self.lookup_enum(["Process", "process"])
            if not process:
                return STATE_DISHWASHER_PROCESS.OFF
            self._process = self._set_unknown(
                state=DISHWASHERPROCESS.get(process, None), key=process, type="process"
            )
        return self._process

    def _get_error(self):
        if not self._error:
            error = self.lookup_reference(["Error", "error"], get_comment=False)
            if not error:
                return STATE_DISHWASHER_ERROR.OFF
            self._error = self._set_unknown(
                state=DISHWASHERERRORS.get(error, None), key=error, type="error_status"
            )
        return self._error

    @property
    def is_on(self):
        run_state = self._get_run_state()
        return run_state != STATE_DISHWASHER.POWER_OFF

    @property
    def is_run_completed(self):
        run_state = self._get_run_state()
        process = self._get_process()
        if run_state == STATE_DISHWASHER.COMPLETE or (
            run_state == STATE_DISHWASHER.POWER_OFF and process == STATE_DISHWASHER_PROCESS.COMPLETE
        ):
            return True
        return False

    @property
    def is_error(self):
        error = self._get_error()
        if error != STATE_DISHWASHER_ERROR.NO_ERROR and error != STATE_DISHWASHER_ERROR.OFF:
            return True
        return False

    @property
    def run_state(self):
        run_state = self._get_run_state()
        return run_state.value

    @property
    def process_state(self):
        process = self._get_process()
        return process.value

    @property
    def error_state(self):
        if not self.is_on:
            return STATE_OPTIONITEM_NONE
        error = self._get_error()
        return error.value

    @property
    def current_course(self):
        if self.is_info_v2:
            course_key = self._device.model_info.config_value(
                "courseType"
            )
        else:
            course_key = ["APCourse", "Course"]
        course = self.lookup_reference(course_key)
        return course

    @property
    def current_smartcourse(self):
        if self.is_info_v2:
            course_key = self._device.model_info.config_value(
                "smartCourseType"
            )
        else:
            course_key = "SmartCourse"
        smart_course = self.lookup_reference(course_key)
        return smart_course

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
    def halfload_state(self):
        if self.is_info_v2:
            half_load = self.lookup_bit_enum("halfLoad")
        else:
            half_load = self.lookup_bit_enum("HalfLoad")
        if not half_load:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=DISHWASHERHALFLOAD.get(half_load, None),
            key=half_load,
            type="HalfLoad",
        ).value

    @property
    def tubclean_count(self):
        if self.is_info_v2:
            result = DeviceStatus.int_or_none(self._data.get("tclCount"))
        else:
            result = self._data.get("TclCount")
        if result is None:
            return "N/A"
        return result

    @property
    def door_opened_state(self):
        if self.is_info_v2:
            return self.lookup_bit("door")
        return self.lookup_bit("Door")

    @property
    def childlock_state(self):
        if self.is_info_v2:
            return self.lookup_bit("childLock")
        return self.lookup_bit("ChildLock")

    @property
    def delaystart_state(self):
        if self.is_info_v2:
            return self.lookup_bit("delayStart")
        return self.lookup_bit("DelayStart")

    @property
    def energysaver_state(self):
        if self.is_info_v2:
            return self.lookup_bit("energySaver")
        return self.lookup_bit("EnergySaver")

    @property
    def dualzone_state(self):
        if self.is_info_v2:
            return self.lookup_bit("dualZone")
        return self.lookup_bit("DualZone")

    @property
    def rinserefill_state(self):
        if self.is_info_v2:
            return self.lookup_bit("rinseRefill")
        return self.lookup_bit("RinseRefill")

    @property
    def saltrefill_state(self):
        if self.is_info_v2:
            return self.lookup_bit("saltRefill")
        return self.lookup_bit("SaltRefill")
