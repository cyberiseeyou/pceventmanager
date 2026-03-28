"""
Authentication routes blueprint
Handles user login, logout, and session management
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, Response, stream_with_context
from functools import wraps
from datetime import datetime, timedelta
import secrets
import redis
import json
import os
import time

import urllib.parse

# Create blueprint
auth_bp = Blueprint('auth', __name__)

# Redis Connection (Lazy loading pattern)
_redis_client = None

def get_redis_client():
    """Get or create Redis client"""
    global _redis_client
    if _redis_client is None:
        redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        # Handle case where REDIS_PASSWORD is set but not in URL
        redis_password = current_app.config.get('REDIS_PASSWORD')
        if redis_password and '@' not in redis_url:
            # Inject password into URL if needed (URL encoded)
            parts = redis_url.split('://')
            if len(parts) == 2:
                encoded_password = urllib.parse.quote_plus(redis_password)
                redis_url = f"{parts[0]}://:{encoded_password}@{parts[1]}"
        
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client

def get_session(session_id):
    """Retrieve session data from Redis"""
    if not session_id:
        return None
    try:
        client = get_redis_client()
        data = client.get(f"session:{session_id}")
        if data:
            return json.loads(data)
    except Exception as e:
        current_app.logger.error(f"Redis session read error: {e}")
    return None

def save_session(session_id, data, ttl_seconds=86400):
    """Save session data to Redis"""
    try:
        client = get_redis_client()
        # Ensure datetimes are serializable
        if 'created_at' in data and isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
            
        client.setex(
            f"session:{session_id}",
            ttl_seconds,
            json.dumps(data)
        )
    except Exception as e:
        current_app.logger.error(f"Redis session write error: {e}")

def delete_session(session_id):
    """Delete session from Redis"""
    if not session_id:
        return
    try:
        client = get_redis_client()
        client.delete(f"session:{session_id}")
    except Exception as e:
        current_app.logger.error(f"Redis session delete error: {e}")


def get_inactivity_timeout():
    """Get session inactivity timeout from config (in seconds)"""
    # Default: 600 seconds (10 minutes)
    return current_app.config.get('SESSION_INACTIVITY_TIMEOUT', 600)


# Roles that stay logged in indefinitely (no inactivity timeout, no 24h expiry)
PERSISTENT_SESSION_ROLES = ('lead', 'specialist')
PERSISTENT_SESSION_TTL = 2592000  # 30 days in seconds


def _is_persistent_session(session_data):
    """Check if session belongs to a role that should never auto-expire."""
    user_info = session_data.get('user_info', {})
    return user_info.get('role') in PERSISTENT_SESSION_ROLES


def update_session_activity(session_id):
    """
    Update last_activity timestamp for a session.
    Called by heartbeat endpoint when user is active.
    """
    if not session_id:
        return False
    
    session_data = get_session(session_id)
    if not session_data:
        return False
    
    session_data['last_activity'] = datetime.utcnow().isoformat()
    save_session(session_id, session_data)
    return True

def is_authenticated():
    """Check if user is authenticated"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return False

    session_data = get_session(session_id)
    if not session_data:
        return False

    # Leads and specialists stay logged in indefinitely — skip timeout checks
    if _is_persistent_session(session_data):
        return True

    # Check expiration (handled by Redis TTL mostly, but logic kept for safety)
    try:
        created_at_str = session_data.get('created_at')
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str)
            if datetime.utcnow() - created_at > timedelta(hours=24):
                delete_session(session_id)
                return False
    except Exception:
        pass # Ignore parsing errors, trust Redis TTL

    # Check inactivity timeout
    try:
        last_activity_str = session_data.get('last_activity')
        if last_activity_str:
            last_activity = datetime.fromisoformat(last_activity_str)
            inactivity_timeout = get_inactivity_timeout()
            if (datetime.utcnow() - last_activity).total_seconds() > inactivity_timeout:
                current_app.logger.info(f"Session {session_id[:8]}... expired due to inactivity")
                delete_session(session_id)
                return False
    except Exception as e:
        current_app.logger.error(f"Error checking inactivity timeout: {e}")

    return True


def get_current_user():
    """Get current authenticated user info"""
    session_id = request.cookies.get('session_id')
    session_data = get_session(session_id)
    if session_data:
        return session_data.get('user_info')
    return None


