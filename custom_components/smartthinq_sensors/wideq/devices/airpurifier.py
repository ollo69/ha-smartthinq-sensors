"""------------------for Air Purifier"""

from __future__ import annotations

from enum import Enum

from ..backports.functools import cached_property
from ..const import AirPurifierFeatures
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

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
        [
            AirPurifierFeatures.FILTER_MAIN_LIFE,
            AirPurifierFeatures.FILTER_MAIN_USE,
            AirPurifierFeatures.FILTER_MAIN_MAX,
        ],
        ["FilterUse", "airState.filterMngStates.useTime"],
        ["FilterMax", "airState.filterMngStates.maxTime"],
        None,
    ],
    [
        [
            AirPurifierFeatures.FILTER_TOP_LIFE,
            AirPurifierFeatures.FILTER_TOP_USE,
            AirPurifierFeatures.FILTER_TOP_MAX,
        ],
        ["FilterUseTop", "airState.filterMngStates.useTimeTop"],
        ["FilterMaxTop", "airState.filterMngStates.maxTimeTop"],
        ["@SUPPORT_TOP_HUMIDIFILTER", "@SUPPORT_D_PLUS_TOP"],
    ],
    [
        [
            AirPurifierFeatures.FILTER_MID_LIFE,
            AirPurifierFeatures.FILTER_MID_USE,
            AirPurifierFeatures.FILTER_MID_MAX,
        ],
        ["FilterUseMiddle", "airState.filterMngStates.useTimeMiddle"],
        ["FilterMaxMiddle", "airState.filterMngStates.maxTimeMiddle"],
        ["@SUPPORT_MID_HUMIDIFILTER"],
    ],
    [
        [
            AirPurifierFeatures.FILTER_BOTTOM_LIFE,
            AirPurifierFeatures.FILTER_BOTTOM_USE,
            AirPurifierFeatures.FILTER_BOTTOM_MAX,
        ],
        ["FilterUseBottom", "airState.filterMngStates.useTimeBottom"],
        ["FilterMaxBottom", "airState.filterMngStates.maxTimeBottom"],
        ["@SUPPORT_BOTTOM_PREFILTER"],
    ],
    [
        [
            AirPurifierFeatures.FILTER_DUST_LIFE,
            AirPurifierFeatures.FILTER_DUST_USE,
            AirPurifierFeatures.FILTER_DUST_MAX,
        ],
        ["FilterUseDeodor", "airState.filterMngStates.useTimeDeodor"],
        ["FilterMaxDeodor", "airState.filterMngStates.maxTimeDeodor"],
        ["@SUPPORT_BOTTOM_DUSTCOLLECTION"],
    ],
]


class AirPurifierOp(Enum):
    """Whether a device is on or off."""

    OFF = "@operation_off"
    ON = "@operation_on"


class AirPurifierMode(Enum):
    """The operation mode for a AirPurifier device."""

    CLEAN = "@AP_MAIN_MID_OPMODE_CLEAN_W"
    SILENT = "@AP_MAIN_MID_OPMODE_SILENT_W"
    HUMIDITY = "@AP_MAIN_MID_OPMODE_HUMIDITY_W"


class AirPurifierFanSpeed(Enum):
    """The fan speed for a AirPurifier device."""

    LOW = "@AP_MAIN_MID_WINDSTRENGTH_LOW_W"
    MID = "@AP_MAIN_MID_WINDSTRENGTH_MID_W"
    HIGH = "@AP_MAIN_MID_WINDSTRENGTH_HIGH_W"


class AirPurifierFanPreset(Enum):
    """The fan preset for a AirPurifier device."""

    POWER = "@AP_MAIN_MID_WINDSTRENGTH_POWER_W"
    AUTO = "@AP_MAIN_MID_WINDSTRENGTH_AUTO_W"


