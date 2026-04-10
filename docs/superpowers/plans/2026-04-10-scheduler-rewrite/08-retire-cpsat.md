# Plan 08 — Retire CP-SAT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`.

**Goal:** Remove CP-SAT from the production code path entirely. The `cpsat_scheduler.py` module is preserved in the repo as a deprecated analyzer (callable via a separate entry point for offline scenarios), but `CPSAT_ENABLED` and the production dispatch logic are removed.

**Architecture:** Three-part change: (1) delete the CPSAT_ENABLED branch in `app/routes/auto_scheduler.py`; (2) delete `CPSAT_ENABLED` from `app/config.py`; (3) mark the CP-SAT stress tests as `@pytest.mark.optional` and stop running them in CI.

**Source spec:** No new spec. Implements the "retire CP-SAT" decision from the master plan README.

**Depends on:** Plans 00–07 (all categories must be implemented in greedy first).

---

## Pre-flight (Gate B)

```
Files to audit:
- /home/elliot/flask-schedule-webapp/app/routes/auto_scheduler.py (CPSAT dispatch logic)
- /home/elliot/flask-schedule-webapp/app/config.py (flag definition)
- /home/elliot/flask-schedule-webapp/tests/test_cpsat_stress.py
- /home/elliot/flask-schedule-webapp/tests/test_cpsat_scheduler.py
- /home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py (module to deprecate)

Focus on:
1. Every place CPSAT_ENABLED is read.
2. Every place CPSATSchedulingEngine is imported or instantiated.
3. Tests that explicitly opt into CPSAT (from plan 00 T2 fix).
4. CI configuration: does CI currently run the CPSAT stress tests?
   (Check .github/workflows/ci.yml and pytest.ini if present.)
```

## Task T1 — Gate condition: verify all conformance tests pass

Before touching anything, confirm the greedy engine fully satisfies the spec:

- [ ] **Step 1: Run the full conformance test suite**

```bash
pytest tests/scheduler_spec_conformance/ -v 2>&1 | tail -20
```

Expected: every test PASSES (or is explicitly marked xfail with a reference to a follow-up plan — none should be xfail at this point).

- [ ] **Step 2: Verify no xfail remains from plans 02–07**

```bash
grep -r "xfail" tests/scheduler_spec_conformance/ tests/test_scheduler.py tests/test_scheduling_engine.py 2>&1
```

Expected: no xfail markers in scheduler tests.

- [ ] **Step 3: If any xfail remains, STOP and go back to the relevant plan (02–07) to fix.**

Do NOT proceed with CP-SAT retirement if the greedy engine is incomplete.

## Task T2 — Remove CPSAT_ENABLED from auto_scheduler.py

- [ ] **Step 1: Test — a failing test that asserts CPSAT is not invoked**

```python
# tests/scheduler_spec_conformance/test_08_cpsat_retired.py
"""Confirm CP-SAT is no longer invokable via the production auto-scheduler route."""
from unittest.mock import patch


def test_cpsat_not_invoked_by_production_route(client, db_session, models):
    """The /auto-schedule/run route never instantiates CPSATSchedulingEngine."""
    with patch('app.services.cpsat_scheduler.CPSATSchedulingEngine') as mock_cpsat:
        # POST to the run endpoint
        response = client.post('/auto-schedule/run', data={'run_type': 'manual'},
                                follow_redirects=False)
        # Assert CPSAT was never constructed
        assert not mock_cpsat.called, (
            "CPSATSchedulingEngine must not be called from the production "
            "route after plan 08")
```

- [ ] **Step 2: Run → FAIL** (CP-SAT is still callable via `CPSAT_ENABLED=true`).

- [ ] **Step 3: Edit `app/routes/auto_scheduler.py`**

Remove the `CPSAT_ENABLED` check entirely. Replace:

```python
use_cpsat = current_app.config.get('CPSAT_ENABLED', False)
if use_cpsat:
    from app.services.cpsat_scheduler import CPSATSchedulingEngine
    ...
    engine = CPSATSchedulingEngine(db.session, cpsat_models)
else:
    engine = SchedulingEngine(db.session, models)
```

With:

```python
engine = SchedulingEngine(db.session, models)
```

And remove the adjacent `cpsat_enabled = current_app.config.get('CPSAT_ENABLED', False)` line used in the GET view (line 72-ish).

- [ ] **Step 4: Run test, verify pass.** Commit + Gate D review.

