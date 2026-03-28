# Phase 1: Code Quality & Architecture Review

## Code Quality Findings

### Critical

**CRT-01: `_tool_verify_schedule` defined but missing from `tool_map` (Dead Code)**
- File: `app/services/ai_tools.py` ~line 980 (definition) vs ~line 911 (tool_map)
- The method is fully implemented (~100 lines) but never wired into the dispatcher. AI assistant cannot invoke this tool.
- Fix: Add `'verify_schedule': self._tool_verify_schedule` to `tool_map`.

**CRT-02: Migration missing `server_default` that model defines**
- File: `app/models/schedule.py` lines 37-39 vs `migrations/versions/6a96501dd084_add_schedule_outcomes.py`
- Model declares `server_default=sa.text('0')` for `was_completed`/`was_swapped`/`was_no_show`, but migration adds columns as `nullable=True` with no `server_default`. Existing rows will have NULL instead of False/0. Queries like `Schedule.was_completed == False` will miss NULLs.
- Fix: Add `server_default=sa.text('0')` to the migration's `add_column` calls.

**CRT-03: Fix Wizard routes lack authentication**
- File: `app/routes/dashboard.py` lines 1069-1165
- None of the 4 Fix Wizard routes (`fix_wizard`, `fix_wizard_issues`, `fix_wizard_apply`, `fix_wizard_skip`) have `@require_authentication()` decorator. The apply endpoint accepts `action_type` and `target` from JSON body and can modify schedules.
- Fix: Add `@require_authentication()` to all Fix Wizard routes.

### High

**HGH-01: `showError()` defined twice in fix-wizard.js**
- File: `app/static/js/pages/fix-wizard.js` lines 35 and 325
- Second definition silently overrides the first due to JS hoisting. The first (transient alert) is the one intended for apply/skip operations but is unreachable.
- Fix: Rename second function to `showFatalError` or `showBlockingError`.

**HGH-02: Duplicate model dict construction repeated 5 times in dashboard.py**
- File: `app/routes/dashboard.py` lines ~1069-1080, 1122-1132, 1173-1179
- Every Fix Wizard endpoint builds nearly identical models dict. Maintenance risk.
- Fix: Extract `_get_fix_wizard_models()` helper function.

**HGH-03: `_check_past_date` uses `date.today()` which is timezone-naive**
- File: `app/services/constraint_validator.py` lines 473-484
- Server-local time used, but scheduling operates in `America/Indiana/Indianapolis`. Production servers in UTC could reject valid evening scheduling.
- Fix: Use `datetime.now(local_tz).date()` from the configured timezone.

**HGH-04: `_confirmed` flag can be injected by untrusted AI model output**
- File: `app/services/ai_assistant.py` lines 538-541, `app/services/ai_tools.py` multiple
- The `_confirmed` key is checked via `args.get('_confirmed', False)`. If the LLM generates a function_call with `_confirmed: true`, it bypasses confirmation.
- Fix: Strip `_confirmed` from `tool_args` before dispatch; pass `confirmed` as a separate parameter.

**HGH-05: CP-SAT `_add_weekly_hours_cap` creates O(E x D) boolean variables per employee-week**
- File: `app/services/cpsat_scheduler.py` weekly hours constraint
- Creates BoolVar for every (event, employee, week, day) combination even when remaining <= 0. Hundreds of unnecessary variables.
- Fix: Skip variable creation for invalid combinations; use `AddImplication` with existing variables.

**HGH-06: `to_local_time` regex strips leading zeros from minutes**
- File: `app/utils/timezone.py` line 37
- `re.sub(r'\b0(\d)', r'\1', formatted)` matches `:06` → `:6` in times like `10:06 PM`.
- Fix: Use `%-m/%-d/%-I` format codes (Linux) or make regex target-specific.

### Medium

**MED-01: FixWizardService._apply_unschedule uses old 6-digit regex for Supervisor pairing**
- File: `app/services/fix_wizard.py` lines 744-759
- CP-SAT uses improved 9-12 digit pattern; Fix Wizard still uses `r'\d{6}'`. False positive risk.

**MED-02: `ConstraintModifier` creates `get_models()`/`get_db()` in `__init__`**
- File: `app/services/constraint_modifier.py` lines 81-84
- Should accept db_session/models as constructor parameters for testability and consistency.

**MED-03: `_get_ml_affinity_scores` iterates all events x employees — O(N*M) database queries**
- File: `app/services/cpsat_scheduler.py`
- 50 events x 15 employees = 50 ML inference round-trips before solver starts.

**MED-04: Auto-scheduler approval creates Schedule inside loop without batch commit**
- File: `app/routes/auto_scheduler.py`
- If supervisor auto-scheduling exception occurs, Core schedule is created but Supervisor failure is only logged. No flush between iterations.

**MED-05: `database_refresh_service` schedule restoration doesn't check employee validity**
- File: `app/services/database_refresh_service.py`
- Restored schedule could reference inactive/deleted employee.