class AirPurifierDevice(Device):
    """A higher-level interface for a Air Purifier."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        super().__init__(client, device_info, AirPurifierStatus(self))

    @cached_property
    def op_modes(self) -> list:
        """Available operation modes."""
        return self._get_property_values(SUPPORT_OPERATION_MODE, AirPurifierMode)

    @cached_property
    def fan_speeds(self) -> list:
        """Available fan speeds."""
        return self._get_property_values(SUPPORT_WIND_STRENGTH, AirPurifierFanSpeed)

    @cached_property
    def fan_presets(self) -> list:
        """Available fan presets."""
        return self._get_property_values(SUPPORT_WIND_STRENGTH, AirPurifierFanPreset)

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op_mode = AirPurifierOp.ON if turn_on else AirPurifierOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op_mode.value)
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
        speed_value = self.model_info.enum_value(
            keys[2], AirPurifierFanSpeed[speed].value
        )
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set_fan_preset(self, preset):
        """Set the fan preset to a value from the `AirPurifierFanPreset` enum."""

        if preset not in self.fan_presets:
            raise ValueError(f"Invalid fan preset: {preset}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(
            keys[2], AirPurifierFanPreset[preset].value
        )
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if key is not None and self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = AirPurifierStatus(self)
        return self._status

    async def poll(self) -> AirPurifierStatus | None:
        """Poll the device's current state."""

        res = await self._device_poll()
        if not res:
            return None

        self._status = AirPurifierStatus(self, res)
        return self._status


class AirPurifierStatus(DeviceStatus):
    """Higher-level information about a Air Purifier's current status."""

    _device: AirPurifierDevice

    def __init__(self, device: AirPurifierDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._operation = None

    def _get_operation(self):
        """Get current operation."""
        if self._operation is None:
            key = self._get_state_key(STATE_OPERATION)
            operation = self.lookup_enum(key, True)
            if not operation:
                return None
            self._operation = operation
        try:
            return AirPurifierOp(self._operation)
        except ValueError:
            return None

    def update_status(self, key, value):
        """Update device status."""
        if not super().update_status(key, value):
            return False
        if key in STATE_OPERATION:
            self._operation = None
        return True

    @property
    def is_on(self):
        """Return if device is on."""
        op_mode = self._get_operation()
        if not op_mode:
            return False
        return op_mode != AirPurifierOp.OFF

    @property
    def operation(self):
        """Return current device operation."""
        op_mode = self._get_operation()
        if not op_mode:
            return None
        return op_mode.name

    @property
    def operation_mode(self):
        """Return current device operation mode."""
        key = self._get_state_key(STATE_OPERATION_MODE)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return AirPurifierMode(value).name
        except ValueError:
            return None

    @property
    def fan_speed(self):
        """Return current fan speed."""
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return AirPurifierFanSpeed(value).name
        except ValueError:
            return None

    @property
    def fan_preset(self):
        """Return current fan preset."""
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return AirPurifierFanPreset(value).name
        except ValueError:
            return None

    @property
    def current_humidity(self):
        """Return current humidity."""
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if (
            self._device.model_info.enum_value(support_key, "@SENSOR_HUMID_SUPPORT")
            is None
        ):
            return None
        key = self._get_state_key(STATE_HUMIDITY)
        if (value := self.to_int_or_none(self.lookup_range(key))) is None:
            return None
        return self._update_feature(AirPurifierFeatures.HUMIDITY, value, False)

    @property
    def pm1(self):
        """Return Air PM1 value."""
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@PM1_0_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_PM1)
        if (value := self.lookup_range(key)) is None:
            return None
        return self._update_feature(AirPurifierFeatures.PM1, value, False)

    @property
    def pm10(self):
        """Return Air PM10 value."""
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@PM10_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_PM10)
        if (value := self.lookup_range(key)) is None:
            return None
        return self._update_feature(AirPurifierFeatures.PM10, value, False)

    @property
    def pm25(self):
        """Return Air PM2.5 value."""
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@PM2_5_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_PM25)
        if (value := self.lookup_range(key)) is None:
            return None
        return self._update_feature(AirPurifierFeatures.PM25, value, False)

    @property
    def filters_life(self):
        """Return percentage status for all filters."""
        result = {}

        # Get the filter feature key
        support_key = self._get_state_key(SUPPORT_MFILTER)

        for filter_def in FILTER_TYPES:
            status = self._get_filter_life(
                filter_def[1],
                filter_def[2],
                filter_def[3],
                support_key,
                use_time_inverted=True,
            )
            if status is not None:
                for index, feat in enumerate(filter_def[0]):
                    if index >= len(status):
                        break
                    self._update_feature(feat, status[index], False)
                    result[feat] = status[index]

        return result

    def _update_features(self):
        _ = [
            self.current_humidity,
            self.pm1,
            self.pm10,
            self.pm25,
            self.filters_life,
        ]
