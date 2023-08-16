"""------------------for Microwave"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time
from enum import Enum

from ..const import BIT_OFF, MicroWaveFeatures, StateOptions
from ..core_async import ClientAsync
from ..device import Device, DeviceStatus
from ..device_info import DeviceInfo

ITEM_STATE_OFF = "@OV_STATE_INITIAL_W"

CMD_SET_PREFERENCE = "SetPreference"
CMD_SET_VENTLAMP = "setVentLampLevel"

CMD_PREF_DICT = {
    "command": "Set",
    "ctrlKey": CMD_SET_PREFERENCE,
    "dataSetList": {
        "ovenState": {
            "cmdOptionContentsType": "REMOTE_SETTING",
            "cmdOptionDataLength": "REMOTE_SETTING",
            "mwoSettingClockDisplay": "NOT_SET",
            "mwoSettingClockSetHourMode": "NOT_SET",
            "mwoSettingClockSetTimeHour": 128,
            "mwoSettingClockSetTimeMin": 128,
            "mwoSettingClockSetTimeSec": 128,
            "mwoSettingDefrostWeightMode": "NOT_SET",
            "mwoSettingDemoMode": "NOT_SET",
            "mwoSettingDisplayScrollSpeed": "NOT_SET",
            "mwoSettingSound": "NOT_SET",
        }
    },
}

CMD_VENTLAMP_DICT = {
    "command": "Set",
    "ctrlKey": CMD_SET_VENTLAMP,
    "dataSetList": {
        "ovenState": {
            "cmdOptionContentsType": "REMOTE_VENT_LAMP",
            "cmdOptionDataLength": "REMOTE_VENT_LAMP",
        }
    },
}

MW_CMD = {
    CMD_SET_PREFERENCE: CMD_PREF_DICT,
    CMD_SET_VENTLAMP: CMD_VENTLAMP_DICT,
}


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


class WeightUnit(Enum):
    """The weight unit for a Microwave device."""

    KG = "@OV_TERM_UNIT_KG_W"
    LB = "@OV_TERM_UNIT_LBS_W"


class MicroWaveDevice(Device):
    """A higher-level interface for a cooking range."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        """Init the device."""
        super().__init__(client, device_info, MicroWaveStatus(self))
        self._supported_vent_speed_options = None
        self._supported_light_mode_options = None
        self._supported_display_scroll_speed_options = None
        self._supported_defrost_weight_unit_options = None

    def reset_status(self):
        self._status = MicroWaveStatus(self)
        return self._status

    # Settings
    def _prepare_command_ventlamp(self):
        """Prepare vent / lamp command."""
        if not self._status:
            return {}

        status_data = self._status.data
        vent_level = status_data.get("MwoVentSpeedLevel", "0")
        lamp_level = status_data.get("MwoLampLevel", "0")
        return {
            "mwoVentOnOff": "ENABLE" if vent_level != "0" else "DISABLE",
            "mwoVentSpeedLevel": int(vent_level),
            "mwoLampOnOff": "ENABLE" if lamp_level != "0" else "DISABLE",
            "mwoLampLevel": int(lamp_level),
        }

    def _prepare_command(self, ctrl_key, command, key, value):
        """
        Prepare command for specific device.
        Overwrite for specific device settings.
        """
        if (cmd_key := MW_CMD.get(ctrl_key)) is None:
            return None

        if ctrl_key == CMD_SET_VENTLAMP:
            full_cmd = self._prepare_command_ventlamp()
        else:
            full_cmd = {}

        cmd = deepcopy(cmd_key)
        def_cmd = cmd["dataSetList"].get("ovenState", {})
        cmd["dataSetList"]["ovenState"] = {**def_cmd, **full_cmd, **command}

        return cmd

    # Clock
    async def set_clock_display(self, turn_on: bool):
        """Set display clock on/off."""
        state = "CLOCK_SHOW" if turn_on else "CLOCK_HIDE"
        cmd = {"mwoSettingClockDisplay": state}
        await self.set(
            CMD_SET_PREFERENCE, cmd, key="MwoSettingClockDisplay", value=state
        )

    async def set_time(self, time_wanted: time | None = None):
        """Set time on microwave."""
        if time_wanted is None:
            time_wanted = datetime.now().time()

        cmd = {
            "mwoSettingClockSetTimeHour": time_wanted.hour,
            "mwoSettingClockSetTimeMin": time_wanted.minute,
            "mwoSettingClockSetTimeSec": time_wanted.second,
        }
        await self.set(CMD_SET_PREFERENCE, cmd)

    # Sound
    async def set_sound(self, turn_on: bool):
        """Set sound on/off."""
        state = "HIGH" if turn_on else "MUTE"
        cmd = {"mwoSettingSound": state}
        await self.set(CMD_SET_PREFERENCE, cmd, key="MwoSettingSound", value=state)

    # Unit
    @property
    def defrost_weight_unit_options(self) -> list[str]:
        """Get display scrool speed list."""
        if self._supported_defrost_weight_unit_options is None:
            key = self._get_state_key("MwoSettingDefrostWeightMode")
            if not self.model_info.is_enum_type(key):
                self._supported_defrost_weight_unit_options = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in WeightUnit]
            self._supported_defrost_weight_unit_options = [
                WeightUnit(o).name for o in mapping.values() if o in mode_list
            ]
        return self._supported_defrost_weight_unit_options

    async def set_defrost_weight_unit(self, unit: str):
        """Set weight unit kg/lb."""
        if unit not in self.defrost_weight_unit_options:
            raise ValueError(f"Invalid display unit: {unit}")
        cmd = {"mwoSettingDefrostWeightMode": unit}
        await self.set(
            CMD_SET_PREFERENCE, cmd, key="MwoSettingDefrostWeightMode", value=unit
        )

    # Display
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

    async def set_display_scroll_speed(self, speed: str):
        """Set display scrool speed."""
        if speed not in self.display_scroll_speed_options:
            raise ValueError(f"Invalid display scroll speed: {speed}")

        cmd = {"mwoSettingDisplayScrollSpeed": speed}
        await self.set(
            CMD_SET_PREFERENCE, cmd, key="MwoSettingDisplayScrollSpeed", value=speed
        )

    # Light
    @property
    def light_mode_options(self) -> list[str]:
        """Get display scrool speed list."""
        if self._supported_light_mode_options is None:
            key = self._get_state_key("MwoLampLevelString")
            if not self.model_info.is_enum_type(key):
                self._supported_light_mode_options = {}
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in LightLevel]
            self._supported_light_mode_options = {
                LightLevel(k).name: k for k in mapping.keys() if k in mode_list
            }
        return list(self._supported_light_mode_options)

    async def set_light_mode(self, mode: str):
        """Set light mode."""
        if mode not in self.light_mode_options:
            raise ValueError(f"Invalid light mode: {mode}")

        level = self._supported_light_mode_options[mode]
        status = "ENABLE" if level != "0" else "DISABLE"

        cmd = {
            "mwoLampOnOff": status,
            "mwoLampLevel": int(level),
        }

        await self.set(CMD_SET_VENTLAMP, cmd, key="MwoLampLevel", value=level)

    # Vent
    @property
    def vent_speed_options(self) -> list[str]:
        """Get vent speed list."""
        if self._supported_vent_speed_options is None:
            key = self._get_state_key("MwoVentSpeedLevelString")
            if not self.model_info.is_enum_type(key):
                self._supported_vent_speed_options = {}
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in VentSpeed]
            self._supported_vent_speed_options = {
                VentSpeed(k).name: k for k in mapping.keys() if k in mode_list
            }
        return list(self._supported_vent_speed_options)

    async def set_vent_speed(self, option: str):
        """Set vent speed."""
        if option not in self.vent_speed_options:
            raise ValueError(f"Invalid vent mode: {option}")

        level = self._supported_vent_speed_options[option]
        mode = "ENABLE" if level != "0" else "DISABLE"

        cmd = {
            "mwoVentOnOff": mode,
            "mwoVentSpeedLevel": int(level),
        }

        await self.set(CMD_SET_VENTLAMP, cmd, key="MwoVentSpeedLevel", value=level)

    async def set(
        self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None
    ):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
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
    Higher-level information about an range's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

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
        if (status := self.data.get("MwoSettingClockDisplay")) is None:
            return None
        return self._update_feature(
            MicroWaveFeatures.CLOCK_DISPLAY, status == "CLOCK_SHOW", False
        )

    @property
    def is_sound_on(self):
        """Get sound on/off."""
        if (status := self.data.get("MwoSettingSound")) is None:
            return None
        return self._update_feature(MicroWaveFeatures.SOUND, status == "HIGH", False)

    @property
    def weight_unit(self):
        """Get weight unit kg/lb."""
        if (value := self.lookup_enum("MwoSettingDefrostWeightMode")) is None:
            return None

        try:
            return self._update_feature(
                MicroWaveFeatures.WEIGHT_UNIT, WeightUnit(value).name, False
            )
        except ValueError:
            return None

    @property
    def display_scroll_speed(self):
        """Get display scrool speed."""
        if (value := self.lookup_enum("MwoSettingDisplayScrollSpeed")) is None:
            return None

        try:
            return self._update_feature(
                MicroWaveFeatures.DISPLAY_SCROLL_SPEED,
                DisplayScrollSpeed(value).name,
                False,
            )
        except ValueError:
            return None

    @property
    def light_mode(self):
        """Get light mode."""
        if (value := self.lookup_range("MwoLampLevel")) is None:
            return None

        try:
            return self._update_feature(
                MicroWaveFeatures.LIGHT_MODE, LightLevel(value).name, False
            )
        except ValueError:
            return None

    @property
    def vent_speed(self):
        """Get vent speed."""
        if (value := self.lookup_range("MwoVentSpeedLevel")) is None:
            return None

        try:
            return self._update_feature(
                MicroWaveFeatures.VENT_SPEED, VentSpeed(value).name, False
            )
        except ValueError:
            return None

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
