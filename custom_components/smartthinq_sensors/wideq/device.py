"""Provide a high-level abstraction for the LG SmartThinQ API."""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
import json
import logging
from numbers import Number
from pathlib import Path
from typing import Any, Protocol, Self, cast

import aiohttp

from . import core_exceptions as core_exc
from .const import BIT_OFF, BIT_ON, StateOptions
from .core_async import ClientAsync
from .device_info import DeviceInfo, PlatformType
from .model_info import ModelInfo

LANG_PACK = "pack"

LABEL_BIT_OFF = "@CP_OFF_EN_W"
LABEL_BIT_ON = "@CP_ON_EN_W"

LOCAL_LANG_PACK = {
    BIT_OFF: StateOptions.OFF,
    BIT_ON: StateOptions.ON,
    LABEL_BIT_OFF: StateOptions.OFF,
    LABEL_BIT_ON: StateOptions.ON,
    "CLOSE": StateOptions.OFF,
    "OPEN": StateOptions.ON,
    "UNLOCK": StateOptions.OFF,
    "LOCK": StateOptions.ON,
    "INITIAL_BIT_OFF": StateOptions.OFF,
    "INITIAL_BIT_ON": StateOptions.ON,
    "STANDBY_OFF": StateOptions.OFF,
    "STANDBY_ON": StateOptions.ON,
    "@WM_EDD_REFILL_W": StateOptions.OFF,
    "IGNORE": StateOptions.NONE,
    "NONE": StateOptions.NONE,
    "NOT_USE": "Not Used",
}

MIN_TIME_BETWEEN_CLI_REFRESH = 10  # seconds
MAX_RETRIES = 3
MAX_UPDATE_FAIL_ALLOWED = 10
MAX_INVALID_CREDENTIAL_ERR = 3
SLEEP_BETWEEN_RETRIES = 2  # seconds

_LOGGER = logging.getLogger(__name__)


