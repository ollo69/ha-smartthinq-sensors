"""Regression tests for setup retries and platform lifecycle."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_CLIENT_ID, CONF_REGION, CONF_TOKEN, Platform
from homeassistant.util import dt as dt_util

from custom_components.smartthinq_sensors import AUTH_RETRY
from custom_components.smartthinq_sensors.const import (
    CONF_LANGUAGE,
    CONF_SCAN_INTERVAL,
    CONF_USE_API_V2,
    DOMAIN,
)
from custom_components.smartthinq_sensors.wideq.core_exceptions import (
    InvalidCredentialError,
    UseOfficialAPIError,
)


@pytest.fixture
def entry(hass):
    """Create an entry without contacting LG."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REGION: "US",
            CONF_LANGUAGE: "en-US",
            CONF_USE_API_V2: True,
            CONF_TOKEN: "test-token",
            CONF_CLIENT_ID: "test-client",
        },
        options={CONF_SCAN_INTERVAL: 120},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize(
    "failure", ["client", "client_repeated", "auth", "devices", "empty_discovery"]
)
async def test_setup_retry_then_recovery(hass, entry, failure, freezer):
    """Retry through HA, set up the real number platform once, and unload it."""
    client = AsyncMock()
    client.has_devices = True
    create = AsyncMock(return_value=client)
    discover = AsyncMock(return_value=({}, {}, {}))
    if failure == "client_repeated":
        create.side_effect = [
            UseOfficialAPIError("temporary rejection"),
            UseOfficialAPIError("still unavailable"),
            client,
        ]
    elif failure == "client":
        create.side_effect = [UseOfficialAPIError("temporary rejection"), client]
    elif failure == "auth":
        create.side_effect = [InvalidCredentialError("temporary rejection"), client]
    elif failure == "devices":
        discover.side_effect = [
            UseOfficialAPIError("temporary rejection"),
            ({}, {}, {}),
        ]
    else:
        discover.side_effect = [({}, {}, None), ({}, {}, {})]

    with (
        patch(
            "custom_components.smartthinq_sensors.LGEAuthentication.create_client_from_token",
            create,
        ),
        patch("custom_components.smartthinq_sensors.lge_devices_setup", discover),
        # Exercise real forwarding and real number setup, not a mocked forwarder.
        # The appliance platforms have no devices in this test.
        patch(
            "custom_components.smartthinq_sensors.SMARTTHINQ_PLATFORMS",
            [Platform.NUMBER],
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert hass.states.get("number.scan_interval") is None
        if failure in ("devices", "empty_discovery"):
            client.close.assert_awaited_once()
        else:
            client.close.assert_not_awaited()

        # Let HA's own retry callback run; do not call the integration directly.
        if failure == "client_repeated":
            freezer.tick(timedelta(seconds=60))
            async_fire_time_changed(hass, dt_util.utcnow())
            await hass.async_block_till_done(wait_background_tasks=True)
            assert entry.state is ConfigEntryState.SETUP_RETRY
            assert hass.states.get("number.scan_interval") is None

        freezer.tick(timedelta(seconds=60))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.state is ConfigEntryState.LOADED
        state = hass.states.get("number.scan_interval")
        assert state is not None
        assert float(state.state) == 120
        assert AUTH_RETRY not in hass.data[DOMAIN]
        assert create.await_count == (3 if failure == "client_repeated" else 2)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        state = hass.states.get("number.scan_interval")
        assert state is not None
        assert state.state == "unavailable"
        assert state.attributes["restored"]
        assert client.close.await_count == (
            2 if failure in ("devices", "empty_discovery") else 1
        )


async def test_unload_cancels_setup_retry(hass, entry):
    """Unloading an entry waiting for LG must cancel HA's pending retry."""
    create = AsyncMock(side_effect=UseOfficialAPIError("temporary rejection"))
    with patch(
        "custom_components.smartthinq_sensors.LGEAuthentication.create_client_from_token",
        create,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert await hass.config_entries.async_unload(entry.entry_id)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
        await hass.async_block_till_done(wait_background_tasks=True)
        create.assert_awaited_once()
