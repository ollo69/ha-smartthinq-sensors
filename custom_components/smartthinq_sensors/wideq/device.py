"""A high-level, convenient abstraction for interacting with the LG
SmartThinQ API for most use cases.
"""
import base64
import json
from collections import namedtuple
from datetime import datetime, timedelta
import enum
import logging
from numbers import Number
from typing import Any, Dict, Optional

from . import EMULATION, wideq_log_level
from .core_exceptions import MonitorError

BIT_OFF = "OFF"
BIT_ON = "ON"

LABEL_BIT_OFF = "@CP_OFF_EN_W"
LABEL_BIT_ON = "@CP_ON_EN_W"

DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_REFRESH_TIMEOUT = 20  # seconds

STATE_OPTIONITEM_OFF = "off"
STATE_OPTIONITEM_ON = "on"
STATE_OPTIONITEM_NONE = "-"
STATE_OPTIONITEM_UNKNOWN = "unknown"

UNIT_TEMP_CELSIUS = "celsius"
UNIT_TEMP_FAHRENHEIT = "fahrenheit"

LOCAL_LANG_PACK = {
    LABEL_BIT_OFF: STATE_OPTIONITEM_OFF,
    LABEL_BIT_ON: STATE_OPTIONITEM_ON,
    BIT_OFF: STATE_OPTIONITEM_OFF,
    BIT_ON: STATE_OPTIONITEM_ON,
    "CLOSE": STATE_OPTIONITEM_OFF,
    "OPEN": STATE_OPTIONITEM_ON,
    "UNLOCK": STATE_OPTIONITEM_OFF,
    "LOCK": STATE_OPTIONITEM_ON,
    "INITIAL_BIT_OFF": STATE_OPTIONITEM_OFF,
    "INITIAL_BIT_ON": STATE_OPTIONITEM_ON,
    "IGNORE": STATE_OPTIONITEM_NONE,
    "NOT_USE": "Not Used",
}


class OPTIONITEMMODES(enum.Enum):
    ON = STATE_OPTIONITEM_ON
    OFF = STATE_OPTIONITEM_OFF


class UNITTEMPMODES(enum.Enum):
    Celsius = UNIT_TEMP_CELSIUS
    Fahrenheit = UNIT_TEMP_FAHRENHEIT


class STATE_UNKNOWN(enum.Enum):
    UNKNOWN = STATE_OPTIONITEM_UNKNOWN


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


WM_DEVICE_TYPES = [
    DeviceType.DRYER,
    DeviceType.TOWER_DRYER,
    DeviceType.TOWER_WASHER,
    DeviceType.WASHER,
]

_LOGGER = logging.getLogger(__name__)


class Monitor(object):
    """A monitoring task for a device.
        
        This task is robust to some API-level failures. If the monitoring
        task expires, it attempts to start a new one automatically. This
        makes one `Monitor` object suitable for long-term monitoring.
        """

    def __init__(self, session, device_id: str) -> None:
        self.session = session
        self.device_id = device_id

    def start(self) -> None:
        self.work_id = self.session.monitor_start(self.device_id)

    def stop(self) -> None:
        self.session.monitor_stop(self.device_id, self.work_id)

    def poll(self) -> Optional[bytes]:
        """Get the current status data (a bytestring) or None if the
            device is not yet ready.
            """
        self.work_id = self.session.monitor_start(self.device_id)
        try:
            return self.session.monitor_poll(self.device_id, self.work_id)
        except MonitorError:
            # Try to restart the task.
            self.stop()
            self.start()
            return None

    @staticmethod
    def decode_json(data: bytes) -> Dict[str, Any]:
        """Decode a bytestring that encodes JSON status data."""

        return json.loads(data.decode("utf8"))

    def poll_json(self) -> Optional[Dict[str, Any]]:
        """For devices where status is reported via JSON data, get the
            decoded status result (or None if status is not available).
            """

        data = self.poll()
        return self.decode_json(data) if data else None

    def __enter__(self) -> "Monitor":
        self.start()
        return self

    def __exit__(self, type, value, tb) -> None:
        self.stop()


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
        if "snapshot" in self._data:
            return self._data["snapshot"]
        return None


