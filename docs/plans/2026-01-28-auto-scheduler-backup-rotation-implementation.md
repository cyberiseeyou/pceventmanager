# Auto-Scheduler Date Fix and Backup Rotation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix auto-scheduler scheduling events on past dates and add backup rotation configuration for automatic failover when primary employees are unavailable.

**Architecture:** Add `backup_employee_id` to RotationAssignment model, enhance RotationManager to support backup lookup, update SchedulingEngine to check past dates and try backup employees when primary is unavailable.

**Tech Stack:** Flask-SQLAlchemy, Alembic migrations, Python datetime

---

## Phase 1: Database Migration for Backup Rotation

### Task 1: Create Database Migration

**Files:**
- Create: `migrations/versions/YYYY_add_backup_employee_to_rotations.py` (auto-generated)
- Reference: `app/models/auto_scheduler.py:58-87`

**Step 1: Create migration file**

Run: `flask db migrate -m "add backup_employee_id to rotation_assignments"`

Expected: Migration file created in `migrations/versions/`

**Step 2: Review generated migration**

Open the generated migration file and verify it contains:
- `op.add_column('rotation_assignments', sa.Column('backup_employee_id', sa.String(), nullable=True))`
- Foreign key to `employees.id`

If missing foreign key, edit migration to add:
```python
def upgrade():
    op.add_column('rotation_assignments', sa.Column('backup_employee_id', sa.String(), nullable=True))
    op.create_foreign_key('fk_rotation_backup_employee', 'rotation_assignments', 'employees', ['backup_employee_id'], ['id'])

def downgrade():
    op.drop_constraint('fk_rotation_backup_employee', 'rotation_assignments', type_='foreignkey')
    op.drop_column('rotation_assignments', 'backup_employee_id')
```

**Step 3: Test migration on test database**

Run:
```bash
./start_test_instance.sh
flask db upgrade
```

Expected: Migration applies successfully without errors

**Step 4: Verify schema**

Run:
```bash
sqlite3 instance/scheduler_test.db ".schema rotation_assignments"
```

Expected: `backup_employee_id` column exists with foreign key

**Step 5: Test downgrade**

Run: `flask db downgrade`

Expected: Migration rolls back cleanly, column removed

**Step 6: Re-apply migration**

Run: `flask db upgrade`

Expected: Migration applies again successfully

**Step 7: Clean up test instance**

Run: `./cleanup_test_instance.sh`

**Step 8: Apply to development database**

Run: `flask db upgrade`

Expected: Migration applies to main database

**Step 9: Commit migration**

```bash
git add migrations/versions/*backup_employee*.py
git commit -m "feat: add backup_employee_id to rotation_assignments table

- Add nullable backup_employee_id column
- Add foreign key constraint to employees table
- Supports automatic failover to backup when primary unavailable

Migration tested on test instance and development database"
```

---

## Phase 2: Update RotationAssignment Model

### Task 2: Add Backup Employee Field to Model

**Files:**
- Modify: `app/models/auto_scheduler.py:58-87`

**Step 1: Add backup_employee_id column**

In `create_auto_scheduler_models()` function, in the `RotationAssignment` class definition, after line 70:

```python
employee_id = db.Column(db.String, db.ForeignKey('employees.id'), nullable=False)

# NEW: Backup employee for when primary is unavailable
backup_employee_id = db.Column(db.String, db.ForeignKey('employees.id'), nullable=True)
```

**Step 2: Update relationships**

Replace line 73:
```python
# OLD
employee = db.relationship('Employee', backref='rotation_assignments')

# NEW
employee = db.relationship('Employee', foreign_keys=[employee_id], backref='rotation_assignments')
backup_employee = db.relationship('Employee', foreign_keys=[backup_employee_id], backref='backup_rotation_assignments')
```

**Step 3: Update __repr__ method (optional enhancement)**

After line 87, update the repr to show backup info:
```python
def __repr__(self):
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    backup_info = f" (backup: {self.backup_employee_id})" if self.backup_employee_id else ""
    return f'<RotationAssignment {days[self.day_of_week]} {self.rotation_type}: {self.employee_id}{backup_info}>'
```

