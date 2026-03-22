# Core Event Scheduling Logic Rewrite

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Wave 2 Core event scheduling logic so it always tries empty slots first (with correct employee priority), then bumps, and respects a 3-day/7-day short-notice notification system. Apply the same notification system to the CP-SAT solver.

**Architecture:** Replace `_schedule_core_events_wave2_new()` with a simplified day-by-day loop: for each unstaffed Core event (sorted by due date), iterate from start_date (or tomorrow if past) through due_date. On each day, try empty slots first (leads → specialists by weekly count), then bump. Add a `ScheduleNotification` model to track short-notice assignments that need supervisor acknowledgment. Add a page under `/auto-schedule/notifications` for the supervisor to review and mark as notified. For the CP-SAT solver, add a post-extraction pass that creates notifications for any schedules assigned within 7 days.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, existing factory-pattern models, Alembic migrations

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/services/scheduling_engine.py` | Modify | Rewrite `_schedule_core_events_wave2_new`, update `_try_fill_empty_slot` for primary-lead time slot |
| `app/services/cpsat_scheduler.py` | Modify | Add `_create_short_notice_notifications` post-extraction pass |
| `app/models/auto_scheduler.py` | Modify | Add `ScheduleNotification` model to factory function |
| `app/models/__init__.py` | Modify | Register `ScheduleNotification` in model dict |
| `app/routes/auto_scheduler.py` | Modify | Add notifications route |
| `app/templates/auto_schedule_notifications.html` | Create | Notification tracking page |
| `migrations/versions/xxxx_add_schedule_notifications.py` | Create | DB migration |
| `tests/test_core_scheduling_rewrite.py` | Create | Tests for new scheduling logic |

---

## Chunk 1: Model & Migration

### Task 1: Add ScheduleNotification model

**Files:**
- Modify: `app/models/auto_scheduler.py:50-404` (inside `create_auto_scheduler_models`)
- Modify: `app/models/__init__.py:37,59`

- [ ] **Step 1: Write the failing test for ScheduleNotification model**

Create `tests/test_core_scheduling_rewrite.py`:

```python
import pytest
from datetime import datetime, date, time, timedelta


