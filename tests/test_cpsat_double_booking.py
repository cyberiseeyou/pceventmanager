"""
Tests for CP-SAT double-booking bug fix (H11/H12 constraints)
and post-solve review safety net.

The bug: _add_emp_day_limits() and _add_emp_week_limits() only counted
new events being placed by the solver, ignoring existing posted Schedule
records. This allowed the solver to assign Core events to employees who
already had posted Core events on the same day.
"""
import pytest
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

from app.models import get_models, get_db
from app.services.cpsat_scheduler import (
    CPSATSchedulingEngine,
    MAX_CORE_EVENTS_PER_DAY,
    MAX_CORE_EVENTS_PER_WEEK,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_employee(models, db_session, emp_id, name=None):
    """Create a minimal active employee."""
    Employee = models['Employee']
    emp = Employee(
        id=emp_id,
        name=name or f'Test Employee {emp_id}',
        is_active=True,
        job_title='Event Specialist',
    )
    db_session.add(emp)
    db_session.flush()
    return emp


def _make_event(models, db_session, ref_num, event_type='Core', start_date=None, due_date=None):
    """Create a minimal unscheduled event."""
    Event = models['Event']
    start = start_date or (date.today() + timedelta(days=5))
    due = due_date or (start + timedelta(days=2))
    event = Event(
        project_name=f'Test Event ({ref_num})',
        project_ref_num=ref_num,
        start_datetime=datetime.combine(start, time(0, 0)),
        due_datetime=datetime.combine(due, time(23, 59)),
        event_type=event_type,
        is_scheduled=False,
        condition='Unstaffed',
    )
    db_session.add(event)
    db_session.flush()
    return event


def _make_schedule(models, db_session, ref_num, emp_id, sched_date):
    """Create a posted Schedule record (already committed assignment)."""
    Schedule = models['Schedule']
    schedule = Schedule(
        event_ref_num=ref_num,
        employee_id=emp_id,
        schedule_datetime=datetime.combine(sched_date, time(10, 15)),
    )
    db_session.add(schedule)
    db_session.flush()
    return schedule


def _make_run(models, db_session):
    """Create a SchedulerRunHistory record."""
    SchedulerRunHistory = models['SchedulerRunHistory']
    run = SchedulerRunHistory(
        run_type='manual',
        status='running',
    )
    db_session.add(run)
    db_session.flush()
    return run


def _make_pending(models, db_session, run, ref_num, emp_id, sched_date, failure_reason=None):
    """Create a PendingSchedule record."""
    PendingSchedule = models['PendingSchedule']
    ps = PendingSchedule(
        scheduler_run_id=run.id,
        event_ref_num=ref_num,
        employee_id=emp_id if not failure_reason else None,
        schedule_datetime=datetime.combine(sched_date, time(10, 15)) if not failure_reason else None,
        schedule_time=time(10, 15) if not failure_reason else None,
        status='proposed',
        failure_reason=failure_reason,
    )
    db_session.add(ps)
    db_session.flush()
    return ps


# ---------------------------------------------------------------------------
# Tests: _compute_existing_core_counts
# ---------------------------------------------------------------------------

class TestComputeExistingCoreCounts:
    """Verify the helper correctly counts existing posted Core events."""

    def test_counts_core_by_emp_day(self, app, db_session, models):
        """Existing Core schedules are counted per (employee, day)."""
        emp = _make_employee(models, db_session, 'EMP001')
        target_day = date.today() + timedelta(days=5)

        # Create a posted Core event+schedule
        ev = _make_event(models, db_session, 900001, 'Core', target_day, target_day + timedelta(days=1))
        _make_schedule(models, db_session, 900001, 'EMP001', target_day)

        # Also mark the event as scheduled so it won't be loaded as "to schedule"
        ev.is_scheduled = True
        db_session.flush()

        engine = CPSATSchedulingEngine(db_session, models)
        engine._load_data()

        assert engine.existing_core_count_by_emp_day[('EMP001', target_day)] == 1

    def test_ignores_non_core(self, app, db_session, models):
        """Non-Core posted schedules don't count toward Core limits."""
        emp = _make_employee(models, db_session, 'EMP002')
        target_day = date.today() + timedelta(days=5)

        ev = _make_event(models, db_session, 900002, 'Digital Setup', target_day, target_day + timedelta(days=1))
        _make_schedule(models, db_session, 900002, 'EMP002', target_day)
        ev.is_scheduled = True
        db_session.flush()

        engine = CPSATSchedulingEngine(db_session, models)
        engine._load_data()

        assert engine.existing_core_count_by_emp_day.get(('EMP002', target_day), 0) == 0


# ---------------------------------------------------------------------------
# Tests: H11 constraint fix
# ---------------------------------------------------------------------------

class TestH11ExistingCoreBlocksNew:
    """H11: Employee with posted Core on a day cannot get another new Core."""

    def test_existing_core_blocks_new_core(self, app, db_session, models):
        """An employee with a posted Core event on day X should NOT get a new
        Core event on day X from the solver."""
        target_day = date.today() + timedelta(days=5)

        # Two employees, but only emp1 has an existing posted Core
        emp1 = _make_employee(models, db_session, 'EMP010')
        emp2 = _make_employee(models, db_session, 'EMP011')

        # Existing posted Core for emp1
        existing_ev = _make_event(
            models, db_session, 800001, 'Core',
            target_day, target_day + timedelta(days=1),
        )
        _make_schedule(models, db_session, 800001, 'EMP010', target_day)
        existing_ev.is_scheduled = True
        db_session.flush()

        # New unscheduled Core event that could land on target_day
        new_ev = _make_event(
            models, db_session, 800002, 'Core',
            target_day, target_day + timedelta(days=1),
        )
        db_session.commit()

        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.run_auto_scheduler(run_type='manual', time_limit_seconds=10)

        PendingSchedule = models['PendingSchedule']
        pending = PendingSchedule.query.filter_by(
            scheduler_run_id=run.id,
            event_ref_num=800002,
        ).first()

        if pending and pending.employee_id == 'EMP010':
            # Should NOT be assigned to emp1 on the same day
            sched_date = pending.schedule_datetime.date()
            assert sched_date != target_day, (
                f"Double booking! EMP010 already has Core on {target_day} "
                f"but got assigned event 800002 on {sched_date}"
            )

    def test_no_existing_allows_assignment(self, app, db_session, models):
        """An employee with NO posted Core can still get one (no false positives)."""
        target_day = date.today() + timedelta(days=5)

        emp = _make_employee(models, db_session, 'EMP020')

        new_ev = _make_event(
            models, db_session, 800010, 'Core',
            target_day, target_day + timedelta(days=1),
        )
        db_session.commit()

        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.run_auto_scheduler(run_type='manual', time_limit_seconds=10)

        PendingSchedule = models['PendingSchedule']
        pending = PendingSchedule.query.filter_by(
            scheduler_run_id=run.id,
            event_ref_num=800010,
        ).first()

        # Should be scheduled (either to this employee or at least not failed
        # due to overly restrictive constraints)
        assert pending is not None
        if pending.employee_id is not None:
            assert pending.employee_id == 'EMP020'


# ---------------------------------------------------------------------------
# Tests: H12 constraint fix
# ---------------------------------------------------------------------------

class TestH12WeeklyLimitWithExisting:
    """H12: Weekly limit accounts for existing posted schedules."""

    def test_weekly_limit_with_existing(self, app, db_session, models):
        """Employee with existing posted Core events in a week should have
        the weekly limit reduced accordingly.

        CP-SAT uses Sunday-Saturday weeks, so we place all events within
        a single Sun-Sat span to test the weekly constraint correctly.
        """
        today = date.today()
        # SCHEDULING_WINDOW_DAYS=3, so earliest schedulable = today+3
        earliest = today + timedelta(days=3)

        # Find the first Sunday >= earliest (start of a solver week)
        days_until_sunday = (6 - earliest.weekday()) % 7
        base_sunday = earliest + timedelta(days=days_until_sunday)

        # All dates Sun-Sat are in the same solver week
        # Existing Core on Mon-Fri (5 events)
        emp = _make_employee(models, db_session, 'EMP030')

        for i in range(5):
            day = base_sunday + timedelta(days=1 + i)  # Mon through Fri
            ref = 700001 + i
            ev = _make_event(models, db_session, ref, 'Core', day, day + timedelta(days=1))
            _make_schedule(models, db_session, ref, 'EMP030', day)
            ev.is_scheduled = True

        # Create 2 new unscheduled Core events on Sunday and Saturday (same week)
        new_ev1 = _make_event(
            models, db_session, 700010, 'Core',
            base_sunday, base_sunday + timedelta(days=1),
        )
        sat = base_sunday + timedelta(days=6)
        new_ev2 = _make_event(
            models, db_session, 700011, 'Core',
            sat, sat + timedelta(days=1),
        )
        db_session.commit()

        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.run_auto_scheduler(run_type='manual', time_limit_seconds=10)

        # Check: at most MAX_CORE_EVENTS_PER_WEEK - 5 = 1 new Core assigned to EMP030
        PendingSchedule = models['PendingSchedule']
        new_assigned = PendingSchedule.query.filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.employee_id == 'EMP030',
            PendingSchedule.failure_reason.is_(None),
        ).all()

        allowed_new = MAX_CORE_EVENTS_PER_WEEK - 5  # Should be 1
        assert len(new_assigned) <= allowed_new, (
            f"EMP030 has 5 existing + {len(new_assigned)} new Core events in week "
            f"(max allowed new: {allowed_new})"
        )


