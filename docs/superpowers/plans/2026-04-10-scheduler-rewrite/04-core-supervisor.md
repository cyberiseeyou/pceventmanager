# Plan 04 — CORE/Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. This is the largest plan in the set — ~19 tasks. Dispatch one subagent per task; do NOT try to batch.

**Goal:** Implement `_process_core_supervisor` to match spec `04-core-supervisor.md` branches C1–C16 (CORE scheduling) and S1–S8 (Supervisor scheduling). Handles bumped events from plan 02. Critical features: due-date sort, employee priority tiers, fill-2-per-slot time logic, CORE-to-CORE bumping, Supervisor with Lead-has-CORE verification.

**Architecture:** Two new methods in `scheduling_engine.py`:
- `_process_core_supervisor(pool, run)` — top-level loop over CORE events in due-date order, with mid-loop re-sort when bumps occur.
- `_schedule_single_core(event, run)` — the per-event logic (date window, employee selection, time slot, bump-if-needed).
- `_schedule_paired_supervisor(core_ps, run)` — called after each successful CORE to schedule its paired Supervisor @ 12 PM.

New module: `app/services/core_slot_allocator.py` — the "fill 2 per slot" time allocation logic. Isolated and unit-tested because it's the trickiest piece.

**Tech Stack:** Flask 2.0+, pytest.

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/04-core-supervisor.md`.

**Depends on:** Plans 00, 01, 02.

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py (the old Wave 2 code — _schedule_wave2_core_events, _find_least_busy_time_slot, CORE_TIME_SLOTS constant)
- /home/elliot/flask-schedule-webapp/app/services/rotation_manager.py
- /home/elliot/flask-schedule-webapp/app/services/constraint_validator.py (the daily-limit check for CORE)

Focus on:
1. The current time-slot allocation logic. How close is _find_least_busy_time_slot
   to "fill 2 per slot before advancing"? Flag any behavior that's stricter
   or looser than the spec.
2. The old CORE → Lead → Specialist subwave structure. Which parts are
   reusable, which parts need full rewrite?
3. The existing Supervisor assignment code (_schedule_supervisor_for_date).
   Does it currently enforce Primary/Backup Lead "has CORE" check? (Audit
   found earlier: NO. Confirm.)
4. Existing CORE-to-CORE bumping logic. If any exists, cite line numbers.
```

## Task T1 — Iterate core_supervisor pool sorted by due date (branch C1)

- [ ] **Test + implement + commit + Gate D.**

Test verifies that when the pool has 5 CORE events added in reverse due-date order, they are processed earliest-due-first. The plan 01 T3 dispatcher already sorts the pool before calling `_process_core_supervisor`, so this task mostly adds a test that the handler respects the input order.

## Task T2 — Date window computation (branches C2, C3)

- [ ] **Test + implement + commit + Gate D.**

```python
# app/services/scheduling_engine.py
from datetime import date, timedelta

def _compute_date_window(self, event, mode: str = 'normal') -> tuple[date, date]:
    """Return (window_start, window_end_exclusive) for a CORE event.

    Normal: max(event.start, today + 3 days)
    Emergency: max(event.start, today)
    End: event.due_datetime.date()
    """
    today = date.today()
    buffer_days = 0 if mode == 'emergency' else 3
    earliest = today + timedelta(days=buffer_days)
    start = max(event.start_datetime.date(), earliest)
    end = event.due_datetime.date()
    return (start, end)
```

## Task T3 — Candidate-day iteration (branch C4)

- [ ] **Test + implement + commit + Gate D.**

```python
def _schedule_single_core(self, event, run):
    window_start, window_end = self._compute_date_window(event, self.mode)
    candidate_day = window_start
    while candidate_day < window_end:
        if self._try_schedule_core_on_day(event, candidate_day, run):
            return  # success
        candidate_day += timedelta(days=1)
    # C15: exhausted window → manual review
    self._create_failed_pending_schedule(
        run, event,
        f"No employee available in window [{window_start}, {window_end}) and no bumpable CORE found")
```

## Task T4 — Primary Lead @ 10:15 AM hard assignment (branch C5)

- [ ] **Test** — verify Primary Lead gets slot 10:15 exactly when they have no CORE yet and are available that day. Include a test that the time is exactly 10:15, not "somewhere between 10:15 and 11:45".

- [ ] **Implement**:

