"""------------------for Oven"""
import enum
import logging

from typing import Optional

from . import (
    FEAT_COOKTOP_LEFT_FRONT_STATE,
    FEAT_COOKTOP_LEFT_REAR_STATE,
    FEAT_COOKTOP_CENTER_STATE,
    FEAT_COOKTOP_RIGHT_FRONT_STATE,
    FEAT_COOKTOP_RIGHT_REAR_STATE,
    FEAT_OVEN_LOWER_STATE,
    FEAT_OVEN_UPPER_STATE,
)

from .device import (
    Device,
    DeviceStatus,
    UNITTEMPMODES,
    UNIT_TEMP_FAHRENHEIT,
    UNIT_TEMP_CELSIUS,
)


_LOGGER = logging.getLogger(__name__)

OVEN_TEMP_UNIT = {
    "0": UNITTEMPMODES.Fahrenheit,
    "1": UNITTEMPMODES.Celsius,
}


class OvenDevice(Device):
    """A higher-level interface for an Oven."""

    def __init__(self, client, device):
        super().__init__(client, device, OvenStatus(self, None))

    def reset_status(self):
        self._status = OvenStatus(self, None)
        return self._status

    def poll(self) -> Optional["OvenStatus"]:
        """Poll the device's current state."""

        res = self.device_poll("ovenState")
        if not res:
            return None

        self._status = OvenStatus(self, res)
        return self._status


class OvenStatus(DeviceStatus):
    """Higher-level information about an Oven's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(self, device, data):
        super().__init__(device, data)
        self._oven_temp_unit = None

    def _update_features(self):
        result = [
            self.cooktop_left_front_state,
            self.cooktop_left_rear_state,
            self.cooktop_center_state,
            self.cooktop_right_front_state,
            self.cooktop_right_rear_state,
            self.oven_lower_state,
            self.oven_lower_target_temp,
            self.oven_upper_state,
            self.oven_upper_target_temp,
            self.oven_temp_unit,
        ]
        return

    def _get_oven_temp_unit(self):
        if not self._oven_temp_unit:
            oven_temp_unit = self.lookup_enum(["MonTempUnit"])
            if not oven_temp_unit:
                self._oven_temp_unit = STATE_OPTIONITEM_NONE
            else:
                self._oven_temp_unit = (
                    OVEN_TEMP_UNIT.get(oven_temp_unit, UNITTEMPMODES.Celsius)
                ).value
        return self._oven_temp_unit

    @property
    def is_on(self):
        result = [
            self.cooktop_left_front_state,
            self.cooktop_left_rear_state,
            self.cooktop_center_state,
            self.cooktop_right_front_state,
            self.cooktop_right_rear_state,
            self.oven_lower_state,
            self.oven_upper_state,
        ]
        for r in result:
            if r != 'Off':
                return True
        return False

    @property
    def cooktop_left_front_state(self):
        status = self.lookup_enum(["LFState"])
        return self._update_feature(
            FEAT_COOKTOP_LEFT_FRONT_STATE, status, True
        )

    @property
    def cooktop_left_rear_state(self):
        status = self.lookup_enum(["LRState"])
        return self._update_feature(
            FEAT_COOKTOP_LEFT_REAR_STATE, status, True
        )

    @property
    def cooktop_center_state(self):
        status = self.lookup_enum(["CenterState"])
        return self._update_feature(
            FEAT_COOKTOP_CENTER_STATE, status, True
        )

    @property
    def cooktop_right_front_state(self):
        status = self.lookup_enum(["RFState"])
        return self._update_feature(
            FEAT_COOKTOP_RIGHT_FRONT_STATE, status, True
        )

    @property
    def cooktop_right_rear_state(self):
        status = self.lookup_enum(["RRState"])
        return self._update_feature(
            FEAT_COOKTOP_RIGHT_REAR_STATE, status, True
        )

    @property
    def oven_lower_state(self):
        status = self.lookup_enum(["LowerOvenState"])
        return self._update_feature(
            FEAT_OVEN_LOWER_STATE, status, True
        )

    @property
    def oven_upper_state(self):
        status = self.lookup_enum(["UpperOvenState"])
        return self._update_feature(
            FEAT_OVEN_UPPER_STATE, status, True
        )

    @property
    def oven_lower_target_temp(self):
        unit = self._get_oven_temp_unit()
        if unit == UNIT_TEMP_FAHRENHEIT:
            key = "LowerTargetTemp_F"
        elif unit == UNIT_TEMP_CELSIUS:
            key = "LowerTargetTemp_C"
        else:
            return "N/A"
        result = self._data.get(key)
        if result is None:
            result = "N/A"
        return result

    @property
    def oven_upper_target_temp(self):
        unit = self._get_oven_temp_unit()
        if unit == UNIT_TEMP_FAHRENHEIT:
            key = "UpperTargetTemp_F"
        elif unit == UNIT_TEMP_CELSIUS:
            key = "UpperTargetTemp_C"
        else:
            return "N/A"
        result = self._data.get(key)
        if result is None:
            result = "N/A"
        return result
    
    @property
    def oven_temp_unit(self):
        return self._get_oven_temp_unit()

