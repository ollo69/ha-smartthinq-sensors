"""Support for LG SmartThinQ device."""

import math
import uuid


def as_list(obj) -> list:
    """
    Wrap non-lists in lists.

    If `obj` is a list, return it unchanged.
    Otherwise, return a single-element list containing it.
    """

    if isinstance(obj, list):
        return obj
    return [obj]


def add_end_slash(url: str) -> str:
    """Add final slash to url."""
    if not url.endswith("/"):
        return url + "/"
    return url


def gen_uuid() -> str:
    """Return a str uuid in uuid4 format"""
    return str(uuid.uuid4())


class TempUnitConversion:
    """Class to convert temperature unit with LG device conversion rules."""

    def __init__(self):
        """Initialize object."""
        self._f2c_map = None
        self._c2f_map = None

    def f2c(self, value, model_info):
        """Convert Fahrenheit to Celsius temperatures based on model info."""

        # Unbelievably, SmartThinQ devices have their own lookup tables
        # for mapping the two temperature scales. You can get *close* by
        # using a real conversion between the two temperature scales, but
        # precise control requires using the custom LUT.

        if self._f2c_map is None:
            mapping = model_info.value("TempFahToCel").options
            self._f2c_map = {int(f): c for f, c in mapping.items()}
        return self._f2c_map.get(value, value)

    def c2f(self, value, model_info):
        """Convert Celsius to Fahrenheit temperatures based on model info."""

        # Just as unbelievably, this is not exactly the inverse of the
        # `f2c` map. There are a few values in this reverse mapping that
        # are not in the other.

        if self._c2f_map is None:
            mapping = model_info.value("TempCelToFah").options
            out = {}
            for cel, fah in mapping.items():
                try:
                    c_num = int(cel)
                except ValueError:
                    c_num = float(cel)
                out[c_num] = fah
            self._c2f_map = out
        if value is None:
            return None
        if (fah := self._c2f_map.get(value)) is not None:
            return fah

        # The LUT only covers the values used for target temperatures, while
        # room temperatures can be reported with decimals not in the map
        # (e.g. 22.7). Fall back to a real conversion instead of returning
        # the Celsius value unchanged.
        return math.floor(float(value) * 9 / 5 + 32 + 0.5)
