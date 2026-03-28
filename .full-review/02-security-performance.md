# Phase 2: Security & Performance Review

## Security Findings

### Critical (7) — CVSS 7.5-9.8

| ID | Finding | CVSS | CWE | Location |
|----|---------|------|-----|----------|
| CRIT-01 | **Mass unauthenticated API endpoints** — 24+ endpoints expose PII, allow data modification (schedule/unschedule/import) without any auth | 9.8 | CWE-306 | `api.py` (24+ routes), `health_bp`, `ai_rag_bp`, `attendance_api_bp`, `api_demo_goals_bp` |
| CRIT-02 | **Plaintext credential logging** — `request.form` (contains password) and raw POST body logged at INFO level | 9.1 | CWE-532 | `auth.py:235-237` |
| CRIT-03 | **Broken rate limiting** — lambda pattern resets counter per request + memory:// storage is per-worker | 9.1 | CWE-307 | `auth.py:228-231`, `extensions.py:20-24` |
| CRIT-04 | **Unauthenticated webhook** — CSRF-exempt, no HMAC verification, allows direct DB deletion | 9.1 | CWE-345 | `admin.py:268-323` |
| CRIT-05 | **Singleton race condition** — concurrent logins can cross-contaminate auth state between users | 8.7 | CWE-362 | `session_api_service.py:1802`, `auth.py:256-277` |
| CRIT-06 | **Role assignment bug** — undefined `db` variable + bare except = all Crossmark users get supervisor role | 8.6 | CWE-269 | `auth.py:319-336` |
| CRIT-07 | **Unauthenticated diagnostics** — `/api/auth/diag` exposes Redis infrastructure details | 7.5 | CWE-200 | `auth.py:636-654` |

### High (11) — CVSS 6.5-7.5

| ID | Finding | Location |
|----|---------|----------|
| HIGH-01 | Exception details leaked in 100+ API responses via `str(e)` — exposes DB schema, paths, SQL | `api.py`, `admin.py`, `api_notes.py`, etc. |
| HIGH-02 | SSL verification disabled (`verify=False`) for external requests | `demo_goals_service.py:40,59` |
| HIGH-03 | Hardcoded employee PII (names + Crossmark RepIDs) in source code, committed to git | `sync_service.py:84-92, 198-206` |
| HIGH-04 | Pickle deserialization of cached session data — code execution risk if tmp writable | `admin.py:924-937, 982-984` |
| HIGH-05 | Insecure default SECRET_KEY in production config | `config.py:141` |
| HIGH-06 | PHPSESSID stored in Redis session data — Redis compromise = Crossmark access | `auth.py:344-352` |
| HIGH-07 | Debug mode enabled by default (`FLASK_ENV` not set = development mode) | `config.py` |
| HIGH-08 | HAR file containing HTTP requests/responses committed to repository | `crossmark.mvretail.com.har` |
| HIGH-09 | Unsafe CSP — no Content-Security-Policy header configured | `__init__.py` |
| HIGH-10 | Missing security headers (X-Content-Type-Options, X-Frame-Options on API) | Various |
| HIGH-11 | Insecure cookie flags — session cookie missing Secure and HttpOnly in non-HTTPS | `auth.py` |

### Medium (14)

- 26 bare `except:` clauses silently swallowing all exceptions
- Credential logging in `session_api_service.py` (PHPSESSID partial logging)
- SQL-like pattern injection potential in search/filter endpoints
- Account enumeration via different error messages for valid/invalid usernames
- Weak PIN policy (4-digit PINs, no complexity requirements)
- CSRF gaps on some AJAX endpoints
- Missing rate limiting on PIN login endpoint
- Role default escalation (supervisor as default instead of least privilege)
- Exposed metrics at `/health/metrics` without auth
- Deprecated endpoint bypass (old endpoints bypass new auth checks)
- Password stored in singleton instance attributes
- Missing input length validation on search parameters
- Session fixation potential during role changes
- No audit logging for sensitive operations

### Low (8)

- Deprecated X-XSS-Protection header still set
- CSRF cookie design considerations
- `remember_me` parameter accepted but not implemented
- Role derivation from external API without validation
- Cookie SameSite policy considerations
- Database file path disclosed in error messages
- Import functionality exposure
- Redis session cleanup timing

---

## Performance Findings

### Critical (7)

