"""
Routes package for Flask Schedule Webapp
Centralizes all route blueprints
"""
from .auth import (
    auth_bp,
    is_authenticated,
    get_current_user,
    require_authentication
)
from .employees import employees_bp
from .api import api_bp
from .admin import admin_bp

__all__ = [
    'auth_bp',
    'employees_bp',
    'api_bp',
    'admin_bp',
    'is_authenticated',
    'get_current_user',
    'require_authentication'
]