**Step 4: Verify model loads**

Run:
```bash
python -c "from app.models import get_models; models = get_models(); print(models['RotationAssignment'])"
```

Expected: No import errors, model loads successfully

**Step 5: Commit model changes**

```bash
git add app/models/auto_scheduler.py
git commit -m "feat: add backup_employee to RotationAssignment model

- Add backup_employee_id field (nullable)
- Add backup_employee relationship
- Update __repr__ to show backup info
- Supports failover to backup when primary unavailable"
```

---

## Phase 3: Enhance RotationManager Service

### Task 3: Add Backup Employee Lookup

**Files:**
- Modify: `app/services/rotation_manager.py:32-76`
- Create: `tests/test_rotation_manager_backup.py`

**Step 1: Write failing test for backup employee lookup**

Create `tests/test_rotation_manager_backup.py`:
```python
import pytest
from datetime import datetime
from app.services.rotation_manager import RotationManager

def test_get_rotation_employee_returns_backup_when_requested(session, models):
    """Test that get_rotation_employee returns backup when try_backup=True"""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    # Create employees
    primary = Employee(id="emp1", name="Primary Juicer", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup Juicer", job_title="Juicer Barista")
    session.add_all([primary, backup])
    session.commit()

    # Create rotation with backup
    rotation = RotationAssignment(
        day_of_week=0,  # Monday
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    session.add(rotation)
    session.commit()

    # Test primary
    manager = RotationManager(session, models)
    monday = datetime(2026, 2, 2)  # A Monday

    primary_emp = manager.get_rotation_employee(monday, 'juicer', try_backup=False)
    assert primary_emp.id == 'emp1'

    # Test backup
    backup_emp = manager.get_rotation_employee(monday, 'juicer', try_backup=True)
    assert backup_emp.id == 'emp2'

def test_get_rotation_employee_returns_primary_when_no_backup_configured(session, models):
    """Test fallback to primary when backup not configured"""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    primary = Employee(id="emp1", name="Primary", job_title="Juicer Barista")
    session.add(primary)
    session.commit()

    rotation = RotationAssignment(
        day_of_week=0,
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id=None  # No backup
    )
    session.add(rotation)
    session.commit()

    manager = RotationManager(session, models)
    monday = datetime(2026, 2, 2)

    # Both should return primary
    emp1 = manager.get_rotation_employee(monday, 'juicer', try_backup=False)
    emp2 = manager.get_rotation_employee(monday, 'juicer', try_backup=True)
    assert emp1.id == 'emp1'
    assert emp2.id == 'emp1'

def test_get_rotation_with_backup_returns_both(session, models):
    """Test get_rotation_with_backup returns (primary, backup) tuple"""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    primary = Employee(id="emp1", name="Primary", job_title="Lead Event Specialist")
    backup = Employee(id="emp2", name="Backup", job_title="Lead Event Specialist")
    session.add_all([primary, backup])
    session.commit()

    rotation = RotationAssignment(
        day_of_week=1,  # Tuesday
        rotation_type='primary_lead',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    session.add(rotation)
    session.commit()

    manager = RotationManager(session, models)
    tuesday = datetime(2026, 2, 3)

    primary_emp, backup_emp = manager.get_rotation_with_backup(tuesday, 'primary_lead')
    assert primary_emp.id == 'emp1'
    assert backup_emp.id == 'emp2'
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_rotation_manager_backup.py -v`

Expected: FAIL - `get_rotation_employee() got an unexpected keyword argument 'try_backup'`

**Step 3: Update get_rotation_employee method signature**

In `app/services/rotation_manager.py`, update method at line 32:

