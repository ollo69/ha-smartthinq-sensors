"""Test SmartThinQ integration setup behavior."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_LANGUAGE, CONF_REGION, CONF_TOKEN
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.smartthinq_sensors import async_setup_entry
from custom_components.smartthinq_sensors.const import CONF_USE_API_V2, DOMAIN
from custom_components.smartthinq_sensors.wideq.core_exceptions import (
    UseOfficialAPIError,
)


async def test_setup_retries_after_generic_lg_api_error(hass):
    """Retry setup when the LG API is temporarily unavailable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REGION: "US",
            CONF_LANGUAGE: "en-US",
            CONF_TOKEN: "refresh-token",
            CONF_USE_API_V2: True,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.smartthinq_sensors.LGEAuthentication.create_client_from_token",
            new=AsyncMock(side_effect=UseOfficialAPIError("temporary API refusal")),
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)
