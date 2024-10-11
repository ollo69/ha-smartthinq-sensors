"""Test the SmartThinQ sensors config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (
    CONF_BASE,
    CONF_CLIENT_ID,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_TOKEN,
    CONF_USERNAME,
)

from custom_components.smartthinq_sensors.const import (
    CONF_LANGUAGE,
    CONF_OAUTH2_URL,
    CONF_USE_API_V2,
    CONF_USE_REDIRECT,
    DOMAIN,
)
from custom_components.smartthinq_sensors.wideq.core_exceptions import (
    AuthenticationError,
    InvalidCredentialError,
)

TEST_USER = "test-email@test-domain.com"
TEST_TOKEN = "test-token"
TEST_URL = "test-url"
TEST_CLIENT_ID = "abcde"

CONFIG_DATA = {
    CONF_USERNAME: TEST_USER,
    CONF_PASSWORD: "test-password",
    CONF_REGION: "US",
    CONF_LANGUAGE: "en",
    CONF_USE_REDIRECT: False,
}
CONFIG_RESULT = {
    CONF_REGION: "US",
    CONF_LANGUAGE: "en-US",
    CONF_USE_API_V2: True,
    CONF_TOKEN: TEST_TOKEN,
    CONF_CLIENT_ID: TEST_CLIENT_ID,
    CONF_OAUTH2_URL: TEST_URL,
}


class MockClient:
    """Mock wideq ClientAsync."""

    def __init__(self, has_devices=True):
        """Initialize a fake client to test config flow."""
        self.has_devices = has_devices
        self.client_id = TEST_CLIENT_ID

    async def close(self):
        """Fake close method."""
        return


@pytest.fixture(name="connect")
def mock_controller_connect():
    """Mock a successful connection."""
    with patch(
        "custom_components.smartthinq_sensors.config_flow.LGEAuthentication"
    ) as service_mock:
        service_mock.return_value.get_oauth_info_from_login = AsyncMock(
            return_value={"refresh_token": TEST_TOKEN, "oauth_url": TEST_URL}
        )
        service_mock.return_value.create_client_from_token = AsyncMock(
            return_value=MockClient()
        )
        yield service_mock


PATCH_SETUP_ENTRY = patch(
    "custom_components.smartthinq_sensors.async_setup_entry",
    return_value=True,
)


async def test_form(hass, connect):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] is None

    with PATCH_SETUP_ENTRY as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=CONFIG_DATA
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["data"] == CONFIG_RESULT
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    "error,reason",
    [
        (AuthenticationError(), "invalid_credentials"),
        (InvalidCredentialError(), "invalid_credentials"),
        (Exception(), "error_connect"),
    ],
)
async def test_form_errors(hass, connect, error, reason):
    """Test we handle cannot connect error."""
    connect.return_value.create_client_from_token = AsyncMock(side_effect=error)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=CONFIG_DATA,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_BASE: reason}


@pytest.mark.parametrize(
    "login_result",
    [None, MockClient(False)],
)
async def test_form_response_nodev(hass, connect, login_result):
    """Test we handle response errors."""
    connect.return_value.create_client_from_token = AsyncMock(return_value=login_result)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=CONFIG_DATA,
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "no_smartthinq_devices"


async def test_token_refresh(hass, connect):
    """Re-configuration when config is invalid should refresh token."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**CONFIG_RESULT, CONF_TOKEN: "test-original-token"},
    )
    mock_entry.add_to_hass(hass)
    assert mock_entry.data[CONF_TOKEN] == "test-original-token"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data=CONFIG_DATA,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {CONF_BASE: "invalid_config"}

    with PATCH_SETUP_ENTRY as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=CONFIG_DATA
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert len(mock_setup_entry.mock_calls) == 1

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    entry = entries[0]
    assert entry.data[CONF_TOKEN] == TEST_TOKEN
