"""Diagnostics support for LG ThinQ."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant

from . import UNSUPPORTED_DEVICES
from .const import DOMAIN, LGE_DEVICES

TO_REDACT = {CONF_TOKEN}
TO_REDACT_DEV = {"macAddress", "ssid", "userNo"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    diag_data = {"entry": async_redact_data(entry.as_dict(), TO_REDACT)}

    lge_devices = hass.data[DOMAIN].get(LGE_DEVICES, {})
    devs_data = {}
    for dev_type, devices in lge_devices.items():
        lge_devs = {}
        for lge_device in devices:
            device = lge_device.device
            lge_devs[lge_device.unique_id] = {
                "device_info": async_redact_data(
                    device.device_info.as_dict(), TO_REDACT_DEV
                ),
                "model_info": device.model_info.as_dict(),
                "device_status": device.status.data if device.status else {},
            }
        devs_data[dev_type.name] = lge_devs

    if devs_data:
        diag_data[LGE_DEVICES] = devs_data

    unsup_devices = hass.data[DOMAIN].get(UNSUPPORTED_DEVICES, {})
    unsup_data = {}
    for dev_type, devices in unsup_devices.items():
        unsup_devs = [
            async_redact_data(device.as_dict(), TO_REDACT_DEV)
            for device in devices
        ]
        unsup_data[dev_type.name] = unsup_devs

    if unsup_data:
        diag_data[UNSUPPORTED_DEVICES] = unsup_data

    return diag_data
