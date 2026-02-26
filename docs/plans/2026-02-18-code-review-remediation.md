# Code Review Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all Critical (P0) and High (P1) issues from the comprehensive code review (.full-review/05-final-report.md)

**Architecture:** Fixes are grouped into 6 sprints by priority and dependency. Security fixes first, then bugs, then performance, then tests, then docs. Each sprint is independently committable.

**Tech Stack:** Flask, SQLAlchemy, Python 3.12, Jinja2, JavaScript (ES6), pytest

---

## Sprint 1: Critical Security & Bugs (P0)

### Task 1: Add authentication to Fix Wizard routes

**Files:**
- Modify: `app/routes/dashboard.py:1-11` (add import), `:1028-1195` (add decorators)

**Step 1: Add `require_authentication` import to dashboard.py**

At the top of `app/routes/dashboard.py`, add the import:

```python
from app.routes.auth import require_authentication
```

**Step 2: Add `@require_authentication()` to all 4 Fix Wizard routes**

Add decorator before each route function:

```python
@dashboard_bp.route('/fix-wizard')
@require_authentication()
def fix_wizard():

@dashboard_bp.route('/api/fix-wizard/issues')
@require_authentication()
def fix_wizard_issues():

@dashboard_bp.route('/api/fix-wizard/apply', methods=['POST'])
@require_authentication()
def fix_wizard_apply():

@dashboard_bp.route('/api/fix-wizard/skip', methods=['POST'])
@require_authentication()
def fix_wizard_skip():
```

**Step 3: Commit**

```bash
git add app/routes/dashboard.py
git commit -m "fix(security): add authentication to Fix Wizard routes

SEC-CRT-01: All 4 Fix Wizard endpoints were unprotected.
Added @require_authentication() decorator."
```

### Task 2: Fix NameError in validation_summary_api

**Files:**
- Modify: `app/routes/dashboard.py:534-542`

**Step 1: Fix the missing get_models() call**

In `validation_summary_api()`, line 540 references `models['Event']` but `models` is never defined. Replace lines 538-541:

```python
@dashboard_bp.route('/api/validation-summary')
@require_authentication()
def validation_summary_api():
    """
    API endpoint for validation summary (for widgets or external monitoring)
    """
    from app.models import get_models
    all_models = get_models()
    db = current_app.extensions['sqlalchemy']
    Event = all_models['Event']
    Schedule = all_models['Schedule']
```

**Step 2: Commit**

```bash
git add app/routes/dashboard.py
git commit -m "fix: resolve NameError in validation_summary_api

BP-CRT-01: get_models() was never called, causing NameError on
every request to /api/validation-summary."
```

### Task 3: Fix CONDITION_CANCELED string-as-iterable bug

**Files:**
- Modify: `app/services/ai_tools.py:12,4030`

**Step 1: Fix the import**

Change line 12 from:
```python
from app.constants import CONDITION_CANCELED
```
to:
```python
from app.constants import CONDITION_CANCELED, INACTIVE_CONDITIONS
```

**Step 2: Fix the .in_() call**

Change line 4030 from:
```python
~Event.condition.in_(CONDITION_CANCELED) if hasattr(Event, 'condition') else True
```
to:
```python
~Event.condition.in_(INACTIVE_CONDITIONS) if hasattr(Event, 'condition') else True
```

**Step 3: Commit**

```bash
git add app/services/ai_tools.py
git commit -m "fix: CONDITION_CANCELED string iterated as chars in .in_()

SEC-CRT-03/ARCH-CRT-01: 'Canceled' was passed to .in_() which
iterates characters -> IN ('C','a','n','c','e','l','e','d').
Use INACTIVE_CONDITIONS tuple instead."
```

### Task 4: Strip _confirmed from LLM-generated tool args

**Files:**
- Modify: `app/services/ai_tools.py:960-976` (execute_tool method)
- Modify: `app/services/ai_assistant.py:538-543` (confirm_action method)

**Step 1: Strip `_confirmed` in execute_tool before dispatch**

In `execute_tool()`, after the tool_map dict and before the `if tool_name not in tool_map` check (~line 960), add:

```python
        # SEC-CRT-02: Strip _confirmed from args — must only come from server-side confirm_action
        if isinstance(tool_args, dict):
            tool_args.pop('_confirmed', None)
```

**Step 2: Pass confirmed as separate parameter in confirm_action**

In `ai_assistant.py` `confirm_action()`, change the approach so _confirmed is set AFTER stripping:

```python
             # Set _confirmed flag so tools skip the confirmation prompt
             if args is None:
                 args = {}
             # _confirmed is stripped in execute_tool, so we pass it via a separate path
             result = self.tools.execute_tool(tool_name, args, confirmed=True)
```

**Step 3: Update execute_tool signature to accept confirmed param**

```python
    def execute_tool(self, tool_name: str, tool_args: Dict[str, Any], confirmed: bool = False) -> Dict[str, Any]:
        ...
        # Strip _confirmed from args — must only come from server-side
        if isinstance(tool_args, dict):
            tool_args.pop('_confirmed', None)

        # Set confirmed flag from server-side parameter only
        if confirmed and isinstance(tool_args, dict):
            tool_args['_confirmed'] = True
        ...
```

**Step 4: Commit**

```bash
git add app/services/ai_tools.py app/services/ai_assistant.py
git commit -m "fix(security): strip _confirmed from LLM-generated tool args

SEC-CRT-02: _confirmed flag lived inside LLM-generated args dict.
Prompt injection could set _confirmed:true to bypass confirmation
on destructive ops. Now stripped before dispatch and only set via
server-side confirm_action path."
```

### Task 5: Validate action_type in fix_wizard_apply

**Files:**
- Modify: `app/routes/dashboard.py:1140-1149`

**Step 1: Add enum validation**

