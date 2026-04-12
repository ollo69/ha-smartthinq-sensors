"""Support for ThinQ device sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
from typing import Any, cast

from thinqconnect import ThinQAPIException
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
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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
    LGE_DISCOVERY_NEW,
    LGE_OFFICIAL_DISCOVERY,
)
from .device_helpers import (
    DEVICE_ICONS,
    WASH_DEVICE_TYPES,
    LGEBaseDevice,
    get_entity_name,
    get_wrapper_device,
)
from .lge_device import LGEDevice
from .official_mapping import find_official_coordinator
from .runtime_data import get_lge_devices
from .wideq import (
    SET_TIME_DEVICE_TYPES,
    WM_DEVICE_TYPES,
    AirConditionerFeatures,
    AirPurifierFeatures,
    DehumidifierFeatures,
    DeviceType,
    MicroWaveFeatures,
    RangeFeatures,
    RefrigeratorFeatures,
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


@dataclass(frozen=True, kw_only=True)
class ThinQEnergySensorEntityDescription(SensorEntityDescription):
    """Describe an official energy usage sensor."""

    device_class: SensorDeviceClass = SensorDeviceClass.ENERGY
    state_class: SensorStateClass = SensorStateClass.TOTAL
    native_unit_of_measurement: str = UnitOfEnergy.WATT_HOUR
    suggested_display_precision: int = 0
    usage_period: str = "day"
    start_date_fn: Callable[[datetime], datetime]
    end_date_fn: Callable[[datetime], datetime]
    update_interval: timedelta = timedelta(days=1)


ENERGY_USAGE_SENSORS: tuple[ThinQEnergySensorEntityDescription, ...] = (
    ThinQEnergySensorEntityDescription(
        key="energy_usage_yesterday",
        name="Energy usage yesterday",
        usage_period="day",
        start_date_fn=lambda now: now - timedelta(days=1),
        end_date_fn=lambda now: now - timedelta(days=1),
    ),
    ThinQEnergySensorEntityDescription(
        key="energy_usage_this_month",
        name="Energy usage this month",
        usage_period="month",
        start_date_fn=lambda now: now,
        end_date_fn=lambda now: now,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ThinQEnergySensorEntityDescription(
        key="energy_usage_last_month",
        name="Energy usage last month",
        usage_period="month",
        start_date_fn=lambda now: now.replace(day=1) - timedelta(days=1),
        end_date_fn=lambda now: now.replace(day=1) - timedelta(days=1),
    ),
)


@dataclass(frozen=True)
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
    ThinQSensorEntityDescription(
        key=RefrigeratorFeatures.FRESHAIRFILTER_REMAIN_PERC,
        name="Fresh air filter remaining",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    ThinQSensorEntityDescription(
        key=RefrigeratorFeatures.WATERFILTER_REMAIN_PERC,
        name="Water filter remaining",
        icon="mdi:waves",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
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
        device_class=SensorDeviceClass.DURATION,
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
    **dict.fromkeys(WASH_DEVICE_TYPES, WASH_DEV_SENSORS),
}

COMMON_SENSORS: tuple[ThinQSensorEntityDescription, ...] = (
    ThinQSensorEntityDescription(
        key="ssid",
        name="SSID",
        icon="mdi:access-point-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: x.ssid,
    ),
)


def _sensor_exist(
    lge_device: LGEDevice, sensor_desc: ThinQSensorEntityDescription
) -> bool:
    """Check if a sensor exist for device."""
    if (
        lge_device.type == DeviceType.AC
        and sensor_desc.key == AirConditionerFeatures.RESERVATION_SLEEP_TIME
        and not lge_device.device.is_reservation_sleep_time_supported
    ):
        return False

    wrapped_device = get_wrapper_device(lge_device, lge_device.type)
    if (
        lge_device.type == DeviceType.REFRIGERATOR
        and wrapped_device is not None
        and hasattr(wrapped_device, "supports_fridge_compartment")
        and hasattr(wrapped_device, "supports_freezer_compartment")
    ):
        if (
            sensor_desc.key == ATTR_FRIDGE_TEMP
            and not wrapped_device.supports_fridge_compartment
        ):
            return False
        if (
            sensor_desc.key == ATTR_FREEZER_TEMP
            and not wrapped_device.supports_freezer_compartment
        ):
            return False

    if sensor_desc.value_fn is not None:
        return True

    feature = sensor_desc.key
    if feature in lge_device.available_features:
        return True

    return False


def _format_energy_property_name(energy_property: str) -> str:
    """Return a user-facing energy property label."""
    words: list[str] = []
    current_word = ""
    for char in energy_property.replace("_", " "):
        if char == " ":
            if current_word:
                words.append(current_word)
                current_word = ""
            continue
        if char.isupper() and current_word:
            words.append(current_word)
            current_word = char
        else:
            current_word += char
    if current_word:
        words.append(current_word)
    return " ".join(word.capitalize() for word in words) or energy_property


def _build_official_energy_sensors(lge_device: LGEDevice) -> list[LGEOfficialEnergySensor]:
    """Create official energy usage sensors for one device when supported."""
    official_coordinator = find_official_coordinator(lge_device.hass, lge_device.device_id)
    if official_coordinator is None:
        return []

    official_device = getattr(getattr(official_coordinator, "api", None), "device", None)
    energy_properties = getattr(official_device, "energy_properties", None)
    if not isinstance(energy_properties, list) or not energy_properties:
        return []

    multi_property = len(energy_properties) > 1
    entities: list[LGEOfficialEnergySensor] = []
    for energy_property in energy_properties:
        property_label = _format_energy_property_name(str(energy_property))
        entities.extend(
            LGEOfficialEnergySensor(
                api=lge_device,
                entity_description=description,
                energy_property=str(energy_property),
                property_label=property_label if multi_property else None,
            )
            for description in ENERGY_USAGE_SENSORS
        )
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE sensors."""
    lge_cfg_devices = get_lge_devices(hass)

    _LOGGER.debug("Starting LGE ThinQ sensors setup")
    known_unique_ids: set[str] = set()

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_sensors: list[LGESensor | LGEOfficialEnergySensor] = [
            LGESensor(lge_device, sensor_desc, get_wrapper_device(lge_device, dev_type))
            for dev_type, sensor_descs in SENSOR_ENTITIES.items()
            for sensor_desc in sensor_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _sensor_exist(lge_device, sensor_desc)
        ]

        lge_common_sensors: list[LGESensor | LGEOfficialEnergySensor] = [
            LGESensor(lge_device, sensor_desc, get_wrapper_device(lge_device, dev_type))
            for sensor_desc in COMMON_SENSORS
            for dev_type in lge_devices
            for lge_device in lge_devices.get(dev_type, [])
        ]

        lge_energy_sensors: list[LGESensor | LGEOfficialEnergySensor] = [
            energy_sensor
            for dev_type in lge_devices
            for lge_device in lge_devices.get(dev_type, [])
            for energy_sensor in _build_official_energy_sensors(lge_device)
        ]

        entities_to_add = [
            entity
            for entity in (lge_sensors + lge_common_sensors + lge_energy_sensors)
            if entity.unique_id not in known_unique_ids
        ]
        if not entities_to_add:
            return

        known_unique_ids.update(
            entity.unique_id
            for entity in entities_to_add
            if entity.unique_id is not None
        )
        async_add_entities(entities_to_add)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            LGE_OFFICIAL_DISCOVERY,
            lambda: _async_discover_device(get_lge_devices(hass)),
        )
    )

    # register services
    platform = current_platform.get()
    if platform is None:
        return
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
    """Class to monitor sensors for LGE device."""

    entity_description: ThinQSensorEntityDescription
    _attr_has_entity_name = True
    _wrap_device: LGEBaseDevice | None

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQSensorEntityDescription,
        wrapped_device: LGEBaseDevice | None = None,
    ) -> None:
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
        """Return the supported entity features."""
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
    def icon(self) -> str | None:
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
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the optional state attributes."""
        if self._is_default and self._wrap_device:
            return cast(dict[str, Any] | None, self._wrap_device.extra_state_attributes)

        features = self.entity_description.feature_attributes
        if not (features and self._api.state):
            return None
        data: dict[str, Any] = {}
        logical_prefix = {
            DeviceType.AC: "ac.filter",
            DeviceType.AIR_PURIFIER: "air_purifier.filter",
        }.get(self._api.type)
        for key, feat in features.items():
            if logical_prefix:
                logical_value = self._api.get_hybrid_value(f"{logical_prefix}.{feat}")
                if logical_value is not None:
                    data[key] = logical_value
                    continue
            if (val := self._api.state.device_features.get(feat)) is not None:
                data[key] = val
        return data

    def _get_sensor_state(self) -> float | int | str | None:
        """Get current sensor state."""
        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            logical_key = {
                ATTR_CURRENT_COURSE: f"{logical_prefix}.current_course",
                WashDeviceFeatures.RUN_STATE: f"{logical_prefix}.run_state",
                WashDeviceFeatures.PROCESS_STATE: f"{logical_prefix}.process_state",
            }.get(self.entity_description.key)
            if (
                self.entity_description.key == DEFAULT_SENSOR
                and self._wrap_device
                and self.entity_description.value_fn is not None
            ):
                return self.entity_description.value_fn(self._wrap_device)
            if logical_key:
                hybrid_value = self._api.get_hybrid_value(logical_key)
                if hybrid_value is not None:
                    return cast(float | int | str, hybrid_value)

        ac_logical_key: str | None = None
        if self.entity_description.key == AirConditionerFeatures.ENERGY_CURRENT:
            ac_logical_key = "ac.power_current"
        elif self.entity_description.key == AirConditionerFeatures.PM1:
            ac_logical_key = "ac.pm1"
        elif self.entity_description.key == AirConditionerFeatures.PM10:
            ac_logical_key = "ac.pm10"
        elif self.entity_description.key == AirConditionerFeatures.PM25:
            ac_logical_key = "ac.pm25"
        elif self.entity_description.key == AirConditionerFeatures.FILTER_MAIN_LIFE:
            ac_logical_key = "ac.filter.filter_main_life"
        if self._api.type == DeviceType.AC and ac_logical_key:
            hybrid_value = self._api.get_hybrid_value(ac_logical_key)
            if hybrid_value is not None:
                return cast(float | int | str, hybrid_value)

        air_purifier_logical_key: str | None = None
        if self.entity_description.key == AirPurifierFeatures.FILTER_MAIN_LIFE:
            air_purifier_logical_key = "air_purifier.filter.filter_main_life"
        elif self.entity_description.key == AirPurifierFeatures.FILTER_BOTTOM_LIFE:
            air_purifier_logical_key = "air_purifier.filter.filter_bottom_life"
        elif self.entity_description.key == AirPurifierFeatures.FILTER_DUST_LIFE:
            air_purifier_logical_key = "air_purifier.filter.filter_dust_life"
        elif self.entity_description.key == AirPurifierFeatures.FILTER_MID_LIFE:
            air_purifier_logical_key = "air_purifier.filter.filter_mid_life"
        elif self.entity_description.key == AirPurifierFeatures.FILTER_TOP_LIFE:
            air_purifier_logical_key = "air_purifier.filter.filter_top_life"
        if self._api.type == DeviceType.AIR_PURIFIER and air_purifier_logical_key:
            hybrid_value = self._api.get_hybrid_value(air_purifier_logical_key)
            if hybrid_value is not None:
                return cast(float | int | str, hybrid_value)

        if self._wrap_device and self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return cast(
                float | int | str | None, self._api.state.device_features.get(feature)
            )

        return None

    async def async_remote_start(self, course: str | None = None) -> None:
        """Call the remote start command for WM devices."""
        if self._api.type not in WM_DEVICE_TYPES:
            raise NotImplementedError
        await self._api.device.remote_start(course)

    async def async_wake_up(self) -> None:
        """Call the wakeup command for WM devices."""
        if self._api.type not in WM_DEVICE_TYPES:
            raise NotImplementedError
        await self._api.device.wake_up()

    async def async_set_time(self, time_wanted: time | None = None) -> None:
        """Call the set time command for Microwave devices."""
        if self._api.type not in SET_TIME_DEVICE_TYPES:
            raise NotImplementedError
        await self._api.device.set_time(time_wanted)


class LGEOfficialEnergySensor(CoordinatorEntity, SensorEntity):
    """Official ThinQ energy usage sensor."""

    entity_description: ThinQEnergySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        entity_description: ThinQEnergySensorEntityDescription,
        energy_property: str,
        property_label: str | None = None,
    ) -> None:
        """Initialize the official energy sensor."""
        super().__init__(api.coordinator)
        self._api = api
        self.entity_description = entity_description
        self._energy_property = energy_property
        self._property_label = property_label
        self._unsub_update: Callable[[], None] | None = None
        self._attr_unique_id = (
            f"{api.unique_id}-{energy_property}-{entity_description.key}"
        )
        self._attr_device_info = api.device_info
        base_name = (
            entity_description.name
            if isinstance(entity_description.name, str)
            else "Energy usage"
        )
        if property_label:
            self._attr_name = f"{base_name} {property_label}"
        else:
            self._attr_name = base_name

    async def async_added_to_hass(self) -> None:
        """Handle entity addition."""
        await super().async_added_to_hass()
        await self._async_update_and_schedule()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None
        await super().async_will_remove_from_hass()

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return self._api.available and self.native_value is not None

    async def async_update(self, now: datetime | None = None) -> None:
        """Update the sensor state."""
        await self._async_update_and_schedule()
        self.async_write_ha_state()

    async def _async_update_and_schedule(self) -> None:
        """Fetch energy usage and schedule the next refresh."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None

        next_update = dt_util.utcnow() + self.entity_description.update_interval
        official_coordinator = find_official_coordinator(self.hass, self._api.device_id)
        official_api = getattr(official_coordinator, "api", None)

        if official_api is not None:
            now = dt_util.now()
            start_date = self.entity_description.start_date_fn(now)
            end_date = self.entity_description.end_date_fn(now)
            try:
                self._attr_native_value = await official_api.async_get_energy_usage(
                    energy_property=self._energy_property,
                    period=self.entity_description.usage_period,
                    start_date=start_date.date(),
                    end_date=end_date.date(),
                    detail=False,
                )
            except (HomeAssistantError, ThinQAPIException, ValueError) as exc:
                _LOGGER.debug(
                    "[%s:%s] Failed to fetch official energy usage for %s: %s",
                    self._api.name,
                    self.entity_description.key,
                    self._energy_property,
                    exc,
                )

        self._unsub_update = async_track_point_in_time(
            self.hass,
            self.async_update,
            next_update,
        )
