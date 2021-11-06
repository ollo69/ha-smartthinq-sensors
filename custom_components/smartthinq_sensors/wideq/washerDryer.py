"""------------------for Washer and Dryer"""
import base64
import json
import logging
from typing import Optional

from . import (
    FEAT_ANTICREASE,
    FEAT_CHILDLOCK,
    FEAT_CREASECARE,
    FEAT_DAMPDRYBEEP,
    FEAT_DOORCLOSE,
    FEAT_DOORLOCK,
    FEAT_DRYLEVEL,
    FEAT_ECOHYBRID,
    FEAT_ERROR_MSG,
    FEAT_HANDIRON,
    FEAT_MEDICRINSE,
    FEAT_PRE_STATE,
    FEAT_PROCESS_STATE,
    FEAT_PREWASH,
    FEAT_REMOTESTART,
    FEAT_RESERVATION,
    FEAT_RUN_STATE,
    FEAT_SELFCLEAN,
    FEAT_SPINSPEED,
    FEAT_STANDBY,
    FEAT_STEAM,
    FEAT_STEAMSOFTENER,
    FEAT_TEMPCONTROL,
    FEAT_TIMEDRY,
    FEAT_TUBCLEAN_COUNT,
    FEAT_TURBOWASH,
    FEAT_WATERTEMP,
)

from .device import (
    Device,
    DeviceStatus,
    DeviceType,
    STATE_OPTIONITEM_NONE,
    STATE_OPTIONITEM_OFF,
    STATE_OPTIONITEM_ON,
)

from .core_exceptions import InvalidDeviceStatus

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

POWER_STATUS_KEY = ["State", "state"]
REMOTE_START_KEY = ["RemoteStart", "remoteStart"]

CMD_POWER_OFF = [["Control", "WMControl"], ["Power", "WMOff"], ["Off", None]]
CMD_WAKE_UP = [["Control", "WMWakeup"], ["Operation", "WMWakeup"], ["WakeUp", None]]
CMD_REMOTE_START = [["Control", "WMStart"], ["OperationStart", "WMStart"], ["Start", "WMStart"]]

_LOGGER = logging.getLogger(__name__)


class WMDevice(Device):
    """A higher-level interface for washer and dryer."""
    def __init__(self, client, device):
        super().__init__(client, device, WMStatus(self, None))
        self._remote_start_status = None

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
        if self.model_info.is_info_v2:
            return self.model_info.data_root(course_key).get(course_id)
        return self.model_info.value(course_key).reference.get(course_id)

    def _update_course_info(self, data, course_id=None):
        """Save information in the data payload for a specific course
        or default course if not already available.
        """
        ret_data = data.copy()
        if self.model_info.is_info_v2:
            n_course_key = self.model_info.config_value("courseType")
            s_course_key = self.model_info.config_value("smartCourseType")
            def_course_id = self.model_info.config_value("defaultCourse")
        else:
            n_course_key = "APCourse" if self.model_info.value_exist("APCourse") else "Course"
            s_course_key = "SmartCourse"
            def_course_id = str(self.model_info.config_value("defaultCourseId"))
        if course_id is None:
            # check if course is defined in data payload
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

    def _prepare_command_v1(self, cmd, key, value):
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

    def _prepare_command_v2(self, cmd, key, value):
        """Prepare command for specific ThinQ2 device."""
        data_set = cmd.pop("data", None)
        if not data_set:
            return cmd

        if key and key == "WMStart":
            status_data = self._update_course_info(self._remote_start_status)
            n_course_key = self.model_info.config_value("courseType")
            s_course_key = self.model_info.config_value("smartCourseType")
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
                elif cmd_key == "initialBit":
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
            return self._prepare_command_v2(cmd, key, value)
        return self._prepare_command_v1(cmd, key, value)

    def power_off(self):
        """Power off the device."""
        keys = self._get_cmd_keys(CMD_POWER_OFF)
        self.set(keys[0], keys[1], value=keys[2])
        self._update_status(POWER_STATUS_KEY, STATE_WM_POWER_OFF)

    def wake_up(self):
        """Wakeup the device."""
        keys = self._get_cmd_keys(CMD_WAKE_UP)
        self.set(keys[0], keys[1], value=keys[2])

    def remote_start(self):
        """Remote start the device."""
        if not self._remote_start_status:
            raise InvalidDeviceStatus()

        keys = self._get_cmd_keys(CMD_REMOTE_START)
        self.set(keys[0], keys[1], key=keys[2])

    def reset_status(self):
        self._status = WMStatus(self, None)
        return self._status

    def _set_remote_start_opt(self, res):
        """Save the status to use for remote start."""

        status_key = self._get_state_key(REMOTE_START_KEY)
        remote_enabled = self._status.lookup_bit(status_key) == STATE_OPTIONITEM_ON
        if not self._remote_start_status:
            if remote_enabled:
                self._remote_start_status = res
        elif not remote_enabled:
            self._remote_start_status = None

    def poll(self) -> Optional["WMStatus"]:
        """Poll the device's current state."""

        res = self.device_poll(WM_ROOT_DATA)
        if not res:
            return None

        self._status = WMStatus(self, res)
        self._set_remote_start_opt(res)
        return self._status