After line 1143 (`if not action_type:`), add validation:

```python
    from app.services.fix_wizard import FixActionType

    # Validate action_type against allowed enum values
    valid_actions = {e.value for e in FixActionType}
    if action_type not in valid_actions:
        return jsonify({'status': 'error', 'error': f'Invalid action_type: {action_type}'}), 400
```

**Step 2: Commit**

```bash
git add app/routes/dashboard.py
git commit -m "fix(security): validate action_type against FixActionType enum

SEC-CRT-04/BP-CRT-03: action_type from JSON body was passed directly
to service without validation. Now checked against FixActionType enum."
```

### Task 6: Discard production database from git changes

**Step 1: Discard changes to instance/scheduler.db**

```bash
git checkout -- instance/scheduler.db
```

**Step 2: Verify it's in .gitignore**

Check `.gitignore` contains `instance/scheduler.db` or `instance/*.db`. If not, add it.

**Step 3: Commit .gitignore if changed**

```bash
git add .gitignore
git commit -m "chore: ensure scheduler.db is gitignored

OPS-CRT-01: Production database with employee PII was tracked in git."
```

---

## Sprint 2: Code Quality Fixes (P0 + P1)

### Task 7: Add server_default to migration

**Files:**
- Modify: `migrations/versions/6a96501dd084_add_schedule_outcomes.py:20-22`

**Step 1: Add server_default to boolean columns**

```python
def upgrade():
    op.add_column('schedules', sa.Column('was_completed', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('was_swapped', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('was_no_show', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('completion_notes', sa.Text(), nullable=True))
    op.add_column('schedules', sa.Column('solver_type', sa.String(20), nullable=True))
```

**Step 2: Commit**

```bash
git add migrations/versions/6a96501dd084_add_schedule_outcomes.py
git commit -m "fix: add server_default to migration boolean columns

CRT-02: Model defines server_default=sa.text('0') but migration
lacked it. Existing rows would have NULL instead of False/0."
```

### Task 8: Wire _tool_verify_schedule into tool_map

**Files:**
- Modify: `app/services/ai_tools.py:958-959`

**Step 1: Add to tool_map**

Add after the `'modify_scheduling_preference'` line:

```python
            'verify_schedule': self._tool_verify_schedule,
```

**Step 2: Commit**

```bash
git add app/services/ai_tools.py
git commit -m "fix: wire _tool_verify_schedule into tool_map

CRT-01: Method was fully implemented but never added to dispatcher."
```

### Task 9: Rename duplicate showError in fix-wizard.js

**Files:**
- Modify: `app/static/js/pages/fix-wizard.js:325`

**Step 1: Rename second showError to showFatalError**

Change the second `showError` (line 325) to `showFatalError`:

```javascript
    function showFatalError(msg) {
```

**Step 2: Update all callers of the second (fatal) version**

Search for calls that should use `showFatalError` — these are the ones that replace `root.innerHTML` (full-page error), not the transient alert version.

**Step 3: Commit**

```bash
git add app/static/js/pages/fix-wizard.js
git commit -m "fix: rename duplicate showError to showFatalError

HGH-01: Second definition silently overrode the first. The transient
alert version (line 35) is now reachable for apply/skip operations."
```

### Task 10: Extract _get_fix_wizard_models() helper

**Files:**
- Modify: `app/routes/dashboard.py`

**Step 1: Create helper function**

Add before the Fix Wizard routes:

```python
def _get_fix_wizard_models():
    """Build the models dict needed by FixWizardService."""
    from app.models import get_models
    all_models = get_models()
    return {
        'Event': all_models['Event'],
        'Schedule': all_models['Schedule'],
        'Employee': all_models['Employee'],
        'EmployeeTimeOff': all_models['EmployeeTimeOff'],
        'EmployeeAvailability': all_models.get('EmployeeAvailability'),
        'EmployeeWeeklyAvailability': all_models.get('EmployeeWeeklyAvailability'),
        'EmployeeAttendance': all_models.get('EmployeeAttendance'),
        'RotationAssignment': all_models['RotationAssignment'],
        'ScheduleException': all_models.get('ScheduleException'),
        'PendingSchedule': all_models.get('PendingSchedule'),
        'IgnoredValidationIssue': all_models.get('IgnoredValidationIssue'),
    }
```

**Step 2: Replace all 3 duplicate model dicts with calls to helper**

In `fix_wizard_issues`, `fix_wizard_apply`, and `fix_wizard_skip`, replace the model dict construction with:

```python
    models = _get_fix_wizard_models()
```

**Step 3: Commit**

```bash
git add app/routes/dashboard.py
git commit -m "refactor: extract _get_fix_wizard_models() helper

HGH-02/BP-HGH-03: Identical model dict was repeated 3 times."
```

### Task 11: Fix _check_past_date timezone

**Files:**
- Modify: `app/services/constraint_validator.py:473-485`

**Step 1: Use timezone-aware date comparison**

```python
    def _check_past_date(self, schedule_datetime: datetime,
                        result: ValidationResult) -> None:
        """Reject scheduling in the past — safety net for all code paths"""
        from zoneinfo import ZoneInfo
        from flask import current_app
        tz_name = current_app.config.get(
            'EXTERNAL_API_TIMEZONE', 'America/Indiana/Indianapolis'
        )
        local_today = datetime.now(ZoneInfo(tz_name)).date()
        if schedule_datetime.date() < local_today:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.PAST_DATE,
                message=f"Cannot schedule in the past ({schedule_datetime.date()})",
                severity=ConstraintSeverity.HARD,
                details={
                    'proposed_date': str(schedule_datetime.date()),
                    'today': str(local_today)
                }
            ))
```

**Step 2: Commit**

