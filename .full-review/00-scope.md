# Review Scope

## Target

Full codebase review of the Flask Schedule Webapp — an employee scheduling system for Crossmark with auto-scheduler, AI assistant, and external integrations (Walmart EDR, MVRetail). Focused on **inconsistencies, code smells, privacy concerns, and performance opportunities**.

## Files

### Python Backend (145 files)
- `app/__init__.py`, `app/config.py`, `app/constants.py`, `app/extensions.py`
- `app/models/` — 17 model files (Employee, Event, Schedule, etc.)
- `app/routes/` — 34 route files (api.py, auth.py, auto_scheduler.py, etc.)
- `app/services/` — 35 service files (scheduling_engine.py, cpsat_scheduler.py, etc.)
- `app/integrations/` — External API (session_api_service.py, sync_engine.py), Walmart EDR, EDR
- `app/ai/` — AI assistant (Ollama provider, RAG context, chat service)
- `app/ml/` — ML scheduling (feature engineering, employee ranker, training)
- `app/error_handlers/`, `app/utils/`

### JavaScript Frontend (51 files)
- `app/static/js/main.js`, `app/static/js/login.js`
- `app/static/js/pages/` — Page-specific JS (daily-view, index-page, fix-wizard, etc.)
- `app/static/js/components/` — Reusable components (modals, AI chat, push-prompt, etc.)
- `app/static/js/modules/` — Shared modules (state-manager, toast-notifications, etc.)
- `app/static/js/utils/` — Utilities (api-client.js)

### Templates (77 files)
- `app/templates/` — Jinja2 templates (base.html, index.html, daily_view.html, etc.)
- `app/templates/components/` — Reusable template components
- `app/templates/dashboard/` — Dashboard pages
- `app/templates/help/` — Help pages

### CSS (31 files)
- `app/static/css/` — Stylesheets (style.css, design-tokens.css, responsive.css, etc.)
- `app/static/css/pages/` — Page-specific styles
- `app/static/css/components/` — Component styles

### Total: ~167,352 lines of code

## Flags

- Security Focus: yes (privacy concerns explicitly requested)
- Performance Critical: yes (performance opportunities explicitly requested)
- Strict Mode: no
- Framework: Flask 2.0+ / SQLAlchemy / Jinja2 / PostgreSQL/SQLite

## Review Phases

1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report
