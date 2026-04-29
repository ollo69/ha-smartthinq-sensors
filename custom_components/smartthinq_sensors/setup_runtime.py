"""Runtime setup helpers for SmartThinQ config entries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any, cast
import uuid

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .auth import LGEAuthentication
from .capability_registry import CapabilityRegistry
from .const import (
    CLIENT,
    CONF_OAUTH2_URL,
    CONF_OFFICIAL_CLIENT_ID,
    CONF_OFFICIAL_PAT,
    DOMAIN,
    LGE_DEVICES,
    OFFICIAL_CLIENT_PREFIX,
    SIGNAL_RELOAD_ENTRY,
    STARTUP,
)
from .data_source_router import DataSourceRouter
from .runtime_data import (
    CAPABILITY_REGISTRY,
    DATA_SOURCE_ROUTER,
    DISCOVERED_DEVICES,
    HYBRID_COORDINATORS,
    SNAPSHOT_MANAGER,
    UNSUPPORTED_DEVICES,
    get_domain_data,
)
from .snapshot_manager import CommunitySnapshotManager
from .wideq.core_async import ClientAsync
from .wideq.core_exceptions import AuthenticationError, InvalidCredentialError

MISSING_OFFICIAL_PAT_ISSUE = "missing_official_pat"
AUTH_RETRY = "auth_retry"
MAX_AUTH_RETRY = 4

_LOGGER = logging.getLogger(__name__)


def notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification."""
    persistent_notification.async_create(
        hass, message, title, f"smartthinq_sensors.{notification_id}"
    )


