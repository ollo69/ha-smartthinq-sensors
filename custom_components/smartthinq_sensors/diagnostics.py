"""Diagnostics support for LG ThinQ."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util.dt import utcnow

from .const import DOMAIN, LGE_DEVICES
from .official_bridge import OFFICIAL_RUNTIME_RETRY_AT, OFFICIAL_RUNTIME_STATUS
from .official_mapping import find_official_coordinator
from .official_runtime import OFFICIAL_RUNTIME_LAST_ERROR
from .runtime_data import (
    CAPABILITY_REGISTRY,
    DATA_SOURCE_ROUTER,
    HYBRID_COORDINATORS,
    SNAPSHOT_MANAGER,
    UNSUPPORTED_DEVICES,
    get_domain_data,
    get_lge_devices,
)
from .trace import get_trace_events
from .wideq.device import Device as ThinQDevice

TO_REDACT = {CONF_TOKEN, "official_pat", "official_client_id"}
TO_REDACT_DEV = {"macAddress", "ssid", "userNo"}
TO_REDACT_STATE = {"macAddress", "ssid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return _async_get_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device entry."""
    return _async_get_diagnostics(hass, entry, device)


@callback
def _async_get_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: dr.DeviceEntry | None = None,
) -> dict:
    """Return diagnostics for a config or a device entry."""
    diag_data = {"entry": async_redact_data(entry.as_dict(), TO_REDACT)}

    lg_device_id = None
    if device:
        lg_device_id = next(iter(device.identifiers))[1]

    devs_data = _async_devices_as_dict(hass, lg_device_id)
    diag_data[LGE_DEVICES] = devs_data
    if hybrid_data := _async_hybrid_as_dict(hass, lg_device_id):
        diag_data["hybrid"] = hybrid_data
    if official_data := _async_official_runtime_as_dict(hass):
        diag_data["official_runtime"] = official_data
    if trace_data := _async_trace_as_dict(hass, lg_device_id):
        diag_data["trace"] = trace_data

    if device:
        return diag_data

    # Get info for unsupported device if diagnostic is for the config entry
    unsup_devices = get_domain_data(hass).get(UNSUPPORTED_DEVICES, {})
    unsup_data = {}
    for dev_type, devices in unsup_devices.items():
        unsup_devs = [
            async_redact_data(device.as_dict(), TO_REDACT_DEV) for device in devices
        ]
        unsup_data[dev_type.name] = unsup_devs

    if unsup_data:
        diag_data[UNSUPPORTED_DEVICES] = unsup_data

    return diag_data


@callback
def _async_devices_as_dict(
    hass: HomeAssistant, lg_device_id: str | None = None
) -> dict[str, Any]:
    """Represent a LGE devices as a dictionary."""

    lge_devices = get_lge_devices(hass)
    devs_data = {}
    for dev_type, devices in lge_devices.items():
        lge_devs = {}
        for lge_device in devices:
            device: ThinQDevice = lge_device.device
            if lg_device_id and device.device_info.device_id != lg_device_id:
                continue

            lge_devs[lge_device.unique_id] = {
                "device_info": async_redact_data(
                    device.device_info.as_dict(), TO_REDACT_DEV
                ),
                "model_info": device.model_info.as_dict(),
                "device_status": device.status.as_dict if device.status else None,
                "home_assistant": _async_device_ha_info(
                    hass, device.device_info.device_id
                ),
            }
            if lg_device_id:
                return {dev_type.name: lge_devs}

        if lge_devs:
            devs_data[dev_type.name] = lge_devs

    return devs_data


