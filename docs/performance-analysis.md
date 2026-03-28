# Performance and Scalability Analysis

**Date**: 2026-03-26
**Scope**: Full codebase analysis of Flask Schedule Webapp
**Codebase**: ~167,352 lines across 145 Python files, 51 JS files, 77 HTML templates, 31 CSS files

---

## Executive Summary

This analysis identifies **7 critical**, **12 high**, **15 medium**, and **8 low** severity performance findings across database queries, memory management, caching, I/O bottlenecks, concurrency, frontend, and scalability. The most impactful findings are:

1. **N+1 query in CP-SAT `_load_existing_schedules`** executing one query per schedule record
2. **217 uses of `func.date()` preventing index utilization** across 26 files
3. **In-memory rate limiter ineffective** with multiple Gunicorn workers
4. **200KB monolithic JavaScript file** (`daily-view.js`) loaded without splitting
5. **Singleton SessionAPIService with shared mutable state** not thread-safe under concurrent requests
6. **`approve_schedule` function with N+1 queries in a 500+ line loop** making sequential API calls
7. **Full table delete-and-recreate in database refresh** causing extended downtime

---

## 1. Database Performance

### 1.1 N+1 Query in CP-SAT `_load_existing_schedules` [CRITICAL]

**File**: `app/services/cpsat_scheduler.py:581-605`

The `_load_existing_schedules` method loads ALL schedules, then for each schedule executes a separate query to find its event:

```python
def _load_existing_schedules(self):
    for s in self.Schedule.query.all():  # Query 1: all schedules
        # ...
        event = self.Event.query.filter_by(project_ref_num=s.event_ref_num).first()  # N additional queries!
        etype = event.event_type if event else 'Unknown'
```

**Impact**: For 200 schedules, this fires 201 queries instead of 1-2. At ~2ms per query, that adds ~400ms on SQLite and potentially more on PostgreSQL with network latency.

**Recommendation**: Pre-load events with a join or build an in-memory lookup:
```python
def _load_existing_schedules(self):
    schedules_with_events = self.db.query(self.Schedule, self.Event).outerjoin(
        self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
    ).all()
    for s, event in schedules_with_events:
        etype = event.event_type if event else 'Unknown'
        est_time = (event.estimated_time if event and event.estimated_time else 60)
        # ... same logic
```

---

### 1.2 N+1 Query in `_inject_pending_as_existing` [CRITICAL]

**File**: `app/services/cpsat_scheduler.py:700-738`

Same pattern: iterates pending schedules and queries each event individually:

```python
for ps in pending:
    event = self.Event.query.filter_by(project_ref_num=ps.event_ref_num).first()  # N queries
```

**Impact**: If 50 pending schedules, 50 additional queries during Phase 3 solver initialization.

**Recommendation**: Pre-load via join or build a `{ref_num: event}` dict from a single query.

---

### 1.3 `func.date()` Preventing Index Usage [HIGH]

**217 occurrences across 26 files**

Using `func.date(Schedule.schedule_datetime)` wraps the column in a function call, preventing the database from using the `idx_schedules_date` index. This forces full table scans.

Key offending files:
- `app/routes/api.py`: 25 occurrences
- `app/services/schedule_verification.py`: 32 occurrences
- `app/services/ai_tools.py`: 26 occurrences
- `app/services/scheduling_engine.py`: 24 occurrences
- `app/services/weekly_validation.py`: 21 occurrences

**Impact**: Every date-filtered query on the schedules table does a full scan instead of an index seek. At 1,000+ schedules, this degrades from O(log n) to O(n).

**Recommendation**: Use date range comparison pattern (already used in some optimized endpoints):
```python
# SLOW: func.date(Schedule.schedule_datetime) == target_date
# FAST: Use date range bounds
date_start = datetime.combine(target_date, time.min)
date_end = datetime.combine(target_date + timedelta(days=1), time.min)
Schedule.schedule_datetime >= date_start,
Schedule.schedule_datetime < date_end
```

Some endpoints (e.g., `get_daily_events`) already use the optimized pattern. The 217 remaining uses should be converted.

---

### 1.4 N+1 Query in Employee Management API [HIGH]

**File**: `app/routes/employees.py:72-103`

```python
for emp in employees:  # All employees loaded
    weekly_availability = EmployeeWeeklyAvailability.query.filter_by(
        employee_id=emp.id
    ).first()  # N additional queries
```

**Impact**: For 15 employees, 16 queries instead of 1 join.

