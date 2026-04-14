"""ThinQ device wrapper used by platform entities."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .const import DOMAIN, SIGNAL_RELOAD_ENTRY
from .coordinator_hybrid import HybridDataCoordinator
from .runtime_data import (
    get_capability_registry,
    get_data_source_router,
    get_hybrid_coordinators,
)
from .wideq import DeviceType, WashDeviceFeatures
from .wideq.core_exceptions import (
    InvalidCredentialError,
    MonitorRefreshError,
    MonitorUnavailableError,
    NotConnectedError,
)
from .wideq.device import Device as ThinQDevice

MAX_DISC_COUNT = 4
SCAN_INTERVAL = timedelta(seconds=30)
_LOGGER = logging.getLogger(__name__)


class LGEDevice:
    """Generic class that represents a LGE device."""

    def __init__(
        self, device: ThinQDevice, hass: HomeAssistant, root_dev_id: str | None = None
    ) -> None:
        """Initialize a LGE device."""
        self._device: Any = device
        self._hass = hass
        self._root_dev_id = root_dev_id
        self._name = device.name
        self._device_id = device.unique_id
        self._type = device.device_info.type
        self._mac = None
        if mac := device.device_info.macaddress:
            self._mac = dr.format_mac(mac)
        self._firmware = device.device_info.firmware

        self._model = f"{device.device_info.model_name}"
        self._unique_id = f"{self._type.name}:{self._device_id}"

        self._state: Any = None
        self._coordinator: DataUpdateCoordinator[Any] | None = None
        self._disc_count = 0
        self._available = True
        self._last_mqtt_update: datetime | None = None

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self._available

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._available and self._disc_count >= MAX_DISC_COUNT

    @property
    def device(self) -> Any:
        """The device instance."""
        return self._device

    @property
    def device_id(self) -> str:
        """The device unique identifier."""
        return self._device_id

    @property
    def hass(self) -> HomeAssistant:
        """Return the Home Assistant instance."""
        return self._hass

    @property
    def name(self) -> str:
        """The device name."""
        return self._name

    @property
    def type(self) -> DeviceType:
        """The device type."""
        return self._type

    @property
    def unique_id(self) -> str:
        """Device unique ID."""
        return self._unique_id

    @property
    def state(self) -> Any:
        """Current device state."""
        return self._state

    def get_hybrid_value(self, attribute_id: str, default: Any = None) -> Any:
        """Return the best available logical attribute value from hybrid routing."""
        data_source_router = get_data_source_router(self._hass)
        capability_registry = get_capability_registry(self._hass)
        if data_source_router is None or capability_registry is None:
            return default

        profile = capability_registry.get_profile(self._device_id)
        if profile is None:
            return default

        value, source = data_source_router.get_attribute_value(
            self._device_id,
            attribute_id,
            fallback_strategy="polling",
        )
        if source in {"official", "polling", "official_stale", "polling_stale"}:
            return value if value is not None else default
        return default

    @property
    def last_mqtt_update(self) -> datetime | None:
        """Return the timestamp of the last MQTT-driven state update."""
        return self._last_mqtt_update

    @property
    def available_features(self) -> dict[Any, Any]:
        """Return a list of available features."""
        return cast(dict[Any, Any], self._device.available_features)

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Return device info for the device."""
        data = dr.DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._name,
            manufacturer="LG",
            model=f"{self._model} ({self._type.name})",
        )
        if self._firmware:
            data["sw_version"] = self._firmware
        if self._mac and not self._root_dev_id:
            data["connections"] = {(dr.CONNECTION_NETWORK_MAC, self._mac)}
        if self._root_dev_id:
            data["via_device"] = (DOMAIN, self._root_dev_id)

        return data

    @property
    def coordinator(self) -> DataUpdateCoordinator[Any]:
        """Return the DataUpdateCoordinator used by this device."""
        if self._coordinator is None:
            raise RuntimeError("Device coordinator is not initialized")
        return self._coordinator

    async def init_device(self) -> bool:
        """Init the device status and start coordinator."""
        if not await self._device.init_device_info():
            return False
        self._state = self._device.status
        if self._state is None:
            return False
        self._model = f"{self._model}-{self._device.model_info.model_type}"

        await self._create_coordinator()
        _ = self._state.device_features
        self._record_state_in_registry()
        return True

    @callback
    def async_set_updated(self) -> None:
        """Manually update state and notify coordinator entities."""
        if self._coordinator:
            self._coordinator.async_set_updated_data(self._state)

    def _get_registry_alias_values(self) -> dict[str, Any]:
        """Return curated logical attributes for hybrid source routing."""
        if self._state is None:
            return {}

        state = self._state
        aliases: dict[str, Any] = {}

        def _normalize_alias_key(key: Any) -> str:
            if hasattr(key, "name"):
                return str(key.name).lower()
            return str(key).lower()

        if self._type == DeviceType.AC:
            operation_mode = getattr(state, "operation_mode", None)
            aliases = {
                "ac.is_on": getattr(state, "is_on", None),
                "ac.operation_mode": operation_mode,
                "ac.current_temperature": getattr(state, "current_temp", None),
                "ac.target_temperature": getattr(state, "target_temp", None),
                "ac.current_humidity": getattr(state, "humidity", None),
                "ac.fan_speed": getattr(state, "fan_speed", None),
                "ac.vertical_step_mode": getattr(state, "vertical_step_mode", None),
                "ac.horizontal_step_mode": getattr(state, "horizontal_step_mode", None),
                "ac.pm1": getattr(state, "pm1", None),
                "ac.pm10": getattr(state, "pm10", None),
                "ac.pm25": getattr(state, "pm25", None),
                "ac.power_save_enabled": operation_mode
                in {"ENERGY_SAVING", "ENERGY_SAVER"},
                "ac.power_current": getattr(state, "energy_current", None),
            }
            if hasattr(state, "filters_life") and isinstance(state.filters_life, dict):
                for key, value in state.filters_life.items():
                    aliases[f"ac.filter.{_normalize_alias_key(key)}"] = value
        elif self._type == DeviceType.REFRIGERATOR:
            aliases = {
                "refrigerator.temp_unit": getattr(state, "temp_unit", None),
                "refrigerator.door_open": getattr(state, "door_opened_state", None),
                "refrigerator.eco_friendly": getattr(state, "eco_friendly_enabled", None),
                "refrigerator.express_fridge": getattr(
                    state, "express_fridge_status", None
                ),
                "refrigerator.express_mode": getattr(state, "express_mode_status", None),
                "refrigerator.fresh_air_filter": getattr(
                    state, "fresh_air_filter_status", None
                ),
                "refrigerator.fresh_air_filter_remain_perc": getattr(
                    state, "fresh_air_filter_remain_perc", None
                ),
                "refrigerator.water_filter": getattr(
                    state, "water_filter_remain_perc", None
                ),
            }
            if self._device.supports_fridge_compartment():
                aliases["refrigerator.fridge_temperature"] = getattr(
                    state, "temp_fridge", None
                )
            if self._device.supports_freezer_compartment():
                aliases["refrigerator.freezer_temperature"] = getattr(
                    state, "temp_freezer", None
                )
        elif self._type == DeviceType.WATER_HEATER:
            aliases = {
                "water_heater.is_on": getattr(state, "is_on", None),
                "water_heater.operation_mode": getattr(state, "operation_mode", None),
                "water_heater.current_temperature": getattr(state, "current_temp", None),
                "water_heater.target_temperature": getattr(state, "target_temp", None),
                "water_heater.power_current": getattr(state, "energy_current", None),
            }
        elif self._type == DeviceType.AIR_PURIFIER:
            aliases = {
                "air_purifier.is_on": getattr(state, "is_on", None),
                "air_purifier.operation": getattr(state, "operation", None),
                "air_purifier.operation_mode": getattr(state, "operation_mode", None),
                "air_purifier.fan_speed": getattr(state, "fan_speed", None),
                "air_purifier.fan_preset": getattr(state, "fan_preset", None),
                "air_purifier.current_humidity": getattr(state, "current_humidity", None),
                "air_purifier.pm1": getattr(state, "pm1", None),
                "air_purifier.pm10": getattr(state, "pm10", None),
                "air_purifier.pm25": getattr(state, "pm25", None),
            }
            if hasattr(state, "filters_life") and isinstance(state.filters_life, dict):
                for key, value in state.filters_life.items():
                    aliases[f"air_purifier.filter.{_normalize_alias_key(key)}"] = value
        elif self._type == DeviceType.FAN:
            aliases = {
                "fan.is_on": getattr(state, "is_on", None),
                "fan.operation": getattr(state, "operation", None),
                "fan.fan_speed": getattr(state, "fan_speed", None),
            }
        elif self._type == DeviceType.DEHUMIDIFIER:
            aliases = {
                "dehumidifier.is_on": getattr(state, "is_on", None),
                "dehumidifier.operation": getattr(state, "operation", None),
                "dehumidifier.operation_mode": getattr(state, "operation_mode", None),
                "dehumidifier.fan_speed": getattr(state, "fan_speed", None),
                "dehumidifier.current_humidity": getattr(state, "current_humidity", None),
                "dehumidifier.target_humidity": getattr(state, "target_humidity", None),
                "dehumidifier.water_tank_full": getattr(state, "water_tank_full", None),
            }
        elif self._type == DeviceType.HOOD:
            aliases = {
                "hood.is_on": getattr(state, "is_on", None),
                "hood.state": getattr(state, "hood_state", None),
                "hood.light_mode": getattr(state, "light_mode", None),
                "hood.vent_speed": getattr(state, "vent_speed", None),
            }
        elif self._type == DeviceType.MICROWAVE:
            aliases = {
                "microwave.is_on": getattr(state, "is_on", None),
                "microwave.oven_upper_state": getattr(state, "oven_upper_state", None),
                "microwave.oven_upper_mode": getattr(state, "oven_upper_mode", None),
                "microwave.clock_display": getattr(state, "is_clock_display_on", None),
                "microwave.sound": getattr(state, "is_sound_on", None),
                "microwave.weight_unit": getattr(state, "weight_unit", None),
                "microwave.display_scroll_speed": getattr(
                    state, "display_scroll_speed", None
                ),
            }
        elif self._type == DeviceType.RANGE:
            aliases = {
                "range.is_on": getattr(state, "is_on", None),
                "range.cooktop_on": getattr(state, "is_cooktop_on", None),
                "range.oven_on": getattr(state, "is_oven_on", None),
                "range.oven_temp_unit": getattr(state, "oven_temp_unit", None),
                "range.oven_lower_state": getattr(state, "oven_lower_state", None),
                "range.oven_upper_state": getattr(state, "oven_upper_state", None),
                "range.oven_lower_mode": getattr(state, "oven_lower_mode", None),
                "range.oven_upper_mode": getattr(state, "oven_upper_mode", None),
                "range.oven_lower_target_temperature": getattr(
                    state, "oven_lower_target_temp", None
                ),
                "range.oven_upper_target_temperature": getattr(
                    state, "oven_upper_target_temp", None
                ),
                "range.oven_lower_current_temperature": getattr(
                    state, "oven_lower_current_temp", None
                ),
                "range.oven_upper_current_temperature": getattr(
                    state, "oven_upper_current_temp", None
                ),
            }
        elif self._type == DeviceType.WASHER:
            selected_course = getattr(self._device, "selected_course", None)
            aliases = {
                "washer.is_on": getattr(state, "is_on", None),
                "washer.run_state": getattr(state, "run_state", None),
                "washer.remote_control_enabled": getattr(
                    state, "remote_control_enabled", None
                ),
                "washer.error_message": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.ERROR_MSG
                ),
                "washer.door_open": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.DOOROPEN
                ),
                "washer.timer_total_hour": getattr(state, "initialtime_hour", None),
                "washer.timer_total_minute": getattr(state, "initialtime_min", None),
                "washer.remain_hour": getattr(state, "remaintime_hour", None),
                "washer.remain_minute": getattr(state, "remaintime_min", None),
                "washer.timer_relative_stop_hour": getattr(
                    state, "reservetime_hour", None
                ),
                "washer.timer_relative_stop_minute": getattr(
                    state, "reservetime_min", None
                ),
                "washer.process_state": getattr(state, "process_state", None),
                "washer.current_course": getattr(state, "current_course", None)
                or (
                    selected_course
                    if selected_course not in (None, "", "Current course")
                    else None
                ),
            }
        elif self._type == DeviceType.DRYER:
            selected_course = getattr(self._device, "selected_course", None)
            aliases = {
                "dryer.is_on": getattr(state, "is_on", None),
                "dryer.run_state": getattr(state, "run_state", None),
                "dryer.remote_control_enabled": getattr(
                    state, "remote_control_enabled", None
                ),
                "dryer.error_message": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.ERROR_MSG
                ),
                "dryer.door_open": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.DOOROPEN
                ),
                "dryer.timer_total_hour": getattr(state, "initialtime_hour", None),
                "dryer.timer_total_minute": getattr(state, "initialtime_min", None),
                "dryer.remain_hour": getattr(state, "remaintime_hour", None),
                "dryer.remain_minute": getattr(state, "remaintime_min", None),
                "dryer.timer_relative_stop_hour": getattr(
                    state, "reservetime_hour", None
                ),
                "dryer.timer_relative_stop_minute": getattr(
                    state, "reservetime_min", None
                ),
                "dryer.process_state": getattr(state, "process_state", None),
                "dryer.current_course": getattr(state, "current_course", None)
                or (
                    selected_course
                    if selected_course not in (None, "", "Current course")
                    else None
                ),
            }
        elif self._type == DeviceType.DISHWASHER:
            selected_course = getattr(self._device, "selected_course", None)
            aliases = {
                "dishwasher.is_on": getattr(state, "is_on", None),
                "dishwasher.run_state": getattr(state, "run_state", None),
                "dishwasher.error_message": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.ERROR_MSG
                ),
                "dishwasher.door_open": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.DOOROPEN
                ),
                "dishwasher.clean_l_reminder": getattr(
                    state, "device_features", {}
                ).get(WashDeviceFeatures.CLEAN_L_REMINDER),
                "dishwasher.machine_clean_reminder": getattr(
                    state, "device_features", {}
                ).get(WashDeviceFeatures.MACHINE_CLEAN_REMINDER),
                "dishwasher.rinse_refill": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.RINSEREFILL
                ),
                "dishwasher.rinse_level": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.RINSELEVEL
                ),
                "dishwasher.signal_level": getattr(state, "device_features", {}).get(
                    WashDeviceFeatures.SIGNAL_LEVEL
                ),
                "dishwasher.softening_level": getattr(
                    state, "device_features", {}
                ).get(WashDeviceFeatures.SOFTENING_LEVEL),
                "dishwasher.timer_relative_start_hour": getattr(
                    state, "reservetime_hour", None
                ),
                "dishwasher.timer_relative_start_minute": getattr(
                    state, "reservetime_min", None
                ),
                "dishwasher.timer_total_hour": getattr(
                    state, "initialtime_hour", None
                ),
                "dishwasher.timer_total_minute": getattr(
                    state, "initialtime_min", None
                ),
                "dishwasher.remain_hour": getattr(state, "remaintime_hour", None),
                "dishwasher.remain_minute": getattr(state, "remaintime_min", None),
                "dishwasher.timer_relative_stop_hour": getattr(
                    state, "reservetime_hour", None
                ),
                "dishwasher.timer_relative_stop_minute": getattr(
                    state, "reservetime_min", None
                ),
                "dishwasher.process_state": getattr(state, "process_state", None),
                "dishwasher.current_course": getattr(state, "current_course", None)
                or (
                    selected_course
                    if selected_course not in (None, "", "Current course")
                    else None
                ),
            }

        return {key: value for key, value in aliases.items() if value is not None}

    def _record_state_in_registry(self, *, official: bool = False) -> None:
        """Record the current state in the capability registry."""
        if self._state is None:
            return

        capability_registry = get_capability_registry(self._hass)
        if capability_registry is None:
            return

        profile = capability_registry.get_profile(self._device_id)
        if profile is None:
            profile = capability_registry.register_device(
                self._device_id,
                self._model,
                self._type,
            )

        if self._available:
            profile.mark_online()
        else:
            profile.mark_offline("community_device_unavailable")

        if not official:
            raw_state = getattr(self._state, "as_dict", {})
            if isinstance(raw_state, dict):
                for key, value in raw_state.items():
                    profile.update_attribute_community(f"state.{key}", value)
            device_features = getattr(self._state, "device_features", {})
            if isinstance(device_features, dict):
                for key, value in device_features.items():
                    profile.update_attribute_community(f"feature.{key}", value)

        for key, value in self._get_registry_alias_values().items():
            if official:
                profile.update_attribute_official(key, value)
            else:
                profile.update_attribute_community(key, value)

    def _state_reports_online(self, state: Any | None = None) -> bool | None:
        """Return the explicit online/offline flag from a state payload, if present."""
        if state is None:
            state = self._state
        if state is None:
            return None

        if hasattr(state, "as_dict"):
            raw_state = state.as_dict
            if callable(raw_state):
                raw_state = raw_state()
            if isinstance(raw_state, dict) and "online" in raw_state:
                online = raw_state.get("online")
                if isinstance(online, bool):
                    return online
                if isinstance(online, (int, float)):
                    return bool(online)

        online_attr = getattr(state, "online", None)
        if isinstance(online_attr, bool):
            return online_attr
        if isinstance(online_attr, (int, float)):
            return bool(online_attr)
        return None

    @callback
    def apply_mqtt_update(self, updates: dict[str, Any]) -> bool:
        """Apply MQTT payload values directly to the current state when possible."""
        if self._state is None or not hasattr(self._state, "update_status"):
            return False

        updated = False
        for key, value in updates.items():
            if key in {"deviceId", "timestamp", "pushType"}:
                continue
            if self._state.update_status(key, value):
                updated = True

        if updated:
            self._last_mqtt_update = utcnow()
            capability_registry = get_capability_registry(self._hass)
            if capability_registry is not None and (
                profile := capability_registry.get_profile(self._device_id)
            ) is not None:
                profile.mark_online()
            self._record_state_in_registry(official=True)
            self.async_set_updated()
        return updated

    async def _create_coordinator(self) -> None:
        """Get the coordinator for a specific device."""
        capability_registry = get_capability_registry(self._hass)
        data_source_router = get_data_source_router(self._hass)
        coordinator: DataUpdateCoordinator[Any]

        if capability_registry is not None and data_source_router is not None:
            capability_registry.register_device(
                self._device_id,
                self._model,
                self._type,
            )
            coordinator = HybridDataCoordinator(
                self._hass,
                _LOGGER,
                name=f"{DOMAIN}-{self._name}",
                device_id=self._device_id,
                device_model=self._model,
                device_type=self._type,
                update_method=self._async_update,
                capability_registry=capability_registry,
                data_source_router=data_source_router,
                base_polling_interval=SCAN_INTERVAL,
                mqtt_healthy_interval=timedelta(seconds=90),
                mqtt_unhealthy_interval=SCAN_INTERVAL,
            )
            get_hybrid_coordinators(self._hass)[self._device_id] = coordinator
        else:
            coordinator = DataUpdateCoordinator(
                self._hass,
                _LOGGER,
                name=f"{DOMAIN}-{self._name}",
                update_method=self._async_update,
                update_interval=SCAN_INTERVAL,
            )
        await coordinator.async_refresh()
        self._coordinator = coordinator

    async def _async_update(self) -> Any:
        """Async update used by coordinator."""
        await self._async_state_update()
        return self._state

    async def _async_state_update(self) -> None:
        """Update device state."""
        _LOGGER.debug("Updating ThinQ device %s", self._name)
        if self._disc_count < MAX_DISC_COUNT:
            self._disc_count += 1

        try:
            state = await self._device.poll()
        except (MonitorRefreshError, NotConnectedError):
            state = None
            capability_registry = get_capability_registry(self._hass)
            if capability_registry is not None and (
                profile := capability_registry.get_profile(self._device_id)
            ) is not None:
                profile.mark_offline("device_disconnected_or_powered_off")
            if (
                self._state is not None
                and self._state.is_on
                and self._disc_count >= MAX_DISC_COUNT
            ):
                _LOGGER.warning(
                    "Status for device %s was reset because disconnected or unreachable",
                    self._name,
                )
                self._state = self._device.reset_status()
        except MonitorUnavailableError:
            if not self._available:
                return
            _LOGGER.warning(
                "Status for device %s was reset because ThinQ connection not available",
                self._name,
            )
            self._available = False
            capability_registry = get_capability_registry(self._hass)
            if capability_registry is not None and (
                profile := capability_registry.get_profile(self._device_id)
            ) is not None:
                profile.mark_offline("thinq_connection_unavailable")
            self._state = self._device.reset_status()
            return
        except InvalidCredentialError:
            async_dispatcher_send(self._hass, SIGNAL_RELOAD_ENTRY)
            return

        self._available = True
        capability_registry = get_capability_registry(self._hass)
        if capability_registry is not None and (
            profile := capability_registry.get_profile(self._device_id)
        ) is not None:
            profile.mark_online()
        if state:
            self._disc_count = 0
            self._state = state
            reported_online = self._state_reports_online(state)
            if reported_online is False:
                self._available = False
                if capability_registry is not None and (
                    profile := capability_registry.get_profile(self._device_id)
                ) is not None:
                    profile.mark_offline("device_reported_offline")
            else:
                self._available = True
                if capability_registry is not None and (
                    profile := capability_registry.get_profile(self._device_id)
                ) is not None:
                    profile.mark_online()
            self._record_state_in_registry()
