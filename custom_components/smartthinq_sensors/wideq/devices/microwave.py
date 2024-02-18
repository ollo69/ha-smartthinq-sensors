"""------------------for Microwave"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time
from enum import Enum

from ..backports.functools import cached_property
from ..const import BIT_OFF, MicroWaveFeatures, StateOptions
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

ITEM_STATE_OFF = "@OV_STATE_INITIAL_W"

STATE_CLOCKDISPLAY = "MwoSettingClockDisplay"
STATE_DEFROSTWMODE = "MwoSettingDefrostWeightMode"
STATE_DISPLAYSCROLL = "MwoSettingDisplayScrollSpeed"
STATE_SOUND = "MwoSettingSound"
STATE_LAMPLEVEL = "MwoLampLevel"
STATE_VENTLEVEL = "MwoVentSpeedLevel"

CMD_CLOCKDISPLAY = "mwoSettingClockDisplay"
CMD_DEFROSTWMODE = "mwoSettingDefrostWeightMode"
CMD_DISPLAYSCROLL = "mwoSettingDisplayScrollSpeed"
CMD_SOUND = "mwoSettingSound"
CMD_TIMEHOUR = "mwoSettingClockSetTimeHour"
CMD_TIMEMIN = "mwoSettingClockSetTimeMin"
CMD_TIMESEC = "mwoSettingClockSetTimeSec"

CMD_LAMPMODE = "mwoLampOnOff"
CMD_LAMPLEVEL = "mwoLampLevel"
CMD_VENTMODE = "mwoVentOnOff"
CMD_VENTLEVEL = "mwoVentSpeedLevel"

CMD_SET_PREFERENCE = "SetPreference"
CMD_SET_VENTLAMP = "setVentLampLevel"

KEY_DATASET = "dataSetList"
KEY_OVENSTATE = "ovenState"

CMD_PREF_DICT = {
    "command": "Set",
    "ctrlKey": CMD_SET_PREFERENCE,
    KEY_DATASET: {
        KEY_OVENSTATE: {
            "cmdOptionContentsType": "REMOTE_SETTING",
            "cmdOptionDataLength": "REMOTE_SETTING",
            CMD_CLOCKDISPLAY: "NOT_SET",
            "mwoSettingClockSetHourMode": "NOT_SET",
            CMD_TIMEHOUR: 128,
            CMD_TIMEMIN: 128,
            CMD_TIMESEC: 128,
            CMD_DEFROSTWMODE: "NOT_SET",
            "mwoSettingDemoMode": "NOT_SET",
            CMD_DISPLAYSCROLL: "NOT_SET",
            CMD_SOUND: "NOT_SET",
        }
    },
}

CMD_VENTLAMP_DICT = {
    "command": "Set",
    "ctrlKey": CMD_SET_VENTLAMP,
    KEY_DATASET: {
        KEY_OVENSTATE: {
            "cmdOptionContentsType": "REMOTE_VENT_LAMP",
            "cmdOptionDataLength": "REMOTE_VENT_LAMP",
        }
    },
}

MW_CMD = {
    CMD_SET_PREFERENCE: CMD_PREF_DICT,
    CMD_SET_VENTLAMP: CMD_VENTLAMP_DICT,
}

MODE_ENABLE = "ENABLE"
MODE_DISABLE = "DISABLE"

MODE_VOLON = "HIGH"
MODE_VOLOFF = "MUTE"

MODE_CLKON = "CLOCK_SHOW"
MODE_CLKOFF = "CLOCK_HIDE"


class DisplayScrollSpeed(Enum):
    """The display scroll speed for a Microwave device."""

    SLOW = "@OV_UX30_TERM_SLOW_W"
    NORMAL = "@OV_UX30_TERM_NORMAL_W"
    FAST = "@OV_UX30_TERM_FAST_W"


class LightLevel(Enum):
    """The light level for a Microwave device."""

    OFF = "0"
    LOW = "1"
    HIGH = "2"


class VentSpeed(Enum):
    """The vent speed for a Microwave device."""

    OFF = "0"
    LOW = "1"
    MID = "2"
    HIGH = "3"
    TURBO = "4"
    MAX = "5"


class WeightUnit(Enum):
    """The weight unit for a Microwave device."""

    KG = "@OV_TERM_UNIT_KG_W"
    LB = "@OV_TERM_UNIT_LBS_W"


class MicroWaveDevice(Device):
    """A higher-level interface for a microwave."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        """Init the device."""
        super().__init__(client, device_info, MicroWaveStatus(self))

    def reset_status(self):
        self._status = MicroWaveStatus(self)
        return self._status

    # Settings
    def _prepare_command_ventlamp(self):
        """Prepare vent / lamp command."""
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

    def _prepare_command(self, ctrl_key, command, key, value):
        """
        Prepare command for specific device.
        Overwrite for specific device settings.
        """
        if self._should_poll:
            raise ValueError("Control not supported for this device")

        if (cmd_key := MW_CMD.get(ctrl_key)) is None:
            return None

        if ctrl_key == CMD_SET_VENTLAMP:
            full_cmd = self._prepare_command_ventlamp()
        else:
            full_cmd = {}

        cmd = deepcopy(cmd_key)
        def_cmd = cmd[KEY_DATASET].get(KEY_OVENSTATE, {})
        cmd[KEY_DATASET][KEY_OVENSTATE] = {**def_cmd, **full_cmd, **command}

        return cmd

    # Clock
    async def set_clock_display(self, turn_on: bool):
        """Set display clock on/off."""
        state = MODE_CLKON if turn_on else MODE_CLKOFF
        cmd = {CMD_CLOCKDISPLAY: state}
        await self.set_val(CMD_SET_PREFERENCE, cmd, key=STATE_CLOCKDISPLAY, value=state)

    async def set_time(self, time_wanted: time | None = None):
        """Set time on microwave."""
        if time_wanted is None:
            time_wanted = datetime.now().time()

        cmd = {
            CMD_TIMEHOUR: time_wanted.hour,
            CMD_TIMEMIN: time_wanted.minute,
            CMD_TIMESEC: time_wanted.second,
        }
        await self.set_val(CMD_SET_PREFERENCE, cmd)

    # Sound
    async def set_sound(self, turn_on: bool):
        """Set sound on/off."""
        state = MODE_VOLON if turn_on else MODE_VOLOFF
        cmd = {CMD_SOUND: state}
        await self.set_val(CMD_SET_PREFERENCE, cmd, key=STATE_SOUND, value=state)

    # Unit
    @cached_property
    def defrost_weight_units(self) -> list[str]:
        """Get display scroll speed list."""
        return self._get_property_values(STATE_DEFROSTWMODE, WeightUnit)

    async def set_defrost_weight_unit(self, unit: str):
        """Set weight unit kg/lb."""
        if unit not in self.defrost_weight_units:
            raise ValueError(f"Invalid display unit: {unit}")
        cmd = {CMD_DEFROSTWMODE: unit}
        await self.set_val(CMD_SET_PREFERENCE, cmd, key=STATE_DEFROSTWMODE, value=unit)

    # Display
    @cached_property
    def display_scroll_speeds(self) -> list[str]:
        """Get display scroll speed list."""
        return self._get_property_values(STATE_DISPLAYSCROLL, DisplayScrollSpeed)

    async def set_display_scroll_speed(self, speed: str):
        """Set display scroll speed."""
        if speed not in self.display_scroll_speeds:
            raise ValueError(f"Invalid display scroll speed: {speed}")

        cmd = {CMD_DISPLAYSCROLL: speed}
        await self.set_val(
            CMD_SET_PREFERENCE, cmd, key=STATE_DISPLAYSCROLL, value=speed
        )

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
        """Set a device's control for microwave and update status."""
        await self.set(ctrl_key, command)
        if self._status and key is not None:
            self._status.update_status(key, value)

    async def poll(self) -> MicroWaveStatus | None:
        """Poll the device's current state."""
        res = await self._device_poll()
        if not res:
            return None

        self._status = MicroWaveStatus(self, res)
        return self._status


