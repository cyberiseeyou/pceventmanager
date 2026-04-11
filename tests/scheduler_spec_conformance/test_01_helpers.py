"""Tests for the per-run cache helpers used by the scheduler."""
from datetime import date, timedelta

from app.services.scheduler_helpers import RunCache, classify_event


def test_run_cache_records_primary_event(models, db_session, future_datetime):
    """RunCache.record_primary tracks a primary assignment for use in
    subsequent 'has_primary_event' queries within the same run.
    """
    cache = RunCache(db_session=db_session, models=models, run_id=1)

    d = future_datetime(5).date()
    cache.record_primary('emp1', d, 'Core', event_ref_num=500001)

    assert cache.has_primary_event('emp1', d) is True
    assert cache.has_primary_event('emp1', d + timedelta(days=1)) is False
    assert cache.has_primary_event('emp2', d) is False


def test_run_cache_primaries_this_week_sun_sat(models, db_session):
    """primaries_this_week uses Sunday-through-Saturday boundaries.

    Spec K9: the scheduling week is Sun-Sat; Python's weekday() is Mon=0..Sun=6,
    so conversion is (weekday() + 1) % 7.
    """
    cache = RunCache(db_session=db_session, models=models, run_id=1)

    # Pick a known Wednesday in 2026 that we can reason about precisely
    wed = date(2026, 4, 15)       # Wed Apr 15 2026
    sun = date(2026, 4, 12)       # Sun Apr 12 2026 (start of the Sun-Sat week)
    sat = date(2026, 4, 18)       # Sat Apr 18 2026 (end of the Sun-Sat week)
    next_sun = date(2026, 4, 19)  # next Sunday — different week

    cache.record_primary('emp1', sun, 'Core', 1)                 # counts (Sun)
    cache.record_primary('emp1', wed, 'Core', 2)                 # counts (Wed)
    cache.record_primary('emp1', sat, 'Juicer Production', 3)    # counts (Sat)
    cache.record_primary('emp1', next_sun, 'Core', 4)            # does NOT count (next week)

    assert cache.primaries_this_week('emp1', wed) == 3
    assert cache.primaries_this_week('emp1', next_sun) == 1


def test_run_cache_is_available_respects_pto(models, db_session):
    """is_available returns False for employees on approved PTO on that date."""
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']

    emp = Employee(id='emp1', name='Alice', job_title='Event Specialist')
    db_session.add(emp)
    db_session.flush()

    d = date(2026, 4, 15)
    pto = EmployeeTimeOff(employee_id='emp1', start_date=d, end_date=d,
                          status='approved')
    db_session.add(pto)
    db_session.commit()

    cache = RunCache(db_session=db_session, models=models, run_id=1)
    assert cache.is_available('emp1', d) is False
    assert cache.is_available('emp1', d + timedelta(days=1)) is True


# --- classify_event (K1–K3) --------------------------------------------------


def test_k1_primary_event_classifier():
    """Spec branch K1: Core and Juicer Production are primary events."""
    assert classify_event('Core') == 'primary'
    assert classify_event('Juicer Production') == 'primary'


def test_k2_secondary_event_classifier():
    """Spec branch K2: Juicer Survey, Supervisor, Freeosk, Digital Setup,
    and Digital Refresh are secondary events."""
    for t in [
        'Juicer Survey',
        'Supervisor',
        'Freeosk',
        'Digital Setup',
        'Digital Refresh',
    ]:
        assert classify_event(t) == 'secondary', (
            f"{t!r} should be classified as 'secondary'")


def test_k3_digital_teardown_is_own_bucket():
    """Spec branch K3: Digital Teardown is its own bucket — not primary,
    not secondary."""
    assert classify_event('Digital Teardown') == 'teardown_bucket'


def test_classify_event_other_type():
    """An unrecognized event type returns 'other'."""
    assert classify_event('Other') == 'other'
    assert classify_event('Unknown Type') == 'other'


# --- has_primary_event from posted Schedule (K8) -----------------------------


def test_k8_has_primary_event_counts_posted_schedule(
    db_session, models, future_datetime
):
    """Spec branch K8: a posted Schedule row (not in-run) counts as
    'has primary event' for the employee/day pair.

    This exercises the DB fall-through branch of RunCache.has_primary_event
    — the in-run cache is empty, so the helper must consult the Schedule
    table to find the posted CORE event on this day.
    """
    Employee = models['Employee']
    Event = models['Event']
    Schedule = models['Schedule']

    emp = Employee(id='emp_k8', name='Alice',
                   job_title='Lead Event Specialist')
    ev = Event(
        project_ref_num=400001,
        project_name='400001-CORE-Posted',
        event_type='Core', condition='Scheduled', is_scheduled=True,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=390,
    )
    db_session.add_all([emp, ev])
    db_session.flush()

    sched_dt = future_datetime(5)
    db_session.add(Schedule(
        event_ref_num=400001,
        employee_id='emp_k8',
        schedule_datetime=sched_dt,
    ))
    db_session.commit()

    cache = RunCache(db_session=db_session, models=models, run_id=1)

    # Posted CORE on sched_dt.date() is a primary event for emp_k8.
    assert cache.has_primary_event('emp_k8', sched_dt.date()) is True
    # No primary on the next day.
    assert cache.has_primary_event(
        'emp_k8', sched_dt.date() + timedelta(days=1)
    ) is False
    # Different employee, same day — no primary.
    assert cache.has_primary_event('other_emp', sched_dt.date()) is False
