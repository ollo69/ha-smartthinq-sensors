"""Entity update patterns for hybrid API source switching."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.climate import ClimateEntity, HVACMode
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capability_registry import CapabilityRegistry
from .coordinator_hybrid import HybridDataCoordinator
from .data_source_router import DataSourceRouter

_LOGGER = logging.getLogger(__name__)


class HybridSourceMixin:
    """Mixin for entities that support both official and community sources."""

    _device: Any
    _router: DataSourceRouter
    _registry: CapabilityRegistry

    def _get_attribute_value(self, attribute_id: str, default: Any = None) -> Any:
        """Get attribute value from the best available source."""
        coordinator = getattr(self, "coordinator", None)
        if not coordinator or not hasattr(self, "_router"):
            return default

        value, source = self._router.get_attribute_value(
            device_id=self._device.device_id,
            attribute_id=attribute_id,
            fallback_strategy="polling",
        )
        if source in {"official", "polling", "official_stale", "polling_stale"}:
            return value if value is not None else default
        return default

    def _log_data_source(self, attribute_id: str, value: Any) -> None:
        """Log which data source provided a value."""
        if not hasattr(self, "_router"):
            return
        _, source = self._router.get_attribute_value(
            device_id=self._device.device_id,
            attribute_id=attribute_id,
            fallback_strategy="polling",
        )
        _LOGGER.debug(
            "%s: %s=%s from %s",
            getattr(self, "entity_id", None),
            attribute_id,
            value,
            source,
        )


class HybridClimateEntity(HybridSourceMixin, ClimateEntity, CoordinatorEntity):
    """Example climate entity with hybrid source support."""

    def __init__(
        self,
        coordinator: HybridDataCoordinator,
        device: Any,
        capability_registry: CapabilityRegistry,
        data_source_router: DataSourceRouter,
    ) -> None:
        """Initialize climate entity."""
        super().__init__(coordinator)
        self._device = device
        self._registry = capability_registry
        self._router = data_source_router

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{self._device.name} Climate"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._device.unique_id}_climate"

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature from the best source."""
        return cast(float | None, self._get_attribute_value("ac.current_temperature"))

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return cast(float | None, self._get_attribute_value("ac.target_temperature"))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is not None:
            self._log_data_source("ac.target_temperature", temperature)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return HVAC mode from the best source."""
        return cast(HVACMode | None, self._get_attribute_value("ac.hvac_mode"))

    @property
    def fan_mode(self) -> str | None:
        """Return fan mode from the best source."""
        return cast(str | None, self._get_attribute_value("ac.fan_mode"))

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        profile = self._registry.get_profile(self._device.device_id)
        if not profile:
            return False
        capability = profile.get_attribute("ac.current_temperature")
        if not capability:
            return False
        return not capability.is_stale(prefer_official=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates."""
        super()._handle_coordinator_update()


class HybridSensorEntity(HybridSourceMixin, SensorEntity, CoordinatorEntity):
    """Example sensor entity with hybrid source support."""

    def __init__(
        self,
        coordinator: HybridDataCoordinator,
        device: Any,
        attribute_id: str,
        capability_registry: CapabilityRegistry,
        data_source_router: DataSourceRouter,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(coordinator)
        self._device = device
        self._attribute_id = attribute_id
        self._registry = capability_registry
        self._router = data_source_router

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{self._device.name} {self._attribute_id}"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._device.unique_id}_{self._attribute_id}"

    @property
    def native_value(self) -> Any:
        """Return sensor value from the best source."""
        value = self._get_attribute_value(self._attribute_id)
        if value is not None:
            self._log_data_source(self._attribute_id, value)
        return value

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        profile = self._registry.get_profile(self._device.device_id)
        if not profile:
            return False
        capability = profile.get_attribute(self._attribute_id)
        return bool(capability and not capability.is_stale())


class EntityUpdateCoordinator:
    """Coordinator that handles entity updates from mixed sources."""

    def __init__(
        self,
        coordinator: HybridDataCoordinator,
        registry: CapabilityRegistry,
        router: DataSourceRouter,
    ) -> None:
        """Initialize."""
        self._coordinator = coordinator
        self._registry = registry
        self._router = router
        self._entities: dict[str, HybridSourceMixin] = {}

    def register_entity(self, entity: HybridSourceMixin) -> None:
        """Register an entity for updates."""
        if unique_id := getattr(entity, "unique_id", None):
            self._entities[str(unique_id)] = entity

    async def async_update_from_mqtt(
        self,
        device_id: str,
        attributes: dict[str, Any],
    ) -> None:
        """Handle an MQTT update and refresh affected entities."""
        await self._coordinator.async_update_from_mqtt(attributes, device_id)
        for entity in self._entities.values():
            entity_device = getattr(entity, "_device", None)
            if entity_device is not None and entity_device.device_id == device_id:
                update_state = getattr(entity, "async_update_ha_state", None)
                if update_state is not None:
                    await update_state(force_refresh=False)

    async def async_update_from_polling(self, device_id: str) -> None:
        """Handle polling update notifications."""
        _LOGGER.debug("Polling update received for device %s", device_id)

    def get_entity_diagnostics(self, unique_id: str) -> dict[str, Any]:
        """Get diagnostic info for an entity."""
        entity = self._entities.get(unique_id)
        if not entity:
            return {}

        attribute_id = getattr(entity, "_attribute_id", None)
        entity_device = getattr(entity, "_device", None)
        if attribute_id is None or entity_device is None:
            return {"unique_id": unique_id, "type": "unknown"}

        return {
            "unique_id": unique_id,
            "attribute_id": attribute_id,
            "current_value": getattr(entity, "native_value", None),
            "source_info": self._router.get_attribute_source_info(
                entity_device.device_id,
                attribute_id,
            ),
        }
