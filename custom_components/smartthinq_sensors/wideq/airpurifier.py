"""------------------for Air Purifier"""
import enum
import logging
from typing import Optional

from .const import (
    FEAT_FILTER_BOTTOM_LIFE,
    FEAT_FILTER_DUST_LIFE,
    FEAT_FILTER_MAIN_LIFE,
    FEAT_FILTER_MID_LIFE,
    FEAT_FILTER_TOP_LIFE,
    FEAT_HUMIDITY,
    FEAT_PM1,
    FEAT_PM10,
    FEAT_PM25,
)
from .device import Device, DeviceStatus

CTRL_BASIC = ["Control", "basicCtrl"]

SUPPORT_OPERATION_MODE = ["SupportOpMode", "support.airState.opMode"]
SUPPORT_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]
SUPPORT_MFILTER = ["SupportMFilter", "support.mFilter"]
SUPPORT_AIR_POLUTION = ["SupportAirPolution", "support.airPolution"]

STATE_OPERATION = ["Operation", "airState.operation"]
STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]

STATE_HUMIDITY = ["SensorHumidity", "airState.humidity.current"]
STATE_PM1 = ["SensorPM1", "airState.quality.PM1"]
STATE_PM10 = ["SensorPM10", "airState.quality.PM10"]
STATE_PM25 = ["SensorPM2", "airState.quality.PM2"]

CMD_STATE_OPERATION = [CTRL_BASIC, "Set", STATE_OPERATION]
CMD_STATE_OP_MODE = [CTRL_BASIC, "Set", STATE_OPERATION_MODE]
CMD_STATE_WIND_STRENGTH = [CTRL_BASIC, "Set", STATE_WIND_STRENGTH]

FILTER_TYPES = [
    [
        FEAT_FILTER_MAIN_LIFE,
        ["FilterUse", "airState.filterMngStates.useTime"],
        ["FilterMax", "airState.filterMngStates.maxTime"],
        None,
    ],
    [
        FEAT_FILTER_TOP_LIFE,
        ["FilterUseTop", "airState.filterMngStates.useTimeTop"],
        ["FilterMaxTop", "airState.filterMngStates.maxTimeTop"],
        ["@SUPPORT_TOP_HUMIDIFILTER", "@SUPPORT_D_PLUS_TOP"],
    ],
    [
        FEAT_FILTER_MID_LIFE,
        ["FilterUseMiddle", "airState.filterMngStates.useTimeMiddle"],
        ["FilterMaxMiddle", "airState.filterMngStates.maxTimeMiddle"],
        ["@SUPPORT_MID_HUMIDIFILTER"],
    ],
    [
        FEAT_FILTER_BOTTOM_LIFE,
        ["FilterUseBottom", "airState.filterMngStates.useTimeBottom"],
        ["FilterMaxBottom", "airState.filterMngStates.maxTimeBottom"],
        ["@SUPPORT_BOTTOM_PREFILTER"],
    ],
    [
        FEAT_FILTER_DUST_LIFE,
        ["FilterUseDeodor", "airState.filterMngStates.useTimeDeodor"],
        ["FilterMaxDeodor", "airState.filterMngStates.maxTimeDeodor"],
        ["@SUPPORT_BOTTOM_DUSTCOLLECTION"],
    ],
]


_LOGGER = logging.getLogger(__name__)


class AirPurifierOp(enum.Enum):
    """Whether a device is on or off."""

    OFF = "@operation_off"
    ON = "@operation_on"


class AirPurifierMode(enum.Enum):
    """The operation mode for a AirPurifier device."""

    CLEAN = "@AP_MAIN_MID_OPMODE_CLEAN_W"
    SILENT = "@AP_MAIN_MID_OPMODE_SILENT_W"
    HUMIDITY = "@AP_MAIN_MID_OPMODE_HUMIDITY_W"


class AirPurifierFanSpeed(enum.Enum):
    """The fan speed for a AirPurifier device."""

    LOW = "@AP_MAIN_MID_WINDSTRENGTH_LOW_W"
    MID = "@AP_MAIN_MID_WINDSTRENGTH_MID_W"
    HIGH = "@AP_MAIN_MID_WINDSTRENGTH_HIGH_W"


class AirPurifierFanPreset(enum.Enum):
    """The fan preset for a AirPurifier device."""

    AUTO = "@AP_MAIN_MID_WINDSTRENGTH_AUTO_W"


