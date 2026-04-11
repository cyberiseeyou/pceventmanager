"""Regression harness for run 192.

Replays the captured run-192 inputs against the greedy scheduler and
asserts the spec-predicted outcomes for every event. This is the
canonical "did the rewrite fix the bug?" test.

The fixture was captured before plans 02–08 landed; the expected
outcomes were authored against the 7-image spec. Failures here mean
either:
  (a) the greedy engine's choice diverges from the spec, OR
  (b) the expected outcomes need to be reconciled with a correct-but-
      different tiebreaker the greedy engine took.

Investigate each failure carefully before updating expected.json.
"""
import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


FIXTURES = Path(__file__).parent / 'fixtures' / 'run_192'


def _load_fixture_loader_module():
    """Import `fixture_loader.py` from the same directory as this test.

    The `tests/` tree is not a package (no `__init__.py` at the top),
    so a normal `from tests.scheduler_spec_conformance.fixture_loader`
    import fails. Load by path to keep the file co-located with the
    test that uses it.
    """
    loader_path = Path(__file__).parent / 'fixture_loader.py'
    spec = importlib.util.spec_from_file_location(
        'fixture_loader', str(loader_path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


load_run_fixture = _load_fixture_loader_module().load_run_fixture

# Freeze "now" to Mar 25 2026 so every captured event's due_datetime is
# strictly after today + 3 (Mar 28) — the Phase 1 M3 buffer. The
# earliest event start_datetime is Mar 28 2026 and the latest due is
# May 16 2026, so Mar 25 keeps every event in scope.
REGRESSION_FROZEN_NOW = datetime(2026, 3, 25, 12, 0, 0)


class _RegressionFrozenDatetime(datetime):
    """datetime subclass returning REGRESSION_FROZEN_NOW from now()/today()."""

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fromtimestamp(REGRESSION_FROZEN_NOW.timestamp())
        return cls.fromtimestamp(REGRESSION_FROZEN_NOW.timestamp(), tz=tz)

    @classmethod
    def utcnow(cls):
        return cls.fromtimestamp(REGRESSION_FROZEN_NOW.timestamp())

    @classmethod
    def today(cls):
        return cls.fromtimestamp(REGRESSION_FROZEN_NOW.timestamp())


class _RegressionFrozenDate(date):
    @classmethod
    def today(cls):
        return cls(
            REGRESSION_FROZEN_NOW.year,
            REGRESSION_FROZEN_NOW.month,
            REGRESSION_FROZEN_NOW.day,
        )


def _override_clock(monkeypatch):
    """Override the autouse `freeze_scheduler_clock` fixture's pinned time
    for this one test so run-192 events sit inside the Phase 1 window."""
    import app.services.scheduling_engine as se_mod
    import app.services.scheduler_helpers as sh_mod
    monkeypatch.setattr(se_mod, 'datetime', _RegressionFrozenDatetime)
    monkeypatch.setattr(se_mod, 'date', _RegressionFrozenDate)
    monkeypatch.setattr(sh_mod, 'date', _RegressionFrozenDate)


def _load_expected():
    return json.loads((FIXTURES / 'expected.json').read_text())


def test_run_192_fixture_loader_reads_all_data(db_session, models, monkeypatch):
    """Smoke-test the fixture loader: every file in run_192/ loads cleanly."""
    _override_clock(monkeypatch)
    from fixture_loader import load_run_fixture
    counts = load_run_fixture(db_session, models, FIXTURES)
    assert counts['events'] == 17
    assert counts['employees'] > 0
    assert counts['rotations'] > 0


def test_run_192_regression_juicer_productions(
    greedy_scheduler, models, db_session, monkeypatch
):
    """Every Juicer Production in run 192 lands on its spec-predicted
    employee + date @ 09:00."""
    _override_clock(monkeypatch)

    load_run_fixture(db_session, models, FIXTURES)
    expected = _load_expected()['juicer_productions']

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    assert run.status == 'completed'

    PendingSchedule = models['PendingSchedule']
    failures: list[str] = []
    for exp in expected:
        ref = exp['project_ref_num']
        ps = (db_session.query(PendingSchedule)
              .filter_by(scheduler_run_id=run.id, event_ref_num=ref)
              .first())
        if ps is None:
            failures.append(f"{ref}: no PendingSchedule produced")
            continue

        want_emp = exp['expected_employee']
        want_dt = datetime.fromisoformat(
            f"{exp['expected_date']}T{exp['expected_time']}"
        )
        if ps.employee_id != want_emp:
            failures.append(
                f"{ref}: expected employee {want_emp}, got {ps.employee_id}. "
                f"Notes: {exp.get('notes', '')}"
            )
            continue
        if ps.schedule_datetime != want_dt:
            failures.append(
                f"{ref}: expected datetime {want_dt}, got {ps.schedule_datetime}"
            )

    if failures:
        msg = (
            f"Run 192 juicer production regression — "
            f"{len(failures)}/{len(expected)} mismatches:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )
        raise AssertionError(msg)


def test_run_192_regression_cores(
    greedy_scheduler, models, db_session, monkeypatch
):
    """Every Core in run 192 lands in its spec-predicted bucket:
    - `scheduled_success` → must have a non-null employee_id and
      a non-manual-review PendingSchedule.
    - `manual_review` → must have a manual-review PendingSchedule.
    """
    _override_clock(monkeypatch)

    load_run_fixture(db_session, models, FIXTURES)
    expected = _load_expected()['cores']

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    assert run.status == 'completed'

    PendingSchedule = models['PendingSchedule']
    failures: list[str] = []
    for exp in expected:
        ref = exp['project_ref_num']
        outcome = exp['expected_outcome']
        rows = (db_session.query(PendingSchedule)
                .filter_by(scheduler_run_id=run.id, event_ref_num=ref)
                .all())
        if not rows:
            failures.append(
                f"{ref}: no PendingSchedule produced (expected {outcome})"
            )
            continue
        # Invariant 1: exactly one row per event per run.
        if len(rows) > 1:
            failures.append(
                f"{ref}: got {len(rows)} PendingSchedule rows, expected 1"
            )
            continue
        ps = rows[0]

        if outcome == 'scheduled_success':
            if ps.employee_id is None or ps.schedule_datetime is None:
                failures.append(
                    f"{ref}: expected scheduled_success but got "
                    f"employee={ps.employee_id}, dt={ps.schedule_datetime}. "
                    f"failure_reason={ps.failure_reason!r}. "
                    f"Notes: {exp.get('notes', '')}"
                )
        elif outcome == 'manual_review':
            if ps.employee_id is not None or ps.failure_reason is None:
                failures.append(
                    f"{ref}: expected manual_review but got "
                    f"employee={ps.employee_id}, "
                    f"failure_reason={ps.failure_reason!r}"
                )
        else:
            failures.append(
                f"{ref}: unknown expected_outcome {outcome!r}"
            )

    if failures:
        msg = (
            f"Run 192 core regression — "
            f"{len(failures)}/{len(expected)} mismatches:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )
        raise AssertionError(msg)


def test_run_192_invariant_one_pending_per_event(
    greedy_scheduler, models, db_session, monkeypatch
):
    """Invariant 1 end-to-end: every event in the run-192 fixture has
    exactly one PendingSchedule row in the run."""
    _override_clock(monkeypatch)

    load_run_fixture(db_session, models, FIXTURES)

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    assert run.status == 'completed'

    Event = models['Event']
    PendingSchedule = models['PendingSchedule']
    all_events = db_session.query(Event).all()
    for event in all_events:
        count = (db_session.query(PendingSchedule)
                 .filter_by(scheduler_run_id=run.id,
                            event_ref_num=event.project_ref_num)
                 .count())
        assert count == 1, (
            f"Event {event.project_ref_num} ({event.event_type}) has "
            f"{count} PendingSchedule rows, expected 1"
        )