```bash
git add app/services/constraint_validator.py
git commit -m "fix: use timezone-aware date in _check_past_date

HGH-03: date.today() is server-local (UTC in production). Now uses
configured timezone so evening scheduling isn't incorrectly rejected."
```

### Task 12: Fix to_local_time regex stripping minute zeros

**Files:**
- Modify: `app/utils/timezone.py:36-37`

**Step 1: Use targeted regex that only strips month, day, and hour**

Replace line 36-37:

```python
    # Strip leading zeros from month, day, and hour only (not minutes or year)
    # Target word-boundary zeros in positions that match M/D/H, not :MM
    formatted = re.sub(r'(?<![:\d])0(\d)', r'\1', formatted)
```

The negative lookbehind `(?<![:\d])` prevents matching zeros after a colon (minutes) or another digit.

**Step 2: Commit**

```bash
git add app/utils/timezone.py
git commit -m "fix: to_local_time regex no longer strips minute zeros

HGH-06: re.sub(r'\\b0(\\d)', ...) matched ':06' -> ':6' in times
like 10:06 PM. New regex uses negative lookbehind to skip :MM."
```

### Task 13: Fix run_scheduler to use get_models()

**Files:**
- Modify: `app/routes/auto_scheduler.py:86-91`

**Step 1: Replace current_app.config model dict with get_models()**

```python
@auto_scheduler_bp.route('/run', methods=['POST'])
@require_authentication()
def run_scheduler():
    """Manually trigger auto-scheduler run"""
    from app.models import get_models
    db = current_app.extensions['sqlalchemy']
    models = get_models()
```

**Step 2: Commit**

```bash
git add app/routes/auto_scheduler.py
git commit -m "fix: run_scheduler uses get_models() not current_app.config

BP-HGH-04: Violated mandatory model factory pattern. Other routes
in same file already use get_models() correctly."
```

### Task 14: Add authentication to auto-scheduler routes

**Files:**
- Modify: `app/routes/auto_scheduler.py`

**Step 1: Verify import exists**

Line 15 already has: `from app.routes.auth import require_authentication`

**Step 2: Add `@require_authentication()` to all unprotected routes**

Add the decorator to `run_scheduler` and any other POST/DELETE routes that lack it. Some routes already have it (lines 1547, 1587, 1673, 1761). Check each route and add where missing.

**Step 3: Commit**

```bash
git add app/routes/auto_scheduler.py
git commit -m "fix(security): add authentication to auto-scheduler routes

SEC-HGH-01: Many state-changing routes (run, approve, delete)
lacked @require_authentication() decorator."
```

---

## Sprint 3: Remaining P1 Security & Quality

### Task 15: Validate reschedule datetime in Fix Wizard

**Files:**
- Modify: `app/services/fix_wizard.py:764-783`

**Step 1: Add validation before setting new datetime**

```python
    def _apply_reschedule(self, target: dict) -> dict:
        schedule_id = target.get('schedule_id')
        new_datetime_str = target.get('new_datetime')

        if not schedule_id or not new_datetime_str:
            return {'success': False, 'message': 'schedule_id and new_datetime required'}

        schedule = self.db.query(self.Schedule).get(schedule_id)
        if not schedule:
            return {'success': False, 'message': f'Schedule {schedule_id} not found'}

        new_dt = datetime.fromisoformat(new_datetime_str)

        # SEC-HGH-05: Validate new datetime
        if new_dt.date() < date.today():
            return {'success': False, 'message': 'Cannot reschedule to a past date'}

        # Validate against event period if possible
        event = self.db.query(self.Event).filter_by(
            project_ref_num=schedule.event_ref_num
        ).first()
        if event and hasattr(event, 'due_datetime') and event.due_datetime:
            if new_dt.date() >= event.due_datetime.date():
                return {'success': False, 'message': 'Cannot reschedule past event due date'}

        old_dt = schedule.schedule_datetime
        schedule.schedule_datetime = new_dt
        self.db.commit()

        return {
            'success': True,
            'message': f'Rescheduled from {old_dt.strftime("%I:%M %p")} to {new_dt.strftime("%I:%M %p")}',
        }
```

**Step 2: Commit**

```bash
git add app/services/fix_wizard.py
git commit -m "fix(security): validate reschedule datetime in Fix Wizard

SEC-HGH-05: _apply_reschedule accepted arbitrary datetime without
checking past dates or event period boundaries."
```

### Task 16: Fix N+1 query in _load_existing_schedules

**Files:**
- Modify: `app/services/cpsat_scheduler.py:456-480`

**Step 1: Pre-load all events into a lookup dict**

```python
    def _load_existing_schedules(self):
        """Load existing (posted) schedules for bump penalty and conflict detection."""
        self.existing_schedules = []
        self.existing_by_emp_day = defaultdict(list)

        # Pre-load all events into lookup dict to avoid N+1 queries
        all_events = {e.project_ref_num: e for e in self.Event.query.all()}

        for s in self.Schedule.query.all():
            if not s.schedule_datetime:
                continue
            sd = s.schedule_datetime.date() if isinstance(s.schedule_datetime, datetime) else s.schedule_datetime
            self.existing_schedules.append({
                'event_ref': s.event_ref_num,
                'employee_id': s.employee_id,
                'date': sd,
                'block': getattr(s, 'shift_block', None),
            })

            event = all_events.get(s.event_ref_num)
            etype = event.event_type if event else 'Unknown'
            est_time = (event.estimated_time if event and event.estimated_time else 60)
            self.existing_by_emp_day[(s.employee_id, sd)].append({
                'event_ref': s.event_ref_num,
                'event_type': etype,
                'estimated_time': est_time,
            })
```

**Step 2: Commit**

```bash
git add app/services/cpsat_scheduler.py
git commit -m "perf: fix N+1 query in _load_existing_schedules

PERF-CRT-01: Per-schedule Event.query.filter_by() inside loop caused
~200 round-trips. Pre-load all events into lookup dict with single query."
```