| ID | Finding | Impact | Location |
|----|---------|--------|----------|
| PERF-01 | **N+1 query in CP-SAT `_load_existing_schedules`** — one DB query per schedule to find its event (201 queries for 200 schedules) | +400ms per solver run | `cpsat_scheduler.py:581-605` |
| PERF-02 | **N+1 query in `_inject_pending_as_existing`** — one query per pending schedule | +100ms per Phase 3 | `cpsat_scheduler.py:700-738` |
| PERF-03 | **In-memory rate limiter** — per-worker counters, ineffective with Gunicorn | Security gap + wasted memory | `extensions.py:20-24` |
| PERF-04 | **Singleton SessionAPIService not thread-safe** — 10-thread parallel fetcher shares mutable auth state | Intermittent auth failures | `session_api_service.py:25-36` |
| PERF-05 | **Synchronous API calls in approve loop** — sequential 30s-timeout HTTP calls per schedule | Up to 10 minutes blocking | `auto_scheduler.py:855-913` |
| PERF-06 | **Delete-all database refresh** — deletes ALL events/schedules then re-inserts | Extended downtime, data loss risk | `database_refresh_service.py:207-217` |
| PERF-07 | **`Schedule.query.all()` in CP-SAT** — loads entire history instead of filtering to horizon | Unbounded memory growth | `cpsat_scheduler.py:586` |

### High (10)

| ID | Finding | Impact | Location |
|----|---------|--------|----------|
| PERF-08 | **217 `func.date()` calls preventing index usage** across 26 files | Full table scans on every date query | `api.py`, `schedule_verification.py`, `ai_tools.py`, etc. |
| PERF-09 | **200KB monolithic daily-view.js** (4,843 lines) | Slow page load, parse blocking | `static/js/pages/daily-view.js` |
| PERF-10 | **No JS/CSS minification** — 743KB JS + 440KB CSS served raw | 6s load on 3G | All static assets |
| PERF-11 | **No shift block config caching** — re-queried on every request | 3+ redundant DB queries/request | `shift_block_config.py` |
| PERF-12 | **No event time settings caching** — re-queried on every scheduler init | 4+ redundant queries | `scheduling_engine.py`, `cpsat_scheduler.py` |
| PERF-13 | **Database refresh blocks auto-scheduler** — 40+ seconds synchronous refresh | Blocks web worker for 40s | `scheduling_engine.py:350-376` |
| PERF-14 | **No pagination on event/schedule list endpoints** | Large unbounded payloads | `api.py`, `auto_scheduler.py` |
| PERF-15 | **N+1 in employee management API** — one query per employee for availability | 16 queries for 15 employees | `employees.py:72-103` |
| PERF-16 | **N+1 in daily employees attendance** — one query per employee | 11 queries for 10 employees | `api.py:564-571` |
| PERF-17 | **Single-process auto-scheduler** — blocks web worker for 15-60 seconds | Capacity starvation | `auto_scheduler.py` |

### Medium (15)

- N+1 in time-off team view (`main.py:196-197`)
- 49 deprecated `Query.get()` usages — will break on SQLAlchemy 2.0
- Missing composite index on `EmployeeAvailability(employee_id, date, is_available)`
- CP-SAT indicator cache grows O(events * employees * days)
- Unbounded event list in parallel fetch (potential 125MB peak)
- Large schedule collections iterated multiple times in approve flow
- No dashboard query caching (complex aggregation on every page load)
- Synchronous external API calls in unschedule endpoints
- Race condition in batch schedule approval (no row-level lock)
- Global MFA state in printing module (not worker-safe)
- Background scheduler runs in each worker (N duplicate jobs)
- 12 CSS files loaded render-blocking in `<head>`
- Material Symbols font loaded without `display=swap`
- Mixed `datetime.utcnow()` (131) vs `datetime.now()` (134) — timezone bugs
- Repeated `get_models()` call overhead across 525 db.session sites

### Low (8)

- Connection pool not configured for non-production
- No response compression (missing gzip/brotli)
- Service worker pre-cache incomplete
- Cache busting via server restart timestamp instead of content hash
- No database read replica support
- Hardcoded employee-to-RepID mapping prevents scaling
- No query result caching for reports
- `SELECT *` patterns where only specific columns needed

---

## Critical Issues for Phase 3 Context

### Testing Implications
- **24+ unauthenticated endpoints** need auth decorator tests to prevent regressions
- **Role assignment bug** needs test proving Crossmark users get correct roles
- **Race conditions** (singleton, batch approval) need concurrency tests
- **N+1 queries** should have performance regression tests
- **Rate limiter** needs integration test proving it actually limits

### Documentation Implications
- **Security headers** configuration needs to be documented
- **Auth decorator requirements** for new endpoints should be in contributing guide
- **Singleton API service** thread-safety constraints must be documented
- **Datetime conventions** (which timezone, which function) need standards doc
- **API response envelope** format must be standardized and documented
