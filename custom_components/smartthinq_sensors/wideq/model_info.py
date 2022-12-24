"""Model Info Classes used to map LG ThinQ device model's capabilities."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import namedtuple
import json
import logging
from numbers import Number

from .const import BIT_OFF, BIT_ON

_LOGGER = logging.getLogger(__name__)

EnumValue = namedtuple("EnumValue", ["options"])
RangeValue = namedtuple("RangeValue", ["min", "max", "step"])
BitValue = namedtuple("BitValue", ["options"])
ReferenceValue = namedtuple("ReferenceValue", ["reference"])


class ModelInfo(ABC):
    """The base abstract class for a device model's capabilities."""

    def __init__(self, data):
        """Initialize the class."""
        self._data = data

    @property
    @abstractmethod
    def is_info_v2(self):
        """Return the type of 'model_info' represented."""

    @abstractmethod
    def as_dict(self):
        """Return the data dictionary"""

    @property
    @abstractmethod
    def model_type(self):
        """Return the model type."""

    @abstractmethod
    def config_value(self, key):
        """Get config value for a specific key."""

    @abstractmethod
    def value_type(self, name):
        """Return the value type for a specific value key."""

    @abstractmethod
    def value_exist(self, name):
        """Check if a value key exist inside model info."""

    @abstractmethod
    def is_enum_type(self, key):
        """Check if specific key is enum type."""

    @abstractmethod
    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name."""

    @abstractmethod
    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value."""

    @abstractmethod
    def enum_index(self, key, index):
        """Look up the friendly enum name for an indexed value."""

    @abstractmethod
    def range_name(self, key):
        """Look up the value of a RangeValue."""

    @abstractmethod
    def bit_name(self, key, bit_index, value):
        """Look up the friendly name for an encoded bit value."""

    @abstractmethod
    def bit_value(self, key, values):
        """Look up the bit value for a specific key."""

    @abstractmethod
    def reference_name(self, key, value, ref_key="_comment"):
        """Look up the friendly name for an encoded reference value."""

    @property
    @abstractmethod
    def binary_control_data(self):
        """Check that type of control is BINARY(BYTE)."""

    @abstractmethod
    def get_control_cmd(self, cmd_key, ctrl_key=None):
        """Get the payload used to send the command."""

    @abstractmethod
    def decode_monitor(self, data):
        """Decode status data."""

    @abstractmethod
    def decode_snapshot(self, data, key):
        """Decode status data."""


