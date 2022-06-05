"""Definition for SmartThinQ device type and information."""

import enum
import logging
from typing import Any, Dict, Optional

from .const import STATE_OPTIONITEM_UNKNOWN

_LOGGER = logging.getLogger(__name__)


class DeviceType(enum.Enum):
    """The category of device."""

    REFRIGERATOR = 101
    KIMCHI_REFRIGERATOR = 102
    WATER_PURIFIER = 103
    WASHER = 201
    DRYER = 202
    STYLER = 203
    DISHWASHER = 204
    TOWER_WASHER = 221
    TOWER_DRYER = 222
    RANGE = 301
    MICROWAVE = 302
    COOKTOP = 303
    HOOD = 304
    AC = 401
    AIR_PURIFIER = 402
    DEHUMIDIFIER = 403
    FAN = 405
    WATER_HEATER = 406
    AIR_PURIFIER_FAN = 410
    ROBOT_KING = 501
    TV = 701
    BOILER = 801
    SPEAKER = 901
    HOMEVU = 902
    ARCH = 1001
    MISSG = 3001
    SENSOR = 3002
    SOLAR_SENSOR = 3102
    IOT_LIGHTING = 3003
    IOT_MOTION_SENSOR = 3004
    IOT_SMART_PLUG = 3005
    IOT_DUST_SENSOR = 3006
    EMS_AIR_STATION = 4001
    AIR_SENSOR = 4003
    PURICARE_AIR_DETECTOR = 4004
    V2PHONE = 6001
    HOMEROBOT = 9000
    UNKNOWN = STATE_OPTIONITEM_UNKNOWN


WM_DEVICE_TYPES = [
    DeviceType.DRYER,
    DeviceType.TOWER_DRYER,
    DeviceType.TOWER_WASHER,
    DeviceType.WASHER,
]


class PlatformType(enum.Enum):
    """The category of device."""

    THINQ1 = "thinq1"
    THINQ2 = "thinq2"
    UNKNOWN = STATE_OPTIONITEM_UNKNOWN


class NetworkType(enum.Enum):
    """The type of network."""

    WIFI = "02"
    NFC3 = "03"
    NFC4 = "04"
    UNKNOWN = STATE_OPTIONITEM_UNKNOWN


class DeviceInfo(object):
    """Details about a user's device.

    This is populated from a JSON dictionary provided by the API.
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data
        self._device_id = None
        self._device_type = None
        self._platform_type = None
        self._network_type = None

    def as_dict(self):
        """Return the data dictionary"""
        if not self._data:
            return {}
        return self._data.copy()

    def _get_data_key(self, keys):
        for key in keys:
            if key in self._data:
                return key
        return ""

    def _get_data_value(self, key, default: Any = STATE_OPTIONITEM_UNKNOWN):
        if isinstance(key, list):
            vkey = self._get_data_key(key)
        else:
            vkey = key

        return self._data.get(vkey, default)

    @property
    def model_id(self) -> str:
        return self._get_data_value(["modelName", "modelNm"])

    @property
    def id(self) -> str:
        if self._device_id is None:
            self._device_id = self._get_data_value("deviceId")
        return self._device_id

    @property
    def model_info_url(self) -> str:
        return self._get_data_value(
            ["modelJsonUrl", "modelJsonUri"], default=None
        )

    @property
    def model_lang_pack_url(self) -> str:
        return self._get_data_value(
            ["langPackModelUrl", "langPackModelUri"], default=None
        )

    @property
    def product_lang_pack_url(self) -> str:
        return self._get_data_value(
            ["langPackProductTypeUrl", "langPackProductTypeUri"], default=None
        )

    @property
    def name(self) -> str:
        return self._get_data_value("alias")

    @property
    def model_name(self) -> str:
        return self._get_data_value(["modelName", "modelNm"])

    @property
    def macaddress(self) -> Optional[str]:
        return self._data.get("macAddress")

    @property
    def firmware(self) -> Optional[str]:
        if fw := self._data.get("fwVer"):
            return fw
        if "modemInfo" in self._data:
            if fw := self._data["modemInfo"].get("appVersion"):
                return fw
        return None

    @property
    def devicestate(self) -> str:
        """The kind of device, as a `DeviceType` value."""
        return self._get_data_value("deviceState")

    @property
    def isonline(self) -> bool:
        """The kind of device, as a `DeviceType` value."""
        return self._data.get("online", False)

    @property
    def type(self) -> DeviceType:
        """The kind of device, as a `DeviceType` value."""
        if self._device_type is None:
            device_type = self._get_data_value("deviceType")
            try:
                ret_val = DeviceType(device_type)
            except ValueError:
                _LOGGER.warning("Device %s: unknown device type with id %s", self.id, device_type)
                ret_val = DeviceType.UNKNOWN
            self._device_type = ret_val
        return self._device_type

    @property
    def platform_type(self) -> PlatformType:
        """The kind of platform, as a `PlatformType` value."""
        if self._platform_type is None:
            # for the moment if unavailable set THINQ1, probably not available in APIv1
            plat_type = self._data.get("platformType", PlatformType.THINQ1.value)
            try:
                ret_val = PlatformType(plat_type)
            except ValueError:
                _LOGGER.warning("Device %s: unknown platform type with id %s", self.id, plat_type)
                ret_val = PlatformType.UNKNOWN
            self._platform_type = ret_val
        return self._platform_type

    @property
    def network_type(self) -> NetworkType:
        """The kind of network, as a `NetworkType` value."""
        if self._network_type is None:
            # for the moment we set WIFI if not available
            net_type = self._data.get("networkType", NetworkType.WIFI.value)
            try:
                ret_val = NetworkType(net_type)
            except ValueError:
                _LOGGER.warning("Device %s: unknown network type with id %s", self.id, net_type)
                # for the moment we set WIFI if unknown
                ret_val = NetworkType.WIFI
            self._network_type = ret_val
        return self._network_type

    @property
    def snapshot(self) -> Optional[Dict[str, Any]]:
        return self._data.get("snapshot")
