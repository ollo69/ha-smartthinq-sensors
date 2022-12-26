"""Factory module for ThinQ library."""

from .const import UNIT_TEMP_CELSIUS
from .device_info import (
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
from .devices.range import RangeDevice
from .devices.refrigerator import RefrigeratorDevice
from .devices.styler import StylerDevice
from .devices.washerDryer import WMDevice
from .devices.waterheater import WaterHeaterDevice


def get_lge_device(client, device: DeviceInfo, temp_unit=UNIT_TEMP_CELSIUS):
    """Return a device based on the device type."""

    device_type = device.type
    platform_type = device.platform_type
    network_type = device.network_type

    if platform_type == PlatformType.UNKNOWN:
        return None
    if network_type != NetworkType.WIFI:
        return None

    if device_type == DeviceType.AC:
        return AirConditionerDevice(client, device, temp_unit)
    if device_type == DeviceType.AIR_PURIFIER:
        return AirPurifierDevice(client, device)
    if device_type == DeviceType.DEHUMIDIFIER:
        return DeHumidifierDevice(client, device)
    if device_type == DeviceType.DISHWASHER:
        return DishWasherDevice(client, device)
    if device_type == DeviceType.FAN:
        return FanDevice(client, device)
    if device_type == DeviceType.RANGE:
        return RangeDevice(client, device)
    if device_type == DeviceType.REFRIGERATOR:
        return RefrigeratorDevice(client, device)
    if device_type == DeviceType.STYLER:
        return StylerDevice(client, device)
    if device_type in WM_DEVICE_TYPES:
        return WMDevice(client, device)
    if device_type == DeviceType.WATER_HEATER:
        return WaterHeaterDevice(client, device, temp_unit)

    return None
