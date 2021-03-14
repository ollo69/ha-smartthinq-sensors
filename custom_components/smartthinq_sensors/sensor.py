# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

import logging
from datetime import timedelta

from .wideq import (
    FEAT_DRYLEVEL,
    FEAT_ERROR_MSG,
    FEAT_PRE_STATE,
    FEAT_PROCESS_STATE,
    FEAT_RUN_STATE,
    FEAT_SPINSPEED,
    FEAT_TUBCLEAN_COUNT,
    FEAT_TEMPCONTROL,
    FEAT_WATERTEMP,
)

from .wideq.device import (
    STATE_OPTIONITEM_OFF,
    STATE_OPTIONITEM_ON,
    UNIT_TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT,
    DeviceType,
)

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_OPENING,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity

from homeassistant.const import (
    DEVICE_CLASS_TEMPERATURE,
    STATE_ON,
    STATE_OFF,
    STATE_UNAVAILABLE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)

from .const import DOMAIN, LGE_DEVICES
from . import LGEDevice

# sensor definition
ATTR_MEASUREMENT_NAME = "measurement_name"
ATTR_ICON = "icon"
ATTR_UNIT_FN = "unit_fn"
ATTR_DEVICE_CLASS = "device_class"
ATTR_VALUE_FEAT = "value_feat"
ATTR_VALUE_FN = "value_fn"
ATTR_ENABLED = "enabled"

# general sensor attributes
ATTR_RUN_COMPLETED = "run_completed"
ATTR_INITIAL_TIME = "initial_time"
ATTR_REMAIN_TIME = "remain_time"
ATTR_RESERVE_TIME = "reserve_time"
ATTR_CURRENT_COURSE = "current_course"
ATTR_ERROR_STATE = "error_state"

# refrigerator sensor attributes
ATTR_REFRIGERATOR_TEMP = "refrigerator_temp"
ATTR_FREEZER_TEMP = "freezer_temp"
ATTR_TEMP_UNIT = "temp_unit"
ATTR_DOOROPEN_STATE = "door_open_state"

STATE_LOOKUP = {
    STATE_OPTIONITEM_OFF: STATE_OFF,
    STATE_OPTIONITEM_ON: STATE_ON,
}

TEMP_UNIT_LOOKUP = {
    UNIT_TEMP_CELSIUS: TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT: TEMP_FAHRENHEIT,
}

DEFAULT_SENSOR = "default"
DISPATCHER_REMOTE_UPDATE = "thinq_remote_update"

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)

WASHER_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:washing-machine",
        # ATTR_UNIT_FN: lambda x: None,
        # ATTR_UNIT_FN: lambda x: "dBm",
        # ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED: True,
    },
    FEAT_RUN_STATE: {
        ATTR_MEASUREMENT_NAME: "Run State",
        ATTR_ICON: "mdi:washing-machine",
        ATTR_VALUE_FEAT: FEAT_RUN_STATE,
        ATTR_ENABLED: True,
    },
    FEAT_PRE_STATE: {
        ATTR_MEASUREMENT_NAME: "Pre State",
        ATTR_ICON: "mdi:washing-machine",
        ATTR_VALUE_FEAT: FEAT_PRE_STATE,
    },
    FEAT_ERROR_MSG: {
        ATTR_MEASUREMENT_NAME: "Error Message",
        ATTR_ICON: "mdi:alert-circle-outline",
        ATTR_VALUE_FEAT: FEAT_ERROR_MSG,
    },
    FEAT_TUBCLEAN_COUNT: {
        ATTR_MEASUREMENT_NAME: "Tube Clean Counter",
        ATTR_ICON: "mdi:washing-machine",
        ATTR_VALUE_FEAT: FEAT_TUBCLEAN_COUNT,
    },
    FEAT_SPINSPEED: {
        ATTR_MEASUREMENT_NAME: "Spin Speed",
        ATTR_ICON: "mdi:rotate-3d",
        ATTR_VALUE_FEAT: FEAT_SPINSPEED,
    },
    FEAT_WATERTEMP: {
        ATTR_MEASUREMENT_NAME: "Water Temp",
        ATTR_ICON: "mdi:thermometer-lines",
        ATTR_VALUE_FEAT: FEAT_WATERTEMP,
    },
    FEAT_DRYLEVEL: {
        ATTR_MEASUREMENT_NAME: "Dry Level",
        ATTR_ICON: "mdi:tumble-dryer",
        ATTR_VALUE_FEAT: FEAT_DRYLEVEL,
    },
    ATTR_CURRENT_COURSE: {
        ATTR_MEASUREMENT_NAME: "Current Course",
        ATTR_ICON: "mdi:pin-outline",
        ATTR_VALUE_FN: lambda x: x._current_course,
    },
}

