"""Capability registry for tracking official vs community API availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import json
import logging
from typing import Any

from homeassistant.util.dt import utcnow

from .wideq import DeviceType

_LOGGER = logging.getLogger(__name__)
RAW_ATTRIBUTE_PREFIXES = ("state.", "feature.")


def is_logical_attribute_id(attribute_id: str) -> bool:
    """Return whether an attribute ID is a logical hybrid-routing attribute."""
    return not attribute_id.startswith(RAW_ATTRIBUTE_PREFIXES)


@dataclass
class AttributeCapability:
    """Capability metadata for one attribute across sources."""

    attribute_id: str
    display_name: str = ""
    has_official: bool = False
    has_community: bool = True
    official_timestamp: Any = None
    community_timestamp: Any = None
    mqtt_timestamp: Any = None
    prefer_official: bool = True
    fallback_strategy: str = "polling"
    official_value: Any = None
    community_value: Any = None

    def __post_init__(self) -> None:
        """Initialize defaults."""
        if not self.display_name:
            self.display_name = self.attribute_id

    def get_preferred_value(self) -> tuple[Any, str]:
        """Get value from the preferred source."""
        official_available = (
            self.has_official
            and self.official_timestamp is not None
            and self.official_value is not None
        )
        community_available = (
            self.has_community
            and self.community_timestamp is not None
            and self.community_value is not None
        )

        if official_available and not community_available:
            return self.official_value, "official"
        if community_available and not official_available:
            return self.community_value, "polling"
        if official_available and community_available:
            if self.prefer_official:
                return self.official_value, "official"
            if self.community_timestamp > self.official_timestamp:
                return self.community_value, "polling"
            return self.official_value, "official"
        return None, "none"

    def is_stale(
        self,
        max_age: timedelta = timedelta(minutes=5),
        prefer_official: bool = True,
    ) -> bool:
        """Check whether the preferred source data is stale."""
        timestamp = (
            self.official_timestamp
            if prefer_official and self.has_official
            else self.community_timestamp
        )
        if timestamp is None:
            return True
        return bool(utcnow() - timestamp > max_age)

    def update_official(self, value: Any, timestamp: Any = None) -> None:
        """Update official source data."""
        self.has_official = True
        self.official_value = value
        self.official_timestamp = timestamp or utcnow()
        self.mqtt_timestamp = self.official_timestamp

    def update_community(self, value: Any, timestamp: Any = None) -> None:
        """Update community source data."""
        self.has_community = True
        self.community_value = value
        self.community_timestamp = timestamp or utcnow()

    def mark_official_stale(self) -> None:
        """Mark official data as stale."""
        self.official_timestamp = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a diagnostic dictionary."""
        return {
            "id": self.attribute_id,
            "display_name": self.display_name,
            "has_official": self.has_official,
            "has_community": self.has_community,
            "prefer_official": self.prefer_official,
            "fallback_strategy": self.fallback_strategy,
            "preferred_value_source": self.get_preferred_value()[1],
            "official_timestamp": (
                self.official_timestamp.isoformat()
                if self.official_timestamp is not None
                else None
            ),
            "community_timestamp": (
                self.community_timestamp.isoformat()
                if self.community_timestamp is not None
                else None
            ),
        }


