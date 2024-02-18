"""------------------for Refrigerator"""

from __future__ import annotations

import base64
import json
import logging

from ..const import RefrigeratorFeatures, StateOptions, TemperatureUnit
from ..core_async import ClientAsync
from ..device import LABEL_BIT_OFF, LABEL_BIT_ON, Device, DeviceStatus
from ..device_info import DeviceInfo
from ..model_info import TYPE_ENUM

FEATURE_DESCR = {
    "@RE_TERM_EXPRESS_FREEZE_W": "express_freeze",
    "@RE_TERM_EXPRESS_FRIDGE_W": "express_cool",
    "@RE_TERM_ICE_PLUS_W": "ice_plus",
}

REFRTEMPUNIT = {
    "Ｆ": TemperatureUnit.FAHRENHEIT,
    "℃": TemperatureUnit.CELSIUS,
    "˚F": TemperatureUnit.FAHRENHEIT,
    "˚C": TemperatureUnit.CELSIUS,
}

# REFRTEMPUNIT = {
#     "\uff26": TemperatureUnit.FAHRENHEIT,
#     "\u2103": TemperatureUnit.CELSIUS,
#     "\u02daF": TemperatureUnit.FAHRENHEIT,
#     "\u02daC": TemperatureUnit.CELSIUS,
# }

DEFAULT_FRIDGE_RANGE_C = [1, 10]
DEFAULT_FRIDGE_RANGE_F = [30, 45]
DEFAULT_FREEZER_RANGE_C = [-24, -14]
DEFAULT_FREEZER_RANGE_F = [-8, 6]

REFR_ROOT_DATA = "refState"
CTRL_BASIC = ["Control", "basicCtrl"]

STATE_ECO_FRIENDLY = ["EcoFriendly", "ecoFriendly"]
STATE_ICE_PLUS = ["IcePlus", ""]
STATE_EXPRESS_FRIDGE = ["", "expressFridge"]
STATE_EXPRESS_MODE = ["", "expressMode"]
STATE_FRIDGE_TEMP = ["TempRefrigerator", "fridgeTemp"]
STATE_FREEZER_TEMP = ["TempFreezer", "freezerTemp"]

CMD_STATE_ECO_FRIENDLY = [CTRL_BASIC, ["SetControl", "basicCtrl"], STATE_ECO_FRIENDLY]
CMD_STATE_ICE_PLUS = [CTRL_BASIC, ["SetControl", "basicCtrl"], STATE_ICE_PLUS]
CMD_STATE_EXPRESS_FRIDGE = [
    CTRL_BASIC,
    ["SetControl", "basicCtrl"],
    STATE_EXPRESS_FRIDGE,
]
CMD_STATE_EXPRESS_MODE = [CTRL_BASIC, ["SetControl", "basicCtrl"], STATE_EXPRESS_MODE]
CMD_STATE_FRIDGE_TEMP = [CTRL_BASIC, ["SetControl", "basicCtrl"], STATE_FRIDGE_TEMP]
CMD_STATE_FREEZER_TEMP = [CTRL_BASIC, ["SetControl", "basicCtrl"], STATE_FREEZER_TEMP]

_LOGGER = logging.getLogger(__name__)