**Recommendation**:
```python
employees = Employee.query.outerjoin(
    EmployeeWeeklyAvailability
).options(contains_eager(Employee.weekly_availability)).all()
```

---

### 1.5 N+1 in `get_daily_employees` Attendance Lookup [HIGH]

**File**: `app/routes/api.py:564-571`

```python
for row in schedules_query:
    attendance = EmployeeAttendance.query.filter_by(
        employee_id=row.employee_id,
        attendance_date=selected_date
    ).first()  # N queries per employee
```

**Impact**: One extra query per employee per day view. With 10 employees, 11 total queries.

**Recommendation**: Pre-load all attendance records for the date in a single query, then use a dict lookup.

---

### 1.6 N+1 in `my_time_off` Team View [MEDIUM]

**File**: `app/routes/main.py:196-197`

```python
for req in team_rows:
    emp = Employee.query.get(req.employee_id)  # N queries
```

**Impact**: One query per time-off record. Already joins Employee but re-queries it.

---

### 1.7 Deprecated `Query.get()` Usage [MEDIUM]

**49 occurrences across 13 files** (e.g., `Schedule.query.get(schedule_id)`)

`Query.get()` is deprecated in SQLAlchemy 1.x and removed in 2.0. These will all break on upgrade.

**Recommendation**: Replace with `db.session.get(Model, id)` (already used in some places).

---

### 1.8 Missing Composite Index on `EmployeeAvailability` [MEDIUM]

**File**: `app/models/availability.py:48-49`

The unique constraint `(employee_id, date)` provides an index, but queries often filter by `employee_id` + `date` + `is_available`. Adding `is_available` to the index would cover the most common query pattern.

---

### 1.9 `Schedule.query.all()` in CP-SAT Data Loading [HIGH]

**File**: `app/services/cpsat_scheduler.py:586`

```python
for s in self.Schedule.query.all():
```

Loads ALL schedules into memory regardless of relevance. With historical data growing, this becomes progressively slower.

**Impact**: A year of data at 30 schedules/day = 10,950 records loaded needlessly.

**Recommendation**: Filter to the solver's horizon window:
```python
self.Schedule.query.filter(
    self.Schedule.schedule_datetime >= earliest_date
).all()
```

---

### 1.10 Connection Pool Not Configured for Non-Production [LOW]

**File**: `app/config.py:156-161`

Only `ProductionConfig` has pool settings. Development and testing configs use SQLAlchemy defaults (pool_size=5, no pre_ping). If development uses PostgreSQL, connections may go stale.

---

## 2. Memory Management

### 2.1 Full Event Table Delete-and-Recreate During Refresh [CRITICAL]

**File**: `app/services/database_refresh_service.py:207-217`

```python
Schedule.query.delete()
Event.query.delete()
db.session.commit()
```

The database refresh service:
1. Loads ALL existing schedules into memory for preservation
2. Deletes ALL events and schedules
3. Re-creates all events one by one in a loop
4. Restores preserved schedules one by one

**Impact**:
- Memory spike: holds both old and new event data simultaneously
- Extended write lock: table is empty between delete and re-insert
- No concurrent read access during refresh
- Risk of data loss if process crashes mid-refresh

**Recommendation**: Use upsert/merge pattern instead of delete-all/re-insert:
```python
for record in records:
    existing = Event.query.filter_by(project_ref_num=record['ref_num']).first()
    if existing:
        # Update fields
        existing.project_name = record['name']
    else:
        # Insert new
        db.session.add(Event(...))
```

---

### 2.2 CP-SAT Solver Memory Growth [MEDIUM]

**File**: `app/services/cpsat_scheduler.py:896-977`

The solver creates BoolVar decision variables for every (event, day), (event, employee), and (event, block) combination. With 100 events, 15 employees, and 60 valid days:
- `v_assign_day`: up to 6,000 variables
- `v_assign_emp`: up to 1,500 variables
- `v_assign_block`: up to 800 variables
- `_indicator_cache`: up to 90,000 entries

The `MAX_HORIZON_WEEKS = 8` cap helps, but the indicator cache grows as O(events * employees * days).

**Impact**: For extreme cases (200+ events, 20+ employees), memory usage could reach hundreds of MB.

**Recommendation**: The existing domain filtering (eligible employees per event, valid days per event) already limits this. Consider adding a memory budget check before model building.

---

### 2.3 Unbounded `all_events` List in Parallel Fetch [MEDIUM]

**File**: `app/integrations/external_api/session_api_service.py:907-934`

