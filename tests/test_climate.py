"""Test the SmartThinQ sensors climate platform."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.components.climate.const import FAN_AUTO

from custom_components.smartthinq_sensors.climate import (
    FAN_MODE_LOOKUP,
    ACFanSpeed,
    LGEACClimate,
)


def _mock_ac_climate(fan_speeds: list[str]) -> LGEACClimate:
    """Create a minimal mocked AC climate entity."""
    climate = LGEACClimate.__new__(LGEACClimate)
    climate._api = SimpleNamespace(async_set_updated=Mock())
    climate._device = SimpleNamespace(
        fan_speeds=fan_speeds,
        set_fan_speed=AsyncMock(),
    )
    return climate


def test_nature_fan_speed_maps_to_auto() -> None:
    """Test LG nature fan speed is exposed as HA auto fan mode."""
    assert FAN_MODE_LOOKUP[ACFanSpeed.NATURE.name] == FAN_AUTO


async def test_set_auto_fan_mode_prefers_nature_when_supported() -> None:
    """Test setting auto uses LG nature fan speed when available."""
    climate = _mock_ac_climate([ACFanSpeed.LOW.name, ACFanSpeed.NATURE.name])

    await climate.async_set_fan_mode(FAN_AUTO)

    climate._device.set_fan_speed.assert_awaited_once_with(ACFanSpeed.NATURE.name)
    climate._api.async_set_updated.assert_called_once_with()


async def test_set_auto_fan_mode_uses_auto_when_nature_is_unsupported() -> None:
    """Test setting auto keeps using LG auto fan speed without nature support."""
    climate = _mock_ac_climate([ACFanSpeed.LOW.name, ACFanSpeed.AUTO.name])

    await climate.async_set_fan_mode(FAN_AUTO)

    climate._device.set_fan_speed.assert_awaited_once_with(ACFanSpeed.AUTO.name)
    climate._api.async_set_updated.assert_called_once_with()
