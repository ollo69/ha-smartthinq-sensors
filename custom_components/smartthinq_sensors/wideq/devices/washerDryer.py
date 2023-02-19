"""------------------for Washer and Dryer"""
from __future__ import annotations

import asyncio
import base64
import json
import logging

from ..const import StateOptions, WashDeviceFeatures
from ..core_async import ClientAsync
from ..core_exceptions import InvalidDeviceStatus
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo, DeviceType

STATE_WM_POWER_OFF = "@WM_STATE_POWER_OFF_W"
STATE_WM_END = [
    "@WM_STATE_END_W",
    "@WM_STATE_COMPLETE_W",
]
STATE_WM_ERROR_OFF = "OFF"
STATE_WM_ERROR_NO_ERROR = [
    "ERROR_NOERROR",
    "ERROR_NOERROR_TITLE",
    "No Error",
    "No_Error",
]

WM_ROOT_DATA = "washerDryer"
WM_SUB_DEV = {"mini": "miniState"}

POWER_STATUS_KEY = ["State", "state"]

CMD_POWER_OFF = [["Control", "WMOff"], ["Power", "WMOff"], ["Off", None]]
CMD_WAKE_UP = [["Control", "WMWakeup"], ["Operation", "WMWakeup"], ["WakeUp", None]]
CMD_REMOTE_START = [
    ["Control", "WMStart"],
    ["OperationStart", "WMStart"],
    ["Start", "WMStart"],
]

BIT_FEATURES = {
    WashDeviceFeatures.ANTICREASE: ["AntiCrease", "antiCrease"],
    WashDeviceFeatures.CHILDLOCK: ["ChildLock", "childLock"],
    WashDeviceFeatures.CREASECARE: ["CreaseCare", "creaseCare"],
    WashDeviceFeatures.DAMPDRYBEEP: ["DampDryBeep", "dampDryBeep"],
    WashDeviceFeatures.DETERGENT: ["DetergentStatus", "ezDetergentState"],
    WashDeviceFeatures.DETERGENTLOW: ["DetergentRemaining", "detergentRemaining"],
    WashDeviceFeatures.DOORCLOSE: ["DoorClose", "doorClose"],
    WashDeviceFeatures.DOORLOCK: ["DoorLock", "doorLock"],
    WashDeviceFeatures.HANDIRON: ["HandIron", "handIron"],
    WashDeviceFeatures.MEDICRINSE: ["MedicRinse", "medicRinse"],
    WashDeviceFeatures.PREWASH: ["PreWash", "preWash"],
    WashDeviceFeatures.REMOTESTART: ["RemoteStart", "remoteStart"],
    WashDeviceFeatures.RESERVATION: ["Reservation", "reservation"],
    WashDeviceFeatures.SELFCLEAN: ["SelfClean", "selfClean"],
    WashDeviceFeatures.SOFTENER: ["SoftenerStatus", "ezSoftenerState"],
    WashDeviceFeatures.SOFTENERLOW: ["SoftenerRemaining", "softenerRemaining"],
    WashDeviceFeatures.STEAM: ["Steam", "steam"],
    WashDeviceFeatures.STEAMSOFTENER: ["SteamSoftener", "steamSoftener"],
    WashDeviceFeatures.TURBOWASH: ["TurboWash", "turboWash"],
}

_LOGGER = logging.getLogger(__name__)


def get_sub_devices(device_info: DeviceInfo) -> list[str]:
    """Search for valid sub devices and return related sub keys."""
    if not (snapshot := device_info.snapshot):
        return []
    if not (payload := snapshot.get(WM_ROOT_DATA)):
        return []
    return [k for k, s in WM_SUB_DEV.items() if s in payload]