EnumValue = namedtuple("EnumValue", ["options"])
RangeValue = namedtuple("RangeValue", ["min", "max", "step"])
BitValue = namedtuple("BitValue", ["options"])
ReferenceValue = namedtuple("ReferenceValue", ["reference"])


class ModelInfo(object):
    """A description of a device model's capabilities.
        """

    def __init__(self, data):
        self._data = data
        self._bit_keys = {}

    @property
    def is_info_v2(self):
        return False

    @property
    def model_type(self):
        return self._data.get("Info", {}).get("modelType", "")

    def config_value(self, key):
        return self._data.get("Config", {}).get(key, "")

    def value_type(self, name):
        if name in self._data["Value"]:
            return self._data["Value"][name]["type"]
        return None

    def value_exist(self, name):
        return name in self._data["Value"]

    def value(self, name):
        """Look up information about a value.
        
        Return either an `EnumValue` or a `RangeValue`.
        """
        d = self._data["Value"][name]
        if d["type"] in ("Enum", "enum"):
            return EnumValue(d["option"])
        elif d["type"] == "Range":
            return RangeValue(
                d["option"]["min"], d["option"]["max"], d["option"].get("step", 0)
            )
        elif d["type"] == "Bit":
            bit_values = {}
            for bit in d["option"]:
                bit_values[bit["startbit"]] = {
                    "value": bit["value"],
                    "length": bit["length"],
                }
            return BitValue(bit_values)
        elif d["type"] == "Reference":
            ref = d["option"][0]
            return ReferenceValue(self._data[ref])
        elif d["type"] == "Boolean":
            return EnumValue({"0": BIT_OFF, "1": BIT_ON})
        elif d["type"] == "String":
            pass
        else:
            _LOGGER.error(
                "ModelInfo: unsupported value type (%s) - value: %s",
                d["type"],
                d,
            )
            return None

    def default(self, name):
        """Get the default value, if it exists, for a given value.
        """

        return self._data.get("Value", {}).get(name, {}).get("default")

    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name.
        """
        if not self.value_type(key):
            return None

        options = self.value(key).options
        options_inv = {v: k for k, v in options.items()}  # Invert the map.
        return options_inv.get(name)

    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value.
        """
        if not self.value_type(key):
            return None

        values = self.value(key)
        if not hasattr(values, "options"):
            return None
        options = values.options
        return options.get(value, "")

    def enum_index(self, key, index):
        """Look up the friendly enum name for an indexed value.
        """
        return self.enum_name(key, index)

    def range_name(self, key):
        """Look up the value of a RangeValue.  Not very useful other than for comprehension
        """

        return key

    def bit_name(self, key, bit_index, value):
        """Look up the friendly name for an encoded bit value
        """
        if not self.value_type(key):
            return str(value)

        options = self.value(key).options

        if not self.value_type(options[bit_index]["value"]):
            return str(value)

        enum_options = self.value(options[bit_index]["value"]).options
        return enum_options[value]

    def _get_bit_key(self, key):

        def search_bit_key(key, data):
            if not data:
                return {}
            for i in range(1, 4):
                opt_key = f"Option{str(i)}"
                option = data.get(opt_key)
                if not option:
                    continue
                for opt in option.get("option", []):
                    if key == opt.get("value", ""):
                        start_bit = opt.get("startbit")
                        length = opt.get("length", 1)
                        if start_bit is None:
                            return {}
                        return {
                            "option": opt_key,
                            "startbit": start_bit,
                            "length": length,
                        }
            return {}

        bit_key = self._bit_keys.get(key)
        if bit_key is None:
            data = self._data.get("Value")
            bit_key = search_bit_key(key, data)
            self._bit_keys[key] = bit_key

        return bit_key

    def bit_value(self, key, values):
        """Look up the bit value for an specific key
        """
        bit_key = self._get_bit_key(key)
        if not bit_key:
            return None
        value = None if not values else values.get(bit_key["option"])
        if not value:
            return "0"
        bit_value = int(value)
        start_bit = bit_key["startbit"]
        length = bit_key["length"]
        val = 0
        for i in range(0, length):
            bit_index = 2 ** (start_bit + i)
            bit = 1 if bit_value & bit_index else 0
            val += bit * (2 ** i)
        return str(val)

    def reference_name(self, key, value, ref_key="_comment"):
        """Look up the friendly name for an encoded reference value
        """
        value = str(value)
        if not self.value_type(key):
            return None

        reference = self.value(key).reference

        if value in reference:
            ref_key_value = reference[value].get(ref_key)
            if ref_key_value:
                return ref_key_value
            return reference[value].get("label")
        return None

    @property
    def binary_control_data(self):
        """Check that type of control is BINARY(BYTE).
        """
        return self._data["ControlWifi"]["type"] == "BINARY(BYTE)"

    def get_control_cmd(self, cmd_key, ctrl_key=None):
        """Get the payload used to send the command."""
        control = None
        if "ControlWifi" in self._data:
            control_data = self._data["ControlWifi"].get("action", {}).get(cmd_key)
            if control_data:
                control = control_data.copy()  # we copy so that we can manipulate
                if ctrl_key:
                    control["cmd"] = ctrl_key
        return control

    @property
    def binary_monitor_data(self):
        """Check that type of monitoring is BINARY(BYTE).
        """
        return self._data["Monitoring"]["type"] == "BINARY(BYTE)"

    def decode_monitor_binary(self, data):
        """Decode binary encoded status data.
        """

        decoded = {}
        for item in self._data["Monitoring"]["protocol"]:
            key = item["value"]
            value = 0
            for v in data[item["startByte"]: item["startByte"] + item["length"]]:
                value = (value << 8) + v
            decoded[key] = str(value)
        return decoded

    def decode_monitor_json(self, data):
        """Decode a bytestring that encodes JSON status data."""

        return json.loads(data.decode("utf8"))

    def decode_monitor(self, data):
        """Decode  status data."""

        if self.binary_monitor_data:
            return self.decode_monitor_binary(data)
        else:
            return self.decode_monitor_json(data)

    @staticmethod
    def _get_current_temp_key(key: str, data):
        """Special case for oven current temperature, that in protocol
        is represented with a suffix "F" or "C" depending from the unit
        """
        if key.count("CurrentTemperature") == 0:
            return key
        new_key = key[:-1]
        if not new_key.endswith("CurrentTemperature"):
            return key
        unit_key = f"{new_key}Unit"
        if unit_key not in data:
            return key
        if data[unit_key][0] == key[-1]:
            return f"{new_key}Value"
        return key

    def decode_snapshot(self, data, key):
        """Decode  status data."""
        decoded = {}
        if self._data["Monitoring"]["type"] != "THINQ2":
            return decoded
        info = data.get(key)
        if not info:
            return decoded

        protocol = self._data["Monitoring"]["protocol"]
        if isinstance(protocol, list):
            for elem in protocol:
                if "superSet" in elem: 
                    key = elem["value"]
                    value = data
                    for ident in elem["superSet"].split("."):
                        if value is None:
                            break
                        pr_key = self._get_current_temp_key(ident, value)
                        value = value.get(pr_key)
                    if value is not None:
                        if isinstance(value, Number):
                            value = int(value)
                        decoded[key] = str(value)
            return decoded

        for data_key, value_key in protocol.items():
            value = info.get(data_key, "")
            if value is not None and isinstance(value, Number):
                value = int(value)
            decoded[value_key] = str(value)
        return decoded


