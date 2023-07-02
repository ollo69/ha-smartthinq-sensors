"""------------------for Microwave"""
from __future__ import annotations
from enum import Enum

import datetime

from ..const import BIT_OFF, MicroWaveFeatures, StateOptions, TemperatureUnit
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

CMD_PREF_DICT = {
    "command": "Set",
    "ctrlKey": "SetPreference",
    "dataSetList": {
        "ovenState": {
            "cmdOptionContentsType": "REMOTE_SETTING",
            "cmdOptionDataLength": "REMOTE_SETTING",
        }
    }
}

CMD_VENTLAMP_DICT = {
    "command": "Set",
    "ctrlKey": "setVentLampLevel",
    "dataSetList": {
        "ovenState": {
            "cmdOptionContentsType": "REMOTE_VENT_LAMP",
            "cmdOptionDataLength": "REMOTE_VENT_LAMP",
        }
    }
}


class DisplayScrollSpeed(Enum):
    """The display scroll speed for a Microwave device."""

    SLOW = '@OV_UX30_TERM_SLOW_W'
    NORMAL = '@OV_UX30_TERM_NORMAL_W'
    FAST = '@OV_UX30_TERM_FAST_W'


class Sound(Enum):
    """Whether the sound is on or off."""

    HIGH = "@CP_ON_EN_W",
    MUTE = "@CP_OFF_EN_W"


class LightOnOff(Enum):
    """The light running state for a Microwave device."""

    DISABLE = '@CP_DISABLE_W'
    ENABLE = '@CP_ENABLE_W'


class LightLevel(Enum):
    """The light level for a Microwave device."""

    OFF = '@CP_OFF_EN_W'
    LOW = '@OV_TERM_LOW_W'
    HIGH = '@OV_TERM_HIGH_W'


class VentOnOff(Enum):
    """The vent running state for a Microwave device."""

    DISABLE = '@CP_DISABLE_W'
    ENABLE = '@CP_ENABLE_W'


class VentSpeed(Enum):
    """The vent speed for a Microwave device."""

    OFF = "@CP_OFF_EN_W"
    LOW = "@OV_TERM_LOW_W"
    MID = "@OV_TERM_MID_W"
    HIGH = "@OV_TERM_HIGH_W"
    TURBO = "@OV_TERM_TURBO_W"


