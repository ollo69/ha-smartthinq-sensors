"""Platform for LGE climate integration."""
import logging
from datetime import timedelta

from .wideq import FEAT_OUT_WATER_TEMP
from .wideq.ac import AirConditionerDevice, ACMode
from .wideq.device import UNIT_TEMP_FAHRENHEIT, DeviceType
from .wideq.refrigerator import RefrigeratorDevice

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_OFF,
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
from .sensor import TEMP_UNIT_LOOKUP

# ac attr definition
ATTR_AC_ENTITY_NAME = "ac_entity_name"
ATTR_ICON = "icon"
ATTR_CURR_TEMP_FN = "curr_temp_fn"
ATTR_RANGE_TEMP_FN = "range_temp_fn"
ATTR_TARGET_TEMP_FN = "target_temp_fn"
ATTR_ENABLED = "enabled"

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

HA_STATE_TO_CURRENT_HVAC = {
    HVAC_MODE_COOL: CURRENT_HVAC_COOL,
    HVAC_MODE_HEAT: CURRENT_HVAC_HEAT,
    HVAC_MODE_OFF: CURRENT_HVAC_OFF,
}

ATTR_SWING_HORIZONTAL = "swing_mode_horizontal"
ATTR_SWING_VERTICAL = "swing_mode_vertical"
SWING_PREFIX = ["Vertical", "Horizontal"]

REFR_AC_ENTITY = {
    ATTR_FRIDGE: {
        ATTR_AC_ENTITY_NAME: "Fridge",
        ATTR_ICON: "mdi:fridge-top",
        ATTR_CURR_TEMP_FN: lambda x: x._fridge_temperature,
        ATTR_RANGE_TEMP_FN: lambda x: x._api.device.fridge_target_temp_range,
        ATTR_TARGET_TEMP_FN: lambda x, y: x._api.device.set_fridge_target_temp(y),
        ATTR_ENABLED: True,
    },
    ATTR_FREEZER: {
        ATTR_AC_ENTITY_NAME: "Freezer",
        ATTR_ICON: "mdi:fridge-bottom",
        ATTR_CURR_TEMP_FN: lambda x: x._freezer_temperature,
        ATTR_RANGE_TEMP_FN: lambda x: x._api.device.freezer_target_temp_range,
        ATTR_TARGET_TEMP_FN: lambda x, y: x._api.device.set_freezer_target_temp(y),
        ATTR_ENABLED: True,
    },
}

SCAN_INTERVAL = timedelta(seconds=120)

_LOGGER = logging.getLogger(__name__)


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
    lge_climates.extend(
        [
            LGEACClimate(lge_device, lge_device.device)
            for lge_device in lge_devices.get(DeviceType.AC, [])
        ]
    )

    lge_climates.extend(
        [
            LGERefrigeratorClimate(lge_device, lge_device.device, ent_id, definition)
            for ent_id, definition in REFR_AC_ENTITY.items()
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
        ]
    )

    async_add_entities(lge_climates)


class LGEClimate(CoordinatorEntity, ClimateEntity):
    """Base climate device."""

    def __init__(self, device: LGEDevice):
        """Initialize the climate."""
        super().__init__(device.coordinator)
        self._api = device
        self._name = device.name

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._api.device_info

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

    def __init__(self, device: LGEDevice, ac_device: AirConditionerDevice) -> None:
        """Initialize the climate."""
        super().__init__(device)
        self._device = ac_device
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
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._api.unique_id}-AC"

    @property
    def name(self):
        """Return the display name of this entity."""
        return self._name

    @property
    def device_state_attributes(self):
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
            mode = HVAC_MODE_OFF
        else:
            modes = self._available_hvac_modes()
            mode = modes.get(op_mode)
        self._attr_hvac_action = HA_STATE_TO_CURRENT_HVAC.get(mode or "NA")
        return mode

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

    def __init__(self, device: LGEDevice, ac_device: RefrigeratorDevice, ent_id, definition) -> None:
        """Initialize the climate."""
        super().__init__(device)
        self._device = ac_device
        self._ent_id = ent_id
        self._def = definition

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._def.get(ATTR_ENABLED, False)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._api.unique_id}-{self._ent_id}-AC"

    @property
    def name(self):
        """Return the display name of this entity."""
        name = self._def[ATTR_AC_ENTITY_NAME]
        return f"{self._name} {name}"

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._def.get(ATTR_ICON)

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation ie. heat, cool mode."""
        return HVAC_MODE_AUTO

    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_AUTO]

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return self._device.target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        if self._api.state:
            unit = self._api.state.temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, TEMP_CELSIUS)
        return TEMP_CELSIUS

    @property
    def _fridge_temperature(self):
        if self._api.state:
            try:
                return int(self._api.state.temp_fridge)
            except ValueError:
                return None
        return None

    @property
    def _freezer_temperature(self):
        if self._api.state:
            try:
                return int(self._api.state.temp_freezer)
            except ValueError:
                return None
        return None

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self.target_temperature

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._def[ATTR_CURR_TEMP_FN](self)

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        new_temp = kwargs.get("temperature", self.target_temperature)
        self._def[ATTR_TARGET_TEMP_FN](self, new_temp)

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        if not self._device.set_values_allowed:
            return 0
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._def[ATTR_RANGE_TEMP_FN](self)[0]

    @property
    def max_temp(self) -> float:
        return self._def[ATTR_RANGE_TEMP_FN](self)[1]
