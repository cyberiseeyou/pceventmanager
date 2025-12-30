"""
Custom exception hierarchy for type-safe error handling

Provides a structured exception hierarchy that maps to HTTP status codes
and enables consistent error responses across the application.

Usage:
    from error_handlers.exceptions import ValidationException

    def process_data(data):
        if not data:
            raise ValidationException('Data is required')

Exception Hierarchy:
    AppException (base)
    ├── ValidationException (400)
    ├── AuthenticationException (401)
    ├── AuthorizationException (403)
    ├── ResourceNotFoundException (404)
    ├── SyncDisabledException (400)
    └── ConfigurationException (500)
"""
from typing import Dict, Any, Optional


class AppException(Exception):
    """
    Base exception for all application errors

    All custom exceptions should inherit from this class to enable
    consistent error handling and response formatting.

    Attributes:
        status_code: HTTP status code for the error
        error_type: String identifier for the error type
        message: Human-readable error message
        details: Additional context about the error
    """
    status_code = 500
    error_type = 'ApplicationError'

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize application exception

        Args:
            message: Human-readable error message
            status_code: Optional HTTP status code override
            details: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.message = message
        if status_code:
            self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to JSON-serializable dictionary

        Returns:
            Dictionary suitable for JSON response
        """
        result = {
            'error': self.error_type,
            'message': self.message,
            'status_code': self.status_code
        }

        # Include details if present
        if self.details:
            result.update(self.details)

        return result

    def __str__(self) -> str:
        return f"{self.error_type}: {self.message}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}('{self.message}', status_code={self.status_code})>"


class ValidationException(AppException):
    """
    Validation errors (HTTP 400)

    Raised when request data fails validation checks.

    Example:
        >>> if not request.json.get('email'):
        ...     raise ValidationException('Email is required')
    """
    status_code = 400
    error_type = 'ValidationError'


class AuthenticationException(AppException):
    """
    Authentication errors (HTTP 401)

    Raised when user is not authenticated or credentials are invalid.

    Example:
        >>> if not is_authenticated():
        ...     raise AuthenticationException('Please log in')
    """
    status_code = 401
    error_type = 'AuthenticationError'


class AuthorizationException(AppException):
    """
    Authorization errors (HTTP 403)

    Raised when user is authenticated but lacks permission.

    Example:
        >>> if not user.is_admin:
        ...     raise AuthorizationException('Admin access required')
    """
    status_code = 403
    error_type = 'AuthorizationError'


class ResourceNotFoundException(AppException):
    """
    Resource not found (HTTP 404)

    Raised when a requested resource doesn't exist.

    Example:
        >>> employee = Employee.query.get(emp_id)
        >>> if not employee:
        ...     raise ResourceNotFoundException(f'Employee {emp_id} not found')
    """
    status_code = 404
    error_type = 'NotFound'


class SyncDisabledException(AppException):
    """
    Sync operations disabled (HTTP 400)

    Raised when sync operations are attempted but sync is disabled in config.

    Example:
        >>> if not current_app.config.get('SYNC_ENABLED'):
        ...     raise SyncDisabledException('Sync operations are disabled')
    """
    status_code = 400
    error_type = 'SyncDisabled'


class ConfigurationException(AppException):
    """
    Configuration errors (HTTP 500)

    Raised when application is misconfigured.

    Example:
        >>> if not config.SECRET_KEY:
        ...     raise ConfigurationException('SECRET_KEY not configured')
    """
    status_code = 500
    error_type = 'ConfigurationError'


class DatabaseException(AppException):
    """
    Database operation errors (HTTP 500)

    Raised when database operations fail.
    """
    status_code = 500
    error_type = 'DatabaseError'


class ExternalAPIException(AppException):
    """
    External API call errors (HTTP 502)

    Raised when external API calls fail.
    """
    status_code = 502
    error_type = 'ExternalAPIError'
