"""------------------for Air Purifier"""
import enum
import logging
from typing import Optional

from .device import Device, DeviceStatus

AIR_PURIFIER_CTRL_BASIC = ["Control", "basicCtrl"]

AIR_PURIFIER_STATE_OPERATION = ["Operation", "airState.operation"]
AIR_PURIFIER_STATE_PM1 = ["PM1", "airState.quality.PM1"]
AIR_PURIFIER_STATE_PM25 = ["PM25", "airState.quality.PM2"]
AIR_PURIFIER_STATE_PM10 = ["PM10", "airState.quality.PM10"]
AIR_PURIFIER_STATE_FILTERMNG_USE_TIME = [
    "FilterMngMaxTime", "airState.filterMngStates.useTime"
]
AIR_PURIFIER_STATE_FILTERMNG_MAX_TIME = [
    "FilterMngMaxTime", "airState.filterMngStates.maxTime"
]

CMD_STATE_OPERATION = [
    AIR_PURIFIER_CTRL_BASIC, "Set", AIR_PURIFIER_STATE_OPERATION
]

_LOGGER = logging.getLogger(__name__)


class AirPurifierOp(enum.Enum):
    """Whether a device is on or off."""

    OFF = "@operation_off"
    ON = "@operation_on"


class AirPurifierDevice(Device):
    """A higher-level interface for a Air Purifier."""

    def __init__(self, client, device):
        super().__init__(client, device, AirPurifierStatus(self, None))
        self._supported_operation = None

    def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = AirPurifierOp.ON if turn_on else AirPurifierOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op.value)
        self.set(keys[0], keys[1], key=keys[2], value=op_value)

    def set(self, ctrl_key, command, *, key=None, value=None, data=None):
        """Set a device's control for `key` to `value`."""
        super().set(ctrl_key, command, key=key, value=value, data=data)
        if self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = AirPurifierStatus(self, None)
        return self._status

    def poll(self) -> Optional["AirPurifierStatus"]:
        """Poll the device's current state."""

        res = self.device_poll()
        if not res:
            return None

        self._status = AirPurifierStatus(self, res)
        return self._status


class AirPurifierStatus(DeviceStatus):
    """Higher-level information about a Air Purifier's current status."""

    def _get_state_key(self, key_name):
        if isinstance(key_name, list):
            return key_name[1 if self.is_info_v2 else 0]
        return key_name

    def _get_operation(self):
        key = self._get_state_key(AIR_PURIFIER_STATE_OPERATION)
        try:
            return AirPurifierOp(self.lookup_enum(key, True))
        except ValueError:
            return None

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
    def pm1(self):
        key = self._get_state_key(AIR_PURIFIER_STATE_PM1)
        return self._data.get(key)

    @property
    def pm25(self):
        key = self._get_state_key(AIR_PURIFIER_STATE_PM25)
        return self._data.get(key)

    @property
    def pm10(self):
        key = self._get_state_key(AIR_PURIFIER_STATE_PM10)
        return self._data.get(key)

    @property
    def filter_mng_use_time(self):
        key = self._get_state_key(AIR_PURIFIER_STATE_FILTERMNG_USE_TIME)
        return self._data.get(key)

    @property
    def filter_mng_max_time(self):
        key = self._get_state_key(AIR_PURIFIER_STATE_FILTERMNG_MAX_TIME)
        return self._data.get(key)

    def _update_features(self):
        result = []
