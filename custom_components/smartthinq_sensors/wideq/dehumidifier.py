"""------------------for Dehumidifier"""
import enum
import logging
from typing import Optional

from .const import (
    FEAT_HUMIDITY,
    FEAT_TARGET_HUMIDITY,
    FEAT_WATER_TANK_FULL,
)
from .core_exceptions import InvalidRequestError
from .device import Device, DeviceStatus

CTRL_BASIC = ["Control", "basicCtrl"]
STATE_POWER_V1 = "InOutInstantPower"

SUPPORT_OPERATION_MODE = ["SupportOpMode", "support.airState.opMode"]
SUPPORT_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]
SUPPORT_AIR_POLUTION = ["SupportAirPolution", "support.airPolution"]

STATE_OPERATION = ["Operation", "airState.operation"]
STATE_OPERATION_MODE = ["OpMode", "airState.opMode"]
STATE_TARGET_HUM = ["HumidityCfg", "airState.humidity.desired"]
STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]

STATE_CURRENT_HUM = ["SensorHumidity", "airState.humidity.current"]
STATE_PM1 = ["SensorPM1", "airState.quality.PM1"]
STATE_PM10 = ["SensorPM10", "airState.quality.PM10"]
STATE_PM25 = ["SensorPM2", "airState.quality.PM2"]
STATE_TANK_LIGHT = ["WatertankLight", "airState.miscFuncState.watertankLight"]

STATE_POWER = [STATE_POWER_V1, "airState.energy.onCurrent"]

CMD_STATE_OPERATION = [CTRL_BASIC, "Set", STATE_OPERATION]
CMD_STATE_OP_MODE = [CTRL_BASIC, "Set", STATE_OPERATION_MODE]
CMD_STATE_TARGET_HUM = [CTRL_BASIC, "Set", STATE_TARGET_HUM]
CMD_STATE_WIND_STRENGTH = [CTRL_BASIC, "Set", STATE_WIND_STRENGTH]

CMD_ENABLE_EVENT_V2 = ["allEventEnable", "Set", "airState.mon.timeout"]

DEFAULT_MIN_HUM = 30
DEFAULT_MAX_HUM = 70
DEFAULT_STEP_HUM = 5

ADD_FEAT_POLL_INTERVAL = 300  # 5 minutes

_LOGGER = logging.getLogger(__name__)


class DHumOp(enum.Enum):
    """Whether a device is on or off."""

    OFF = "@operation_off"
    ON = "@operation_on"


class DHumMode(enum.Enum):
    """The operation mode for a Dehumidifier device."""

    SMART = "@AP_MAIN_MID_OPMODE_SMART_DEHUM_W"
    FAST = "@AP_MAIN_MID_OPMODE_FAST_DEHUM_W"
    CILENT = "@AP_MAIN_MID_OPMODE_CILENT_DEHUM_W"
    CONC_DRY = "@AP_MAIN_MID_OPMODE_CONCENTRATION_DRY_W"
    CLOTH_DRY = "@AP_MAIN_MID_OPMODE_CLOTHING_DRY_W"
    IONIZER = "@AP_MAIN_MID_OPMODE_IONIZER_W"


class DHumFanSpeed(enum.Enum):
    """The fan speed for a Dehumidifier device."""

    LOW = "@AP_MAIN_MID_WINDSTRENGTH_DHUM_LOW_W"
    MID = "@AP_MAIN_MID_WINDSTRENGTH_DHUM_MID_W"
    HIGH = "@AP_MAIN_MID_WINDSTRENGTH_DHUM_HIGH_W"