WASHER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Wash Completed",
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED: True,
    },
}

DRYER_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:tumble-dryer",
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED: True,
    },
    FEAT_RUN_STATE: {
        ATTR_MEASUREMENT_NAME: "Run State",
        ATTR_ICON: "mdi:tumble-dryer",
        ATTR_VALUE_FEAT: FEAT_RUN_STATE,
        ATTR_ENABLED: True,
    },
    FEAT_PRE_STATE: {
        ATTR_MEASUREMENT_NAME: "Pre State",
        ATTR_ICON: "mdi:tumble-dryer",
        ATTR_VALUE_FEAT: FEAT_PRE_STATE,
    },
    FEAT_ERROR_MSG: {
        ATTR_MEASUREMENT_NAME: "Error Message",
        ATTR_ICON: "mdi:alert-circle-outline",
        ATTR_VALUE_FEAT: FEAT_ERROR_MSG,
    },
    FEAT_TEMPCONTROL: {
        ATTR_MEASUREMENT_NAME: "Temp Control",
        ATTR_ICON: "mdi:thermometer-lines",
        ATTR_VALUE_FEAT: FEAT_TEMPCONTROL,
    },
    FEAT_DRYLEVEL: {
        ATTR_MEASUREMENT_NAME: "Dry Level",
        ATTR_ICON: "mdi:tumble-dryer",
        ATTR_VALUE_FEAT: FEAT_DRYLEVEL,
    },
    ATTR_CURRENT_COURSE: {
        ATTR_MEASUREMENT_NAME: "Current Course",
        ATTR_ICON: "mdi:pin-outline",
        ATTR_VALUE_FN: lambda x: x._current_course,
    },
}

DRYER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Dry Completed",
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED: True,
    },
}

STYLER_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:palette-swatch-outline",
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED: True,
    },
    FEAT_RUN_STATE: {
        ATTR_MEASUREMENT_NAME: "Run State",
        ATTR_ICON: "mdi:palette-swatch-outline",
        ATTR_VALUE_FEAT: FEAT_RUN_STATE,
        ATTR_ENABLED: True,
    },
    FEAT_PRE_STATE: {
        ATTR_MEASUREMENT_NAME: "Pre State",
        ATTR_ICON: "mdi:palette-swatch-outline",
        ATTR_VALUE_FEAT: FEAT_PRE_STATE,
    },
    FEAT_ERROR_MSG: {
        ATTR_MEASUREMENT_NAME: "Error Message",
        ATTR_ICON: "mdi:alert-circle-outline",
        ATTR_VALUE_FEAT: FEAT_ERROR_MSG,
    },
    ATTR_CURRENT_COURSE: {
        ATTR_MEASUREMENT_NAME: "Current Course",
        ATTR_ICON: "mdi:pin-outline",
        ATTR_VALUE_FN: lambda x: x._current_course,
    },
}

STYLER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Run Completed",
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED: True,
    },
}

DISHWASHER_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:dishwasher",
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED: True,
    },
    FEAT_RUN_STATE: {
        ATTR_MEASUREMENT_NAME: "Run State",
        ATTR_ICON: "mdi:dishwasher",
        ATTR_VALUE_FEAT: FEAT_RUN_STATE,
        ATTR_ENABLED: True,
    },
    FEAT_PROCESS_STATE: {
        ATTR_MEASUREMENT_NAME: "Process State",
        ATTR_ICON: "mdi:dishwasher",
        ATTR_VALUE_FEAT: FEAT_PROCESS_STATE,
        ATTR_ENABLED: True,
    },
    FEAT_ERROR_MSG: {
        ATTR_MEASUREMENT_NAME: "Error Message",
        ATTR_ICON: "mdi:alert-circle-outline",
        ATTR_VALUE_FEAT: FEAT_ERROR_MSG,
    },
    FEAT_TUBCLEAN_COUNT: {
        ATTR_MEASUREMENT_NAME: "Tube Clean Counter",
        ATTR_ICON: "mdi:dishwasher",
        ATTR_VALUE_FEAT: FEAT_TUBCLEAN_COUNT,
    },
    ATTR_CURRENT_COURSE: {
        ATTR_MEASUREMENT_NAME: "Current Course",
        ATTR_ICON: "mdi:pin-outline",
        ATTR_VALUE_FN: lambda x: x._current_course,
    },
}