class WMStatus(DeviceStatus):
    """Higher-level information about a WM current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """
    def __init__(self, device, data):
        super().__init__(device, data)
        self._run_state = None
        self._pre_state = None
        self._process_state = None
        self._error = None

    def _get_run_state(self):
        if not self._run_state:
            state = self.lookup_enum(POWER_STATUS_KEY)
            if not state:
                self._run_state = STATE_WM_POWER_OFF
            else:
                self._run_state = state
        return self._run_state

    def _get_pre_state(self):
        if not self._pre_state:
            if not self.key_exist(["PreState", "preState"]):
                return None
            state = self.lookup_enum(["PreState", "preState"])
            if not state:
                self._pre_state = STATE_WM_POWER_OFF
            else:
                self._pre_state = state
        return self._pre_state

    def _get_process_state(self):
        if not self._process_state:
            if not self.key_exist(["ProcessState", "processState"]):
                return None
            state = self.lookup_enum(["ProcessState", "processState"])
            if not state:
                self._process_state = STATE_OPTIONITEM_NONE
            else:
                self._process_state = state
        return self._process_state

    def _get_error(self):
        if not self._error:
            error = self.lookup_reference(["Error", "error"], ref_key="title")
            if not error:
                self._error = STATE_WM_ERROR_OFF
            else:
                self._error = error
        return self._error

    def update_status(self, key, value, upd_features=False):
        if not super().update_status(key, value):
            return False
        self._run_state = None
        if upd_features:
            self._update_features()
        return True

    @property
    def is_on(self):
        run_state = self._get_run_state()
        return run_state != STATE_WM_POWER_OFF

    @property
    def is_dryer(self):
        if self._device.device_info.type in [DeviceType.DRYER, DeviceType.TOWER_DRYER]:
            return True
        return False

    @property
    def is_run_completed(self):
        run_state = self._get_run_state()
        pre_state = self._get_pre_state()
        if pre_state is None:
            pre_state = self._get_process_state() or STATE_OPTIONITEM_NONE
        if run_state in STATE_WM_END or (
            run_state == STATE_WM_POWER_OFF and pre_state in STATE_WM_END
        ):
            return True
        return False

    @property
    def is_error(self):
        if not self.is_on:
            return False
        error = self._get_error()
        if error in STATE_WM_ERROR_NO_ERROR or error == STATE_WM_ERROR_OFF:
            return False
        return True

    @property
    def current_course(self):
        if self.is_info_v2:
            course_key = self._device.model_info.config_value("courseType")
        else:
            course_key = ["APCourse", "Course"]
        course = self.lookup_reference(course_key, ref_key="name")
        return self._device.get_enum_text(course)

    @property
    def current_smartcourse(self):
        if self.is_info_v2:
            course_key = self._device.model_info.config_value("smartCourseType")
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
        if run_state == STATE_WM_POWER_OFF:
            run_state = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_RUN_STATE, run_state
        )

    @property
    def pre_state(self):
        pre_state = self._get_pre_state()
        if pre_state is None:
            return None
        if pre_state == STATE_WM_POWER_OFF:
            pre_state = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_PRE_STATE, pre_state
        )

    @property
    def process_state(self):
        process = self._get_process_state()
        if process is None:
            return None
        return self._update_feature(
            FEAT_PROCESS_STATE, process
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
    def spin_option_state(self):
        if not self.key_exist(["SpinSpeed", "spin"]):
            return None
        spin_speed = self.lookup_enum(["SpinSpeed", "spin"])
        if not spin_speed:
            spin_speed = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_SPINSPEED, spin_speed
        )

    @property
    def water_temp_option_state(self):
        if not self.key_exist(["WTemp", "WaterTemp", "temp"]):
            return None
        if self.key_exist("temp") and self.is_dryer:
            return None
        water_temp = self.lookup_enum(["WTemp", "WaterTemp", "temp"])
        if not water_temp:
            water_temp = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_WATERTEMP, water_temp
        )

    @property
    def dry_level_option_state(self):
        if not self.key_exist(["DryLevel", "dryLevel"]):
            return None
        dry_level = self.lookup_enum(["DryLevel", "dryLevel"])
        if not dry_level:
            dry_level = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_DRYLEVEL, dry_level
        )

    @property
    def temp_control_option_state(self):
        if not self.key_exist(["TempControl", "tempControl", "temp"]):
            return None
        if self.key_exist("temp") and not self.is_dryer:
            return None
        temp_control = self.lookup_enum(["TempControl", "tempControl", "temp"])
        if not temp_control:
            temp_control = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_TEMPCONTROL, temp_control
        )

    @property
    def time_dry_option_state(self):
        """Get the time dry setting."""
        if not self.key_exist("TimeDry"):
            return None
        time_dry = self.lookup_enum("TimeDry")
        if not time_dry:
            time_dry = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_TIMEDRY, time_dry, False
        )

    @property
    def eco_hybrid_option_state(self):
        if not self.key_exist(["EcoHybrid", "ecoHybrid"]):
            return None
        eco_hybrid = self.lookup_enum(["EcoHybrid", "ecoHybrid"])
        if not eco_hybrid:
            eco_hybrid = STATE_OPTIONITEM_NONE
        return self._update_feature(
            FEAT_ECOHYBRID, eco_hybrid
        )

    @property
    def tubclean_count(self):
        if not self.key_exist("TCLCount"):
            return None
        if self.is_info_v2:
            result = DeviceStatus.int_or_none(self._data.get("TCLCount"))
        else:
            result = self._data.get("TCLCount")
        if result is None:
            result = "N/A"
        return self._update_feature(
            FEAT_TUBCLEAN_COUNT, result, False
        )

    @property
    def standby_state(self):
        if not self.key_exist(["Standby", "standby"]):
            return None
        status = self.lookup_enum(["Standby", "standby"])
        if not status:
            status = STATE_OPTIONITEM_OFF
        return self._update_feature(
            FEAT_STANDBY, status
        )

    @property
    def remotestart_state(self):
        status = self.lookup_bit(
            REMOTE_START_KEY[1] if self.is_info_v2 else REMOTE_START_KEY[0]
        )
        return self._update_feature(
            FEAT_REMOTESTART, status, False
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
    def doorclose_state(self):
        status = self.lookup_bit(
            "doorClose" if self.is_info_v2 else "DoorClose"
        )
        return self._update_feature(
            FEAT_DOORCLOSE, status, False
        )

    @property
    def childlock_state(self):
        status = self.lookup_bit(
            "childLock" if self.is_info_v2 else "ChildLock"
        )
        return self._update_feature(
            FEAT_CHILDLOCK, status, False
        )

    @property
    def creasecare_state(self):
        status = self.lookup_bit(
            "creaseCare" if self.is_info_v2 else "CreaseCare"
        )
        return self._update_feature(
            FEAT_CREASECARE, status, False
        )

    @property
    def steam_state(self):
        status = self.lookup_bit(
            "steam" if self.is_info_v2 else "Steam"
        )
        return self._update_feature(
            FEAT_STEAM, status, False
        )

    @property
    def steam_softener_state(self):
        status = self.lookup_bit(
            "steamSoftener" if self.is_info_v2 else "SteamSoftener"
        )
        return self._update_feature(
            FEAT_STEAMSOFTENER, status, False
        )

    @property
    def prewash_state(self):
        status = self.lookup_bit(
            "preWash" if self.is_info_v2 else "PreWash"
        )
        return self._update_feature(
            FEAT_PREWASH, status, False
        )

    @property
    def turbowash_state(self):
        status = self.lookup_bit(
            "turboWash" if self.is_info_v2 else "TurboWash"
        )
        return self._update_feature(
            FEAT_TURBOWASH, status, False
        )

    @property
    def medicrinse_state(self):
        status = self.lookup_bit(
            "medicRinse" if self.is_info_v2 else "MedicRinse"
        )
        return self._update_feature(
            FEAT_MEDICRINSE, status, False
        )

    @property
    def dampdrybeep_state(self):
        status = self.lookup_bit(
            "dampDryBeep" if self.is_info_v2 else "DampDryBeep"
        )
        return self._update_feature(
            FEAT_DAMPDRYBEEP, status, False
        )

    @property
    def reservation_state(self):
        status = self.lookup_bit(
            "reservation" if self.is_info_v2 else "Reservation"
        )
        return self._update_feature(
            FEAT_RESERVATION, status, False
        )

    @property
    def handiron_state(self):
        status = self.lookup_bit(
            "handIron" if self.is_info_v2 else "HandIron"
        )
        return self._update_feature(
            FEAT_HANDIRON, status, False
        )

    @property
    def selfclean_state(self):
        status = self.lookup_bit(
            "selfClean" if self.is_info_v2 else "SelfClean"
        )
        return self._update_feature(
            FEAT_SELFCLEAN, status, False
        )

    @property
    def anticrease_state(self):
        status = self.lookup_bit(
            "antiCrease" if self.is_info_v2 else "AntiCrease"
        )
        return self._update_feature(
            FEAT_ANTICREASE, status, False
        )

    def _update_features(self):
        result = [
            self.run_state,
            self.pre_state,
            self.process_state,
            self.error_msg,
            self.spin_option_state,
            self.water_temp_option_state,
            self.dry_level_option_state,
            self.temp_control_option_state,
            # self.time_dry_option_state,
            self.eco_hybrid_option_state,
            self.tubclean_count,
            self.standby_state,
            self.remotestart_state,
            self.doorlock_state,
            self.doorclose_state,
            self.childlock_state,
            self.creasecare_state,
            self.steam_state,
            self.steam_softener_state,
            self.prewash_state,
            self.turbowash_state,
            self.medicrinse_state,
            self.dampdrybeep_state,
            self.reservation_state,
            self.handiron_state,
            self.selfclean_state,
            self.anticrease_state,
        ]