class ModelInfoV1(ModelInfo):
    """A description of a device model's capabilities for type V1."""

    def __init__(self, data):
        """Initialize the class."""
        super().__init__(data)
        self._bit_keys = {}

    @property
    def is_info_v2(self):
        """Return the type of 'model_info' represented."""
        return False

    def as_dict(self):
        """Return the data dictionary"""
        if not self._data:
            return {}
        return self._data.copy()

    @property
    def model_type(self):
        """Return the model type."""
        return self._data.get("Info", {}).get("modelType", "")

    def config_value(self, key):
        """Get config value for a specific key."""
        return self._data.get("Config", {}).get(key, "")

    def value_type(self, name):
        """Return the value type for a specific value key."""
        if name in self._data["Value"]:
            return self._data["Value"][name].get("type")
        return None

    def value_exist(self, name):
        """Check if a value key exist inside model info."""
        return name in self._data["Value"]

    def is_enum_type(self, key):
        """Check if specific key is enum type."""
        if (value_type := self.value_type(key)) is None:
            return False
        return value_type in ("Enum", "enum")

    def value(self, name):
        """Look up information about a value.

        Return either an `EnumValue` or a `RangeValue`.
        """
        d = self._data["Value"][name]
        if d["type"] in ("Enum", "enum"):
            return EnumValue(d["option"])
        if d["type"] == "Range":
            return RangeValue(
                d["option"]["min"], d["option"]["max"], d["option"].get("step", 0)
            )
        if d["type"] == "Bit":
            bit_values = {}
            for bit in d["option"]:
                bit_values[bit["startbit"]] = {
                    "value": bit["value"],
                    "length": bit["length"],
                }
            return BitValue(bit_values)
        if d["type"] == "Reference":
            ref = d["option"][0]
            return ReferenceValue(self._data[ref])
        if d["type"] == "Boolean":
            return EnumValue({"0": BIT_OFF, "1": BIT_ON})
        if d["type"] == "String":
            return None
        raise ValueError(
            f"ModelInfo: unsupported value type {d['type']} - value: {d}",
        )

    def default(self, name):
        """Get the default value, if it exists, for a given value."""
        return self._data.get("Value", {}).get(name, {}).get("default")

    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name."""
        if not self.value_type(key):
            return None

        options = self.value(key).options
        for k, v in options.items():
            if v == name:
                return k
        return None

    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value."""
        if not self.value_type(key):
            return None

        values = self.value(key)
        if not hasattr(values, "options"):
            return None
        options = values.options
        return options.get(value, "")

    def enum_index(self, key, index):
        """Look up the friendly enum name for an indexed value."""
        return self.enum_name(key, index)

    def range_name(self, key):
        """
        Look up the value of a RangeValue.
        Not very useful other than for comprehension.
        """

        return key

    def bit_name(self, key, bit_index, value):
        """Look up the friendly name for an encoded bit value."""
        if not self.value_type(key):
            return str(value)

        options = self.value(key).options

        if not self.value_type(options[bit_index]["value"]):
            return str(value)

        enum_options = self.value(options[bit_index]["value"]).options
        return enum_options[value]

    def _get_bit_key(self, key):
        """Get bit values for a specific key."""

        def search_bit_key():
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
            bit_key = search_bit_key()
            self._bit_keys[key] = bit_key

        return bit_key

    def bit_value(self, key, values):
        """Look up the bit value for an specific key."""
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
            val += bit * (2**i)
        return str(val)

    def reference_name(self, key, value, ref_key="_comment"):
        """Look up the friendly name for an encoded reference value."""
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
        """Check that type of control is BINARY(BYTE)."""
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
    def byte_monitor_data(self):
        """Check that type of monitoring is BINARY(BYTE)."""
        return self._data["Monitoring"]["type"] == "BINARY(BYTE)"

    @property
    def hex_monitor_data(self):
        """Check that type of monitoring is BINARY(HEX)."""
        return self._data["Monitoring"]["type"] == "BINARY(HEX)"

    def decode_monitor_byte(self, data):
        """Decode binary byte encoded status data."""

        decoded = {}
        total_bytes = len(data)
        for item in self._data["Monitoring"]["protocol"]:
            key = item["value"]
            value = 0
            start_byte: int = item["startByte"]
            end_byte: int = start_byte + item["length"]
            if total_bytes >= end_byte:
                for v in data[start_byte:end_byte]:
                    value = (value << 8) + v
            decoded[key] = str(value)
        return decoded

    def decode_monitor_hex(self, data):
        """Decode binary hex encoded status data."""

        decoded = {}
        hex_list = data.decode("utf8").split(",")
        total_bytes = len(hex_list)
        for item in self._data["Monitoring"]["protocol"]:
            key = item["value"]
            value = 0
            start_byte: int = item["startByte"]
            end_byte: int = start_byte + item["length"]
            if total_bytes >= end_byte:
                for i in range(start_byte, end_byte):
                    value = (value << 8) + int(hex_list[i], 16)
            decoded[key] = str(value)
        return decoded

    @staticmethod
    def decode_monitor_json(data):
        """Decode a bytestring that encodes JSON status data."""
        return json.loads(data.decode("utf8"))

    def decode_monitor(self, data):
        """Decode status data."""

        if self.byte_monitor_data:
            return self.decode_monitor_byte(data)
        if self.hex_monitor_data:
            return self.decode_monitor_hex(data)
        return self.decode_monitor_json(data)

    @staticmethod
    def _get_current_temp_key(key: str, data):
        """
        Special case for oven current temperature, that in protocol
        is represented with a suffix "F" or "C" depending on the unit.
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
        """Decode status data."""
        if self._data["Monitoring"]["type"] != "THINQ2":
            return {}

        if key and key not in data:
            return {}

        if not (protocol := self._data["Monitoring"].get("protocol")):
            return data[key] if key else data

        decoded = {}
        if isinstance(protocol, list):
            for elem in protocol:
                if super_set := elem.get("superSet"):
                    key = elem["value"]
                    value = data
                    for ident in super_set.split("."):
                        if value is None:
                            break
                        pr_key = self._get_current_temp_key(ident, value)
                        value = value.get(pr_key)
                    if value is not None:
                        if isinstance(value, Number):
                            try:
                                value = int(value)
                            except ValueError:
                                continue
                        decoded[key] = str(value)
            return decoded

        info = data[key] if key else data
        convert_rule = self._data.get("ConvertingRule", {})
        for data_key, value_key in protocol.items():
            value = ""
            raw_value = info.get(data_key)
            if raw_value is not None:
                value = str(raw_value)
                if isinstance(raw_value, Number):
                    try:
                        value = str(int(raw_value))
                    except ValueError:
                        value = ""
                elif value_key in convert_rule:
                    value_rules = convert_rule[value_key].get(
                        "MonitoringConvertingRule", {}
                    )
                    if raw_value in value_rules:
                        value = value_rules[raw_value]
            decoded[value_key] = str(value)
        return decoded


class ModelInfoV2(ModelInfo):
    """A description of a device model's capabilities for type V2."""

    @property
    def is_info_v2(self):
        """Return the type of 'model_info' represented."""
        return True

    def as_dict(self):
        """Return the data dictionary"""
        if not self._data:
            return {}
        return self._data.copy()

    @property
    def model_type(self):
        """Return the model type."""
        return self._data.get("Info", {}).get("modelType", "")

    def config_value(self, key):
        """Get config value for a specific key."""
        return self._data.get("Config", {}).get(key, "")

    def value_type(self, name):
        """Return the value type for a specific value key."""
        if name in self._data["MonitoringValue"]:
            return self._data["MonitoringValue"][name].get("dataType")
        return None

    def is_enum_type(self, key):
        """Check if specific key is enum type."""
        if (value_type := self.value_type(key)) is None:
            return False
        return value_type in ("Enum", "enum")

    def value_exist(self, name):
        """Check if a value key exist inside model info."""
        return name in self._data["MonitoringValue"]

    def data_root(self, name):
        """Return the data root for a specific value key."""
        if name in self._data["MonitoringValue"]:
            if "dataType" in self._data["MonitoringValue"][name]:
                return self._data["MonitoringValue"][name]
            ref = self._data["MonitoringValue"][name].get("ref")
            if ref:
                return self._data.get(ref)

        return None

    def value(self, data):
        """
        Look up information about a value.
        Return either an `EnumValue` or a `RangeValue`.
        """
        data_type = data.get("dataType")
        if not data_type:
            return data
        if data_type in ("Enum", "enum"):
            return data["valueMapping"]
        if data_type in ("Range", "range"):
            return RangeValue(
                data["valueMapping"]["min"], data["valueMapping"]["max"], 1
            )
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
        if data_type in ("Boolean", "boolean"):
            ret_val = {"BOOL": True}
            ret_val.update(data["valueMapping"])
            return ret_val
        if data_type in ("String", "string"):
            return None
        raise ValueError(
            f"ModelInfoV2: unsupported value type {data_type} - value: {data}",
        )

    def default(self, name):
        """Get the default value, if it exists, for a given value."""
        data = self.data_root(name)
        if data:
            return data.get("default")

        return None

    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name."""
        data = self.data_root(key)
        if not data:
            return None

        options = self.value(data)
        for k, v in options.items():
            if (label := v.get("label")) is None:
                continue
            if label == name:
                return k
        return None

    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value."""
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
        """Look up the friendly enum name for an indexed value."""
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
        """
        Look up the value of a RangeValue.
        Not very useful other than for comprehension.
        """
        return key

    def bit_name(self, key, bit_index, value):
        """Look up the friendly name for an encoded bit value."""
        return None

    def bit_value(self, key, values):
        """
        Look up the bit value for a specific key.
        Not used in model V2.
        """
        return None

    def reference_name(self, key, value, ref_key="_comment"):
        """Look up the friendly name for an encoded reference value."""
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
        """Look up the friendly name for an encoded reference value."""
        data = self.data_root(key)
        if not data:
            return None

        return data.get("targetKey", {}).get(target, {}).get(value)

    @property
    def binary_control_data(self):
        """Check that type of control is BINARY(BYTE)."""
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

    @staticmethod
    def decode_monitor_json(data):
        """Decode a bytestring that encodes JSON status data."""
        return json.loads(data.decode("utf8"))

    def decode_monitor(self, data):
        """Decode status data."""
        return self.decode_monitor_json(data)

    def decode_snapshot(self, data, key):
        """Decode snapshot data inside payload."""
        return data.get(key)


