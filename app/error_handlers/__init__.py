"""
Unified Error Handling System

Provides centralized, consistent error handling across the entire application.
Replaces scattered try/except blocks with a unified decorator and exception hierarchy.

Usage:
    from error_handlers import handle_errors
    from error_handlers.exceptions import ValidationException

    @app.route('/endpoint')
    @handle_errors
    def my_endpoint():
        if not valid:
            raise ValidationException('Invalid data')
        return jsonify({'success': True})
"""
from .exceptions import (
    AppException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    SyncDisabledException,
    ConfigurationException
)
from .decorators import handle_errors, requires_sync_enabled


__all__ = [
    # Exceptions
    'AppException',
    'ValidationException',
    'AuthenticationException',
    'AuthorizationException',
    'ResourceNotFoundException',
    'SyncDisabledException',
    'ConfigurationException',
    # Decorators
    'handle_errors',
    'requires_sync_enabled',
]


# Re-export old functions for backward compatibility
# These are imported from the original error_handlers.py module
def setup_logging(app):
    """
    Configure application logging

    DEPRECATED: Import directly from error_handlers.logging module
    """
    from app.error_handlers import logging as eh_logging
    return eh_logging.setup_logging(app)


def register_error_handlers(app):
    """
    Register global error handlers for the Flask app

    Now integrates with the new unified error handling system
    """
    from app.error_handlers import logging as eh_logging
    eh_logging.register_error_handlers(app)


def log_sync_operation(operation_type, details=None):
    """Log synchronization operations"""
    from app.error_handlers import logging as eh_logging
    return eh_logging.log_sync_operation(operation_type, details)


def handle_sync_error(operation, error, context=None):
    """Centralized sync error handling"""
    from app.error_handlers import logging as eh_logging
    return eh_logging.handle_sync_error(operation, error, context)


def api_error_handler(f):
    """
    DEPRECATED: Use @handle_errors decorator instead

    This decorator is kept for backward compatibility but should
    be replaced with the new @handle_errors decorator.
    """
    return handle_errors(f)


class SyncLogger:
    """
    DEPRECATED: Import from error_handlers.logging module

    Specialized logger for sync operations
    """
    def __init__(self, name='sync'):
        from app.error_handlers import logging as eh_logging
        self._logger = eh_logging.SyncLogger(name)

    def __getattr__(self, name):
        return getattr(self._logger, name)


# Global sync logger instance
from app.error_handlers import logging as eh_logging
sync_logger = eh_logging.sync_logger
