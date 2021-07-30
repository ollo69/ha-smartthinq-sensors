# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

import logging
from datetime import timedelta

from .wideq.device import (
    STATE_OPTIONITEM_OFF,
    STATE_OPTIONITEM_ON,
    WM_DEVICE_TYPES,
    DeviceType,
)
from .wideq import (
    FEAT_ECOFRIENDLY,
    FEAT_EXPRESSFRIDGE,
    FEAT_EXPRESSMODE,
    FEAT_ICEPLUS,
)

from homeassistant.components.switch import (
    DEVICE_CLASS_SWITCH,
    SwitchEntity,
)

from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LGE_DEVICES
from .sensor import DEVICE_ICONS
from . import LGEDevice

# switch definition
ATTR_SWITCH_NAME = "switch_name"
ATTR_ICON = "icon"
ATTR_VALUE_FEAT = "value_feat"
ATTR_VALUE_FN = "value_fn"
ATTR_TURN_OFF_FN = "turn_off_fn"
ATTR_TURN_ON_FN = "turn_on_fn"
ATTR_AVAILABLE_FN = "available_fn"
ATTR_ENABLED = "enabled"

# general sensor attributes
ATTR_POWER_OFF = "power_off"

STATE_LOOKUP = {
    STATE_OPTIONITEM_OFF: STATE_OFF,
    STATE_OPTIONITEM_ON: STATE_ON,
}

DEFAULT_ICON = "def_icon"

SCAN_INTERVAL = timedelta(seconds=120)

_LOGGER = logging.getLogger(__name__)

WASH_DEV_SWITCH = {
    ATTR_POWER_OFF: {
        ATTR_SWITCH_NAME: "Power off",
        # ATTR_ICON: DEFAULT_ICON,
        ATTR_VALUE_FN: lambda x: x._power_on,
        ATTR_TURN_OFF_FN: lambda x: x._api.device.power_off(),
        ATTR_ENABLED: True,
    },
}

REFR_DEV_SWITCH = {
    FEAT_ECOFRIENDLY: {
        ATTR_SWITCH_NAME: "Eco friendly",
        ATTR_ICON: "mdi:gauge-empty",
        ATTR_VALUE_FEAT: FEAT_ECOFRIENDLY,
        ATTR_TURN_OFF_FN: lambda x: x._api.device.set_eco_friendly(False),
        ATTR_TURN_ON_FN: lambda x: x._api.device.set_eco_friendly(True),
        ATTR_ENABLED: True,
    },
    FEAT_EXPRESSFRIDGE: {
        ATTR_SWITCH_NAME: "Express fridge",
        ATTR_ICON: "mdi:coolant-temperature",
        ATTR_VALUE_FEAT: FEAT_EXPRESSFRIDGE,
        ATTR_TURN_OFF_FN: lambda x: x._api.device.set_express_fridge(False),
        ATTR_TURN_ON_FN: lambda x: x._api.device.set_express_fridge(True),
        ATTR_AVAILABLE_FN: lambda x: x._api.device.set_values_allowed,
        ATTR_ENABLED: True,
    },
    FEAT_EXPRESSMODE: {
        ATTR_SWITCH_NAME: "Express mode",
        ATTR_ICON: "mdi:snowflake",
        ATTR_VALUE_FEAT: FEAT_EXPRESSMODE,
        ATTR_TURN_OFF_FN: lambda x: x._api.device.set_express_mode(False),
        ATTR_TURN_ON_FN: lambda x: x._api.device.set_express_mode(True),
        ATTR_AVAILABLE_FN: lambda x: x._api.device.set_values_allowed,
        ATTR_ENABLED: True,
    },
    FEAT_ICEPLUS: {
        ATTR_SWITCH_NAME: "Ice plus",
        ATTR_ICON: "mdi:snowflake",
        ATTR_VALUE_FEAT: FEAT_ICEPLUS,
        ATTR_TURN_OFF_FN: lambda x: x._api.device.set_ice_plus(False),
        ATTR_TURN_ON_FN: lambda x: x._api.device.set_ice_plus(True),
        ATTR_AVAILABLE_FN: lambda x: x._api.device.set_values_allowed,
        ATTR_ENABLED: True,
    },
}


def _feature_exist(lge_device, switch_def):
    """Check if a switch exist for device."""
    if ATTR_VALUE_FN in switch_def:
        return True

    if ATTR_VALUE_FEAT in switch_def:
        feature = switch_def[ATTR_VALUE_FEAT]
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
            LGESwitch(lge_device, def_id, definition)
            for def_id, definition in WASH_DEV_SWITCH.items()
            for lge_device in wash_devices
            if _feature_exist(lge_device, definition)
        ]
    )

    # add refrigerators
    lge_switch.extend(
        [
            LGESwitch(lge_device, def_id, definition)
            for def_id, definition in REFR_DEV_SWITCH.items()
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
            if _feature_exist(lge_device, definition)
        ]
    )

    async_add_entities(lge_switch)


class LGESwitch(CoordinatorEntity, SwitchEntity):
    def __init__(
            self,
            device: LGEDevice,
            def_id,
            definition,
    ):
        """Initialize the switch."""
        super().__init__(device.coordinator)
        self._api = device
        self._name_slug = device.name
        self._def_id = def_id
        self._def = definition
        self._name = None

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
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._def.get(ATTR_ENABLED, False)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        if not self._name:
            name = None
            if ATTR_VALUE_FEAT in self._def:
                feat_key = self._def[ATTR_VALUE_FEAT]
                feat_name = self._api.available_features.get(feat_key)
                if feat_name and feat_name != feat_key:
                    name = feat_name.replace("_", " ").capitalize()
            if not name:
                name = self._def[ATTR_SWITCH_NAME]
            self._name = f"{self._name_slug} {name}"
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._api.unique_id}-{self._def_id}-switch"

    @property
    def device_class(self):
        """Return device class."""
        return DEVICE_CLASS_SWITCH

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        icon = self._def.get(ATTR_ICON)
        if not icon:
            return None
        if icon == DEFAULT_ICON:
            icon = DEVICE_ICONS.get(self._api.type)
        return icon

    @property
    def is_on(self):
        """Return the state of the switch."""
        ret_val = self._get_sensor_state()
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
        if ATTR_AVAILABLE_FN in self._def:
            is_avail = self._def[ATTR_AVAILABLE_FN](self)
        return self._api.available and self._power_on and is_avail

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        return self._api.state_attributes

    @property
    def device_info(self):
        """Return the device info."""
        return self._api.device_info

    def turn_off(self, **kwargs):
        """Turn the entity off."""
        if ATTR_TURN_OFF_FN not in self._def:
            raise NotImplementedError()
        if self.is_on:
            self._def[ATTR_TURN_OFF_FN](self)

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        if ATTR_TURN_ON_FN not in self._def:
            raise NotImplementedError()
        if not self.is_on:
            self._def[ATTR_TURN_ON_FN](self)

    @property
    def _power_on(self):
        """Current power state"""
        if self._api.state:
            return self._api.state.is_on
        return False

    def _get_sensor_state(self):
        if ATTR_VALUE_FN in self._def:
            return self._def[ATTR_VALUE_FN](self)

        if ATTR_VALUE_FEAT in self._def:
            if self._api.state:
                feature = self._def[ATTR_VALUE_FEAT]
                return self._api.state.device_features.get(feature)

        return None
