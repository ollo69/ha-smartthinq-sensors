class APIError(Exception):
    """An error reported by the API."""

    def __init__(self, code, message):
        self.code = code
        self.message = message


class NotLoggedInError(APIError):
    """The session is not valid or expired."""

    def __init__(self):
        pass


class NotConnectedError(APIError):
    """The service can't contact the specified device."""

    def __init__(self):
        pass


class FailedRequestError(APIError):
    """A failed request typically indicates an unsupported control on a
    device.
    """

    def __init__(self):
        pass


class InvalidRequestError(APIError):
    """The server rejected a request as invalid."""

    def __init__(self):
        pass


class InvalidCredentialError(APIError):
    """The server rejected connection."""

    def __init__(self):
        pass


class TokenError(APIError):
    """An authentication token was rejected."""

    def __init__(self):
        pass


class DeviceNotFound(APIError):
    """Device ID not valid."""

    def __init__(self):
        pass


class MonitorError(APIError):
    """Monitoring a device failed, possibly because the monitoring
    session failed and needs to be restarted.
    """

    def __init__(self, device_id, code):
        self.device_id = device_id
        self.code = code


class InvalidDeviceStatus(Exception):
    """Device exception occurred when status of device is not valid."""
