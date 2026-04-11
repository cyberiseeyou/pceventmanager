"""Shared fixtures for scheduler spec conformance tests.

Every test in this directory uses the `greedy_scheduler` fixture to get
a fresh scheduler instance bound to an isolated test database. Tests
assert exact outputs (employee, date, time) against the spec branches
defined in docs/superpowers/specs/2026-04-10-scheduler-rewrite/.

Time determinism — all tests in this directory run with a frozen
"now" pinned to `FROZEN_NOW`. The scheduling engine and scheduler
helper modules have their `datetime.now()` and `date.today()` calls
intercepted so that test data built from `future_datetime(N)` is
always consistent with the scheduler's internal clock, eliminating
wall-clock drift at day/DST boundaries.
"""
from datetime import date, datetime, timedelta

import pytest


# Pinned "now" for every test in this directory. Chosen to be a well-known
# weekday (Wednesday, April 15 2026 at noon) so test data using Sun-Sat
# week math is easy to reason about.
FROZEN_NOW = datetime(2026, 4, 15, 12, 0, 0)


class _FrozenDatetime(datetime):
    """datetime subclass whose classmethods return a pinned "now" value.

    We subclass rather than mock the name so that existing
    `datetime(y, m, d)` constructor calls and `datetime.strptime(...)`
    etc. keep working — only `.now()` and `.today()` are intercepted.
    """

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fromtimestamp(FROZEN_NOW.timestamp())
        return cls.fromtimestamp(FROZEN_NOW.timestamp(), tz=tz)

    @classmethod
    def utcnow(cls):
        return cls.fromtimestamp(FROZEN_NOW.timestamp())

    @classmethod
    def today(cls):
        return cls.fromtimestamp(FROZEN_NOW.timestamp())


class _FrozenDate(date):
    """date subclass whose `today()` returns FROZEN_NOW.date()."""

    @classmethod
    def today(cls):
        return cls(FROZEN_NOW.year, FROZEN_NOW.month, FROZEN_NOW.day)


@pytest.fixture(autouse=True)
def freeze_scheduler_clock(monkeypatch):
    """Autouse fixture — freezes every scheduler time source at FROZEN_NOW.

    Intercepts `datetime` and `date` in the two modules that drive
    scheduler time semantics: `scheduling_engine` and `scheduler_helpers`.
    Tests that need a different "now" can override FROZEN_NOW per-test
    with their own monkeypatch.
    """
    import app.services.scheduling_engine as se_mod
    import app.services.scheduler_helpers as sh_mod
    monkeypatch.setattr(se_mod, 'datetime', _FrozenDatetime)
    monkeypatch.setattr(se_mod, 'date', _FrozenDate)
    monkeypatch.setattr(sh_mod, 'date', _FrozenDate)
    yield


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
    """Return a factory for dates N days past the frozen "now"."""
    def _factory(days: int) -> date:
        return (FROZEN_NOW + timedelta(days=days)).date()
    return _factory


@pytest.fixture
def future_datetime():
    """Return a factory for datetimes N days past the frozen "now",
    normalized to midnight.

    Since FROZEN_NOW is fixed, every test sees the same event timestamps
    regardless of wall-clock time.
    """
    def _factory(days: int) -> datetime:
        base = FROZEN_NOW + timedelta(days=days)
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
            assert ps.bumped_event_ref_num == bumped_event_ref_num, (
                f"Event {event_ref_num}: expected bumped_event_ref_num "
                f"{bumped_event_ref_num}, got {ps.bumped_event_ref_num}")

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