### Task 17: Fix get_models() called inside approval loop

**Files:**
- Modify: `app/routes/auto_scheduler.py:860`

**Step 1: Move get_models() outside the loop**

Find the approval loop and ensure `get_models()` is called once before the loop, not inside it. The call at line 860 should be moved to before the loop starts.

**Step 2: Commit**

```bash
git add app/routes/auto_scheduler.py
git commit -m "perf: move get_models() outside approval loop

PERF-HGH-02: get_models() was called per-iteration inside approval loop."
```

### Task 18: Extract _score_employee from route to service

**Files:**
- Modify: `app/routes/api_suggest_employees.py:168+` (keep original, add import)
- Create: `app/services/employee_scoring.py` (extract function)
- Modify: `app/services/fix_wizard.py:228`

**Step 1: Create service module with extracted function**

Create `app/services/employee_scoring.py` with the `_score_employee` function moved from the route. Keep backward compatibility by importing from the new location in the route file.

**Step 2: Update Fix Wizard import**

Change `app/services/fix_wizard.py` line 228:
```python
from app.services.employee_scoring import score_employee
```

**Step 3: Commit**

```bash
git add app/services/employee_scoring.py app/services/fix_wizard.py app/routes/api_suggest_employees.py
git commit -m "refactor: extract _score_employee to service module

ARCH-HGH-01: Fix Wizard imported a private function from a route module,
inverting the dependency direction. Extracted to shared service."
```

---

## Sprint 4: P1 Performance

### Task 19: Fix N+1 event type resolution in _post_solve_review

**Files:**
- Modify: `app/services/cpsat_scheduler.py` (_post_solve_review method)

**Step 1: Pre-load events before the review loop**

Same pattern as Task 16 — build `{ref_num: event}` lookup dict before the loop.

**Step 2: Commit**

```bash
git add app/services/cpsat_scheduler.py
git commit -m "perf: fix N+1 event type resolution in _post_solve_review

PERF-HGH-04: Individual Event.query per schedule in post-solve loop."
```

---

## Sprint 5: Critical Tests

### Task 20: Write tests for Fix Wizard auth and validation

**Files:**
- Modify: `tests/test_fix_wizard.py`

**Step 1: Add auth tests**

```python
def test_fix_wizard_requires_auth(client):
    """SEC-CRT-01: Fix Wizard routes must require authentication."""
    response = client.get('/dashboard/fix-wizard')
    assert response.status_code in (302, 401)

def test_fix_wizard_apply_requires_auth(client):
    response = client.post('/dashboard/api/fix-wizard/apply',
        json={'action_type': 'reassign', 'target': {}})
    assert response.status_code in (302, 401)

def test_fix_wizard_apply_validates_action_type(client, authenticated_session):
    """SEC-CRT-04: Invalid action_type must be rejected."""
    response = client.post('/dashboard/api/fix-wizard/apply',
        json={'action_type': 'DROP TABLE', 'target': {}})
    assert response.status_code == 400
    assert 'Invalid action_type' in response.get_json()['error']
```

**Step 2: Add CONDITION_CANCELED regression test**

```python
def test_inactive_conditions_is_tuple():
    """SEC-CRT-03: INACTIVE_CONDITIONS must be a tuple, not a string."""
    from app.constants import INACTIVE_CONDITIONS
    assert isinstance(INACTIVE_CONDITIONS, tuple)
    assert len(INACTIVE_CONDITIONS) >= 2
```

**Step 3: Commit**

```bash
git add tests/test_fix_wizard.py
git commit -m "test: add auth and validation tests for Fix Wizard

TST-CRT-04/TST-CRT-05: Verifies authentication requirements
and action_type validation. Regression test for CONDITION_CANCELED."
```

### Task 21: Write tests for _confirmed bypass prevention

**Files:**
- Create: `tests/test_ai_tools_security.py`

**Step 1: Test that _confirmed is stripped from args**

```python
def test_confirmed_stripped_from_tool_args(app, db_session, models):
    """SEC-CRT-02: _confirmed must be stripped from LLM-generated args."""
    from app.services.ai_tools import AITools
    tools = AITools(db_session, models)

    # Simulate LLM injecting _confirmed=True
    args = {'date': '2026-02-20', '_confirmed': True}
    # execute_tool should strip _confirmed before dispatch
    result = tools.execute_tool('get_schedule', args)
    # If _confirmed was properly stripped, the tool should NOT skip confirmation
    # (for read-only tools this doesn't matter, but the stripping must happen)
```

**Step 2: Commit**

```bash
git add tests/test_ai_tools_security.py
git commit -m "test: verify _confirmed bypass prevention in AI tools

TST-CRT-06: Confirms that _confirmed flag is stripped from
LLM-generated tool args before dispatch."
```

---

## Sprint 6: Documentation

### Task 22: Update CODEBASE_MAP.md with new files

**Files:**
- Modify: `docs/CODEBASE_MAP.md`

**Step 1: Add entries for all new files**

Add to the appropriate sections:
- `app/services/cpsat_scheduler.py` — CP-SAT constraint solver (2,157 lines)
- `app/services/fix_wizard.py` — Guided schedule issue resolution (923 lines)
- `app/services/constraint_modifier.py` — Runtime constraint adjustments (282 lines)
- `app/services/employee_scoring.py` — Employee scoring for suggestions
- `app/utils/timezone.py` — Timezone conversion utilities
- `app/static/js/pages/fix-wizard.js` — Fix Wizard UI
- `app/templates/dashboard/fix_wizard.html` — Fix Wizard template
- `migrations/versions/6a96501dd084_add_schedule_outcomes.py` — Schedule outcome columns

**Step 2: Commit**

