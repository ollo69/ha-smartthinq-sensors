"""Factory module for ThinQ library."""

from __future__ import annotations

from .const import TemperatureUnit
from .core_async import ClientAsync
from .device import Device
from .device_info import (
    WM_COMPLEX_DEVICES,
    WM_DEVICE_TYPES,
    DeviceInfo,
    DeviceType,
    NetworkType,
    PlatformType,
)
from .devices.ac import AirConditionerDevice
from .devices.airpurifier import AirPurifierDevice
from .devices.dehumidifier import DeHumidifierDevice
from .devices.dishwasher import DishWasherDevice
from .devices.fan import FanDevice
from .devices.hood import HoodDevice
from .devices.microwave import MicroWaveDevice
from .devices.range import RangeDevice
from .devices.refrigerator import RefrigeratorDevice
from .devices.styler import StylerDevice
from .devices.washerDryer import WMDevice
from .devices.waterheater import WaterHeaterDevice


def _get_sub_devices(device_type: DeviceType) -> list[str | None]:
    """Return a list of complex devices"""
    if sub_devices := WM_COMPLEX_DEVICES.get(device_type):
        return sub_devices
    return [None]


def get_lge_device(
    client: ClientAsync, device_info: DeviceInfo, temp_unit=TemperatureUnit.CELSIUS
) -> list[Device] | None:
    """Return a list of device objects based on the device type."""

    device_type = device_info.type
    platform_type = device_info.platform_type
    network_type = device_info.network_type

    if platform_type == PlatformType.UNKNOWN:
        return None
    if network_type != NetworkType.WIFI:
        return None

    if device_type == DeviceType.AC:
        return [AirConditionerDevice(client, device_info, temp_unit)]
    if device_type == DeviceType.AIR_PURIFIER:
        return [AirPurifierDevice(client, device_info)]
    if device_type == DeviceType.DEHUMIDIFIER:
        return [DeHumidifierDevice(client, device_info)]
    if device_type == DeviceType.DISHWASHER:
        return [DishWasherDevice(client, device_info)]
    if device_type == DeviceType.FAN:
        return [FanDevice(client, device_info)]
    if device_type == DeviceType.HOOD:
        return [HoodDevice(client, device_info)]
    if device_type == DeviceType.MICROWAVE:
        return [MicroWaveDevice(client, device_info)]
    if device_type == DeviceType.RANGE:
        return [RangeDevice(client, device_info)]
    if device_type == DeviceType.REFRIGERATOR:
        return [RefrigeratorDevice(client, device_info)]
    if device_type == DeviceType.STYLER:
        return [StylerDevice(client, device_info)]
    if device_type == DeviceType.WATER_HEATER:
        return [WaterHeaterDevice(client, device_info, temp_unit)]
    if device_type in WM_DEVICE_TYPES:
        return [
            WMDevice(client, device_info, sub_device=sub_device)
            for sub_device in _get_sub_devices(device_type)
        ]
    return None