```python
def get_rotation_employee(
    self,
    target_date: datetime,
    rotation_type: str,
    try_backup: bool = False
) -> Optional[object]:
    """
    Get the assigned employee for a given date and rotation type

    Checks for exceptions first, falls back to weekly rotation

    Args:
        target_date: The date to check
        rotation_type: 'juicer' or 'primary_lead'
        try_backup: If True, return backup employee instead of primary

    Returns:
        Employee object or None if no assignment
    """
    # Check for one-time exception first
    exception = self.db.query(self.ScheduleException).filter_by(
        exception_date=target_date.date(),
        rotation_type=rotation_type
    ).first()

    if exception:
        return exception.employee

    # Fall back to weekly rotation
    day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday

    rotation = self.db.query(self.RotationAssignment).filter_by(
        day_of_week=day_of_week,
        rotation_type=rotation_type
    ).first()

    if not rotation:
        return None

    # Return backup if requested and available, otherwise return primary
    if try_backup and rotation.backup_employee_id:
        return rotation.backup_employee
    else:
        return rotation.employee
```

**Step 4: Add get_rotation_with_backup helper method**

After the `get_rotation_employee_id` method (around line 77), add:

```python
def get_rotation_with_backup(
    self,
    target_date: datetime,
    rotation_type: str
) -> Tuple[Optional[object], Optional[object]]:
    """
    Get both primary and backup employees for a rotation

    Args:
        target_date: The date to check
        rotation_type: 'juicer' or 'primary_lead'

    Returns:
        Tuple of (primary_employee, backup_employee) - either can be None
    """
    primary = self.get_rotation_employee(target_date, rotation_type, try_backup=False)
    backup = self.get_rotation_employee(target_date, rotation_type, try_backup=True)
    return (primary, backup)
```

**Step 5: Add Tuple import**

At top of file, update imports:
```python
from typing import Optional, Dict, List, Tuple
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_rotation_manager_backup.py -v`

Expected: PASS (3 tests)

**Step 7: Run all rotation manager tests**

Run: `pytest tests/ -k rotation -v`

Expected: All rotation-related tests pass

**Step 8: Commit rotation manager changes**

```bash
git add app/services/rotation_manager.py tests/test_rotation_manager_backup.py
git commit -m "feat: add backup employee support to RotationManager

- Add try_backup parameter to get_rotation_employee()
- Add get_rotation_with_backup() helper method
- Returns backup employee when try_backup=True
- Falls back to primary if backup not configured
- Add comprehensive tests for backup lookup"
```

---

## Phase 4: Fix Auto-Scheduler Past Date Logic

### Task 4: Fix Juicer Event Past Date Scheduling

**Files:**
- Modify: `app/services/scheduling_engine.py:1635-1684`
- Create: `tests/test_scheduling_past_dates.py`

**Step 1: Write failing test for past date handling**

Create `tests/test_scheduling_past_dates.py`:
```python
import pytest
from datetime import datetime, timedelta, time
from app.services.scheduling_engine import SchedulingEngine

def test_juicer_event_past_start_date_uses_today(session, models):
    """Test that events with past start dates are scheduled for today"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    # Create juicer employee
    juicer = Employee(id="juicer1", name="Juicer", job_title="Juicer Barista")
    session.add(juicer)
    session.commit()

    # Create rotation for today
    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='juicer1'
    )
    session.add(rotation)
    session.commit()

    # Create event with start date 3 days in the past
    past_date = today - timedelta(days=3)
    future_due = today + timedelta(days=7)

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12345,
        start_datetime=past_date,
        due_datetime=future_due,
        event_type="Juicer Production",
        estimated_time=540
    )
    session.add(event)
    session.commit()

    # Run scheduler
    run = SchedulerRunHistory(run_type='manual')
    session.add(run)
    session.commit()

    engine = SchedulingEngine(session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Verify event was scheduled for today, not the past date
    assert event.is_scheduled
    pending = session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.schedule_datetime.date() == today.date()

def test_juicer_event_past_start_and_due_fails(session, models):
    """Test that events with both dates in past fail appropriately"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    juicer = Employee(id="juicer1", name="Juicer", job_title="Juicer Barista")
    session.add(juicer)
    session.commit()

    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='juicer1'
    )
    session.add(rotation)
    session.commit()

    # Both dates in the past
    past_start = today - timedelta(days=7)
    past_due = today - timedelta(days=2)

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12346,
        start_datetime=past_start,
        due_datetime=past_due,
        event_type="Juicer Production",
        estimated_time=540
    )
    session.add(event)
    session.commit()

    run = SchedulerRunHistory(run_type='manual')
    session.add(run)
    session.commit()

    engine = SchedulingEngine(session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should fail
    assert not event.is_scheduled
    pending = session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.failure_reason is not None
    assert "past" in pending.failure_reason.lower()

def test_juicer_event_future_start_date_unchanged(session, models):
    """Test that events with future start dates use the start date"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    juicer = Employee(id="juicer1", name="Juicer", job_title="Juicer Barista")
    session.add(juicer)
    session.commit()

    # Future date
    future_start = datetime.now() + timedelta(days=5)
    future_due = future_start + timedelta(days=7)

    rotation = RotationAssignment(
        day_of_week=future_start.weekday(),
        rotation_type='juicer',
        employee_id='juicer1'
    )
    session.add(rotation)
    session.commit()

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12347,
        start_datetime=future_start,
        due_datetime=future_due,
        event_type="Juicer Production",
        estimated_time=540
    )
    session.add(event)
    session.commit()

    run = SchedulerRunHistory(run_type='manual')
    session.add(run)
    session.commit()

    engine = SchedulingEngine(session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should be scheduled on the future start date
    assert event.is_scheduled
    pending = session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.schedule_datetime.date() == future_start.date()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduling_past_dates.py::test_juicer_event_past_start_date_uses_today -v`

