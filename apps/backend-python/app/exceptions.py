from typing import Any


class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class AuthenticationError(AppError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"


class AuthorizationError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class MT5ConnectionError(AppError):
    status_code = 502
    code = "MT5_CONNECTION_FAILED"
