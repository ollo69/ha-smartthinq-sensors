"""Support for MelCloud device bynary sensors."""
import logging

from .sensor import setup_sensors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    setup_sensors(hass, entry, async_add_entities, True)

