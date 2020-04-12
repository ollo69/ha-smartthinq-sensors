# REQUIREMENTS = ['wideq']
# DEPENDENCIES = ['smartthinq']

import json
import logging
import voluptuous as vol
from datetime import timedelta
import time

from .wideq.device import (
    OPTIONITEMMODES,
    STATE_OPTIONITEM_ON,
    STATE_OPTIONITEM_OFF,
    DeviceType,
)

from .wideq.washer import WasherDevice

from homeassistant.components import sensor
import homeassistant.helpers.config_validation as cv

from homeassistant.const import STATE_ON, STATE_OFF
from .const import DOMAIN, CLIENT, LGE_DEVICES
from . import LGEDevice

ATTR_CURRENT_STATUS = "current_status"
ATTR_RUN_STATE = "run_state"
ATTR_PRE_STATE = "pre_state"
ATTR_REMAIN_TIME = "remain_time"
ATTR_INITIAL_TIME = "initial_time"
ATTR_RESERVE_TIME = "reserve_time"
ATTR_CURRENT_COURSE = "current_course"
ATTR_ERROR_STATE = "error_state"
ATTR_ERROR_MSG = "error_message"
ATTR_SPIN_OPTION_STATE = "spin_option_state"
ATTR_WATERTEMP_OPTION_STATE = "watertemp_option_state"
ATTR_CREASECARE_MODE = "creasecare_mode"
ATTR_CHILDLOCK_MODE = "childlock_mode"
ATTR_STEAM_MODE = "steam_mode"
ATTR_STEAM_SOFTENER_MODE = "steam_softener_mode"
ATTR_DOORLOCK_MODE = "doorlock_mode"
ATTR_PREWASH_MODE = "prewash_mode"
ATTR_REMOTESTART_MODE = "remotestart_mode"
ATTR_TURBOWASH_MODE = "turbowash_mode"
ATTR_TUBCLEAN_COUNT = "tubclean_count"
ATTR_WASH_COMPLETED = "wash_completed"