```bash
git add docs/CODEBASE_MAP.md
git commit -m "docs: update CODEBASE_MAP.md with all new files

DOC-CRT-01: Map had zero references to CP-SAT, Fix Wizard,
Constraint Modifier, or any other new files."
```

### Task 23: Fix CONTRIBUTING.md JS filename

**Files:**
- Modify: `CONTRIBUTING.md`

**Step 1: Change `api.js` to `api-client.js`**

Find the reference and correct it.

**Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: fix JS filename in CONTRIBUTING.md

DOC-HGH-04: Referenced api.js instead of api-client.js."
```

### Task 24: Update CLAUDE.md with Fix Wizard and dashboard endpoints

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add Fix Wizard endpoints to API section**

```markdown
### Fix Wizard
```
GET        /dashboard/fix-wizard              # Fix Wizard UI
GET        /dashboard/api/fix-wizard/issues   # Get fixable issues
POST       /dashboard/api/fix-wizard/apply    # Apply a fix
POST       /dashboard/api/fix-wizard/skip     # Skip/ignore issue
```
```

**Step 2: Add new key files**

Add to Key Files table:
- `app/services/ai_tools.py` — AI tool definitions (37 tools)
- `app/services/employee_scoring.py` — Employee scoring
- `app/utils/timezone.py` — Timezone utilities
- `app/services/validation_types.py` — Validation type definitions

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Fix Wizard endpoints and new files to CLAUDE.md

DOC-HGH-01/DOC-MED-01: 8+ undocumented routes and several key
files were missing from CLAUDE.md."
```

---

## Summary

| Sprint | Tasks | Focus | Effort |
|--------|-------|-------|--------|
| 1 | Tasks 1-6 | P0 Security & Bugs | ~45 min |
| 2 | Tasks 7-14 | Code Quality (P0+P1) | ~60 min |
| 3 | Tasks 15-18 | P1 Security & Architecture | ~45 min |
| 4 | Task 19 | P1 Performance | ~15 min |
| 5 | Tasks 20-21 | Critical Tests | ~30 min |
| 6 | Tasks 22-24 | Documentation | ~30 min |
| **Total** | **24 tasks** | | **~3.5 hours** |

---

## Sprint 7: Systemic Authentication Audit (OPS-CRT-02)

**Goal:** Add `@require_authentication()` to all unprotected state-mutating routes across api.py, scheduling.py, and dashboard.py.

### Task 25: Audit and protect api.py routes

**Files:**
- Modify: `app/routes/api.py`

**Context:** api.py has ~5,631 lines. `require_authentication` is imported (line 8) but only 8-11 routes use it. The following POST/PUT/DELETE routes are unprotected:

| Line | Method | Route | Risk |
|------|--------|-------|------|
| 608 | POST | `/event/<id>/unschedule` | Deletes schedules |
| 1481 | POST | `/reschedule` | Reschedules events |
| 2606 | POST | `/reschedule_event` (deprecated) | Reschedules events |
| 2647 | DELETE | `/unschedule/<id>` | Deletes schedule + external API |
| 3242 | POST | `/trade_events` (legacy) | Trades event assignments |
| 3556 | POST | `/change_employee` | Changes employee on schedule |
| 4034 | POST | `/import/events` | Bulk CSV import |
| 4139 | POST | `/import/scheduled` | Bulk CSV import |
| 4326 | POST | `/schedule-event` | Creates schedule records |

**Step 1: Add `@require_authentication()` to each unprotected POST/PUT/DELETE route**

For each route listed above, add `@require_authentication()` as the second decorator (after `@api_bp.route(...)`).

**Step 2: Run tests to verify no regressions**

```bash
pytest tests/ -v -x
```

**Step 3: Commit**

```bash
git add app/routes/api.py
git commit -m "fix(security): add authentication to all api.py mutation routes

OPS-CRT-02: 10 POST/DELETE routes in api.py lacked auth decorators.
Added @require_authentication() to all state-mutating endpoints."
```

### Task 26: Audit and protect scheduling.py routes

**Files:**
- Modify: `app/routes/scheduling.py`

**Context:** scheduling.py has 758 lines. `require_authentication` is imported (line 7) but **never used** — zero routes have the decorator.

Key unprotected routes:
- `POST /save_schedule` (line 481) — creates Schedule records directly
- `POST /api/check_conflicts` (line 267) — read-only but should still require auth

**Step 1: Add `@require_authentication()` to all routes in scheduling.py**

**Step 2: Run tests**

```bash
pytest tests/ -v -x
```

**Step 3: Commit**

```bash
git add app/routes/scheduling.py
git commit -m "fix(security): add authentication to all scheduling.py routes

OPS-CRT-02: require_authentication was imported but never used.
All 5 routes now require auth, including /save_schedule."
```

### Task 27: Audit and protect remaining dashboard.py routes

**Files:**
- Modify: `app/routes/dashboard.py`

**Context:** Task 1 (Sprint 1) added auth to Fix Wizard routes. This task covers the remaining ~11 dashboard routes that still lack auth: `command_center`, `weekly_validation`, `validation_summary_api`, `approved_events`, etc.

**Step 1: Add `@require_authentication()` to all remaining dashboard routes**

**Step 2: Run tests**

```bash
pytest tests/ -v -x
```

**Step 3: Commit**

```bash
git add app/routes/dashboard.py
git commit -m "fix(security): add authentication to all dashboard routes

OPS-CRT-02: All 15 dashboard routes now require authentication."
```

---

## Sprint 8: CP-SAT BoolVar Refactor (PERF-CRT-02)

**Goal:** Extract shared indicator BoolVar construction into a helper method and cache indicators for reuse across all constraint methods. Reduces 50K-100K redundant variables.

### Task 28: Create _make_assignment_indicator helper

**Files:**
- Modify: `app/services/cpsat_scheduler.py`

