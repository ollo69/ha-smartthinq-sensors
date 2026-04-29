"""Exceptions."""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    """An error reported by the API."""

    message: str
    code: Any | None

    def __init__(self, message: str = "LG ThinQ API Error", code: Any | None = None) -> None:
        """Initialize the API error."""
        self.message = message
        self.code = code
        if code:
            msg = f"{code} - {message}"
        else:
            msg = message
        super().__init__(msg)


class ClientDisconnected(APIError):
    """Client connection was closed."""

    def __init__(self) -> None:
        """Initialize the client disconnected error."""
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

    def __init__(self, resp_msg: str) -> None:
        """Initialize the invalid response error."""
        super().__init__(f"Received response: {resp_msg}")


class InvalidCredentialError(APIError):
    """The server rejected connection."""


class DelayedResponseError(APIError):
    """The device delay in the response."""


class UseOfficialAPIError(APIError):
    """Requests stop responding suggesting to move to official public API."""


class TokenError(APIError):
    """An authentication token was rejected."""

    def __init__(self) -> None:
        """Initialize the token error."""
        super().__init__("Token Error")


class DeviceNotFound(APIError):
    """Device ID not valid."""


class MonitorError(APIError):
    """Monitoring a device failed, possibly because the session needs restart."""

    device_id: str

    def __init__(self, device_id: str, code: Any | None) -> None:
        """Initialize the monitor error."""
        self.device_id = device_id
        super().__init__(f"Monitor Error for device {device_id}", code)


class InvalidDeviceStatus(Exception):
    """Device exception occurred when status of device is not valid."""


class AuthenticationError(Exception):
    """API exception occurred when fail to authenticate."""

    message: str

    def __init__(self, message: str | None = None) -> None:
        """Initialize the authentication error."""
        if not message:
            self.message = "Authentication Error"
        else:
            self.message = message
        super().__init__(self.message)


class MonitorRefreshError(Exception):
    """Refresh a device status failed."""

    device_id: str
    message: str

    def __init__(self, device_id: str, message: str) -> None:
        """Initialize the monitor refresh error."""
        self.device_id = device_id
        self.message = message
        super().__init__(self.message)


class MonitorUnavailableError(Exception):
    """Refresh a device status failed because connection unavailable."""

    device_id: str
    message: str

    def __init__(self, device_id: str, message: str) -> None:
        """Initialize the monitor unavailable error."""
        self.device_id = device_id
        self.message = message
        super().__init__(self.message)
