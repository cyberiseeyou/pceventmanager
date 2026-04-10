"""Tests for the per-run cache helpers used by the scheduler."""
from datetime import date, timedelta

from app.services.scheduler_helpers import RunCache


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
