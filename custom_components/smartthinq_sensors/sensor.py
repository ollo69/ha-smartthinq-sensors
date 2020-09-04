# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

import logging
from datetime import timedelta

from .wideq.device import (
    STATE_OPTIONITEM_OFF,
    STATE_OPTIONITEM_ON,
    UNIT_TEMP_CELSIUS,
    UNIT_TEMP_FAHRENHEIT,
    DeviceType,
)

from homeassistant.components.binary_sensor import DEVICE_CLASS_PROBLEM, DEVICE_CLASS_OPENING
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity

from homeassistant.const import (
    DEVICE_CLASS_TEMPERATURE,
    STATE_ON,
    STATE_OFF,
    STATE_UNAVAILABLE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT
)

from .const import DOMAIN, LGE_DEVICES
from . import LGEDevice

# sensor definition
ATTR_MEASUREMENT_NAME = "measurement_name"
ATTR_ICON = "icon"
ATTR_UNIT_FN = "unit_fn"
ATTR_DEVICE_CLASS = "device_class"
ATTR_VALUE_FN = "value_fn"
ATTR_ENABLED_FN = "enabled"

# general sensor attributes
ATTR_CURRENT_STATUS = "current_status"
ATTR_RUN_STATE = "run_state"
ATTR_PRE_STATE = "pre_state"
ATTR_RUN_COMPLETED = "run_completed"
ATTR_REMAIN_TIME = "remain_time"
ATTR_INITIAL_TIME = "initial_time"
ATTR_RESERVE_TIME = "reserve_time"
ATTR_CURRENT_COURSE = "current_course"
ATTR_ERROR_STATE = "error_state"
ATTR_ERROR_MSG = "error_message"

# washer sensor attributes
ATTR_SPIN_OPTION_STATE = "spin_option_state"
ATTR_WATERTEMP_OPTION_STATE = "watertemp_option_state"
ATTR_CREASECARE_MODE = "creasecare_mode"
ATTR_CHILDLOCK_MODE = "childlock_mode"
ATTR_STEAM_MODE = "steam_mode"
ATTR_STEAM_SOFTENER_MODE = "steam_softener_mode"
ATTR_DOORLOCK_MODE = "doorlock_mode"
ATTR_DOORCLOSE_MODE = "doorclose_mode"
ATTR_PREWASH_MODE = "prewash_mode"
ATTR_REMOTESTART_MODE = "remotestart_mode"
ATTR_TURBOWASH_MODE = "turbowash_mode"
ATTR_TUBCLEAN_COUNT = "tubclean_count"

# dryer sensor attributes
ATTR_TEMPCONTROL_OPTION_STATE = "tempcontrol_option_state"
ATTR_DRYLEVEL_OPTION_STATE = "drylevel_option_state"
ATTR_TIMEDRY_OPTION_STATE = "timedry_option_state"

# dishwasher sensor attributes
ATTR_PROCESS_STATE = "process_state"
ATTR_DELAYSTART_MODE = "delay_start_mode"
ATTR_ENERGYSAVER_MODE = "energy_saver_mode"
ATTR_DUALZONE_MODE = "dual_zone_mode"
ATTR_HALFLOAD_MODE = "half_load_mode"
ATTR_RINSEREFILL_STATE = "rinse_refill_state"
ATTR_SALTREFILL_STATE = "salt_refill_state"

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
        ATTR_UNIT_FN: lambda x: None,
        # ATTR_UNIT_FN: lambda x: "dBm",
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

WASHER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Wash Completed",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED_FN: lambda x: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

DRYER_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:tumble-dryer",
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

DRYER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Dry Completed",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED_FN: lambda x: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

DISHWASHER_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:dishwasher",
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

