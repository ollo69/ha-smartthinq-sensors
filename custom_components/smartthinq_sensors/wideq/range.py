"""------------------for Oven"""
import logging

from typing import Optional

from . import (
    FEAT_COOKTOP_LEFT_FRONT_STATE,
    FEAT_COOKTOP_LEFT_REAR_STATE,
    FEAT_COOKTOP_CENTER_STATE,
    FEAT_COOKTOP_RIGHT_FRONT_STATE,
    FEAT_COOKTOP_RIGHT_REAR_STATE,
    FEAT_OVEN_LOWER_CURRENT_TEMP,
    FEAT_OVEN_LOWER_STATE,
    FEAT_OVEN_UPPER_CURRENT_TEMP,
    FEAT_OVEN_UPPER_STATE,
)

from .device import (
    Device,
    DeviceStatus,
    BIT_OFF,
    UNITTEMPMODES,
    UNIT_TEMP_FAHRENHEIT,
    UNIT_TEMP_CELSIUS,
    STATE_OPTIONITEM_NONE,
    STATE_OPTIONITEM_OFF,
)

OVEN_TEMP_UNIT = {
    "0": UNITTEMPMODES.Fahrenheit,
    "1": UNITTEMPMODES.Celsius,
    "FAHRENHEIT": UNITTEMPMODES.Fahrenheit,
    "CELSIUS": UNITTEMPMODES.Celsius,
}

ITEM_STATE_OFF = "@OV_STATE_INITIAL_W"

_LOGGER = logging.getLogger(__name__)


class RangeDevice(Device):
    """A higher-level interface for a cooking range."""

    def __init__(self, client, device):
        super().__init__(client, device, RangeStatus(self, None))

    def reset_status(self):
        self._status = RangeStatus(self, None)
        return self._status

    def poll(self) -> Optional["RangeStatus"]:
        """Poll the device's current state."""

        res = self.device_poll("ovenState")
        if not res:
            return None

        self._status = RangeStatus(self, res)
        return self._status


class RangeStatus(DeviceStatus):
    """Higher-level information about an range's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(self, device, data):
        super().__init__(device, data)
        self._oven_temp_unit = None

    def _get_oven_temp_unit(self):
        if not self._oven_temp_unit:
            oven_temp_unit = self.lookup_enum("MonTempUnit")
            if not oven_temp_unit:
                self._oven_temp_unit = STATE_OPTIONITEM_NONE
            else:
                self._oven_temp_unit = (
                    OVEN_TEMP_UNIT.get(oven_temp_unit, UNITTEMPMODES.Celsius)
                ).value
        return self._oven_temp_unit

    @property
    def is_on(self):
        return self.is_cooktop_on or self.is_oven_on

    @property
    def oven_temp_unit(self):
        return self._get_oven_temp_unit()

    @property
    def is_cooktop_on(self):
        result = [
            self.cooktop_left_front_state,
            self.cooktop_left_rear_state,
            self.cooktop_center_state,
            self.cooktop_right_front_state,
            self.cooktop_right_rear_state,
        ]
        for r in result:
            if r and r != STATE_OPTIONITEM_OFF:
                return True
        return False

    @property
    def cooktop_left_front_state(self):
        """For some cooktops (maybe depending on firmware or model), the
        five burners do not report individual status. Instead, the 
        cooktop_left_front reports aggregated status for all burners.
        """
        status = self.lookup_enum("LFState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_COOKTOP_LEFT_FRONT_STATE, status
        )

    @property
    def cooktop_left_rear_state(self):
        status = self.lookup_enum("LRState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_COOKTOP_LEFT_REAR_STATE, status
        )

    @property
    def cooktop_center_state(self):
        status = self.lookup_enum("CenterState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_COOKTOP_CENTER_STATE, status
        )

    @property
    def cooktop_right_front_state(self):
        status = self.lookup_enum("RFState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_COOKTOP_RIGHT_FRONT_STATE, status
        )

    @property
    def cooktop_right_rear_state(self):
        status = self.lookup_enum("RRState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_COOKTOP_RIGHT_REAR_STATE, status
        )

    @property
    def is_oven_on(self):
        result = [
            self.oven_lower_state,
            self.oven_upper_state,
        ]
        for r in result:
            if r and r != STATE_OPTIONITEM_OFF:
                return True
        return False
    
    @property
    def oven_lower_state(self):
        status = self.lookup_enum("LowerOvenState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_OVEN_LOWER_STATE, status
        )

    @property
    def oven_upper_state(self):
        status = self.lookup_enum("UpperOvenState")
        if status and status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(
            FEAT_OVEN_UPPER_STATE, status
        )

    @property
    def oven_lower_target_temp(self):
        unit = self.oven_temp_unit
        if unit == UNIT_TEMP_FAHRENHEIT:
            key = "LowerTargetTemp_F"
        elif unit == UNIT_TEMP_CELSIUS:
            key = "LowerTargetTemp_C"
        else:
            return None
        return self._data.get(key)

    @property
    def oven_upper_target_temp(self):
        unit = self.oven_temp_unit
        if unit == UNIT_TEMP_FAHRENHEIT:
            key = "UpperTargetTemp_F"
        elif unit == UNIT_TEMP_CELSIUS:
            key = "UpperTargetTemp_C"
        else:
            return None
        return self._data.get(key)

    @property
    def oven_lower_current_temp(self):
        unit = self.oven_temp_unit
        if unit == UNIT_TEMP_FAHRENHEIT:
            key = "LowerCookTemp_F"
        elif unit == UNIT_TEMP_CELSIUS:
            key = "LowerCookTemp_C"
        else:
            return None
        status = self._data.get(key)
        return self._update_feature(
            FEAT_OVEN_LOWER_CURRENT_TEMP, status, False
        )

    @property
    def oven_upper_current_temp(self):
        unit = self.oven_temp_unit
        if unit == UNIT_TEMP_FAHRENHEIT:
            key = "UpperCookTemp_F"
        elif unit == UNIT_TEMP_CELSIUS:
            key = "UpperCookTemp_C"
        else:
            return None
        status = self._data.get(key)
        return self._update_feature(
            FEAT_OVEN_UPPER_CURRENT_TEMP, status, False
        )

    def _update_features(self):
        result = [
            self.cooktop_left_front_state,
            self.cooktop_left_rear_state,
            self.cooktop_center_state,
            self.cooktop_right_front_state,
            self.cooktop_right_rear_state,
            self.oven_lower_state,
            self.oven_lower_current_temp,
            self.oven_upper_state,
            self.oven_upper_current_temp,
        ]
        return