def require_authentication():
    """Decorator to require authentication for routes"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not is_authenticated():
                return redirect(url_for('auth.login_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_role(*allowed_roles):
    """
    Decorator to require specific roles for route access.
    Must be used AFTER @require_authentication().

    Usage:
        @require_authentication()
        @require_role('supervisor')
        def admin_view(): ...

        @require_authentication()
        @require_role('supervisor', 'lead')
        def lead_view(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for('auth.login_page'))
            user_role = user.get('role', 'supervisor')  # Default to supervisor for legacy sessions
            if user_role not in allowed_roles:
                from flask import abort
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@auth_bp.route('/login')
def login_page():
    """Display login page.

    Always shows the login form regardless of existing session.
    On shared devices, auto-redirecting an authenticated session would let
    anyone bypass authentication by simply visiting this URL.
    """
    return render_template('login.html')


@auth_bp.route('/login', methods=['POST'])
# Note: CSRF exemption applied in app.py - cannot have token before authentication session exists
def login():
    """
    Handle login form submission and authenticate with Crossmark API

    Rate Limit: 5 attempts per minute to prevent brute force attacks
    """
    from app.integrations.external_api.session_api_service import session_api as external_api

    # Apply strict rate limiting to login endpoint (5 per minute)
    # Note: Using dynamic application pattern to avoid circular imports with app.py
    # The limiter is accessed from app config and applied at runtime
    limiter = current_app.config.get('limiter')
    if limiter:
        # Apply rate limit check by decorating a lambda and immediately calling it
        # This triggers the rate limit check without needing to decorate the route function
        limiter.limit("5 per minute")(lambda: None)()

    try:
        # Debug logging
        current_app.logger.info(f"Login attempt - Content-Type: {request.content_type}")
        current_app.logger.info(f"Login attempt - Form data: {request.form}")
        current_app.logger.info(f"Login attempt - Raw data: {request.get_data(as_text=True)[:200]}")

        # Get credentials from form
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember') == 'on'

        # Validate input
        if not username or not password:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': 'Username and password are required'
                }), 400
            else:
                flash('Username and password are required', 'error')
                return redirect(url_for('auth.login_page'))

        # Temporarily configure external API with user credentials
        original_username = external_api.username
        original_password = external_api.password
        auth_success = False  # Initialize auth_success outside try block

        # CRITICAL: Clear any previous session state on the singleton before
        # attempting fresh authentication.  Without this, the requests.Session
        # may send the previous user's PHPSESSID cookie, and the Crossmark API
        # may accept it — allowing anyone to authenticate as the prior user.
        external_api.authenticated = False
        external_api.phpsessid = None
        external_api.user_info = None
        if external_api.session:
            external_api.session.cookies.clear()

        external_api.username = username
        external_api.password = password

        try:
            # Attempt authentication with Crossmark API
            current_app.logger.info(f"Attempting authentication for user: {username}")

            auth_success = external_api.login()

            if auth_success:
                # Get user information
                user_info = external_api._get_user_info()
                if not user_info:
                    user_info = {
                        'username': username,
                        'userId': username,
                        'authenticated': True
                    }

                # Extract first and last name from API response or parse from username
                first_name = user_info.get('firstName') or user_info.get('first_name')
                last_name = user_info.get('lastName') or user_info.get('last_name')

                # Fallback: try to parse from 'name' field if exists
                if not (first_name and last_name) and 'name' in user_info:
                    name_parts = user_info['name'].split(' ', 1)
                    if len(name_parts) == 2:
                        first_name, last_name = name_parts
                    elif len(name_parts) == 1:
                        first_name = name_parts[0]
                        last_name = ''

                # Fallback: parse from username if still not found
                if not (first_name and last_name):
                    # Try to parse "firstname.lastname" or "firstname lastname" format
                    username_parts = username.replace('.', ' ').split(' ', 1)
                    if len(username_parts) >= 1:
                        first_name = username_parts[0].capitalize()
                    if len(username_parts) >= 2:
                        last_name = username_parts[1].capitalize()
                    else:
                        last_name = ''

                # Add name fields to user_info
                user_info['first_name'] = first_name or 'User'
                user_info['last_name'] = last_name or ''
                user_info['full_name'] = f"{first_name} {last_name}".strip() if (first_name and last_name) else (first_name or username)

                # Determine role from Employee record if it exists
                user_info['role'] = 'supervisor'  # Default for Crossmark users
                try:
                    from app.models.registry import get_models
                    models = get_models()
                    Employee = models['Employee']
                    # Try to match by name or crossmark ID
                    emp = Employee.query.filter(
                        db.or_(
                            Employee.crossmark_employee_id == username,
                            db.func.lower(Employee.name) == user_info.get('full_name', '').lower()
                        )
                    ).first() if hasattr(db, 'or_') else None
                    if emp:
                        user_info['role'] = emp.role
                        user_info['employee_id'] = emp.id
                        user_info['job_title'] = emp.job_title
                except Exception:
                    pass  # Default to supervisor if lookup fails

                # Destroy any existing session to prevent session leakage on shared devices
                old_session_id = request.cookies.get('session_id')
                if old_session_id:
                    delete_session(old_session_id)

                # Create session
                session_id = secrets.token_urlsafe(32)
                session_data = {
                    'user_id': username,
                    'user_info': user_info,
                    'created_at': datetime.utcnow().isoformat(), # Store as ISO string
                    'last_activity': datetime.utcnow().isoformat(),  # Track last activity for timeout
                    'crossmark_authenticated': True,
                    'phpsessid': external_api.phpsessid
                }
                
                # Check if event time settings are configured
                event_times_configured = True
                missing_settings = []
                try:
                    from app.services.event_time_settings import are_event_times_configured
                    event_times_configured, missing_settings = are_event_times_configured()
                except Exception as e:
                    current_app.logger.error(f"Error checking event time settings: {e}")

                # Add event times configuration status to session
                session_data['event_times_configured'] = event_times_configured
                
                # Save to Redis — persistent TTL for leads/specialists
                persistent = _is_persistent_session(session_data)
                session_ttl = PERSISTENT_SESSION_TTL if persistent else 86400
                save_session(session_id, session_data, ttl_seconds=session_ttl)

                current_app.logger.info(f"Successful authentication for user: {username}")

                # Create response - redirect to loading page for database sync
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    response = jsonify({
                        'success': True,
                        'redirect': url_for('auth.loading_page'),
                        'user': user_info,
                        'event_times_configured': event_times_configured
                    })
                else:
                    response = redirect(url_for('auth.loading_page'))

                # Set session cookie — 30 days for leads/specialists, 24h for others
                cookie_max_age = PERSISTENT_SESSION_TTL if persistent else (86400 if remember_me else None)
                response.set_cookie(
                    'session_id',
                    session_id,
                    max_age=cookie_max_age,
                    httponly=True,
                    secure=request.is_secure,
                    samesite='Lax'
                )

                return response

            else:
                current_app.logger.warning(f"Authentication failed for user: {username}")
                error_message = 'Invalid username or password. Please check your Crossmark credentials.'

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'error': error_message
                    })
                else:
                    flash(error_message, 'error')
                    return redirect(url_for('auth.login_page'))

        finally:
            # Only restore original credentials if authentication failed
            # If auth was successful, keep the new credentials for API calls
            if not auth_success:
                external_api.username = original_username
                external_api.password = original_password

    except Exception as e:
        current_app.logger.error(f"Login error for user {username}: {str(e)}")
        error_message = 'An error occurred during login. Please try again.'

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': error_message
            })
        else:
            flash(error_message, 'error')
            return redirect(url_for('auth.login_page'))


