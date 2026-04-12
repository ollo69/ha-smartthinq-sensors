"""Support for ThinQ device selects."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LGEDevice
from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .wideq import WM_DEVICE_TYPES, DeviceType, MicroWaveFeatures
from .wideq.core_exceptions import InvalidDeviceStatus

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThinQSelectRequiredKeysMixin:
    """Mixin for required keys."""

    options_fn: Callable[[Any], list[str]]
    select_option_fn: Callable[[Any, str], Awaitable[None]]


@dataclass(frozen=True)
class ThinQSelectEntityDescription(
    SelectEntityDescription, ThinQSelectRequiredKeysMixin
):
    """A class that describes ThinQ select entities."""

    available_fn: Callable[[Any], bool] | None = None
    value_fn: Callable[[Any], str] | None = None


WASH_DEV_SELECT: tuple[ThinQSelectEntityDescription, ...] = (
    ThinQSelectEntityDescription(
        key="course_selection",
        name="Course selection",
        icon="mdi:tune-vertical-variant",
        options_fn=lambda x: x.device.course_list,
        select_option_fn=lambda x, option: x.device.select_start_course(option),
        available_fn=lambda x: bool(x.device.course_list) and x.available,
        value_fn=lambda x: x.device.selected_course,
    ),
)
MICROWAVE_SELECT: tuple[ThinQSelectEntityDescription, ...] = (
    ThinQSelectEntityDescription(
        key=MicroWaveFeatures.DISPLAY_SCROLL_SPEED,
        name="Display scroll speed",
        icon="mdi:format-pilcrow-arrow-right",
        entity_category=EntityCategory.CONFIG,
        options_fn=lambda x: x.device.display_scroll_speeds,
        select_option_fn=lambda x, option: x.device.set_display_scroll_speed(option),
    ),
    ThinQSelectEntityDescription(
        key=MicroWaveFeatures.WEIGHT_UNIT,
        name="Weight unit",
        icon="mdi:weight",
        entity_category=EntityCategory.CONFIG,
        options_fn=lambda x: x.device.defrost_weight_units,
        select_option_fn=lambda x, option: x.device.set_defrost_weight_unit(option),
    ),
)

SELECT_ENTITIES = {
    DeviceType.MICROWAVE: MICROWAVE_SELECT,
    **dict.fromkeys(WM_DEVICE_TYPES, WASH_DEV_SELECT),
}


def _select_exist(
    lge_device: LGEDevice, select_desc: ThinQSelectEntityDescription
) -> bool:
    """Check if a select exist for device."""
    if select_desc.value_fn is not None:
        return True

    feature = select_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE selects."""
    entry_config = hass.data[DOMAIN]
    lge_cfg_devices = entry_config.get(LGE_DEVICES)

    _LOGGER.debug("Starting LGE ThinQ select setup")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_select = [
            LGESelect(lge_device, select_desc)
            for dev_type, select_descs in SELECT_ENTITIES.items()
            for select_desc in select_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _select_exist(lge_device, select_desc)
        ]

        async_add_entities(lge_select)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGESelect(CoordinatorEntity, SelectEntity):
    """Class to control selects for LGE device."""

    entity_description: ThinQSelectEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQSelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(api.coordinator)
        self._api = api
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-select"
        self._attr_device_info = api.device_info
        self._attr_options = self.entity_description.options_fn(self._api)

    def _hybrid_logical_prefix(self) -> str | None:
        """Return the hybrid logical attribute prefix for the current device."""
        return {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        try:
            await self.entity_description.select_option_fn(self._api, option)
        except InvalidDeviceStatus as exc:
            raise ServiceValidationError(
                "Course selection is not available in the washer's current state."
            ) from exc
        self._api.async_set_updated()

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        if self.entity_description.key == "course_selection":
            logical_prefix = self._hybrid_logical_prefix()
            if logical_prefix:
                hybrid_course = self._api.get_hybrid_value(
                    f"{logical_prefix}.current_course"
                )
                if hybrid_course not in (None, ""):
                    return str(hybrid_course)

        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._api)

        if self._api.state:
            feature = self.entity_description.key
            return cast(str | None, self._api.state.device_features.get(feature))

        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_avail = True
        if self.entity_description.key == "course_selection":
            logical_prefix = self._hybrid_logical_prefix()
            if logical_prefix:
                hybrid_run_state = self._api.get_hybrid_value(
                    f"{logical_prefix}.run_state"
                )
                community_power_state = self._api.get_hybrid_value("state.state")
                feature_remote_start = self._api.get_hybrid_value("feature.remote_start")
                state_remote_start = self._api.get_hybrid_value("state.remoteStart")

                run_state_powered_off = isinstance(
                    hybrid_run_state, str
                ) and hybrid_run_state.lower() in {"power_off", "off", "none"}
                community_powered_off = isinstance(
                    community_power_state, str
                ) and community_power_state.upper() in {"POWEROFF", "POWER_OFF", "OFF"}
                remote_start_ready = (
                    feature_remote_start in {True, "on", "ON"}
                    or (
                        isinstance(state_remote_start, str)
                        and state_remote_start.upper().endswith("_ON")
                    )
                )

                if run_state_powered_off and community_powered_off:
                    return False
                is_avail = bool(self.entity_description.options_fn(self._api)) and (
                    self._api.device.select_course_enabled or remote_start_ready
                )
        elif self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._api)
        return self._api.available and is_avail