DISHWASHER_BINARY_SENSORS = {
    ATTR_RUN_COMPLETED: {
        ATTR_MEASUREMENT_NAME: "Wash Completed",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._run_completed,
        ATTR_ENABLED_FN: lambda x: True,
    },
    ATTR_ERROR_STATE: {
        ATTR_MEASUREMENT_NAME: "Error State",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_PROBLEM,
        ATTR_VALUE_FN: lambda x: x._error_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

REFRIGERATOR_SENSORS = {
    DEFAULT_SENSOR: {
        ATTR_MEASUREMENT_NAME: "Default",
        ATTR_ICON: "mdi:fridge-outline",
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: None,
        ATTR_VALUE_FN: lambda x: x._power_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
    ATTR_REFRIGERATOR_TEMP: {
        ATTR_MEASUREMENT_NAME: "Refrigerator Temp",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: x._temp_unit,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        ATTR_VALUE_FN: lambda x: x._temp_refrigerator,
        ATTR_ENABLED_FN: lambda x: True,
    },
    ATTR_FREEZER_TEMP: {
        ATTR_MEASUREMENT_NAME: "Freezer Temp",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: x._temp_unit,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        ATTR_VALUE_FN: lambda x: x._temp_freezer,
        ATTR_ENABLED_FN: lambda x: True,
    },
}

REFRIGERATOR_BINARY_SENSORS = {
    ATTR_DOOROPEN_STATE: {
        ATTR_MEASUREMENT_NAME: "Door Open",
        ATTR_ICON: None,
        ATTR_UNIT_FN: lambda x: None,
        ATTR_DEVICE_CLASS: DEVICE_CLASS_OPENING,
        ATTR_VALUE_FN: lambda x: x._dooropen_state,
        ATTR_ENABLED_FN: lambda x: True,
    },
}


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass


async def async_setup_sensors(hass, config_entry, async_add_entities, type_binary):
    """Set up LGE device sensors and bynary sensor based on config_entry."""
    lge_sensors = []
    washer_sensors = WASHER_BINARY_SENSORS if type_binary else WASHER_SENSORS
    dryer_sensors = DRYER_BINARY_SENSORS if type_binary else DRYER_SENSORS
    dishwasher_sensors = DISHWASHER_BINARY_SENSORS if type_binary else DISHWASHER_SENSORS
    refrigerator_sensors = REFRIGERATOR_BINARY_SENSORS if type_binary else REFRIGERATOR_SENSORS

    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES, [])

    lge_sensors.extend(
        [
            LGEWasherSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in washer_sensors.items()
            for lge_device in lge_devices.get(DeviceType.WASHER, [])
            if definition[ATTR_ENABLED_FN](lge_device)
        ]
    )
    lge_sensors.extend(
        [
            LGEDryerSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in dryer_sensors.items()
            for lge_device in lge_devices.get(DeviceType.DRYER, [])
            if definition[ATTR_ENABLED_FN](lge_device)
        ]
    )
    lge_sensors.extend(
        [
            LGEDishWasherSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in dishwasher_sensors.items()
            for lge_device in lge_devices.get(DeviceType.DISHWASHER, [])
            if definition[ATTR_ENABLED_FN](lge_device)
        ]
    )
    lge_sensors.extend(
        [
            LGERefrigeratorSensor(lge_device, measurement, definition, type_binary)
            for measurement, definition in refrigerator_sensors.items()
            for lge_device in lge_devices.get(DeviceType.REFRIGERATOR, [])
            if definition[ATTR_ENABLED_FN](lge_device)
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
        self._unsub_dispatcher = None
        self._dispatcher_queue = f"{DISPATCHER_REMOTE_UPDATE}-{self._name_slug}"

    @staticmethod
    def format_time(hours, minutes):
        if not (hours and minutes):
            return "0:00"
        remain_time = [hours, minutes]
        if int(minutes) < 10:
            return ":0".join(remain_time)
        else:
            return ":".join(remain_time)

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
        return self._def[ATTR_UNIT_FN](self)

    @property
    def device_class(self):
        """Return device class."""
        return self._def[ATTR_DEVICE_CLASS]

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._def[ATTR_ICON]

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        if self._is_binary:
            ret_val = self._def[ATTR_VALUE_FN](self)
            if isinstance(ret_val, bool):
                return ret_val
            return True if ret_val == STATE_ON else False
        return False

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.available:
            return STATE_UNAVAILABLE
        if self._is_binary:
            return STATE_ON if self.is_on else STATE_OFF
        return self._def[ATTR_VALUE_FN](self)

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
            self._unsub_dispatcher = async_dispatcher_connect(
                self.hass, self._dispatcher_queue, async_state_update
            )

    async def async_will_remove_from_hass(self):
        """Unregister update dispatcher."""
        if self._unsub_dispatcher is not None:
            self._unsub_dispatcher()
            self._unsub_dispatcher = None

    @property
    def _power_state(self):
        """Current power state"""
        if self._api.state:
            if self._api.state.is_on:
                return STATE_ON
        return STATE_OFF


class LGEWasherSensor(LGESensor):
    """A sensor to monitor LGE Washer devices"""

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_RUN_COMPLETED: self._run_completed,
            ATTR_ERROR_STATE: self._error_state,
            ATTR_ERROR_MSG: self._error_msg,
            ATTR_RUN_STATE: self._current_run_state,
            ATTR_PRE_STATE: self._pre_state,
            ATTR_CURRENT_COURSE: self._current_course,
            ATTR_SPIN_OPTION_STATE: self._spin_option_state,
            ATTR_WATERTEMP_OPTION_STATE: self._watertemp_option_state,
            ATTR_DRYLEVEL_OPTION_STATE: self._drylevel_option_state,
            ATTR_TUBCLEAN_COUNT: self._tubclean_count,
            ATTR_REMAIN_TIME: self._remain_time,
            ATTR_INITIAL_TIME: self._initial_time,
            ATTR_RESERVE_TIME: self._reserve_time,
            ATTR_DOORLOCK_MODE: self._doorlock_mode,
            ATTR_DOORCLOSE_MODE: self._doorclose_mode,
            ATTR_CHILDLOCK_MODE: self._childlock_mode,
            ATTR_REMOTESTART_MODE: self._remotestart_mode,
            ATTR_CREASECARE_MODE: self._creasecare_mode,
            ATTR_STEAM_MODE: self._steam_mode,
            ATTR_STEAM_SOFTENER_MODE: self._steam_softener_mode,
            ATTR_PREWASH_MODE: self._prewash_mode,
            ATTR_TURBOWASH_MODE: self._turbowash_mode,
        }
        return data

    @property
    def _run_completed(self):
        if self._api.state:
            if self._api.state.is_run_completed:
                return STATE_ON
        return STATE_OFF

    @property
    def _current_run_state(self):
        if self._api.state:
            run_state = self._api.state.run_state
            return run_state
        return "-"

    @property
    def _pre_state(self):
        if self._api.state:
            pre_state = self._api.state.pre_state
            return pre_state
        return "-"

    @property
    def _remain_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.remaintime_hour,
                    self._api.state.remaintime_min
                )
        return "0:00"

    @property
    def _initial_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.initialtime_hour,
                    self._api.state.initialtime_min
                )
        return "0:00"

    @property
    def _reserve_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.reservetime_hour,
                    self._api.state.reservetime_min
                )
        return "0:00"

    @property
    def _current_course(self):
        if self._api.state:
            if self._api.state.is_on:
                course = self._api.state.current_course
                if course:
                    return course
                smartcourse = self._api.state.current_smartcourse
                if smartcourse:
                    return smartcourse
        return "-"

    @property
    def _error_state(self):
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def _error_msg(self):
        if self._api.state:
            error = self._api.state.error_state
            return error
        return "-"

    @property
    def _spin_option_state(self):
        if self._api.state:
            spin_option = self._api.state.spin_option_state
            return spin_option
        return "-"

    @property
    def _watertemp_option_state(self):
        if self._api.state:
            watertemp_option = self._api.state.water_temp_option_state
            return watertemp_option
        return "-"

    @property
    def _drylevel_option_state(self):
        if self._api.state:
            drylevel_option = self._api.state.dry_level_option_state
            return drylevel_option
        return "-"

    @property
    def _tubclean_count(self):
        if self._api.state:
            tubclean_count = self._api.state.tubclean_count
            return tubclean_count
        return "N/A"

    @property
    def _doorlock_mode(self):
        if self._api.state:
            mode = self._api.state.doorlock_state
            return mode
        return None

    @property
    def _doorclose_mode(self):
        if self._api.state:
            mode = self._api.state.doorclose_state
            return mode
        return None

    @property
    def _childlock_mode(self):
        if self._api.state:
            mode = self._api.state.childlock_state
            return mode
        return None

    @property
    def _remotestart_mode(self):
        if self._api.state:
            mode = self._api.state.remotestart_state
            return mode
        return None

    @property
    def _creasecare_mode(self):
        if self._api.state:
            mode = self._api.state.creasecare_state
            return mode
        return None

    @property
    def _steam_mode(self):
        if self._api.state:
            mode = self._api.state.steam_state
            return mode
        return None

    @property
    def _steam_softener_mode(self):
        if self._api.state:
            mode = self._api.state.steam_softener_state
            return mode
        return None

    @property
    def _prewash_mode(self):
        if self._api.state:
            mode = self._api.state.prewash_state
            return mode
        return None

    @property
    def _turbowash_mode(self):
        if self._api.state:
            mode = self._api.state.turbowash_state
            return mode
        return None


