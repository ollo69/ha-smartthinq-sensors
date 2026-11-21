"""Test supported washer snapshot attributes through the default HA sensor."""

from unittest.mock import Mock

import pytest

from custom_components.smartthinq_sensors.device_helpers import LGEWashDevice
from custom_components.smartthinq_sensors.sensor import WASH_DEV_SENSORS, LGESensor
from custom_components.smartthinq_sensors.wideq.device_info import (
    DeviceInfo,
    DeviceType,
)
from custom_components.smartthinq_sensors.wideq.devices.washerDryer import (
    WMDevice,
    WMStatus,
)
from custom_components.smartthinq_sensors.wideq.model_info import ModelInfoV2


@pytest.fixture
def washer_model() -> dict:
    """Describe the two separate ThinQ2 course slots and the run state."""
    return {
        "Config": {
            "courseType": "currentCycle",
            "smartCourseType": "selectedSmartCycle",
            "downloadedCourseType": "storedDownload",
        },
        "MonitoringValue": {
            "state": {
                "dataType": "enum",
                "valueMapping": {"RUNNING": {"label": "STATE_RUNNING"}},
            },
            "currentCycle": {"ref": "Course"},
            "selectedSmartCycle": {"ref": "SmartCourse"},
            "storedDownload": {"ref": "SmartCourse"},
        },
        "Course": {"COTTON": {"name": "Cotton"}},
        "SmartCourse": {
            "BABYCARE": {"name": "Baby Care"},
            "RINSESPIN": {"name": "Rinse + Spin"},
        },
    }


def make_sensor(
    model: dict, snapshot: dict, *, device_type: DeviceType = DeviceType.WASHER
) -> LGESensor:
    """Construct the actual primary HA sensor around a ThinQ2 snapshot."""
    device = WMDevice(
        Mock(), DeviceInfo({"deviceId": "test-washer", "deviceType": device_type})
    )
    device._model_info = ModelInfoV2(model)
    state = WMStatus(device, {"state": "RUNNING", **snapshot})
    api = Mock(device=device, state=state, unique_id="test-washer")
    api.available_features = device.available_features
    return LGESensor(api, WASH_DEV_SENSORS[0], LGEWashDevice(api))


@pytest.mark.parametrize(
    ("drawer", "indicator", "drawer_state", "indicator_state"),
    [
        ("ezDisDrawer_CLOSE", "AIDDLed_ON", "closed", "on"),
        ("ezDisDrawer_OPEN", "AIDDLed_OFF", "open", "off"),
    ],
)
def test_exposes_drawer_and_ai_dd_states(
    washer_model: dict,
    drawer: str,
    indicator: str,
    drawer_state: str,
    indicator_state: str,
) -> None:
    """Report the drawer, dispenser type and indicator independently."""
    sensor = make_sensor(
        washer_model,
        {
            "ezDispenseDrawerState": drawer,
            "ezDispenseType": "EZD_DETERGENT_SOFTENER",
            "AIDDLed": indicator,
        },
    )
    attrs = sensor.extra_state_attributes
    assert attrs["ezdispense_drawer"] == drawer_state
    assert attrs["ezdispense_type"] == "detergent_softener"
    assert attrs["ai_dd_indicator"] == indicator_state


def test_exposes_downloaded_course_separately(washer_model: dict) -> None:
    """Resolve the stored course even when both selected programs differ."""
    sensor = make_sensor(
        washer_model,
        {
            "currentCycle": "COTTON",
            "selectedSmartCycle": "BABYCARE",
            "storedDownload": "RINSESPIN",
        },
    )
    attrs = sensor.extra_state_attributes
    assert attrs["current_course"] == "Cotton"
    assert attrs["downloaded_course"] == "Rinse + Spin"


def test_downloaded_course_uses_model_name_when_translation_is_missing(
    washer_model: dict,
) -> None:
    """Use the model's readable description when LG's language pack lacks a key."""
    washer_model["SmartCourse"]["RINSESPIN"] = {
        "name": "@WM_WW_FL_SMARTCOURSE_RINSE_SPIN_W",
        "_comment": "Rinse + Spin",
    }
    sensor = make_sensor(washer_model, {"storedDownload": "RINSESPIN"})
    assert sensor.extra_state_attributes["downloaded_course"] == "Rinse + Spin"


def test_does_not_use_selected_smart_course_as_download(washer_model: dict) -> None:
    """An unset download slot must not substitute the selected program."""
    sensor = make_sensor(
        washer_model,
        {"selectedSmartCycle": "BABYCARE", "storedDownload": "NOT_SELECTED"},
    )
    assert "downloaded_course" not in sensor.extra_state_attributes


def test_preserves_energy_scale_and_zero(washer_model: dict) -> None:
    """Publish only the two reported values without conversions."""
    sensor = make_sensor(
        washer_model, {"periodicEnergyData": 0, "accumulatedEnergyData": "591"}
    )
    attrs = sensor.extra_state_attributes
    assert attrs["periodic_energy_raw"] == 0
    assert attrs["accumulated_energy_raw"] == 591


def test_exposes_numeric_weather_inputs(washer_model: dict) -> None:
    """Accept numeric strings while keeping the two washing indexes distinct."""
    sensor = make_sensor(
        washer_model,
        {
            "dnn_temp": "-2",
            "dnn_humidity": "74",
            "dnn_precipitationProbability": "1",
            "dnn_dust": "18",
            "dnn_washingIndex": "80",
            "washingIndex": 75,
        },
    )
    attrs = sensor.extra_state_attributes
    assert attrs["weather_temperature"] == -2
    assert attrs["weather_humidity"] == 74
    assert attrs["weather_precipitation_probability"] == 1
    assert attrs["weather_dust"] == 18
    assert attrs["weather_washing_index"] == 80
    assert attrs["washing_index"] == 75


@pytest.mark.parametrize("value", [None, "-", "", True, "nan", "inf", {}, []])
def test_omits_invalid_numeric_readings(washer_model: dict, value: object) -> None:
    """Placeholders and invalid values must not become telemetry."""
    sensor = make_sensor(washer_model, {"dnn_dust": value})
    assert "weather_dust" not in sensor.extra_state_attributes


def test_omits_unrecognized_enum_states(washer_model: dict) -> None:
    """Do not interpret unknown tokens as closed, off, or a dispenser type."""
    sensor = make_sensor(
        washer_model,
        {
            "ezDispenseDrawerState": "unknown",
            "ezDispenseType": "DO_NOT_CARE",
            "AIDDLed": {},
        },
    )
    attrs = sensor.extra_state_attributes
    assert {"ezdispense_drawer", "ezdispense_type", "ai_dd_indicator"}.isdisjoint(attrs)


def test_dryer_does_not_publish_washer_attributes(washer_model: dict) -> None:
    """Keep the washer telemetry scope when using the shared dryer decoder."""
    sensor = make_sensor(
        washer_model, {"accumulatedEnergyData": 591}, device_type=DeviceType.DRYER
    )
    assert "accumulated_energy_raw" not in sensor.extra_state_attributes
