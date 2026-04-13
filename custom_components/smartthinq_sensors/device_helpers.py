"""Helper class for ThinQ devices."""

from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.components.climate import HVACMode
from homeassistant.const import STATE_OFF, STATE_ON, UnitOfTemperature
from homeassistant.util.dt import utcnow

from .const import (
    ATTR_CURRENT_COURSE,
    ATTR_DOOR_OPEN,
    ATTR_END_TIME,
    ATTR_ERROR_STATE,
    ATTR_FREEZER_TEMP,
    ATTR_FRIDGE_TEMP,
    ATTR_INITIAL_TIME,
    ATTR_OVEN_LOWER_TARGET_TEMP,
    ATTR_OVEN_TEMP_UNIT,
    ATTR_OVEN_UPPER_TARGET_TEMP,
    ATTR_REMAIN_TIME,
    ATTR_RESERVE_TIME,
    ATTR_RUN_COMPLETED,
    ATTR_START_TIME,
    ATTR_TEMP_UNIT,
    DEFAULT_SENSOR,
)
from .lge_device import LGEDevice
from .wideq import (
    WM_DEVICE_TYPES,
    DeviceType,
    StateOptions,
    TemperatureUnit,
    WashDeviceFeatures,
)
from .wideq.devices.ac import ACMode, AirConditionerDevice

STATE_LOOKUP = {
    StateOptions.OFF: STATE_OFF,
    StateOptions.ON: STATE_ON,
}

TEMP_UNIT_LOOKUP = {
    TemperatureUnit.CELSIUS: UnitOfTemperature.CELSIUS,
    TemperatureUnit.FAHRENHEIT: UnitOfTemperature.FAHRENHEIT,
}

AC_HVAC_MODE_LOOKUP: dict[str, HVACMode] = {
    ACMode.AI.name: HVACMode.AUTO,
    ACMode.HEAT.name: HVACMode.HEAT,
    ACMode.DRY.name: HVACMode.DRY,
    ACMode.COOL.name: HVACMode.COOL,
    ACMode.FAN.name: HVACMode.FAN_ONLY,
    ACMode.ACO.name: HVACMode.HEAT_COOL,
}

DEVICE_ICONS = {
    DeviceType.DISHWASHER: "mdi:dishwasher",
    DeviceType.DRYER: "mdi:tumble-dryer",
    DeviceType.HOOD: "mdi:scent-off",
    DeviceType.MICROWAVE: "mdi:microwave",
    DeviceType.RANGE: "mdi:stove",
    DeviceType.REFRIGERATOR: "mdi:fridge-outline",
    DeviceType.STYLER: "mdi:palette-swatch-outline",
    DeviceType.TOWER_DRYER: "mdi:tumble-dryer",
    DeviceType.TOWER_WASHER: "mdi:washing-machine",
    DeviceType.TOWER_WASHERDRYER: "mdi:washing-machine",
    DeviceType.WASHER: "mdi:washing-machine",
}

WASH_DEVICE_TYPES = [
    *WM_DEVICE_TYPES,
    DeviceType.DISHWASHER,
    DeviceType.STYLER,
]

DEFAULT_SELECTED_COURSE = "Current course"


def get_entity_name(device: LGEDevice, ent_key: str) -> str | None:
    """Get the name for the entity."""
    if ent_key == DEFAULT_SENSOR:
        return None

    name = ent_key.replace("_", " ").capitalize()
    feat_name = device.available_features.get(ent_key)
    if feat_name and feat_name != ent_key:
        name = feat_name.replace("_", " ").capitalize()

    return name


