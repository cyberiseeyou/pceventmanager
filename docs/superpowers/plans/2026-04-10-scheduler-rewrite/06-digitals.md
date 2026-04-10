# Plan 06 — Digitals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Implement `_process_digitals` to match spec `06-digitals.md` branches D1–D15. Key features: 3 subcategories identified by name-ends-with, Setup restricted to Saturdays, per-event +15 min offsets, Teardown uses unique "Lead ≠ Primary Lead scheduled that day" logic.

**Architecture:** `_process_digitals(pool, run)` partitions into Setup/Refresh/Teardown subcategories, then processes each in order. Uses `digital_subcategory()` helper from `scheduler_helpers.py` (added here).

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/06-digitals.md`.

**Depends on:** Plans 00, 01, 04.

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py (old _schedule_digital_*)

Focus on:
1. Does current code use "Digital Demo Setup" name matching or
   event_type='Digital Setup' column matching? Audit found: event_type.
   We will switch to name-ends-with per spec.
2. Saturday restriction for Setup: audit found NONE. Confirm.
3. +15 min offsets: audit found `_get_next_digital_time_slot` rotates slots.
   We reuse the concept but reimplement around spec-defined base times.
4. Teardown "find Lead ≠ Primary Lead scheduled that day" logic: audit
   found a "Secondary Lead" concept. Confirm it matches the spec's intent.
```

## Task T1 — Subcategory classifier (branches D1, D6, D10)

- [ ] **Test**

```python
from app.services.scheduler_helpers import digital_subcategory

def test_d1_setup_ends_with():
    assert digital_subcategory('191001-Brand-Digital Demo Setup') == 'setup'

def test_d6_refresh_ends_with():
    assert digital_subcategory('191002-Digital Demo Refresh') == 'refresh'

def test_d10_teardown_ends_with():
    assert digital_subcategory('191003-Brand Digital Demo Tear Down') == 'teardown'

def test_unknown_returns_none():
    assert digital_subcategory('191004-Generic Digitals Event') is None
```

- [ ] **Implement in `scheduler_helpers.py`:**

```python
def digital_subcategory(project_name: str) -> str | None:
    """Return 'setup', 'refresh', 'teardown', or None.

    Matches by name-ends-with per spec 06-digitals.md.
    """
    if not project_name:
        return None
    name = project_name.strip()
    if name.endswith('Digital Demo Setup'):
        return 'setup'
    if name.endswith('Digital Demo Refresh'):
        return 'refresh'
    if name.endswith('Digital Demo Tear Down'):
        return 'teardown'
    return None
```

- [ ] **Commit + Gate D.**

## Task T2 — Saturday-only restriction for Setup (branches D2, D3)

- [ ] **Test**

```python
def test_d3_setup_non_saturday_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec D3: Setup event with non-Saturday start_date → manual review."""
    # Pick a date that is definitely not a Saturday
    from datetime import timedelta, date
    base = date.today() + timedelta(days=5)
    while base.weekday() == 5:  # 5 = Saturday
        base += timedelta(days=1)

    # Create a Setup event
    Event = models['Event']
    db_session.add(Event(
        project_ref_num=600001,
        project_name='600001-Brand-Digital Demo Setup',
        event_type='Digitals', condition='Unstaffed',
        start_datetime=datetime.combine(base, time(0, 0)),
        due_datetime=datetime.combine(base + timedelta(days=2), time(0, 0)),
        estimated_time=60))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(run.id, 600001, reason_contains="must be on Saturdays")
```

- [ ] **Implement**