**MED-06: `_post_solve_review` cross-run conflict check is O(N^2)**
- File: `app/services/cpsat_scheduler.py`
- Manageable for typical 30-40 Core events but could be O(N) with pre-grouped data.

**MED-07: AI tools `_tool_list_employees` has TODO for `available_on` that silently passes**
- File: `app/services/ai_tools.py` lines 1521-1525
- Parses date but does nothing. User gets unfiltered results with no indication filter was ignored.

**MED-08: `get_models()` called inside approval loop**
- File: `app/routes/auto_scheduler.py`
- Should be called once before the loop.

### Low

**LOW-01: `ai_assistant.py` indentation inconsistency in `confirm_action`**
**LOW-02: `fix_wizard.html` loads Font Awesome when base template likely already includes it**
**LOW-03: CP-SAT `_log_solution_explanations` output is never stored**
**LOW-04: `validation_failed` status renamed to `api_failed` without migration of existing data**
**LOW-05: `_apply_reschedule` lacks constraint validation before updating datetime**
**LOW-06: Scheduling engine past-date checks duplicate constraint validator logic**

---

## Architecture Findings

### Critical

**ARCH-CRT-01: `CONDITION_CANCELED` used as iterable in `.in_()` — runtime bug**
- File: `app/services/ai_tools.py` ~line 4030 in `_tool_suggest_schedule_improvement`
- `CONDITION_CANCELED` is a string `'Canceled'`, not a tuple. Passing to `.in_()` iterates characters → `IN ('C','a','n','c','e','l','e','d')`.
- Fix: Change to `~Event.condition.in_(INACTIVE_CONDITIONS)`.

### High

**ARCH-HGH-01: Fix Wizard imports route-level private function — inverts dependency direction**
- File: `app/services/fix_wizard.py` line 228 imports `from app.routes.api_suggest_employees import _score_employee`
- Services consumed by routes, not the other way around. Private function (underscore prefix) from route module.
- Fix: Extract `_score_employee` into a shared service module.

**ARCH-HGH-02: CP-SAT AI tool ignores date range arguments**
- File: `app/services/ai_tools.py` `_tool_run_cpsat_scheduler`
- Parses `start_date`/`end_date` from args but never passes them to engine. Tool description misleads AI.
- Fix: Either pass dates to engine or update tool description.

**ARCH-HGH-03: Schedule model columns migration has handcrafted revision ID**
- File: `migrations/versions/6a96501dd084_add_schedule_outcomes.py`
- Revision ID was manually replaced. Verify `down_revision` matches current head and test against `scheduler_test.db`.

### Medium

**ARCH-MED-01: Inconsistent string vs enum for `action_type` across endpoints**
- File: `app/services/fix_wizard.py` / `app/routes/dashboard.py`
- One endpoint sends raw string, another sends enum. Works due to `str, Enum` but unclear API contract.

**ARCH-MED-02: Supervisor validation bypass without fallback check**
- File: `app/routes/auto_scheduler.py`
- Completely bypasses period validation for Supervisor events. Invalid Supervisor schedules silently accepted.
- Fix: Validate Supervisor schedule matches a scheduled Core event's date.

**ARCH-MED-03: Date comparison relaxation changes safety semantics**
- File: `app/services/scheduling_engine.py` line 3499
- Changed from datetime to date-only comparison. Event with `due_datetime = 2026-02-18 08:00` accepts schedule at `17:00`.
- Fix: Document why date-only is correct for this domain.

---

## Critical Issues for Phase 2 Context

Security-relevant for Phase 2:
1. **CRT-03**: Fix Wizard routes lack authentication — anyone can modify schedules
2. **HGH-04**: AI `_confirmed` flag injection — LLM can bypass confirmation for destructive ops
3. **ARCH-CRT-01**: `CONDITION_CANCELED` string-as-iterable — data filtering bug in AI tools

Performance-relevant for Phase 2:
1. **HGH-05**: CP-SAT variable explosion in weekly hours cap
2. **MED-03**: O(N*M) ML affinity scoring
3. **MED-06**: O(N^2) post-solve review

---

## Positive Observations

1. **Model factory pattern compliance**: 100% across all new code — no direct model imports
2. **CP-SAT post-solve review**: Excellent defense-in-depth for constraint validation
3. **Database refresh schedule preservation**: Well-designed reconciliation pattern
4. **CSRF header standardization**: Consistent `X-CSRF-Token` across all new/modified JS
5. **Fix Wizard architecture**: Clean separation with dataclasses, enums, and dispatcher pattern
6. **Escalating penalty encoding**: Mathematically clean CP-SAT soft constraint implementation
7. **Supervisor event bypass comment**: Good domain-specific documentation preventing future "fixes"
8. **Defense-in-depth past-date validation**: Enforced across 3 independent layers
