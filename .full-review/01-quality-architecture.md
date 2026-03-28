# Phase 1: Code Quality & Architecture Review

## Code Quality Findings

### Critical (3)

1. **C1 — Login logs credentials in plain text** (`app/routes/auth.py:235-237`). The login endpoint logs `request.form` (contains password) and raw POST body at INFO level. These will appear in production log files.

2. **C2 — Hardcoded employee PII in source code** (`app/services/sync_service.py:84-92, 198-209`). Employee names and Crossmark RepIDs are hardcoded in two duplicate dicts. Leaks PII via git history.

3. **C3 — Unauthenticated API endpoints** (`app/routes/api.py`, 18 of 40 endpoints). Critical write operations (`/api/event/<id>/unschedule`, `/api/import/events`) and read endpoints exposing employee names, schedules, and attendance data lack authentication.

### High (9)

- **H1** — `EVENT_TYPE_PRIORITY` duplicated in `scheduling_engine.py` and `cpsat_scheduler.py` with slight differences; `LEAD_ONLY_EVENT_TYPES` defined in 3 places with different contents.
- **H2** — Three competing DB access patterns: `get_models()` (correct), `current_app.config[Model]` (deprecated, 20+ usages), and `current_app.extensions['sqlalchemy']` (30+ usages).
- **H3** — 30+ usages of deprecated `Query.get()` that will break on SQLAlchemy 2.0.
- **H4** — 25+ bare `except:` clauses silently swallowing errors including in database operations.
- **H5** — Mixed `datetime.utcnow()` (131 usages) and `datetime.now()` (134 usages) — both deprecated in Python 3.12+, and mixing them creates timezone bugs.
- **H6** — Login rate limiting is broken — the `limiter.limit()(lambda: None)()` pattern creates a new lambda each request, so the rate limit counter resets every time.
- **H7** — Rate limiter uses `storage_uri="memory://"` in production, making it per-worker (ineffective with Gunicorn).
- **H8** — `/api/auth/diag` exposes Redis infrastructure details without authentication.
- **H9** — Role lookup in Crossmark login uses an undefined `db` variable, so `hasattr(db, 'or_')` likely returns False, causing all Crossmark users to default to `'supervisor'` role.

### Medium (14)

- `api.py` is 6,940 lines — a god file spanning 53 route handlers across 7 business domains
- `approve_schedule` function exceeds 500 lines of cyclomatic complexity
- N+1 queries in `get_pending_schedules` and time-off team view
- Logic bug in `_is_within_7_days` that sends notifications for events 100 days in the past
- Duplicate route registration for `/api/event/<id>/change-employee`
- `ProductionConfig` pool options that break SQLite
- Two competing `get_models()` functions with different return signatures (`app.models` vs `app.utils.db_helpers`)
- Mixed use of `get_models()` sources within single files (`api.py` uses both)
- Services accessing `current_app.config` for models instead of constructor injection
- Inconsistent blueprint initialization patterns (3 different patterns)
- Event type priority duplicated across files without single source of truth
- Two validation systems (`ConstraintValidator` and `ConflictValidator`) with overlapping responsibilities
- `@handle_errors` decorator exists but has zero usages in any route file
- SSL verification disabled in `demo_goals_service.py`

### Low (8)

- PHPSESSID partial logging
- Inconsistent `import re` placement
- Fragile string matching in event type detection
- Magic number fallbacks
- Inconsistent API error response formats
- Stale import in `main.py` (`init_models` imported but never called)
- No API versioning
- Global engine listener in `__init__.py`

---

## Architecture Findings

### Critical (1)

1. **Hardcoded employee PII** — `sync_service.py` contains real employee names and Crossmark RepIDs in two duplicate dictionaries committed to version control.

### High (6)

1. **Monolithic api.py** (6,940 lines) — Contains 53 route handlers spanning 7 domains. Partial decomposition started but vast majority of logic remains monolithic.
2. **Three competing model access patterns** — `get_models()`, `current_app.config[Model]` (60+ sites), and `db_helpers.get_models()` all active simultaneously.
3. **Direct model imports in sync modules** — `sync_service.py` and `sync_engine.py` use `from app import db, Schedule, Event, Employee`, the exact anti-pattern CLAUDE.md prohibits.
4. **Route handlers contain business logic** — 488 occurrences of `db.session.*` in route files. `unschedule_event` is 140 lines of orchestration in a route handler.
5. **Exception details leaked in API responses** — 117 occurrences of `return jsonify({'error': str(e)})` exposing database schema, file paths, and SQL queries.
6. **Missing authentication on 18+ API endpoints** — Read and write endpoints for employee data, schedules, and events lack auth decorators.

### Medium (13)

1. Duplicate API endpoints for same operations (reschedule, trade, unschedule, change-employee)
2. Inconsistent blueprint initialization (3 different patterns)
3. Services reaching through Flask context for models via deprecated `current_app.config`
4. Two validation systems with overlapping business rules
5. Singleton `SessionAPIService` with shared auth state (not thread-safe)
6. Inconsistent API response envelope formats (4+ different shapes)
7. Bare `except:` clauses swallowing errors (26 sites)
8. Unused `@handle_errors` decorator framework
9. N+1 query patterns in time-off team view
10. In-memory rate limiter ineffective in multi-worker production
11. SSL verification disabled for external requests
12. Admin routes using deprecated model access pattern
13. Mixed `get_models()` sources within single files

### Low (5)

1. Factory pattern overhead vs modern Flask-SQLAlchemy patterns
2. Business key used as foreign key (Schedule → Event via `project_ref_num`)
3. No API versioning
4. Stale import in `main.py`
5. Global engine listener registration

---

## Critical Issues for Phase 2 Context

The following findings should directly inform the Security and Performance reviews:

### Security-Critical
- **Plain-text credential logging** in auth.py (C1)
- **18+ unauthenticated API endpoints** exposing PII and schedule data (C3)
- **Hardcoded employee PII** in source code (C2)
- **Exception details leaked** in 117 API responses
- **Broken rate limiting** on login endpoint (H6, H7)
- **Unauthenticated diagnostics endpoint** exposing Redis details (H8)
- **SSL verification disabled** for external requests
- **Role assignment bug** possibly granting all Crossmark users supervisor role (H9)

### Performance-Critical
- **N+1 query patterns** in pending schedules and time-off views
- **6,940-line monolithic api.py** impacting developer productivity
- **In-memory rate limiter** ineffective with Gunicorn workers
- **Singleton API service** not thread-safe under concurrent requests
- **30+ deprecated `Query.get()` calls** that will break on SQLAlchemy 2.0 upgrade
- **Mixed datetime functions** creating potential timezone bugs
