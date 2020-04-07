#REQUIREMENTS = ['wideq']
#DEPENDENCIES = ['smartthinq']

import logging
import voluptuous as vol
import json
from datetime import timedelta
import time

from .wideq.device import(
    OPTIONITEMMODES,
    STATE_OPTIONITEM_ON,
    STATE_OPTIONITEM_OFF,
    DeviceType,
)

from .wideq.core_exceptions import(
    NotLoggedInError,
    NotConnectedError,
)

from .wideq.washer import (
    WasherDevice,
)

from homeassistant.components import sensor
import homeassistant.helpers.config_validation as cv

from homeassistant.const import STATE_ON, STATE_OFF
from .const import DOMAIN, CLIENT, LGE_DEVICES 
from . import LGEDevice

#LGE_WASHER_DEVICES = 'lge_washer_devices'

ATTR_CURRENT_STATUS = 'current_status'
ATTR_RUN_STATE = 'run_state'
ATTR_PRE_STATE = 'pre_state'
ATTR_REMAIN_TIME = 'remain_time'
ATTR_INITIAL_TIME = 'initial_time'
ATTR_RESERVE_TIME = 'reserve_time'
ATTR_CURRENT_COURSE = 'current_course'
ATTR_ERROR_STATE = 'error_state'
ATTR_ERROR_MSG = 'error_message'
ATTR_SPIN_OPTION_STATE = 'spin_option_state'
ATTR_WATERTEMP_OPTION_STATE = 'watertemp_option_state'
ATTR_CREASECARE_MODE = 'creasecare_mode'
ATTR_CHILDLOCK_MODE = 'childlock_mode'
ATTR_STEAM_MODE = 'steam_mode'
ATTR_STEAM_SOFTENER_MODE = 'steam_softener_mode'
ATTR_DOORLOCK_MODE = 'doorlock_mode'
ATTR_PREWASH_MODE = 'prewash_mode'
ATTR_REMOTESTART_MODE = 'remotestart_mode'
ATTR_TURBOWASH_MODE = 'turbowash_mode'
ATTR_TUBCLEAN_COUNT = 'tubclean_count'
ATTR_WASH_COMPLETED = 'wash_completed'

SENSORMODES = {
    'ON': STATE_ON,
    'OFF': STATE_OFF,
}

MAX_RETRIES = 4
MAX_CONN_RETRIES = 2
MAX_LOOP_WARN = 2

LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)

