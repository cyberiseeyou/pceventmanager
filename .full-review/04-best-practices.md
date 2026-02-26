# Phase 4: Best Practices & Standards

## Framework & Language Findings

### Critical

**BP-CRT-01: `NameError` in `validation_summary_api` — missing `get_models()` call**
- File: `app/routes/dashboard.py` line 540
- References `models['Event']` without calling `get_models()` first. Runtime crash on every request.

**BP-CRT-02: Missing authentication on all dashboard mutation endpoints**
- File: `app/routes/dashboard.py`
- `fix_wizard_apply`, `fix_wizard_skip`, `assign_supervisor_event` perform writes without `@require_authentication()`.

**BP-CRT-03: No input validation on `fix_wizard_apply` action type**
- File: `app/routes/dashboard.py` line 1140
- `action_type` from request JSON passed directly to service without enum validation.

### High

**BP-HGH-01: Repeated indicator BoolVar construction — code duplication (~30 times)**
- File: `app/services/cpsat_scheduler.py`
- Same 7-line pattern copy-pasted across 8 constraint methods. Extract `_make_emp_day_indicator()` helper.

**BP-HGH-02: `isinstance(svar, int)` guard for CP-SAT constants is fragile**
- File: `app/services/cpsat_scheduler.py`
- `model.NewConstant(0)` returns `IntVar`, not Python `int`. Use a separate `_unschedulable_events` set.

**BP-HGH-03: Duplicate model dict construction in dashboard Fix Wizard routes (3x)**
- File: `app/routes/dashboard.py`
- Extract helper or pass `get_models()` output directly to FixWizardService.

**BP-HGH-04: `auto_scheduler.py:run_scheduler` uses `current_app.config` instead of `get_models()`**
- File: `app/routes/auto_scheduler.py` line 86
- Violates the documented model factory pattern. Other routes in same file use `get_models()` correctly.

**BP-HGH-05: N+1 queries in `_load_existing_schedules`**
- File: `app/services/cpsat_scheduler.py` line 473
- Per-schedule event lookup inside loop. Pre-load events into lookup dict.

### Medium

**BP-MED-01**: Deprecated `Session.query(Model).get(id)` — use `Session.get(Model, id)` (SQLAlchemy 2.0)
**BP-MED-02**: `ConstraintModifier` uses `get_models()` at constructor time — should accept DI params
**BP-MED-03**: Bare `except:` in `database_refresh_service.py` line 359 — use `except Exception:`
**BP-MED-04**: `ai_assistant.py` indentation inconsistency (5-space in `confirm_action`)
**BP-MED-05**: `fix-wizard.js` uses `var` exclusively — rest of codebase uses `let`/`const`
**BP-MED-06**: `showError` function defined twice in `fix-wizard.js`
**BP-MED-07**: AI tools `get_tool_schemas()` returns 900-line inline dict — extract to data module
**BP-MED-08**: Missing `match/case` opportunity in `fix_wizard.py:apply_fix` (Python 3.10+)
**BP-MED-09**: `_check_already_scheduled` bypasses cached `_get_active_run_ids()` method
**BP-MED-10**: No type hints on `FixWizardService._apply_*` methods

### Low

**BP-LOW-01**: `to_local_time` regex could strip intentional leading zeros in edge cases
**BP-LOW-02**: `_compute_pairings` mutates `self.events` list in-place during setup
**BP-LOW-03**: Template ARIA improvements incomplete — missing `aria-labelledby` on modals
**BP-LOW-04**: `daily-view.js` CSRF fix correct but audit should confirm no other files use old header
**BP-LOW-05**: `ai_assistant.py` provider selection could use strategy pattern
**BP-LOW-06**: `test_validator.py:_next_weekday` helper should be shared fixture in `conftest.py`

---

## CI/CD & DevOps Findings

### Critical

**OPS-CRT-01: Production database (`instance/scheduler.db`) tracked in git**
- 2.8MB binary with employee PII. Not in `.gitignore`. Must be untracked immediately.

**OPS-CRT-02: Dashboard, API, and scheduling routes lack authentication (systemic)**
- `dashboard.py`: All 15 routes unprotected
- `api.py`: ~21 of 30+ routes unprotected (including POST/DELETE)
- `scheduling.py`: All 5 routes unprotected (`require_authentication` imported but never used)

### High

**OPS-HGH-01**: No deployment stage in CI (only test + lint, no CD)
**OPS-HGH-02**: No security scanning (no Dependabot, Bandit, pip-audit, Trivy)
**OPS-HGH-03**: No blue-green or canary deployment — single container, manual deploys
**OPS-HGH-04**: Single gunicorn worker — CP-SAT solver blocks all requests for 15s+
**OPS-HGH-05**: Nginx SSL not configured (commented out); relies on Cloudflare
**OPS-HGH-06**: No log rotation — `FileHandler` grows unbounded
**OPS-HGH-07**: No external monitoring or alerting (no Sentry, Prometheus, PagerDuty)
**OPS-HGH-08**: Weak production `SECRET_KEY` default — validation not auto-run
**OPS-HGH-09**: MCP server (`.mcp.json`) points at production database with full write access
**OPS-HGH-10**: Handcrafted migration revision IDs (non-Alembic hashes)
**OPS-HGH-11**: No automated backup schedule — manual-only `./backup_now.sh`
**OPS-HGH-12**: SQLite with bind mount shared by app + Celery containers (corruption risk)
**OPS-HGH-13**: No migration testing in CI pipeline

### Medium

**OPS-MED-01**: CI skips 51 ML tests without substitute/tracking job
**OPS-MED-02**: JS lint job swallows all errors with `|| true`
**OPS-MED-03**: Two conflicting docker-compose production configs (SQLite vs PostgreSQL)
**OPS-MED-04**: Health endpoint exposes Python version, PID, memory, disk without auth
**OPS-MED-05**: No rollback procedure documented or automated
**OPS-MED-06**: Mixed dependency pinning (exact vs `>=`) in `requirements.txt`
**OPS-MED-07**: No backup restoration testing

### Low

**OPS-LOW-01**: Python version mismatch (CI: 3.11, local: 3.12)
**OPS-LOW-02**: Duplicate Dockerfiles (root and `deployment/docker/`)
**OPS-LOW-03**: Hardcoded credentials in dev docker-compose
**OPS-LOW-04**: 7-day backup retention may be insufficient
**OPS-LOW-05**: Testing dependencies in production `requirements.txt`
