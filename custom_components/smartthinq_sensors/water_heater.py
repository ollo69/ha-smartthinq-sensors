"""Platform for LGE water heater integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_HEAT_PUMP,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .wideq import (
    AirConditionerFeatures,
    DeviceType,
    TemperatureUnit,
    WaterHeaterFeatures,
)
from .wideq.devices.ac import AWHP_MAX_TEMP, AWHP_MIN_TEMP, AirConditionerDevice
from .wideq.devices.waterheater import (
    DEFAULT_MAX_TEMP as WH_MAX_TEMP,
    DEFAULT_MIN_TEMP as WH_MIN_TEMP,
    WaterHeaterDevice,
    WHMode,
)

LGEAC_SUPPORT_FLAGS = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
)

LGEWH_AWAY_MODE = WHMode.VACATION.name
LGEWH_STATE_TO_HA = {
    WHMode.AUTO.name: STATE_ECO,
    WHMode.HEAT_PUMP.name: STATE_HEAT_PUMP,
    WHMode.TURBO.name: STATE_PERFORMANCE,
    WHMode.VACATION.name: STATE_OFF,
}

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up LGE device water heater based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ water heater setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        # WH devices
        lge_water_heater = [
            LGEWHWaterHeater(lge_device)
            for lge_device in lge_devices.get(DeviceType.WATER_HEATER, [])
        ]

        # AC devices
        lge_water_heater.extend(
            [
                LGEACWaterHeater(lge_device)
                for lge_device in lge_devices.get(DeviceType.AC, [])
                if lge_device.device.is_water_heater_supported
            ]
        )

        async_add_entities(lge_water_heater)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGEWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Base water heater device."""

    def __init__(self, api: LGEDevice):
        """Initialize the climate."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGEWHWaterHeater(LGEWaterHeater):
    """LGE AWHP water heater."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the device."""
        super().__init__(api)
        self._device: WaterHeaterDevice = api.device
        self._attr_unique_id = f"{api.unique_id}-WH"
        self._supported_features = None
        self._modes_lookup = None

    def _available_modes(self) -> dict[str, str]:
        """Return available modes from lookup dict."""
        if self._modes_lookup is None:
            self._modes_lookup = {
                key: mode
                for key, mode in LGEWH_STATE_TO_HA.items()
                if key in self._device.op_modes
            }
        return self._modes_lookup

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Return the list of supported features."""
        if self._supported_features is None:
            features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
            if self.operation_list is not None:
                features |= WaterHeaterEntityFeature.OPERATION_MODE
            self._supported_features = features
        return self._supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._device.temperature_unit == TemperatureUnit.FAHRENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def current_operation(self) -> str | None:
        """Return current operation."""
        op_mode: str | None = self._api.state.operation_mode
        if op_mode is None:
            return STATE_OFF
        modes = self._available_modes()
        return modes.get(op_mode)

    @property
    def operation_list(self) -> list[str] | None:
        """Return the list of available hvac operation modes."""
        if not (modes := self._available_modes()):
            return None
        return list(modes.values())

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if new_temp := kwargs.get(ATTR_TEMPERATURE):
            await self._device.set_target_temp(int(new_temp))
            self._api.async_set_updated()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set operation mode."""
        modes = self._available_modes()
        reverse_lookup = {v: k for k, v in modes.items()}
        if (new_mode := reverse_lookup.get(operation_mode)) is None:
            raise ValueError(f"Invalid operation_mode [{operation_mode}]")
        await self._device.set_op_mode(new_mode)
        self._api.async_set_updated()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.async_set_operation_mode(STATE_HEAT_PUMP)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        await self.async_set_operation_mode(STATE_OFF)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._api.state.device_features.get(WaterHeaterFeatures.HOT_WATER_TEMP)

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._api.state.target_temp

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if (min_value := self._device.target_temperature_min) is not None:
            return min_value
        return self._device.conv_temp_unit(WH_MIN_TEMP)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if (max_value := self._device.target_temperature_max) is not None:
            return max_value
        return self._device.conv_temp_unit(WH_MAX_TEMP)


class LGEACWaterHeater(LGEWaterHeater):
    """LGE AWHP water heater AC device based."""

    _attr_has_entity_name = True
    _attr_name = "Water Heater"

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the device."""
        super().__init__(api)
        self._device: AirConditionerDevice = api.device
        self._attr_unique_id = f"{api.unique_id}-AC-WH"
        self._attr_supported_features = LGEAC_SUPPORT_FLAGS
        self._attr_operation_list = [STATE_OFF, STATE_HEAT_PUMP]
        # self._attr_precision = self._device.hot_water_target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._device.temperature_unit == TemperatureUnit.FAHRENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def current_operation(self) -> str | None:
        """Return current operation."""
        if self._api.state.is_hot_water_on:
            return STATE_HEAT_PUMP
        return STATE_OFF

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if new_temp := kwargs.get(ATTR_TEMPERATURE):
            await self._device.set_hot_water_target_temp(int(new_temp))
            self._api.async_set_updated()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set operation mode."""
        if operation_mode not in self.operation_list:
            raise ValueError(f"Invalid operation mode [{operation_mode}]")
        if operation_mode == self.current_operation:
            return
        await self._device.hot_water_mode(operation_mode == STATE_HEAT_PUMP)
        self._api.async_set_updated()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.async_set_operation_mode(STATE_HEAT_PUMP)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        await self.async_set_operation_mode(STATE_OFF)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._api.state.device_features.get(
            AirConditionerFeatures.HOT_WATER_TEMP
        )

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._api.state.hot_water_target_temp

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if (min_value := self._device.hot_water_target_temperature_min) is not None:
            return min_value
        return self._device.conv_temp_unit(AWHP_MIN_TEMP)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if (max_value := self._device.hot_water_target_temperature_max) is not None:
            return max_value
        return self._device.conv_temp_unit(AWHP_MAX_TEMP)
