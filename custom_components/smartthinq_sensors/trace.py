"""Lightweight in-memory tracing for hybrid/MQTT debugging."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow

from .const import DOMAIN

TRACE_BUFFER = "trace_buffer"
TRACE_BUFFER_LIMIT = 200


@dataclass(slots=True)
class TraceEvent:
    """One debug trace event."""

    timestamp: datetime
    category: str
    action: str
    device_id: str | None = None
    details: dict[str, Any] | None = None


def add_trace_event(
    hass: HomeAssistant,
    *,
    category: str,
    action: str,
    device_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a trace event to the bounded in-memory buffer."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    buffer = domain_data.setdefault(
        TRACE_BUFFER,
        deque(maxlen=TRACE_BUFFER_LIMIT),
    )
    if not isinstance(buffer, deque):
        return

    sanitized_details = None
    if details:
        sanitized_details = {
            str(key): _sanitize_trace_value(value) for key, value in details.items()
        }

    buffer.append(
        TraceEvent(
            timestamp=utcnow(),
            category=category,
            action=action,
            device_id=device_id,
            details=sanitized_details,
        )
    )


def get_trace_events(
    hass: HomeAssistant,
    *,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return serialized trace events, optionally filtered by device."""
    domain_data = hass.data.get(DOMAIN, {})
    buffer = domain_data.get(TRACE_BUFFER)
    if not isinstance(buffer, deque):
        return []

    events: Iterable[TraceEvent] = buffer
    if device_id is not None:
        events = (event for event in buffer if event.device_id in {None, device_id})

    serialized: list[dict[str, Any]] = []
    for event in events:
        payload = asdict(event)
        payload["timestamp"] = event.timestamp.isoformat()
        serialized.append(payload)
    return serialized


def _sanitize_trace_value(value: Any) -> Any:
    """Convert trace values into a compact diagnostics-friendly form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _sanitize_trace_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_trace_value(item) for item in value[:20]]
    return repr(value)
