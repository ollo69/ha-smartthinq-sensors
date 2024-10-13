"""Platform for LGE climate integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

import voluptuous as vol

from homeassistant.components.climate import ClimateEntity, ClimateEntityDescription
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import TEMP_UNIT_LOOKUP, LGERefrigeratorDevice
from .wideq import AirConditionerFeatures, DeviceType, TemperatureUnit
from .wideq.devices.ac import (
    AWHP_MAX_TEMP,
    AWHP_MIN_TEMP,
    ACFanSpeed,
    ACMode,
    AirConditionerDevice,
)

# general ac attributes
ATTR_FRIDGE = "fridge"
ATTR_FREEZER = "freezer"
ATTR_SWING_HORIZONTAL = "swing_mode_horizontal"
ATTR_SWING_VERTICAL = "swing_mode_vertical"
HVAC_MODE_NONE = "--"
SWING_PREFIX = ["Vertical", "Horizontal"]

# service definitions
SERVICE_SET_SLEEP_TIME = "set_sleep_time"

HVAC_MODE_LOOKUP: dict[str, HVACMode] = {
    ACMode.AI.name: HVACMode.AUTO,
    ACMode.HEAT.name: HVACMode.HEAT,
    ACMode.DRY.name: HVACMode.DRY,
    ACMode.COOL.name: HVACMode.COOL,
    ACMode.FAN.name: HVACMode.FAN_ONLY,
    ACMode.ACO.name: HVACMode.HEAT_COOL,
}

FAN_MODE_LOOKUP: dict[str, str] = {
    ACFanSpeed.AUTO.name: FAN_AUTO,
    ACFanSpeed.HIGH.name: FAN_HIGH,
    ACFanSpeed.LOW.name: FAN_LOW,
    ACFanSpeed.MID.name: FAN_MEDIUM,
    ACFanSpeed.NATURE.name: FAN_DIFFUSE,
}
FAN_MODE_REVERSE_LOOKUP = {v: k for k, v in FAN_MODE_LOOKUP.items()}

PRESET_MODE_LOOKUP: dict[str, dict[str, HVACMode]] = {
    ACMode.ENERGY_SAVING.name: {"preset": PRESET_ECO, "hvac": HVACMode.COOL},
    ACMode.ENERGY_SAVER.name: {"preset": PRESET_ECO, "hvac": HVACMode.COOL},
}

DEFAULT_AC_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQRefClimateRequiredKeysMixin:
    """Mixin for required keys."""

    range_temp_fn: Callable[[Any], list[float]]
    set_temp_fn: Callable[[Any, float], Awaitable[None]]
    temp_fn: Callable[[Any], float | str]


@dataclass
class ThinQRefClimateEntityDescription(
    ClimateEntityDescription, ThinQRefClimateRequiredKeysMixin
):
    """A class that describes ThinQ climate entities."""


REFRIGERATOR_CLIMATE: tuple[ThinQRefClimateEntityDescription, ...] = (
    ThinQRefClimateEntityDescription(
        key=ATTR_FRIDGE,
        name="Fridge",
        icon="mdi:fridge-top",
        range_temp_fn=lambda x: x.device.fridge_target_temp_range,
        set_temp_fn=lambda x, y: x.device.set_fridge_target_temp(y),
        temp_fn=lambda x: x.temp_fridge,
    ),
    ThinQRefClimateEntityDescription(
        key=ATTR_FREEZER,
        name="Freezer",
        icon="mdi:fridge-bottom",
        range_temp_fn=lambda x: x.device.freezer_target_temp_range,
        set_temp_fn=lambda x, y: x.device.set_freezer_target_temp(y),
        temp_fn=lambda x: x.temp_freezer,
    ),
)


def remove_prefix(text: str, prefix: str) -> str:
    """Remove a prefix from a string."""
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up LGE device climate based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ climate setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        # AC devices
        lge_climates = [
            LGEACClimate(lge_device)
            for lge_device in lge_devices.get(DeviceType.AC, [])
        ]

        # Refrigerator devices
        lge_climates.extend(
            [
                LGERefrigeratorClimate(lge_device, refrigerator_desc)
                for refrigerator_desc in REFRIGERATOR_CLIMATE
                for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
            ]
        )

        async_add_entities(lge_climates)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )

    # register services
    platform = current_platform.get()
    platform.async_register_entity_service(
        SERVICE_SET_SLEEP_TIME,
        {vol.Required("sleep_time"): int},
        "async_set_sleep_time",
    )


class LGEClimate(CoordinatorEntity, ClimateEntity):
    """Base climate device."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, api: LGEDevice):
        """Initialize the climate."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available

    async def async_set_sleep_time(self, sleep_time: int) -> None:
        """Call the set sleep time command for AC devices."""
        raise NotImplementedError()


class LGEACClimate(LGEClimate):
    """Air-to-Air climate device."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the climate."""
        super().__init__(api)
        self._device: AirConditionerDevice = api.device
        self._attr_unique_id = f"{api.unique_id}-AC"
        self._attr_fan_modes = [
            FAN_MODE_LOOKUP.get(s, s) for s in self._device.fan_speeds
        ]
        self._attr_swing_modes = [
            f"{SWING_PREFIX[0]}{mode}" for mode in self._device.vertical_step_modes
        ] + [f"{SWING_PREFIX[1]}{mode}" for mode in self._device.horizontal_step_modes]
        self._attr_preset_mode = None

        self._hvac_mode_lookup: dict[str, HVACMode] | None = None
        self._preset_mode_lookup: dict[str, str] | None = None
        self._support_ver_swing = len(self._device.vertical_step_modes) > 0
        self._support_hor_swing = len(self._device.horizontal_step_modes) > 0
        self._set_hor_swing = self._support_hor_swing and not self._support_ver_swing

    def _available_hvac_modes(self) -> dict[str, HVACMode]:
        """Return available hvac modes from lookup dict."""
        if self._hvac_mode_lookup is None:
            self._hvac_mode_lookup = {
                key: mode
                for key, mode in HVAC_MODE_LOOKUP.items()
                if key in self._device.op_modes
            }
            if not self._hvac_mode_lookup:
                self._hvac_mode_lookup = {HVAC_MODE_NONE: HVACMode.AUTO}

        return self._hvac_mode_lookup

    def _available_preset_modes(self) -> dict[str, str]:
        """Return available preset modes from lookup dict."""
        if self._preset_mode_lookup is None:
            hvac_modes = list(self._available_hvac_modes().values())
            modes = {}
            for key, mode in PRESET_MODE_LOOKUP.items():
                if key not in self._device.op_modes:
                    continue
                # skip preset mode with invalid hvac mode associated
                if mode["hvac"] not in hvac_modes:
                    continue
                # invert key and mode to avoid duplicated preset modes
                modes[mode["preset"]] = key
            if modes:
                self._attr_preset_mode = PRESET_NONE
            self._preset_mode_lookup = {v: k for k, v in modes.items()}
        return self._preset_mode_lookup

    def _get_swing_mode(self, hor_mode=False) -> str | None:
        """Return the current swing mode for vert of hor mode."""
        if hor_mode:
            mode = self._api.state.horizontal_step_mode
        else:
            mode = self._api.state.vertical_step_mode
        if mode:
            return f"{SWING_PREFIX[1 if hor_mode else 0]}{mode}"
        return None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        features = DEFAULT_AC_FEATURES
        if len(self.fan_modes) > 0:
            features |= ClimateEntityFeature.FAN_MODE
        if self.preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        if self._support_ver_swing or self._support_hor_swing:
            features |= ClimateEntityFeature.SWING_MODE
        return features

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes with device specific additions."""
        attr = {}
        if self._support_hor_swing:
            attr[ATTR_SWING_HORIZONTAL] = self._get_swing_mode(True)
        if self._support_ver_swing:
            attr[ATTR_SWING_VERTICAL] = self._get_swing_mode(False)

        return attr

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return self._device.target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._device.temperature_unit == TemperatureUnit.FAHRENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation i.e. heat, cool mode."""
        op_mode: str | None = self._api.state.operation_mode
        if not self._api.state.is_on or op_mode is None:
            if self._attr_preset_mode:
                self._attr_preset_mode = PRESET_NONE
            return HVACMode.OFF
        presets = self._available_preset_modes()
        if op_mode in presets:
            self._attr_preset_mode = presets[op_mode]
            return PRESET_MODE_LOOKUP[op_mode]["hvac"]
        if self._attr_preset_mode:
            self._attr_preset_mode = PRESET_NONE
        modes = self._available_hvac_modes()
        return modes.get(op_mode, HVACMode.AUTO)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self._device.power(False)
            self._api.async_set_updated()
            return

        modes = self._available_hvac_modes()
        reverse_lookup = {v: k for k, v in modes.items()}
        if (operation_mode := reverse_lookup.get(hvac_mode)) is None:
            raise ValueError(f"Invalid hvac_mode [{hvac_mode}]")

        if not self._api.state.is_on:
            await self._device.power(True)
        if operation_mode != HVAC_MODE_NONE:
            await self._device.set_op_mode(operation_mode)
        self._api.async_set_updated()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        modes = self._available_hvac_modes()
        return [HVACMode.OFF] + list(modes.values())

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if not (modes := self._available_preset_modes()):
            raise NotImplementedError()

        reverse_lookup = {v: k for k, v in modes.items()}
        if preset_mode == PRESET_NONE:
            curr_preset = self._attr_preset_mode
            if curr_preset != PRESET_NONE and self._api.state.is_on:
                op_mode = reverse_lookup[curr_preset]
                await self.async_set_hvac_mode(PRESET_MODE_LOOKUP[op_mode]["hvac"])
            return

        if (operation_mode := reverse_lookup.get(preset_mode)) is None:
            raise ValueError(f"Invalid preset_mode [{preset_mode}]")

        if not self._api.state.is_on:
            await self._device.power(True)
        await self._device.set_op_mode(operation_mode)
        self._api.async_set_updated()

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes."""
        modes = self._available_preset_modes()
        if not modes:
            return None
        return [PRESET_NONE] + list(modes.values())

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._api.state.current_temp

    @property
    def current_humidity(self) -> int | None:
        return self._api.state.device_features.get(AirConditionerFeatures.HUMIDITY)

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._api.state.target_temp

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if hvac_mode := kwargs.get(ATTR_HVAC_MODE):
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
            if hvac_mode == HVACMode.OFF:
                return

        if (new_temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._device.set_target_temp(new_temp)
            self._api.async_set_updated()

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        speed = self._api.state.fan_speed
        return FAN_MODE_LOOKUP.get(speed, speed)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        lg_fan_mode = FAN_MODE_REVERSE_LOOKUP.get(fan_mode, fan_mode)
        if lg_fan_mode not in self._device.fan_speeds:
            raise ValueError(f"Invalid fan mode [{fan_mode}]")
        await self._device.set_fan_speed(lg_fan_mode)
        self._api.async_set_updated()

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode setting."""
        if self._set_hor_swing and self._support_hor_swing:
            return self._get_swing_mode(True)
        return self._get_swing_mode(False)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing mode."""
        avl_mode = False
        curr_mode = None
        set_hor_swing = swing_mode.startswith(SWING_PREFIX[1])
        dev_mode = remove_prefix(swing_mode, SWING_PREFIX[1 if set_hor_swing else 0])
        if set_hor_swing:
            if dev_mode in self._device.horizontal_step_modes:
                avl_mode = True
                curr_mode = self._api.state.horizontal_step_mode
        elif swing_mode.startswith(SWING_PREFIX[0]):
            if dev_mode in self._device.vertical_step_modes:
                avl_mode = True
                curr_mode = self._api.state.vertical_step_mode

        if not avl_mode:
            raise ValueError(f"Invalid swing_mode [{swing_mode}].")

        if curr_mode != dev_mode:
            if set_hor_swing:
                await self._device.set_horizontal_step_mode(dev_mode)
            else:
                await self._device.set_vertical_step_mode(dev_mode)
            self._api.async_set_updated()
        self._set_hor_swing = set_hor_swing

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self._device.power(True)
        self._api.async_set_updated()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self._device.power(False)
        self._api.async_set_updated()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if (min_value := self._device.target_temperature_min) is not None:
            return min_value
        return self._device.conv_temp_unit(
            AWHP_MIN_TEMP if self._device.is_air_to_water else DEFAULT_MIN_TEMP
        )

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if (max_value := self._device.target_temperature_max) is not None:
            return max_value
        return self._device.conv_temp_unit(
            AWHP_MAX_TEMP if self._device.is_air_to_water else DEFAULT_MAX_TEMP
        )

    async def async_set_sleep_time(self, sleep_time: int) -> None:
        """Call the set sleep time command for AC devices."""
        await self._device.set_reservation_sleep_time(sleep_time)


class LGERefrigeratorClimate(LGEClimate):
    """Refrigerator climate device."""

    entity_description: ThinQRefClimateEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQRefClimateEntityDescription,
    ) -> None:
        """Initialize the climate."""
        super().__init__(api)
        self._wrap_device = LGERefrigeratorDevice(api)
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-AC"
        self._attr_hvac_modes = [HVACMode.AUTO]
        self._attr_hvac_mode = HVACMode.AUTO

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        if not self._wrap_device.device.set_values_allowed:
            return ClimateEntityFeature(0)
        return ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return self._wrap_device.device.target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._api.state:
            unit = self._api.state.temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, UnitOfTemperature.CELSIUS)
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        target_temp = self.entity_description.temp_fn(self._wrap_device)
        if target_temp is None:
            return None
        try:
            return int(target_temp)
        except ValueError:
            return None

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if (new_temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.entity_description.set_temp_fn(self._wrap_device, new_temp)
            self._api.async_set_updated()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self.entity_description.range_temp_fn(self._wrap_device)[0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self.entity_description.range_temp_fn(self._wrap_device)[1]
