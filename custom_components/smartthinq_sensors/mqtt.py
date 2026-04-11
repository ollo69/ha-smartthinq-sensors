"""ThinQ MQTT support for direct official push updates with community fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
import json
import logging
from typing import Any

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException, ThinQMQTTClient

from homeassistant.core import Event, HomeAssistant

from .const import DOMAIN
from .wideq.core_async import ClientAsync

_LOGGER = logging.getLogger(__name__)

CAPABILITY_REGISTRY = "capability_registry"
OFFICIAL_LGE_DEVICES = "official_lge_devices"
ALREADY_SUBSCRIBED_PUSH = getattr(
    ThinQAPIErrorCodes, "ALREADY_SUBSCRIBED_PUSH", None
)


class ThinQMQTTHandler:
    """Manage ThinQ MQTT lifecycle and route push updates to wrapped devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        official_api: Any,
        client: ClientAsync,
        official_client_id: str,
        refresh_callback: Callable[[ClientAsync, Any], Awaitable[bool]] | None = None,
    ) -> None:
        """Initialize MQTT handler."""
        self._hass = hass
        self._official_api = official_api
        self._client = client
        self._official_client_id = official_client_id
        self._refresh_callback = refresh_callback
        self._mqtt: ThinQMQTTClient | None = None

    async def async_connect(self) -> bool:
        """Create the MQTT client and prepare it."""
        self._mqtt = await ThinQMQTTClient(
            self._official_api,
            self._official_client_id,
            self.on_message_received,
        )
        if self._mqtt is None:
            return False
        return bool(await self._mqtt.async_prepare_mqtt())

    async def async_disconnect(self, event: Event | None = None) -> None:
        """Disconnect the ThinQ MQTT client."""
        await self.async_end_subscribes()
        if self._mqtt is not None:
            try:
                await self._mqtt.async_disconnect()
            except (ThinQAPIException, TypeError, ValueError):
                _LOGGER.exception("Failed to disconnect ThinQ MQTT")
            self._mqtt = None

    def _get_failed_device_count(
        self,
        results: list[dict[str, Any] | BaseException | None],
    ) -> int:
        """Return count of failed subscription tasks."""
        return sum(
            isinstance(result, (TypeError, ValueError))
            or (
                isinstance(result, ThinQAPIException)
                and result.code != ALREADY_SUBSCRIBED_PUSH
            )
            for result in results
        )

    async def async_start_subscribes(self) -> None:
        """Subscribe to push/event topics and then connect MQTT."""
        if self._mqtt is None:
            _LOGGER.error("Failed to start ThinQ MQTT subscription: no client")
            return

        official_devices = self._hass.data[DOMAIN].get(OFFICIAL_LGE_DEVICES, {})
        tasks = [
            self._hass.async_create_task(
                self._official_api.async_post_push_subscribe(official_device_id)
            )
            for official_device_id in official_devices
        ]
        tasks.extend(
            self._hass.async_create_task(
                self._official_api.async_post_event_subscribe(official_device_id)
            )
            for official_device_id in official_devices
        )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if (count := self._get_failed_device_count(results)) > 0:
                _LOGGER.error("Failed to start ThinQ MQTT subscription on %s devices", count)

        await self._mqtt.async_connect_mqtt()

    async def async_refresh_subscribe(self, now: datetime | None = None) -> None:
        """Refresh event subscriptions periodically."""
        _LOGGER.debug("ThinQ MQTT async_refresh_subscribe: now=%s", now)
        official_devices = self._hass.data[DOMAIN].get(OFFICIAL_LGE_DEVICES, {})
        tasks = [
            self._hass.async_create_task(
                self._official_api.async_post_event_subscribe(official_device_id)
            )
            for official_device_id in official_devices
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if (count := self._get_failed_device_count(results)) > 0:
                _LOGGER.error("Failed to refresh ThinQ MQTT subscription on %s devices", count)

    async def async_end_subscribes(self) -> None:
        """Unsubscribe push/event topics."""
        official_devices = self._hass.data[DOMAIN].get(OFFICIAL_LGE_DEVICES, {})
        tasks = [
            self._hass.async_create_task(
                self._official_api.async_delete_push_subscribe(official_device_id)
            )
            for official_device_id in official_devices
        ]
        tasks.extend(
            self._hass.async_create_task(
                self._official_api.async_delete_event_subscribe(official_device_id)
            )
            for official_device_id in official_devices
        )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if (count := self._get_failed_device_count(results)) > 0:
                _LOGGER.error("Failed to end ThinQ MQTT subscription on %s devices", count)

    def on_message_received(
        self,
        topic: str,
        payload: bytes,
        dup: bool,
        qos: Any,
        retain: bool,
        **kwargs: dict[str, Any],
    ) -> None:
        """Handle the received MQTT message."""
        del topic, dup, qos, retain, kwargs
        decoded = payload.decode()
        try:
            message = json.loads(decoded)
        except ValueError:
            _LOGGER.error("Failed to parse ThinQ MQTT message: payload=%s", decoded)
            return

        asyncio.run_coroutine_threadsafe(
            self._async_handle_message(message),
            self._hass.loop,
        ).result()

    async def _async_handle_message(self, message: dict[str, Any]) -> None:
        """Route MQTT message to the correct wrapped device."""
        official_device_id = message.get("deviceId")
        if not official_device_id:
            _LOGGER.debug("ThinQ MQTT message missing deviceId: %s", message)
            return

        official_devices = self._hass.data[DOMAIN].get(OFFICIAL_LGE_DEVICES, {})
        lge_dev = official_devices.get(official_device_id)
        if lge_dev is None:
            _LOGGER.debug(
                "ThinQ MQTT message for unknown official_device=%s",
                official_device_id,
            )
            return

        updated = lge_dev.apply_mqtt_update(message)
        if not updated and self._refresh_callback is not None:
            refreshed = await self._refresh_callback(self._client, lge_dev)
            if not refreshed:
                return
            lge_dev.async_set_updated()

        domain_data = self._hass.data.get(DOMAIN, {})
        capability_registry = domain_data.get(CAPABILITY_REGISTRY)
        hybrid_coordinators = domain_data.get("hybrid_coordinators", {})
        device_id = lge_dev.device_id

        if capability_registry and device_id:
            profile = capability_registry.get_profile(device_id)
            if profile:
                for attr_name, attr_value in message.items():
                    if attr_name not in {"deviceId", "timestamp", "pushType"}:
                        profile.register_attribute(attr_name, has_official=True)
                        profile.update_attribute_official(attr_name, attr_value)

        coordinator = hybrid_coordinators.get(device_id)
        if coordinator is not None:
            coordinator.mark_mqtt_success()
            await coordinator.async_update_from_mqtt(message, device_id)
