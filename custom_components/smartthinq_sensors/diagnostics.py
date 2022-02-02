"""Diagnostics support for LG ThinQ."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LGE_DEVICES

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    diag_data = {"entry": async_redact_data(entry.as_dict(), TO_REDACT)}

    lge_devices = hass.data[DOMAIN].get(LGE_DEVICES, {})
    devs_data = {}
    for dev_type, devices in lge_devices.items():
        dev_data = {}
        for lge_device in devices:
            device = lge_device.device
            dev_id = device.device_info.id
            dev_data[dev_id] = {
                "device_info": device.device_info.as_dict(),
                "model_info": device.model_info.as_dict(),
                "device_status": device.status.data if device.status else {},
            }
        devs_data[dev_type.name] = dev_data

    diag_data["devices"] = devs_data

    return diag_data
