"""Bridge official Home Assistant LG ThinQ coordinators into hybrid routing."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.util.dt import utcnow

from .official_mapping import (
    extract_official_attributes,
    find_target_device_id,
    update_profile_subscription,
)
from .official_runtime import async_setup_official_runtime
from .runtime_data import get_domain_data
from .trace import add_trace_event

_LOGGER = logging.getLogger(__name__)
OFFICIAL_DOMAIN = "lg_thinq"
OFFICIAL_RUNTIME = "official_runtime"
OFFICIAL_RUNTIME_STATUS = "official_runtime_status"
OFFICIAL_RUNTIME_RETRY_COUNT = "official_runtime_retry_count"
OFFICIAL_RUNTIME_RETRY_AT = "official_runtime_retry_at"
OFFICIAL_RUNTIME_RETRY_UNSUB = "official_runtime_retry_unsub"
async def _async_handle_official_update(
    hass: HomeAssistant,
    official_coordinator: Any,
) -> None:
    """Mirror an official coordinator update into the hybrid coordinator."""
    domain_data = get_domain_data(hass)
    capability_registry = domain_data.get("capability_registry")
    hybrid_coordinators = domain_data.get("hybrid_coordinators", {})
    if capability_registry is None:
        return

    target_device_id = find_target_device_id(hass, official_coordinator)
    if target_device_id is None:
        _LOGGER.debug("No community device match found for official coordinator")
        add_trace_event(
            hass,
            category="bridge",
            action="unmatched_official_device",
            details={
                "official_device_id": getattr(official_coordinator, "device_id", None),
                "official_unique_id": getattr(official_coordinator, "unique_id", None),
            },
        )
        return

    hybrid_coordinator = hybrid_coordinators.get(target_device_id)

    profile = capability_registry.get_profile(target_device_id)
    if profile is not None:
        update_profile_subscription(profile)

    aliases = extract_official_attributes(official_coordinator)
    if not aliases:
        if profile is not None and profile.is_known_offline():
            add_trace_event(
                hass,
                category="bridge",
                action="offline_no_official_data",
                device_id=target_device_id,
                details={
                    "offline_reason": profile.offline_reason,
                    "official_device_type": getattr(
                        getattr(official_coordinator.api, "device", None),
                        "device_type",
                        None,
                    ),
                },
            )
            return
        add_trace_event(
            hass,
            category="bridge",
            action="no_aliases_extracted",
            device_id=target_device_id,
            details={
                "official_device_type": getattr(
                    getattr(official_coordinator.api, "device", None),
                    "device_type",
                    None,
                ),
                "data_keys": sorted(
                    str(key) for key in getattr(official_coordinator, "data", {})
                )[:20],
            },
        )
        return

    add_trace_event(
        hass,
        category="bridge",
        action="official_update_applied",
        device_id=target_device_id,
        details={"attributes": sorted(aliases)},
    )

    if hybrid_coordinator is not None:
        await hybrid_coordinator.async_update_from_mqtt(aliases, target_device_id)
    elif profile is not None:
        for attr_id, value in aliases.items():
            profile.update_attribute_official(attr_id, value)


async def async_setup_official_bridge(
    hass: HomeAssistant,
    on_unload: Callable[[Callable[[], None]], None],
    *,
    official_pat: str | None = None,
    official_client_id: str | None = None,
    country_code: str | None = None,
    on_devices_changed: Callable[[], None] | None = None,
) -> None:
    """Subscribe to official lg_thinq coordinators when available."""
    domain_data = get_domain_data(hass)
    if domain_data.get(OFFICIAL_RUNTIME) is not None:
        return
    domain_data[OFFICIAL_RUNTIME_STATUS] = {
        "mode": "disabled",
        "status": "not_configured",
    }

    if official_pat and official_client_id and country_code:
        domain_data[OFFICIAL_RUNTIME_STATUS] = {
            "mode": "custom_runtime",
            "status": "initializing",
            "country_code": country_code,
        }
        runtime = await async_setup_official_runtime(
            hass,
            on_unload,
            access_token=official_pat,
            client_id=official_client_id,
            country_code=country_code,
            on_devices_changed=on_devices_changed,
        )
        if runtime is not None:
            if retry_unsub := domain_data.pop(OFFICIAL_RUNTIME_RETRY_UNSUB, None):
                retry_unsub()
            domain_data[OFFICIAL_RUNTIME_RETRY_COUNT] = 0
            domain_data.pop(OFFICIAL_RUNTIME_RETRY_AT, None)
            domain_data[OFFICIAL_RUNTIME] = runtime
            domain_data[OFFICIAL_RUNTIME_STATUS] = {
                "mode": "custom_runtime",
                "status": "connected",
                "coordinator_count": len(runtime.coordinators),
                "mqtt_ready": runtime.mqtt_client is not None,
            }
            for official_coordinator in runtime.coordinators.values():
                def _handle_runtime_update(
                    coordinator: Any = official_coordinator,
                ) -> None:
                    hass.async_create_task(_async_handle_official_update(hass, coordinator))

                remove_listener = official_coordinator.async_add_listener(
                    _handle_runtime_update
                )
                on_unload(remove_listener)
                await _async_handle_official_update(hass, official_coordinator)
            return
        retry_count = int(domain_data.get(OFFICIAL_RUNTIME_RETRY_COUNT, 0)) + 1
        domain_data[OFFICIAL_RUNTIME_RETRY_COUNT] = retry_count
        retry_seconds = min(300 * retry_count, 3600)
        retry_at = utcnow().timestamp() + retry_seconds
        domain_data[OFFICIAL_RUNTIME_RETRY_AT] = retry_at
        domain_data[OFFICIAL_RUNTIME_STATUS] = {
            "mode": "custom_runtime",
            "status": "failed",
            "reason": "official_runtime_unavailable",
            "retry_seconds": retry_seconds,
            "retry_count": retry_count,
            "retry_at": retry_at,
        }

        if domain_data.get(OFFICIAL_RUNTIME_RETRY_UNSUB) is None:

            def _retry_official_runtime(_now: datetime) -> None:
                domain_data.pop(OFFICIAL_RUNTIME_RETRY_UNSUB, None)
                hass.async_create_task(
                    async_setup_official_bridge(
                        hass,
                        on_unload,
                        official_pat=official_pat,
                        official_client_id=official_client_id,
                        country_code=country_code,
                        on_devices_changed=on_devices_changed,
                    )
                )

            retry_unsub = async_call_later(hass, retry_seconds, _retry_official_runtime)
            domain_data[OFFICIAL_RUNTIME_RETRY_UNSUB] = retry_unsub
            on_unload(retry_unsub)

    official_entries = hass.config_entries.async_entries(OFFICIAL_DOMAIN)
    if not official_entries:
        domain_data[OFFICIAL_RUNTIME_STATUS] = {
            "mode": "builtin_bridge",
            "status": "not_found",
        }
        _LOGGER.debug("No official lg_thinq config entries found for bridge")
        return

    domain_data[OFFICIAL_RUNTIME_STATUS] = {
        "mode": "builtin_bridge",
        "status": "connected",
        "entry_count": len(official_entries),
    }
    for entry in official_entries:
        runtime_data = getattr(entry, "runtime_data", None)
        coordinators = getattr(runtime_data, "coordinators", None)
        if not isinstance(coordinators, dict):
            continue

        for official_coordinator in coordinators.values():
            def _handle_entry_update(
                coordinator: Any = official_coordinator,
            ) -> None:
                hass.async_create_task(_async_handle_official_update(hass, coordinator))

            remove_listener = official_coordinator.async_add_listener(
                _handle_entry_update
            )
            on_unload(remove_listener)
            await _async_handle_official_update(hass, official_coordinator)
