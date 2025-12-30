"""
Validation utilities for Flask Schedule Webapp
Provides reusable validation functions and decorators for API endpoints

All functions include comprehensive type hints for better IDE support and type checking.
"""
from functools import wraps
from flask import jsonify, current_app
from datetime import datetime, date
from typing import Any, Callable, Dict, List, Optional


class ValidationError(Exception):
    """Custom validation exception with HTTP status code"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message: str = message
        self.status_code: int = status_code
        super().__init__(self.message)


def validate_date_param(date_str: str, param_name: str = 'date') -> date:
    """
    Validate and parse date parameter from string.

    Args:
        date_str: Date string in YYYY-MM-DD format
        param_name: Name of parameter for error messages (default: 'date')

    Returns:
        date: Parsed date object

    Raises:
        ValidationError: If date format is invalid

    Examples:
        >>> validate_date_param('2025-10-15')
        date(2025, 10, 15)
        >>> validate_date_param('invalid')
        ValidationError: Invalid date format. Use YYYY-MM-DD
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValidationError(
            f"Invalid {param_name} format. Use YYYY-MM-DD (e.g., 2025-10-15)",
            status_code=400
        )


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
    """
    Validate that all required fields are present in request data.

    Args:
        data: Request data dictionary
        required_fields: List of required field names

    Raises:
        ValidationError: If any required field is missing
    """
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing)}",
            status_code=400
        )


def handle_validation_errors(f: Callable) -> Callable:
    """
    Decorator to handle ValidationError exceptions consistently across all endpoints.

    Usage:
        @api_bp.route('/endpoint')
        @handle_validation_errors
        def my_endpoint():
            date = validate_date_param(request.args.get('date'))
            # ... rest of function

    Args:
        f: Function to decorate

    Returns:
        Decorated function that catches ValidationError
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            current_app.logger.warning(f"Validation error in {f.__name__}: {e.message}")
            return jsonify({'error': e.message}), e.status_code
    return decorated


def sanitize_request_data(data: str) -> str:
    """
    Remove sensitive data from request strings for safe logging.

    Redacts common sensitive field patterns (passwords, tokens, API keys, secrets).

    Args:
        data: Request data as string

    Returns:
        Sanitized string with sensitive data replaced with [REDACTED]

    Examples:
        >>> sanitize_request_data('{"password": "secret123"}')
        '{"password": "[REDACTED]"}'
    """
    import re

    # Redact common sensitive field patterns
    data = re.sub(r'("password"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', data, flags=re.IGNORECASE)
    data = re.sub(r'("token"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', data, flags=re.IGNORECASE)
    data = re.sub(r'("api_key"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', data, flags=re.IGNORECASE)
    data = re.sub(r'("secret"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', data, flags=re.IGNORECASE)
    data = re.sub(r'("credential"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', data, flags=re.IGNORECASE)

    return data
