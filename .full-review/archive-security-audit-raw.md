# Security Audit Report: Uncommitted Changes

**Date**: 2026-02-18
**Auditor**: Claude Opus 4.6 (DevSecOps Security Audit)
**Scope**: All uncommitted changes in `flask-schedule-webapp`
**Framework**: Flask 2.0+ / SQLAlchemy / Jinja2
**Methodology**: Manual code review against OWASP Top 10 (2021), CWE taxonomy, ASVS 4.0

---

## Executive Summary

**39 files changed** (+2,692 / -3,358 lines). The changeset introduces significant new functionality (Fix Wizard, AI tool expansion, CP-SAT scheduler enhancements, constraint modifier, schedule preservation) alongside CSRF header standardization and bug fixes.

**4 Critical**, **5 High**, **6 Medium**, **3 Low** findings identified.

| Severity | Count | Immediate Action Required |
|----------|-------|---------------------------|
| Critical | 4     | Yes - deploy blockers     |
| High     | 5     | Yes - before next release |
| Medium   | 6     | Planned remediation       |
| Low      | 3     | Best-practice hardening   |

---

## Critical Findings

### CRT-01: Fix Wizard Routes Missing Authentication

**Severity**: Critical (CVSS 9.1)
**CWE**: CWE-306 (Missing Authentication for Critical Function)
**OWASP**: A01:2021 - Broken Access Control
**File**: `/home/elliot/flask-schedule-webapp/app/routes/dashboard.py`, lines 1028-1195

**Description**: Four new Fix Wizard routes lack the `@require_authentication()` decorator that is applied to virtually every other route in the application. These routes perform destructive schedule modifications (reassign employees, delete schedules, reschedule events, create database records).

**Affected Endpoints**:
- `GET /fix-wizard` (line 1028) -- renders page
- `GET /api/fix-wizard/issues` (line 1056) -- returns all schedule issues with employee data
- `POST /api/fix-wizard/apply` (line 1109) -- **modifies/deletes schedules**
- `POST /api/fix-wizard/skip` (line 1157) -- **creates IgnoredValidationIssue records**

**Proof of Concept**:
```bash
# Unauthenticated attacker can reassign any schedule to any employee
curl -X POST https://target/api/fix-wizard/apply \
  -H "Content-Type: application/json" \
  -d '{"action_type": "reassign", "target": {"schedule_id": 1, "new_employee_id": "E001"}}'

# Unauthenticated attacker can delete any schedule
curl -X POST https://target/api/fix-wizard/apply \
  -H "Content-Type: application/json" \
  -d '{"action_type": "unschedule", "target": {"schedule_id": 1}}'
```

**Evidence**: The existing dashboard routes (`daily_validation`, `weekly_validation`, `assign_supervisor_event`, etc. at lines 14-1025) also lack `@require_authentication()`, but the new Fix Wizard routes are uniquely dangerous because they accept POST requests that modify database state. This appears to be a systemic gap in the dashboard blueprint -- none of its routes have the decorator.

**Remediation**:
```python
# Option A: Decorate each route
@dashboard_bp.route('/fix-wizard')
@require_authentication()
def fix_wizard():
    ...

@dashboard_bp.route('/api/fix-wizard/apply', methods=['POST'])
@require_authentication()
def fix_wizard_apply():
    ...

# Option B (preferred): Apply to entire blueprint via before_request
@dashboard_bp.before_request
@require_authentication()
def dashboard_require_auth():
    pass
```

---

### CRT-02: AI Confirmation Bypass via `_confirmed` Flag Injection

**Severity**: Critical (CVSS 8.6)
**CWE**: CWE-807 (Reliance on Untrusted Inputs in a Security Decision)
**OWASP**: A01:2021 - Broken Access Control
**File**: `/home/elliot/flask-schedule-webapp/app/services/ai_assistant.py`, lines 534-543; `/home/elliot/flask-schedule-webapp/app/services/ai_tools.py`, multiple locations

