"""------------------for Dehumidifier"""
import enum
import logging
from typing import Optional

from .device import Device, DeviceStatus

DEHUMIDIFER_CTRL_BASIC = ["Control", "basicCtrl"]

DEHUMIDIFER_STATE_OPERATION = ["Operation", "airState.operation"]

CMD_STATE_OPERATION = [
    DEHUMIDIFER_CTRL_BASIC, "Set", DEHUMIDIFER_STATE_OPERATION
]

_LOGGER = logging.getLogger(__name__)


class DeHumidifierOp(enum.Enum):
    """Whether a device is on or off."""

    OFF = "@operation_off"
    ON = "@operation_on"


class DehumidifierDevice(Device):
    """A higher-level interface for a DeHumidifier."""

    def __init__(self, client, device):
        super().__init__(client, device, DeHumidifierStatus(self, None))
        self._supported_operation = None

    def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = DeHumidifierOp.ON if turn_on else DeHumidifierOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op.value)
        self.set(keys[0], keys[1], key=keys[2], value=op_value)

    def set(self, ctrl_key, command, *, key=None, value=None, data=None):
        """Set a device's control for `key` to `value`."""
        super().set(ctrl_key, command, key=key, value=value, data=data)
        if self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = DeHumidifierStatus(self, None)
        return self._status

    def poll(self) -> Optional["DeHumidifierStatus"]:
        """Poll the device's current state."""

        res = self.device_poll()
        if not res:
            return None

        self._status = DeHumidifierStatus(self, res)
        return self._status


class DeHumidifierStatus(DeviceStatus):
    """Higher-level information about a DeHumidifier's current status."""

    def _get_operation(self):
        try:
            return DeHumidifierOp(
                self.lookup_enum(DEHUMIDIFER_STATE_OPERATION, True)
            )
        except ValueError:
            return None

    @property
    def is_on(self):
        op = self._get_operation()
        if not op:
            return False
        return op != DeHumidifierOp.OFF

    @property
    def operation(self):
        op = self._get_operation()
        if not op:
            return None
        return op.name

    def _update_features(self):
        result = []
