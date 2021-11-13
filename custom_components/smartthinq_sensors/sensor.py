# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Tuple

from .wideq import (
    FEAT_DRYLEVEL,
    FEAT_ENERGY_CURRENT,
    FEAT_ERROR_MSG,
    FEAT_HALFLOAD,
    FEAT_HOT_WATER_TEMP,
    FEAT_HUMIDITY,
    FEAT_IN_WATER_TEMP,
    FEAT_LOWER_FILTER_LIFE,
    FEAT_OUT_WATER_TEMP,
    FEAT_PRE_STATE,
    FEAT_PROCESS_STATE,
    FEAT_RUN_STATE,
    FEAT_SPINSPEED,
    FEAT_TUBCLEAN_COUNT,
    FEAT_TEMPCONTROL,
    FEAT_UPPER_FILTER_LIFE,
    FEAT_WATERTEMP,
    FEAT_COOKTOP_LEFT_FRONT_STATE,
    FEAT_COOKTOP_LEFT_REAR_STATE,
    FEAT_COOKTOP_CENTER_STATE,
    FEAT_COOKTOP_RIGHT_FRONT_STATE,
    FEAT_COOKTOP_RIGHT_REAR_STATE,
    FEAT_OVEN_LOWER_CURRENT_TEMP,
    FEAT_OVEN_LOWER_STATE,
    FEAT_OVEN_UPPER_CURRENT_TEMP,
    FEAT_OVEN_UPPER_STATE,
)
from .wideq.device import WM_DEVICE_TYPES, DeviceType

from homeassistant.components.sensor import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_PM1,
    DEVICE_CLASS_PM10,
    DEVICE_CLASS_PM25,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_TEMPERATURE,
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    POWER_WATT,
    STATE_UNAVAILABLE,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DEFAULT_ICON, DEFAULT_SENSOR, DOMAIN, LGE_DEVICES
from .device_helpers import (
    DEVICE_ICONS,
    WASH_DEVICE_TYPES,
    LGEACDevice,
    LGEAirPurifierDevice,
    LGERangeDevice,
    LGERefrigeratorDevice,
    LGEWashDevice,
    get_entity_name,
)

# service definition
SERVICE_REMOTE_START = "remote_start"
SERVICE_WAKE_UP = "wake_up"

# general sensor attributes
ATTR_CURRENT_COURSE = "current_course"
ATTR_ERROR_STATE = "error_state"
ATTR_INITIAL_TIME = "initial_time"
ATTR_REMAIN_TIME = "remain_time"
ATTR_RESERVE_TIME = "reserve_time"
ATTR_RUN_COMPLETED = "run_completed"

# refrigerator sensor attributes
ATTR_DOOR_OPEN = "door_open"
ATTR_FRIDGE_TEMP = "fridge_temp"
ATTR_FREEZER_TEMP = "freezer_temp"
ATTR_TEMP_UNIT = "temp_unit"

# ac sensor attributes
ATTR_ROOM_TEMP = "room_temperature"

# range sensor attributes
ATTR_OVEN_LOWER_TARGET_TEMP = "oven_lower_target_temp"
ATTR_OVEN_UPPER_TARGET_TEMP = "oven_upper_target_temp"
ATTR_OVEN_TEMP_UNIT = "oven_temp_unit"

# air purifier sensor attributes
ATTR_PM1 = "pm1"
ATTR_PM10 = "pm10"
ATTR_PM25 = "pm25"

# supported features
SUPPORT_REMOTE_START = 1
SUPPORT_WAKE_UP = 2

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQSensorEntityDescription(SensorEntityDescription):
    """A class that describes ThinQ sensor entities."""

    unit_fn: Callable[[Any], str] | None = None
    value_fn: Callable[[Any], float | str] | None = None


