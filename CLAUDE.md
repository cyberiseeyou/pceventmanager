# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask Schedule Webapp is an employee scheduling system for Crossmark that manages event scheduling, employee availability, and integrates with external systems (Walmart Retail Link EDR, MVRetail API). It features an auto-scheduler, AI assistant, and PDF report generation.

## Commands

### Development
```bash
# Run development server
python wsgi.py

# Run with Flask debug mode
FLASK_ENV=development python wsgi.py
```

### Production
```bash
# Run with Gunicorn
gunicorn --config gunicorn_config.py wsgi:app

# Run Celery worker (for background tasks)
celery -A celery_worker:celery_app worker --loglevel=info
```

### Database
```bash
# Initialize/upgrade database
flask db upgrade

# Create new migration
flask db migrate -m "description"

# Downgrade one version
flask db downgrade
```

### Testing
```bash
pytest
pytest -v                    # verbose
pytest --cov=app             # with coverage
pytest tests/test_file.py    # single file
```

## Architecture

### Application Factory Pattern
- Entry point: `wsgi.py` creates app via `app/__init__.py:create_app()`
- Configuration: `app/config.py` with DevelopmentConfig, TestingConfig, ProductionConfig
- Extensions initialized in `app/extensions.py` (db, migrate, csrf, limiter)

### Model Factory Pattern
Models use factory functions in `app/models/` that accept `db` instance:
```python
from app.models import init_models
models = init_models(db)
Employee = models['Employee']
```

Access models via registry (`app/models/registry.py`):
```python
from app.models import get_models, get_db
models = get_models()
db = get_db()
```

Key models: Employee, Event, Schedule, EmployeeAvailability, EmployeeTimeOff, RotationAssignment, PendingSchedule, SystemSetting

### Core Services (`app/services/`)
- `SchedulingEngine` - Auto-scheduler orchestrator, handles event prioritization and assignment
- `RotationManager` - Manages employee rotation assignments (Juicer, Digital)
- `ConstraintValidator` - Validates scheduling constraints (availability, time-off, max shifts)
- `ConflictResolver` - Resolves scheduling conflicts with swap proposals

### Route Blueprints (`app/routes/`)
- `main_bp` - Main views
- `scheduling_bp` - Schedule management
- `employees_bp` - Employee CRUD
- `api_bp` - REST API endpoints
- `auto_scheduler_bp` - Auto-scheduling interface
- `admin_bp` - Admin functions
- `ai_bp`, `ai_rag_bp` - AI assistant endpoints
- `walmart_bp` - Walmart EDR integration

### Integrations (`app/integrations/`)
- `walmart_api/` - Walmart Retail Link EDR retrieval with MFA session management
- `external_api/` - MVRetail sync engine and session API
- `edr/` - EDR report generation and PDF creation

### AI Module (`app/ai/`)
RAG-based AI assistant using local Ollama or cloud providers:
- `providers/` - LLM provider implementations (Ollama, etc.)
- `context/` - Context retrieval and classification
- `services/chat.py` - Chat service implementation

## Configuration

Environment variables (`.env` file):
- `FLASK_ENV` - development/testing/production
- `SECRET_KEY` - Required in production (min 32 chars)
- `DATABASE_URL` - Database connection string
- `EXTERNAL_API_USERNAME/PASSWORD` - MVRetail credentials
- `WALMART_EDR_*` - Walmart integration credentials
- `SYNC_ENABLED` - Enable MVRetail sync (default: false)

## Database

- Development: SQLite (`instance/scheduler.db`)
- Production: PostgreSQL (via `DATABASE_URL`)
- Migrations in `migrations/versions/`

## Event Types & Scheduling Priority

Events are scheduled by priority: Juicer > Digital Setup > Digital Refresh > Freeosk > Digital Teardown > Core > Supervisor > Digitals > Other

The auto-scheduler:
1. Filters events within a 3-day window
2. Schedules rotation-based events (Juicer, Digital)
3. Schedules Core events (Leads first, then Specialists)
4. Auto-pairs Supervisor events with Core events
5. Creates PendingSchedule records for approval