class ModelInfoV2(object):
    """A description of a device model's capabilities.
        Type V2.
        """

    def __init__(self, data):
        self._data = data

    @property
    def is_info_v2(self):
        return True

    @property
    def model_type(self):
        return self._data.get("Info", {}).get("modelType", "")

    def config_value(self, key):
        return self._data.get("Config", {}).get(key, "")

    def value_type(self, name):
        if name in self._data["MonitoringValue"]:
            return self._data["MonitoringValue"][name].get("dataType")
        return None

    def value_exist(self, name):
        return name in self._data["MonitoringValue"]

    def data_root(self, name):
        if name in self._data["MonitoringValue"]:
            if "dataType" in self._data["MonitoringValue"][name]:
                return self._data["MonitoringValue"][name]
            ref = self._data["MonitoringValue"][name].get("ref")
            if ref:
                return self._data.get(ref)

        return None

    def value(self, data):
        """Look up information about a value.
        
        Return either an `EnumValue` or a `RangeValue`.
        """
        data_type = data.get("dataType")
        if not data_type:
            return data
        elif data_type in ("Enum", "enum"):
            return data["valueMapping"]
        elif data_type == "range":
            return RangeValue(data["valueMapping"]["min"], data["valueMapping"]["max"], 1)
        # elif d['dataType'] == 'Bit':
        #    bit_values = {}
        #    for bit in d['option']:
        #        bit_values[bit['startbit']] = {
        #        'value' : bit['value'],
        #        'length' : bit['length'],
        #        }
        #    return BitValue(
        #            bit_values
        #            )
        # elif d['dataType'] == 'Reference':
        #    ref =  d['option'][0]
        #    return ReferenceValue(
        #            self.data[ref]
        #            )
        elif data_type in ("Boolean", "boolean"):
            ret_val = {"BOOL": True}
            ret_val.update(data["valueMapping"])
            return ret_val
        # elif d['dataType'] == 'String':
        #    pass
        else:
            _LOGGER.error(
                "ModelInfoV2: unsupported value type (%s) - value: %s",
                data_type,
                data,
            )
            return None

    def default(self, name):
        """Get the default value, if it exists, for a given value.
        """
        data = self.data_root(name)
        if data:
            return data.get("default")

        return None

    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name.
        """
        data = self.data_root(key)
        if not data:
            return None

        options = self.value(data)
        options_inv = {v["label"]: k for k, v in options.items() if v.get("label")}  # Invert the map.
        return options_inv.get(name)

    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value.
        """
        data = self.data_root(key)
        if not data:
            return None

        options = self.value(data)
        item = options.get(value, {})
        if options.get("BOOL", False):
            index = item.get("index", 0)
            return BIT_ON if index == 1 else BIT_OFF
        return item.get("label", "")

    def enum_index(self, key, index):
        """Look up the friendly enum name for an indexed value.
        """
        data = self.data_root(key)
        if not data:
            return None

        options = self.value(data)
        for item in options.values():
            idx = item.get("index", -1)
            if idx == index:
                return item.get("label", "")

        return ""

    def range_name(self, key):
        """Look up the value of a RangeValue.  Not very useful other than for comprehension
        """
        return key

    def bit_name(self, key, bit_index, value):
        """Look up the friendly name for an encoded bit value
        """
        return None

    def bit_value(self, key, value):
        """Look up the bit value for an specific key
            Not used in model V2
            """
        return None

    def reference_name(self, key, value, ref_key="_comment"):
        """Look up the friendly name for an encoded reference value
        """
        data = self.data_root(key)
        if not data:
            return None

        reference = self.value(data)

        if value in reference:
            ref_key_value = reference[value].get(ref_key)
            if ref_key_value:
                return ref_key_value
            return reference[value].get("label")
        return None

    def target_key(self, key, value, target):
        """Look up the friendly name for an encoded reference value
        """
        data = self.data_root(key)
        if not data:
            return None

        return data.get("targetKey", {}).get(target, {}).get(value)

    @property
    def binary_control_data(self):
        """Check that type of control is BINARY(BYTE).
        """
        return False

    def get_control_cmd(self, cmd_key, ctrl_key=None):
        """Get the payload used to send the command."""
        control = None
        if "ControlWifi" in self._data:
            control_data = self._data["ControlWifi"].get(cmd_key)
            if control_data:
                control = control_data.copy()  # we copy so that we can manipulate
                if ctrl_key:
                    control["ctrlKey"] = ctrl_key
        return control

    @property
    def binary_monitor_data(self):
        """Check that type of monitoring is BINARY(BYTE).
        """
        return False

    def decode_monitor_binary(self, data):
        """Decode binary encoded status data.
        """

        return {}

    def decode_monitor_json(self, data):
        """Decode a bytestring that encodes JSON status data."""

        return json.loads(data.decode("utf8"))

    def decode_monitor(self, data):
        """Decode  status data."""

        if self.binary_monitor_data:
            return self.decode_monitor_binary(data)
        else:
            return self.decode_monitor_json(data)

    def decode_snapshot(self, data, key):
        """Decode  status data."""
        return data.get(key)