```python
all_events = []
with ThreadPoolExecutor(max_workers=10) as executor:
    for future in as_completed(future_to_chunk):
        events = future.result()
        all_events.extend(events)  # Unbounded growth
```

With 150 days of data in 3-day chunks (50 chunks), each returning up to 5,000 events, the list could hold 250,000+ event dicts.

**Impact**: Each event dict is ~500 bytes, so 250K events = ~125MB peak memory.

**Recommendation**: Stream results through a deduplication set rather than accumulating all in memory.

---

### 2.4 Large Schedule Collections in `approve_schedule` [MEDIUM]

**File**: `app/routes/auto_scheduler.py:512-516`

```python
pending_schedules = db.session.query(models['PendingSchedule']).filter(
    models['PendingSchedule'].scheduler_run_id == run_id,
    models['PendingSchedule'].failure_reason.is_(None)
).all()
```

Then iterated multiple times (swap check, locked day check, approval loop) with individual queries for each.

---

## 3. Caching Opportunities

### 3.1 No Caching for Shift Block Configuration [HIGH]

**Files**: `app/services/shift_block_config.py`, called from many places

`ShiftBlockConfig.get_all_blocks()` and `ShiftBlockConfig.get_block()` are called from:
- `api.py` (daily-summary endpoint)
- `scheduling_engine.py` (multiple times during init)
- `cpsat_scheduler.py` (init)
- `schedule_verification.py` (init)

Each call likely queries `SystemSetting` table. During a single daily-summary request, `get_all_blocks()` is called at least 3 times.

**Impact**: Redundant DB queries on every request.

**Recommendation**: Cache with a short TTL (30-60 seconds) or per-request cache:
```python
@lru_cache(maxsize=1)
def get_all_blocks():
    # ... load from DB
    # Clear cache on setting change
```

---

### 3.2 No Caching for Event Time Settings [HIGH]

**Files**: Multiple calls to `get_freeosk_times()`, `get_digital_setup_slots()`, etc.

Both `SchedulingEngine.__init__` and `CPSATSchedulingEngine._load_time_settings` call the same settings functions. During a scheduler run, these are called at init time but settings rarely change.

**Recommendation**: Cache settings at app startup and invalidate on admin update.

---

### 3.3 Repeated `get_models()` Calls [MEDIUM]

Every route handler calls `get_models()` which accesses the model registry. While the registry itself is likely O(1) dict lookup, the call overhead adds up across 525 `db.session.*` call sites in route files.

**Recommendation**: This is inherent to the factory pattern; minimal optimization needed. Consider passing models via `g` context.

---

### 3.4 No Query Result Caching for Dashboard [MEDIUM]

**File**: `app/routes/dashboard.py` and `app/services/command_center_service.py`

The command center dashboard runs complex aggregation queries on every page load. These queries scan events, schedules, notes, and time-off tables.

**Recommendation**: Cache dashboard data for 30-60 seconds. Use Redis (already available for sessions):
```python
cache_key = f"dashboard:{date.today()}"
cached = redis_client.get(cache_key)
if cached:
    return json.loads(cached)
```

---

## 4. I/O Bottlenecks

### 4.1 Synchronous API Calls in `approve_schedule` Loop [CRITICAL]

**File**: `app/routes/auto_scheduler.py:855-913`

The approval loop makes sequential, synchronous HTTP calls to Crossmark API for each pending schedule:

```python
for pending in pending_schedules:
    # ... validation ...
    api_result = external_api.schedule_mplan_event(...)  # Blocking HTTP call per event
```

Each API call has a 30-second timeout. For 20 pending schedules, worst case is 600 seconds (10 minutes).

**Impact**: The HTTP request to the Flask server blocks for the entire duration. Users see a spinner for minutes. Connection timeouts likely.

**Recommendation**:
1. **Immediate**: Process API submissions asynchronously via Celery tasks
2. **Short-term**: Use ThreadPoolExecutor with a small pool (3-5 workers) for parallel API calls
3. **Long-term**: Return immediately with a job ID, poll for completion via WebSocket/SSE

---

### 4.2 Database Refresh Blocks Auto-Scheduler [HIGH]

**File**: `app/services/scheduling_engine.py:350-376`

```python
def run_auto_scheduler(self, run_type):
    # AUTO-REFRESH: Sync database from external API before scheduling
    refresh_service = DatabaseRefreshService()
    refresh_result = refresh_service.refresh()  # Blocks for 30-90 seconds
```