```python
from datetime import time, datetime

CORE_TIME_SLOTS = [time(10, 15), time(10, 45), time(11, 15), time(11, 45)]

def _try_schedule_core_on_day(self, event, d: date, run) -> bool:
    primary_lead_id, backup_lead_id = lookup_rotation(self.db, self.models, d, 'primary_lead')

    # C5: Primary Lead, if no CORE yet and available → always 10:15 (block 1)
    if primary_lead_id and self.cache.is_available(primary_lead_id, d):
        if not self.cache.has_primary_event(primary_lead_id, d):
            return self._assign_core(event, primary_lead_id, d, time(10, 15), shift_block=1, run=run)

    # C6: Other leads (task T5)
    # C7: Fewest primaries this week (task T6)
    # C12-C13: Bump (task T10)
    # ...
    return False


def _assign_core(self, event, emp_id, d, t, shift_block, run) -> bool:
    dt = datetime.combine(d, t)
    ps = self._create_pending_schedule(run, event, emp_id, dt, shift_block=shift_block)
    self.cache.record_primary(emp_id, d, 'Core', event.project_ref_num)
    # C16: if this was a bumped event re-entering, update any previous
    # manual-review entries for the same ref_num to use this new assignment
    return True
```

- [ ] **Commit + Gate D.**

## Task T5 — Other Leads (branch C6)

- [ ] **Test** — primary lead unavailable or already has CORE → try other leads in order.

- [ ] **Implement** — list all `Employee.job_title == 'Lead Event Specialist'` except `primary_lead_id`, iterate with `is_available` + `has_primary_event` checks. Assign to the first one that qualifies. Time slot: use the "fill 2 per slot" allocator (task T7).

- [ ] **Commit + Gate D.**

## Task T6 — Fewest-primaries-this-week tiebreaker (branches C7, C8)

- [ ] **Test** — no lead available, 3 Event Specialists, one with 2 primaries this week, one with 1, one with 0 → CORE goes to the one with 0. Tie: lexicographic employee_id.

- [ ] **Implement**:

```python
def _fewest_primaries_candidate(self, d: date) -> str | None:
    """Return the employee_id with the fewest primary events this week."""
    Employee = self.models['Employee']
    all_emps = (self.db.query(Employee)
                .filter(Employee.is_active == True)
                .order_by(Employee.id.asc())  # deterministic tiebreak
                .all())
    best = None
    best_count = None
    for emp in all_emps:
        if not self.cache.is_available(emp.id, d):
            continue
        if self.cache.has_primary_event(emp.id, d):
            continue
        count = self.cache.primaries_this_week(emp.id, d)
        if best is None or count < best_count:
            best = emp.id
            best_count = count
    return best
```

- [ ] **Commit + Gate D.**

## Task T7 — "Fill 2 per slot before advancing" allocator (branches C9, C10, C11)

**Files:** Create `app/services/core_slot_allocator.py`.

- [ ] **Step 1: Write the unit tests for the allocator in isolation**

```python
# tests/scheduler_spec_conformance/test_04_core_slot_allocator.py
from datetime import time
import pytest
from app.services.core_slot_allocator import allocate_slot


def test_c9_fill_2_per_slot_before_advancing():
    """Spec C9: 2 per slot, fill in order 10:15, 10:15, 10:45, 10:45, 11:15, 11:15, 11:45, 11:45."""
    # Empty day: first event gets 10:15, block 1
    assert allocate_slot(existing={}, is_primary_lead=False) == (time(10, 15), 1)
    # One event at 10:15: next gets 10:15, block 2
    assert allocate_slot(existing={time(10, 15): 1}, is_primary_lead=False) == (time(10, 15), 2)
    # Two at 10:15: next gets 10:45, block 3
    assert allocate_slot(existing={time(10, 15): 2}, is_primary_lead=False) == (time(10, 45), 3)
    # Two at each slot = 8 events: next goes to 10:15, block 9 (+1 per slot rule)
    full = {time(10, 15): 2, time(10, 45): 2, time(11, 15): 2, time(11, 45): 2}
    assert allocate_slot(existing=full, is_primary_lead=False) == (time(10, 15), 9)


def test_c10_fill_gaps_first():
    """Spec C10: if slot 10:45 has only 1 event (gap), next goes there not to 11:15."""
    # Normally 10:15, 10:15, 10:45, 10:45, ... but with a gap at 10:45
    existing = {time(10, 15): 2, time(10, 45): 1, time(11, 15): 2}
    # Next should fill the 10:45 gap
    assert allocate_slot(existing=existing, is_primary_lead=False) == (time(10, 45), 4)


def test_c5_primary_lead_always_1015():
    """Spec C5: Primary Lead always gets 10:15, block 1 (if no CORE yet)."""
    assert allocate_slot(existing={}, is_primary_lead=True) == (time(10, 15), 1)


def test_c11_exclude_bumped_persons_old_slot():
    """Spec C11: when computing slot occupancy, exclude slots that were
    freed by a bump within the current scheduling pass."""
    # Caller's responsibility — pass `existing` that already excludes bumped slots.
    # This test documents the expected input shape.
    existing = {time(10, 15): 2, time(10, 45): 0}  # 10:45 was freed by a bump
    assert allocate_slot(existing=existing, is_primary_lead=False) == (time(10, 45), 3)
```