class WMDevice(Device):
    """A higher-level interface for washer and dryer."""

    def __init__(
        self, client: ClientAsync, device_info: DeviceInfo, sub_key: str | None = None
    ):
        super().__init__(client, device_info, WMStatus(self))
        self._sub_key = sub_key
        if sub_key:
            self._attr_unique_id += f"-{sub_key}"
            self._attr_name += f" {sub_key.capitalize()}"
        self._stand_by = False
        self._remote_start_status = None

    def getkey(self, key: str | None) -> str | None:
        """Add subkey prefix to a key if required."""
        if not (key and self._sub_key):
            return key
        return f"{self._sub_key}{key[0].upper()}{key[1:]}"

    def _getcmdkey(self, key: str | None) -> str | None:
        """Add subkey prefix to a command key if required."""
        if not (key and self._sub_key):
            return key
        return f"{self._sub_key.capitalize()}{key}"

    def _update_status(self, key, value):
        if self._status:
            status_key = self._get_state_key(key)
            status_value = self.model_info.enum_value(status_key, value)
            if status_value:
                self._status.update_status(status_key, status_value)

    def _get_course_info(self, course_key, course_id):
        """Get definition for a specific course ID."""
        if course_key is None:
            return None
        return self.model_info.value(course_key).reference.get(course_id)

    def _update_course_info(self, data, course_id=None):
        """
        Save information in the data payload for a specific course
        or default course if not already available.
        """
        ret_data = data.copy()
        if self.model_info.is_info_v2:
            n_course_key = self.model_info.config_value(self.getkey("courseType"))
            s_course_key = self.model_info.config_value(self.getkey("smartCourseType"))
            def_course_id = self.model_info.config_value(
                f"default{self._getcmdkey('Course')}"
            )
        else:
            n_course_key = (
                "APCourse" if self.model_info.value_exist("APCourse") else "Course"
            )
            s_course_key = "SmartCourse"
            def_course_id = str(self.model_info.config_value("defaultCourseId"))
        if course_id is None:
            # check if this course is defined in data payload
            for course_key in [n_course_key, s_course_key]:
                course_id = str(data.get(course_key))
                if self._get_course_info(course_key, course_id):
                    return ret_data
            course_id = def_course_id

        # save information for specific or default course
        course_info = self._get_course_info(n_course_key, course_id)
        if course_info:
            ret_data[n_course_key] = course_id
            for func_key in course_info["function"]:
                key = func_key.get("value")
                data = func_key.get("default")
                if key and data:
                    ret_data[key] = data

        return ret_data

    def _prepare_command_v1(self, cmd, key):
        """Prepare command for specific ThinQ1 device."""
        if "data" in cmd:
            str_data = cmd["data"]
            status_data = self._update_course_info(self._remote_start_status)
            for dt_key, dt_value in status_data.items():
                # for start command we set initial bit to 1, assuming that
                # is the 1st bit of Option2. This probably should be reviewed
                # to use right address from model_info
                if key and key == "Start" and dt_key == "Option2":
                    dt_value = str(int(dt_value) | 1)
                str_data = str_data.replace(f"{{{{{dt_key}}}}}", dt_value)
            _LOGGER.debug("Command data content: %s", str_data)
            encode = cmd.pop("encode", False)
            if encode:
                cmd["format"] = "B64"
                str_list = json.loads(str_data)
                str_data = base64.b64encode(bytes(str_list)).decode("ascii")
            cmd["data"] = str_data
        return cmd

    def _prepare_command_v2(self, cmd, key: str):
        """Prepare command for specific ThinQ2 device."""
        data_set = cmd.pop("data", None)
        if not data_set:
            return cmd

        if key and key.find("WMStart") >= 0:
            status_data = self._update_course_info(self._remote_start_status)
            n_course_key = self.model_info.config_value(self.getkey("courseType"))
            s_course_key = self.model_info.config_value(self.getkey("smartCourseType"))
            cmd_data_set = {}

            for cmd_key, cmd_value in data_set[WM_ROOT_DATA].items():
                if cmd_key in ["course", "Course", "ApCourse", n_course_key]:
                    course_data = status_data.get(n_course_key, "NOT_SELECTED")
                    course_type = self.model_info.reference_name(
                        n_course_key, course_data, ref_key="courseType"
                    )
                    if course_type:
                        cmd_data_set[n_course_key] = course_data
                        cmd_data_set["courseType"] = course_type
                    else:
                        cmd_data_set[n_course_key] = "NOT_SELECTED"
                elif cmd_key in ["smartCourse", "SmartCourse", s_course_key]:
                    course_data = status_data.get(s_course_key, "NOT_SELECTED")
                    course_type = self.model_info.reference_name(
                        s_course_key, course_data, ref_key="courseType"
                    )
                    if course_type:
                        cmd_data_set[s_course_key] = course_data
                        cmd_data_set["courseType"] = course_type
                    else:
                        cmd_data_set[s_course_key] = "NOT_SELECTED"
                elif cmd_key == self.getkey("initialBit"):
                    cmd_data_set[cmd_key] = "INITIAL_BIT_ON"
                else:
                    cmd_data_set[cmd_key] = status_data.get(cmd_key, cmd_value)
            data_set[WM_ROOT_DATA] = cmd_data_set

        cmd["dataSetList"] = data_set

        return cmd

    def _prepare_command(self, ctrl_key, command, key, value):
        """Prepare command for specific device."""
        cmd = self.model_info.get_control_cmd(command, ctrl_key)
        if not cmd:
            return None

        if self.model_info.is_info_v2:
            return self._prepare_command_v2(cmd, key)
        return self._prepare_command_v1(cmd, key)

    @property
    def stand_by(self) -> bool:
        """Return if device is in standby mode."""
        return self._stand_by

    @property
    def remote_start_enabled(self) -> bool:
        """Return if remote start is enabled."""
        if not self._status.is_on:
            return False
        return self._remote_start_status is not None and not self._stand_by

    async def power_off(self):
        """Power off the device."""
        keys = self._get_cmd_keys(CMD_POWER_OFF)
        await self.set_with_retry(keys[0], keys[1], value=keys[2], num_retry=2)
        self._remote_start_status = None
        self._update_status(POWER_STATUS_KEY, STATE_WM_POWER_OFF)

    async def wake_up(self):
        """Wakeup the device."""
        if not self._stand_by:
            raise InvalidDeviceStatus()

        keys = self._get_cmd_keys(CMD_WAKE_UP)
        await self.set_with_retry(keys[0], keys[1], value=keys[2], num_retry=2)
        self._stand_by = False

    async def remote_start(self):
        """Remote start the device."""
        if not self.remote_start_enabled:
            raise InvalidDeviceStatus()

        keys = self._get_cmd_keys(CMD_REMOTE_START)
        await self.set_with_retry(keys[0], keys[1], key=keys[2], num_retry=2)

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            self._getcmdkey(ctrl_key),
            self._getcmdkey(command),
            key=self._getcmdkey(key),
            value=value,
            data=data,
            ctrl_path=ctrl_path,
        )

    async def set_with_retry(
        self,
        ctrl_key,
        command,
        *,
        key=None,
        value=None,
        data=None,
        ctrl_path=None,
        num_retry=1,
    ):
        """Set a device's control for `key` to `value` with retry."""
        if num_retry <= 0:
            num_retry = 1
        for i in range(num_retry):
            try:
                await self.set(
                    ctrl_key,
                    command,
                    key=key,
                    value=value,
                    data=data,
                    ctrl_path=ctrl_path,
                )
                return
            except Exception as exc:  # pylint: disable=broad-except
                if i == num_retry - 1:
                    raise
                _LOGGER.debug(
                    "Device %s, error executing command %s, tentative %s: %s",
                    self.name,
                    command,
                    i,
                    exc,
                )
            await asyncio.sleep(1)

    def reset_status(self):
        tcl_count = None
        if self._status:
            tcl_count = self._status.tubclean_count
        self._status = WMStatus(self, tcl_count=tcl_count)
        return self._status

    def _set_remote_start_opt(self, res):
        """Save the status to use for remote start."""
        standby_enable = self.model_info.config_value("standbyEnable")
        if standby_enable and not self._should_poll:
            self._stand_by = not self._status.is_on
        else:
            self._stand_by = (
                self._status.device_features.get(WashDeviceFeatures.STANDBY)
                == StateOptions.ON
            )
        remote_start = self._status.device_features.get(WashDeviceFeatures.REMOTESTART)
        if remote_start == StateOptions.ON:
            if self._remote_start_status is None:
                self._remote_start_status = res
        else:
            self._remote_start_status = None

    async def poll(self) -> WMStatus | None:
        """Poll the device's current state."""

        res = await self._device_poll(WM_ROOT_DATA)
        if not res:
            self._stand_by = False
            return None

        self._status = WMStatus(self, res)
        self._set_remote_start_opt(res)
        return self._status