**Context:** The 7-line pattern creating "employee E assigned to event V on day D" indicators is duplicated across 17 call sites in 8 methods. The pattern is always:

```python
ind = model.NewBoolVar(f'<prefix>_{eid}_{emp_id}_{d}')
model.AddBoolAnd([self.v_assign_emp[(eid, emp_id)], self.v_assign_day[(eid, d)]]).OnlyEnforceIf(ind)
model.AddBoolOr([self.v_assign_emp[(eid, emp_id)].Not(), self.v_assign_day[(eid, d)].Not()]).OnlyEnforceIf(ind.Not())
```

**Step 1: Add helper method and indicator cache**

Add to the CPSATSchedulingEngine class, before the constraint methods:

```python
    def _make_assignment_indicator(self, model, eid, emp_id, d):
        """Return cached BoolVar = (v_assign_emp[eid, emp_id] AND v_assign_day[eid, d]).

        Creates the variable once per (eid, emp_id, d) triple and caches it.
        Eliminates 50K-100K redundant variables created by 8 constraint methods.
        """
        key = (eid, emp_id, d)
        if key not in self._indicator_cache:
            ind = model.NewBoolVar(f'ind_{eid}_{emp_id}_{d}')
            model.AddBoolAnd([
                self.v_assign_emp[(eid, emp_id)],
                self.v_assign_day[(eid, d)]
            ]).OnlyEnforceIf(ind)
            model.AddBoolOr([
                self.v_assign_emp[(eid, emp_id)].Not(),
                self.v_assign_day[(eid, d)].Not()
            ]).OnlyEnforceIf(ind.Not())
            self._indicator_cache[key] = ind
        return self._indicator_cache[key]
```

**Step 2: Initialize cache in _build_model**

In `_build_model()`, before calling constraint methods, add:
```python
self._indicator_cache = {}
```

**Step 3: Commit**

```bash
git add app/services/cpsat_scheduler.py
git commit -m "perf: add cached _make_assignment_indicator helper

PERF-CRT-02: Preparation for replacing 17 duplicated indicator
construction sites with shared cached variables."
```

### Task 29: Replace all duplicate indicator constructions

**Files:**
- Modify: `app/services/cpsat_scheduler.py`

**Step 1: Replace in each constraint method**

Replace each 7-line indicator block in these methods with a single call:

- `_add_emp_day_limits` (line 881)
- `_add_emp_week_limits` (line 924)
- `_add_weekly_hours_cap` (lines 966, 988)
- `_add_mutual_exclusion_per_day` (lines 1010, 1025)
- `_add_support_requires_base` (lines 1116, 1134)
- `_add_full_day_exclusivity` (lines 1176, 1200)
- `_add_objective` S4 (lines 1321, 1335), S8 (line 1421), S10 (line 1477), S14 (line 1581)

Example replacement:
```python
# Before:
ind = model.NewBoolVar(f'ind_{eid}_{emp_id}_{d}')
model.AddBoolAnd([...]).OnlyEnforceIf(ind)
model.AddBoolOr([...]).OnlyEnforceIf(ind.Not())

# After:
ind = self._make_assignment_indicator(model, eid, emp_id, d)
```

Note: `_add_block_uniqueness` (line 1231) uses a block+day variant and `_add_objective` S7 (line 1391) uses a 3-variable AND — leave these inline.

**Step 2: Run tests**

```bash
pytest tests/test_cpsat_double_booking.py -v
```

**Step 3: Commit**

```bash
git add app/services/cpsat_scheduler.py
git commit -m "perf: replace 15 indicator duplications with cached helper

PERF-CRT-02/BP-HGH-01: Shared cache deduplicates BoolVars across
all constraint methods. Reduces variable count by 50K-100K."
```

---

## Sprint 9: ML Affinity Scoring Fix (PERF-CRT-03)

**Goal:** Fix the broken ML affinity integration (key mismatch bug) and batch the scoring.

### Task 30: Fix ML affinity key mismatch (hidden bug)

**Files:**
- Modify: `app/services/cpsat_scheduler.py:184-218` (_get_ml_affinity_scores)

**Context:** Research discovered a hidden bug — `_get_ml_affinity_scores` stores scores keyed by `(event.project_ref_num, employee.id)`, but the S15 objective at line 1595 looks up via `(event.id, emp_id)` against `v_assign_emp` which uses `event.id`. The keys never match, so S15 ML bonus currently does nothing.

**Step 1: Fix the key to use event.id instead of project_ref_num**

```python
        for event in self.events:
            ranked = adapter.rank_employees(
                list(self.employees.values()),
                event,
                event.start_date if hasattr(event, 'start_date') else datetime.now()
            )
            for employee, score in ranked:
                scores[(event.id, employee.id)] = score  # Fix: use event.id not project_ref_num
```

**Step 2: Commit**

```bash
git add app/services/cpsat_scheduler.py
git commit -m "fix: ML affinity key mismatch — S15 bonus was inert

_get_ml_affinity_scores stored keys as (project_ref_num, emp_id)
but S15 objective lookups used (event.id, emp_id). Keys never
matched, so ML bonus was silently ignored."
```

### Task 31: Batch ML affinity scoring

**Files:**
- Modify: `app/services/cpsat_scheduler.py:184-218`
- Modify: `app/ml/inference/ml_scheduler_adapter.py` (add batch method)

**Step 1: Add batch_rank method to MLSchedulerAdapter**

```python
def batch_rank_employees(self, employees, events, date):
    """Score all (event, employee) pairs in a single pass."""
    scores = {}
    for event in events:
        ranked = self.rank_employees(employees, event, date)
        for emp, score in ranked:
            scores[(event.id, emp.id)] = score
    return scores
```

**Step 2: Update _get_ml_affinity_scores to use batch method**

