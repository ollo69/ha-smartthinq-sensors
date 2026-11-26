"""Number platform for SmartThinQ: scan_interval option and device numbers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LGE_DEVICES,
    LGE_DISCOVERY_NEW,
    LGE_DISCOVERY_NUMBER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .wideq import AirConditionerFeatures, DeviceType

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQNumberRequiredKeysMixin:
    """Mixin for required keys."""

    set_value_fn: Callable[[Any, int], Awaitable[None]]


@dataclass
class ThinQNumberEntityDescription(
    NumberEntityDescription, ThinQNumberRequiredKeysMixin
):
    """A class that describes ThinQ number entities."""

    available_fn: Callable[[Any], bool] | None = None


AC_NUMBER: tuple[ThinQNumberEntityDescription, ...] = (
    ThinQNumberEntityDescription(
        key=AirConditionerFeatures.RESERVATION_START_TIME,
        name="Turn-on timer",
        icon="mdi:timer-play-outline",
        mode=NumberMode.BOX,
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        set_value_fn=lambda x, value: x.device.set_reservation_start_time(value),
    ),
    ThinQNumberEntityDescription(
        key=AirConditionerFeatures.RESERVATION_STOP_TIME,
        name="Turn-off timer",
        icon="mdi:timer-stop-outline",
        mode=NumberMode.BOX,
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        set_value_fn=lambda x, value: x.device.set_reservation_stop_time(value),
    ),
)

NUMBER_ENTITIES = {
    DeviceType.AC: AC_NUMBER,
}


def _number_exist(
    lge_device: LGEDevice, number_desc: ThinQNumberEntityDescription
) -> bool:
    """Check if a number exist for device."""
    return number_desc.key in lge_device.available_features


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SmartThinQ numbers."""
    async_add_entities([SmartThinQScanIntervalNumber(config_entry)])

    entry_config = hass.data[DOMAIN]
    # Devices are normally not loaded yet: this platform is set up before the
    # LG cloud is queried and receives them through LGE_DISCOVERY_NUMBER.
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ number setup...")

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

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NUMBER, _async_discover_device)
    )


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
        """Change the value."""
        await self.entity_description.set_value_fn(self._api, int(value))
        self._api.async_set_updated()

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if self._api.state:
            value = self._api.state.device_features.get(self.entity_description.key)
            if value is not None:
                return float(value)
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._api)
        return self._api.available and is_avail