```python
def _process_digitals(self, pool, run):
    """Spec 06. Partition, Saturday check for Setup, per-subcategory processing."""
    from app.services.scheduler_helpers import digital_subcategory

    buckets = {'setup': [], 'refresh': [], 'teardown': []}
    for event in pool:
        sub = digital_subcategory(event.project_name)
        if sub is None:
            self._create_failed_pending_schedule(
                run, event,
                f"Digital event with unrecognized name pattern: {event.project_name!r}")
            continue
        if sub == 'setup' and event.start_datetime.weekday() != 5:  # 5 = Saturday
            dow_name = event.start_datetime.strftime('%A')
            self._create_failed_pending_schedule(
                run, event,
                f"Digital Demo Setup events must be on Saturdays; "
                f"event has start date {event.start_datetime.date()} ({dow_name})")
            continue
        buckets[sub].append(event)

    # Process in order: Setup → Refresh → Teardown
    for sub_name in ('setup', 'refresh', 'teardown'):
        for event in sorted(buckets[sub_name], key=lambda e: e.start_datetime):
            self._schedule_single_digital(event, sub_name, run)
```

- [ ] **Commit + Gate D.**

## Task T3 — Setup +15 min offsets (branch D4)

- [ ] **Test** — two Setup events on the same Saturday → first gets 10:15, second gets 10:30. Third would get 10:45, etc.

- [ ] **Implement**

Create a per-run counter `self._digital_slot_counters: dict[(date, sub_name), int]` that increments with each assignment. Use it to compute the offset:

```python
def _next_digital_time(self, target_date: date, sub_name: str) -> time:
    key = (target_date, sub_name)
    idx = self._digital_slot_counters.get(key, 0)
    self._digital_slot_counters[key] = idx + 1
    base = self._digital_base_time(target_date, sub_name)
    minutes_offset = idx * 15
    hh, mm = divmod(base.hour * 60 + base.minute + minutes_offset, 60)
    return time(hh % 24, mm)


def _digital_base_time(self, target_date: date, sub_name: str) -> time:
    if sub_name == 'setup':
        return time(10, 15)
    if sub_name == 'refresh':
        if target_date.weekday() == 5:  # Saturday
            return time(12, 0)
        return time(10, 15)
    # teardown
    return time(17, 0)
```

- [ ] **Commit + Gate D.**

## Task T4 — Setup/Refresh employee priority (branches D5, D9)

- [ ] **Step 1: Test**

```python
def test_d5_setup_primary_lead_with_primary_event(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec D5: Setup goes to Primary Lead when they're available AND have a primary event that day."""
    # Setup: Saturday target; Primary Lead has a CORE posted on that Saturday.
    # Expected: Setup assigned to Primary Lead @ 10:15.
    # (Full setup code analogous to plan 05 T5; adjust event_type and name.)
```

- [ ] **Step 2: Implement**

```python
def _schedule_single_digital(self, event, sub_name, run):
    target_date = event.start_datetime.date()
    target_time = self._next_digital_time(target_date, sub_name)
    target_dt = datetime.combine(target_date, target_time)

    if sub_name == 'teardown':
        return self._schedule_digital_teardown(event, target_date, target_dt, run)

    # Setup and Refresh share the Primary Lead → Backup Lead → CS chain
    primary_lead_id, backup_lead_id = lookup_rotation(
        self.db, self.models, target_date, 'primary_lead')

    # D5/D9: Primary Lead + has primary event
    if primary_lead_id and self.cache.is_available(primary_lead_id, target_date):
        if self.cache.has_primary_event(primary_lead_id, target_date):
            self._create_pending_schedule(run, event, primary_lead_id, target_dt)
            return

    # D5/D9 continued: Backup Lead + has primary event
    if backup_lead_id and self.cache.is_available(backup_lead_id, target_date):
        if self.cache.has_primary_event(backup_lead_id, target_date):
            self._create_pending_schedule(run, event, backup_lead_id, target_dt)
            return

    # D5/D9 continued: Club Supervisor unconditionally
    cs_id = self._get_club_supervisor_employee_id()
    if cs_id and self.cache.is_available(cs_id, target_date):
        self._create_pending_schedule(run, event, cs_id, target_dt)
        return

    # No available employee → manual review
    self._create_failed_pending_schedule(
        run, event,
        f"Digital {sub_name}: no Lead with primary event and Club Supervisor "
        f"unavailable on {target_date}")
```

