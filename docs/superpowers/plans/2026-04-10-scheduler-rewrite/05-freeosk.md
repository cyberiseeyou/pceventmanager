# Plan 05 — Freeosk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Implement `_process_freeosk` to match spec `05-freeosk.md` branches F1–F11. Key features: 3 subcategories identified by name pattern, strict processing order (Daily Service → Changeover → Troubleshooting), fixed times per subcategory, Primary Lead → Backup Lead → CS unconditional.

**Architecture:** `_process_freeosk(pool, run)` partitions the pool into 3 subcategory lists, then iterates them in order. Each event uses `freeosk_subcategory()` helper from `scheduler_helpers.py` (added in this plan's Task T1) to determine subcategory and time.

**Source spec:** `docs/superpowers/specs/2026-04-10-scheduler-rewrite/05-freeosk.md`.

**Depends on:** Plans 00, 01, 04 (for `has_primary_event` query cache).

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/services/scheduling_engine.py (the old _schedule_freeosk_* methods)

Focus on:
1. Does ANY current code detect "FSK-Daily Service-11AM" or "CO-11AM"
   as subcategories? Audit confirmed NO; verify.
2. The existing Freeosk code uses `_get_next_freeosk_time_slot` or similar.
   What times does it currently produce?
3. Existing Troubleshooting detection code — reuse if clean.
```

## Task T1 — Subcategory classifier (branches F1, F2)

- [ ] **Step 1: Test the classifier in isolation**

```python
# tests/scheduler_spec_conformance/test_05_freeosk.py
from app.services.scheduler_helpers import freeosk_subcategory

def test_f1_classifier_daily_service():
    assert freeosk_subcategory('191001-FSK-Daily Service-11AM-Brand') == 'daily_service'

def test_f1_classifier_changeover():
    assert freeosk_subcategory('191002-CO-11AM-Brand-Product') == 'changeover'

def test_f1_classifier_troubleshooting():
    assert freeosk_subcategory('191003-FSK-Troubleshooting-Visit') == 'troubleshooting'

def test_f2_classifier_unrecognized_returns_none():
    assert freeosk_subcategory('191004-FSK-Unknown-Format') is None
```

- [ ] **Step 2: Implement in `app/services/scheduler_helpers.py`**

```python
def freeosk_subcategory(project_name: str) -> str | None:
    """Return 'daily_service', 'changeover', 'troubleshooting', or None.

    Matches the name-contains rules from spec 05-freeosk.md.
    """
    if not project_name:
        return None
    name = project_name
    # Order matters — Daily Service has a specific substring that could
    # overlap with Troubleshooting in edge cases. Check most specific first.
    if 'FSK-Daily Service-11AM' in name:
        return 'daily_service'
    if 'CO-11AM' in name:
        return 'changeover'
    if 'Troubleshooting' in name:
        return 'troubleshooting'
    return None
```

- [ ] **Step 3-5:** Run tests, commit, Gate D.

## Task T2 — Partition pool by subcategory + unrecognized to manual review (branches F1, F2)

- [ ] **Test + implement + commit + Gate D.**

```python
def _process_freeosk(self, pool, run):
    """Spec 05. Partition, order by subcategory, schedule each."""
    from app.services.scheduler_helpers import freeosk_subcategory

    buckets = {'daily_service': [], 'changeover': [], 'troubleshooting': []}
    for event in pool:
        sub = freeosk_subcategory(event.project_name)
        if sub is None:
            self._create_failed_pending_schedule(
                run, event,
                f"Freeosk event with unrecognized name pattern: {event.project_name!r}. "
                f"Expected 'FSK-Daily Service-11AM', 'CO-11AM', or 'Troubleshooting' "
                f"in the name.")
            continue
        buckets[sub].append(event)

    # F3, F4: strict processing order A → B → C, sorted by start_datetime within each
    for sub_name in ('daily_service', 'changeover', 'troubleshooting'):
        for event in sorted(buckets[sub_name], key=lambda e: e.start_datetime):
            self._schedule_single_freeosk(event, sub_name, run)
```

## Task T3 — Processing order verification (branches F3, F4)

Test: add 3 events of different subcategories in "wrong" order. Assert they're scheduled in A → B → C order (verify via a spy on `_schedule_single_freeosk`).

- [ ] **Commit + Gate D.**

## Task T4 — Time by subcategory (branches F5, F6)

- [ ] **Test + implement + commit + Gate D.**

```python
FREEOSK_TIMES = {
    'daily_service': time(10, 0),
    'changeover': time(10, 0),
    'troubleshooting': time(12, 0),
}


def _schedule_single_freeosk(self, event, sub_name, run):
    target_date = event.start_datetime.date()
    target_time = FREEOSK_TIMES[sub_name]
    target_dt = datetime.combine(target_date, target_time)
    # ... employee priority chain (T5-T7) ...
```

## Task T5 — Primary Lead + has primary event (branch F7)

- [ ] **Test + implement + commit + Gate D.**

```python
primary_lead_id, backup_lead_id = lookup_rotation(self.db, self.models, target_date, 'primary_lead')

if primary_lead_id and self.cache.is_available(primary_lead_id, target_date):
    if self.cache.has_primary_event(primary_lead_id, target_date):
        self._create_pending_schedule(run, event, primary_lead_id, target_dt)
        return
```

## Task T6 — Backup Lead + has primary event (branches F8, F9)

- [ ] **Test + implement + commit + Gate D.** Pattern repeats T5 for backup_lead_id.

## Task T7 — Club Supervisor unconditional fallback (branch F10)

- [ ] **Test** — both leads unavailable or no primary event → CS gets Freeosk, CS has no primary event that day, assignment still succeeds.

- [ ] **Implement + commit + Gate D.**

```python
cs_id = self._get_club_supervisor_employee_id()
if cs_id and self.cache.is_available(cs_id, target_date):
    self._create_pending_schedule(run, event, cs_id, target_dt)
    return
```

## Task T8 — CS on PTO → manual review (branch F11)

- [ ] **Test + implement + commit + Gate D.**

```python
self._create_failed_pending_schedule(
    run, event,
    f"Freeosk {sub_name}: no Lead with primary event and Club Supervisor "
    f"unavailable on {target_date}")
```

## Post-flight

- [ ] **Gate C:** cover F1–F11.
- [ ] **Gate E:** every branch test.
- [ ] Open PR: `plan 05: freeosk subcategory conformance`.
- [ ] Un-xfail any Freeosk tests that were xfail'd in plan 01 T3.
