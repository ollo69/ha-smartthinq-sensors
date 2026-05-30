"""Repairs for SmartThinQ LGE Sensors."""

from __future__ import annotations

from typing import Any, cast
import uuid

from aiohttp import ClientError
from thinqconnect import ThinQApi, ThinQAPIErrorCodes, ThinQAPIException
import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_OFFICIAL_CLIENT_ID, CONF_OFFICIAL_PAT, OFFICIAL_CLIENT_PREFIX

MISSING_OFFICIAL_PAT_ISSUE = "missing_official_pat"

THINQ_ERRORS = {
    ThinQAPIErrorCodes.INVALID_TOKEN: "invalid_official_pat",
    ThinQAPIErrorCodes.NOT_ACCEPTABLE_TERMS: "official_terms_not_accepted",
    ThinQAPIErrorCodes.NOT_ALLOWED_API_AGAIN: "official_api_not_allowed",
    ThinQAPIErrorCodes.NOT_SUPPORTED_COUNTRY: "official_country_not_supported",
    ThinQAPIErrorCodes.EXCEEDED_API_CALLS: "official_api_calls_exceeded",
}
if exceeded_user_calls := getattr(
    ThinQAPIErrorCodes, "EXCEEDED_USER_API_CALLS", None
):
    THINQ_ERRORS[exceeded_user_calls] = "official_user_api_calls_exceeded"


class MissingOfficialPatRepairFlow(RepairsFlow):
    """Repair flow to add the optional official LG PAT."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the repair flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the repair flow."""
        errors: dict[str, str] = {}
        official_pat = user_input.get(CONF_OFFICIAL_PAT) if user_input else None

        if official_pat:
            official_client_id = self.entry.data.get(CONF_OFFICIAL_CLIENT_ID)
            if not official_client_id:
                official_client_id = f"{OFFICIAL_CLIENT_PREFIX}-{uuid.uuid4()!s}"

            try:
                await ThinQApi(
                    session=async_get_clientsession(self.hass),
                    access_token=official_pat,
                    country_code=self.entry.data["region"],
                    client_id=official_client_id,
                ).async_get_device_list()
            except ThinQAPIException as err:
                errors["base"] = THINQ_ERRORS.get(err.code, "invalid_official_pat")
            except (AttributeError, ClientError, TypeError, ValueError):
                errors["base"] = "error_connect"
            else:
                data = {
                    **self.entry.data,
                    CONF_OFFICIAL_PAT: official_pat,
                    CONF_OFFICIAL_CLIENT_ID: official_client_id,
                }
                self.hass.config_entries.async_update_entry(self.entry, data=data)
                await self.hass.config_entries.async_reload(self.entry.entry_id)
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_OFFICIAL_PAT): TextSelector(
                        config=TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"title": self.entry.title},
            errors=errors,
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create a repair flow for a SmartThinQ issue."""
    if (
        issue_id.startswith(f"{MISSING_OFFICIAL_PAT_ISSUE}_")
        and data
        and isinstance(data.get("entry_id"), str)
        and (entry := hass.config_entries.async_get_entry(cast(str, data["entry_id"])))
    ):
        return MissingOfficialPatRepairFlow(entry)

    return ConfirmRepairFlow()
