from wideq.device import DeviceType
from .test_device import DeviceTest

class RangeTest(DeviceTest):

    def test_status(self):
        device, status = super().setup("./tests/fixtures/washer.json", DeviceType.WASHER)
        self.assertTrue(status.is_on)
        self.assertFalse(status.is_run_completed)
        self.assertFalse(status.is_error)
        self.assertEqual("Bedding", status.current_course)
        self.assertEqual("Swimwear", status.current_smartcourse)
        self.assertEqual(None, status.initialtime_hour)
        self.assertEqual("60", status.initialtime_min)
        self.assertEqual(None, status.remaintime_hour)
        self.assertEqual("58", status.remaintime_min)
        self.assertEqual(None, status.reservetime_hour)
        self.assertEqual("0", status.reservetime_min)
        self.assertEqual("Washing", status.run_state)
        self.assertEqual("-", status.pre_state)
        self.assertEqual("Medium", status.spin_option_state)
        self.assertEqual("Warm", status.water_temp_option_state)
        self.assertEqual("Not Selected", status.dry_level_option_state)
        self.assertEqual("-", status.error_msg)
        self.assertEqual("18", status.tubclean_count)
        self.assertEqual(None, status.doorlock_state)
        self.assertEqual("off", status.doorclose_state)
        self.assertEqual("off", status.childlock_state)
        self.assertEqual("on", status.remotestart_state)
        self.assertEqual(None, status.creasecare_state)
        self.assertEqual("off", status.steam_state)
        self.assertEqual(None, status.steam_softener_state)
        self.assertEqual("off", status.prewash_state)
        self.assertEqual("off", status.turbowash_state)
        self.assertEqual(None, status.medicrinse_state)
        pass