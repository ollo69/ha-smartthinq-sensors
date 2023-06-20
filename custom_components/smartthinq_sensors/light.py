"""Support for ThinQ device lights."""
from __future__ import annotations

import asyncio

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable, Tuple

from homeassistant.components.light import (
    LightEntity,
    LightEntityDescription,
    ColorMode,
    ATTR_BRIGHTNESS,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import LGEBaseDevice, get_entity_name, get_multiple_devices_types
from .wideq import DeviceType, WM_DEVICE_TYPES, WashDeviceFeatures, MicroWaveFeatures

# general light attributes
ATTR_LIGHT = "light"

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQLightEntityDescription(LightEntityDescription):
    """A class that describes ThinQ light entities."""

    available_fn: Callable[[Any], bool] | None = None
    turn_off_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_on_fn: Callable[[Any], Awaitable[None]] | None = None
    light_is_on_fn: Callable[[Any], bool] | None = None
    brightness_fn: Callable[[Any], bool] | None = None
    related_feature: str | None = None


MICROWAVE_DEV_LIGHT: Tuple[ThinQLightEntityDescription, ...] = (
    ThinQLightEntityDescription(
        key=ATTR_LIGHT,
        name="Light",
        icon="mdi:wall-sconce-flat",
        turn_on_fn=lambda x, **kwargs: x.device.light_turn_onoff(True, **kwargs),
        turn_off_fn=lambda x, **kwargs: x.device.light_turn_onoff(False, **kwargs),
        light_is_on_fn=lambda x: x.device.light_is_on,
        brightness_fn=lambda x: x.device.light_brightness,
        available_fn=lambda x: x.is_power_on,
        related_feature=MicroWaveFeatures.LIGHT,
    ),
)


def _light_exist(
    lge_device: LGEDevice, light_desc: ThinQLightEntityDescription
) -> bool:
    """Check if a light exist for device."""
    feature = light_desc.related_feature
    if feature is None or feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE lights."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ light setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_light = []

        # add WM devices
        lge_light.extend(
            [
                LGELight(lge_device, light_desc)
                for light_desc in MICROWAVE_DEV_LIGHT
                for lge_device in lge_devices.get(DeviceType.MICROWAVE, [])
                if _light_exist(lge_device, light_desc)
            ]
        )

        async_add_entities(lge_light)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGELight(CoordinatorEntity, LightEntity):
    """Class to control lights for LGE device"""

    entity_description: ThinQLightEntityDescription

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQLightEntityDescription,
    ):
        """Initialize the light."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = LGEBaseDevice(api)
        self.entity_description = description
        self._attr_name = get_entity_name(api, description.key, description.name)
        self._attr_unique_id = f"{api.unique_id}-{description.key}-light"
        self._attr_device_info = api.device_info

    async def async_turn_on(self, **kwargs) -> None:
        await self.entity_description.turn_on_fn(self._wrap_device, **kwargs)
        # This is an async callback that will write the state to the state machine
        # within yielding to the event loop.
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.entity_description.turn_off_fn(self._wrap_device, **kwargs)
        # This is an async callback that will write the state to the state machine
        # within yielding to the event loop.
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if device is on (brightness above 0)."""
        return self.entity_description.light_is_on_fn(self._wrap_device)

    @property
    def brightness(self) -> int | None:
        return self.entity_description.brightness_fn(self._wrap_device)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._wrap_device)
        return self._api.available and is_avail

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return list of available color modes."""
        modes: set[ColorMode] = set()
        modes.add(ColorMode.BRIGHTNESS)
        modes.add(ColorMode.ONOFF)

        return modes