class DeHumidifierDevice(Device):
    """A higher-level interface for DeHumidifier."""

    def __init__(self, client, device):
        super().__init__(client, device, DeHumidifierStatus(self, None))
        self._supported_op_modes = None
        self._supported_fan_speeds = None
        self._humidity_range = None
        self._humidity_step = DEFAULT_STEP_HUM

        self._current_power = 0
        self._current_power_supported = True

    def _get_humidity_range(self):
        """Get valid humidity range for model."""

        if not self._humidity_range:
            if not self.model_info:
                return None

            key = self._get_state_key(STATE_TARGET_HUM)
            range_info = self.model_info.value(key)
            if not range_info:
                min_hum = DEFAULT_MIN_HUM
                max_hum = DEFAULT_MAX_HUM
            else:
                min_hum = min(range_info.min, DEFAULT_MIN_HUM)
                max_hum = max(range_info.max, DEFAULT_MAX_HUM)
            self._humidity_range = [min_hum, max_hum]

        return self._humidity_range

    @property
    def op_modes(self):
        """Return a list of available operation modes."""
        if self._supported_op_modes is None:
            key = self._get_state_key(SUPPORT_OPERATION_MODE)
            if not self.model_info.is_enum_type(key):
                self._supported_op_modes = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in DHumMode]
            self._supported_op_modes = [DHumMode(o).name for o in mapping.values() if o in mode_list]
        return self._supported_op_modes

    @property
    def fan_speeds(self):
        """Return a list of available fan speeds."""
        if self._supported_fan_speeds is None:
            key = self._get_state_key(SUPPORT_WIND_STRENGTH)
            if not self.model_info.is_enum_type(key):
                self._supported_fan_speeds = []
                return []
            mapping = self.model_info.value(key).options
            mode_list = [e.value for e in DHumFanSpeed]
            self._supported_fan_speeds = [DHumFanSpeed(o).name for o in mapping.values() if o in mode_list]
        return self._supported_fan_speeds

    @property
    def target_humidity_step(self):
        """Return target humidity step used."""
        return self._humidity_step

    @property
    def target_humidity_min(self):
        """Return minimum value for target humidity."""
        if not (hum_range := self._get_humidity_range()):
            return None
        return hum_range[0]

    @property
    def target_humidity_max(self):
        """Return maximum value for target humidity."""
        if not (hum_range := self._get_humidity_range()):
            return None
        return hum_range[1]

    async def power(self, turn_on):
        """Turn on or off the device (according to a boolean)."""

        op = DHumOp.ON if turn_on else DHumOp.OFF
        keys = self._get_cmd_keys(CMD_STATE_OPERATION)
        op_value = self.model_info.enum_value(keys[2], op.value)
        if self._should_poll:
            # different power command for ThinQ1 devices
            cmd = "Start" if turn_on else "Stop"
            await self.set(keys[0], keys[2], key=None, value=cmd)
            self._status.update_status(keys[2], op_value)
            return
        await self.set(keys[0], keys[1], key=keys[2], value=op_value)

    async def set_op_mode(self, mode):
        """Set the device's operating mode to an `OpMode` value."""

        if mode not in self.op_modes:
            raise ValueError(f"Invalid operating mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_OP_MODE)
        mode_value = self.model_info.enum_value(keys[2], DHumMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=mode_value)

    async def set_fan_speed(self, speed):
        """Set the fan speed to a value from the `ACFanSpeed` enum."""

        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], DHumFanSpeed[speed].value)
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set_target_humidity(self, humidity):
        """Set the device's target humidity."""

        range_info = self._get_humidity_range()
        if range_info and not (range_info[0] <= humidity <= range_info[1]):
            raise ValueError(f"Target humidity out of range: {humidity}")
        keys = self._get_cmd_keys(CMD_STATE_TARGET_HUM)
        await self.set(keys[0], keys[1], key=keys[2], value=humidity)

    async def get_power(self):
        """Get the instant power usage in watts of the whole unit"""
        if not self._current_power_supported:
            return 0

        try:
            value = await self._get_config(STATE_POWER_V1)
            return value[STATE_POWER_V1]
        except (ValueError, InvalidRequestError):
            # Device does not support whole unit instant power usage
            self._current_power_supported = False
            return 0

    async def set(self, ctrl_key, command, *, key=None, value=None, data=None, ctrl_path=None):
        """Set a device's control for `key` to `value`."""
        await super().set(
            ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
        )
        if key is not None and self._status:
            self._status.update_status(key, value)

    def reset_status(self):
        self._status = DeHumidifierStatus(self, None)
        return self._status

    # async def _get_device_info(self):
    #    """Call additional method to get device information for API v1.
    #
    #    Called by 'device_poll' method using a lower poll rate
    #    """
    #    # this command is to get power usage on V1 device
    #    self._current_power = await self.get_power()

    # async def _pre_update_v2(self):
    #    """Call additional methods before data update for v2 API."""
    #    # this command is to get power and temp info on V2 device
    #    keys = self._get_cmd_keys(CMD_ENABLE_EVENT_V2)
    #    await self.set(keys[0], keys[1], key=keys[2], value="70", ctrl_path="control")

    async def poll(self) -> Optional["DeHumidifierStatus"]:
        """Poll the device's current state."""

        res = await self.device_poll()
        # res = await self.device_poll(
        #     thinq1_additional_poll=ADD_FEAT_POLL_INTERVAL,
        #     thinq2_query_device=True,
        # )
        if not res:
            return None
        # if self._should_poll:
        #     res[AC_STATE_POWER_V1] = self._current_power

        self._status = DeHumidifierStatus(self, res)

        return self._status


class DeHumidifierStatus(DeviceStatus):
    """Higher-level information about a DeHumidifier's current status."""

    def __init__(self, device, data):
        super().__init__(device, data)
        self._operation = None

    def _get_operation(self):
        if self._operation is None:
            key = self._get_state_key(STATE_OPERATION)
            self._operation = self.lookup_enum(key, True)
            if self._operation is None:
                return None
        try:
            return DHumOp(self._operation)
        except ValueError:
            return None

    def update_status(self, key, value):
        if not super().update_status(key, value):
            return False
        if key in STATE_OPERATION:
            self._operation = None
        return True

    @property
    def is_on(self):
        op = self._get_operation()
        if not op:
            return False
        return op != DHumOp.OFF

    @property
    def operation(self):
        op = self._get_operation()
        if not op:
            return None
        return op.name

    @property
    def operation_mode(self):
        key = self._get_state_key(STATE_OPERATION_MODE)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return DHumMode(value).name
        except ValueError:
            return None

    @property
    def fan_speed(self):
        key = self._get_state_key(STATE_WIND_STRENGTH)
        if (value := self.lookup_enum(key, True)) is None:
            return None
        try:
            return DHumFanSpeed(value).name
        except ValueError:
            return None

    @property
    def current_humidity(self):
        support_key = self._get_state_key(SUPPORT_AIR_POLUTION)
        if self._device.model_info.enum_value(support_key, "@SENSOR_HUMID_SUPPORT") is None:
            return None
        key = self._get_state_key(STATE_CURRENT_HUM)
        if (value := self.to_int_or_none(self.lookup_range(key))) is None:
            return None
        return self._update_feature(FEAT_HUMIDITY, value, False)

    @property
    def target_humidity(self):
        key = self._get_state_key(STATE_TARGET_HUM)
        if (value := self.to_int_or_none(self.lookup_range(key))) is None:
            return None
        return self._update_feature(FEAT_TARGET_HUMIDITY, value, False)

    @property
    def water_tank_full(self):
        key = self._get_state_key(STATE_TANK_LIGHT)
        if (value := self.lookup_enum(key)) is None:
            return None
        return self._update_feature(FEAT_WATER_TANK_FULL, value)

    def _update_features(self):
        _ = [
            self.current_humidity,
            self.target_humidity,
            self.water_tank_full,
        ]