The auto-scheduler synchronously refreshes the entire database before scheduling. This involves parallel HTTP fetching (improved from 185s to ~41s) but still blocks the request.

**Impact**: The scheduling request blocks for 40+ seconds just for the refresh step.

**Recommendation**: Decouple refresh from scheduling. Run refresh as a periodic Celery task (every 5-15 minutes) and let the scheduler use the latest cached data.

---

### 4.3 No Pagination on Event List Endpoints [HIGH]

**File**: `app/routes/api.py` and `app/routes/main.py`

The events list page loads ALL events. With the 4-month horizon containing 500+ events, this is a large payload.

Key unpaginated queries:
- `auto_scheduler.py:38-60`: All unscheduled events loaded for page render
- Employee list: All employees loaded (manageable at ~15-20)
- Events by date range: No LIMIT clause

**Recommendation**: Add cursor-based or offset pagination:
```python
page = request.args.get('page', 1, type=int)
per_page = request.args.get('per_page', 50, type=int)
events = Event.query.paginate(page=page, per_page=per_page)
```

---

### 4.4 Synchronous External API Calls in Unschedule Endpoints [MEDIUM]

**File**: `app/routes/api.py:773-803`

```python
api_result = external_api.unschedule_mplan_event(str(schedule.external_id))
```

Every unschedule operation makes a blocking HTTP call. When unscheduling a Core event, it also unschedules the paired Supervisor event, doubling the blocking time.

---

### 4.5 No Response Compression [LOW]

No gzip/brotli compression middleware detected in `app/__init__.py`. Large JSON responses (daily-summary, events list) are sent uncompressed.

**Recommendation**: Add `flask-compress`:
```python
from flask_compress import Compress
compress = Compress()
compress.init_app(app)
```

---

## 5. Concurrency Issues

### 5.1 In-Memory Rate Limiter [CRITICAL]

**File**: `app/extensions.py:20-24`

```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",  # TODO comment acknowledges the issue
    strategy="fixed-window"
)
```

With Gunicorn running multiple workers, each worker has its own in-memory counter. A client can make `N * workers` requests before being limited.

**Impact**: Rate limiting is effectively disabled in production with multiple workers.

**Recommendation**: Use Redis (already deployed for sessions):
```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379/1",
    strategy="fixed-window"
)
```

---

### 5.2 Singleton SessionAPIService Not Thread-Safe [CRITICAL]

**File**: `app/integrations/external_api/session_api_service.py:25-36`

```python
class SessionAPIService:
    def __init__(self):
        self.session = None           # Shared mutable state
        self.authenticated = False     # Shared mutable state
        self.phpsessid = None         # Shared mutable state
```

This is a module-level singleton (`session_api = SessionAPIService()`). All workers/threads share the same instance. Two concurrent requests could:
1. Both see `authenticated = False`
2. Both call `login()`
3. One overwrites the other's PHPSESSID
4. First request uses second request's session
5. Session state corruption

The `_fetch_planning_events_parallel` method uses 10 threads that all share the same `requests.Session` and cookies, compounding the issue.

**Impact**: Intermittent authentication failures, session hijacking between requests.

**Recommendation**:
1. Add a threading lock around authentication:
```python
import threading
self._auth_lock = threading.Lock()

def ensure_authenticated(self):
    with self._auth_lock:
        if self.is_session_valid():
            return True
        return self.login()
```
2. For the parallel fetcher, ensure all threads reuse the already-authenticated session rather than triggering re-auth.

---

### 5.3 Race Condition in Schedule Approval [MEDIUM]

**File**: `app/routes/auto_scheduler.py:508`

```python
run = db.session.query(models['SchedulerRunHistory']).get(run_id)
```

No row-level lock on the run record. Two concurrent approve requests for the same `run_id` could both proceed, creating duplicate schedules.

Note: The `approve_single_schedule` endpoint DOES use `.with_for_update()` (line 1022), but the batch `approve_schedule` does not.

**Recommendation**: Add `with_for_update()`:
```python
run = db.session.query(models['SchedulerRunHistory']).with_for_update().get(run_id)
```

---

### 5.4 Global MFA State in Printing Module [MEDIUM]

**File**: `app/routes/printing.py:66-70`

```python
# Global mutable state
MFA_CODE_EXPIRY_SECONDS = 300
mfa_request_timestamp = None
mfa_auth_state = {'status': 'idle', 'error': None}
```

Module-level mutable dicts shared across workers. Not safe with multiple Gunicorn workers.

---

