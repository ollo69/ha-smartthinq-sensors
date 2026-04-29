"""Helpers for accessing shared integration runtime data."""

from __future__ import annotations

from collections import deque
from collections.abc import MutableMapping
from typing import Any, cast

from homeassistant.core import HomeAssistant

from .capability_registry import CapabilityRegistry
from .const import CLIENT, DOMAIN, LGE_DEVICES
from .data_source_router import DataSourceRouter

DISCOVERED_DEVICES = "discovered_devices"
UNSUPPORTED_DEVICES = "unsupported_devices"
SNAPSHOT_MANAGER = "snapshot_manager"
CAPABILITY_REGISTRY = "capability_registry"
DATA_SOURCE_ROUTER = "data_source_router"
HYBRID_COORDINATORS = "hybrid_coordinators"


def get_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the domain runtime store, creating it if needed."""
    return cast(dict[str, Any], hass.data.setdefault(DOMAIN, {}))


def get_domain_value[T](hass: HomeAssistant, key: str, default: T) -> T:
    """Return a typed value from the domain runtime store."""
    return cast(T, get_domain_data(hass).get(key, default))


def set_domain_value(hass: HomeAssistant, key: str, value: Any) -> None:
    """Store a value in the domain runtime store."""
    get_domain_data(hass)[key] = value


def pop_domain_value(hass: HomeAssistant, key: str, default: Any = None) -> Any:
    """Pop a value from the domain runtime store."""
    return get_domain_data(hass).pop(key, default)


def get_lge_devices(hass: HomeAssistant) -> dict[Any, list[Any]]:
    """Return known LG devices grouped by device type."""
    return get_domain_value(hass, LGE_DEVICES, {})


def get_client(hass: HomeAssistant) -> Any:
    """Return the ThinQ community client."""
    return get_domain_value(hass, CLIENT, None)


def get_discovered_devices(hass: HomeAssistant) -> dict[str, list[str]]:
    """Return discovered community devices by root device id."""
    return get_domain_value(hass, DISCOVERED_DEVICES, {})


def get_unsupported_devices(hass: HomeAssistant) -> dict[Any, list[Any]]:
    """Return unsupported community devices grouped by type."""
    return get_domain_value(hass, UNSUPPORTED_DEVICES, {})


def get_snapshot_manager(hass: HomeAssistant) -> Any:
    """Return the shared snapshot manager."""
    return get_domain_value(hass, SNAPSHOT_MANAGER, None)


def get_capability_registry(hass: HomeAssistant) -> CapabilityRegistry | None:
    """Return the hybrid capability registry."""
    return get_domain_value(hass, CAPABILITY_REGISTRY, None)


def get_data_source_router(hass: HomeAssistant) -> DataSourceRouter | None:
    """Return the hybrid data source router."""
    return get_domain_value(hass, DATA_SOURCE_ROUTER, None)


def get_hybrid_coordinators(hass: HomeAssistant) -> dict[str, Any]:
    """Return hybrid coordinators keyed by device id."""
    return get_domain_value(hass, HYBRID_COORDINATORS, {})


def get_trace_buffer(hass: HomeAssistant, key: str, maxlen: int) -> deque[Any]:
    """Return a bounded deque stored in the domain runtime store."""
    domain_data = get_domain_data(hass)
    buffer = domain_data.get(key)
    if isinstance(buffer, deque):
        return buffer

    new_buffer: deque[Any] = deque(maxlen=maxlen)
    domain_data[key] = new_buffer
    return new_buffer


def remove_none_values(data: MutableMapping[str, Any]) -> None:
    """Remove keys with ``None`` values from a mutable mapping."""
    for key in [key for key, value in data.items() if value is None]:
        data.pop(key, None)
