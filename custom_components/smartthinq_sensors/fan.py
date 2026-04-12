"""Platform for LGE fan integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from thinqconnect.devices.const import Property as ThinQProperty

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

from .const import LGE_DISCOVERY_NEW
from .lge_device import LGEDevice
from .official_control import (
    async_call_official_post,
    async_call_official_turn_off,
    async_call_official_turn_on,
)
from .runtime_data import get_lge_devices
from .wideq import DeviceType, HoodFeatures, MicroWaveFeatures

ATTR_FAN_MODE = "fan_mode"
ATTR_FAN_MODES = "fan_modes"
DEFAULT_KEY = "default"

_LOGGER = logging.getLogger(__name__)

OFFICIAL_OPERATION_KEYS = {
    DeviceType.FAN: (ThinQProperty.CEILING_FAN_OPERATION_MODE,),
    DeviceType.AIR_PURIFIER: (
        ThinQProperty.AIR_PURIFIER_OPERATION_MODE,
        ThinQProperty.AIR_FAN_OPERATION_MODE,
    ),
}
OFFICIAL_SPEED_KEYS = {
    DeviceType.FAN: (ThinQProperty.WIND_STRENGTH,),
    DeviceType.AIR_PURIFIER: (ThinQProperty.WIND_STRENGTH,),
    DeviceType.HOOD: (ThinQProperty.FAN_SPEED,),
    DeviceType.MICROWAVE: (ThinQProperty.FAN_SPEED,),
}


@dataclass(frozen=True)
class LGEFanWrapperDescription:
    """A class that describes LG fan wrapper."""

    fanspeed_fn: Callable[[Any], str] | None
    fanspeeds_fn: Callable[[Any], list[str]]
    set_fanspeed_fn: Callable[[Any, str], Awaitable[None]]
    fanpreset_fn: Callable[[Any], str] | None = None
    fanpresets_fn: Callable[[Any], list[str]] | None = None
    set_fanpreset_fn: Callable[[Any, str], Awaitable[None]] | None = None
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


@dataclass(frozen=True)
class ThinQFanRequiredKeysMixin:
    """Mixin for required keys."""

    wrapper_description: LGEFanWrapperDescription


@dataclass(frozen=True)
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
    lge_cfg_devices = get_lge_devices(hass)

    _LOGGER.debug("Starting LGE ThinQ fan setup")

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
        self._turn_off_speed: str | None = None
        self._last_speed: str | None = None
        self._avl_speeds: list[str] = self._get_fan_speeds()

    def _get_fan_speeds(self) -> list[str]:
        """List of available speeds."""
        avl_speeds = self._description.fanspeeds_fn(self._api).copy()
        if self._description.turn_off_fn is None:
            self._turn_off_speed = avl_speeds.pop(0)
        return avl_speeds

    def _normalize_speed_value(self, speed: Any) -> str | None:
        """Normalize a speed value to the canonical item from available speeds."""
        if speed is None:
            return None

        speed_text = str(speed)
        speed_lookup = {
            candidate.casefold(): candidate for candidate in self._avl_speeds
        }
        if self._turn_off_speed is not None:
            speed_lookup[self._turn_off_speed.casefold()] = self._turn_off_speed
        return speed_lookup.get(speed_text.casefold(), speed_text)

    @property
    def fan_speed(self) -> str | None:
        """Return current speed."""
        logical_key = {
            DeviceType.FAN: "fan.fan_speed",
            DeviceType.AIR_PURIFIER: "air_purifier.fan_speed",
        }.get(self._api.type)
        if logical_key is not None:
            hybrid_speed = self._api.get_hybrid_value(logical_key)
            if hybrid_speed is not None:
                return self._normalize_speed_value(hybrid_speed)
        if self._description.fanspeed_fn:
            return self._normalize_speed_value(self._description.fanspeed_fn(self._api))
        if feature := self._feature_key:
            return self._normalize_speed_value(self._api.state.device_features.get(feature))
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
        logical_key = {
            DeviceType.FAN: "fan.is_on",
            DeviceType.AIR_PURIFIER: "air_purifier.is_on",
            DeviceType.HOOD: "hood.is_on",
            DeviceType.MICROWAVE: "microwave.is_on",
        }.get(self._api.type)
        if logical_key is not None:
            hybrid_is_on = self._api.get_hybrid_value(logical_key)
            if hybrid_is_on is not None:
                return bool(hybrid_is_on)
        if self._description.turn_off_fn is None:
            return self.fan_speed != self._turn_off_speed
        return cast(bool, self._api.state.is_on)

    async def async_set_speed(self, speed: str) -> None:
        """Set fan speed."""
        await self._description.set_fanspeed_fn(self._api, speed)

    async def async_set_preset(self, preset: str) -> None:
        """Set fan preset."""
        if self._description.set_fanpreset_fn is None:
            raise NotImplementedError
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
            if self._turn_off_speed is not None:
                await self.async_set_speed(self._turn_off_speed)
        else:
            await self._description.turn_off_fn(self._api)


class LGEBaseFan(CoordinatorEntity, FanEntity):
    """Base fan device."""

    def __init__(self, api: LGEDevice) -> None:
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
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self.speed_count > 1:
            features |= FanEntityFeature.SET_SPEED
        if self.preset_modes is not None:
            features |= FanEntityFeature.PRESET_MODE
        return features

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the optional state attributes with device specific additions."""
        state: dict[str, Any] = {}
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
        if (fan_speed := self._wrapper.fan_speed) is None:
            return None
        return ordered_list_item_to_percentage(
            self._wrapper.fan_speeds, fan_speed
        )

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        if self.preset_modes is None:
            return None
        if not self._wrapper.is_on:
            return None
        return self._wrapper.fan_preset

    async def _async_try_official_set_speed(self, named_speed: str) -> bool:
        """Try setting fan speed with the official API."""
        speed_keys = OFFICIAL_SPEED_KEYS.get(self._api.type)
        if not speed_keys:
            return False
        if not self._wrapper.is_on:
            operation_keys = OFFICIAL_OPERATION_KEYS.get(self._api.type)
            if operation_keys:
                await async_call_official_turn_on(self._api, *operation_keys)
        return await async_call_official_post(
            self._api,
            str(named_speed).lower(),
            *speed_keys,
        )

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        if self.speed_count == 0:
            raise NotImplementedError

        if percentage == 0:
            if self.preset_mode is None:
                await self.async_turn_off()
            return

        named_speed = percentage_to_ordered_list_item(
            self._wrapper.fan_speeds, percentage
        )
        if await self._async_try_official_set_speed(named_speed):
            return
        if not self._wrapper.is_on:
            await self._wrapper.async_turn_on(speed=named_speed)
        else:
            await self._wrapper.async_set_speed(named_speed)
        self._api.async_set_updated()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self.preset_modes is None:
            raise NotImplementedError
        if not self._wrapper.is_on:
            await self._wrapper.async_turn_on(preset=preset_mode)
        else:
            await self._wrapper.async_set_preset(preset_mode)
        self._api.async_set_updated()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        if preset_mode and self.preset_modes:
            await self.async_set_preset_mode(preset_mode)
        elif percentage or self.speed_count == 1:
            await self.async_set_percentage(percentage or 100)
        else:
            operation_keys = OFFICIAL_OPERATION_KEYS.get(self._api.type)
            if operation_keys and await async_call_official_turn_on(
                self._api,
                *operation_keys,
            ):
                return
            await self._wrapper.async_turn_on()
            self._api.async_set_updated()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if not self._wrapper.is_on:
            return
        operation_keys = OFFICIAL_OPERATION_KEYS.get(self._api.type)
        if operation_keys and await async_call_official_turn_off(
            self._api,
            *operation_keys,
        ):
            return
        await self._wrapper.async_turn_off()
        self._api.async_set_updated()
