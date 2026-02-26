# Review Scope

## Target

All uncommitted changes in the flask-schedule-webapp repository — includes code review remediation fixes, ML test repairs, new features (CP-SAT scheduler, fix wizard, constraint modifier, AI tools), CSRF security fixes, and scheduling engine improvements.

## Files — Modified (27 production + test files)

### Production Code
- `app/__init__.py` — localtime filter registration
- `app/ai/prompts/templates.py` — AI prompt templates
- `app/ml/inference/ml_scheduler_adapter.py` — ML adapter fallback logic fixes
- `app/models/schedule.py` — Boolean column defaults
- `app/routes/api.py` — REST API changes
- `app/routes/auto_scheduler.py` — Auto-scheduler route refactor
- `app/routes/dashboard.py` — Dashboard validation routes
- `app/routes/scheduling.py` — Schedule management
- `app/services/ai_assistant.py` — AI assistant service
- `app/services/ai_tools.py` — AI tool definitions (+723 lines)
- `app/services/constraint_validator.py` — Business rule validation
- `app/services/cpsat_scheduler.py` — CP-SAT constraint solver (+622 lines)
- `app/services/database_refresh_service.py` — Database refresh ops
- `app/services/scheduling_engine.py` — Core scheduling logic, date validation fix
- `app/services/validation_types.py` — Validation type definitions
- `app/static/js/components/ai-assistant.js` — AI panel JS, aria-hidden fix
- `app/static/js/pages/daily-view.js` — CSRF header standardization
- `app/templates/auto_scheduler_main.html` — CSRF header fix
- `app/templates/components/ai_panel.html` — AI panel template
- `app/templates/dashboard/weekly_validation.html` — Dialog role/aria fixes
- `app/templates/scheduler_history.html` — Scheduler history template

### New Files
- `app/services/constraint_modifier.py` — Runtime constraint adjustments
- `app/services/fix_wizard.py` — Guided schedule issue resolution
- `app/static/js/pages/fix-wizard.js` — Fix wizard UI (CSRF + error handling)
- `app/templates/dashboard/fix_wizard.html` — Fix wizard template
- `app/utils/timezone.py` — Timezone utility (configurable, cached)
- `migrations/versions/6a96501dd084_add_schedule_outcomes.py` — Migration

### Tests
- `tests/test_ml_effectiveness.py` — ML effectiveness tests (schema fixes)
- `tests/test_ml_functional.py` — ML functional tests (schema fixes)
- `tests/test_ml_performance.py` — ML performance tests (schema fixes)
- `tests/test_ml_safety.py` — ML safety tests (schema fixes)
- `tests/test_ml_shadow_mode.py` — ML shadow mode tests (schema fixes)
- `tests/test_validator.py` — Validator tests
- `tests/test_cancelled_events.py` — Cancelled events tests (new)
- `tests/test_cpsat_double_booking.py` — CP-SAT double booking tests (new)
- `tests/test_fix_wizard.py` — Fix wizard tests (new)

### Config
- `CLAUDE.md` — Project instructions update
- `.mcp.json` — MCP server configuration (new)

## Flags

- Security Focus: no
- Performance Critical: no
- Strict Mode: no
- Framework: Flask/SQLAlchemy/Jinja2 (auto-detected)

## Review Phases

1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report
