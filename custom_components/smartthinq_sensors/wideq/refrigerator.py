"""------------------for Refrigerator"""
import logging
from typing import Optional

from .device import (
    LABEL_BIT_ON,
    STATE_OPTIONITEM_NONE,
    UNIT_TEMP_FAHRENHEIT,
    UNITTEMPMODES,
    Device,
    DeviceStatus,
)

FEATURE_DESCR = {
    "@RE_TERM_EXPRESS_FREEZE_W": "express_freeze_state",
    "@RE_TERM_EXPRESS_FRIDGE_W": "express_cool_state",
    "@RE_TERM_ICE_PLUS_W": "ice_plus_state",
}

REFRTEMPUNIT = {
    "Ｆ": UNITTEMPMODES.Fahrenheit,
    "℃": UNITTEMPMODES.Celsius,
    "˚F": UNITTEMPMODES.Fahrenheit,
    "˚C": UNITTEMPMODES.Celsius,
}

# REFRTEMPUNIT = {
#     "\uff26": UNITTEMPMODES.Fahrenheit,
#     "\u2103": UNITTEMPMODES.Celsius,
#     "\u02daF": UNITTEMPMODES.Fahrenheit,
#     "\u02daC": UNITTEMPMODES.Celsius,
# }

FEAT_ECOFRIENDLY_STATE = "eco_friendly_state"
FEAT_ICEPLUS_STATE = "ice_plus_state"
FEAT_EXPRESSMODE_STATE = "express_mode_state"
FEAT_EXPRESSFRIDGE_STATE = "express_fridge_state"
FEAT_SMARTSAVING_MODE = "smart_saving_mode"
# FEAT_SMARTSAVING_STATE = "smart_saving_state"
FEAT_FRESHAIRFILTER_STATE = "fresh_air_filter_state"
FEAT_WATERFILTERUSED_MONTH = "water_filter_used_month"

_LOGGER = logging.getLogger(__name__)


