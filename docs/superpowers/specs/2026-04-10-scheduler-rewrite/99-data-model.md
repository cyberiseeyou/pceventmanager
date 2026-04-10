# Spec 99 — Data Model Mapping

> This is NOT a spec of *behavior*; it is a bridge document. It maps the abstract concepts used in the category specs ("Primary Lead", "has a primary event", "fewest primaries this week") onto the concrete SQLAlchemy models already present in `app/models/`. Every category plan's implementation tasks must refer to these mappings rather than invent their own.

## Models at a glance

Source: confirmed via direct read of the model files on 2026-04-10.

### Employee — `app/models/employee.py:32–55`

Fields the scheduler uses:
- `id: String(50)` — primary key, used as the employee reference string everywhere.
- `name: String(100)` — display only.
- `is_active: Boolean (default True)` — skip inactive employees entirely.
- `termination_date: Date (nullable)` — if set and `<= today`, employee is gone.
- `job_title: String(50) (default 'Event Specialist')` — the ONLY valid values in production are:
  - `'Club Supervisor'`
  - `'Lead Event Specialist'`
  - `'Juicer Barista'`
  - `'Event Specialist'`
- `juicer_trained: Boolean (default False)` — used ONLY as eligibility for Juicer events when not on rotation. The rotation table is authoritative for Primary/Backup Juicer on a given date.
- `adult_beverage_trained: Boolean` — not used by the scheduler for assignment decisions.
- `is_supervisor: Boolean` — legacy field; equivalent to `job_title == 'Club Supervisor'`. Prefer `job_title`.

### RotationAssignment — `app/models/auto_scheduler.py:58–87`

Fields:
- `id: Integer` — PK.
- `day_of_week: Integer` — **0=Mon through 6=Sun** (Python `date.weekday()` convention — NOT the Sunday-first convention used for "week Sun–Sat" math; see §Week Math below).
- `rotation_type: String(20)` — values: `'juicer'`, `'primary_lead'`. (There may be other values in the DB, e.g., `'secondary_lead'`, but the spec only cares about these two.)
- `employee_id: String` — FK to Employee.id. The **primary** rotation employee for that DoW+type.
- `backup_employee_id: String (nullable)` — FK to Employee.id. The **backup** rotation employee.
- Unique constraint: `(day_of_week, rotation_type)`.

**Primary Juicer lookup:** `RotationAssignment.query.filter_by(day_of_week=<day.weekday()>, rotation_type='juicer').first()`.
- If returns None → no Primary Juicer for that day; both branches ("primary available" and "backup available") evaluate as NO.
- Returned row's `.employee_id` = Primary Juicer; `.backup_employee_id` = Backup Juicer (may be None).

**Primary Lead lookup:** same query with `rotation_type='primary_lead'`.

### ScheduleException — `app/models/auto_scheduler.py:226–257`

Per-date override of the rotation.
- `exception_date: Date`
- `rotation_type: String(20)` — 'juicer' or 'primary_lead'.
- `employee_id: String` — the override employee for that specific date.
- Unique constraint: `(exception_date, rotation_type)`.

**Lookup:** Before using the rotation for a given `(date, rotation_type)`, check for an exception:
```python
exc = ScheduleException.query.filter_by(exception_date=d, rotation_type='juicer').first()
if exc:
    primary_id = exc.employee_id  # backup_id is not overrideable via exceptions
    backup_id = None
else:
    row = RotationAssignment.query.filter_by(day_of_week=d.weekday(), rotation_type='juicer').first()
    primary_id, backup_id = (row.employee_id, row.backup_employee_id) if row else (None, None)
```

### Event — `app/models/event.py:35–51`

Fields the scheduler uses:
- `id: Integer` — PK.
- `project_name: Text` — used for name-pattern matching (Freeosk subcategories, Digitals subcategories, 6-digit event number extraction for CORE/Supervisor pairing and Juicer Production/Survey pairing).
- `project_ref_num: Integer (unique)` — the public event reference number (used as FK in Schedule and PendingSchedule).
- `start_datetime: DateTime` — the earliest schedulable date.
- `due_datetime: DateTime` — the latest schedulable date (exclusive — scheduler uses `d < due.date()`).
- `estimated_time: Integer (nullable)` — minutes; used for weekly-hours cap safety rail (not a spec rule).
- `is_scheduled: Boolean (default False)` — true iff a posted `Schedule` row exists. Kept in sync by approval workflow.
- `event_type: String(20) (default 'Other')` — values in production data: `'Core'`, `'Digitals'`, `'Digital Setup'`, `'Digital Refresh'`, `'Digital Teardown'`, `'Freeosk'`, `'Juicer Production'`, `'Juicer Survey'`, `'Juicer Deep Clean'`, `'Supervisor'`, `'Other'`.
- `condition: String(20) (default 'Unstaffed')` — values: `'Scheduled'`, `'Staffed'`, `'Submitted'`, `'Unstaffed'`, `'In Progress'`, `'Reissued'`, `'Canceled'`, `'Cannot Complete'`.

