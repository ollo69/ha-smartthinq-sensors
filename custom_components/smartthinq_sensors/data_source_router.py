"""Data source routing logic for hybrid API access."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.util.dt import utcnow

from .capability_registry import AttributeCapability, CapabilityRegistry


class DataSourceRouter:
    """Determine which data source to use for each attribute."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        max_official_age: timedelta = timedelta(minutes=5),
        max_community_age: timedelta = timedelta(minutes=5),
    ) -> None:
        """Initialize router."""
        self._registry = registry
        self._max_official_age = max_official_age
        self._max_community_age = max_community_age

    def get_attribute_value(
        self,
        device_id: str,
        attribute_id: str,
        fallback_strategy: str = "polling",
    ) -> tuple[Any, str]:
        """Get attribute value from the best available source."""
        profile = self._registry.get_profile(device_id)
        if not profile:
            return None, "unknown"

        capability = profile.get_attribute(attribute_id)
        if not capability:
            return None, "unknown"

        return self._resolve_value(capability, fallback_strategy)

    def _resolve_value(
        self,
        capability: AttributeCapability,
        fallback_strategy: str,
    ) -> tuple[Any, str]:
        """Resolve which source value to use."""
        official_available = self._is_source_available(
            capability.official_value,
            capability.official_timestamp,
            self._max_official_age,
        )
        community_available = self._is_source_available(
            capability.community_value,
            capability.community_timestamp,
            self._max_community_age,
        )

        if official_available and community_available:
            if capability.prefer_official:
                return capability.official_value, "official"
            return capability.community_value, "polling"

        if official_available:
            return capability.official_value, "official"

        if community_available:
            return capability.community_value, "polling"

        if fallback_strategy == "polling":
            if capability.community_value is not None:
                return capability.community_value, "polling_stale"
            if capability.official_value is not None:
                return capability.official_value, "official_stale"

        if fallback_strategy == "skip":
            return None, "skipped"

        return None, "none"

    def _is_source_available(
        self,
        value: Any,
        timestamp: Any,
        max_age: timedelta,
    ) -> bool:
        """Check if a source's data is fresh and available."""
        if value is None or timestamp is None:
            return False
        return bool(utcnow() - timestamp <= max_age)

    def should_use_official(self, device_id: str, attribute_id: str) -> bool:
        """Quick check for whether official data should be preferred."""
        _value, source = self.get_attribute_value(
            device_id,
            attribute_id,
            fallback_strategy="polling",
        )
        return source.startswith("official")

    def get_attribute_source_info(
        self,
        device_id: str,
        attribute_id: str,
    ) -> dict[str, Any]:
        """Get detailed source information for diagnostics."""
        profile = self._registry.get_profile(device_id)
        if not profile:
            return {
                "device_id": device_id,
                "attribute_id": attribute_id,
                "status": "unknown",
            }

        capability = profile.get_attribute(attribute_id)
        if not capability:
            return {
                "device_id": device_id,
                "attribute_id": attribute_id,
                "status": "not_registered",
            }

        value, source = self.get_attribute_value(
            device_id,
            attribute_id,
            fallback_strategy="polling",
        )
        return {
            "device_id": device_id,
            "attribute_id": attribute_id,
            "status": source,
            "value": value,
            "has_official": capability.has_official,
            "has_community": capability.has_community,
            "prefer_official": capability.prefer_official,
            "official_timestamp": (
                capability.official_timestamp.isoformat()
                if capability.official_timestamp is not None
                else None
            ),
            "community_timestamp": (
                capability.community_timestamp.isoformat()
                if capability.community_timestamp is not None
                else None
            ),
        }

    def validate_conflict(
        self,
        device_id: str,
        attribute_id: str,
    ) -> tuple[bool, str | None]:
        """Check whether official and community values conflict significantly."""
        profile = self._registry.get_profile(device_id)
        if not profile:
            return False, None

        capability = profile.get_attribute(attribute_id)
        if not capability:
            return False, None

        official = capability.official_value
        community = capability.community_value
        if official is None or community is None:
            return False, None

        if type(official) is not type(community):
            return (
                True,
                f"Type mismatch: official={type(official).__name__}, community={type(community).__name__}",
            )

        if isinstance(official, (int, float)) and official != 0:
            percent_diff = abs((community - official) / official) * 100
            if percent_diff > 20:
                return True, f"Numeric difference: {percent_diff:.1f}%"

        if isinstance(official, str) and official != community:
            return True, f"String mismatch: official={official!r} vs community={community!r}"

        return False, None

    def get_routing_decision(
        self,
        device_id: str,
        attributes: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Get routing decisions for multiple attributes."""
        return {
            attr_id: self.get_attribute_source_info(device_id, attr_id)
            for attr_id in attributes
        }
