"""Platform for LGE humidifier integration."""
from __future__ import annotations

from datetime import timedelta
import logging
import voluptuous as vol

from .wideq import FEAT_HUMIDITY, FEAT_TARGET_HUMIDITY, DeviceType
from .wideq.dehumidifier import DeHumidifierDevice

from homeassistant.components.humidifier import HumidifierEntity, HumidifierDeviceClass
from homeassistant.components.humidifier.const import (
    DEFAULT_MAX_HUMIDITY,
    DEFAULT_MIN_HUMIDITY,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES

ATTR_CURRENT_HUMIDITY = "current_humidity"
ATTR_FAN_MODE = "fan_mode"
ATTR_FAN_MODES = "fan_modes"
SERVICE_SET_FAN_MODE = "set_fan_mode"

SCAN_INTERVAL = timedelta(seconds=120)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up LGE device humidifier based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES)
    if not lge_devices:
        return

    _LOGGER.debug("Starting LGE ThinQ humidifier setup...")
    lge_humidifier = []

    # DeHumidifier devices
    lge_humidifier.extend(
        [
            LGEDeHumidifier(lge_device)
            for lge_device in lge_devices.get(DeviceType.DEHUMIDIFIER, [])
        ]
    )

    async_add_entities(lge_humidifier)

    # register services
    platform = current_platform.get()
    platform.async_register_entity_service(
        SERVICE_SET_FAN_MODE,
        {vol.Required(ATTR_FAN_MODE): cv.string},
        "async_set_fan_mode",
    )


class LGEBaseHumidifier(CoordinatorEntity, HumidifierEntity):
    """Base humidifier device."""

    def __init__(self, api: LGEDevice):
        """Initialize the humidifier."""
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


class LGEDeHumidifier(LGEBaseHumidifier):
    """LG DeHumidifier device."""

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the dehumidifier."""
        super().__init__(api)
        self._device: DeHumidifierDevice = api.device
        self._attr_name = api.name
        self._attr_unique_id = f"{api.unique_id}-DEHUM"
        self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
        self._attr_available_modes = self._device.op_modes

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        if self.available_modes:
            return HumidifierEntityFeature.MODES
        return 0

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes with device specific additions."""
        state = {}
        if humidity := self._api.state.device_features.get(FEAT_HUMIDITY):
            state[ATTR_CURRENT_HUMIDITY] = humidity
        if fan_modes := self._device.fan_speeds:
            state[ATTR_FAN_MODES] = fan_modes
            if fan_mode := self._api.state.fan_speed:
                state[ATTR_FAN_MODE] = fan_mode

        return state

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        return self._api.state.is_on

    @property
    def mode(self) -> str | None:
        """Return current operation."""
        return self._api.state.operation_mode

    async def async_set_mode(self, mode: str) -> None:
        """Set new target mode."""
        if mode not in self.available_modes:
            raise ValueError(f"Invalid mode [{mode}]")
        await self._device.set_op_mode(mode)

    @property
    def target_humidity(self) -> int | None:
        """Return the humidity we try to reach."""
        return self._api.state.device_features.get(FEAT_TARGET_HUMIDITY)

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""
        humidity_step = self._device.target_humidity_step or 1
        target_humidity = humidity + (humidity % humidity_step)
        await self._device.set_target_humidity(target_humidity)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        await self._device.power(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        await self._device.power(False)

    @property
    def min_humidity(self) -> int:
        """Return the minimum humidity."""
        if (min_value := self._device.target_humidity_min) is not None:
            return min_value

        return DEFAULT_MIN_HUMIDITY

    @property
    def max_humidity(self) -> int:
        """Return the maximum humidity."""
        if (max_value := self._device.target_humidity_max) is not None:
            return max_value

        return DEFAULT_MAX_HUMIDITY

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        if fan_mode not in self._device.fan_speeds:
            raise ValueError(f"Invalid fan mode [{fan_mode}]")
        await self._device.set_fan_speed(fan_mode)
