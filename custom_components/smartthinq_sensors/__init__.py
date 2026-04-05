"""Support for LG SmartThinQ device."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable

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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from thinqconnect import ThinQApi, ThinQAPIException

from .const import (
    CLIENT,
    CONF_LANGUAGE,
    CONF_OFFICIAL_CLIENT_ID,
    CONF_OFFICIAL_PAT,
    CONF_OAUTH2_URL,
    CONF_USE_API_V2,
    CONF_USE_HA_SESSION,
    DOMAIN,
    LGE_DEVICES,
    LGE_DISCOVERY_NEW,
    MIN_HA_MAJ_VER,
    MIN_HA_MIN_VER,
    MQTT_SUBSCRIPTION_INTERVAL,
    OFFICIAL_LGE_DEVICES,
    STARTUP,
    THINQ_MQTT,
    __min_ha_version__,
)
from .mqtt import ThinQMQTTHandler
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
from .wideq.devices.ac import normalize_official_ac_read
from .wideq.devices.fan import normalize_official_fan_read

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

AUTH_RETRY = "auth_retry"
MAX_AUTH_RETRY = 4

MAX_DISC_COUNT = 4
SIGNAL_RELOAD_ENTRY = f"{DOMAIN}_reload_entry"

DISCOVERED_DEVICES = "discovered_devices"
UNSUPPORTED_DEVICES = "unsupported_devices"

SCAN_INTERVAL = timedelta(seconds=30)
_LOGGER = logging.getLogger(__name__)

OfficialNormalizer = Callable[[dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


@dataclass(frozen=True)
class OfficialFamilySpec:
    """Configuration for official family enrichment."""

    label: str
    normalize: OfficialNormalizer
    require_profile: bool = True
    require_state: bool = True
    store_state: bool = False
    runtime_primary: bool = False
    community_poll_interval: int = 1


OFFICIAL_FAMILY_SPECS: dict[DeviceType, OfficialFamilySpec] = {
    DeviceType.AC: OfficialFamilySpec(
        label="AC",
        normalize=normalize_official_ac_read,
        require_profile=True,
        require_state=True,
        store_state=True,
        runtime_primary=False,
        community_poll_interval=1,
    ),
    DeviceType.FAN: OfficialFamilySpec(
        label="fan",
        normalize=normalize_official_fan_read,
        require_profile=True,
        require_state=True,
        store_state=True,
        runtime_primary=True,
        community_poll_interval=4,
    ),
}


class LGEAuthentication:
    """Class to authenticate connection with LG ThinQ."""

    def __init__(
        self, hass: HomeAssistant, region: str, language: str, use_ha_session=False
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
        official_pat: str | None = None,
        official_client_id: str | None = None,
    ) -> ClientAsync:
        """Create a new client using refresh token."""
        return await ClientAsync.from_token(
            token,
            country=self._region,
            language=self._language,
            oauth_url=oauth_url,
            aiohttp_session=self._client_session,
            client_id=client_id,
            official_pat=official_pat,
            official_client_id=official_client_id,
        )


def is_min_ha_version(min_ha_major_ver: int, min_ha_minor_ver: int) -> bool:
    """Check if HA version at least a specific version."""
    return MAJOR_VERSION > min_ha_major_ver or (
        MAJOR_VERSION == min_ha_major_ver and MINOR_VERSION >= min_ha_minor_ver
    )


def is_valid_ha_version() -> bool:
    """Check if HA version is valid for this integration."""
    return is_min_ha_version(MIN_HA_MAJ_VER, MIN_HA_MIN_VER)


def _notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification"""
    persistent_notification.async_create(
        hass, message, title, f"{DOMAIN}.{notification_id}"
    )


@callback
def _needs_official_pat_migration(entry: ConfigEntry) -> bool:
    """Return True when the entry still needs official PAT migration."""
    return not bool(entry.data.get(CONF_OFFICIAL_PAT))


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