# ---------------------------------------------------------------------------
# Tests: Post-solve review
# ---------------------------------------------------------------------------

class TestPostSolveReview:
    """The _post_solve_review() safety net catches violations."""

    def test_removes_duplicate_same_run(self, app, db_session, models):
        """Post-review catches 2 Core PendingSchedules for same emp+day."""
        target_day = date.today() + timedelta(days=5)
        emp = _make_employee(models, db_session, 'EMP040')

        # Create two Core events
        ev1 = _make_event(models, db_session, 600001, 'Core', target_day, target_day + timedelta(days=1))
        ev2 = _make_event(models, db_session, 600002, 'Core', target_day, target_day + timedelta(days=1))
        db_session.commit()

        engine = CPSATSchedulingEngine(db_session, models)
        engine._load_data()

        run = _make_run(models, db_session)

        # Simulate two Core pending schedules for same emp+day
        # (as if the solver somehow produced this)
        _make_pending(models, db_session, run, 600001, 'EMP040', target_day)
        _make_pending(models, db_session, run, 600002, 'EMP040', target_day)
        db_session.flush()

        removed = engine._post_solve_review(run)

        assert removed == 1, f"Expected 1 removal, got {removed}"

        PendingSchedule = models['PendingSchedule']
        still_assigned = PendingSchedule.query.filter_by(
            scheduler_run_id=run.id,
        ).filter(
            PendingSchedule.employee_id.isnot(None),
        ).all()

        assert len(still_assigned) == 1, f"Expected 1 still assigned, got {len(still_assigned)}"

    def test_removes_conflict_with_posted(self, app, db_session, models):
        """Post-review catches new Core conflicting with posted Core."""
        target_day = date.today() + timedelta(days=5)
        emp = _make_employee(models, db_session, 'EMP050')

        # Existing posted Core
        existing_ev = _make_event(
            models, db_session, 500001, 'Core',
            target_day, target_day + timedelta(days=1),
        )
        _make_schedule(models, db_session, 500001, 'EMP050', target_day)
        existing_ev.is_scheduled = True

        # New event
        new_ev = _make_event(
            models, db_session, 500002, 'Core',
            target_day, target_day + timedelta(days=1),
        )
        db_session.commit()

        engine = CPSATSchedulingEngine(db_session, models)
        engine._load_data()

        run = _make_run(models, db_session)

        # Simulate a pending schedule that conflicts
        _make_pending(models, db_session, run, 500002, 'EMP050', target_day)
        db_session.flush()

        removed = engine._post_solve_review(run)

        assert removed == 1, f"Expected 1 removal, got {removed}"

        PendingSchedule = models['PendingSchedule']
        conflict_ps = PendingSchedule.query.filter_by(
            scheduler_run_id=run.id,
            event_ref_num=500002,
        ).first()

        assert conflict_ps.employee_id is None
        assert 'Post-review' in conflict_ps.failure_reason


