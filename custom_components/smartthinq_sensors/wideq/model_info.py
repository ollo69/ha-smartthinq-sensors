"""Model Info Classes used to map LG ThinQ device model's capabilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import namedtuple
import json
from numbers import Number

from .const import BIT_OFF, BIT_ON

TYPE_BIT = "bit"
TYPE_BOOL = "boolean"
TYPE_ENUM = "enum"
TYPE_NUMBER = "number"
TYPE_RANGE = "range"
TYPE_REFERENCE = "reference"
TYPE_STRING = "string"


EnumValue = namedtuple("EnumValue", ["options"])
RangeValue = namedtuple("RangeValue", ["min", "max", "step"])
BitValue = namedtuple("BitValue", ["options"])
ReferenceValue = namedtuple("ReferenceValue", ["reference"])


class ModelInfo(ABC):
    """The base abstract class for a device model's capabilities."""

    @staticmethod
    def get_model_info(model_data: dict) -> ModelInfo | None:
        """Return the correct model info."""
        if ModelInfoV2AC.is_valid_model_data(model_data):
            # this is new V2 model for AC
            return ModelInfoV2AC(model_data)
        if ModelInfoV1.is_valid_model_data(model_data):
            # this is old V1 model
            return ModelInfoV1(model_data)
        if ModelInfoV2.is_valid_model_data(model_data):
            # this is new V2 model
            return ModelInfoV2(model_data)
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
        return self._data.copy()

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

    def bit_name(self, key, bit_index, value) -> str | None:
        """Look up the friendly name for an encoded bit value."""
        return None

    def bit_value(self, key, values) -> str | None:
        """
        Look up the bit value for a specific key.
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


class ModelInfoV1(ModelInfo):
    """A description of a device model's capabilities for type V1."""

    @staticmethod
    def is_valid_model_data(model_data: dict) -> bool:
        """Determine if model data is valid for this model."""
        return "Monitoring" in model_data and "Value" in model_data

    def __init__(self, data):
        """Initialize the class."""
        super().__init__(data)
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
                data["option"].get("step", 0),
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
            return EnumValue({"0": BIT_OFF, "1": BIT_ON})
        if data_type == TYPE_STRING:
            return None
        raise ValueError(
            f"ModelInfo: unsupported value type {data_type} - value: {data}",
        )

    def default(self, name):
        """Get the default value, if it exists, for a given value."""
        return self._data.get("Value", {}).get(name, {}).get("default")

    def bit_name(self, key, bit_index, value) -> str | None:
        """Look up the friendly name for an encoded bit value."""
        if not (values := self.value(key, [TYPE_BIT])):
            return str(value)

        options = values.options
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

    def bit_value(self, key, values) -> str | None:
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
                data["valueMapping"]["min"], data["valueMapping"]["max"], 1
            )
        if data_type == TYPE_REFERENCE:
            ref = data["ref"]
            return ReferenceValue(self._data.get(ref))
        if data_type == TYPE_BOOL:
            return EnumValue({0: BIT_OFF, 1: BIT_ON})
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
        """Look up tarket key inside a value."""
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
