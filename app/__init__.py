"""
Flask application factory.

This module implements the application factory pattern for creating
Flask application instances with different configurations.
"""

from flask import Flask, render_template, abort, jsonify, request, redirect, url_for, flash, make_response
from flask_wtf.csrf import generate_csrf
import os
import logging
from datetime import datetime, time, date, timedelta

from .extensions import db, migrate, csrf, limiter
from .config import get_config


def create_app(config_name=None):
    """
    Application factory function.

    Args:
        config_name: Configuration name (development, testing, production)
                    If None, determined from environment

    Returns:
        Flask application instance
    """
    # Create Flask app
    app = Flask(__name__)

    # Apply ProxyFix for correct IP and scheme handling behind reverse proxies (Nginx/Cloudflare)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Load configuration
    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Set dynamic version for cache busting (updates on each server restart)
    app.config['VERSION'] = datetime.now().strftime('%Y%m%d%H%M%S')

    # Ensure instance directory exists
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)

    # Update database URI to use absolute path
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///instance/'):
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "instance", "scheduler.db")}'

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Initialize rate limiter
    limiter.init_app(app)
    limiter._default_limits = [app.config.get('RATELIMIT_DEFAULT', '100 per hour')]
    limiter._enabled = app.config.get('RATELIMIT_ENABLED', True)

    # Store limiter in app config for access in blueprints
    app.config['limiter'] = limiter

    # Initialize external API services
    from app.integrations.external_api.session_api_service import session_api as external_api
    from app.integrations.external_api.sync_engine import sync_engine
    external_api.init_app(app)
    sync_engine.init_app(app, db)
    app.config['SESSION_API_SERVICE'] = external_api

    # Enable foreign key constraints for SQLite
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """Enable foreign key constraints for SQLite connections"""
        if 'sqlite' in str(dbapi_conn):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # Configure logging and error handling
    from app.error_handlers import setup_logging, register_error_handlers
    setup_logging(app)
    register_error_handlers(app)

    # Initialize database models
    from app.models import init_models, model_registry
    models = init_models(db)

    # Initialize model registry
    model_registry.init_app(app)
    model_registry.register(models)

    # Extract commonly used models for convenience
    Employee = models['Employee']
    Event = models['Event']
    Schedule = models['Schedule']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
    EmployeeAvailability = models['EmployeeAvailability']
    EmployeeTimeOff = models['EmployeeTimeOff']
    RotationAssignment = models['RotationAssignment']
    PendingSchedule = models['PendingSchedule']
    SchedulerRunHistory = models['SchedulerRunHistory']
    ScheduleException = models['ScheduleException']
    SystemSetting = models['SystemSetting']
    EmployeeAttendance = models['EmployeeAttendance']
    PaperworkTemplate = models['PaperworkTemplate']
    UserSession = models['UserSession']
    CompanyHoliday = models['CompanyHoliday']

    # Extract audit models (if available)
    AuditLog = models.get('AuditLog')
    AuditNotificationSettings = models.get('AuditNotificationSettings')

    # DEPRECATED: Models in app.config - kept for backward compatibility during transition
    # NEW: Use model_registry or get_models() instead (see models/registry.py)
    # TODO: Remove these after all blueprints are updated to use model_registry
    app.config['Employee'] = Employee
    app.config['Event'] = Event
    app.config['Schedule'] = Schedule
    app.config['EmployeeWeeklyAvailability'] = EmployeeWeeklyAvailability
    app.config['EmployeeAvailability'] = EmployeeAvailability
    app.config['EmployeeTimeOff'] = EmployeeTimeOff
    app.config['RotationAssignment'] = RotationAssignment
    app.config['PendingSchedule'] = PendingSchedule
    app.config['SchedulerRunHistory'] = SchedulerRunHistory
    app.config['ScheduleException'] = ScheduleException
    app.config['SystemSetting'] = SystemSetting
    app.config['AuditLog'] = AuditLog
    app.config['AuditNotificationSettings'] = AuditNotificationSettings
    app.config['EmployeeAttendance'] = EmployeeAttendance
    app.config['PaperworkTemplate'] = PaperworkTemplate
    app.config['UserSession'] = UserSession
    app.config['CompanyHoliday'] = CompanyHoliday

    # Register blueprints
    register_blueprints(app, db, models)

    # Setup background tasks
    setup_background_tasks(app)

    # Setup request/response handlers
    setup_request_handlers(app)

    return app


