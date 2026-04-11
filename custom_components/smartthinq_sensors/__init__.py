"""Support for LG SmartThinQ device."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any, cast
import uuid

from homeassistant.components import persistent_notification
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_REGION,
    CONF_TOKEN,
    EVENT_HOMEASSISTANT_STOP,
    MAJOR_VERSION,
    MINOR_VERSION,
    Platform,
    UnitOfTemperature,
    __version__,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .capability_registry import CapabilityRegistry
from .const import (
    CLIENT,
    CONF_LANGUAGE,
    CONF_OAUTH2_URL,
    CONF_OFFICIAL_CLIENT_ID,
    CONF_OFFICIAL_PAT,
    CONF_USE_API_V2,
    CONF_USE_HA_SESSION,
    DOMAIN,
    LGE_DEVICES,
    LGE_DISCOVERY_NEW,
    MIN_HA_MAJ_VER,
    MIN_HA_MIN_VER,
    OFFICIAL_CLIENT_PREFIX,
    STARTUP,
    __min_ha_version__,
)
from .coordinator_hybrid import HybridDataCoordinator
from .data_source_router import DataSourceRouter
from .official_bridge import async_setup_official_bridge
from .snapshot_manager import CommunitySnapshotManager
from .wideq import (
    DeviceInfo as ThinQDeviceInfo,
    DeviceType,
    TemperatureUnit,
    get_lge_device,
)
from .wideq.core_async import ClientAsync
from .wideq.core_exceptions import (
    AuthenticationError,
    InvalidCredentialError,
    MonitorRefreshError,
    MonitorUnavailableError,
    NotConnectedError,
)
from .wideq.device import Device as ThinQDevice

SMARTTHINQ_PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.HUMIDIFIER,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

MISSING_OFFICIAL_PAT_ISSUE = "missing_official_pat"

AUTH_RETRY = "auth_retry"
MAX_AUTH_RETRY = 4

MAX_DISC_COUNT = 4
SIGNAL_RELOAD_ENTRY = f"{DOMAIN}_reload_entry"

DISCOVERED_DEVICES = "discovered_devices"
UNSUPPORTED_DEVICES = "unsupported_devices"
SNAPSHOT_MANAGER = "snapshot_manager"
CAPABILITY_REGISTRY = "capability_registry"
DATA_SOURCE_ROUTER = "data_source_router"
HYBRID_COORDINATORS = "hybrid_coordinators"

SCAN_INTERVAL = timedelta(seconds=30)
_LOGGER = logging.getLogger(__name__)


class LGEAuthentication:
    """Class to authenticate connection with LG ThinQ."""

    def __init__(
        self,
        hass: HomeAssistant,
        region: str,
        language: str,
        use_ha_session: bool = False,
    ) -> None:
        """Initialize the class."""
        self._region = region
        self._language = language
        self._client_session = None
        if use_ha_session:
            self._client_session = async_get_clientsession(hass)

    async def get_login_url(self) -> str | None:
        """Get an url to login in browser."""
        try:
            return await ClientAsync.get_login_url(
                self._region, self._language, aiohttp_session=self._client_session
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("Error retrieving login URL from ThinQ", exc_info=exc)

        return None

    async def get_oauth_info_from_url(self, callback_url: str) -> dict[str, str] | None:
        """Retrieve oauth info from redirect url."""
        try:
            return await ClientAsync.oauth_info_from_url(
                callback_url,
                self._region,
                self._language,
                aiohttp_session=self._client_session,
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("Error retrieving OAuth info from ThinQ", exc_info=exc)

        return None

    async def get_oauth_info_from_login(
        self, username: str, password: str
    ) -> dict[str, str] | None:
        """Retrieve oauth info from user login credential."""
        try:
            return await ClientAsync.oauth_info_from_user_login(
                username,
                password,
                self._region,
                self._language,
                aiohttp_session=self._client_session,
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("Error retrieving OAuth info from ThinQ", exc_info=exc)

        return None

    async def create_client_from_token(
        self,
        token: str,
        oauth_url: str | None = None,
        client_id: str | None = None,
        update_clientid_callback: Callable[[str], None] | None = None,
    ) -> ClientAsync:
        """Create a new client using refresh token."""
        return await ClientAsync.from_token(
            token,
            country=self._region,
            language=self._language,
            oauth_url=oauth_url,
            aiohttp_session=self._client_session,
            client_id=client_id,
            update_clientid_callback=update_clientid_callback,
        )


def is_min_ha_version(min_ha_major_ver: int, min_ha_minor_ver: int) -> bool:
    """Check if HA version at least a specific version."""
    return min_ha_major_ver < MAJOR_VERSION or (
        min_ha_major_ver == MAJOR_VERSION and min_ha_minor_ver <= MINOR_VERSION
    )


def is_valid_ha_version() -> bool:
    """Check if HA version is valid for this integration."""
    return is_min_ha_version(MIN_HA_MAJ_VER, MIN_HA_MIN_VER)


def _notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification."""
    persistent_notification.async_create(
        hass, message, title, f"{DOMAIN}.{notification_id}"
    )


