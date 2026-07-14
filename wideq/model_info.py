"""Model Info Classes used to map LG ThinQ device model's capabilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import namedtuple
from copy import deepcopy
import json
import logging
from numbers import Number

import xmltodict

from .const import BIT_OFF, BIT_ON

TYPE_BIT = "bit"
TYPE_BOOL = "boolean"
TYPE_ENUM = "enum"
TYPE_NUMBER = "number"
TYPE_RANGE = "range"
TYPE_REFERENCE = "reference"
TYPE_STRING = "string"

_LOGGER = logging.getLogger(__name__)


EnumValue = namedtuple("EnumValue", ["options"])
RangeValue = namedtuple("RangeValue", ["min", "max", "step"])
BitValue = namedtuple("BitValue", ["options"])
ReferenceValue = namedtuple("ReferenceValue", ["reference"])


class ModelInfo(ABC):
    """The base abstract class for a device model's capabilities."""

    @staticmethod
    def get_model_info(
        model_data: dict, sub_device: str | None = None
    ) -> ModelInfo | None:
        """Return the correct model info."""
        if sub_device is not None:
            data = {"Info": model_data["Info"], **model_data[sub_device]}
        else:
            data = model_data

        if ModelInfoV2AC.is_valid_model_data(data):
            # this is new V2 model for AC
            return ModelInfoV2AC(data)
        if ModelInfoV1.is_valid_model_data(data):
            # this is old V1 model
            return ModelInfoV1(data)
        if ModelInfoV2.is_valid_model_data(data):
            # this is new V2 model
            return ModelInfoV2(data)
        return None

    @staticmethod
    @abstractmethod
    def is_valid_model_data(model_data: dict) -> bool:
        """Determine if model data is valid for this model."""

    def __init__(self, data):
        """Initialize the class."""
        self._data = data

    @property
    @abstractmethod
    def is_info_v2(self) -> bool:
        """Return the type of 'model_info' represented."""

    def as_dict(self):
        """Return the data dictionary"""
        if not self._data:
            return {}
        return deepcopy(self._data)

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
    def value_exist(self, name) -> bool:
        """Check if a value key exist inside model info."""

    @abstractmethod
    def value(
        self, name: str, req_type: list | None = None
    ) -> EnumValue | RangeValue | BitValue | ReferenceValue | None:
        """Look up information about a name key."""

    def is_enum_type(self, key):
        """Check if specific key is enum type."""
        if (value_type := self.value_type(key)) is None:
            return False
        return value_type == TYPE_ENUM

    def enum_value(self, key, name):
        """Look up the encoded value for a friendly enum name."""
        if not (values := self.value(key, [TYPE_ENUM, TYPE_BOOL])):
            return None

        options = values.options
        for opt_key, value in options.items():
            if value == name:
                return opt_key
        return None

    def enum_name(self, key, value):
        """Look up the friendly enum name for an encoded value."""
        if not (values := self.value(key, [TYPE_ENUM, TYPE_BOOL])):
            return None

        options = values.options
        if self.value_type(key) == TYPE_BOOL:
            bool_val = options.get(value, 0)
            return BIT_ON if bool_val else BIT_OFF
        return options.get(value, "")

    def enum_index(self, key, index):
        """Look up the friendly enum name for an indexed value."""
        return self.enum_name(key, index)

    def range_name(self, key) -> str | None:
        """
        Look up the value of a RangeValue.
        Not very useful other than for comprehension.
        """
        return key

    def enum_range_values(self, key) -> list[str] | None:
        """Return a list from a range value."""
        if not (values := self.value(key, [TYPE_RANGE])):
            return None

        return [str(i) for i in range(values.min, values.max + 1, values.step)]

    def reference_values(self, key) -> dict | None:
        """Look up the reference section."""
        if not (values := self.value(key, [TYPE_REFERENCE])):
            return None

        reference: dict = values.reference
        return reference

    def reference_name(self, key, value, ref_key="_comment") -> str | None:
        """Look up the friendly name for an encoded reference value."""
        if not (values := self.value(key, [TYPE_REFERENCE])):
            return None

        str_value = str(value)
        reference = values.reference
        if str_value in reference:
            ref_value = reference[str_value]
            for key_id in (ref_key, "label"):
                if key_id in ref_value:
                    return ref_value[key_id]
            return ref_value.get("name")
        return None

    def option_keys(self, subkey: str | None = None) -> list:
        """Return a list of available option keys."""
        return []

    def bit_name(self, key, bit_index) -> str | None:
        """Look up the friendly name for an encoded bit based on the bit index."""
        return None

    def bit_index(self, key, bit_name) -> str | None:
        """Look up the start index for an encoded bit based on friendly name."""
        return None

    def bit_value(self, key, bit_name, value) -> int | None:
        """
        Look up the bit value for a specific key.
        Not used in model V2.
        """
        return None

    def option_bit_value(self, key, values, sub_key=None) -> str | None:
        """
        Look up the bit value for a specific option key.
        Not used in model V2.
        """
        return None

    def target_key(self, key, value, target) -> str | None:
        """Look up tarket key inside a value."""
        return None

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

    @property
    def monitor_type(self) -> str | None:
        """Return used monitor type."""
        return None