class MicroWaveDevice(Device):
    """A higher-level interface for a cooking range."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        super().__init__(client, device_info, MicroWaveStatus(self))
        self._supported_vent_speed_options = None
        self._supported_display_scroll_speed_options = None

    def reset_status(self):
        self._status = MicroWaveStatus(self)
        return self._status


    # Settings

    # Clock
    async def set_clock_display(self, turn_on: bool):
        """Set display clock on/off."""
        if turn_on:
            state = "CLOCK_SHOW"
        else:
            state = "CLOCK_HIDE"
        cmd = CMD_PREF_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoSettingClockDisplay"] = state
        cmd["dataSetList"]["ovenState"]["mwoSettingClockSetHourMode"] = self._status.clock_24hmode
        await self.set(cmd, None, key="MwoSettingClockDisplay", value = str(state))

    @property
    def clock_display_state(self) -> bool:
        """Get display clock on/off."""
        state = self._status.data.get("MwoSettingClockDisplay")
        if state == "CLOCK_SHOW":
            return True
        elif state == "CLOCK_HIDE":
            return False
        raise

    async def set_time(self, time_wanted: datetime.time|None=None):
        """Set time on microwave."""
        if time_wanted is None:
            time_wanted = datetime.datetime.now().time()

        cmd = CMD_PREF_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoSettingClockSetTimeHour"] =  time_wanted.hour
        cmd["dataSetList"]["ovenState"]["mwoSettingClockSetTimeMin"] = time_wanted.minute

        await self.set(cmd, None)

    # Unit
    async def set_weight_unit_kg(self, turn_on: bool):
        """Set weight unit kg/lb."""
        if turn_on:
            state = "KG"
        else:
            state = "LB"
        cmd = CMD_PREF_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoSettingDefrostWeightMode"] = state
        cmd["dataSetList"]["ovenState"]["mwoSettingClockSetHourMode"] = self._status.clock_24hmode

        await self.set(cmd, None, key="MwoSettingDefrostWeightMode", value = state)

    @property
    def weight_unit_kg_state(self) -> bool:
        """Get weight unit kg/lb."""
        state = self._status.data.get("MwoSettingDefrostWeightMode")
        if state == "KG":
            return True
        return False

    async def set_display_scroll_speed(self, option: str):
        """Set display scrool speed."""
        if option not in ["SLOW", "NORMAL", "FAST"]:
            raise

        cmd = CMD_PREF_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoSettingDisplayScrollSpeed"] = option
        cmd["dataSetList"]["ovenState"]["mwoSettingClockSetHourMode"] = self._status.clock_24hmode

        await self.set(cmd, None, key="MwoSettingDisplayScrollSpeed", value = option)


    @property
    def display_scroll_speed_state(self) -> str:
        """Get display scrool speed."""
        state = self._status.data.get("MwoSettingDisplayScrollSpeed")
        return state

    @property
    def display_scroll_speed_options(self) -> list[str]:
        """Get display scrool speed list."""
        if self._supported_display_scroll_speed_options is None:
            key = self._get_state_key("MwoSettingDisplayScrollSpeed")
            if not self.model_info.is_enum_type(key):
                self._supported_display_scroll_speed_options = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in DisplayScrollSpeed]
            self._supported_display_scroll_speed_options = [
                DisplayScrollSpeed(o).name for o in mapping.values() if o in mode_list
            ]
        return self._supported_display_scroll_speed_options

    # Sound
    async def set_sound(self, turn_on: bool):
        """Set sound on/off."""
        state = "MUTE"
        if turn_on:
            state = "HIGH"
        cmd = CMD_PREF_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoSettingSound"] = state
        cmd["dataSetList"]["ovenState"]["mwoSettingClockSetHourMode"] = self._status.clock_24hmode

        await self.set(cmd, None, key="MwoSettingSound", value = state)

    @property
    def sound_state(self) -> bool:
        """Get sound on/off."""
        state = self._status.sound

        if state == "HIGH":
            return True
        return False

    # Light
    async def light_turn_onoff(self, on: bool, **kwargs):
        """Set light on/off."""
        if on:
            state = "ENABLE"
        else:
            state = "DISABLE"
        cmd = CMD_VENTLAMP_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoLampOnOff"] = state
        # Get brightness wanted
        brightness = kwargs.get("brightness")
        mwoLampLevel = 0
        # if ON and no brightness set, let's turn on the light
        # with max brightness
        if on and brightness is None:
            brightness = 255

        if brightness:
            if 1 < brightness < 170:
                # Set brightness to level 1
                mwoLampLevel = 1
            elif brightness >= 170:
                # Set brightness to level 2
                mwoLampLevel = 2
            # Set brightness
            cmd["dataSetList"]["ovenState"]["mwoLampLevel"] = mwoLampLevel

        await self.set(cmd, None, key="MwoLampLevel", value = str(mwoLampLevel))

    @property
    def light_is_on(self) -> bool:
        """Get light on/off state."""
        if self._status.data["MwoLampLevel"] == '0':
            return False
        return True

    @property
    def light_brightness(self) -> int:
        """Get light brightness."""
        mwoLampLevel = self._status.data["MwoLampLevel"]
        if mwoLampLevel == '0' :
            return 0
        elif mwoLampLevel == '1':
            return 127
        elif mwoLampLevel == '2':
            return 255
        raise


    # Vent
    async def set_vent_speed(self, option: str):
        """Set vent speed."""
        if option not in self.vent_speed_options:
            raise
        on_off = self.model_info.enum_value("MwoVentOnOff", getattr(VentOnOff, "ENABLE").value)
        if option == "OFF":
            on_off = self.model_info.enum_value("MwoVentOnOff", getattr(VentOnOff, "DISABLE").value)
        speed_str = self.model_info.enum_value("MwoVentSpeedLevelString", getattr(VentSpeed, option).value)

        cmd = CMD_VENTLAMP_DICT.copy()
        cmd["dataSetList"]["ovenState"]["mwoVentOnOff"] = on_off
        cmd["dataSetList"]["ovenState"]["mwoVentSpeedLevel"] = int(speed_str)

        await self.set(cmd, None, key="MwoVentSpeedLevel", value = option)

    @property
    def vent_speed_state(self) -> str:
        """Get vent speed."""
        state = self._status.vent_speed
        return state.upper()

    @property
    def vent_speed_options(self) -> list[str]:
        """Get vent speed list."""
        if self._supported_vent_speed_options is None:
            key = self._get_state_key("MwoVentSpeedLevelString")
            if not self.model_info.is_enum_type(key):
                self._supported_vent_speed_options = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in VentSpeed]
            self._supported_vent_speed_options = [
                VentSpeed(o).name for o in mapping.values() if o in mode_list
            ]
        return self._supported_vent_speed_options

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if self._status:
            self._status.update_status(key, value)

    async def poll(self) -> MicroWaveStatus | None:
        """Poll the device's current state."""
        res = await self._device_poll()
        if not res:
            return None

        for key, value in res.items():
            status_res = self._status.update_status(key, value)
            if not status_res:
                self._status = MicroWaveStatus(self, res)
                return self._status
        return self._status


