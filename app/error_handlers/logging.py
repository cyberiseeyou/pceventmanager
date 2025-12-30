"""
Error handling and logging utilities for Flask Schedule Webapp
Provides centralized error handling, logging, and debugging capabilities
"""
import logging
import traceback
from datetime import datetime
from flask import jsonify, request, current_app
from functools import wraps
import os


def setup_logging(app):
    """Configure application logging"""
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    log_file = app.config.get('LOG_FILE', 'scheduler.log')

    # Make log file path absolute if it's not
    if not os.path.isabs(log_file):
        # Get the base directory (project root)
        basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        log_file = os.path.join(basedir, log_file)

    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging format
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # Configure app logger
    app.logger.setLevel(log_level)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)

    # Configure werkzeug logger (Flask's request logger)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(log_level)

    return app.logger


def register_error_handlers(app):
    """Register global error handlers for the Flask app"""

    @app.errorhandler(400)
    def bad_request_error(error):
        """Handle 400 Bad Request errors"""
        app.logger.warning(f"Bad request from {request.remote_addr}: {request.url}")
        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Bad Request',
                'message': 'The request could not be understood by the server',
                'status_code': 400
            }), 400
        return "Bad Request", 400

    @app.errorhandler(401)
    def unauthorized_error(error):
        """Handle 401 Unauthorized errors"""
        app.logger.warning(f"Unauthorized access attempt from {request.remote_addr}: {request.url}")
        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Authentication required',
                'status_code': 401
            }), 401
        return "Unauthorized", 401

    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 Forbidden errors"""
        app.logger.warning(f"Forbidden access attempt from {request.remote_addr}: {request.url}")
        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Forbidden',
                'message': 'Access denied',
                'status_code': 403
            }), 403
        return "Forbidden", 403

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 Not Found errors"""
        app.logger.info(f"404 Not Found: {request.url} from {request.remote_addr}")
        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Not Found',
                'message': 'The requested resource was not found',
                'status_code': 404
            }), 404
        return "Not Found", 404

    @app.errorhandler(405)
    def method_not_allowed_error(error):
        """Handle 405 Method Not Allowed errors"""
        app.logger.warning(f"Method not allowed: {request.method} {request.url} from {request.remote_addr}")
        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Method Not Allowed',
                'message': f'The {request.method} method is not allowed for this endpoint',
                'status_code': 405
            }), 405
        return "Method Not Allowed", 405

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server Error"""
        from app.utils.validators import sanitize_request_data

        error_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        app.logger.error(f"Internal Server Error [{error_id}]: {str(error)}")
        app.logger.error(f"Traceback [{error_id}]: {traceback.format_exc()}")

        # Log request details for debugging (SANITIZED to prevent credential leakage)
        app.logger.error(f"Request details [{error_id}]: {request.method} {request.url}")
        request_data = sanitize_request_data(request.get_data(as_text=True)[:1000])
        app.logger.error(f"Request data [{error_id}]: {request_data}")

        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred',
                'error_id': error_id,
                'status_code': 500
            }), 500
        return f"Internal Server Error (ID: {error_id})", 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle any unexpected errors"""
        from app.utils.validators import sanitize_request_data

        error_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        app.logger.critical(f"Unexpected error [{error_id}]: {str(error)}")
        app.logger.critical(f"Traceback [{error_id}]: {traceback.format_exc()}")

        # Log sanitized request data for security
        request_data = sanitize_request_data(request.get_data(as_text=True)[:1000])
        app.logger.critical(f"Request data [{error_id}]: {request_data}")

        if request.is_json or request.content_type == 'application/json':
            return jsonify({
                'error': 'Unexpected Error',
                'message': 'An unexpected error occurred',
                'error_id': error_id,
                'status_code': 500
            }), 500
        return f"Unexpected Error (ID: {error_id})", 500


def log_sync_operation(operation_type, details=None):
    """Log synchronization operations"""
    logger = logging.getLogger('sync')
    timestamp = datetime.utcnow().isoformat()

    log_message = f"SYNC [{operation_type}] at {timestamp}"
    if details:
        log_message += f" - {details}"

    logger.info(log_message)


def handle_sync_error(operation, error, context=None):
    """Centralized sync error handling"""
    logger = logging.getLogger('sync')
    error_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')

    log_message = f"SYNC ERROR [{error_id}] in {operation}: {str(error)}"
    if context:
        log_message += f" | Context: {context}"

    logger.error(log_message)
    logger.debug(f"SYNC ERROR TRACEBACK [{error_id}]: {traceback.format_exc()}")

    return {
        'error_id': error_id,
        'operation': operation,
        'error_message': str(error),
        'timestamp': datetime.utcnow().isoformat()
    }


def requires_sync_enabled(f):
    """Decorator to check if sync is enabled before executing sync operations"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.config.get('SYNC_ENABLED'):
            current_app.logger.warning(f"Sync operation {f.__name__} attempted but sync is disabled")
            return jsonify({
                'error': 'Sync Disabled',
                'message': 'Synchronization is disabled in configuration',
                'status_code': 400
            }), 400
        return f(*args, **kwargs)
    return decorated_function


def api_error_handler(f):
    """Decorator for API endpoints to handle errors consistently"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            error_details = handle_sync_error(f.__name__, e, {
                'args': args,
                'kwargs': kwargs,
                'request_url': request.url if request else 'N/A'
            })

            current_app.logger.error(f"API Error in {f.__name__}: {str(e)}")

            return jsonify({
                'error': 'Operation Failed',
                'message': str(e),
                'error_id': error_details['error_id'],
                'status_code': 500
            }), 500
    return decorated_function


class SyncLogger:
    """Specialized logger for sync operations"""

    def __init__(self, name='sync'):
        self.logger = logging.getLogger(name)

    def sync_started(self, operation, details=None):
        """Log sync operation start"""
        message = f"Started: {operation}"
        if details:
            message += f" | {details}"
        self.logger.info(message)

    def sync_completed(self, operation, stats=None):
        """Log sync operation completion"""
        message = f"Completed: {operation}"
        if stats:
            message += f" | Stats: {stats}"
        self.logger.info(message)

    def sync_failed(self, operation, error, context=None):
        """Log sync operation failure"""
        error_details = handle_sync_error(operation, error, context)
        return error_details['error_id']

    def sync_warning(self, operation, message):
        """Log sync warnings"""
        self.logger.warning(f"{operation}: {message}")


# Global sync logger instance
sync_logger = SyncLogger()