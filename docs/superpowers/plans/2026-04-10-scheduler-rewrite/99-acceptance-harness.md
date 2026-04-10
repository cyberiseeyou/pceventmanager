# Plan 99 — Acceptance Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Build a regression test that replays the run-192 input data against the new greedy scheduler and asserts the spec-predicted outcome for every event. This is the canonical "did we fix the bug?" test and becomes part of CI forever.

**Architecture:** Load the captured fixtures from plan 00 T1, insert them into a clean test DB, run the scheduler, then compare every PendingSchedule row against `expected.json`.

**Source spec:** Not a single spec file; uses the canonical run-192 expected outcomes authored in plan 00 T1 Step 3.

**Depends on:** Plans 00–08.

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/tests/scheduler_spec_conformance/fixtures/run_192/
  (should exist after plan 00 T1; verify contents)
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py
  (should implement all 6 categories; verify)

Focus on:
1. Does the fixtures/run_192/ directory exist and contain events.json,
   rotations.json, time_off.json, weekly_availability.json, expected.json?
2. Is there a helper to load JSON fixtures into the test DB? If not, build one.
```

## Task T1 — Fixture loader helper

- [ ] **Step 1: Test for the loader**

```python
# tests/scheduler_spec_conformance/test_99_fixture_loader.py
from pathlib import Path


def test_load_run_fixture(db_session, models, tmp_path):
    """Given a fixtures directory, load all records into the test DB."""
    from tests.scheduler_spec_conformance.fixture_loader import load_run_fixture

    fixtures_dir = Path('tests/scheduler_spec_conformance/fixtures/run_192')
    load_run_fixture(db_session, models, fixtures_dir)

    Event = models['Event']
    events = Event.query.all()
    assert len(events) >= 17, f"Expected at least 17 events, got {len(events)}"
```

- [ ] **Step 2: Implement the loader**

```python
# tests/scheduler_spec_conformance/fixture_loader.py
"""Load a scheduler run fixture (captured by scripts/capture_run_fixture.py)
into the test DB.
"""
import json
from datetime import date, datetime
from pathlib import Path


def _parse(value):
    """Parse ISO 8601 strings back to datetime/date."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
    return value


def load_run_fixture(db_session, models, fixtures_dir: Path):
    """Load events, rotations, time_off, and weekly_availability from JSON
    files in `fixtures_dir` into the test DB."""
    Event = models['Event']
    RotationAssignment = models['RotationAssignment']
    EmployeeTimeOff = models['EmployeeTimeOff']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
    Employee = models['Employee']

    # Load events
    events_data = json.loads((fixtures_dir / 'events.json').read_text())
    for data in events_data:
        db_session.add(Event(
            project_ref_num=data['project_ref_num'],
            project_name=data['project_name'],
            event_type=data['event_type'],
            condition=data.get('condition', 'Unstaffed'),
            is_scheduled=False,
            start_datetime=_parse(data['start_datetime']),
            due_datetime=_parse(data['due_datetime']),
            estimated_time=data.get('estimated_time'),
        ))

    # Load employees referenced by rotations and time_off
    rotations_data = json.loads((fixtures_dir / 'rotations.json').read_text())
    time_off_data = json.loads((fixtures_dir / 'time_off.json').read_text())
    weekly_data = json.loads((fixtures_dir / 'weekly_availability.json').read_text())

    emp_ids = set()
    for r in rotations_data:
        emp_ids.add(r['employee_id'])
        if r.get('backup_employee_id'):
            emp_ids.add(r['backup_employee_id'])
    for t in time_off_data:
        emp_ids.add(t['employee_id'])
    for w in weekly_data:
        emp_ids.add(w['employee_id'])

    # Minimal employees — name and job_title derived from IDs or stubbed
    # In practice, the run_192 fixtures should include an employees.json too;
    # add it to the capture script if not present.
    employees_data_path = fixtures_dir / 'employees.json'
    if employees_data_path.exists():
        for data in json.loads(employees_data_path.read_text()):
            db_session.add(Employee(**data))
    else:
        # Stub employees with minimal info
        for eid in emp_ids:
            db_session.add(Employee(
                id=eid, name=eid, job_title='Event Specialist', is_active=True))

    db_session.flush()

    # Load rotations
    for r in rotations_data:
        db_session.add(RotationAssignment(**r))

    # Load time off
    for t in time_off_data:
        db_session.add(EmployeeTimeOff(
            employee_id=t['employee_id'],
            start_date=_parse(t['start_date']),
            end_date=_parse(t['end_date']),
            status='approved',
        ))

    # Load weekly availability
    for w in weekly_data:
        db_session.add(EmployeeWeeklyAvailability(**w))

    db_session.commit()
```

- [ ] **Step 3: Run tests, verify load works. Commit + Gate D.**

**Note for executor:** if `employees.json` is not in the fixture capture, add it to `scripts/capture_run_fixture.py` in plan 00 T1 and re-capture.

## Task T2 — Capture employees.json (if missing)

Update the capture script from plan 00 T1 to also dump employees.

- [ ] **Test** — after running the script, `employees.json` exists and contains all employee fields.

- [ ] **Implement** — extend `capture_run_fixture.py`:

```python
# Add to capture():
employees = Employee.query.all()
emp_data = [{
    'id': e.id, 'name': e.name, 'job_title': e.job_title,
    'is_active': e.is_active, 'juicer_trained': e.juicer_trained,
    'termination_date': e.termination_date,
} for e in employees]
(out_dir / 'employees.json').write_text(
    json.dumps(emp_data, default=_serialize, indent=2))
```

- [ ] **Commit + Gate D.**

## Task T3 — The regression test itself

- [ ] **Step 1: Test**

```python
# tests/scheduler_spec_conformance/test_99_run_192_regression.py
"""Run 192 regression harness.

