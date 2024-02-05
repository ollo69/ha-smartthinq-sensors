"""Platform for LGE fan integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .wideq import DeviceType, HoodFeatures, MicroWaveFeatures

ATTR_FAN_MODE = "fan_mode"
ATTR_FAN_MODES = "fan_modes"
DEFAULT_KEY = "default"

_LOGGER = logging.getLogger(__name__)


@dataclass
class LGEFanWrapperDescription:
    """A class that describes LG fan wrapper."""

    fanspeed_fn: Callable[[Any], str] | None
    fanspeeds_fn: Callable[[Any], list[str]]
    set_fanspeed_fn: Callable[[Any], Awaitable[None]]
    fanpreset_fn: Callable[[Any], str] | None = None
    fanpresets_fn: Callable[[Any], list[str]] | None = None
    set_fanpreset_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_off_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_on_fn: Callable[[Any], Awaitable[None]] | None = None


FAN_WRAPPER = LGEFanWrapperDescription(
    fanspeed_fn=lambda x: x.state.fan_speed,
    fanspeeds_fn=lambda x: x.device.fan_speeds,
    set_fanspeed_fn=lambda x, option: x.device.set_fan_speed(option),
    turn_off_fn=lambda x: x.device.power(False),
    turn_on_fn=lambda x: x.device.power(True),
)
AIRPURIFIER_WRAPPER = LGEFanWrapperDescription(
    fanspeed_fn=lambda x: x.state.fan_speed,
    fanspeeds_fn=lambda x: x.device.fan_speeds,
    set_fanspeed_fn=lambda x, option: x.device.set_fan_speed(option),
    fanpreset_fn=lambda x: x.state.fan_preset,
    fanpresets_fn=lambda x: x.device.fan_presets,
    set_fanpreset_fn=lambda x, option: x.device.set_fan_preset(option),
    turn_off_fn=lambda x: x.device.power(False),
    turn_on_fn=lambda x: x.device.power(True),
)
HOOD_WRAPPER = LGEFanWrapperDescription(
    fanspeed_fn=None,
    fanspeeds_fn=lambda x: x.device.vent_speeds,
    set_fanspeed_fn=lambda x, option: x.device.set_vent_speed(option),
)
MICROWAVE_WRAPPER = LGEFanWrapperDescription(
    fanspeed_fn=None,
    fanspeeds_fn=lambda x: x.device.vent_speeds,
    set_fanspeed_fn=lambda x, option: x.device.set_vent_speed(option),
)


@dataclass
class ThinQFanRequiredKeysMixin:
    """Mixin for required keys."""

    wrapper_description: LGEFanWrapperDescription


@dataclass
class ThinQFanEntityDescription(FanEntityDescription, ThinQFanRequiredKeysMixin):
    """A class that describes ThinQ fan entities."""


FAN_DEVICE: tuple[ThinQFanEntityDescription, ...] = (
    ThinQFanEntityDescription(
        key=DEFAULT_KEY,
        name=None,
        wrapper_description=FAN_WRAPPER,
    ),
)
AIRPURIFIER_DEVICE: tuple[ThinQFanEntityDescription, ...] = (
    ThinQFanEntityDescription(
        key=DEFAULT_KEY,
        name=None,
        icon="mdi:air-purifier",
        wrapper_description=AIRPURIFIER_WRAPPER,
    ),
)
HOOD_DEVICE: tuple[ThinQFanEntityDescription, ...] = (
    ThinQFanEntityDescription(
        key=HoodFeatures.VENT_SPEED,
        name="Fan",
        wrapper_description=HOOD_WRAPPER,
    ),
)
MICROWAVE_DEVICE: tuple[ThinQFanEntityDescription, ...] = (
    ThinQFanEntityDescription(
        key=MicroWaveFeatures.VENT_SPEED,
        name="Fan",
        wrapper_description=MICROWAVE_WRAPPER,
    ),
)

FAN_ENTITIES = {
    DeviceType.FAN: FAN_DEVICE,
    DeviceType.AIR_PURIFIER: AIRPURIFIER_DEVICE,
    DeviceType.HOOD: HOOD_DEVICE,
    DeviceType.MICROWAVE: MICROWAVE_DEVICE,
}


def _fan_exist(lge_device: LGEDevice, fan_desc: ThinQFanEntityDescription) -> bool:
    """Check if a fan exist for device."""
    feature = fan_desc.key
    if feature == DEFAULT_KEY:
        return True

    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up LGE device fan based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ fan setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        # Fan devices
        lge_fan = [
            LGEFan(lge_device, fan_desc)
            for dev_type, fan_descs in FAN_ENTITIES.items()
            for fan_desc in fan_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _fan_exist(lge_device, fan_desc)
        ]

        async_add_entities(lge_fan)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGEFanWrapper:
    """Wrapper class for LG fan device."""

    def __init__(
        self,
        api: LGEDevice,
        descr: LGEFanWrapperDescription,
        feature_key: str | None = None,
    ) -> None:
        """Initialize the wrapper."""
        self._api = api
        self._description = descr
        self._feature_key = feature_key
        self._turn_off_speed = None
        self._last_speed = None
        self._avl_speeds = self._get_fan_speeds()

    def _get_fan_speeds(self) -> list[str]:
        """List of available speeds."""
        avl_speeds = self._description.fanspeeds_fn(self._api).copy()
        if self._description.turn_off_fn is None:
            self._turn_off_speed = avl_speeds.pop(0)
        return avl_speeds

    @property
    def fan_speed(self) -> str | None:
        """Return current speed."""
        if self._description.fanspeed_fn:
            return self._description.fanspeed_fn(self._api)
        if feature := self._feature_key:
            return self._api.state.device_features.get(feature)
        return None

    @property
    def fan_speeds(self) -> list[str]:
        """List of available speeds."""
        return self._avl_speeds

    @property
    def fan_preset(self) -> str | None:
        """Return current preset."""
        if self._description.fanpreset_fn is None:
            return None
        return self._description.fanpreset_fn(self._api)

    @property
    def fan_presets(self) -> list[str]:
        """List of available presets."""
        if self._description.fanpresets_fn is None:
            return []
        return self._description.fanpresets_fn(self._api)

    @property
    def is_on(self) -> bool:
        """Return if fan is on."""
        if self._description.turn_off_fn is None:
            return self.fan_speed != self._turn_off_speed
        return self._api.state.is_on

    async def async_set_speed(self, speed: str) -> None:
        """Set fan speed."""
        await self._description.set_fanspeed_fn(self._api, speed)

    async def async_set_preset(self, preset: str) -> None:
        """Set fan preset."""
        if self._description.set_fanpreset_fn is None:
            return NotImplementedError()
        await self._description.set_fanpreset_fn(self._api, preset)

    async def async_turn_on(
        self, speed: str | None = None, preset: str | None = None
    ) -> None:
        """Turn on the fan."""
        on_speed = speed
        if self._description.turn_on_fn is not None:
            await self._description.turn_on_fn(self._api)
        elif not on_speed:
            on_speed = self._last_speed or self.fan_speeds[0]

        if on_speed:
            await self.async_set_speed(on_speed)
        elif preset:
            await self.async_set_preset(preset)

    async def async_turn_off(self) -> None:
        """Turn on the fan."""
        if self._description.turn_off_fn is None:
            self._last_speed = self.fan_speed
            await self.async_set_speed(self._turn_off_speed)
        else:
            await self._description.turn_off_fn(self._api)


class LGEBaseFan(CoordinatorEntity, FanEntity):
    """Base fan device."""

    def __init__(self, api: LGEDevice):
        """Initialize the base fan."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGEFan(LGEBaseFan):
    """LG Fan device."""

    entity_description: ThinQFanEntityDescription
    _attr_has_entity_name = True

    def __init__(self, api: LGEDevice, description: ThinQFanEntityDescription) -> None:
        """Initialize the fan."""
        super().__init__(api)
        wrapper = LGEFanWrapper(api, description.wrapper_description, description.key)
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-FAN"
        if description.key != DEFAULT_KEY:
            self._attr_unique_id += f"-{description.key}"
        self._attr_speed_count = len(wrapper.fan_speeds)
        if presets := wrapper.fan_presets:
            self._attr_preset_modes = presets
        self._wrapper = wrapper

    @property
    def supported_features(self) -> FanEntityFeature:
        """Return the list of supported features."""
        features = FanEntityFeature(0)
        if self.speed_count > 1:
            features |= FanEntityFeature.SET_SPEED
        if self.preset_modes is not None:
            features |= FanEntityFeature.PRESET_MODE
        return features

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes with device specific additions."""
        state = {}
        if fan_modes := self._wrapper.fan_speeds:
            state[ATTR_FAN_MODES] = fan_modes
            if fan_mode := self._wrapper.fan_speed:
                state[ATTR_FAN_MODE] = fan_mode

        return state

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if not self._wrapper.is_on:
            return 0
        if self._wrapper.fan_speed is None and self._wrapper.fan_preset:
            return None
        if self.speed_count <= 1:
            return 100
        return ordered_list_item_to_percentage(
            self._wrapper.fan_speeds, self._wrapper.fan_speed
        )

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        if self.preset_modes is None:
            return None
        if not self._wrapper.is_on:
            return None
        return self._wrapper.fan_preset

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        if self.speed_count == 0:
            raise NotImplementedError()

        if percentage == 0:
            if self.preset_mode is None:
                await self.async_turn_off()
            return

        named_speed = percentage_to_ordered_list_item(
            self._wrapper.fan_speeds, percentage
        )
        if not self._wrapper.is_on:
            await self._wrapper.async_turn_on(speed=named_speed)
        else:
            await self._wrapper.async_set_speed(named_speed)
        self._api.async_set_updated()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self.preset_modes is None:
            raise NotImplementedError()
        if not self._wrapper.is_on:
            await self._wrapper.async_turn_on(preset=preset_mode)
        else:
            await self._wrapper.async_set_preset(preset_mode)
        self._api.async_set_updated()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        """Turn on the fan."""
        if preset_mode and self.preset_modes:
            await self.async_set_preset_mode(preset_mode)
        elif percentage or self.speed_count == 1:
            await self.async_set_percentage(percentage or 100)
        else:
            await self._wrapper.async_turn_on()
            self._api.async_set_updated()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        if not self._wrapper.is_on:
            return
        await self._wrapper.async_turn_off()
        self._api.async_set_updated()
