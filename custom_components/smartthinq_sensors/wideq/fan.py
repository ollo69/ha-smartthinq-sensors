"""------------------for Fan"""
import enum
import logging
from typing import Optional

from .device import Device, DeviceStatus

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


class FanOp(enum.Enum):
    """Whether a device is on or off."""

    OFF = "@OFF"
    ON = "@ON"


class FanMode(enum.Enum):
    """The operation mode for a Fan device."""

    NORMAL = "@FAN_MAIN_OPERATION_MODE_NORMAL_W"


class FanSpeed(enum.Enum):
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

    def __init__(self, client, device):
        super().__init__(client, device, FanStatus(self, None))
        self._supported_fan_speeds = None

    @property
    def fan_speeds(self):
        """Return a list of available fan speeds."""
        if self._supported_fan_speeds is None:
            key = self._get_state_key(SUPPORT_WIND_STRENGTH)
            if not self.model_info.is_enum_type(key):
                self._supported_fan_speeds = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in FanSpeed]
            self._supported_fan_speeds = [FanSpeed(o).name for o in mapping.values() if o in mode_list]
        return self._supported_fan_speeds

    @property
    def fan_presets(self):
        """Return a list of available fan presets."""
        return []

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = FanOp.ON if turn_on else FanOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op.value)
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

    async def set(self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if key is not None and self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = FanStatus(self, None)
        return self._status

    async def poll(self) -> Optional["FanStatus"]:
        """Poll the device's current state."""

        res = await self.device_poll()
        if not res:
            return None

        self._status = FanStatus(self, res)

        return self._status


class FanStatus(DeviceStatus):
    """Higher-level information about a Fan's current status."""

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
            return FanOp(self._operation)
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
        return op != FanOp.OFF

    @property
    def operation(self):
        op = self._get_operation()
        if not op:
            return None
        return op.name

    @property
    def fan_speed(self):
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return FanSpeed(value).name
        except ValueError:
            return None

    @property
    def fan_preset(self):
        return None

    def _update_features(self):
        return
