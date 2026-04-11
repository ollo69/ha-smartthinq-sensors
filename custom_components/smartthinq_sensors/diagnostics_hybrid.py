"""Diagnostic utilities for hybrid API operations and debugging."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow

from .capability_registry import CapabilityRegistry
from .data_source_router import DataSourceRouter

_LOGGER = logging.getLogger(__name__)


class HybridAPIStatistics:
    """Track statistics about data source usage."""

    def __init__(self) -> None:
        """Initialize statistics."""
        self._api_calls: dict[str, int] = {
            "official_successful": 0,
            "official_failed": 0,
            "community_successful": 0,
            "community_failed": 0,
            "mqtt_messages_received": 0,
            "mqtt_connection_losses": 0,
            "fallback_activations": 0,
            "fallback_recoveries": 0,
        }
        self._source_usage: dict[str, int] = {
            "official": 0,
            "polling": 0,
            "mqtt": 0,
            "stale": 0,
            "none": 0,
        }
        self._timestamp = {
            "started": utcnow(),
            "last_reset": utcnow(),
        }

    def record_api_call(self, api_type: str, success: bool) -> None:
        """Record an API call result."""
        suffix = "successful" if success else "failed"
        key = f"{api_type}_{suffix}"
        self._api_calls[key] = self._api_calls.get(key, 0) + 1

    def record_source_usage(self, source: str) -> None:
        """Record data source usage."""
        self._source_usage[source] = self._source_usage.get(source, 0) + 1

    def record_mqtt_message(self) -> None:
        """Record an MQTT message."""
        self._api_calls["mqtt_messages_received"] += 1

    def record_mqtt_loss(self) -> None:
        """Record MQTT connection loss."""
        self._api_calls["mqtt_connection_losses"] += 1

    def record_fallback(self, recovery: bool = False) -> None:
        """Record fallback activation or recovery."""
        key = "fallback_recoveries" if recovery else "fallback_activations"
        self._api_calls[key] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        uptime = utcnow() - self._timestamp["started"]
        return {
            "uptime_seconds": uptime.total_seconds(),
            "api_calls": self._api_calls.copy(),
            "source_usage": self._source_usage.copy(),
            "timestamps": {key: value.isoformat() for key, value in self._timestamp.items()},
        }

    def reset(self) -> None:
        """Reset all statistics."""
        self._api_calls = dict.fromkeys(self._api_calls, 0)
        self._source_usage = dict.fromkeys(self._source_usage, 0)
        self._timestamp["last_reset"] = utcnow()

    def to_string(self) -> str:
        """Get a formatted statistics string."""
        return json.dumps(self.get_stats(), indent=2, default=str)


class DiagnosticCollector:
    """Collect diagnostic information for debugging."""

    def __init__(
        self,
        hass: HomeAssistant,
        capability_registry: CapabilityRegistry,
        data_source_router: DataSourceRouter,
    ) -> None:
        """Initialize collector."""
        self._hass = hass
        self._capability_registry = capability_registry
        self._data_source_router = data_source_router
        self._stats = HybridAPIStatistics()

    def collect_device_diagnostics(self, device_id: str) -> dict[str, Any]:
        """Collect diagnostics for one device."""
        profile = self._capability_registry.get_profile(device_id)
        if not profile:
            return {"device_id": device_id, "status": "not_found"}

        attributes_info = [
            self._data_source_router.get_attribute_source_info(device_id, attr_id)
            for attr_id in profile.attributes
        ]
        return {
            "device_id": device_id,
            "device_model": profile.device_model,
            "device_type": profile.device_type.name,
            "available": profile.available,
            "offline_reason": profile.offline_reason,
            "offline_since": (
                profile.offline_since.isoformat()
                if profile.offline_since is not None
                else None
            ),
            "mqtt_subscribed": profile.mqtt_subscribed,
            "mqtt_subscription_error": profile.mqtt_subscription_error,
            "fallback_active": profile.fallback_active,
            "fallback_reason": profile.fallback_reason,
            "fallback_count": profile.fallback_count,
            "last_mqtt_activity": (
                profile.last_mqtt_activity.isoformat()
                if profile.last_mqtt_activity is not None
                else None
            ),
            "attributes": attributes_info,
        }

    def collect_all_diagnostics(self) -> dict[str, Any]:
        """Collect diagnostics for all devices."""
        all_profiles = self._capability_registry.all_profiles()
        return {
            "timestamp": utcnow().isoformat(),
            "total_devices": len(all_profiles),
            "devices": {
                device_id: self.collect_device_diagnostics(device_id)
                for device_id in all_profiles
            },
            "statistics": self._stats.get_stats(),
        }

    def export_diagnostics_json(self) -> str:
        """Export diagnostics as JSON."""
        try:
            return json.dumps(self.collect_all_diagnostics(), indent=2, default=str)
        except TypeError:
            _LOGGER.exception("Failed to export diagnostics")
            return "{}"

    def print_diagnostics(self, device_id: str | None = None) -> None:
        """Print diagnostics to the log."""
        diagnostics = (
            self.collect_device_diagnostics(device_id)
            if device_id
            else self.collect_all_diagnostics()
        )
        _LOGGER.info("Hybrid API Diagnostics:\n%s", json.dumps(diagnostics, indent=2, default=str))


class ConflictDetector:
    """Detect and log conflicts between official and community data."""

    def __init__(self, registry: CapabilityRegistry, router: DataSourceRouter) -> None:
        """Initialize detector."""
        self._registry = registry
        self._router = router

    def check_device_conflicts(self, device_id: str) -> list[tuple[str, str]]:
        """Check for conflicts in a device's attributes."""
        profile = self._registry.get_profile(device_id)
        if not profile:
            return []

        conflicts: list[tuple[str, str]] = []
        for attr_id in profile.attributes:
            has_conflict, description = self._router.validate_conflict(device_id, attr_id)
            if has_conflict:
                conflicts.append((attr_id, description or "Unknown conflict"))
        return conflicts

    def check_all_conflicts(self) -> dict[str, list[tuple[str, str]]]:
        """Check all devices for conflicts."""
        return {
            device_id: conflicts
            for device_id in self._registry.all_profiles()
            if (conflicts := self.check_device_conflicts(device_id))
        }

    def log_conflicts(self, log_level: int = logging.WARNING) -> None:
        """Log detected conflicts."""
        conflicts = self.check_all_conflicts()
        if not conflicts:
            _LOGGER.debug("No data source conflicts detected")
            return
        for device_id, conflict_list in conflicts.items():
            _LOGGER.log(
                log_level,
                "Device %s conflicts: %s",
                device_id,
                ", ".join(f"{attr}({desc})" for attr, desc in conflict_list),
            )


