"""Support for ThinQ device switches."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import STATE_LOOKUP, LGEBaseDevice
from .wideq import (
    WM_DEVICE_TYPES,
    AirConditionerFeatures,
    DeviceType,
    MicroWaveFeatures,
    RefrigeratorFeatures,
)

# general sensor attributes
ATTR_POWER = "power"

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQSwitchEntityDescription(SwitchEntityDescription):
    """A class that describes ThinQ switch entities."""

    available_fn: Callable[[Any], bool] | None = None
    turn_off_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_on_fn: Callable[[Any], Awaitable[None]] | None = None
    value_fn: Callable[[Any], bool] | None = None


WASH_DEV_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=ATTR_POWER,
        name="Power",
        value_fn=lambda x: x.is_power_on and not x.device.stand_by,
        turn_off_fn=lambda x: x.device.power_off(),
        turn_on_fn=lambda x: x.device.wake_up(),
        available_fn=lambda x: x.is_power_on or x.device.stand_by,
    ),
)
REFRIGERATOR_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.ECOFRIENDLY,
        name="Eco friendly",
        icon="mdi:gauge-empty",
        turn_off_fn=lambda x: x.device.set_eco_friendly(False),
        turn_on_fn=lambda x: x.device.set_eco_friendly(True),
        available_fn=lambda x: x.is_power_on,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.EXPRESSFRIDGE,
        name="Express fridge",
        icon="mdi:coolant-temperature",
        turn_off_fn=lambda x: x.device.set_express_fridge(False),
        turn_on_fn=lambda x: x.device.set_express_fridge(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.EXPRESSMODE,
        name="Express mode",
        icon="mdi:snowflake",
        turn_off_fn=lambda x: x.device.set_express_mode(False),
        turn_on_fn=lambda x: x.device.set_express_mode(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.ICEPLUS,
        name="Ice plus",
        icon="mdi:snowflake",
        turn_off_fn=lambda x: x.device.set_ice_plus(False),
        turn_on_fn=lambda x: x.device.set_ice_plus(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
)
AC_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.MODE_AIRCLEAN,
        name="Ionizer",
        icon="mdi:pine-tree",
        turn_off_fn=lambda x: x.device.set_mode_airclean(False),
        turn_on_fn=lambda x: x.device.set_mode_airclean(True),
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.MODE_JET,
        name="Jet mode",
        icon="mdi:turbine",
        turn_off_fn=lambda x: x.device.set_mode_jet(False),
        turn_on_fn=lambda x: x.device.set_mode_jet(True),
        available_fn=lambda x: x.device.is_mode_jet_available,
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.LIGHTING_DISPLAY,
        name="Display light",
        icon="mdi:wall-sconce-round",
        turn_off_fn=lambda x: x.device.set_lighting_display(False),
        turn_on_fn=lambda x: x.device.set_lighting_display(True),
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.MODE_AWHP_SILENT,
        name="Silent mode",
        icon="mdi:ear-hearing-off",
        turn_off_fn=lambda x: x.device.set_mode_awhp_silent(False),
        turn_on_fn=lambda x: x.device.set_mode_awhp_silent(True),
        available_fn=lambda x: x.is_power_on,
    ),
)
MICROWAVE_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=MicroWaveFeatures.SOUND,
        name="Sound",
        icon="mdi:volume-high",
        entity_category=EntityCategory.CONFIG,
        turn_off_fn=lambda x: x.device.set_sound(False),
        turn_on_fn=lambda x: x.device.set_sound(True),
    ),
    ThinQSwitchEntityDescription(
        key=MicroWaveFeatures.CLOCK_DISPLAY,
        name="Clock Display",
        icon="mdi:clock-digital",
        entity_category=EntityCategory.CONFIG,
        turn_off_fn=lambda x: x.device.set_clock_display(False),
        turn_on_fn=lambda x: x.device.set_clock_display(True),
    ),
)


SWITCH_ENTITIES = {
    DeviceType.AC: AC_SWITCH,
    DeviceType.MICROWAVE: MICROWAVE_SWITCH,
    DeviceType.REFRIGERATOR: REFRIGERATOR_SWITCH,
    **{dev_type: WASH_DEV_SWITCH for dev_type in WM_DEVICE_TYPES},
}


def _switch_exist(
    lge_device: LGEDevice, switch_desc: ThinQSwitchEntityDescription
) -> bool:
    """Check if a switch exist for device."""
    if switch_desc.value_fn is not None:
        return True

    feature = switch_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE switch."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ switch setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_switch = [
            LGESwitch(lge_device, switch_desc)
            for dev_type, switch_descs in SWITCH_ENTITIES.items()
            for switch_desc in switch_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _switch_exist(lge_device, switch_desc)
        ]

        # add AC duct zone switch
        lge_switch.extend(
            [
                LGEDuctSwitch(lge_device, duct_zone)
                for lge_device in lge_devices.get(DeviceType.AC, [])
                for duct_zone in lge_device.device.duct_zones
            ]
        )

        async_add_entities(lge_switch)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGEBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base switch device."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, api: LGEDevice):
        """Initialize the base switch."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info
        self._wrap_device = LGEBaseDevice(api)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGESwitch(LGEBaseSwitch):
    """Class to control switches for LGE device"""

    entity_description: ThinQSwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQSwitchEntityDescription,
    ):
        """Initialize the switch."""
        super().__init__(api)
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-switch"

    @property
    def is_on(self):
        """Return the state of the switch."""
        ret_val = self._get_switch_state()
        if ret_val is None:
            return False
        if isinstance(ret_val, bool):
            return ret_val
        if ret_val == STATE_ON:
            return True
        state = STATE_LOOKUP.get(ret_val, STATE_OFF)
        return state == STATE_ON

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._wrap_device)
        return self._api.available and is_avail

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        if self.entity_description.turn_off_fn is None:
            raise NotImplementedError()
        if self.is_on:
            await self.entity_description.turn_off_fn(self._wrap_device)
            self._api.async_set_updated()

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        if self.entity_description.turn_on_fn is None:
            raise NotImplementedError()
        if not self.is_on:
            await self.entity_description.turn_on_fn(self._wrap_device)
            self._api.async_set_updated()

    def _get_switch_state(self):
        """Get current switch state"""
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return self._api.state.device_features.get(feature)

        return None


class LGEDuctSwitch(LGEBaseSwitch):
    """Class to control switches for LGE AC duct device"""

    _attr_has_entity_name = True

    def __init__(self, api: LGEDevice, duct_zone: str):
        """Initialize the switch."""
        super().__init__(api)
        self._attr_unique_id = f"{api.unique_id}-duct-zone-switch-{duct_zone}"
        self._attr_name = f"Zone {duct_zone}"
        self._zone = duct_zone

    @property
    def is_on(self):
        """Return the state of the switch."""
        return self._wrap_device.device.get_duct_zone(self._zone)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self._wrap_device.device.is_duct_zone_enabled(self._zone)
            and self._wrap_device.is_power_on
        )

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        self._wrap_device.device.set_duct_zone(self._zone, False)
        self._api.async_set_updated()

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        self._wrap_device.device.set_duct_zone(self._zone, True)
        self._api.async_set_updated()