Loads the run-192 fixtures, runs the greedy scheduler, compares every
PendingSchedule against the expected outcomes authored per the spec.

This is the canonical "did the rewrite fix the bug?" test. It MUST pass
in CI for every commit to main after plan 99 lands.
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from tests.scheduler_spec_conformance.fixture_loader import load_run_fixture


FIXTURES = Path('tests/scheduler_spec_conformance/fixtures/run_192')


def test_run_192_regression(greedy_scheduler, models, db_session):
    """Replay run 192 inputs; assert spec-predicted outcomes for every event."""
    load_run_fixture(db_session, models, FIXTURES)

    # Freeze "today" to the date of run 192 so the scheduler's "today+3 days"
    # window computation matches the original run.
    import app.services.scheduling_engine as eng
    original_date_today = eng.date.today if hasattr(eng, 'date') else None
    # (In practice, use freezegun or monkeypatch datetime.now.)
    # ... freezing code omitted; follow the project's existing date-freeze pattern ...

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    assert run.status == 'completed'

    # Load expected outcomes
    expected = json.loads((FIXTURES / 'expected.json').read_text())['events']

    # Compare each expected outcome to the actual PendingSchedule
    PendingSchedule = models['PendingSchedule']
    failures = []

    for exp in expected:
        ref = exp['project_ref_num']
        ps = db_session.query(PendingSchedule).filter_by(
            scheduler_run_id=run.id, event_ref_num=ref).first()

        if ps is None:
            failures.append(f"Event {ref}: no PendingSchedule in run {run.id}")
            continue

        expected_employee = exp.get('expected_employee')
        expected_date = exp.get('expected_date')
        expected_time = exp.get('expected_time')
        expected_manual_review = exp.get('expected_manual_review', False)

        if expected_manual_review:
            if ps.employee_id is not None:
                failures.append(
                    f"Event {ref}: expected manual review, got "
                    f"employee={ps.employee_id}")
            continue

        if ps.employee_id != expected_employee:
            failures.append(
                f"Event {ref}: expected employee {expected_employee}, "
                f"got {ps.employee_id}. Reason: {exp.get('notes', '(no notes)')}")
            continue

        actual_dt = ps.schedule_datetime
        expected_dt = datetime.fromisoformat(f"{expected_date}T{expected_time}")
        if actual_dt != expected_dt:
            failures.append(
                f"Event {ref}: expected {expected_dt}, got {actual_dt}")

    if failures:
        pytest.fail(
            f"Run 192 regression: {len(failures)}/{len(expected)} mismatches:\n"
            + "\n".join(f"  - {f}" for f in failures))
```

- [ ] **Step 2: Run → expected initial output:**

  - On first run, some events may mismatch because the hand-authored `expected.json` includes specific employees whose IDs differ from what the greedy engine picks under the fairness tiebreaker. This is normal. Investigate each mismatch: either (a) update `expected.json` if the greedy engine's choice is also spec-correct (e.g., two employees both have 0 primaries this week and the tiebreaker picked the first one alphabetically, but the human expected the other), or (b) fix the engine if the greedy choice is spec-wrong.

- [ ] **Step 3: Iterate until all 17 events are correctly predicted.**

- [ ] **Step 4: Commit + Gate D.**

## Task T4 — Add the regression test to CI

- [ ] **Edit `.github/workflows/ci.yml`** (when GitHub Actions billing is restored) to run `pytest tests/scheduler_spec_conformance/test_99_run_192_regression.py` as a required check.

- [ ] **Commit + Gate D.**

## Task T5 — Final smoke test

- [ ] **Step 1: Run the full conformance suite**

```bash
pytest tests/scheduler_spec_conformance/ -v 2>&1 | tail -30
```

Expected: every test PASSES. Count: ~60 tests across all categories plus the regression harness.

- [ ] **Step 2: Run the full existing project test suite**

```bash
pytest -v 2>&1 | tail -10
```

Expected: all tests pass except the pre-existing unrelated `test_export_with_date_params` failure (which is not in scope for this rewrite).

- [ ] **Step 3: Run the scheduler manually in dev mode against the real DB**

```bash
./backup_now.sh    # safety first
FLASK_ENV=development python wsgi.py &
# ... trigger auto-schedule via UI or via curl to /auto-schedule/run ...
```

Expected: successful run, events scheduled per spec, no exceptions.

- [ ] **Step 4: Compare the dev-run output against the run-192 expected schedule** to sanity-check the production behavior.

## Post-flight

- [ ] **Gate C:** trivially passes.
- [ ] **Gate E:** the regression test is self-contained; manually verify it covers every event type (primary, secondary, teardown, other).
- [ ] Open PR: `plan 99: run-192 regression harness and final cutover`.
- [ ] **Post-merge:** update `docs/superpowers/plans/2026-04-10-scheduler-rewrite/README.md` status to mark the rewrite complete. Announce in the changelog: `changelog/2026-MM-DD-scheduler-rewrite-complete.md`.