class ModelInfoV1(ModelInfo):
    """A description of a device model's capabilities for type V1."""

    @staticmethod
    def is_valid_model_data(model_data: dict) -> bool:
        """Determine if model data is valid for this model."""
        return "Monitoring" in model_data and "Value" in model_data

    def __init__(self, data):
        """Initialize the class."""
        super().__init__(data)
        self._monitor_type = None
        self._bit_keys = {}

    @property
    def is_info_v2(self) -> bool:
        """Return the type of 'model_info' represented."""
        return False

    @property
    def model_type(self):
        """Return the model type."""
        return self._data.get("Info", {}).get("modelType", "")

    def config_value(self, key):
        """Get config value for a specific key."""
        return self._data.get("Config", {}).get(key, "")

    def _get_data_type(self, data):
        """Return data type in specific data."""
        if "type" in data:
            return data["type"].casefold()
        return None

    def value_type(self, name):
        """Return the value type for a specific value key."""
        if value := self._data["Value"].get(name):
            return self._get_data_type(value)
        return None

    def value_exist(self, name) -> bool:
        """Check if a value key exist inside model info."""
        return name in self._data["Value"]

    def value(
        self, name: str, req_type: list | None = None
    ) -> EnumValue | RangeValue | BitValue | ReferenceValue | None:
        """Look up information about a name key."""
        if not self.value_exist(name):
            return None
        data = self._data["Value"][name]
        if not (data_type := self._get_data_type(data)):
            return None
        if req_type:
            if data_type not in req_type:
                return None

        if data_type == TYPE_ENUM:
            return EnumValue(data["option"])
        if data_type == TYPE_RANGE:
            return RangeValue(
                data["option"]["min"],
                data["option"]["max"],
                data["option"].get("step", 1),
            )
        if data_type == TYPE_BIT:
            bit_values = {}
            for bit in data["option"]:
                bit_values[bit["startbit"]] = {
                    "value": bit["value"],
                    "length": bit["length"],
                }
            return BitValue(bit_values)
        if data_type == TYPE_REFERENCE:
            ref = data["option"][0]
            return ReferenceValue(self._data[ref])
        if data_type == TYPE_BOOL:
            return EnumValue({"0": 0, "1": 1})
        if data_type == TYPE_STRING:
            return None
        raise ValueError(
            f"ModelInfo: unsupported value type {data_type} - value: {data}",
        )

    def default(self, name):
        """Get the default value, if it exists, for a given value."""
        return self._data.get("Value", {}).get(name, {}).get("default")

    def option_keys(self, subkey: str | None = None) -> list:
        """Return a list of available option keys."""
        if not (data := self._data.get("Value")):
            return []

        opt_key = "Option"
        if subkey:
            opt_key = subkey + opt_key
        ret_keys = []
        for i in range(1, 4):
            key_id = f"{opt_key}{str(i)}"
            if key_id in data:
                ret_keys.append(key_id)
        return ret_keys

    def bit_name(self, key, bit_index) -> str | None:
        """Look up the friendly name for an encoded bit based on the bit index."""
        if not (values := self.value(key, [TYPE_BIT])):
            return None

        options = values.options
        if not (bit_info := options.get(bit_index)):
            return None
        return bit_info["value"]

    def bit_index(self, key, bit_name) -> str | None:
        """Look up the start index for an encoded bit based on friendly name."""
        if not (values := self.value(key, [TYPE_BIT])):
            return None

        options = values.options
        for bit_index, bit_info in options.items():
            if bit_info["value"] == bit_name:
                return bit_index

        return None

    def bit_value(self, key, bit_name, value) -> int | None:
        """Look up the bit value for a specific key."""
        if not (values := self.value(key, [TYPE_BIT])):
            return None

        options = values.options
        for bit_index, bit_info in options.items():
            if bit_info["value"] == bit_name:
                return self._get_bit_value(value, bit_index, bit_info["length"])

        return None

    def option_bit_value(self, key, values, sub_key=None) -> str | None:
        """Look up the bit value for an specific option key."""
        bit_key = self._get_bit_key(key, sub_key)
        if not bit_key:
            return None
        value = None if not values else values.get(bit_key["option"])
        if not value:
            return "0"
        bit_val = self._get_bit_value(
            int(value), bit_key["startbit"], bit_key["length"]
        )
        return str(bit_val)

    def _get_bit_key(self, key: str, sub_key: str | None = None):
        """Get bit values for a specific key."""

        def search_bit_key(option_keys: list, data: dict | None):
            if not data:
                return {}
            for opt_key in option_keys:
                if not (option := data.get(opt_key)):
                    continue
                for opt in option.get("option", []):
                    if key != opt.get("value", ""):
                        continue
                    if (start_bit := opt.get("startbit")) is None:
                        return {}
                    return {
                        "option": opt_key,
                        "startbit": start_bit,
                        "length": opt.get("length", 1),
                    }

            return {}

        key_bit = sub_key + key if sub_key else key
        if (bit_key := self._bit_keys.get(key_bit)) is None:
            option_keys = self.option_keys(sub_key)
            bit_key = search_bit_key(option_keys, self._data.get("Value"))
            self._bit_keys[key_bit] = bit_key

        return bit_key

    @staticmethod
    def _get_bit_value(value: int, start_bit: int, length: int = 1):
        """Return bit value inside byte."""
        val = 0
        for i in range(0, length):
            bit_index = 2 ** (start_bit + i)
            bit = 1 if value & bit_index else 0
            val += bit * (2**i)
        return val

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
                control = deepcopy(control_data)  # we copy so that we can manipulate
                if ctrl_key:
                    control["cmd"] = ctrl_key
        return control

    @property
    def monitor_type(self) -> str | None:
        """Return used monitor type."""
        if self._monitor_type is None:
            self._monitor_type = self._data["Monitoring"]["type"]
        return self._monitor_type

    @property
    def byte_monitor_data(self):
        """Check that type of monitoring is BINARY(BYTE)."""
        return self.monitor_type == "BINARY(BYTE)"

    @property
    def hex_monitor_data(self):
        """Check that type of monitoring is BINARY(HEX)."""
        return self.monitor_type == "BINARY(HEX)"

    @property
    def xml_monitor_data(self):
        """Check that type of monitoring is XML."""
        return self.monitor_type == "XML"

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
                for byte_data in data[start_byte:end_byte]:
                    value = (value << 8) + byte_data
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

    def decode_monitor_xml(self, data):
        """Decode a xml that encodes status data."""

        try:
            xml_json = xmltodict.parse(data.decode("utf8"))
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to decode XML message: [%s] - error: %s", data, ex)
            return None

        main_tag: str | None = self._data["Monitoring"].get("tag")
        if not main_tag or main_tag not in xml_json:
            _LOGGER.warning(
                "Invalid root tag [%s] for XML message: [%s]", main_tag, xml_json
            )
            return None

        decoded = {}
        dev_vals = xml_json[main_tag]
        for item in self._data["Monitoring"]["protocol"]:
            tags: str = item["tag"]
            tag_list = tags.split(".")
            tag_key = tag_list[0]
            if len(tag_list) > 1:
                value_dict: dict = dev_vals[tag_key]
                tag_key = tag_list[1]
            else:
                value_dict: dict = dev_vals

            if val := value_dict.get(tag_key):
                key = item["value"]
                if isinstance(key, list):
                    if isinstance(val, str):
                        sub_val = val.split(",")
                    else:
                        sub_val = []
                    for sub_idx, sub_key in enumerate(key):
                        if not isinstance(sub_key, str):
                            continue
                        decoded[sub_key] = (
                            sub_val[sub_idx] if len(sub_val) > sub_idx else ""
                        )

                elif isinstance(key, str):
                    decoded[key] = val

        return decoded

    @staticmethod
    def decode_monitor_json(data, mon_type):
        """Decode a bytestring that encodes JSON status data."""
        try:
            return json.loads(data.decode("utf8"))
        except json.JSONDecodeError:
            _LOGGER.warning(
                "Received data with invalid format from device. Type: %s - Data: %s",
                mon_type,
                data,
            )
            return None

    def decode_monitor(self, data):
        """Decode status data."""

        if self.byte_monitor_data:
            return self.decode_monitor_byte(data)
        if self.hex_monitor_data:
            return self.decode_monitor_hex(data)
        if self.xml_monitor_data:
            return self.decode_monitor_xml(data)
        return self.decode_monitor_json(data, self.monitor_type)

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
        if self.monitor_type != "THINQ2":
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

    @staticmethod
    def is_valid_model_data(model_data: dict) -> bool:
        """Determine if model data is valid for this model."""
        return "MonitoringValue" in model_data

    @property
    def is_info_v2(self) -> bool:
        """Return the type of 'model_info' represented."""
        return True

    @property
    def model_type(self):
        """Return the model type."""
        return self._data.get("Info", {}).get("modelType", "")

    def config_value(self, key):
        """Get config value for a specific key."""
        return self._data.get("Config", {}).get(key, "")

    def _get_data_type(self, data):
        """Return data type in specific data."""
        if "dataType" in data:
            return data["dataType"].casefold()
        return None

    def value_type(self, name):
        """Return the value type for a specific value key."""
        if value := self._data["MonitoringValue"].get(name):
            return self._get_data_type(value)
        return None

    def value_exist(self, name) -> bool:
        """Check if a value key exist inside model info."""
        return name in self._data["MonitoringValue"]

    def _data_root(self, name):
        """Return the data root for a specific value key."""
        if not self.value_exist(name):
            return None
        data = self._data["MonitoringValue"][name]
        if "dataType" in data or "ref" in data:
            return data
        return None

    def value(
        self, name: str, req_type: list | None = None
    ) -> EnumValue | RangeValue | BitValue | ReferenceValue | None:
        """Look up information about a name key."""
        if not (data := self._data_root(name)):
            return None
        if not (data_type := self._get_data_type(data)):
            if "ref" not in data:
                return None
            data_type = TYPE_REFERENCE

        if req_type:
            if data_type not in req_type:
                return None

        if data_type == TYPE_ENUM:
            mapping = data["valueMapping"]
            return EnumValue(
                {k: v["label"] for k, v in mapping.items() if "label" in v}
            )
        if data_type == TYPE_RANGE:
            return RangeValue(
                data["valueMapping"]["min"],
                data["valueMapping"]["max"],
                data["valueMapping"].get("step", 1),
            )
        if data_type == TYPE_REFERENCE:
            ref = data["ref"]
            return ReferenceValue(self._data.get(ref))
        if data_type == TYPE_BOOL:
            if "valueMapping" in data:
                mapping = data["valueMapping"]
                return EnumValue({k: v.get("index", 0) for k, v in mapping.items()})
            return EnumValue({0: 0, 1: 1})
        if data_type == TYPE_STRING:
            return None
        raise ValueError(
            f"ModelInfoV2: unsupported value type {data_type} - value: {data}",
        )

    def default(self, name):
        """Get the default value, if it exists, for a given value."""
        if data := self._data_root(name):
            return data.get("default")

        return None

    def enum_index(self, key, index) -> str | None:
        """Look up the friendly enum name for an indexed value."""
        if not (data := self._data_root(key)):
            return None
        if not (data_type := self._get_data_type(data)):
            return None
        if data_type != TYPE_ENUM:
            return None

        mapping = data["valueMapping"]
        options = {
            v["index"]: v["label"]
            for v in mapping.values()
            if "index" in v and "label" in v
        }
        return options.get(index, "")

    def target_key(self, key, value, target) -> str | None:
        """Look up target key inside a value."""
        if not (data := self._data_root(key)):
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
                control = deepcopy(control_data)  # we copy so that we can manipulate
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

    @staticmethod
    def is_valid_model_data(model_data: dict) -> bool:
        """Determine if model data is valid for this model."""
        if "ControlDevice" in model_data and "Value" in model_data:
            return True
        if "Monitoring" in model_data and "Value" in model_data:
            value_data = model_data["Value"]
            first_value = list(value_data.values())[0]
            if "data_type" in first_value and "type" not in first_value:
                return True
        return False

    def __init__(self, data):
        """Initialize the class."""
        super().__init__(data)
        self._has_monitoring = "Monitoring" in data

    @property
    def is_info_v2(self) -> bool:
        """Return the type of 'model_info' represented."""
        return True

    def _get_data_type(self, data):
        """Return data type in specific data."""
        if "data_type" in data:
            return data["data_type"].casefold()
        return None

    def value_type(self, name):
        """Return the value type for a specific value key."""
        if value := self._data["Value"].get(name):
            return self._get_data_type(value)
        return None

    def value(
        self, name: str, req_type: list | None = None
    ) -> EnumValue | RangeValue | BitValue | ReferenceValue | None:
        """Look up information about a name key."""
        if not self.value_exist(name):
            return None
        data = self._data["Value"][name]
        if not (data_type := self._get_data_type(data)):
            return None
        if req_type:
            if data_type not in req_type:
                return None

        if data_type == TYPE_ENUM:
            return EnumValue(data["value_mapping"])
        if data_type == TYPE_RANGE:
            return RangeValue(
                data["value_validation"]["min"],
                data["value_validation"]["max"],
                data["value_validation"].get("step", 0),
            )
        if data_type in (TYPE_STRING, TYPE_NUMBER, TYPE_REFERENCE):
            return None
        raise ValueError(
            f"ModelInfoV2AC: unsupported value type {data['data_type']} - value: {data}",
        )

    def decode_snapshot(self, data, key):
        """Decode snapshot data inside payload."""
        if not key or not self._has_monitoring:
            return data
        return super().decode_snapshot(data, key)