WASH_DEV_SENSORS: Tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_CURRENT_COURSE,
        name="Current course",
        icon="mdi:pin-outline",
        value_fn=lambda x: x.current_course,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_RUN_STATE,
        name="Run state",
        icon=DEFAULT_ICON,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_PROCESS_STATE,
        name="Process state",
        icon=DEFAULT_ICON,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_SPINSPEED,
        name="Spin speed",
        icon="mdi:rotate-3d",
    ),
    ThinQSensorEntityDescription(
        key=FEAT_WATERTEMP,
        name="Water temp",
        icon="mdi:thermometer-lines",
    ),
    ThinQSensorEntityDescription(
        key=FEAT_TEMPCONTROL,
        name="Temp control",
        icon="mdi:thermometer-lines",
    ),
    ThinQSensorEntityDescription(
        key=FEAT_DRYLEVEL,
        name="Dry level",
        icon="mdi:tumble-dryer",
    ),
    ThinQSensorEntityDescription(
        key=FEAT_ERROR_MSG,
        name="Error message",
        icon="mdi:alert-circle-outline",
    ),
    ThinQSensorEntityDescription(
        key=FEAT_PRE_STATE,
        name="Pre state",
        icon=DEFAULT_ICON,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_TUBCLEAN_COUNT,
        name="Tub clean counter",
        icon=DEFAULT_ICON,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_HALFLOAD,
        name="Half load",
        icon="mdi:circle-half-full",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_INITIAL_TIME,
        name="Initial time",
        icon="mdi:clock-outline",
        value_fn=lambda x: x.initial_time,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_REMAIN_TIME,
        name="Remaining time",
        icon="mdi:clock-outline",
        value_fn=lambda x: x.remain_time,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_RESERVE_TIME,
        name="Countdown time",
        icon="mdi:clock-outline",
        value_fn=lambda x: x.reserve_time,
        entity_registry_enabled_default=False,
    ),
)
REFRIGERATOR_SENSORS: Tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_FRIDGE_TEMP,
        name="Fridge temp",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        value_fn=lambda x: x.temp_fridge,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_FREEZER_TEMP,
        name="Freezer temp",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        value_fn=lambda x: x.temp_freezer,
    ),
)
AC_SENSORS: Tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=ATTR_ROOM_TEMP,
        name="Room temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        value_fn=lambda x: x.curr_temp,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_HOT_WATER_TEMP,
        name="Hot water temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_IN_WATER_TEMP,
        name="In water temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_OUT_WATER_TEMP,
        name="Out water temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_ENERGY_CURRENT,
        name="Energy current",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_POWER,
        native_unit_of_measurement=POWER_WATT,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_HUMIDITY,
        name="Humidity",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
)
RANGE_SENSORS: Tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_COOKTOP_LEFT_FRONT_STATE,
        name="Cooktop left front state",
        icon="mdi:arrow-left-bold-box-outline",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_COOKTOP_LEFT_REAR_STATE,
        name="Cooktop left rear state",
        icon="mdi:arrow-left-bold-box",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_COOKTOP_CENTER_STATE,
        name="Cooktop center state",
        icon="mdi:minus-box-outline",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_COOKTOP_RIGHT_FRONT_STATE,
        name="Cooktop right front state",
        icon="mdi:arrow-right-bold-box-outline",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_COOKTOP_RIGHT_REAR_STATE,
        name="Cooktop right rear state",
        icon="mdi:arrow-right-bold-box",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_OVEN_LOWER_STATE,
        name="Oven lower state",
        icon="mdi:inbox-arrow-down",
    ),
    ThinQSensorEntityDescription(
        key=FEAT_OVEN_UPPER_STATE,
        name="Oven upper state",
        icon="mdi:inbox-arrow-up",
    ),
    ThinQSensorEntityDescription(
        key=ATTR_OVEN_LOWER_TARGET_TEMP,
        name="Oven lower target temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
        value_fn=lambda x: x.oven_lower_target_temp,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_OVEN_LOWER_CURRENT_TEMP,
        name="Oven lower current temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_OVEN_UPPER_TARGET_TEMP,
        name="Oven upper target temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
        value_fn=lambda x: x.oven_upper_target_temp,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_OVEN_UPPER_CURRENT_TEMP,
        name="Oven upper current temperature",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
    ),
)
AIR_PURIFIER_SENSORS: Tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=ATTR_PM1,
        name="PM1",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_PM1,
        value_fn=lambda x: x.pm1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_PM25,
        name="PM2.5",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_PM25,
        value_fn=lambda x: x.pm25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_PM10,
        name="PM10",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_PM10,
        value_fn=lambda x: x.pm10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_LOWER_FILTER_LIFE,
        name="Filter Remaining Life (Bottom)",
        icon="mdi:air-filter",
        state_class=STATE_CLASS_MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    ThinQSensorEntityDescription(
        key=FEAT_UPPER_FILTER_LIFE,
        name="Filter Remaining Life (Top)",
        icon="mdi:air-filter",
        state_class=STATE_CLASS_MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
)