### Schedule — `app/models/schedule.py:20–42`

A posted schedule (already approved, in the calendar).
- `id: Integer` — PK.
- `event_ref_num: Integer` — FK to Event.project_ref_num.
- `employee_id: String (nullable)` — FK to Employee.id.
- `employee_name: String` — cached display name.
- `schedule_datetime: DateTime` — the date + time the event is scheduled for.
- `shift_block: Integer (nullable)` — 1..8 for CORE events, representing which of the 4 time slots × 2 positions per slot this event occupies.
- `was_completed / was_no_show / was_swapped: Boolean` — historical flags; not read by the scheduler.

### PendingSchedule — `app/models/auto_scheduler.py:148–220`

A proposed schedule from a scheduler run, awaiting supervisor approval.
- `id: Integer` — PK.
- `scheduler_run_id: Integer` — FK to SchedulerRunHistory.id.
- `event_ref_num: Integer` — FK to Event.project_ref_num.
- `employee_id: String (nullable)` — the proposed employee (NULL means manual review).
- `schedule_datetime: DateTime (nullable)` — the proposed date+time (NULL means manual review).
- `schedule_time: Time (nullable)` — legacy; mirrors the time portion of schedule_datetime. Set both.
- `status: String(20) (default 'proposed')` — values: `'proposed'`, `'user_edited'`, `'approved'`, `'api_submitted'`, `'api_failed'`, `'superseded'`.
- `is_swap: Boolean (default False)` — True if this proposal bumps a posted Schedule.
- `bumped_event_ref_num: Integer (nullable)` — the event that was bumped (if is_swap).
- `bumped_posted_schedule_id: Integer (nullable)` — the ID of the old Schedule row that this proposal replaces.
- `swap_reason: Text (nullable)` — human-readable reason.
- `failure_reason: Text (nullable)` — populated for manual-review entries.

**Manual review entry:** `PendingSchedule(scheduler_run_id=<run>, event_ref_num=<e>, employee_id=None, schedule_datetime=None, schedule_time=None, status='proposed', failure_reason=<text>)`.

**Invariant:** A PendingSchedule with `employee_id=None` MUST have `failure_reason` set. A PendingSchedule with `employee_id` set MUST have `schedule_datetime` and `schedule_time` set.

### SchedulerRunHistory — `app/models/auto_scheduler.py:95–145`

- `id: Integer` — PK.
- `run_type: String` — 'manual', 'scheduled', etc.
- `started_at / completed_at: DateTime`.
- `status: String (default 'running')` — 'running', 'completed', 'failed', 'approved'.
- `total_events_processed / events_scheduled / events_requiring_swaps / events_failed: Integer`.
- `solver_type: String (nullable)` — set to `'greedy'` for the rewritten scheduler (replacing `'cpsat'`).
- `approved_at / approved_by_user: ...` — approval workflow.

### EmployeeTimeOff — `app/models/availability.py:56–89`

- `employee_id`, `start_date`, `end_date`, `status`.
- `status` values: `'approved'`, `'pending'`, `'denied'`. Only `'approved'` blocks scheduling.
- A time-off range `[start_date, end_date]` is inclusive on both ends.

### EmployeeWeeklyAvailability — `app/models/availability.py:11–33`

- `employee_id`, `monday` ... `sunday` (all Boolean, default True).
- `False` on a day means the employee is not available that day-of-week (e.g., part-time employees). This is checked per target_date by converting `target_date.weekday()` to the corresponding column.

### EmployeeAvailabilityOverride — `app/models/availability.py:91–161`

A date-range override of weekly availability, with same structure but nullable day columns (NULL = no override, True/False = override).

## Derived concepts — how to implement them

