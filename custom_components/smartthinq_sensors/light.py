"""Support for ThinQ light devices."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.light import (
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityDescription,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import LGEBaseDevice
from .wideq import DeviceType, HoodFeatures, MicroWaveFeatures

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQLightEntityDescription(LightEntityDescription):
    """A class that describes ThinQ light entities."""

    value_fn: Callable[[Any], str] | None = None
    effects_fn: Callable[[Any], list[str]] | None = None
    set_effect_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_off_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_on_fn: Callable[[Any], Awaitable[None]] | None = None


HOOD_LIGHT: tuple[ThinQLightEntityDescription, ...] = (
    ThinQLightEntityDescription(
        key=HoodFeatures.LIGHT_MODE,
        name="Light",
        effects_fn=lambda x: x.device.light_modes,
        set_effect_fn=lambda x, option: x.device.set_light_mode(option),
    ),
)
MICROWAVE_LIGHT: tuple[ThinQLightEntityDescription, ...] = (
    ThinQLightEntityDescription(
        key=MicroWaveFeatures.LIGHT_MODE,
        name="Light",
        effects_fn=lambda x: x.device.light_modes,
        set_effect_fn=lambda x, option: x.device.set_light_mode(option),
    ),
)

LIGHT_ENTITIES = {
    DeviceType.HOOD: HOOD_LIGHT,
    DeviceType.MICROWAVE: MICROWAVE_LIGHT,
}


def _light_exist(
    lge_device: LGEDevice, light_desc: ThinQLightEntityDescription
) -> bool:
    """Check if a light exist for device."""
    if light_desc.value_fn is not None:
        return True

    feature = light_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE selects."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ light setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_light = [
            LGELight(lge_device, light_desc)
            for dev_type, light_descs in LIGHT_ENTITIES.items()
            for light_desc in light_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _light_exist(lge_device, light_desc)
        ]

        async_add_entities(lge_light)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGELight(CoordinatorEntity, LightEntity):
    """Class to control lights for LGE device"""

    entity_description: ThinQLightEntityDescription
    _attr_has_entity_name = True
    _attr_supported_color_modes = set(ColorMode.ONOFF)
    _attr_color_mode = ColorMode.ONOFF

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
        self._attr_unique_id = f"{api.unique_id}-{description.key}-light"
        self._attr_device_info = api.device_info
        self._turn_off_effect = None
        self._last_effect = None
        self._attr_effect_list = self._get_light_effects()

    def _get_light_effects(self) -> list[str]:
        """Get available light effects."""
        if self.entity_description.effects_fn is None:
            return None
        avl_effects = self.entity_description.effects_fn(self._api).copy()
        if self.entity_description.turn_off_fn is None:
            self._turn_off_effect = avl_effects.pop(0)
        return avl_effects

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available

    @property
    def supported_features(self) -> LightEntityFeature:
        """Return the list of supported features."""
        if self.effect_list and len(self.effect_list) > 1:
            return LightEntityFeature.EFFECT
        return LightEntityFeature(0)

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        if self.entity_description.value_fn is not None:
            effect = self.entity_description.value_fn(self._api)
        else:
            effect = self._api.state.device_features.get(self.entity_description.key)

        off_effect = self._turn_off_effect
        if not effect or (off_effect and effect == off_effect):
            return None
        return effect

    @property
    def is_on(self) -> bool:
        """Return if light is on."""
        if self._turn_off_effect is not None:
            return self.effect is not None
        return self._api.state.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        effect = kwargs.get(ATTR_EFFECT)
        is_on = self.is_on
        if self.entity_description.turn_on_fn is not None:
            if not is_on:
                await self.entity_description.turn_on_fn(self._api)
        elif effect is None:
            effect = self._last_effect or self.effect_list[0]

        if not effect and is_on:
            return

        if effect and self.entity_description.set_effect_fn:
            await self.entity_description.set_effect_fn(self._api, effect)
        self._api.async_set_updated()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if not self.is_on:
            return
        effect = self._turn_off_effect
        if self.entity_description.turn_off_fn is not None:
            await self.entity_description.turn_off_fn(self._api)
        elif effect and self.entity_description.set_effect_fn is not None:
            self._last_effect = self.effect
            await self.entity_description.set_effect_fn(self._api, effect)
        else:
            raise NotImplementedError()
        self._api.async_set_updated()
