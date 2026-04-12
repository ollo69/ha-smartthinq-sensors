"""Community ThinQ device discovery and setup helpers."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, LGE_DEVICES, LGE_DISCOVERY_NEW
from .lge_device import LGEDevice
from .runtime_data import (
    DISCOVERED_DEVICES,
    UNSUPPORTED_DEVICES,
    get_discovered_devices,
    get_domain_data,
    get_lge_devices,
    get_snapshot_manager,
    get_unsupported_devices,
)
from .snapshot_manager import CommunitySnapshotManager
from .wideq import (
    DeviceInfo as ThinQDeviceInfo,
    DeviceType,
    TemperatureUnit,
    get_lge_device,
)
from .wideq.core_async import ClientAsync

_LOGGER = logging.getLogger(__name__)
DISCOVERY_SCAN_INTERVAL = timedelta(minutes=30)


async def lge_devices_setup(
    hass: HomeAssistant,
    client: ClientAsync,
    discovered_devices: dict[str, list[str]] | None = None,
    *,
    snapshot_manager: CommunitySnapshotManager | None = None,
) -> tuple[
    dict[DeviceType, list[LGEDevice]],
    dict[DeviceType, list[ThinQDeviceInfo]],
    dict[str, list[str]],
]:
    """Query connected devices from LG ThinQ."""
    _LOGGER.debug("Searching LGE ThinQ devices")

    wrapped_devices: dict[DeviceType, list[LGEDevice]] = {}
    unsupported_devices: dict[DeviceType, list[ThinQDeviceInfo]] = {}
    if discovered_devices is None:
        discovered_devices = {}

    if not client.has_devices:
        await client.refresh_devices()

    if (client_devices := client.devices) is None:
        return wrapped_devices, unsupported_devices, discovered_devices

    new_devices: dict[str, list[str]] = {}
    device_count = 0
    temp_unit = TemperatureUnit.CELSIUS
    if hass.config.units.temperature_unit != UnitOfTemperature.CELSIUS:
        temp_unit = TemperatureUnit.FAHRENHEIT

    async def init_device(
        lge_dev: Any, device_info: ThinQDeviceInfo, root_dev_id: str | None
    ) -> bool:
        """Initialize a new device."""
        root_dev = None if root_dev_id == lge_dev.unique_id else root_dev_id
        dev = LGEDevice(lge_dev, hass, root_dev)
        if not await dev.init_device():
            _LOGGER.error(
                "Error initializing LGE Device. Name: %s - Type: %s - InfoUrl: %s",
                device_info.name,
                device_info.type.name,
                device_info.model_info_url,
            )
            return False

        new_devices[device_info.device_id].append(dev.device_id)
        wrapped_devices.setdefault(device_info.type, []).append(dev)
        _LOGGER.info(
            "LGE Device added. Name: %s - Type: %s - Model: %s - ID: %s",
            dev.name,
            device_info.type.name,
            device_info.model_name,
            dev.device_id,
        )
        return True

    for device_info in client_devices:
        device_id = device_info.device_id
        if device_id in discovered_devices:
            new_devices[device_id] = discovered_devices[device_id]
            continue

        new_devices[device_id] = []
        device_count += 1

        lge_devs = get_lge_device(
            client,
            device_info,
            temp_unit,
            snapshot_provider=snapshot_manager,
        )
        if not lge_devs:
            _LOGGER.info(
                "Found unsupported LGE Device. Name: %s - Type: %s - NetworkType: %s",
                device_info.name,
                device_info.type.name,
                device_info.network_type.name,
            )
            unsupported_devices.setdefault(device_info.type, []).append(device_info)
            continue

        root_dev = None
        for idx, lge_dev in enumerate(lge_devs):
            if idx == 0:
                root_dev = lge_dev.unique_id
            if not await init_device(lge_dev, device_info, root_dev):
                break
            if sub_dev := lge_dev.subkey_device:
                await init_device(sub_dev, device_info, root_dev)

    if device_count > 0:
        _LOGGER.info("Founds %s LGE device(s)", device_count)

    return wrapped_devices, unsupported_devices, new_devices


@callback
def cleanup_orphan_lge_devices(
    hass: HomeAssistant, entry_id: str, valid_dev_ids: list[str]
) -> None:
    """Delete devices that are not registered in LG client app."""
    device_registry = dr.async_get(hass)
    all_lg_dev_entries = dr.async_entries_for_config_entry(device_registry, entry_id)

    valid_reg_dev_ids = []
    for device_id in valid_dev_ids:
        dev = device_registry.async_get_device({(DOMAIN, device_id)})
        if dev is not None:
            valid_reg_dev_ids.append(dev.id)

    for dev_entry in all_lg_dev_entries:
        dev_id = dev_entry.id
        if dev_id in valid_reg_dev_ids:
            continue
        device_registry.async_remove_device(dev_id)


@callback
def _apply_discovery_results(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    lge_devs: dict[DeviceType, list[LGEDevice]],
    unsupported_devs: dict[DeviceType, list[ThinQDeviceInfo]],
    old_devs: dict[str, list[str]],
    new_devs: dict[str, list[str]],
    notify_message: Any,
) -> None:
    """Apply device discovery results to runtime data."""
    runtime_data = get_domain_data(hass)
    runtime_data[DISCOVERED_DEVICES] = new_devs

    if lge_devs:
        notify_message(
            hass, "new_devices", "SmartThinQ Sensors", "Discovered new devices."
        )
        async_dispatcher_send(hass, LGE_DISCOVERY_NEW, lge_devs)

    if lge_devs or unsupported_devs or len(old_devs) != len(new_devs):
        new_ids = [v for ids in new_devs.values() for v in ids]
        cleanup_orphan_lge_devices(hass, entry.entry_id, new_ids)

        prev_lge_devs: dict[DeviceType, list[LGEDevice]] = get_lge_devices(hass)
        new_lge_devs: dict[DeviceType, list[LGEDevice]] = {}
        for dev_type, dev_list in prev_lge_devs.items():
            valid_lge_devs = [dev for dev in dev_list if dev.device_id in new_ids]
            if valid_lge_devs:
                new_lge_devs[dev_type] = valid_lge_devs
        for dev_type, dev_list in lge_devs.items():
            if dev_type in new_lge_devs:
                new_lge_devs[dev_type].extend(dev_list)
            else:
                new_lge_devs[dev_type] = dev_list
        runtime_data[LGE_DEVICES] = new_lge_devs

        prev_uns_devs: dict[DeviceType, list[ThinQDeviceInfo]] = (
            get_unsupported_devices(hass)
        )
        new_uns_devs: dict[DeviceType, list[ThinQDeviceInfo]] = {}
        for uns_dev_type, uns_dev_list in prev_uns_devs.items():
            valid_uns_devs = [
                dev for dev in uns_dev_list if dev.device_id in new_devs
            ]
            if valid_uns_devs:
                new_uns_devs[uns_dev_type] = valid_uns_devs
        for uns_dev_type, uns_dev_list in unsupported_devs.items():
            if uns_dev_type in new_uns_devs:
                new_uns_devs[uns_dev_type].extend(uns_dev_list)
            else:
                new_uns_devs[uns_dev_type] = uns_dev_list
        runtime_data[UNSUPPORTED_DEVICES] = new_uns_devs


async def async_refresh_devices_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: ClientAsync,
    notify_message: Any,
) -> None:
    """Refresh device discovery immediately."""
    _LOGGER.debug("Discovering new devices")

    old_devs = get_discovered_devices(hass)
    snapshot_manager = get_snapshot_manager(hass)
    lge_devs, unsupported_devs, new_devs = await lge_devices_setup(
        hass,
        client,
        old_devs,
        snapshot_manager=snapshot_manager,
    )
    _apply_discovery_results(
        hass,
        entry,
        lge_devs=lge_devs,
        unsupported_devs=unsupported_devs,
        old_devs=old_devs,
        new_devs=new_devs,
        notify_message=notify_message,
    )


@callback
def start_devices_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: ClientAsync,
    notify_message: Any,
) -> None:
    """Start devices discovery."""

    async def _async_discover_devices(_event: Any) -> None:
        """Discover new devices."""
        await async_refresh_devices_discovery(hass, entry, client, notify_message)

    entry.async_on_unload(
        async_track_time_interval(hass, _async_discover_devices, DISCOVERY_SCAN_INTERVAL)
    )