Expected: FAIL - event scheduled to past date instead of today

**Step 3: Update _schedule_juicer_event_wave2 method**

In `app/services/scheduling_engine.py`, replace the method starting at line 1635:

```python
def _schedule_juicer_event_wave2(self, run: object, event: object) -> None:
    """
    Wave 2: Schedule a Juicer event to the rotation-assigned Juicer Barista

    UPDATED: If start date is in the past, schedule for today or earliest valid date
    instead of failing. Only fail if due date has also passed.

    Scheduling times:
    - JUICER-PRODUCTION-SPCLTY: 9:00 AM
    - Juicer Survey: 5:00 PM
    - Other Juicer events: 9:00 AM
    """
    # Determine the appropriate time for this Juicer event
    juicer_time = self._get_juicer_time(event)

    # NEW: Check if start date is in the past
    today = datetime.now().date()
    event_start_date = event.start_datetime.date()

    if event_start_date < today:
        # Start date has passed - use today instead
        target_date = datetime.combine(today, time(0, 0))
        current_app.logger.info(
            f"Event {event.project_ref_num} start date {event_start_date} is in the past. "
            f"Using today {today} as target date."
        )
    else:
        # Start date is today or future - use it
        target_date = event.start_datetime

    # Validate target date is not past the due date
    if target_date.date() > event.due_datetime.date():
        self._create_failed_pending_schedule(
            run, event,
            f"Event start date {event_start_date} is in the past and due date {event.due_datetime.date()} has also passed"
        )
        run.events_failed += 1
        return

    # Get rotation employee for target date
    employee = self.rotation_manager.get_rotation_employee(target_date, 'juicer')
    if not employee:
        # No Juicer assigned for this day in rotation
        self._create_failed_pending_schedule(
            run, event,
            f"No Juicer rotation employee assigned for {target_date.date()}"
        )
        run.events_failed += 1
        return

    schedule_datetime = datetime.combine(target_date.date(), juicer_time)
    validation = self.validator.validate_assignment(event, employee, schedule_datetime)

    if validation.is_valid:
        # Juicer is available - schedule it
        self._create_pending_schedule(run, event, employee, schedule_datetime, False, None, None)
        run.events_scheduled += 1
        current_app.logger.info(
            f"Wave 2: Scheduled Juicer event {event.project_ref_num} to {employee.name} on {target_date.date()}"
        )
        return

    # Juicer not available on target date - fail
    violation_reasons = ", ".join([v.message for v in validation.violations])
    self._create_failed_pending_schedule(
        run, event,
        f"Juicer unavailable on {target_date.date()}: {violation_reasons}"
    )
    run.events_failed += 1
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduling_past_dates.py -v`

