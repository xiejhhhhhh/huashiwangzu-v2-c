class AppException(Exception):
    """Base exception for app"""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class AuthError(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTH_ERROR", status_code=401)


class PermissionDenied(AppException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, code="PERMISSION_DENIED", status_code=403)


class NotFound(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="NOT_FOUND", status_code=404)


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed", details: list | None = None):
        self.details = details
        super().__init__(message, code="VALIDATION_ERROR", status_code=422)


class ConflictError(AppException):
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, code="CONFLICT", status_code=409)


class RateLimitError(AppException):
    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, code="RATE_LIMIT", status_code=429)
