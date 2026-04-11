"""Support for LG SmartThinQ device."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast
import uuid

if TYPE_CHECKING:
    from .model_info import EnumValue, ModelInfo

_T = TypeVar("_T")

def as_list(obj: _T | list[_T]) -> list[_T]:
    """Wrap non-lists in lists.

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
    """Return a str UUID in UUID4 format."""
    return str(uuid.uuid4())


class TempUnitConversion:
    """Class to convert temperature unit with LG device conversion rules."""

    def __init__(self) -> None:
        """Initialize object."""
        self._f2c_map: dict[int, int | str] | None = None
        self._c2f_map: dict[int | float, int | str] | None = None

    def f2c(self, value: int | str, model_info: ModelInfo) -> int | str:
        """Convert Fahrenheit to Celsius temperatures based on model info."""

        # Unbelievably, SmartThinQ devices have their own lookup tables
        # for mapping the two temperature scales. You can get *close* by
        # using a real conversion between the two temperature scales, but
        # precise control requires using the custom LUT.

        if self._f2c_map is None:
            mapping_value = model_info.value("TempFahToCel")
            if mapping_value is None:
                return value
            mapping = cast("EnumValue", mapping_value).options
            self._f2c_map = {int(f): c for f, c in mapping.items()}
        if not isinstance(value, int):
            return value
        return self._f2c_map.get(value, value)

    def c2f(self, value: float, model_info: ModelInfo) -> int | str | float:
        """Convert Celsius to Fahrenheit temperatures based on model info."""

        # Just as unbelievably, this is not exactly the inverse of the
        # `f2c` map. There are a few values in this reverse mapping that
        # are not in the other.

        if self._c2f_map is None:
            mapping_value = model_info.value("TempCelToFah")
            if mapping_value is None:
                return value
            mapping = cast("EnumValue", mapping_value).options
            out: dict[int | float, int | str] = {}
            for cel, fah in mapping.items():
                try:
                    c_num: int | float = int(cel)
                except ValueError:
                    c_num = float(cel)
                out[c_num] = fah
            self._c2f_map = out
        return self._c2f_map.get(value, value)
