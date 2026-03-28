# Phase 2: Security & Performance Review

## Security Findings

### Critical

**SEC-CRT-01: Fix Wizard Routes Missing Authentication (CVSS 9.1)**
- CWE-306 / OWASP A01:2021 — Broken Access Control
- File: `app/routes/dashboard.py` lines 1028-1195
- Four Fix Wizard routes (`fix_wizard`, `fix_wizard_issues`, `fix_wizard_apply`, `fix_wizard_skip`) lack `@require_authentication()`. POST endpoints can modify/delete schedules without auth.
- Systemic: The entire dashboard blueprint appears to lack auth decorators.
- Fix: Add `@require_authentication()` to all Fix Wizard routes, or apply `@dashboard_bp.before_request`.

**SEC-CRT-02: AI `_confirmed` Flag Bypass via LLM Injection (CVSS 8.6)**
- CWE-807 / OWASP A01:2021 — Reliance on Untrusted Inputs in Security Decision
- File: `app/services/ai_assistant.py` lines 534-543; `app/services/ai_tools.py` 12+ locations
- `_confirmed` flag lives inside `args` dict, which is LLM-generated. Prompt injection can set `_confirmed: true` to bypass confirmation on destructive ops (remove_schedule, bulk_reschedule, swap_schedules, etc.).
- Fix: Strip `_confirmed` from args; pass `confirmed` as separate server-side parameter.

**SEC-CRT-03: `CONDITION_CANCELED` String-as-Iterable in `.in_()` (CVSS 7.5)**
- CWE-704 / OWASP A04:2021 — Incorrect Type Conversion
- File: `app/services/ai_tools.py` line 4030
- `CONDITION_CANCELED` is a string `'Canceled'`, not a tuple. `.in_()` iterates characters → `IN ('C','a','n','c','e','l','e','d')`. Canceled events are never actually filtered, producing incorrect schedule improvement suggestions.
- Fix: Use `INACTIVE_CONDITIONS` tuple instead.

**SEC-CRT-04: Fix Wizard `apply_fix` Accepts Arbitrary Targets Without Validation (CVSS 8.1)**
- CWE-20 / OWASP A03:2021 — Improper Input Validation
- File: `app/routes/dashboard.py` lines 1109-1155; `app/services/fix_wizard.py` lines 666-693
- `action_type` and `target` dict passed through from JSON body without validation. Combined with CRT-01, allows unauthenticated modification of any schedule.
- Fix: Allowlist `action_type` values, validate `target` fields per action type.

### High

**SEC-HGH-01: Auto-Scheduler Routes Missing Authentication (CVSS 7.5)**
- File: `app/routes/auto_scheduler.py`
- Many state-changing routes lack `@require_authentication()`: `POST /auto-schedule/run`, `POST /auto-schedule/approve`, `DELETE /auto-schedule/api/pending/by-ref/<ref>`, etc.
- Fix: Apply `@auto_scheduler_bp.before_request` guard.

**SEC-HGH-02: `completion_notes` Stored Without Sanitization — Stored XSS Risk (CVSS 7.2)**
- CWE-79 / OWASP A03:2021
- File: `app/services/ai_tools.py` line 3885
- New `completion_notes` field accepts arbitrary text from LLM args. If rendered with `|safe`, creates stored XSS.
- Fix: Sanitize, limit length (500 chars), ensure template auto-escaping.

**SEC-HGH-03: Production Database (`scheduler.db`) in Uncommitted Changes (CVSS 6.5)**
- CWE-200 / OWASP A01:2021
- File: `instance/scheduler.db` (changed from 1.4MB to 2.8MB)
- Contains employee schedules, names, time-off records. Should never be committed.
- Fix: Discard with `git checkout -- instance/scheduler.db`.

**SEC-HGH-04: Savepoint-Based Dry Run May Leak Side Effects (CVSS 6.8)**
- CWE-662
- File: `app/services/ai_tools.py` lines 3755-3792 (`_tool_compare_schedulers`)
- Runs schedulers inside SQLAlchemy savepoints then rolls back. SQLite savepoints may not isolate correctly; autoflush before rollback could persist partial state.
- Fix: Use separate session or `dry_run=True` flag.

**SEC-HGH-05: Fix Wizard `_apply_reschedule` Accepts Arbitrary Datetime (CVSS 6.5)**
- CWE-20
- File: `app/services/fix_wizard.py` lines 764-783
- `new_datetime` set directly without validating event period, past dates, or business hours.
- Fix: Validate against event period and `date.today()`.

### Medium

