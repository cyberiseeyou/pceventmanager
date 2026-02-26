# CLAUDE.md

Flask Schedule Webapp - Employee scheduling system for Crossmark with auto-scheduler, AI assistant, and external integrations (Walmart EDR, MVRetail).

**Stack**: Flask 2.0+, SQLAlchemy, PostgreSQL/SQLite, Celery, Redis, Ollama AI
**Docs**: `docs/CODEBASE_MAP.md` (architecture), `docs/scheduling_validation_rules.md` (business rules)

---

## Critical Safety Rules

### Database Safety
- **ALWAYS** backup before schema changes: `./backup_now.sh`
- **ALWAYS** test migrations on `scheduler_test.db` first
- **NEVER** modify schema without creating a migration

### Code Safety
- **ALWAYS** run `pytest -v` before commits
- **NEVER** commit credentials or `.env` files
- **NEVER** import models directly - use `get_models()` (see Model Factory Pattern)

### Integration Safety
- **ALWAYS** check feature flags before calling external APIs
- **ALWAYS** use timeouts and error handling for external calls
- **ALWAYS** preserve session management logic for stateful APIs

---

## Model Factory Pattern (MANDATORY)

**CORRECT:**
```python
from app.models import get_models, get_db

def my_function():
    models = get_models()
    db = get_db()
    Employee = models['Employee']
    employee = Employee.query.filter_by(name='John').first()
    db.session.commit()
```

**WRONG - NEVER DO THIS:**
```python
from app.models.employee import Employee  # Breaks factory pattern, causes circular imports
```

---

## Change Ripple Effects

When you change a **Model**: Also update migrations, services, routes, templates, JavaScript, tests
When you change a **Service**: Also update routes, background jobs, error handlers, tests
When you change a **Route**: Also update templates, JavaScript API clients, tests
When you change a **Template**: Also update routes, JavaScript, CSS
When you change **JavaScript**: Also update API endpoints, templates, CSS

### Key Model Dependencies

| Model | Also Check |
|-------|------------|
| Event | `scheduling_engine.py`, `schedule_verification.py`, `api.py`, `index.html`, `main.js`, `sync_engine.py` |
| Employee | `constraint_validator.py`, `rotation_manager.py`, `employees.py`, `employees.js` |
| Schedule | `scheduling_engine.py`, `conflict_resolver.py`, `api.py`, `main.js` |
| RotationAssignment | `rotation_manager.py`, `scheduling_engine.py`, `auto_scheduler.py` |
| PendingSchedule | `scheduling_engine.py`, `auto_scheduler.py`, `auto_schedule_review.html` |

---

## Event Priority Order (Critical for Scheduling)

Auto-scheduler processes events in this order:
1. **Juicer** - Highest priority
2. **Digital Setup**
3. **Digital Refresh**
4. **Freeosk**
5. **Digital Teardown**
6. **Core**
7. **Supervisor** (auto-paired with Core)
8. **Digitals**
9. **Other** - Lowest priority

---

## Commands

```bash
# Development
python wsgi.py                              # Start server
FLASK_ENV=development python wsgi.py        # Debug mode
pytest -v                                   # Run tests
pytest --cov=app                            # With coverage
./backup_now.sh                             # Backup database
./start_test_instance.sh                    # Test instance (port 8001)

# Production
gunicorn --config gunicorn_config.py wsgi:app
celery -A celery_worker:celery_app worker --loglevel=info

# Database
./backup_now.sh                             # ALWAYS backup first!
flask db migrate -m "description"           # Create migration
flask db upgrade                            # Apply migration
flask db downgrade                          # Rollback
```

---

## Key Files

| File | Purpose |
|------|---------|
| `app/routes/api.py` | Main REST API |
| `app/services/scheduling_engine.py` | Auto-scheduler logic |
| `app/services/cpsat_scheduler.py` | CP-SAT constraint solver |
| `app/services/schedule_verification.py` | Daily validation |
| `app/services/constraint_validator.py` | Business rule validation |
| `app/services/constraint_modifier.py` | Runtime constraint adjustments |
| `app/services/fix_wizard.py` | Guided schedule issue resolution |
| `app/services/rotation_manager.py` | Rotation assignments |
| `app/services/weekly_validation.py` | Weekly schedule validation |
| `app/services/ai_assistant.py` | AI assistant service |
| `app/services/database_refresh_service.py` | Database refresh operations |
| `app/constants.py` | Event types, department codes |
| `app/config.py` | Environment configuration |
| `app/integrations/external_api/` | MVRetail sync |
| `app/integrations/walmart_api/` | Walmart EDR integration |
| `docs/scheduling_validation_rules.md` | Business rules |

