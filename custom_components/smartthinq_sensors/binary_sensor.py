"""Support for ThinQ device bynary sensors."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Tuple

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DEFAULT_ICON, DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import (
    DEVICE_ICONS,
    STATE_LOOKUP,
    WASH_DEVICE_TYPES,
    LGEBaseDevice,
    LGERangeDevice,
    LGERefrigeratorDevice,
    LGEWashDevice,
    get_entity_name,
    get_multiple_devices_types,
)
from .sensor import ATTR_DOOR_OPEN, ATTR_ERROR_STATE, ATTR_RUN_COMPLETED
from .wideq import DehumidifierFeatures, DeviceType, WashDeviceFeatures

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
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda x: x.error_state,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.STANDBY,
        name="Standby",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.CHILDLOCK,
        name="Child lock",
        icon="mdi:account-off-outline",
        icon_on="mdi:account-lock",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.DOORCLOSE,
        name="Door close",
        icon="mdi:alpha-o-box-outline",
        icon_on="mdi:alpha-c-box",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.DOORLOCK,
        name="Door lock",
        icon="mdi:lock-open-variant-outline",
        icon_on="mdi:lock",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.DOOROPEN,
        name="Door open",
        device_class=BinarySensorDeviceClass.OPENING,
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.AUTODOOR,
        name="Auto door",
        icon="mdi:auto-upload",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.REMOTESTART,
        name="Remote start",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.DUALZONE,
        name="Dual zone",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.RINSEREFILL,
        name="Rinse refill",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.SALTREFILL,
        name="Salt refill",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.HIGHTEMP,
        name="High temp",
        device_class=BinarySensorDeviceClass.HEAT,
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.EXTRADRY,
        name="Extra dry",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.NIGHTDRY,
        name="Night dry",
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.DETERGENT,
        name="Detergent",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
    ThinQBinarySensorEntityDescription(
        key=WashDeviceFeatures.SOFTENER,
        name="Softener",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
)
REFRIGERATOR_BINARY_SENSORS: Tuple[ThinQBinarySensorEntityDescription, ...] = (
    ThinQBinarySensorEntityDescription(
        key=ATTR_DOOR_OPEN,
        name="Door open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda x: x.dooropen_state,
    ),
)
RANGE_BINARY_SENSORS: Tuple[ThinQBinarySensorEntityDescription, ...] = (
    ThinQBinarySensorEntityDescription(
        key=ATTR_COOKTOP_STATE,
        name="Cooktop state",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda x: x.cooktop_state,
    ),
    ThinQBinarySensorEntityDescription(
        key=ATTR_OVEN_STATE,
        name="Oven state",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda x: x.oven_state,
        entity_registry_enabled_default=False,
    ),
)
DEHUMIDIFIER_BINARY_SENSORS: Tuple[ThinQBinarySensorEntityDescription, ...] = (
    ThinQBinarySensorEntityDescription(
        key=DehumidifierFeatures.WATER_TANK_FULL,
        name="Water Tank Full",
    ),
)


def _binary_sensor_exist(
    lge_device: LGEDevice, sensor_desc: ThinQBinarySensorEntityDescription
) -> bool:
    """Check if a sensor exist for device."""
    if sensor_desc.value_fn is not None:
        return True

    feature = sensor_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE binary sensors."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ binary sensors setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_sensors = []

        # add WASH devices
        lge_sensors.extend(
            [
                LGEBinarySensor(lge_device, sensor_desc, LGEWashDevice(lge_device))
                for sensor_desc in WASH_DEV_BINARY_SENSORS
                for lge_device in get_multiple_devices_types(
                    lge_devices, WASH_DEVICE_TYPES
                )
                if _binary_sensor_exist(lge_device, sensor_desc)
            ]
        )

        # add refrigerators
        lge_sensors.extend(
            [
                LGEBinarySensor(
                    lge_device, sensor_desc, LGERefrigeratorDevice(lge_device)
                )
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

        # add dehumidifier
        lge_sensors.extend(
            [
                LGEBinarySensor(lge_device, sensor_desc)
                for sensor_desc in DEHUMIDIFIER_BINARY_SENSORS
                for lge_device in lge_devices.get(DeviceType.DEHUMIDIFIER, [])
                if _binary_sensor_exist(lge_device, sensor_desc)
            ]
        )

        async_add_entities(lge_sensors)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


def get_binary_sensor_name(device, ent_key, ent_name) -> str:
    """Get the name for the binary sensor"""
    name = get_entity_name(device, ent_key, ent_name)
    if ent_key == ATTR_RUN_COMPLETED:
        name = name.replace("<Run>", RUN_COMPLETED_PREFIX.get(device.type, "Run"))

    return name


class LGEBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Class to monitor binary sensors for LGE device"""

    entity_description: ThinQBinarySensorEntityDescription
    _wrap_device: LGEBaseDevice | None

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQBinarySensorEntityDescription,
        wrapped_device: LGEBaseDevice | None = None,
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
        ret_val = ret_val.lower()
        if ret_val == STATE_ON:
            return True
        state = STATE_LOOKUP.get(ret_val, STATE_OFF)
        return state == STATE_ON

    def _get_sensor_state(self):
        if self._wrap_device and self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return self._api.state.device_features.get(feature)

        return None