Expected: PASS (3 tests)

**Step 5: Run existing scheduling tests**

Run: `pytest tests/test_scheduling_engine.py -v`

Expected: All existing tests still pass

**Step 6: Commit past date fix**

```bash
git add app/services/scheduling_engine.py tests/test_scheduling_past_dates.py
git commit -m "fix: handle past start dates in juicer event scheduling

- Check if event start_datetime is in the past
- Use today as target date if start date has passed
- Fail only if both start and due dates have passed
- Add logging for date adjustments
- Add comprehensive tests for date handling edge cases

Fixes issue where scheduler attempted to schedule events on past dates"
```

---

## Phase 5: Add Backup Employee Scheduling Logic

### Task 5: Implement Backup Failover in Scheduling Engine

**Files:**
- Modify: `app/services/scheduling_engine.py` (add new method, update _schedule_juicer_event_wave2)
- Create: `tests/test_scheduling_backup_rotation.py`

**Step 1: Write failing test for backup rotation**

Create `tests/test_scheduling_backup_rotation.py`:
```python
import pytest
from datetime import datetime, timedelta
from app.services.scheduling_engine import SchedulingEngine

def test_backup_used_when_primary_unavailable(session, models):
    """Test that backup employee is used when primary has time-off"""
    Event = models['Event']
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    # Create employees
    primary = Employee(id="emp1", name="Primary Juicer", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup Juicer", job_title="Juicer Barista")
    session.add_all([primary, backup])
    session.commit()

    # Create rotation with backup
    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    session.add(rotation)
    session.commit()

    # Primary has time off today
    time_off = EmployeeTimeOff(
        employee_id='emp1',
        start_date=today.date(),
        end_date=today.date(),
        status='approved'
    )
    session.add(time_off)
    session.commit()

    # Create juicer event for today
    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12348,
        start_datetime=today,
        due_datetime=today + timedelta(days=1),
        event_type="Juicer Production",
        estimated_time=540
    )
    session.add(event)
    session.commit()

    run = SchedulerRunHistory(run_type='manual')
    session.add(run)
    session.commit()

    engine = SchedulingEngine(session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should be scheduled to backup, not primary
    assert event.is_scheduled
    pending = session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.employee_id == 'emp2'  # Backup employee

def test_primary_preferred_when_both_available(session, models):
    """Test that primary is used when both primary and backup are available"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    primary = Employee(id="emp1", name="Primary", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup", job_title="Juicer Barista")
    session.add_all([primary, backup])
    session.commit()

    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    session.add(rotation)
    session.commit()

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12349,
        start_datetime=today,
        due_datetime=today + timedelta(days=1),
        event_type="Juicer Production",
        estimated_time=540
    )
    session.add(event)
    session.commit()

    run = SchedulerRunHistory(run_type='manual')
    session.add(run)
    session.commit()

    engine = SchedulingEngine(session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should use primary
    assert event.is_scheduled
    pending = session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending.employee_id == 'emp1'  # Primary

def test_both_unavailable_creates_failed_schedule(session, models):
    """Test failure when both primary and backup are unavailable"""
    Event = models['Event']
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    primary = Employee(id="emp1", name="Primary", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup", job_title="Juicer Barista")
    session.add_all([primary, backup])
    session.commit()

    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    session.add(rotation)
    session.commit()

    # Both have time off
    for emp_id in ['emp1', 'emp2']:
        time_off = EmployeeTimeOff(
            employee_id=emp_id,
            start_date=today.date(),
            end_date=today.date(),
            status='approved'
        )
        session.add(time_off)
    session.commit()

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12350,
        start_datetime=today,
        due_datetime=today + timedelta(days=1),
        event_type="Juicer Production",
        estimated_time=540
    )
    session.add(event)
    session.commit()

    run = SchedulerRunHistory(run_type='manual')
    session.add(run)
    session.commit()

    engine = SchedulingEngine(session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should fail
    assert not event.is_scheduled
    pending = session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending.failure_reason is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduling_backup_rotation.py::test_backup_used_when_primary_unavailable -v`