**Description**: Destructive AI tool operations (delete schedules, bulk reschedule, time-off requests, etc.) use a `_confirmed` flag inside the tool `args` dict to determine whether to require user confirmation. The `confirm_action()` method in `ai_assistant.py` sets `args['_confirmed'] = True` before calling `execute_tool()`. However, nothing prevents the LLM from including `_confirmed: true` in its initial function call arguments, bypassing the confirmation dialog entirely.

The `_confirmed` flag is checked at 12+ locations (lines 1368, 1408, 1625, 1826, 2007, 2125, 2494, 3277, 3361, 3463 in `ai_tools.py`), and each one guards a destructive operation:
- `_tool_print_paperwork` (line 1368)
- `_tool_request_time_off` (line 1408)
- `_tool_remove_schedule` (line 1625)
- `_tool_bulk_reschedule_day` (line 1826)
- `_tool_reassign_employee_events` (line 2007)
- `_tool_auto_fill_unscheduled` (line 2125)
- `_tool_swap_schedules` (line 2494)
- `_tool_run_cpsat_scheduler` (new, line ~3702 via requires_confirmation in tool def)
- `_tool_log_event_outcome` (new, line ~3880 via requires_confirmation)
- `_tool_modify_scheduling_preference` (new, line ~3920 via requires_confirmation)

**Attack Scenario**: A prompt injection via user input or compromised AI context could instruct the LLM to include `"_confirmed": true` in its function call, executing destructive operations without user consent.

**Remediation**:
```python
# In ai_assistant.py confirm_action(), instead of setting _confirmed in args:
def confirm_action(self, confirmation_data):
    tool_name = confirmation_data.get('tool_name')
    args = confirmation_data.get('tool_args') or confirmation_data.get('args')
    if not tool_name:
        raise ValueError("Invalid confirmation data: missing tool_name")

    # Execute tool directly with server-side confirmation flag
    # NOT passed through args where LLM could set it
    result = self.tools.execute_tool(tool_name, args, confirmed=True)
    ...

# In ai_tools.py execute_tool():
def execute_tool(self, tool_name, args, confirmed=False):
    # Strip _confirmed from args to prevent LLM injection
    args.pop('_confirmed', None)
    tool_map[tool_name](args, confirmed=confirmed)

# In each tool method:
def _tool_remove_schedule(self, args, confirmed=False):
    if not confirmed:
        return {'requires_confirmation': True, ...}
```

---

### CRT-03: `CONDITION_CANCELED` String Passed to `.in_()` - Iterates Characters

**Severity**: Critical (CVSS 7.5)
**CWE**: CWE-704 (Incorrect Type Conversion or Cast)
**OWASP**: A04:2021 - Insecure Design
**File**: `/home/elliot/flask-schedule-webapp/app/services/ai_tools.py`, line 4030

**Description**: The `_tool_suggest_schedule_improvement` method passes a bare string `CONDITION_CANCELED` (value: `'Canceled'`) to SQLAlchemy's `.in_()` method, which expects an iterable of values. When a string is passed, Python iterates over its characters, producing `IN ('C', 'a', 'n', 'c', 'e', 'l', 'e', 'd')`. This means the filter matches events whose `condition` is any single character in "Canceled" -- which never matches real conditions but also fails to filter out canceled events.

**Affected Code**:
```python
# Line 4030 - WRONG: iterates characters of 'Canceled'
~Event.condition.in_(CONDITION_CANCELED) if hasattr(Event, 'condition') else True
```

**Impact**: The unscheduled events query returns canceled/expired events that should be filtered out, producing incorrect schedule improvement suggestions that include dead events.

**Remediation**:
```python
# Use INACTIVE_CONDITIONS tuple instead of CONDITION_CANCELED string
from app.constants import INACTIVE_CONDITIONS

events_in_range = self.db.query(Event).filter(
    Event.start_date >= start,
    Event.start_date <= end,
    Event.is_scheduled == False,
    ~Event.condition.in_(list(INACTIVE_CONDITIONS))
).all()
```

