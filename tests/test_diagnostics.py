"""Test diagnostics.py's threading of config_entry_id through to device lookup (#992)."""

from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import device_registry as dr

from custom_components.smartthinq_sensors.const import DOMAIN, LGE_DEVICES
from custom_components.smartthinq_sensors.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.smartthinq_sensors.wideq.device_info import DeviceType


async def test_async_get_config_entry_diagnostics_with_no_devices(hass):
    """Smoke test: config_entry_id threads through _async_devices_as_dict
    without error even when there are no LG devices registered yet."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[LGE_DEVICES] = {}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result[LGE_DEVICES] == {}
    assert "entry" in result


def _fake_lge_device(lg_device_id: str) -> SimpleNamespace:
    """The attributes _async_devices_as_dict reads from a wrapped LG device."""
    return SimpleNamespace(
        unique_id=f"{lg_device_id}-unique",
        device=SimpleNamespace(
            device_info=SimpleNamespace(
                device_id=lg_device_id,
                as_dict=lambda: {"deviceId": lg_device_id},
            ),
            model_info=SimpleNamespace(as_dict=lambda: {}),
            status=None,
        ),
    )


async def test_async_get_config_entry_diagnostics_looks_up_device_by_entry(
    hass, monkeypatch
):
    """With a registered LG device, diagnostics must look it up through
    async_get_device_by_identifier() with this config entry's id.

    On HA 2026.8.0+ the real method is wrapped to record its arguments. The
    pinned test environment (HA 2025.7.4) predates it, so there a stand-in
    is added to DeviceRegistry that records the arguments and then resolves
    the device with the old lookup, restricted to that config entry.
    """
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "lg-device-1")},
        name="LG Washer",
    )
    hass.data.setdefault(DOMAIN, {})[LGE_DEVICES] = {
        DeviceType.WASHER: [_fake_lge_device("lg-device-1")]
    }

    calls = []
    registry_cls = type(device_registry)
    real_new_api = getattr(registry_cls, "async_get_device_by_identifier", None)
    old_api = registry_cls.async_get_device

    def _recording_new_api(self, identifier, config_entry_id):
        calls.append((identifier, config_entry_id))
        if real_new_api is not None:
            return real_new_api(self, identifier, config_entry_id)
        device = old_api(self, {identifier})
        if device is None or config_entry_id not in device.config_entries:
            return None
        return device

    monkeypatch.setattr(
        registry_cls,
        "async_get_device_by_identifier",
        _recording_new_api,
        raising=False,
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert calls == [((DOMAIN, "lg-device-1"), entry.entry_id)]
    ha_info = result[LGE_DEVICES][DeviceType.WASHER.name]["lg-device-1-unique"][
        "home_assistant"
    ]
    assert ha_info["name"] == "LG Washer"