Expected: FAIL - primary is used despite being unavailable

**Step 3: Add backup failover helper method**

In `app/services/scheduling_engine.py`, add this new method after `_get_juicer_time` (around line 1634):

```python
def _try_schedule_with_rotation_and_backup(
    self,
    run: object,
    event: object,
    target_date: datetime,
    schedule_time: time,
    rotation_type: str
) -> bool:
    """
    Try to schedule event with rotation employee, fallback to backup if needed

    Algorithm:
    1. Try primary rotation employee
    2. If primary invalid, try backup employee
    3. If both fail, create failed pending schedule

    Args:
        run: SchedulerRunHistory object
        event: Event to schedule
        target_date: Date to schedule on
        schedule_time: Time to schedule at
        rotation_type: 'juicer' or 'primary_lead'

    Returns:
        True if scheduled successfully, False otherwise
    """
    # Try primary rotation employee first
    primary_employee = self.rotation_manager.get_rotation_employee(
        target_date, rotation_type, try_backup=False
    )

    if primary_employee:
        schedule_datetime = datetime.combine(target_date.date(), schedule_time)
        validation = self.validator.validate_assignment(event, primary_employee, schedule_datetime)

        if validation.is_valid:
            # Primary is available - schedule it
            self._create_pending_schedule(run, event, primary_employee, schedule_datetime, False, None, None)
            run.events_scheduled += 1
            current_app.logger.info(
                f"Scheduled {rotation_type} event {event.project_ref_num} to {primary_employee.name} (primary) on {target_date.date()}"
            )
            return True
        else:
            # Log why primary was rejected
            primary_reasons = ", ".join([v.message for v in validation.violations])
            current_app.logger.info(
                f"Primary {rotation_type} {primary_employee.name} unavailable: {primary_reasons}. Trying backup..."
            )

    # Primary unavailable or doesn't exist - try backup
    backup_employee = self.rotation_manager.get_rotation_employee(
        target_date, rotation_type, try_backup=True
    )

    if backup_employee and (not primary_employee or backup_employee.id != primary_employee.id):
        schedule_datetime = datetime.combine(target_date.date(), schedule_time)
        validation = self.validator.validate_assignment(event, backup_employee, schedule_datetime)

        if validation.is_valid:
            # Backup is available - schedule it
            self._create_pending_schedule(run, event, backup_employee, schedule_datetime, False, None, None)
            run.events_scheduled += 1
            current_app.logger.info(
                f"Scheduled {rotation_type} event {event.project_ref_num} to {backup_employee.name} (BACKUP) on {target_date.date()}"
            )
            return True
        else:
            backup_reasons = ", ".join([v.message for v in validation.violations])
            current_app.logger.warning(
                f"Backup {rotation_type} {backup_employee.name} also unavailable: {backup_reasons}"
            )

    # Both primary and backup failed
    primary_reason = f"No primary {rotation_type} assigned" if not primary_employee else "Primary unavailable"
    backup_reason = f"No backup configured" if not backup_employee else "Backup also unavailable"

    self._create_failed_pending_schedule(
        run, event,
        f"{primary_reason} and {backup_reason} for {target_date.date()}"
    )
    run.events_failed += 1
    return False
```

**Step 4: Update _schedule_juicer_event_wave2 to use backup logic**

Replace the portion of `_schedule_juicer_event_wave2` after the date validation (starting around line 1668):

```python
    # Validate target date is not past the due date
    if target_date.date() > event.due_datetime.date():
        self._create_failed_pending_schedule(
            run, event,
            f"Event start date {event_start_date} is in the past and due date {event.due_datetime.date()} has also passed"
        )
        run.events_failed += 1
        return

    # Try to schedule with rotation (primary first, backup if needed)
    self._try_schedule_with_rotation_and_backup(
        run, event, target_date, juicer_time, 'juicer'
    )
```

Remove the old logic that only tried primary employee (lines ~1668-1684).

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scheduling_backup_rotation.py -v`

Expected: PASS (3 tests)

**Step 6: Run all scheduling tests**

Run: `pytest tests/test_scheduling*.py -v`

Expected: All tests pass

**Step 7: Commit backup rotation logic**

```bash
git add app/services/scheduling_engine.py tests/test_scheduling_backup_rotation.py
git commit -m "feat: add backup rotation failover to scheduling engine

