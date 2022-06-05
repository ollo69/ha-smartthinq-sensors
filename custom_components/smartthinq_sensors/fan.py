"""Platform for LGE fan integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from .wideq import DeviceType
from .wideq.fan import FanDevice

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import ordered_list_item_to_percentage, percentage_to_ordered_list_item

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES


ATTR_FAN_MODE = "fan_mode"
ATTR_FAN_MODES = "fan_modes"

SCAN_INTERVAL = timedelta(seconds=120)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up LGE device fan based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES)
    if not lge_devices:
        return

    _LOGGER.debug("Starting LGE ThinQ fan setup...")
    lge_fan = []

    # Fan devices
    lge_fan.extend(
        [
            LGEFan(lge_device)
            for lge_device in lge_devices.get(DeviceType.FAN, [])
        ]
    )

    # Air Purifier devices
    lge_fan.extend(
        [
            LGEFan(lge_device, icon="mdi:air-purifier")
            for lge_device in lge_devices.get(DeviceType.AIR_PURIFIER, [])
        ]
    )

    async_add_entities(lge_fan)


class LGEBaseFan(CoordinatorEntity, FanEntity):
    """Base fan device."""

    def __init__(self, api: LGEDevice):
        """Initialize the base fan."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        We overwrite coordinator property default setting because we need
        to poll to avoid the effect that after changing a climate settings
        it is immediately set to prev state. The async_update method here
        do nothing because the real update is performed by coordinator.
        """
        return True

    async def async_update(self) -> None:
        """Update the entity.

        This is a fake update, real update is done by coordinator.
        """
        return

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGEFan(LGEBaseFan):
    """LG Fan device."""

    def __init__(self, api: LGEDevice, *, icon: str = None) -> None:
        """Initialize the fan."""
        super().__init__(api)
        self._device: FanDevice = api.device
        self._attr_name = api.name
        self._attr_unique_id = f"{api.unique_id}-FAN"
        if icon:
            self._attr_icon = icon
        self._attr_speed_count = len(self._device.fan_speeds)
        if len(self._device.fan_presets) > 0:
            self._attr_preset_modes = self._device.fan_presets

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        features = 0
        if self.speed_count > 0:
            features |= FanEntityFeature.SET_SPEED
        if self.preset_modes is not None:
            features |= FanEntityFeature.PRESET_MODE
        return features

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes with device specific additions."""
        state = {}
        if fan_modes := self._device.fan_speeds:
            state[ATTR_FAN_MODES] = fan_modes
            if fan_mode := self._api.state.fan_speed:
                state[ATTR_FAN_MODE] = fan_mode

        return state

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if not self._api.state.is_on:
            return 0
        if self.speed_count == 0:
            return 100
        if self._api.state.fan_speed is None:
            return None
        return ordered_list_item_to_percentage(
            self._device.fan_speeds, self._api.state.fan_speed
        )

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        if self.preset_modes is None:
            return None
        return self._api.state.fan_preset

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        if percentage == 0 and self.preset_mode is None:
            await self.async_turn_off()
            return
        if self.speed_count == 0:
            return
        named_speed = percentage_to_ordered_list_item(self._device.fan_speeds, percentage)
        await self._device.set_fan_speed(named_speed)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self.preset_modes is None:
            raise NotImplementedError()
        await self._device.set_fan_preset(preset_mode)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        """Turn on the fan."""
        await self._device.power(True)
        if percentage:
            await self.async_set_percentage(percentage)
        elif preset_mode and self.preset_modes:
            await self.async_set_preset_mode(preset_mode)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        await self._device.power(False)
