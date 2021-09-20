"""------------------for Air Purifier"""
import enum
import logging

from typing import Optional

from .device import (
    Device,
    DeviceStatus,
)

AIRPURIFIER_CTRL_BASIC = ["Control", "basicCtrl"]

AIRPURIFIER_STATE_OPERATION = ["Operation", "airState.operation"]
AIRPURIFIER_STATE_PM1 = ["PM1", "airState.quality.PM1"]
AIRPURIFIER_STATE_PM25 = ["PM25", "airState.quality.PM2"]
AIRPURIFIER_STATE_PM10 = ["PM10", "airState.quality.PM10"]
AIRPURIFIER_STATE_FILTERMNG_USE_TIME = [
    "FilterMngMaxTime", "airState.filterMngStates.useTime"]
AIRPURIFIER_STATE_FILTERMNG_MAX_TIME = [
    "FilterMngMaxTime", "airState.filterMngStates.maxTime"]


CMD_STATE_OPERATION = [AIRPURIFIER_CTRL_BASIC,
                       "Set", AIRPURIFIER_STATE_OPERATION]

_LOGGER = logging.getLogger(__name__)


class AirPufifierOp(enum.Enum):
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

        op = AirPufifierOp.ON if turn_on else AirPufifierOp.OFF
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
    """Higher-level information about a Air Pufifier's current status."""

    def _get_state_key(self, key_name):
        if isinstance(key_name, list):
            return key_name[1 if self.is_info_v2 else 0]
        return key_name

    def _get_operation(self):
        key = self._get_state_key(AIRPURIFIER_STATE_OPERATION)
        try:
            return AirPufifierOp(self.lookup_enum(key, True))
        except ValueError:
            return None

    @property
    def is_on(self):
        op = self._get_operation()
        _LOGGER.debug(op)
        if not op:
            return False
        return op != AirPufifierOp.OFF

    @property
    def operation(self):
        op = self._get_operation()
        if not op:
            return None
        return op.name

    @property
    def pm1(self):
        key = self._get_state_key(AIRPURIFIER_STATE_PM1)
        return self._data.get(key)

    @property
    def pm25(self):
        key = self._get_state_key(AIRPURIFIER_STATE_PM25)
        return self._data.get(key)

    @property
    def pm10(self):
        key = self._get_state_key(AIRPURIFIER_STATE_PM10)
        return self._data.get(key)

    @property
    def filterMngUseTime(self):
        key = self._get_state_key(AIRPURIFIER_STATE_FILTERMNG_USE_TIME)
        return self._data.get(key)

    @property
    def filterMngMaxTime(self):
        key = self._get_state_key(AIRPURIFIER_STATE_FILTERMNG_MAX_TIME)
        return self._data.get(key)

    def _update_features(self):
        result = []
