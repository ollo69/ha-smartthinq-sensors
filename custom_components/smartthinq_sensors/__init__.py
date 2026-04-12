"""Support for LG SmartThinQ device."""

from __future__ import annotations

import logging

from aiohttp import ClientError
from thinqconnect import ThinQAPIException

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_REGION,
    CONF_TOKEN,
    Platform,
    __version__,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .auth import is_valid_ha_version
from .community_setup import (
    cleanup_orphan_lge_devices,
    lge_devices_setup,
    start_devices_discovery,
)
from .const import (
    CONF_LANGUAGE,
    CONF_USE_API_V2,
    CONF_USE_HA_SESSION,
    DOMAIN,
    SIGNAL_RELOAD_ENTRY,
    __min_ha_version__,
)
from .official_bridge import async_setup_official_bridge
from .runtime_data import get_domain_data
from .setup_runtime import (
    async_create_community_client,
    async_unload_runtime_data,
    ensure_official_runtime_config,
    migrate_old_config_entry,
    notify_message as _notify_message,
    prepare_runtime_context,
    register_entry_lifecycle_hooks,
    store_entry_runtime_data,
    update_missing_official_pat_issue,
)
from .snapshot_manager import CommunitySnapshotManager

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

_LOGGER = logging.getLogger(__name__)


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

    migrate_old_config_entry(hass, entry)
    region = entry.data[CONF_REGION]
    language = entry.data[CONF_LANGUAGE]
    refresh_token = entry.data[CONF_TOKEN]
    oauth2_url = None  # entry.data.get(CONF_OAUTH2_URL)
    client_id: str | None = entry.data.get(CONF_CLIENT_ID)
    official_pat, official_client_id = ensure_official_runtime_config(hass, entry)
    use_api_v2 = entry.data.get(CONF_USE_API_V2, False)
    use_ha_session = entry.data.get(CONF_USE_HA_SESSION, False)
    update_missing_official_pat_issue(hass, entry, official_pat)

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

    domain_data, log_info = prepare_runtime_context(
        hass, region=region, language=language
    )

    client = await async_create_community_client(
        hass,
        entry,
        region=region,
        language=language,
        refresh_token=refresh_token,
        oauth2_url=oauth2_url,
        client_id=client_id,
        use_ha_session=use_ha_session,
        log_info=log_info,
        domain_key=DOMAIN,
    )

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
        runtime_data = get_domain_data(hass)
        if SIGNAL_RELOAD_ENTRY in runtime_data:
            return
        runtime_data[SIGNAL_RELOAD_ENTRY] = 1
        await hass.config_entries.async_reload(entry.entry_id)

    register_entry_lifecycle_hooks(
        hass,
        entry,
        client=client,
        reload_entry=_async_call_reload_entry,
    )
    store_entry_runtime_data(
        hass,
        client=client,
        lge_devices=lge_devices,
        unsupported_devices=unsupported_devices,
        discovered_devices=discovered_devices,
        snapshot_manager=snapshot_manager,
        domain_data=domain_data,
    )
    await hass.config_entries.async_forward_entry_setups(entry, SMARTTHINQ_PLATFORMS)
    try:
        await async_setup_official_bridge(
            hass,
            entry.async_on_unload,
            official_pat=official_pat,
            official_client_id=official_client_id,
            country_code=region,
        )
    except (ClientError, OSError, TimeoutError, ThinQAPIException):
        _LOGGER.warning(
            "Official ThinQ runtime unavailable; continuing with community API only",
            exc_info=True,
        )

    start_devices_discovery(hass, entry, client, _notify_message)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, SMARTTHINQ_PLATFORMS
    ):
        client = await async_unload_runtime_data(hass)
        if client is not None:
            await client.close()
    return unload_ok