- [ ] **Step 2: Run → ImportError.**

- [ ] **Step 3: Implement the allocator**

```python
# app/services/core_slot_allocator.py
"""CORE event time-slot allocator.

Implements spec 04-core-supervisor.md branches C9, C10, C11:
- Fill 2 per slot before advancing (10:15, 10:15, 10:45, 10:45, 11:15, 11:15, 11:45, 11:45).
- After 8 events, +1 per slot in order (10:15 gets the 9th, 10:45 gets the 10th, ...).
- Always fill gaps first (if a slot has fewer events than earlier slots in the
  order, prefer filling that gap).
- Primary Lead always gets 10:15 / block 1.
"""
from datetime import time
from typing import Mapping

# The four time slots in order. Index = slot_order (0..3).
SLOT_ORDER = [time(10, 15), time(10, 45), time(11, 15), time(11, 45)]


def allocate_slot(
    existing: Mapping[time, int],
    is_primary_lead: bool = False,
) -> tuple[time, int]:
    """Return (slot_time, shift_block_number) for the next CORE event on a day.

    Args:
        existing: dict mapping slot_time → count of CORE events already scheduled
                  in that slot. Missing keys are treated as 0. Must have been
                  pre-cleaned by the caller to exclude slots freed by bumps.
        is_primary_lead: If True, force (10:15, 1). Used when the Primary Lead
                  is being assigned a CORE for the first time that day.

    Returns:
        (slot_time, shift_block): the slot to assign and the 1-indexed block number.

    Raises:
        ValueError: if is_primary_lead=True but slot 10:15 already has 2+ events
                    (the Primary Lead can't take slot 1). Caller should catch and
                    handle.
    """
    if is_primary_lead:
        count_at_1015 = existing.get(time(10, 15), 0)
        if count_at_1015 >= 1:
            # Primary Lead reuses slot 10:15 only if it's empty. Otherwise
            # they go somewhere else — but per spec C5 "Primary Lead always
            # gets 10:15", if 10:15 is taken, the Primary Lead is NOT the
            # one being assigned here (they already have a CORE that day
            # or the day's first CORE wasn't theirs). Raise to let caller decide.
            raise ValueError(
                "Primary Lead cannot take 10:15; slot already has "
                f"{count_at_1015} event(s)")
        return (time(10, 15), 1)

    # Fill-gaps-first rule (C10): find the slot with the lowest count. Ties
    # broken by SLOT_ORDER (earliest slot wins).
    counts = {s: existing.get(s, 0) for s in SLOT_ORDER}
    min_count = min(counts.values())

    # Within slots that have the lowest count, pick the earliest in SLOT_ORDER.
    chosen_slot = next(s for s in SLOT_ORDER if counts[s] == min_count)

    # Compute block number: C9's "2 per slot before advancing" means that
    # the shift_block index is `slot_order_index + 1 + (count_at_slot * 4)`
    # for the first pass (blocks 1-8), and for overflow (blocks 9+) it
    # continues the +1-per-slot pattern.
    slot_idx = SLOT_ORDER.index(chosen_slot)
    count_at_chosen = counts[chosen_slot]
    # Block numbering: 1=(10:15, pos 0), 2=(10:15, pos 1), 3=(10:45, pos 0),
    # 4=(10:45, pos 1), 5=(11:15, pos 0), 6=(11:15, pos 1), 7=(11:45, pos 0),
    # 8=(11:45, pos 1), 9=(10:15, pos 2), 10=(10:45, pos 2), ...
    # The formula for shift_block:
    #   pos = count_at_chosen (0-indexed position within the chosen slot)
    #   if pos < 2: shift_block = slot_idx * 2 + pos + 1
    #   else: shift_block = 8 + (pos - 2) * 4 + slot_idx + 1
    if count_at_chosen < 2:
        shift_block = slot_idx * 2 + count_at_chosen + 1
    else:
        shift_block = 8 + (count_at_chosen - 2) * 4 + slot_idx + 1

    return (chosen_slot, shift_block)
```

- [ ] **Step 4: Run unit tests, verify pass.**

