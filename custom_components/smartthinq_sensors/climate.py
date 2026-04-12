"""Platform for LGE climate integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from thinqconnect.integration import ExtendedProperty
import voluptuous as vol

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LGE_DISCOVERY_NEW
from .device_helpers import TEMP_UNIT_LOOKUP, LGEACDevice, LGERefrigeratorDevice
from .lge_device import LGEDevice
from .official_control import (
    async_call_official_set_fan_mode,
    async_call_official_set_hvac_mode,
    async_call_official_set_target_temperature,
    async_call_official_turn_off,
    async_call_official_turn_on,
)
from .runtime_data import get_lge_devices
from .wideq import DeviceType, TemperatureUnit
from .wideq.devices.ac import ACFanSpeed, ACMode, AirConditionerDevice

# general ac attributes
ATTR_FRIDGE = "fridge"
ATTR_FREEZER = "freezer"
HVAC_MODE_NONE = "--"

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
OFFICIAL_HVAC_MODE_LOOKUP: dict[HVACMode, str] = {
    HVACMode.AUTO: "auto",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "air_dry",
    HVACMode.COOL: "cool",
    HVACMode.FAN_ONLY: "fan",
    HVACMode.HEAT_COOL: "auto",
}

PRESET_MODE_LOOKUP: dict[str, dict[str, Any]] = {
    ACMode.ENERGY_SAVING.name: {"preset": PRESET_ECO, "hvac": HVACMode.COOL},
    ACMode.ENERGY_SAVER.name: {"preset": PRESET_ECO, "hvac": HVACMode.COOL},
}

DEFAULT_AC_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThinQRefClimateRequiredKeysMixin:
    """Mixin for required keys."""

    range_temp_fn: Callable[[Any], list[float]]
    set_temp_fn: Callable[[Any, float], Awaitable[None]]
    temp_fn: Callable[[Any], float | str]


@dataclass(frozen=True)
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
    lge_cfg_devices = get_lge_devices(hass)

    _LOGGER.debug("Starting LGE ThinQ climate setup")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        # AC devices
        lge_climates: list[LGEClimate] = [
            LGEACClimate(lge_device)
            for lge_device in lge_devices.get(DeviceType.AC, [])
        ]

        # Refrigerator devices
        lge_climates.extend(
            [
                LGERefrigeratorClimate(lge_device, refrigerator_desc)
                for refrigerator_desc in REFRIGERATOR_CLIMATE
                for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
                if not (
                    refrigerator_desc.key == ATTR_FRIDGE
                    and not LGERefrigeratorDevice(lge_device).supports_fridge_compartment
                )
                if not (
                    refrigerator_desc.key == ATTR_FREEZER
                    and not LGERefrigeratorDevice(lge_device).supports_freezer_compartment
                )
            ]
        )

        async_add_entities(lge_climates)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )

    # register services
    platform = current_platform.get()
    if platform is None:
        return
    platform.async_register_entity_service(
        SERVICE_SET_SLEEP_TIME,
        {vol.Required("sleep_time"): int},
        "async_set_sleep_time",
    )


class LGEClimate(CoordinatorEntity, ClimateEntity):
    """Base climate device."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, api: LGEDevice) -> None:
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
        raise NotImplementedError