class ModelInfoV2AC(ModelInfo):
    """A description of a device model's capabilities.
        Type V2AC and other models with "data_type in Value.
        """

    @staticmethod
    def valid_value_data(value_data):
        """Determine if valid Value data is in this model."""
        first_value = list(value_data.values())[0]
        if "data_type" in first_value:
            return True
        return False

    @property
    def is_info_v2(self):
        return True

    def value_type(self, name):
        if name in self._data["Value"]:
            return self._data["Value"][name]["data_type"]
        return None

    def value(self, name):
        """Look up information about a value.

        Return either an `EnumValue` or a `RangeValue`.
        """
        d = self._data["Value"][name]
        if d["data_type"] in ("Enum", "enum"):
            return EnumValue(d["value_mapping"])
        elif d["data_type"] in ("Range", "range"):
            return RangeValue(
                d["value_validation"]["min"], d["value_validation"]["max"], d["value_validation"].get("step", 0)
            )
        # elif d["type"] == "Bit":
        #    bit_values = {}
        #    for bit in d["option"]:
        #        bit_values[bit["startbit"]] = {
        #            "value": bit["value"],
        #            "length": bit["length"],
        #        }
        #    return BitValue(bit_values)
        # elif d["type"] == "Reference":
        #    ref = d["option"][0]
        #    return ReferenceValue(self._data[ref])
        # elif d["type"] == "Boolean":
        #    return EnumValue({"0": "False", "1": "True"})
        elif d["data_type"] == "String":
            pass
        else:
            assert False, "unsupported value type {}".format(d["data_type"])

    def decode_snapshot(self, data, key):
        return data


