# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

import logging
from datetime import timedelta

from .wideq.device import (
    STATE_OPTIONITEM_OFF,
    STATE_OPTIONITEM_ON,
    DeviceType,
)

from homeassistant.components.switch import (
    DOMAIN as SENSOR_DOMAIN,
    SwitchEntity,
)

from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LGE_DEVICES
from . import LGEDevice

# switch definition
ATTR_MEASUREMENT_NAME = "measurement_name"
ATTR_ICON = "icon"
ATTR_DEVICE_CLASS = "device_class"
ATTR_VALUE_FEAT = "value_feat"
ATTR_VALUE_FN = "value_fn"
ATTR_TURN_OFF_FN = "turn_off_fn"
ATTR_TURN_ON_FN = "turn_on_fn"
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

DEVICE_ICONS = {
    DeviceType.WASHER: "mdi:washing-machine",
    DeviceType.DRYER: "mdi:tumble-dryer",
    DeviceType.STYLER: "mdi:palette-swatch-outline",
    DeviceType.DISHWASHER: "mdi:dishwasher",
    DeviceType.REFRIGERATOR: "mdi:fridge-outline",
    DeviceType.RANGE: "mdi:stove",
}

WASH_DEV_SWITCH = {
    ATTR_POWER_OFF: {
        ATTR_MEASUREMENT_NAME: "Power Off",
        # ATTR_ICON: DEFAULT_ICON,
        # ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._power_on,
        ATTR_TURN_OFF_FN: lambda x: x._api.device.power_off(),
        ATTR_ENABLED: True,
    },
}

WASH_DEVICE_TYPES = [
    # DeviceType.DISHWASHER,
    DeviceType.DRYER,
    DeviceType.STYLER,
    DeviceType.TOWER_DRYER,
    DeviceType.TOWER_WASHER,
    DeviceType.WASHER,
]


def _feature_exist(lge_device, switch_def):
    """Check if a switch exist for device."""
    if ATTR_VALUE_FN in switch_def:
        return True

    if ATTR_VALUE_FEAT in switch_def:
        feature = switch_def[ATTR_VALUE_FEAT]
        if feature in lge_device.available_features:
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
        if dev_type in WASH_DEVICE_TYPES:
            wash_devices.extend(devices)

    lge_switch.extend(
        [
            LGESwitch(lge_device, measurement, definition)
            for measurement, definition in WASH_DEV_SWITCH.items()
            for lge_device in wash_devices
            if _feature_exist(lge_device, definition)
        ]
    )

    async_add_entities(lge_switch)


class LGESwitch(CoordinatorEntity, SwitchEntity):
    def __init__(
            self,
            device: LGEDevice,
            measurement,
            definition,
    ):
        """Initialize the switch."""
        super().__init__(device.coordinator)
        self._api = device
        self._name_slug = device.name
        self._measurement = measurement
        self._def = definition

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
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._def.get(ATTR_ENABLED, False)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        name = self._def[ATTR_MEASUREMENT_NAME]
        return f"{self._name_slug} {name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._api.unique_id}-{self._measurement}-switch"

    @property
    def device_class(self):
        """Return device class."""
        return self._def.get(ATTR_DEVICE_CLASS)

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
        return self._api.available and self._power_on

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._api.assumed_state

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        return self._api.state_attributes

    @property
    def device_info(self):
        """Return the device info."""
        return self._api.device_info

    def turn_off(self):
        """Turn the entity off."""
        if ATTR_TURN_OFF_FN not in self._def:
            raise NotImplementedError()
        if self.is_on:
            self._def[ATTR_TURN_OFF_FN](self)

    def turn_on(self):
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

    def _get_features_value(self):
        ret_val = {}
        if self._api.state:
            states = self._api.state.device_features
        else:
            states = {}
        features = self._api.available_features
        for feature in features.values():
            ret_val[feature] = states.get(feature)
        return ret_val