class LGEDryerSensor(LGESensor):
    """A sensor to monitor LGE Dryer devices"""

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_RUN_COMPLETED: self._run_completed,
            ATTR_ERROR_STATE: self._error_state,
            ATTR_ERROR_MSG: self._error_msg,
            ATTR_RUN_STATE: self._current_run_state,
            ATTR_PRE_STATE: self._pre_state,
            ATTR_CURRENT_COURSE: self._current_course,
            ATTR_TEMPCONTROL_OPTION_STATE: self._tempcontrol_option_state,
            ATTR_DRYLEVEL_OPTION_STATE: self._drylevel_option_state,
            # ATTR_TIMEDRY_OPTION_STATE: self._timedry_option_state,
            ATTR_REMAIN_TIME: self._remain_time,
            ATTR_INITIAL_TIME: self._initial_time,
            ATTR_RESERVE_TIME: self._reserve_time,
            ATTR_DOORLOCK_MODE: self._doorlock_mode,
            ATTR_CHILDLOCK_MODE: self._childlock_mode,
        }
        return data

    @property
    def _run_completed(self):
        if self._api.state:
            if self._api.state.is_run_completed:
                return STATE_ON
        return STATE_OFF

    @property
    def _current_run_state(self):
        if self._api.state:
            run_state = self._api.state.run_state
            return run_state
        return "-"

    @property
    def _pre_state(self):
        if self._api.state:
            pre_state = self._api.state.pre_state
            return pre_state
        return "-"

    @property
    def _remain_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.remaintime_hour,
                    self._api.state.remaintime_min
                )
        return "0:00"

    @property
    def _initial_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.initialtime_hour,
                    self._api.state.initialtime_min
                )
        return "0:00"

    @property
    def _reserve_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.reservetime_hour,
                    self._api.state.reservetime_min
                )
        return "0:00"

    @property
    def _current_course(self):
        if self._api.state:
            if self._api.state.is_on:
                course = self._api.state.current_course
                if course:
                    return course
                smartcourse = self._api.state.current_smartcourse
                if smartcourse:
                    return smartcourse
        return "-"

    @property
    def _error_state(self):
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def _error_msg(self):
        if self._api.state:
            error = self._api.state.error_state
            return error
        return "-"

    @property
    def _tempcontrol_option_state(self):
        if self._api.state:
            temp_option = self._api.state.temp_control_option_state
            return temp_option
        return "-"

    @property
    def _drylevel_option_state(self):
        if self._api.state:
            drylevel_option = self._api.state.dry_level_option_state
            return drylevel_option
        return "-"

    @property
    def _timedry_option_state(self):
        if self._api.state:
            timedry_option = self._api.state.time_dry_option_state
            return timedry_option
        return "-"

    @property
    def _doorlock_mode(self):
        if self._api.state:
            mode = self._api.state.doorlock_state
            return mode
        return None

    @property
    def _childlock_mode(self):
        if self._api.state:
            mode = self._api.state.childlock_state
            return mode
        return None


