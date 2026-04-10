# Plan 00 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Establish the infrastructure needed to refactor the scheduler: flip the production default to the greedy engine, create the `tests/scheduler_spec_conformance/` directory, build the shared test fixtures, and capture the run-192 regression baseline.

**Architecture:** Pure infrastructure. No spec-level behavior changes. Everything is reversible via the `CPSAT_ENABLED` env var.

**Tech Stack:** Flask 2.0+, pytest, SQLAlchemy (inherited).

**Source spec:** No spec file (infrastructure-only). References `docs/superpowers/specs/2026-04-10-scheduler-rewrite/README.md` for conventions.

**Depends on:** Nothing.

---

## Pre-flight (Gate B — Pre-Implementation Audit)

Before Task 1, dispatch Gate B with this input:

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/config.py (CPSAT_ENABLED flag)
- /home/elliot/flask-schedule-webapp/app/routes/auto_scheduler.py (scheduler dispatch)
- /home/elliot/flask-schedule-webapp/tests/conftest.py (root test fixtures)
- /home/elliot/flask-schedule-webapp/tests/test_cpsat_scheduler.py
- /home/elliot/flask-schedule-webapp/tests/test_cpsat_stress.py

Focus on:
1. Where CPSAT_ENABLED is read (there should be one central location).
2. Whether flipping the default to False breaks any existing test (most tests either mock the scheduler or set the flag explicitly).
3. Whether the existing stress tests in tests/test_cpsat_stress.py assume the CP-SAT path. These will become optional after plan 08 but must continue to pass on every commit until then.
4. Whether the scheduling_engine.py (greedy) currently has sufficient test coverage to detect regressions. Report the number of direct tests of scheduling_engine.py.
```

Expected audit output: 2–3 tests that will break from the flag flip (they'll need explicit `CPSAT_ENABLED=true` setup), a count of scheduling_engine.py tests (likely low — this is a finding, not a blocker).

## Task T0 — Create the conformance test directory skeleton

**Files:**
- Create: `tests/scheduler_spec_conformance/__init__.py`
- Create: `tests/scheduler_spec_conformance/conftest.py`
- Create: `tests/scheduler_spec_conformance/README.md`

- [ ] **Step 1: Create the empty package**

```bash
mkdir -p tests/scheduler_spec_conformance/fixtures
touch tests/scheduler_spec_conformance/__init__.py
```

- [ ] **Step 2: Create the conftest.py with shared fixtures**

```python
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
```

- [ ] **Step 3: Create the README.md**

```markdown
# Scheduler Spec Conformance Tests

Every test in this directory corresponds to a branch in the spec files at
`docs/superpowers/specs/2026-04-10-scheduler-rewrite/`. Test names follow
the convention `test_<branch_id>_<description>` so that a spec→test coverage
matrix can be built automatically.

## Running

```bash
# Full conformance suite
pytest tests/scheduler_spec_conformance/ -v

# Single category
pytest tests/scheduler_spec_conformance/test_02_juicer_production.py -v

# Single branch
pytest tests/scheduler_spec_conformance/test_02_juicer_production.py::test_jp7 -v
```

## Invariants

Every test MUST:
- Use `spec_assert.exact_assignment(...)` or `spec_assert.manual_review(...)` to
  verify outcomes. Do not use `assert ... in ...` or other fuzzy assertions.
- Use fixed dates from `future_date(N)` rather than `datetime.now()`.
- Reference the spec branch ID in its docstring (e.g., `"""Spec branch JP7: ..."""`).
```

- [ ] **Step 4: Verify test discovery**

Run:
```bash
pytest tests/scheduler_spec_conformance/ --collect-only 2>&1 | head -20
```
Expected output: `0 tests collected` (no tests yet, but pytest recognizes the directory).

- [ ] **Step 5: Commit**

```bash
git add tests/scheduler_spec_conformance/
git commit -m "test: add scheduler spec conformance test directory skeleton

Empty package plus shared fixtures (greedy_scheduler, future_date, spec_assert).
See docs/superpowers/specs/2026-04-10-scheduler-rewrite/README.md for the
conformance test conventions.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Gate D — Implementation Drift Review**

Dispatch Gate D with the prompt from `review-gates.md` substituting `<T-id>` = `T0`.

## Task T1 — Capture run-192 fixture data

