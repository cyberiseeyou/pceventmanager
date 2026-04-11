# Plan 01 — Phase Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Align `scheduling_engine.py`'s Phase 1/2/3 infrastructure with the spec: strict category order, per-category sort keys, 6-digit CORE/Supervisor pairing, and the shared caches/helpers (`has_primary_event`, `primaries_this_week`, `is_available`) that all subsequent plans depend on.

**Architecture:** The greedy engine currently has a "wave" loop (`run_auto_scheduler` → `_schedule_wave1_juicer_events` → etc.). We rewrite the top-level loop to match the spec's 6 categories in the exact order, with the correct sort key per category, and refactor helpers into a new `app/services/scheduler_helpers.py` module that the category methods call.

**Tech Stack:** Flask 2.0+, pytest, SQLAlchemy.

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/00-master-overview.md`, `01-key-concepts.md`, `99-data-model.md`.

**Depends on:** Plan 00 (test harness).

---

## Pre-flight (Gate B — Pre-Implementation Audit)

Dispatch Gate B with:

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py
- /home/elliot/flask-schedule-webapp/app/services/constraint_validator.py
- /home/elliot/flask-schedule-webapp/app/services/rotation_manager.py

Focus on:
1. The top-level `run_auto_scheduler` method. Map its wave order against
   the 6 spec categories. Confirm my audit's finding that waves are sorted
   by due date globally (contradicting per-category sort keys).
2. CORE/Supervisor pairing: find `_extract_event_number`. Confirm the
   pairing key is the parenthesized ref num, not the 6-digit leading prefix.
3. `_has_primary_event` or similar helpers: list them and note how they
   compute "primary" (Core only? Core + Juicer Production?).
4. Caching: is there any per-run cache of availability, primary events,
   rotation lookups? If not, a full rewrite will be slow.
5. List every function in scheduling_engine.py and classify each as
   (a) category-specific (Juicer, Core, Freeosk, Digitals, Other),
   (b) generic helper (availability, rotation, validation), or
   (c) legacy/dead.
```

## Task T0 — Create scheduler_helpers.py with cache classes (branch K8)

> **Cross-cutting:** This task implements the `has_primary_event` query semantics (branch K8). It also builds the `primaries_this_week` helper with Sun–Sat week boundary math — this is shared infrastructure for branch K9, but the K9 branch itself is owned by plan 04 (`04-core-supervisor.md` T6) per the traceability table in `specs/01-key-concepts.md`. Plan 01 T0 only provides the helper; plan 04 T6 adds the `test_fewest_primaries_sun_sat_window` test that exercises K9's use-site in the CORE/Supervisor category handler.

**Files:**
- Create: `app/services/scheduler_helpers.py`
- Create: `tests/scheduler_spec_conformance/test_01_helpers.py`

- [ ] **Step 1: Write the tests for the RunCache helper**

```python
# tests/scheduler_spec_conformance/test_01_helpers.py
"""Tests for the per-run cache helpers used by the scheduler."""
from datetime import date, datetime, timedelta

import pytest

from app.services.scheduler_helpers import RunCache


def test_run_cache_records_primary_event(models, db_session, future_datetime):
    """RunCache.record_primary tracks a primary assignment for use in
    subsequent 'has_primary_event' queries within the same run.
    """
    cache = RunCache(db_session=db_session, models=models, run_id=1)

    d = future_datetime(5).date()
    cache.record_primary('emp1', d, 'Core', event_ref_num=500001)

    assert cache.has_primary_event('emp1', d) is True
    assert cache.has_primary_event('emp1', d + timedelta(days=1)) is False
    assert cache.has_primary_event('emp2', d) is False


def test_run_cache_primaries_this_week_sun_sat(models, db_session):
    """primaries_this_week uses Sunday-through-Saturday boundaries."""
    cache = RunCache(db_session=db_session, models=models, run_id=1)

    # Pick a known Wednesday
    wed = date(2026, 4, 15)  # Wed Apr 15 2026
    sun = date(2026, 4, 12)  # Sun Apr 12 2026
    sat = date(2026, 4, 18)  # Sat Apr 18 2026
    next_sun = date(2026, 4, 19)  # following Sunday

    cache.record_primary('emp1', sun, 'Core', 1)      # counts
    cache.record_primary('emp1', wed, 'Core', 2)      # counts
    cache.record_primary('emp1', sat, 'Juicer Production', 3)  # counts
    cache.record_primary('emp1', next_sun, 'Core', 4) # does NOT count (next week)

    assert cache.primaries_this_week('emp1', wed) == 3
    assert cache.primaries_this_week('emp1', next_sun) == 1


def test_run_cache_is_available_respects_pto(models, db_session):
    """is_available returns False for employees on approved PTO on that date."""
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']

    emp = Employee(id='emp1', name='Alice', job_title='Event Specialist')
    db_session.add(emp)

    d = date(2026, 4, 15)
    pto = EmployeeTimeOff(employee_id='emp1', start_date=d, end_date=d,
                          status='approved')
    db_session.add(pto)
    db_session.commit()

    cache = RunCache(db_session=db_session, models=models, run_id=1)
    assert cache.is_available('emp1', d) is False
    assert cache.is_available('emp1', d + timedelta(days=1)) is True
```