class LGEDishWasherSensor(LGESensor):
    """A sensor to monitor LGE DishWasher devices"""

    @property
    def device_state_attributes(self):
        """Return the optional state attributes."""
        if not self._is_default:
            return None

        data = {
            ATTR_RUN_COMPLETED: self._run_completed,
            ATTR_ERROR_STATE: self._error_state,
            ATTR_ERROR_MSG: self._error_msg,
            ATTR_DOOROPEN_STATE: self._dooropen_state,
            ATTR_RINSEREFILL_STATE: self._rinserefill_state,
            ATTR_SALTREFILL_STATE: self._saltrefill_state,
            ATTR_RUN_STATE: self._current_run_state,
            ATTR_PROCESS_STATE: self._process_state,
            ATTR_CURRENT_COURSE: self._current_course,
            ATTR_TUBCLEAN_COUNT: self._tubclean_count,
            ATTR_REMAIN_TIME: self._remain_time,
            ATTR_INITIAL_TIME: self._initial_time,
            ATTR_RESERVE_TIME: self._reserve_time,
            ATTR_HALFLOAD_MODE: self._halfload_mode,
            ATTR_CHILDLOCK_MODE: self._childlock_mode,
            ATTR_DELAYSTART_MODE: self._delaystart_mode,
            ATTR_ENERGYSAVER_MODE: self._energysaver_mode,
            ATTR_DUALZONE_MODE: self._dualzone_mode,
        }
        return data

    @property
    def _run_completed(self):
        if self._api.state:
            if self._api.state.is_run_completed:
                return STATE_ON
        return STATE_OFF

    @property
    def _current_run_state(self):
        if self._api.state:
            run_state = self._api.state.run_state
            return run_state
        return "-"

    @property
    def _process_state(self):
        if self._api.state:
            process = self._api.state.process_state
            return process
        return "-"

    @property
    def _remain_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.remaintime_hour,
                    self._api.state.remaintime_min
                )
        return "0:00"

    @property
    def _initial_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.initialtime_hour,
                    self._api.state.initialtime_min
                )
        return "0:00"

    @property
    def _reserve_time(self):
        if self._api.state:
            if self._api.state.is_on:
                return LGESensor.format_time(
                    self._api.state.reservetime_hour,
                    self._api.state.reservetime_min
                )
        return "0:00"

    @property
    def _current_course(self):
        if self._api.state:
            if self._api.state.is_on:
                course = self._api.state.current_course
                if course:
                    return course
                smartcourse = self._api.state.current_smartcourse
                if smartcourse:
                    return smartcourse
        return "-"

    @property
    def _error_state(self):
        if self._api.state:
            if self._api.state.is_error:
                return STATE_ON
        return STATE_OFF

    @property
    def _error_msg(self):
        if self._api.state:
            error = self._api.state.error_state
            return error
        return "-"

    @property
    def _tubclean_count(self):
        if self._api.state:
            tubclean_count = self._api.state.tubclean_count
            return tubclean_count
        return "N/A"

    @property
    def _dooropen_state(self):
        if self._api.state:
            state = self._api.state.door_opened_state
            return STATE_LOOKUP.get(state, STATE_OFF)
        return None

    @property
    def _rinserefill_state(self):
        if self._api.state:
            state = self._api.state.rinserefill_state
            return STATE_LOOKUP.get(state, STATE_OFF)
        return STATE_OFF

    @property
    def _saltrefill_state(self):
        if self._api.state:
            state = self._api.state.saltrefill_state
            return STATE_LOOKUP.get(state, STATE_OFF)
        return STATE_OFF

    @property
    def _halfload_mode(self):
        if self._api.state:
            mode = self._api.state.halfload_state
            return mode
        return None

    @property
    def _childlock_mode(self):
        if self._api.state:
            mode = self._api.state.childlock_state
            return mode
        return None

    @property
    def _delaystart_mode(self):
        if self._api.state:
            mode = self._api.state.delaystart_state
            return mode
        return None

    @property
    def _energysaver_mode(self):
        if self._api.state:
            mode = self._api.state.energysaver_state
            return mode
        return None

    @property
    def _dualzone_mode(self):
        if self._api.state:
            mode = self._api.state.dualzone_state
            return mode
        return None


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
            for name, value in self._api.state.device_features.items():
                data[name] = value

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