@callback
def migrate_old_config_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate an old config entry if available."""
    old_key = "outh_url"
    if old_key not in entry.data:
        return

    oauth2_url = entry.data[old_key]
    new_data = {key: value for key, value in entry.data.items() if key != old_key}
    hass.config_entries.async_update_entry(
        entry, data={**new_data, CONF_OAUTH2_URL: oauth2_url}
    )


def ensure_official_runtime_config(
    hass: HomeAssistant, entry: ConfigEntry
) -> tuple[str | None, str | None]:
    """Ensure optional official runtime config is internally complete."""
    official_client_id: str | None = entry.data.get(CONF_OFFICIAL_CLIENT_ID)
    official_pat: str | None = entry.data.get(CONF_OFFICIAL_PAT)

    if official_pat and not official_client_id:
        official_client_id = f"{OFFICIAL_CLIENT_PREFIX}-{uuid.uuid4()!s}"
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_OFFICIAL_CLIENT_ID: official_client_id},
        )

    return official_pat, official_client_id


def update_missing_official_pat_issue(
    hass: HomeAssistant, entry: ConfigEntry, official_pat: str | None
) -> None:
    """Create or clear the optional official PAT issue."""
    issue_id = f"{MISSING_OFFICIAL_PAT_ISSUE}_{entry.entry_id}"
    if official_pat:
        ir.async_delete_issue(hass, "smartthinq_sensors", issue_id)
        return

    ir.async_create_issue(
        hass,
        "smartthinq_sensors",
        issue_id,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=MISSING_OFFICIAL_PAT_ISSUE,
        translation_placeholders={"title": entry.title},
        data={"entry_id": entry.entry_id},
    )


def prepare_runtime_context(
    hass: HomeAssistant, *, region: str, language: str
) -> tuple[dict[str, Any], bool]:
    """Prepare shared runtime state and return whether startup logging is needed."""
    domain_data = get_domain_data(hass)
    log_info: bool = domain_data.get(SIGNAL_RELOAD_ENTRY, 0) < 2
    if log_info:
        hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: 2}
        _LOGGER.info(STARTUP)
        _LOGGER.info(
            "Initializing ThinQ platform with region: %s - language: %s",
            region,
            language,
        )

    domain_data = get_domain_data(hass)
    domain_data.setdefault(CAPABILITY_REGISTRY, CapabilityRegistry())
    domain_data.setdefault(
        DATA_SOURCE_ROUTER,
        DataSourceRouter(domain_data[CAPABILITY_REGISTRY]),
    )
    domain_data.setdefault(HYBRID_COORDINATORS, {})
    return domain_data, log_info


async def async_create_community_client(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    region: str,
    language: str,
    refresh_token: str,
    oauth2_url: str | None,
    client_id: str | None,
    use_ha_session: bool,
    log_info: bool,
    domain_key: str,
) -> ClientAsync:
    """Create and validate the ThinQ community client."""

    def _update_clientid_callback(updated_client_id: str) -> None:
        """Update config entry with the new client id."""
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CLIENT_ID: updated_client_id}
        )

    domain_data = get_domain_data(hass)
    lge_auth = LGEAuthentication(hass, region, language, use_ha_session)
    try:
        return await lge_auth.create_client_from_token(
            refresh_token, oauth2_url, client_id, _update_clientid_callback
        )
    except (AuthenticationError, InvalidCredentialError) as exc:
        if (auth_retry := domain_data.get(AUTH_RETRY, 0)) >= MAX_AUTH_RETRY:
            hass.data.pop(domain_key, None)
            raise ConfigEntryAuthFailed("ThinQ authentication failed") from exc

        domain_data[AUTH_RETRY] = auth_retry + 1
        msg = (
            "Invalid ThinQ credential error, integration setup aborted."
            " Please use the LG App on your mobile device to ensure your"
            " credentials are correct or there are new Term of Service to accept"
        )
        if log_info:
            _LOGGER.warning(msg, exc_info=True)
        raise ConfigEntryNotReady(msg) from exc
    except Exception as exc:
        if log_info:
            _LOGGER.warning(
                "Connection not available. ThinQ platform not ready", exc_info=True
            )
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc


def store_entry_runtime_data(
    hass: HomeAssistant,
    *,
    client: ClientAsync,
    lge_devices: dict[Any, list[Any]],
    unsupported_devices: dict[Any, list[Any]],
    discovered_devices: dict[str, list[str]],
    snapshot_manager: CommunitySnapshotManager,
    domain_data: dict[str, Any],
) -> None:
    """Store the active integration runtime state in ``hass.data``."""
    registry = domain_data[CAPABILITY_REGISTRY]
    router = domain_data[DATA_SOURCE_ROUTER]
    hybrid_coordinators = domain_data[HYBRID_COORDINATORS]
    reload_signal = domain_data.get(SIGNAL_RELOAD_ENTRY)
    hass.data[DOMAIN] = {
        CLIENT: client,
        LGE_DEVICES: lge_devices,
        UNSUPPORTED_DEVICES: unsupported_devices,
        DISCOVERED_DEVICES: discovered_devices,
        SNAPSHOT_MANAGER: snapshot_manager,
        CAPABILITY_REGISTRY: registry,
        DATA_SOURCE_ROUTER: router,
        HYBRID_COORDINATORS: hybrid_coordinators,
    }
    if reload_signal is not None:
        hass.data[DOMAIN][SIGNAL_RELOAD_ENTRY] = reload_signal


def register_entry_lifecycle_hooks(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    client: ClientAsync,
    reload_entry: Callable[[], Awaitable[None]],
) -> None:
    """Register entry reload and shutdown listeners."""

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_RELOAD_ENTRY, reload_entry)
    )

    async def _close_lg_client(_event: Event) -> None:
        """Close client to abort polling."""
        await client.close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _close_lg_client)
    )


async def async_unload_runtime_data(hass: HomeAssistant) -> ClientAsync | None:
    """Remove runtime data and preserve reload state across unload."""
    data = hass.data.pop(DOMAIN)
    reload_count = data.get(SIGNAL_RELOAD_ENTRY, 0)
    if reload_count > 0:
        hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: reload_count}
    return cast(ClientAsync | None, data.get(CLIENT))