### "Primary Juicer for day D"
```python
def get_primary_juicer(d: date) -> tuple[str | None, str | None]:
    """Returns (primary_employee_id, backup_employee_id) for date d."""
    # Check exception first
    exc = ScheduleException.query.filter_by(
        exception_date=d, rotation_type='juicer'
    ).first()
    if exc:
        return (exc.employee_id, None)  # exceptions have no backup
    row = RotationAssignment.query.filter_by(
        day_of_week=d.weekday(), rotation_type='juicer'
    ).first()
    if not row:
        return (None, None)
    return (row.employee_id, row.backup_employee_id)
```

### "Primary Lead for day D"
Same as above with `rotation_type='primary_lead'`.

### "Employee is available on day D" (no PTO, workable DoW)
```python
def is_available(emp_id: str, d: date) -> bool:
    # Approved time off?
    off = EmployeeTimeOff.query.filter(
        EmployeeTimeOff.employee_id == emp_id,
        EmployeeTimeOff.status == 'approved',
        EmployeeTimeOff.start_date <= d,
        EmployeeTimeOff.end_date >= d,
    ).first()
    if off:
        return False

    # Date-range override?
    ov = EmployeeAvailabilityOverride.query.filter(
        EmployeeAvailabilityOverride.employee_id == emp_id,
        EmployeeAvailabilityOverride.start_date <= d,
        EmployeeAvailabilityOverride.end_date >= d,
    ).first()
    if ov:
        day_col = ['monday', 'tuesday', 'wednesday', 'thursday',
                   'friday', 'saturday', 'sunday'][d.weekday()]
        val = getattr(ov, day_col)
        if val is False:
            return False
        if val is True:
            return True  # override explicitly grants availability
        # val is None → fall through to weekly

    # Weekly availability?
    wa = EmployeeWeeklyAvailability.query.filter_by(employee_id=emp_id).first()
    if wa:
        day_col = ['monday', 'tuesday', 'wednesday', 'thursday',
                   'friday', 'saturday', 'sunday'][d.weekday()]
        if getattr(wa, day_col) is False:
            return False

    return True
```

### "Employee has a primary event on day D"
```python
def has_primary_event(emp_id: str, d: date, run_id: int) -> bool:
    """True if employee has any CORE or Juicer Production scheduled on date d,
    counting both posted schedules AND in-run PendingSchedule proposals."""
    # Posted schedules
    posted = (db.session.query(Schedule.id)
              .join(Event, Schedule.event_ref_num == Event.project_ref_num)
              .filter(
                  Schedule.employee_id == emp_id,
                  func.date(Schedule.schedule_datetime) == d,
                  Event.event_type.in_(['Core', 'Juicer Production']),
              ).first())
    if posted:
        return True

    # In-run pending schedules (not yet approved but already proposed in this run)
    pending = (db.session.query(PendingSchedule.id)
               .join(Event, PendingSchedule.event_ref_num == Event.project_ref_num)
               .filter(
                   PendingSchedule.scheduler_run_id == run_id,
                   PendingSchedule.employee_id == emp_id,
                   func.date(PendingSchedule.schedule_datetime) == d,
                   PendingSchedule.failure_reason.is_(None),
                   Event.event_type.in_(['Core', 'Juicer Production']),
               ).first())
    return pending is not None
```

### "Fewest primary events this week (Sun–Sat)"
```python
def primaries_this_week(emp_id: str, d: date, run_id: int) -> int:
    """Count of CORE + Juicer Production for this employee in the Sun–Sat
    week containing d (both posted and in-run)."""
    # Sun–Sat week boundaries: Sunday is day 0 of the scheduling week.
    # Python's weekday() has Mon=0..Sun=6, so convert:
    #   days_since_sunday = (d.weekday() + 1) % 7
    days_since_sunday = (d.weekday() + 1) % 7
    week_start = d - timedelta(days=days_since_sunday)       # Sunday
    week_end = week_start + timedelta(days=6)                # Saturday

    posted = (db.session.query(func.count(Schedule.id))
              .join(Event, Schedule.event_ref_num == Event.project_ref_num)
              .filter(
                  Schedule.employee_id == emp_id,
                  func.date(Schedule.schedule_datetime).between(week_start, week_end),
                  Event.event_type.in_(['Core', 'Juicer Production']),
              ).scalar()) or 0

    pending = (db.session.query(func.count(PendingSchedule.id))
               .join(Event, PendingSchedule.event_ref_num == Event.project_ref_num)
               .filter(
                   PendingSchedule.scheduler_run_id == run_id,
                   PendingSchedule.employee_id == emp_id,
                   func.date(PendingSchedule.schedule_datetime).between(week_start, week_end),
                   PendingSchedule.failure_reason.is_(None),
                   Event.event_type.in_(['Core', 'Juicer Production']),
               ).scalar()) or 0

    return posted + pending
```