def register_blueprints(app, db, models):
    """Register all Flask blueprints."""

    # Import authentication helpers and blueprint
    from app.routes import (
        auth_bp,
        is_authenticated,
        get_current_user,
        require_authentication
    )

    # Register blueprints
    app.register_blueprint(auth_bp)

    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    from app.routes.scheduling import scheduling_bp
    app.register_blueprint(scheduling_bp)

    from app.routes.employees import employees_bp
    app.register_blueprint(employees_bp)

    from app.routes.api import api_bp
    app.register_blueprint(api_bp)

    from app.routes.ai_routes import ai_bp
    app.register_blueprint(ai_bp)

    # AI RAG blueprint (local Ollama-based AI)
    from app.ai.routes import ai_rag_bp
    app.register_blueprint(ai_rag_bp)

    from app.routes.rotations import rotations_bp
    app.register_blueprint(rotations_bp)

    from app.routes.auto_scheduler import auto_scheduler_bp
    app.register_blueprint(auto_scheduler_bp)

    # Exempt auto_scheduler from rate limiting - it makes many API calls during scheduling
    limiter.exempt(auto_scheduler_bp)

    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    from app.routes.printing import printing_bp
    app.register_blueprint(printing_bp)

    from app.integrations.walmart_api import walmart_bp
    app.register_blueprint(walmart_bp)

    from app.routes.edr_sync import edr_sync_bp
    app.register_blueprint(edr_sync_bp)

    from app.routes.help import help_bp
    app.register_blueprint(help_bp)

    from app.routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from app.routes.health import health_bp
    app.register_blueprint(health_bp)

    from app.routes.api_attendance import init_attendance_routes
    attendance_api_bp = init_attendance_routes(db, models)
    app.register_blueprint(attendance_api_bp)

    from app.routes.api_notifications import init_notification_routes
    notifications_api_bp = init_notification_routes(db, models)
    app.register_blueprint(notifications_api_bp)

    from app.routes.api_paperwork_templates import api_paperwork_templates_bp
    app.register_blueprint(api_paperwork_templates_bp)

    from app.routes.api_company_holidays import api_company_holidays_bp
    app.register_blueprint(api_company_holidays_bp)

    # Configure CSRF exemptions for specific routes (after blueprint registration)
    if 'auth.login' in app.view_functions:
        csrf.exempt(app.view_functions['auth.login'])

    if 'admin.webhook_schedule_update' in app.view_functions:
        csrf.exempt(app.view_functions['admin.webhook_schedule_update'])

    # Session heartbeat doesn't need CSRF - it only updates last_activity timestamp
    if 'auth.session_heartbeat' in app.view_functions:
        csrf.exempt(app.view_functions['auth.session_heartbeat'])


def setup_background_tasks(app):
    """Setup background tasks and schedulers."""

    from app.integrations.walmart_api import session_manager
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    import atexit

    def cleanup_walmart_sessions():
        """Background task to cleanup expired Walmart sessions."""
        with app.app_context():
            session_manager.cleanup_expired_sessions()

    # Create and start background scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=cleanup_walmart_sessions,
        trigger=IntervalTrigger(seconds=60),
        id='walmart_session_cleanup',
        name='Cleanup expired Walmart sessions',
        replace_existing=True
    )
    scheduler.start()

    # Ensure scheduler shuts down when app exits
    atexit.register(lambda: scheduler.shutdown())


def setup_request_handlers(app):
    """Setup request and response handlers."""

    from app.routes import get_current_user

    @app.context_processor
    def inject_user():
        """Make get_current_user available in templates"""
        return dict(get_current_user=get_current_user)

    @app.after_request
    def add_csrf_token_cookie(response):
        """
        Add CSRF token to cookie for AJAX requests.

        This allows JavaScript to read the token and include it in AJAX request headers.
        The token is validated on the server side for all POST/PUT/DELETE requests.
        """
        if request.endpoint and not request.endpoint.startswith('static'):
            # Generate and set CSRF token in cookie
            csrf_token = generate_csrf()
            response.set_cookie(
                'csrf_token',
                csrf_token,
                secure=app.config.get('SESSION_COOKIE_SECURE', False),
                httponly=False,
                samesite='Lax'
            )
        return response


def init_db(app):
    """Initialize the database."""
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    db_path = os.path.join(basedir, "instance", "scheduler.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with app.app_context():
        db.create_all()
