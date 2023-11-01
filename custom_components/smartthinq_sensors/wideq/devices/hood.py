"""------------------for Hood"""
from __future__ import annotations

from copy import deepcopy
from enum import Enum
from functools import cached_property

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

CMD_SET_VENTLAMP = "setCookStart"

KEY_DATASET = "dataSetList"
KEY_HOODSTATE = "hoodState"

CMD_VENTLAMP_DICT = {
    "command": "Set",
    "ctrlKey": CMD_SET_VENTLAMP,
    KEY_DATASET: {KEY_HOODSTATE: {}},
}

HOOD_CMD = {
    CMD_SET_VENTLAMP: CMD_VENTLAMP_DICT,
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
    def _prepare_command_ventlamp(self):
        """Prepare vent / lamp command."""
        if not self._status:
            return {}

        status_data = self._status.data
        vent_level = status_data.get(STATE_VENTLEVEL, "0")
        lamp_level = status_data.get(STATE_LAMPLEVEL, "0")
        return {
            CMD_VENTMODE: MODE_ENABLE if vent_level != "0" else MODE_DISABLE,
            CMD_VENTLEVEL: int(vent_level),
            CMD_LAMPMODE: MODE_ENABLE if lamp_level != "0" else MODE_DISABLE,
            CMD_LAMPLEVEL: int(lamp_level),
        }

    def _prepare_command(self, ctrl_key, command, key, value):
        """
        Prepare command for specific device.
        Overwrite for specific device settings.
        """
        if (cmd_key := HOOD_CMD.get(ctrl_key)) is None:
            return None

        if ctrl_key == CMD_SET_VENTLAMP:
            full_cmd = self._prepare_command_ventlamp()
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

        await self.set(CMD_SET_VENTLAMP, cmd, key=STATE_LAMPLEVEL, value=level)

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

        await self.set(CMD_SET_VENTLAMP, cmd, key=STATE_VENTLEVEL, value=level)

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
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
