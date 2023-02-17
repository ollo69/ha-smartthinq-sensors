"""Helper class for ThinQ devices"""

from datetime import datetime, timedelta

from homeassistant.const import STATE_OFF, STATE_ON, UnitOfTemperature
from homeassistant.util.dt import utcnow

from .const import DEFAULT_SENSOR
from .wideq import WM_DEVICE_TYPES, DeviceType, StateOptions, TemperatureUnit

STATE_LOOKUP = {
    StateOptions.OFF: STATE_OFF,
    StateOptions.ON: STATE_ON,
}

TEMP_UNIT_LOOKUP = {
    TemperatureUnit.CELSIUS: UnitOfTemperature.CELSIUS,
    TemperatureUnit.FAHRENHEIT: UnitOfTemperature.FAHRENHEIT,
}

DEVICE_ICONS = {
    DeviceType.WASHER: "mdi:washing-machine",
    DeviceType.DRYER: "mdi:tumble-dryer",
    DeviceType.STYLER: "mdi:palette-swatch-outline",
    DeviceType.DISHWASHER: "mdi:dishwasher",
    DeviceType.REFRIGERATOR: "mdi:fridge-outline",
    DeviceType.RANGE: "mdi:stove",
}

WASH_DEVICE_TYPES = [
    *WM_DEVICE_TYPES,
    DeviceType.DISHWASHER,
    DeviceType.STYLER,
]


def get_multiple_devices_types(lge_devices: dict, dev_types: list) -> list:
    """Return a list of devices of multiple types."""
    return [
        dev
        for dev_type, devices in lge_devices.items()
        for dev in devices
        if dev_type in dev_types
    ]


def get_entity_name(device, ent_key, ent_name) -> str:
    """Get the name for the entity"""
    name_slug = device.name
    if ent_key == DEFAULT_SENSOR:
        return name_slug

    name = ent_name or ent_key
    if not ent_name:
        feat_name = device.available_features.get(ent_key)
        if feat_name and feat_name != ent_key:
            name = feat_name.replace("_", " ").capitalize()

    return f"{name_slug} {name}"


class LGEBaseDevice:
    """A wrapper to monitor LGE devices"""

    def __init__(self, api_device):
        """Initialize the device."""
        self._api = api_device

    @staticmethod
    def format_time(hours, minutes):
        """Return a time in format hh:mm:ss based on input hours and minutes."""
        if not minutes:
            return "0:00:00"

        if not hours:
            int_minutes = int(minutes)
            if int_minutes >= 60:
                int_hours = int(int_minutes / 60)
                minutes = str(int_minutes - (int_hours * 60))
                hours = str(int_hours)
            else:
                hours = "0"

        if int(minutes) < 10:
            minutes = f"0{int(minutes)}"
        remain_time = [hours, minutes, "00"]
        return ":".join(remain_time)

    @property
    def device(self):
        """The API device"""
        return self._api.device

    @property
    def is_power_on(self):
        """Current power state"""
        if self._api.state:
            if self._api.state.is_on:
                return True
        return False

    @property
    def power_state(self):
        """Current power state"""
        if self.is_power_on:
            return STATE_ON
        return STATE_OFF

    def get_features_attributes(self):
        """Return a dict with device features and name."""
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
        self._start_time: datetime | None = None

    @property
    def run_completed(self):
        """Return the state on/off for run completed."""
        if self._api.state:
            if self._api.state.is_run_completed:
                return STATE_ON
        return STATE_OFF

    @property
    def error_state(self):
        """Return the state on/off for error."""
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def start_time(self):
        """Return the time and date the wash began or will begin in ISO format."""
        if not (self._api.state and self._api.state.is_on):
            self._start_time = None
            return None

        state = self._api.state
        st_hrs = int(state.remaintime_hour or "0") - int(state.initialtime_hour or "0")
        st_min = int(state.remaintime_min or "0") - int(state.initialtime_min or "0")
        if st_hrs == 0 and st_min == 0:
            self._start_time = None
            hrs = int(state.reservetime_hour or "0")
            mins = int(state.reservetime_min or "0")
            return (utcnow() + timedelta(hours=hrs, minutes=mins)).isoformat()

        if self._start_time is None:
            self._start_time = utcnow() + timedelta(hours=st_hrs, minutes=st_min)
        return self._start_time.isoformat()

    @property
    def end_time(self):
        """Return the time and date the wash will end in ISO format."""
        if not (self._api.state and self._api.state.is_on):
            return None
        state = self._api.state
        hrs = int(state.reservetime_hour or "0") + int(state.remaintime_hour or "0")
        mins = int(state.reservetime_min or "0") + int(state.remaintime_min or "0")
        return (utcnow() + timedelta(hours=hrs, minutes=mins)).isoformat()

    @property
    def initial_time(self):
        """Return the initial time in format HH:MM."""
        if self._api.state:
            if self._api.state.is_on:
                return self.format_time(
                    self._api.state.initialtime_hour, self._api.state.initialtime_min
                )
        return self.format_time(None, None)

    @property
    def remain_time(self):
        """Return the remaining time in format HH:MM."""
        if self._api.state:
            if self._api.state.is_on:
                return self.format_time(
                    self._api.state.remaintime_hour, self._api.state.remaintime_min
                )
        return self.format_time(None, None)

    @property
    def reserve_time(self):
        """Return the reserved time in format HH:MM."""
        if self._api.state:
            if self._api.state.is_on:
                return self.format_time(
                    self._api.state.reservetime_hour, self._api.state.reservetime_min
                )
        return self.format_time(None, None)

    @property
    def current_course(self):
        """Return wash device current course."""
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
        """Return fridge temperature."""
        if self._api.state:
            return self._api.state.temp_fridge
        return None

    @property
    def temp_freezer(self):
        """Return freezer temperature."""
        if self._api.state:
            return self._api.state.temp_freezer
        return None

    @property
    def temp_unit(self):
        """Return refrigerator temperature unit."""
        if self._api.state:
            unit = self._api.state.temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)
        return UnitOfTemperature.CELSIUS

    @property
    def dooropen_state(self):
        """Return refrigerator door open state."""
        if self._api.state:
            state = self._api.state.door_opened_state
            return STATE_LOOKUP.get(state, STATE_OFF)
        return STATE_OFF


class LGETempDevice(LGEBaseDevice):
    """A wrapper to monitor LGE devices that support temperature unit."""

    @property
    def temp_unit(self):
        """Return device temperature unit."""
        unit = self._api.device.temperature_unit
        return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)


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
        """Oven lower target temperature."""
        if self._api.state:
            return self._api.state.oven_lower_target_temp
        return None

    @property
    def oven_upper_target_temp(self):
        """Oven upper target temperature."""
        if self._api.state:
            return self._api.state.oven_upper_target_temp
        return None

    @property
    def oven_temp_unit(self):
        """Oven temperature unit."""
        if self._api.state:
            unit = self._api.state.oven_temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)
        return UnitOfTemperature.CELSIUS
