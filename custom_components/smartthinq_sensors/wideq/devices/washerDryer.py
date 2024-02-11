"""------------------for Washer and Dryer"""

from __future__ import annotations

import base64
import json
import logging

from ..backports.functools import cached_property
from ..const import StateOptions, WashDeviceFeatures
from ..core_async import ClientAsync
from ..core_exceptions import InvalidDeviceStatus
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo, DeviceType

STATE_WM_POWER_OFF = "STATE_POWER_OFF"
STATE_WM_INITIAL = "STATE_INITIAL"
STATE_WM_PAUSE = "STATE_PAUSE"
STATE_WM_END = ["STATE_END", "STATE_COMPLETE"]
STATE_WM_ERROR_OFF = "OFF"
STATE_WM_ERROR_NO_ERROR = [
    "ERROR_NOERROR",
    "ERROR_NOERROR_TITLE",
    "No Error",
    "No_Error",
]

WM_ROOT_DATA = "washerDryer"
WM_SUB_KEYS = {"mini": "miniState", "Sub": "SubState"}

POWER_STATUS_KEY = ["State", "state"]

CMD_POWER_OFF = [[None, "WMControl"], ["PowerOff", "WMOff"], [None, None]]
CMD_WAKE_UP = [[None, "WMWakeup"], ["OperationWakeUp", "WMWakeup"], [None, None]]
CMD_PAUSE = [[None, "WMControl"], ["OperationStop", "WMStop"], [None, None]]
CMD_REMOTE_START = [
    [None, "WMStart"],
    ["OperationStart", "WMStart"],
    ["Start", "WMStart"],
]

VT_CTRL_CMD = {
    "WMOff": [{"cmd": "power", "type": "ABSOLUTE", "value": "POWER_OFF"}],
    "WMWakeup": [{"cmd": "power", "type": "ABSOLUTE", "value": "POWER_ON"}],
    "WMStop": [{"cmd": "wmControl", "type": "ABSOLUTE", "value": "PAUSE"}],
    "WMStart": [{"cmd": "wmControl", "type": "ABSOLUTE", "value": "START"}],
}

