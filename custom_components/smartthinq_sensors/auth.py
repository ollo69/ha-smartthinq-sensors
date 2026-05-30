"""Authentication and version helpers for SmartThinQ."""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MIN_HA_MAJ_VER, MIN_HA_MIN_VER
from .wideq.core_async import ClientAsync

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
