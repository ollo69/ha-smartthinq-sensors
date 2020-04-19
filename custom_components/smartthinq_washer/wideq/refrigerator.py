"""------------------for Refrigerator"""
import logging
from typing import Optional

from .device import (
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

    def poll(self) -> Optional["RefrigeratorStatus"]:
        """Poll the device's current state."""

        res = self.device_poll("washerDryer")
        if not res:
            return None

        return RefrigeratorStatus(self, res)


class RefrigeratorStatus(DeviceStatus):
    """Higher-level information about a refrigerator's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """
    def __init__(self, device, data):
        super().__init__(device, data)

    @property
    def is_on(self):
        return True

    @property
    def temp_refrigerator_c(self):
        temp = self.lookup_enum("TempRefrigerator")
        return temp

    @property
    def temp_freezer_c(self):
        temp = self.lookup_enum("TempFreezer")
        return temp

    @property
    def temp_unit(self):
        temp_unit = self.lookup_enum("TempUnit")
        return self._set_unknown(
            state=REFRTEMPUNIT.get(temp_unit, None), key=temp_unit, type="TempUnit",
        ).value

    @property
    def ice_plus_status(self):
        status = self.lookup_enum("IcePlus")
        return self._set_unknown(
            state=REFRICEPLUS.get(status, None), key=status, type="IcePlus",
        ).value

    @property
    def fresh_air_filter_status(self):
        status = self.lookup_enum("FreshAirFilter")
        return self._set_unknown(
            state=REFRAIRFILTER.get(status, None), key=status, type="FreshAirFilter",
        ).value

    @property
    def energy_saving_mode(self):
        mode = self.lookup_enum("SmartSavingMode")
        return self._set_unknown(
            state=REFRSMARTSAVMODE.get(mode, None), key=mode, type="SmartSavingMode",
        ).value

    @property
    def energy_saving_state(self):
        mode = self.lookup_enum("SmartSavingModeStatus")
        return self._set_unknown(
            state=REFRSMARTSAVSTATUS.get(mode, None), key=mode, type="SmartSavingModeStatus",
        ).value

    @property
    def door_opened_state(self):
        state = self.lookup_enum("DoorOpenState")
        return self._set_unknown(
            state=REFRDOORSTATUS.get(state, None), key=state, type="DoorOpenState",
        ).value

    @property
    def locked_state(self):
        state = self.lookup_enum("LockingStatus")
        return self._set_unknown(
            state=REFRLOCKSTATUS.get(state, None), key=state, type="LockingStatus",
        ).value

    @property
    def eco_enabled_state(self):
        state = self.lookup_enum("EcoFriendly")
        return self._set_unknown(
            state=REFRECOSTATUS.get(state, None), key=state, type="EcoFriendly",
        ).value

    @property
    def active_saving_status(self):
        return self._data.get("ActiveSavingStatus", "N/A")

    @property
    def water_filter_used_month(self):
        return self._data.get("WaterFilterUsedMonth", "N/A")