class ThinQSnapshotProvider(Protocol):
    """Protocol for shared ThinQ2 snapshot providers."""

    async def async_get_snapshot(
        self,
        device_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        """Return the snapshot for one device."""


class Monitor:
    """A monitoring task for a device.

    This task is robust to some API-level failures. If the monitoring
    task expires, it attempts to start a new one automatically. This
    makes one `Monitor` object suitable for long-term monitoring.
    """

    _client_lock = asyncio.Lock()
    _client_connected = True
    _critical_error = False
    _last_client_refresh = datetime.min
    _not_logged_count = 0

    def __init__(
        self,
        client: ClientAsync,
        device_info: DeviceInfo,
        snapshot_provider: ThinQSnapshotProvider | None = None,
    ) -> None:
        """Initialize monitor class."""
        self._client: ClientAsync = client
        self._device_id = device_info.device_id
        self._platform_type = device_info.platform_type
        self._device_descr = device_info.name
        self._snapshot_provider = snapshot_provider
        self._work_id: str | None = None
        self._has_error = False
        self._invalid_credential_count = 0
        self._error_log_count = 0

    def _raise_error(
        self,
        msg: str,
        *,
        not_logged: bool = False,
        exc: Exception | None = None,
        exc_info: bool = False,
        debug_count: int = 0,
    ) -> None:
        """Log and raise error with different level depending on condition."""

        if not_logged and Monitor._client_connected:
            Monitor._client_connected = False

        self._error_log_count += 1
        if self._error_log_count > debug_count:
            self._has_error = True

        if self._has_error or not_logged:
            log_lev = logging.WARNING
        else:
            log_lev = logging.DEBUG

        _LOGGER.log(
            log_lev, "%s - Device: %s", msg, self._device_descr, exc_info=exc_info
        )

        if (
            not Monitor._critical_error
            and Monitor._not_logged_count >= MAX_UPDATE_FAIL_ALLOWED
        ):
            Monitor._critical_error = True
            _LOGGER.error(msg, exc_info=exc_info)

        if Monitor._critical_error:
            raise core_exc.MonitorUnavailableError(self._device_id, msg) from exc
        raise core_exc.MonitorRefreshError(self._device_id, msg) from exc

    async def _refresh_auth(self) -> bool:
        """Refresh the devices shared client auth token."""
        async with Monitor._client_lock:
            if Monitor._client_connected:
                await self._client.refresh_auth()
                return True
            return await self._refresh_client()

    async def _refresh_client(self) -> bool:
        """Refresh the devices shared client."""
        if Monitor._client_connected:
            return True
        call_time = datetime.now(UTC)
        difference = (call_time - Monitor._last_client_refresh).total_seconds()
        if difference <= MIN_TIME_BETWEEN_CLI_REFRESH:
            return False

        Monitor._last_client_refresh = call_time
        refresh_gateway = False
        if Monitor._not_logged_count >= 30:
            Monitor._not_logged_count = 0
            refresh_gateway = True
        Monitor._not_logged_count += 1
        _LOGGER.debug("ThinQ client not connected, trying to reconnect")
        await self._client.refresh(refresh_gateway)
        _LOGGER.warning("ThinQ client successfully reconnected")
        Monitor._client_connected = True
        Monitor._critical_error = False
        Monitor._not_logged_count = 0
        return True

    async def refresh(self, query_device: bool = False) -> Any | None:
        """Update device state."""
        _LOGGER.debug("Updating ThinQ device %s", self._device_descr)
        invalid_credential_count = self._invalid_credential_count
        self._invalid_credential_count = 0

        state = None
        retry = False
        err9012raised = False
        for iteration in range(MAX_RETRIES):
            _LOGGER.debug("Polling")
            # Wait one second between iteration

            if iteration > 0:
                await asyncio.sleep(SLEEP_BETWEEN_RETRIES)

            try:
                if refresh_auth := await self._refresh_auth():
                    state, retry = await self.poll(query_device)

            except core_exc.NotConnectedError:
                # This exceptions occurs when APIv1 device is turned off
                self._error_log_count = 0
                if self._has_error:
                    _LOGGER.info(
                        "Connection is now available - Device: %s", self._device_descr
                    )
                    self._has_error = False
                _LOGGER.debug(
                    "Status not available. Device %s not connected", self._device_descr
                )
                if iteration >= 1:  # just retry 2 times
                    raise
                continue

            except core_exc.UseOfficialAPIError as exc:
                # When this exception comes, we retry 1 time before raising
                if not err9012raised:
                    err9012raised = True
                    continue

                self._raise_error(
                    "Received error 9012 multiple time while updating device status",
                    not_logged=True,
                    exc=exc,
                    exc_info=True,
                )

            except core_exc.ClientDisconnected:
                return None

            except core_exc.FailedRequestError:
                self._raise_error("Status update request failed", debug_count=2)

            except core_exc.DeviceNotFound:
                self._raise_error(
                    f"Device ID {self._device_id} is invalid, status update failed"
                )

            except core_exc.InvalidResponseError as exc:
                self._raise_error(
                    "Received invalid response, status update failed",
                    exc=exc,
                    exc_info=True,
                )

            except core_exc.NotLoggedInError as exc:
                # This could be raised by an expired token
                self._raise_error(
                    "Connection to ThinQ failed. ThinQ API error",
                    not_logged=True,
                    exc=exc,
                )

            except core_exc.TokenError as exc:
                self._raise_error(
                    "Connection to ThinQ failed. Invalid Token",
                    not_logged=True,
                    exc=exc,
                )

            except core_exc.InvalidCredentialError as exc:
                self._invalid_credential_count = invalid_credential_count
                if self._invalid_credential_count >= MAX_INVALID_CREDENTIAL_ERR:
                    raise
                self._invalid_credential_count += 1
                self._raise_error(
                    "Connection to ThinQ failed. Invalid Credential",
                    not_logged=True,
                    exc=exc,
                )

            except (TimeoutError, aiohttp.ServerTimeoutError) as exc:
                # These are network errors, refresh client is not required
                self._raise_error(
                    "Connection to ThinQ failed. Timeout error", exc=exc, debug_count=2
                )

            except aiohttp.ClientError as exc:
                # These are network errors, refresh client is not required
                self._raise_error(
                    "Connection to ThinQ failed. Network connection error",
                    exc=exc,
                    debug_count=2,
                )

            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
                self._raise_error(
                    "Unexpected error while updating device status",
                    not_logged=True,
                    exc=exc,
                    exc_info=True,
                )

            else:
                if not refresh_auth:
                    self._raise_error(
                        "Connection to ThinQ not available. Client refresh error",
                        not_logged=True,
                    )

                if state or not retry:
                    break

                _LOGGER.debug("No status available yet")

        self._error_log_count = 0
        if self._has_error:
            _LOGGER.info("Connection is now available - Device: %s", self._device_descr)
            self._has_error = False
        return state

    async def start(self) -> None:
        """Start monitor for ThinQ1 device."""
        if self._platform_type != PlatformType.THINQ1:
            return
        if self._work_id:
            return
        self._work_id = await self._client.session.monitor_start(self._device_id)

    async def stop(self) -> None:
        """Stop monitor for ThinQ1 device."""
        if not self._work_id:
            return
        work_id = self._work_id
        self._work_id = None
        await self._client.session.monitor_stop(self._device_id, work_id)

    async def poll(self, query_device: bool = False) -> tuple[Any | None, bool]:
        """Get the current status data.

        Returns a bytestring or None if the device is not yet ready.
        """
        if self._platform_type == PlatformType.THINQ1:
            return await self._poll_v1()
        return await self._poll_v2(query_device)

    async def _poll_v1(self) -> tuple[Any | None, bool]:
        """Get the current ThinQ1 status data.

        Returns a bytestring or None if the device is not yet ready.
        """
        await self.start()
        if not self._work_id:
            return None, True

        try:
            result = await self._client.session.monitor_poll(
                self._device_id, self._work_id
            )
        except core_exc.MonitorError:
            result = None
        except Exception:
            self._work_id = None
            raise

        if not result:
            self._work_id = None

        return result, True

    async def _poll_v2(self, query_device: bool = False) -> tuple[Any | None, bool]:
        """Get the current ThinQ2 status data.

        Returns JSON data or None if the device is not yet ready.
        """
        if self._platform_type != PlatformType.THINQ2:
            return None, False

        snapshot = None
        if query_device:
            result = await self._client.session.get_device_v2_settings(self._device_id)
            if "snapshot" in result:
                snapshot = deepcopy(result["snapshot"])
            return snapshot, False

        if self._snapshot_provider is not None:
            snapshot = await self._snapshot_provider.async_get_snapshot(self._device_id)
            if snapshot is not None:
                return deepcopy(snapshot), False

        await self._client.refresh_devices()
        if device_data := self._client.get_device(self._device_id):
            if dev_snapshot := device_data.snapshot:
                snapshot = deepcopy(dev_snapshot)

        return snapshot, False

    @staticmethod
    def decode_json(data: bytes) -> dict[str, Any]:
        """Decode a bytestring that encodes JSON status data."""

        return cast(dict[str, Any], json.loads(data.decode("utf8")))

    async def poll_json(self) -> dict[str, Any] | None:
        """Get the decoded status result for JSON-backed devices.

        Returns None if status is not available.
        """

        data, _ = await self.poll()
        if not isinstance(data, bytes):
            return None
        return self.decode_json(data)

    async def __aenter__(self) -> Self:
        """Enter the monitor context."""
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: object, exc_value: object, exc_traceback: object
    ) -> None:
        """Exit the monitor context."""
        await self.stop()