```bash
pytest tests/scheduler_spec_conformance/test_04_core_slot_allocator.py -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Commit + Gate D.**

## Task T8 — Integrate the allocator into _try_schedule_core_on_day (C10 integration)

- [ ] **Test + implement + commit + Gate D.**

```python
# inside _try_schedule_core_on_day
existing_on_day = self._get_slot_counts(d)

# If Primary Lead branch
if primary_lead_id and self.cache.is_available(primary_lead_id, d) and not self.cache.has_primary_event(primary_lead_id, d):
    try:
        slot_time, block = allocate_slot(existing_on_day, is_primary_lead=True)
        return self._assign_core(event, primary_lead_id, d, slot_time, block, run)
    except ValueError:
        pass  # Slot 10:15 taken; Primary Lead can't take first CORE

# If Other Lead branch
for lead_id in self._other_lead_ids(primary_lead_id):
    if self.cache.is_available(lead_id, d) and not self.cache.has_primary_event(lead_id, d):
        slot_time, block = allocate_slot(existing_on_day, is_primary_lead=False)
        return self._assign_core(event, lead_id, d, slot_time, block, run)

# If Fewest-primaries branch
emp_id = self._fewest_primaries_candidate(d)
if emp_id:
    slot_time, block = allocate_slot(existing_on_day, is_primary_lead=False)
    return self._assign_core(event, emp_id, d, slot_time, block, run)

return False  # No employee on this day — fall through to bump logic
```

```python
def _get_slot_counts(self, d: date) -> dict[time, int]:
    """Return {slot_time: count} of CORE events already scheduled on day d.
    Counts both posted Schedule AND in-run PendingSchedule."""
    from datetime import time as T
    counts = {T(10, 15): 0, T(10, 45): 0, T(11, 15): 0, T(11, 45): 0}
    # ... query code omitted; see spec 99-data-model.md for the pattern
    return counts
```

## Task T9 — Bumped person's old slot exclusion (branch C11)

- [ ] **Test + implement + commit + Gate D.**

Track a per-run set of `(date, shift_block)` tuples that have been freed by bumps in this run. When computing `_get_slot_counts`, subtract these from the counts.

## Task T10 — CORE-to-CORE bumping with latest due date (branches C12, C13)

- [ ] **Test** — 8 CORE events already on day D, all earlier due dates than the current event → no bump, advance. Swap: 8 CORE on D with one having LATER due date → bump that one.

- [ ] **Implement**:

```python
def _try_bump_core_on_day(self, event, d: date, run) -> bool:
    """Find a CORE on day d whose due date is LATER than event's, with the
    latest due date. Bump it, take its slot."""
    # Query all CORE on day d (from Schedule and in-run PendingSchedule)
    candidates = self._cores_on_day(d)
    # Filter: due_datetime > event.due_datetime
    bumpable = [c for c in candidates if c.due_datetime > event.due_datetime]
    if not bumpable:
        return False
    # Sort descending by due_datetime, tiebreak by event_ref_num DESC
    bumpable.sort(key=lambda c: (c.due_datetime, c.project_ref_num), reverse=True)
    target = bumpable[0]
    # Bump via _bump_core_to_pool (from plan 02 T6)
    target_schedule = self._get_schedule_for(target, d)
    self._bump_core_to_pool(target_schedule, run)
    # Now take the freed slot
    freed_slot, freed_block = self._get_slot_of(target, d)
    assigned_emp = target_schedule.employee_id
    return self._assign_core(event, assigned_emp, d, freed_slot, freed_block, run)
```

- [ ] **Commit + Gate D.**

## Task T11 — No bump + day advances + manual review (branches C14, C15)

- [ ] **Test + implement + commit + Gate D.**

Already covered by the retry loop in T3. Add specific tests for the "manual review" exit.

## Task T12 — Bumped CORE re-enters pool and is reprocessed (branches C16, K5)

> **Cross-cutting:** Also implements K5 (bumped CORE re-enters category 3 sorted by due date). Verify via a test that bumps a CORE mid-loop and confirms it is processed after other still-pending CORE events with earlier due dates.

- [ ] **Test** — CORE A bumps CORE B (later due date); CORE B re-enters pool; CORE B is processed later in the same `_process_core_supervisor` iteration.

- [ ] **Implement** — the iteration loop in `_process_core_supervisor` must be restart-safe when the pool is mutated mid-loop. Strategy:

```python
def _process_core_supervisor(self, pool, run):
    """Process CORE events in due-date order. Pool may be mutated by bumps."""
    processed_ids = set()
    while True:
        # Find the next unprocessed event, sorted by due date
        remaining = [e for e in pool if e.id not in processed_ids]
        if not remaining:
            break
        remaining.sort(key=lambda e: (e.due_datetime, e.project_ref_num))
        event = remaining[0]
        processed_ids.add(event.id)
        self._schedule_single_core(event, run)
        # If _schedule_single_core bumped something, it's already in the pool
        # via _bump_core_to_pool → _enqueue_bumped_core. The while loop picks
        # it up on the next iteration.

        # Schedule the paired Supervisor (if any) now, after the CORE succeeded
        if self._last_core_pending and not self._last_core_pending.failure_reason:
            sup_event = self.pairs.get(event.id)
            if sup_event:
                self._schedule_paired_supervisor(sup_event, self._last_core_pending, run)