---

## Directory Structure

```
app/
├── models/          # Database models (use get_models() to access)
├── routes/          # Flask blueprints (api.py, auto_scheduler.py, employees.py, etc.)
├── services/        # Business logic (scheduling_engine.py, rotation_manager.py, etc.)
├── integrations/    # External APIs (walmart_api/, external_api/, edr/)
├── ai/              # RAG-based AI assistant
├── templates/       # Jinja2 templates
├── static/          # JS (js/), CSS (css/)
├── error_handlers/  # Custom exceptions
└── utils/           # Helper functions

tests/               # Pytest test suite
migrations/versions/ # Alembic migrations
instance/            # Database files (scheduler.db)
docs/                # Documentation
```

---

## API Endpoints

### Events
```
GET/POST   /api/events              # List/Create
GET/PUT/DELETE /api/events/<id>     # Read/Update/Delete
GET        /api/events/date/<date>  # By date
```

### Employees
```
GET/POST   /api/employees           # List/Create
GET/PUT/DELETE /api/employees/<id>  # Read/Update/Delete
GET        /api/employees/<id>/availability
POST       /api/employees/<id>/time-off
```

### Schedules
```
GET/POST   /api/schedules           # List/Create
DELETE     /api/schedules/<id>      # Remove
POST       /api/schedules/bulk      # Bulk create
GET        /api/schedules/validation
```

### Auto-Scheduler
```
POST       /auto-schedule/run             # Run scheduler
GET        /auto-schedule/api/pending     # Pending schedules
POST       /auto-schedule/approve         # Approve batch
POST       /auto-schedule/approve-single/<id>  # Approve one
GET        /auto-schedule/review          # Review UI
```

### Response Format
```json
{"status": "success", "data": {...}}
{"status": "error", "error": "message", "details": {...}}
```

---

## Configuration

### Core Environment Variables
```bash
FLASK_ENV=development|testing|production
SECRET_KEY=<min 32 chars, required in production>
DATABASE_URL=sqlite:///instance/scheduler.db  # or postgresql://...

# Feature Flags
SYNC_ENABLED=false          # MVRetail sync
ENABLE_EDR_FEATURES=false   # Walmart EDR
ML_ENABLED=false            # Machine learning

# External APIs
EXTERNAL_API_USERNAME/PASSWORD  # MVRetail
WALMART_EDR_USERNAME/PASSWORD   # Walmart

# Redis/Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
```

### Feature Flag Pattern
```python
from app.config import get_config
config = get_config()

if not config.SYNC_ENABLED:
    return jsonify({'error': 'Sync not enabled'}), 400
```

---

> **Templates**: See `docs/component-patterns.md` for model creation and service patterns.

---

## Testing

### Fixtures (from conftest.py)
```python
def test_example(client, db_session, models):
    Employee = models['Employee']
    employee = Employee(name='Test')
    db_session.add(employee)
    db_session.commit()
    # Automatic cleanup after test
```

### Key Fixtures
- `app` - Flask app instance
- `client` - Test client for HTTP requests
- `db_session` - Database session with cleanup
- `models` - Model registry

### Running Tests
```bash
pytest                              # All tests
pytest -v                           # Verbose
pytest -x                           # Stop on first failure
pytest tests/test_file.py           # Single file
pytest -k "schedule"                # Pattern match
```

---

## Migrations

1. **Backup**: `./backup_now.sh`
2. **Edit model** in `app/models/`
3. **Generate**: `flask db migrate -m "description"`
4. **Review** the generated migration file
5. **Test**: `DATABASE_URL=sqlite:///instance/scheduler_test.db flask db upgrade`
6. **Apply**: `flask db upgrade`

For non-nullable columns: add as nullable first, backfill data, then alter to non-nullable.

---

## Common Pitfalls

