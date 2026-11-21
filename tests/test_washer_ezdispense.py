"""Test the washer features reported by compatible ThinQ2 snapshots."""

from unittest.mock import Mock

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfVolume

from custom_components.smartthinq_sensors.sensor import WASH_DEV_SENSORS, LGESensor
from custom_components.smartthinq_sensors.wideq.const import WashDeviceFeatures
from custom_components.smartthinq_sensors.wideq.device_info import (
    DeviceInfo,
    DeviceType,
)
from custom_components.smartthinq_sensors.wideq.devices.washerDryer import (
    WMDevice,
    WMStatus,
)
from custom_components.smartthinq_sensors.wideq.model_info import ModelInfoV2


def enum_values(**labels: str) -> dict:
    """Create the enum schema used by ThinQ2 model profiles."""
    return {
        "dataType": "enum",
        "valueMapping": {value: {"label": label} for value, label in labels.items()},
    }


@pytest.fixture
def washer_model() -> dict:
    """Describe the reported fields without device or account identifiers."""
    range_ml = {"dataType": "range", "valueMapping": {"min": 9, "max": 150}}
    return {
        "MonitoringValue": {
            "ezCSDetergentSetVal": enum_values(
                EZCSDT_OFF="@WM_EDD_NOT_USE_W",
                EZCSDT_LESS="@WM_EDD_LESS_W",
                EZCSDT_NORMAL="@WM_EDD_NORMAL_W",
                EZCSDT_MORE="@WM_EDD_MORE_W",
            ),
            "ezCSSoftenerSetVal": enum_values(
                EZCSSO_OFF="@WM_EDD_NOT_USE_W", EZCSSO_NORMAL="@WM_EDD_NORMAL_W"
            ),
            "ezDetergentAmount": range_ml,
            "ezSoftenerAmount": range_ml,
            "ezDispenseNotation": enum_values(
                ezDisNotation_ml="ml", ezDisNotation_oz="oz"
            ),
            "soilWash": enum_values(SOILWASH_NORMAL="Normal"),
        }
    }


def read_features(model: dict, snapshot: dict) -> dict:
    """Run the washer decoder over the supplied model and snapshot."""
    device = WMDevice(
        Mock(),
        DeviceInfo({"deviceId": "test-washer", "deviceType": DeviceType.WASHER}),
    )
    device._model_info = ModelInfoV2(model)
    return WMStatus(device, snapshot).device_features


def test_reads_separate_dispense_modes_and_configured_doses(washer_model: dict) -> None:
    """A saved dose remains meaningful when automatic dispensing is off."""
    features = read_features(
        washer_model,
        {
            "ezCSDetergentSetVal": "EZCSDT_OFF",
            "ezCSSoftenerSetVal": "EZCSSO_NORMAL",
            "ezDetergentAmount": 42.0,
            "ezSoftenerAmount": "30",
            "ezDispenseNotation": "ezDisNotation_ml",
            "soilWash": "SOILWASH_NORMAL",
        },
    )
    assert features[WashDeviceFeatures.DETERGENT_DISPENSE_MODE] == "off"
    assert features[WashDeviceFeatures.SOFTENER_DISPENSE_MODE] == "normal"
    assert features[WashDeviceFeatures.DETERGENT_DOSE] == 42
    assert features[WashDeviceFeatures.SOFTENER_DOSE] == 30
    assert features[WashDeviceFeatures.WASH_MODE] == "Normal"


@pytest.mark.parametrize("value", [None, "", "unknown", True, 0, 151, "nan"])
def test_invalid_dose_is_unknown(washer_model: dict, value: object) -> None:
    """Invalid or out-of-range quantities leave the sensor unknown."""
    features = read_features(
        washer_model,
        {"ezDetergentAmount": value, "ezDispenseNotation": "ezDisNotation_ml"},
    )
    assert features[WashDeviceFeatures.DETERGENT_DOSE] is None


@pytest.mark.parametrize("notation", [None, "ezDisNotation_oz"])
def test_nonmetric_or_unknown_notation_is_not_labeled_ml(
    washer_model: dict, notation: str | None
) -> None:
    """Leave quantity unknown when its scale cannot be inferred."""
    features = read_features(
        washer_model,
        {"ezDetergentAmount": 42, "ezDispenseNotation": notation},
    )
    assert features[WashDeviceFeatures.DETERGENT_DOSE] is None


def test_unsupported_models_do_not_advertise_new_features() -> None:
    """A washer without the relevant model fields keeps its existing sensors."""
    features = read_features({"MonitoringValue": {}}, {})
    assert WashDeviceFeatures.WASH_MODE not in features
    assert WashDeviceFeatures.DETERGENT_DOSE not in features
    assert WashDeviceFeatures.SOFTENER_DISPENSE_MODE not in features


def test_configured_dose_entity_exposes_its_volume_and_readable_name(
    washer_model: dict,
) -> None:
    """Expose the decoded milliliter setting as a read-only HA sensor."""
    features = read_features(
        washer_model,
        {"ezDetergentAmount": 42, "ezDispenseNotation": "ezDisNotation_ml"},
    )
    key = WashDeviceFeatures.DETERGENT_DOSE
    description = next(sensor for sensor in WASH_DEV_SENSORS if sensor.key == key)
    api = Mock(available=True, unique_id="test-washer")
    api.state.device_features = features
    sensor = LGESensor(api, description)

    assert sensor.native_value == 42
    assert sensor.native_unit_of_measurement == UnitOfVolume.MILLILITERS
    assert sensor.device_class == SensorDeviceClass.VOLUME
    assert sensor.translation_key == key