def _remove_duplicated(elem: list[Any]) -> list[Any]:
    """Remove duplicated values from a list."""
    return list(dict.fromkeys(elem))


class DeviceNotInitialized(Exception):
    """Device exception occurred when device is not initialized."""


class Device:
    """Represent a higher-level interface to a specific device.

    Unlike `DeviceInfo`, which just stores data *about* a device,
    `Device` objects refer to their client and can perform operations
    regarding the device.
    """

    def __init__(
        self,
        client: ClientAsync,
        device_info: DeviceInfo,
        status: DeviceStatus | None = None,
        *,
        sub_device: str | None = None,
        snapshot_provider: ThinQSnapshotProvider | None = None,
    ) -> None:
        """Create a wrapper for a `DeviceInfo` object associated with a Client."""

        self._client = client
        self._device_info = device_info
        self._status = status
        self._sub_device = sub_device
        self._model_data: dict[str, Any] | None = None
        self._model_info: ModelInfo | None = None
        self._model_lang_pack: dict[str, Any] | None = None
        self._product_lang_pack: dict[str, Any] | None = None
        self._local_lang_pack: dict[str, str] | None = None
        self._should_poll = device_info.platform_type == PlatformType.THINQ1
        self._mon = Monitor(client, device_info, snapshot_provider)
        self._snapshot_provider = snapshot_provider
        self._control_set = 0
        self._last_additional_poll: datetime | None = None
        self._available_features: dict[str, str | None] = {}

        # attributes for properties
        self._attr_unique_id = self._device_info.device_id
        self._attr_name = self._device_info.name
        if sub_device:
            self._attr_unique_id += f"-{sub_device}"
            self._attr_name += f" {sub_device.capitalize()}"

        # for logging unknown states received
        self._unknown_states: list[str] = []

    @property
    def client(self) -> ClientAsync:
        """Return client instance associated to this device."""
        return self._client

    @property
    def device_info(self) -> DeviceInfo:
        """Return 'device_info' for this device."""
        return self._device_info

    @property
    def unique_id(self) -> str:
        """Return unique id for this device."""
        return self._attr_unique_id

    @property
    def name(self) -> str:
        """Return name for this device."""
        return self._attr_name

    @property
    def model_info(self) -> ModelInfo:
        """Return 'model_info' for this device."""
        if self._model_info is None:
            raise DeviceNotInitialized
        return self._model_info

    @property
    def subkey_device(self) -> Device | None:
        """Return the available sub device."""
        return None

    @property
    def available_features(self) -> dict[str, str | None]:
        """Return available features."""
        return self._available_features

    @property
    def status(self) -> DeviceStatus | None:
        """Return status object associated to the device."""
        if not self._model_info:
            return None
        return self._status

    def reset_status(self) -> DeviceStatus | None:
        """Reset the status objevt associated to the device."""
        self._status = None
        return self._status

    async def init_device_info(self) -> bool:
        """Initialize the information for the device."""

        if self._model_info is None:
            if self._model_data is None:
                self._model_data = await self._client.model_url_info(
                    self._device_info.model_info_url,
                    self._device_info,
                )
                if self._model_data is None:
                    return False

            self._model_info = ModelInfo.get_model_info(
                self._model_data, self._sub_device
            )
            if self._model_info is None:
                return False

        # load model language pack
        if self._model_lang_pack is None:
            self._model_lang_pack = await self._client.model_url_info(
                self._device_info.model_lang_pack_url
            )

        # load product language pack
        if self._product_lang_pack is None:
            self._product_lang_pack = await self._client.model_url_info(
                self._device_info.product_lang_pack_url
            )

        # load local language pack
        if self._local_lang_pack is None:
            self._local_lang_pack = await self._client.local_lang_pack()

        return True

    def _get_state_key(self, key_name: str | list[str]) -> str:
        """Get the key used for state from an array based on info type."""
        if isinstance(key_name, list):
            return key_name[1 if self.model_info.is_info_v2 else 0]
        return key_name

    def _get_cmd_keys(self, key_name: list[str | list[str]]) -> list[str]:
        """Get the keys used for control based on info type."""
        ctrl = self._get_state_key(key_name[0])
        cmd = self._get_state_key(key_name[1])
        key = self._get_state_key(key_name[2])

        return [ctrl, cmd, key]

    def _get_property_values(
        self, prop_key: list[str] | str, prop_enum: type[Enum]
    ) -> list[str]:
        """Return a list of available values for a specific device property."""
        key = self._get_state_key(prop_key)
        if not self.model_info.is_enum_type(key):
            return []
        options = cast(Any, self.model_info.value(key)).options
        mapping = _remove_duplicated(list(options.values()))
        valid_props = [e.value for e in prop_enum]
        return [prop_enum(o).name for o in mapping if o in valid_props]

    async def _set_control(
        self,
        ctrl_key: str,
        command: str | None = None,
        *,
        key: str | None = None,
        value: str | None = None,
        data: str | None = None,
        ctrl_path: str | None = None,
    ) -> None:
        """Set a device's control for `key` to `value`."""
        if self._client.emulation:
            return

        if self._should_poll:
            await self._client.session.set_device_controls(
                self._device_info.device_id,
                ctrl_key,
                command,
                {key: value} if key and value else value,
                {key: data} if key and data else data,
            )
            self._control_set = 2
            return

        await self._client.session.device_v2_controls(
            self._device_info.device_id,
            ctrl_key,
            command,
            key,
            value,
            ctrl_path=ctrl_path,
        )

    def _prepare_command(
        self, ctrl_key: str, command: str | None, key: str | None, value: str | None
    ) -> Any:
        """Prepare command for specific device.

        Overwrite for specific device settings.
        """
        return None

    async def set(
        self,
        ctrl_key: str,
        command: str | None,
        *,
        key: str | None = None,
        value: str | None = None,
        data: str | None = None,
        ctrl_path: str | None = None,
    ) -> None:
        """Set a device's control for `key` to `value`."""
        log_level = logging.INFO if self._client.emulation else logging.DEBUG
        if full_key := self._prepare_command(ctrl_key, command, key, value):
            _LOGGER.log(
                log_level,
                "Setting new state for device %s: %s",
                self._device_info.device_id,
                str(full_key),
            )
            await self._set_control(full_key, ctrl_path=ctrl_path)
        else:
            _LOGGER.log(
                log_level,
                "Setting new state for device %s:  %s - %s - %s - %s",
                self._device_info.device_id,
                ctrl_key,
                command,
                key,
                value,
            )
            await self._set_control(
                ctrl_key, command, key=key, value=value, data=data, ctrl_path=ctrl_path
            )

    async def _get_config_v2(
        self,
        ctrl_key: str,
        command: str,
        *,
        key: str | None = None,
        value: str | None = None,
        ctrl_path: str | None = None,
    ) -> Any:
        """Look up a device's V2 configuration for a given value."""
        if self._should_poll or self.client.emulation:
            return None

        result = await self._client.session.device_v2_controls(
            self._device_info.device_id,
            ctrl_key,
            command,
            key,
            value,
            ctrl_path=ctrl_path,
        )

        if not result or "data" not in result:
            return None
        return result["data"]

    async def _get_config(self, key: str) -> Any:
        """Look up a device's configuration for a given value.

        The response is parsed as base64-encoded JSON.
        """
        if not self._should_poll:
            return None

        data = await self._client.session.get_device_config(
            self._device_info.device_id, key
        )
        if self._control_set == 0:
            self._control_set = 1
        return json.loads(base64.b64decode(data).decode("utf8"))

    async def _get_control(self, key: str) -> str | None:
        """Look up a device's control value."""
        if not self._should_poll:
            return None

        data = await self._client.session.get_device_config(
            self._device_info.device_id,
            key,
            "Control",
        )
        if self._control_set == 0:
            self._control_set = 1

        # The response comes in a funky key/value format: "(key:value)".
        _, value = str(data)[1:-1].split(":")
        return value

    async def _delete_permission(self) -> None:
        """Remove permission acquired in set command."""
        if not self._should_poll:
            return
        if self._control_set <= 0:
            return
        if self._control_set == 1:
            await self._client.session.delete_permission(self._device_info.device_id)
        self._control_set -= 1

    async def _pre_update_v2(self) -> None:
        """Call additional methods before data update for v2 API.

        Override in specific device to call requested methods.
        """
        return

    async def _get_device_info(self) -> None:
        """Call additional method to get device information for V1 API.

        Override in specific device to call requested methods.
        """
        return

    async def _get_device_info_v2(self) -> None:
        """Call additional method to get device information for V2 API.

        Override in specific device to call requested methods.
        """
        return

    async def _get_device_snapshot(self, query_device: bool = False) -> Any | None:
        """Get snapshot for ThinQ2 devices.

        Perform dedicated device query if query_device is set to true,
        otherwise use the dashboard result.
        """
        if self._client.emulation:
            query_device = False

        if query_device:
            try:
                await self._pre_update_v2()
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
                _LOGGER.debug("Error calling pre_update function: %s", exc)

        return await self._mon.refresh(query_device)

    async def _additional_poll(self, poll_interval: int) -> None:
        """Perform dedicated additional device poll with a slower rate."""
        if poll_interval <= 0:
            return
        call_time = datetime.now(UTC)
        if self._last_additional_poll is None:
            difference = float(poll_interval)
        else:
            difference = (call_time - self._last_additional_poll).total_seconds()
        if difference < poll_interval:
            return
        self._last_additional_poll = call_time
        if self._should_poll:
            try:
                await self._get_device_info()
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
                _LOGGER.debug("Error calling additional poll V1 methods: %s", exc)
        else:
            try:
                await self._get_device_info_v2()
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
                _LOGGER.debug("Error calling additional poll V2 methods: %s", exc)

    def _load_emul_v1_payload(self) -> bytes | None:
        """This is used only for debug.

        Load the payload for V1 device from file "deviceV1.txt".
        """
        if not self._client.emulation:
            return None

        data_file = Path(__file__).resolve().parent / "deviceV1.txt"
        try:
            with data_file.open(encoding="utf-8") as emu_payload:
                device_v1 = json.load(emu_payload)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if ret_val := device_v1.get(self.device_info.device_id):
            return str(ret_val).encode()
        return None

    async def _device_poll(
        self,
        snapshot_key: str = "",
        *,
        additional_poll_interval_v1: int = 0,
        additional_poll_interval_v2: int = 0,
        thinq2_query_device: bool = False,
    ) -> Any | None:
        """Poll the device's current state.

        Monitoring for thinq1 devices must be started first with `monitor_start`.

        Return either a `Status` object or `None` if the status is not yet available.

        :param snapshot_key: the key used to extract the thinq2 snapshot from payload.
        :param additional_poll_interval_v1: run an additional poll command for V1 devices
            at specified rate (0 means disabled).
        :param additional_poll_interval_v2: run an additional poll command for V2 devices
            at specified rate (0 means disabled).
        :param thinq2_query_device: if True query thinq2 devices with dedicated command
            instead using dashboard.
        """

        # load device info at first call if not loaded before
        if self._model_info is None:
            if not await self.init_device_info():
                return None

        # ThinQ V2 - Monitor data is with device info
        if not self._should_poll:
            snapshot = await self._get_device_snapshot(thinq2_query_device)
            if not snapshot:
                return None
            # do additional poll
            if additional_poll_interval_v2 > 0:
                await self._additional_poll(additional_poll_interval_v2)
            return self.model_info.decode_snapshot(snapshot, snapshot_key)

        # ThinQ V1 - Monitor data must be polled """
        data = None
        if self._client.emulation:
            data = await asyncio.to_thread(self._load_emul_v1_payload)
        if not data:
            data = await self._mon.refresh()
        if not data:
            return None

        res = self.model_info.decode_monitor(data)
        # do additional poll
        if res and additional_poll_interval_v1 > 0:
            await self._additional_poll(additional_poll_interval_v1)

        # remove control permission if previously set
        await self._delete_permission()

        return res

    async def poll(self) -> DeviceStatus | None:
        """Poll the device's current state."""
        return None

    def _get_feature_title(self, feature_name: str, item_key: str | None) -> str:
        """Override this function to manage feature title per device type."""
        return feature_name

    def feature_title(
        self,
        feature_name: str,
        item_key: str | None = None,
        status: str | None = None,
        allow_none: bool = False,
    ) -> str | None:
        """Return title associated to a specific feature."""
        if (title := self._available_features.get(feature_name)) is None:
            if status is None and not allow_none:
                return None
            if not (title := self._get_feature_title(feature_name, item_key)):
                return None
            self._available_features[feature_name] = title
        return title

    def get_enum_text(self, enum_name: str | None) -> str:
        """Get the text associated to an enum value from language pack."""
        if not enum_name:
            return StateOptions.NONE

        text_value = LOCAL_LANG_PACK.get(enum_name)
        if not text_value and self._model_lang_pack:
            if LANG_PACK in self._model_lang_pack:
                text_value = self._model_lang_pack[LANG_PACK].get(enum_name)
        if not text_value and self._product_lang_pack:
            if LANG_PACK in self._product_lang_pack:
                text_value = self._product_lang_pack[LANG_PACK].get(enum_name)
        if not text_value and self._local_lang_pack:
            text_value = self._local_lang_pack.get(enum_name)
        if not text_value:
            text_value = enum_name

        return text_value

    def is_unknown_status(self, status: str) -> bool:
        """Return if status is unknown."""
        if status in self._unknown_states:
            return False

        self._unknown_states.append(status)
        return True


