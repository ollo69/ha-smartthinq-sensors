"""------------------for Oven"""
from __future__ import annotations

from ..const import BIT_OFF, RangeFeatures, StateOptions, TemperatureUnit
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

OVEN_TEMP_UNIT = {
    "0": TemperatureUnit.FAHRENHEIT,
    "1": TemperatureUnit.CELSIUS,
    "FAHRENHEIT": TemperatureUnit.FAHRENHEIT,
    "CELSIUS": TemperatureUnit.CELSIUS,
}

ITEM_STATE_OFF = "@OV_STATE_INITIAL_W"


class RangeDevice(Device):
    """A higher-level interface for a cooking range."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        super().__init__(client, device_info, RangeStatus(self))

    def reset_status(self):
        self._status = RangeStatus(self)
        return self._status

    async def poll(self) -> RangeStatus | None:
        """Poll the device's current state."""

        res = await self._device_poll("ovenState")
        if not res:
            return None

        self._status = RangeStatus(self, res)
        return self._status


class RangeStatus(DeviceStatus):
    """
    Higher-level information about an range's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(self, device: RangeDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._oven_temp_unit = None

    def _get_oven_temp_unit(self):
        """Get the used temperature unit."""
        if not self._oven_temp_unit:
            oven_temp_unit = self.lookup_enum("MonTempUnit")
            if not oven_temp_unit:
                self._oven_temp_unit = StateOptions.NONE
            else:
                self._oven_temp_unit = OVEN_TEMP_UNIT.get(
                    oven_temp_unit, TemperatureUnit.CELSIUS
                )
        return self._oven_temp_unit

    @property
    def is_on(self):
        """Return if device is on."""
        return self.is_cooktop_on or self.is_oven_on

    @property
    def oven_temp_unit(self):
        """Return used temperature unit."""
        return self._get_oven_temp_unit()

    @property
    def is_cooktop_on(self):
        """Return if cooktop is on."""
        for feature in [
            RangeFeatures.COOKTOP_CENTER_STATE,
            RangeFeatures.COOKTOP_LEFT_FRONT_STATE,
            RangeFeatures.COOKTOP_LEFT_REAR_STATE,
            RangeFeatures.COOKTOP_RIGHT_FRONT_STATE,
            RangeFeatures.COOKTOP_RIGHT_REAR_STATE,
        ]:
            res = self.device_features.get(feature)
            if res and res != StateOptions.OFF:
                return True
        return False

    @property
    def cooktop_left_front_state(self):
        """Return left front cooktop state."""
        # For some cooktops (maybe depending on firmware or model),
        # the five burners do not report individual status.
        # Instead, the cooktop_left_front reports aggregated status for all burners.
        status = self.lookup_enum("LFState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.COOKTOP_LEFT_FRONT_STATE, status)

    @property
    def cooktop_left_rear_state(self):
        """Return left rear cooktop state."""
        status = self.lookup_enum("LRState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.COOKTOP_LEFT_REAR_STATE, status)

    @property
    def cooktop_center_state(self):
        """Return center cooktop state."""
        status = self.lookup_enum("CenterState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.COOKTOP_CENTER_STATE, status)

    @property
    def cooktop_right_front_state(self):
        """Return right front cooktop state."""
        status = self.lookup_enum("RFState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.COOKTOP_RIGHT_FRONT_STATE, status)

    @property
    def cooktop_right_rear_state(self):
        """Return right rear cooktop state."""
        status = self.lookup_enum("RRState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.COOKTOP_RIGHT_REAR_STATE, status)

    @property
    def is_oven_on(self):
        """Return if oven is on."""
        for feature in [
            RangeFeatures.OVEN_LOWER_STATE,
            RangeFeatures.OVEN_UPPER_STATE,
        ]:
            res = self.device_features.get(feature)
            if res and res != StateOptions.OFF:
                return True
        return False

    @property
    def oven_lower_state(self):
        """Return oven lower state."""
        status = self.lookup_enum("LowerOvenState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.OVEN_LOWER_STATE, status)

    @property
    def oven_lower_mode(self):
        """Return oven lower mode."""
        status = self.lookup_enum("LowerCookMode")
        if status is None:
            return None
        return self._update_feature(RangeFeatures.OVEN_LOWER_MODE, status)

    @property
    def oven_upper_state(self):
        """Return oven upper state."""
        status = self.lookup_enum("UpperOvenState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(RangeFeatures.OVEN_UPPER_STATE, status)

    @property
    def oven_upper_mode(self):
        """Return oven upper mode."""
        status = self.lookup_enum("UpperCookMode")
        if status is None:
            return None
        return self._update_feature(RangeFeatures.OVEN_UPPER_MODE, status)

    @property
    def oven_lower_target_temp(self):
        """Return oven lower target temperature."""
        unit = self.oven_temp_unit
        if unit == TemperatureUnit.FAHRENHEIT:
            key = "LowerTargetTemp_F"
        elif unit == TemperatureUnit.CELSIUS:
            key = "LowerTargetTemp_C"
        else:
            return None
        status = self.to_int_or_none(self._data.get(key))
        if not status:  # 0 means not availabe
            status = None
        return status

    @property
    def oven_upper_target_temp(self):
        """Return oven upper target temperature."""
        unit = self.oven_temp_unit
        if unit == TemperatureUnit.FAHRENHEIT:
            key = "UpperTargetTemp_F"
        elif unit == TemperatureUnit.CELSIUS:
            key = "UpperTargetTemp_C"
        else:
            return None
        status = self.to_int_or_none(self._data.get(key))
        if not status:  # 0 means not availabe
            status = None
        return status

    @property
    def oven_lower_current_temp(self):
        """Return oven lower current temperature."""
        unit = self.oven_temp_unit
        if unit == TemperatureUnit.FAHRENHEIT:
            key = "LowerCookTemp_F"
        elif unit == TemperatureUnit.CELSIUS:
            key = "LowerCookTemp_C"
        else:
            return None
        status = self.to_int_or_none(self._data.get(key))
        if not status:  # 0 means not availabe
            status = None
        return self._update_feature(
            RangeFeatures.OVEN_LOWER_CURRENT_TEMP, status, False, allow_none=True
        )

    @property
    def oven_upper_current_temp(self):
        """Return oven upper current temperature."""
        unit = self.oven_temp_unit
        if unit == TemperatureUnit.FAHRENHEIT:
            key = "UpperCookTemp_F"
        elif unit == TemperatureUnit.CELSIUS:
            key = "UpperCookTemp_C"
        else:
            return None
        status = self.to_int_or_none(self._data.get(key))
        if not status:  # 0 means not availabe
            status = None
        return self._update_feature(
            RangeFeatures.OVEN_UPPER_CURRENT_TEMP, status, False, allow_none=True
        )

    def _update_features(self):
        _ = [
            self.cooktop_left_front_state,
            self.cooktop_left_rear_state,
            self.cooktop_center_state,
            self.cooktop_right_front_state,
            self.cooktop_right_rear_state,
            self.oven_lower_state,
            self.oven_lower_mode,
            self.oven_lower_current_temp,
            self.oven_upper_state,
            self.oven_upper_mode,
            self.oven_upper_current_temp,
        ]
