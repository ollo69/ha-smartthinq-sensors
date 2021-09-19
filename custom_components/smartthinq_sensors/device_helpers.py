import logging

from .wideq.device import (
    STATE_OPTIONITEM_OFF,
    STATE_OPTIONITEM_ON,
    UNIT_TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT,
    WM_DEVICE_TYPES,
    DeviceType,
)

from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)

STATE_LOOKUP = {
    STATE_OPTIONITEM_OFF: STATE_OFF,
    STATE_OPTIONITEM_ON: STATE_ON,
}

TEMP_UNIT_LOOKUP = {
    UNIT_TEMP_CELSIUS: TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT: TEMP_FAHRENHEIT,
}

_LOGGER = logging.getLogger(__name__)

DEVICE_ICONS = {
    DeviceType.WASHER: "mdi:washing-machine",
    DeviceType.DRYER: "mdi:tumble-dryer",
    DeviceType.STYLER: "mdi:palette-swatch-outline",
    DeviceType.DISHWASHER: "mdi:dishwasher",
    DeviceType.REFRIGERATOR: "mdi:fridge-outline",
    DeviceType.RANGE: "mdi:stove",
}

WASH_DEVICE_TYPES = WM_DEVICE_TYPES + [
    DeviceType.DISHWASHER,
    DeviceType.STYLER,
]


class LGEBaseDevice:
    """A wrapper to monitor LGE devices"""
    def __init__(self, api_device):
        """Initialize the device."""
        self._api = api_device

    @staticmethod
    def format_time(hours, minutes):
        if not minutes:
            return "0:00"
        if not hours:
            if int(minutes) >= 60:
                int_minutes = int(minutes)
                int_hours = int(int_minutes / 60)
                minutes = str(int_minutes - (int_hours * 60))
                hours = str(int_hours)
            else:
                hours = "0"
        remain_time = [hours, minutes]
        if int(minutes) < 10:
            return ":0".join(remain_time)
        else:
            return ":".join(remain_time)

    @property
    def power_state(self):
        """Current power state"""
        if self._api.state:
            if self._api.state.is_on:
                return STATE_ON
        return STATE_OFF

    def get_features_attributes(self):
        ret_val = {}
        if self._api.state:
            states = self._api.state.device_features
        else:
            states = {}
        features = self._api.available_features
        for feat_key, feat_name in features.items():
            ret_val[feat_name] = states.get(feat_key)
        return ret_val


class LGEWashDevice(LGEBaseDevice):
    """A wrapper to monitor LGE Wash devices"""

    def __init__(self, api_device):
        """Initialize the device."""
        super().__init__(api_device)
        self._forced_run_completed = False

    @property
    def run_completed(self):
        if self._api.state:
            run_completed = self._api.state.is_run_completed
            if self._api.was_unavailable or self._forced_run_completed:
                self._forced_run_completed = run_completed
            if run_completed and not self._forced_run_completed:
                return STATE_ON
        return STATE_OFF

    @property
    def error_state(self):
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def initial_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGEBaseDevice.format_time(
                    self._api.state.initialtime_hour, self._api.state.initialtime_min
                )
        return "0:00"

    @property
    def remain_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGEBaseDevice.format_time(
                    self._api.state.remaintime_hour, self._api.state.remaintime_min
                )
        return "0:00"

    @property
    def reserve_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGEBaseDevice.format_time(
                    self._api.state.reservetime_hour, self._api.state.reservetime_min
                )
        return "0:00"

    @property
    def current_course(self):
        if self._api.state:
            if self._api.state.is_on:
                course = self._api.state.current_course
                if course:
                    return course
                smart_course = self._api.state.current_smartcourse
                if smart_course:
                    return smart_course
        return "-"


class LGERefrigeratorDevice(LGEBaseDevice):
    """A wrapper to monitor LGE Refrigerator devices"""

    @property
    def temp_fridge(self):
        if self._api.state:
            return self._api.state.temp_fridge
        return None

    @property
    def temp_freezer(self):
        if self._api.state:
            return self._api.state.temp_freezer
        return None

    @property
    def temp_unit(self):
        if self._api.state:
            unit = self._api.state.temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, TEMP_CELSIUS)
        return TEMP_CELSIUS

    @property
    def dooropen_state(self):
        if self._api.state:
            state = self._api.state.door_opened_state
            return STATE_LOOKUP.get(state, STATE_OFF)
        return STATE_OFF


class LGEACDevice(LGEBaseDevice):
    """A wrapper to monitor LGE AC devices"""

    @property
    def curr_temp(self):
        if self._api.state:
            return self._api.state.current_temp
        return None

    @property
    def temp_unit(self):
        unit = self._api.device.temperature_unit
        return TEMP_UNIT_LOOKUP.get(unit, TEMP_CELSIUS)


class LGERangeDevice(LGEBaseDevice):
    """A wrapper to monitor LGE range devices"""

    @property
    def cooktop_state(self):
        """Current cooktop state"""
        if self._api.state:
            if self._api.state.is_cooktop_on:
                return STATE_ON
        return STATE_OFF

    @property
    def oven_state(self):
        """Current oven state"""
        if self._api.state:
            if self._api.state.is_oven_on:
                return STATE_ON
        return STATE_OFF

    @property
    def oven_lower_target_temp(self):
        if self._api.state:
            return self._api.state.oven_lower_target_temp
        return None

    @property
    def oven_upper_target_temp(self):
        if self._api.state:
            return self._api.state.oven_upper_target_temp
        return None

    @property
    def oven_temp_unit(self):
        if self._api.state:
            unit = self._api.state.oven_temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, TEMP_CELSIUS)
        return TEMP_CELSIUS
