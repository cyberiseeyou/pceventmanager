# Comprehensive Security Audit Report

**Application:** Flask Schedule Webapp (Crossmark Employee Scheduling System)
**Audit Date:** 2026-03-26
**Auditor:** Security Audit (Claude Code)
**Scope:** Full codebase -- 145 Python files, 51 JS files, 77 HTML templates
**Framework:** Flask 3.0.3 / SQLAlchemy / Jinja2 / PostgreSQL+SQLite / Redis / Celery

---

## Executive Summary

This audit identified **7 Critical**, **11 High**, **14 Medium**, and **8 Low** severity findings across the application. The most severe issues involve unauthenticated API endpoints exposing PII and enabling data modification, plaintext credential logging, a broken rate limiter that provides no brute-force protection, and a race-condition-prone singleton that can leak authentication state between users.

The application demonstrates some positive security practices -- Werkzeug password hashing for PINs, Redis-based session management with proper TTLs, CSRF protection via Flask-WTF, and ProxyFix for reverse-proxy awareness. However, the large number of unauthenticated endpoints and the systematic leaking of exception details represent systemic risks that need priority remediation.

**Risk Rating: HIGH** -- Multiple critical vulnerabilities are exploitable without authentication and can lead to data breach, unauthorized data modification, and credential exposure.

---

## Table of Contents

