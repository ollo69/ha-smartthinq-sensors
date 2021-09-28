
from .ac import AirConditionerDevice
from .airpurifier import AirPurifierDevice
from .dishwasher import DishWasherDevice
from .range import RangeDevice
from .refrigerator import RefrigeratorDevice
from .styler import StylerDevice
from .washerDryer import WMDevice

from .device import(
    UNIT_TEMP_CELSIUS,
    WM_DEVICE_TYPES,
    DeviceInfo,
    DeviceType,
    NetworkType,
    PlatformType,
)


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
    if device_type == DeviceType.DISHWASHER:
        return DishWasherDevice(client, device)
    if device_type == DeviceType.RANGE:
        return RangeDevice(client, device)
    if device_type == DeviceType.REFRIGERATOR:
        return RefrigeratorDevice(client, device)
    if device_type == DeviceType.STYLER:
        return StylerDevice(client, device)
    if device_type in WM_DEVICE_TYPES:
        return WMDevice(client, device)

    return None
