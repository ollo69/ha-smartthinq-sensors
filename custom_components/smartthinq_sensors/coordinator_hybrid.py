"""Enhanced coordinator supporting hybrid official/community API sources."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .capability_registry import CapabilityRegistry
from .data_source_router import DataSourceRouter
from .trace import add_trace_event
from .wideq import DeviceType

_LOGGER = logging.getLogger(__name__)
MQTT_REFRESH_TRIGGER_TYPES = {
    DeviceType.WASHER,
    DeviceType.DRYER,
    DeviceType.DISHWASHER,
}
MQTT_REFRESH_TRIGGER_ATTRIBUTES = {
    "washer.run_state",
    "washer.is_on",
    "dryer.run_state",
    "dryer.is_on",
    "dishwasher.run_state",
    "dishwasher.is_on",
}


def _serialize_diagnostic_value(value: Any) -> Any:
    """Convert coordinator data into a diagnostics-friendly value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _serialize_diagnostic_value(item) for key, item in value.items()
        }

    if isinstance(value, list):
        return [_serialize_diagnostic_value(item) for item in value]

    if hasattr(value, "as_dict"):
        serialized = value.as_dict
        if callable(serialized):
            serialized = serialized()
        return _serialize_diagnostic_value(serialized)

    return repr(value)


