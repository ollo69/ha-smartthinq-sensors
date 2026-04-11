"""Error handling and fallback mechanisms for hybrid API sources."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow

from .capability_registry import CapabilityRegistry
from .coordinator_hybrid import HybridDataCoordinator

_LOGGER = logging.getLogger(__name__)


class FallbackStrategy:
    """Base class for fallback strategies."""

    async def should_activate(self) -> bool:
        """Determine whether fallback should be activated."""
        return False

    async def activate(self) -> None:
        """Activate fallback."""

    async def deactivate(self) -> None:
        """Deactivate fallback."""


class MQTTConnectionFailureFallback(FallbackStrategy):
    """Fallback activated when MQTT connection fails."""

    def __init__(
        self,
        device_id: str,
        coordinator: HybridDataCoordinator,
        registry: CapabilityRegistry,
        max_consecutive_failures: int = 3,
    ) -> None:
        """Initialize fallback."""
        self._device_id = device_id
        self._coordinator = coordinator
        self._registry = registry
        self._max_consecutive_failures = max_consecutive_failures
        self._consecutive_failures = 0

    async def should_activate(self) -> bool:
        """Activate on MQTT connection failures."""
        profile = self._registry.get_profile(self._device_id)
        if profile and profile.fallback_active:
            return False
        if self._coordinator.get_mqtt_health().get("mqtt_healthy"):
            self._consecutive_failures = 0
            return False
        self._consecutive_failures += 1
        return self._consecutive_failures >= self._max_consecutive_failures

    async def activate(self) -> None:
        """Activate MQTT fallback."""
        profile = self._registry.get_profile(self._device_id)
        if profile:
            profile.activate_fallback("MQTT connection failure")
        self._coordinator.mark_mqtt_disconnected("Connection failed")
        self._consecutive_failures = 0

    async def deactivate(self) -> None:
        """Deactivate fallback when MQTT recovers."""
        profile = self._registry.get_profile(self._device_id)
        if profile:
            profile.deactivate_fallback()
        self._consecutive_failures = 0


class MQTTDataStaleFallback(FallbackStrategy):
    """Fallback activated when MQTT data becomes stale."""

    def __init__(
        self,
        device_id: str,
        coordinator: HybridDataCoordinator,
        registry: CapabilityRegistry,
        stale_threshold: timedelta = timedelta(minutes=5),
    ) -> None:
        """Initialize fallback."""
        self._device_id = device_id
        self._coordinator = coordinator
        self._registry = registry
        self._stale_threshold = stale_threshold

    async def should_activate(self) -> bool:
        """Activate if MQTT data is too stale."""
        profile = self._registry.get_profile(self._device_id)
        if not profile or profile.fallback_active or profile.last_mqtt_activity is None:
            return False
        return bool(utcnow() - profile.last_mqtt_activity > self._stale_threshold)

    async def activate(self) -> None:
        """Activate stale-data fallback."""
        profile = self._registry.get_profile(self._device_id)
        if profile:
            profile.activate_fallback("MQTT data stale")

    async def deactivate(self) -> None:
        """Deactivate when fresh MQTT data arrives."""
        profile = self._registry.get_profile(self._device_id)
        if profile:
            profile.deactivate_fallback()


class DataConflictFallback(FallbackStrategy):
    """Fallback activated when source data conflicts significantly."""

    def __init__(
        self,
        device_id: str,
        coordinator: HybridDataCoordinator,
        registry: CapabilityRegistry,
        conflict_threshold_percent: float = 20.0,
    ) -> None:
        """Initialize fallback."""
        self._device_id = device_id
        self._coordinator = coordinator
        self._registry = registry
        self._conflict_threshold_percent = conflict_threshold_percent

    async def should_activate(self) -> bool:
        """Activate if critical data conflicts are detected."""
        profile = self._registry.get_profile(self._device_id)
        if not profile or profile.fallback_active:
            return False
        for capability in profile.attributes.values():
            official = capability.official_value
            community = capability.community_value
            if official is None or community is None:
                continue
            if isinstance(official, (int, float)) and isinstance(community, (int, float)) and official != 0:
                percent_diff = abs((community - official) / official) * 100
                if percent_diff > self._conflict_threshold_percent:
                    return True
            if isinstance(official, str) and official != community:
                return True
        return False

    async def activate(self) -> None:
        """Activate conflict fallback."""
        profile = self._registry.get_profile(self._device_id)
        if profile:
            profile.activate_fallback("Data conflicts detected")

    async def deactivate(self) -> None:
        """Deactivate when conflicts are resolved."""
        profile = self._registry.get_profile(self._device_id)
        if profile:
            profile.deactivate_fallback()


class FallbackManager:
    """Manage fallback strategies for a device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        coordinator: HybridDataCoordinator,
        registry: CapabilityRegistry,
    ) -> None:
        """Initialize fallback manager."""
        self._hass = hass
        self._device_id = device_id
        self._coordinator = coordinator
        self._registry = registry
        self._strategies: list[FallbackStrategy] = [
            MQTTConnectionFailureFallback(device_id, coordinator, registry),
            MQTTDataStaleFallback(device_id, coordinator, registry),
            DataConflictFallback(device_id, coordinator, registry),
        ]
        self._active_strategy: FallbackStrategy | None = None

    async def async_check_and_update(self) -> None:
        """Check whether any fallback should be activated or deactivated."""
        for strategy in self._strategies:
            if await strategy.should_activate():
                if self._active_strategy is not strategy:
                    if self._active_strategy is not None:
                        await self._active_strategy.deactivate()
                    await strategy.activate()
                    self._active_strategy = strategy
                return

        if self._active_strategy is not None:
            await self._active_strategy.deactivate()
            self._active_strategy = None

    def get_status(self) -> dict[str, Any]:
        """Get fallback status."""
        return {
            "fallback_active": self._active_strategy is not None,
            "active_strategy": (
                type(self._active_strategy).__name__ if self._active_strategy else None
            ),
        }