class LGEBaseDevice:
    """A wrapper to monitor LGE devices."""

    def __init__(self, api_device: LGEDevice) -> None:
        """Initialize the device."""
        self._api = api_device

    @staticmethod
    def format_time(hours: Any, minutes: Any) -> str:
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
        else:
            hours = str(int(hours))

        if int(minutes) < 10:
            minutes = f"0{int(minutes)}"
        else:
            minutes = str(int(minutes))
        remain_time = [hours, minutes, "00"]
        return ":".join(remain_time)

    @property
    def device(self) -> Any:
        """The API device."""
        return self._api.device

    @property
    def is_power_on(self) -> bool:
        """Current power state."""
        if self._api.type in WM_DEVICE_TYPES or self._api.type == DeviceType.DISHWASHER:
            logical_prefix = {
                DeviceType.WASHER: "washer",
                DeviceType.DRYER: "dryer",
                DeviceType.DISHWASHER: "dishwasher",
            }.get(self._api.type)
            if logical_prefix:
                hybrid_run_state = self._api.get_hybrid_value(
                    f"{logical_prefix}.run_state"
                )
                if isinstance(hybrid_run_state, str):
                    normalized_run_state = hybrid_run_state.lower()
                    if normalized_run_state in {"power_off", "off", "none"}:
                        return False
                    return True
            if self._api.state and not self._api.state.is_on:
                return False

        logical_key = {
            DeviceType.WASHER: "washer.is_on",
            DeviceType.DRYER: "dryer.is_on",
            DeviceType.DISHWASHER: "dishwasher.is_on",
            DeviceType.FAN: "fan.is_on",
            DeviceType.AIR_PURIFIER: "air_purifier.is_on",
            DeviceType.HOOD: "hood.is_on",
            DeviceType.MICROWAVE: "microwave.is_on",
        }.get(self._api.type)
        if logical_key:
            hybrid_is_on = self._api.get_hybrid_value(logical_key)
            if hybrid_is_on is not None:
                return bool(hybrid_is_on)
        if self._api.state:
            if self._api.state.is_on:
                return True
        return False

    @property
    def power_state(self) -> str:
        """Current power state."""
        if self.is_power_on:
            return STATE_ON
        return STATE_OFF

    @property
    def ssid(self) -> str | None:
        """The device network SSID."""
        ssid = self._api.device.device_info.ssid
        return str(ssid) if ssid is not None else None

    @property
    def power_save_enabled(self) -> bool:
        """Return whether AC power save is enabled."""
        if self._api.type != DeviceType.AC:
            return False

        value = self._api.get_hybrid_value("ac.power_save_enabled")
        if value is not None:
            return bool(value)

        operation_mode = getattr(self._api.state, "operation_mode", None)
        return operation_mode in {ACMode.ENERGY_SAVING.name, ACMode.ENERGY_SAVER.name}

    def get_features_attributes(self) -> dict[str | None, Any]:
        """Return a dict with device features and name."""
        ret_val: dict[str | None, Any] = {}
        if self._api.state:
            states = self._api.state.device_features
        else:
            states = {}
        features = self._api.available_features
        for feat_key, feat_name in features.items():
            ret_val[feat_name] = states.get(feat_key)
        return ret_val

    @property
    def extra_state_attributes(self) -> dict[str | None, Any]:
        """Return the optional state attributes."""
        return self.get_features_attributes()


