"""
Support for LG SmartThinQ device.
"""
from enum import Enum

from .const import *

# enable emulation mode for debug / test
EMULATION = False


class CoreVersion(Enum):
    """The version of the core API."""

    CoreV1 = "coreV1"
    CoreV2 = "coreV2"
    CoreAsync = "coreAsync"