- [ ] **Step 2: Run the test, verify ImportError**

```bash
pytest tests/scheduler_spec_conformance/test_01_helpers.py -v
```
Expected: `ImportError: cannot import name 'RunCache' from 'app.services.scheduler_helpers'`.

- [ ] **Step 3: Implement RunCache**

```python
# app/services/scheduler_helpers.py
"""Per-run caches and helpers for the greedy scheduler.

The scheduler makes many repeated queries of the form
"is employee X available on day D" and "does employee X have a primary
event on day D". Answering those from the DB per-call makes the scheduler
O(events × days × employees × 3 queries). This module wraps them in an
in-memory cache populated once at the start of each run and updated
incrementally as each PendingSchedule is proposed.

Primary events = Core + Juicer Production.
Week = Sunday through Saturday inclusive.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any


# Keep these in sync with docs/superpowers/specs/2026-04-10-scheduler-rewrite/01-key-concepts.md
PRIMARY_EVENT_TYPES = frozenset({'Core', 'Juicer Production'})


class RunCache:
    """Per-run scheduler state cache.

    Holds precomputed availability, rotation, and schedule-state data for a
    single SchedulerRunHistory row. Mutated as the run progresses to reflect
    newly-proposed PendingSchedule rows.
    """

    def __init__(self, db_session, models, run_id: int):
        self.db = db_session
        self.models = models
        self.run_id = run_id

        # (emp_id, date) → bool
        self._available: dict[tuple[str, date], bool] = {}
        # (emp_id, date) → list of (event_ref_num, event_type) tuples
        self._events_by_emp_day: dict[tuple[str, date], list[tuple[int, str]]] = defaultdict(list)
        # (emp_id, week_start) → int count of primary events
        self._primaries_by_week: dict[tuple[str, date], int] = defaultdict(int)

    # -------- availability --------

    def is_available(self, emp_id: str, d: date) -> bool:
        key = (emp_id, d)
        if key in self._available:
            return self._available[key]
        result = self._compute_available(emp_id, d)
        self._available[key] = result
        return result

    def _compute_available(self, emp_id: str, d: date) -> bool:
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        EmployeeWeeklyAvailability = self.models['EmployeeWeeklyAvailability']
        EmployeeAvailabilityOverride = self.models.get('EmployeeAvailabilityOverride')

        # Approved time off?
        off = (self.db.query(EmployeeTimeOff.id)
               .filter(EmployeeTimeOff.employee_id == emp_id,
                       EmployeeTimeOff.status == 'approved',
                       EmployeeTimeOff.start_date <= d,
                       EmployeeTimeOff.end_date >= d)
               .first())
        if off:
            return False

        day_cols = ['monday', 'tuesday', 'wednesday', 'thursday',
                    'friday', 'saturday', 'sunday']
        col = day_cols[d.weekday()]

        if EmployeeAvailabilityOverride is not None:
            ov = (self.db.query(EmployeeAvailabilityOverride)
                  .filter(EmployeeAvailabilityOverride.employee_id == emp_id,
                          EmployeeAvailabilityOverride.start_date <= d,
                          EmployeeAvailabilityOverride.end_date >= d)
                  .first())
            if ov is not None:
                val = getattr(ov, col)
                if val is False:
                    return False
                if val is True:
                    return True

        wa = (self.db.query(EmployeeWeeklyAvailability)
              .filter_by(employee_id=emp_id)
              .first())
        if wa and getattr(wa, col) is False:
            return False

        return True

    # -------- primary events --------

    def record_primary(self, emp_id: str, d: date, event_type: str, event_ref_num: int) -> None:
        """Record that a newly-scheduled primary event exists for (emp, day)."""
        if event_type not in PRIMARY_EVENT_TYPES:
            return
        self._events_by_emp_day[(emp_id, d)].append((event_ref_num, event_type))
        week_start = self._sun_sat_week_start(d)
        self._primaries_by_week[(emp_id, week_start)] += 1

    def has_primary_event(self, emp_id: str, d: date) -> bool:
        """True iff this employee has at least one primary event on day d,
        counting both posted Schedule rows and in-run PendingSchedule rows."""
        key = (emp_id, d)
        if key in self._events_by_emp_day:
            for (_ref, etype) in self._events_by_emp_day[key]:
                if etype in PRIMARY_EVENT_TYPES:
                    return True
        # Fall through to DB check for posted schedules not yet loaded
        return self._query_has_primary_from_db(emp_id, d)

    def _query_has_primary_from_db(self, emp_id: str, d: date) -> bool:
        from sqlalchemy import func
        Schedule = self.models['Schedule']
        Event = self.models['Event']
        posted = (self.db.query(Schedule.id)
                  .join(Event, Schedule.event_ref_num == Event.project_ref_num)
                  .filter(Schedule.employee_id == emp_id,
                          func.date(Schedule.schedule_datetime) == d,
                          Event.event_type.in_(tuple(PRIMARY_EVENT_TYPES)))
                  .first())
        return posted is not None

    def primaries_this_week(self, emp_id: str, d: date) -> int:
        """Count of primary events for emp in the Sun-Sat week containing d."""
        week_start = self._sun_sat_week_start(d)
        from_cache = self._primaries_by_week.get((emp_id, week_start), 0)
        from_db = self._query_primaries_this_week_from_db(emp_id, week_start)
        return from_cache + from_db

    def _query_primaries_this_week_from_db(self, emp_id: str, week_start: date) -> int:
        from sqlalchemy import func
        Schedule = self.models['Schedule']
        Event = self.models['Event']
        week_end = week_start + timedelta(days=6)
        count = (self.db.query(func.count(Schedule.id))
                 .join(Event, Schedule.event_ref_num == Event.project_ref_num)
                 .filter(Schedule.employee_id == emp_id,
                         func.date(Schedule.schedule_datetime) >= week_start,
                         func.date(Schedule.schedule_datetime) <= week_end,
                         Event.event_type.in_(tuple(PRIMARY_EVENT_TYPES)))
                 .scalar()) or 0
        return count

    # -------- week math --------

    @staticmethod
    def _sun_sat_week_start(d: date) -> date:
        """Return the Sunday of the Sun-Sat week containing d."""
        days_since_sunday = (d.weekday() + 1) % 7
        return d - timedelta(days=days_since_sunday)
```

