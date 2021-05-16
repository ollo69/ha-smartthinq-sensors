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
    FEAT_OVEN_LOWER_TARGET_TEMP,
    FEAT_OVEN_UPPER_STATE,
    FEAT_OVEN_UPPER_TARGET_TEMP,
)

from .device import (
    Device,
    DeviceStatus,
)


_LOGGER = logging.getLogger(__name__)


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
        ]
        return

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
        status = self.lookup_enum(["LFState", "cooktop1CooktopState"])
        return self._update_feature(
            FEAT_COOKTOP_LEFT_FRONT_STATE, status, True
        )

    @property
    def cooktop_left_rear_state(self):
        status = self.lookup_enum(["LRState", "cooktop2CooktopState"])
        return self._update_feature(
            FEAT_COOKTOP_LEFT_REAR_STATE, status, True
        )

    @property
    def cooktop_center_state(self):
        status = self.lookup_enum(["CenterState", "cooktop3CooktopState"])
        return self._update_feature(
            FEAT_COOKTOP_CENTER_STATE, status, True
        )

    @property
    def cooktop_right_front_state(self):
        status = self.lookup_enum(["RFState", "cooktop4CooktopState"])
        return self._update_feature(
            FEAT_COOKTOP_RIGHT_FRONT_STATE, status, True
        )

    @property
    def cooktop_right_rear_state(self):
        status = self.lookup_enum(["RRState", "cooktop5CooktopState"])
        return self._update_feature(
            FEAT_COOKTOP_RIGHT_REAR_STATE, status, True
        )

    @property
    def oven_lower_state(self):
        status = self.lookup_enum(["LowerOvenState", "lowerState"])
        return self._update_feature(
            FEAT_OVEN_LOWER_STATE, status, True
        )

    @property
    def oven_upper_state(self):
        status = self.lookup_enum(["UpperOvenState", "upperState"])
        return self._update_feature(
            FEAT_OVEN_UPPER_STATE, status, True
        )

    @property
    def oven_lower_target_temp(self):
        if self.is_info_v2:
            result = DeviceStatus.int_or_none(self._data.get("lowerTargetTemperatureValue"))
        else:
            result = self._data.get("lowerTargetTemperatureValue")
        if result is None:
            result = "N/A"
        return self._update_feature(
            FEAT_OVEN_LOWER_TARGET_TEMP, result, False
        )

    @property
    def oven_upper_target_temp(self):
        if self.is_info_v2:
            result = DeviceStatus.int_or_none(self._data.get("upperTargetTemperatureValue"))
        else:
            result = self._data.get("upperTargetTemperatureValue")
        if result is None:
            result = "N/A"
        return self._update_feature(
            FEAT_OVEN_UPPER_TARGET_TEMP, result, False
        )
    