class RefrigeratorDevice(Device):
    """A higher-level interface for a refrigerator."""

    def __init__(self, client: ClientAsync, device_info: DeviceInfo):
        super().__init__(client, device_info, RefrigeratorStatus(self))
        self._temp_unit = None
        self._fridge_temps = None
        self._fridge_ranges = None
        self._freezer_temps = None
        self._freezer_ranges = None

    def _get_feature_info(self, item_key):
        config = self.model_info.config_value("visibleItems")
        if not config or not isinstance(config, list):
            return None
        if self.model_info.is_info_v2:
            feature_key = "feature"
        else:
            feature_key = "Feature"
        for item in config:
            feature_value = item.get(feature_key, "")
            if feature_value and feature_value == item_key:
                return item
        return None

    def _get_feature_title(self, feature_name, item_key):
        item_info = self._get_feature_info(item_key)
        if not item_info:
            return None
        if self.model_info.is_info_v2:
            title_key = "monTitle"
        else:
            title_key = "Title"
        title_value = item_info.get(title_key)
        if not title_value:
            return feature_name
        return FEATURE_DESCR.get(title_value, feature_name)

    def _prepare_command_v1(self, cmd, key, value):
        """Prepare command for specific ThinQ1 device."""
        data_key = "value"
        if cmd.get(data_key, "") == "ControlData":
            data_key = "data"
        str_data = cmd.get(data_key)

        if str_data:
            status_data = self._status.as_dict
            for dt_key, dt_value in status_data.items():
                if dt_key == key:
                    dt_value = value
                str_data = str_data.replace(f"{{{{{dt_key}}}}}", dt_value)

            json_data = json.loads(str_data)
            _LOGGER.debug("Command data content: %s", str(json_data))
            if self.model_info.binary_control_data:
                cmd["format"] = "B64"
                json_data = base64.b64encode(bytes(json_data)).decode("ascii")
            cmd[data_key] = json_data

        return cmd

    def _prepare_command_v2(self, cmd, key, value):
        """Prepare command for specific ThinQ2 device."""
        data_set = cmd.pop("data", None)
        if not data_set:
            data_set = {REFR_ROOT_DATA: {key: value}}
        else:
            for cmd_key in data_set[REFR_ROOT_DATA].keys():
                data_set[REFR_ROOT_DATA][cmd_key] = (
                    value if cmd_key == key else "IGNORE"
                )
        cmd["dataSetList"] = data_set

        return cmd

    def _prepare_command(self, ctrl_key, command, key, value):
        """Prepare command for specific device."""
        cmd = self.model_info.get_control_cmd(command, ctrl_key)
        if not cmd:
            return None

        if self.model_info.is_info_v2:
            return self._prepare_command_v2(cmd, key, value)
        return self._prepare_command_v1(cmd, key, value)

    def _set_temp_unit(self, unit=None):
        """Set the configured temperature unit."""
        if unit and unit != StateOptions.NONE:
            if not self._temp_unit or unit != self._temp_unit:
                self._temp_unit = unit
                self._fridge_temps = None
                self._freezer_temps = None

    def _get_temp_unit(self, unit=None):
        """Get the configured temperature unit."""
        if unit:
            self._set_temp_unit(unit)
        return self._temp_unit

    def _get_temps_v1(self, key):
        """Get valid values for temps for V1 models"""
        unit = self._get_temp_unit()
        if unit:
            unit_key = "_F" if unit == TemperatureUnit.FAHRENHEIT else "_C"
            if self.model_info.value_exist(key + unit_key):
                key = key + unit_key
        value_type = self.model_info.value_type(key)
        if not value_type or value_type != TYPE_ENUM:
            return {}
        temp_values = self.model_info.value(key).options
        return {k: v for k, v in temp_values.items() if v != ""}

    def _get_temps_v2(self, key, unit_key=None):
        """Get valid values for temps for V2 models"""
        if unit_key:
            if ref_key := self.model_info.target_key(key, unit_key, "tempUnit"):
                key = ref_key
        value_type = self.model_info.value_type(key)
        if not value_type or value_type != TYPE_ENUM:
            return {}
        temp_values = self.model_info.value(key).options
        return {k: v for k, v in temp_values.items() if v != "IGNORE"}

    @staticmethod
    def _get_temp_ranges(temps):
        """Get min and max values inside a dict."""
        min_val = 100
        max_val = -100
        for value in temps.values():
            try:
                int_val = int(value)
            except ValueError:
                continue
            if int_val < min_val:
                min_val = int_val
            if int_val > max_val:
                max_val = int_val
        if min_val > max_val:
            return None
        return [min_val, max_val]

    @staticmethod
    def _get_temp_key(temps, value):
        """Get temp_key based on his value."""
        if not temps:
            return None

        str_val = str(int(value))
        for key, temp_val in temps.items():
            if str_val == temp_val:
                try:
                    return int(key)
                except ValueError:
                    return None
        return None

    def get_fridge_temps(self, unit=None, unit_key=None):
        """Get valid values for fridge temp."""
        self._set_temp_unit(unit)
        if self._fridge_temps is None:
            key = self._get_state_key(STATE_FRIDGE_TEMP)
            if self.model_info.is_info_v2:
                self._fridge_temps = self._get_temps_v2(key, unit_key)
            else:
                self._fridge_temps = self._get_temps_v1(key)
            self._fridge_ranges = self._get_temp_ranges(self._fridge_temps)
        return self._fridge_temps

    def get_freezer_temps(self, unit=None, unit_key=None):
        """Get valid values for freezer temp."""
        self._set_temp_unit(unit)
        if self._freezer_temps is None:
            key = self._get_state_key(STATE_FREEZER_TEMP)
            if self.model_info.is_info_v2:
                self._freezer_temps = self._get_temps_v2(key, unit_key)
            else:
                self._freezer_temps = self._get_temps_v1(key)
            self._freezer_ranges = self._get_temp_ranges(self._freezer_temps)
        return self._freezer_temps

    @property
    def target_temperature_step(self):
        """Return target temperature step used."""
        return 1

    @property
    def fridge_target_temp_range(self):
        """Return range value for fridge target temperature."""
        if self._fridge_ranges is None:
            unit = self._get_temp_unit() or StateOptions.NONE
            if unit == TemperatureUnit.FAHRENHEIT:
                return DEFAULT_FRIDGE_RANGE_F
            return DEFAULT_FRIDGE_RANGE_C
        return self._fridge_ranges

    @property
    def freezer_target_temp_range(self):
        """Return range value for freezer target temperature."""
        if self._freezer_ranges is None:
            unit = self._get_temp_unit() or StateOptions.NONE
            if unit == TemperatureUnit.FAHRENHEIT:
                return DEFAULT_FREEZER_RANGE_F
            return DEFAULT_FREEZER_RANGE_C
        return self._freezer_ranges

    @property
    def set_values_allowed(self):
        """Check if values can be changed."""
        if (
            not self._status
            or not self._status.is_on
            or self._status.eco_friendly_enabled
        ):
            return False
        return True

    async def _set_feature(self, turn_on: bool, state_key, cmd_key):
        """Switch a feature."""

        status_key = self._get_state_key(state_key)
        if not status_key:
            return
        status_name = LABEL_BIT_ON if turn_on else LABEL_BIT_OFF
        status_value = self.model_info.enum_value(status_key, status_name)
        if not status_value:
            return
        keys = self._get_cmd_keys(cmd_key)
        await self.set(keys[0], keys[1], key=keys[2], value=status_value)
        self._status.update_status_feat(status_key, status_value, True)

    async def set_eco_friendly(self, turn_on=False):
        """Switch the echo friendly status."""
        await self._set_feature(turn_on, STATE_ECO_FRIENDLY, CMD_STATE_ECO_FRIENDLY)

    async def set_ice_plus(self, turn_on=False):
        """Switch the ice plus status."""
        if self.model_info.is_info_v2:
            return
        if not self.set_values_allowed:
            return
        await self._set_feature(turn_on, STATE_ICE_PLUS, CMD_STATE_ICE_PLUS)

    async def set_express_fridge(self, turn_on=False):
        """Switch the express fridge status."""
        if not self.model_info.is_info_v2:
            return
        if not self.set_values_allowed:
            return
        await self._set_feature(turn_on, STATE_EXPRESS_FRIDGE, CMD_STATE_EXPRESS_FRIDGE)

    async def set_express_mode(self, turn_on=False):
        """Switch the express mode status."""
        if not self.model_info.is_info_v2:
            return
        if not self.set_values_allowed:
            return
        await self._set_feature(turn_on, STATE_EXPRESS_MODE, CMD_STATE_EXPRESS_MODE)

    async def set_fridge_target_temp(self, temp):
        """Set the fridge target temperature."""
        if not self.set_values_allowed:
            return
        if self._status.temp_fridge is None:
            return

        if (temp_key := self._get_temp_key(self._fridge_temps, temp)) is None:
            raise ValueError(f"Target fridge temperature not valid: {temp}")
        if not self.model_info.is_info_v2:
            temp_key = str(temp_key)

        status_key = self._get_state_key(STATE_FRIDGE_TEMP)
        keys = self._get_cmd_keys(CMD_STATE_FRIDGE_TEMP)
        await self.set(keys[0], keys[1], key=keys[2], value=temp_key)
        self._status.update_status_feat(status_key, temp_key, False)

    async def set_freezer_target_temp(self, temp):
        """Set the freezer target temperature."""
        if not self.set_values_allowed:
            return
        if self._status.temp_freezer is None:
            return

        if (temp_key := self._get_temp_key(self._freezer_temps, temp)) is None:
            raise ValueError(f"Target freezer temperature not valid: {temp}")
        if not self.model_info.is_info_v2:
            temp_key = str(temp_key)

        status_key = self._get_state_key(STATE_FREEZER_TEMP)
        keys = self._get_cmd_keys(CMD_STATE_FREEZER_TEMP)
        await self.set(keys[0], keys[1], key=keys[2], value=temp_key)
        self._status.update_status_feat(status_key, temp_key, False)

    def reset_status(self):
        self._status = RefrigeratorStatus(self)
        return self._status

    async def poll(self) -> RefrigeratorStatus | None:
        """Poll the device's current state."""

        res = await self._device_poll(REFR_ROOT_DATA)
        if not res:
            return None

        self._status = RefrigeratorStatus(self, res)
        return self._status