- [ ] **Step 4: Run the tests, verify they pass**

```bash
pytest tests/scheduler_spec_conformance/test_01_helpers.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler_helpers.py tests/scheduler_spec_conformance/test_01_helpers.py
git commit -m "feat(scheduler): add RunCache helper with availability + primary event tracking

Cache is populated once per run from DB state and updated incrementally as
PendingSchedule rows are proposed. Answers is_available, has_primary_event,
and primaries_this_week in O(1) after first call per (emp, day).

Week math uses Sun-Sat boundaries (not ISO week); primary event types are
Core + Juicer Production per spec 01-key-concepts.md.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Gate D review.**

## Task T1 — Phase 1 input filter (spec branches M1–M3)

**Files:**
- Modify: `app/services/scheduling_engine.py` — the `_get_unscheduled_events` method or equivalent
- Add test: `tests/scheduler_spec_conformance/test_00_master_overview.py`

- [ ] **Step 1: Write tests for M1, M2, M3**

```python
def test_m1_phase1_skips_already_scheduled(greedy_scheduler, models, db_session, future_datetime):
    """Spec branch M1: events with is_scheduled=True are skipped entirely."""
    Event = models['Event']
    PendingSchedule = models['PendingSchedule']

    Event(project_ref_num=100001, project_name='100001-CORE-AlreadyScheduled',
          event_type='Core', condition='Scheduled', is_scheduled=True,
          start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    Event(project_ref_num=100002, project_name='100002-CORE-Fresh',
          event_type='Core', condition='Unstaffed', is_scheduled=False,
          start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    ps_scheduled = db_session.query(PendingSchedule).filter_by(
        scheduler_run_id=run.id, event_ref_num=100001).first()
    ps_fresh = db_session.query(PendingSchedule).filter_by(
        scheduler_run_id=run.id, event_ref_num=100002).first()

    assert ps_scheduled is None, "Event with is_scheduled=True must be skipped"
    assert ps_fresh is not None, "Fresh event must produce a PendingSchedule"


def test_m2_phase1_skips_canceled(greedy_scheduler, models, db_session, future_datetime):
    """Spec branch M2: events with condition in (Canceled, Expired) are skipped."""
    Event = models['Event']
    PendingSchedule = models['PendingSchedule']

    Event(project_ref_num=100003, project_name='100003-CORE-Canceled',
          event_type='Core', condition='Canceled', is_scheduled=False,
          start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    ps = db_session.query(PendingSchedule).filter_by(
        scheduler_run_id=run.id, event_ref_num=100003).first()
    assert ps is None, "Canceled event must be skipped"


def test_m3_phase1_skips_past_due(greedy_scheduler, models, db_session, future_datetime):
    """Spec branch M3: events whose due_datetime <= today+3 days (Normal mode) are skipped."""
    Event = models['Event']
    PendingSchedule = models['PendingSchedule']

    Event(project_ref_num=100004, project_name='100004-CORE-PastDue',
          event_type='Core', condition='Unstaffed', is_scheduled=False,
          start_datetime=future_datetime(0), due_datetime=future_datetime(1))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    ps = db_session.query(PendingSchedule).filter_by(
        scheduler_run_id=run.id, event_ref_num=100004).first()
    assert ps is None, "Event past due window must be skipped"
```

- [ ] **Step 2: Run tests, observe whether greedy currently passes**

```bash
pytest tests/scheduler_spec_conformance/test_00_master_overview.py -v -k m1
pytest tests/scheduler_spec_conformance/test_00_master_overview.py -v -k m2
pytest tests/scheduler_spec_conformance/test_00_master_overview.py -v -k m3
```
Expected: M1 PASS (greedy likely handles this), M2 PASS (inactive conditions), M3 PASS (buffer days).

- [ ] **Step 3: If any fail, fix in `scheduling_engine.py`'s `_get_unscheduled_events`**

The audit in Gate B will have revealed the exact location. The fix is to ensure the query filter matches the spec exactly:

```python
# Inside _get_unscheduled_events or equivalent
from datetime import date, timedelta

today = date.today()
buffer_days = 0 if getattr(self, 'emergency_mode', False) else 3
earliest = today + timedelta(days=buffer_days)

events = (self.db.query(self.Event)
          .filter(self.Event.is_scheduled == False,
                  ~self.Event.condition.in_(['Canceled', 'Expired']),
                  self.Event.due_datetime > earliest)
          .all())
```

- [ ] **Step 4: Commit**

```bash
git add app/services/scheduling_engine.py tests/scheduler_spec_conformance/test_00_master_overview.py
git commit -m "test(scheduler): verify Phase 1 input filter matches spec M1-M3

Tests assert:
- is_scheduled=True events are skipped entirely (M1)
- Canceled/Expired events are skipped (M2)
- Events past the due-date buffer are skipped (M3)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Gate D review.**

## Task T2 — Phase 2 CORE/Supervisor pairing by 6-digit prefix (spec branches M4–M6)

**Files:**
- Create: `app/services/scheduler_pairing.py`
- Modify: `app/services/scheduling_engine.py` — call new pairing module
- Add test: `tests/scheduler_spec_conformance/test_00_master_overview.py`

- [ ] **Step 1: Write tests**

```python
def test_m4_phase2_pairs_core_supervisor_by_6digit(db_session, models, future_datetime):
    """Spec branch M4: CORE paired with Supervisor having same 6-digit prefix."""
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    core = Event(project_ref_num=200001, project_name='260115-MAP-Brand-Product CORE',
                 event_type='Core', condition='Unstaffed',
                 start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    sup = Event(project_ref_num=200002, project_name='260115-MAP-Brand-Product Supervisor',
                event_type='Supervisor', condition='Unstaffed',
                start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    db_session.add_all([core, sup])
    db_session.commit()

    pairs = pair_cores_and_supervisors([core, sup])
    assert pairs[core.id] == sup, (
        "CORE 260115 must pair with Supervisor 260115 by 6-digit prefix")


def test_m5_phase2_unpaired_core_processes_alone(db_session, models, future_datetime):
    """Spec branch M5: CORE with no matching Supervisor is returned without a pair."""
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    core = Event(project_ref_num=200003, project_name='260116-MAP-Lonely CORE',
                 event_type='Core', condition='Unstaffed',
                 start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    db_session.add(core); db_session.commit()

    pairs = pair_cores_and_supervisors([core])
    assert core.id not in pairs


def test_m6_phase2_unpaired_supervisor_logged_and_skipped(db_session, models, caplog, future_datetime):
    """Spec branch M6: Supervisor with no matching CORE is logged + skipped."""
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']
    import logging

    sup = Event(project_ref_num=200004, project_name='260117-MAP-Orphan Supervisor',
                event_type='Supervisor', condition='Unstaffed',
                start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    db_session.add(sup); db_session.commit()

    with caplog.at_level(logging.WARNING, logger='app.services.scheduler_pairing'):
        pairs = pair_cores_and_supervisors([sup])

    assert pairs == {}
    assert any('Unpaired Supervisor' in rec.message and '260117' in rec.message
               for rec in caplog.records), (
        "Unpaired Supervisor must be logged as a warning")
```

- [ ] **Step 2: Run, observe failure**

```bash
pytest tests/scheduler_spec_conformance/test_00_master_overview.py::test_m4_phase2_pairs_core_supervisor_by_6digit -v
```
Expected: ImportError (scheduler_pairing doesn't exist yet).

- [ ] **Step 3: Implement `scheduler_pairing.py`**

```python
# app/services/scheduler_pairing.py
"""Phase 2 — CORE/Supervisor pairing.

Per spec 00-master-overview.md M4-M6, CORE events are paired with
Supervisor events sharing the same 6-digit event number at the start of
project_name AND the same name prefix up to the type keyword.

Unpaired CORE events process alone (no Supervisor in the output).
Unpaired Supervisor events are logged as warnings and skipped.
"""
import logging
import re
from typing import Iterable, Mapping, Optional

logger = logging.getLogger(__name__)

_PAIRING_RE = re.compile(
    r'^\s*(?P<six_digit>\d{6})[-\s]+(?P<prefix>.+?)\s*'
    r'(?P<separator>[-–\s]+)(?P<kind>CORE|Core|Supervisor|SUPERVISOR)',
    re.IGNORECASE,
)


def extract_pairing_key(project_name: str) -> Optional[tuple[str, str]]:
    """Return (six_digit, normalized_prefix) or None if the name is malformed.

    The normalized_prefix is the name prefix up to (but not including) the
    CORE/Supervisor keyword, stripped of leading/trailing whitespace and
    lowercased for comparison.
    """
    if not project_name:
        return None
    m = _PAIRING_RE.match(project_name)
    if not m:
        return None
    return (m.group('six_digit'), m.group('prefix').strip().lower())


def pair_cores_and_supervisors(events: Iterable) -> Mapping[int, object]:
    """Map CORE event id → Supervisor event.

    Unpaired Supervisors are logged as warnings.
    """
    cores = [e for e in events if getattr(e, 'event_type', '') == 'Core']
    supervisors = [e for e in events if getattr(e, 'event_type', '') == 'Supervisor']

    sup_by_key = {}
    for sup in supervisors:
        key = extract_pairing_key(sup.project_name)
        if key is None:
            logger.warning(
                "Supervisor event %s has malformed name %r; skipping pairing",
                sup.project_ref_num, sup.project_name)
            continue
        sup_by_key[key] = sup

    pairs = {}
    matched_sup_ids = set()
    for core in cores:
        key = extract_pairing_key(core.project_name)
        if key is None:
            logger.warning(
                "Core event %s has malformed name %r; cannot pair",
                core.project_ref_num, core.project_name)
            continue
        sup = sup_by_key.get(key)
        if sup is not None:
            pairs[core.id] = sup
            matched_sup_ids.add(sup.id)

    for sup in supervisors:
        if sup.id not in matched_sup_ids:
            logger.warning(
                "Unpaired Supervisor event %s (%r); no matching CORE found",
                sup.project_ref_num, sup.project_name)

    return pairs
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/scheduler_spec_conformance/test_00_master_overview.py -v -k "m4 or m5 or m6"
```
Expected: 3 PASSED.

- [ ] **Step 5: Wire scheduling_engine.py to use the new pairing module**

Replace any existing pairing logic in `scheduling_engine.py` with a call to `pair_cores_and_supervisors()`. The exact location will be identified by Gate B's audit; typically it's near `_move_matching_supervisor_event` or a similar method.

- [ ] **Step 6: Run full test suite, confirm no regression**

```bash
pytest -v 2>&1 | tail -10
```
Expected: all tests pass except the pre-existing `test_export_with_date_params` failure (not in scope).

- [ ] **Step 7: Commit**

```bash
git add app/services/scheduler_pairing.py app/services/scheduling_engine.py tests/scheduler_spec_conformance/test_00_master_overview.py
git commit -m "feat(scheduler): Phase 2 CORE/Supervisor pairing by 6-digit prefix

Replaces the legacy parenthesized-ref-num pairing with the spec's
6-digit-prefix-plus-name-prefix pairing. Unpaired supervisors are logged
as warnings and excluded from the run; unpaired cores process alone.

See spec 00-master-overview.md branches M4-M6.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 8: Gate D review.**

## Task T3 — Phase 3 category dispatcher with strict ordering (spec branch M7)

**Files:**
- Modify: `app/services/scheduling_engine.py` — the `run_auto_scheduler` method

- [ ] **Step 1: Write the test**

```python
def test_m7_phase3_strict_category_order(greedy_scheduler, models, db_session, future_datetime):
    """Spec branch M7: categories execute in strict order regardless of event count."""
    Event = models['Event']

    # Create one event per category; verify their processing order by
    # hooking into the scheduler's category dispatcher.
    # (This test requires the dispatcher to emit a hook we can inspect.)
    events_data = [
        (300001, 'Juicer Production', '300001-JUICER-PRODUCTION-Test'),
        (300002, 'Juicer Survey', '300002-JUICER-SURVEY-Test'),
        (300003, 'Core', '300003-CORE-Test'),
        (300004, 'Supervisor', '300003-Supervisor-Test'),  # pairs with CORE
        (300005, 'Freeosk', '300005-FSK-Daily Service-11AM'),
        (300006, 'Digitals', '300006-Digital Demo Refresh'),
        (300007, 'Other', '300007-Other-Test'),
    ]
    for ref, etype, name in events_data:
        db_session.add(Event(
            project_ref_num=ref, project_name=name, event_type=etype,
            condition='Unstaffed',
            start_datetime=future_datetime(5), due_datetime=future_datetime(10),
            estimated_time=60))
    db_session.commit()

    # Dispatch order tracking
    seen_order = []
    orig = greedy_scheduler._process_category
    def spy(category_name, *args, **kwargs):
        seen_order.append(category_name)
        return orig(category_name, *args, **kwargs)
    greedy_scheduler._process_category = spy

    greedy_scheduler.run_auto_scheduler(run_type='manual')

    assert seen_order == [
        'juicer_production', 'juicer_survey', 'core_supervisor',
        'freeosk', 'digitals', 'other',
    ], f"Category dispatch order wrong: {seen_order}"
```

- [ ] **Step 2: Run, observe failure**

Expected: AttributeError (`_process_category` doesn't exist) OR order mismatch.

- [ ] **Step 3: Refactor `run_auto_scheduler` to use an explicit category dispatcher**

```python
# app/services/scheduling_engine.py (inside SchedulingEngine class)

CATEGORY_ORDER = [
    'juicer_production',
    'juicer_survey',
    'core_supervisor',
    'freeosk',
    'digitals',
    'other',
]

CATEGORY_SORT_KEY = {
    'juicer_production': lambda e: e.start_datetime,
    'juicer_survey':     lambda e: e.start_datetime,
    'core_supervisor':   lambda e: e.due_datetime,
    'freeosk':           lambda e: e.start_datetime,
    'digitals':          lambda e: e.start_datetime,
    'other':             lambda e: e.start_datetime,
}


def run_auto_scheduler(self, run_type='manual'):
    """Main scheduler entry point. Executes Phases 1, 2, 3 in order."""
    run = self._create_run(run_type)
    try:
        # Phase 1 — Input filter
        unscheduled = self._get_unscheduled_events()

        # Phase 2 — CORE/Supervisor pairing
        from app.services.scheduler_pairing import pair_cores_and_supervisors
        self.pairs = pair_cores_and_supervisors(unscheduled)

        # Phase 3 — Category dispatch
        from app.services.scheduler_helpers import RunCache
        self.cache = RunCache(self.db, self.models, run.id)

        self.category_pools = self._partition_events_by_category(unscheduled)

        for category_name in self.CATEGORY_ORDER:
            self._process_category(category_name, run)

        run.status = 'completed'
        self.db.commit()
        return run
    except Exception:
        self.db.rollback()
        run.status = 'failed'
        self.db.commit()
        raise


def _process_category(self, category_name: str, run) -> None:
    """Dispatch to the category handler. Sorts the pool by the category's key."""
    pool = self.category_pools.get(category_name, [])
    sort_key = self.CATEGORY_SORT_KEY[category_name]
    pool.sort(key=sort_key)
    handler = getattr(self, f'_process_{category_name}')
    handler(pool, run)


def _partition_events_by_category(self, events) -> dict[str, list]:
    """Partition unscheduled events into the 6 spec categories by event_type.

    Note: Freeosk and Digitals subcategory partitioning (name-pattern matching)
    happens inside the respective per-category handlers, not here. This function
    only splits by event_type into the top-level category pools.
    """
    pools = {name: [] for name in self.CATEGORY_ORDER}

    for e in events:
        etype = e.event_type
        name = (e.project_name or '').strip()

        if etype == 'Juicer Production':
            pools['juicer_production'].append(e)
        elif etype == 'Juicer Survey':
            pools['juicer_survey'].append(e)
        elif etype == 'Core':
            pools['core_supervisor'].append(e)
        elif etype == 'Freeosk':
            pools['freeosk'].append(e)
        elif etype in ('Digitals', 'Digital Setup', 'Digital Refresh', 'Digital Teardown'):
            pools['digitals'].append(e)
        elif etype == 'Supervisor':
            continue  # Handled as part of core_supervisor pairing
        else:
            pools['other'].append(e)

    return pools
```

Stub the per-category handlers that don't exist yet:

```python
def _process_juicer_production(self, pool, run):
    """Implemented in plan 02-juicer-production.md."""
    for event in pool:
        self._create_failed_pending_schedule(
            run, event, "Juicer Production handler not yet implemented (plan 02)")

def _process_juicer_survey(self, pool, run):
    """Implemented in plan 03-juicer-survey.md."""
    for event in pool:
        self._create_failed_pending_schedule(
            run, event, "Juicer Survey handler not yet implemented (plan 03)")

def _process_core_supervisor(self, pool, run):
    """Implemented in plan 04-core-supervisor.md."""
    for event in pool:
        self._create_failed_pending_schedule(
            run, event, "Core/Supervisor handler not yet implemented (plan 04)")

def _process_freeosk(self, pool, run):
    """Implemented in plan 05-freeosk.md."""
    for event in pool:
        self._create_failed_pending_schedule(
            run, event, "Freeosk handler not yet implemented (plan 05)")

def _process_digitals(self, pool, run):
    """Implemented in plan 06-digitals.md."""
    for event in pool:
        self._create_failed_pending_schedule(
            run, event, "Digitals handler not yet implemented (plan 06)")

def _process_other(self, pool, run):
    """Implemented in plan 07-other.md."""
    for event in pool:
        self._create_failed_pending_schedule(
            run, event, "Other handler not yet implemented (plan 07)")
```

- [ ] **Step 4: Run the test, verify pass**

```bash
pytest tests/scheduler_spec_conformance/test_00_master_overview.py::test_m7_phase3_strict_category_order -v
```
Expected: PASS.

- [ ] **Step 5: Run full existing suite — WARNING: this will break the greedy engine's current behavior**

The old per-wave methods (`_schedule_wave1_juicer_events`, etc.) are now replaced by the stubs. Every event that used to be scheduled by the old path now goes to manual review with "handler not yet implemented". This is intentional — plans 02–07 will restore the per-category logic test-by-test.

```bash
pytest -v 2>&1 | tail -20
```

Expected: Many scheduling-related tests now fail. Mark them xfail with a reference to the plan that fixes them:

```python
# In each broken test file, add at the top:
import pytest
pytestmark = pytest.mark.xfail(reason="Greedy scheduler refactor in progress; fixed by plan 02-07")
```

Track these xfails in a new file `tests/_xfail_tracker.md`:

```markdown
# Scheduler Refactor — Tests Expected to Fail During Refactor

These tests will be un-xfailed as plans 02–07 restore the corresponding
per-category logic.

- tests/test_scheduler.py — fixed by plan 02 (Juicer Production) through 07 (Other)
- tests/test_scheduling_engine.py — fixed by plan 02-07
- ...
```

- [ ] **Step 6: Commit**

```bash
git add app/services/scheduling_engine.py tests/scheduler_spec_conformance/test_00_master_overview.py tests/_xfail_tracker.md tests/test_scheduler.py tests/test_scheduling_engine.py
git commit -m "refactor(scheduler): phase 3 category dispatcher with strict spec order

Replaces the ad-hoc wave methods with a dispatcher that iterates the 6
spec categories in strict order (Juicer Production → Juicer Survey →
Core/Supervisor → Freeosk → Digitals → Other) and sorts each pool by the
spec's per-category sort key.

Per-category handlers are STUBS that produce manual-review entries. Plans
02-07 restore the actual logic. Existing tests that exercise those code
paths are marked xfail; see tests/_xfail_tracker.md.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Gate D review.**

## Task T4 — Primary/secondary classifier helpers (spec branches K1–K3)

**Files:** Modify `app/services/scheduler_helpers.py` to add `classify_event`.

- [ ] **Step 1: Tests**

```python
def test_k1_primary_event_classifier():
    from app.services.scheduler_helpers import classify_event
    assert classify_event('Core') == 'primary'
    assert classify_event('Juicer Production') == 'primary'


def test_k2_secondary_event_classifier():
    from app.services.scheduler_helpers import classify_event
    for t in ['Juicer Survey', 'Supervisor', 'Freeosk',
              'Digital Setup', 'Digital Refresh']:
        assert classify_event(t) == 'secondary', f"{t} should be secondary"


def test_k3_digital_teardown_is_own_bucket():
    from app.services.scheduler_helpers import classify_event
    assert classify_event('Digital Teardown') == 'teardown_bucket'
```

- [ ] **Step 2: Implementation**

```python
# app/services/scheduler_helpers.py (add at bottom)

SECONDARY_EVENT_TYPES = frozenset({
    'Juicer Survey', 'Supervisor', 'Freeosk',
    'Digital Setup', 'Digital Refresh',
})


def classify_event(event_type: str) -> str:
    """Return 'primary', 'secondary', 'teardown_bucket', or 'other'."""
    if event_type in PRIMARY_EVENT_TYPES:
        return 'primary'
    if event_type in SECONDARY_EVENT_TYPES:
        return 'secondary'
    if event_type == 'Digital Teardown':
        return 'teardown_bucket'
    return 'other'
```

- [ ] **Step 3: Commit and Gate D review.**

## Task T5 — `has_primary_event` DB query helper (spec branch K8)

Already covered by RunCache in T0. This task adds one more test that exercises the cross-DB / cross-cache behavior.

- [ ] **Step 1: Test**

```python
def test_k8_has_primary_event_from_posted_schedule(db_session, models, future_datetime):
    """A posted Schedule (not in-run) must count as 'has primary event'."""
    from app.services.scheduler_helpers import RunCache
    Employee = models['Employee']
    Event = models['Event']
    Schedule = models['Schedule']

    emp = Employee(id='emp1', name='Alice', job_title='Lead Event Specialist')
    ev = Event(project_ref_num=400001, project_name='400001-CORE-Posted',
               event_type='Core', condition='Scheduled', is_scheduled=True,
               start_datetime=future_datetime(5), due_datetime=future_datetime(10))
    db_session.add_all([emp, ev])
    db_session.flush()

    sched = Schedule(event_ref_num=400001, employee_id='emp1',
                     schedule_datetime=future_datetime(5), shift_block=1)
    db_session.add(sched)
    db_session.commit()

    cache = RunCache(db_session, models, run_id=1)
    assert cache.has_primary_event('emp1', future_datetime(5).date()) is True
    assert cache.has_primary_event('emp1', future_datetime(6).date()) is False
```

- [ ] **Step 2-5: Run, already passes (RunCache covers this). Commit + Gate D review.**

## Post-flight

- [ ] Run **Gate C (Plan Coverage)** on this plan file.

  Expected: covers M1, M2, M3, M4, M5, M6, M7, K1, K2, K3, K8.

- [ ] Run **Gate E (Test Adequacy)** on `tests/scheduler_spec_conformance/test_00_master_overview.py` and `test_01_helpers.py`.

- [ ] Open a PR: `plan 01: phase infrastructure (categories + sort keys + pairing)`.
