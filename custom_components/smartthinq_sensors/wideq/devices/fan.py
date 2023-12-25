"""------------------for Fan"""
from __future__ import annotations

from enum import Enum
import logging

from ..backports.functools import cached_property
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

CTRL_BASIC = ["Control", "basicCtrl"]

SUPPORT_OPERATION_MODE = ["SupportOpMode", "support.airState.opMode"]
SUPPORT_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]

STATE_OPERATION = ["Operation", "airState.operation"]
STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]

CMD_STATE_OPERATION = [CTRL_BASIC, "Set", STATE_OPERATION]
CMD_STATE_OP_MODE = [CTRL_BASIC, "Set", STATE_OPERATION_MODE]
CMD_STATE_WIND_STRENGTH = [CTRL_BASIC, "Set", STATE_WIND_STRENGTH]

_LOGGER = logging.getLogger(__name__)


class FanOp(Enum):
    """Whether a device is on or off."""

    OFF = "@OFF"
    ON = "@ON"


class FanMode(Enum):
    """The operation mode for a Fan device."""

    NORMAL = "@FAN_MAIN_OPERATION_MODE_NORMAL_W"


class FanSpeed(Enum):
    """The fan speed for a Fan device."""

    LOWEST_LOW = "@LOWST_LOW"
    LOWEST = "@LOWST"
    LOW = "@LOW"
    LOW_MID = "@LOW_MED"
    MID = "@MED"
    MID_HIGH = "@MED_HIGH"
    HIGH = "@HIGH"
    TURBO = "@TURBO"


class FanDevice(Device):
    """A higher-level interface for Fan."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        super().__init__(client, device_info, FanStatus(self))

    @cached_property
    def fan_speeds(self) -> list:
        """Available fan speeds."""
        return self._get_property_values(SUPPORT_WIND_STRENGTH, FanSpeed)

    @property
    def fan_presets(self) -> list:
        """Available fan presets."""
        return []

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op_mode = FanOp.ON if turn_on else FanOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op_mode.value)
        if self._should_poll:
            # different power command for ThinQ1 devices
            cmd = "Start" if turn_on else "Stop"
            await self.set(keys[0], keys[2], key=None, value=cmd)
            self._status.update_status(keys[2], op_value)
            return
        await self.set(keys[0], keys[1], key=keys[2], value=op_value)

    async def set_fan_speed(self, speed):
        """Set the fan speed to a value from the `FanSpeed` enum."""

        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], FanSpeed[speed].value)
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set_fan_preset(self, preset):
        """Set the fan preset to a value from the `FanPreset` enum."""

        raise ValueError(f"Invalid fan preset: {preset}")

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
        self._status = FanStatus(self)
        return self._status

    async def poll(self) -> FanStatus | None:
        """Poll the device's current state."""

        res = await self._device_poll()
        if not res:
            return None

        self._status = FanStatus(self, res)

        return self._status


class FanStatus(DeviceStatus):
    """Higher-level information about a Fan's current status."""

    _device: FanDevice

    def __init__(self, device: FanDevice, data: dict | None = None):
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
            return FanOp(self._operation)
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
        return op_mode != FanOp.OFF

    @property
    def operation(self):
        """Return current device operation."""
        op_mode = self._get_operation()
        if not op_mode:
            return None
        return op_mode.name

    @property
    def fan_speed(self):
        """Return current fan speed."""
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return FanSpeed(value).name
        except ValueError:
            return None

    @property
    def fan_preset(self):
        """Return current fan preset."""
        return None

    def _update_features(self):
        return