class PerformanceMonitor:
    """Monitor API call latency and performance."""

    def __init__(self) -> None:
        """Initialize monitor."""
        self._latencies: dict[str, list[float]] = {
            "official_api": [],
            "community_api": [],
            "mqtt": [],
        }
        self._max_samples = 100

    def record_latency(self, source: str, latency_ms: float) -> None:
        """Record API call latency."""
        if source not in self._latencies:
            return
        samples = self._latencies[source]
        samples.append(latency_ms)
        if len(samples) > self._max_samples:
            samples.pop(0)

    def get_average_latency(self, source: str) -> float | None:
        """Get average latency for a source."""
        samples = self._latencies.get(source, [])
        return (sum(samples) / len(samples)) if samples else None

    def get_percentile_latency(self, source: str, percentile: float) -> float | None:
        """Get percentile latency for a source."""
        samples = sorted(self._latencies.get(source, []))
        if not samples:
            return None
        index = min(int(len(samples) * percentile / 100), len(samples) - 1)
        return samples[index]

    def get_summary(self) -> dict[str, Any]:
        """Get performance summary."""
        return {
            source: {
                "avg_ms": self.get_average_latency(source),
                "p50_ms": self.get_percentile_latency(source, 50),
                "p95_ms": self.get_percentile_latency(source, 95),
                "p99_ms": self.get_percentile_latency(source, 99),
                "samples": len(latencies),
            }
            for source, latencies in self._latencies.items()
        }

    def print_summary(self) -> None:
        """Print performance summary."""
        _LOGGER.info("API Performance:\n%s", json.dumps(self.get_summary(), indent=2, default=str))