@callback
def _migrate_old_config_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate an old config entry if available."""
    old_key = "outh_url"  # old conf key with typo error
    if old_key not in entry.data:
        return

    oauth2_url = entry.data[old_key]
    new_data = {k: v for k, v in entry.data.items() if k != old_key}
    hass.config_entries.async_update_entry(
        entry, data={**new_data, CONF_OAUTH2_URL: oauth2_url}
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartThinQ integration from a config entry."""

    if not is_valid_ha_version():
        msg = (
            "This integration require at least HomeAssistant version "
            f" {__min_ha_version__}, you are running version {__version__}."
            " Please upgrade HomeAssistant to continue use this integration."
        )
        _notify_message(hass, "inv_ha_version", "SmartThinQ Sensors", msg)
        _LOGGER.warning(msg)
        return False

    _migrate_old_config_entry(hass, entry)
    region = entry.data[CONF_REGION]
    language = entry.data[CONF_LANGUAGE]
    refresh_token = entry.data[CONF_TOKEN]
    oauth2_url = None  # entry.data.get(CONF_OAUTH2_URL)
    client_id: str | None = entry.data.get(CONF_CLIENT_ID)
    official_client_id: str | None = entry.data.get(CONF_OFFICIAL_CLIENT_ID)
    official_pat: str | None = entry.data.get(CONF_OFFICIAL_PAT)
    use_api_v2 = entry.data.get(CONF_USE_API_V2, False)
    use_ha_session = entry.data.get(CONF_USE_HA_SESSION, False)

    if official_pat and not official_client_id:
        official_client_id = f"{OFFICIAL_CLIENT_PREFIX}-{uuid.uuid4()!s}"
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_OFFICIAL_CLIENT_ID: official_client_id},
        )

    issue_id = f"{MISSING_OFFICIAL_PAT_ISSUE}_{entry.entry_id}"
    if official_pat:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    else:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=MISSING_OFFICIAL_PAT_ISSUE,
            translation_placeholders={"title": entry.title},
        )

    if not use_api_v2:
        _LOGGER.warning(
            "Integration configuration is using ThinQ APIv1 that is unsupported. Please reconfigure"
        )
        # Launch config entries setup
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=entry.data
            )
        )
        return False

    log_info: bool = hass.data.get(DOMAIN, {}).get(SIGNAL_RELOAD_ENTRY, 0) < 2
    if log_info:
        hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: 2}
        _LOGGER.info(STARTUP)
        _LOGGER.info(
            "Initializing ThinQ platform with region: %s - language: %s",
            region,
            language,
        )
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(CAPABILITY_REGISTRY, CapabilityRegistry())
    domain_data.setdefault(
        DATA_SOURCE_ROUTER,
        DataSourceRouter(domain_data[CAPABILITY_REGISTRY]),
    )
    domain_data.setdefault(HYBRID_COORDINATORS, {})

    def _update_clientid_callback(client_id: str) -> None:
        """Update config entry with the new client id."""
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CLIENT_ID: client_id}
        )

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lge_auth = LGEAuthentication(hass, region, language, use_ha_session)
    try:
        client = await lge_auth.create_client_from_token(
            refresh_token, oauth2_url, client_id, _update_clientid_callback
        )
    except (AuthenticationError, InvalidCredentialError) as exc:
        if (auth_retry := hass.data[DOMAIN].get(AUTH_RETRY, 0)) >= MAX_AUTH_RETRY:
            hass.data.pop(DOMAIN)
            # Launch config entries reauth setup
            raise ConfigEntryAuthFailed("ThinQ authentication failed") from exc

        hass.data[DOMAIN][AUTH_RETRY] = auth_retry + 1
        msg = (
            "Invalid ThinQ credential error, integration setup aborted."
            " Please use the LG App on your mobile device to ensure your"
            " credentials are correct or there are new Term of Service to accept"
        )
        if log_info:
            _LOGGER.warning(msg, exc_info=True)
        raise ConfigEntryNotReady(msg) from exc

    except Exception as exc:
        if log_info:
            _LOGGER.warning(
                "Connection not available. ThinQ platform not ready", exc_info=True
            )
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    if not client.has_devices:
        _LOGGER.error("No ThinQ devices found. Component setup aborted")
        return False

    _LOGGER.debug("ThinQ client connected")

    try:
        snapshot_manager = CommunitySnapshotManager(client)
        lge_devices, unsupported_devices, discovered_devices = await lge_devices_setup(
            hass,
            client,
            snapshot_manager=snapshot_manager,
        )
    except Exception as exc:
        if log_info:
            _LOGGER.warning(
                "Connection not available. ThinQ platform not ready", exc_info=True
            )
        await client.close()
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    # remove device not available anymore
    dev_ids = [v for ids in discovered_devices.values() for v in ids]
    cleanup_orphan_lge_devices(hass, entry.entry_id, dev_ids)

    async def _async_call_reload_entry() -> None:
        """Reload current entry."""
        if SIGNAL_RELOAD_ENTRY in hass.data[DOMAIN]:
            return
        hass.data[DOMAIN][SIGNAL_RELOAD_ENTRY] = 1
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_RELOAD_ENTRY, _async_call_reload_entry)
    )

    async def _close_lg_client(event: Event) -> None:
        """Close client to abort pollong."""
        await client.close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _close_lg_client)
    )

    registry = hass.data[DOMAIN][CAPABILITY_REGISTRY]
    router = hass.data[DOMAIN][DATA_SOURCE_ROUTER]
    hybrid_coordinators = hass.data[DOMAIN][HYBRID_COORDINATORS]
    reload_signal = hass.data[DOMAIN].get(SIGNAL_RELOAD_ENTRY)
    hass.data[DOMAIN] = {
        CLIENT: client,
        LGE_DEVICES: lge_devices,
        UNSUPPORTED_DEVICES: unsupported_devices,
        DISCOVERED_DEVICES: discovered_devices,
        SNAPSHOT_MANAGER: snapshot_manager,
        CAPABILITY_REGISTRY: registry,
        DATA_SOURCE_ROUTER: router,
        HYBRID_COORDINATORS: hybrid_coordinators,
    }
    if reload_signal is not None:
        hass.data[DOMAIN][SIGNAL_RELOAD_ENTRY] = reload_signal
    await hass.config_entries.async_forward_entry_setups(entry, SMARTTHINQ_PLATFORMS)
    await async_setup_official_bridge(
        hass,
        entry.async_on_unload,
        official_pat=official_pat,
        official_client_id=official_client_id,
        country_code=region,
    )

    start_devices_discovery(hass, entry, client)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, SMARTTHINQ_PLATFORMS
    ):
        data = hass.data.pop(DOMAIN)
        reload = data.get(SIGNAL_RELOAD_ENTRY, 0)
        if reload > 0:
            hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: reload}
        await data[CLIENT].close()
    return unload_ok


