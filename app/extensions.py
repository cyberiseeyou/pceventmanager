"""
Flask extensions initialization.

This module initializes all Flask extensions used in the application.
Extensions are initialized here without binding to the app, then bound
in the application factory using init_app() pattern.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize extensions
# These will be bound to the app in create_app() using init_app()
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",  # TODO: Use Redis in production for distributed rate limiting
    strategy="fixed-window"  # Count requests in fixed time windows
)
