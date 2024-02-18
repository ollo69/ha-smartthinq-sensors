"""------------------for Hood"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum

from ..backports.functools import cached_property
from ..const import BIT_OFF, HoodFeatures, StateOptions
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

ITEM_STATE_OFF = "@OV_STATE_INITIAL_W"

STATE_LAMPLEVEL = "LampLevel"
STATE_VENTLEVEL = "VentLevel"

CMD_LAMPMODE = "lampOnOff"
CMD_LAMPLEVEL = "lampLevel"
CMD_VENTMODE = "ventOnOff"
CMD_VENTLEVEL = "ventLevel"
CMD_VENTTIMER = "ventTimer"

CMD_SET_VENTLAMP = "setCookStart"

KEY_DATASET = "dataSetList"
KEY_HOODSTATE = "hoodState"

CMD_VENTLAMP_V1_DICT = {
    "cmd": "Control",
    "cmdOpt": "Operation",
    "value": "Start",
    "data": "",
}

CMD_VENTLAMP_V2_DICT = {
    "command": "Set",
    "ctrlKey": CMD_SET_VENTLAMP,
    KEY_DATASET: {
        KEY_HOODSTATE: {
            "contentType": 22,
            "dataLength": 5,
            CMD_VENTTIMER: 0,
        }
    },
}

HOOD_CMD = {
    CMD_SET_VENTLAMP: CMD_VENTLAMP_V2_DICT,
}

MODE_ENABLE = "ENABLE"
MODE_DISABLE = "DISABLE"


class LightLevel(Enum):
    """The light level for a Hood device."""

    OFF = "0"
    LOW = "1"
    HIGH = "2"


class VentSpeed(Enum):
    """The vent speed for a Hood device."""

    OFF = "0"
    LOW = "1"
    MID = "2"
    HIGH = "3"
    TURBO = "4"
    MAX = "5"


class HoodDevice(Device):
    """A higher-level interface for a hood."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        """Init the device."""
        super().__init__(client, device_info, HoodStatus(self))

    def reset_status(self):
        self._status = HoodStatus(self)
        return self._status

    # Settings
    def _prepare_command_ventlamp_v1(self, command):
        """Prepare vent / lamp command for API V1 devices."""
        if not self._status:
            return {}

        status_data = self._status.as_dict
        if (vent_level := command.get(CMD_VENTLEVEL)) is None:
            vent_level = status_data.get(STATE_VENTLEVEL, "0")
        if (lamp_level := command.get(CMD_LAMPLEVEL)) is None:
            lamp_level = status_data.get(STATE_LAMPLEVEL, "0")
        vent_state = "01" if int(vent_level) != 0 else "00"
        lamp_state = "01" if int(lamp_level) != 0 else "00"
        data = (
            f"2205{vent_state}{int(vent_level):02d}{lamp_state}{int(lamp_level):02d}00"
        )

        return {**CMD_VENTLAMP_V1_DICT, "data": data}

    def _prepare_command_ventlamp_v2(self):
        """Prepare vent / lamp command for API V2 devices."""
        if not self._status:
            return {}

        status_data = self._status.as_dict
        vent_level = status_data.get(STATE_VENTLEVEL, "0")
        lamp_level = status_data.get(STATE_LAMPLEVEL, "0")
        return {
            CMD_VENTMODE: MODE_ENABLE if int(vent_level) != 0 else MODE_DISABLE,
            CMD_VENTLEVEL: int(vent_level),
            CMD_LAMPMODE: MODE_ENABLE if int(lamp_level) != 0 else MODE_DISABLE,
            CMD_LAMPLEVEL: int(lamp_level),
        }

    def _prepare_command_v1(self, ctrl_key, command, key, value):
        """
        Prepare command for specific API V1 device.
        Overwrite for specific device settings.
        """
        if ctrl_key == CMD_SET_VENTLAMP:
            return self._prepare_command_ventlamp_v1(command)
        return None

    def _prepare_command(self, ctrl_key, command, key, value):
        """
        Prepare command for specific device.
        Overwrite for specific device settings.
        """
        if self._should_poll:
            return self._prepare_command_v1(ctrl_key, command, key, value)

        if (cmd_key := HOOD_CMD.get(ctrl_key)) is None:
            return None

        if ctrl_key == CMD_SET_VENTLAMP:
            full_cmd = self._prepare_command_ventlamp_v2()
        else:
            full_cmd = {}

        cmd = deepcopy(cmd_key)
        def_cmd = cmd[KEY_DATASET].get(KEY_HOODSTATE, {})
        cmd[KEY_DATASET][KEY_HOODSTATE] = {**def_cmd, **full_cmd, **command}

        return cmd

    # Light
    @cached_property
    def _supported_light_modes(self) -> dict[str, str]:
        """Get display scroll speed list."""
        key = self._get_state_key(STATE_LAMPLEVEL)
        if not (mapping := self.model_info.enum_range_values(key)):
            return {}
        mode_list = [e.value for e in LightLevel]
        return {LightLevel(k).name: k for k in mapping if k in mode_list}

    @property
    def light_modes(self) -> list[str]:
        """Get display scroll speed list."""
        return list(self._supported_light_modes)

    async def set_light_mode(self, mode: str):
        """Set light mode."""
        if mode not in self.light_modes:
            raise ValueError(f"Invalid light mode: {mode}")

        level = self._supported_light_modes[mode]
        status = MODE_ENABLE if level != "0" else MODE_DISABLE
        cmd = {CMD_LAMPMODE: status, CMD_LAMPLEVEL: int(level)}

        await self.set_val(CMD_SET_VENTLAMP, cmd, key=STATE_LAMPLEVEL, value=level)

    # Vent
    @cached_property
    def _supported_vent_speeds(self) -> dict[str, str]:
        """Get vent speed."""
        key = self._get_state_key(STATE_VENTLEVEL)
        if not (mapping := self.model_info.enum_range_values(key)):
            return {}
        mode_list = [e.value for e in VentSpeed]
        return {VentSpeed(k).name: k for k in mapping if k in mode_list}

    @property
    def vent_speeds(self) -> list[str]:
        """Get vent speed list."""
        return list(self._supported_vent_speeds)

    async def set_vent_speed(self, option: str):
        """Set vent speed."""
        if option not in self.vent_speeds:
            raise ValueError(f"Invalid vent mode: {option}")

        level = self._supported_vent_speeds[option]
        mode = MODE_ENABLE if level != "0" else MODE_DISABLE
        cmd = {CMD_VENTMODE: mode, CMD_VENTLEVEL: int(level)}

        await self.set_val(CMD_SET_VENTLAMP, cmd, key=STATE_VENTLEVEL, value=level)

    async def set_val(self, ctrl_key, command, key=None, value=None):
        """Set a device's control for hood and update status."""
        await self.set(ctrl_key, command)
        if self._status and key is not None:
            self._status.update_status(key, value)

    async def poll(self) -> HoodStatus | None:
        """Poll the device's current state."""
        res = await self._device_poll()
        if not res:
            return None

        self._status = HoodStatus(self, res)
        return self._status


class HoodStatus(DeviceStatus):
    """
    Higher-level information about a hood current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    _device: HoodDevice

    @property
    def hood_state(self):
        """Return hood state."""
        status = self.lookup_enum("HoodState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(HoodFeatures.HOOD_STATE, status)

    @property
    def is_on(self):
        """Return if device is on."""
        res = self.device_features.get(HoodFeatures.HOOD_STATE)
        if res and res != StateOptions.OFF:
            return True
        return False

    @property
    def light_mode(self):
        """Get light mode."""
        if (value := self.lookup_range(STATE_LAMPLEVEL)) is None:
            return None
        try:
            status = LightLevel(value).name
        except ValueError:
            return None
        return self._update_feature(HoodFeatures.LIGHT_MODE, status, False)

    @property
    def vent_speed(self):
        """Get vent speed."""
        if (value := self.lookup_range(STATE_VENTLEVEL)) is None:
            return None
        try:
            status = VentSpeed(value).name
        except ValueError:
            return None
        return self._update_feature(HoodFeatures.VENT_SPEED, status, False)

    def _update_features(self):
        _ = [
            self.hood_state,
            self.light_mode,
            self.vent_speed,
        ]