def _sensor_exist(lge_device: LGEDevice, sensor_desc: ThinQSensorEntityDescription):
    """Check if a sensor exist for device."""
    if sensor_desc.value_fn is not None:
        return True

    feature = sensor_desc.key
    for feat_name in lge_device.available_features.keys():
        if feat_name == feature:
            return True

    return False


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the LGE sensors."""
    _LOGGER.info("Starting LGE ThinQ sensors...")

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
            LGEWashDeviceSensor(lge_device, sensor_desc)
            for sensor_desc in WASH_DEV_SENSORS
            for lge_device in wash_devices
            if _sensor_exist(lge_device, sensor_desc)
        ]
    )

    # add refrigerators
    lge_sensors.extend(
        [
            LGERefrigeratorSensor(lge_device, sensor_desc)
            for sensor_desc in REFRIGERATOR_SENSORS
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
            if _sensor_exist(lge_device, sensor_desc)
        ]
    )

    # add AC
    lge_sensors.extend(
        [
            LGESensor(lge_device, sensor_desc, LGEACDevice(lge_device))
            for sensor_desc in AC_SENSORS
            for lge_device in lge_devices.get(DeviceType.AC, [])
            if _sensor_exist(lge_device, sensor_desc)
        ]
    )

    # add ranges
    lge_sensors.extend(
        [
            LGERangeSensor(lge_device, sensor_desc)
            for sensor_desc in RANGE_SENSORS
            for lge_device in lge_devices.get(DeviceType.RANGE, [])
            if _sensor_exist(lge_device, sensor_desc)
        ]
    )

    # add air purifiers
    lge_sensors.extend(
        [
            LGESensor(lge_device, sensor_desc, LGEAirPurifierDevice(lge_device))
            for sensor_desc in AIR_PURIFIER_SENSORS
            for lge_device in lge_devices.get(DeviceType.AIR_PURIFIER, [])
            if _sensor_exist(lge_device, sensor_desc)
        ]
    )

    async_add_entities(lge_sensors)

    # register services
    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_REMOTE_START,
        {},
        "async_remote_start",
        [SUPPORT_REMOTE_START],
    )
    platform.async_register_entity_service(
        SERVICE_WAKE_UP,
        {},
        "async_wake_up",
        [SUPPORT_WAKE_UP],
    )


class LGESensor(CoordinatorEntity, SensorEntity):
    """Class to monitor sensors for LGE device"""

    entity_description = ThinQSensorEntityDescription

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQSensorEntityDescription,
            wrapped_device,
    ):
        """Initialize the sensor."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = wrapped_device
        self.entity_description = description
        self._attr_name = get_entity_name(api, description.key, description.name)
        self._attr_unique_id = api.unique_id
        if description.key != DEFAULT_SENSOR:
            self._attr_unique_id += f"-{description.key}"
        self._attr_device_info = api.device_info
        self._is_default = description.key == DEFAULT_SENSOR

    @property
    def supported_features(self):
        if self._is_default and self._api.type in WM_DEVICE_TYPES:
            return SUPPORT_REMOTE_START | SUPPORT_WAKE_UP
        return None

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.available:
            return STATE_UNAVAILABLE
        return self._get_sensor_state()

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self._wrap_device)
        return super().native_unit_of_measurement

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
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

    def _get_sensor_state(self):
        """Get current sensor state"""
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return self._api.state.device_features.get(feature)

        return None

    async def async_remote_start(self):
        """Call the remote start command for WM devices."""
        if self._api.type not in WM_DEVICE_TYPES:
            raise NotImplementedError()
        await self.hass.async_add_executor_job(self._api.device.remote_start)

    async def async_wake_up(self):
        """Call the wakeup command for WM devices."""
        if self._api.type not in WM_DEVICE_TYPES:
            raise NotImplementedError()
        await self.hass.async_add_executor_job(self._api.device.wake_up)


class LGEWashDeviceSensor(LGESensor):
    """A sensor to monitor LGE Wash devices"""

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQSensorEntityDescription,
    ):
        """Initialize the sensor."""
        super().__init__(api, description, LGEWashDevice(api))

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_RUN_COMPLETED: self._wrap_device.run_completed,
            ATTR_ERROR_STATE: self._wrap_device.error_state,
            ATTR_INITIAL_TIME: self._wrap_device.initial_time,
            ATTR_REMAIN_TIME: self._wrap_device.remain_time,
            ATTR_RESERVE_TIME: self._wrap_device.reserve_time,
            ATTR_CURRENT_COURSE: self._wrap_device.current_course,
        }
        features = self._wrap_device.get_features_attributes()
        data.update(features)

        return data


class LGERefrigeratorSensor(LGESensor):
    """A sensor to monitor LGE Refrigerator devices"""

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQSensorEntityDescription,
    ):
        """Initialize the sensor."""
        super().__init__(api, description, LGERefrigeratorDevice(api))

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_FRIDGE_TEMP: self._wrap_device.temp_fridge,
            ATTR_FREEZER_TEMP: self._wrap_device.temp_freezer,
            ATTR_TEMP_UNIT: self._wrap_device.temp_unit,
            ATTR_DOOR_OPEN: self._wrap_device.dooropen_state,
        }

        if self._api.state:
            features = self._wrap_device.get_features_attributes()
            data.update(features)

        return data


class LGERangeSensor(LGESensor):
    """A sensor to monitor LGE range devices"""

    def __init__(
            self,
            api: LGEDevice,
            description: ThinQSensorEntityDescription,
    ):
        """Initialize the sensor."""
        super().__init__(api, description, LGERangeDevice(api))

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_OVEN_LOWER_TARGET_TEMP: self._wrap_device.oven_lower_target_temp,
            ATTR_OVEN_UPPER_TARGET_TEMP: self._wrap_device.oven_upper_target_temp,
            ATTR_OVEN_TEMP_UNIT: self._wrap_device.oven_temp_unit,
        }
        features = self._wrap_device.get_features_attributes()
        data.update(features)

        return data