@auth_bp.route('/employee-login')
def employee_login_page():
    """Display employee self-service login page.

    Always shows the login form regardless of existing session.
    On shared devices, auto-redirecting an authenticated session would let
    anyone bypass authentication by simply visiting this URL.
    """
    return render_template('auth/employee_login.html')


@auth_bp.route('/employee-login', methods=['POST'])
def employee_login():
    """Authenticate employee via Employee ID + PIN"""
    from app.models.registry import get_models, get_db

    employee_id_input = request.form.get('employee_id', '').strip()
    pin = request.form.get('pin', '').strip()

    if not employee_id_input or not pin:
        flash('Employee ID and PIN are required', 'error')
        return redirect(url_for('auth.employee_login_page'))

    # Prepend "US" prefix if user entered just the numeric portion
    if employee_id_input.upper().startswith('US'):
        employee_id = employee_id_input.upper()
    else:
        employee_id = f'US{employee_id_input}'

    models = get_models()
    Employee = models['Employee']
    employee = Employee.query.get(employee_id)

    if not employee or not employee.has_account or not employee.check_pin(pin):
        flash('Invalid credentials. Check your Employee ID and PIN.', 'error')
        return redirect(url_for('auth.employee_login_page'))

    if not employee.is_active:
        flash('Your account has been deactivated. Contact your supervisor.', 'error')
        return redirect(url_for('auth.employee_login_page'))

    # Destroy any existing session to prevent session leakage on shared devices
    old_session_id = request.cookies.get('session_id')
    if old_session_id:
        delete_session(old_session_id)

    # Create session with role
    session_id = secrets.token_urlsafe(32)
    name_parts = employee.name.split(' ', 1)
    first_name = name_parts[0] if name_parts else employee.name
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    session_data = {
        'user_id': f'emp_{employee.id}',
        'user_info': {
            'username': employee.name,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': employee.name,
            'role': employee.role,
            'employee_id': employee.id,
            'job_title': employee.job_title,
            'authenticated': True
        },
        'created_at': datetime.utcnow().isoformat(),
        'last_activity': datetime.utcnow().isoformat(),
        'pin_authenticated': True,
        'event_times_configured': True  # Employees don't need to configure this
    }

    # Leads and specialists get persistent sessions (30 days); supervisors get 24h
    persistent = employee.role in PERSISTENT_SESSION_ROLES
    session_ttl = PERSISTENT_SESSION_TTL if persistent else 86400
    save_session(session_id, session_data, ttl_seconds=session_ttl)

    # Specialists and leads land on their personal dashboard; supervisors get the daily view
    if employee.role in ('specialist', 'lead'):
        response = redirect(url_for('main.my_dashboard'))
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        response = redirect(url_for('main.daily_schedule_view', date=today))

    response.set_cookie(
        'session_id', session_id,
        max_age=session_ttl, httponly=True,
        secure=request.is_secure, samesite='Lax'
    )
    return response