**Files:**
- Create: `tests/scheduler_spec_conformance/fixtures/run_192_events.json`
- Create: `tests/scheduler_spec_conformance/fixtures/run_192_rotations.json`
- Create: `tests/scheduler_spec_conformance/fixtures/run_192_expected.json`
- Create: `scripts/capture_run_fixture.py`

This task captures the actual event/rotation snapshot from the production DB as it existed when run 192 failed, plus the human-authored "expected outcome" that the spec predicts.

- [ ] **Step 1: Write the capture script**

```python
# scripts/capture_run_fixture.py
"""Capture a scheduler-run fixture from the current DB state.

Usage:
    python scripts/capture_run_fixture.py --run-id 192 --out tests/scheduler_spec_conformance/fixtures/run_192
"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from app import create_app
from app.models import get_models


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def capture(run_id: int, out_dir: Path):
    app = create_app('development')
    with app.app_context():
        models = get_models()
        Event = models['Event']
        Schedule = models['Schedule']
        RotationAssignment = models['RotationAssignment']
        EmployeeTimeOff = models['EmployeeTimeOff']
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
        SchedulerRunHistory = models['SchedulerRunHistory']

        run = SchedulerRunHistory.query.get(run_id)
        if not run:
            raise SystemExit(f"No run {run_id}")

        # Events that were in the run's scope (unscheduled at run time).
        events = Event.query.filter(
            Event.is_scheduled == False,
            Event.due_datetime > run.started_at,
        ).all()
        events_data = [{
            'project_ref_num': e.project_ref_num,
            'project_name': e.project_name,
            'event_type': e.event_type,
            'condition': e.condition,
            'start_datetime': e.start_datetime,
            'due_datetime': e.due_datetime,
            'estimated_time': e.estimated_time,
        } for e in events]

        rotations = RotationAssignment.query.all()
        rot_data = [{
            'day_of_week': r.day_of_week,
            'rotation_type': r.rotation_type,
            'employee_id': r.employee_id,
            'backup_employee_id': r.backup_employee_id,
        } for r in rotations]

        # Approved time off overlapping the run's scheduling window.
        time_off = EmployeeTimeOff.query.filter_by(status='approved').all()
        to_data = [{
            'employee_id': t.employee_id,
            'start_date': t.start_date,
            'end_date': t.end_date,
        } for t in time_off]

        weekly = EmployeeWeeklyAvailability.query.all()
        wa_data = [{
            'employee_id': w.employee_id,
            'monday': w.monday, 'tuesday': w.tuesday,
            'wednesday': w.wednesday, 'thursday': w.thursday,
            'friday': w.friday, 'saturday': w.saturday, 'sunday': w.sunday,
        } for w in weekly]

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'events.json').write_text(
            json.dumps(events_data, default=_serialize, indent=2))
        (out_dir / 'rotations.json').write_text(
            json.dumps(rot_data, default=_serialize, indent=2))
        (out_dir / 'time_off.json').write_text(
            json.dumps(to_data, default=_serialize, indent=2))
        (out_dir / 'weekly_availability.json').write_text(
            json.dumps(wa_data, default=_serialize, indent=2))
        print(f"Wrote {len(events_data)} events, {len(rot_data)} rotations, "
              f"{len(to_data)} time-off, {len(wa_data)} weekly availability "
              f"to {out_dir}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--out', type=str, required=True)
    args = parser.parse_args()
    capture(args.run_id, Path(args.out))
```

- [ ] **Step 2: Run the capture against the current DB**

```bash
python scripts/capture_run_fixture.py --run-id 192 --out tests/scheduler_spec_conformance/fixtures/run_192
```

Expected: 4 JSON files created under `fixtures/run_192/`.

- [ ] **Step 3: Hand-author the expected outcome file**

This is manual work: for each of the 17 events in run 192's scope, the human reviewer decides what the spec says the outcome should be. Create `tests/scheduler_spec_conformance/fixtures/run_192/expected.json`:

```json
{
  "meta": {
    "run_id": 192,
    "description": "Expected outcomes per the 7-image spec (2026-04-10)",
    "spec_version": "2026-04-10-scheduler-rewrite"
  },
  "events": [
    {
      "project_ref_num": 624232,
      "expected_employee": "US935801",
      "expected_date": "2026-04-17",
      "expected_time": "09:00:00",
      "notes": "ESI Juicer Production Apr 17 Fri → CLAUDIA (primary juicer, bumps her Core)",
      "spec_branches": ["JP6", "JP17"]
    }
    // ... remaining 16 events
  ]
}
```

