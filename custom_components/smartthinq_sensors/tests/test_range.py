from wideq.device import DeviceType
from .test_device import DeviceTest

class RangeTest(DeviceTest):

    def test_status(self):
        device, status = super().setup("./tests/fixtures/range.json", DeviceType.RANGE)
        self.assertTrue(status.is_on)
        self.assertTrue(status.is_cooktop_on)
        self.assertEqual("off", status.cooktop_left_front_state)
        self.assertEqual("Cooking", status.cooktop_left_rear_state)
        self.assertEqual("off", status.cooktop_center_state)
        self.assertEqual("off", status.cooktop_right_front_state)
        self.assertEqual("off", status.cooktop_right_rear_state)
        self.assertTrue(status.is_oven_on)
        self.assertEqual("Preheating", status.oven_lower_state)
        self.assertEqual('350', status.oven_lower_target_temp)
        self.assertEqual("off", status.oven_upper_state)
        self.assertEqual('0', status.oven_upper_target_temp)
        self.assertEqual('fahrenheit', status.oven_temp_unit)
        pass