class RefrigeratorStatus(DeviceStatus):
    """
    Higher-level information about a refrigerator's current status.

    :param device: The Device instance.
    :param data: JSON data from the API.
    """

    _device: RefrigeratorDevice

    def __init__(self, device: RefrigeratorDevice, data: dict | None = None):
        """Initialize device status."""
        super().__init__(device, data)
        self._temp_unit = None
        self._eco_friendly_state = None
        self._sabbath_state = None

    def _get_eco_friendly_state(self):
        """Get current eco-friendly state."""
        if self._eco_friendly_state is None:
            state = self.lookup_enum(STATE_ECO_FRIENDLY)
            if not state:
                self._eco_friendly_state = ""
            else:
                self._eco_friendly_state = state
        return self._eco_friendly_state

    def _get_sabbath_state(self):
        """Get current sabbath-mode state."""
        if self._sabbath_state is None:
            state = self.lookup_enum(["Sabbath", "sabbathMode"])
            if not state:
                self._sabbath_state = ""
            else:
                self._sabbath_state = state
        return self._sabbath_state

    def _get_default_index(self, key_mode, key_index):
        """Get default model info index key."""
        config = self._device.model_info.config_value(key_mode)
        if not config or not isinstance(config, dict):
            return None
        return config.get(key_index)

    def _get_default_name_index(self, key_mode, key_index):
        """Get default model info index name."""
        index = self._get_default_index(key_mode, key_index)
        if index is None:
            return None
        return self._device.model_info.enum_index(key_index, index)

    def _get_default_temp_index(self, key_mode, key_index):
        """Get default model info temperature index key."""
        config = self._get_default_index(key_mode, key_index)
        if not config or not isinstance(config, dict):
            return None
        unit = self._get_temp_unit() or StateOptions.NONE
        unit_key = "tempUnit_F" if unit == TemperatureUnit.FAHRENHEIT else "tempUnit_C"
        return config.get(unit_key)

    def _get_temp_unit(self):
        """Get used temperature unit."""
        if not self._temp_unit:
            temp_unit = self.lookup_enum(["TempUnit", "tempUnit"])
            if not temp_unit:
                return None
            self._temp_unit = REFRTEMPUNIT.get(temp_unit, TemperatureUnit.CELSIUS)
        return self._temp_unit

    def _get_temp_key(self, key):
        """Get used temperature unit key."""
        temp_key = None
        if self.eco_friendly_enabled:
            temp_key = self._get_default_temp_index("ecoFriendlyDefaultIndex", key)
        if temp_key is None:
            if self.is_info_v2:
                temp_key = self.int_or_none(self._data.get(key))
            else:
                temp_key = self._data.get(key)
            if temp_key is None:
                return None
        return str(temp_key)

    def update_status(self, key, value):
        """Update device status."""
        if not super().update_status(key, value):
            return False
        self._eco_friendly_state = None
        return True

    @property
    def is_on(self):
        """Return if device is on."""
        return self.has_data

    @property
    def temp_fridge(self):
        """Return current fridge temperature."""
        index = 0
        unit_key = None
        if self.is_info_v2:
            unit_key = self._data.get("tempUnit")
            index = 1
        temp_key = self._get_temp_key(STATE_FRIDGE_TEMP[index])
        if temp_key is None:
            return None
        temp_lists = self._device.get_fridge_temps(self._get_temp_unit(), unit_key)
        return self.to_int_or_none(temp_lists.get(temp_key))

    @property
    def temp_freezer(self):
        """Return current freezer temperature."""
        index = 0
        unit_key = None
        if self.is_info_v2:
            unit_key = self._data.get("tempUnit")
            index = 1
        temp_key = self._get_temp_key(STATE_FREEZER_TEMP[index])
        if temp_key is None:
            return None
        temp_lists = self._device.get_freezer_temps(self._get_temp_unit(), unit_key)
        return self.to_int_or_none(temp_lists.get(temp_key))

    @property
    def temp_unit(self):
        """Return used temperature unit."""
        return self._get_temp_unit() or StateOptions.NONE

    @property
    def door_opened_state(self):
        """Return door opened state."""
        if self.is_info_v2:
            state = self._data.get("atLeastOneDoorOpen")
        else:
            state = self.lookup_enum("DoorOpenState")
        if not state:
            return StateOptions.NONE
        return self._device.get_enum_text(state)

    @property
    def eco_friendly_enabled(self):
        """Return if eco friendly is enabled."""
        state = self._get_eco_friendly_state()
        if not state:
            return False
        return bool(state == LABEL_BIT_ON)

    @property
    def eco_friendly_state(self):
        """Return current eco friendly state."""
        key = STATE_ECO_FRIENDLY[1 if self.is_info_v2 else 0]
        status = self._get_eco_friendly_state()
        return self._update_feature(RefrigeratorFeatures.ECOFRIENDLY, status, True, key)

    @property
    def ice_plus_status(self):
        """Return current ice plus status."""
        if self.is_info_v2:
            return None
        key = STATE_ICE_PLUS[0]
        status = self.lookup_enum(key)
        return self._update_feature(RefrigeratorFeatures.ICEPLUS, status, True, key)

    @property
    def express_fridge_status(self):
        """Return current express fridge status."""
        if not self.is_info_v2:
            return None
        key = STATE_EXPRESS_FRIDGE[1]
        status = self.lookup_enum(key)
        return self._update_feature(
            RefrigeratorFeatures.EXPRESSFRIDGE, status, True, key
        )

    @property
    def express_mode_status(self):
        """Return current express mode status."""
        if not self.is_info_v2:
            return None
        key = STATE_EXPRESS_MODE[1]
        status = self.lookup_enum(key)
        return self._update_feature(RefrigeratorFeatures.EXPRESSMODE, status, True, key)

    @property
    def smart_saving_state(self):
        """Return current smart saving state."""
        state = self.lookup_enum(["SmartSavingModeStatus", "smartSavingRun"])
        if not state:
            return StateOptions.NONE
        return self._device.get_enum_text(state)

    @property
    def smart_saving_mode(self):
        """Return current smart saving mode."""
        if self.is_info_v2:
            key = "smartSavingMode"
        else:
            key = "SmartSavingMode"
        status = self.lookup_enum(key)
        return self._update_feature(
            RefrigeratorFeatures.SMARTSAVINGMODE, status, True, key
        )

    @property
    def fresh_air_filter_status(self):
        """Return current fresh air filter status."""
        if self.is_info_v2:
            key = "freshAirFilter"
        else:
            key = "FreshAirFilter"
        status = self.lookup_enum(key)
        return self._update_feature(
            RefrigeratorFeatures.FRESHAIRFILTER, status, True, key
        )

    @property
    def water_filter_used_month(self):
        """Return water filter used months."""
        if self.is_info_v2:
            key = "waterFilter"
        else:
            key = "WaterFilterUsedMonth"

        counter = None
        if self.is_info_v2:
            status = self._data.get(key)
            if status:
                counters = status.split("_", 1)
                if len(counters) > 1:
                    counter = counters[0]
        else:
            counter = self._data.get(key)
        value = "N/A" if not counter else counter
        return self._update_feature(
            RefrigeratorFeatures.WATERFILTERUSED_MONTH, value, False, key
        )

    @property
    def locked_state(self):
        """Return current locked state."""
        state = self.lookup_enum("LockingStatus")
        if not state:
            return StateOptions.NONE
        return self._device.get_enum_text(state)

    @property
    def active_saving_status(self):
        """Return current active saving status."""
        return self._data.get("ActiveSavingStatus", "N/A")

    def _update_features(self):
        _ = [
            self.eco_friendly_state,
            self.ice_plus_status,
            self.express_fridge_status,
            self.express_mode_status,
            self.smart_saving_mode,
            self.fresh_air_filter_status,
            self.water_filter_used_month,
        ]