- Add _try_schedule_with_rotation_and_backup() helper method
- Try primary rotation employee first
- Automatically fall back to backup if primary unavailable
- Log which employee type was used (primary/BACKUP)
- Fail only if both primary and backup unavailable
- Update juicer event scheduling to use backup logic
- Add comprehensive tests for backup failover scenarios"
```

---

## Phase 6: Update API Endpoints for Backup Configuration

### Task 6: Add Backup Support to Rotation API

**Files:**
- Modify: `app/routes/api.py` (find rotation endpoints and update)
- Note: If rotation endpoints don't exist yet, document that UI/API will be needed

**Step 1: Search for existing rotation endpoints**

Run:
```bash
grep -n "rotation" app/routes/api.py | grep -i "def\|@.*route"
```

**Step 2: If endpoints exist, update them**

Update POST/PUT endpoints to accept `backup_employee_id`:

```python
# Example structure - adjust to match actual endpoint patterns
@api_bp.route('/api/rotations', methods=['POST'])
def create_or_update_rotation():
    data = request.get_json()

    # Validate backup is different from primary
    if data.get('backup_employee_id') and data.get('backup_employee_id') == data.get('employee_id'):
        return jsonify({'success': False, 'error': 'Backup employee must be different from primary'}), 400

    # ... rest of endpoint logic
    # Make sure to include backup_employee_id in rotation creation/update
```

Update GET endpoints to include `backup_employee_id` in response:

```python
# Include backup employee details in response
rotation_data = {
    'id': rotation.id,
    'day_of_week': rotation.day_of_week,
    'rotation_type': rotation.rotation_type,
    'employee_id': rotation.employee_id,
    'employee_name': rotation.employee.name if rotation.employee else None,
    'backup_employee_id': rotation.backup_employee_id,  # NEW
    'backup_employee_name': rotation.backup_employee.name if rotation.backup_employee else None,  # NEW
}
```

**Step 3: If no rotation endpoints exist**

Document that API endpoints need to be created:
- Create `app/routes/api_rotations.py` blueprint
- Add CRUD endpoints for rotation management
- Include backup_employee_id in all operations
- (This can be a follow-up task or separate feature)

**Step 4: Test API changes manually**

If endpoints were updated, test with curl:
```bash
# Create rotation with backup
curl -X POST http://localhost:5000/api/rotations \
  -H "Content-Type: application/json" \
  -d '{"day_of_week": 0, "rotation_type": "juicer", "employee_id": "emp1", "backup_employee_id": "emp2"}'

# Get rotations (should include backup)
curl http://localhost:5000/api/rotations
```

**Step 5: Commit API changes**

```bash
git add app/routes/api*.py
git commit -m "feat: add backup employee support to rotation API endpoints

- Accept backup_employee_id in POST/PUT rotation endpoints
- Validate backup differs from primary
- Include backup employee details in GET responses
- Enable UI configuration of backup rotations"
```

---

## Phase 7: Documentation and Changelog

### Task 7: Document Changes

**Files:**
- Create: `changelog/2026-01-28-auto-scheduler-backup-rotation.md`
- Modify: `changelog/README.md`

**Step 1: Create changelog**

Create `changelog/2026-01-28-auto-scheduler-backup-rotation.md`:

```markdown
# Auto-Scheduler: Date Fix and Backup Rotation

**Date:** 2026-01-28
**Type:** Enhancement + Bug Fix

## Summary
Fixed auto-scheduler attempting to schedule juicer events on past dates, and added backup rotation configuration for automatic failover when primary employees are unavailable.

## Changes Made

### Files Modified
- `app/models/auto_scheduler.py` (lines 58-87)
  - Added `backup_employee_id` field to RotationAssignment model
  - Added `backup_employee` relationship
  - Updated `__repr__` to show backup info