SENSORMODES = {
    "ON": STATE_ON,
    "OFF": STATE_OFF,
}

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the LGE Washer components."""
    _LOGGER.info("Starting smartthinq sensors...")

    client = hass.data[DOMAIN][CLIENT]
    lge_sensors = []

    for device in client.devices:
        device_id = device.id
        device_name = device.name
        device_mac = device.macaddress
        model_name = device.model_name

        if device.type == DeviceType.WASHER:

            base_name = device_name

            w = LGEWasherDevice(client, device, base_name)
            lge_sensors.append(w)
            hass.data[DOMAIN][LGE_DEVICES][w.unique_id] = w

            _LOGGER.info(
                "LGE Washer added. Name: %s - Model: %s - Mac: %s - ID: %s",
                base_name,
                model_name,
                device_mac,
                device_id,
            )

    if lge_sensors:
        async_add_entities(lge_sensors)

    return True


class LGEWasherDevice(LGEDevice):
    """A sensor to monitor LGE Washer devices"""

    def __init__(self, client, device, name):

        """initialize a LGE Washer Device."""
        super().__init__(WasherDevice(client, device), name)

    @property
    def icon(self):
        return "mdi:washing-machine"

    @property
    def state_attributes(self):
        """Return the optional state attributes."""
        data = {
            ATTR_WASH_COMPLETED: self._wash_completed,
            ATTR_ERROR_STATE: self._error_state,
            ATTR_ERROR_MSG: self._error_msg,
            ATTR_RUN_STATE: self._current_run_state,
            ATTR_PRE_STATE: self._pre_state,
            ATTR_CURRENT_COURSE: self._current_course,
            ATTR_SPIN_OPTION_STATE: self._spin_option_state,
            ATTR_WATERTEMP_OPTION_STATE: self._watertemp_option_state,
            ATTR_TUBCLEAN_COUNT: self._tubclean_count,
            ATTR_REMAIN_TIME: self._remain_time,
            ATTR_INITIAL_TIME: self._initial_time,
            ATTR_RESERVE_TIME: self._reserve_time,
            ATTR_CREASECARE_MODE: self._creasecare_mode,
            ATTR_CHILDLOCK_MODE: self._childlock_mode,
            ATTR_STEAM_MODE: self._steam_mode,
            ATTR_STEAM_SOFTENER_MODE: self._steam_softener_mode,
            ATTR_DOORLOCK_MODE: self._doorlock_mode,
            ATTR_PREWASH_MODE: self._prewash_mode,
            ATTR_REMOTESTART_MODE: self._remotestart_mode,
            ATTR_TURBOWASH_MODE: self._turbowash_mode,
        }
        return data

    # @property
    # def is_on(self):
    #     if self._state:
    #         return self._state.is_on

    @property
    def _wash_completed(self):
        if self._state:
            if self._state.is_wash_completed:
                return SENSORMODES["ON"]

        return SENSORMODES["OFF"]

    @property
    def _current_run_state(self):
        if self._state:
            if self._state.is_on:
                run_state = self._state.run_state
                return run_state

        return "-"

    # @property
    # def run_list(self):
    #     return list(RUNSTATES.values())

    @property
    def _pre_state(self):
        if self._state:
            pre_state = self._state.pre_state
            if pre_state == STATE_OPTIONITEM_OFF:
                return "-"
            else:
                return pre_state

        return "-"

    @property
    def _remain_time(self):
        if self._state:
            if self._state.is_on:
                remain_hour = self._state.remaintime_hour
                remain_min = self._state.remaintime_min
                remaintime = [remain_hour, remain_min]
                if int(remain_min) < 10:
                    return ":0".join(remaintime)
                else:
                    return ":".join(remaintime)
        return "0:00"

    @property
    def _initial_time(self):
        if self._state:
            if self._state.is_on:
                initial_hour = self._state.initialtime_hour
                initial_min = self._state.initialtime_min
                initialtime = [initial_hour, initial_min]
                if int(initial_min) < 10:
                    return ":0".join(initialtime)
                else:
                    return ":".join(initialtime)
        return "0:00"

    @property
    def _reserve_time(self):
        if self._state:
            if self._state.is_on:
                reserve_hour = self._state.reservetime_hour
                reserve_min = self._state.reservetime_min
                reservetime = [reserve_hour, reserve_min]
                if int(reserve_min) < 10:
                    return ":0".join(reservetime)
                else:
                    return ":".join(reservetime)
        return "0:00"

    @property
    def _current_course(self):
        if self._state:
            course = self._state.current_course
            smartcourse = self._state.current_smartcourse
            if self._state.is_on:
                if course == "Download course":
                    return smartcourse
                elif course == "OFF":
                    return "-"
                else:
                    return course

        return "-"

    @property
    def _error_state(self):
        if self._state:
            if self._state.is_on:
                if self._state.is_error:
                    return SENSORMODES["ON"]

        return SENSORMODES["OFF"]

    @property
    def _error_msg(self):
        if self._state:
            if self._state.is_on:
                error = self._state.error_state
                return error

        return "-"

    @property
    def _spin_option_state(self):
        if self._state:
            spin_option = self._state.spin_option_state
            if spin_option == "OFF":
                return "-"
            else:
                return spin_option
        else:
            return "-"

    @property
    def _watertemp_option_state(self):
        if self._state:
            watertemp_option = self._state.water_temp_option_state
            if watertemp_option == "OFF":
                return "-"
            else:
                return watertemp_option
        else:
            return "-"

    @property
    def _creasecare_mode(self):
        if self._state:
            mode = self._state.creasecare_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _childlock_mode(self):
        if self._state:
            mode = self._state.childlock_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _steam_mode(self):
        if self._state:
            mode = self._state.steam_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _steam_softener_mode(self):
        if self._state:
            mode = self._state.steam_softener_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _prewash_mode(self):
        if self._state:
            mode = self._state.prewash_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _doorlock_mode(self):
        if self._state:
            mode = self._state.doorlock_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _remotestart_mode(self):
        if self._state:
            mode = self._state.remotestart_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _turbowash_mode(self):
        if self._state:
            mode = self._state.turbowash_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES["OFF"]

    @property
    def _tubclean_count(self):
        if self._state:
            return self._state.tubclean_count

        return "N/A"
