"""ThinQ MQTT support for push-triggered official refresh."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException, ThinQMQTTClient

from .const import DOMAIN, OFFICIAL_LGE_DEVICES
from .wideq.core_async import ClientAsync

_LOGGER = logging.getLogger(__name__)


class ThinQMQTTHandler:
    """Manage ThinQ MQTT lifecycle and route push updates to wrapped devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        official_api,
        client: ClientAsync,
        official_client_id: str,
        refresh_callback,
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
        return await self._mqtt.async_prepare_mqtt()

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
        self, results: list[dict | BaseException | None]
    ) -> int:
        """Return count of failed subscription tasks."""
        return sum(
            isinstance(result, (TypeError, ValueError))
            or (
                isinstance(result, ThinQAPIException)
                and result.code != ThinQAPIErrorCodes.ALREADY_SUBSCRIBED_PUSH
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
        **kwargs: dict,
    ) -> None:
        """Handle the received MQTT message."""
        decoded = payload.decode()
        try:
            message = json.loads(decoded)
        except ValueError:
            _LOGGER.error("Failed to parse ThinQ MQTT message: payload=%s", decoded)
            return

        asyncio.run_coroutine_threadsafe(
            self._async_handle_message(message), self._hass.loop
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

        refreshed = await self._refresh_callback(self._client, lge_dev)
        if refreshed:
            lge_dev.runtime_state.last_mqtt_refresh = datetime.utcnow()
            lge_dev.async_set_updated()