---

### CRT-04: Fix Wizard `apply_fix` Accepts Arbitrary `action_type` Without Allowlist

**Severity**: Critical (CVSS 8.1)
**CWE**: CWE-20 (Improper Input Validation)
**OWASP**: A03:2021 - Injection
**File**: `/home/elliot/flask-schedule-webapp/app/routes/dashboard.py`, lines 1109-1155; `/home/elliot/flask-schedule-webapp/app/services/fix_wizard.py`, lines 666-693

**Description**: The `/api/fix-wizard/apply` endpoint accepts `action_type` from user-supplied JSON and passes it directly to `FixWizardService.apply_fix()`. While the service does validate against `FixActionType` enum values, the route itself does no validation. More critically, the `target` dict is passed through without validation -- `schedule_id`, `new_employee_id`, `new_datetime`, and `core_event_ref` are all accepted as-is from the request body.

Combined with CRT-01 (no authentication), an attacker can:
1. Reassign any schedule to any employee by specifying arbitrary `schedule_id` and `new_employee_id`
2. Delete any schedule by specifying arbitrary `schedule_id` with action `unschedule`
3. Change any schedule's datetime by specifying arbitrary `schedule_id` and `new_datetime`

**Proof of Concept**:
```bash
# Move any schedule to any time
curl -X POST https://target/api/fix-wizard/apply \
  -H "Content-Type: application/json" \
  -d '{"action_type":"reschedule","target":{"schedule_id":42,"new_datetime":"2026-01-01T00:00:00"}}'
```

**Remediation**:
```python
@dashboard_bp.route('/api/fix-wizard/apply', methods=['POST'])
@require_authentication()
def fix_wizard_apply():
    data = flask_request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'error': 'No data provided'}), 400

    action_type = data.get('action_type')
    target = data.get('target')

    # Validate action_type against allowlist
    ALLOWED_ACTIONS = {'reassign', 'unschedule', 'reschedule', 'assign_supervisor', 'ignore'}
    if action_type not in ALLOWED_ACTIONS:
        return jsonify({'status': 'error', 'error': f'Invalid action_type: {action_type}'}), 400

    # Validate target fields based on action type
    if action_type == 'reassign':
        if not isinstance(target.get('schedule_id'), int):
            return jsonify({'status': 'error', 'error': 'Invalid schedule_id'}), 400
    # ... additional per-action validation
```

---

## High Findings

### HGH-01: Auto-Scheduler Routes Missing Authentication (Systemic)

**Severity**: High (CVSS 7.5)
**CWE**: CWE-306 (Missing Authentication for Critical Function)
**File**: `/home/elliot/flask-schedule-webapp/app/routes/auto_scheduler.py`

**Description**: While the auto_scheduler blueprint has `@require_authentication()` on some routes (lines 22, 1547, 1587, 1673, 1761), many state-changing routes lack it:

- `POST /auto-schedule/run` (line 82) -- runs the auto-scheduler
- `GET /auto-schedule/review` (line 166) -- review page
- `GET /auto-schedule/api/pending` (line 187) -- list pending schedules
- `PUT /auto-schedule/api/pending/<id>` (line 386) -- modify pending
- `DELETE /auto-schedule/api/pending/by-ref/<ref>` (line 429) -- delete pending
- `POST /auto-schedule/approve` (line 471) -- **approve and submit to external API**
- `POST /auto-schedule/approve-single/<id>` (line 932) -- approve single
- `POST /auto-schedule/mark-approved/<id>` (line 1229) -- mark as approved
- `POST /auto-schedule/reject` (line 1379) -- reject schedules

**Impact**: Unauthenticated users can trigger the auto-scheduler, approve/reject pending schedules, and submit schedules to external APIs.

