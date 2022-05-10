"""
Support for LG SmartThinQ device.
"""
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import DEFAULT_CIPHERS
import ssl
import uuid

# request ciphers settings
CIPHERS = ":HIGH:!DH:!aNULL"


def as_list(obj):
    """Wrap non-lists in lists.

    If `obj` is a list, return it unchanged. Otherwise, return a
    single-element list containing it.
    """

    if isinstance(obj, list):
        return obj
    else:
        return [obj]


def add_end_slash(url: str):
    """Add final slash to url."""
    if not url.endswith("/"):
        return url + "/"
    return url


def gen_uuid():
    return str(uuid.uuid4())


class AuthHTTPAdapter(HTTPAdapter):
    def __init__(self, use_tls_v1=False, exclude_dh=False):
        self._use_tls_v1 = use_tls_v1
        self._exclude_dh = exclude_dh
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        """
        Secure settings adding required ciphers
        """
        context = ssl.create_default_context()  # SSLContext()
        ciphers = DEFAULT_CIPHERS
        if self._exclude_dh:
            ciphers += CIPHERS

        context.set_ciphers(ciphers)
        self.poolmanager = PoolManager(
            *args,
            ssl_context=context,
            ssl_version=ssl.PROTOCOL_TLSv1 if self._use_tls_v1 else None,
            **kwargs,
        )