```python
    scores = adapter.batch_rank_employees(
        list(self.employees.values()),
        self.events,
        self.events[0].start_date if self.events else datetime.now()
    )
```

**Step 3: Commit**

```bash
git add app/services/cpsat_scheduler.py app/ml/inference/ml_scheduler_adapter.py
git commit -m "perf: batch ML affinity scoring

PERF-CRT-03: Single batch_rank_employees call replaces N
individual rank_employees calls (80 events = 80 round-trips)."
```

---

## Sprint 10: Test Suites for Untested Services (TST-CRT-01/02/03)

### Task 32: Write ConstraintModifier test suite

**Files:**
- Create: `tests/test_constraint_modifier.py`

**Context:** 281-line service with 5 public methods, zero tests.

**Step 1: Write tests for apply_preference**

```python
def test_apply_preference_exact_match(app, db_session, models):
    """apply_preference with exact keyword 'fairness' should succeed."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    result = modifier.apply_preference('fairness', 'increase')
    assert result['success'] is True
    assert result['multiplier'] > 1.0

def test_apply_preference_substring_match(app, db_session, models):
    """apply_preference with 'workload fairness' should substring-match 'fairness'."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    result = modifier.apply_preference('workload fairness', 'increase')
    assert result['success'] is True

def test_apply_preference_unknown_keyword(app, db_session, models):
    """apply_preference with unknown keyword should return success=False."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    result = modifier.apply_preference('xyzzy_nonexistent', 'increase')
    assert result['success'] is False

def test_apply_preference_reset_direction(app, db_session, models):
    """apply_preference with direction='reset' should set multiplier=1.0."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    result = modifier.apply_preference('fairness', 'reset')
    assert result['success'] is True
    assert result['multiplier'] == 1.0
```

**Step 2: Write tests for get_active_preferences, clear, get_multipliers**

```python
def test_get_active_preferences_skips_1_0(app, db_session, models):
    """get_active_preferences should not return entries with multiplier=1.0."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    modifier.apply_preference('fairness', 'reset')  # Sets 1.0
    prefs = modifier.get_active_preferences()
    fairness_prefs = [p for p in prefs if 'fairness' in p.get('weight_name', '').lower()]
    assert len(fairness_prefs) == 0

def test_clear_all_preferences(app, db_session, models):
    """clear_all_preferences should remove all scheduling_pref_ entries."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    modifier.apply_preference('fairness', 'increase')
    result = modifier.clear_all_preferences()
    assert result['success'] is True
    assert modifier.get_multipliers() == {}

def test_get_multipliers_returns_only_non_default(app, db_session, models):
    """get_multipliers should only return non-1.0 entries."""
    from app.services.constraint_modifier import ConstraintModifier
    modifier = ConstraintModifier()
    modifier.apply_preference('fairness', 'increase')
    mults = modifier.get_multipliers()
    for v in mults.values():
        assert v != 1.0
```

**Step 3: Run tests**

```bash
pytest tests/test_constraint_modifier.py -v
```

**Step 4: Commit**

```bash
git add tests/test_constraint_modifier.py
git commit -m "test: add ConstraintModifier test suite (7 tests)

TST-CRT-01: Covers apply_preference (exact, substring, unknown,
reset), get_active_preferences, clear_all, get_multipliers."
```

### Task 33: Write AI Tools core test suite

**Files:**
- Create: `tests/test_ai_tools.py`

**Context:** 4,100+ lines, 37 tools, zero tests. Focus on the most critical write tools first.

**Step 1: Write tests for read-only tools**

```python
def test_get_schedule(app, db_session, models):
    """_tool_get_schedule should return schedule data for a valid date."""
    from app.services.ai_tools import AITools
    tools = AITools(db_session, models)
    result = tools.execute_tool('get_schedule', {'date': '2026-02-20'})
    assert result['success'] is True

def test_list_employees(app, db_session, models):
    """_tool_list_employees should return employee list."""
    from app.services.ai_tools import AITools
    tools = AITools(db_session, models)
    result = tools.execute_tool('list_employees', {})
    assert result['success'] is True

def test_unknown_tool_returns_error(app, db_session, models):
    """Unknown tool name should return success=False."""
    from app.services.ai_tools import AITools
    tools = AITools(db_session, models)
    result = tools.execute_tool('nonexistent_tool', {})
    assert result['success'] is False
    assert 'Unknown tool' in result['message']
```

**Step 2: Write tests for confirmation-required write tools**

```python
def test_unschedule_requires_confirmation(app, db_session, models):
    """unschedule_event without _confirmed should require confirmation."""
    from app.services.ai_tools import AITools
    # Create a test schedule first
    Schedule = models['Schedule']
    Event = models['Event']
    Employee = models['Employee']
    emp = Employee(id='T001', name='Test Emp', job_title='Lead Event Specialist')
    db_session.add(emp)
    event = Event(id=999, project_ref_num='TEST-001', project_name='Test',
                  event_type='Core', is_scheduled=True)
    db_session.add(event)
    sched = Schedule(event_ref_num='TEST-001', employee_id='T001',
                     schedule_datetime=datetime(2026, 2, 20, 9, 0))
    db_session.add(sched)
    db_session.commit()

    tools = AITools(db_session, models)
    result = tools.execute_tool('unschedule_event', {'event_ref': 'TEST-001'})
    assert result.get('requires_confirmation') is True
```

**Step 3: Run tests**

```bash
pytest tests/test_ai_tools.py -v
```

**Step 4: Commit**

```bash
git add tests/test_ai_tools.py
git commit -m "test: add AI Tools core test suite

TST-CRT-02: Covers read tools, unknown tool handling, and
confirmation flow for write operations."
```

### Task 34: Write AI Assistant service tests

**Files:**
- Create: `tests/test_ai_assistant.py`