- `app/services/rotation_manager.py` (lines 32-95)
  - Added `try_backup` parameter to `get_rotation_employee()`
  - Added `get_rotation_with_backup()` helper method
  - Returns backup employee when requested

- `app/services/scheduling_engine.py` (lines 1635-1750)
  - Fixed past date logic in `_schedule_juicer_event_wave2()`
  - Added `_try_schedule_with_rotation_and_backup()` helper
  - Automatic failover to backup when primary unavailable
  - Enhanced logging for date adjustments and backup usage

- `app/routes/api.py` (rotation endpoints)
  - Added `backup_employee_id` to rotation CRUD operations
  - Validation to ensure backup differs from primary
  - Include backup employee in API responses

### Database Changes
- Migration: Add `backup_employee_id` column to `rotation_assignments` table
- Foreign key constraint to `employees` table
- Nullable column (backward compatible)

### Business Logic Changes

**Past Date Handling:**
- If event `start_date` is in the past, use today as target date
- Fail only if both `start_date` and `due_date` are in the past
- Log when date adjustment occurs

**Backup Rotation:**
- Try primary rotation employee first
- Automatically fall back to backup if primary unavailable
- Fail only if both primary and backup unavailable
- Clear logging shows whether primary or backup was used

## Bug Fixes
- **Issue:** Auto-scheduler attempted to schedule events on past dates
- **Root Cause:** `_schedule_juicer_event_wave2` used `event.start_datetime` directly without checking if it was in the past
- **Resolution:** Added date comparison logic to use today if start date has passed

## Testing
- Added `tests/test_rotation_manager_backup.py` - Backup employee lookup tests (3 tests)
- Added `tests/test_scheduling_past_dates.py` - Past date handling tests (3 tests)
- Added `tests/test_scheduling_backup_rotation.py` - Backup failover tests (3 tests)
- All existing tests continue to pass

## Related Files
- Design document: `docs/plans/2026-01-28-auto-scheduler-date-fix-and-backup-rotation-design.md`
- Implementation plan: `docs/plans/2026-01-28-auto-scheduler-backup-rotation-implementation.md`
```

**Step 2: Update changelog index**

Add to `changelog/README.md`:
```markdown
- [2026-01-28-auto-scheduler-backup-rotation.md](2026-01-28-auto-scheduler-backup-rotation.md) - Auto-scheduler date fix and backup rotation configuration
```

**Step 3: Commit documentation**

```bash
git add changelog/
git commit -m "docs: add changelog for auto-scheduler backup rotation feature

- Document past date fix
- Document backup rotation system
- List all files changed
- Include testing summary"
```

---

## Phase 8: Final Verification

### Task 8: End-to-End Testing

**Step 1: Run full test suite**

Run: `pytest -v`

Expected: All tests pass

**Step 2: Test on test instance**

```bash
./start_test_instance.sh
# Access test instance and verify:
# 1. Create rotation with backup employee
# 2. Create juicer event with past start date
# 3. Mark primary employee unavailable
# 4. Run auto-scheduler
# 5. Verify event scheduled to backup with today's date
./cleanup_test_instance.sh
```

**Step 3: Review all commits**

Run: `git log --oneline feature/auto-scheduler-backup-rotation`

Expected: Clean, descriptive commit history

**Step 4: Final commit if needed**

If any final tweaks were made during testing:
```bash
git add .
git commit -m "chore: final verification and cleanup"
```

---

## Summary

**Implementation complete! The plan includes:**

✅ **Phase 1:** Database migration for `backup_employee_id`
✅ **Phase 2:** Updated RotationAssignment model
✅ **Phase 3:** Enhanced RotationManager service with backup lookup
✅ **Phase 4:** Fixed past date logic in scheduling engine
✅ **Phase 5:** Added backup failover to scheduling engine
✅ **Phase 6:** Updated API endpoints for backup configuration
✅ **Phase 7:** Comprehensive documentation and changelog
✅ **Phase 8:** End-to-end verification

**Total tasks:** 8 main tasks, ~40 individual steps
**Estimated time:** 2-3 hours for experienced developer
**Testing:** 9 new tests added, all existing tests maintained