@callback
def _add_clientid_config_entry(
    hass: HomeAssistant, entry: ConfigEntry, client_id: str
) -> None:
    """Add the client id to the config entry, so it can be reused."""
    if CONF_CLIENT_ID in entry.data or not client_id:
        return

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_CLIENT_ID: client_id}
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
    official_pat: str | None = entry.data.get(CONF_OFFICIAL_PAT)
    official_client_id: str | None = entry.data.get(CONF_OFFICIAL_CLIENT_ID)
    use_api_v2 = entry.data.get(CONF_USE_API_V2, False)
    use_ha_session = entry.data.get(CONF_USE_HA_SESSION, False)

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

    if _needs_official_pat_migration(entry):
        raise ConfigEntryAuthFailed(
            "Official ThinQ Personal Access Token required to migrate this entry to hybrid official/community API mode"
        )

    # if network is not connected we can have some error
    # raising ConfigEntryNotReady platform setup will be retried
    lge_auth = LGEAuthentication(hass, region, language, use_ha_session)
    try:
        client = await lge_auth.create_client_from_token(
            refresh_token,
            oauth2_url,
            client_id,
            official_pat,
            official_client_id,
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
        _LOGGER.exception(
            "ThinQ client creation failed during setup (region=%s, language=%s, has_official_pat=%s, has_official_client_id=%s)",
            region,
            language,
            bool(official_pat),
            bool(official_client_id),
            exc_info=exc,
        )
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    if not client.has_devices:
        _LOGGER.error("No ThinQ devices found. Component setup aborted")
        return False

    _LOGGER.debug("ThinQ client connected")

    if not client_id:
        _add_clientid_config_entry(hass, entry, client.client_id)

    try:
        lge_devices, unsupported_devices, discovered_devices = await lge_devices_setup(
            hass, client
        )
    except Exception as exc:
        _LOGGER.exception(
            "ThinQ device setup failed after client creation",
            exc_info=exc,
        )
        await client.close()
        raise ConfigEntryNotReady("ThinQ platform not ready") from exc

    if discovered_devices is None:
        await client.close()
        raise ConfigEntryNotReady("ThinQ platform not ready: no devices found.")

    await _enrich_official_families(client, lge_devices)
    official_lge_devices = _build_official_lge_device_map(client, lge_devices)

    # remove device not available anymore
    dev_ids = [v for ids in discovered_devices.values() for v in ids]
    cleanup_orphan_lge_devices(hass, entry.entry_id, dev_ids)

    async def _async_call_reload_entry():
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

    hass.data[DOMAIN] = {
        CLIENT: client,
        LGE_DEVICES: lge_devices,
        UNSUPPORTED_DEVICES: unsupported_devices,
        DISCOVERED_DEVICES: discovered_devices,
        OFFICIAL_LGE_DEVICES: official_lge_devices,
    }
    await hass.config_entries.async_forward_entry_setups(entry, SMARTTHINQ_PLATFORMS)

    if official_pat and official_client_id:
        thinq_api = ThinQApi(
            session=async_get_clientsession(hass),
            access_token=official_pat,
            country_code=region,
            client_id=official_client_id,
        )
        mqtt_handler = ThinQMQTTHandler(
            hass=hass,
            official_api=thinq_api,
            client=client,
            official_client_id=official_client_id,
            refresh_callback=_refresh_official_lge_device_runtime,
        )
        try:
            mqtt_connected = await mqtt_handler.async_connect()
        except (AttributeError, ThinQAPIException, TypeError, ValueError) as exc:
            _LOGGER.warning("Failed to set up ThinQ MQTT connection: %s", exc)
        else:
            if mqtt_connected:
                await mqtt_handler.async_start_subscribes()
                hass.data[DOMAIN][THINQ_MQTT] = mqtt_handler
                entry.async_on_unload(
                    async_track_time_interval(
                        hass,
                        mqtt_handler.async_refresh_subscribe,
                        MQTT_SUBSCRIPTION_INTERVAL,
                        cancel_on_shutdown=True,
                    )
                )
                entry.async_on_unload(
                    hass.bus.async_listen_once(
                        EVENT_HOMEASSISTANT_STOP,
                        mqtt_handler.async_disconnect,
                    )
                )
            else:
                _LOGGER.error("Failed to set up ThinQ MQTT connection")

    start_devices_discovery(hass, entry, client)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, SMARTTHINQ_PLATFORMS
    ):
        data = hass.data.pop(DOMAIN)
        reload = data.get(SIGNAL_RELOAD_ENTRY, 0)
        mqtt_handler = data.get(THINQ_MQTT)
        if mqtt_handler is not None:
            await mqtt_handler.async_disconnect()
        if reload > 0:
            hass.data[DOMAIN] = {SIGNAL_RELOAD_ENTRY: reload}
        await data[CLIENT].close()
    return unload_ok


