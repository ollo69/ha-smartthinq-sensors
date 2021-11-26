"""Platform for LGE climate integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable, List, Tuple


from .wideq import FEAT_HUMIDITY, FEAT_OUT_WATER_TEMP
from .wideq.ac import AirConditionerDevice, ACMode
from .wideq.device import UNIT_TEMP_FAHRENHEIT, DeviceType

from homeassistant.components.climate import ClimateEntity, ClimateEntityDescription
from homeassistant.components.climate.const import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
    SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES
from .device_helpers import (
    TEMP_UNIT_LOOKUP,
    LGERefrigeratorDevice,
    get_entity_name,
)

# general ac attributes
ATTR_FRIDGE = "fridge"
ATTR_FREEZER = "freezer"

HVAC_MODE_LOOKUP = {
    ACMode.ENERGY_SAVER.name: HVAC_MODE_AUTO,
    ACMode.AI.name: HVAC_MODE_AUTO,
    ACMode.HEAT.name: HVAC_MODE_HEAT,
    ACMode.DRY.name: HVAC_MODE_DRY,
    ACMode.COOL.name: HVAC_MODE_COOL,
    ACMode.FAN.name: HVAC_MODE_FAN_ONLY,
    ACMode.ACO.name: HVAC_MODE_HEAT_COOL,
}

ATTR_SWING_HORIZONTAL = "swing_mode_horizontal"
ATTR_SWING_VERTICAL = "swing_mode_vertical"
SWING_PREFIX = ["Vertical", "Horizontal"]

SCAN_INTERVAL = timedelta(seconds=120)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQRefClimateRequiredKeysMixin:
    """Mixin for required keys."""
    range_temp_fn: Callable[[Any], List[float]]
    set_temp_fn: Callable[[Any, float], None]
    temp_fn: Callable[[Any], float | str]


@dataclass
class ThinQRefClimateEntityDescription(
    ClimateEntityDescription, ThinQRefClimateRequiredKeysMixin
):
    """A class that describes ThinQ climate entities."""


REFRIGERATOR_CLIMATE: Tuple[ThinQRefClimateEntityDescription, ...] = (
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
        return text[len(prefix):]
    return text


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up LGE device climate based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES)
    if not lge_devices:
        return

    lge_climates = []

    # AC devices
    lge_climates.extend(
        [
            LGEACClimate(lge_device)
            for lge_device in lge_devices.get(DeviceType.AC, [])
        ]
    )

    # Refrigerator devices
    lge_climates.extend(
        [
            LGERefrigeratorClimate(lge_device, refrigerator_desc)
            for refrigerator_desc in REFRIGERATOR_CLIMATE
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
        ]
    )

    async_add_entities(lge_climates)


class LGEClimate(CoordinatorEntity, ClimateEntity):
    """Base climate device."""

    def __init__(self, api: LGEDevice):
        """Initialize the climate."""
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


class LGEACClimate(LGEClimate):
    """Air-to-Air climate device."""

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the climate."""
        super().__init__(api)
        self._device: AirConditionerDevice = api.device
        self._attr_name = api.name
        self._attr_unique_id = f"{api.unique_id}-AC"

        self._hvac_mode_lookup = None
        self._support_ver_swing = len(self._device.vertical_step_modes) > 0
        self._support_hor_swing = len(self._device.horizontal_step_modes) > 0
        self._set_hor_swing = self._support_hor_swing and not self._support_ver_swing

    def _available_hvac_modes(self):
        """Return available hvac modes from lookup dict."""
        if self._hvac_mode_lookup is None:
            modes = {}
            for key, mode in HVAC_MODE_LOOKUP.items():
                if key in self._device.op_modes:
                    # invert key and mode to avoid duplicated HVAC modes
                    modes[mode] = key
            self._hvac_mode_lookup = {v: k for k, v in modes.items()}
        return self._hvac_mode_lookup

    def _get_swing_mode(self, hor_mode=False):
        """Return the current swing mode for vert of hor mode."""
        if hor_mode:
            mode = self._api.state.horizontal_step_mode
        else:
            mode = self._api.state.vertical_step_mode
        if mode:
            return f"{SWING_PREFIX[1 if hor_mode else 0]}{mode}"
        return None

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
        if self._device.temperature_unit == UNIT_TEMP_FAHRENHEIT:
            return TEMP_FAHRENHEIT
        return TEMP_CELSIUS

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation ie. heat, cool mode."""
        op_mode = self._api.state.operation_mode
        if not self._api.state.is_on or op_mode is None:
            return HVAC_MODE_OFF
        modes = self._available_hvac_modes()
        return modes.get(op_mode, HVAC_MODE_AUTO)

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            self._device.power(False)
            return

        modes = self._available_hvac_modes()
        reverse_lookup = {v: k for k, v in modes.items()}
        operation_mode = reverse_lookup.get(hvac_mode)
        if operation_mode is None:
            raise ValueError(f"Invalid hvac_mode [{hvac_mode}]")

        if self.hvac_mode == HVAC_MODE_OFF:
            self._device.power(True)
        self._device.set_op_mode(operation_mode)

    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes."""
        modes = self._available_hvac_modes()
        return [HVAC_MODE_OFF] + list(modes.values())

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        curr_temp = None
        if self._device.is_air_to_water:
            curr_temp = self._api.state.device_features.get(FEAT_OUT_WATER_TEMP)
        if curr_temp is None:
            curr_temp = self._api.state.current_temp
        return curr_temp

    @property
    def current_humidity(self) -> int | None:
        return self._api.state.device_features.get(FEAT_HUMIDITY)

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._api.state.target_temp

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        self._device.set_target_temp(
            kwargs.get("temperature", self.target_temperature)
        )

    @property
    def fan_mode(self) -> str:
        """Return the fan setting."""
        return self._api.state.fan_speed

    def set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        self._device.set_fan_speed(fan_mode)

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return self._device.fan_speeds

    @property
    def swing_mode(self) -> str:
        """Return the swing mode setting."""
        if self._set_hor_swing and self._support_hor_swing:
            return self._get_swing_mode(True)
        return self._get_swing_mode(False)

    def set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing mode."""
        avl_mode = False
        curr_mode = None
        set_hor_swing = swing_mode.startswith(SWING_PREFIX[1])
        dev_mode = remove_prefix(
            swing_mode, SWING_PREFIX[1 if set_hor_swing else 0]
        )
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
                self._device.set_horizontal_step_mode(dev_mode)
            else:
                self._device.set_vertical_step_mode(dev_mode)
        self._set_hor_swing = set_hor_swing

    @property
    def swing_modes(self):
        """Return the list of available swing modes."""
        list_modes = list()
        for mode in self._device.vertical_step_modes:
            list_modes.append(f"{SWING_PREFIX[0]}{mode}")
        for mode in self._device.horizontal_step_modes:
            list_modes.append(f"{SWING_PREFIX[1]}{mode}")
        return list_modes

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        features = SUPPORT_TARGET_TEMPERATURE
        if len(self._device.fan_speeds) > 0:
            features |= SUPPORT_FAN_MODE
        if self._support_ver_swing or self._support_hor_swing:
            features |= SUPPORT_SWING_MODE
        return features

    def turn_on(self) -> None:
        """Turn the entity on."""
        self._device.power(True)

    def turn_off(self) -> None:
        """Turn the entity off."""
        self._device.power(False)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        min_value = self._device.target_temperature_min
        if min_value is not None:
            return min_value

        return self._device.conv_temp_unit(DEFAULT_MIN_TEMP)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        max_value = self._device.target_temperature_max
        if max_value is not None:
            return max_value

        return self._device.conv_temp_unit(DEFAULT_MAX_TEMP)


class LGERefrigeratorClimate(LGEClimate):
    """Refrigerator climate device."""

    entity_description = ThinQRefClimateEntityDescription

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQRefClimateEntityDescription,
    ) -> None:
        """Initialize the climate."""
        super().__init__(api)
        self._wrap_device = LGERefrigeratorDevice(api)
        self.entity_description = description
        self._attr_name = get_entity_name(api, description.key, description.name)
        self._attr_unique_id = f"{api.unique_id}-{description.key}-AC"
        self._attr_hvac_modes = [HVAC_MODE_AUTO]
        self._attr_hvac_mode = HVAC_MODE_AUTO

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return self._wrap_device.device.target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._api.state:
            unit = self._api.state.temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, TEMP_CELSIUS)
        return TEMP_CELSIUS

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        curr_temp = self.entity_description.temp_fn(self._wrap_device)
        if curr_temp is None:
            return None
        try:
            return int(curr_temp)
        except ValueError:
            return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self.current_temperature

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        new_temp = kwargs.get("temperature", self.target_temperature)
        self.entity_description.set_temp_fn(self._wrap_device, new_temp)

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        if not self._wrap_device.device.set_values_allowed:
            return 0
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self.entity_description.range_temp_fn(self._wrap_device)[0]

    @property
    def max_temp(self) -> float:
        return self.entity_description.range_temp_fn(self._wrap_device)[1]