**Remediation**: Apply `@require_authentication()` to all routes, or use `@auto_scheduler_bp.before_request` as a blanket guard.

---

### HGH-02: `completion_notes` Field Stored Without Sanitization (Stored XSS Risk)

**Severity**: High (CVSS 7.2)
**CWE**: CWE-79 (Improper Neutralization of Input During Web Page Generation)
**OWASP**: A03:2021 - Injection
**File**: `/home/elliot/flask-schedule-webapp/app/services/ai_tools.py`, line 3885 (`_tool_log_event_outcome`); `/home/elliot/flask-schedule-webapp/app/models/schedule.py`, new `completion_notes` column

**Description**: The new `completion_notes` field on the Schedule model accepts arbitrary text from the AI tool's `notes` parameter (line 3886: `schedule.completion_notes = notes`) without any sanitization or length validation. If this value is later rendered in a template without escaping, it creates a stored XSS vector.

The `notes` parameter originates from LLM-generated function call arguments, which can contain attacker-controlled content via prompt injection.

**Remediation**:
```python
# In _tool_log_event_outcome:
notes = args.get('notes', '')
if notes:
    # Sanitize and limit length
    notes = notes[:500]  # Reasonable limit
    schedule.completion_notes = notes
```
Ensure all template rendering of `completion_notes` uses Jinja2 auto-escaping (verify `{{ schedule.completion_notes }}` not `{{ schedule.completion_notes|safe }}`).

---

### HGH-03: Database Binary (scheduler.db) in Uncommitted Changes

**Severity**: High (CVSS 6.5)
**CWE**: CWE-200 (Exposure of Sensitive Information)
**OWASP**: A01:2021 - Broken Access Control
**File**: `/home/elliot/flask-schedule-webapp/instance/scheduler.db`

**Description**: The git diff shows `instance/scheduler.db` has changed from 1,462,272 to 2,842,624 bytes. This binary database file contains production schedule data, employee information, and potentially sensitive business data. It should never be committed to version control.

**Impact**: Anyone with repository access gains full read access to all employee schedules, names, time-off records, and business data.

**Remediation**:
1. Add `instance/scheduler.db` to `.gitignore` (verify it is already listed)
2. Run `git checkout -- instance/scheduler.db` to discard the change
3. If already committed in history, consider using `git filter-branch` or BFG Repo Cleaner

---

### HGH-04: Savepoint-Based Dry Run May Leak Side Effects

**Severity**: High (CVSS 6.8)
**CWE**: CWE-662 (Improper Synchronization)
**File**: `/home/elliot/flask-schedule-webapp/app/services/ai_tools.py`, lines 3755-3792 (`_tool_compare_schedulers`)

**Description**: The `compare_schedulers` tool runs both the greedy and CP-SAT schedulers inside SQLAlchemy savepoints, then rolls them back. However, the schedulers perform complex operations including:
- Querying and caching model state
- Potentially triggering SQLAlchemy relationship lazy loads
- Creating `SchedulerRunHistory` records
- Potentially calling external services (if `SYNC_ENABLED`)

If the scheduler triggers an autoflush before the savepoint rollback, or if an exception occurs between flush and rollback, partial state may persist. Additionally, SQLite does not support savepoints in the same way PostgreSQL does -- `begin_nested()` on SQLite may not isolate changes correctly.

**Remediation**:
```python
# Use explicit session isolation instead of savepoints
from sqlalchemy.orm import Session

def _tool_compare_schedulers(self, args):
    # Create a separate session that is always rolled back
    with Session(self.db.get_bind(), expire_on_commit=False) as temp_session:
        try:
            # Run scheduler with temp_session
            ...
        finally:
            temp_session.rollback()
```
Or flag the scheduler with a `dry_run=True` parameter that skips all writes.

---

### HGH-05: Fix Wizard `_apply_reschedule` Accepts Arbitrary Datetime Without Bounds

