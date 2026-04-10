# Plan 03 — Juicer Survey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Implement `_process_juicer_survey` to match spec `03-juicer-survey.md` branches JS1–JS17. Most surveys are already paired by plan 02 T12 (via Juicer Production); this plan handles the standalone surveys (Mon/Wed surveys with no matching Production). **CRITICAL:** this plan fixes the pre-existing silent-drop bug where standalone surveys were dropped from `self.events` without a PendingSchedule.

**Architecture:** `_process_juicer_survey(pool, run)` iterates the Juicer Survey pool. For each survey: if it was already paired by the Juicer Production category (detected via existing PendingSchedule with the same event_ref_num), skip. Otherwise, apply the standalone decision tree: Primary Juicer + has primary event → Backup Juicer + has primary event → CS unconditional.

**Tech Stack:** Flask 2.0+, pytest.

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/03-juicer-survey.md`.

**Depends on:** Plans 00, 01, 02.

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py
  (_process_juicer_production from plan 02 — look at the Survey pairing code)
- /home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py
  (lines 753-774 — the silent-drop bug site; confirm it's in CPSAT only, not in greedy)

Focus on:
1. Whether the greedy engine currently has ANY path for standalone surveys.
2. What "has primary event" means in the current greedy code — does it
   match spec branch K8 (Core + Juicer Production from both Schedule
   and PendingSchedule)?
3. The exact shape of the Club Supervisor fallback in other categories
   (we'll reuse the same pattern here).
```

## Task T1 — Detect paired surveys and skip them (branches JS1, JS2)

- [ ] **Step 1: Test**

```python
def test_js1_js2_paired_survey_skipped(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branches JS1 + JS2: survey matched in plan 02 is not re-scheduled here."""
    # Setup: a Juicer Production + matching Juicer Survey (same 6-digit prefix).
    # Run the scheduler end-to-end.
    # Expected:
    # - Production has 1 PendingSchedule @ 9 AM
    # - Survey has exactly 1 PendingSchedule @ 5 PM (created by plan 02)
    # - The Juicer Survey category in plan 03 does NOT create a second PendingSchedule for it
    PendingSchedule = models['PendingSchedule']
    # setup elided
    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    survey_count = db_session.query(PendingSchedule).filter_by(
        scheduler_run_id=run.id, event_ref_num=<survey_ref>).count()
    assert survey_count == 1, "Paired survey must have exactly one PendingSchedule"
```