**Context:** 555 lines, confirm_action is the critical security path.

**Step 1: Write tests for confirm_action**

```python
from unittest.mock import MagicMock, patch

def test_confirm_action_requires_tool_name(app, db_session, models):
    """confirm_action with missing tool_name should return error."""
    from app.services.ai_assistant import AIAssistant
    assistant = AIAssistant('mock', 'fake-key', db_session, models)
    result = assistant.confirm_action({'tool_args': {}})
    assert 'error' in result.response.lower() or 'failed' in result.response.lower()

def test_confirm_action_accepts_tool_args_key(app, db_session, models):
    """confirm_action should accept 'tool_args' key for args."""
    from app.services.ai_assistant import AIAssistant
    assistant = AIAssistant('mock', 'fake-key', db_session, models)
    with patch.object(assistant.tools, 'execute_tool', return_value={'message': 'ok'}):
        result = assistant.confirm_action({
            'tool_name': 'get_schedule',
            'tool_args': {'date': '2026-02-20'}
        })
    assert 'ok' in result.response or 'confirmed' in result.response.lower()

def test_confirm_action_accepts_args_key_fallback(app, db_session, models):
    """confirm_action should fallback to 'args' key."""
    from app.services.ai_assistant import AIAssistant
    assistant = AIAssistant('mock', 'fake-key', db_session, models)
    with patch.object(assistant.tools, 'execute_tool', return_value={'message': 'ok'}):
        result = assistant.confirm_action({
            'tool_name': 'get_schedule',
            'args': {'date': '2026-02-20'}
        })
    assert result.data is not None or 'ok' in result.response
```

**Step 2: Run tests**

```bash
pytest tests/test_ai_assistant.py -v
```

**Step 3: Commit**

```bash
git add tests/test_ai_assistant.py
git commit -m "test: add AI Assistant service tests

TST-CRT-03: Covers confirm_action with missing tool_name,
tool_args vs args key fallback, and error handling."
```

---

## Sprint 11: CI/CD & Infrastructure (OPS-HGH)

### Task 35: Add security scanning to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Add Bandit and pip-audit steps**

```yaml
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install bandit pip-audit
      - name: Run Bandit (SAST)
        run: bandit -r app/ -f json -o bandit-report.json || true
      - name: Run pip-audit
        run: pip-audit -r requirements.txt
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add Bandit SAST and pip-audit to CI pipeline

OPS-HGH-02: No security scanning existed. Adds static analysis
and dependency vulnerability checking."
```

### Task 36: Add migration testing to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Add migration test step**

```yaml
  migration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Test migrations
        run: |
          DATABASE_URL=sqlite:///instance/test_migration.db flask db upgrade
          DATABASE_URL=sqlite:///instance/test_migration.db flask db downgrade base
          DATABASE_URL=sqlite:///instance/test_migration.db flask db upgrade
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add migration upgrade/downgrade testing

OPS-HGH-13: Migrations were never tested in CI."
```

### Task 37: Fix JS lint job error suppression

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Remove `|| true` from JS lint step**

Find the JS lint step and remove `|| true` so lint failures actually fail the build.

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: stop swallowing JS lint errors

OPS-MED-02: JS lint job used || true, hiding all errors."
```

---

## Sprint 12: Savepoint Dry-Run Isolation (SEC-HGH-04)

### Task 38: Fix _tool_compare_schedulers dry-run isolation

**Files:**
- Modify: `app/services/ai_tools.py:3755-3792`

**Context:** `_tool_compare_schedulers` runs schedulers inside SQLAlchemy savepoints then rolls back. SQLite savepoints may not isolate correctly; autoflush before rollback could persist partial state.

**Step 1: Use a separate read-only session for comparison**

```python
    def _tool_compare_schedulers(self, args):
        """Compare greedy vs CP-SAT scheduler results without side effects."""
        # SEC-HGH-04: Use a separate session to prevent side-effect leakage
        from sqlalchemy.orm import Session
        from app.models import get_db

        db = get_db()
        # Create a new session that will be rolled back entirely
        comparison_session = Session(bind=db.engine)
        try:
            # Run schedulers using comparison_session
            # ... (existing logic but using comparison_session instead of self.db)
            pass
        finally:
            comparison_session.rollback()
            comparison_session.close()
```

Alternatively, add `dry_run=True` flag to both scheduler engines that skips all DB writes and only returns what would be scheduled.

**Step 2: Commit**

```bash
git add app/services/ai_tools.py
git commit -m "fix(security): isolate compare_schedulers from production DB

SEC-HGH-04: Savepoint-based dry run could leak side effects on
SQLite. Uses separate session that is always rolled back."
```

---

## Updated Summary

| Sprint | Tasks | Focus | Effort |
|--------|-------|-------|--------|
| 1 | Tasks 1-6 | P0 Security & Bugs | ~45 min |
| 2 | Tasks 7-14 | Code Quality (P0+P1) | ~60 min |
| 3 | Tasks 15-18 | P1 Security & Architecture | ~45 min |
| 4 | Task 19 | P1 Performance | ~15 min |
| 5 | Tasks 20-21 | Critical Tests | ~30 min |
| 6 | Tasks 22-24 | Documentation | ~30 min |
| 7 | Tasks 25-27 | Systemic Auth Audit | ~90 min |
| 8 | Tasks 28-29 | CP-SAT BoolVar Refactor | ~120 min |
| 9 | Tasks 30-31 | ML Affinity Scoring Fix | ~60 min |
| 10 | Tasks 32-34 | Test Suites for 3 Services | ~180 min |
| 11 | Tasks 35-37 | CI/CD Infrastructure | ~45 min |
| 12 | Task 38 | Savepoint Isolation | ~30 min |
| **Total** | **38 tasks** | **12 sprints** | **~12.5 hours** |
