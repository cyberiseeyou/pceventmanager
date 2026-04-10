# Plan 02 — Juicer Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Implement `_process_juicer_production` in `scheduling_engine.py` to match spec `02-juicer-production.md` branches JP1–JP19. Core ideas: sort by start date, look up Primary Juicer, bump CORE on primary's day when needed, fall back to Backup Juicer ONLY on PTO, cascade bumped CORE to category 3 pool, auto-pair the matching Juicer Survey @ 5 PM.

**Architecture:** Build a new category handler `_process_juicer_production(pool, run)` that replaces the stub from plan 01 T3. Uses `scheduler_helpers.RunCache` for availability and `scheduler_pairing` for Survey matching. Delegates bumping to a shared `_bump_core_to_pool(core_schedule)` helper.

**Tech Stack:** Flask 2.0+, pytest.

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/02-juicer-production.md`.

**Depends on:** Plans 00, 01.

---

## Pre-flight (Gate B — Pre-Impl Audit)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py (current Wave 1 code — _schedule_wave1_juicer_events, _schedule_single_juicer_event_wave1, _bump_core_events, _try_juicer_fallback, _get_core_events_for_employee_on_date)
- /home/elliot/flask-schedule-webapp/app/services/rotation_manager.py (get_rotation_employee)
- /home/elliot/flask-schedule-webapp/app/services/scheduler_helpers.py (RunCache from plan 01)
- /home/elliot/flask-schedule-webapp/app/services/scheduler_pairing.py (Phase 2 pairing from plan 01)

Focus on:
1. The full flow of _schedule_single_juicer_event_wave1 line-by-line.
   Which JP branches does it currently implement? Which does it skip?
2. _try_juicer_fallback — does it distinguish PTO from CORE conflicts?
   (Audit confirmed earlier it does not; verify no change.)
3. _bump_core_events — what does it mutate? Does it DELETE the old
   Schedule, or just disassociate? What PendingSchedule fields does it set?
4. The Juicer Survey pairing logic (_move_matching_supervisor_event or similar).
5. Rotation exception lookup — does it correctly consult ScheduleException
   before falling back to RotationAssignment?
```

## Task T1 — Sort juicer production pool by start date (branch JP1)

**Files:** Modify `app/services/scheduling_engine.py`.

- [ ] **Step 1: Test**

```python
# tests/scheduler_spec_conformance/test_02_juicer_production.py
"""Conformance tests for spec 02-juicer-production.md."""
from datetime import datetime, timedelta
import pytest


def test_jp1_juicer_production_sorted_by_start_date(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec branch JP1: events are sorted by start_datetime ascending."""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    emp = Employee(id='jb1', name='Frank', job_title='Juicer Barista',
                   juicer_trained=True)
    db_session.add(emp)
    for dow in range(7):
        db_session.add(RotationAssignment(
            day_of_week=dow, rotation_type='juicer', employee_id='jb1'))

    # Three Juicer Production events with distinct start dates; add in
    # reverse order to the DB to verify the sort happens in the scheduler.
    starts = [future_datetime(8), future_datetime(5), future_datetime(6)]
    for i, start in enumerate(starts):
        db_session.add(Event(
            project_ref_num=500100 + i,
            project_name=f'{500100 + i}-JUICER-PRODUCTION-Test',
            event_type='Juicer Production', condition='Unstaffed',
            start_datetime=start, due_datetime=start + timedelta(days=2),
            estimated_time=540))
    db_session.commit()

    # Spy on the order events hit the handler
    observed = []
    orig = greedy_scheduler._schedule_single_juicer_production
    def spy(event, run):
        observed.append(event.project_ref_num)
        return orig(event, run)
    greedy_scheduler._schedule_single_juicer_production = spy

    greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Expected order: event with start_days=5 (ref 500101), then 6 (500102),
    # then 8 (500100)
    assert observed == [500101, 500102, 500100]
```