**SEC-MED-01**: CSRF protection gap on dashboard POST endpoints (CVSS 5.4)
**SEC-MED-02**: Supervisor event approval bypasses period validation (CVSS 5.3)
**SEC-MED-03**: `_apply_reassign` TOCTOU race — no re-validation before commit (CVSS 5.0)
**SEC-MED-04**: AI confirmation data round-trips through browser unverified (CVSS 5.3)
**SEC-MED-05**: Raw exception messages exposed in API responses (CVSS 4.3)
**SEC-MED-06**: CDN SRI hash potentially incorrect in fix_wizard.html (CVSS 4.0)

### Low

**SEC-LOW-01**: `showError` defined twice in fix-wizard.js (dead code)
**SEC-LOW-02**: `_parse_direction` defaults to 1.5x multiplier on unknown input
**SEC-LOW-03**: Migration missing `server_default` that model defines

---

## Performance Findings

### Critical

**PERF-CRT-01: N+1 Query in `_load_existing_schedules` — O(S) Individual Queries**
- File: `app/services/cpsat_scheduler.py` lines 456-480
- Per-schedule `Event.query.filter_by(project_ref_num=...).first()` inside loop. 200 schedules = 200 round-trips (~400ms).
- Fix: Pre-load all events into lookup dict with single query.

**PERF-CRT-02: Redundant Indicator BoolVars Across CP-SAT Constraints — 50K-100K Variables**
- File: `app/services/cpsat_scheduler.py` lines 944-1000
- `_add_weekly_hours_cap` creates O(E x D x W) BoolVars per employee. Same pattern in 6+ constraint methods creates identical (event, emp, day) indicators independently.
- With 15 employees, 3 weeks, 80 events: ~18K vars per constraint method, 50K-100K total.
- Fix: Create shared indicator variables once in `_build_model()`, reuse across all constraints.

**PERF-CRT-03: O(N*M) ML Affinity Scoring — 5-15 Seconds with ML Enabled**
- File: `app/services/cpsat_scheduler.py` lines 184-218
- `_get_ml_affinity_scores()` calls `adapter.rank_employees()` per event, each extracting features from DB. 80 events x 15 employees = 80 external calls.
- Fix: Batch feature extraction and vectorized scoring.

### High

**PERF-HGH-01**: O(N^2) post-solve cross-run conflict check (`_post_solve_review`)
**PERF-HGH-02**: `get_models()` called inside approval loop (auto_scheduler.py line 860)
**PERF-HGH-03**: Unbounded `.query.all()` loads entire tables (time-off, exceptions, locked days)
**PERF-HGH-04**: N+1 event type resolution in `_post_solve_review` (~80 individual queries)
**PERF-HGH-05**: Fix Wizard `_options_for_reassign` creates ConstraintValidator per issue

### Medium

**PERF-MED-01**: Database refresh schedule preservation queries inside loop
**PERF-MED-02**: Database refresh restoration loop queries per item
**PERF-MED-03**: AI tools `_find_employee_fuzzy` loads all employees per call
**PERF-MED-04**: `_valid_days_for_event` called 8+ times per event (not memoized)
**PERF-MED-05**: Fix Wizard generates all issues upfront (no pagination)
**PERF-MED-06**: AI Tools module 4,344 lines — 40 schemas rebuilt per request
**PERF-MED-07**: `_compute_eligibility` nested O(E x M) loop
**PERF-MED-08**: Fix Wizard re-renders entire DOM on each issue transition

### Low

**PERF-LOW-01**: `to_local_time` regex not pre-compiled
**PERF-LOW-02**: `ConstraintModifier.__init__` calls `get_models()`/`get_db()` per instantiation
**PERF-LOW-03**: New Schedule model columns lack database indexes
**PERF-LOW-04**: Approval workflow commits per-schedule instead of batch

### Concurrency

**PERF-CONC-01**: CP-SAT `num_workers=4` may starve request threads under gunicorn
**PERF-CONC-02**: `ConstraintModifier.clear_all_preferences()` no transaction safety

---

## Critical Issues for Phase 3 Context

Testing requirements driven by Phase 2:
1. **Authentication tests**: Verify unauthenticated requests to Fix Wizard and auto-scheduler return 401/302
2. **CSRF tests**: Verify POST requests without CSRF tokens are rejected
3. **Input validation tests**: Test Fix Wizard with invalid action_type, non-existent schedule_id, past datetime, XSS payloads
4. **AI confirmation bypass test**: Verify `_confirmed: true` in LLM-generated args is stripped
5. **`.in_()` bug test**: Unit test `_tool_suggest_schedule_improvement` with canceled events
6. **N+1 regression tests**: Measure query count for CP-SAT data loading