### Session Management
```python
# Always commit explicitly
db.session.commit()

# Always rollback on error
try:
    db.session.commit()
except:
    db.session.rollback()
    raise
```

### External APIs
```python
# Always use timeouts
response = requests.get(url, timeout=config.EXTERNAL_API_TIMEOUT)

# Always check feature flags first
if not config.SYNC_ENABLED:
    return error_response
```

### Scheduling
```python
# Always validate before creating schedules
from app.services.constraint_validator import ConstraintValidator
validator = ConstraintValidator()
if not validator.can_assign(employee, event):
    raise ValidationError("Cannot assign")
```

---

## Model Relationships

```
Employee
├── EmployeeAvailability / EmployeeWeeklyAvailability / EmployeeAvailabilityOverride
├── EmployeeTimeOff (one-to-many)
├── Schedule (one-to-many)
├── RotationAssignment (one-to-many)
└── EmployeeAttendance (one-to-many)

Event
├── Schedule (one-to-many)
├── Note (one-to-many)
└── EventSchedulingOverride / EventTypeOverride

Schedule
├── Employee (many-to-one)
└── Event (many-to-one)

PendingSchedule (approval workflow)
├── Event, Employee (many-to-one)
└── Status: pending | approved | rejected

Auto-Scheduler: RotationAssignment, SchedulerRunHistory, ScheduleException, LockedDay
System: AuditLog, SystemSetting, CompanyHoliday, ShiftBlockSetting, UserSession
Content: Note, RecurringReminder, PaperworkTemplate, IgnoredValidationIssue
Inventory: SupplyCategory, Supply, SupplyAdjustment, PurchaseOrder, OrderItem, InventoryReminder
```

---

## Changelog

Create `changelog/YYYY-MM-DD-description.md` for:
- New features
- Bug fixes
- Breaking changes
- Schema changes
- API changes

---

## Blueprint Routes

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| main_bp | / | Dashboard, calendar |
| auth_bp | / | Authentication, sessions |
| api_bp | /api | REST API |
| employees_bp | / | Employee CRUD |
| scheduling_bp | / | Schedule management |
| auto_scheduler_bp | /auto-schedule | Scheduling UI |
| dashboard_bp | /dashboard | Validation dashboards |
| rotations_bp | /rotations | Rotation management |
| admin_bp | / | Admin panel |
| printing_bp | /printing | PDF generation |
| walmart_bp | /walmart | Walmart integration |
| edr_sync_bp | /api/sync | EDR synchronization |
| ai_bp | /api/ai | AI assistant |
| inventory_bp | /inventory | Supply inventory |
| health_bp | /health | Health checks |
| help_bp | /help | Help pages |
| attendance_api_bp | /api/attendance | Attendance endpoints |
| notifications_api_bp | /api/notifications | Notification endpoints |
| api_notes_bp | /api/notes | Notes endpoints |
| api_locked_days_bp | /api/locked-days | Locked days endpoints |
| api_shift_blocks_bp | /api/shift-blocks | Shift block endpoints |
| api_company_holidays_bp | /api/company-holidays | Company holiday endpoints |
| api_paperwork_templates_bp | /api/paperwork-templates | Paperwork template endpoints |

---

## JavaScript Integration

API calls should use centralized client:
```javascript
import { api } from './utils/api-client.js';
const events = await api.getEvents();
```

Key files:
- `app/static/js/utils/api-client.js` - API client
- `app/static/js/main.js` - Main application
- `app/static/js/pages/daily-view.js` - Daily view
- `app/static/js/pages/fix-wizard.js` - Fix wizard UI
- `app/static/js/components/ai-assistant.js` - AI assistant panel

---

## Error Handling

Use custom exceptions from `app/error_handlers/exceptions.py`:
```python
from app.error_handlers.exceptions import ValidationError, NotFoundError, ExternalAPIError

if not resource:
    raise NotFoundError(f"Resource {id} not found")
```

---

## Test Instance

```bash
# Start isolated test instance on port 8001
cp instance/scheduler.db instance/scheduler_test.db
./start_test_instance.sh

# Verify
./verify_test_instance.sh

# Cleanup
./cleanup_test_instance.sh
```

---

**Last updated**: 2026-02-18 | **Architecture docs**: `docs/CODEBASE_MAP.md`