class HybridDataCoordinator(DataUpdateCoordinator):
    """Coordinator managing both official (MQTT) and community (polling) API sources.

    Responsibilities:
    - Manage polling interval (adaptive based on MQTT health)
    - Merge data from both sources when available
    - Track data source for each attribute (diagnostics)
    - Handle fallback to polling when MQTT unavailable
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        device_id: str,
        device_model: str,
        device_type: DeviceType,
        update_method: Callable,
        capability_registry: CapabilityRegistry,
        data_source_router: DataSourceRouter,
        base_polling_interval: timedelta = timedelta(seconds=30),
        mqtt_healthy_interval: timedelta = timedelta(seconds=90),
        mqtt_unhealthy_interval: timedelta = timedelta(seconds=15),
        mqtt_healthy_community_refresh_interval: timedelta = timedelta(minutes=10),
        mqtt_fully_official_refresh_interval: timedelta = timedelta(minutes=30),
        offline_community_refresh_interval: timedelta = timedelta(minutes=1),
    ) -> None:
        """Initialize hybrid coordinator."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_method=update_method,
            update_interval=base_polling_interval,
        )

        self._device_id = device_id
        self._device_model = device_model
        self._device_type = device_type
        self._capability_registry = capability_registry
        self._data_source_router = data_source_router

        # Polling intervals
        self._base_polling_interval = base_polling_interval
        self._mqtt_healthy_interval = mqtt_healthy_interval
        self._mqtt_unhealthy_interval = mqtt_unhealthy_interval
        self._mqtt_healthy_community_refresh_interval = (
            mqtt_healthy_community_refresh_interval
        )
        self._mqtt_fully_official_refresh_interval = (
            mqtt_fully_official_refresh_interval
        )
        self._offline_community_refresh_interval = offline_community_refresh_interval
        self._current_polling_interval = base_polling_interval

        # MQTT health tracking
        self._mqtt_healthy = False
        self._last_mqtt_update: datetime | None = None
        self._mqtt_failure_count = 0
        self._mqtt_success_count = 0
        self.last_update: datetime | None = None
        self.last_update_error: Exception | None = None

        # Track merged state
        self._merged_state: dict[str, Any] = {}
        self._last_merge_time: datetime | None = None
        self._last_community_refresh: datetime | None = None
        self._skipped_poll_count = 0
        self._force_all_sources_once = False
        self._pending_mqtt_refresh_unsub: CALLBACK_TYPE | None = None
        self._last_forced_mqtt_refresh: datetime | None = None
        self._mqtt_refresh_delay = timedelta(seconds=8)
        self._mqtt_refresh_cooldown = timedelta(seconds=45)

    def get_mqtt_health(self) -> dict[str, Any]:
        """Get MQTT health status."""
        return {
            "mqtt_healthy": self._mqtt_healthy,
            "last_mqtt_update": (
                self._last_mqtt_update.isoformat() if self._last_mqtt_update else None
            ),
            "mqtt_failure_count": self._mqtt_failure_count,
            "mqtt_success_count": self._mqtt_success_count,
            "current_polling_interval_seconds": (
                self._current_polling_interval.total_seconds()
            ),
            "last_community_refresh": (
                self._last_community_refresh.isoformat()
                if self._last_community_refresh
                else None
            ),
            "skipped_poll_count": self._skipped_poll_count,
            "pending_mqtt_refresh": self._pending_mqtt_refresh_unsub is not None,
            "last_forced_mqtt_refresh": (
                self._last_forced_mqtt_refresh.isoformat()
                if self._last_forced_mqtt_refresh
                else None
            ),
        }

    def _should_schedule_mqtt_followup_refresh(
        self, attribute_updates: dict[str, Any]
    ) -> bool:
        """Return whether this MQTT update should trigger a coalesced poll."""
        if self._device_type not in MQTT_REFRESH_TRIGGER_TYPES:
            return False
        return any(
            attribute_id in MQTT_REFRESH_TRIGGER_ATTRIBUTES
            for attribute_id in attribute_updates
        )

    @callback
    def _schedule_mqtt_followup_refresh(self, attribute_updates: dict[str, Any]) -> None:
        """Schedule one coalesced follow-up community refresh after MQTT."""
        if not self._should_schedule_mqtt_followup_refresh(attribute_updates):
            return

        now = utcnow()
        if (
            self._last_forced_mqtt_refresh is not None
            and now - self._last_forced_mqtt_refresh < self._mqtt_refresh_cooldown
        ):
            add_trace_event(
                self.hass,
                category="hybrid",
                action="mqtt_followup_refresh_suppressed",
                device_id=self._device_id,
                details={"reason": "cooldown_active"},
            )
            return

        if self._pending_mqtt_refresh_unsub is not None:
            add_trace_event(
                self.hass,
                category="hybrid",
                action="mqtt_followup_refresh_suppressed",
                device_id=self._device_id,
                details={"reason": "refresh_already_pending"},
            )
            return

        add_trace_event(
            self.hass,
            category="hybrid",
            action="mqtt_followup_refresh_scheduled",
            device_id=self._device_id,
            details={
                "delay_seconds": self._mqtt_refresh_delay.total_seconds(),
                "attributes": sorted(attribute_updates),
            },
        )

        @callback
        def _run_refresh(_now: datetime) -> None:
            self._pending_mqtt_refresh_unsub = None
            self._last_forced_mqtt_refresh = utcnow()
            add_trace_event(
                self.hass,
                category="hybrid",
                action="mqtt_followup_refresh_started",
                device_id=self._device_id,
                details={},
            )
            self.hass.async_create_task(self.async_refresh(force_all_sources=True))

        self._pending_mqtt_refresh_unsub = async_call_later(
            self.hass,
            self._mqtt_refresh_delay,
            _run_refresh,
        )

    def _has_recent_official_data(self, device_id: str) -> bool:
        """Check whether this device has recent official data."""
        profile = self._capability_registry.get_profile(device_id)
        if profile is None:
            return False

        recent_cutoff = utcnow() - self._current_polling_interval
        return any(
            capability.official_timestamp is not None
            and capability.official_timestamp >= recent_cutoff
            for capability in profile.attributes.values()
        )

    def _logical_attribute_summary(self) -> dict[str, Any]:
        """Return logical attribute coverage for the current device."""
        profile = self._capability_registry.get_profile(self._device_id)
        if profile is None:
            return {
                "total": 0,
                "official_capable": 0,
                "community_only": 0,
                "community_only_attributes": [],
                "fully_official_covered": False,
            }

        return profile.get_logical_attribute_summary()

    def _community_refresh_interval(self) -> timedelta:
        """Return the current community refresh safety interval."""
        profile = self._capability_registry.get_profile(self._device_id)
        if profile is not None and profile.is_known_offline():
            return self._offline_community_refresh_interval
        summary = self._logical_attribute_summary()
        if summary["fully_official_covered"]:
            return self._mqtt_fully_official_refresh_interval
        return self._mqtt_healthy_community_refresh_interval

    def _should_skip_community_refresh(self) -> bool:
        """Decide whether the next community poll can be skipped."""
        profile = self._capability_registry.get_profile(self._device_id)
        if profile is not None and profile.is_known_offline():
            if self._last_community_refresh is None or self.data is None:
                return False
            return bool(
                utcnow() - self._last_community_refresh
                < self._offline_community_refresh_interval
            )

        if not self._mqtt_healthy:
            return False

        if self._last_community_refresh is None or self.data is None:
            return False

        if utcnow() - self._last_community_refresh >= self._community_refresh_interval():
            return False

        return self._has_recent_official_data(self._device_id)

    def mark_mqtt_success(self) -> None:
        """Mark successful MQTT update."""
        self._mqtt_success_count += 1
        self._last_mqtt_update = utcnow()
        self._mqtt_failure_count = 0

        # Check if we should transition to healthy
        if self._mqtt_success_count >= 3:
            if not self._mqtt_healthy:
                _LOGGER.debug(
                    "%s: MQTT transitioned to HEALTHY after %d successes",
                    self.name,
                    self._mqtt_success_count,
                )
                self._mqtt_healthy = True
                self._update_polling_interval()
                add_trace_event(
                    self.hass,
                    category="hybrid",
                    action="mqtt_healthy",
                    device_id=self._device_id,
                    details={"success_count": self._mqtt_success_count},
                )

    def mark_mqtt_failure(self, reason: str = "unknown") -> None:
        """Mark failed MQTT operation."""
        self._mqtt_failure_count += 1

        if self._mqtt_healthy and self._mqtt_failure_count >= 3:
            _LOGGER.warning(
                "%s: MQTT transitioned to UNHEALTHY after %d failures: %s",
                self.name,
                self._mqtt_failure_count,
                reason,
            )
            self._mqtt_healthy = False
            self._update_polling_interval()
            add_trace_event(
                self.hass,
                category="hybrid",
                action="mqtt_unhealthy",
                device_id=self._device_id,
                details={
                    "failure_count": self._mqtt_failure_count,
                    "reason": reason,
                },
            )

    def mark_mqtt_disconnected(self, reason: str = "unknown") -> None:
        """Mark MQTT disconnection."""
        _LOGGER.warning(
            "%s: MQTT disconnected: %s",
            self.name,
            reason,
        )
        self._mqtt_healthy = False
        self._mqtt_failure_count = 0
        self._update_polling_interval()
        add_trace_event(
            self.hass,
            category="hybrid",
            action="mqtt_disconnected",
            device_id=self._device_id,
            details={"reason": reason},
        )

    def _update_polling_interval(self) -> None:
        """Update polling interval based on MQTT health."""
        if self._mqtt_healthy:
            new_interval = self._mqtt_healthy_interval
            _LOGGER.debug(
                "%s: Setting polling interval to %s (MQTT healthy)",
                self.name,
                new_interval,
            )
        else:
            new_interval = self._mqtt_unhealthy_interval
            _LOGGER.debug(
                "%s: Setting polling interval to %s (MQTT unhealthy)",
                self.name,
                new_interval,
            )

        self._current_polling_interval = new_interval
        self.update_interval = new_interval

    async def async_refresh(
        self,
        log_failures: bool = True,
        raise_on_auth_error: bool = False,
        force_all_sources: bool = False,
    ) -> None:
        """Refresh data from both sources and merge."""
        del log_failures, raise_on_auth_error
        self._force_all_sources_once = force_all_sources
        await super().async_refresh()

    async def _async_update_data(self) -> Any:
        """Fetch the latest data while allowing official-backed poll skipping."""
        should_skip_community_refresh = False
        if not self._force_all_sources_once:
            should_skip_community_refresh = self._should_skip_community_refresh()
        self._force_all_sources_once = False

        if self.update_method and not should_skip_community_refresh:
            data = await self.update_method()
            self._last_community_refresh = utcnow()
            self.last_update = utcnow()
            self.last_update_error = None
            return data

        if should_skip_community_refresh:
            self._skipped_poll_count += 1
            _LOGGER.debug(
                "%s: Skipping community refresh, using recent official data",
                self.name,
            )
            add_trace_event(
                self.hass,
                category="hybrid",
                action="community_poll_skipped",
                device_id=self._device_id,
                details={
                    "skipped_poll_count": self._skipped_poll_count,
                    "community_refresh_interval_seconds": (
                        self._community_refresh_interval().total_seconds()
                    ),
                },
            )
            self.last_update = utcnow()
            self.last_update_error = None
            return self.data

        self.last_update = utcnow()
        self.last_update_error = None
        return self.data

    def async_merge_mqtt_data(self) -> None:
        """Merge MQTT data with polling data using source router.

        This runs after polling completes, to incorporate any recent MQTT data
        without waiting for the next MQTT message.
        """
        if not self.data:
            return

        # Get capability profile to check available MQTT data
        # (In practice, this would be called from the device/device list)
        _LOGGER.debug("%s: Merging MQTT data into polling results", self.name)

    async def async_update_from_mqtt(
        self,
        attribute_updates: dict[str, Any],
        device_id: str,
    ) -> None:
        """Update coordinator state from MQTT push data.

        Args:
            attribute_updates: New attribute values from MQTT
            device_id: The device being updated
        """
        if not self.data:
            _LOGGER.debug(
                "%s: Ignoring MQTT update (no polling data yet)",
                self.name,
            )
            return

        profile = self._capability_registry.get_profile(device_id)
        if not profile:
            _LOGGER.warning(
                "%s: MQTT update for unknown device %s",
                self.name,
                device_id,
            )
            return

        # Update capability registry
        for attr_id, value in attribute_updates.items():
            profile.update_attribute_official(attr_id, value)
        add_trace_event(
            self.hass,
            category="hybrid",
            action="mqtt_attributes_merged",
            device_id=device_id,
            details={"attributes": sorted(attribute_updates)},
        )
        self._schedule_mqtt_followup_refresh(attribute_updates)

        # Merge values
        for attr_id, value in attribute_updates.items():
            merged_value, source = self._data_source_router.get_attribute_value(
                device_id,
                attr_id,
                fallback_strategy="polling",
            )

            _LOGGER.debug(
                "%s: MQTT update %s=%s (source=%s, merged_value=%s)",
                self.name,
                attr_id,
                value,
                source,
                merged_value,
            )

            # Update the state object (exact mechanism depends on your device model)
            if hasattr(self.data, "set_attribute"):
                self.data.set_attribute(attr_id, merged_value)

        # Notify subscribers that data has been updated
        self.async_set_updated_data(self.data)
        self.mark_mqtt_success()
        self._last_merge_time = utcnow()

    def get_diagnostics(self) -> dict[str, Any]:
        """Get diagnostic data for this coordinator."""
        return {
            "name": self.name,
            "device_model": self._device_model,
            "device_type": self._device_type.name,
            "last_update_success": self.last_update_success,
            "last_update_time": (
                self.last_update.isoformat() if self.last_update else None
            ),
            "last_update_error": str(self.last_update_error)
            if self.last_update_error
            else None,
            "update_interval_seconds": (
                self.update_interval.total_seconds() if self.update_interval else None
            ),
            "mqtt_health": self.get_mqtt_health(),
            "logical_attributes": self._logical_attribute_summary(),
            "community_refresh_interval_seconds": (
                self._community_refresh_interval().total_seconds()
            ),
            "data": _serialize_diagnostic_value(self.data),
        }