class LGEDevice:
    """Generic class that represents a LGE device."""

    def __init__(
        self,
        device: ThinQDevice,
        hass: HomeAssistant,
        client: ClientAsync,
        root_dev_id: str | None = None,
    ):
        """initialize a LGE Device."""

        self._device = device
        self._hass = hass
        self._client = client
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

        self._state = None
        self._coordinator: DataUpdateCoordinator | None = None
        self._disc_count = 0
        self._community_poll_counter = 0
        self._available = True

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self._available

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._available and self._disc_count >= MAX_DISC_COUNT

    @property
    def device(self):
        """The device instance"""
        return self._device

    @property
    def device_id(self):
        """The device unique identifier"""
        return self._device_id

    @property
    def name(self) -> str:
        """The device name"""
        return self._name

    @property
    def type(self) -> DeviceType:
        """The device type"""
        return self._type

    @property
    def unique_id(self) -> str:
        """Device unique ID"""
        return self._unique_id

    @property
    def state(self):
        """Current device state"""
        return self._state

    @property
    def available_features(self) -> dict:
        """Return a list of available features."""
        return self._device.available_features

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the device."""
        data = DeviceInfo(
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
    def coordinator(self) -> DataUpdateCoordinator | None:
        """Return the DataUpdateCoordinator used by this device."""
        return self._coordinator

    async def init_device(self) -> bool:
        """Init the device status and start coordinator."""
        if not await self._device.init_device_info():
            return False
        self._state = self._device.status
        self._model = f"{self._model}-{self._device.model_info.model_type}"

        # Create status update coordinator
        await self._create_coordinator()

        # Initialize device features
        _ = self._state.device_features

        return True

    @callback
    def async_set_updated(self):
        """Manually update state and notify coordinator entities."""
        if self._coordinator:
            self._coordinator.async_set_updated_data(self._state)

    async def _create_coordinator(self) -> None:
        """Get the coordinator for a specific device."""
        coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
            self._hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._name}",
            update_method=self._async_update,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=SCAN_INTERVAL,
        )
        await coordinator.async_refresh()
        self._coordinator = coordinator

    async def _async_update(self):
        """Async update used by coordinator."""
        await self._async_state_update()
        return self._state

    async def _async_state_update(self):
        """Update device state."""
        _LOGGER.debug("Updating ThinQ device %s", self._name)
        if self._disc_count < MAX_DISC_COUNT:
            self._disc_count += 1

        client = self._client
        spec = OFFICIAL_FAMILY_SPECS.get(self._type)

        try:
            if spec and spec.runtime_primary:
                refreshed = await _refresh_official_lge_device(
                    client=client,
                    lge_device=self,
                    spec=spec,
                    include_profile=self._device.official_profile is None,
                )
                if refreshed:
                    _LOGGER.debug(
                        "ThinQ official runtime state updated for %s",
                        self._name,
                    )
                    self._available = True
                    self._disc_count = 0
                    self._community_poll_counter += 1
                    should_poll_community = (
                        self._state is None
                        or self._community_poll_counter >= spec.community_poll_interval
                    )
                    if not should_poll_community:
                        return
                    self._community_poll_counter = 0

            # method poll should return None if status is not yet available
            # or due to temporary connection failure that will be restored
            state = await self._device.poll()

        except (MonitorRefreshError, NotConnectedError):
            # These exceptions are raised when device is not connected (turned off)
            # or unreachable due to network or API errors
            # If device status is "on" we reset the status, otherwise we just
            # ignore and use previous known state
            state = None
            if self._state.is_on and self._disc_count >= MAX_DISC_COUNT:
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
            self._state = self._device.reset_status()
            return

        except InvalidCredentialError:
            # If we receive invalid credential, we reload integration
            # to provide proper notification
            async_dispatcher_send(self._hass, SIGNAL_RELOAD_ENTRY)
            return

        self._available = True
        if state:
            _LOGGER.debug("ThinQ status updated")
            # l = dir(state)
            # _LOGGER.debug('Status attributes: %s', l)
            self._disc_count = 0
            self._state = state


async def _refresh_official_lge_device(
    client: ClientAsync,
    lge_device: LGEDevice,
    spec: OfficialFamilySpec,
    *,
    include_profile: bool = False,
) -> bool:
    """Refresh official profile/state and normalized data for one wrapped LGE device."""
    dev = lge_device.device
    community_device_id = dev.device_info.device_id

    if not client._official_discovered_devices:
        await client.refresh_official_discovery_cache()

    official_device_id = client.official_device_id_for(dev.device_info)
    if not official_device_id:
        _LOGGER.debug(
            "LG official %s runtime mapping unavailable for community_device=%s",
            spec.label,
            community_device_id,
        )
        return False

    profile = dev.official_profile
    if include_profile or (spec.require_profile and not isinstance(profile, dict)):
        profile = await client.official_get_device_profile(official_device_id)
        if spec.require_profile and not isinstance(profile, dict):
            _LOGGER.warning(
                "LG official %s runtime profile missing/invalid for community_device=%s official_device=%s profile=%r",
                spec.label,
                community_device_id,
                official_device_id,
                profile,
            )
            return False
        dev._official_profile = profile

    state = await client.official_get_device_state(official_device_id)
    if spec.require_state and not isinstance(state, dict):
        if spec.label == "fan":
            _LOGGER.info(
                "LG official %s runtime state unavailable for community_device=%s official_device=%s state=%r",
                spec.label,
                community_device_id,
                official_device_id,
                state,
            )
        else:
            _LOGGER.warning(
                "LG official %s runtime state missing/invalid for community_device=%s official_device=%s state=%r",
                spec.label,
                community_device_id,
                official_device_id,
                state,
            )
        return False

    try:
        normalized = spec.normalize(profile, state)
    except Exception:
        _LOGGER.exception(
            "LG official %s runtime normalize failed for community_device=%s official_device=%s",
            spec.label,
            community_device_id,
            official_device_id,
        )
        return False

    if spec.store_state:
        dev._official_state = state
    dev._official_normalized = normalized

    _LOGGER.debug(
        "LG official %s runtime refresh community_device=%s official_device=%s is_on=%s fan_mode=%s hvac_mode=%s",
        spec.label,
        community_device_id,
        official_device_id,
        normalized.get("is_on") if isinstance(normalized, dict) else None,
        normalized.get("fan_mode") if isinstance(normalized, dict) else None,
        normalized.get("hvac_mode") if isinstance(normalized, dict) else None,
    )
    return True


def _build_official_lge_device_map(
    client: ClientAsync,
    lge_devices: dict[DeviceType, list[LGEDevice]],
) -> dict[str, LGEDevice]:
    """Build a lookup map from official device ID to wrapped LGEDevice."""
    official_devices: dict[str, LGEDevice] = {}

    for dev_list in lge_devices.values():
        for lge_dev in dev_list:
            official_device_id = client.official_device_id_for(
                lge_dev.device.device_info
            )
            if official_device_id:
                official_devices[official_device_id] = lge_dev

    return official_devices


async def _refresh_official_lge_device_runtime(
    client: ClientAsync,
    lge_device: LGEDevice,
) -> bool:
    """Refresh official runtime data for one wrapped device using family spec."""
    spec = OFFICIAL_FAMILY_SPECS.get(lge_device.type)
    if spec is None:
        return False

    return await _refresh_official_lge_device(
        client=client,
        lge_device=lge_device,
        spec=spec,
        include_profile=lge_device.device.official_profile is None,
    )


async def _enrich_official_family(
    client: ClientAsync,
    lge_devices: dict[DeviceType, list[LGEDevice]],
    device_type: DeviceType,
    spec: OfficialFamilySpec,
) -> None:
    """Fetch official profile/state and attach normalized data for one device family."""
    if not client._official_discovered_devices:
        await client.refresh_official_discovery_cache()

    for lge_dev in lge_devices.get(device_type, []):
        dev = lge_dev.device
        community_device_id = dev.device_info.device_id

        official_device_id = client.official_device_id_for(dev.device_info)
        if not official_device_id:
            _LOGGER.warning(
                "LG official %s mapping failed for community_device=%s",
                spec.label,
                community_device_id,
            )
            continue

        profile = await client.official_get_device_profile(official_device_id)
        if spec.require_profile and not isinstance(profile, dict):
            _LOGGER.warning(
                "LG official %s profile missing/invalid for community_device=%s official_device=%s profile=%r",
                spec.label,
                community_device_id,
                official_device_id,
                profile,
            )
            continue

        state = await client.official_get_device_state(official_device_id)
        if spec.require_state and not isinstance(state, dict):
            _LOGGER.warning(
                "LG official %s state missing/invalid for community_device=%s official_device=%s state=%r",
                spec.label,
                community_device_id,
                official_device_id,
                state,
            )
            continue

        try:
            normalized = spec.normalize(profile, state)
        except Exception:
            _LOGGER.exception(
                "LG official %s normalize failed for community_device=%s official_device=%s",
                spec.label,
                community_device_id,
                official_device_id,
            )
            continue

        dev._official_profile = profile
        if spec.store_state:
            dev._official_state = state
        dev._official_normalized = normalized

        _LOGGER.debug(
            "LG official %s normalized community_device=%s official_device=%s data=%s",
            spec.label,
            community_device_id,
            official_device_id,
            normalized,
        )


async def _enrich_official_families(
    client: ClientAsync,
    lge_devices: dict[DeviceType, list[LGEDevice]],
    device_types: list[DeviceType] | None = None,
) -> None:
    """Fetch official profile/state and attach normalized data for supported families."""
    target_types = device_types or list(OFFICIAL_FAMILY_SPECS.keys())

    for device_type in target_types:
        spec = OFFICIAL_FAMILY_SPECS.get(device_type)
        if spec is None:
            continue

        await _enrich_official_family(
            client=client,
            lge_devices=lge_devices,
            device_type=device_type,
            spec=spec,
        )


async def _enrich_official_ac_profiles(
    client: ClientAsync,
    lge_devices: dict[DeviceType, list[LGEDevice]],
) -> None:
    """Fetch official PAT-host AC profiles after device setup."""
    await _enrich_official_family(
        client=client,
        lge_devices=lge_devices,
        device_type=DeviceType.AC,
        spec=OFFICIAL_FAMILY_SPECS[DeviceType.AC],
    )


async def _enrich_official_fan_profiles(
    client: ClientAsync,
    lge_devices: dict[DeviceType, list[LGEDevice]],
) -> None:
    """Fetch official PAT-host fan profiles/state after device setup."""
    await _enrich_official_family(
        client=client,
        lge_devices=lge_devices,
        device_type=DeviceType.FAN,
        spec=OFFICIAL_FAMILY_SPECS[DeviceType.FAN],
    )


async def lge_devices_setup(
    hass: HomeAssistant,
    client: ClientAsync,
    discovered_devices: dict[str, list[str]] | None = None,
) -> tuple[
    dict[DeviceType, list[LGEDevice]],
    dict[DeviceType, list[ThinQDeviceInfo]],
    dict[str, list[str]],
]:
    """Query connected devices from LG ThinQ."""
    _LOGGER.debug("Searching LGE ThinQ devices...")

    wrapped_devices: dict[DeviceType, list[LGEDevice]] = {}
    unsupported_devices: dict[DeviceType, list[ThinQDeviceInfo]] = {}

    if not client.has_devices:
        await client.refresh_devices()

    # if client device is None somenthing is wrong
    if (client_devices := client.devices) is None:
        return wrapped_devices, unsupported_devices, discovered_devices

    new_devices = {}
    if discovered_devices is None:
        discovered_devices = {}

    device_count = 0
    temp_unit = TemperatureUnit.CELSIUS
    if hass.config.units.temperature_unit != UnitOfTemperature.CELSIUS:
        temp_unit = TemperatureUnit.FAHRENHEIT

    async def init_device(
        lge_dev: ThinQDevice, device_info: ThinQDeviceInfo, root_dev_id: str
    ):
        """Initialize a new device."""
        root_dev = None if root_dev_id == lge_dev.unique_id else root_dev_id
        dev = LGEDevice(lge_dev, hass, client, root_dev)
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

        lge_devs = get_lge_device(client, device_info, temp_unit)
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
    """Delete devices that are not registered in LG client app"""

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

    async def _async_discover_devices(_):
        """Discover new devices."""
        _LOGGER.debug("Discovering new devices...")

        old_devs = hass.data[DOMAIN][DISCOVERED_DEVICES]
        lge_devs, unsupported_devs, new_devs = await lge_devices_setup(
            hass, client, old_devs
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
                new_dev_list = [dev for dev in dev_list if dev.device_id in new_ids]
                if new_dev_list:
                    new_lge_devs[dev_type] = new_dev_list
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
            for dev_type, dev_list in prev_uns_devs.items():
                new_dev_list = [dev for dev in dev_list if dev.device_id in new_devs]
                if new_dev_list:
                    new_uns_devs[dev_type] = new_dev_list
            for dev_type, dev_list in unsupported_devs.items():
                if dev_type in new_uns_devs:
                    new_uns_devs[dev_type].extend(dev_list)
                else:
                    new_uns_devs[dev_type] = dev_list
            hass.data[DOMAIN][UNSUPPORTED_DEVICES] = new_uns_devs

    # schedule discover new devices every 5 minutes
    entry.async_on_unload(
        async_track_time_interval(hass, _async_discover_devices, timedelta(minutes=5))
    )
