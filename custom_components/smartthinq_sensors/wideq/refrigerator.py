"""------------------for Refrigerator"""
import logging
from typing import Optional

from .device import (
    STATE_OPTIONITEM_NONE,
    UNIT_TEMP_FAHRENHEIT,
    Device,
    DeviceStatus,
)

from .refrigerator_states import (
    REFRTEMPUNIT,
    REFRICEPLUS,
    REFRAIRFILTER,
    REFRSMARTSAVMODE,
    REFRSMARTSAVSTATUS,
    REFRDOORSTATUS,
    REFRLOCKSTATUS,
    REFRECOSTATUS,
)

_LOGGER = logging.getLogger(__name__)


class RefrigeratorDevice(Device):
    """A higher-level interface for a dryer."""
    def __init__(self, client, device):
        super().__init__(client, device, RefrigeratorStatus(self, None))

    def poll(self) -> Optional["RefrigeratorStatus"]:
        """Poll the device's current state."""

        res = self.device_poll("refState")
        if not res:
            return None

        self._status = RefrigeratorStatus(self, res)
        return self._status


class RefrigeratorStatus(DeviceStatus):
    """Higher-level information about a refrigerator's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """
    def __init__(self, device, data):
        super().__init__(device, data)
        self._temp_unit = None

    def _get_temp_unit(self):
        if not self._temp_unit:
            temp_unit = self.lookup_enum(["TempUnit", "tempUnit"])
            if not temp_unit:
                self._temp_unit = STATE_OPTIONITEM_NONE
            else:
                self._temp_unit = self._set_unknown(
                    state=REFRTEMPUNIT.get(temp_unit, None), key=temp_unit, type="TempUnit",
                ).value
        return self._temp_unit

    def _get_temp_val_v1(self, key):
        temp = self.lookup_enum(key)
        temp_key = self._data.get(key)
        if not temp or temp_key is None:
            if temp_key is not None:
                return str(temp_key)
            return STATE_OPTIONITEM_NONE
        if temp != temp_key:
            return temp
        unit = self._get_temp_unit()
        unit_key = "_F" if unit == UNIT_TEMP_FAHRENHEIT else "_C"
        result = self._device.model_info.enum_name(
            key + unit_key, temp_key
        )
        if not result:
            return temp
        return result

    def _get_temp_val_v2(self, key):
        temp = self.int_or_none(self._data.get(key))
        if not temp:
            return STATE_OPTIONITEM_NONE
        unit = self._data.get("tempUnit")
        ref_key = self._device.model_info.target_key(
            key, unit, "tempUnit"
        )
        if not ref_key:
            return str(temp)
        return self._device.model_info.enum_name(
            ref_key, str(temp)
        )

    @property
    def is_on(self):
        return True

    @property
    def temp_refrigerator(self):
        if self.is_info_v2:
            return self._get_temp_val_v2("fridgeTemp")
        return self._get_temp_val_v1("TempRefrigerator")

    @property
    def temp_freezer(self):
        if self.is_info_v2:
            return self._get_temp_val_v2("freezerTemp")
        return self._get_temp_val_v1("TempFreezer")

    @property
    def temp_unit(self):
        return self._get_temp_unit()

    @property
    def door_opened_state(self):
        if self.is_info_v2:
            state = self._data.get("atLeastOneDoorOpen")
        else:
            state = self.lookup_enum("DoorOpenState")
        if not state:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRDOORSTATUS.get(state, None), key=state, type="DoorOpenState",
        ).value

    @property
    def smart_saving_mode(self):
        mode = self.lookup_enum(["SmartSavingMode", "smartSavingMode"])
        if not mode:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRSMARTSAVMODE.get(mode, None), key=mode, type="SmartSavingMode",
        ).value

    @property
    def smart_saving_state(self):
        state = self.lookup_enum(["SmartSavingModeStatus", "smartSavingRun"])
        if not state:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRSMARTSAVSTATUS.get(state, None), key=state, type="SmartSavingModeStatus",
        ).value

    @property
    def eco_friendly_state(self):
        state = self.lookup_enum(["EcoFriendly", "ecoFriendly"])
        if not state:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRECOSTATUS.get(state, None), key=state, type="EcoFriendly",
        ).value

    @property
    def ice_plus_status(self):
        status = self.lookup_enum(["IcePlus", "expressFridge"])
        if not status:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRICEPLUS.get(status, None), key=status, type="IcePlus",
        ).value

    @property
    def fresh_air_filter_status(self):
        status = self.lookup_enum(["FreshAirFilter", "freshAirFilter"])
        if not status:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRAIRFILTER.get(status, None), key=status, type="FreshAirFilter",
        ).value

    @property
    def water_filter_used_month(self):
        counter = None
        if self.is_info_v2:
            status = self._data.get("waterFilter")
            if status:
                counters = status.split("_", 1)
                if len(counters) > 1:
                    counter = counters[0]
        else:
            counter = self._data.get("WaterFilterUsedMonth")
        return "N/A" if not counter else counter

    @property
    def locked_state(self):
        state = self.lookup_enum("LockingStatus")
        if not state:
            return STATE_OPTIONITEM_NONE
        return self._set_unknown(
            state=REFRLOCKSTATUS.get(state, None), key=state, type="LockingStatus",
        ).value

    @property
    def active_saving_status(self):
        return self._data.get("ActiveSavingStatus", "N/A")
