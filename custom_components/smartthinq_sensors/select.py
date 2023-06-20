"""Support for ThinQ device selects."""
from __future__ import annotations

import asyncio

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable, Tuple

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import LGEBaseDevice, get_entity_name, get_multiple_devices_types
from .wideq import DeviceType, WM_DEVICE_TYPES, WashDeviceFeatures, MicroWaveFeatures


_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQSelectEntityDescription(SelectEntityDescription):
    """A class that describes ThinQ select entities."""

    available_fn: Callable[[Any], bool] | None = None
    select_option_fn: Callable[[Any], Awaitable[None]] | None = None
    value_fn: Callable[[Any], str] | None = None
    options_fn: Callable[[Any], str] | None = None


MICROWAVE_DEV_SELECT: Tuple[ThinQSelectEntityDescription, ...] = (
    ThinQSelectEntityDescription(
        key=MicroWaveFeatures.DISPLAY_SCROLL_SPEED,
        name="Display Scroll Speed",
        icon="mdi:format-pilcrow-arrow-right",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda x: x.is_power_on and x.device.display_scroll_speed_state,
        select_option_fn=lambda x, option: x.device.set_display_scroll_speed(option),
        options_fn=lambda x: x.device.display_scroll_speed_options,
        available_fn=lambda x: x.is_power_on,
    ),
    ThinQSelectEntityDescription(
        key=MicroWaveFeatures.VENT_SPEED,
        name="Vent",
        icon="mdi:fan",
        value_fn=lambda x: x.is_power_on and x.device.vent_speed_state,
        select_option_fn=lambda x, option: x.device.set_vent_speed(option),
        options_fn=lambda x: x.device.vent_speed_options,
        available_fn=lambda x: x.is_power_on,
    ),
)


def _select_exist(
    lge_device: LGEDevice, select_desc: ThinQSelectEntityDescription
) -> bool:
    """Check if a select exist for device."""
    if select_desc.value_fn is not None:
        return True

    feature = select_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE selects."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ select setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_select = []

        # add WM devices
        lge_select.extend(
            [
                LGESelect(lge_device, select_desc)
                for select_desc in MICROWAVE_DEV_SELECT
                for lge_device in lge_devices.get(DeviceType.MICROWAVE, [])
                if _select_exist(lge_device, select_desc)
            ]
        )

        async_add_entities(lge_select)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGESelect(CoordinatorEntity, SelectEntity):
    """Class to control selects for LGE device"""

    entity_description: ThinQSelectEntityDescription

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQSelectEntityDescription,
    ):
        """Initialize the select."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = LGEBaseDevice(api)
        self.entity_description = description
        self._attr_name = get_entity_name(api, description.key, description.name)
        self._attr_unique_id = f"{api.unique_id}-{description.key}-select"
        self._attr_device_info = api.device_info

    async def async_select_option(self, option: str) -> None:
        await self.entity_description.select_option_fn(self._wrap_device, option)
        # This is an async callback that will write the state to the state machine
        # within yielding to the event loop.
        self.async_write_ha_state()

    @property
    def current_option(self) -> str:
        return self.entity_description.value_fn(self._wrap_device)

    @property
    def options(self) -> list[str]:
        return self.entity_description.options_fn(self._wrap_device)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._wrap_device)
        return self._api.available and is_avail