class WMStatus(DeviceStatus):
    """
    Higher-level information about a WM current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(
        self,
        device: WMDevice,
        data: dict | None = None,
        *,
        tcl_count: str | None = None,
    ):
        """Initialize device status."""
        super().__init__(device, data)
        self._run_state = None
        self._pre_state = None
        self._process_state = None
        self._error = None
        self._tcl_count = tcl_count

    def _getkeys(self, keys: str | list[str]) -> str | list[str]:
        """Add subkey prefix to a key or a list of keys if required."""
        if isinstance(keys, list):
            return [self._device.getkey(key) for key in keys]
        return self._device.getkey(keys)

    def _get_run_state(self):
        """Get current run state."""
        if not self._run_state:
            state = self.lookup_enum(self._getkeys(POWER_STATUS_KEY))
            if not state:
                self._run_state = STATE_WM_POWER_OFF
            else:
                self._run_state = state
        return self._run_state

    def _get_pre_state(self):
        """Get previous run state."""
        if not self._pre_state:
            keys = self._getkeys(["PreState", "preState"])
            if not (key := self.get_model_info_key(keys)):
                return None
            state = self.lookup_enum(key)
            if not state:
                self._pre_state = STATE_WM_POWER_OFF
            else:
                self._pre_state = state
        return self._pre_state

    def _get_process_state(self):
        """Get current process state."""
        if not self._process_state:
            keys = self._getkeys(["ProcessState", "processState"])
            if not (key := self.get_model_info_key(keys)):
                return None
            state = self.lookup_enum(key)
            if not state:
                self._process_state = StateOptions.NONE
            else:
                self._process_state = state
        return self._process_state

    def _get_error(self):
        """Get current error."""
        if not self._error:
            keys = self._getkeys(["Error", "error"])
            error = self.lookup_reference(keys, ref_key="title")
            if not error:
                self._error = STATE_WM_ERROR_OFF
            else:
                self._error = error
        return self._error

    def update_status(self, key, value):
        """Update device status."""
        if not super().update_status(self._getkeys(key), value):
            return False
        self._run_state = None
        return True

    @property
    def is_on(self):
        """Return if device is on."""
        run_state = self._get_run_state()
        return run_state != STATE_WM_POWER_OFF

    @property
    def is_dryer(self):
        """Return if device is a dryer."""
        if self._device.device_info.type in [DeviceType.DRYER, DeviceType.TOWER_DRYER]:
            return True
        return False

    @property
    def is_run_completed(self):
        """Return if run is completed."""
        run_state = self._get_run_state()
        pre_state = self._get_pre_state()
        if pre_state is None:
            pre_state = self._get_process_state() or StateOptions.NONE
        if run_state in STATE_WM_END or (
            run_state == STATE_WM_POWER_OFF and pre_state in STATE_WM_END
        ):
            return True
        return False

    @property
    def is_error(self):
        """Return if an error is present."""
        if not self.is_on:
            return False
        error = self._get_error()
        if error in STATE_WM_ERROR_NO_ERROR or error == STATE_WM_ERROR_OFF:
            return False
        return True

    @property
    def current_course(self):
        """Return current course."""
        if self.is_info_v2:
            course_key = self._device.model_info.config_value(
                self._getkeys("courseType")
            )
        else:
            course_key = ["APCourse", "Course"]
        course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(course)

    @property
    def current_smartcourse(self):
        """Return current smartcourse."""
        if self.is_info_v2:
            course_key = self._device.model_info.config_value(
                self._getkeys("smartCourseType")
            )
        else:
            course_key = "SmartCourse"
        smart_course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(smart_course)

    @property
    def initialtime_hour(self):
        """Return hour initial time."""
        if self.is_info_v2:
            return self.int_or_none(self._data.get(self._getkeys("initialTimeHour")))
        return self._data.get("Initial_Time_H")

    @property
    def initialtime_min(self):
        """Return minute initial time."""
        if self.is_info_v2:
            return self.int_or_none(self._data.get(self._getkeys("initialTimeMinute")))
        return self._data.get("Initial_Time_M")

    @property
    def remaintime_hour(self):
        """Return hour remaining time."""
        if self.is_info_v2:
            return self.int_or_none(self._data.get(self._getkeys("remainTimeHour")))
        return self._data.get("Remain_Time_H")

    @property
    def remaintime_min(self):
        """Return minute remaining time."""
        if self.is_info_v2:
            return self.int_or_none(self._data.get(self._getkeys("remainTimeMinute")))
        return self._data.get("Remain_Time_M")

    @property
    def reservetime_hour(self):
        """Return hour reserved time."""
        if self.is_info_v2:
            return self.int_or_none(self._data.get(self._getkeys("reserveTimeHour")))
        return self._data.get("Reserve_Time_H")

    @property
    def reservetime_min(self):
        """Return minute reserved time."""
        if self.is_info_v2:
            return self.int_or_none(self._data.get(self._getkeys("reserveTimeMinute")))
        return self._data.get("Reserve_Time_M")

    @property
    def run_state(self):
        """Return current run state."""
        run_state = self._get_run_state()
        if run_state == STATE_WM_POWER_OFF:
            run_state = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.RUN_STATE, run_state)

    @property
    def pre_state(self):
        """Return previous run state."""
        pre_state = self._get_pre_state()
        if pre_state is None:
            return None
        if pre_state == STATE_WM_POWER_OFF:
            pre_state = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.PRE_STATE, pre_state)

    @property
    def process_state(self):
        """Return current process state."""
        process = self._get_process_state()
        if process is None:
            return None
        return self._update_feature(WashDeviceFeatures.PROCESS_STATE, process)

    @property
    def error_msg(self):
        """Return current error message."""
        if not self.is_error:
            error = StateOptions.NONE
        else:
            error = self._get_error()
        return self._update_feature(WashDeviceFeatures.ERROR_MSG, error)

    @property
    def spin_option_state(self):
        """Return spin option state."""
        keys = self._getkeys(["SpinSpeed", "spin"])
        if not (key := self.get_model_info_key(keys)):
            return None
        spin_speed = self.lookup_enum(key)
        if not spin_speed:
            spin_speed = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.SPINSPEED, spin_speed)

    @property
    def water_temp_option_state(self):
        """Return water temperature option state."""
        keys = self._getkeys(["WTemp", "WaterTemp", "temp"])
        if not (key := self.get_model_info_key(keys)):
            return None
        if self.key_exist("temp") and self.is_dryer:
            return None
        water_temp = self.lookup_enum(key)
        if not water_temp:
            water_temp = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.WATERTEMP, water_temp)

    @property
    def rinse_mode_option_state(self):
        """Return rinse mode option state."""
        keys = self._getkeys(["RinseOption", "rinse"])
        if not (key := self.get_model_info_key(keys)):
            return None
        rinse_mode = self.lookup_enum(key)
        if not rinse_mode:
            rinse_mode = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.RINSEMODE, rinse_mode)

    @property
    def dry_level_option_state(self):
        """Return dry level option state."""
        keys = self._getkeys(["DryLevel", "dryLevel"])
        if not (key := self.get_model_info_key(keys)):
            return None
        dry_level = self.lookup_enum(key)
        if not dry_level:
            dry_level = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.DRYLEVEL, dry_level)

    @property
    def temp_control_option_state(self):
        """Return temperature control option state."""
        keys = self._getkeys(["TempControl", "tempControl", "temp"])
        if not (key := self.get_model_info_key(keys)):
            return None
        if self.key_exist("temp") and not self.is_dryer:
            return None
        temp_control = self.lookup_enum(key)
        if not temp_control:
            temp_control = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.TEMPCONTROL, temp_control)

    @property
    def time_dry_option_state(self):
        """Return time dry option state."""
        keys = self._getkeys("TimeDry")
        if not (key := self.get_model_info_key(keys)):
            return None
        time_dry = self.lookup_enum(key)
        if not time_dry:
            time_dry = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.TIMEDRY, time_dry, False)

    @property
    def eco_hybrid_option_state(self):
        """Return eco hybrid option state."""
        keys = self._getkeys(["EcoHybrid", "ecoHybrid"])
        if not (key := self.get_model_info_key(keys)):
            return None
        eco_hybrid = self.lookup_enum(key)
        if not eco_hybrid:
            eco_hybrid = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.ECOHYBRID, eco_hybrid)

    @property
    def tubclean_count(self):
        """Return tub clean counter."""
        key = self._getkeys("TCLCount")
        if self.is_info_v2:
            if (result := self.int_or_none(self._data.get(key))) is None:
                return None
        else:
            if not self.get_model_info_key(key):
                return None
            result = self._data.get(key)
            if result is None:
                result = self._tcl_count or "N/A"
        return self._update_feature(WashDeviceFeatures.TUBCLEAN_COUNT, result, False)

    @property
    def standby_state(self):
        """Return standby state."""
        keys = self._getkeys(["Standby", "standby"])
        if not (key := self.get_model_info_key(keys)):
            return None
        status = self.lookup_enum(key)
        if not status:
            status = StateOptions.OFF
        return self._update_feature(WashDeviceFeatures.STANDBY, status)

    def _update_bit_features(self):
        """Update features related to bit status."""
        index = 1 if self.is_info_v2 else 0
        for feature, keys in BIT_FEATURES.items():
            status = self.lookup_bit(self._getkeys(keys[index]))
            self._update_feature(feature, status, False)

    def _update_features(self):
        _ = [
            self.run_state,
            self.pre_state,
            self.process_state,
            self.error_msg,
            self.spin_option_state,
            self.water_temp_option_state,
            self.rinse_mode_option_state,
            self.dry_level_option_state,
            self.temp_control_option_state,
            # self.time_dry_option_state,
            self.eco_hybrid_option_state,
            self.tubclean_count,
            self.standby_state,
        ]
        self._update_bit_features()