class AirPurifierDevice(Device):
    """A higher-level interface for a Air Purifier."""

    def __init__(self, client, device):
        super().__init__(client, device, AirPurifierStatus(self, None))
        self._supported_op_modes = None
        self._supported_fan_speeds = None
        self._supported_fan_presets = None

    @property
    def op_modes(self):
        """Return a list of available operation modes."""
        if self._supported_op_modes is None:
            key = self._get_state_key(SUPPORT_OPERATION_MODE)
            if not self.model_info.is_enum_type(key):
                self._supported_op_modes = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in AirPurifierMode]
            self._supported_op_modes = [AirPurifierMode(o).name for o in mapping.values() if o in mode_list]
        return self._supported_op_modes

    @property
    def fan_speeds(self):
        """Return a list of available fan speeds."""
        if self._supported_fan_speeds is None:
            key = self._get_state_key(SUPPORT_WIND_STRENGTH)
            if not self.model_info.is_enum_type(key):
                self._supported_fan_speeds = []
                self._supported_fan_presets = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in AirPurifierFanSpeed]
            preset_list = [e.value for e in AirPurifierFanPreset]
            self._supported_fan_speeds = [AirPurifierFanSpeed(o).name for o in mapping.values() if o in mode_list]
            self._supported_fan_presets = [AirPurifierFanPreset(o).name for o in mapping.values() if o in preset_list]
        return self._supported_fan_speeds

    @property
    def fan_presets(self):
        """Return a list of available fan presets."""
        if self._supported_fan_presets is None:
            _ = self.fan_speeds
        return self._supported_fan_presets

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = AirPurifierOp.ON if turn_on else AirPurifierOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op.value)
        await self.set(keys[0], keys[1], key=keys[2], value=op_value)

    async def set_op_mode(self, mode):
        """Set the device's operating mode to an `OpMode` value."""

        if mode not in self.op_modes:
            raise ValueError(f"Invalid operating mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_OP_MODE)
        mode_value = self.model_info.enum_value(keys[2], AirPurifierMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=mode_value)

    async def set_fan_speed(self, speed):
        """Set the fan speed to a value from the `AirPurifierFanSpeed` enum."""

        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], AirPurifierFanSpeed[speed].value)
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set_fan_preset(self, preset):
        """Set the fan preset to a value from the `AirPurifierFanPreset` enum."""

        if preset not in self.fan_presets:
            raise ValueError(f"Invalid fan preset: {preset}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], AirPurifierFanPreset[preset].value)
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set(self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if key is not None and self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = AirPurifierStatus(self, None)
        return self._status

    async def poll(self) -> Optional["AirPurifierStatus"]:
        """Poll the device's current state."""

        res = await self.device_poll()
        if not res:
            return None

        self._status = AirPurifierStatus(self, res)
        return self._status


class AirPurifierStatus(DeviceStatus):
    """Higher-level information about a Air Purifier's current status."""

    def __init__(self, device, data):
        super().__init__(device, data)
        self._operation = None

    def _get_operation(self):
        if self._operation is None:
            key = self._get_state_key(STATE_OPERATION)
            self._operation = self.lookup_enum(key, True)
            if self._operation is None:
                return None
        try:
            return AirPurifierOp(self._operation)
        except ValueError:
            return None

    def update_status(self, key, value):
        if not super().update_status(key, value):
            return False
        if key in STATE_OPERATION:
            self._operation = None
        return True

    @property
    def is_on(self):
        op = self._get_operation()
        if not op:
            return False
        return op != AirPurifierOp.OFF

    @property
    def operation(self):
        op = self._get_operation()
        if not op:
            return None
        return op.name

    @property
    def operation_mode(self):
        key = self._get_state_key(STATE_OPERATION_MODE)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return AirPurifierMode(value).name
        except ValueError:
            return None

    @property
    def fan_speed(self):
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return AirPurifierFanSpeed(value).name
        except ValueError:
            return None

    @property
    def fan_preset(self):
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return AirPurifierFanPreset(value).name
        except ValueError:
            return None

    @property
    def current_humidity(self):
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@SENSOR_HUMID_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_HUMIDITY)
        if (value := self.to_int_or_none(self.lookup_range(key))) is None:
            return None
        return self._update_feature(FEAT_HUMIDITY, value, False)

    @property
    def pm1(self):
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@PM1_0_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_PM1)
        if (value := self.lookup_range(key)) is None:
            return None
        return self._update_feature(FEAT_PM1, value, False)

    @property
    def pm10(self):
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@PM10_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_PM10)
        if (value := self.lookup_range(key)) is None:
            return None
        return self._update_feature(FEAT_PM10, value, False)

    @property
    def pm25(self):
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@PM2_5_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_PM25)
        if (value := self.lookup_range(key)) is None:
            return None
        return self._update_feature(FEAT_PM25, value, False)

    def _get_filter_life(self, use_time_status, max_time_status, support_key, filter_types=None):
        if filter_types:
            supported = False
            for filter_type in filter_types:
                if self._device.model_info.enum_value(support_key, filter_type) is not None:
                    supported = True
                    break
            if not supported:
                return None

        key_max_status = self._get_state_key(max_time_status)
        max_time = self.to_int_or_none(
            self.lookup_enum(key_max_status, True)
        )
        if max_time is None:
            max_time = self.to_int_or_none(
                self.lookup_range(key_max_status)
            )
            if max_time is None:
                return None
            if max_time < 10:  # because is an enum
                return None

        use_time = self.to_int_or_none(
            self.lookup_range(self._get_state_key(use_time_status))
        )
        if use_time is None:
            return None
        if max_time < use_time:
            return None

        try:
            return int((use_time/max_time)*100)
        except ValueError:
            return None

    @property
    def filters_life(self):
        """Return percentage status for all filters"""
        result = {}

        # Get the filter feature key
        support_key = self._get_state_key(SUPPORT_MFILTER)

        for filter_def in FILTER_TYPES:
            status = self._get_filter_life(filter_def[1], filter_def[2], support_key, filter_def[3])
            if status is not None:
                self._update_feature(filter_def[0], status, False)
                result[filter_def[0]] = status

        return result

    def _update_features(self):
        _ = [
            self.current_humidity,
            self.pm1,
            self.pm10,
            self.pm25,
            self.filters_life,
        ]
