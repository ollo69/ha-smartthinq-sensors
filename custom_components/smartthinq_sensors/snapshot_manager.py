"""Shared ThinQ snapshot caching for community API devices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .wideq.core_async import ClientAsync


class CommunitySnapshotManager:
    """Cache ThinQ2 dashboard snapshots across all devices for one account."""

    def __init__(
        self,
        client: ClientAsync,
        min_refresh_interval: timedelta = timedelta(seconds=25),
    ) -> None:
        """Initialize the snapshot manager."""
        self._client = client
        self._min_refresh_interval = min_refresh_interval
        self._last_refresh: datetime | None = None

    async def async_refresh_if_needed(self, *, force: bool = False) -> None:
        """Refresh the shared snapshot cache when stale."""
        if not force and self._last_refresh is not None:
            age = datetime.now(UTC) - self._last_refresh
            if age < self._min_refresh_interval:
                return

        await self._client.refresh_devices()
        self._last_refresh = datetime.now(UTC)

    async def async_get_snapshot(
        self,
        device_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        """Return the cached snapshot for one device."""
        await self.async_refresh_if_needed(force=force_refresh)
        if device_data := self._client.get_device(device_id):
            if snapshot := device_data.snapshot:
                return dict(snapshot)
        return None

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information for the shared snapshot cache."""
        return {
            "min_refresh_interval_seconds": self._min_refresh_interval.total_seconds(),
            "last_refresh": (
                self._last_refresh.isoformat() if self._last_refresh else None
            ),
        }
