"""
Error handling decorators

Provides decorators for consistent error handling across endpoints.
"""
from functools import wraps
from flask import jsonify, current_app
from datetime import datetime
from .exceptions import AppException, SyncDisabledException


def handle_errors(f):
    """
    Universal error handler decorator - use on all endpoints

    Provides:
    - Consistent JSON error responses
    - Automatic logging with error IDs
    - Exception type hierarchy support
    - Backward compatible with existing code

    Usage:
        @app.route('/endpoint')
        @handle_errors
        def my_endpoint():
            # Raise exceptions directly - decorator handles them
            if not valid:
                raise ValidationException('Invalid input')
            return jsonify({'success': True})

    Args:
        f: Function to decorate

    Returns:
        Decorated function with error handling
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)

        except AppException as e:
            # Custom exceptions - already formatted
            current_app.logger.warning(
                f"{e.error_type} in {f.__name__}: {e.message}",
                extra={'details': e.details} if e.details else {}
            )
            return jsonify(e.to_dict()), e.status_code

        except Exception as e:
            # Unexpected errors - log with ID and full traceback
            error_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')

            current_app.logger.error(
                f"Unexpected error [{error_id}] in {f.__name__}: {str(e)}",
                exc_info=True
            )

            # Don't expose internal error details in production
            return jsonify({
                'error': 'InternalError',
                'message': 'An unexpected error occurred',
                'error_id': error_id,
                'status_code': 500
            }), 500

    return decorated


def requires_sync_enabled(f):
    """
    Decorator to check if sync is enabled before executing sync operations

    Raises SyncDisabledException if sync is not enabled in config.

    Usage:
        @api_bp.route('/sync/start')
        @handle_errors  # Apply this first
        @requires_sync_enabled
        def start_sync():
            # This code only runs if sync is enabled
            ...

    Args:
        f: Function to decorate

    Returns:
        Decorated function that checks sync status

    Note:
        This should be used in combination with @handle_errors:
            @handle_errors
            @requires_sync_enabled
            def my_function():
                ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.config.get('SYNC_ENABLED'):
            current_app.logger.warning(
                f"Sync operation {f.__name__} attempted but sync is disabled"
            )
            raise SyncDisabledException(
                'Synchronization is disabled in configuration. '
                'Enable SYNC_ENABLED in your configuration to use sync features.'
            )
        return f(*args, **kwargs)
    return decorated_function


def with_db_transaction(f):
    """
    Decorator to wrap function in database transaction

    Automatically commits on success or rolls back on error.
    Useful for functions that perform multiple database operations.

    Usage:
        @handle_errors
        @with_db_transaction
        def update_employee(employee_id, data):
            employee = Employee.query.get(employee_id)
            employee.name = data['name']
            # Automatically committed on success

    Args:
        f: Function to decorate

    Returns:
        Decorated function with transaction management
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import current_app

        db = current_app.extensions['sqlalchemy']

        try:
            result = f(*args, **kwargs)
            db.session.commit()
            return result
        except Exception:
            db.session.rollback()
            raise  # Re-raise for error handler

    return decorated
