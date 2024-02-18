"""Diagnostics support for LG ThinQ."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import UNSUPPORTED_DEVICES
from .const import DOMAIN, LGE_DEVICES
from .wideq.device import Device as ThinQDevice

TO_REDACT = {CONF_TOKEN}
TO_REDACT_DEV = {"macAddress", "ssid", "userNo"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    return _async_get_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> dict:
    """Return diagnostics for a device entry."""
    return _async_get_diagnostics(hass, entry, device)


@callback
def _async_get_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: dr.DeviceEntry | None = None,
) -> dict:
    """Return diagnostics for a config or a device entry."""
    diag_data = {"entry": async_redact_data(entry.as_dict(), TO_REDACT)}

    lg_device_id = None
    if device:
        lg_device_id = next(iter(device.identifiers))[1]

    devs_data = _async_devices_as_dict(hass, lg_device_id)
    diag_data[LGE_DEVICES] = devs_data

    if device:
        return diag_data

    # Get info for unsupported device if diagnostic is for the config entry
    unsup_devices = hass.data[DOMAIN].get(UNSUPPORTED_DEVICES, {})
    unsup_data = {}
    for dev_type, devices in unsup_devices.items():
        unsup_devs = [
            async_redact_data(device.as_dict(), TO_REDACT_DEV) for device in devices
        ]
        unsup_data[dev_type.name] = unsup_devs

    if unsup_data:
        diag_data[UNSUPPORTED_DEVICES] = unsup_data

    return diag_data


@callback
def _async_devices_as_dict(
    hass: HomeAssistant, lg_device_id: str | None = None
) -> dict:
    """Represent a LGE devices as a dictionary."""

    lge_devices = hass.data[DOMAIN].get(LGE_DEVICES, {})
    devs_data = {}
    for dev_type, devices in lge_devices.items():
        lge_devs = {}
        for lge_device in devices:
            device: ThinQDevice = lge_device.device
            if lg_device_id and device.device_info.device_id != lg_device_id:
                continue

            lge_devs[lge_device.unique_id] = {
                "device_info": async_redact_data(
                    device.device_info.as_dict(), TO_REDACT_DEV
                ),
                "model_info": device.model_info.as_dict(),
                "device_status": device.status.as_dict if device.status else None,
                "home_assistant": _async_device_ha_info(
                    hass, device.device_info.device_id
                ),
            }
            if lg_device_id:
                return {dev_type.name: lge_devs}

        if lge_devs:
            devs_data[dev_type.name] = lge_devs

    return devs_data


@callback
def _async_device_ha_info(hass: HomeAssistant, lg_device_id: str) -> dict | None:
    """Gather information how this ThinQ device is represented in Home Assistant."""

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    hass_device = device_registry.async_get_device(identifiers={(DOMAIN, lg_device_id)})
    if not hass_device:
        return None

    data = {
        "name": hass_device.name,
        "name_by_user": hass_device.name_by_user,
        "model": hass_device.model,
        "manufacturer": hass_device.manufacturer,
        "sw_version": hass_device.sw_version,
        "disabled": hass_device.disabled,
        "disabled_by": hass_device.disabled_by,
        "entities": {},
    }

    hass_entities = er.async_entries_for_device(
        entity_registry,
        device_id=hass_device.id,
        include_disabled_entities=True,
    )

    for entity_entry in hass_entities:
        if entity_entry.platform != DOMAIN:
            continue
        state = hass.states.get(entity_entry.entity_id)
        state_dict = None
        if state:
            state_dict = dict(state.as_dict())
            # The entity_id is already provided at root level.
            state_dict.pop("entity_id", None)
            # The context doesn't provide useful information in this case.
            state_dict.pop("context", None)

        data["entities"][entity_entry.entity_id] = {
            "name": entity_entry.name,
            "original_name": entity_entry.original_name,
            "disabled": entity_entry.disabled,
            "disabled_by": entity_entry.disabled_by,
            "entity_category": entity_entry.entity_category,
            "device_class": entity_entry.device_class,
            "original_device_class": entity_entry.original_device_class,
            "icon": entity_entry.icon,
            "original_icon": entity_entry.original_icon,
            "unit_of_measurement": entity_entry.unit_of_measurement,
            "state": state_dict,
        }

    return data
