# Plan 07 — Other Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Implement `_process_other` to match spec `07-other.md` branches O1–O6. Key feature: REVERSED priority — Club Supervisor is the FIRST choice (not fallback), Primary Lead is the fallback.

**Architecture:** Smallest plan in the set. `_process_other(pool, run)` iterates the pool in start-date order. For each event: try CS first, fall through to Primary Lead, fall through to manual review.

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/07-other.md`.

**Depends on:** Plans 00, 01, 04.

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py (old _schedule_wave5_other_events)

Focus on:
1. Does current code prioritize Club Supervisor first? Audit found: YES in greedy.
2. Does it check "has primary event" for CS or Primary Lead? Audit found:
   NO in greedy. This matches spec intent (O2 says no, O5 implicitly says no).
3. The time constant used for "Other" events in the old code.
```

## Task T1 — CS FIRST, Primary Lead fallback (branches O1, O2, O3, O4, O5)

- [ ] **Step 1: Tests for each branch**

```python
# tests/scheduler_spec_conformance/test_07_other.py

def test_o2_o3_cs_first_when_available(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O2+O3: CS available → CS gets Other @ 12 PM (first choice, not fallback)."""
    # Setup: CS available on target_date, CS has NO primary event that day.
    # Expected: Other event assigned to CS @ 12 PM.
    # This is the REVERSED behavior — CS is the first choice.
    from datetime import time
    Employee = models['Employee']
    cs = Employee(id='cs1', name='Grace', job_title='Club Supervisor')
    db_session.add(cs)
    Event = models['Event']
    target = future_datetime(5)
    db_session.add(Event(
        project_ref_num=700001, project_name='700001-Other-Generic',
        event_type='Other', condition='Unstaffed',
        start_datetime=target, due_datetime=target + timedelta(days=2),
        estimated_time=60))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=700001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target.date(), time(12, 0)))


def test_o4_o5_primary_lead_fallback_when_cs_pto(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O4+O5: CS on PTO → Primary Lead gets Other @ 12 PM.

    Note: spec does NOT require Primary Lead to have a primary event.
    This is unique to the Other category.
    """
    # Setup: CS on PTO, Primary Lead available with NO primary event that day.
    # Expected: Primary Lead still gets the Other event.


def test_o6_manual_review_when_both_unavailable(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O6: CS on PTO + Primary Lead on PTO → manual review."""
```

- [ ] **Step 2: Implement**

```python
# app/services/scheduling_engine.py

def _process_other(self, pool, run):
    """Spec 07. Catch-all. Club Supervisor FIRST, Primary Lead fallback."""
    from datetime import datetime, time
    OTHER_TIME = time(12, 0)

    cs_id = self._get_club_supervisor_employee_id()

    for event in pool:  # already sorted by start_datetime in plan 01 T3
        target_date = event.start_datetime.date()
        target_dt = datetime.combine(target_date, OTHER_TIME)

        # O2+O3: CS first (not fallback)
        if cs_id and self.cache.is_available(cs_id, target_date):
            self._create_pending_schedule(run, event, cs_id, target_dt)
            continue

        # O4+O5: Primary Lead fallback (no has_primary_event check — spec is
        # explicit about this omission for the Other category)
        primary_lead_id, _ = lookup_rotation(self.db, self.models, target_date, 'primary_lead')
        if primary_lead_id and self.cache.is_available(primary_lead_id, target_date):
            self._create_pending_schedule(run, event, primary_lead_id, target_dt)
            continue

        # O6: manual review
        self._create_failed_pending_schedule(
            run, event,
            f"Other event: Club Supervisor on PTO and Primary Lead unavailable on {target_date}")
```

- [ ] **Step 3: Run tests, verify pass. Commit.**

- [ ] **Step 4: Gate D review.**

## Task T2 — Add the reversed-priority invariant test (from spec K7)

- [ ] **Test**

```python
def test_k7_other_category_has_reversed_priority(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Cross-category invariant K7: for an Other event, CS is ALWAYS first
    even when Primary Lead has a primary event that day."""
    # Setup: CS available (no PTO), Primary Lead ALSO available AND has a CORE.
    # Expected: CS gets the Other event, NOT Primary Lead.
    # This confirms CS is the first choice, not a fallback.
```

- [ ] **Step 2-5:** Already covered by T1's implementation. This test exists purely to document and enforce the invariant. Commit + Gate D.

## Post-flight

- [ ] **Gate C:** cover O1–O6.
- [ ] **Gate E:** test per branch.
- [ ] Open PR: `plan 07: other events catch-all (CS-first reversed priority)`.
- [ ] Un-xfail any Other-category tests from plan 01 T3.
