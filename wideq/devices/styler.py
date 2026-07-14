"""------------------for Styler"""

from __future__ import annotations

from ..const import StateOptions, WashDeviceFeatures
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

STATE_STYLER_POWER_OFF = "STATE_POWER_OFF"
STATE_STYLER_END = ["STATE_END", "STATE_COMPLETE"]
STATE_STYLER_ERROR_OFF = "OFF"
STATE_STYLER_ERROR_NO_ERROR = [
    "ERROR_NOERROR",
    "ERROR_NOERROR_TITLE",
    "No Error",
    "No_Error",
]

BIT_FEATURES = {
    WashDeviceFeatures.CHILDLOCK: ["ChildLock", "childLock"],
    WashDeviceFeatures.NIGHTDRY: ["NightDry", "nightDry"],
    WashDeviceFeatures.REMOTESTART: ["RemoteStart", "remoteStart"],
}


class StylerDevice(Device):
    """A higher-level interface for a styler."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        super().__init__(client, device_info, StylerStatus(self))

    @property
    def is_run_completed(self) -> bool:
        """Return device run completed state."""
        return self._status.is_run_completed if self._status else False

    def reset_status(self):
        self._status = StylerStatus(self)
        return self._status

    async def poll(self) -> StylerStatus | None:
        """Poll the device's current state."""

        res = await self._device_poll("styler")
        if not res:
            return None

        self._status = StylerStatus(self, res)
        return self._status


class StylerStatus(DeviceStatus):
    """
    Higher-level information about a styler's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    _device: StylerDevice

    def __init__(self, device: StylerDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._run_state = None
        self._pre_state = None
        self._error = None

    def _get_run_state(self):
        """Get current run state."""
        if not self._run_state:
            state = self.lookup_enum(["State", "state"])
            if not state:
                self._run_state = STATE_STYLER_POWER_OFF
            else:
                self._run_state = state
        return self._run_state

    def _get_pre_state(self):
        """Get previous run state."""
        if not self._pre_state:
            state = self.lookup_enum(["PreState", "preState"])
            if not state:
                self._pre_state = STATE_STYLER_POWER_OFF
            else:
                self._pre_state = state
        return self._pre_state

    def _get_error(self):
        """Get current error."""
        if not self._error:
            error = self.lookup_reference(["Error", "error"], ref_key="title")
            if not error:
                self._error = STATE_STYLER_ERROR_OFF
            else:
                self._error = error
        return self._error

    def update_status(self, key, value):
        """Update device status."""
        if not super().update_status(key, value):
            return False
        self._run_state = None
        return True

    @property
    def is_on(self):
        """Return if device is on."""
        run_state = self._get_run_state()
        return STATE_STYLER_POWER_OFF not in run_state

    @property
    def is_run_completed(self):
        """Return if run is completed."""
        run_state = self._get_run_state()
        pre_state = self._get_pre_state()
        if any(state in run_state for state in STATE_STYLER_END) or (
            STATE_STYLER_POWER_OFF in run_state
            and any(state in pre_state for state in STATE_STYLER_END)
        ):
            return True
        return False

    @property
    def is_error(self):
        """Return if an error is present."""
        if not self.is_on:
            return False
        error = self._get_error()
        if error in STATE_STYLER_ERROR_NO_ERROR or error == STATE_STYLER_ERROR_OFF:
            return False
        return True

    @property
    def current_course(self):
        """Return current course."""
        if self.is_info_v2:
            course_key = self._device.model_info.config_value("courseType")
        else:
            course_key = ["APCourse", "Course"]
        course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(course)

    @property
    def current_smartcourse(self):
        """Return current smartcourse."""
        if self.is_info_v2:
            course_key = self._device.model_info.config_value("smartCourseType")
        else:
            course_key = "SmartCourse"
        smart_course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(smart_course)

    def _get_time_info(self, keys: list[str]):
        """Return time info for specific key."""
        if self.is_info_v2:
            if not self.is_on:
                return 0
            return self.int_or_none(self._data.get(keys[1]))
        return self._data.get(keys[0])

    @property
    def initialtime_hour(self):
        """Return hour initial time."""
        return self._get_time_info(["Initial_Time_H", "initialTimeHour"])

    @property
    def initialtime_min(self):
        """Return minute initial time."""
        return self._get_time_info(["Initial_Time_M", "initialTimeMinute"])

    @property
    def remaintime_hour(self):
        """Return hour remaining time."""
        return self._get_time_info(["Remain_Time_H", "remainTimeHour"])

    @property
    def remaintime_min(self):
        """Return minute remaining time."""
        return self._get_time_info(["Remain_Time_M", "remainTimeMinute"])

    @property
    def reservetime_hour(self):
        """Return hour reserved time."""
        return self._get_time_info(["Reserve_Time_H", "reserveTimeHour"])

    @property
    def reservetime_min(self):
        """Return minute reserved time."""
        return self._get_time_info(["Reserve_Time_M", "reserveTimeMinute"])

    @property
    def run_state(self):
        """Return current run state."""
        run_state = self._get_run_state()
        if STATE_STYLER_POWER_OFF in run_state:
            run_state = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.RUN_STATE, run_state)

    @property
    def pre_state(self):
        """Return previous run state."""
        pre_state = self._get_pre_state()
        if STATE_STYLER_POWER_OFF in pre_state:
            pre_state = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.PRE_STATE, pre_state)

    @property
    def error_msg(self):
        """Return current error message."""
        if not self.is_error:
            error = StateOptions.NONE
        else:
            error = self._get_error()
        return self._update_feature(WashDeviceFeatures.ERROR_MSG, error)

    def _update_bit_features(self):
        """Update features related to bit status."""
        index = 1 if self.is_info_v2 else 0
        for feature, keys in BIT_FEATURES.items():
            status = self.lookup_bit(keys[index])
            self._update_feature(feature, status, False)

    def _update_features(self):
        _ = [
            self.run_state,
            self.pre_state,
            self.error_msg,
        ]
        self._update_bit_features()