def _serialize_hybrid_value(value: Any) -> Any:
    """Convert a hybrid diagnostic value into plain data."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _serialize_hybrid_value(item) for key, item in value.items()
        }

    if isinstance(value, list):
        return [_serialize_hybrid_value(item) for item in value]

    return repr(value)


@callback
def _async_hybrid_as_dict(
    hass: HomeAssistant,
    lg_device_id: str | None = None,
) -> dict[str, Any] | None:
    """Represent hybrid coordinator and routing state as diagnostics."""
    domain_data = get_domain_data(hass)
    capability_registry = domain_data.get(CAPABILITY_REGISTRY)
    data_source_router = domain_data.get(DATA_SOURCE_ROUTER)
    hybrid_coordinators = domain_data.get(HYBRID_COORDINATORS)
    snapshot_manager = domain_data.get(SNAPSHOT_MANAGER)

    if (
        capability_registry is None
        and data_source_router is None
        and not isinstance(hybrid_coordinators, dict)
        and snapshot_manager is None
    ):
        return None

    all_device_ids: set[str] = set()
    if capability_registry is not None:
        all_device_ids.update(capability_registry.all_profiles())
    if isinstance(hybrid_coordinators, dict):
        all_device_ids.update(
            device_id
            for device_id in hybrid_coordinators
            if isinstance(device_id, str)
        )

    if lg_device_id is not None:
        device_ids = [lg_device_id]
    else:
        device_ids = sorted(all_device_ids)

    devices: dict[str, Any] = {}
    for device_id in device_ids:
        profile = (
            capability_registry.get_profile(device_id)
            if capability_registry is not None
            else None
        )
        coordinator = (
            hybrid_coordinators.get(device_id)
            if isinstance(hybrid_coordinators, dict)
            else None
        )
        official_coordinator = find_official_coordinator(hass, device_id)
        attributes = (
            sorted(profile.attributes)
            if profile is not None
            else []
        )
        routing = (
            {
                attr_id: data_source_router.get_attribute_source_info(
                    device_id,
                    attr_id,
                )
                for attr_id in attributes
            }
            if data_source_router is not None and profile is not None
            else {}
        )

        if (
            profile is None
            and coordinator is None
            and not routing
            and lg_device_id is not None
        ):
            continue

        devices[device_id] = {
            "profile": profile.to_dict() if profile is not None else None,
            "coordinator": (
                _serialize_hybrid_value(coordinator.get_diagnostics())
                if coordinator is not None and hasattr(coordinator, "get_diagnostics")
                else None
            ),
            "official": (
                _async_official_device_as_dict(official_coordinator)
                if official_coordinator is not None
                else None
            ),
            "routing": routing,
        }

    hybrid_data: dict[str, Any] = {"devices": devices}
    if snapshot_manager is not None and hasattr(snapshot_manager, "get_diagnostics"):
        hybrid_data["snapshot_manager"] = _serialize_hybrid_value(
            snapshot_manager.get_diagnostics()
        )
    return hybrid_data


def _async_official_device_as_dict(official_coordinator: Any) -> dict[str, Any]:
    """Represent one matched official coordinator as diagnostics."""
    official_api = getattr(official_coordinator, "api", None)
    official_device = getattr(official_api, "device", None)
    data = getattr(official_coordinator, "data", {})

    return {
        "device_id": getattr(official_coordinator, "device_id", None),
        "unique_id": getattr(official_coordinator, "unique_id", None),
        "sub_id": getattr(official_coordinator, "sub_id", None),
        "device_type": getattr(getattr(official_device, "device_type", None), "name", None),
        "model_name": getattr(official_device, "model_name", None),
        "alias": getattr(official_device, "alias", None),
        "energy_properties": _serialize_hybrid_value(
            getattr(official_device, "energy_properties", None)
        ),
        "data_keys": sorted(str(key) for key in data)[:100],
    }


@callback
def _async_official_runtime_as_dict(hass: HomeAssistant) -> dict[str, Any] | None:
    """Represent official runtime status for diagnostics."""
    domain_data = get_domain_data(hass)
    status = domain_data.get(OFFICIAL_RUNTIME_STATUS)
    last_error = domain_data.get(OFFICIAL_RUNTIME_LAST_ERROR)
    retry_at = domain_data.get(OFFICIAL_RUNTIME_RETRY_AT)
    if status is None and last_error is None:
        return None

    retry_info = None
    if isinstance(retry_at, (int, float)):
        retry_dt = datetime.fromtimestamp(retry_at, tz=utcnow().tzinfo)
        retry_info = {
            "retry_at": retry_dt.isoformat(),
            "retry_in_seconds": max(0, int(retry_at - utcnow().timestamp())),
        }

    return {
        "status": _serialize_hybrid_value(status),
        "last_error": last_error,
        "retry": retry_info,
    }


@callback
def _async_trace_as_dict(
    hass: HomeAssistant,
    lg_device_id: str | None = None,
) -> dict[str, Any] | None:
    """Return recent in-memory trace events for diagnostics."""
    events = get_trace_events(hass, device_id=lg_device_id)
    if not events:
        return None
    return {"recent_events": events}


@callback
def _async_device_ha_info(
    hass: HomeAssistant, lg_device_id: str
) -> dict[str, Any] | None:
    """Gather information how this ThinQ device is represented in Home Assistant."""

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    hass_device = device_registry.async_get_device(identifiers={(DOMAIN, lg_device_id)})
    if not hass_device:
        return None

    entities: dict[str, Any] = {}
    data: dict[str, Any] = {
        "name": hass_device.name,
        "name_by_user": hass_device.name_by_user,
        "model": hass_device.model,
        "manufacturer": hass_device.manufacturer,
        "sw_version": hass_device.sw_version,
        "disabled": hass_device.disabled,
        "disabled_by": hass_device.disabled_by,
        "entities": entities,
    }

    hass_entities = er.async_entries_for_device(
        entity_registry,
        device_id=hass_device.id,
        include_disabled_entities=True,
    )

    for entity_entry in hass_entities:
        if entity_entry.platform != DOMAIN:
            continue
        state = hass.states.get(entity_entry.entity_id)
        state_dict = None
        if state:
            state_dict = dict(state.as_dict())
            # The entity_id is already provided at root level.
            state_dict.pop("entity_id", None)
            # The context doesn't provide useful information in this case.
            state_dict.pop("context", None)

        if state_dict and "state" in state_dict:
            for to_redact in TO_REDACT_STATE:
                if entity_entry.entity_id.endswith(f"_{to_redact}"):
                    state_dict["state"] = REDACTED
                    break

        entities[entity_entry.entity_id] = {
            "name": entity_entry.name,
            "original_name": entity_entry.original_name,
            "disabled": entity_entry.disabled,
            "disabled_by": entity_entry.disabled_by,
            "entity_category": entity_entry.entity_category,
            "device_class": entity_entry.device_class,
            "original_device_class": entity_entry.original_device_class,
            "icon": entity_entry.icon,
            "original_icon": entity_entry.original_icon,
            "unit_of_measurement": entity_entry.unit_of_measurement,
            "state": state_dict,
        }

    return data
