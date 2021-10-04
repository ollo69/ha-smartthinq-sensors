"""------------------for Air Purifier"""
import enum
import logging
from typing import Optional

from . import FEAT_LOWER_FILTER_LIFE, FEAT_UPPER_FILTER_LIFE

from .device import Device, DeviceStatus

LABEL_UPPER_FILTER_SUPPORT = "@SUPPORT_D_PLUS_TOP"

AIR_PURIFIER_CTRL_BASIC = ["Control", "basicCtrl"]

SUPPORT_AIR_PURIFIER_MFILTER = ["MFILTER", "support.mFilter"]
AIR_PURIFIER_STATE_OPERATION = ["Operation", "airState.operation"]
AIR_PURIFIER_STATE_PM1 = ["PM1", "airState.quality.PM1"]
AIR_PURIFIER_STATE_PM25 = ["PM25", "airState.quality.PM2"]
AIR_PURIFIER_STATE_PM10 = ["PM10", "airState.quality.PM10"]
AIR_PURIFIER_STATE_FILTERMNG_USE_TIME = [
    "FilterMngUseTime", "airState.filterMngStates.useTime"
]
AIR_PURIFIER_STATE_FILTERMNG_MAX_TIME = [
    "FilterMngMaxTime", "airState.filterMngStates.maxTime"
]
AIR_PURIFIER_STATE_FILTERMNG_USE_TIME_TOP = [
    "FilterMngUseTimeTop", "airState.filterMngStates.useTimeTop"
]
AIR_PURIFIER_STATE_FILTERMNG_MAX_TIME_TOP = [
    "FilterMngMaxTimeTop", "airState.filterMngStates.maxTimeTop"
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

    def _get_operation(self):
        try:
            return AirPurifierOp(
                self.lookup_enum(AIR_PURIFIER_STATE_OPERATION, True)
            )
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
        return self.lookup_range(AIR_PURIFIER_STATE_PM1)

    @property
    def pm25(self):
        return self.lookup_range(AIR_PURIFIER_STATE_PM25)

    @property
    def pm10(self):
        return self.lookup_range(AIR_PURIFIER_STATE_PM10)

    def _get_lower_filter_life(self):
        max_time = self.lookup_enum(AIR_PURIFIER_STATE_FILTERMNG_MAX_TIME, True)
        use_time = self.lookup_range(AIR_PURIFIER_STATE_FILTERMNG_USE_TIME)
        if max_time is None or use_time is None:
            return None
        try:
            return use_time/max_time*100
        except ValueError:
            return None

    def _get_upper_filter_life(self):
        max_time = self.lookup_enum(AIR_PURIFIER_STATE_FILTERMNG_MAX_TIME_TOP, True)
        use_time = self.lookup_range(AIR_PURIFIER_STATE_FILTERMNG_USE_TIME_TOP)
        if max_time is None or use_time is None:
            return None
        try:
            return use_time/max_time*100
        except ValueError:
            return None

    @property
    def lower_filter_life(self):
        feat_value = self._get_lower_filter_life()
        if feat_value is None:
            return None
        return self._update_feature(
            FEAT_LOWER_FILTER_LIFE, feat_value, False
        )

    @property
    def upper_filter_life(self):
        # Check the upper filter is exist
        if self._device.model_info.enum_value(SUPPORT_AIR_PURIFIER_MFILTER[1], LABEL_UPPER_FILTER_SUPPORT) is None:
            return None
        
        feat_value = self._get_upper_filter_life()
        if feat_value is None:
            return None
        return self._update_feature(
            FEAT_UPPER_FILTER_LIFE, feat_value, False
        )

    def _update_features(self):
        result = [
            self.lower_filter_life,
            self.upper_filter_life,
        ]
