"""Shared fixtures for scheduler spec conformance tests.

Every test in this directory uses the `greedy_scheduler` fixture to get
a fresh scheduler instance bound to an isolated test database. Tests
assert exact outputs (employee, date, time) against the spec branches
defined in docs/superpowers/specs/2026-04-10-scheduler-rewrite/.
"""
import pytest
from datetime import date, datetime, timedelta
from typing import Any


@pytest.fixture
def greedy_scheduler(db_session, models, app):
    """Return a fresh SchedulingEngine instance bound to the test DB.

    Forces the greedy path regardless of the CPSAT_ENABLED setting so
    that conformance tests always exercise the code under test.
    """
    from app.services.scheduling_engine import SchedulingEngine

    engine = SchedulingEngine(db_session, models)
    return engine


@pytest.fixture
def future_date():
    """Return a factory for dates N days in the future."""
    def _factory(days: int) -> date:
        return (datetime.now() + timedelta(days=days)).date()
    return _factory


@pytest.fixture
def future_datetime():
    """Return a factory for datetimes N days in the future (at midnight)."""
    def _factory(days: int) -> datetime:
        base = datetime.now() + timedelta(days=days)
        return base.replace(hour=0, minute=0, second=0, microsecond=0)
    return _factory


@pytest.fixture
def spec_assert(greedy_scheduler, models, db_session):
    """Factory that returns a helper for asserting a spec branch outcome.

    Usage in a test:
        def test_jp7_primary_assigned_no_bump(spec_assert, ...):
            run = run_the_scheduler(...)
            spec_assert.exact_assignment(
                run_id=run.id,
                event_ref_num=123,
                employee_id='jb1',
                scheduled_datetime=datetime(2026, 4, 11, 9, 0),
                failure_reason=None,
            )
    """
    class Helper:
        def exact_assignment(self, run_id, event_ref_num, employee_id,
                             scheduled_datetime, failure_reason=None,
                             is_swap=False, bumped_event_ref_num=None):
            PendingSchedule = models['PendingSchedule']
            ps = (db_session.query(PendingSchedule)
                  .filter_by(scheduler_run_id=run_id,
                             event_ref_num=event_ref_num)
                  .one())
            assert ps.employee_id == employee_id, (
                f"Event {event_ref_num}: expected employee {employee_id}, "
                f"got {ps.employee_id}")
            assert ps.schedule_datetime == scheduled_datetime, (
                f"Event {event_ref_num}: expected datetime "
                f"{scheduled_datetime}, got {ps.schedule_datetime}")
            assert ps.failure_reason == failure_reason, (
                f"Event {event_ref_num}: expected failure_reason "
                f"{failure_reason!r}, got {ps.failure_reason!r}")
            assert ps.is_swap == is_swap, (
                f"Event {event_ref_num}: expected is_swap={is_swap}, "
                f"got {ps.is_swap}")
            if bumped_event_ref_num is not None:
                assert ps.bumped_event_ref_num == bumped_event_ref_num

        def manual_review(self, run_id, event_ref_num, reason_contains=None):
            PendingSchedule = models['PendingSchedule']
            ps = (db_session.query(PendingSchedule)
                  .filter_by(scheduler_run_id=run_id,
                             event_ref_num=event_ref_num)
                  .one())
            assert ps.employee_id is None
            assert ps.schedule_datetime is None
            assert ps.failure_reason is not None
            if reason_contains:
                assert reason_contains in ps.failure_reason, (
                    f"Expected failure_reason to contain "
                    f"{reason_contains!r}, got {ps.failure_reason!r}")

        def count_in_run(self, run_id, event_ref_num):
            PendingSchedule = models['PendingSchedule']
            return (db_session.query(PendingSchedule)
                    .filter_by(scheduler_run_id=run_id,
                               event_ref_num=event_ref_num)
                    .count())

    return Helper()
