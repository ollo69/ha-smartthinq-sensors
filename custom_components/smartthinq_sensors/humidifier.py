"""Platform for LGE humidifier integration."""

from __future__ import annotations

import logging
from typing import Any, cast

from thinqconnect.devices.const import Property as ThinQProperty
import voluptuous as vol

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .official_control import (
    async_call_official_post,
    async_call_official_turn_off,
    async_call_official_turn_on,
)
from .wideq import DehumidifierFeatures, DeviceType
from .wideq.devices.dehumidifier import DeHumidifierDevice

ATTR_CURRENT_HUMIDITY = "current_humidity"
ATTR_FAN_MODE = "fan_mode"
ATTR_FAN_MODES = "fan_modes"
SERVICE_SET_FAN_MODE = "set_fan_mode"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up LGE device humidifier based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ humidifier setup")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        # DeHumidifier devices
        lge_humidifier = [
            LGEDeHumidifier(lge_device)
            for lge_device in lge_devices.get(DeviceType.DEHUMIDIFIER, [])
        ]

        async_add_entities(lge_humidifier)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )

    # register services
    platform = current_platform.get()
    if platform is None:
        return
    platform.async_register_entity_service(
        SERVICE_SET_FAN_MODE,
        {vol.Required(ATTR_FAN_MODE): cv.string},
        "async_set_fan_mode",
    )


class LGEBaseHumidifier(CoordinatorEntity, HumidifierEntity):
    """Base humidifier device."""

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the humidifier."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGEDeHumidifier(LGEBaseHumidifier):
    """LG DeHumidifier device."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the dehumidifier."""
        super().__init__(api)
        self._device: DeHumidifierDevice = api.device
        self._attr_unique_id = f"{api.unique_id}-DEHUM"
        self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER

        self._use_fan_modes = False
        self._attr_available_modes = None
        if len(self._device.op_modes) > 1:
            self._attr_available_modes = self._device.op_modes
        elif len(self._device.fan_speeds) > 1:
            self._attr_available_modes = self._device.fan_speeds
            self._use_fan_modes = True

    @property
    def supported_features(self) -> HumidifierEntityFeature:
        """Return the list of supported features."""
        if self.available_modes:
            return HumidifierEntityFeature.MODES
        return HumidifierEntityFeature(0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the optional state attributes with device specific additions."""
        state: dict[str, Any] = {}
        if humidity := self._api.state.device_features.get(
            DehumidifierFeatures.HUMIDITY
        ):
            state[ATTR_CURRENT_HUMIDITY] = humidity
        if fan_modes := self._device.fan_speeds:
            state[ATTR_FAN_MODES] = fan_modes
            if fan_mode := self._api.state.fan_speed:
                state[ATTR_FAN_MODE] = fan_mode

        return state

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        return cast(bool | None, self._api.state.is_on)

    @property
    def mode(self) -> str | None:
        """Return current operation."""
        if self._use_fan_modes:
            return cast(str | None, self._api.state.fan_speed)
        return cast(str | None, self._api.state.operation_mode)

    async def async_set_mode(self, mode: str) -> None:
        """Set new target mode."""
        if not self.available_modes:
            raise NotImplementedError
        if mode not in self.available_modes:
            raise ValueError(f"Invalid mode [{mode}]")
        if await async_call_official_post(
            self._api,
            mode,
            ThinQProperty.CURRENT_JOB_MODE,
        ):
            return
        if self._use_fan_modes:
            await self._device.set_fan_speed(mode)
        else:
            await self._device.set_op_mode(mode)
        self._api.async_set_updated()

    @property
    def target_humidity(self) -> int | None:
        """Return the humidity we try to reach."""
        return cast(
            int | None,
            self._api.state.device_features.get(DehumidifierFeatures.TARGET_HUMIDITY),
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""
        humidity_step = self._device.target_humidity_step or 1
        target_humidity = humidity + (humidity % humidity_step)
        if await async_call_official_post(
            self._api,
            target_humidity,
            ThinQProperty.TARGET_HUMIDITY,
        ):
            return
        await self._device.set_target_humidity(target_humidity)
        self._api.async_set_updated()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if await async_call_official_turn_on(
            self._api,
            ThinQProperty.DEHUMIDIFIER_OPERATION_MODE,
        ):
            return
        await self._device.power(True)
        self._api.async_set_updated()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if await async_call_official_turn_off(
            self._api,
            ThinQProperty.DEHUMIDIFIER_OPERATION_MODE,
        ):
            return
        await self._device.power(False)
        self._api.async_set_updated()

    @property
    def min_humidity(self) -> int:
        """Return the minimum humidity."""
        return self._device.target_humidity_min

    @property
    def max_humidity(self) -> int:
        """Return the maximum humidity."""
        return self._device.target_humidity_max

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        if fan_mode not in self._device.fan_speeds:
            raise ValueError(f"Invalid fan mode [{fan_mode}]")
        if await async_call_official_post(
            self._api,
            fan_mode,
            ThinQProperty.WIND_STRENGTH,
        ):
            return
        await self._device.set_fan_speed(fan_mode)
        self._api.async_set_updated()