def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the LGE Washer components."""
    LOGGER.info("Starting smartthinq sensors...")

    client = hass.data[DOMAIN][CLIENT]
    lge_sensors = []

    for device in client.devices:
        device_id = device.id
        device_name = device.name
        device_mac = device.macaddress
        model_name = device.model_name

        if device.type == DeviceType.WASHER:

            base_name = device_name
            model_info = client.model_info(device)
            model = model_name + '-' + model_info.model_type
            
            w = LGEWASHERDEVICE(client, device, base_name, model)
            lge_sensors.append(w)
            hass.data[DOMAIN][LGE_DEVICES][w.unique_id] = w

            LOGGER.info("LGE Washer added. Name: %s - Model: %s - Mac: %s - ID: %s", base_name, model, device_mac, device_id)

    if lge_sensors:
        async_add_entities(lge_sensors)
    
    return True


class LGEWASHERDEVICE(LGEDevice):
    def __init__(self, client, device, name, model):
        
        """initialize a LGE Washer Device."""
        LGEDevice.__init__(self, client, device)

        # This constructor is called during platform creation. It must not
        # involve any API calls that actually need the dishwasher to be
        # connected, otherwise the device construction will fail and the entity
        # will not get created. Specifically, calls that depend on dishwasher
        # interaction should only happen in update(...), including the start of
        # the monitor task.
        self._washer = WasherDevice(client, device)
        self._name = name
        self._device_id = device.id
        self._mac = device.macaddress
        self._firmware = device.firmware
        
        self._model = model
        self._id = "%s:%s" % ("washer", device.id)

        self._state = None

        self._retrycount = 0
        self._disconected = True
        self._notlogged = False

    #@property
    #def supported_features(self):
    #    """ none """

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self) -> bool:
        # This sensors must be polled. We leave this task to the HomeAssistant engine
        return True

    @property
    def unique_id(self) -> str:
        return self._id

    @property
    def icon(self):
        return "mdi:washing-machine"

    @property
    def device_info(self):
        data = {
            'identifiers': {(DOMAIN, self._device_id)},
            'name': self._name,
            'manufacturer': 'LG',
            'model': 'Washer %s (MAC: %s)' % (self._model, self._mac)
        }
        if self._firmware:
            data['sw_version'] = self._firmware
            
        return data

    @property
    def state_attributes(self):
        """Return the optional state attributes."""
        data={}
        data[ATTR_WASH_COMPLETED] = self.wash_completed
        data[ATTR_ERROR_STATE] = self.error_state
        data[ATTR_ERROR_MSG] = self.error_msg
        data[ATTR_RUN_STATE] = self.current_run_state
        data[ATTR_PRE_STATE] = self.pre_state
        data[ATTR_CURRENT_COURSE] = self.current_course
        data[ATTR_SPIN_OPTION_STATE] = self.spin_option_state
        data[ATTR_WATERTEMP_OPTION_STATE] = self.watertemp_option_state
        data[ATTR_TUBCLEAN_COUNT] = self.tubclean_count
        data[ATTR_REMAIN_TIME] = self.remain_time
        data[ATTR_INITIAL_TIME] = self.initial_time
        data[ATTR_RESERVE_TIME] = self.reserve_time
        data[ATTR_CREASECARE_MODE] = self.creasecare_mode
        data[ATTR_CHILDLOCK_MODE] = self.childlock_mode
        data[ATTR_STEAM_MODE] = self.steam_mode
        data[ATTR_STEAM_SOFTENER_MODE] = self.steam_softener_mode
        data[ATTR_DOORLOCK_MODE] = self.doorlock_mode
        data[ATTR_PREWASH_MODE] = self.prewash_mode
        data[ATTR_REMOTESTART_MODE] = self.remotestart_mode
        data[ATTR_TURBOWASH_MODE] = self.turbowash_mode
        
        return data

    #@property
    #def is_on(self):
    #    if self._state:
    #        return self._state.is_on

    @property
    def state(self):
        if self._state:
            if self._state.is_on:
                return SENSORMODES['ON']
                
        return SENSORMODES['OFF']

    @property
    def wash_completed(self):
        if self._state:
            if self._state.is_wash_completed:
                return SENSORMODES['ON']
                
        return SENSORMODES['OFF']

    @property
    def current_run_state(self):
        if self._state:
            if self._state.is_on:
                run_state = self._state.run_state
                return run_state
                
        return '-'

    #@property
    #def run_list(self):
    #    return list(RUNSTATES.values())

    @property
    def pre_state(self):
        if self._state:
            pre_state = self._state.pre_state
            if pre_state == STATE_OPTIONITEM_OFF:
                return '-'
            else:
                return pre_state
                
        return '-'

    @property
    def remain_time(self):
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
    def initial_time(self):
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
    def reserve_time(self):
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
    def current_course(self):
        if self._state:
            course = self._state.current_course
            smartcourse = self._state.current_smartcourse
            if self._state.is_on:
                if course == 'Download course':
                    return smartcourse
                elif course == 'OFF':
                    return '-'
                else:
                    return course

        return '-'

    @property
    def error_state(self):
        if self._state:
            if self._state.is_on:
                if self._state.is_error:
                    return SENSORMODES['ON']

        return SENSORMODES['OFF']

    @property
    def error_msg(self):
        if self._state:
            if self._state.is_on:
                error = self._state.error_state
                return error
                
        return '-'

    @property
    def spin_option_state(self):
        if self._state:
            spin_option = self._state.spin_option_state
            if spin_option == 'OFF':
                return '-'
            else:
                return spin_option
        else:
            return '-'

    @property
    def watertemp_option_state(self):
        if self._state:
            watertemp_option = self._state.water_temp_option_state
            if watertemp_option == 'OFF':
                return '-'
            else:
                return watertemp_option
        else:
            return '-'

    @property
    def creasecare_mode(self):
        if self._state:
            mode = self._state.creasecare_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def childlock_mode(self):
        if self._state:
            mode = self._state.childlock_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def steam_mode(self):
        if self._state:
            mode = self._state.steam_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def steam_softener_mode(self):
        if self._state:
            mode = self._state.steam_softener_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def prewash_mode(self):
        if self._state:
            mode = self._state.prewash_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def doorlock_mode(self):
        if self._state:
            mode = self._state.doorlock_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def remotestart_mode(self):
        if self._state:
            mode = self._state.remotestart_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def turbowash_mode(self):
        if self._state:
            mode = self._state.turbowash_state
            return OPTIONITEMMODES[mode]
        else:
            return OPTIONITEMMODES['OFF']

    @property
    def tubclean_count(self):
        if self._state:
            return self._state.tubclean_count

        return 'N/A'

    def _restart_monitor(self):

        try:
            if self._notlogged:
                self._client.refresh()
                self._notlogged = False
                self._disconected = True
                
            self._washer.monitor_start()
            #self._washer.delete_permission()
            self._disconected = False
        
        except NotConnectedError:
            LOGGER.debug('Device not connected. Status not available.')
            self._disconected = True
            #self._state = None

        except NotLoggedInError:
            LOGGER.info('Session expired. Refreshing.')
            #self._client.refresh()
            self._notlogged = True
            
        except Exception as ex:
            LOGGER.warn('Generic Wideq Error - [%s]. Exiting', str(ex))
            self._notlogged = True

    def update(self):

        LOGGER.debug('Updating smartthinq device %s.', self.name)

        # On initial construction, the dishwasher monitor task
        # will not have been created. If so, start monitoring here.
        #if getattr(self._washer, 'mon', None) is None:
        #    self._restart_monitor()

        for iteration in range(MAX_RETRIES):
            LOGGER.debug('Polling...')

            if self._disconected or self._notlogged:
                if iteration >= MAX_CONN_RETRIES and iteration > 0:
                    LOGGER.debug('Connection not available. Status update failed.')
                    return
                    
                self._retrycount = 0
                self._restart_monitor()
            
            if self._disconected:
                return

            if not (self._disconected or self._notlogged):
                try:
                    state = self._washer.poll()
                    
                except NotLoggedInError:
                    #self._client.refresh()
                    #self._restart_monitor()
                    self._notlogged = True

                except NotConnectedError:
                    self._disconected = True
                    return
                    #time.sleep(1)

                except:
                    LOGGER.warn('Generic Wideq Error.')
                    self._notlogged = True

                else:
                    if state:
                        LOGGER.debug('Status updated: %s', state.run_state)
                        #l = dir(state)
                        #LOGGER.debug('Status attributes: %s', l)
                        
                        self._retrycount = 0
                        self._state = state
                        return

                    LOGGER.debug('No status available yet.')
                
            #time.sleep(2 ** iteration)
            time.sleep(1)

        # We tried several times but got no result. This might happen
        # when the monitoring request gets into a bad state, so we
        # restart the task.
        if self._retrycount >= MAX_LOOP_WARN:
            self._retrycount = 0
            LOGGER.warn('Status update failed.')
        else:
            self._retrycount += 1
            LOGGER.debug('Status update failed.')
