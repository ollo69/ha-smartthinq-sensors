"""Support for ThinQ device sensors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import logging
from typing import Any, Callable

import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import (
    ATTR_CURRENT_COURSE,
    ATTR_FREEZER_TEMP,
    ATTR_FRIDGE_TEMP,
    ATTR_INITIAL_TIME,
    ATTR_OVEN_LOWER_TARGET_TEMP,
    ATTR_OVEN_UPPER_TARGET_TEMP,
    ATTR_REMAIN_TIME,
    ATTR_RESERVE_TIME,
    DEFAULT_ICON,
    DEFAULT_SENSOR,
    DOMAIN,
    LGE_DEVICES,
    LGE_DISCOVERY_NEW,
)
from .device_helpers import (
    DEVICE_ICONS,
    WASH_DEVICE_TYPES,
    LGEBaseDevice,
    get_entity_name,
    get_wrapper_device,
)
from .wideq import (
    SET_TIME_DEVICE_TYPES,
    WM_DEVICE_TYPES,
    AirConditionerFeatures,
    AirPurifierFeatures,
    DehumidifierFeatures,
    DeviceType,
    MicroWaveFeatures,
    RangeFeatures,
    WashDeviceFeatures,
    WaterHeaterFeatures,
)

# service definition
SERVICE_REMOTE_START = "remote_start"
SERVICE_WAKE_UP = "wake_up"
SERVICE_SET_TIME = "set_time"

# supported features
# this is used to limit the device's entities
# used to call the specific service
SUPPORT_WM_SERVICES = 1
SUPPORT_SET_TIME = 2

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQSensorEntityDescription(SensorEntityDescription):
    """A class that describes ThinQ sensor entities."""

    unit_fn: Callable[[Any], str] | None = None
    value_fn: Callable[[Any], float | str] | None = None
    feature_attributes: dict[str, str] | None = None


WASH_DEV_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
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
        key=WashDeviceFeatures.RUN_STATE,
        name="Run state",
        icon=DEFAULT_ICON,
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.PROCESS_STATE,
        name="Process state",
        icon=DEFAULT_ICON,
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.SPINSPEED,
        name="Spin speed",
        icon="mdi:rotate-3d",
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.WATERTEMP,
        name="Water temp",
        icon="mdi:thermometer-lines",
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.RINSEMODE,
        name="Rinse mode",
        icon="mdi:waves",
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.TEMPCONTROL,
        name="Temp control",
        icon="mdi:thermometer-lines",
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.DRYLEVEL,
        name="Dry level",
        icon="mdi:tumble-dryer",
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.ERROR_MSG,
        name="Error message",
        icon="mdi:alert-circle-outline",
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.PRE_STATE,
        name="Pre state",
        icon=DEFAULT_ICON,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.TUBCLEAN_COUNT,
        name="Tub clean counter",
        icon=DEFAULT_ICON,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=WashDeviceFeatures.HALFLOAD,
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
REFRIGERATOR_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_FRIDGE_TEMP,
        name="Fridge temp",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        value_fn=lambda x: x.temp_fridge,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_FREEZER_TEMP,
        name="Freezer temp",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        value_fn=lambda x: x.temp_freezer,
    ),
)
AC_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.ROOM_TEMP,
        name="Room temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.HOT_WATER_TEMP,
        name="Hot water temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.WATER_IN_TEMP,
        name="In water temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.WATER_OUT_TEMP,
        name="Out water temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.ENERGY_CURRENT,
        name="Energy current",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.HUMIDITY,
        name="Humidity",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.PM1,
        name="PM1",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PM1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.PM10,
        name="PM10",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.PM25,
        name="PM2.5",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.FILTER_MAIN_LIFE,
        name="Filter Remaining Life",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        feature_attributes={
            "use_time": AirConditionerFeatures.FILTER_MAIN_USE,
            "max_time": AirConditionerFeatures.FILTER_MAIN_MAX,
        },
    ),
    ThinQSensorEntityDescription(
        key=AirConditionerFeatures.RESERVATION_SLEEP_TIME,
        name="Sleep time",
        icon="mdi:weather-night",
        state_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
)
RANGE_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.COOKTOP_LEFT_FRONT_STATE,
        name="Cooktop left front state",
        icon="mdi:arrow-left-bold-box-outline",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.COOKTOP_LEFT_REAR_STATE,
        name="Cooktop left rear state",
        icon="mdi:arrow-left-bold-box",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.COOKTOP_CENTER_STATE,
        name="Cooktop center state",
        icon="mdi:minus-box-outline",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.COOKTOP_RIGHT_FRONT_STATE,
        name="Cooktop right front state",
        icon="mdi:arrow-right-bold-box-outline",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.COOKTOP_RIGHT_REAR_STATE,
        name="Cooktop right rear state",
        icon="mdi:arrow-right-bold-box",
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.OVEN_LOWER_STATE,
        name="Oven lower state",
        icon="mdi:inbox-arrow-down",
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.OVEN_LOWER_MODE,
        name="Oven lower mode",
        icon="mdi:inbox-arrow-down",
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.OVEN_UPPER_STATE,
        name="Oven upper state",
        icon="mdi:inbox-arrow-up",
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.OVEN_UPPER_MODE,
        name="Oven upper mode",
        icon="mdi:inbox-arrow-up",
    ),
    ThinQSensorEntityDescription(
        key=ATTR_OVEN_LOWER_TARGET_TEMP,
        name="Oven lower target temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
        value_fn=lambda x: x.oven_lower_target_temp,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.OVEN_LOWER_CURRENT_TEMP,
        name="Oven lower current temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
    ),
    ThinQSensorEntityDescription(
        key=ATTR_OVEN_UPPER_TARGET_TEMP,
        name="Oven upper target temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
        value_fn=lambda x: x.oven_upper_target_temp,
    ),
    ThinQSensorEntityDescription(
        key=RangeFeatures.OVEN_UPPER_CURRENT_TEMP,
        name="Oven upper current temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.oven_temp_unit,
    ),
)
AIR_PURIFIER_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.HUMIDITY,
        name="Current Humidity",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.PM1,
        name="PM1",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PM1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.PM10,
        name="PM10",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.PM25,
        name="PM2.5",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.FILTER_MAIN_LIFE,
        name="Filter Remaining Life (Main)",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        feature_attributes={
            "use_time": AirPurifierFeatures.FILTER_MAIN_USE,
            "max_time": AirPurifierFeatures.FILTER_MAIN_MAX,
        },
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.FILTER_BOTTOM_LIFE,
        name="Filter Remaining Life (Bottom)",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        feature_attributes={
            "use_time": AirPurifierFeatures.FILTER_BOTTOM_USE,
            "max_time": AirPurifierFeatures.FILTER_BOTTOM_MAX,
        },
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.FILTER_DUST_LIFE,
        name="Filter Remaining Life (Dust)",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        feature_attributes={
            "use_time": AirPurifierFeatures.FILTER_DUST_USE,
            "max_time": AirPurifierFeatures.FILTER_DUST_MAX,
        },
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.FILTER_MID_LIFE,
        name="Filter Remaining Life (Middle)",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        feature_attributes={
            "use_time": AirPurifierFeatures.FILTER_MID_USE,
            "max_time": AirPurifierFeatures.FILTER_MID_MAX,
        },
    ),
    ThinQSensorEntityDescription(
        key=AirPurifierFeatures.FILTER_TOP_LIFE,
        name="Filter Remaining Life (Top)",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        feature_attributes={
            "use_time": AirPurifierFeatures.FILTER_TOP_USE,
            "max_time": AirPurifierFeatures.FILTER_TOP_MAX,
        },
    ),
)
DEHUMIDIFIER_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DehumidifierFeatures.HUMIDITY,
        name="Current Humidity",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
    ),
    ThinQSensorEntityDescription(
        key=DehumidifierFeatures.TARGET_HUMIDITY,
        name="Target Humidity",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
)
WATER_HEATER_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=WaterHeaterFeatures.HOT_WATER_TEMP,
        name="Hot water temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit_fn=lambda x: x.temp_unit,
        entity_registry_enabled_default=False,
    ),
    ThinQSensorEntityDescription(
        key=WaterHeaterFeatures.ENERGY_CURRENT,
        name="Energy current",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
)
HOOD_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
)
MICROWAVE_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key=DEFAULT_SENSOR,
        icon=DEFAULT_ICON,
        value_fn=lambda x: x.power_state,
    ),
    ThinQSensorEntityDescription(
        key=MicroWaveFeatures.OVEN_UPPER_STATE,
        name="Oven state",
        icon=DEFAULT_ICON,
    ),
    ThinQSensorEntityDescription(
        key=MicroWaveFeatures.OVEN_UPPER_MODE,
        name="Oven mode",
        icon="mdi:inbox-full",
    ),
)

SENSOR_ENTITIES = {
    DeviceType.AC: AC_SENSORS,
    DeviceType.AIR_PURIFIER: AIR_PURIFIER_SENSORS,
    DeviceType.DEHUMIDIFIER: DEHUMIDIFIER_SENSORS,
    DeviceType.HOOD: HOOD_SENSORS,
    DeviceType.MICROWAVE: MICROWAVE_SENSORS,
    DeviceType.RANGE: RANGE_SENSORS,
    DeviceType.REFRIGERATOR: REFRIGERATOR_SENSORS,
    DeviceType.WATER_HEATER: WATER_HEATER_SENSORS,
    **{dev_type: WASH_DEV_SENSORS for dev_type in WASH_DEVICE_TYPES},
}


def _sensor_exist(
    lge_device: LGEDevice, sensor_desc: ThinQSensorEntityDescription
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
    """Set up the LGE sensors."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ sensors setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_sensors = [
            LGESensor(lge_device, sensor_desc, get_wrapper_device(lge_device, dev_type))
            for dev_type, sensor_descs in SENSOR_ENTITIES.items()
            for sensor_desc in sensor_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _sensor_exist(lge_device, sensor_desc)
        ]

        async_add_entities(lge_sensors)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )

    # register services
    platform = current_platform.get()
    platform.async_register_entity_service(
        SERVICE_REMOTE_START,
        {vol.Optional("course"): str},
        "async_remote_start",
        [SUPPORT_WM_SERVICES],
    )
    platform.async_register_entity_service(
        SERVICE_WAKE_UP,
        {},
        "async_wake_up",
        [SUPPORT_WM_SERVICES],
    )
    platform.async_register_entity_service(
        SERVICE_SET_TIME,
        {vol.Optional("time_wanted"): cv.time},
        "async_set_time",
        [SUPPORT_SET_TIME],
    )