**Severity**: High (CVSS 6.5)
**CWE**: CWE-20 (Improper Input Validation)
**File**: `/home/elliot/flask-schedule-webapp/app/services/fix_wizard.py`, lines 764-783

**Description**: The `_apply_reschedule` method accepts `new_datetime` from user input and sets it directly on the schedule record without validating:
- Whether the datetime is within the event's valid period (start_date to due_date)
- Whether the datetime is in the future (not in the past)
- Whether the datetime is a valid business hour

```python
def _apply_reschedule(self, target: dict) -> dict:
    new_dt = datetime.fromisoformat(new_datetime_str)
    schedule.schedule_datetime = new_dt  # No validation
    self.db.commit()
```

**Impact**: An attacker (or a buggy client) could reschedule events to arbitrary dates, including past dates, dates outside event windows, or midnight.

**Remediation**:
```python
def _apply_reschedule(self, target: dict) -> dict:
    new_dt = datetime.fromisoformat(new_datetime_str)

    # Validate against event period
    event = self.db.query(self.Event).filter_by(
        project_ref_num=schedule.event_ref_num
    ).first()
    if event:
        if not (event.start_datetime.date() <= new_dt.date() <= event.due_datetime.date()):
            return {'success': False, 'message': 'New datetime outside event period'}

    # Validate not in the past
    if new_dt.date() < date.today():
        return {'success': False, 'message': 'Cannot reschedule to a past date'}

    schedule.schedule_datetime = new_dt
    self.db.commit()
```

---

## Medium Findings

### MED-01: CSRF Protection Gap on Dashboard POST Endpoints

**Severity**: Medium (CVSS 5.4)
**CWE**: CWE-352 (Cross-Site Request Forgery)
**OWASP**: A01:2021 - Broken Access Control
**File**: `/home/elliot/flask-schedule-webapp/app/routes/dashboard.py`

**Description**: While the new Fix Wizard JavaScript correctly sends `X-CSRF-Token` headers on POST requests (fix-wizard.js lines 244, 284), the existing dashboard POST endpoints (`/api/validation/ignore`, `/api/validation/unignore`, `/api/validation/assign-supervisor`) do not verify CSRF tokens because Flask-WTF's CSRF protection may not be enforced on all blueprint routes.

Additionally, in `DevelopmentConfig`, `WTF_CSRF_ENABLED` defaults to Flask-WTF's default (True), but `TestingConfig` explicitly disables it (line 121). Verify that the development configuration does not inadvertently disable CSRF.

**Remediation**: Ensure `csrf.protect()` is called globally in `create_app()`, and verify that the `csrf` extension from `app/extensions.py` covers all blueprints. Add CSRF token verification tests.

---

### MED-02: Auto-Scheduler Approval Bypasses Event Period Validation for Supervisor Events

**Severity**: Medium (CVSS 5.3)
**CWE**: CWE-284 (Improper Access Control)
**File**: `/home/elliot/flask-schedule-webapp/app/routes/auto_scheduler.py`, line 717

**Description**: The approval flow now skips event period validation for Supervisor events:

```python
if event.event_type != 'Supervisor' and not (event.start_datetime <= start_datetime <= event.due_datetime):
```