class LGEWashDevice(LGEBaseDevice):
    """A wrapper to monitor LGE Wash devices."""

    def __init__(self, api_device: LGEDevice) -> None:
        """Initialize the device."""
        super().__init__(api_device)
        self._start_time: datetime | None = None

    @property
    def run_completed(self) -> str:
        """Return the state on/off for device run completed."""
        if self._api.device.is_run_completed:
            return STATE_ON
        return STATE_OFF

    @property
    def error_state(self) -> str:
        """Return the state on/off for error."""
        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            error_message = self._api.get_hybrid_value(f"{logical_prefix}.error_message")
            if error_message not in (None, "", StateOptions.NONE):
                return STATE_ON
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def start_time(self) -> str | None:
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
    def end_time(self) -> str | None:
        """Return the time and date the wash will end in ISO format."""
        if not (self._api.state and self._api.state.is_on):
            return None
        state = self._api.state
        hrs = int(state.reservetime_hour or "0") + int(state.remaintime_hour or "0")
        mins = int(state.reservetime_min or "0") + int(state.remaintime_min or "0")
        return (utcnow() + timedelta(hours=hrs, minutes=mins)).isoformat()

    @property
    def initial_time(self) -> str:
        """Return the initial time in format HH:MM."""
        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            initial_hour = self._api.get_hybrid_value(
                f"{logical_prefix}.timer_total_hour"
            )
            initial_minute = self._api.get_hybrid_value(
                f"{logical_prefix}.timer_total_minute"
            )
            if initial_hour is not None or initial_minute is not None:
                return self.format_time(initial_hour, initial_minute)
        if self._api.state:
            if self._api.state.is_on:
                return self.format_time(
                    self._api.state.initialtime_hour, self._api.state.initialtime_min
                )
        return self.format_time(None, None)

    @property
    def remain_time(self) -> str:
        """Return the remaining time in format HH:MM."""
        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            remain_hour = self._api.get_hybrid_value(f"{logical_prefix}.remain_hour")
            remain_minute = self._api.get_hybrid_value(f"{logical_prefix}.remain_minute")
            if remain_hour is not None or remain_minute is not None:
                return self.format_time(remain_hour, remain_minute)
        if self._api.state:
            if self._api.state.is_on:
                return self.format_time(
                    self._api.state.remaintime_hour, self._api.state.remaintime_min
                )
        return self.format_time(None, None)

    @property
    def reserve_time(self) -> str:
        """Return the reserved time in format HH:MM."""
        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            if self._api.type == DeviceType.DISHWASHER:
                reserve_time_set = self._api.get_hybrid_value(
                    "dishwasher.timer_relative_start_set"
                )
                reserve_hour = self._api.get_hybrid_value(
                    "dishwasher.timer_relative_start_hour"
                )
                reserve_minute = self._api.get_hybrid_value(
                    "dishwasher.timer_relative_start_minute"
                )
                if reserve_time_set is False:
                    return self.format_time(None, None)
                if reserve_hour is not None or reserve_minute is not None:
                    return self.format_time(reserve_hour, reserve_minute)
            reserve_time_set = self._api.get_hybrid_value(
                f"{logical_prefix}.timer_relative_stop_set"
            )
            reserve_hour = self._api.get_hybrid_value(
                f"{logical_prefix}.timer_relative_stop_hour"
            )
            reserve_minute = self._api.get_hybrid_value(
                f"{logical_prefix}.timer_relative_stop_minute"
            )
            if reserve_time_set is False:
                return self.format_time(None, None)
            if reserve_hour is not None or reserve_minute is not None:
                return self.format_time(reserve_hour, reserve_minute)
        if self._api.state:
            if self._api.state.is_on:
                return self.format_time(
                    self._api.state.reservetime_hour, self._api.state.reservetime_min
                )
        return self.format_time(None, None)

    @property
    def current_course(self) -> str:
        """Return wash device current course."""
        logical_key = {
            DeviceType.WASHER: "washer.current_course",
            DeviceType.DRYER: "dryer.current_course",
            DeviceType.DISHWASHER: "dishwasher.current_course",
        }.get(self._api.type)
        if logical_key:
            hybrid_course = self._api.get_hybrid_value(logical_key)
            if hybrid_course not in (None, ""):
                return str(hybrid_course)
        selected_course = getattr(self._api.device, "selected_course", None)
        if selected_course not in (None, "", DEFAULT_SELECTED_COURSE):
            return str(selected_course)
        if self._api.state:
            if self._api.state.is_on:
                course = self._api.state.current_course
                if course:
                    return str(course)
                smart_course = self._api.state.current_smartcourse
                if smart_course:
                    return str(smart_course)
        return "-"

    @staticmethod
    def _normalize_binary_feature_value(value: Any) -> Any:
        """Normalize binary-like values to on/off strings for attributes."""
        if isinstance(value, bool):
            return STATE_ON if value else STATE_OFF
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"open", "opened", "set", "on", "true"}:
                return STATE_ON
            if normalized in {"close", "closed", "unset", "off", "false"}:
                return STATE_OFF
        return value

    @staticmethod
    def _normalize_dishwasher_preference_value(key: str, value: Any) -> str | None:
        """Normalize dishwasher preference enums into user-friendly values."""
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return STATE_ON if value else STATE_OFF

        normalized = str(value).strip()
        upper = normalized.upper()

        binary_prefixes = {
            "clean_l_reminder": "CLEANLREMINDER_",
            "machine_clean_reminder": "MCREMINDER_",
            "signal_level": "SIGNALLEVEL_",
        }
        if prefix := binary_prefixes.get(key):
            if upper.startswith(prefix):
                upper = upper.removeprefix(prefix)
            return cast(
                str | None, LGEWashDevice._normalize_binary_feature_value(upper)
            )

        level_prefixes = {
            "rinse_level": "RINSELEVEL_",
            "softening_level": "SOFTENINGLEVEL_",
        }
        if prefix := level_prefixes.get(key):
            if upper.startswith(prefix):
                level_value = upper.removeprefix(prefix)
            else:
                level_value = normalized
            return level_value

        return normalized

    @staticmethod
    def _normalize_dishwasher_numeric_level(key: str, value: Any) -> int | None:
        """Normalize dishwasher enum-like level values into integers."""
        normalized = LGEWashDevice._normalize_dishwasher_preference_value(key, value)
        if normalized in (None, ""):
            return None
        try:
            return int(str(normalized))
        except (TypeError, ValueError):
            return None

    @property
    def rinse_level(self) -> int | None:
        """Return dishwasher rinse level."""
        if self._api.type != DeviceType.DISHWASHER:
            return None
        value = self._api.get_hybrid_value("dishwasher.rinse_level")
        if value not in (None, ""):
            return self._normalize_dishwasher_numeric_level("rinse_level", value)
        if self._api.state:
            feature_value = self._api.state.device_features.get(
                WashDeviceFeatures.RINSELEVEL
            )
            if feature_value not in (None, ""):
                return self._normalize_dishwasher_numeric_level(
                    "rinse_level", feature_value
                )
        return None

    def get_dishwasher_preference(self, key: str) -> str | None:
        """Return one dishwasher preference value."""
        if self._api.type != DeviceType.DISHWASHER:
            return None
        value = self._api.get_hybrid_value(f"dishwasher.{key}")
        if value not in (None, ""):
            return self._normalize_dishwasher_preference_value(key, value)
        return None

    @property
    def softening_level(self) -> int | None:
        """Return dishwasher softening level."""
        if self._api.type != DeviceType.DISHWASHER:
            return None
        value = self._api.get_hybrid_value("dishwasher.softening_level")
        if value not in (None, ""):
            return self._normalize_dishwasher_numeric_level(
                "softening_level", value
            )
        if self._api.state:
            feature_value = self._api.state.device_features.get(
                WashDeviceFeatures.SOFTENING_LEVEL
            )
            if feature_value not in (None, ""):
                return self._normalize_dishwasher_numeric_level(
                    "softening_level", feature_value
                )
        return None

    @property
    def extra_state_attributes(self) -> dict[str | None, Any]:
        """Return the optional state attributes."""
        data: dict[str | None, Any] = {
            ATTR_RUN_COMPLETED: self.run_completed,
            ATTR_ERROR_STATE: self.error_state,
            ATTR_START_TIME: self.start_time,
            ATTR_END_TIME: self.end_time,
            ATTR_INITIAL_TIME: self.initial_time,
            ATTR_REMAIN_TIME: self.remain_time,
            ATTR_RESERVE_TIME: self.reserve_time,
            ATTR_CURRENT_COURSE: self.current_course,
        }
        features = super().extra_state_attributes
        data.update(features)

        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            hybrid_feature_keys = {
                "run_state": f"{logical_prefix}.run_state",
                "process_state": f"{logical_prefix}.process_state",
                "error_message": f"{logical_prefix}.error_message",
                "door_open": f"{logical_prefix}.door_open",
                "rinse_refill": f"{logical_prefix}.rinse_refill",
                "rinse_level": f"{logical_prefix}.rinse_level",
                "clean_l_reminder": f"{logical_prefix}.clean_l_reminder",
                "machine_clean_reminder": f"{logical_prefix}.machine_clean_reminder",
                "signal_level": f"{logical_prefix}.signal_level",
                "softening_level": f"{logical_prefix}.softening_level",
            }
            binary_feature_keys = {"door_open", "rinse_refill"}
            for attr_key, logical_key in hybrid_feature_keys.items():
                value = self._api.get_hybrid_value(logical_key)
                if value is None:
                    continue
                if attr_key in binary_feature_keys:
                    value = self._normalize_binary_feature_value(value)
                elif self._api.type == DeviceType.DISHWASHER and attr_key in {
                    "rinse_level",
                    "clean_l_reminder",
                    "machine_clean_reminder",
                    "signal_level",
                    "softening_level",
                }:
                    normalized_value = self._normalize_dishwasher_preference_value(
                        attr_key, value
                    )
                    if normalized_value is not None:
                        value = normalized_value
                data[attr_key] = value

        return data