```

- [ ] **Commit + Gate D.**

## Tasks T13–T19 — Supervisor scheduling (branches S1–S8)

### Task T13 — Paired Supervisor lookup (branches S1, S2)

- [ ] **Test + implement + commit + Gate D.**

```python
def _schedule_paired_supervisor(self, sup_event, core_pending, run):
    """Schedule the Supervisor paired with a freshly-scheduled CORE."""
    if sup_event is None:
        return  # S2: no paired supervisor, skip
    target_date = core_pending.schedule_datetime.date()
    self._assign_supervisor(sup_event, target_date, run)
```

### Task T14 — Supervisor @ 12 PM time constant (branch S3)

- [ ] **Test + implement** — hard-code 12:00 PM in `_assign_supervisor`. **Commit + Gate D.**

### Task T15 — Club Supervisor first, no primary required (branch S4)

- [ ] **Test** — CS available, CS has NO primary event → still gets the Supervisor. Do NOT call `has_primary_event` for this branch.

- [ ] **Implement**:

```python
def _assign_supervisor(self, sup_event, target_date, run):
    from datetime import datetime, time
    target_dt = datetime.combine(target_date, time(12, 0))

    cs_id = self._get_club_supervisor_employee_id()
    if cs_id and self.cache.is_available(cs_id, target_date):
        # S4: CS first, no primary event required
        self._create_pending_schedule(run, sup_event, cs_id, target_dt)
        return

    # S5: Primary Lead + has CORE
    primary_lead, backup_lead = lookup_rotation(self.db, self.models, target_date, 'primary_lead')
    if (primary_lead and self.cache.is_available(primary_lead, target_date)
            and self.cache.has_primary_event(primary_lead, target_date)):
        self._create_pending_schedule(run, sup_event, primary_lead, target_dt)
        return

    # S6: Backup Lead + has CORE
    if (backup_lead and self.cache.is_available(backup_lead, target_date)
            and self.cache.has_primary_event(backup_lead, target_date)):
        self._create_pending_schedule(run, sup_event, backup_lead, target_dt)
        return

    # S7: Neither qualifies → CS unconditional (but still PTO-check)
    if cs_id and self.cache.is_available(cs_id, target_date):
        self._create_pending_schedule(run, sup_event, cs_id, target_dt)
        return

    # S8: CS on PTO or missing → manual review
    self._create_failed_pending_schedule(
        run, sup_event,
        f"Supervisor: Club Supervisor unavailable on {target_date} "
        f"and no Lead with a CORE on that day")
```

- [ ] **Commit + Gate D.**

### Tasks T16, T17, T18, T19

One test each for branches S5, S6, S7, S8. The implementation is already in T15; these tasks are TEST-ONLY tasks that verify each branch is hit under the right conditions.

- [ ] **T16:** `test_s5_primary_lead_with_core_assigned` — CS on PTO, Primary Lead has CORE → Primary Lead gets Supervisor.
- [ ] **T17:** `test_s6_backup_lead_with_core_assigned` — CS on PTO, Primary Lead has no CORE, Backup Lead has CORE → Backup Lead gets Supervisor.
- [ ] **T18:** `test_s7_cs_unconditional_fallback` — CS on PTO for target_date BUT available (e.g., approved leave revoked), both leads have no CORE → CS gets Supervisor unconditionally. Also test: CS missing entirely → fall through to S8.
- [ ] **T19:** `test_s8_manual_review` — all paths exhausted (CS on PTO, leads no CORE) → manual review.

## Post-flight

- [ ] **Gate C:** cover C1–C16 + S1–S8.
- [ ] **Gate E:** every branch deterministic test.
- [ ] Open PR: `plan 04: core/supervisor greedy conformance`.
- [ ] Re-run `pytest tests/scheduler_spec_conformance/ -v` — all of test_00, 01, 02, 03, 04 pass.
- [ ] Un-xfail any `tests/test_scheduler.py` tests that exercise CORE.