@auth_bp.route('/api/employee/set-pin', methods=['POST'])
@require_authentication()
def set_employee_pin():
    """Supervisor sets a PIN for an employee (enables their self-service login)"""
    user = get_current_user()
    if not user or user.get('role', 'supervisor') not in ('supervisor',):
        return jsonify({'success': False, 'error': 'Supervisor access required'}), 403

    from app.models.registry import get_models, get_db

    data = request.get_json()
    employee_id = data.get('employee_id')
    pin = data.get('pin', '').strip()

    if not employee_id or not pin:
        return jsonify({'success': False, 'error': 'Employee ID and PIN required'}), 400

    if len(pin) < 4:
        return jsonify({'success': False, 'error': 'PIN must be at least 4 characters'}), 400

    models = get_models()
    db = get_db()
    Employee = models['Employee']
    employee = Employee.query.get(employee_id)

    if not employee:
        return jsonify({'success': False, 'error': 'Employee not found'}), 404

    employee.set_pin(pin)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'PIN set for {employee.name}. They can now log in at /employee-login.'
    })


@auth_bp.route('/api/employee/revoke-access', methods=['POST'])
@require_authentication()
def revoke_employee_access():
    """Supervisor revokes an employee's login access (clears PIN and disables account)"""
    user = get_current_user()
    if not user or user.get('role', 'supervisor') not in ('supervisor',):
        return jsonify({'success': False, 'error': 'Supervisor access required'}), 403

    from app.models.registry import get_models, get_db

    data = request.get_json()
    employee_id = data.get('employee_id')

    if not employee_id:
        return jsonify({'success': False, 'error': 'Employee ID required'}), 400

    models = get_models()
    db = get_db()
    Employee = models['Employee']
    employee = Employee.query.get(employee_id)

    if not employee:
        return jsonify({'success': False, 'error': 'Employee not found'}), 404

    employee.pin_hash = None
    employee.has_account = False
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Login access revoked for {employee.name}.'
    })


@auth_bp.route('/api/session-info')
def session_info():
    """Get session information including event times configuration status"""
    session_id = request.cookies.get('session_id')
    
    session_data = get_session(session_id)

    if not session_data:
        return jsonify({
            'success': False,
            'message': 'Not authenticated'
        }), 401

    event_times_configured = session_data.get('event_times_configured', True)

    return jsonify({
        'success': True,
        'event_times_configured': event_times_configured,
        'user': session_data.get('user_info', {})
    })