While the comment explains the business rationale (Supervisor events match their paired Core event's date, not their own API-reported period), this creates a validation gap where a Supervisor event could be approved with any datetime, including dates far outside any reasonable window.

**Remediation**: Add a softer validation for Supervisor events that checks the Core event's date range instead:
```python
if event.event_type == 'Supervisor':
    # Validate against paired Core event's period instead
    core_event = find_paired_core_event(event)
    if core_event and not (core_event.start_datetime <= start_datetime <= core_event.due_datetime):
        # Log warning but allow (or reject)
        ...
elif not (event.start_datetime <= start_datetime <= event.due_datetime):
    # Reject non-Supervisor events outside period
    ...
```

---

### MED-03: `_apply_reassign` Does Not Re-Validate Constraints Before Committing

**Severity**: Medium (CVSS 5.0)
**CWE**: CWE-754 (Improper Check for Unusual or Exceptional Conditions)
**File**: `/home/elliot/flask-schedule-webapp/app/services/fix_wizard.py`, lines 695-718

**Description**: When the Fix Wizard reassigns a schedule to a new employee, it directly updates `schedule.employee_id` without running the constraint validator. While the options were generated with constraint-checked employees, a TOCTOU (time-of-check/time-of-use) race exists: between generating options and applying the fix, another user could have scheduled that employee elsewhere, creating a conflict.

```python
def _apply_reassign(self, target: dict) -> dict:
    schedule.employee_id = new_employee_id  # No re-validation
    self.db.commit()
```

**Remediation**:
```python
def _apply_reassign(self, target: dict) -> dict:
    from app.services.constraint_validator import ConstraintValidator
    validator = ConstraintValidator(self.db, self.models)
    event = self.db.query(self.Event).filter_by(project_ref_num=schedule.event_ref_num).first()
    new_emp = self.db.query(self.Employee).get(new_employee_id)
    result = validator.validate_assignment(event, new_emp, schedule.schedule_datetime)
    if not result.is_valid:
        return {'success': False, 'message': f'Constraint violation: {result.violations[0].message}'}
    schedule.employee_id = new_employee_id
    self.db.commit()
```

---

### MED-04: AI Confirmation Data Passed Unvalidated from Client

**Severity**: Medium (CVSS 5.3)
**CWE**: CWE-20 (Improper Input Validation)
**File**: `/home/elliot/flask-schedule-webapp/app/routes/ai_routes.py`, lines 106-175; `/home/elliot/flask-schedule-webapp/app/static/js/components/ai-assistant.js`, lines 278-312

**Description**: The `/api/ai/confirm` endpoint receives `confirmation_data` from the client, which contains `tool_name` and `tool_args`. This data was originally generated server-side by the AI tool, but it round-trips through the browser -- the client-side JavaScript stores it and sends it back verbatim. A malicious user could modify `confirmation_data` in the browser's DevTools to execute any AI tool with arbitrary arguments.

```javascript
// ai-assistant.js line 290 - sends confirmation_data back to server
body: JSON.stringify({ confirmation_data: confirmationData })
```

```python
# ai_routes.py line 160 - executes whatever tool_name and args are in confirmation_data
result = assistant.confirm_action(confirmation_data)
```

**Attack Scenario**: User modifies `confirmationData` in browser to `{"tool_name": "remove_schedule", "tool_args": {"schedule_id": 999, "_confirmed": true}}`.

**Remediation**: Sign the `confirmation_data` server-side with HMAC before sending to client, and verify the signature on return:
```python
import hmac, hashlib, json

def sign_confirmation(data, secret_key):
    payload = json.dumps(data, sort_keys=True)
    sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {**data, '_sig': sig}

def verify_confirmation(data, secret_key):
    sig = data.pop('_sig', '')
    payload = json.dumps(data, sort_keys=True)
    expected = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)
```

---

### MED-05: Excessive Error Detail Exposure in API Responses

**Severity**: Medium (CVSS 4.3)
**CWE**: CWE-209 (Generation of Error Message Containing Sensitive Information)
**OWASP**: A09:2021 - Security Logging and Monitoring Failures
**Files**: Multiple endpoints

**Description**: Several new endpoints return raw exception messages to the client:

- `/home/elliot/flask-schedule-webapp/app/routes/dashboard.py` line 1099: `return jsonify({'status': 'error', 'error': str(e)}), 500`
- `/home/elliot/flask-schedule-webapp/app/routes/ai_routes.py` line 173: `'details': str(e)`
- `/home/elliot/flask-schedule-webapp/app/services/fix_wizard.py` line 693: `return {'success': False, 'message': str(e)}`

Exception messages may contain database schema details, file paths, SQL queries, or internal state.

**Remediation**:
```python
except Exception as e:
    current_app.logger.error(f"Fix wizard error: {e}", exc_info=True)
    return jsonify({'status': 'error', 'error': 'An internal error occurred'}), 500
```

---

### MED-06: CDN Integrity Hash Mismatch Risk in Fix Wizard Template

**Severity**: Medium (CVSS 4.0)
**CWE**: CWE-353 (Missing Support for Integrity Check)
**File**: `/home/elliot/flask-schedule-webapp/app/templates/dashboard/fix_wizard.html`, lines 6-7

**Description**: The fix_wizard.html template loads Font Awesome from cdnjs with an SRI hash:
```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
    integrity="sha384-iw3OoTErCYJJB9mCa8LNS2hbsQ7M3C0EpIsO/H5+EGAkPGc6rk+V8i04oW/K5xq0" crossorigin="anonymous" />
```

The integrity hash format looks truncated/incorrect (SRI hashes for this resource should be longer). If the hash is wrong, the browser will either block the resource (good but breaks UI) or the integrity check is silently ignored (bad).

**Remediation**: Regenerate the SRI hash from the actual CDN resource:
```bash
curl -s https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css | openssl dgst -sha384 -binary | openssl enc -base64
```
Or preferably, use the same CDN resource version and SRI hash that `base.html` uses for consistency.

---

## Low Findings

### LOW-01: `showError` Function Defined Twice in fix-wizard.js

**Severity**: Low (CVSS 2.0)
**CWE**: CWE-561 (Dead Code)
**File**: `/home/elliot/flask-schedule-webapp/app/static/js/pages/fix-wizard.js`, lines 35 and 325

**Description**: Two `function showError` declarations exist in the same IIFE scope. The second definition (line 325) silently overwrites the first (line 35). The first version creates a dismissible alert element; the second replaces the entire wizard root with an error message. This means the first definition is dead code and the error behavior may differ from what was intended.

**Remediation**: Remove the first definition or rename one. The second (full-page error) appears intentional for fatal errors, while the first (toast-style) would be better for non-fatal errors. Consider renaming one to `showFatalError`.

---

### LOW-02: `_parse_direction` Defaults to 1.5x Multiplier on Unknown Input

**Severity**: Low (CVSS 3.1)
**CWE**: CWE-1188 (Insecure Default Initialization of Resource)
**File**: `/home/elliot/flask-schedule-webapp/app/services/constraint_modifier.py`, lines 267-281

**Description**: The `_parse_direction` method falls back to `return 1.5` when no direction keyword matches. This means any unrecognized input (typos, LLM hallucinations, adversarial prompts) silently increases the weight by 50%.

```python
def _parse_direction(self, direction):
    direction_lower = direction.lower().strip()
    if direction_lower in self.DIRECTION_MAP:
        return self.DIRECTION_MAP[direction_lower]
    for keyword, mult in self.DIRECTION_MAP.items():
        if keyword in direction_lower:
            return mult
    return 1.5  # Silent default: increases weight
```

**Remediation**: Return an error or default to `1.0` (no change) for unrecognized directions:
```python
    return 1.0  # No change on unrecognized input
```

---

### LOW-03: Migration Uses `nullable=True` But Model Uses `server_default`

**Severity**: Low (CVSS 2.0)
**CWE**: CWE-1164 (Irrelevant Code)
**Files**: `/home/elliot/flask-schedule-webapp/migrations/versions/6a96501dd084_add_schedule_outcomes.py`; `/home/elliot/flask-schedule-webapp/app/models/schedule.py`

**Description**: The model defines `was_completed = db.Column(db.Boolean, default=False, server_default=sa.text('0'))` with a `server_default`, but the migration creates the column as `sa.Column('was_completed', sa.Boolean(), nullable=True)` without a `server_default`. Existing rows will have `NULL` instead of `False`/`0`, which could cause unexpected behavior when querying `Schedule.was_completed == False` (NULL != False in SQL).

**Remediation**: Add `server_default` to the migration:
```python
def upgrade():
    op.add_column('schedules', sa.Column('was_completed', sa.Boolean(),
                  nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('was_swapped', sa.Boolean(),
                  nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('was_no_show', sa.Boolean(),
                  nullable=True, server_default=sa.text('0')))
```

---

## Positive Security Observations

The following security improvements in this changeset are commendable:

1. **CSRF Header Standardization** (`daily-view.js`, `auto_scheduler_main.html`): Consistent use of `X-CSRF-Token` header across all JavaScript POST requests. This aligns with the canonical header established in Sprint 1.

2. **Past-Date Validation** (`constraint_validator.py`, `scheduling_engine.py`): New `_check_past_date` constraint and 3-day scheduling buffer prevent scheduling events in the past, adding defense-in-depth.

3. **XSS Protection in Fix Wizard** (`fix-wizard.js`): Consistent use of `escapeHtml()` for all user-facing data, and `data-action` delegation pattern instead of inline event handlers.

4. **AI Confirmation Flow** (`ai-assistant.js`, `ai_routes.py`): The UI-level confirmation dialog for destructive AI operations is a good UX pattern, even though the server-side implementation needs the signing improvement noted in MED-04.

5. **Schedule Preservation Across Refresh** (`database_refresh_service.py`): The schedule restoration logic correctly checks for canceled events and avoids duplicates.

6. **INACTIVE_CONDITIONS Constant Usage** (`api.py`, `database_refresh_service.py`, `cpsat_scheduler.py`): Proper use of the tuple constant with `.in_()` in most locations.

7. **Date-Only Comparison Fix** (`scheduling_engine.py` line 3496): Changing datetime-to-datetime comparison to date-to-date prevents false rejections from time-component mismatches.

---

## Remediation Priority Matrix

| Finding | Severity | Effort | Priority |
|---------|----------|--------|----------|
| CRT-01  | Critical | Low    | P0 - Immediate |
| CRT-02  | Critical | Medium | P0 - Immediate |
| CRT-03  | Critical | Low    | P0 - Immediate |
| CRT-04  | Critical | Low    | P0 - Immediate |
| HGH-01  | High     | Low    | P1 - This sprint |
| HGH-02  | High     | Low    | P1 - This sprint |
| HGH-03  | High     | Low    | P1 - This sprint |
| HGH-04  | High     | Medium | P1 - This sprint |
| HGH-05  | High     | Low    | P1 - This sprint |
| MED-01  | Medium   | Medium | P2 - Next sprint |
| MED-02  | Medium   | Low    | P2 - Next sprint |
| MED-03  | Medium   | Medium | P2 - Next sprint |
| MED-04  | Medium   | Medium | P2 - Next sprint |
| MED-05  | Medium   | Low    | P2 - Next sprint |
| MED-06  | Medium   | Low    | P2 - Next sprint |
| LOW-01  | Low      | Low    | P3 - Backlog |
| LOW-02  | Low      | Low    | P3 - Backlog |
| LOW-03  | Low      | Low    | P3 - Backlog |

---

## Testing Recommendations

1. **Authentication Tests**: Add pytest cases verifying that unauthenticated requests to Fix Wizard and auto-scheduler endpoints return 401/302.
2. **CSRF Tests**: Add cases verifying that POST requests without CSRF tokens are rejected.
3. **Input Validation Tests**: Test Fix Wizard with invalid `action_type`, non-existent `schedule_id`, past `new_datetime`, and XSS payloads in `completion_notes`.
4. **AI Confirmation Bypass Test**: Craft an AI tool call with `_confirmed: true` in args and verify it is stripped before execution.
5. **`.in_()` Bug Test**: Unit test `_tool_suggest_schedule_improvement` with canceled events to verify they are properly filtered.

---

**Report generated**: 2026-02-18
**Classification**: Internal - Security Sensitive
**Next review**: After remediation of P0 findings
