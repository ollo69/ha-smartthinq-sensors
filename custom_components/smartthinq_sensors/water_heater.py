"""Platform for LGE water heater integration."""
from __future__ import annotations

import logging

from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_OFF,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .wideq import UNIT_TEMP_FAHRENHEIT, DeviceType
from .wideq.ac import MAX_AWHP_TEMP, MIN_AWHP_TEMP, AirConditionerDevice

SUPPORT_FLAGS_HEATER = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
)

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

        lge_climates = []

        # AC devices
        lge_climates.extend(
            [
                LGEACWaterHeater(lge_device)
                for lge_device in lge_devices.get(DeviceType.AC, [])
                if lge_device.device.is_water_heater_supported
            ]
        )

        async_add_entities(lge_climates)

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


class LGEACWaterHeater(LGEWaterHeater):
    """LGE AWHP water heater AC device based."""

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the climate."""
        super().__init__(api)
        self._device: AirConditionerDevice = api.device
        self._attr_name = f"{api.name} Water Heater"
        self._attr_unique_id = f"{api.unique_id}-AC-WH"
        self._attr_supported_features = SUPPORT_FLAGS_HEATER
        self._attr_operation_list = [STATE_OFF, STATE_HEAT_PUMP]
        self._attr_precision = self._device.hot_water_target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._device.temperature_unit == UNIT_TEMP_FAHRENHEIT:
            return TEMP_FAHRENHEIT
        return TEMP_CELSIUS

    @property
    def current_operation(self) -> str | None:
        """Return current operation."""
        if self._api.state.is_hot_water_on:
            return STATE_HEAT_PUMP
        return STATE_OFF

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if new_temp := kwargs.get(ATTR_TEMPERATURE):
            await self._device.set_hot_water_target_temp(new_temp)
            self._api.async_set_updated()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set operation mode."""
        if operation_mode not in self.operation_list:
            raise ValueError(f"Invalid operation mode [{operation_mode}]")
        if operation_mode == self.current_operation:
            return
        await self._device.hot_water_mode(operation_mode == STATE_HEAT_PUMP)
        self._api.async_set_updated()

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._api.state.hot_water_current_temp

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._api.state.hot_water_target_temp

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if (min_value := self._device.hot_water_target_temperature_min) is not None:
            return min_value
        return self._device.conv_temp_unit(MIN_AWHP_TEMP)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if (max_value := self._device.hot_water_target_temperature_max) is not None:
            return max_value
        return self._device.conv_temp_unit(MAX_AWHP_TEMP)
