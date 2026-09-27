"""Tests for wideq core utilities."""

from types import SimpleNamespace

from custom_components.smartthinq_sensors.wideq.core_util import TempUnitConversion

C2F_LUT = {"22": 72, "22.5": 72, "23": 73, "23.5": 74, "24": 75}


class _ModelInfo:
    """Minimal model info stub exposing a TempCelToFah mapping."""

    def value(self, name):
        assert name == "TempCelToFah"
        return SimpleNamespace(options=C2F_LUT)


def test_c2f_uses_lut():
    """Values in the model LUT use the LG mapping."""
    conv = TempUnitConversion()
    assert conv.c2f(23, _ModelInfo()) == 73
    assert conv.c2f(23.5, _ModelInfo()) == 74


def test_c2f_converts_values_missing_from_lut():
    """Values not in the LUT are converted instead of returned as Celsius."""
    conv = TempUnitConversion()
    assert conv.c2f(22.7, _ModelInfo()) == 73
    assert conv.c2f(17.2, _ModelInfo()) == 63
    assert conv.c2f(23.7, _ModelInfo()) == 75


def test_c2f_none():
    """A missing value stays missing."""
    assert TempUnitConversion().c2f(None, _ModelInfo()) is None