class LGERefrigeratorDevice(LGEBaseDevice):
    """A wrapper to monitor LGE Refrigerator devices."""

    @property
    def supports_fridge_compartment(self) -> bool:
        """Return whether the refrigerator has a fridge compartment."""
        return bool(self._api.device.supports_fridge_compartment())

    @property
    def supports_freezer_compartment(self) -> bool:
        """Return whether the refrigerator has a freezer compartment."""
        return bool(self._api.device.supports_freezer_compartment())

    @property
    def temp_fridge(self) -> Any:
        """Return fridge temperature."""
        if self.supports_fridge_compartment:
            value = self._api.get_hybrid_value(
                "refrigerator.fridge_temperature",
                self._api.state.temp_fridge if self._api.state else None,
            )
            if value is not None:
                return value
        return None

    @property
    def temp_freezer(self) -> Any:
        """Return freezer temperature."""
        if self.supports_freezer_compartment:
            value = self._api.get_hybrid_value(
                "refrigerator.freezer_temperature",
                self._api.state.temp_freezer if self._api.state else None,
            )
            if value is not None:
                return value
        return None

    @property
    def temp_unit(self) -> Any:
        """Return refrigerator temperature unit."""
        unit = self._api.get_hybrid_value(
            "refrigerator.temp_unit",
            self._api.state.temp_unit if self._api.state else None,
        )
        if unit is not None:
            return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)
        return UnitOfTemperature.CELSIUS

    @property
    def dooropen_state(self) -> str:
        """Return refrigerator door open state."""
        state = self._api.get_hybrid_value(
            "refrigerator.door_open",
            self._api.state.door_opened_state if self._api.state else None,
        )
        if state is not None:
            return STATE_LOOKUP.get(state, STATE_OFF)
        return STATE_OFF

    @property
    def power_save_enabled(self) -> bool:
        """Return whether refrigerator power save is enabled."""
        value = self._api.get_hybrid_value("refrigerator.power_save_enabled")
        if isinstance(value, bool):
            return value
        return False

    @property
    def extra_state_attributes(self) -> dict[str | None, Any]:
        """Return the optional state attributes."""
        data: dict[str | None, Any] = {
            ATTR_TEMP_UNIT: self.temp_unit,
            ATTR_DOOR_OPEN: self.dooropen_state,
        }
        if self.supports_fridge_compartment:
            data[ATTR_FRIDGE_TEMP] = self.temp_fridge
        if self.supports_freezer_compartment:
            data[ATTR_FREEZER_TEMP] = self.temp_freezer
        features = super().extra_state_attributes
        data.update(features)

        return data