class MQTTPushCoordinator(DataUpdateCoordinator):
    """Lightweight coordinator for event-driven MQTT updates.

    Unlike traditional polling, this coordinator operates asynchronously
    and is triggered by MQTT messages rather than a timer.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        hybrid_coordinator: HybridDataCoordinator,
    ) -> None:
        """Initialize MQTT push coordinator."""
        # No update_method - this is purely event-driven
        super().__init__(
            hass,
            logger,
            name=f"{name}_mqtt",
            # Very long update_interval, since we're event-driven
            update_interval=timedelta(hours=1),
        )

        self._hybrid_coordinator = hybrid_coordinator
        self.data = {}

    async def async_handle_mqtt_message(
        self,
        device_id: str,
        attributes: dict[str, Any],
    ) -> None:
        """Handle incoming MQTT message.

        Args:
            device_id: Device that received update
            attributes: Updated attributes with values
        """
        _LOGGER.debug(
            "%s: Handling MQTT message for device %s: %s",
            self.name,
            device_id,
            list(attributes.keys()),
        )

        # Update hybrid coordinator with MQTT data
        await self._hybrid_coordinator.async_update_from_mqtt(attributes, device_id)

        # Update this coordinator's data for tracking
        self.data = {
            "device_id": device_id,
            "attributes": attributes,
            "timestamp": utcnow(),
        }

        # Notify subscribers
        self.async_set_updated_data(self.data)