class LGEACClimate(LGEClimate):
    """Air-to-Air climate device."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the climate."""
        super().__init__(api)
        self._device: AirConditionerDevice = api.device
        self._wrap_device = LGEACDevice(api)
        self._attr_unique_id = f"{api.unique_id}-AC"
        self._attr_fan_modes = [
            FAN_MODE_LOOKUP.get(s, s) for s in self._device.fan_speeds
        ]

        self._use_h_mode = False
        self._attr_swing_modes = self._device.vertical_step_modes or None
        self._attr_swing_horizontal_modes = self._device.horizontal_step_modes or None
        if not self._attr_swing_modes and self._attr_swing_horizontal_modes:
            self._attr_swing_modes = self._attr_swing_horizontal_modes
            self._attr_swing_horizontal_modes = None
            self._use_h_mode = True

        self._attr_preset_mode = None

        self._hvac_mode_lookup: dict[str, HVACMode] | None = None
        self._preset_mode_lookup: dict[str, str] | None = None
        self._attr_supported_features = DEFAULT_AC_FEATURES
        if self._attr_fan_modes:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        if self._attr_swing_modes:
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
        if self._attr_swing_horizontal_modes:
            self._attr_supported_features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE

    def _is_on_for_control(self) -> bool:
        """Return the best available power state for control decisions."""
        return self._wrap_device.is_on

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
            modes: dict[str, str] = {}
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
                self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
            self._preset_mode_lookup = {v: k for k, v in modes.items()}
        return self._preset_mode_lookup

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
        op_mode = self._wrap_device.operation_mode
        if not self._wrap_device.is_on or op_mode is None:
            if self._attr_preset_mode:
                self._attr_preset_mode = PRESET_NONE
            return HVACMode.OFF
        presets = self._available_preset_modes()
        if op_mode in presets:
            self._attr_preset_mode = presets[op_mode]
            return cast(HVACMode, PRESET_MODE_LOOKUP[op_mode]["hvac"])
        if self._attr_preset_mode:
            self._attr_preset_mode = PRESET_NONE
        modes = self._available_hvac_modes()
        return modes.get(op_mode, HVACMode.AUTO)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            if await async_call_official_turn_off(
                self._api,
                ExtendedProperty.CLIMATE_AIR_CONDITIONER,
            ):
                return
            await self._device.power(False)
            self._api.async_set_updated()
            return

        modes = self._available_hvac_modes()
        reverse_lookup = {v: k for k, v in modes.items()}
        if (operation_mode := reverse_lookup.get(hvac_mode)) is None:
            raise ValueError(f"Invalid hvac_mode [{hvac_mode}]")

        official_hvac_mode = OFFICIAL_HVAC_MODE_LOOKUP.get(hvac_mode)
        if official_hvac_mode is not None:
            if not self._is_on_for_control():
                await async_call_official_turn_on(
                    self._api,
                    ExtendedProperty.CLIMATE_AIR_CONDITIONER,
                )
            if operation_mode == HVAC_MODE_NONE or await async_call_official_set_hvac_mode(
                self._api,
                official_hvac_mode,
                ExtendedProperty.CLIMATE_AIR_CONDITIONER,
            ):
                return

        if not self._is_on_for_control():
            await self._device.power(True)
        if operation_mode != HVAC_MODE_NONE:
            await self._device.set_op_mode(operation_mode)
        self._api.async_set_updated()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        modes = self._available_hvac_modes()
        return [HVACMode.OFF, *list(modes.values())]

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if not (modes := self._available_preset_modes()):
            raise NotImplementedError

        reverse_lookup = {v: k for k, v in modes.items()}
        if preset_mode == PRESET_NONE:
            curr_preset = self._attr_preset_mode
            if (
                curr_preset is not None
                and curr_preset != PRESET_NONE
                and self._is_on_for_control()
            ):
                op_mode = reverse_lookup[curr_preset]
                await self.async_set_hvac_mode(PRESET_MODE_LOOKUP[op_mode]["hvac"])
            return

        if (operation_mode := reverse_lookup.get(preset_mode)) is None:
            raise ValueError(f"Invalid preset_mode [{preset_mode}]")

        if not self._is_on_for_control():
            await async_call_official_turn_on(
                self._api,
                ExtendedProperty.CLIMATE_AIR_CONDITIONER,
            )
        if await async_call_official_set_hvac_mode(
            self._api,
            operation_mode.lower(),
            ExtendedProperty.CLIMATE_AIR_CONDITIONER,
        ):
            return

        if not self._is_on_for_control():
            await self._device.power(True)
        await self._device.set_op_mode(operation_mode)
        self._api.async_set_updated()

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes."""
        modes = self._available_preset_modes()
        if not modes:
            return None
        return [PRESET_NONE, *list(modes.values())]

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._wrap_device.current_temperature

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        return self._wrap_device.current_humidity

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._wrap_device.target_temperature

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if hvac_mode := kwargs.get(ATTR_HVAC_MODE):
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
            if hvac_mode == HVACMode.OFF:
                return

        if (new_temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            if await async_call_official_set_target_temperature(
                self._api,
                float(new_temp),
                ExtendedProperty.CLIMATE_AIR_CONDITIONER,
            ):
                return
            await self._device.set_target_temp(float(new_temp))
            self._api.async_set_updated()

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        speed = self._wrap_device.fan_speed
        if speed is None:
            return None
        return FAN_MODE_LOOKUP.get(speed, speed)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        lg_fan_mode = FAN_MODE_REVERSE_LOOKUP.get(fan_mode, fan_mode)
        if lg_fan_mode not in self._device.fan_speeds:
            raise ValueError(f"Invalid fan mode [{fan_mode}]")
        if await async_call_official_set_fan_mode(
            self._api,
            str(lg_fan_mode).lower(),
            ExtendedProperty.CLIMATE_AIR_CONDITIONER,
        ):
            return
        await self._device.set_fan_speed(lg_fan_mode)
        self._api.async_set_updated()

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode setting."""
        if self._use_h_mode:
            return self._wrap_device.horizontal_step_mode
        return self._wrap_device.vertical_step_mode

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation."""
        if swing_mode not in (self.swing_modes or []):
            raise ValueError(f"Invalid swing_mode [{swing_mode}].")

        if swing_mode != self.swing_mode:
            if self._use_h_mode:
                await self._device.set_horizontal_step_mode(swing_mode)
            else:
                await self._device.set_vertical_step_mode(swing_mode)
            self._api.async_set_updated()

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing mode setting."""
        return self._wrap_device.horizontal_step_mode

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Set new target horizontal swing operation."""
        if swing_horizontal_mode not in (self.swing_horizontal_modes or []):
            raise ValueError(
                f"Invalid horizontal swing_mode [{swing_horizontal_mode}]."
            )

        if swing_horizontal_mode != self.swing_horizontal_mode:
            await self._device.set_horizontal_step_mode(swing_horizontal_mode)
            self._api.async_set_updated()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if await async_call_official_turn_on(
            self._api,
            ExtendedProperty.CLIMATE_AIR_CONDITIONER,
        ):
            return
        await self._device.power(True)
        self._api.async_set_updated()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        if await async_call_official_turn_off(
            self._api,
            ExtendedProperty.CLIMATE_AIR_CONDITIONER,
        ):
            return
        await self._device.power(False)
        self._api.async_set_updated()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._device.target_temperature_min

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._device.target_temperature_max

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
        return cast(float, self._wrap_device.device.target_temperature_step)

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
        try:
            return float(target_temp)
        except (TypeError, ValueError):
            return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (new_temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.entity_description.set_temp_fn(self._wrap_device, float(new_temp))
            self._api.async_set_updated()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self.entity_description.range_temp_fn(self._wrap_device)[0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self.entity_description.range_temp_fn(self._wrap_device)[1]
