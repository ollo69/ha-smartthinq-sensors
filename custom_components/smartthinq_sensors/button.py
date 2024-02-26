"""Support for ThinQ device buttons."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .device_helpers import LGEBaseDevice
from .wideq import WM_DEVICE_TYPES, WashDeviceFeatures

# general button attributes
ATTR_REMOTE_START = "remote_start"
ATTR_PAUSE = "device_pause"

_LOGGER = logging.getLogger(__name__)


@dataclass
class ThinQButtonDescriptionMixin:
    """Mixin to describe a Button entity."""

    press_action_fn: Callable[[Any], Awaitable[None]]


@dataclass
class ThinQButtonEntityDescription(
    ButtonEntityDescription, ThinQButtonDescriptionMixin
):
    """A class that describes ThinQ button entities."""

    available_fn: Callable[[Any], bool] | None = None
    related_feature: str | None = None


WASH_DEV_BUTTON: tuple[ThinQButtonEntityDescription, ...] = (
    ThinQButtonEntityDescription(
        key=ATTR_REMOTE_START,
        name="Remote Start",
        icon="mdi:play-circle-outline",
        device_class=ButtonDeviceClass.UPDATE,
        press_action_fn=lambda x: x.device.remote_start(),
        available_fn=lambda x: x.device.remote_start_enabled,
        related_feature=WashDeviceFeatures.REMOTESTART,
    ),
    ThinQButtonEntityDescription(
        key=ATTR_PAUSE,
        name="Pause",
        icon="mdi:pause-circle-outline",
        device_class=ButtonDeviceClass.UPDATE,
        press_action_fn=lambda x: x.device.pause(),
        available_fn=lambda x: x.device.pause_enabled,
        related_feature=WashDeviceFeatures.REMOTESTART,
    ),
)

BUTTON_ENTITIES = {
    **{dev_type: WASH_DEV_BUTTON for dev_type in WM_DEVICE_TYPES},
}


def _button_exist(
    lge_device: LGEDevice, button_desc: ThinQButtonEntityDescription
) -> bool:
    """Check if a button exist for device."""
    feature = button_desc.related_feature
    if feature is None or feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE buttons."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ button setup...")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_button = [
            LGEButton(lge_device, button_desc)
            for dev_type, button_descs in BUTTON_ENTITIES.items()
            for button_desc in button_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _button_exist(lge_device, button_desc)
        ]

        async_add_entities(lge_button)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGEButton(CoordinatorEntity, ButtonEntity):
    """Class to control buttons for LGE device"""

    entity_description: ThinQButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQButtonEntityDescription,
    ):
        """Initialize the button."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = LGEBaseDevice(api)
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-button"
        self._attr_device_info = api.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._wrap_device)
        return self._api.available and is_avail

    async def async_press(self) -> None:
        """Triggers service."""
        await self.entity_description.press_action_fn(self._wrap_device)
        self._api.async_set_updated()