**NOTE for the executing agent:** The expected outcomes table was enumerated in the original plan `.claude/plans/glowing-fluttering-kazoo.md` §Pattern B. Use those specific event refs and dates as ground truth when authoring this file. If a judgment call is needed, escalate to the human.

- [ ] **Step 4: Commit**

```bash
git add scripts/capture_run_fixture.py tests/scheduler_spec_conformance/fixtures/
git commit -m "test: capture run 192 fixture data for regression harness

Events, rotations, time-off, and weekly availability as they existed at
run 192 (2026-04-10 08:32:37). Expected outcomes are hand-authored from
the spec to form the ground truth for the regression replay test.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Gate D review**

## Task T2 — Flip CPSAT_ENABLED default to False

**Files:**
- Modify: `app/config.py:63`
- Modify: tests that assume CPSAT_ENABLED=True (found during Gate B audit)

- [ ] **Step 1: Write a failing test**

```python
# tests/scheduler_spec_conformance/test_00_master_overview.py
"""Conformance tests for spec 00-master-overview.md."""
from unittest.mock import patch

import pytest


def test_m0_default_scheduler_is_greedy(app):
    """Spec: the production scheduler is the greedy engine, not CP-SAT.

    Verified indirectly via the CPSAT_ENABLED config default.
    """
    assert app.config['CPSAT_ENABLED'] is False, (
        "CPSAT_ENABLED must default to False. Greedy is the "
        "production scheduler per the 2026-04-10 rewrite.")
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
pytest tests/scheduler_spec_conformance/test_00_master_overview.py::test_m0_default_scheduler_is_greedy -v
```

Expected: FAIL, `assert True is False`.

- [ ] **Step 3: Flip the default**

Edit `app/config.py:63`:
```python
# Before:
CPSAT_ENABLED = config('CPSAT_ENABLED', default=True, cast=bool)

# After:
CPSAT_ENABLED = config('CPSAT_ENABLED', default=False, cast=bool)
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
pytest tests/scheduler_spec_conformance/test_00_master_overview.py::test_m0_default_scheduler_is_greedy -v
```

Expected: PASS.

- [ ] **Step 5: Run the full existing test suite; expect 1–3 failures**

```bash
pytest -v 2>&1 | tail -30
```

Expected: A small number of tests fail because they assumed CPSAT_ENABLED=True. These are identified in the Gate B audit output.

- [ ] **Step 6: Fix the broken tests by explicitly setting the flag**

For each broken test, add `app.config['CPSAT_ENABLED'] = True` to its setup (or use a fixture scoped to the test file). Do NOT remove the tests — they still validate CP-SAT behavior, they just need explicit opt-in now.

Example:
```python
# tests/test_cpsat_stress.py
import pytest

@pytest.fixture(autouse=True)
def _force_cpsat(app):
    """Existing stress tests all assume CP-SAT. Force-enable it."""
    old = app.config.get('CPSAT_ENABLED', False)
    app.config['CPSAT_ENABLED'] = True
    yield
    app.config['CPSAT_ENABLED'] = old
```

- [ ] **Step 7: Re-run the full suite; verify everything passes**

```bash
pytest -v 2>&1 | tail -10
```

Expected: all tests pass (including the pre-existing `test_export_with_date_params` unrelated failure, which is not in scope).

- [ ] **Step 8: Commit**

```bash
git add app/config.py tests/scheduler_spec_conformance/test_00_master_overview.py tests/test_cpsat_stress.py
git commit -m "feat(scheduler): flip CPSAT_ENABLED default to False

The greedy scheduling_engine.py is now the production scheduler. CP-SAT
remains reachable by setting CPSAT_ENABLED=true in the environment.

Existing CP-SAT tests (test_cpsat_stress.py, test_cpsat_scheduler.py)
now explicitly force CPSAT_ENABLED=True via a fixture.

Part of the scheduler rewrite — see docs/superpowers/plans/2026-04-10-scheduler-rewrite/.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 9: Gate D review**

## Task T3 — Add the "one PendingSchedule per event" invariant check as a shared helper

**Files:**
- Modify: `tests/scheduler_spec_conformance/conftest.py`
- Create test: `tests/scheduler_spec_conformance/test_00_invariants.py`

