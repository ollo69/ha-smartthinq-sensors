"""Test the SmartThinQ sensors setup retry."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import CONF_CLIENT_ID, CONF_REGION, CONF_TOKEN
from homeassistant.util import dt as dt_util

from custom_components.smartthinq_sensors import SETUP_RETRY_DELAY
from custom_components.smartthinq_sensors.const import (
    CONF_LANGUAGE,
    CONF_USE_API_V2,
    DOMAIN,
)
from custom_components.smartthinq_sensors.wideq.core_exceptions import (
    UseOfficialAPIError,
)


async def test_setup_failure_schedules_reload(hass):
    """A generic LG API error must not leave the entry loaded forever."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REGION: "US",
            CONF_LANGUAGE: "en-US",
            CONF_USE_API_V2: True,
            CONF_TOKEN: "test-token",
            CONF_CLIENT_ID: "abcde",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smartthinq_sensors.LGEAuthentication.create_client_from_token",
        AsyncMock(side_effect=UseOfficialAPIError("9006")),
    ), patch.object(
        hass.config_entries, "async_schedule_reload"
    ) as schedule_reload:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        schedule_reload.assert_not_called()

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=SETUP_RETRY_DELAY + 1)
        )
        await hass.async_block_till_done()
        schedule_reload.assert_called_once_with(entry.entry_id)