class TestFullRunNoDoubleBooking:
    """End-to-end: no employee should have >1 Core across posted + pending."""

    def test_full_run_no_double_booking(self, app, db_session, models):
        """Run the full scheduler and verify no double-bookings exist."""
        target_day = date.today() + timedelta(days=5)

        # Create several employees
        for i in range(3):
            _make_employee(models, db_session, f'EMP06{i}')

        # Existing posted Core for EMP060
        existing_ev = _make_event(
            models, db_session, 400001, 'Core',
            target_day, target_day + timedelta(days=1),
        )
        _make_schedule(models, db_session, 400001, 'EMP060', target_day)
        existing_ev.is_scheduled = True

        # Create 3 new unscheduled Core events for same day window
        for i in range(3):
            _make_event(
                models, db_session, 400010 + i, 'Core',
                target_day, target_day + timedelta(days=1),
            )
        db_session.commit()

        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.run_auto_scheduler(run_type='manual', time_limit_seconds=10)

        # Collect all Core assignments (posted + pending) per (emp, day)
        emp_day_core = defaultdict(int)

        # Count existing posted schedules
        Schedule = models['Schedule']
        Event = models['Event']
        for s in Schedule.query.all():
            ev = Event.query.filter_by(project_ref_num=s.event_ref_num).first()
            if ev and ev.event_type == 'Core':
                sd = s.schedule_datetime.date() if isinstance(s.schedule_datetime, datetime) else s.schedule_datetime
                emp_day_core[(s.employee_id, sd)] += 1

        # Count new pending schedules
        PendingSchedule = models['PendingSchedule']
        for ps in PendingSchedule.query.filter_by(scheduler_run_id=run.id).all():
            if ps.employee_id is None or ps.schedule_datetime is None:
                continue
            ev = Event.query.filter_by(project_ref_num=ps.event_ref_num).first()
            if ev and ev.event_type == 'Core':
                sd = ps.schedule_datetime.date()
                emp_day_core[(ps.employee_id, sd)] += 1

        # Verify: no (emp, day) pair has more than MAX_CORE_EVENTS_PER_DAY
        violations = {
            k: v for k, v in emp_day_core.items()
            if v > MAX_CORE_EVENTS_PER_DAY
        }
        assert not violations, (
            f"Double-booking detected! Violations: "
            + ", ".join(
                f"{emp} on {day}: {count} Core events"
                for (emp, day), count in violations.items()
            )
        )
