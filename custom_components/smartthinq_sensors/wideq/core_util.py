"""Support for LG SmartThinQ device."""
import uuid


def as_list(obj):
    """
    Wrap non-lists in lists.

    If `obj` is a list, return it unchanged.
    Otherwise, return a single-element list containing it.
    """

    if isinstance(obj, list):
        return obj
    return [obj]


def add_end_slash(url: str):
    """Add final slash to url."""
    if not url.endswith("/"):
        return url + "/"
    return url


def gen_uuid():
    return str(uuid.uuid4())
