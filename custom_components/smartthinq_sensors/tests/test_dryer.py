from wideq.device import DeviceType
from .test_device import DeviceTest

class RangeTest(DeviceTest):

    def test_status(self):
        device, status = super().setup("./tests/fixtures/dryer.json", DeviceType.DRYER)
        self.assertTrue(status.is_on)
        self.assertFalse(status.is_run_completed)
        self.assertFalse(status.is_error)
        self.assertEqual("Bedding", status.current_course)
        self.assertEqual("-", status.current_smartcourse)
        self.assertEqual("0", status.initialtime_hour)
        self.assertEqual("55", status.initialtime_min)
        self.assertEqual("0", status.remaintime_hour)
        self.assertEqual("54", status.remaintime_min)
        self.assertEqual(None, status.reservetime_hour)
        self.assertEqual(None, status.reservetime_min)
        self.assertEqual("Drying", status.run_state)
        self.assertEqual("Standby", status.pre_state)
        self.assertEqual("Medium", status.temp_control_option_state)
        self.assertEqual("Normal", status.dry_level_option_state)
        self.assertEqual("-", status.time_dry_option_state)
        self.assertEqual("-", status.error_msg)
        self.assertEqual(None, status.doorlock_state)
        self.assertEqual("off", status.childlock_state)
        pass