BIT_FEATURES = {
    WashDeviceFeatures.ANTICREASE: ["AntiCrease", "antiCrease"],
    WashDeviceFeatures.CHILDLOCK: ["ChildLock", "childLock"],
    WashDeviceFeatures.CREASECARE: ["CreaseCare", "creaseCare"],
    WashDeviceFeatures.DAMPDRYBEEP: ["DampDryBeep", "dampDryBeep"],
    WashDeviceFeatures.DETERGENT: ["DetergentStatus", "ezDetergentState"],
    WashDeviceFeatures.DETERGENTLOW: ["DetergentRemaining", "detergentRemaining"],
    WashDeviceFeatures.DOOROPEN: ["DoorClose", "doorClose"],
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

INVERTED_BITS = [WashDeviceFeatures.DOOROPEN]

_LOGGER = logging.getLogger(__name__)


class WMDevice(Device):
    """A higher-level interface for washer and dryer."""

    def __init__(
        self,
        client: ClientAsync,
        device_info: DeviceInfo,
        *,
        sub_device: str | None = None,
        sub_key: str | None = None,
    ):
        super().__init__(client, device_info, WMStatus(self), sub_device=sub_device)
        self._sub_key = sub_key
        if sub_key:
            self._attr_unique_id += f"-{sub_key}"
            self._attr_name += f" {sub_key.capitalize()}"
        self._subkey_device = None
        self._internal_state = None
        self._stand_by = False
        self._remote_start_status = None
        self._remote_start_pressed = False
        self._power_on_available: bool = None
        self._initial_bit_start = False

    @cached_property
    def _state_power_off(self):
        """Return native value for power off state."""
        return self._get_runstate_key(STATE_WM_POWER_OFF)

    @cached_property
    def _state_power_on_init(self):
        """Return native value for power on init state."""
        return self._get_runstate_key(STATE_WM_INITIAL)

    @cached_property
    def _state_pause(self):
        """Return native value for pause state."""
        return self._get_runstate_key(STATE_WM_PAUSE)

    @property
    def sub_key(self) -> str | None:
        """Return device sub key."""
        return self._sub_key

    @property
    def subkey_device(self) -> Device | None:
        """Return the available sub key device."""
        return self._subkey_device

    async def init_device_info(self) -> bool:
        """Initialize the information for the device"""
        if result := await super().init_device_info():
            self._init_subkey_device()
        return result

    def _init_subkey_device(self) -> None:
        """Initialize the available sub key device."""
        if self._sub_key or self._subkey_device or not self.model_info:
            return
        for key, val in WM_SUB_KEYS.items():
            if self.model_info.value_exist(val):
                # we check for value in the snapshot if available
                if snapshot := self.device_info.snapshot:
                    if payload := snapshot.get(self._sub_device or WM_ROOT_DATA):
                        if val not in payload:
                            continue
                self._subkey_device = WMDevice(
                    self.client,
                    self.device_info,
                    sub_device=self._sub_device,
                    sub_key=key,
                )
                return

    def update_internal_state(self, state):
        """Update internal state used by sub key device."""
        if not self._sub_key:
            return
        self._internal_state = state

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
        if self._status and value:
            self._status.update_status(key, value)

    def _update_opt_bit(self, opt_name: str, opt_val: str, bit_name: str, bit_val: int):
        """Update the option bit with correct value."""
        if self.model_info.is_info_v2:
            return None

        option_val = int(opt_val)
        if (bit_index := self.model_info.bit_index(opt_name, bit_name)) is not None:
            if bit_val:
                new_val = option_val | (2**bit_index)
            else:
                new_val = option_val ^ (option_val & (2**bit_index))
            return str(new_val)

        return None

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
        if not data:
            return {}

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

        # Prepare the course data initializing option for infoV1 device
        ret_data = data.copy()
        option_keys = self.model_info.option_keys(self._sub_key)
        if not self.model_info.is_info_v2:
            for opt_name in option_keys:
                ret_data[opt_name] = data.get(opt_name, "0")

        # Search valid course Info
        course_info = None
        course_set = False
        if course_id is None:
            # check if this course is defined in data payload
            for course_key in [n_course_key, s_course_key]:
                course_id = str(ret_data.get(course_key))
                if course_info := self._get_course_info(course_key, course_id):
                    course_set = True
                    break
        else:
            course_info = self._get_course_info(n_course_key, course_id)

        if not course_info:
            course_id = def_course_id
            course_info = self._get_course_info(n_course_key, course_id)

        # Save information for specific or default course
        if course_info:
            if not course_set:
                ret_data[n_course_key] = course_id
            for func_key in course_info["function"]:
                key = func_key.get("value")
                data = func_key.get("default")
                opt_set = False
                for opt_name in option_keys:
                    if opt_name not in ret_data:
                        continue
                    opt_val = ret_data[opt_name]
                    new_val = self._update_opt_bit(opt_name, opt_val, key, int(data))
                    if new_val is not None:
                        opt_set = True
                        if not course_set:
                            ret_data[opt_name] = new_val
                        break
                if opt_set or (course_set and key in ret_data):
                    continue
                if key and data:
                    ret_data[key] = data

        return ret_data

    def _prepare_command_v1(self, cmd, key):
        """Prepare command for specific ThinQ1 device."""
        encode = cmd.pop("encode", False)

        str_data = ""
        if "data" in cmd:
            str_data = cmd["data"]
            option_keys = self.model_info.option_keys(self._sub_key)
            status_data = self._update_course_info(self._remote_start_status)

            for dt_key, dt_value in status_data.items():
                repl_key = f"{{{{{dt_key}}}}}"
                if repl_key not in str_data:
                    continue
                # for start command we set initial bit to 1
                if key and key == "Start" and dt_key in option_keys:
                    bit_val = 1 if self._initial_bit_start else 0
                    new_value = self._update_opt_bit(
                        dt_key, dt_value, "InitialBit", bit_val
                    )
                    if new_value is not None:
                        dt_value = new_value
                str_data = str_data.replace(repl_key, dt_value)
            _LOGGER.debug("Command data content: %s", str_data)
            if encode:
                cmd["format"] = "B64"
                str_list = json.loads(str_data)
                str_data = base64.b64encode(bytes(str_list)).decode("ascii")

        return {**cmd, "data": str_data}

    def _prepare_command_v2(self, cmd, key: str):
        """Prepare command for specific ThinQ2 device."""
        data_set = cmd.pop("data", None)
        if not data_set:
            return cmd

        res_data_set = None
        if key and key.find("WMStart") >= 0 and WM_ROOT_DATA in data_set:
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
                    if self._initial_bit_start:
                        cmd_data_set[cmd_key] = "INITIAL_BIT_ON"
                    else:
                        cmd_data_set[cmd_key] = "INITIAL_BIT_OFF"
                else:
                    cmd_data_set[cmd_key] = status_data.get(cmd_key, cmd_value)
            res_data_set = {WM_ROOT_DATA: cmd_data_set}

        return {
            **cmd,
            "dataKey": None,
            "dataValue": None,
            "dataSetList": res_data_set or data_set,
            "dataGetList": None,
        }

    def _prepare_command_vtctrl(self, cmd: dict, command: str):
        """Prepare vtCtrl command for specific ThinQ2 device."""
        data_set: dict = cmd.pop("data", None)
        if not data_set:
            return cmd

        cmd_data_set = {}
        ctrl_target = None if not self._sub_device else self._sub_device.upper()
        for cmd_key, cmd_val in data_set.items():
            if cmd_key == "ctrlTarget":
                cmd_data_set[cmd_key] = [ctrl_target] if ctrl_target else cmd_val
            elif cmd_key == "reqDevType":
                cmd_data_set[cmd_key] = "APP"
            elif cmd_key == "vtData":
                vt_data = {}
                for dt_key in cmd_val.keys():
                    vt_data[ctrl_target or dt_key] = VT_CTRL_CMD[command]
                cmd_data_set[cmd_key] = vt_data
            else:
                cmd_data_set[cmd_key] = cmd_val

        return {
            **cmd,
            "dataKey": None,
            "dataValue": None,
            "dataSetList": cmd_data_set,
            "dataGetList": None,
        }

    def _prepare_command(self, ctrl_key, command, key, value):
        """Prepare command for specific device."""
        cmd = None
        vt_ctrl = True
        if command in VT_CTRL_CMD:
            cmd = self.model_info.get_control_cmd("vtCtrl", "vtCtrl")
        if not cmd:
            vt_ctrl = False
            cmd = self.model_info.get_control_cmd(command, ctrl_key)

        if not cmd:
            return None

        if self.model_info.is_info_v2:
            if vt_ctrl:
                return self._prepare_command_vtctrl(cmd, command)
            return self._prepare_command_v2(cmd, key)
        return self._prepare_command_v1(cmd, key)

    def _get_runstate_key(self, state_name: str) -> str | None:
        """Return the run state key based on state name."""
        key = self.getkey(self._get_state_key(POWER_STATUS_KEY))
        if not self.model_info.is_enum_type(key):
            return None
        mapping = self.model_info.value(key).options
        for key, val in mapping.items():
            if state_name in val:
                return key
        return None

    @property
    def stand_by(self) -> bool:
        """Return if device is in standby mode."""
        return self._stand_by

    @property
    def remote_start_enabled(self) -> bool:
        """Return if remote start is enabled."""
        if self._remote_start_pressed:
            self._remote_start_pressed = False
            return False
        if not self._status.is_on:
            return False
        if self._remote_start_status is None or self._stand_by:
            return False
        if self._status.internal_run_state in [
            self._state_power_on_init,
            self._state_pause,
        ]:
            self._initial_bit_start = (
                self._status.internal_run_state == self._state_power_on_init
            )
            return True
        return False

    @property
    def pause_enabled(self) -> bool:
        """Return if pause is enabled."""
        if not self._status.is_on:
            return False
        if self._remote_start_status is None or self._stand_by:
            return False
        if self._status.internal_run_state not in [
            self._state_power_on_init,
            self._state_pause,
        ]:
            return True
        return False

    async def power_off(self):
        """Power off the device."""
        keys = self._get_cmd_keys(CMD_POWER_OFF)
        await self.set(keys[0], keys[1])
        self._remote_start_status = None
        self._update_status(POWER_STATUS_KEY, self._state_power_off)

    async def wake_up(self):
        """Wakeup the device."""
        if not self._stand_by:
            raise InvalidDeviceStatus()

        keys = self._get_cmd_keys(CMD_WAKE_UP)
        await self.set(keys[0], keys[1])
        self._stand_by = False
        self._update_status(POWER_STATUS_KEY, self._state_power_on_init)

    async def remote_start(self):
        """Remote start the device."""
        if not self.remote_start_enabled:
            raise InvalidDeviceStatus()

        keys = self._get_cmd_keys(CMD_REMOTE_START)
        await self.set(keys[0], keys[1], key=keys[2])
        self._remote_start_pressed = True

    async def pause(self):
        """Pause the device."""
        if not self.pause_enabled:
            raise InvalidDeviceStatus()

        keys = self._get_cmd_keys(CMD_PAUSE)
        await self.set(keys[0], keys[1])
        self._update_status(POWER_STATUS_KEY, self._state_pause)

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            self._getcmdkey(ctrl_key),
            self._getcmdkey(command),
            key=key,
            value=value,
            data=data,
            ctrl_path=ctrl_path,
        )

    def reset_status(self):
        tcl_count = None
        if self._status:
            tcl_count = self._status.tubclean_count
        self._status = WMStatus(self, tcl_count=tcl_count)
        return self._status

    def _set_remote_start_opt(self, res):
        """Save the status to use for remote start."""
        if self._power_on_available is None:
            if self.model_info.config_value("powerOnButtonAvailable"):
                self._power_on_available = True
            else:
                self._power_on_available = False

        if self._power_on_available:
            self._stand_by = not self._status.is_on
        else:
            stand_by = self._status.device_features.get(WashDeviceFeatures.STANDBY)
            if stand_by is None:
                standby_enable = self.model_info.config_value("standbyEnable")
                if standby_enable and not self._should_poll and not self._sub_key:
                    self._stand_by = not self._status.is_on
                else:
                    self._stand_by = False
            else:
                self._stand_by = stand_by == StateOptions.ON

        remote_start = self._status.device_features.get(WashDeviceFeatures.REMOTESTART)
        if remote_start == StateOptions.ON:
            if self._remote_start_status is None:
                self._remote_start_status = res
        else:
            self._remote_start_status = None

    async def poll(self) -> WMStatus | None:
        """Poll the device's current state."""

        if not self._sub_key:
            res = await self._device_poll(self._sub_device or WM_ROOT_DATA)
            if self._subkey_device:
                self._subkey_device.update_internal_state(res)
        else:
            res = self._internal_state

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

    _device: WMDevice

    def __init__(
        self,
        device: WMDevice,
        data: dict | None = None,
        *,
        tcl_count: str | None = None,
    ):
        """Initialize device status."""
        super().__init__(device, data)
        self._internal_run_state = None
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
            curr_key = self._get_data_key(self._getkeys(POWER_STATUS_KEY))
            state = self.lookup_enum(curr_key)
            if not state:
                self._internal_run_state = None
                self._run_state = STATE_WM_POWER_OFF
            else:
                self._internal_run_state = self._data[curr_key]
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
            if (error := self.lookup_enum(keys)) is None:
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
    def internal_run_state(self):
        """Return internal representation for run state."""
        self._get_run_state()
        return self._internal_run_state

    @property
    def is_on(self):
        """Return if device is on."""
        run_state = self._get_run_state()
        return STATE_WM_POWER_OFF not in run_state

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
        if any(state in run_state for state in STATE_WM_END) or (
            STATE_WM_POWER_OFF in run_state
            and any(state in pre_state for state in STATE_WM_END)
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

    def _get_time_info(self, keys: list[str]):
        """Return time info for specific key."""
        if self.is_info_v2:
            if not self.is_on:
                return 0
            return self.int_or_none(self._data.get(self._getkeys(keys[1])))
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
        if STATE_WM_POWER_OFF in run_state:
            run_state = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.RUN_STATE, run_state)

    @property
    def pre_state(self):
        """Return previous run state."""
        pre_state = self._get_pre_state()
        if pre_state is None:
            return None
        if STATE_WM_POWER_OFF in pre_state:
            pre_state = StateOptions.NONE
        return self._update_feature(WashDeviceFeatures.PRE_STATE, pre_state)

    @property
    def process_state(self):
        """Return current process state."""
        process = self._get_process_state()
        if process is None:
            return None
        if not self.is_on:
            process = StateOptions.NONE
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
        status = None
        keys = self._getkeys(["Standby", "standby"])
        if key := self.get_model_info_key(keys):
            status = self.lookup_enum(key)
        if not status and not self.is_info_v2:
            status = self.lookup_bit(keys[0], sub_key=self._device.sub_key)
        if not (status or key):
            return None
        if not status:
            status = StateOptions.OFF
        return self._update_feature(WashDeviceFeatures.STANDBY, status)

    def _update_bit_features(self):
        """Update features related to bit status."""
        index = 1 if self.is_info_v2 else 0
        for feature, keys in BIT_FEATURES.items():
            invert = feature in INVERTED_BITS
            status = self.lookup_bit(
                self._getkeys(keys[index]), sub_key=self._device.sub_key, invert=invert
            )
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
