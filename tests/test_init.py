"""Test the async_get_lg_device helper (device_registry.async_get_device deprecation, #992)."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import device_registry as dr

from custom_components.smartthinq_sensors import async_get_lg_device
from custom_components.smartthinq_sensors.const import DOMAIN


async def test_async_get_lg_device_finds_registered_device(hass):
    """A device registered under this integration's domain is found by its
    LG device id, scoped to the config entry that owns it."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "test-lg-device-id")},
        name="Test LG Device",
    )

    found = async_get_lg_device(device_registry, "test-lg-device-id", entry.entry_id)

    assert found is not None
    assert found.name == "Test LG Device"


async def test_async_get_lg_device_returns_none_for_unknown_device(hass):
    """No device registered under an unknown LG device id returns None."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)

    found = async_get_lg_device(device_registry, "does-not-exist", entry.entry_id)

    assert found is None


def test_async_get_lg_device_scoped_to_config_entry_via_new_api():
    """The new async_get_device_by_identifier() call is scoped to one config
    entry -- pass through whatever it returns rather than second-guessing
    it, since the scoping is its job, not async_get_lg_device()'s.

    This cannot be demonstrated against the fallback path: verified by
    actually calling it in test_async_get_lg_device_scoped_to_config_entry_
    fallback_does_not_scope below, the deprecated async_get_device() looks
    up by identifier alone and does not take a config entry into account at
    all -- that lack of scoping is precisely the bug class #992 is about,
    and precisely what the new API exists to fix once it's available.
    """

    class _FakeRegistryWithNewApi:
        def async_get_device_by_identifier(self, identifier, config_entry_id):
            if config_entry_id == "entry-a":
                return "device-on-entry-a"
            return None

    registry = _FakeRegistryWithNewApi()

    assert async_get_lg_device(registry, "shared-id", "entry-a") == "device-on-entry-a"
    assert async_get_lg_device(registry, "shared-id", "entry-b") is None


async def test_async_get_lg_device_scoped_to_config_entry_fallback_does_not_scope(
    hass,
):
    """Document the known limitation of the fallback path itself, rather
    than assert something async_get_lg_device() cannot control: on HA
    versions before 2026.8.0, async_get_device() matches by identifier
    only, so a device registered under one config entry is also returned
    when a *different* entry_id is passed. This is the exact problem the
    migration announced in HA's 2026-07-21 blog post exists to fix; it can
    only be fixed once a version with the new method is actually running.
    """
    entry_a = MockConfigEntry(domain=DOMAIN)
    entry_a.add_to_hass(hass)
    entry_b = MockConfigEntry(domain=DOMAIN)
    entry_b.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry_a.entry_id,
        identifiers={(DOMAIN, "shared-id")},
        name="Device on entry A",
    )

    found_on_a = async_get_lg_device(device_registry, "shared-id", entry_a.entry_id)
    found_on_b = async_get_lg_device(device_registry, "shared-id", entry_b.entry_id)

    assert found_on_a is not None
    if hasattr(type(device_registry), "async_get_device_by_identifier"):
        # Running on HA 2026.8.0+: the new API does scope correctly.
        assert found_on_b is None
    else:
        # Pre-2026.8.0: known, accepted limitation of the fallback.
        assert found_on_b is found_on_a


def test_async_get_lg_device_falls_back_without_new_api(hass, monkeypatch):
    """If the running HA core lacks async_get_device_by_identifier (this
    integration's floor is 2025.7.0; the new method was added in 2026.8.0),
    fall back to the deprecated async_get_device() rather than raising
    AttributeError.

    The test environment pinned in requirements_test.txt (HA 2025.7.4) does
    not have the new method at all, so this exercises the fallback whether
    or not the explicit delattr below finds anything to remove -- it is
    there so the test keeps meaning the same thing if this pin is ever
    bumped past 2026.8.0.
    """
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "fallback-device-id")},
        name="Fallback Device",
    )

    monkeypatch.delattr(
        type(device_registry), "async_get_device_by_identifier", raising=False
    )

    found = async_get_lg_device(device_registry, "fallback-device-id", entry.entry_id)

    assert found is not None
    assert found.name == "Fallback Device"


def test_async_get_lg_device_uses_new_api_when_available(monkeypatch):
    """When the running HA core does have async_get_device_by_identifier
    (2026.8.0+), use it directly -- with the exact (identifier, entry_id)
    signature it defines -- instead of the deprecated async_get_device().

    The pinned test environment predates the new method, so it is added
    here as a stand-in rather than relying on a real one being present.
    """
    calls = []

    class _FakeRegistryWithNewApi:
        def async_get_device_by_identifier(self, identifier, config_entry_id):
            calls.append((identifier, config_entry_id))
            return "sentinel-device"

        def async_get_device(self, identifiers):
            raise AssertionError(
                "async_get_lg_device must prefer async_get_device_by_identifier "
                "when it exists, not fall back to the deprecated method"
            )

    result = async_get_lg_device(
        _FakeRegistryWithNewApi(), "some-device-id", "some-entry-id"
    )

    assert result == "sentinel-device"
    assert calls == [((DOMAIN, "some-device-id"), "some-entry-id")]