@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    from app.integrations.external_api.session_api_service import session_api as external_api
    from app.models import get_models, get_db

    session_id = request.cookies.get('session_id')

    if session_id:
        # Read session before deleting to get employee_id for push cleanup
        session_data = get_session(session_id)
        if session_data:
            employee_id = session_data.get('employee_id')
            if employee_id:
                # Deactivate push subscriptions so this device stops receiving notifications
                try:
                    models = get_models()
                    db = get_db()
                    PushSubscription = models.get('PushSubscription')
                    if PushSubscription:
                        PushSubscription.query.filter_by(
                            employee_id=employee_id, is_active=True
                        ).update({'is_active': False})
                        db.session.commit()
                        current_app.logger.info(f"Deactivated push subscriptions for employee {employee_id} on logout")
                except Exception as e:
                    current_app.logger.error(f"Error deactivating push subscriptions on logout: {e}")

        delete_session(session_id)
        current_app.logger.info("User logged out successfully")

    # Clear external API session if authenticated
    if external_api.authenticated:
        external_api.logout()

    response = redirect(url_for('auth.login_page'))
    response.set_cookie('session_id', '', expires=0)
    flash('You have been logged out successfully', 'info')

    return response


@auth_bp.route('/api/auth/diag')
def auth_diag():
    """Diagnostic endpoint to check Redis connection"""
    status = {
        'redis': 'unknown',
        'env_redis_url_set': bool(current_app.config.get('REDIS_URL')),
        'env_redis_password_set': bool(current_app.config.get('REDIS_PASSWORD')),
        'error': None
    }
    
    try:
        client = get_redis_client()
        client.ping()
        status['redis'] = 'connected'
    except Exception as e:
        status['redis'] = 'failed'
        status['error'] = str(e)
        
    return jsonify(status)

@auth_bp.route('/api/auth/status')
def auth_status():
    """Check authentication status and return timeout info"""
    session_id = request.cookies.get('session_id')
    session_data = get_session(session_id) if session_id else None
    
    if is_authenticated() and session_data:
        user_info = get_current_user()

        # Leads and specialists have no inactivity timeout
        if _is_persistent_session(session_data):
            return jsonify({
                'authenticated': True,
                'user': user_info,
                'no_inactivity_timeout': True
            })

        # Calculate seconds until timeout
        inactivity_timeout = get_inactivity_timeout()
        seconds_remaining = inactivity_timeout

        last_activity_str = session_data.get('last_activity')
        if last_activity_str:
            try:
                last_activity = datetime.fromisoformat(last_activity_str)
                elapsed = (datetime.utcnow() - last_activity).total_seconds()
                seconds_remaining = max(0, inactivity_timeout - elapsed)
            except Exception:
                pass

        return jsonify({
            'authenticated': True,
            'user': user_info,
            'inactivity_timeout': inactivity_timeout,
            'seconds_remaining': int(seconds_remaining)
        })
    else:
        return jsonify({
            'authenticated': False
        }), 401


@auth_bp.route('/api/session/heartbeat', methods=['POST'])
def session_heartbeat():
    """
    Update session activity timestamp.
    Called by frontend when user is actively using the application.
    """
    session_id = request.cookies.get('session_id')

    if not session_id:
        return jsonify({'success': False, 'error': 'No session'}), 401

    if update_session_activity(session_id):
        # Refresh Redis TTL for persistent sessions so they don't expire after 30 days of active use
        session_data = get_session(session_id)
        if session_data and _is_persistent_session(session_data):
            save_session(session_id, session_data, ttl_seconds=PERSISTENT_SESSION_TTL)
            return jsonify({
                'success': True,
                'message': 'Session activity updated',
                'no_inactivity_timeout': True
            })

        inactivity_timeout = get_inactivity_timeout()
        return jsonify({
            'success': True,
            'message': 'Session activity updated',
            'inactivity_timeout': inactivity_timeout
        })
    else:
        return jsonify({'success': False, 'error': 'Session not found'}), 401


# =============================================================================
# Database Refresh Progress Tracking
# =============================================================================

REFRESH_PROGRESS_PREFIX = "db_refresh_progress:"
REFRESH_PROGRESS_TTL = 300  # 5 minutes


def save_refresh_progress(task_id, progress_data):
    """Save refresh progress state to Redis"""
    try:
        client = get_redis_client()
        client.setex(
            f"{REFRESH_PROGRESS_PREFIX}{task_id}",
            REFRESH_PROGRESS_TTL,
            json.dumps(progress_data)
        )
    except Exception as e:
        current_app.logger.error(f"Redis progress write error: {e}")