- [ ] **Step 3-5:** Run tests, commit, Gate D.

## Task T5 — Refresh any-day rule (branch D7)

- [ ] **Test** — Refresh on a Wednesday → scheduled at 10:15 AM (non-Saturday base).
- [ ] **Test** — Refresh on a Saturday → scheduled at 12:00 PM.
- [ ] **Implement** — already covered by `_digital_base_time` from T3.
- [ ] **Commit + Gate D.**

## Task T6 — Refresh Saturday vs other time (branch D8)

Duplicate of T5's test. Make it explicit.

- [ ] **Commit + Gate D.**

## Task T7 — Refresh employee priority (branch D9)

Duplicate of T4 for Refresh subcategory. Test + commit + Gate D.

## Task T8 — Teardown any-day rule (branches D10, D11)

- [ ] **Test** — Teardown on a Tuesday → scheduled at 5:00 PM, no day restriction.
- [ ] **Commit + Gate D.**

## Task T9 — Teardown +15 min offsets (branch D12)

- [ ] **Test + implement** — two Teardowns on the same day → 5:00 and 5:15.
- [ ] **Commit + Gate D.**

## Task T10 — Teardown unique employee logic (branches D13, D14)

- [ ] **Test** — a Primary Lead is scheduled for that day (has any event), a non-Primary Lead is also scheduled → the non-Primary Lead gets the Teardown (NOT the Primary Lead).

- [ ] **Implement**

```python
def _find_teardown_employee(self, target_date: date) -> str | None:
    """Spec D13: a Lead != Primary Lead who is scheduled that day.

    "scheduled that day" = has ANY event (primary or secondary) posted
    or in-run on target_date.
    """
    Employee = self.models['Employee']
    primary_lead_id, _ = lookup_rotation(self.db, self.models, target_date, 'primary_lead')

    leads = (self.db.query(Employee)
             .filter(Employee.job_title == 'Lead Event Specialist',
                     Employee.is_active == True,
                     Employee.id != primary_lead_id)
             .order_by(Employee.id.asc())
             .all())

    for lead in leads:
        if not self.cache.is_available(lead.id, target_date):
            continue
        if self._is_scheduled_anywhere(lead.id, target_date):
            return lead.id
    return None


def _is_scheduled_anywhere(self, emp_id: str, d: date) -> bool:
    """True if the employee has ANY event (primary, secondary, teardown) on d.
    Checks both posted Schedule and in-run PendingSchedule."""
    from sqlalchemy import func
    Schedule = self.models['Schedule']
    PendingSchedule = self.models['PendingSchedule']

    posted = (self.db.query(Schedule.id)
              .filter(Schedule.employee_id == emp_id,
                      func.date(Schedule.schedule_datetime) == d)
              .first())
    if posted:
        return True

    pending = (self.db.query(PendingSchedule.id)
               .filter(PendingSchedule.scheduler_run_id == self.current_run_id,
                       PendingSchedule.employee_id == emp_id,
                       func.date(PendingSchedule.schedule_datetime) == d,
                       PendingSchedule.failure_reason.is_(None))
               .first())
    return pending is not None
```

- [ ] **Commit + Gate D.**

## Task T11 — Teardown CS fallback (branch D15)

- [ ] **Test** — no non-Primary Lead scheduled that day → CS gets the Teardown unconditionally.
- [ ] **Implement** — at the end of `_schedule_single_digital` for teardown subcategory, if `_find_teardown_employee` returns None, assign to CS.
- [ ] **Commit + Gate D.**

## Post-flight

- [ ] **Gate C:** cover D1–D15.
- [ ] **Gate E:** every branch test.
- [ ] Open PR: `plan 06: digitals subcategory conformance (Saturday Setup, +15min offsets, Teardown logic)`.
- [ ] Un-xfail any Digitals tests.
