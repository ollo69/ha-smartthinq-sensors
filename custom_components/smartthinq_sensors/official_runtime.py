"""Self-contained official ThinQ Connect runtime for this custom integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
from typing import Any

from aiohttp import ClientError
from thinqconnect import (
    DeviceType as OfficialDeviceType,
    ThinQApi,
    ThinQAPIErrorCodes,
    ThinQAPIException,
    ThinQMQTTClient,
)
from thinqconnect.integration import HABridge, async_get_ha_bridge_list

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .trace import add_trace_event

_LOGGER = logging.getLogger(__name__)

DEVICE_PUSH_MESSAGE = "DEVICE_PUSH"
DEVICE_STATUS_MESSAGE = "DEVICE_STATUS"
HYBRID_COORDINATORS = "hybrid_coordinators"
MQTT_SUBSCRIPTION_INTERVAL = timedelta(days=1)
OFFICIAL_RUNTIME_LAST_ERROR = "official_runtime_last_error"
ALREADY_SUBSCRIBED_PUSH = getattr(
    ThinQAPIErrorCodes, "ALREADY_SUBSCRIBED_PUSH", None
)


@dataclass(slots=True)
class OfficialThinQRuntime:
    """Official ThinQ runtime objects managed by this integration."""

    api: ThinQApi
    coordinators: dict[str, OfficialDeviceCoordinator] = field(default_factory=dict)
    mqtt_client: OfficialThinQMQTT | None = None


class OfficialDeviceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Official ThinQ coordinator for one bridge/device."""

    def __init__(self, hass: HomeAssistant, bridge: HABridge) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_official_{bridge.device.device_id}",
        )
        self.data = bridge.update_status(None)
        self.api = bridge
        self.device_id = bridge.device.device_id
        self.sub_id = bridge.sub_id
        alias = bridge.device.alias
        self.device_name = f"{alias} {self.sub_id}" if self.sub_id else alias
        self.unique_id = (
            f"{self.device_id}_{self.sub_id}" if self.sub_id else self.device_id
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch fresh official data."""
        try:
            return dict(await self.api.fetch_data())
        except ThinQAPIException as err:
            raise UpdateFailed(err) from err

    def handle_update_status(self, status: dict[str, Any]) -> None:
        """Handle status payload received from MQTT."""
        data = self.api.update_status(status)
        if data is not None:
            self.async_set_updated_data(data)

    def handle_notification_message(self, message: str | None) -> None:
        """Handle notification payload received from MQTT."""
        data = self.api.update_notification(message)
        if data is not None:
            self.async_set_updated_data(data)


class OfficialThinQMQTT:
    """Manage ThinQ Connect MQTT for the custom integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        thinq_api: ThinQApi,
        client_id: str,
        coordinators: dict[str, OfficialDeviceCoordinator],
    ) -> None:
        """Initialize MQTT runtime."""
        self._hass = hass
        self._thinq_api = thinq_api
        self._client_id = client_id
        self._coordinators = coordinators
        self._client: ThinQMQTTClient | None = None

    def _mark_all_disconnected(self, reason: str) -> None:
        """Mark all hybrid coordinators as disconnected."""
        add_trace_event(
            self._hass,
            category="mqtt",
            action="disconnected",
            details={"reason": reason},
        )
        hybrid_coordinators = self._hass.data.get(DOMAIN, {}).get(HYBRID_COORDINATORS)
        if not isinstance(hybrid_coordinators, dict):
            return
        for coordinator in hybrid_coordinators.values():
            if hasattr(coordinator, "mark_mqtt_disconnected"):
                coordinator.mark_mqtt_disconnected(reason)

    async def async_connect(self) -> bool:
        """Create MQTT client and prepare certificates."""
        def _mark_interrupted(*_args: Any, **_kwargs: Any) -> None:
            self._mark_all_disconnected("official_mqtt_interrupted")

        def _mark_failure(*_args: Any, **_kwargs: Any) -> None:
            self._mark_all_disconnected("official_mqtt_failure")

        def _mark_closed(*_args: Any, **_kwargs: Any) -> None:
            self._mark_all_disconnected("official_mqtt_closed")

        self._client = await ThinQMQTTClient(
            self._thinq_api,
            self._client_id,
            self.on_message_received,
            on_connection_interrupted=_mark_interrupted,
            on_connection_failure=_mark_failure,
            on_connection_closed=_mark_closed,
        )
        return bool(self._client and await self._client.async_prepare_mqtt())

    async def async_start_subscribes(self) -> None:
        """Start official push/event subscriptions."""
        if self._client is None:
            _LOGGER.error("Cannot start official ThinQ MQTT: no client")
            return

        tasks = [
            self._hass.async_create_task(
                self._thinq_api.async_post_push_subscribe(coordinator.device_id)
            )
            for coordinator in self._coordinators.values()
        ]
        tasks.extend(
            self._hass.async_create_task(
                self._thinq_api.async_post_event_subscribe(coordinator.device_id)
            )
            for coordinator in self._coordinators.values()
        )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failed = self._get_failed_device_count(results)
            if failed:
                _LOGGER.error(
                    "Failed to start official ThinQ subscriptions on %s devices",
                    failed,
                )

        await self._client.async_connect_mqtt()
        add_trace_event(
            self._hass,
            category="mqtt",
            action="subscriptions_started",
            details={"device_count": len(self._coordinators)},
        )

    async def async_refresh_subscribe(self, now: datetime | None = None) -> None:
        """Refresh event subscriptions."""
        _LOGGER.debug("Refreshing official ThinQ subscriptions: now=%s", now)
        tasks = [
            self._hass.async_create_task(
                self._thinq_api.async_post_event_subscribe(coordinator.device_id)
            )
            for coordinator in self._coordinators.values()
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failed = self._get_failed_device_count(results)
            if failed:
                _LOGGER.error(
                    "Failed to refresh official ThinQ subscriptions on %s devices",
                    failed,
                )

    async def async_end_subscribes(self) -> None:
        """End official push/event subscriptions."""
        tasks = [
            self._hass.async_create_task(
                self._thinq_api.async_delete_push_subscribe(coordinator.device_id)
            )
            for coordinator in self._coordinators.values()
        ]
        tasks.extend(
            self._hass.async_create_task(
                self._thinq_api.async_delete_event_subscribe(coordinator.device_id)
            )
            for coordinator in self._coordinators.values()
        )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failed = self._get_failed_device_count(results)
            if failed:
                _LOGGER.error(
                    "Failed to end official ThinQ subscriptions on %s devices",
                    failed,
                )

    async def async_disconnect(self) -> None:
        """Disconnect MQTT and clear registrations."""
        await self.async_end_subscribes()
        if self._client is None:
            return
        try:
            await self._client.async_disconnect()
        except (ThinQAPIException, TypeError, ValueError):
            _LOGGER.exception("Failed to disconnect official ThinQ MQTT")
        self._client = None

    def _get_failed_device_count(
        self, results: list[dict[str, Any] | BaseException | None]
    ) -> int:
        """Count failing subscription results."""
        return sum(
            isinstance(result, (TypeError, ValueError))
            or (
                isinstance(result, ThinQAPIException)
                and result.code != ALREADY_SUBSCRIBED_PUSH
            )
            for result in results
        )

    def on_message_received(
        self,
        topic: str,
        payload: bytes,
        dup: bool,
        qos: Any,
        retain: bool,
        **kwargs: dict[str, Any],
    ) -> None:
        """Handle incoming MQTT payload."""
        del topic, dup, qos, retain, kwargs
        decoded = payload.decode()
        try:
            message = json.loads(decoded)
        except ValueError:
            _LOGGER.error("Failed to parse official ThinQ MQTT payload: %s", decoded)
            return

        asyncio.run_coroutine_threadsafe(
            self.async_handle_device_event(message),
            self._hass.loop,
        ).result()

    async def async_handle_device_event(self, message: dict[str, Any]) -> None:
        """Handle one official MQTT message."""
        unique_id = (
            f"{message['deviceId']}_{list(message['report'].keys())[0]}"
            if message.get("deviceType") == OfficialDeviceType.WASHTOWER
            and message.get("report")
            else message.get("deviceId")
        )
        if unique_id is None:
            return

        coordinator = self._coordinators.get(unique_id)
        if coordinator is None:
            _LOGGER.debug("Ignoring official MQTT for unknown device: %s", unique_id)
            add_trace_event(
                self._hass,
                category="mqtt",
                action="unknown_device",
                device_id=str(unique_id),
                details={"push_type": message.get("pushType")},
            )
            return

        push_type = message.get("pushType")
        add_trace_event(
            self._hass,
            category="mqtt",
            action="message_received",
            device_id=coordinator.device_id,
            details={
                "push_type": push_type,
                "message_keys": sorted(message.keys()),
            },
        )
        if push_type == DEVICE_STATUS_MESSAGE:
            coordinator.handle_update_status(message.get("report", {}))
        elif push_type == DEVICE_PUSH_MESSAGE:
            coordinator.handle_notification_message(message.get("pushCode"))


async def async_setup_official_runtime(
    hass: HomeAssistant,
    on_unload: Callable[[Callable[[], None]], None],
    *,
    access_token: str,
    client_id: str,
    country_code: str,
) -> OfficialThinQRuntime | None:
    """Create a self-contained official ThinQ runtime."""
    thinq_api = ThinQApi(
        session=async_get_clientsession(hass),
        access_token=access_token,
        country_code=country_code,
        client_id=client_id,
    )

    try:
        bridge_list = await async_get_ha_bridge_list(thinq_api)
    except (ClientError, OSError, TimeoutError, ThinQAPIException) as err:
        hass.data.setdefault(DOMAIN, {})[OFFICIAL_RUNTIME_LAST_ERROR] = str(err)
        _LOGGER.warning("Failed to initialize official ThinQ bridge list: %s", err)
        return None

    if not bridge_list:
        _LOGGER.debug("No official ThinQ bridges discovered")
        return None

    runtime = OfficialThinQRuntime(api=thinq_api)
    tasks = [
        hass.async_create_task(_async_setup_official_coordinator(hass, bridge))
        for bridge in bridge_list
    ]
    results = await asyncio.gather(*tasks)
    for coordinator in results:
        runtime.coordinators[coordinator.unique_id] = coordinator

    mqtt_client = OfficialThinQMQTT(hass, thinq_api, client_id, runtime.coordinators)
    runtime.mqtt_client = mqtt_client

    try:
        mqtt_ready = await mqtt_client.async_connect()
    except (AttributeError, ThinQAPIException, TypeError, ValueError) as err:
        hass.data.setdefault(DOMAIN, {})[OFFICIAL_RUNTIME_LAST_ERROR] = str(err)
        _LOGGER.warning("Failed to prepare official ThinQ MQTT: %s", err)
        return runtime

    if mqtt_ready:
        await mqtt_client.async_start_subscribes()
        on_unload(
            async_track_time_interval(
                hass,
                mqtt_client.async_refresh_subscribe,
                MQTT_SUBSCRIPTION_INTERVAL,
                cancel_on_shutdown=True,
            )
        )

        def _schedule_disconnect() -> None:
            hass.async_create_task(mqtt_client.async_disconnect())

        on_unload(_schedule_disconnect)
    else:
        hass.data.setdefault(DOMAIN, {})[OFFICIAL_RUNTIME_LAST_ERROR] = (
            "mqtt_prepare_returned_false"
        )
        _LOGGER.warning("Official ThinQ MQTT preparation did not complete")

    return runtime


async def _async_setup_official_coordinator(
    hass: HomeAssistant,
    bridge: HABridge,
) -> OfficialDeviceCoordinator:
    """Create and initialize one official coordinator."""
    coordinator = OfficialDeviceCoordinator(hass, bridge)
    await coordinator.async_refresh()
    return coordinator