class RefrigeratorDevice(Device):
    """A higher-level interface for a dryer."""
    def __init__(self, client, device):
        super().__init__(client, device, RefrigeratorStatus(self, None))
        self._feature_titles = {}

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

    def _get_feature_title(self, item_key, def_value):
        item_info = self._get_feature_info(item_key)
        if not item_info:
            return None
        if self.model_info.is_info_v2:
            title_key = "monTitle"
        else:
            title_key = "Title"
        title_value = item_info.get(title_key)
        if not title_value:
            return def_value
        return FEATURE_DESCR.get(title_value, def_value)

    def feature_title(self, feature_name, def_value):
        title = self._feature_titles.get(feature_name)
        if title is None:
            title = self._get_feature_title(feature_name, def_value)
            self._feature_titles[feature_name] = title or ""
        return title

    def reset_status(self):
        self._status = RefrigeratorStatus(self, None)
        return self._status

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
        self._eco_friendly_state = None
        self._sabbath_state = None
        self._available_features = {}

    def _get_eco_friendly_state(self):
        if self._eco_friendly_state is None:
            state = self.lookup_enum(["EcoFriendly", "ecoFriendly"])
            if not state:
                self._eco_friendly_state = ""
            else:
                self._eco_friendly_state = state
        return self._eco_friendly_state

    def _get_sabbath_state(self):
        if self._sabbath_state is None:
            state = self.lookup_enum(["Sabbath", "sabbathMode"])
            if not state:
                self._sabbath_state = ""
            else:
                self._sabbath_state = state
        return self._sabbath_state

    def _get_feature_value(self, key, def_title, value_func=None):
        title = self._device.feature_title(
            key, def_title
        )
        if not title:
            return None

        if value_func:
            status = getattr(self, value_func)()
        else:
            status = self.lookup_enum(key)
        if not status:
            value = STATE_OPTIONITEM_NONE
        else:
            value = self._device.get_enum_text(status)
        self._available_features[title] = value
        return value

    def _get_default_index(self, key_mode, key_index):
        config = self._device.model_info.config_value(key_mode)
        if not config or not isinstance(config, dict):
            return None
        return config.get(key_index)

    def _get_default_name_index(self, key_mode, key_index):
        index = self._get_default_index(key_mode, key_index)
        if index is None:
            return None
        return self._device.model_info.enum_index(key_index, index)

    def _get_default_temp_index(self, key_mode, key_index):
        config = self._get_default_index(key_mode, key_index)
        if not config or not isinstance(config, dict):
            return None
        unit = self._get_temp_unit()
        unit_key = "tempUnit_F" if unit == UNIT_TEMP_FAHRENHEIT else "tempUnit_C"
        return config.get(unit_key)

    def _get_temp_unit(self):
        if not self._temp_unit:
            temp_unit = self.lookup_enum(["TempUnit", "tempUnit"])
            if not temp_unit:
                self._temp_unit = STATE_OPTIONITEM_NONE
            else:
                self._temp_unit = (
                    REFRTEMPUNIT.get(temp_unit, UNITTEMPMODES.Celsius)
                ).value
        return self._temp_unit

    def _get_temp_val_v1(self, key):
        temp_key = None
        if self.eco_friendly_enabled:
            temp_key = self._get_default_temp_index("ecoFriendlyDefaultIndex", key)
        if temp_key is None:
            temp_key = self._data.get(key)
            if temp_key is None:
                return STATE_OPTIONITEM_NONE
        temp_key = str(temp_key)
        value_type = self._device.model_info.value_type(key)
        if value_type and value_type == "Enum":
            temp = self.lookup_enum(key)
            if not temp:
                return temp_key
            if temp != temp_key:
                return temp
        unit = self._get_temp_unit()
        unit_key = "_F" if unit == UNIT_TEMP_FAHRENHEIT else "_C"
        result = self._device.model_info.enum_name(
            key + unit_key, temp_key
        )
        if not result:
            return temp_key
        return result

    def _get_temp_val_v2(self, key):
        temp = None
        if self.eco_friendly_enabled:
            temp = self._get_default_temp_index("ecoFriendlyDefaultIndex", key)
        if temp is None:
            temp = self.int_or_none(self._data.get(key))
            if not temp:
                return STATE_OPTIONITEM_NONE
        temp = str(temp)

        unit = self._data.get("tempUnit")
        if not unit:
            return temp
        ref_key = self._device.model_info.target_key(
            key, unit, "tempUnit"
        )
        if not ref_key:
            return temp
        return self._device.model_info.enum_name(
            ref_key, temp
        )

    @property
    def is_on(self):
        return self.has_data

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
        return self._device.get_enum_text(state)

    @property
    def eco_friendly_enabled(self):
        state = self._get_eco_friendly_state()
        if not state:
            return False
        return True if state == LABEL_BIT_ON else False

    @property
    def eco_friendly_state(self):
        if self.is_info_v2:
            key = "ecoFriendly"
        else:
            key = "EcoFriendly"

        return self._get_feature_value(
            key, FEAT_ECOFRIENDLY_STATE, "_get_eco_friendly_state"
        )

    @property
    def ice_plus_status(self):
        if self.is_info_v2:
            return None

        return self._get_feature_value(
            "IcePlus", FEAT_ICEPLUS_STATE
        )

    @property
    def express_fridge_status(self):
        if not self.is_info_v2:
            return None

        return self._get_feature_value(
            "expressFridge", FEAT_EXPRESSFRIDGE_STATE
        )

    @property
    def express_mode_status(self):
        if not self.is_info_v2:
            return None

        return self._get_feature_value(
            "expressMode", FEAT_EXPRESSMODE_STATE
        )

    @property
    def smart_saving_state(self):
        state = self.lookup_enum(["SmartSavingModeStatus", "smartSavingRun"])
        if not state:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(state)

    @property
    def smart_saving_mode(self):
        if self.is_info_v2:
            key = "smartSavingMode"
        else:
            key = "SmartSavingMode"

        return self._get_feature_value(
            key, FEAT_SMARTSAVING_MODE
        )

    @property
    def fresh_air_filter_status(self):
        if self.is_info_v2:
            key = "freshAirFilter"
        else:
            key = "FreshAirFilter"

        return self._get_feature_value(
            key, FEAT_FRESHAIRFILTER_STATE
        )

    @property
    def water_filter_used_month(self):
        if self.is_info_v2:
            key = "waterFilter"
        else:
            key = "WaterFilterUsedMonth"

        title = self._device.feature_title(
            key, FEAT_WATERFILTERUSED_MONTH
        )
        if not title:
            return None

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
        self._available_features[title] = value
        return value

    @property
    def locked_state(self):
        state = self.lookup_enum("LockingStatus")
        if not state:
            return STATE_OPTIONITEM_NONE
        return self._device.get_enum_text(state)

    @property
    def active_saving_status(self):
        return self._data.get("ActiveSavingStatus", "N/A")

    @property
    def device_features(self):

        feat_value = self.eco_friendly_state
        feat_value = self.ice_plus_status
        feat_value = self.express_fridge_status
        feat_value = self.express_mode_status
        feat_value = self.smart_saving_mode
        feat_value = self.fresh_air_filter_status
        feat_value = self.water_filter_used_month

        return self._available_features
