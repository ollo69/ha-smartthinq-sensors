"""Support for ThinQ device buttons."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

from thinqconnect.devices.const import Property as ThinQProperty

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LGE_DISCOVERY_NEW
from .device_helpers import LGEBaseDevice
from .lge_device import LGEDevice
from .official_control import async_call_official_post
from .runtime_data import get_lge_devices
from .trace import add_trace_event
from .wideq import WM_DEVICE_TYPES, DeviceType, WashDeviceFeatures
from .wideq.core_exceptions import InvalidDeviceStatus

# general button attributes
ATTR_REMOTE_START = "remote_start"
ATTR_RESUME = "device_resume"
ATTR_PAUSE = "device_pause"

_LOGGER = logging.getLogger(__name__)

OFFICIAL_BUTTON_COMMANDS = {
    DeviceType.WASHER: {
        ATTR_REMOTE_START: ((ThinQProperty.WASHER_OPERATION_MODE,), "START"),
        ATTR_RESUME: ((ThinQProperty.WASHER_OPERATION_MODE,), "START"),
        ATTR_PAUSE: ((ThinQProperty.WASHER_OPERATION_MODE,), "STOP"),
    },
    DeviceType.DRYER: {
        ATTR_REMOTE_START: ((ThinQProperty.DRYER_OPERATION_MODE,), "START"),
        ATTR_RESUME: ((ThinQProperty.DRYER_OPERATION_MODE,), "START"),
        ATTR_PAUSE: ((ThinQProperty.DRYER_OPERATION_MODE,), "STOP"),
    },
    DeviceType.DISHWASHER: {
        ATTR_REMOTE_START: ((ThinQProperty.DISH_WASHER_OPERATION_MODE,), "START"),
        ATTR_RESUME: ((ThinQProperty.DISH_WASHER_OPERATION_MODE,), "START"),
        ATTR_PAUSE: ((ThinQProperty.DISH_WASHER_OPERATION_MODE,), "STOP"),
    },
}


@dataclass(frozen=True)
class ThinQButtonDescriptionMixin:
    """Mixin to describe a Button entity."""

    press_action_fn: Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
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
        available_fn=lambda x: x.device.start_enabled,
        related_feature=WashDeviceFeatures.REMOTESTART,
    ),
    ThinQButtonEntityDescription(
        key=ATTR_RESUME,
        name="Resume",
        icon="mdi:play-circle-outline",
        device_class=ButtonDeviceClass.UPDATE,
        press_action_fn=lambda x: x.device.resume(),
        available_fn=lambda x: x.device.resume_enabled,
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
    **dict.fromkeys(WM_DEVICE_TYPES, WASH_DEV_BUTTON),
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
    lge_cfg_devices = get_lge_devices(hass)

    _LOGGER.debug("Starting LGE ThinQ button setup")

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
    """Class to control buttons for LGE device."""

    entity_description: ThinQButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(api.coordinator)
        self._api = api
        self._wrap_device = LGEBaseDevice(api)
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-button"
        self._attr_device_info = api.device_info

    def _hybrid_logical_prefix(self) -> str | None:
        """Return the hybrid logical attribute prefix for the current device."""
        return {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)

    def _normalized_hybrid_run_state(self) -> str | None:
        """Return the normalized hybrid run state for laundry devices."""
        logical_prefix = self._hybrid_logical_prefix()
        hybrid_run_state = (
            self._api.get_hybrid_value(f"{logical_prefix}.run_state")
            if logical_prefix
            else None
        )
        if isinstance(hybrid_run_state, str):
            return hybrid_run_state.lower()
        return None

    def _official_remote_control_ready(self) -> bool:
        """Return whether official hybrid state says remote control is enabled."""
        logical_prefix = self._hybrid_logical_prefix()
        if not logical_prefix:
            return False
        return (
            self._api.get_hybrid_value(f"{logical_prefix}.remote_control_enabled")
            is True
        )

    async def _async_wait_for_dryer_ready_after_wake(self) -> bool:
        """Wait for a dryer wake-up to surface in hybrid state before starting."""
        for _attempt in range(20):
            run_state = self._normalized_hybrid_run_state()
            if run_state in {"initial", "pause", "running"}:
                return True
            await asyncio.sleep(0.25)

        await self._api.coordinator.async_request_refresh()
        run_state = self._normalized_hybrid_run_state()
        return run_state in {"initial", "pause", "running"}

    async def _async_wait_for_post_start_transition(self) -> bool:
        """Wait for laundry start/resume to move beyond the idle-ready state."""
        if self.entity_description.key == ATTR_REMOTE_START:
            blocked_states = {"initial", "sleep", "standby", "power_off", "off", "none"}
        elif self.entity_description.key == ATTR_RESUME:
            blocked_states = {"pause"}
        else:
            return True

        for _attempt in range(24):
            run_state = self._normalized_hybrid_run_state()
            if run_state is not None and run_state not in blocked_states:
                add_trace_event(
                    self.hass,
                    category="control",
                    action="official_transition_confirmed",
                    device_id=self._api.device_id,
                    details={
                        "button": self.entity_description.key,
                        "run_state": run_state,
                    },
                )
                return True
            await asyncio.sleep(0.25)

        await self._api.coordinator.async_request_refresh()
        run_state = self._normalized_hybrid_run_state()
        if run_state is not None and run_state not in blocked_states:
            add_trace_event(
                self.hass,
                category="control",
                action="official_transition_confirmed",
                device_id=self._api.device_id,
                details={
                    "button": self.entity_description.key,
                    "run_state": run_state,
                    "after_refresh": True,
                },
            )
            return True

        add_trace_event(
            self.hass,
            category="control",
            action="official_transition_missing",
            device_id=self._api.device_id,
            details={
                "button": self.entity_description.key,
                "run_state": run_state,
            },
        )
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self._api.type in WM_DEVICE_TYPES and self.entity_description.key in {
            ATTR_REMOTE_START,
            ATTR_RESUME,
            ATTR_PAUSE,
        }:
            normalized_run_state = self._normalized_hybrid_run_state()
            if normalized_run_state in {"power_off", "off", "none"}:
                is_avail = False
            elif normalized_run_state is not None:
                if self.entity_description.key == ATTR_REMOTE_START:
                    backend_ready = (
                        self.entity_description.available_fn(self._wrap_device)
                        if self.entity_description.available_fn is not None
                        else False
                    )
                    is_avail = backend_ready or (
                        normalized_run_state in {"initial", "sleep"}
                        and self._official_remote_control_ready()
                    )
                elif self.entity_description.key == ATTR_RESUME:
                    is_avail = (
                        normalized_run_state == "pause"
                        and (
                            (
                                self.entity_description.available_fn(self._wrap_device)
                                if self.entity_description.available_fn is not None
                                else False
                            )
                            or self._official_remote_control_ready()
                        )
                    )
                else:
                    is_avail = (
                        normalized_run_state
                        not in {
                            "pause",
                            "initial",
                            "sleep",
                        }
                        and (
                            self.entity_description.available_fn(self._wrap_device)
                            if self.entity_description.available_fn is not None
                            else False
                        )
                    )
            elif self.entity_description.available_fn is not None:
                is_avail = self.entity_description.available_fn(self._wrap_device)
        elif self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._wrap_device)
        return self._api.available and is_avail

    async def _async_try_official_button_control(self) -> bool:
        """Try controlling a laundry button through the official API."""
        command = OFFICIAL_BUTTON_COMMANDS.get(self._api.type, {}).get(
            self.entity_description.key
        )
        if not command:
            return False

        property_keys, value = command
        if (
            self._api.type == DeviceType.DRYER
            and self.entity_description.key == ATTR_REMOTE_START
            and self._wrap_device.device.stand_by
        ):
            if not await async_call_official_post(self._api, "WAKE_UP", *property_keys):
                return False
            self._api.async_set_updated()
            if not await self._async_wait_for_dryer_ready_after_wake():
                return False
            # When the dryer is sleeping, keep the first press as a wake-up only
            # action. This leaves room for course selection changes after wake
            # instead of immediately starting the cycle on the same button press.
            add_trace_event(
                self.hass,
                category="control",
                action="official_wake_only",
                device_id=self._api.device_id,
                details={"button": self.entity_description.key},
            )
            return True

        if not await async_call_official_post(self._api, value, *property_keys):
            return False

        if self._api.type in {DeviceType.DRYER, DeviceType.WASHER} and self.entity_description.key in {
            ATTR_REMOTE_START,
            ATTR_RESUME,
        }:
            # Some laundry devices accept START but remain in an idle-ready state.
            # If no meaningful transition happens, fall back to the community
            # command path rather than treating the official post as sufficient.
            return await self._async_wait_for_post_start_transition()

        return True

    def _get_fallback_selected_course(self) -> Any:
        """Return the best selected course to use for community fallback."""
        selected_course = getattr(self._api.device, "selected_course", None)
        if selected_course not in {None, "", "Current course"}:
            return selected_course

        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        if logical_prefix:
            hybrid_course = self._api.get_hybrid_value(f"{logical_prefix}.current_course")
            if hybrid_course not in {None, "", "-", "Current course"}:
                return hybrid_course

        current_course = getattr(self._api.state, "current_course", None)
        if current_course not in {None, "", "-", "Current course"}:
            return current_course

        return None

    async def async_press(self) -> None:
        """Triggers service."""
        try:
            if await self._async_try_official_button_control():
                return

            if self._api.type in WM_DEVICE_TYPES and self.entity_description.key in {
                ATTR_REMOTE_START,
                ATTR_RESUME,
            }:
                await self._api.coordinator.async_request_refresh()

                if self.entity_description.key == ATTR_REMOTE_START:
                    selected_course = self._get_fallback_selected_course()
                    add_trace_event(
                        self.hass,
                        category="control",
                        action="community_fallback",
                        device_id=self._api.device_id,
                        details={
                            "button": self.entity_description.key,
                            "selected_course": selected_course,
                        },
                    )
                    await self._api.device.remote_start(selected_course)
                else:
                    add_trace_event(
                        self.hass,
                        category="control",
                        action="community_fallback",
                        device_id=self._api.device_id,
                        details={"button": self.entity_description.key},
                    )
                    await self._api.device.resume()
            else:
                await self.entity_description.press_action_fn(self._wrap_device)
        except InvalidDeviceStatus as exc:
            raise ServiceValidationError(
                "This action is not available for the device's current state."
            ) from exc
        except TimeoutError as exc:
            if self.entity_description.key in {ATTR_REMOTE_START, ATTR_RESUME}:
                self._api.coordinator.async_set_updated_data(self._api.state)
                raise HomeAssistantError(
                    "The device may have accepted the command, but LG did not respond in time. Please wait a few seconds for the state to update."
                ) from exc
            raise HomeAssistantError(
                "The LG device did not respond in time. Please try again."
            ) from exc
        self._api.async_set_updated()