class LGEDevice:
    """Generic class that represents a LGE device."""

    def __init__(
        self, device: ThinQDevice, hass: HomeAssistant, root_dev_id: str | None = None
    ) -> None:
        """Initialize a LGE device."""

        self._device: Any = device
        self._hass = hass
        self._root_dev_id = root_dev_id
        self._name = device.name
        self._device_id = device.unique_id
        self._type = device.device_info.type
        self._mac = None
        if mac := device.device_info.macaddress:
            self._mac = dr.format_mac(mac)
        self._firmware = device.device_info.firmware

        self._model = f"{device.device_info.model_name}"
        self._unique_id = f"{self._type.name}:{self._device_id}"

        self._state: Any = None
        self._coordinator: DataUpdateCoordinator[Any] | None = None
        self._disc_count = 0
        self._available = True
        self._last_mqtt_update: datetime | None = None

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self._available

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._available and self._disc_count >= MAX_DISC_COUNT

    @property
    def device(self) -> Any:
        """The device instance."""
        return self._device

    @property
    def device_id(self) -> str:
        """The device unique identifier."""
        return self._device_id

    @property
    def name(self) -> str:
        """The device name."""
        return self._name

    @property
    def type(self) -> DeviceType:
        """The device type."""
        return self._type

    @property
    def unique_id(self) -> str:
        """Device unique ID."""
        return self._unique_id

    @property
    def state(self) -> Any:
        """Current device state."""
        return self._state

    @property
    def last_mqtt_update(self) -> datetime | None:
        """Return the timestamp of the last MQTT-driven state update."""
        return self._last_mqtt_update

    @property
    def available_features(self) -> dict[Any, Any]:
        """Return a list of available features."""
        return cast(dict[Any, Any], self._device.available_features)

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Return device info for the device."""
        data = dr.DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._name,
            manufacturer="LG",
            model=f"{self._model} ({self._type.name})",
        )
        if self._firmware:
            data["sw_version"] = self._firmware
        if self._mac and not self._root_dev_id:
            data["connections"] = {(dr.CONNECTION_NETWORK_MAC, self._mac)}
        if self._root_dev_id:
            data["via_device"] = (DOMAIN, self._root_dev_id)

        return data

    @property
    def coordinator(self) -> DataUpdateCoordinator[Any]:
        """Return the DataUpdateCoordinator used by this device."""
        if self._coordinator is None:
            raise RuntimeError("Device coordinator is not initialized")
        return self._coordinator

    async def init_device(self) -> bool:
        """Init the device status and start coordinator."""
        if not await self._device.init_device_info():
            return False
        self._state = self._device.status
        if self._state is None:
            return False
        self._model = f"{self._model}-{self._device.model_info.model_type}"

        # Create status update coordinator
        await self._create_coordinator()

        # Initialize device features
        _ = self._state.device_features
        self._record_state_in_registry()

        return True

    @callback
    def async_set_updated(self) -> None:
        """Manually update state and notify coordinator entities."""
        if self._coordinator:
            self._coordinator.async_set_updated_data(self._state)

    def _get_registry_alias_values(self) -> dict[str, Any]:
        """Return curated logical attributes for hybrid source routing."""
        if self._state is None:
            return {}

        state = self._state
        aliases: dict[str, Any] = {}

        def _normalize_alias_key(key: Any) -> str:
            """Return a stable attribute suffix."""
            if hasattr(key, "name"):
                return str(key.name).lower()
            return str(key).lower()

        if self._type == DeviceType.AC:
            aliases = {
                "ac.is_on": getattr(state, "is_on", None),
                "ac.operation_mode": getattr(state, "operation_mode", None),
                "ac.current_temperature": getattr(state, "current_temp", None),
                "ac.target_temperature": getattr(state, "target_temp", None),
                "ac.current_humidity": getattr(state, "humidity", None),
                "ac.power_current": getattr(state, "energy_current", None),
            }
            if hasattr(state, "filters_life"):
                filters_life = state.filters_life
                if isinstance(filters_life, dict):
                    for key, value in filters_life.items():
                        aliases[f"ac.filter.{_normalize_alias_key(key)}"] = value

        elif self._type == DeviceType.REFRIGERATOR:
            aliases = {
                "refrigerator.temp_unit": getattr(state, "temp_unit", None),
                "refrigerator.door_open": getattr(state, "door_opened_state", None),
                "refrigerator.eco_friendly": getattr(
                    state,
                    "eco_friendly_enabled",
                    None,
                ),
                "refrigerator.fresh_air_filter": getattr(
                    state,
                    "fresh_air_filter_remain_perc",
                    None,
                ),
                "refrigerator.water_filter": getattr(
                    state,
                    "water_filter_remain_perc",
                    None,
                ),
            }
            if self._device.supports_fridge_compartment():
                aliases["refrigerator.fridge_temperature"] = getattr(
                    state,
                    "temp_fridge",
                    None,
                )
            if self._device.supports_freezer_compartment():
                aliases["refrigerator.freezer_temperature"] = getattr(
                    state,
                    "temp_freezer",
                    None,
                )

        elif self._type == DeviceType.WATER_HEATER:
            aliases = {
                "water_heater.is_on": getattr(state, "is_on", None),
                "water_heater.operation_mode": getattr(state, "operation_mode", None),
                "water_heater.current_temperature": getattr(state, "current_temp", None),
                "water_heater.target_temperature": getattr(state, "target_temp", None),
                "water_heater.power_current": getattr(state, "energy_current", None),
            }

        elif self._type == DeviceType.AIR_PURIFIER:
            aliases = {
                "air_purifier.is_on": getattr(state, "is_on", None),
                "air_purifier.operation": getattr(state, "operation", None),
                "air_purifier.operation_mode": getattr(state, "operation_mode", None),
                "air_purifier.fan_speed": getattr(state, "fan_speed", None),
                "air_purifier.fan_preset": getattr(state, "fan_preset", None),
                "air_purifier.current_humidity": getattr(
                    state,
                    "current_humidity",
                    None,
                ),
                "air_purifier.pm1": getattr(state, "pm1", None),
                "air_purifier.pm10": getattr(state, "pm10", None),
                "air_purifier.pm25": getattr(state, "pm25", None),
            }
            if hasattr(state, "filters_life"):
                filters_life = state.filters_life
                if isinstance(filters_life, dict):
                    for key, value in filters_life.items():
                        aliases[
                            f"air_purifier.filter.{_normalize_alias_key(key)}"
                        ] = value

        elif self._type == DeviceType.FAN:
            aliases = {
                "fan.is_on": getattr(state, "is_on", None),
                "fan.operation": getattr(state, "operation", None),
                "fan.fan_speed": getattr(state, "fan_speed", None),
            }

        elif self._type == DeviceType.DEHUMIDIFIER:
            aliases = {
                "dehumidifier.is_on": getattr(state, "is_on", None),
                "dehumidifier.operation": getattr(state, "operation", None),
                "dehumidifier.operation_mode": getattr(state, "operation_mode", None),
                "dehumidifier.fan_speed": getattr(state, "fan_speed", None),
                "dehumidifier.current_humidity": getattr(
                    state,
                    "current_humidity",
                    None,
                ),
                "dehumidifier.target_humidity": getattr(
                    state,
                    "target_humidity",
                    None,
                ),
                "dehumidifier.water_tank_full": getattr(
                    state,
                    "water_tank_full",
                    None,
                ),
            }

        elif self._type == DeviceType.HOOD:
            aliases = {
                "hood.is_on": getattr(state, "is_on", None),
                "hood.state": getattr(state, "hood_state", None),
                "hood.light_mode": getattr(state, "light_mode", None),
                "hood.vent_speed": getattr(state, "vent_speed", None),
            }

        elif self._type == DeviceType.MICROWAVE:
            aliases = {
                "microwave.is_on": getattr(state, "is_on", None),
                "microwave.oven_upper_state": getattr(
                    state,
                    "oven_upper_state",
                    None,
                ),
                "microwave.oven_upper_mode": getattr(
                    state,
                    "oven_upper_mode",
                    None,
                ),
                "microwave.clock_display": getattr(
                    state,
                    "is_clock_display_on",
                    None,
                ),
                "microwave.sound": getattr(state, "is_sound_on", None),
                "microwave.weight_unit": getattr(state, "weight_unit", None),
                "microwave.display_scroll_speed": getattr(
                    state,
                    "display_scroll_speed",
                    None,
                ),
            }

        elif self._type == DeviceType.RANGE:
            aliases = {
                "range.is_on": getattr(state, "is_on", None),
                "range.cooktop_on": getattr(state, "is_cooktop_on", None),
                "range.oven_on": getattr(state, "is_oven_on", None),
                "range.oven_temp_unit": getattr(state, "oven_temp_unit", None),
                "range.oven_lower_state": getattr(state, "oven_lower_state", None),
                "range.oven_upper_state": getattr(state, "oven_upper_state", None),
                "range.oven_lower_mode": getattr(state, "oven_lower_mode", None),
                "range.oven_upper_mode": getattr(state, "oven_upper_mode", None),
                "range.oven_lower_target_temperature": getattr(
                    state,
                    "oven_lower_target_temp",
                    None,
                ),
                "range.oven_upper_target_temperature": getattr(
                    state,
                    "oven_upper_target_temp",
                    None,
                ),
                "range.oven_lower_current_temperature": getattr(
                    state,
                    "oven_lower_current_temp",
                    None,
                ),
                "range.oven_upper_current_temperature": getattr(
                    state,
                    "oven_upper_current_temp",
                    None,
                ),
            }

        elif self._type == DeviceType.WASHER:
            aliases = {
                "washer.is_on": getattr(state, "is_on", None),
                "washer.run_state": getattr(state, "run_state", None),
                "washer.process_state": getattr(state, "process_state", None),
                "washer.current_course": getattr(state, "current_course", None),
            }

        elif self._type == DeviceType.DRYER:
            aliases = {
                "dryer.is_on": getattr(state, "is_on", None),
                "dryer.run_state": getattr(state, "run_state", None),
                "dryer.process_state": getattr(state, "process_state", None),
                "dryer.current_course": getattr(state, "current_course", None),
            }

        elif self._type == DeviceType.DISHWASHER:
            aliases = {
                "dishwasher.is_on": getattr(state, "is_on", None),
                "dishwasher.run_state": getattr(state, "run_state", None),
                "dishwasher.process_state": getattr(state, "process_state", None),
                "dishwasher.current_course": getattr(state, "current_course", None),
            }

        return {
            key: value for key, value in aliases.items() if value is not None
        }

    def _record_state_in_registry(self, *, official: bool = False) -> None:
        """Record the current state in the capability registry."""
        if self._state is None:
            return

        domain_data = self._hass.data.get(DOMAIN, {})
        capability_registry = domain_data.get(CAPABILITY_REGISTRY)
        if capability_registry is None:
            return

        profile = capability_registry.get_profile(self._device_id)
        if profile is None:
            profile = capability_registry.register_device(
                self._device_id,
                self._model,
                self._type,
            )

        if self._available:
            profile.mark_online()
        else:
            profile.mark_offline("community_device_unavailable")

        if not official:
            raw_state = getattr(self._state, "as_dict", {})
            if isinstance(raw_state, dict):
                for key, value in raw_state.items():
                    profile.update_attribute_community(f"state.{key}", value)

            device_features = getattr(self._state, "device_features", {})
            if isinstance(device_features, dict):
                for key, value in device_features.items():
                    profile.update_attribute_community(f"feature.{key}", value)

        for key, value in self._get_registry_alias_values().items():
            if official:
                profile.update_attribute_official(key, value)
            else:
                profile.update_attribute_community(key, value)

    def _state_reports_online(self, state: Any | None = None) -> bool | None:
        """Return the explicit online/offline flag from a state payload, if present."""
        if state is None:
            state = self._state
        if state is None:
            return None

        if hasattr(state, "as_dict"):
            raw_state = state.as_dict
            if callable(raw_state):
                raw_state = raw_state()
            if isinstance(raw_state, dict) and "online" in raw_state:
                online = raw_state.get("online")
                if isinstance(online, bool):
                    return online
                if isinstance(online, (int, float)):
                    return bool(online)

        online_attr = getattr(state, "online", None)
        if isinstance(online_attr, bool):
            return online_attr
        if isinstance(online_attr, (int, float)):
            return bool(online_attr)
        return None

    @callback
    def apply_mqtt_update(self, updates: dict[str, Any]) -> bool:
        """Apply MQTT payload values directly to the current state when possible."""
        if self._state is None or not hasattr(self._state, "update_status"):
            return False

        updated = False
        for key, value in updates.items():
            if key in {"deviceId", "timestamp", "pushType"}:
                continue
            if self._state.update_status(key, value):
                updated = True

        if updated:
            self._last_mqtt_update = utcnow()
            domain_data = self._hass.data.get(DOMAIN, {})
            capability_registry = domain_data.get(CAPABILITY_REGISTRY)
            if capability_registry is not None and (
                profile := capability_registry.get_profile(self._device_id)
            ) is not None:
                profile.mark_online()
            self._record_state_in_registry(official=True)
            self.async_set_updated()
        return updated

    async def _create_coordinator(self) -> None:
        """Get the coordinator for a specific device."""
        domain_data = self._hass.data.get(DOMAIN, {})
        capability_registry = domain_data.get(CAPABILITY_REGISTRY)
        data_source_router = domain_data.get(DATA_SOURCE_ROUTER)
        coordinator: DataUpdateCoordinator[Any]

        if capability_registry is not None and data_source_router is not None:
            capability_registry.register_device(
                self._device_id,
                self._model,
                self._type,
            )
            coordinator = HybridDataCoordinator(
                self._hass,
                _LOGGER,
                name=f"{DOMAIN}-{self._name}",
                device_id=self._device_id,
                device_model=self._model,
                device_type=self._type,
                update_method=self._async_update,
                capability_registry=capability_registry,
                data_source_router=data_source_router,
                base_polling_interval=SCAN_INTERVAL,
                mqtt_healthy_interval=timedelta(seconds=90),
                mqtt_unhealthy_interval=SCAN_INTERVAL,
            )
            hybrid_coordinators = domain_data.get(HYBRID_COORDINATORS)
            if isinstance(hybrid_coordinators, dict):
                hybrid_coordinators[self._device_id] = coordinator
        else:
            coordinator = DataUpdateCoordinator(
                self._hass,
                _LOGGER,
                name=f"{DOMAIN}-{self._name}",
                update_method=self._async_update,
                # Polling interval. Will only be polled if there are subscribers.
                update_interval=SCAN_INTERVAL,
            )
        await coordinator.async_refresh()
        self._coordinator = coordinator

    async def _async_update(self) -> Any:
        """Async update used by coordinator."""
        await self._async_state_update()
        return self._state

    async def _async_state_update(self) -> None:
        """Update device state."""
        _LOGGER.debug("Updating ThinQ device %s", self._name)
        if self._disc_count < MAX_DISC_COUNT:
            self._disc_count += 1

        try:
            # method poll should return None if status is not yet available
            # or due to temporary connection failure that will be restored
            state = await self._device.poll()

        except (MonitorRefreshError, NotConnectedError):
            # These exceptions are raised when device is not connected (turned off)
            # or unreachable due to network or API errors
            # If device status is "on" we reset the status, otherwise we just
            # ignore and use previous known state
            state = None
            capability_registry = self._hass.data.get(DOMAIN, {}).get(CAPABILITY_REGISTRY)
            if capability_registry is not None and (
                profile := capability_registry.get_profile(self._device_id)
            ) is not None:
                profile.mark_offline("device_disconnected_or_powered_off")
            if (
                self._state is not None
                and self._state.is_on
                and self._disc_count >= MAX_DISC_COUNT
            ):
                _LOGGER.warning(
                    "Status for device %s was reset because disconnected or unreachable",
                    self._name,
                )
                self._state = self._device.reset_status()

        except MonitorUnavailableError:
            # This exception is raised when issue with ThinQ persist
            # In this case available is set to false and device status
            # is reset to avoid confusion when connection is restored
            if not self._available:
                return
            _LOGGER.warning(
                "Status for device %s was reset because ThinQ connection not available",
                self._name,
            )
            self._available = False
            capability_registry = self._hass.data.get(DOMAIN, {}).get(CAPABILITY_REGISTRY)
            if capability_registry is not None and (
                profile := capability_registry.get_profile(self._device_id)
            ) is not None:
                profile.mark_offline("thinq_connection_unavailable")
            self._state = self._device.reset_status()
            return

        except InvalidCredentialError:
            # If we receive invalid credential, we reload integration
            # to provide proper notification
            async_dispatcher_send(self._hass, SIGNAL_RELOAD_ENTRY)
            return

        self._available = True
        capability_registry = self._hass.data.get(DOMAIN, {}).get(CAPABILITY_REGISTRY)
        if capability_registry is not None and (
            profile := capability_registry.get_profile(self._device_id)
        ) is not None:
            profile.mark_online()
        if state:
            _LOGGER.debug("ThinQ status updated")
            # l = dir(state)
            # _LOGGER.debug('Status attributes: %s', l)
            self._disc_count = 0
            self._state = state
            reported_online = self._state_reports_online(state)
            if reported_online is False:
                self._available = False
                if capability_registry is not None and (
                    profile := capability_registry.get_profile(self._device_id)
                ) is not None:
                    profile.mark_offline("device_reported_offline")
            else:
                self._available = True
                if capability_registry is not None and (
                    profile := capability_registry.get_profile(self._device_id)
                ) is not None:
                    profile.mark_online()
            self._record_state_in_registry()


async def lge_devices_setup(
    hass: HomeAssistant,
    client: ClientAsync,
    discovered_devices: dict[str, list[str]] | None = None,
    *,
    snapshot_manager: CommunitySnapshotManager | None = None,
) -> tuple[
    dict[DeviceType, list[LGEDevice]],
    dict[DeviceType, list[ThinQDeviceInfo]],
    dict[str, list[str]],
]:
    """Query connected devices from LG ThinQ."""
    _LOGGER.debug("Searching LGE ThinQ devices")

    wrapped_devices: dict[DeviceType, list[LGEDevice]] = {}
    unsupported_devices: dict[DeviceType, list[ThinQDeviceInfo]] = {}
    if discovered_devices is None:
        discovered_devices = {}

    if not client.has_devices:
        await client.refresh_devices()

    # if client device is None somenthing is wrong
    if (client_devices := client.devices) is None:
        return wrapped_devices, unsupported_devices, discovered_devices

    new_devices: dict[str, list[str]] = {}

    device_count = 0
    temp_unit = TemperatureUnit.CELSIUS
    if hass.config.units.temperature_unit != UnitOfTemperature.CELSIUS:
        temp_unit = TemperatureUnit.FAHRENHEIT

    async def init_device(
        lge_dev: ThinQDevice, device_info: ThinQDeviceInfo, root_dev_id: str | None
    ) -> bool:
        """Initialize a new device."""
        root_dev = None if root_dev_id == lge_dev.unique_id else root_dev_id
        dev = LGEDevice(lge_dev, hass, root_dev)
        if not await dev.init_device():
            _LOGGER.error(
                "Error initializing LGE Device. Name: %s - Type: %s - InfoUrl: %s",
                device_info.name,
                device_info.type.name,
                device_info.model_info_url,
            )
            return False

        new_devices[device_info.device_id].append(dev.device_id)
        wrapped_devices.setdefault(device_info.type, []).append(dev)
        _LOGGER.info(
            "LGE Device added. Name: %s - Type: %s - Model: %s - ID: %s",
            dev.name,
            device_info.type.name,
            device_info.model_name,
            dev.device_id,
        )
        return True

    for device_info in client_devices:
        device_id = device_info.device_id
        if device_id in discovered_devices:
            new_devices[device_id] = discovered_devices[device_id]
            continue

        new_devices[device_id] = []
        device_count += 1

        lge_devs = get_lge_device(
            client,
            device_info,
            temp_unit,
            snapshot_provider=snapshot_manager,
        )
        if not lge_devs:
            _LOGGER.info(
                "Found unsupported LGE Device. Name: %s - Type: %s - NetworkType: %s",
                device_info.name,
                device_info.type.name,
                device_info.network_type.name,
            )
            unsupported_devices.setdefault(device_info.type, []).append(device_info)
            continue

        root_dev = None
        for idx, lge_dev in enumerate(lge_devs):
            if idx == 0:
                root_dev = lge_dev.unique_id
            if not await init_device(lge_dev, device_info, root_dev):
                break
            if sub_dev := lge_dev.subkey_device:
                await init_device(sub_dev, device_info, root_dev)

    if device_count > 0:
        _LOGGER.info("Founds %s LGE device(s)", device_count)

    return wrapped_devices, unsupported_devices, new_devices


@callback
def cleanup_orphan_lge_devices(
    hass: HomeAssistant, entry_id: str, valid_dev_ids: list[str]
) -> None:
    """Delete devices that are not registered in LG client app."""

    # Load lg devices from registry
    device_registry = dr.async_get(hass)
    all_lg_dev_entries = dr.async_entries_for_config_entry(device_registry, entry_id)

    # get list of valid devices
    valid_reg_dev_ids = []
    for device_id in valid_dev_ids:
        dev = device_registry.async_get_device({(DOMAIN, device_id)})
        if dev is not None:
            valid_reg_dev_ids.append(dev.id)

    # clean-up invalid devices
    for dev_entry in all_lg_dev_entries:
        dev_id = dev_entry.id
        if dev_id in valid_reg_dev_ids:
            continue
        device_registry.async_remove_device(dev_id)


@callback
def start_devices_discovery(
    hass: HomeAssistant, entry: ConfigEntry, client: ClientAsync
) -> None:
    """Start devices discovery."""

    async def _async_discover_devices(_event: Any) -> None:
        """Discover new devices."""
        _LOGGER.debug("Discovering new devices")

        old_devs = hass.data[DOMAIN][DISCOVERED_DEVICES]
        snapshot_manager = hass.data[DOMAIN].get(SNAPSHOT_MANAGER)
        lge_devs, unsupported_devs, new_devs = await lge_devices_setup(
            hass,
            client,
            old_devs,
            snapshot_manager=snapshot_manager,
        )
        hass.data[DOMAIN][DISCOVERED_DEVICES] = new_devs

        # send signal to set up new entities
        if lge_devs:
            _notify_message(
                hass, "new_devices", "SmartThinQ Sensors", "Discovered new devices."
            )
            async_dispatcher_send(hass, LGE_DISCOVERY_NEW, lge_devs)

        # remove device not available anymore
        if lge_devs or unsupported_devs or len(old_devs) != len(new_devs):
            new_ids = [v for ids in new_devs.values() for v in ids]
            cleanup_orphan_lge_devices(hass, entry.entry_id, new_ids)

            # Update hass data LGE_DEVICES
            prev_lge_devs: dict[DeviceType, list[LGEDevice]] = hass.data[DOMAIN][
                LGE_DEVICES
            ]
            new_lge_devs: dict[DeviceType, list[LGEDevice]] = {}
            for dev_type, dev_list in prev_lge_devs.items():
                valid_lge_devs = [dev for dev in dev_list if dev.device_id in new_ids]
                if valid_lge_devs:
                    new_lge_devs[dev_type] = valid_lge_devs
            for dev_type, dev_list in lge_devs.items():
                if dev_type in new_lge_devs:
                    new_lge_devs[dev_type].extend(dev_list)
                else:
                    new_lge_devs[dev_type] = dev_list
            hass.data[DOMAIN][LGE_DEVICES] = new_lge_devs

            # Update hass data UNSUPPORTED_DEVICES
            prev_uns_devs: dict[DeviceType, list[ThinQDeviceInfo]] = hass.data[DOMAIN][
                UNSUPPORTED_DEVICES
            ]
            new_uns_devs: dict[DeviceType, list[ThinQDeviceInfo]] = {}
            for uns_dev_type, uns_dev_list in prev_uns_devs.items():
                valid_uns_devs = [
                    dev for dev in uns_dev_list if dev.device_id in new_devs
                ]
                if valid_uns_devs:
                    new_uns_devs[uns_dev_type] = valid_uns_devs
            for uns_dev_type, uns_dev_list in unsupported_devs.items():
                if uns_dev_type in new_uns_devs:
                    new_uns_devs[uns_dev_type].extend(uns_dev_list)
                else:
                    new_uns_devs[uns_dev_type] = uns_dev_list
            hass.data[DOMAIN][UNSUPPORTED_DEVICES] = new_uns_devs

    # schedule discover new devices every 5 minutes
    entry.async_on_unload(
        async_track_time_interval(hass, _async_discover_devices, timedelta(minutes=5))
    )