class Device(object):
    """A higher-level interface to a specific device.
        
    Unlike `DeviceInfo`, which just stores data *about* a device,
    `Device` objects refer to their client and can perform operations
    regarding the device.
    """

    def __init__(self, client, device: DeviceInfo, status=None, available_features=None):
        """Create a wrapper for a `DeviceInfo` object associated with a
        `Client`.
        """

        self._client = client
        self._device_info = device
        self._status = status
        self._model_data = None
        self._model_info = None
        self._model_lang_pack = None
        self._product_lang_pack = None
        self._should_poll = device.platform_type == PlatformType.THINQ1
        self._mon = None
        self._control_set = 0
        self._last_additional_poll: Optional[datetime] = None
        self._available_features = available_features or {}

        # for logging unknown states received
        self._unknown_states = []

    @property
    def client(self):
        return self._client

    @property
    def device_info(self):
        return self._device_info

    @property
    def model_info(self):
        return self._model_info

    @property
    def available_features(self) -> Dict:
        return self._available_features

    @property
    def status(self):
        if not self._model_info:
            return None
        return self._status

    def reset_status(self):
        self._status = None
        return self._status

    def _get_feature_title(self, feature_name, item_key):
        """Override this function to manage feature title per device type"""
        return feature_name

    def feature_title(self, feature_name, item_key=None, status=None):
        title = self._available_features.get(feature_name)
        if title is None:
            if status is None:
                return None
            title = self._get_feature_title(feature_name, item_key)
            if not title:
                return None
            self._available_features[feature_name] = title
        return title

    def _get_state_key(self, key_name):
        """Get the key used for state from an array based on info type"""
        if isinstance(key_name, list):
            return key_name[1 if self.model_info.is_info_v2 else 0]
        return key_name

    def _get_cmd_keys(self, key_name):
        """Get the keys used for control based on info type"""
        ctrl = self._get_state_key(key_name[0])
        cmd = self._get_state_key(key_name[1])
        key = self._get_state_key(key_name[2])

        return [ctrl, cmd, key]

    def _set_control(
            self,
            ctrl_key,
            command=None,
            *,
            key=None,
            value=None,
            data=None,
            ctrl_path=None,
    ):
        """Set a device's control for `key` to `value`.
        """
        if EMULATION:
            return

        if self._should_poll:
            self._client.session.set_device_controls(
                self._device_info.id,
                ctrl_key,
                command,
                {key: value} if key and value else value,
                {key: data} if key and data else data,
            )
            self._control_set = 2
            return

        self._client.session.set_device_v2_controls(
            self._device_info.id,
            ctrl_key,
            command,
            key,
            value,
            ctrl_path=ctrl_path,
        )

    def _prepare_command(self, ctrl_key, command, key, value):
        """Prepare command for specific device.
        Overwrite for specific device settings.
        """
        return None

    def set(self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None):
        """Set a device's control for `key` to `value`."""
        log_level = wideq_log_level()
        full_key = self._prepare_command(ctrl_key, command, key, value)
        if full_key:
            _LOGGER.log(
                log_level,
                "Setting new state for device %s: %s",
                self._device_info.id, str(full_key),
            )
            self._set_control(full_key, ctrl_path=ctrl_path)
        else:
            _LOGGER.log(
                log_level,
                "Setting new state for device %s:  %s - %s - %s - %s",
                self._device_info.id, ctrl_key, command, key, value,
            )
            self._set_control(
                ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
            )

    def _get_config(self, key):
        """Look up a device's configuration for a given value.
            
        The response is parsed as base64-encoded JSON.
        """
        if not self._should_poll:
            return
        data = self._client.session.get_device_config(self._device_info.id, key)
        if self._control_set == 0:
            self._control_set = 1
        return json.loads(base64.b64decode(data).decode("utf8"))

    def _get_control(self, key):
        """Look up a device's control value.
            """
        if not self._should_poll:
            return
        data = self._client.session.get_device_config(
            self._device_info.id, key, "Control",
        )
        if self._control_set == 0:
            self._control_set = 1

        # The response comes in a funky key/value format: "(key:value)".
        _, value = data[1:-1].split(":")
        return value

    def init_device_info(self):
        """Initialize the information for the device"""

        if self._model_info is None:
            if self._model_data is None:
                self._model_data = self._client.model_url_info(
                    self._device_info.model_info_url,
                    self._device_info,
                )

            model_data = self._model_data
            if "Monitoring" in model_data and "Value" in model_data:
                if ModelInfoV2AC.valid_value_data(model_data["Value"]):
                    # this are V2 models with format similar to V1
                    self._model_info = ModelInfoV2AC(model_data)
                else:
                    # this are old V1 model
                    self._model_info = ModelInfo(model_data)
            elif "MonitoringValue" in model_data:
                # this are new V2 devices
                self._model_info = ModelInfoV2(model_data)
            elif "ControlDevice" in model_data and "Value" in model_data:
                # this are new V2 ac
                self._model_info = ModelInfoV2AC(model_data)

        if self._model_info is not None:
            # load model language pack
            if self._model_lang_pack is None:
                self._model_lang_pack = self._client.model_url_info(
                    self._device_info.model_lang_pack_url
                )

            # load product language pack
            if self._product_lang_pack is None:
                self._product_lang_pack = self._client.model_url_info(
                    self._device_info.product_lang_pack_url
                )

        return self._model_info is not None

    def monitor_start(self):
        """Start monitoring the device's status."""
        if not self._should_poll:
            return
        mon = Monitor(self._client.session, self._device_info.id)
        mon.start()
        self._mon = mon

    def monitor_stop(self):
        """Stop monitoring the device's status."""
        if not self._mon:
            return
        self._mon.stop()
        self._mon = None

    def _pre_update_v2(self):
        """Call additional methods before data update for v2 API.

        Override in specific device to call requested methods
        """
        return

    def _get_device_snapshot(self, query_device=False):
        """Get snapshot for ThinQ2 devices.

        Perform dedicated device query if query_device is set to true,
        otherwise use the dashboard result
        """
        if EMULATION:
            query_device = False

        if query_device:
            try:
                self._pre_update_v2()
            except Exception:
                pass
            result = self._client.session.get_device_v2_settings(self._device_info.id)
            return result.get("snapshot")

        self._client.refresh_devices()
        device_data = self._client.get_device(self._device_info.id)
        if device_data:
            return device_data.snapshot
        return None

    def _delete_permission(self):
        """Remove permission acquired in set command."""
        if not self._should_poll:
            return
        if self._control_set <= 0:
            return
        if self._control_set == 1:
            self._client.session.delete_permission(self._device_info.id)
        self._control_set -= 1

    def _get_device_info(self):
        """Call additional method to get device information for V1 API.

        Override in specific device to call requested methods
        """
        return

    def _additional_poll(self, poll_interval: int):
        """Perform dedicated additional device poll with a slower rate."""
        if not self._should_poll:
            return
        if poll_interval <= 0:
            return
        call_time = datetime.now()
        if self._last_additional_poll is None:
            self._last_additional_poll = (
                call_time - timedelta(seconds=max(poll_interval - 10, 1))
            )
        difference = (call_time - self._last_additional_poll).total_seconds()
        if difference >= poll_interval:
            self._last_additional_poll = datetime.now()
            self._get_device_info()

    def device_poll(
            self,
            snapshot_key="",
            *,
            thinq1_additional_poll=0,
            thinq2_query_device=False,
    ):
        """Poll the device's current state.
        Monitoring for thinq1 devices must be started first with `monitor_start`.

        Return either a `Status` object or `None` if the status is not yet available.

        :param snapshot_key: the key used to extract the thinq2 snapshot from payload.
        :param thinq1_additional_poll: run an additional poll command for thinq1 devices
            at specified rate (0 means disabled).
        :param thinq2_query_device: if True query thinq2 devices with dedicated command
            instead using dashboard.
        """
        res = None

        # load device info at first call if not loaded before
        if not self.init_device_info():
            return None

        # ThinQ V2 - Monitor data is with device info
        if not self._should_poll:
            snapshot = self._get_device_snapshot(thinq2_query_device)
            if not snapshot:
                return None
            return self._model_info.decode_snapshot(snapshot, snapshot_key)

        # ThinQ V1 - Monitor data must be polled """
        if not self._mon:
            # Abort if monitoring has not started yet.
            return None
        data = self._mon.poll()
        if data:
            res = self._model_info.decode_monitor(data)

        # do additional poll
        if res and thinq1_additional_poll > 0:
            try:
                self._additional_poll(thinq1_additional_poll)
            except Exception as exc:
                _LOGGER.warning("Error calling additional poll methods. Error %s", exc)

        # remove control permission if previously set
        self._delete_permission()

        return res

    def get_enum_text(self, enum_name):

        if not enum_name:
            return STATE_OPTIONITEM_NONE

        text_value = LOCAL_LANG_PACK.get(enum_name)
        if not text_value and self._model_lang_pack:
            text_value = self._model_lang_pack.get("pack", {}).get(enum_name)
        if not text_value and self._product_lang_pack:
            text_value = self._product_lang_pack.get("pack", {}).get(enum_name)
        if not text_value:
            text_value = enum_name

        return text_value

    def is_unknown_status(self, status):

        if status in self._unknown_states:
            return False

        self._unknown_states.append(status)
        return True


