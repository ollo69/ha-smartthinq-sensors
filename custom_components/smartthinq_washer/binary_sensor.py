"""Support for MelCloud device bynary sensors."""
import logging

from .sensor import async_setup_sensors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_sensors(hass, entry, async_add_entities, True)

