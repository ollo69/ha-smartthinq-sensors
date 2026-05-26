"""Number platform exposing SmartThinQ polling interval options."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ACTIVE_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_ACTIVE_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_ACTIVE_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_ACTIVE_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up polling interval number entities for this config entry."""
    async_add_entities(
        [
            SmartThinQScanIntervalNumber(config_entry),
            SmartThinQActiveScanIntervalNumber(config_entry),
        ]
    )


class _ScanIntervalNumberBase(NumberEntity):
    """Base class for SmartThinQ polling interval number entities."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-cog-outline"

    _conf_key: str
    _default: int

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize."""
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}-{self._conf_key}"

    async def async_added_to_hass(self) -> None:
        """Refresh state whenever the option is changed via OptionsFlow."""

        async def _options_changed(_hass: HomeAssistant, _entry: ConfigEntry) -> None:
            self.async_write_ha_state()

        self.async_on_remove(self._config_entry.add_update_listener(_options_changed))

    @property
    def native_value(self) -> float:
        """Return the current interval (seconds)."""
        return float(self._config_entry.options.get(self._conf_key, self._default))

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new interval; the options listener picks it up live."""
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, self._conf_key: int(value)},
        )


class SmartThinQScanIntervalNumber(_ScanIntervalNumberBase):
    """Idle polling interval — used when all devices are off."""

    _attr_translation_key = "scan_interval"
    _attr_native_min_value = MIN_SCAN_INTERVAL
    _attr_native_max_value = MAX_SCAN_INTERVAL
    _attr_native_step = 1
    _conf_key = CONF_SCAN_INTERVAL
    _default = DEFAULT_SCAN_INTERVAL


class SmartThinQActiveScanIntervalNumber(_ScanIntervalNumberBase):
    """Active polling interval — used while a device is running."""

    _attr_translation_key = "active_scan_interval"
    _attr_native_min_value = MIN_ACTIVE_SCAN_INTERVAL
    _attr_native_max_value = MAX_ACTIVE_SCAN_INTERVAL
    _attr_native_step = 1
    _conf_key = CONF_ACTIVE_SCAN_INTERVAL
    _default = DEFAULT_ACTIVE_SCAN_INTERVAL