class MicroWaveStatus(DeviceStatus):
    """
    Higher-level information about an range's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    def __init__(self, device: MicroWaveDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._oven_temp_unit = None

    @property
    def is_on(self):
        """Return if device is on."""
        return self.is_oven_on

    @property
    def is_oven_on(self):
        """Return if oven is on."""
        # FIXME: detect the microwave is online
        self.data.get('UpperOvenState')
        self.data.get('StandBy')
        return True

    # FIXME add timer and cook status

    @property
    def clock_display(self):
        """Get display clock on/off."""
        status = self.data.get("MwoSettingClockDisplay")
        return self._update_feature(MicroWaveFeatures.CLOCK_DISPLAY, status)

    @property
    def weight_unit_kg(self):
        """Get weight unit kg/lb."""
        status = self.data.get("MwoSettingDefrostWeightMode")
        return self._update_feature(MicroWaveFeatures.WEIGHT_UNIT_KG, status)

    @property
    def display_scroll_speed(self):
        """Get display scrool speed."""
        status = self.data.get("mwoSettingDisplayScrollSpeed")
        return self._update_feature(MicroWaveFeatures.DISPLAY_SCROLL_SPEED, status)

    @property
    def sound(self):
        """Get sound on/off."""
        status = self.data.get('MwoSettingSound')
        return self._update_feature(MicroWaveFeatures.SOUND, status)

    @property
    def light(self):
        """Get light on/off."""
        status = self.lookup_range("MwoLampLevel")
        return self._update_feature(MicroWaveFeatures.LIGHT, status)

    @property
    def vent_speed(self):
        """Get vent speed."""
        raw_value = self.lookup_range("MwoVentSpeedLevel")

        if hasattr(VentSpeed, raw_value):
            value = VentSpeed[raw_value].value
        else:
            value = self._device.model_info.enum_name("MwoVentSpeedLevelString", raw_value)

        if value is None:
            return None
        try:
            return self._update_feature(MicroWaveFeatures.VENT_SPEED, VentSpeed(value).name)
        except ValueError:
            return None

    def _update_features(self):
        _ = [
            self.light,
            self.clock_display,
            self.weight_unit_kg,
            self.display_scroll_speed,
            self.sound,
        ]