### 5.5 Background Scheduler in Each Worker [LOW]

**File**: `app/__init__.py:290-315`

```python
scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_walmart_sessions, ...)
scheduler.start()
```

APScheduler runs in each Gunicorn worker process, meaning the cleanup job runs N times (once per worker) every 60 seconds.

**Recommendation**: Use a process-aware scheduler or move to Celery Beat for periodic tasks.

---

## 6. Frontend Performance

### 6.1 Monolithic 200KB JavaScript File [HIGH]

**File**: `app/static/js/pages/daily-view.js` (201,946 bytes / 4,843 lines)

This single file is loaded for the daily view page. It contains all UI logic, event handlers, modal management, drag-and-drop, and API calls.

**Impact**: ~200KB of JavaScript parsed and executed on every daily view page load, even if the user only views the page without interaction.

**Recommendation**:
1. Split into focused modules (event-cards.js, modals.js, drag-drop.js)
2. Use dynamic `import()` for modal and drag-drop code
3. Minify all JS files (no build step detected)

---

### 6.2 No JavaScript or CSS Minification [HIGH]

**Total JS**: 743,773 bytes across all files
**Total CSS**: 439,923 bytes across all files
**Combined**: ~1.15MB of unminified static assets

No build pipeline, bundler, or minification detected. Files are served as-is.

**Impact**: On a 3G mobile connection (1.5 Mbps), downloading 1.15MB takes ~6 seconds. Minification typically achieves 40-60% reduction.

**Recommendation**: Add a build step with esbuild or terser:
```bash
# Example: minify all JS
npx terser app/static/js/pages/daily-view.js -o app/static/js/pages/daily-view.min.js -c -m
```

---

### 6.3 No Lazy Loading for Below-the-Fold Content [MEDIUM]

**File**: `app/templates/base.html:22-37`

All 10 CSS files are loaded in `<head>` with render-blocking `<link>` tags:
- `design-tokens.css`
- `style.css`
- `modal.css`
- `loading-states.css`
- `keyboard-shortcuts.css`
- `form-validation.css`
- `responsive.css`
- `notification-modal.css`
- `sidebar.css`
- `bottom-nav.css`

**Impact**: Browser must download and parse all CSS before rendering any content (FOUC protection vs. load time tradeoff).

**Recommendation**:
1. Combine CSS files that are always needed into one file
2. Load modal/keyboard-shortcuts/notification CSS asynchronously:
```html
<link rel="stylesheet" href="modal.css" media="print" onload="this.media='all'">
```

---

### 6.4 External Font Loading Without `font-display` [MEDIUM]

**File**: `app/templates/base.html:24-26`

```html
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:..." />
```

Material Symbols font is loaded without `display=swap`, causing invisible text while the font loads.

**Recommendation**: Add `&display=swap` to the Material Symbols URL.

---

### 6.5 Service Worker Pre-Cache Incomplete [LOW]

**File**: `app/static/service-worker.js:15-28`

Only 12 assets are pre-cached. Page-specific JS files (daily-view.js, index-page.js) are not pre-cached, causing cold-start delays on repeat visits.

---

### 6.6 Cache Busting via Server Restart Timestamp [LOW]

**File**: `app/__init__.py:42`

```python
app.config['VERSION'] = datetime.now().strftime('%Y%m%d%H%M%S')
```

Cache busting uses server startup time, not file content hash. Every restart invalidates all cached static assets even if files have not changed.

**Recommendation**: Use content-based hashing (e.g., Flask-Assets or manual `md5` of files).

---

## 7. Scalability Concerns

### 7.1 Single-Process Auto-Scheduler [HIGH]

The auto-scheduler (both greedy and CP-SAT) runs synchronously in the web request process. During the ~15-60 second execution:
- The web worker is blocked
- No other requests can be served by that worker
- With 4 workers, 4 concurrent scheduler runs could block all capacity

**Recommendation**: Move scheduler execution to Celery:
```python
@auto_scheduler_bp.route('/run', methods=['POST'])
def run_scheduler():
    task = run_auto_scheduler_task.delay(run_type='manual')
    return jsonify({'task_id': task.id, 'status': 'queued'})
```

---

### 7.2 Redis Session Without Cluster Support [MEDIUM]

**File**: `app/routes/auth.py:22-37`

Sessions are stored in a single Redis instance. No sentinel or cluster configuration.

**Impact**: Redis failure = all users logged out. No horizontal scaling of session storage.

---

### 7.3 SQLite in Production [MEDIUM]

