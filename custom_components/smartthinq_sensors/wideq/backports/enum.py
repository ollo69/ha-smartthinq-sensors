"""Enum backports from standard lib."""

from __future__ import annotations

from enum import StrEnum as _StrEnum
from typing import Any, Self


class StrEnum(_StrEnum):
    """Partial backport of Python 3.11's StrEnum for our basic use cases."""

    def __new__(cls, value: str, *_args: Any, **_kwargs: Any) -> Self:
        """Create a new StrEnum instance."""
        if not isinstance(value, str):
            raise TypeError(f"{value!r} is not a string")
        obj = str.__new__(cls, value)
        obj._value_ = value
        return obj

    def __str__(self) -> str:
        """Return self.value."""
        return str(self.value)

    @staticmethod
    def _generate_next_value_(
        name: str, start: int, count: int, last_values: list[Any]
    ) -> Any:
        """Make `auto()` explicitly unsupported.

        We may revisit this when it's very clear that Python 3.11's
        `StrEnum.auto()` behavior will no longer change.
        """
        raise TypeError("auto() is not supported by this implementation")
