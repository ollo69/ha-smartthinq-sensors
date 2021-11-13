# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable, Tuple

from .wideq.device import WM_DEVICE_TYPES, DeviceType
from .wideq import (
    FEAT_ECOFRIENDLY,
    FEAT_EXPRESSFRIDGE,
    FEAT_EXPRESSMODE,
    FEAT_ICEPLUS,
)

from homeassistant.components.switch import (
    DEVICE_CLASS_SWITCH,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES
from .device_helpers import STATE_LOOKUP, LGEBaseDevice, get_entity_name

# general sensor attributes
ATTR_POWER_OFF = "power_off"

SCAN_INTERVAL = timedelta(seconds=120)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQSwitchEntityDescription(SwitchEntityDescription):
    """A class that describes ThinQ switch entities."""

    available_fn: Callable[[Any], bool] | None = None
    turn_off_fn: Callable[[Any], None] | None = None
    turn_on_fn: Callable[[Any], None] | None = None
    value_fn: Callable[[Any], bool] | None = None


WASH_DEV_SWITCH: Tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=ATTR_POWER_OFF,
        name="Power off",
        value_fn=lambda x: x.is_power_on,
        turn_off_fn=lambda x: x.device.power_off(),
        available_fn=lambda x: x.is_power_on,
    ),
)
REFRIGERATOR_SWITCH: Tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=FEAT_ECOFRIENDLY,
        name="Eco friendly",
        icon="mdi:gauge-empty",
        turn_off_fn=lambda x: x.device.set_eco_friendly(False),
        turn_on_fn=lambda x: x.device.set_eco_friendly(True),
        available_fn=lambda x: x.is_power_on,
    ),
    ThinQSwitchEntityDescription(
        key=FEAT_EXPRESSFRIDGE,
        name="Express fridge",
        icon="mdi:coolant-temperature",
        turn_off_fn=lambda x: x.device.set_express_fridge(False),
        turn_on_fn=lambda x: x.device.set_express_fridge(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
    ThinQSwitchEntityDescription(
        key=FEAT_EXPRESSMODE,
        name="Express mode",
        icon="mdi:snowflake",
        turn_off_fn=lambda x: x.device.set_express_mode(False),
        turn_on_fn=lambda x: x.device.set_express_mode(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
    ThinQSwitchEntityDescription(
        key=FEAT_ICEPLUS,
        name="Ice plus",
        icon="mdi:snowflake",
        turn_off_fn=lambda x: x.device.set_ice_plus(False),
        turn_on_fn=lambda x: x.device.set_ice_plus(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
)
AIR_PURIFIER_SWITCH: Tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key="power",
        name="Power",
        value_fn=lambda x: x.is_power_on,
        turn_on_fn=lambda x: x.device.power(True),
        turn_off_fn=lambda x: x.device.power(False),
    ),
)

AC_DUCT_SWITCH = ThinQSwitchEntityDescription(
    key="duct-zone",
    name="Zone",
)


def _switch_exist(lge_device: LGEDevice, switch_desc: ThinQSwitchEntityDescription):
    """Check if a switch exist for device."""
    if switch_desc.value_fn is not None:
        return True

    feature = switch_desc.key
    for feat_name in lge_device.available_features.keys():
        if feat_name == feature:
            return True

    return False


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the LGE switch."""
    _LOGGER.info("Starting LGE ThinQ switch...")

    lge_switch = []
    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES)
    if not lge_devices:
        return

    # add wash devices
    wash_devices = []
    for dev_type, devices in lge_devices.items():
        if dev_type in WM_DEVICE_TYPES:
            wash_devices.extend(devices)

    lge_switch.extend(
        [
            LGESwitch(lge_device, switch_desc)
            for switch_desc in WASH_DEV_SWITCH
            for lge_device in wash_devices
            if _switch_exist(lge_device, switch_desc)
        ]
    )

    # add refrigerators
    lge_switch.extend(
        [
            LGESwitch(lge_device, switch_desc)
            for switch_desc in REFRIGERATOR_SWITCH
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
            if _switch_exist(lge_device, switch_desc)
        ]
    )

    # add air purifiers
    lge_switch.extend(
        [
            LGESwitch(lge_device, switch_desc)
            for switch_desc in AIR_PURIFIER_SWITCH
            for lge_device in lge_devices.get(DeviceType.AIR_PURIFIER, [])
            if _switch_exist(lge_device, switch_desc)
        ]
    )

    # add AC duct zone switch
    lge_switch.extend(
        [
            LGEDuctSwitch(lge_device, duct_zone)
            for lge_device in lge_devices.get(DeviceType.AC, [])
            for duct_zone in lge_device.device.duct_zones
        ]
    )

    async_add_entities(lge_switch)


class LGESwitch(CoordinatorEntity, SwitchEntity):
    """Class to control switches for LGE device"""

    entity_description = ThinQSwitchEntityDescription

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQSwitchEntityDescription,
    ):
        """Initialize the switch."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = LGEBaseDevice(api)
        self.entity_description = description
        self._attr_name = get_entity_name(api, description.key, description.name)
        self._attr_unique_id = f"{api.unique_id}-{description.key}-switch"
        self._attr_device_class = DEVICE_CLASS_SWITCH
        self._attr_device_info = api.device_info

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        We overwrite coordinator property default setting because we need
        to poll to avoid the effect that after changing switch state
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

    def turn_off(self, **kwargs):
        """Turn the entity off."""
        if self.entity_description.turn_off_fn is None:
            raise NotImplementedError()
        if self.is_on:
            self.entity_description.turn_off_fn(self._wrap_device)

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        if self.entity_description.turn_on_fn is None:
            raise NotImplementedError()
        if not self.is_on:
            self.entity_description.turn_on_fn(self._wrap_device)

    def _get_switch_state(self):
        """Get current switch state"""
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return self._api.state.device_features.get(feature)

        return None


class LGEDuctSwitch(LGESwitch):
    """Class to control switches for LGE AC duct device"""

    def __init__(
            self,
            api: LGEDevice,
            duct_zone: str
    ):
        """Initialize the switch."""
        super().__init__(api, AC_DUCT_SWITCH)
        self._attr_name += f" {duct_zone}"
        self._attr_unique_id += f"-{duct_zone}"
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

    def turn_off(self, **kwargs):
        """Turn the entity off."""
        self._wrap_device.device.set_duct_zone(self._zone, False)

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        self._wrap_device.device.set_duct_zone(self._zone, True)