```bash
git add app/routes/auto_scheduler.py tests/scheduler_spec_conformance/test_08_cpsat_retired.py
git commit -m "refactor(scheduler): remove CPSAT_ENABLED from production route

The greedy SchedulingEngine is now the only scheduler invoked from the
production auto-schedule route. CP-SAT remains in the repo as a module
that can be run via a separate analyzer entry point (see docs).

Part of the scheduler rewrite — plan 08.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task T3 — Remove CPSAT_ENABLED from app/config.py

- [ ] **Step 1: Test**

```python
def test_cpsat_enabled_flag_removed(app):
    """Config should not define CPSAT_ENABLED."""
    assert 'CPSAT_ENABLED' not in app.config, (
        "CPSAT_ENABLED flag must be removed after plan 08")
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Edit `app/config.py:63`, delete the line `CPSAT_ENABLED = config('CPSAT_ENABLED', ...)`.**

- [ ] **Step 4: Run → PASS. Commit + Gate D.**

## Task T4 — Mark CPSAT stress tests optional

- [ ] **Step 1: Edit `tests/test_cpsat_stress.py` and `tests/test_cpsat_scheduler.py`**

Add at the top of each file:

```python
import pytest

# After plan 08, CP-SAT is no longer in the production code path. These
# tests are preserved for when CP-SAT is resurrected as an offline analyzer
# but are marked `optional` so CI does not run them by default.
pytestmark = pytest.mark.optional
```

- [ ] **Step 2: Register the mark in `pytest.ini`**

```ini
# pytest.ini (or pyproject.toml [tool.pytest.ini_options])
[pytest]
markers =
    optional: Optional test, not run by default
addopts = -m "not optional"
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_cpsat_stress.py tests/test_cpsat_scheduler.py -v
```

Expected: all tests skipped (due to `-m "not optional"`).

```bash
pytest tests/test_cpsat_stress.py tests/test_cpsat_scheduler.py -v -m optional
```

Expected: tests run (explicit opt-in).

- [ ] **Step 4: Commit + Gate D.**

## Task T5 — Remove `_force_cpsat` fixtures that were added in plan 00 T2

After plans 00–07, the fixtures in `tests/test_cpsat_stress.py` that force `CPSAT_ENABLED=true` are no longer needed because the flag is gone. Delete them.

- [ ] **Step 1: Edit `tests/test_cpsat_stress.py` — remove the `_force_cpsat` autouse fixture added in plan 00 T2.**

- [ ] **Step 2: Run the full suite — confirm nothing breaks.**

- [ ] **Step 3: Commit + Gate D.**

## Task T6 — Add deprecation comment to cpsat_scheduler.py

- [ ] **Step 1: Edit the top of `app/services/cpsat_scheduler.py`:**

```python
"""
CP-SAT Constraint-Programming Auto-Scheduler
=============================================

⚠️ DEPRECATED: This module is NOT the production scheduler as of 2026-04-10.

The production scheduler is `app/services/scheduling_engine.py` (greedy,
spec-conformant). This CP-SAT implementation is preserved for:
1. Historical reference.
2. Optional offline analysis (e.g., "what would the globally-optimal
   schedule look like for this input?") via a separate entry point.
3. Stress tests under tests/test_cpsat_stress.py (run with `-m optional`).

DO NOT import this module from production code. See
docs/superpowers/plans/2026-04-10-scheduler-rewrite/08-retire-cpsat.md
for the retirement rationale and the scheduler rewrite overview.
"""
```

- [ ] **Step 2: Commit + Gate D.**

## Task T7 — Remove the CPSAT sidebar UI (if any)

Audit `app/templates/auto_schedule_review.html` and any admin UI that exposed the CPSAT-vs-greedy toggle. Remove the UI controls.

- [ ] **Step 1: Grep for CPSAT_ENABLED or "CP-SAT" in templates.**

```bash
grep -rn "CPSAT\|CP-SAT\|cpsat" app/templates/ 2>&1
```

- [ ] **Step 2: Remove any UI references. If any template was showing the flag, delete that section.**

- [ ] **Step 3: Run template tests to ensure no regression.**

- [ ] **Step 4: Commit + Gate D.**

## Post-flight

- [ ] **Gate C:** trivially passes (no spec branches).
- [ ] **Gate E:** the single conformance test `test_cpsat_not_invoked_by_production_route` adequately verifies the retirement.
- [ ] Open PR: `plan 08: retire CP-SAT from production path`.
- [ ] **Smoke test:** run `python wsgi.py` and manually trigger an auto-schedule run via the UI. Verify it succeeds and uses the greedy engine (check the `solver_type` column in SchedulerRunHistory).