class LGETempDevice(LGEBaseDevice):
    """A wrapper to monitor LGE devices that support temperature unit."""

    @property
    def temp_unit(self) -> Any:
        """Return device temperature unit."""
        unit = self._api.device.temperature_unit
        return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)


class LGEACDevice(LGETempDevice):
    """A wrapper to monitor LGE AC devices with hybrid-aware state."""

    def _normalize_enum_value(
        self,
        value: Any,
        supported_values: list[str],
        *,
        aliases: dict[str, str] | None = None,
    ) -> str | None:
        """Normalize hybrid/community values to the device's enum names."""
        if value is None:
            return None

        normalized = str(value).strip()
        if normalized in supported_values:
            return normalized

        upper_value = normalized.upper().replace("-", "_").replace(" ", "_")
        for candidate in (upper_value, upper_value.title()):
            if candidate in supported_values:
                return candidate

        if aliases and (aliased := aliases.get(upper_value)) in supported_values:
            return aliased

        return normalized

    @property
    def device(self) -> AirConditionerDevice:
        """Return the wrapped AC device."""
        return cast(AirConditionerDevice, self._api.device)

    @property
    def is_on(self) -> bool:
        """Return the best current AC power state."""
        return bool(self._api.get_hybrid_value("ac.is_on", self._api.state.is_on))

    @property
    def operation_mode(self) -> str | None:
        """Return the best current AC operation mode."""
        value = self._api.get_hybrid_value(
            "ac.operation_mode", self._api.state.operation_mode
        )
        alias_map = {
            "AIR_DRY": ACMode.DRY.name,
            "DRY": ACMode.DRY.name,
            "FAN": ACMode.FAN.name,
            "AUTO": ACMode.AI.name if ACMode.AI.name in self.device.op_modes else "AUTO",
        }
        normalized = self._normalize_enum_value(
            value, self.device.op_modes, aliases=alias_map
        )
        if normalized in self.device.op_modes:
            return normalized

        return str(self._api.state.operation_mode) if self._api.state.operation_mode else normalized

    @property
    def current_temperature(self) -> float:
        """Return the best current AC temperature."""
        return float(
            self._api.get_hybrid_value("ac.current_temperature", self._api.state.current_temp)
        )

    @property
    def target_temperature(self) -> float:
        """Return the best current AC target temperature."""
        return float(
            self._api.get_hybrid_value("ac.target_temperature", self._api.state.target_temp)
        )

    @property
    def current_humidity(self) -> int | None:
        """Return the best current AC humidity."""
        value = self._api.get_hybrid_value(
            "ac.current_humidity",
            self._api.state.device_features.get("humidity"),
        )
        return int(value) if value is not None else None

    @property
    def power_save_enabled(self) -> bool:
        """Return whether AC power save is enabled."""
        value = self._api.get_hybrid_value("ac.power_save_enabled")
        if value is not None:
            return bool(value)
        return self.operation_mode in {ACMode.ENERGY_SAVING.name, ACMode.ENERGY_SAVER.name}

    @property
    def fan_speed(self) -> str | None:
        """Return the best current AC fan speed."""
        value = self._api.get_hybrid_value("ac.fan_speed", self._api.state.fan_speed)
        normalized = self._normalize_enum_value(value, self.device.fan_speeds)
        if normalized in self.device.fan_speeds:
            return normalized
        return self._api.state.fan_speed or normalized

    @property
    def vertical_step_mode(self) -> str | None:
        """Return the best current AC vertical step mode."""
        value = self._api.get_hybrid_value(
            "ac.vertical_step_mode", self._api.state.vertical_step_mode
        )
        normalized = self._normalize_enum_value(value, self.device.vertical_step_modes)
        if normalized in self.device.vertical_step_modes:
            return normalized
        return self._api.state.vertical_step_mode or normalized

    @property
    def horizontal_step_mode(self) -> str | None:
        """Return the best current AC horizontal step mode."""
        value = self._api.get_hybrid_value(
            "ac.horizontal_step_mode", self._api.state.horizontal_step_mode
        )
        normalized = self._normalize_enum_value(value, self.device.horizontal_step_modes)
        if normalized in self.device.horizontal_step_modes:
            return normalized
        return self._api.state.horizontal_step_mode or normalized