DISHWASHER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Wash Completed",
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED: True,
    },
}

REFRIGERATOR_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:fridge-outline",
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED: True,
    },
    ATTR_REFRIGERATOR_TEMP: {
        ATTR_MEASUREMENT_NAME: "Refrigerator Temp",
        ATTR_UNIT_FN: lambda x: x._temp_unit,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        ATTR_VALUE_FN: lambda x: x._temp_refrigerator,
        ATTR_ENABLED: True,
    },
    ATTR_FREEZER_TEMP: {
        ATTR_MEASUREMENT_NAME: "Freezer Temp",
        ATTR_UNIT_FN: lambda x: x._temp_unit,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        ATTR_VALUE_FN: lambda x: x._temp_freezer,
        ATTR_ENABLED: True,
    },
}

REFRIGERATOR_BINARY_SENSORS = {
    ATTR_DOOROPEN_STATE: {
        ATTR_MEASUREMENT_NAME: "Door Open",
        ATTR_DEVICE_CLASS: DEVICE_CLASS_OPENING,
        ATTR_VALUE_FN: lambda x: x._dooropen_state,
        ATTR_ENABLED: True,
    },
}


async def async_setup_sensors(hass, config_entry, async_add_entities, type_binary):
    """Set up LGE device sensors and bynary sensor based on config_entry."""
    lge_sensors = []
    washer_sensors = WASHER_BINARY_SENSORS if type_binary else WASHER_SENSORS
    dryer_sensors = DRYER_BINARY_SENSORS if type_binary else DRYER_SENSORS
    styler_sensors = STYLER_BINARY_SENSORS if type_binary else STYLER_SENSORS
    dishwasher_sensors = (
        DISHWASHER_BINARY_SENSORS if type_binary else DISHWASHER_SENSORS
    )
    refrigerator_sensors = (
        REFRIGERATOR_BINARY_SENSORS if type_binary else REFRIGERATOR_SENSORS
    )

    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES, [])

    lge_sensors.extend(
        [
            LGEWashDeviceSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in washer_sensors.items()
            for lge_device in lge_devices.get(DeviceType.WASHER, [])
        ]
    )
    lge_sensors.extend(
        [
            LGEWashDeviceSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in dryer_sensors.items()
            for lge_device in lge_devices.get(DeviceType.DRYER, [])
        ]
    )
    lge_sensors.extend(
        [
            LGEWashDeviceSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in styler_sensors.items()
            for lge_device in lge_devices.get(DeviceType.STYLER, [])
        ]
    )
    lge_sensors.extend(
        [
            LGEWashDeviceSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in dishwasher_sensors.items()
            for lge_device in lge_devices.get(DeviceType.DISHWASHER, [])
        ]
    )
    lge_sensors.extend(
        [
            LGERefrigeratorSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in refrigerator_sensors.items()
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
        ]
    )

    async_add_entities(lge_sensors, True)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the LGE sensors."""
    _LOGGER.info("Starting LGE ThinQ sensors...")
    await async_setup_sensors(hass, config_entry, async_add_entities, False)


class LGESensor(Entity):
    def __init__(self, device: LGEDevice, measurement, definition, is_binary):
        """Initialize the sensor."""
        self._api = device
        self._name_slug = device.name
        self._measurement = measurement
        self._def = definition
        self._is_binary = is_binary
        self._is_default = self._measurement == DEFAULT_SENSOR
        self._dispatcher_queue = f"{DISPATCHER_REMOTE_UPDATE}-{self._name_slug}"

    @staticmethod
    def format_time(hours, minutes):
        if not minutes:
            return "0:00"
        if not hours:
            if int(minutes) >= 60:
                int_minutes = int(minutes)
                int_hours = int(int_minutes / 60)
                minutes = str(int_minutes - (int_hours * 60))
                hours = str(int_hours)
            else:
                hours = "0"
        remain_time = [hours, minutes]
        if int(minutes) < 10:
            return ":0".join(remain_time)
        else:
            return ":".join(remain_time)

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._def.get(ATTR_ENABLED, False)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        if self._is_default:
            return self._name_slug
        return f"{self._name_slug} {self._def[ATTR_MEASUREMENT_NAME]}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        if self._is_default:
            return self._api.unique_id
        return f"{self._api.unique_id}-{self._measurement}"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        if ATTR_UNIT_FN in self._def:
            return self._def[ATTR_UNIT_FN](self)
        return None

    @property
    def device_class(self):
        """Return device class."""
        return self._def.get(ATTR_DEVICE_CLASS)

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._def.get(ATTR_ICON)

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        if self._is_binary:
            ret_val = self._get_sensor_state()
            if ret_val is None:
                return False
            if isinstance(ret_val, bool):
                return ret_val
            if ret_val == STATE_ON:
                return True
            state = STATE_LOOKUP.get(ret_val, STATE_OFF)
            return True if state == STATE_ON else False
        return False

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.available:
            return STATE_UNAVAILABLE
        if self._is_binary:
            return STATE_ON if self.is_on else STATE_OFF
        return self._get_sensor_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._api.assumed_state

    @property
    def state_attributes(self):
        """Return the optional state attributes."""
        return self._api.state_attributes

    @property
    def device_info(self):
        """Return the device info."""
        return self._api.device_info

    @property
    def should_poll(self) -> bool:
        """ This sensors must be polled only by default entity """
        return self._is_default

    def update(self):
        """Update the device status"""
        self._api.device_update()
        dispatcher_send(self.hass, self._dispatcher_queue)

    async def async_added_to_hass(self):
        """Register update dispatcher."""

        async def async_state_update():
            """Update callback."""
            _LOGGER.debug("Updating %s state by dispatch", self.name)
            self.async_write_ha_state()

        if not self._is_default:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass, self._dispatcher_queue, async_state_update
                )
            )

    @property
    def _power_state(self):
        """Current power state"""
        if self._api.state:
            if self._api.state.is_on:
                return STATE_ON
        return STATE_OFF

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
        features = self._api.available_features
        if self._api.state:
            states = self._api.state.device_features
        else:
            states = {}
        for feature in features.values():
            ret_val[feature] = states.get(feature)
        return ret_val


class LGEWashDeviceSensor(LGESensor):
    """A sensor to monitor LGE Wash devices"""

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_RUN_COMPLETED: self._run_completed,
            ATTR_ERROR_STATE: self._error_state,
            ATTR_INITIAL_TIME: self._initial_time,
            ATTR_REMAIN_TIME: self._remain_time,
            ATTR_RESERVE_TIME: self._reserve_time,
            ATTR_CURRENT_COURSE: self._current_course,
        }
        features = self._get_features_value()
        data.update(features)

        return data

    @property
    def _run_completed(self):
        if self._api.state:
            if self._api.state.is_run_completed:
                return STATE_ON
        return STATE_OFF

    @property
    def _error_state(self):
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def _initial_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.initialtime_hour, self._api.state.initialtime_min
                )
        return "0:00"

    @property
    def _remain_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.remaintime_hour, self._api.state.remaintime_min
                )
        return "0:00"

    @property
    def _reserve_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.reservetime_hour, self._api.state.reservetime_min
                )
        return "0:00"

    @property
    def _current_course(self):
        if self._api.state:
            if self._api.state.is_on:
                course = self._api.state.current_course
                if course:
                    return course
                smart_course = self._api.state.current_smartcourse
                if smart_course:
                    return smart_course
        return "-"


class LGERefrigeratorSensor(LGESensor):
    """A sensor to monitor LGE Refrigerator devices"""

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_REFRIGERATOR_TEMP: self._temp_refrigerator,
            ATTR_FREEZER_TEMP: self._temp_freezer,
            ATTR_TEMP_UNIT: self._temp_unit,
            ATTR_DOOROPEN_STATE: self._dooropen_state,
        }

        if self._api.state:
            features = self._get_features_value()
            data.update(features)

        return data

    @property
    def _temp_refrigerator(self):
        if self._api.state:
            return self._api.state.temp_refrigerator
        return None

    @property
    def _temp_freezer(self):
        if self._api.state:
            return self._api.state.temp_freezer
        return None

    @property
    def _temp_unit(self):
        if self._api.state:
            unit = self._api.state.temp_unit
            return TEMP_UNIT_LOOKUP.get(unit, TEMP_CELSIUS)
        return TEMP_CELSIUS

    @property
    def _dooropen_state(self):
        if self._api.state:
            state = self._api.state.door_opened_state
            return STATE_LOOKUP.get(state, STATE_OFF)
        return STATE_OFF