class LGESensor(CoordinatorEntity, SensorEntity):
    """Class to monitor sensors for LGE device"""

    entity_description: ThinQSensorEntityDescription
    _attr_has_entity_name = True
    _wrap_device: LGEBaseDevice | None

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQSensorEntityDescription,
        wrapped_device: LGEBaseDevice | None = None,
    ):
        """Initialize the sensor."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = wrapped_device
        self.entity_description = description
        self._attr_unique_id = api.unique_id
        if description.key != DEFAULT_SENSOR:
            self._attr_unique_id += f"-{description.key}"
        self._attr_device_info = api.device_info
        if not description.translation_key and description.name is UNDEFINED:
            self._attr_name = get_entity_name(api, description.key)
        self._is_default = description.key == DEFAULT_SENSOR

    @property
    def supported_features(self) -> int:
        features = 0
        if self._is_default:
            if self._api.type in WM_DEVICE_TYPES:
                features |= SUPPORT_WM_SERVICES
            if self._api.type in SET_TIME_DEVICE_TYPES:
                features |= SUPPORT_SET_TIME
        return features

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if not self.available:
            return STATE_UNAVAILABLE
        return self._get_sensor_state()

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        if self._wrap_device and self.entity_description.unit_fn is not None:
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

    @property
    def extra_state_attributes(self):
        """Return the optional state attributes."""
        if self._is_default and self._wrap_device:
            return self._wrap_device.extra_state_attributes

        features = self.entity_description.feature_attributes
        if not (features and self._api.state):
            return None
        data = {}
        for key, feat in features.items():
            if (val := self._api.state.device_features.get(feat)) is not None:
                data[key] = val
        return data

    def _get_sensor_state(self):
        """Get current sensor state"""
        if self._wrap_device and self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return self._api.state.device_features.get(feature)

        return None

    async def async_remote_start(self, course: str | None = None):
        """Call the remote start command for WM devices."""
        if self._api.type not in WM_DEVICE_TYPES:
            raise NotImplementedError()
        await self._api.device.remote_start(course)

    async def async_wake_up(self):
        """Call the wakeup command for WM devices."""
        if self._api.type not in WM_DEVICE_TYPES:
            raise NotImplementedError()
        await self._api.device.wake_up()

    async def async_set_time(self, time_wanted: time | None = None):
        """Call the set time command for Microwave devices."""
        if self._api.type not in SET_TIME_DEVICE_TYPES:
            raise NotImplementedError()
        await self._api.device.set_time(time_wanted)