### Week math gotcha
Python's `date.weekday()` uses Monday=0. The scheduling week in this spec is Sunday–Saturday. Conversion:
- `days_since_sunday = (d.weekday() + 1) % 7` → 0 for Sunday, 1 for Monday, ..., 6 for Saturday.
- `week_start = d - timedelta(days=days_since_sunday)` → the Sunday of d's week.
- `week_end = week_start + timedelta(days=6)` → the Saturday of d's week.
Use this, not ISO week boundaries.

### CORE-Supervisor pairing key
From the existing code (`cpsat_scheduler.py:474–486` `_extract_event_number`), event pairing uses the parenthesized reference number in `project_name` (e.g., `(260115542007)`). The spec says "same 6-digit number and name prefix".

**Reconciliation:** The 6-digit number referred to by the spec is the first 6 digits of the project name (e.g., `"260115-MAP-Brand-Product"` → `"260115"`). The parenthesized ref is a different identifier and may not match between a CORE and its Supervisor.

**Correct pairing:** Extract the leading 6-digit sequence from `project_name` AND compare the non-numeric name prefix up to the first type keyword ("CORE", "Supervisor", "Juicer", etc.). If BOTH match, they're paired.

Implementation sketch:
```python
import re

def extract_pairing_key(project_name: str) -> tuple[str, str] | None:
    """Returns (six_digit, name_prefix) for pairing, or None if name is malformed."""
    m = re.match(r'^\s*(\d{6})[-\s]+(.+?)(?:\s+[-–]\s+|-)(CORE|Supervisor|SUPERVISOR|Core)', project_name)
    if not m:
        return None
    return (m.group(1), m.group(2).strip())

def pair_cores_and_supervisors(events: list[Event]) -> dict[int, Event]:
    """Map CORE event id → Supervisor event."""
    cores = [e for e in events if e.event_type == 'Core']
    supervisors = [e for e in events if e.event_type == 'Supervisor']
    sup_by_key = {}
    for s in supervisors:
        key = extract_pairing_key(s.project_name)
        if key:
            sup_by_key[key] = s
    pairs = {}
    for c in cores:
        key = extract_pairing_key(c.project_name)
        if key and key in sup_by_key:
            pairs[c.id] = sup_by_key[key]
    return pairs
```

The regex must be validated against real production event names in the `sam_club_8135` dataset during Plan Task 01-phase-infrastructure T4. If actual name patterns differ, update the regex and document the change in this file.

### Juicer Production → Juicer Survey matching key
Same pattern as CORE/Supervisor, but with keyword matches for "JUICER-PRODUCTION" and "JUICER-SURVEY" in the name. Example from existing tests: `"111111-JUICER-PRODUCTION-SPCLTY"` pairs with `"111111-JUICER-SURVEY"` by the leading 6 digits.

### Freeosk subcategory classifier
```python
def freeosk_subcategory(project_name: str) -> str | None:
    """Returns 'daily_service', 'changeover', 'troubleshooting', or None."""
    name = project_name or ''
    if 'FSK-Daily Service-11AM' in name:
        return 'daily_service'
    if 'CO-11AM' in name:
        return 'changeover'
    if 'Troubleshooting' in name:
        return 'troubleshooting'
    return None
```

### Digital subcategory classifier
```python
def digital_subcategory(project_name: str) -> str | None:
    """Returns 'setup', 'refresh', 'teardown', or None."""
    name = (project_name or '').strip()
    if name.endswith('Digital Demo Setup'):
        return 'setup'
    if name.endswith('Digital Demo Refresh'):
        return 'refresh'
    if name.endswith('Digital Demo Tear Down'):
        return 'teardown'
    return None
```

## Query performance notes

- `has_primary_event` and `primaries_this_week` are called O(n × employees × days) times during a run. They **must** be backed by an in-memory cache built once per run from bulk queries, not recomputed per call. The cache layout:
  - `primary_events_by_emp_day[(emp_id, date)] = [event_ref_num, ...]`
  - `primary_events_by_emp_week[(emp_id, week_start)] = int_count`
  - Updated incrementally as each PendingSchedule is proposed within the run.

- `is_available` should also be cached per `(emp_id, date)` for the run.

These caches are the difference between a 5-second run and a 5-minute run; build them in plan task `01-phase-infrastructure.md` T0.