class ModelInfoV2AC(ModelInfoV1):
    """
    A description of a device model's capabilities.
    Type V2AC and other models with 'data_type' in Value.
    """

    def __init__(self, data):
        """Initialize the class."""
        super().__init__(data)
        self._has_monitoring = "Monitoring" in data

    @staticmethod
    def valid_value_data(value_data):
        """Determine if valid Value data is in this model."""
        first_value = list(value_data.values())[0]
        if "data_type" in first_value:
            return True
        return False

    @property
    def is_info_v2(self):
        """Return the type of 'model_info' represented."""
        return True

    def value_type(self, name):
        """Return the value type for a specific value key."""
        if name in self._data["Value"]:
            return self._data["Value"][name].get("data_type")
        return None

    def value(self, name):
        """
        Look up information about a value.
        Return either an `EnumValue` or a `RangeValue`.
        """
        d = self._data["Value"][name]
        if d["data_type"] in ("Enum", "enum"):
            return EnumValue(d["value_mapping"])
        if d["data_type"] in ("Range", "range"):
            return RangeValue(
                d["value_validation"]["min"],
                d["value_validation"]["max"],
                d["value_validation"].get("step", 0),
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
        if d["data_type"] in ("String", "string"):
            return None
        if d["data_type"] in ("Number", "number"):
            return None
        raise ValueError(
            f"ModelInfoV2AC: unsupported value type {d['data_type']} - value: {d}",
        )

    def decode_snapshot(self, data, key):
        """Decode snapshot data inside payload."""
        if not key or not self._has_monitoring:
            return data
        return super().decode_snapshot(data, key)