class TestScheduleNotificationModel:
    """Test the ScheduleNotification model CRUD operations."""

    def test_create_schedule_notification(self, db_session, models):
        """ScheduleNotification can be created with required fields."""
        ScheduleNotification = models['ScheduleNotification']
        Employee = models['Employee']
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        # Setup
        emp = Employee(id="emp1", name="Test Employee", job_title="Event Specialist")
        db_session.add(emp)

        today = datetime.now()
        event = Event(
            project_ref_num=99999,
            project_name="Test Core Event",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today,
            due_datetime=today + timedelta(days=14),
            estimated_time=60,
        )
        db_session.add(event)

        run = SchedulerRunHistory(
            run_type='manual',
            started_at=datetime.utcnow(),
            status='running',
            solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()

        notification = ScheduleNotification(
            scheduler_run_id=run.id,
            event_ref_num=99999,
            employee_id="emp1",
            schedule_date=today.date() + timedelta(days=5),
            schedule_time=time(10, 15),
            days_notice=5,
        )
        db_session.add(notification)
        db_session.commit()

        saved = db_session.query(ScheduleNotification).first()
        assert saved is not None
        assert saved.event_ref_num == 99999
        assert saved.employee_id == "emp1"
        assert saved.days_notice == 5
        assert saved.notified is False
        assert saved.notified_at is None

    def test_mark_notification_as_notified(self, db_session, models):
        """Notification can be marked as acknowledged by supervisor."""
        ScheduleNotification = models['ScheduleNotification']
        Employee = models['Employee']
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        emp = Employee(id="emp2", name="Test Employee 2", job_title="Lead Event Specialist")
        db_session.add(emp)

        today = datetime.now()
        event = Event(
            project_ref_num=99998,
            project_name="Test Core Event 2",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today,
            due_datetime=today + timedelta(days=14),
            estimated_time=60,
        )
        db_session.add(event)

        run = SchedulerRunHistory(
            run_type='manual',
            started_at=datetime.utcnow(),
            status='running',
            solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()

        notification = ScheduleNotification(
            scheduler_run_id=run.id,
            event_ref_num=99998,
            employee_id="emp2",
            schedule_date=today.date() + timedelta(days=4),
            schedule_time=time(10, 15),
            days_notice=4,
        )
        db_session.add(notification)
        db_session.commit()

        # Mark as notified
        notification.notified = True
        notification.notified_at = datetime.utcnow()
        notification.notified_by = "supervisor"
        db_session.commit()

        saved = db_session.query(ScheduleNotification).first()
        assert saved.notified is True
        assert saved.notified_at is not None
        assert saved.notified_by == "supervisor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestScheduleNotificationModel -v`
Expected: FAIL with `KeyError: 'ScheduleNotification'`

- [ ] **Step 3: Add ScheduleNotification to auto_scheduler.py**

In `app/models/auto_scheduler.py`, add the new model class inside `create_auto_scheduler_models()` just before the `return` statement (line ~403), and update the return tuple.

```python
    class ScheduleNotification(db.Model):
        """
        Tracks short-notice schedule assignments that need supervisor acknowledgment.

        When the auto-scheduler assigns an employee to an event within 7 days,
        a notification record is created. The supervisor must acknowledge they
        have notified the employee. Records within 3 days are only created
        when emergency mode is active.
        """
        __tablename__ = 'schedule_notifications'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        scheduler_run_id = db.Column(
            db.Integer,
            db.ForeignKey('scheduler_run_history.id', ondelete='CASCADE'),
            nullable=False
        )
        event_ref_num = db.Column(
            db.Integer,
            db.ForeignKey('events.project_ref_num'),
            nullable=False
        )
        employee_id = db.Column(
            db.String,
            db.ForeignKey('employees.id'),
            nullable=False
        )
        schedule_date = db.Column(db.Date, nullable=False)
        schedule_time = db.Column(db.Time, nullable=False)
        days_notice = db.Column(db.Integer, nullable=False)  # How many days notice

        # Supervisor acknowledgment
        notified = db.Column(db.Boolean, default=False, nullable=False)
        notified_at = db.Column(db.DateTime, nullable=True)
        notified_by = db.Column(db.String(100), nullable=True)

        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        # Relationships
        event = db.relationship('Event', foreign_keys=[event_ref_num])
        employee = db.relationship('Employee', backref='schedule_notifications')
        scheduler_run = db.relationship('SchedulerRunHistory', foreign_keys=[scheduler_run_id])

        __table_args__ = (
            db.Index('idx_schedule_notifications_run', 'scheduler_run_id'),
            db.Index('idx_schedule_notifications_notified', 'notified'),
        )

        def __repr__(self):
            status = "notified" if self.notified else "pending"
            return f'<ScheduleNotification {self.id}: Event {self.event_ref_num} ({status})>'
```

Also update the `return` statement to include `ScheduleNotification`:

```python
    return (RotationAssignment, PendingSchedule, SchedulerRunHistory,
            ScheduleException, EventSchedulingOverride, LockedDay,
            EventTypeOverride, ScheduleNotification)
```

- [ ] **Step 4: Register ScheduleNotification in `app/models/__init__.py`**

Update the unpacking on line 37 to include `ScheduleNotification`:

```python
(RotationAssignment, PendingSchedule, SchedulerRunHistory, ScheduleException,
 EventSchedulingOverride, LockedDay, EventTypeOverride,
 ScheduleNotification) = create_auto_scheduler_models(db)
```

Add to the return dict (after `'EventTypeOverride'`):

```python
'ScheduleNotification': ScheduleNotification,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestScheduleNotificationModel -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Create migration**

```bash
./backup_now.sh
flask db migrate -m "add schedule_notifications table"
# Review the generated migration file
flask db upgrade
```

- [ ] **Step 7: Commit**

```bash
git add app/models/auto_scheduler.py app/models/__init__.py \
       tests/test_core_scheduling_rewrite.py migrations/versions/
git commit -m "feat: add ScheduleNotification model for short-notice tracking"
```

---

## Chunk 2: Core Scheduling Logic Rewrite

### Task 2: Rewrite `_schedule_core_events_wave2_new`

**Files:**
- Modify: `app/services/scheduling_engine.py:1840-1975`

The new logic:
1. Sort unstaffed Core events by due date (earliest first)
2. For each event, search day-by-day from `max(start_date, tomorrow)` to `due_date`
3. On each day:
   - **Skip if within 3 days** unless `self.emergency_mode` is True
   - **Skip if day is locked**
   - **Try empty slots first** via `_try_fill_empty_slot()`
   - **If no empty slots**, try bump via `_try_bump_for_day()`
   - **If scheduled within 7 days**, create a `ScheduleNotification`
4. If bumped, re-add bumped event to queue and re-sort
5. If not scheduled by due date, create failure record

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_core_scheduling_rewrite.py`:

```python
class TestCoreSchedulingWave2:
    """Test the rewritten Wave 2 Core scheduling logic."""

    def _setup_basic(self, db_session, models):
        """Helper: create a Lead, a Specialist, and an engine."""
        Employee = models['Employee']
        RotationAssignment = models['RotationAssignment']

        lead = Employee(
            id="lead1", name="Lead One",
            job_title="Lead Event Specialist", is_active=True
        )
        specialist = Employee(
            id="spec1", name="Specialist One",
            job_title="Event Specialist", is_active=True
        )
        db_session.add_all([lead, specialist])
        db_session.flush()

        # Make lead the primary lead for all weekdays
        for day in range(5):
            ra = RotationAssignment(
                day_of_week=day,
                rotation_type='primary_lead',
                employee_id="lead1",
            )
            db_session.add(ra)
        db_session.flush()

        from app.services.scheduling_engine import SchedulingEngine
        engine = SchedulingEngine(db_session, models)
        return engine, lead, specialist

    def test_empty_slot_tried_before_bump(self, db_session, models):
        """When an unscheduled employee exists, should fill empty slot, never bump."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        # Event starts 5 days from now (outside 3-day buffer), due in 14 days
        start = today + timedelta(days=5)
        event = Event(
            project_ref_num=10001,
            project_name="Test Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=9),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0
        assert event.is_scheduled is True

        # Should have created a pending schedule (empty slot, not a bump)
        pending = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.event_ref_num == 10001,
            PendingSchedule.failure_reason.is_(None),
        ).first()
        assert pending is not None
        assert pending.is_swap is False  # Filled empty slot, not a bump

    def test_3day_buffer_respected(self, db_session, models):
        """Events within 3 days should NOT be scheduled unless emergency mode."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        today = datetime.now()
        # Event that can ONLY be scheduled within 3 days (start=tomorrow, due=3 days)
        event = Event(
            project_ref_num=10002,
            project_name="Urgent Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today + timedelta(days=1),
            due_datetime=today + timedelta(days=3),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        # Without emergency mode — should fail
        engine.emergency_mode = False
        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 1  # Could not schedule within buffer

    def test_3day_buffer_bypassed_in_emergency(self, db_session, models):
        """In emergency mode, 3-day buffer is ignored."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        today = datetime.now()
        event = Event(
            project_ref_num=10003,
            project_name="Emergency Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today + timedelta(days=1),
            due_datetime=today + timedelta(days=3),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        # With emergency mode — should succeed
        engine.emergency_mode = True
        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

    def test_7day_notification_created(self, db_session, models):
        """Scheduling within 7 days should create a ScheduleNotification."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        ScheduleNotification = models['ScheduleNotification']

        today = datetime.now()
        # Event starts 4 days out (inside 7 days, outside 3 days)
        start = today + timedelta(days=4)
        event = Event(
            project_ref_num=10004,
            project_name="Short Notice Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=3),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

        # Should have created a short-notice notification
        notif = db_session.query(ScheduleNotification).filter(
            ScheduleNotification.event_ref_num == 10004,
        ).first()
        assert notif is not None
        assert notif.days_notice <= 7
        assert notif.notified is False

    def test_bump_only_when_no_empty_slots(self, db_session, models):
        """Bump should only happen when all employees are already scheduled."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        start = today + timedelta(days=5)

        # Event A: already scheduled (takes lead's slot)
        event_a = Event(
            project_ref_num=10010,
            project_name="Existing Core A",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=14),
            estimated_time=60,
        )
        # Event B: already scheduled (takes specialist's slot)
        event_b = Event(
            project_ref_num=10011,
            project_name="Existing Core B",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=14),
            estimated_time=60,
        )
        # Event C: more urgent, needs to bump one of the above
        event_c = Event(
            project_ref_num=10012,
            project_name="Urgent Core C",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=7),
            estimated_time=60,
        )
        db_session.add_all([event_a, event_b, event_c])
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        # Schedule A and B first (they fill all slots)
        failed = engine._schedule_core_events_wave2_new(run, [event_a, event_b, event_c])

        # All 3 should be scheduled (C bumps the one with latest due date)
        scheduled = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.failure_reason.is_(None),
            PendingSchedule.status != 'superseded',
        ).count()
        # At minimum, C should be scheduled
        assert event_c.is_scheduled is True

    def test_primary_lead_gets_first_time_slot(self, db_session, models):
        """Primary Lead Event Specialist should always be scheduled at 10:15."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        start = today + timedelta(days=5)

        event = Event(
            project_ref_num=10020,
            project_name="Primary Lead Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=9),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

        pending = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.event_ref_num == 10020,
            PendingSchedule.failure_reason.is_(None),
        ).first()
        assert pending is not None
        assert pending.employee_id == "lead1"  # Primary lead gets priority
        # Primary lead should get 10:15 (first CORE_TIME_SLOT)
        first_slot = engine.CORE_TIME_SLOTS[0] if engine.CORE_TIME_SLOTS else time(10, 15)
        assert pending.schedule_time == first_slot

    def test_search_starts_from_event_start_not_tomorrow(self, db_session, models):
        """Search should start from event start date, not always tomorrow."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        # Event starts 10 days from now
        start = today + timedelta(days=10)
        event = Event(
            project_ref_num=10030,
            project_name="Future Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=5),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

        pending = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.event_ref_num == 10030,
            PendingSchedule.failure_reason.is_(None),
        ).first()
        assert pending is not None
        # Should be scheduled on or after start date, not tomorrow
        assert pending.schedule_datetime.date() >= start.date()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestCoreSchedulingWave2 -v`
Expected: Multiple failures (old logic doesn't match new expectations)

- [ ] **Step 3: Rewrite `_schedule_core_events_wave2_new`**

Replace lines 1840-1975 of `app/services/scheduling_engine.py` with:

```python
    def _schedule_core_events_wave2_new(self, run: object, events: List[object]) -> List[object]:
        """
        Wave 2: Schedule Core events using day-by-day empty-slot-first logic

        For each unstaffed Core event (sorted by due date, most urgent first):
        1. Search day-by-day from max(start_date, tomorrow) through due_date
        2. On each day:
           a. Skip if within 3 days and not emergency mode
           b. Skip if day is locked
           c. Try to fill an empty slot (leads first, then specialists by weekly count)
           d. If no empty slots, try to bump an event with a later due date
        3. If bump succeeds, put bumped event back in queue
        4. If scheduled within 7 days, create a ScheduleNotification

        Returns:
            List of events that could not be scheduled (for user review)
        """
        current_app.logger.info("=== WAVE 2: Core Events (Empty-Slot-First Logic) ===")

        # Get all unstaffed Core events and sort by due date (most urgent first)
        unstaffed_core = [e for e in events if e.event_type == 'Core' and not e.is_scheduled]
        unstaffed_core.sort(key=lambda e: e.due_datetime)

        failed_events = []
        today = datetime.now()

        current_app.logger.info(f"Processing {len(unstaffed_core)} unstaffed Core events")

        while unstaffed_core:
            event = unstaffed_core.pop(0)

            current_app.logger.info(
                f"Processing Core event {event.project_ref_num} "
                f"(start: {event.start_datetime.date()}, due: {event.due_datetime.date()})"
            )

            scheduled = False
            locked_days_encountered = []

            # Start from event's start date or tomorrow, whichever is later
            search_start = max(event.start_datetime, today + timedelta(days=1))
            search_end = event.due_datetime
            current_date = search_start

            while current_date < search_end and not scheduled:
                days_from_now = (current_date.date() - today.date()).days

                current_app.logger.info(
                    f"  Checking date {current_date.date()} (day {days_from_now} from now)"
                )

                # Within 3 days: skip unless emergency mode
                if days_from_now <= 3 and not self.emergency_mode:
                    current_app.logger.info(
                        f"  Skipping {current_date.date()} — within 3-day buffer (use emergency mode to override)"
                    )
                    current_date += timedelta(days=1)
                    continue

                # Skip locked days entirely
                if self._is_day_locked(current_date):
                    locked_info = self._get_locked_day_info(current_date)
                    reason = locked_info.reason if locked_info else "Unknown"
                    locked_days_encountered.append(current_date.date())
                    current_app.logger.info(
                        f"  Skipping {current_date.date()} — day is LOCKED (reason: {reason})"
                    )
                    current_date += timedelta(days=1)
                    continue

                # STEP 1: Try to fill an empty slot (unscheduled employee)
                if self._try_fill_empty_slot(run, event, current_date, events):
                    scheduled = True
                    event.is_scheduled = True
                    current_app.logger.info(
                        f"  SUCCESS: Filled empty slot for {event.project_ref_num}"
                    )

                    # Create short-notice notification if within 7 days
                    if days_from_now <= 7:
                        self._create_short_notice_notification(run, event, current_date)
                else:
                    # STEP 2: No empty slots available — try to bump
                    bumped_event = self._try_bump_for_day(run, event, current_date, events)
                    if bumped_event:
                        scheduled = True
                        event.is_scheduled = True
                        # Re-insert bumped event into queue and re-sort by due date
                        unstaffed_core.append(bumped_event)
                        unstaffed_core.sort(key=lambda e: e.due_datetime)
                        current_app.logger.info(
                            f"  SUCCESS: Scheduled {event.project_ref_num}, "
                            f"bumped {bumped_event.project_ref_num} back to queue"
                        )

                        # Create short-notice notification if within 7 days
                        if days_from_now <= 7:
                            self._create_short_notice_notification(run, event, current_date)

                # Move to next day
                current_date += timedelta(days=1)

            # If not scheduled by due date, add to failed list
            if not scheduled:
                failure_reason = (
                    f"Could not find slot or event to bump within valid window "
                    f"(start: {event.start_datetime.date()}, due: {event.due_datetime.date()})"
                )
                if locked_days_encountered:
                    locked_str = ", ".join(str(d) for d in locked_days_encountered)
                    failure_reason += f". Days locked: {locked_str}"

                current_app.logger.warning(
                    f"FAILED: Could not schedule Core event {event.project_ref_num} "
                    f"(due {event.due_datetime.date()}). {failure_reason}"
                )
                failed_events.append(event)
                self._create_failed_pending_schedule(run, event, failure_reason)
                run.events_failed += 1

        scheduled_count = run.events_scheduled
        current_app.logger.info(
            f"Wave 2 complete: {scheduled_count} scheduled, {len(failed_events)} failed"
        )

        return failed_events
```

- [ ] **Step 4: Add `_create_short_notice_notification` helper**

Add this method to the `SchedulingEngine` class (after `_create_failed_pending_schedule`):

```python
    def _create_short_notice_notification(self, run: object, event: object,
                                          schedule_date: datetime) -> None:
        """
        Create a ScheduleNotification for a short-notice schedule (within 7 days).

        The supervisor must acknowledge they have notified the employee.
        """
        ScheduleNotification = self.models.get('ScheduleNotification')
        if not ScheduleNotification:
            current_app.logger.warning(
                "ScheduleNotification model not available — skipping notification"
            )
            return

        # Find the pending schedule we just created for this event
        pending = self.db.query(self.PendingSchedule).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.event_ref_num == event.project_ref_num,
            self.PendingSchedule.failure_reason.is_(None),
            self.PendingSchedule.status != 'superseded',
        ).first()

        if not pending or not pending.employee_id:
            return

        days_notice = (schedule_date.date() - datetime.now().date()).days

        notification = ScheduleNotification(
            scheduler_run_id=run.id,
            event_ref_num=event.project_ref_num,
            employee_id=pending.employee_id,
            schedule_date=schedule_date.date(),
            schedule_time=pending.schedule_time,
            days_notice=days_notice,
        )
        self.db.add(notification)
        self.db.flush()

        current_app.logger.info(
            f"  SHORT NOTICE: Created notification for {event.project_ref_num} "
            f"({days_notice} days notice, employee {pending.employee.name})"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestCoreSchedulingWave2 -v`
Expected: PASS (all 7 tests)

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `pytest -v --timeout=120`
Expected: No new failures

- [ ] **Step 7: Commit**

```bash
git add app/services/scheduling_engine.py tests/test_core_scheduling_rewrite.py
git commit -m "feat: rewrite Wave 2 Core scheduling — empty slots first, 3-day buffer, 7-day notifications"
```

---

### Task 3: Update `_try_fill_empty_slot` for lead priority and primary lead time slot

**Files:**
- Modify: `app/services/scheduling_engine.py:2096-2254` (`_try_fill_empty_slot` method)

The employee pool ordering is already correct (Lead=0 → Specialist=1 → Juicer-as-Specialist=2),
so all Lead Event Specialists are tried before any Event Specialists. Within each tier,
employees are sorted by lowest weekly Core count (Sun-Sat).

What's missing is the **time slot** distinction for leads:
- **Primary Lead** for that date → always use first CORE_TIME_SLOT (10:15)
- **Other Leads** → use `_find_least_busy_time_slot`
- **Event Specialists** (only tried after ALL leads are scheduled) → use `_find_least_busy_time_slot`

- [ ] **Step 1: The test `test_primary_lead_gets_first_time_slot` already covers this**

This was written in Task 2. If it's still failing after Task 2, that failure guides this task.

- [ ] **Step 2: Modify `_try_fill_empty_slot`**

In `app/services/scheduling_engine.py`, replace the time-slot selection block inside the employee loop (around lines 2219-2226):

**Current code (lines 2219-2226):**
```python
            # Find the time slot with fewest scheduled employees
            time_slot = self._find_least_busy_time_slot(run, target_date_obj)

            if not time_slot:
                current_app.logger.error(f"    ERROR: _find_least_busy_time_slot returned None for {target_date_obj}")
                continue

            schedule_datetime = datetime.combine(target_date_obj, time_slot)
```

**Replace with:**
```python
            # Determine time slot based on employee role
            # Primary Lead for this date always gets the first CORE_TIME_SLOT (10:15)
            primary_lead = self.rotation_manager.get_rotation_employee(target_date, 'primary_lead')
            first_slot = self.CORE_TIME_SLOTS[0] if self.CORE_TIME_SLOTS else time(10, 15)

            if primary_lead and employee.id == primary_lead.id:
                time_slot = first_slot
            else:
                time_slot = self._find_least_busy_time_slot(run, target_date_obj)

            if not time_slot:
                current_app.logger.error(f"    ERROR: Could not determine time slot for {target_date_obj}")
                continue

            schedule_datetime = datetime.combine(target_date_obj, time_slot)
```

- [ ] **Step 3: Run the specific test**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestCoreSchedulingWave2::test_primary_lead_gets_first_time_slot -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest -v --timeout=120`
Expected: No new failures

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduling_engine.py
git commit -m "feat: primary lead always scheduled at first Core time slot (10:15)"
```

---

## Chunk 3: Notification UI

### Task 4: Add notifications route and page

**Files:**
- Modify: `app/routes/auto_scheduler.py`
- Create: `app/templates/auto_schedule_notifications.html`

- [ ] **Step 1: Add the notification list and acknowledge routes**

Add to `app/routes/auto_scheduler.py`:

```python
@auto_scheduler_bp.route('/notifications')
@require_authentication()
def notifications():
    """Short-notice schedule notifications that need supervisor acknowledgment."""
    models = get_models()
    ScheduleNotification = models.get('ScheduleNotification')

    if not ScheduleNotification:
        return render_template('auto_schedule_notifications.html', notifications=[], error="Notifications not available")

    # Get filter: 'pending' (default) or 'all'
    show_filter = request.args.get('filter', 'pending')

    query = ScheduleNotification.query.order_by(ScheduleNotification.schedule_date.asc())
    if show_filter == 'pending':
        query = query.filter(ScheduleNotification.notified == False)

    notifications = query.all()

    return render_template(
        'auto_schedule_notifications.html',
        notifications=notifications,
        current_filter=show_filter,
    )


@auto_scheduler_bp.route('/notifications/<int:notification_id>/acknowledge', methods=['POST'])
@require_authentication()
def acknowledge_notification(notification_id):
    """Mark a notification as acknowledged (employee has been notified)."""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    ScheduleNotification = models.get('ScheduleNotification')

    if not ScheduleNotification:
        return jsonify({'status': 'error', 'error': 'Notifications not available'}), 400

    notification = ScheduleNotification.query.get(notification_id)
    if not notification:
        return jsonify({'status': 'error', 'error': 'Notification not found'}), 404

    notification.notified = True
    notification.notified_at = datetime.utcnow()
    notification.notified_by = request.form.get('notified_by', 'supervisor')
    db.session.commit()

    return jsonify({'status': 'success', 'message': 'Notification acknowledged'})
```

- [ ] **Step 2: Create the notification page template**

Create `app/templates/auto_schedule_notifications.html`:

```html
{% extends "base.html" %}

{% block title %}Short-Notice Notifications{% endblock %}

{% block content %}
<div class="container-fluid py-3">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h2>Short-Notice Schedule Notifications</h2>
        <div>
            <a href="{{ url_for('auto_scheduler.notifications', filter='pending') }}"
               class="btn btn-sm {{ 'btn-primary' if current_filter == 'pending' else 'btn-outline-primary' }}">
                Pending
            </a>
            <a href="{{ url_for('auto_scheduler.notifications', filter='all') }}"
               class="btn btn-sm {{ 'btn-primary' if current_filter == 'all' else 'btn-outline-primary' }}">
                All
            </a>
        </div>
    </div>

    {% if not notifications %}
    <div class="alert alert-success">No pending notifications.</div>
    {% else %}
    <div class="table-responsive">
        <table class="table table-striped table-hover">
            <thead class="table-dark">
                <tr>
                    <th>Event</th>
                    <th>Employee</th>
                    <th>Scheduled Date</th>
                    <th>Time</th>
                    <th>Days Notice</th>
                    <th>Status</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {% for n in notifications %}
                <tr data-notification-id="{{ n.id }}">
                    <td>
                        <strong>{{ n.event.project_name if n.event else n.event_ref_num }}</strong>
                        <br><small class="text-muted">Ref: {{ n.event_ref_num }}</small>
                    </td>
                    <td>{{ n.employee.name if n.employee else n.employee_id }}</td>
                    <td>{{ n.schedule_date.strftime('%a %m/%d/%Y') }}</td>
                    <td>{{ n.schedule_time.strftime('%I:%M %p') }}</td>
                    <td>
                        {% if n.days_notice <= 3 %}
                        <span class="badge bg-danger">{{ n.days_notice }} days</span>
                        {% elif n.days_notice <= 5 %}
                        <span class="badge bg-warning text-dark">{{ n.days_notice }} days</span>
                        {% else %}
                        <span class="badge bg-info">{{ n.days_notice }} days</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if n.notified %}
                        <span class="badge bg-success">Notified</span>
                        <br><small class="text-muted">{{ n.notified_at.strftime('%m/%d %I:%M %p') if n.notified_at else '' }}</small>
                        {% else %}
                        <span class="badge bg-warning text-dark">Pending</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if not n.notified %}
                        <button class="btn btn-sm btn-success"
                                data-action="acknowledge-notification"
                                data-notification-id="{{ n.id }}">
                            Mark Notified
                        </button>
                        {% else %}
                        <span class="text-muted">Done</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
</div>

<script>
document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-action="acknowledge-notification"]');
    if (!btn) return;

    var id = btn.getAttribute('data-notification-id');
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = {'Content-Type': 'application/x-www-form-urlencoded'};
    if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken.getAttribute('content');
    }

    fetch('/auto-schedule/notifications/' + id + '/acknowledge', {
        method: 'POST',
        headers: headers,
        body: 'notified_by=supervisor'
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.status === 'success') {
            var row = btn.closest('tr');
            row.querySelector('td:nth-child(6)').innerHTML = '<span class="badge bg-success">Notified</span>';
            btn.parentElement.innerHTML = '<span class="text-muted">Done</span>';
        }
    });
});
</script>
{% endblock %}
```

- [ ] **Step 3: Add navigation link to auto-scheduler page**

In `app/templates/auto_scheduler_main.html`, add a link button near the top controls:

```html
<a href="{{ url_for('auto_scheduler.notifications') }}" class="btn btn-outline-warning btn-sm">
    Short-Notice Notifications
</a>
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -v --timeout=120`
Expected: No new failures

- [ ] **Step 5: Commit**

```bash
git add app/routes/auto_scheduler.py app/templates/auto_schedule_notifications.html \
       app/templates/auto_scheduler_main.html
git commit -m "feat: add short-notice notification page for supervisor acknowledgment"
```

---

## Chunk 4: CP-SAT Solver Alignment

### Task 6: Add short-notice notifications to CP-SAT solver

**Files:**
- Modify: `app/services/cpsat_scheduler.py:2048-2260` (`_extract_solution` method)
- Modify: `app/services/cpsat_scheduler.py:3361-3368` (finalize section of `run_auto_scheduler`)

The CP-SAT solver already handles the scheduling logic through constraints and objectives:
- **3-day buffer**: Already enforced via `SCHEDULING_WINDOW_DAYS = 3` in `_valid_days_for_event` (line 755)
- **Primary lead at block 1**: Already has soft weight `WEIGHT_LEAD_BLOCK1 = 25` (line 39)
- **Bump penalty**: Already penalized via `WEIGHT_BUMP = 200` (line 46)

What's missing: **short-notice notification creation** when the solver assigns events within 7 days.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_core_scheduling_rewrite.py`:

```python
class TestCPSATNotifications:
    """Test that CP-SAT solver creates short-notice notifications."""

    def test_cpsat_creates_notification_for_short_notice(self, db_session, models):
        """CP-SAT should create ScheduleNotification when scheduling within 7 days."""
        ScheduleNotification = models['ScheduleNotification']
        PendingSchedule = models['PendingSchedule']
        SchedulerRunHistory = models['SchedulerRunHistory']

        # Check if any pending schedules were created within 7 days
        # and have corresponding notifications
        # (This test validates the post-extraction hook)
        today = datetime.now()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='completed', solver_type='cpsat',
        )
        db_session.add(run)
        db_session.flush()

        # Simulate a pending schedule within 7 days
        Employee = models['Employee']
        Event = models['Event']
        emp = Employee(id="cpsat_emp1", name="CPSAT Test Emp", job_title="Event Specialist")
        db_session.add(emp)

        event = Event(
            project_ref_num=20001,
            project_name="CPSAT Short Notice",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today + timedelta(days=4),
            due_datetime=today + timedelta(days=10),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        schedule_dt = datetime.combine(
            (today + timedelta(days=5)).date(), time(10, 15)
        )
        ps = PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=20001,
            employee_id="cpsat_emp1",
            schedule_datetime=schedule_dt,
            schedule_time=schedule_dt.time(),
            status='proposed',
        )
        db_session.add(ps)
        db_session.flush()

        # Call the notification creation helper
        from app.services.cpsat_scheduler import CPSATSchedulingEngine
        engine = CPSATSchedulingEngine(db_session, models)
        engine._create_short_notice_notifications(run)

        notif = db_session.query(ScheduleNotification).filter(
            ScheduleNotification.event_ref_num == 20001,
        ).first()
        assert notif is not None
        assert notif.days_notice <= 7
        assert notif.employee_id == "cpsat_emp1"
        assert notif.notified is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestCPSATNotifications -v`
Expected: FAIL with `AttributeError: 'CPSATSchedulingEngine' object has no attribute '_create_short_notice_notifications'`

- [ ] **Step 3: Add `_create_short_notice_notifications` to CPSATSchedulingEngine**

Add this method to `app/services/cpsat_scheduler.py` (after `_create_pending_failure`):

```python
    def _create_short_notice_notifications(self, run):
        """
        Create ScheduleNotification records for any pending schedules within 7 days.

        Called after solution extraction (Phases 2-4) to track short-notice
        assignments that need supervisor acknowledgment.
        """
        ScheduleNotification = self.models.get('ScheduleNotification')
        if not ScheduleNotification:
            logger.warning("ScheduleNotification model not available — skipping")
            return

        today = date.today()

        # Find all successfully scheduled pending records from this run
        pending_schedules = self.db.query(self.PendingSchedule).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.employee_id.isnot(None),
            self.PendingSchedule.schedule_datetime.isnot(None),
            self.PendingSchedule.failure_reason.is_(None),
        ).all()

        count = 0
        for ps in pending_schedules:
            schedule_date = ps.schedule_datetime.date()
            days_notice = (schedule_date - today).days

            if days_notice <= 7:
                notification = ScheduleNotification(
                    scheduler_run_id=run.id,
                    event_ref_num=ps.event_ref_num,
                    employee_id=ps.employee_id,
                    schedule_date=schedule_date,
                    schedule_time=ps.schedule_time,
                    days_notice=days_notice,
                )
                self.db.add(notification)
                count += 1

        if count > 0:
            self.db.flush()
            logger.info(f"Created {count} short-notice notification(s) for run {run.id}")
```

- [ ] **Step 4: Call `_create_short_notice_notifications` in `run_auto_scheduler`**

In `app/services/cpsat_scheduler.py`, in the `run_auto_scheduler` method, add the call just before the `=== Finalize ===` section (around line 3361):

```python
            # === SHORT-NOTICE NOTIFICATIONS ===
            logger.info("=== Creating short-notice notifications ===")
            self._create_short_notice_notifications(run)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_core_scheduling_rewrite.py::TestCPSATNotifications -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest -v --timeout=120`
Expected: No new failures

- [ ] **Step 7: Commit**

```bash
git add app/services/cpsat_scheduler.py tests/test_core_scheduling_rewrite.py
git commit -m "feat: add short-notice notifications to CP-SAT solver"
```

---

## Chunk 5: Cleanup & Verification

### Task 5: Remove dead code from old days 1-3 bump-only logic

**Files:**
- Modify: `app/services/scheduling_engine.py`

- [ ] **Step 1: Verify old `_schedule_core_events_wave1` is not called**

Search for calls to `_schedule_core_events_wave1`. It should only be the dead reference at line 2334. If it's not called anywhere in the active flow, it's safe dead code but we should leave it with a NOTE comment since CLAUDE.md says it's kept for reference.

- [ ] **Step 2: Run full test suite one final time**

Run: `pytest -v --timeout=120`
Expected: All existing tests pass, plus the 9 new tests from this plan.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify all tests pass after Core scheduling rewrite"
```