- [ ] **Step 1: Write the test**

```python
# tests/scheduler_spec_conformance/test_00_invariants.py
"""Scheduler invariants that must hold for every run, regardless of spec branch."""
from datetime import datetime, timedelta

import pytest


def test_every_event_produces_exactly_one_pending_schedule(
    greedy_scheduler, models, db_session, future_datetime
):
    """Invariant: no silent drops, no duplicates.

    Run the scheduler against 3 events of different types; assert each
    has exactly one PendingSchedule in the run.
    """
    Event = models['Event']
    Employee = models['Employee']
    PendingSchedule = models['PendingSchedule']

    # Create a minimal employee + rotation context
    emp = Employee(id='jb1', name='Frank', job_title='Juicer Barista',
                   juicer_trained=True)
    db_session.add(emp)
    db_session.flush()

    # Add 3 events: one Juicer, one CORE, one Freeosk.
    events = [
        Event(project_ref_num=900001, project_name='900001-JUICER-PRODUCTION-Test',
              event_type='Juicer Production', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(7),
              estimated_time=540),
        Event(project_ref_num=900002, project_name='900002-CORE-Test',
              event_type='Core', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(12),
              estimated_time=390),
        Event(project_ref_num=900003, project_name='900003-FSK-Daily Service-11AM',
              event_type='Freeosk', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(6),
              estimated_time=60),
    ]
    for e in events:
        db_session.add(e)
    db_session.commit()

    # Run the greedy scheduler
    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Invariant: every event has exactly one PendingSchedule
    for e in events:
        count = (db_session.query(PendingSchedule)
                 .filter_by(scheduler_run_id=run.id,
                            event_ref_num=e.project_ref_num)
                 .count())
        assert count == 1, (
            f"Event {e.project_ref_num} has {count} PendingSchedule rows "
            f"in run {run.id}, expected exactly 1")


def test_pending_schedule_null_employee_requires_failure_reason(
    greedy_scheduler, models, db_session, future_datetime
):
    """Invariant: PendingSchedule(employee_id=None) MUST have failure_reason."""
    Event = models['Event']
    PendingSchedule = models['PendingSchedule']

    # Create an unschedulable event: no employees at all
    e = Event(project_ref_num=900010, project_name='900010-CORE-Impossible',
              event_type='Core', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(7),
              estimated_time=390)
    db_session.add(e)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    ps = (db_session.query(PendingSchedule)
          .filter_by(scheduler_run_id=run.id, event_ref_num=900010)
          .one())
    assert ps.employee_id is None
    assert ps.failure_reason is not None, (
        "Invariant violated: PendingSchedule with employee_id=None must "
        "have a failure_reason set")
```

- [ ] **Step 2: Run the tests; they should currently FAIL or ERROR**

```bash
pytest tests/scheduler_spec_conformance/test_00_invariants.py -v
```

Expected: FAIL or ERROR. The current greedy scheduler may already satisfy these invariants, in which case the test PASSES. Either way, record the outcome.

- [ ] **Step 3: If failing, note the gaps**

If the tests fail, add the specific gaps to the plan for the affected category (01, 02, or 03). Do NOT fix the greedy engine in this task — that's the job of the per-category plans.

- [ ] **Step 4: Mark the failing tests xfail for now**

```python
import pytest
pytestmark = pytest.mark.xfail(reason="Fixed by plan 01-phase-infrastructure")
```

- [ ] **Step 5: Commit**

```bash
git add tests/scheduler_spec_conformance/test_00_invariants.py
git commit -m "test: add scheduler invariant tests (xfail until plan 01 completes)

These invariants hold for every scheduler run regardless of which spec
branch is exercised. Marked xfail because the current greedy engine may
not yet satisfy them; plan 01-phase-infrastructure makes them pass.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Gate D review**

## Post-flight

- [ ] Run **Gate C (Plan Coverage)** on this plan file.

  Expected result: 0 MISSING branches (this plan has no spec branches; it's infrastructure). STATUS should be PASS trivially.

- [ ] Run **Gate E (Test Adequacy)** for the tests added in T0–T3.

  Expected result: PASS. There are 3 tests; all are deterministic and assert exact outcomes.

- [ ] Open a PR for this plan with the title `plan 00: foundation + conformance test harness` and the body summarizing T0–T3.

- [ ] After PR merges, update the master plan README's "status" to mark plan 00 complete.