class LGERangeDevice(LGEBaseDevice):
    """A wrapper to monitor LGE range devices."""

    @property
    def cooktop_state(self) -> str:
        """Current cooktop state."""
        if self._api.state:
            if self._api.state.is_cooktop_on:
                return STATE_ON
        return STATE_OFF

    @property
    def oven_state(self) -> str:
        """Current oven state."""
        if self._api.state:
            if self._api.state.is_oven_on:
                return STATE_ON
        return STATE_OFF

    @property
    def oven_lower_target_temp(self) -> Any:
        """Oven lower target temperature."""
        if self._api.state:
            return self._api.state.oven_lower_target_temp
        return None

    @property
    def oven_upper_target_temp(self) -> Any:
        """Oven upper target temperature."""
        if self._api.state:
            return self._api.state.oven_upper_target_temp
        return None

    @property
    def oven_temp_unit(self) -> Any:
        """Oven temperature unit."""
        if self._api.state:
            unit = self._api.state.oven_temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)
        return UnitOfTemperature.CELSIUS

    @property
    def extra_state_attributes(self) -> dict[str | None, Any]:
        """Return the optional state attributes."""
        data: dict[str | None, Any] = {
            ATTR_OVEN_LOWER_TARGET_TEMP: self.oven_lower_target_temp,
            ATTR_OVEN_UPPER_TARGET_TEMP: self.oven_upper_target_temp,
            ATTR_OVEN_TEMP_UNIT: self.oven_temp_unit,
        }
        features = super().extra_state_attributes
        data.update(features)

        return data


def get_wrapper_device(
    lge_device: LGEDevice, dev_type: DeviceType
) -> LGEBaseDevice | None:
    """Return a wrapper device for specific device type."""
    if dev_type in WASH_DEVICE_TYPES:
        return LGEWashDevice(lge_device)
    if dev_type == DeviceType.REFRIGERATOR:
        return LGERefrigeratorDevice(lge_device)
    if dev_type == DeviceType.RANGE:
        return LGERangeDevice(lge_device)
    if dev_type == DeviceType.AC:
        return LGEACDevice(lge_device)
    if dev_type == DeviceType.WATER_HEATER:
        return LGETempDevice(lge_device)
    if dev_type in (DeviceType.HOOD, DeviceType.MICROWAVE):
        return LGEBaseDevice(lge_device)
    return None