**File**: `app/config.py:19`

```python
SQLALCHEMY_DATABASE_URI = config('DATABASE_URL', default='sqlite:///instance/scheduler.db')
```

Default database is SQLite. While PostgreSQL is supported via `DATABASE_URL`, the default and likely production setup is SQLite, which:
- Has a single-writer lock (no concurrent writes)
- Cannot handle multiple Gunicorn workers writing simultaneously
- Has no connection pooling benefit

**Impact**: Write contention under concurrent requests.

---

### 7.4 Stateful External API Client [MEDIUM]

The `SessionAPIService` singleton holds PHP session state. This cannot be replicated across multiple servers. If the app scales to multiple hosts, only one can hold the authenticated session.

**Recommendation**: Store external API session credentials in Redis with expiry, allowing any worker to resume the session.

---

### 7.5 No Database Read Replicas Support [LOW]

All reads and writes go through the same database connection. For read-heavy workloads (dashboard, daily view), read replicas could offload the primary.

---

### 7.6 Hardcoded Employee-to-RepID Mapping [LOW]

**File**: `app/services/sync_service.py:84-91`

```python
employee_to_repid = {
    'MAT CONDER': '152052',
    'DIANE CARR': '19461',
    # ...
}
```

Hardcoded mapping that must be manually updated. This is a maintenance issue, not strictly performance, but prevents automated scaling of employee onboarding.

---

## 8. Mixed Datetime Usage

### 8.1 `datetime.utcnow()` vs `datetime.now()` [MEDIUM]

- **131 uses of `datetime.utcnow()`** (model defaults, timestamps)
- **134 uses of `datetime.now()`** (scheduling logic, comparisons)

The inconsistency means:
- Model `created_at` fields store UTC
- Scheduling comparisons use local time
- Date boundary calculations could be off by hours

**Impact**: Events near midnight could be scheduled on the wrong day depending on which datetime function is used in the comparison.

**Recommendation**: Standardize on timezone-aware datetimes:
```python
from datetime import datetime, timezone
datetime.now(timezone.utc)  # Replaces both utcnow() and now()
```

---

## Priority Matrix

| # | Finding | Severity | Estimated Effort | Performance Gain |
|---|---------|----------|-----------------|-----------------|
| 5.1 | In-memory rate limiter | Critical | 15 min | Fixes security gap |
| 5.2 | SessionAPIService thread safety | Critical | 1 hour | Fixes auth corruption |
| 1.1 | CP-SAT N+1 in `_load_existing_schedules` | Critical | 30 min | -400ms per solver run |
| 1.2 | CP-SAT N+1 in `_inject_pending_as_existing` | Critical | 30 min | -100ms per Phase 3 |
| 4.1 | Synchronous API calls in approve loop | Critical | 4 hours | Minutes -> seconds |
| 2.1 | Delete-all database refresh | Critical | 8 hours | Eliminates downtime |
| 1.3 | 217x `func.date()` preventing indexes | High | 4 hours | 2-10x faster date queries |
| 6.1 | 200KB monolithic JS | High | 4 hours | -50% page load time |
| 6.2 | No JS/CSS minification | High | 2 hours | -40% transfer size |
| 3.1 | No shift block caching | High | 1 hour | -3 queries per request |
| 3.2 | No event time settings caching | High | 1 hour | -4 queries per scheduler init |
| 4.2 | Sync refresh blocking scheduler | High | 4 hours | -40s per scheduler run |
| 4.3 | No pagination on event lists | High | 2 hours | Constant response time |
| 7.1 | Synchronous auto-scheduler | High | 4 hours | Unblocks web workers |
| 1.4 | N+1 in employee management | High | 30 min | -15 queries |
| 1.5 | N+1 in daily employees | High | 30 min | -10 queries |
| 1.9 | Unfiltered Schedule.query.all() | High | 30 min | -50% memory in solver |

---

## Appendix: Query Pattern Inventory

| Pattern | Count | Files | Risk |
|---------|-------|-------|------|
| `func.date()` on indexed columns | 217 | 26 | Index bypass |
| `db.session.*` in route files | 525 | 24 | Logic in routes |
| `.query.get()` (deprecated) | 49 | 13 | SQLAlchemy 2.0 breakage |
| `joinedload`/`selectinload` usage | 12 | 4 | Very low eager loading adoption |
| `datetime.utcnow()` | 131 | 61 | Mixed timezone handling |
| `datetime.now()` | 134 | 61 | Mixed timezone handling |
