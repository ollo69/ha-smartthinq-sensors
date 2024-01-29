"""Definition for SmartThinQ device type and information."""

from enum import Enum
import logging
from typing import Any

from .const import StateOptions

KEY_DEVICE_ID = "deviceId"

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
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
    TOWER_WASHERDRYER = 223
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
    ROBOT_VACUUM = 501
    STICK_VACUUM = 504
    CLOUD_GATEWAY = 603
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
    UNKNOWN = StateOptions.UNKNOWN


WM_DEVICE_TYPES = [
    DeviceType.DRYER,
    DeviceType.TOWER_DRYER,
    DeviceType.TOWER_WASHER,
    DeviceType.TOWER_WASHERDRYER,
    DeviceType.WASHER,
]

WM_COMPLEX_DEVICES = {DeviceType.TOWER_WASHERDRYER: ["washer", "dryer"]}

SET_TIME_DEVICE_TYPES = [
    DeviceType.MICROWAVE,
]


class PlatformType(Enum):
    """The category of device."""

    THINQ1 = "thinq1"
    THINQ2 = "thinq2"
    UNKNOWN = StateOptions.UNKNOWN


class NetworkType(Enum):
    """The type of network."""

    WIFI = "02"
    NFC3 = "03"
    NFC4 = "04"
    UNKNOWN = StateOptions.UNKNOWN


class DeviceInfo:
    """
    Details about a user's device.
    This is populated from a JSON dictionary provided by the API.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize the object."""
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
        """Get valid key from a list of possible keys."""
        for key in keys:
            if key in self._data:
                return key
        return ""

    def _get_data_value(self, key, default: Any = StateOptions.UNKNOWN):
        """Get data value for a specific key or list of keys."""
        if isinstance(key, list):
            vkey = self._get_data_key(key)
        else:
            vkey = key

        return self._data.get(vkey, default)

    @property
    def model_id(self) -> str:
        """Return the model name."""
        return self._get_data_value(["modelName", "modelNm"])

    @property
    def device_id(self) -> str:
        """Return the device id."""
        if self._device_id is None:
            self._device_id = self._data.get(KEY_DEVICE_ID, StateOptions.UNKNOWN)
        return self._device_id

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._data.get("alias", self.device_id)

    @property
    def model_info_url(self) -> str:
        """Return the url used to retrieve model info."""
        return self._get_data_value(["modelJsonUrl", "modelJsonUri"], default=None)

    @property
    def model_lang_pack_url(self) -> str:
        """Return the url used to retrieve model language pack."""
        return self._get_data_value(
            ["langPackModelUrl", "langPackModelUri"], default=None
        )

    @property
    def product_lang_pack_url(self) -> str:
        """Return the url used to retrieve product info."""
        return self._get_data_value(
            ["langPackProductTypeUrl", "langPackProductTypeUri"], default=None
        )

    @property
    def model_name(self) -> str:
        """Return the model name for the device."""
        return self._get_data_value(["modelName", "modelNm"])

    @property
    def macaddress(self) -> str | None:
        """Return the device mac address."""
        return self._data.get("macAddress")

    @property
    def firmware(self) -> str | None:
        """Return the device firmware version."""
        if fw_ver := self._data.get("fwVer"):
            return fw_ver
        if (fw_ver := self._data.get("modemInfo")) is not None:
            if isinstance(fw_ver, dict):
                return fw_ver.get("appVersion")
            return fw_ver
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
                _LOGGER.warning(
                    "Device %s: unknown device type with id %s",
                    self.device_id,
                    device_type,
                )
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
                _LOGGER.warning(
                    "Device %s: unknown platform type with id %s",
                    self.device_id,
                    plat_type,
                )
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
                _LOGGER.warning(
                    "Device %s: unknown network type with id %s",
                    self.device_id,
                    net_type,
                )
                # for the moment we set WIFI if unknown
                ret_val = NetworkType.WIFI
            self._network_type = ret_val
        return self._network_type

    @property
    def device_state(self) -> str | None:
        """Return the status associated to the device."""
        return self._data.get("deviceState")

    @property
    def snapshot(self) -> dict[str, Any] | None:
        """Return the snapshot data associated to the device."""
        return self._data.get("snapshot")
