import json
import unittest

from wideq.ac import AirConditionerDevice
from wideq.core_v2 import ClientV2
from wideq.device import Device
from wideq.device import DeviceStatus
from wideq.device import DeviceType
from wideq.device import UNIT_TEMP_FAHRENHEIT
from wideq.dishwasher import DishWasherDevice
from wideq.dryer import DryerDevice
from wideq.factory import get_lge_device
from wideq.range import RangeDevice
from wideq.refrigerator import RefrigeratorDevice
from wideq.styler import StylerDevice
from wideq.washer import WasherDevice

class DeviceTest(unittest.TestCase):

    def setup(self, type, fixture):
        """
        This method reads the json fixture file and returns the corresponding device and device status
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
                device = get_lge_device(client, device_info, UNIT_TEMP_FAHRENHEIT)
                self.assertIsNotNone(device)
                return device, device.poll()
        self.assertTrue(False)
