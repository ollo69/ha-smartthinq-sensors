"""Helpers for issuing official ThinQ Connect control commands."""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any, cast

from thinqconnect import ThinQAPIException
from thinqconnect.integration import ActiveMode, ExtendedProperty

from homeassistant.core import HomeAssistant

from .runtime_data import get_domain_data
from .trace import add_trace_event

_LOGGER = logging.getLogger(__name__)

OFFICIAL_DOMAIN = "lg_thinq"
OFFICIAL_DEVICE_LINKS = "official_device_links"
OFFICIAL_RUNTIME = "official_runtime"


def _normalize_text(value: Any) -> str:
    """Normalize text for stable comparisons."""
    return str(value or "").strip().casefold()


def _iter_official_coordinators(hass: HomeAssistant) -> Iterable[Any]:
    """Yield official coordinators from custom runtime or built-in integration."""
    domain_data = get_domain_data(hass)
    runtime = domain_data.get(OFFICIAL_RUNTIME)
    coordinators = getattr(runtime, "coordinators", None)
    if isinstance(coordinators, dict):
        yield from coordinators.values()

    for entry in hass.config_entries.async_entries(OFFICIAL_DOMAIN):
        runtime_data = getattr(entry, "runtime_data", None)
        builtin = getattr(runtime_data, "coordinators", None)
        if isinstance(builtin, dict):
            yield from builtin.values()


def _find_official_coordinator(lge_device: Any) -> Any | None:
    """Find the official coordinator that matches a community device."""
    hass = lge_device.hass
    domain_data = get_domain_data(hass)
    reverse_links = {
        target_device_id: official_key
        for official_key, target_device_id in domain_data.get(OFFICIAL_DEVICE_LINKS, {}).items()
    }
    wanted_official_key = reverse_links.get(lge_device.device_id)

    community_name = _normalize_text(lge_device.name)
    community_model = _normalize_text(lge_device.device.device_info.model_name)
    community_type = _normalize_text(lge_device.type.name)

    for coordinator in _iter_official_coordinators(hass):
        if wanted_official_key and wanted_official_key in {
            getattr(coordinator, "device_id", None),
            getattr(coordinator, "unique_id", None),
        }:
            return coordinator

        official_device = getattr(getattr(coordinator, "api", None), "device", None)
        if official_device is None:
            continue

        official_type = _normalize_text(getattr(official_device, "device_type", None))
        if official_type.startswith("device_"):
            official_type = official_type.removeprefix("device_")
        if community_type and community_type not in official_type:
            continue

        if _normalize_text(getattr(official_device, "alias", None)) != community_name:
            continue
        if (
            community_model
            and _normalize_text(getattr(official_device, "model_name", None))
            != community_model
        ):
            continue
        return coordinator

    return None


def _resolve_property_id(
    coordinator: Any,
    property_keys: tuple[Any, ...],
    *,
    active_mode: ActiveMode = ActiveMode.WRITABLE,
) -> str | None:
    """Resolve a writable official property id from candidate keys."""
    for key in property_keys:
        modes = [None] if isinstance(key, ExtendedProperty) else [active_mode, None]
        for mode in modes:
            property_ids = coordinator.api.get_active_idx(key, mode)
            if property_ids:
                return cast(str, property_ids[0])
    return None


async def _async_run_official_command(
    lge_device: Any,
    action: str,
    property_keys: tuple[Any, ...],
    command_factory: Any,
    *,
    active_mode: ActiveMode = ActiveMode.WRITABLE,
    trace_details: dict[str, Any] | None = None,
) -> bool:
    """Try an official command and refresh the official coordinator if it succeeds."""
    coordinator = _find_official_coordinator(lge_device)
    if coordinator is None:
        return False

    property_id = _resolve_property_id(
        coordinator,
        property_keys,
        active_mode=active_mode,
    )
    if property_id is None:
        return False

    details = {"property_id": property_id, "action": action}
    if trace_details:
        details.update(trace_details)

    try:
        await command_factory(coordinator, property_id)
        await coordinator.async_request_refresh()
    except (ThinQAPIException, ValueError) as err:
        _LOGGER.debug("Official control fallback for %s: %s", lge_device.name, err)
        add_trace_event(
            lge_device.hass,
            category="control",
            action="official_fallback",
            device_id=lge_device.device_id,
            details={**details, "reason": str(err)},
        )
        return False

    add_trace_event(
        lge_device.hass,
        category="control",
        action="official_applied",
        device_id=lge_device.device_id,
        details=details,
    )
    return True


async def async_call_official_turn_on(
    lge_device: Any,
    *property_keys: Any,
) -> bool:
    """Turn on a device through the official API."""
    return await _async_run_official_command(
        lge_device,
        "turn_on",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.async_turn_on(property_id),
    )


async def async_call_official_turn_off(
    lge_device: Any,
    *property_keys: Any,
) -> bool:
    """Turn off a device through the official API."""
    return await _async_run_official_command(
        lge_device,
        "turn_off",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.async_turn_off(property_id),
    )


async def async_call_official_post(
    lge_device: Any,
    value: Any,
    *property_keys: Any,
) -> bool:
    """Post a writable value through the official API."""
    return await _async_run_official_command(
        lge_device,
        "post",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.post(property_id, value),
        trace_details={"value": value},
    )


async def async_call_official_set_target_temperature(
    lge_device: Any,
    value: float,
    *property_keys: Any,
) -> bool:
    """Set target temperature through the official API."""
    return await _async_run_official_command(
        lge_device,
        "set_target_temperature",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.async_set_target_temperature(
            property_id, value
        ),
        trace_details={"value": value},
    )


async def async_call_official_set_hvac_mode(
    lge_device: Any,
    value: str,
    *property_keys: Any,
) -> bool:
    """Set HVAC mode through the official API."""
    return await _async_run_official_command(
        lge_device,
        "set_hvac_mode",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.async_set_hvac_mode(
            property_id, value
        ),
        trace_details={"value": value},
    )


async def async_call_official_set_fan_mode(
    lge_device: Any,
    value: str,
    *property_keys: Any,
) -> bool:
    """Set fan mode through the official API."""
    return await _async_run_official_command(
        lge_device,
        "set_fan_mode",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.async_set_fan_mode(
            property_id, value
        ),
        trace_details={"value": value},
    )


async def async_call_official_set_job_mode(
    lge_device: Any,
    value: str,
    *property_keys: Any,
) -> bool:
    """Set job mode through the official API."""
    return await _async_run_official_command(
        lge_device,
        "set_job_mode",
        tuple(property_keys),
        lambda coordinator, property_id: coordinator.api.async_set_job_mode(
            property_id, value
        ),
        trace_details={"value": value},
    )
