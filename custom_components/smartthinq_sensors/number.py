"""Number platform exposing the SmartThinQ scan_interval option."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the scan_interval number entity for this config entry."""
    async_add_entities([SmartThinQScanIntervalNumber(config_entry)])


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