- [ ] **Step 2: Run, observe** (currently 0 or 2 depending on plan 02's Survey pairing code). Fix if necessary.

- [ ] **Step 3: Implement**

```python
# app/services/scheduling_engine.py

def _process_juicer_survey(self, pool, run):
    """Spec 03. Handle only surveys that were NOT auto-paired by plan 02."""
    PendingSchedule = self.models['PendingSchedule']
    for survey in pool:
        existing = (self.db.query(PendingSchedule)
                    .filter_by(scheduler_run_id=run.id,
                               event_ref_num=survey.project_ref_num)
                    .first())
        if existing is not None:
            continue  # JS2: already handled by plan 02
        self._schedule_standalone_juicer_survey(survey, run)


def _schedule_standalone_juicer_survey(self, survey, run):
    """Stub — tasks T2-T7 implement the decision tree."""
    self._create_failed_pending_schedule(
        run, survey, "Standalone Juicer Survey handler stub (plan 03 T1)")
```

- [ ] **Step 4-5:** Run, commit, Gate D.

## Task T2 — Production scheduled but Survey not matching (branch JS3)

- [ ] **Step 1: Test**

```python
def test_js3_survey_of_failed_production_treated_standalone(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JS3: if matching Production failed (manual review),
    the survey still runs through the standalone tree."""
    # Setup: Production with both juicers on PTO for all retry days → manual review
    # AND a matching Survey (same 6-digit prefix, same start date).
    # Expected: the Survey IS still processed as a standalone (e.g., goes to CS fallback)
```

- [ ] **Step 2-5:** In `_process_juicer_survey`, the check is simpler than it looks: we check for an EXISTING PendingSchedule with this survey's ref_num. If the Production failed, its PendingSchedule is a manual-review entry — BUT it's for the Production's ref_num, NOT the Survey's ref_num. So the Survey's ref_num has no PendingSchedule → our code naturally falls through to standalone handling. No code change needed; this test just verifies the behavior. Commit + Gate D.

## Task T3 — No matching Production → standalone (branch JS4)

- [ ] **Step 1: Test**

```python
def test_js4_standalone_survey_no_matching_production(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JS4: a Juicer Survey with no matching Production → standalone."""
    # Setup: just a Juicer Survey (no Production at all).
    # Expected: the standalone decision tree runs and produces a valid PendingSchedule.
```

- [ ] **Step 2-5:** No code change — this is the default path. Commit + Gate D.

## Task T4 — Standalone: target_date + rotation lookup (branches JS5, JS6)

Reuses the `lookup_rotation(db, models, target_date, 'juicer')` helper from plan 02 T3.

- [ ] **Step 1: Test + implement + commit + Gate D.**

## Task T5 — Primary Juicer PTO check (branch JS7)

- [ ] **Step 1: Test + implement + commit + Gate D.**

```python
# inside _schedule_standalone_juicer_survey
from datetime import datetime, time
target_date = survey.start_datetime.date()
target_dt = datetime.combine(target_date, time(17, 0))  # 5 PM
primary_id, backup_id = lookup_rotation(self.db, self.models, target_date, 'juicer')
cs_employee_id = self._get_club_supervisor_employee_id()

if primary_id and self.cache.is_available(primary_id, target_date):
    if self.cache.has_primary_event(primary_id, target_date):
        self._create_pending_schedule(run, survey, primary_id, target_dt)
        return
# ... fall through to backup
```

## Task T6 — Primary available + has primary event → assign (branch JS8)

Already covered by T5's implementation. Add the specific test.

## Task T7 — Primary without primary event → fall through (branch JS9)

Also covered by T5. Test asserts the fall-through behavior:

```python
def test_js9_primary_without_primary_event_falls_through(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JS9: primary available but no primary event that day → try backup."""
    # Setup: Primary available on D, has NO CORE/Juicer Production on D. Backup has primary event.
    # Expected: backup gets the survey, not primary.
```

## Task T8 — Backup Juicer logic (branches JS10, JS11, JS12, JS13, JS14)

Same pattern as T5–T7 but applied to the backup.

## Task T9 — Club Supervisor unconditional fallback (branches JS15, K6)

> **Cross-cutting:** This task implements K6 (CS fallback is unconditional w.r.t. "requires primary event" but still respects approved PTO). The tests below cover both the unconditional assignment case and the PTO-blocks-CS case.

- [ ] **Step 1: Test**

```python
def test_js15_cs_unconditional_fallback(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec branch JS15: neither juicer qualifies → CS gets the survey
    UNCONDITIONALLY (no 'has primary event' check for CS)."""
    # Setup: both juicers on PTO, CS available (no PTO).
    # Expected: CS gets survey @ 5 PM even though CS has no primary event.
    # ALSO setup: verify CS has no primary event that day, but assignment still succeeds.
    Employee = models['Employee']
    cs = Employee(id='cs1', name='Grace', job_title='Club Supervisor')
    db_session.add(cs)
    # ... rest of setup
    # Expected:
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=<survey_ref>,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target_date, time(17, 0)))
```

- [ ] **Step 2-5:** Implement the CS unconditional branch. Helper:

```python
def _get_club_supervisor_employee_id(self) -> str | None:
    Employee = self.models['Employee']
    cs = (self.db.query(Employee)
          .filter(Employee.job_title == 'Club Supervisor',
                  Employee.is_active == True)
          .first())
    return cs.id if cs else None
```

In `_schedule_standalone_juicer_survey`, the final branch:

```python
cs_id = self._get_club_supervisor_employee_id()
if cs_id and self.cache.is_available(cs_id, target_date):
    self._create_pending_schedule(run, survey, cs_id, target_dt)
    return

# JS16/JS17: CS on PTO or missing → manual review
self._create_failed_pending_schedule(
    run, survey,
    f"Standalone Juicer Survey: no available juicer and Club Supervisor "
    f"unavailable on {target_date}")
```

Commit + Gate D.

## Task T10 — CS on PTO or missing → manual review (branches JS16, JS17)

Already covered by T9's final branch. Add explicit tests:

```python
def test_js16_cs_on_pto_manual_review(...):
    """All fallbacks exhausted including CS PTO → manual review."""
    # Setup: both juicers + CS all on PTO.
    # Expected: spec_assert.manual_review(run_id, survey_ref, reason_contains="unavailable")


def test_js17_no_cs_employee_manual_review(...):
    """No Club Supervisor in the club → manual review."""
    # Setup: no Employee with job_title='Club Supervisor', both juicers on PTO.
    # Expected: manual review.
```

## Task T11 — K4 invariant: secondary events do not bump (branch K4)

> **Cross-cutting:** Spec `01-key-concepts.md` branch K4 states "Bumping only moves primary events". This task adds an explicit negative test to verify the scheduler never bumps when processing a Juicer Survey (or any other secondary) regardless of conflicts.

- [ ] **Step 1: Test**

```python
def test_k4_juicer_survey_does_not_bump(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec K4: secondary events (including Juicer Survey) never bump.

    If a standalone Juicer Survey cannot find an employee via its decision
    tree, it falls to manual review — it does NOT bump a posted primary event.
    """
    Event = models['Event']
    Employee = models['Employee']
    Schedule = models['Schedule']
    PendingSchedule = models['PendingSchedule']

    # Setup: a Club Supervisor who has a posted CORE on target_date.
    # Both juicers on PTO. The standalone Survey should try CS unconditional,
    # CS is available, CS gets the Survey — but crucially the CORE is NOT
    # bumped. The CORE should still be posted after the run.
    cs = Employee(id='cs1', name='Grace', job_title='Club Supervisor')
    db_session.add(cs)
    target = future_datetime(5)

    # A CORE posted to CS
    posted_core = Event(project_ref_num=700001,
                        project_name='700001-CORE-Posted',
                        event_type='Core', condition='Scheduled',
                        is_scheduled=True,
                        start_datetime=target, due_datetime=target + timedelta(days=5))
    db_session.add(posted_core)
    db_session.flush()
    db_session.add(Schedule(event_ref_num=700001, employee_id='cs1',
                             schedule_datetime=target, shift_block=1))

    # A standalone Juicer Survey
    survey = Event(project_ref_num=700002,
                   project_name='700002-JUICER-SURVEY-Standalone',
                   event_type='Juicer Survey', condition='Unstaffed',
                   is_scheduled=False,
                   start_datetime=target, due_datetime=target + timedelta(days=2))
    db_session.add(survey)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # K4 assertion: the original CORE posted Schedule is STILL THERE (not bumped)
    remaining = (db_session.query(Schedule)
                 .filter_by(event_ref_num=700001).first())
    assert remaining is not None, (
        "Juicer Survey must not bump the posted CORE — K4 violation")

    # And the Survey was either scheduled to CS (CS unconditional) or
    # scheduled alongside; either way, no PendingSchedule is_swap=True for the CORE
    swap_entries = (db_session.query(PendingSchedule)
                    .filter_by(scheduler_run_id=run.id,
                               event_ref_num=700001, is_swap=True).count())
    assert swap_entries == 0, (
        "No bump PendingSchedule should exist for the CORE — K4 violation")
```

- [ ] **Step 2-5:** This test should PASS without any code change (the greedy engine has no bump logic in secondary categories). It's a guard test against future regressions. Commit + Gate D.

## Post-flight

- [ ] **Gate C:** cover JS1–JS17 + K4.
- [ ] **Gate E:** every branch has a deterministic test.
- [ ] Open PR: `plan 03: juicer survey + standalone fallback (fixes silent-drop bug)`.
- [ ] Manually verify the fix: create a standalone Juicer Survey in the test DB, run the greedy scheduler, confirm a PendingSchedule exists (previously would have been silently dropped in CP-SAT).