class DeviceStatus(object):
    """A higher-level interface to a specific device status."""

    def __init__(self, device, data):
        self._device = device
        self._data = {} if data is None else data
        self._device_features = {}
        self._features_updated = False

    @staticmethod
    def int_or_none(value):
        if value is not None and isinstance(value, Number):
            return str(int(value))
        return None

    @staticmethod
    def to_int_or_none(value):
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def has_data(self):
        return True if self._data else False

    @property
    def data(self):
        return self._data

    @property
    def is_on(self) -> bool:
        return False

    @property
    def is_info_v2(self):
        return self._device.model_info.is_info_v2

    def _get_data_key(self, keys):
        if not self._data:
            return ""
        if isinstance(keys, list):
            for key in keys:
                if key in self._data:
                    return key
        elif keys in self._data:
            return keys

        return ""

    def _set_unknown(self, state, key, type):
        if state:
            return state

        if self._device.is_unknown_status(key):
            _LOGGER.warning(
                "ThinQ: received unknown %s status '%s' of type '%s'",
                self._device.device_info.type.name,
                key,
                type,
            )

        return STATE_UNKNOWN.UNKNOWN

    def update_status(self, key, value):
        if key in self._data:
            self._data[key] = value
            return True
        return False

    def key_exist(self, keys):
        if isinstance(keys, list):
            for key in keys:
                if self._device.model_info.value_exist(key):
                    return True
            return False
        return self._device.model_info.value_exist(keys)

    def lookup_enum(self, key, data_is_num=False):
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        value = self._data[curr_key]
        if data_is_num:
            value = str(int(value))

        return self._device.model_info.enum_name(
            curr_key, value
        )

    def lookup_range(self, key):
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        return self._data[curr_key]

    def lookup_reference(self, key, ref_key="_comment"):
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        return self._device.model_info.reference_name(
            curr_key, self._data[curr_key], ref_key
        )

    def lookup_bit_enum(self, key):
        if not self._data:
            str_val = ""
        else:
            str_val = self._data.get(key)
            if not str_val:
                str_val = self._device.model_info.bit_value(
                    key, self._data
                )

        if str_val is None:
            return None
        ret_val = self._device.model_info.enum_name(key, str_val)

        # exception because doorlock bit
        # is not inside the model enum
        if key == "DoorLock" and ret_val is None:
            if str_val == "1":
                return LABEL_BIT_ON
            return LABEL_BIT_OFF

        return ret_val

    def lookup_bit(self, key):
        enum_val = self.lookup_bit_enum(key)
        if enum_val is None:
            return None
        bit_val = LOCAL_LANG_PACK.get(enum_val, STATE_OPTIONITEM_OFF)
        if bit_val == STATE_OPTIONITEM_ON:
            return STATE_OPTIONITEM_ON
        return STATE_OPTIONITEM_OFF

    def _update_feature(self, key, status, get_text=True, item_key=None):
        title = self._device.feature_title(
            key, item_key, status
        )
        if not title:
            return None

        if status is None:
            status = STATE_OPTIONITEM_NONE
        if status == STATE_OPTIONITEM_NONE or not get_text:
            value = status
        else:
            value = self._device.get_enum_text(status)

        self._device_features[key] = value
        return value

    def _update_features(self):
        """Override this function to manage device features"""
        raise NotImplementedError()

    @property
    def device_features(self):
        if not self._features_updated:
            self._update_features()
            self._features_updated = True
        return self._device_features