class StaleDataHandler:
    """Handle detection and recovery from stale MQTT data."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        stale_threshold: timedelta = timedelta(minutes=5),
        recovery_strategy: str = "polling",
    ) -> None:
        """Initialize handler."""
        self._registry = registry
        self._stale_threshold = stale_threshold
        self._recovery_strategy = recovery_strategy

    def detect_stale_data(self, device_id: str) -> list[str]:
        """Detect which attributes have stale official data."""
        profile = self._registry.get_profile(device_id)
        if not profile:
            return []
        return [
            attr_id
            for attr_id, capability in profile.attributes.items()
            if capability.has_official and capability.is_stale(self._stale_threshold)
        ]

    async def recover_from_stale(self, device_id: str) -> bool:
        """Attempt recovery from stale data."""
        profile = self._registry.get_profile(device_id)
        if not profile:
            return False

        stale = self.detect_stale_data(device_id)
        if not stale:
            return True

        if self._recovery_strategy == "skip":
            for attr_id in stale:
                capability = profile.get_attribute(attr_id)
                if capability:
                    capability.fallback_strategy = "skip"
        return True


class RecoveryStrategy:
    """Strategy for recovering from errors."""

    def __init__(self) -> None:
        """Initialize."""
        self._retry_count = 0
        self._max_retries = 5
        self._last_retry_time: datetime | None = None

    async def should_retry(self) -> bool:
        """Check whether a retry should be attempted."""
        if self._retry_count >= self._max_retries:
            return False
        if self._last_retry_time is None:
            return True
        return utcnow() - self._last_retry_time > timedelta(seconds=1)

    async def execute_with_retry(
        self,
        coroutine_func: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a coroutine with automatic retry."""
        while self._retry_count < self._max_retries:
            try:
                result = await coroutine_func(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except (RuntimeError, TimeoutError, ValueError) as exc:
                self._retry_count += 1
                self._last_retry_time = utcnow()
                if self._retry_count >= self._max_retries:
                    _LOGGER.error("Failed after %d retries: %s", self._max_retries, exc)
                    return None
                await asyncio.sleep(2**self._retry_count)
            else:
                self._retry_count = 0
                self._last_retry_time = None
                return result
        return None

    def reset(self) -> None:
        """Reset retry counter."""
        self._retry_count = 0
        self._last_retry_time = None