class MicroWaveStatus(DeviceStatus):
    """
    Higher-level information about a microwave current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    _device: MicroWaveDevice

    def __init__(self, device: MicroWaveDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._oven_temp_unit = None

    @property
    def oven_upper_state(self):
        """Return upper microwave oven state."""
        # Known microwave models only have upper oven state information
        status = self.lookup_enum("UpperOvenState")
        if status is None:
            return None
        if status == ITEM_STATE_OFF:
            status = BIT_OFF
        return self._update_feature(MicroWaveFeatures.OVEN_UPPER_STATE, status)

    @property
    def oven_upper_mode(self):
        """Return upper microwave oven mode."""
        # Known microwave models only have upper oven state information
        status = self.lookup_enum("UpperCookMode")
        if status is None:
            return None
        return self._update_feature(MicroWaveFeatures.OVEN_UPPER_MODE, status)

    @property
    def is_on(self):
        """Return if device is on."""
        return self.is_oven_on

    @property
    def is_oven_on(self):
        """Return if oven is on."""
        for feature in [
            MicroWaveFeatures.OVEN_UPPER_STATE,
        ]:
            res = self.device_features.get(feature)
            if res and res != StateOptions.OFF:
                return True
        return False

    @property
    def is_clock_display_on(self):
        """Get display clock on/off."""
        if (status := self._data.get(STATE_CLOCKDISPLAY)) is None:
            return None
        return self._update_feature(
            MicroWaveFeatures.CLOCK_DISPLAY, status == MODE_CLKON, False
        )

    @property
    def is_sound_on(self):
        """Get sound on/off."""
        if (status := self._data.get(STATE_SOUND)) is None:
            return None
        return self._update_feature(
            MicroWaveFeatures.SOUND, status == MODE_VOLON, False
        )

    @property
    def weight_unit(self):
        """Get weight unit kg/lb."""
        if (value := self.lookup_enum(STATE_DEFROSTWMODE)) is None:
            return None
        try:
            status = WeightUnit(value).name
        except ValueError:
            return None
        return self._update_feature(MicroWaveFeatures.WEIGHT_UNIT, status, False)

    @property
    def display_scroll_speed(self):
        """Get display scroll speed."""
        if (value := self.lookup_enum(STATE_DISPLAYSCROLL)) is None:
            return None
        try:
            status = DisplayScrollSpeed(value).name
        except ValueError:
            return None
        return self._update_feature(
            MicroWaveFeatures.DISPLAY_SCROLL_SPEED, status, False
        )

    @property
    def light_mode(self):
        """Get light mode."""
        if (value := self.lookup_range(STATE_LAMPLEVEL)) is None:
            return None
        try:
            status = LightLevel(value).name
        except ValueError:
            return None
        return self._update_feature(MicroWaveFeatures.LIGHT_MODE, status, False)

    @property
    def vent_speed(self):
        """Get vent speed."""
        if (value := self.lookup_range(STATE_VENTLEVEL)) is None:
            return None
        try:
            status = VentSpeed(value).name
        except ValueError:
            return None
        return self._update_feature(MicroWaveFeatures.VENT_SPEED, status, False)

    def _update_features(self):
        _ = [
            self.oven_upper_state,
            self.oven_upper_mode,
            self.is_clock_display_on,
            self.is_sound_on,
            self.weight_unit,
            self.display_scroll_speed,
            self.light_mode,
            self.vent_speed,
        ]