@dataclass
class DeviceCapabilityProfile:
    """All capabilities for one device."""

    device_id: str
    device_model: str
    device_type: DeviceType
    attributes: dict[str, AttributeCapability] = field(default_factory=dict)
    mqtt_subscribed: bool = False
    mqtt_subscription_error: str | None = None
    mqtt_subscription_time: Any = None
    last_mqtt_activity: Any = None
    fallback_active: bool = False
    fallback_reason: str | None = None
    fallback_activated_time: Any = None
    fallback_count: int = 0
    available: bool = True
    offline_reason: str | None = None
    offline_since: Any = None

    def register_attribute(
        self,
        attribute_id: str,
        display_name: str = "",
        has_official: bool = False,
        has_community: bool = True,
        prefer_official: bool = True,
        fallback_strategy: str = "polling",
    ) -> None:
        """Register a new attribute capability."""
        if attribute_id in self.attributes:
            capability = self.attributes[attribute_id]
            capability.has_official = capability.has_official or has_official
            capability.has_community = capability.has_community or has_community
            return

        self.attributes[attribute_id] = AttributeCapability(
            attribute_id=attribute_id,
            display_name=display_name or attribute_id,
            has_official=has_official,
            has_community=has_community,
            prefer_official=prefer_official,
            fallback_strategy=fallback_strategy,
        )

    def update_attribute_official(self, attribute_id: str, value: Any) -> None:
        """Update an attribute's official value."""
        if attribute_id not in self.attributes:
            self.register_attribute(attribute_id, has_official=True, has_community=False)
        self.attributes[attribute_id].update_official(value)
        self.last_mqtt_activity = utcnow()

    def update_attribute_community(self, attribute_id: str, value: Any) -> None:
        """Update an attribute's community value."""
        if attribute_id not in self.attributes:
            self.register_attribute(attribute_id, has_official=False, has_community=True)
        self.attributes[attribute_id].update_community(value)

    def get_attribute(self, attribute_id: str) -> AttributeCapability | None:
        """Get attribute capability by ID."""
        return self.attributes.get(attribute_id)

    def get_logical_attributes(self) -> dict[str, AttributeCapability]:
        """Return logical attributes excluding raw diagnostic-only fields."""
        return {
            attr_id: capability
            for attr_id, capability in self.attributes.items()
            if is_logical_attribute_id(attr_id)
        }

    def get_logical_attribute_summary(self) -> dict[str, Any]:
        """Return summary counts for logical attributes."""
        logical_attributes = self.get_logical_attributes()
        community_only = [
            attr_id
            for attr_id, capability in logical_attributes.items()
            if capability.has_community and not capability.has_official
        ]
        official_capable = [
            attr_id
            for attr_id, capability in logical_attributes.items()
            if capability.has_official
        ]
        return {
            "total": len(logical_attributes),
            "official_capable": len(official_capable),
            "community_only": len(community_only),
            "community_only_attributes": sorted(community_only),
            "fully_official_covered": bool(logical_attributes) and not community_only,
        }

    def activate_fallback(self, reason: str = "unknown") -> None:
        """Activate fallback mode."""
        if not self.fallback_active:
            self.fallback_activated_time = utcnow()
            self.fallback_count += 1

        self.fallback_active = True
        self.fallback_reason = reason
        self.mqtt_subscribed = False

        for capability in self.attributes.values():
            capability.mark_official_stale()

        _LOGGER.warning("Device %s fallback activated: %s", self.device_id, reason)

    def deactivate_fallback(self) -> None:
        """Deactivate fallback mode."""
        self.fallback_active = False
        self.fallback_reason = None

    def mark_online(self) -> None:
        """Mark the device as online and clear offline status."""
        self.available = True
        self.offline_reason = None
        self.offline_since = None

    def mark_offline(self, reason: str) -> None:
        """Mark the device as offline or externally powered off."""
        self.available = False
        self.offline_reason = reason
        if self.offline_since is None:
            self.offline_since = utcnow()

    def is_known_offline(self) -> bool:
        """Return whether the device is currently marked offline."""
        return not self.available

    def to_dict(self) -> dict[str, Any]:
        """Convert to a diagnostic dictionary."""
        return {
            "device_id": self.device_id,
            "device_model": self.device_model,
            "device_type": self.device_type.name,
            "mqtt_subscribed": self.mqtt_subscribed,
            "mqtt_subscription_error": self.mqtt_subscription_error,
            "mqtt_subscription_time": (
                self.mqtt_subscription_time.isoformat()
                if self.mqtt_subscription_time is not None
                else None
            ),
            "last_mqtt_activity": (
                self.last_mqtt_activity.isoformat()
                if self.last_mqtt_activity is not None
                else None
            ),
            "fallback_active": self.fallback_active,
            "fallback_reason": self.fallback_reason,
            "fallback_count": self.fallback_count,
            "available": self.available,
            "offline_reason": self.offline_reason,
            "offline_since": (
                self.offline_since.isoformat()
                if self.offline_since is not None
                else None
            ),
            "logical_attributes": self.get_logical_attribute_summary(),
            "attributes": {
                attr_id: capability.to_dict()
                for attr_id, capability in self.attributes.items()
            },
        }


class CapabilityRegistry:
    """Global registry of device capabilities."""

    def __init__(self) -> None:
        """Initialize registry."""
        self._profiles: dict[str, DeviceCapabilityProfile] = {}

    def register_device(
        self,
        device_id: str,
        device_model: str,
        device_type: DeviceType,
    ) -> DeviceCapabilityProfile:
        """Register or retrieve a device capability profile."""
        if device_id not in self._profiles:
            self._profiles[device_id] = DeviceCapabilityProfile(
                device_id=device_id,
                device_model=device_model,
                device_type=device_type,
            )
        return self._profiles[device_id]

    def get_profile(self, device_id: str) -> DeviceCapabilityProfile | None:
        """Get a device capability profile."""
        return self._profiles.get(device_id)

    def all_profiles(self) -> dict[str, DeviceCapabilityProfile]:
        """Get all profiles."""
        return self._profiles.copy()

    def has_official_capability(self, device_id: str, attribute_id: str) -> bool:
        """Check whether a device has official support for an attribute."""
        profile = self.get_profile(device_id)
        if not profile:
            return False
        capability = profile.get_attribute(attribute_id)
        return bool(capability and capability.has_official)

    def get_preferred_value(
        self,
        device_id: str,
        attribute_id: str,
    ) -> tuple[Any, str]:
        """Get preferred value for an attribute."""
        profile = self.get_profile(device_id)
        if not profile:
            return None, "unknown"
        capability = profile.get_attribute(attribute_id)
        if not capability:
            return None, "unknown"
        return capability.get_preferred_value()

    def to_dict(self) -> dict[str, Any]:
        """Export all capabilities as a dictionary."""
        return {
            device_id: profile.to_dict()
            for device_id, profile in self._profiles.items()
        }

    def to_json(self) -> str:
        """Export all capabilities as JSON."""
        try:
            return json.dumps(self.to_dict(), indent=2)
        except TypeError:
            _LOGGER.exception("Failed to export capability registry as JSON")
            return "{}"