def get_refresh_progress(task_id):
    """Get refresh progress state from Redis"""
    try:
        client = get_redis_client()
        data = client.get(f"{REFRESH_PROGRESS_PREFIX}{task_id}")
        return json.loads(data) if data else None
    except Exception as e:
        current_app.logger.error(f"Redis progress read error: {e}")
        return None


def update_refresh_progress(task_id, **kwargs):
    """Update specific refresh progress fields"""
    progress = get_refresh_progress(task_id) or {
        'status': 'pending',
        'current_step': 0,
        'total_steps': 5,
        'step_label': 'Initializing...',
        'processed': 0,
        'total': 0,
        'error': None,
        'stats': None
    }
    progress.update(kwargs)
    save_refresh_progress(task_id, progress)


def delete_refresh_progress(task_id):
    """Delete refresh progress from Redis"""
    try:
        client = get_redis_client()
        client.delete(f"{REFRESH_PROGRESS_PREFIX}{task_id}")
    except Exception as e:
        current_app.logger.error(f"Redis progress delete error: {e}")


# =============================================================================
# Loading Page Routes
# =============================================================================

@auth_bp.route('/loading')
@require_authentication()
def loading_page():
    """Display the database refresh loading page"""
    # Generate unique task ID for this refresh operation
    task_id = secrets.token_urlsafe(16)

    # Initialize progress state in Redis
    progress_data = {
        'status': 'pending',
        'current_step': 0,
        'total_steps': 5,
        'step_label': 'Initializing...',
        'processed': 0,
        'total': 0,
        'error': None,
        'stats': None
    }
    save_refresh_progress(task_id, progress_data)

    # Redirect after completion: leads/specialists go to my-dashboard, supervisors to daily view
    user = get_current_user()
    user_role = user.get('role') if user else None

    if user_role in ('specialist', 'lead'):
        redirect_url = url_for('main.my_dashboard')
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        redirect_url = url_for('main.daily_schedule_view', date=today)

    return render_template(
        'auth/loading.html',
        task_id=task_id,
        redirect_url=redirect_url
    )


@auth_bp.route('/loading/progress/<task_id>')
@require_authentication()
def loading_progress(task_id):
    """Stream database refresh progress via Server-Sent Events"""

    def generate():
        max_iterations = 3000  # Max 5 minutes (3000 * 0.1s)
        iteration = 0

        while iteration < max_iterations:
            progress = get_refresh_progress(task_id)

            if not progress:
                yield f"data: {json.dumps({'error': 'Task not found', 'status': 'error'})}\n\n"
                break

            yield f"data: {json.dumps(progress)}\n\n"

            if progress.get('status') in ('completed', 'error'):
                break

            time.sleep(0.1)  # 100ms delay - 5x faster updates
            iteration += 1

        # Cleanup progress data after completion
        if progress and progress.get('status') == 'completed':
            delete_refresh_progress(task_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@auth_bp.route('/loading/start/<task_id>', methods=['POST'])
@require_authentication()
def start_loading_refresh(task_id):
    """Start the database refresh process with progress tracking"""
    try:
        # Verify task exists
        progress = get_refresh_progress(task_id)
        if not progress:
            return jsonify({'success': False, 'error': 'Invalid task ID'}), 400

        # Check if already running
        if progress.get('status') == 'running':
            return jsonify({'success': False, 'error': 'Refresh already in progress'}), 400

        # Import and run the refresh service IN BACKGROUND THREAD
        # This prevents blocking the single gunicorn worker, allowing SSE to work
        import threading
        from app.services.database_refresh_service import refresh_database_with_progress

        # CRITICAL: Capture the actual Flask app BEFORE starting the thread
        # current_app is a proxy that doesn't work in background threads
        app = current_app._get_current_object()

        def run_refresh():
            """Run refresh in background with Flask app context"""
            with app.app_context():
                try:
                    refresh_database_with_progress(task_id)
                except Exception as e:
                    app.logger.error(f"Background refresh failed: {e}", exc_info=True)
                    update_refresh_progress(task_id, status='error', error=str(e))

        # Start background thread
        thread = threading.Thread(target=run_refresh, daemon=True)
        thread.start()

        # Return immediately so SSE endpoint can be served
        return jsonify({'success': True, 'message': 'Database refresh started'})

    except Exception as e:
        current_app.logger.error(f"Failed to start database refresh: {e}")
        update_refresh_progress(task_id, status='error', error=str(e))
        return jsonify({'success': False, 'error': str(e)}), 500
