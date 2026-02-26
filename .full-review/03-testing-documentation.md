# Phase 3: Testing & Documentation Review

## Test Coverage Findings

### Critical

**TST-CRT-01: Zero tests for ConstraintModifier service (280 lines)**
- File: `app/services/constraint_modifier.py`
- No coverage for `apply_preference()`, `get_multipliers()`, `clear_preference()`, `_match_preference()`, `_parse_direction()`.

**TST-CRT-02: Zero tests for AI Tools (4,100+ lines, 37 tools)**
- File: `app/services/ai_tools.py`
- No unit tests for any tool function. Write tools that modify DB state are completely untested.

**TST-CRT-03: Zero tests for AI Assistant (560 lines)**
- File: `app/services/ai_assistant.py`
- `confirm_action()` sets `_confirmed=True` from untrusted `confirmation_data` — no test validates this is secure.

**TST-CRT-04: No authentication tests for Fix Wizard or auto-scheduler routes**
- Fix Wizard: 4 routes with no `@require_authentication()`, zero tests verify auth requirement
- Auto-scheduler: `run_scheduler()` POST has no auth, zero tests verify

**TST-CRT-05: `.in_(CONDITION_CANCELED)` bug has no regression test**
- `ai_tools.py` line 4030 iterates string characters. No test catches this.

**TST-CRT-06: `_confirmed` bypass has no test**
- LLM can inject `_confirmed: true` into tool args. No test verifies stripping.

### High

**TST-HGH-01**: CP-SAT Supervisor pairing (`_compute_pairings`) — zero tests
**TST-HGH-02**: `_get_effective_weight()` with user preference multipliers — zero tests
**TST-HGH-03**: Fix Wizard `_apply_assign_supervisor()` — creates Schedule records, untested
**TST-HGH-04**: Fix Wizard `_apply_unschedule()` paired Supervisor cascade — untested
**TST-HGH-05**: Constraint validator `_check_time_off()`, `_check_weekly_limit()`, `_check_already_scheduled()` — untested
**TST-HGH-06**: `get_available_employees()` used by Fix Wizard and AI tools — untested
**TST-HGH-07**: N+1 query regression in `_load_existing_schedules()` — no query count test
**TST-HGH-08**: `_parse_date()` and `_find_employee()` fuzzy matching — untested
**TST-HGH-09**: Silent assertion patterns in `test_cancelled_events.py` — `if cancelled:` guard silently passes when event not found

### Medium

**TST-MED-01**: CP-SAT soft constraints (S1-S15) objective weights — zero tests
**TST-MED-02**: Fix Wizard option generators (5 of 7 untested): `_options_for_core_limit`, `_options_for_supervisor_pairing`, `_options_for_juicer_core_conflict`, `_options_for_weekly_limit`, `_options_for_duplicate_product`
**TST-MED-03**: Fix Wizard input validation — invalid action_type, non-existent schedule_id, past datetime
**TST-MED-04**: Timezone utility (`to_local_time`) — zero tests
**TST-MED-05**: CP-SAT event type override handling — untested
**TST-MED-06**: CP-SAT locked days, company holidays — untested
**TST-MED-07**: `_extract_product_key()` parsing — untested

### Test Quality Assessment

| Level | Count | % | Health |
|-------|-------|---|--------|
| Unit (no DB) | ~15 | 8% | LOW |
| Integration (service + DB) | ~130 | 72% | MODERATE |
| Route/API | ~35 | 20% | LOW |
| E2E | 0 | 0% | MISSING |

Test pyramid is inverted — almost all tests require a database.

---

## Documentation Findings

### Critical

**DOC-CRT-01: `docs/CODEBASE_MAP.md` has zero references to any new files**
- Last updated 2026-02-09. Missing: `cpsat_scheduler.py` (2,157 lines), `fix_wizard.py` (923 lines), `constraint_modifier.py` (282 lines), `timezone.py`, all new templates/JS/tests.
- Also missing: CP-SAT data flow diagram, Schedule outcome columns.

### High

**DOC-HGH-01**: `CLAUDE.md` API Endpoints section missing Fix Wizard and Dashboard validation endpoints (8+ undocumented routes)
**DOC-HGH-02**: `docs/scheduling_validation_rules.md` missing 5 CP-SAT hard constraints (H18, H20, H22-H24)
**DOC-HGH-03**: No changelog entries for CP-SAT scheduler, Fix Wizard, AI tools expansion, or schema changes
**DOC-HGH-04**: `CONTRIBUTING.md` line 58 references wrong JS filename (`api.js` instead of `api-client.js`)

### Medium

**DOC-MED-01**: `CLAUDE.md` Key Files table missing `ai_tools.py`, `validation_types.py`, `timezone.py`
**DOC-MED-02**: `CLAUDE.md` Change Ripple Effects missing CP-SAT and Fix Wizard dependencies
**DOC-MED-03**: No documentation of runtime constraint modifier system in business rules doc
**DOC-MED-04**: AI Tools confirmation workflow not documented in code or tool schemas
**DOC-MED-05**: New migration not documented in any changelog
**DOC-MED-06**: No top-level `README.md` exists (CLAUDE.md serves as primary docs)
**DOC-MED-07**: Schedule model outcome columns undocumented in CODEBASE_MAP

### Low

**DOC-LOW-01**: Fix Wizard dispatcher mapping not cross-referenced to validation rule sources
**DOC-LOW-02**: `_post_solve_review` defense-in-depth rationale not fully explained in docstring
**DOC-LOW-03**: CODEBASE_MAP Navigation Guide missing Fix Wizard task entry
**DOC-LOW-04**: Migration nullable defaults inconsistent with model `server_default`

### Positive Observations

- CP-SAT scheduler has excellent inline documentation (constraint IDs H2-H24, S1-S15, weight comments)
- Constraint Modifier has well-structured self-documenting dictionaries
- Fix Wizard dataclasses and enums provide clear API contract
