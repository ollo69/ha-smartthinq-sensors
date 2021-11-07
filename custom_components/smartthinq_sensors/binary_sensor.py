"""Support for ThinQ device bynary sensors."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Tuple

from .wideq import (
    FEAT_CHILDLOCK,
    FEAT_DOORCLOSE,
    FEAT_DOORLOCK,
    FEAT_DOOROPEN,
    FEAT_DUALZONE,
    FEAT_STANDBY,
    FEAT_REMOTESTART,
    FEAT_RINSEREFILL,
    FEAT_SALTREFILL,
)
from .wideq.device import DeviceType

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_HEAT,
    DEVICE_CLASS_OPENING,
    DEVICE_CLASS_PROBLEM,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DEFAULT_ICON, DOMAIN, LGE_DEVICES
from .device_helpers import (
    DEVICE_ICONS,
    STATE_LOOKUP,
    WASH_DEVICE_TYPES,
    LGERangeDevice,
    LGERefrigeratorDevice,
    LGEWashDevice,
    get_entity_name,
)
from .sensor import (
    ATTR_DOOR_OPEN,
    ATTR_ERROR_STATE,
    ATTR_RUN_COMPLETED,
)

# range sensor attributes
ATTR_COOKTOP_STATE = "cooktop_state"
ATTR_OVEN_STATE = "oven_state"

_LOGGER = logging.getLogger(__name__)

RUN_COMPLETED_PREFIX = {
    DeviceType.WASHER: "Wash",
    DeviceType.DRYER: "Dry",
    DeviceType.STYLER: "Style",
    DeviceType.DISHWASHER: "Wash",
}


@dataclass
class ThinQBinarySensorEntityDescription(BinarySensorEntityDescription):
    """A class that describes ThinQ binary sensor entities."""

    icon_on: str | None = None
    value_fn: Callable[[Any], bool | str] | None = None


WASH_DEV_BINARY_SENSORS: Tuple[ThinQBinarySensorEntityDescription, ...] = (
    ThinQBinarySensorEntityDescription(
        key=ATTR_RUN_COMPLETED,
        name="<Run> completed",
        value_fn=lambda x: x.run_completed,
    ),
    ThinQBinarySensorEntityDescription(
        key=ATTR_ERROR_STATE,
        name="Error state",
        device_class=DEVICE_CLASS_PROBLEM,
        value_fn=lambda x: x.error_state,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_STANDBY,
        name="Standby",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_CHILDLOCK,
        name="Child lock",
        icon="mdi:account-off-outline",
        icon_on="mdi:account-lock",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_DOORCLOSE,
        name="Door close",
        icon="mdi:alpha-o-box-outline",
        icon_on="mdi:alpha-c-box",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_DOORLOCK,
        name="Door lock",
        icon="mdi:lock-open-variant-outline",
        icon_on="mdi:lock",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_DOOROPEN,
        name="Door open",
        device_class=DEVICE_CLASS_OPENING,
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_REMOTESTART,
        name="Remote start",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_DUALZONE,
        name="Dual zone",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_RINSEREFILL,
        name="Rinse refill",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=FEAT_SALTREFILL,
        name="Salt refill",
        entity_registry_enabled_default=False,
    ),
)
REFRIGERATOR_BINARY_SENSORS: Tuple[ThinQBinarySensorEntityDescription, ...] = (
    ThinQBinarySensorEntityDescription(
        key=ATTR_DOOR_OPEN,
        name="Door open",
        device_class=DEVICE_CLASS_OPENING,
        value_fn=lambda x: x.dooropen_state,
    ),
)
RANGE_BINARY_SENSORS: Tuple[ThinQBinarySensorEntityDescription, ...] = (
    ThinQBinarySensorEntityDescription(
        key=ATTR_COOKTOP_STATE,
        name="Cooktop state",
        device_class=DEVICE_CLASS_HEAT,
        value_fn=lambda x: x.cooktop_state,
    ),
    ThinQBinarySensorEntityDescription(
        key=ATTR_OVEN_STATE,
        name="Oven state",
        device_class=DEVICE_CLASS_HEAT,
        value_fn=lambda x: x.oven_state,
    ),
)


def _binary_sensor_exist(lge_device: LGEDevice, sensor_desc: ThinQBinarySensorEntityDescription):
    """Check if a sensor exist for device."""
    if sensor_desc.value_fn is not None:
        return True

    feature = sensor_desc.key
    for feat_name in lge_device.available_features.keys():
        if feat_name == feature:
            return True

    return False


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the LGE binary sensors."""
    _LOGGER.info("Starting LGE ThinQ binary sensors...")

    lge_sensors = []
    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES)
    if not lge_devices:
        return

    # add wash devices
    wash_devices = []
    for dev_type, devices in lge_devices.items():
        if dev_type in WASH_DEVICE_TYPES:
            wash_devices.extend(devices)

    lge_sensors.extend(
        [
            LGEBinarySensor(lge_device, sensor_desc, LGEWashDevice(lge_device))
            for sensor_desc in WASH_DEV_BINARY_SENSORS
            for lge_device in wash_devices
            if _binary_sensor_exist(lge_device, sensor_desc)
        ]
    )

    # add refrigerators
    lge_sensors.extend(
        [
            LGEBinarySensor(lge_device, sensor_desc, LGERefrigeratorDevice(lge_device))
            for sensor_desc in REFRIGERATOR_BINARY_SENSORS
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
            if _binary_sensor_exist(lge_device, sensor_desc)
        ]
    )

    # add ranges
    lge_sensors.extend(
        [
            LGEBinarySensor(lge_device, sensor_desc, LGERangeDevice(lge_device))
            for sensor_desc in RANGE_BINARY_SENSORS
            for lge_device in lge_devices.get(DeviceType.RANGE, [])
            if _binary_sensor_exist(lge_device, sensor_desc)
        ]
    )

    async_add_entities(lge_sensors)


def get_binary_sensor_name(device, ent_key, ent_name) -> str:
    """Get the name for the binary sensor"""
    name = get_entity_name(device, ent_key, ent_name)
    if ent_key == ATTR_RUN_COMPLETED:
        name = name.replace(
            "<Run>", RUN_COMPLETED_PREFIX.get(device.type, "Run")
        )

    return name


class LGEBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Class to monitor binary sensors for LGE device"""

    entity_description = ThinQBinarySensorEntityDescription

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQBinarySensorEntityDescription,
            wrapped_device,
    ):
        """Initialize the binary sensor."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = wrapped_device
        self.entity_description = description
        self._attr_name = get_binary_sensor_name(api, description.key, description.name)
        self._attr_unique_id = f"{api.unique_id}-{description.key}"
        self._attr_device_info = api.device_info

        self._is_on = None

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        self._is_on = self._get_on_state()
        return self._is_on

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        if self.entity_description.icon_on and self._is_on:
            return self.entity_description.icon_on
        ent_icon = self.entity_description.icon
        if ent_icon and ent_icon == DEFAULT_ICON:
            return DEVICE_ICONS.get(self._api.type)
        return super().icon

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._api.assumed_state

    def _get_on_state(self):
        """Return true if the binary sensor is on."""
        ret_val = self._get_sensor_state()
        if ret_val is None:
            return False
        if isinstance(ret_val, bool):
            return ret_val
        if ret_val == STATE_ON:
            return True
        state = STATE_LOOKUP.get(ret_val, STATE_OFF)
        return state == STATE_ON

    def _get_sensor_state(self):
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return self._api.state.device_features.get(feature)

        return None
