"""Exceptions"""


class APIError(Exception):
    """An error reported by the API."""

    def __init__(self, message="LG ThinQ API Error", code=None):
        self.message = message
        self.code = code
        if code:
            msg = f"{code} - {message}"
        else:
            msg = message
        super().__init__(msg)


class ClientDisconnected(APIError):
    """Client connection was closed."""

    def __init__(self):
        super().__init__("Client connection was closed")


class NotLoggedInError(APIError):
    """The session is not valid or expired."""


class NotConnectedError(APIError):
    """The service can't contact the specified device."""


class FailedRequestError(APIError):
    """A failed request typically indicates an unsupported control on a device."""


class InvalidRequestError(APIError):
    """The server rejected a request as invalid."""


class InvalidResponseError(APIError):
    """The server provide an invalid response."""

    def __init__(self, resp_msg):
        super().__init__(f"Received response: {resp_msg}")


class InvalidCredentialError(APIError):
    """The server rejected connection."""


class DelayedResponseError(APIError):
    """The device delay in the response."""


class TokenError(APIError):
    """An authentication token was rejected."""

    def __init__(self):
        super().__init__("Token Error")


class DeviceNotFound(APIError):
    """Device ID not valid."""


class MonitorError(APIError):
    """Monitoring a device failed, possibly because the monitoring
    session failed and needs to be restarted.
    """

    def __init__(self, device_id, code):
        self.device_id = device_id
        super().__init__(f"Monitor Error for device {device_id}", code)


class InvalidDeviceStatus(Exception):
    """Device exception occurred when status of device is not valid."""


class AuthenticationError(Exception):
    """API exception occurred when fail to authenticate."""

    def __init__(self, message=None):
        if not message:
            self.message = "Authentication Error"
        else:
            self.message = message
        super().__init__(self.message)


class MonitorRefreshError(Exception):
    """Refresh a device status failed."""

    def __init__(self, device_id, message):
        self.device_id = device_id
        self.message = message
        super().__init__(self.message)


class MonitorUnavailableError(Exception):
    """Refresh a device status failed because connection unavailable."""

    def __init__(self, device_id, message):
        self.device_id = device_id
        self.message = message
        super().__init__(self.message)
