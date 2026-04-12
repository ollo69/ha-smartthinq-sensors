"""Support for ThinQ device switches."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from thinqconnect.devices.const import Property as ThinQProperty
from thinqconnect.integration import ActiveMode

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LGE_DISCOVERY_NEW
from .device_helpers import STATE_LOOKUP, LGEBaseDevice
from .lge_device import LGEDevice
from .official_control import (
    async_call_official_post,
    async_call_official_turn_off,
    async_call_official_turn_on,
)
from .official_mapping import find_official_coordinator
from .runtime_data import get_lge_devices
from .wideq import (
    WM_DEVICE_TYPES,
    AirConditionerFeatures,
    DeviceType,
    MicroWaveFeatures,
    RefrigeratorFeatures,
)

# general sensor attributes
ATTR_POWER = "power"

_LOGGER = logging.getLogger(__name__)

OFFICIAL_POWER_KEYS = {
    DeviceType.WASHER: (ThinQProperty.WASHER_OPERATION_MODE,),
    DeviceType.DRYER: (ThinQProperty.DRYER_OPERATION_MODE,),
    DeviceType.DISHWASHER: (ThinQProperty.DISH_WASHER_OPERATION_MODE,),
}


@dataclass(frozen=True)
class ThinQSwitchEntityDescription(SwitchEntityDescription):
    """A class that describes ThinQ switch entities."""

    available_fn: Callable[[Any], bool] | None = None
    turn_off_fn: Callable[[Any], Awaitable[None]] | None = None
    turn_on_fn: Callable[[Any], Awaitable[None]] | None = None
    value_fn: Callable[[Any], bool] | None = None


WASH_DEV_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=ATTR_POWER,
        name="Power",
        value_fn=lambda x: x.is_power_on and not x.device.stand_by,
        turn_off_fn=lambda x: x.device.power_off(),
        turn_on_fn=lambda x: x.device.wake_up(),
        available_fn=lambda x: x.is_power_on or x.device.stand_by,
    ),
)
REFRIGERATOR_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.POWER_SAVE,
        name="Power save",
        icon="mdi:leaf",
        value_fn=lambda x: x.power_save_enabled,
        available_fn=lambda x: x.is_power_on,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.ECOFRIENDLY,
        name="Eco friendly",
        icon="mdi:gauge-empty",
        turn_off_fn=lambda x: x.device.set_eco_friendly(False),
        turn_on_fn=lambda x: x.device.set_eco_friendly(True),
        available_fn=lambda x: x.is_power_on,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.EXPRESSFRIDGE,
        name="Express fridge",
        icon="mdi:coolant-temperature",
        turn_off_fn=lambda x: x.device.set_express_fridge(False),
        turn_on_fn=lambda x: x.device.set_express_fridge(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.EXPRESSMODE,
        name="Express mode",
        icon="mdi:snowflake",
        turn_off_fn=lambda x: x.device.set_express_mode(False),
        turn_on_fn=lambda x: x.device.set_express_mode(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
    ThinQSwitchEntityDescription(
        key=RefrigeratorFeatures.ICEPLUS,
        name="Ice plus",
        icon="mdi:snowflake",
        turn_off_fn=lambda x: x.device.set_ice_plus(False),
        turn_on_fn=lambda x: x.device.set_ice_plus(True),
        available_fn=lambda x: x.device.set_values_allowed,
    ),
)
AC_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.POWER_SAVE,
        name="Power save",
        icon="mdi:leaf",
        value_fn=lambda x: x.power_save_enabled,
        available_fn=lambda x: x.is_power_on,
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.MODE_AIRCLEAN,
        name="Ionizer",
        icon="mdi:pine-tree",
        turn_off_fn=lambda x: x.device.set_mode_airclean(False),
        turn_on_fn=lambda x: x.device.set_mode_airclean(True),
        available_fn=lambda x: x.device.is_mode_airclean_supported and x.is_power_on,
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.MODE_JET,
        name="Jet mode",
        icon="mdi:turbine",
        turn_off_fn=lambda x: x.device.set_mode_jet(False),
        turn_on_fn=lambda x: x.device.set_mode_jet(True),
        available_fn=lambda x: x.device.is_mode_jet_available,
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.LIGHTING_DISPLAY,
        name="Display light",
        icon="mdi:wall-sconce-round",
        turn_off_fn=lambda x: x.device.set_lighting_display(False),
        turn_on_fn=lambda x: x.device.set_lighting_display(True),
    ),
    ThinQSwitchEntityDescription(
        key=AirConditionerFeatures.MODE_AWHP_SILENT,
        name="Silent mode",
        icon="mdi:ear-hearing-off",
        turn_off_fn=lambda x: x.device.set_mode_awhp_silent(False),
        turn_on_fn=lambda x: x.device.set_mode_awhp_silent(True),
        available_fn=lambda x: x.is_power_on,
    ),
)
MICROWAVE_SWITCH: tuple[ThinQSwitchEntityDescription, ...] = (
    ThinQSwitchEntityDescription(
        key=MicroWaveFeatures.SOUND,
        name="Sound",
        icon="mdi:volume-high",
        entity_category=EntityCategory.CONFIG,
        turn_off_fn=lambda x: x.device.set_sound(False),
        turn_on_fn=lambda x: x.device.set_sound(True),
    ),
    ThinQSwitchEntityDescription(
        key=MicroWaveFeatures.CLOCK_DISPLAY,
        name="Clock Display",
        icon="mdi:clock-digital",
        entity_category=EntityCategory.CONFIG,
        turn_off_fn=lambda x: x.device.set_clock_display(False),
        turn_on_fn=lambda x: x.device.set_clock_display(True),
    ),
)


SWITCH_ENTITIES = {
    DeviceType.AC: AC_SWITCH,
    DeviceType.MICROWAVE: MICROWAVE_SWITCH,
    DeviceType.REFRIGERATOR: REFRIGERATOR_SWITCH,
    **dict.fromkeys(WM_DEVICE_TYPES, WASH_DEV_SWITCH),
}


def _switch_exist(
    lge_device: LGEDevice, switch_desc: ThinQSwitchEntityDescription
) -> bool:
    """Check if a switch exist for device."""
    if (
        lge_device.type == DeviceType.AC
        and switch_desc.key == AirConditionerFeatures.POWER_SAVE
    ):
        official_coordinator = find_official_coordinator(
            lge_device.hass, lge_device.device_id
        )
        if official_coordinator is None:
            return False
        return bool(
            official_coordinator.api.get_active_idx(
                ThinQProperty.POWER_SAVE_ENABLED,
                ActiveMode.WRITABLE,
            )
        )
    if (
        lge_device.type == DeviceType.REFRIGERATOR
        and switch_desc.key == RefrigeratorFeatures.POWER_SAVE
    ):
        official_coordinator = find_official_coordinator(
            lge_device.hass, lge_device.device_id
        )
        if official_coordinator is None:
            return False
        return bool(
            official_coordinator.api.get_active_idx(
                ThinQProperty.POWER_SAVE_ENABLED,
                ActiveMode.WRITABLE,
            )
        )

    if (
        lge_device.type == DeviceType.REFRIGERATOR
        and switch_desc.key == RefrigeratorFeatures.EXPRESSFRIDGE
        and not lge_device.device.supports_express_fridge()
    ):
        return False

    if switch_desc.value_fn is not None:
        return True

    feature = switch_desc.key
    if feature in lge_device.available_features:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LGE switch."""
    lge_cfg_devices = get_lge_devices(hass)

    _LOGGER.debug("Starting LGE ThinQ switch setup")

    @callback
    def _async_discover_device(lge_devices: dict) -> None:
        """Add entities for a discovered ThinQ device."""

        if not lge_devices:
            return

        lge_switch: list[LGEBaseSwitch] = [
            LGESwitch(lge_device, switch_desc)
            for dev_type, switch_descs in SWITCH_ENTITIES.items()
            for switch_desc in switch_descs
            for lge_device in lge_devices.get(dev_type, [])
            if _switch_exist(lge_device, switch_desc)
        ]

        # add AC duct zone switch
        lge_switch.extend(
            [
                LGEDuctSwitch(lge_device, duct_zone)
                for lge_device in lge_devices.get(DeviceType.AC, [])
                for duct_zone in lge_device.device.duct_zones
            ]
        )

        async_add_entities(lge_switch)

    _async_discover_device(lge_cfg_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, LGE_DISCOVERY_NEW, _async_discover_device)
    )


class LGEBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base switch device."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, api: LGEDevice) -> None:
        """Initialize the base switch."""
        super().__init__(api.coordinator)
        self._api = api
        self._attr_device_info = api.device_info
        self._wrap_device = LGEBaseDevice(api)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGESwitch(LGEBaseSwitch):
    """Class to control switches for LGE device."""

    entity_description: ThinQSwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: LGEDevice,
        description: ThinQSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(api)
        self.entity_description = description
        self._attr_unique_id = f"{api.unique_id}-{description.key}-switch"

    def _normalized_hybrid_run_state(self) -> str | None:
        """Return the normalized hybrid run state for laundry devices."""
        logical_prefix = {
            DeviceType.WASHER: "washer",
            DeviceType.DRYER: "dryer",
            DeviceType.DISHWASHER: "dishwasher",
        }.get(self._api.type)
        hybrid_run_state = (
            self._api.get_hybrid_value(f"{logical_prefix}.run_state")
            if logical_prefix
            else None
        )
        if isinstance(hybrid_run_state, str):
            return hybrid_run_state.lower()
        return None

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        ret_val = self._get_switch_state()
        if ret_val is None:
            return False
        if isinstance(ret_val, bool):
            return ret_val
        if ret_val == STATE_ON:
            return True
        state = STATE_LOOKUP.get(cast(Any, ret_val), STATE_OFF)
        return state == STATE_ON

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if (
            self.entity_description.key == ATTR_POWER
            and self._api.type in WM_DEVICE_TYPES
            and self._normalized_hybrid_run_state() in {"power_off", "off", "none"}
        ):
            return False
        is_avail = True
        if self.entity_description.available_fn is not None:
            is_avail = self.entity_description.available_fn(self._wrap_device)
        return self._api.available and is_avail

    async def _async_try_official_power_control(self, turn_on: bool) -> bool:
        """Try controlling a wash-device power switch through the official API."""
        if self.entity_description.key != ATTR_POWER:
            return False

        property_keys = OFFICIAL_POWER_KEYS.get(self._api.type)
        if not property_keys:
            return False

        if turn_on:
            return await async_call_official_turn_on(self._api, *property_keys)
        return await async_call_official_turn_off(self._api, *property_keys)

    async def _async_try_official_switch_control(self, turn_on: bool) -> bool:
        """Try controlling switch entities through the official API when supported."""
        if self.entity_description.key == AirConditionerFeatures.POWER_SAVE:
            return await async_call_official_post(
                self._api,
                turn_on,
                ThinQProperty.POWER_SAVE_ENABLED,
            )
        if self.entity_description.key == RefrigeratorFeatures.POWER_SAVE:
            return await async_call_official_post(
                self._api,
                turn_on,
                ThinQProperty.POWER_SAVE_ENABLED,
            )
        if self.entity_description.key == AirConditionerFeatures.MODE_AIRCLEAN:
            return await async_call_official_post(
                self._api,
                "START" if turn_on else "STOP",
                ThinQProperty.AIR_CLEAN_OPERATION_MODE,
            )
        return False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if self.is_on and await self._async_try_official_switch_control(False):
            return
        if self.entity_description.turn_off_fn is None:
            if self.entity_description.key == AirConditionerFeatures.POWER_SAVE:
                raise HomeAssistantError(
                    "Power Save control is not available through this device path."
                )
            if self.entity_description.key == RefrigeratorFeatures.POWER_SAVE:
                raise HomeAssistantError(
                    "Power Save control is not available through this device path."
                )
            raise NotImplementedError
        if self.is_on:
            if await self._async_try_official_power_control(False):
                return
            await self.entity_description.turn_off_fn(self._wrap_device)
            self._api.async_set_updated()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if not self.is_on and await self._async_try_official_switch_control(True):
            return
        if self.entity_description.turn_on_fn is None:
            if self.entity_description.key == AirConditionerFeatures.POWER_SAVE:
                raise HomeAssistantError(
                    "Power Save control is not available through this device path."
                )
            if self.entity_description.key == RefrigeratorFeatures.POWER_SAVE:
                raise HomeAssistantError(
                    "Power Save control is not available through this device path."
                )
            raise NotImplementedError
        if not self.is_on:
            if await self._async_try_official_power_control(True):
                return
            await self.entity_description.turn_on_fn(self._wrap_device)
            self._api.async_set_updated()

    def _get_switch_state(self) -> bool | str | None:
        """Get current switch state."""
        if self.entity_description.key == ATTR_POWER:
            if self._api.type in WM_DEVICE_TYPES or self._api.type == DeviceType.DISHWASHER:
                return self._wrap_device.is_power_on

            logical_key = {
                DeviceType.WASHER: "washer.is_on",
                DeviceType.DRYER: "dryer.is_on",
                DeviceType.DISHWASHER: "dishwasher.is_on",
            }.get(self._api.type)
            if logical_key:
                hybrid_is_on = self._api.get_hybrid_value(logical_key)
                if hybrid_is_on is not None:
                    return bool(hybrid_is_on)

        if self._api.type == DeviceType.REFRIGERATOR:
            refrigerator_logical_keys: dict[RefrigeratorFeatures, str] = {
                RefrigeratorFeatures.POWER_SAVE: "refrigerator.power_save_enabled",
                RefrigeratorFeatures.ECOFRIENDLY: "refrigerator.eco_friendly",
                RefrigeratorFeatures.EXPRESSFRIDGE: "refrigerator.express_fridge",
                RefrigeratorFeatures.EXPRESSMODE: "refrigerator.express_mode",
            }
            logical_key = refrigerator_logical_keys.get(
                cast(RefrigeratorFeatures, self.entity_description.key)
            )
            if logical_key:
                hybrid_value = self._api.get_hybrid_value(logical_key)
                if hybrid_value is not None:
                    return cast(bool | str | None, hybrid_value)

        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._wrap_device)

        if self._api.state:
            feature = self.entity_description.key
            return cast(bool | str | None, self._api.state.device_features.get(feature))

        return None


class LGEDuctSwitch(LGEBaseSwitch):
    """Class to control switches for LGE AC duct device."""

    _attr_has_entity_name = True

    def __init__(self, api: LGEDevice, duct_zone: str) -> None:
        """Initialize the switch."""
        super().__init__(api)
        self._attr_unique_id = f"{api.unique_id}-duct-zone-switch-{duct_zone}"
        self._attr_name = f"Zone {duct_zone}"
        self._zone = duct_zone

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        return cast(bool, self._wrap_device.device.get_duct_zone(self._zone))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self._wrap_device.device.is_duct_zone_enabled(self._zone)
            and self._wrap_device.is_power_on
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._wrap_device.device.set_duct_zone(self._zone, False)
        self._api.async_set_updated()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self._wrap_device.device.set_duct_zone(self._zone, True)
        self._api.async_set_updated()
