import json
import unittest

from wideq.core_v2 import ClientV2
from wideq.device import DeviceType
from wideq.device import Device
from wideq.device import DeviceStatus
from wideq.device import UNIT_TEMP_FAHRENHEIT
from wideq.range import RangeDevice
from wideq.washer import WasherDevice
from wideq.dryer import DryerDevice
from wideq.styler import StylerDevice
from wideq.dishwasher import DishWasherDevice
from wideq.refrigerator import RefrigeratorDevice
from wideq.ac import AirConditionerDevice

class DeviceTest(unittest.TestCase):

    def setup(self, fixture, type):
        """
        This method reads the json fixture file and returns the
        corresponding device and device status
        :param fixture: path to json fixture file
        :param type: DeviceType of the device
        :return: tuple of Device, DeviceStatus
        """
        with open(fixture) as file:
            state = json.load(file)
        self.assertIsNotNone(state)
        client = ClientV2().load(state)
        self.assertIsNotNone(client)
        for device_info in client.devices:
            if device_info.type == type:
                if type in [DeviceType.WASHER, DeviceType.TOWER_WASHER]:
                    device = WasherDevice(client, device_info)
                elif type in [DeviceType.DRYER, DeviceType.TOWER_DRYER]:
                    device = DryerDevice(client, device_info)
                elif type == DeviceType.STYLER:
                    device = StylerDevice(client, device_info)
                elif type == DeviceType.DISHWASHER:
                    device = DishWasherDevice(client, device_info)
                elif type == DeviceType.REFRIGERATOR:
                    device = RefrigeratorDevice(client, device_info)
                elif type == DeviceType.AC:
                    device = AirConditionerDevice(client, device_info, UNIT_TEMP_FAHRENHEIT)
                elif type == DeviceType.RANGE:
                    device = RangeDevice(client, device_info)
                else:
                    self.assertTrue(False)
                return device, device.poll()
        self.assertTrue(False)
