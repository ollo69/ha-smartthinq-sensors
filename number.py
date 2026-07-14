"""Support for ThinQ device numbers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import (
    DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW,
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL
)
from .wideq import DeviceType, AirConditionerFeatures

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQNumberRequiredKeysMixin:
    """Mixin for required keys."""

    set_value_fn: Callable[[Any, float], Awaitable[None]]


@dataclass
class ThinQNumberEntityDescription(
    NumberEntityDescription, ThinQNumberRequiredKeysMixin
):
    """A class that describes ThinQ number entities."""

    available_fn: Callable[[Any], bool] | None = None
    value_fn: Callable[[Any], float | None] | None = None
    min_value_fn: Callable[[Any], float] | None = None
    max_value_fn: Callable[[Any], float] | None = None
    step_fn: Callable[[Any], float] | None = None


AC_NUMBER: tuple[ThinQNumberEntityDescription, ...] = (
    ThinQNumberEntityDescription(
        key=AirConditionerFeatures.RESERVATION_SLEEP_TIME,
        name="Sleep timer",
        icon="mdi:timer-outline",
        entity_category=EntityCategory.CONFIG,
        set_value_fn=lambda x, option: x.device.set_reservation_sleep_time(int(option)),
        available_fn=lambda x: x.state and x.state.is_on and x.device.is_reservation_sleep_time_available,
        min_value_fn=lambda x: x.device.sleep_time_range[0],
        max_value_fn=lambda x: x.device.sleep_time_range[1],
        step_fn=lambda x: 1.0,
    ),
)

NUMBER_ENTITIES = {
    DeviceType.AC: AC_NUMBER,
}


def _number_exist(
    lge_device: LGEDevice, number_desc: ThinQNumberEntityDescription
) -> bool:
    """Check if a number exist for device."""
    if number_desc.value_fn is not None:
        return True

    feature = number_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE numbers."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ number setup...")

    # Set up the scan_interval number entity for this config entry
    async_add_entities([SmartThinQScanIntervalNumber(entry)])

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_number = [
            LGENumber(lge_device, number_desc)
            for dev_type, number_descs in NUMBER_ENTITIES.items()
            for number_desc in number_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _number_exist(lge_device, number_desc)
        ]

        async_add_entities(lge_number)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGENumber(CoordinatorEntity, NumberEntity):
    """Class to control numbers for LGE device"""

    entity_description: ThinQNumberEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQNumberEntityDescription,
    ):
        """Initialize the number."""
        super().__init__(api.coordinator)
        self._api = api
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-number"
        self._attr_device_info = api.device_info

    async def async_set_native_value(self, value: float) -> None:
        """Change the selected value."""
        await self.entity_description.set_value_fn(self._api, value)
        self._api.async_set_updated()

    @property
    def native_value(self) -> float | None:
        """Return the entity value to represent the entity state."""
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._api)

        if self._api.state:
            feature = self.entity_description.key
            val = self._api.state.device_features.get(feature)
            if val is not None:
                return float(val)

        return None

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        if self.entity_description.min_value_fn is not None:
            return self.entity_description.min_value_fn(self._api)
        return super().native_min_value
        
    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        if self.entity_description.max_value_fn is not None:
            return self.entity_description.max_value_fn(self._api)
        return super().native_max_value

    @property
    def native_step(self) -> float:
        """Return the step value."""
        if self.entity_description.step_fn is not None:
            return self.entity_description.step_fn(self._api)
        return super().native_step

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._api)
        return self._api.available and is_avail


class SmartThinQScanIntervalNumber(NumberEntity):
    """Polling interval (seconds) shared by all SmartThinQ coordinators."""

    _attr_has_entity_name = True
    _attr_translation_key = "scan_interval"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_SCAN_INTERVAL
    _attr_native_max_value = MAX_SCAN_INTERVAL
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize."""
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}-scan_interval"

    async def async_added_to_hass(self) -> None:
        """Refresh state whenever the option is changed via OptionsFlow."""

        async def _options_changed(_hass: HomeAssistant, _entry: ConfigEntry) -> None:
            self.async_write_ha_state()

        self.async_on_remove(self._config_entry.add_update_listener(_options_changed))

    @property
    def native_value(self) -> float:
        """Return the current interval (seconds)."""
        return float(
            self._config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new interval; the options listener picks it up live."""
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, CONF_SCAN_INTERVAL: int(value)},
        )
