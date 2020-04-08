"""------------------for Washer"""
import datetime
import enum
import time
import logging
from typing import Optional

from .device import(
    Device,
    DeviceStatus,
    STATE_UNKNOWN,
    STATE_OPTIONITEM_ON,
    STATE_OPTIONITEM_OFF,
)

from .washer_states import(
    STATE_WASHER,
    STATE_WASHER_ERROR,
    WASHERSTATES,
    WASHERWATERTEMPS,
    WASHERSPINSPEEDS,
    WASHREFERRORS,
    WASHERERRORS,
)

_LOGGER = logging.getLogger(__name__)


class WasherDevice(Device):
    
    def delete_permission(self):
        self._delete_permission()
    
    def poll(self) -> Optional['WasherStatus']:
        """Poll the device's current state."""

        res = self.device_poll("washerDryer")
        if not res:
            return None

        return WasherStatus(self, res)


class WasherStatus(DeviceStatus):
    
    def __init__(self, device, data):
        super().__init__(device, data)
        self._run_state = None
        self._pre_state = None
        self._error = None

    def _get_run_state(self):
        if not self._run_state:
            state = self.lookup_enum(['State', 'state'])
            self._run_state = self.set_unknown(WASHERSTATES.get(state, None), state, 'status')
        return self._run_state

    def _get_pre_state(self):
        if not self._pre_state:
            state = self.lookup_enum(['PreState', 'preState'])
            self._pre_state = self.set_unknown(WASHERSTATES.get(state, None), state, 'status')
        return self._pre_state

    def _get_error(self):
        if not self._error:
            error = self.lookup_reference(['Error', 'error'])
            self._error = self.set_unknown(WASHREFERRORS.get(error, None), error, 'error_status')
        return self._error

    @property
    def is_on(self):
        run_state = self._get_run_state()
        return run_state != STATE_WASHER.POWER_OFF

    @property
    def is_wash_completed(self):
        run_state = self._get_run_state()
        pre_state = self._get_pre_state()
        if (run_state == STATE_WASHER.END or (run_state == STATE_WASHER.POWER_OFF and pre_state == STATE_WASHER.END)):
            return True
        return False

    @property
    def is_error(self):
        error = self._get_error()
        if (error != STATE_WASHER_ERROR.NO_ERROR and error != STATE_WASHER_ERROR.OFF):
            return True
        return False
        
    @property
    def run_state(self):
        run_state = self._get_run_state()
        return run_state.value

    @property
    def pre_state(self):
        pre_state = self._get_pre_state()
        return pre_state.value

    @property
    def error_state(self):
        error = self._get_error()
        return error.value
    #    error = self.lookup_reference('Error')
    #    if error == '-':
    #        return 'OFF'
    #    elif error == 'No Error':
    #        return 'NO_ERROR'
    #    else:
    #        return WASHERERROR(error)

    @property
    def spin_option_state(self):
        spinspeed = self.lookup_enum(['SpinSpeed', 'spin'])
        if spinspeed == '-':
            return 'OFF'
        return self.set_unknown(WASHERSPINSPEEDS.get(spinspeed, None), spinspeed, 'spin_option').value

    @property
    def water_temp_option_state(self):
        water_temp = self.lookup_enum(['WTemp', 'WaterTemp', 'temp'])
        if water_temp == '-':
            return 'OFF'
        return self.set_unknown(WASHERWATERTEMPS.get(water_temp, None), water_temp, 'water_temp').value

    @property
    def current_course(self):
        course = self.lookup_reference(['APCourse', 'Course'])
        if course == '-':
            return 'OFF'
        return course
   
    @property
    def current_smartcourse(self):
        smartcourse = self.lookup_reference('SmartCourse')
        if smartcourse == '-':
            return 'OFF'
        else:
            return smartcourse

    @property
    def remaintime_hour(self):
        value = self.data.get('Remain_Time_H')
        if not value:
            value = str(int(self.data.get('remainTimeHour')))
        return value
    
    @property
    def remaintime_min(self):
        value = self.data.get('Remain_Time_M')
        if not value:
            value = str(int(self.data.get('remainTimeMinute')))
        return value

    @property
    def initialtime_hour(self):
        value = self.data.get('Initial_Time_H')
        if not value:
            value = str(int(self.data.get('initialTimeHour')))
        return value

    @property
    def initialtime_min(self):
        value = self.data.get('Initial_Time_M')
        if not value:
            value = str(int(self.data.get('initialTimeMinute')))
        return value

    @property
    def reservetime_hour(self):
        value = self.data.get('Reserve_Time_H')
        if not value:
            value = str(int(self.data.get('reserveTimeHour')))
        return value
    
    @property
    def reservetime_min(self):
        value = self.data.get('Reserve_Time_M')
        if not value:
            value = str(int(self.data.get('reserveTimeMinute')))
        return value

    @property
    def creasecare_state(self):
        return self.lookup_bit('Option1', 1)

    @property
    def childlock_state(self):
        return self.lookup_bit('Option2', 7)

    @property
    def steam_state(self):
        return self.lookup_bit('Option1', 7)

    @property
    def steam_softener_state(self):
        return self.lookup_bit('Option1', 2)

    @property
    def doorlock_state(self):
        return self.lookup_bit('Option2', 6)

    @property
    def prewash_state(self):
        return self.lookup_bit('Option1', 6)

    @property
    def remotestart_state(self):
        return self.lookup_bit('Option2', 1)

    @property
    def turbowash_state(self):
        return self.lookup_bit('Option1', 0)

    @property
    def tubclean_count(self):
        return self.data['TCLCount']