1. [Critical Findings (CVSS 9.0-10.0)](#1-critical-findings)
2. [High Findings (CVSS 7.0-8.9)](#2-high-findings)
3. [Medium Findings (CVSS 4.0-6.9)](#3-medium-findings)
4. [Low Findings (CVSS 0.1-3.9)](#4-low-findings)
5. [Informational / Best Practice](#5-informational)
6. [Dependency Analysis](#6-dependency-analysis)
7. [Remediation Priority Matrix](#7-remediation-priority-matrix)

---

## 1. Critical Findings

### CRIT-01: Mass Unauthenticated API Endpoints Exposing PII and Enabling Data Modification

**Severity:** Critical (CVSS 9.8)
**CWE:** CWE-306 (Missing Authentication for Critical Function)
**OWASP:** A01:2021 -- Broken Access Control

**Location:** `app/routes/api.py` -- 24+ route definitions without `@require_authentication()`

**Description:**
The majority of API endpoints in `api.py` lack the `@require_authentication()` decorator. Out of approximately 50 routes, only 25 are protected. The unprotected endpoints include routes that read, modify, and delete schedule data, employee data, and PII.

**Affected Unauthenticated Endpoints (partial list):**
```
GET  /api/employees/with-accounts       -- Lists employee names and IDs with accounts
GET  /api/daily-summary/<date>          -- Employee names, schedules, event details
GET  /api/daily-events/<date>           -- Full daily schedule with employee names
GET  /api/daily-employees/<date>        -- Employee names, attendance, schedule details
GET  /api/event-by-ref/<ref_num>        -- Event details lookup
POST /api/event/<id>/unschedule         -- DELETE schedule (data modification!)
POST /api/reschedule                    -- Modify schedule datetime (data modification!)
GET  /api/core_employees_for_trade/...  -- Employee names and IDs
GET  /api/available_employees_for_change/... -- Employee names, job titles, IDs
GET  /api/event-default-time/<type>     -- Event configuration
GET  /api/event-allowed-times/<type>    -- Event configuration
GET  /api/event-time-settings           -- System configuration
GET  /api/validate_schedule_for_export  -- Employee names, event data
GET  /api/schedule/<id>                 -- Schedule details with employee ID
POST /api/schedule-event                -- CREATE new schedule (data modification!)
POST /api/reschedule_event              -- Modify schedule (deprecated but active)
DELETE /api/unschedule/<id>             -- DELETE schedule (data modification!)
POST /api/unschedule_event/<id>         -- DELETE schedule (data modification!)
POST /api/change_employee               -- Modify employee assignment
GET  /api/export/schedule               -- Full schedule export with PII
GET  /api/export/events                 -- Full event export
POST /api/import/events                 -- Import data into database
POST /api/import/scheduled              -- Import scheduled data
POST /api/validate-schedule             -- Internal validation data
GET  /api/suggest-employees             -- Employee data
GET  /api/workload                      -- Employee workload data
GET  /api/employee-schedule-details     -- Employee schedule details
POST /api/fix-coverage-times/<date>     -- Modify schedule times
```

Additionally, the following blueprints also have unauthenticated endpoints:
- `health_bp` -- `/health/status` exposes debug mode, Python version, process ID, environment, memory/disk metrics
- `health_bp` -- `/health/metrics` exposes database table counts
- `api_demo_goals_bp` -- `/api/demo-goals/data` and `/api/demo-goals/download` (no auth)
- `attendance_api_bp` -- Multiple routes lack `@require_authentication()`
- `ai_rag_bp` -- `/api/ai/rag/chat` allows unauthenticated AI queries against the database

**Attack Scenario:**
1. Attacker discovers the application URL
2. Calls `GET /api/daily-events/2026-03-26` -- obtains all employee names, IDs, schedules
3. Calls `POST /api/event/123/unschedule` -- deletes a schedule record
4. Calls `POST /api/schedule-event` -- creates unauthorized schedule entries
5. Calls `GET /api/export/schedule` -- exports full PII-laden schedule as CSV

**Remediation:**
Add `@require_authentication()` to every API endpoint. For role-restricted operations (create, update, delete), add `@require_role('supervisor')` or `@require_role('supervisor', 'lead')`.

```python
# BEFORE (vulnerable)
@api_bp.route('/daily-events/<date>', methods=['GET'])
def get_daily_events(date):
    ...

# AFTER (secured)
@api_bp.route('/daily-events/<date>', methods=['GET'])
@require_authentication()
def get_daily_events(date):
    ...
```

For write operations:
```python
@api_bp.route('/schedule-event', methods=['POST'])
@require_authentication()
@require_role('supervisor')
def schedule_event():
    ...
```

---

### CRIT-02: Plaintext Credential Logging

**Severity:** Critical (CVSS 9.1)
**CWE:** CWE-532 (Insertion of Sensitive Information into Log File)
**OWASP:** A09:2021 -- Security Logging and Monitoring Failures

**Location:** `app/routes/auth.py`, lines 235-237

**Description:**
The login handler logs the entire `request.form` dictionary and raw request body at INFO level, which contains the user's plaintext password. These log entries persist in log files and may be forwarded to log aggregation systems.

```python
# auth.py:235-237 -- CRITICAL: Logs plaintext passwords
current_app.logger.info(f"Login attempt - Content-Type: {request.content_type}")
current_app.logger.info(f"Login attempt - Form data: {request.form}")
current_app.logger.info(f"Login attempt - Raw data: {request.get_data(as_text=True)[:200]}")
```

The logged output includes: `Login attempt - Form data: ImmutableMultiDict([('username', 'john.doe'), ('password', 's3cr3tP@ssw0rd')])`

**Attack Scenario:**
1. Attacker gains read access to log files (via log aggregation, backup, shared hosting, or misconfigured log rotation)
2. Extracts all user credentials from log entries
3. Uses credentials for Crossmark API authentication or lateral movement

**Remediation:**
Remove all three debug logging statements. If login debugging is needed, log only the username:

```python
current_app.logger.info(f"Login attempt for user: {username}")
```

---

### CRIT-03: Broken Rate Limiting on Login Endpoint

**Severity:** Critical (CVSS 9.1)
**CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts)
**OWASP:** A07:2021 -- Identification and Authentication Failures

**Location:** `app/routes/auth.py`, lines 228-231 and `app/extensions.py`, line 20-24

**Description:**
Two compounding issues make brute-force protection completely ineffective:

**Issue A -- Lambda rate limit check is a no-op:**
```python
# auth.py:231 -- This creates a NEW decorated function on each call
# The rate limit state is per-decorated-function, so each request gets a fresh counter
limiter.limit("5 per minute")(lambda: None)()
```

The `limiter.limit()` decorator wraps a *new* anonymous lambda on every request. Since Flask-Limiter tracks rate limits per decorated view function (using its identity), each call creates a new identity and thus never triggers the limit.

**Issue B -- In-memory storage resets across workers:**
```python
# extensions.py:20-24
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",  # Per-process memory -- not shared between Gunicorn workers
    strategy="fixed-window"
)
```

With Gunicorn running multiple workers, the in-memory storage is per-worker, so rate limits are divided across workers and never accumulate properly.

**Attack Scenario:**
Unlimited brute-force attempts against the login endpoint. An attacker can try thousands of credential pairs per minute with no throttling.

**Remediation:**

1. Apply the rate limit as a proper decorator:
```python
@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    ...
```

2. Switch storage to Redis (already available in the stack):
```python
# extensions.py
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379/1",
    strategy="fixed-window"
)
```

3. Add account lockout after N failed attempts, with exponential backoff.

---

### CRIT-04: Unauthenticated Webhook Endpoint Without Signature Verification

**Severity:** Critical (CVSS 9.1)
**CWE:** CWE-345 (Insufficient Verification of Data Authenticity)
**OWASP:** A01:2021 -- Broken Access Control

**Location:** `app/routes/admin.py`, lines 268-323

**Description:**
The webhook endpoint `/api/webhook/schedule_update` is CSRF-exempt, requires no authentication, and has no HMAC signature verification. Any external party can call this endpoint to create, update, or delete schedule records.

```python
@admin_bp.route('/api/webhook/schedule_update', methods=['POST'])
# Note: CSRF exemption applied in app.py - external webhook cannot include CSRF token
def webhook_schedule_update():
    """
    Security: This route is CSRF-exempt because it's called by external systems.
    TODO: Implement HMAC signature validation to verify webhook authenticity.
    """
    data = request.get_json()
    webhook_type = data.get('type', '')
    payload = data.get('data', {})

    if webhook_type == 'schedule.created':
        result = sync_engine._create_local_schedule_from_external(payload)
    elif webhook_type == 'schedule.deleted':
        schedule = Schedule.query.filter_by(external_id=payload.get('id')).first()
        if schedule:
            db.session.delete(schedule)  # Direct database deletion from untrusted input
```

**Attack Scenario:**
```bash
curl -X POST https://target.com/api/webhook/schedule_update \
  -H "Content-Type: application/json" \
  -d '{"type": "schedule.deleted", "data": {"id": "any-external-id"}}'
```

**Remediation:**
Implement HMAC signature verification:

```python
import hmac
import hashlib

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')

@admin_bp.route('/api/webhook/schedule_update', methods=['POST'])
def webhook_schedule_update():
    signature = request.headers.get('X-Webhook-Signature')
    if not signature or not WEBHOOK_SECRET:
        abort(401)

    payload = request.get_data()
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(f"sha256={expected}", signature):
        abort(401)
    ...
```

---

### CRIT-05: Singleton SessionAPIService Race Condition -- Cross-User Authentication Leakage

**Severity:** Critical (CVSS 8.7)
**CWE:** CWE-362 (Concurrent Execution Using Shared Resource with Improper Synchronization)
**OWASP:** A07:2021 -- Identification and Authentication Failures

**Location:** `app/integrations/external_api/session_api_service.py` (module-level singleton at line 1802) and `app/routes/auth.py`, lines 256-277

**Description:**
The `session_api` is a process-level singleton shared across all requests. During login, the singleton's `username`, `password`, and session cookies are temporarily overwritten with the authenticating user's credentials. Although the auth code clears state before login, under concurrent requests in the same worker, two users logging in simultaneously can cause:

1. User A's credentials being used for User B's authentication
2. User B inheriting User A's Crossmark PHPSESSID
3. One user's authentication being lost when the other's `finally` block restores original credentials

```python
# auth.py:256-271 -- Non-atomic mutation of shared singleton
external_api.username = username      # Thread-unsafe write
external_api.password = password      # Thread-unsafe write
try:
    auth_success = external_api.login()
finally:
    if not auth_success:
        external_api.username = original_username  # Restores wrong user's creds
        external_api.password = original_password
```

The singleton at module level:
```python
# session_api_service.py:1802
session_api = SessionAPIService()  # Single instance for entire process
```

**Attack Scenario:**
Two users log in simultaneously on the same Gunicorn worker. User A (low-privilege specialist) ends up authenticated with User B's (supervisor) Crossmark session, gaining access to supervisor-level API operations on the external Crossmark system.

**Remediation:**
Replace the singleton pattern with per-request instances, or use a threading lock to serialize login operations:

```python
import threading

class SessionAPIService:
    _login_lock = threading.Lock()

    def login_as_user(self, username, password):
        """Create a dedicated session for this login attempt."""
        with self._login_lock:
            # Save and clear state
            ...
```

Better approach -- create a separate requests.Session per login attempt rather than mutating the shared singleton.

---

### CRIT-06: Role Assignment Bug -- Undefined `db` Variable May Grant Supervisor Access

**Severity:** Critical (CVSS 8.6)
**CWE:** CWE-269 (Improper Privilege Management)
**OWASP:** A01:2021 -- Broken Access Control

**Location:** `app/routes/auth.py`, lines 319-336

**Description:**
The role determination code during Crossmark login references `db.or_()` and `db.func.lower()`, but `db` is never imported or defined in this scope. The code sets the default role to `'supervisor'` (line 319) and then wraps the role lookup in a bare `except` that silently falls back to the supervisor default.

```python
user_info['role'] = 'supervisor'  # Default for Crossmark users
try:
    from app.models.registry import get_models
    models = get_models()
    Employee = models['Employee']
    emp = Employee.query.filter(
        db.or_(  # NameError: 'db' is not defined
            Employee.crossmark_employee_id == username,
            db.func.lower(Employee.name) == user_info.get('full_name', '').lower()
        )
    ).first() if hasattr(db, 'or_') else None  # hasattr(undefined, ...) -> NameError
    if emp:
        user_info['role'] = emp.role
        user_info['employee_id'] = emp.id
except Exception:
    pass  # Silently grants supervisor role
```

Since `db` is undefined, the `hasattr(db, 'or_')` call raises a `NameError` (caught by `except Exception: pass`), and every Crossmark-authenticated user receives the `supervisor` role.

**Attack Scenario:**
Any Crossmark user (even those who should be specialists or leads) can authenticate and receive full supervisor privileges, gaining access to:
- Auto-scheduler operations
- Employee management (set/revoke PINs)
- Database refresh
- EDR report generation
- All supervisor-only routes

**Remediation:**
Import `db` properly and fix the query:

```python
from app.models.registry import get_models, get_db

user_info['role'] = 'specialist'  # Safe default (least privilege)
try:
    models = get_models()
    db = get_db()
    Employee = models['Employee']
    emp = Employee.query.filter(
        db.or_(
            Employee.crossmark_employee_id == username,
            db.func.lower(Employee.name) == user_info.get('full_name', '').lower()
        )
    ).first()
    if emp:
        user_info['role'] = emp.role
        user_info['employee_id'] = emp.id
except Exception as e:
    current_app.logger.error(f"Role lookup failed for {username}: {e}")
    # Keep least-privilege default
```

---

### CRIT-07: Unauthenticated Infrastructure Diagnostic Endpoint

**Severity:** Critical (CVSS 7.5)
**CWE:** CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor)
**OWASP:** A05:2021 -- Security Misconfiguration

**Location:** `app/routes/auth.py`, lines 636-654

**Description:**
The `/api/auth/diag` endpoint requires no authentication and exposes Redis infrastructure details including connection status, whether credentials are configured, and error messages that may contain connection strings.

```python
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
        status['error'] = str(e)  # May leak Redis connection details
    return jsonify(status)
```

**Remediation:**
Require authentication and supervisor role, or remove entirely:

```python
@auth_bp.route('/api/auth/diag')
@require_authentication()
@require_role('supervisor')
def auth_diag():
    ...
```

---

## 2. High Findings

### HIGH-01: Systematic Exception Detail Leakage in API Responses

**Severity:** High (CVSS 7.5)
**CWE:** CWE-209 (Generation of Error Message Containing Sensitive Information)
**OWASP:** A05:2021 -- Security Misconfiguration

**Location:** 100+ occurrences across `app/routes/` (particularly `api.py`, `api_notes.py`, `api_company_holidays.py`, `admin.py`)

**Description:**
Across the entire API surface, exception messages are exposed to the client via `str(e)` in JSON responses. These messages frequently contain:
- Database schema information (table names, column names, constraint names)
- File system paths
- SQL query fragments
- Internal implementation details

**Examples from the codebase:**
```python
# api.py:922 (multiple similar patterns)
return jsonify({'error': 'Failed to unschedule event', 'details': str(e)}), 500

# api_notes.py:90
return jsonify({'success': False, 'error': str(e)}), 500

# admin.py:158
return jsonify({'success': False, 'message': f'Error removing event: {str(e)}'}), 500
```

**Count of affected locations:** 60+ in routes alone, 117+ across the full application.

**Attack Scenario:**
An attacker triggers errors deliberately (e.g., malformed input) to harvest database schema, table names, and file paths, then uses this information to craft targeted injection attacks.

**Remediation:**
Create a standardized error handler that logs the full exception internally but returns a generic message to the client:

```python
def safe_error_response(message, status_code=500, exception=None):
    """Return safe error response without leaking internals."""
    if exception:
        current_app.logger.error(f"{message}: {exception}", exc_info=True)
    return jsonify({
        'success': False,
        'error': message
    }), status_code

# Usage:
except Exception as e:
    return safe_error_response('Failed to process request', 500, e)
```

---

### HIGH-02: SSL/TLS Verification Disabled for External HTTP Requests

**Severity:** High (CVSS 7.4)
**CWE:** CWE-295 (Improper Certificate Validation)
**OWASP:** A07:2021 -- Identification and Authentication Failures

**Location:** `app/services/demo_goals_service.py`, lines 40 and 59

**Description:**
External HTTPS requests to `productconnections.com` are made with `verify=False`, disabling TLS certificate validation. This makes the application vulnerable to man-in-the-middle attacks.

```python
resp = requests.get(DEMO_GOALS_PAGE_URL, headers=_HEADERS, timeout=timeout, verify=False)
resp = requests.get(AJAX_URL, params=params, headers=_HEADERS, timeout=timeout, verify=False)
```

**Remediation:**
Remove `verify=False`. If there is a legitimate certificate issue with the target server, use a custom CA bundle:

```python
resp = requests.get(url, headers=_HEADERS, timeout=timeout)  # verify=True is default
```

---

### HIGH-03: Hardcoded Employee PII in Source Code

**Severity:** High (CVSS 7.1)
**CWE:** CWE-798 (Use of Hard-coded Credentials) / CWE-312 (Cleartext Storage of Sensitive Information)
**OWASP:** A02:2021 -- Cryptographic Failures

**Location:** `app/services/sync_service.py`, lines 84-92 and 198-206

**Description:**
Real employee names and their Crossmark RepIDs are hardcoded in the source code as a lookup dictionary, appearing in two separate locations:

```python
employee_to_repid = {
    'MAT CONDER': '152052',
    'DIANE CARR': '19461',
    'BRANDY CREASEY': '157632',
    'NANCY DINKINS': '141359',
    'MELISSA MCINTOSH': '141359',
    'KRISSY TAYLOR': '184862',
    'BETH DAVIS': '188743'
}
```

This data is committed to version control and visible to anyone with repository access.

**Remediation:**
Move the mapping to a database table or environment configuration:

```python
# Use the Employee model's external_id field instead
rep_id = employee.external_id  # Already available on the Employee model
if not rep_id:
    logger.error(f"No external_id configured for employee: {employee.name}")
    return {'success': False, 'message': 'Employee not configured for sync'}
```

---

### HIGH-04: Pickle Deserialization of Cached Session Data

**Severity:** High (CVSS 7.0)
**CWE:** CWE-502 (Deserialization of Untrusted Data)
**OWASP:** A08:2021 -- Software and Data Integrity Failures

**Location:** `app/routes/admin.py`, lines 924-937 (pickle.dump) and 982-984 (pickle.load)

**Description:**
The EDR MFA workflow serializes session cookies to a temporary file using `pickle.dump()` and later deserializes with `pickle.load()`. The cache file path includes a user-controlled session ID component:

```python
session_id = flask_session.get('user_id') or 'default'
cache_file = os.path.join(tempfile.gettempdir(), f'edr_session_{session_id}.pkl')

# Later:
with open(cache_file, 'rb') as f:
    session_cookies = pickle.load(f)  # Dangerous deserialization
```

While the file path includes the user's session ID and is stored in `/tmp`, an attacker with write access to the temp directory could replace the pickle file with a malicious payload containing arbitrary code execution commands.

**Remediation:**
Replace pickle with JSON serialization (session cookies are simple string key-value pairs):

```python
import json

# Serialize
with open(cache_file, 'w') as f:
    json.dump(session_data, f)

# Deserialize
with open(cache_file, 'r') as f:
    session_cookies = json.load(f)
```

---

### HIGH-05: Insecure Production SECRET_KEY Default

**Severity:** High (CVSS 7.0)
**CWE:** CWE-798 (Use of Hard-coded Credentials)
**OWASP:** A02:2021 -- Cryptographic Failures

**Location:** `app/config.py`, line 141

**Description:**
The production configuration has a weak default SECRET_KEY that will be used if the environment variable is not set. While there is a validation method, it is only called when `validate=True` is explicitly passed to `get_config()`.

```python
class ProductionConfig(Config):
    SECRET_KEY = config('SECRET_KEY', default='change-this-to-a-random-secret-key-in-production')
```

If the application is started in production mode without the `SECRET_KEY` environment variable, it runs with this predictable key. The base `Config` class generates a random key at import time (`secrets.token_hex(32)`) but this is per-process and non-persistent, meaning sessions break across restarts.

**Remediation:**
Remove the default and raise an error immediately:

```python
class ProductionConfig(Config):
    SECRET_KEY = config('SECRET_KEY')  # No default -- raises UndefinedValueError if missing
```

---

### HIGH-06: PHPSESSID Stored in Redis Session Data

**Severity:** High (CVSS 6.8)
**CWE:** CWE-522 (Insufficiently Protected Credentials)
**OWASP:** A07:2021 -- Identification and Authentication Failures

**Location:** `app/routes/auth.py`, lines 344-352

**Description:**
The Crossmark API's PHPSESSID (a session token granting access to the external Crossmark system) is stored in the user's Redis session:

```python
session_data = {
    'user_id': username,
    'user_info': user_info,
    ...
    'phpsessid': external_api.phpsessid  # External session token stored in user session
}
```

If the Redis instance is compromised, an attacker obtains both the application session tokens and the Crossmark PHPSESSID, enabling direct access to the Crossmark external API.

**Remediation:**
Do not store external session tokens in user sessions. If the PHPSESSID is needed for subsequent API calls, store it only in the server-side singleton's memory (encrypted if possible), not in per-user Redis data.

---

### HIGH-07: Debug Mode Enabled in Development Config Used in Production

**Severity:** High (CVSS 6.5)
**CWE:** CWE-489 (Active Debug Code)
**OWASP:** A05:2021 -- Security Misconfiguration

**Location:** `app/config.py`, lines 110-112 and `app/routes/health.py`, line 120

**Description:**
The `DevelopmentConfig` sets `DEBUG = True` and is the default configuration. If `FLASK_ENV` is not explicitly set to `production`, the application runs in debug mode. The health endpoint confirms this by exposing `current_app.debug` status to unauthenticated users.

```python
class DevelopmentConfig(Config):
    DEBUG = True  # Werkzeug debugger, stack traces, auto-reload

# config.py:237
config_mapping = {
    'default': DevelopmentConfig  # Debug mode is the default
}
```

The `/health/status` endpoint (unauthenticated) reports whether debug mode is active:
```python
'debug': current_app.debug,  # Confirms attack surface to unauthenticated users
```

**Remediation:**
1. Set `FLASK_ENV=production` in deployment configuration
2. Require authentication for `/health/status`
3. Remove `debug` from health response

---

### HIGH-08: HAR File Committed to Repository

**Severity:** High (CVSS 6.5)
**CWE:** CWE-200 (Exposure of Sensitive Information)
**OWASP:** A05:2021 -- Security Misconfiguration

**Location:** `crossmark.mvretail.com.har` (548 KB, untracked but present in working directory)

**Description:**
An HTTP Archive (HAR) file for `crossmark.mvretail.com` is present in the repository root. HAR files typically contain:
- Authentication cookies and session tokens
- Request/response headers with credentials
- API keys and tokens
- Full request/response bodies

This file is currently untracked (`??` in git status) but could be accidentally committed.

**Remediation:**
1. Delete the file immediately: `rm crossmark.mvretail.com.har`
2. Add `*.har` to `.gitignore`
3. If the file was ever committed, credentials exposed in it should be rotated

---

### HIGH-09: Content Security Policy Allows `unsafe-inline`

**Severity:** High (CVSS 6.1)
**CWE:** CWE-79 (Cross-site Scripting)
**OWASP:** A03:2021 -- Injection

**Location:** `app/config.py`, lines 169-177

**Description:**
The CSP header in `ProductionConfig` allows `'unsafe-inline'` for both scripts and styles:

```python
"script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com; "
"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com ...;"
```

`unsafe-inline` in `script-src` completely defeats CSP's XSS protection because any injected inline script will execute.

**Remediation:**
Replace `unsafe-inline` with nonce-based CSP:

```python
# In the after_request handler, generate a nonce per request:
import secrets
nonce = secrets.token_urlsafe(16)
response.headers['Content-Security-Policy'] = (
    f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
    f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
)
# Pass nonce to templates for use in <script nonce="..."> tags
```

---

### HIGH-10: Security Headers Only Applied in Production

**Severity:** High (CVSS 5.8)
**CWE:** CWE-16 (Configuration)
**OWASP:** A05:2021 -- Security Misconfiguration

**Location:** `app/config.py` and `app/__init__.py`, lines 360-365

**Description:**
The `SECURITY_HEADERS` dictionary (including HSTS, X-Content-Type-Options, X-Frame-Options, CSP) is only defined in `ProductionConfig`. In development (the default), no security headers are applied. If the application is deployed without explicitly setting `FLASK_ENV=production`, all security headers are missing.

```python
# app/__init__.py:361-364 -- Only applies headers if they exist in config
@app.after_request
def apply_security_headers(response):
    for header, value in app.config.get('SECURITY_HEADERS', {}).items():
        response.headers[header] = value
```

Since `Config` (base) and `DevelopmentConfig` have no `SECURITY_HEADERS`, the loop iterates over an empty dict.

**Remediation:**
Move critical security headers to the base `Config` class:

```python
class Config:
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '0',  # Deprecated but harmless
        'Referrer-Policy': 'strict-origin-when-cross-origin',
    }
```

---

### HIGH-11: Session Cookie `secure` Flag Conditional on `request.is_secure`

**Severity:** High (CVSS 5.4)
**CWE:** CWE-614 (Sensitive Cookie in HTTPS Session Without 'Secure' Attribute)
**OWASP:** A02:2021 -- Cryptographic Failures

**Location:** `app/routes/auth.py`, lines 390-393 and 513-516

**Description:**
The session cookie's `secure` flag is set dynamically based on `request.is_secure`:

```python
response.set_cookie(
    'session_id', session_id,
    max_age=cookie_max_age,
    httponly=True,
    secure=request.is_secure,  # False if behind misconfigured proxy
    samesite='Lax'
)
```

If the reverse proxy does not properly forward the `X-Forwarded-Proto` header (or ProxyFix is misconfigured), `request.is_secure` returns `False` even on HTTPS connections. This causes the session cookie to be sent over unencrypted HTTP connections.

**Remediation:**
In production, always set `secure=True`:

```python
is_production = not current_app.debug
response.set_cookie(
    'session_id', session_id,
    httponly=True,
    secure=is_production or request.is_secure,
    samesite='Lax'
)
```

---

## 3. Medium Findings

### MED-01: 26 Bare `except:` Clauses Swallowing Errors

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-754 (Improper Check for Unusual or Exceptional Conditions)
**OWASP:** A09:2021 -- Security Logging and Monitoring Failures

**Locations:** 26 sites across `app/` (see grep results in analysis)

**Description:**
Bare `except:` clauses catch all exceptions including `SystemExit`, `KeyboardInterrupt`, and memory errors. They silently discard errors, preventing detection of security-relevant failures.

Key locations:
- `app/services/sync_service.py:145` -- Swallows database commit errors
- `app/routes/health.py:176,182,188` -- Swallows database query errors
- `app/integrations/edr/pdf_generator.py:167,315,818` -- Swallows EDR processing errors
- `app/routes/printing.py:681,857,1128` -- Swallows document generation errors

**Remediation:**
Replace with `except Exception as e:` and add logging:

```python
except Exception as e:
    logger.error(f"Operation failed: {e}")
```

---

### MED-02: Crossmark Authentication Credentials Logged at INFO Level

**Severity:** Medium (CVSS 6.2)
**CWE:** CWE-532 (Insertion of Sensitive Information into Log File)

**Location:** `app/integrations/external_api/session_api_service.py`, lines 117-119

**Description:**
The `login()` method logs the full authentication data payload (containing the user's password) at INFO level:

```python
self.logger.info(f"Authentication URL: {auth_url}")
self.logger.info(f"Authentication headers: {headers}")
self.logger.info(f"Authentication data: {auth_data}")  # Contains "Password": "..."
```

**Remediation:**
Log only non-sensitive fields:

```python
self.logger.info(f"Authenticating user: {self.username} at {auth_url}")
```

---

### MED-03: SQL-Like Pattern Injection via Search Parameters

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-943 (Improper Neutralization of Special Elements in Data Query Logic)

**Location:** `app/routes/admin.py`, lines 367-370 and `app/routes/api.py`, line 4269

**Description:**
Search queries use `ilike(f'%{query}%')` with user input directly interpolated into the LIKE pattern. While SQLAlchemy parameterizes the query, the LIKE wildcards (`%` and `_`) in user input are not escaped, allowing users to craft patterns that produce excessive database load or return unexpected results.

```python
Event.project_name.ilike(f'%{query}%')  # User can inject % and _ wildcards
```

**Remediation:**
Escape LIKE wildcards in user input:

```python
from sqlalchemy import func

def escape_like(s):
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

Event.project_name.ilike(f'%{escape_like(query)}%', escape='\\')
```

---

### MED-04: Unauthenticated Employee Account Enumeration

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-204 (Observable Response Discrepancy)
**OWASP:** A07:2021 -- Identification and Authentication Failures

**Location:** `app/routes/api.py`, lines 28-38

**Description:**
The `/api/employees/with-accounts` endpoint requires no authentication and returns a list of all employees with active PIN accounts, including their names and IDs:

```python
@api_bp.route('/employees/with-accounts', methods=['GET'])
def get_employees_with_accounts():
    """Get active employees who have PIN accounts set up (for login dropdown)."""
    employees = Employee.query.filter_by(is_active=True, has_account=True).all()
    return jsonify({'employees': [{'id': e.id, 'name': e.name} for e in employees]})
```

This provides an attacker with a verified list of valid employee IDs for brute-forcing the PIN-based login.

**Remediation:**
This endpoint is used for the employee login dropdown. Consider rate-limiting it and requiring a preliminary interaction (e.g., captcha), or remove the dropdown in favor of a free-text employee ID input field.

---

### MED-05: Weak PIN Policy -- Minimum 4 Characters, No Complexity

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-521 (Weak Password Requirements)
**OWASP:** A07:2021 -- Identification and Authentication Failures

**Location:** `app/routes/auth.py`, lines 538-539

**Description:**
PINs are only required to be 4 characters minimum with no complexity requirements:

```python
if len(pin) < 4:
    return jsonify({'success': False, 'error': 'PIN must be at least 4 characters'}), 400
```

A 4-digit numeric PIN has only 10,000 combinations. Combined with the broken rate limiter (CRIT-03), this is trivially brute-forceable.

**Remediation:**
1. Increase minimum PIN length to 6
2. Add rate limiting to the employee login endpoint
3. Implement account lockout after 5 failed attempts
4. Consider requiring alphanumeric PINs

---

### MED-06: CSRF Protection Gaps for State-Changing Endpoints

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-352 (Cross-Site Request Forgery)
**OWASP:** A01:2021 -- Broken Access Control

**Location:** `app/__init__.py`, lines 276-287

**Description:**
Several state-changing endpoints are explicitly CSRF-exempt:

```python
csrf.exempt(app.view_functions['auth.login'])           # Expected (pre-auth)
csrf.exempt(app.view_functions['admin.webhook_schedule_update'])  # Dangerous
csrf.exempt(app.view_functions['auth.session_heartbeat'])  # Low risk
csrf.exempt(app.view_functions['auth.start_loading_refresh'])  # Moderate risk
```

Additionally, the entire `auto_scheduler_bp` is exempt from rate limiting (line 208), and unauthenticated POST endpoints in `api.py` (like `/api/reschedule`, `/api/schedule-event`, etc.) can be targeted via CSRF since they lack both authentication and CSRF checks.

**Remediation:**
CSRF exemption for the webhook is acceptable only with HMAC verification (see CRIT-04). For `start_loading_refresh`, add CSRF protection or validate a nonce from the loading page.

---

### MED-07: No Rate Limiting on Employee PIN Login

**Severity:** Medium (CVSS 5.9)
**CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts)

**Location:** `app/routes/auth.py`, lines 442-518

**Description:**
The employee PIN login endpoint (`/employee-login` POST) has no rate limiting at all. Unlike the Crossmark login which at least attempts rate limiting (albeit broken), the PIN login has no throttling mechanism.

**Remediation:**
Apply the rate limiter decorator directly:

```python
@auth_bp.route('/employee-login', methods=['POST'])
@limiter.limit("5 per minute")
def employee_login():
    ...
```

---

### MED-08: `require_role` Default Grants Supervisor to Legacy Sessions

**Severity:** Medium (CVSS 5.5)
**CWE:** CWE-269 (Improper Privilege Management)

**Location:** `app/routes/auth.py`, line 194

**Description:**
The `require_role` decorator defaults to `'supervisor'` if the role field is missing from the session:

```python
user_role = user.get('role', 'supervisor')  # Default to supervisor for legacy sessions
```

Any session data that lacks a `role` field (due to corruption, migration, or a bug) automatically receives the highest privilege level.

**Remediation:**
Default to the least privileged role:

```python
user_role = user.get('role', 'specialist')  # Default to least privilege
```

---

### MED-09: Health/Metrics Endpoints Expose Internal Metrics Without Auth

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-200 (Exposure of Sensitive Information)

**Location:** `app/routes/health.py`, lines 90-205

**Description:**
The `/health/status` and `/health/metrics` endpoints expose:
- Python version
- OS platform
- Process ID
- Memory usage
- CPU usage
- Disk usage
- Database type
- Debug mode status
- Database table record counts

None of these endpoints require authentication.

**Remediation:**
Keep `/health/ping` and `/health/live` unauthenticated for load balancer probes. Require authentication for `/health/status` and `/health/metrics`:

```python
@health_bp.route('/status', methods=['GET'])
@require_authentication()
@require_role('supervisor')
def status():
    ...
```

---

### MED-10: Crossmark API Credentials Logged During Authentication

**Severity:** Medium (CVSS 5.0)
**CWE:** CWE-532 (Insertion of Sensitive Information into Log File)

**Location:** `app/routes/auth.py`, line 275

**Description:**
After setting the singleton's credentials to the user's values, the login handler logs the username in clear text:

```python
current_app.logger.info(f"Attempting authentication for user: {username}")
```

While logging the username alone is lower risk than logging the password (CRIT-02), the combined effect with the form data logging creates a complete credential exposure vector.

**Remediation:**
Keep this log entry but ensure CRIT-02 is fixed. Optionally, hash or truncate the username for log files.

---

### MED-11: Missing `Referrer-Policy` Header

**Severity:** Medium (CVSS 4.3)
**CWE:** CWE-16 (Configuration)

**Location:** `app/config.py`, lines 164-178

**Description:**
The `SECURITY_HEADERS` dict does not include a `Referrer-Policy` header. Without it, the browser's default behavior may leak the full URL (including query parameters) to external sites via the `Referer` header.

**Remediation:**
Add to security headers:

```python
SECURITY_HEADERS = {
    ...
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}
```

---

### MED-12: Thread Safety of Background Database Refresh

**Severity:** Medium (CVSS 4.3)
**CWE:** CWE-362 (Concurrent Execution Using Shared Resource)

**Location:** `app/routes/auth.py`, lines 890-901

**Description:**
The loading page refresh endpoint spawns a background thread for database operations. Multiple simultaneous logins could trigger concurrent database refreshes, potentially causing data corruption:

```python
thread = threading.Thread(target=run_refresh, daemon=True)
thread.start()
```

There is no mechanism to prevent concurrent execution.

**Remediation:**
Use a Redis-based lock to ensure only one refresh runs at a time:

```python
if not redis_client.set('db_refresh_lock', '1', nx=True, ex=300):
    return jsonify({'success': False, 'error': 'Refresh already in progress'}), 429
```

---

### MED-13: `session_info` Endpoint Returns Full User Object Without Auth Validation

**Severity:** Medium (CVSS 4.3)
**CWE:** CWE-200 (Exposure of Sensitive Information)

**Location:** `app/routes/auth.py`, lines 592-611

**Description:**
The `/api/session-info` endpoint reads the session data directly from Redis using the session cookie, but does not call `is_authenticated()` to validate timeout/expiry. It returns the full `user_info` dict, which may contain employee IDs, job titles, and role information:

```python
@auth_bp.route('/api/session-info')
def session_info():
    session_id = request.cookies.get('session_id')
    session_data = get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    # Returns user_info without checking timeout/expiry
    return jsonify({'success': True, 'user': session_data.get('user_info', {})})
```

**Remediation:**
Use `is_authenticated()` for proper validation, and limit the returned fields.

---

### MED-14: Deprecated Endpoint Processes Requests via Internal Redirect

**Severity:** Medium (CVSS 4.3)
**CWE:** CWE-601 (URL Redirection to Untrusted Site)

**Location:** `app/routes/api.py`, lines 2819-2857

**Description:**
The deprecated `/api/reschedule_event` endpoint creates a new request context and calls `reschedule()` directly. This bypasses CSRF validation, rate limiting, and potentially authentication for the target function:

```python
with current_app.test_request_context('/api/reschedule', method='POST', json=transformed_data):
    return reschedule()
```

**Remediation:**
Remove deprecated endpoints, or redirect with proper HTTP redirect:

```python
return redirect(url_for('api.reschedule'), code=307)  # 307 preserves POST method
```

---

## 4. Low Findings

### LOW-01: `X-XSS-Protection: 1; mode=block` Uses Deprecated Header

**Severity:** Low (CVSS 3.1)
**Location:** `app/config.py`, line 168

**Description:**
The `X-XSS-Protection` header is deprecated in modern browsers and can actually introduce vulnerabilities in some edge cases. Chrome removed support in 2019.

**Remediation:**
Set to `0` (disabled) and rely on CSP instead:
```python
'X-XSS-Protection': '0',
```

---

### LOW-02: CSRF Token Cookie Not HTTPOnly

**Severity:** Low (CVSS 3.1)
**Location:** `app/__init__.py`, lines 351-356

**Description:**
The CSRF token cookie is intentionally set with `httponly=False` so JavaScript can read it. This is the correct behavior for a double-submit cookie pattern, but means JavaScript (including any injected XSS payload) can read the CSRF token.

**Remediation:**
This is expected behavior for the double-submit pattern. Mitigate by fixing the CSP (HIGH-09) to prevent XSS.

---

### LOW-03: `remember_me` Checkbox Has No Effect on Session Expiry

**Severity:** Low (CVSS 2.0)
**Location:** `app/routes/auth.py`, line 385

**Description:**
The `remember_me` parameter only affects cookie `max_age` for non-persistent sessions but has no effect on Redis TTL. The session expires in Redis after 24 hours regardless:

```python
cookie_max_age = PERSISTENT_SESSION_TTL if persistent else (86400 if remember_me else None)
# But Redis TTL is always 86400 for non-persistent sessions
```

When `remember_me` is False, the cookie has no `max_age` (session cookie), but Redis still stores the session for 24 hours. This is a minor UX issue rather than a security issue.

---

### LOW-04: Employee `role` Property Derives from `job_title` Without Validation

**Severity:** Low (CVSS 3.4)
**Location:** `app/models/employee.py`, lines 114-120

**Description:**
The `role` property on the Employee model derives the access level from the `job_title` field. If an admin modifies `job_title` to 'Club Supervisor' for any employee, that employee gains supervisor privileges.

```python
@property
def role(self):
    if self.job_title == 'Club Supervisor' or self.is_supervisor:
        return 'supervisor'
    elif self.job_title == 'Lead Event Specialist':
        return 'lead'
```

**Remediation:**
Consider storing the role as an explicit database column rather than deriving it from job title.

---

### LOW-05: Missing `SameSite=Strict` on Session Cookie

**Severity:** Low (CVSS 3.1)
**Location:** `app/routes/auth.py`, lines 390-393

**Description:**
Session cookies use `samesite='Lax'`. While `Lax` prevents CSRF on POST requests, it allows cookies to be sent on top-level GET navigations from external sites. `Strict` would provide stronger protection but may impact legitimate cross-site navigation (e.g., links from email).

---

### LOW-06: Database Connection String in Default Config

**Severity:** Low (CVSS 2.0)
**Location:** `app/config.py`, line 19

**Description:**
The default database URI is `sqlite:///instance/scheduler.db`. While SQLite is file-based and doesn't involve network credentials, it reveals the database path. For PostgreSQL deployments, ensure the connection string is provided via environment variable only.

---

### LOW-07: Missing `__all__` in Model Registry -- Broad Import Exposure

**Severity:** Low (CVSS 1.0)
**Location:** `app/models/__init__.py`

**Description:**
Without `__all__` definitions, wildcard imports could expose internal implementation details.

---

### LOW-08: Thread-Local `_redis_client` Without Cleanup

**Severity:** Low (CVSS 2.0)
**Location:** `app/routes/auth.py`, lines 20-37

**Description:**
The Redis client is stored in a global variable and never cleaned up. While `redis-py` handles connection pooling internally, the global reference pattern can lead to stale connections after Redis restarts.

---

## 5. Informational / Best Practice

### INFO-01: Missing Security-Related HTTP Headers

The following headers are recommended but not currently set:
- `Permissions-Policy: camera=(), microphone=(), geolocation=()` -- Restricts browser feature access
- `Cross-Origin-Embedder-Policy: require-corp` -- Prevents loading cross-origin resources without CORS
- `Cross-Origin-Opener-Policy: same-origin` -- Isolates browsing context
- `Cross-Origin-Resource-Policy: same-origin` -- Prevents cross-origin reads

### INFO-02: No Audit Logging for Administrative Actions

While `AuditLog` model exists, the code paths for critical administrative actions (PIN set/revoke, database refresh, scheduler runs, employee termination) do not consistently create audit records.

### INFO-03: No HSTS Preload

The HSTS header includes `includeSubDomains` but not `preload`. For maximum security, add to the HSTS preload list.

### INFO-04: Service Worker Caches API Responses

The service worker (`app/static/service-worker.js`) caches API responses via the `network-first` strategy. If a user logs out but the service worker cache contains sensitive data, the next user on a shared device could see cached responses.

### INFO-05: `ProxyFix` Trusts 1 Hop

```python
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
```

Ensure this matches the actual number of reverse proxies. If there are two proxies (e.g., Cloudflare + Nginx), set `x_for=2`.

---

## 6. Dependency Analysis

### Pinned Versions with Known Considerations

| Package | Version | Notes |
|---------|---------|-------|
| Flask | 3.0.3 | Current as of audit date |
| cryptography | 42.0.5 | Check for updates; active security project |
| requests | 2.32.3 | Current |
| urllib3 | 2.2.1 | Current |
| gunicorn | 21.2.0 | Current |
| redis | 5.0.3 | Current |
| celery | 5.3.6 | Current |
| Pillow | >=10.0.0 | Unpinned upper bound; pin to specific version |
| PyPDF2 | 3.0.1 | Deprecated; consider `pypdf` |
| pychrome | >=0.2.4 | Browser automation library; review if needed |
| psycopg2-binary | 2.9.9 | Use `psycopg2` (non-binary) in production |

### Unpinned Dependencies (Risk: Supply Chain)

The following packages use loose version specifiers (`>=`) which could introduce breaking changes or compromised versions:
- `pywebpush>=2.0.0`
- `py-vapid>=1.9.0`
- `python-barcode>=0.15.1`
- `Pillow>=10.0.0`
- `openpyxl>=3.1.0`
- `google-generativeai>=0.3.0`
- `ollama>=0.4.0`
- `pandas>=2.0.0`
- `numpy>=1.24.0`
- `scikit-learn>=1.3.0`
- `xgboost>=2.0.0`
- `joblib>=1.3.0`

**Remediation:** Pin all dependencies to exact versions. Generate and verify `requirements.txt` hashes:
```bash
pip install pip-tools
pip-compile --generate-hashes requirements.in -o requirements.txt
```

---

## 7. Remediation Priority Matrix

### Immediate (Week 1) -- Stop the Bleeding

| Finding | Effort | Impact |
|---------|--------|--------|
| CRIT-01 | Medium | Add `@require_authentication()` to all API endpoints |
| CRIT-02 | Trivial | Delete 3 lines of debug logging |
| CRIT-03 | Low | Fix rate limiter: proper decorator + Redis storage |
| CRIT-06 | Low | Import `db` properly, change default role to `specialist` |
| CRIT-07 | Trivial | Add `@require_authentication()` to diag endpoint |
| HIGH-08 | Trivial | Delete HAR file, add `*.har` to `.gitignore` |

### Short-term (Week 2-3) -- Structural Fixes

| Finding | Effort | Impact |
|---------|--------|--------|
| CRIT-04 | Medium | Implement HMAC webhook verification |
| CRIT-05 | High | Refactor singleton to per-request or use locking |
| HIGH-01 | High | Create `safe_error_response()`, replace 100+ sites |
| HIGH-02 | Trivial | Remove `verify=False` (2 lines) |
| HIGH-03 | Medium | Move PII to database, delete from source code |
| HIGH-05 | Low | Remove default SECRET_KEY in production config |
| MED-05 | Low | Increase PIN length, add lockout |
| MED-07 | Trivial | Add `@limiter.limit()` to employee login |

### Medium-term (Month 1-2) -- Hardening

| Finding | Effort | Impact |
|---------|--------|--------|
| HIGH-04 | Low | Replace pickle with JSON |
| HIGH-06 | Low | Remove PHPSESSID from Redis session |
| HIGH-09 | High | Implement nonce-based CSP |
| HIGH-10 | Medium | Move security headers to base config |
| HIGH-11 | Low | Force `secure=True` in production |
| MED-01 | Medium | Fix 26 bare except clauses |
| MED-08 | Trivial | Change role default to `specialist` |
| MED-09 | Low | Add auth to health/metrics endpoints |

### Long-term (Quarter) -- Architecture Improvements

| Finding | Effort | Impact |
|---------|--------|--------|
| MED-02 | Low | Sanitize auth logging |
| MED-06 | Medium | Review and fix CSRF gaps |
| MED-12 | Medium | Add distributed locking for background tasks |
| MED-14 | Low | Remove deprecated endpoints |
| INFO-02 | High | Implement comprehensive audit logging |

---

## Appendix: Files Referenced

- `/home/elliot/flask-schedule-webapp/app/routes/auth.py` -- Authentication, session management
- `/home/elliot/flask-schedule-webapp/app/routes/api.py` -- Main REST API (6900+ lines)
- `/home/elliot/flask-schedule-webapp/app/routes/admin.py` -- Admin operations, webhook, EDR
- `/home/elliot/flask-schedule-webapp/app/routes/api_push.py` -- Web Push subscriptions
- `/home/elliot/flask-schedule-webapp/app/routes/api_schedule_changes.py` -- Schedule notifications
- `/home/elliot/flask-schedule-webapp/app/routes/api_demo_goals.py` -- Demo goals (unauthenticated)
- `/home/elliot/flask-schedule-webapp/app/routes/api_attendance.py` -- Attendance API
- `/home/elliot/flask-schedule-webapp/app/routes/health.py` -- Health/metrics (unauthenticated)
- `/home/elliot/flask-schedule-webapp/app/config.py` -- Configuration classes
- `/home/elliot/flask-schedule-webapp/app/__init__.py` -- Application factory
- `/home/elliot/flask-schedule-webapp/app/extensions.py` -- Flask extensions (rate limiter)
- `/home/elliot/flask-schedule-webapp/app/integrations/external_api/session_api_service.py` -- Singleton API service
- `/home/elliot/flask-schedule-webapp/app/services/sync_service.py` -- Background sync (hardcoded PII)
- `/home/elliot/flask-schedule-webapp/app/services/demo_goals_service.py` -- SSL verification disabled
- `/home/elliot/flask-schedule-webapp/app/models/employee.py` -- Employee model, PIN hashing
- `/home/elliot/flask-schedule-webapp/app/models/event.py` -- Event model
- `/home/elliot/flask-schedule-webapp/app/ai/routes.py` -- AI endpoints (unauthenticated)
- `/home/elliot/flask-schedule-webapp/app/static/service-worker.js` -- PWA service worker
- `/home/elliot/flask-schedule-webapp/requirements.txt` -- Dependencies
- `/home/elliot/flask-schedule-webapp/crossmark.mvretail.com.har` -- HAR file (sensitive data risk)

---

*Report generated 2026-03-26. Findings should be validated in a staging environment before applying remediations to production.*