class DeviceStatus:
    """A higher-level interface to a specific device status."""

    def __init__(self, device: Device, data: dict[str, Any] | None = None) -> None:
        """Initialize devicestatus object."""
        self._device = device
        self._data = data or {}
        self._device_features: dict[str, Any] = {}
        self._features_updated = False

    @staticmethod
    def int_or_none(value: Any) -> str | None:
        """Return specific value only if is a number."""
        if value is None:
            return None
        if not isinstance(value, Number):
            return None
        if (num_val := DeviceStatus.to_int_or_none(value)) is None:
            return None
        return str(num_val)

    @staticmethod
    def to_int_or_none(value: Any) -> int | None:
        """Try to convert the value to int or return None."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _str_to_num(str_val: str | None) -> int | float | None:
        """Convert a string to either an `int` or a `float`.

        Troublingly, the API likes values like "18", without a trailing
        ".0", for whole numbers. So we use `int`s for integers and
        `float`s for non-whole numbers.
        """
        if not str_val:
            return None

        fl_val = float(str_val)
        int_val = int(fl_val)
        return int_val if int_val == fl_val else fl_val

    def _get_filter_life(
        self,
        use_time_status: str | list[str],
        max_time_status: str | list[str],
        filter_types: list[str] | None = None,
        support_key: str | None = None,
        *,
        use_time_inverted: bool = False,
    ) -> list[int] | None:
        """Get filter status filtering by type if required."""
        if filter_types and support_key:
            supported = False
            for filter_type in filter_types:
                if (
                    self._device.model_info.enum_value(support_key, filter_type)
                    is not None
                ):
                    supported = True
                    break
            if not supported:
                return None

        key_max_status = self._get_state_key(max_time_status)
        max_time = self.to_int_or_none(self.lookup_enum(key_max_status, True))
        if max_time is None:
            max_time = self.to_int_or_none(self.lookup_range(key_max_status))
            if max_time is None:
                return None
            if max_time < 10:  # because is an enum
                return None

        use_time = self.to_int_or_none(
            self.lookup_range(self._get_state_key(use_time_status))
        )
        if use_time is None:
            return None
        # for models that return use_time directly in the payload,
        # the value actually represent remaining time
        if use_time_inverted:
            try:
                use_time = max(max_time - use_time, 0)
            except ValueError:
                return None

        try:
            return [
                int(((max_time - min(use_time, max_time)) / max_time) * 100),
                use_time,
                max_time,
            ]
        except ValueError:
            return None

    @property
    def has_data(self) -> bool:
        """Check if status contain valid data."""
        return bool(self._data)

    @property
    def as_dict(self) -> dict[str, Any]:
        """Return status raw data."""
        return deepcopy(self._data)

    @property
    def is_on(self) -> bool:
        """Check is on status."""
        return False

    @property
    def is_info_v2(self) -> bool:
        """Return type of associated model info."""
        return self._device.model_info.is_info_v2

    def _get_state_key(self, key_name: str | list[str]) -> str:
        """Return the key name based on model info type."""
        if isinstance(key_name, list):
            return key_name[1 if self.is_info_v2 else 0]
        return key_name

    def _get_data_key(self, keys: str | list[str]) -> str:
        """Return the key inside status data if match one of provided keys."""
        if not self._data:
            return ""
        if isinstance(keys, list):
            for key in keys:
                if key in self._data:
                    return key
        elif keys in self._data:
            return keys

        return ""

    def _set_unknown(
        self, status: str | None, key: str, status_type: str
    ) -> str | StateOptions:
        """Set a status for a specific key as unknown."""
        if status:
            return status

        if self._device.is_unknown_status(key):
            _LOGGER.warning(
                "ThinQ: received unknown %s status '%s' of type '%s'",
                self._device.device_info.type.name,
                key,
                status_type,
            )

        return StateOptions.UNKNOWN

    def update_status(self, key: str | list[str], value: Any) -> bool:
        """Update the status key to a specific value."""
        if not (upd_key := self._get_data_key(key)):
            return False
        self._data[upd_key] = value
        self._features_updated = False
        return True

    def update_status_feat(
        self, key: str | list[str], value: Any, upd_features: bool = False
    ) -> bool:
        """Update device status and features."""
        if not self.update_status(key, value):
            return False
        if upd_features:
            self._update_features()
        return True

    def get_model_info_key(self, keys: str | list[str]) -> str | None:
        """Return a key if one of provided keys exists in associated model info."""
        if isinstance(keys, list):
            for key in keys:
                if self._device.model_info.value_exist(key):
                    return key
        elif self._device.model_info.value_exist(keys):
            return keys
        return None

    def key_exist(self, keys: str | list[str]) -> bool:
        """Check if one of provided keys exists in associated model info."""
        return bool(self.get_model_info_key(keys))

    def lookup_enum(
        self, key: str | list[str], data_is_num: bool = False
    ) -> str | None:
        """Lookup value for a specific key of type enum."""
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        value = self._data[curr_key]
        if data_is_num:
            value = str(int(value))

        return self._device.model_info.enum_name(curr_key, value)

    def lookup_enum_bool(self, key: str | list[str]) -> str | None:
        """Lookup value for a specific key of type enum checking for bool type."""
        value = self.lookup_enum(key, True)
        if value and isinstance(value, str):
            if value.endswith("_ON_W"):
                return BIT_ON
            if value.endswith("_OFF_W"):
                return BIT_OFF
        return value

    def lookup_range(self, key: str | list[str]) -> Any:
        """Lookup value for a specific key of type range."""
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        return self._data[curr_key]

    def lookup_reference(
        self, key: str | list[str], ref_key: str = "_comment"
    ) -> str | None:
        """Lookup value for a specific key of type reference."""
        curr_key = self._get_data_key(key)
        if not curr_key:
            return None
        return self._device.model_info.reference_name(
            curr_key, self._data[curr_key], ref_key
        )

    def lookup_bit_enum(
        self, key: str, *, sub_key: str | None = None
    ) -> str | None:
        """Lookup value for a specific key of type bit enum."""
        if not self._data:
            str_val: str | None = None
        else:
            raw_val = self._data.get(key)
            str_val = raw_val if isinstance(raw_val, str) else None
            if not str_val:
                str_val = self._device.model_info.option_bit_value(
                    key, self._data, sub_key
                )

        if str_val is None:
            return None
        ret_val = self._device.model_info.enum_name(key, str_val)

        # exception because doorlock bit
        # is not inside the model enum
        door_locks = {"DoorLock": "1", "doorLock": "DOORLOCK_ON"}
        if not ret_val and key in door_locks:
            if str_val == door_locks[key]:
                return LABEL_BIT_ON
            return LABEL_BIT_OFF

        return ret_val

    def lookup_bit(
        self, key: str, *, sub_key: str | None = None, invert: bool = False
    ) -> str | StateOptions | None:
        """Lookup bit value for a specific key of type enum."""
        enum_val = self.lookup_bit_enum(key, sub_key=sub_key)
        if enum_val is None:
            return None
        bit_val = LOCAL_LANG_PACK.get(enum_val)
        if not bit_val:
            return StateOptions.OFF
        if not invert:
            return bit_val
        if bit_val == StateOptions.OFF:
            return StateOptions.ON
        return StateOptions.OFF

    def _update_feature(
        self,
        key: str,
        status: str | StateOptions | None,
        get_text: bool = True,
        item_key: str | None = None,
        *,
        allow_none: bool = False,
    ) -> str | StateOptions | None:
        """Update the status features."""
        if not self._device.feature_title(key, item_key, status, allow_none):
            return None

        if status is None and not allow_none:
            status = StateOptions.NONE

        if status == StateOptions.NONE:
            get_text = False

        if status is None or not get_text:
            value = status
        else:
            value = self._device.get_enum_text(status)

        self._device_features[key] = value
        return value

    def _update_features(self) -> None:
        """Override this function to manage device features."""
        raise NotImplementedError

    @property
    def device_features(self) -> dict[str, Any]:
        """Return features associated to the status."""
        if not self._features_updated:
            self._update_features()
            self._features_updated = True
        return self._device_features