- [ ] **Step 2: Run → ImportError or AttributeError (handler doesn't exist yet).**

- [ ] **Step 3: Implement the handler skeleton**

```python
# app/services/scheduling_engine.py (replace the stub from plan 01 T3)

def _process_juicer_production(self, pool, run):
    """Spec 02-juicer-production.md. Process events in start-date order."""
    for event in pool:  # pool is already sorted by start_datetime per plan 01 T3
        self._schedule_single_juicer_production(event, run)


def _schedule_single_juicer_production(self, event, run):
    """Implemented across tasks T2-T12. Stub for T1."""
    self._create_failed_pending_schedule(
        run, event, "Juicer Production handler stub (plan 02 T1)")
```

- [ ] **Step 4: Run test, verify it passes.** Commit + Gate D review.

## Task T2 — Target date from event start (branch JP2)

- [ ] **Step 1: Test**

```python
def test_jp2_juicer_production_uses_start_date_as_target(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec branch JP2: target_date = event.start_datetime.date()."""
    # ... setup elided; see T1 pattern ...
    start = future_datetime(5)  # specific day
    # Run the scheduler, then assert the PendingSchedule uses start.date()
```

- [ ] **Step 2-5:** Minimal implementation: set `target_date = event.start_datetime.date()` as the first line of `_schedule_single_juicer_production`. Commit + Gate D review.

## Task T3 — Rotation lookup with ScheduleException (branches JP3, JP4)

- [ ] **Step 1: Test**

```python
def test_jp3_jp4_rotation_lookup_with_exception(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec branches JP3 + JP4: look up RotationAssignment by DoW, override via ScheduleException."""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    ScheduleException = models['ScheduleException']

    for emp_id, name in [('jb1', 'Frank'), ('jb2', 'Leo')]:
        db_session.add(Employee(id=emp_id, name=name,
                                 job_title='Juicer Barista', juicer_trained=True))

    target = future_datetime(5)
    dow = target.weekday()
    db_session.add(RotationAssignment(day_of_week=dow, rotation_type='juicer',
                                       employee_id='jb1', backup_employee_id='jb2'))

    # Exception override for that exact date
    db_session.add(ScheduleException(
        exception_date=target.date(), rotation_type='juicer', employee_id='jb2',
        reason='One-off swap'))

    # Create a juicer production event
    Event = models['Event']
    db_session.add(Event(
        project_ref_num=501001, project_name='501001-JUICER-PRODUCTION',
        event_type='Juicer Production', condition='Unstaffed',
        start_datetime=target, due_datetime=target + timedelta(days=2),
        estimated_time=540))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    from app.services.scheduler_helpers import spec_assert  # or use the fixture
    # Assert: the exception override wins
    PendingSchedule = models['PendingSchedule']
    ps = db_session.query(PendingSchedule).filter_by(
        scheduler_run_id=run.id, event_ref_num=501001).one()
    assert ps.employee_id == 'jb2', \
        "ScheduleException must override RotationAssignment"
```

- [ ] **Step 2-5:** Implement `_lookup_juicer_rotation(target_date)` helper in `scheduler_helpers.py`:

```python
# app/services/scheduler_helpers.py (add)

def lookup_rotation(db, models, target_date, rotation_type: str) -> tuple[str | None, str | None]:
    """Return (primary_emp_id, backup_emp_id) for the given date + rotation_type.

    Checks ScheduleException first (which has no backup), then RotationAssignment.
    Returns (None, None) if neither is present.
    """
    ScheduleException = models['ScheduleException']
    RotationAssignment = models['RotationAssignment']
    exc = (db.query(ScheduleException)
           .filter_by(exception_date=target_date, rotation_type=rotation_type)
           .first())
    if exc:
        return (exc.employee_id, None)
    row = (db.query(RotationAssignment)
           .filter_by(day_of_week=target_date.weekday(), rotation_type=rotation_type)
           .first())
    if not row:
        return (None, None)
    return (row.employee_id, row.backup_employee_id)
```

Wire it into `_schedule_single_juicer_production`. Commit + Gate D review.

## Task T4 — Primary Juicer availability check (branch JP5)

- [ ] **Step 1: Test**

```python
def test_jp5_primary_juicer_pto_detected(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec branch JP5: primary juicer with approved PTO on target_date is 'unavailable'."""
    # Setup: jb1 is primary, jb2 is backup. jb1 has PTO on target_date.
    # Expectation: jb1 is "unavailable", flow falls to backup check (JP9).
    # Concrete assertion: the Production ends up with jb2, not jb1.
```

- [ ] **Step 2-5:** Use `RunCache.is_available(emp_id, target_date)`. Commit + Gate D.

## Task T5 — Primary Juicer available + no CORE (branch JP7)

- [ ] **Step 1: Test**

```python
def test_jp7_primary_juicer_assigned_no_bump(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JP7: primary available with no CORE conflict → assign @ 9 AM."""
    # Setup: jb1 primary juicer, available, no CORE on target_date.
    # Expected: PendingSchedule(event_ref=X, employee='jb1',
    #   schedule_datetime=target@9:00, is_swap=False)
    from datetime import time
    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=502001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(future_datetime(5).date(), time(9, 0)))
```

- [ ] **Step 2-5:** Implement the "assign @ 9 AM" branch. Reference: `scheduling_engine.py` already has a `_create_pending_schedule` helper; use it with `schedule_datetime = datetime.combine(target_date, time(9, 0))`. Commit + Gate D.

## Task T6 — Primary with CORE conflict → bump the CORE (branches JP6, JP17, JP18, JP19, K4, K5, M8)

> **Cross-cutting:** This task also implements cross-category invariants K4 (bumping only moves primary events — CORE), K5 (bumped CORE re-enters category 3 sorted by due date), and M8 (Phase 3 bumped-CORE flow from category 1 to category 3). Add assertions for K5's sort order to the test below.

**Files:** Modify `scheduling_engine.py`. Add `_bump_core_to_pool(core_schedule, run)` helper.

- [ ] **Step 1: Test**

```python
def test_jp6_primary_juicer_bumps_posted_core(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branches JP6 + JP17: primary has posted CORE → bump CORE, assign Prod."""
    # Setup:
    # - jb1 primary juicer, available on target_date
    # - A posted Schedule exists for jb1 on target_date with a CORE event
    # - Juicer Production starts on target_date
    # Expected:
    # - Juicer Production PendingSchedule: employee=jb1, time=9:00, is_swap=False
    # - CORE's old Schedule row is DELETED
    # - A second PendingSchedule exists for the CORE with is_swap=True,
    #   bumped_posted_schedule_id=<old_sched_id>, employee_id=NULL,
    #   schedule_datetime=NULL — it's "re-queued" awaiting re-scheduling by category 3
    #   (but category 3 hasn't run yet in this sub-test)


def test_jp19_primary_juicer_bumps_in_run_core(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JP19: primary has an in-run (PendingSchedule) CORE.

    This scenario exercises the case where a CORE was just proposed earlier
    in this same run (e.g., from a prior Juicer Production that moved CORE
    to a different day). The CORE is in PendingSchedule, not in Schedule.

    In practice, Juicer Production is category 1 and runs BEFORE Core category 3,
    so this branch is only hit when an earlier JP event already bumped and
    rescheduled a CORE that landed on this employee's day. Rare but tested.
    """
```

- [ ] **Step 2-5:** Implement the helper:

```python
# app/services/scheduling_engine.py (inside SchedulingEngine)

def _bump_core_to_pool(self, core_schedule_or_pending, run):
    """Bump an existing CORE and re-queue it into the core_supervisor pool.

    Accepts either:
    - A posted Schedule row: deletes the row, creates a swap-marker
      PendingSchedule with is_swap=True, bumped_posted_schedule_id=<old>.
      The bump-marker's employee_id and schedule_datetime are NULL (the
      CORE needs re-scheduling by category 3).
    - An in-run PendingSchedule row: clears the employee_id and
      schedule_datetime; re-queues the underlying Event for category 3.

    In both cases, the underlying Event is appended to
    self.category_pools['core_supervisor'] and the pool is re-sorted by
    due date ascending.
    """
    Schedule = self.models['Schedule']
    PendingSchedule = self.models['PendingSchedule']
    Event = self.models['Event']

    if isinstance(core_schedule_or_pending, Schedule):
        old = core_schedule_or_pending
        event = Event.query.filter_by(project_ref_num=old.event_ref_num).one()
        # Create swap-marker pending
        swap = PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=old.event_ref_num,
            employee_id=None,
            schedule_datetime=None,
            schedule_time=None,
            status='proposed',
            is_swap=True,
            bumped_posted_schedule_id=old.id,
            bumped_event_ref_num=old.event_ref_num,
            swap_reason='Bumped by Juicer Production scheduling',
        )
        self.db.add(swap)
        self.db.delete(old)
        # Update Event.is_scheduled to False since the CORE is no longer posted
        event.is_scheduled = False
        # Re-queue into core_supervisor pool
        self._enqueue_bumped_core(event)
    else:
        # PendingSchedule case
        old_ps = core_schedule_or_pending
        event = Event.query.filter_by(project_ref_num=old_ps.event_ref_num).one()
        old_ps.employee_id = None
        old_ps.schedule_datetime = None
        old_ps.schedule_time = None
        old_ps.is_swap = True
        old_ps.swap_reason = 'Bumped by Juicer Production scheduling'
        self._enqueue_bumped_core(event)


def _enqueue_bumped_core(self, event):
    """Append the event to core_supervisor pool and re-sort by due date."""
    if event not in self.category_pools['core_supervisor']:
        self.category_pools['core_supervisor'].append(event)
    self.category_pools['core_supervisor'].sort(key=lambda e: e.due_datetime)
```

Wire this into `_schedule_single_juicer_production` — after the primary juicer is chosen and found to be on a CORE, call `_bump_core_to_pool(core_schedule, run)`, then proceed to assign the Juicer Production to the same employee @ 9 AM.

- [ ] **Step 6: Run tests, commit, Gate D review.**

## Task T7 — Backup juicer fallback (branches JP8, JP9, JP10, JP11)

- [ ] **Step 1: Test (the critical "backup ONLY on PTO" assertion)**

```python
def test_jp7_jp8_backup_used_only_on_primary_pto(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branches JP8 + JP9: backup is used ONLY when primary has PTO,
    NOT when primary has a CORE conflict."""
    # Setup A: primary has CORE, no PTO. Expected: primary gets Production (bump CORE).
    # Setup B: primary has PTO. Expected: backup gets Production.
    # Run both scenarios; assert the employee_id in each case.
```

- [ ] **Step 2-5:** Implement the branch: after `is_available(primary, target_date)` returns False, look up backup; otherwise stay with primary. Commit + Gate D.

## Task T8 — Backup with CORE conflict → bump CORE (branch JP10)

Pattern repeats T6 but applied to the backup juicer. Same helper `_bump_core_to_pool`. Test + implement + commit + Gate D.

## Task T9 — Backup no CORE → assign directly (branch JP11)

Pattern repeats T5 but for backup. Test + implement + commit + Gate D.

## Task T10 — Both juicers unavailable → retry next day (branch JP12, JP13)

- [ ] **Step 1: Test**

```python
def test_jp12_jp13_both_unavailable_retry_next_day(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branches JP12 + JP13: if primary and backup both unavailable on D,
    retry on D+1 (if D+1 < due_datetime)."""
    # Setup: primary and backup both on PTO on D, both available on D+1.
    # Event start_datetime = D, due_datetime = D+3.
    # Expected: PendingSchedule uses D+1 @ 9 AM, employee=primary.
```

- [ ] **Step 2-5:** Wrap `_schedule_single_juicer_production`'s main logic in a `for attempt_date in daterange(start, due):` loop. On each iteration try the full primary/backup flow. Commit + Gate D.

## Task T11 — Past due date → manual review (branch JP14)

- [ ] **Step 1: Test**

```python
def test_jp14_past_due_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JP14: retry loop exhausted → manual review entry with clear reason."""
    # Setup: narrow window (D=D+1), both juicers on PTO.
    # Expected: spec_assert.manual_review(run_id, event_ref_num,
    #             reason_contains="both unavailable")
```

- [ ] **Step 2-5:** At the end of the retry loop, call `_create_failed_pending_schedule` with a specific reason. Commit + Gate D.

## Task T12 — Matching Juicer Survey auto-pairing (branches JP15, JP16)

- [ ] **Step 1: Test**

```python
def test_jp15_matching_survey_paired_at_5pm(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JP15: matching Juicer Survey assigned to same person @ 5 PM."""
    # Setup: a Juicer Production AND a Juicer Survey with same 6-digit prefix
    # and same start_datetime.
    # Expected: Production @ 9 AM; Survey @ 5 PM; both assigned to jb1.


def test_jp16_no_matching_survey_no_action(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec branch JP16: no matching Survey → no action on Survey side."""
    # Setup: a Juicer Production with no matching Juicer Survey.
    # Expected: the Production is scheduled normally; no extra PendingSchedule.
```

- [ ] **Step 2-5:** Implement `_find_matching_juicer_survey(production_event)` that extracts the 6-digit prefix via `scheduler_pairing.extract_pairing_key` and looks for a Juicer Survey with the same 6-digit prefix (not necessarily exact name_prefix — juicer productions and surveys have the same leading 6-digit ref by convention). After successfully scheduling a Production, find its matching Survey and create a second PendingSchedule @ 5 PM to the same employee. Commit + Gate D.

## Post-flight

- [ ] **Gate C (Plan Coverage):** cover JP1 through JP19.

- [ ] **Gate E (Test Adequacy):** every branch in spec 02's traceability table has a test.

- [ ] Open PR: `plan 02: juicer production greedy conformance`.

- [ ] Run `pytest tests/scheduler_spec_conformance/test_02_juicer_production.py -v` — expect all PASS.

- [ ] Run `pytest -v` full suite — any xfail'd test from plan 01 T3 that exercised Juicer Production should now PASS. Remove the xfail marker for those tests.
