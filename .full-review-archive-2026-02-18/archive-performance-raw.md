# Performance & Scalability Analysis

**Target**: All uncommitted changes (CP-SAT scheduler, Fix Wizard, AI tools, constraint modifier, database refresh, approval workflow, frontend)
**Date**: 2026-02-18
**Framework**: Flask 2.0+ / SQLAlchemy / OR-Tools CP-SAT / SQLite

---

## Summary

| Severity | Count | Estimated Impact |
|----------|-------|-----------------|
| Critical | 3 | Service outage or >10x degradation on realistic data |
| High | 5 | 2-10x slower on moderate data, blocking for scale |
| Medium | 8 | Measurable slowdown, latency spikes under load |
| Low | 4 | Minor inefficiency, cosmetic or future concern |

---

## Critical Findings

### CRIT-01: CP-SAT `_load_existing_schedules` N+1 Query (O(S) individual queries)

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 456-480

**Problem**: For every existing schedule record, a separate `Event.query.filter_by(project_ref_num=...).first()` is issued inside the loop. With 200 schedules, this fires 200 individual SELECT queries during data loading.

```python
for s in self.Schedule.query.all():   # 1 query: loads all schedules
    ...
    event = self.Event.query.filter_by(project_ref_num=s.event_ref_num).first()  # N queries
    etype = event.event_type if event else 'Unknown'
    est_time = (event.estimated_time if event and event.estimated_time else 60)
```

**Impact**: With ~200 posted schedules, this adds 200 round-trips to SQLite (or worse, to PostgreSQL over network). At ~2ms per query, that is ~400ms of pure query latency just in data loading. With 500+ schedules this exceeds 1 second.

**Fix**: Pre-load all events into a lookup dictionary, then join in memory.

```python
def _load_existing_schedules(self):
    """Load existing (posted) schedules for bump penalty and conflict detection."""
    self.existing_schedules = []
    self.existing_by_emp_day = defaultdict(list)

    # Pre-load all events keyed by ref_num (single query)
    all_events = {e.project_ref_num: e for e in self.Event.query.all()}

    for s in self.Schedule.query.all():
        if not s.schedule_datetime:
            continue
        sd = s.schedule_datetime.date() if isinstance(s.schedule_datetime, datetime) else s.schedule_datetime
        self.existing_schedules.append({
            'event_ref': s.event_ref_num,
            'employee_id': s.employee_id,
            'date': sd,
            'block': getattr(s, 'shift_block', None),
        })

        event = all_events.get(s.event_ref_num)
        etype = event.event_type if event else 'Unknown'
        est_time = (event.estimated_time if event and event.estimated_time else 60)
        self.existing_by_emp_day[(s.employee_id, sd)].append({
            'event_ref': s.event_ref_num,
            'event_type': etype,
            'estimated_time': est_time,
        })
```

---

### CRIT-02: CP-SAT `_add_weekly_hours_cap` Creates O(E x D x W) BoolVars Per Employee

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 944-1000

**Problem**: `_add_weekly_hours_cap` iterates over ALL employees, ALL weeks, and within each creates a boolean indicator variable for every (event, day) combination. The same pattern is repeated when `remaining <= 0` (lines 959-975) AND again for the general case (lines 978-997). In total this creates:

```
Variables = employees x weeks x (events x days_per_week)
```

With 15 employees, 3 weeks, 80 events, and ~5 days/week, this is: `15 x 3 x 80 x 5 = 18,000` indicator variables for this single constraint alone. Combined with `_add_emp_day_limits`, `_add_emp_week_limits`, `_add_mutual_exclusion_per_day`, `_add_support_requires_base`, `_add_full_day_exclusivity`, and `_add_block_uniqueness` (all using the same pattern), the total indicator variable count can easily reach **50,000-100,000 BoolVars**.

Each BoolVar requires memory in the CP-SAT model and adds propagation overhead. While CP-SAT can handle millions of variables, the pattern of creating redundant indicator variables (the same (event, emp, day) combo is re-created independently in multiple constraints) inflates the model needlessly.

**Impact**: Model build time grows quadratically. With 150 events and 20 employees, model building can take 10-30 seconds before solving even begins. The 60-second solver timeout may be consumed largely by propagation overhead on redundant indicators.

**Fix**: Create indicator variables once and share them across constraints.

```python
def _build_model(self):
    # ... (after creating v_assign_day and v_assign_emp) ...

    # Pre-compute shared indicator variables: (event_id, emp_id, day) -> BoolVar
    # This is the conjunction assign_emp[e,emp] AND assign_day[e,d]
    self.v_indicator = {}
    for event in self.events:
        eid = event.id
        if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
            continue
        eligible = self.eligible_employees.get(eid, set())
        for emp_id in eligible:
            if (eid, emp_id) not in self.v_assign_emp:
                continue
            for d in self._valid_days_for_event(event):
                if (eid, d) not in self.v_assign_day:
                    continue
                key = (eid, emp_id, d)
                ind = model.NewBoolVar(f'ind_{eid}_{emp_id}_{d}')
                model.AddBoolAnd([
                    self.v_assign_emp[(eid, emp_id)],
                    self.v_assign_day[(eid, d)]
                ]).OnlyEnforceIf(ind)
                model.AddBoolOr([
                    self.v_assign_emp[(eid, emp_id)].Not(),
                    self.v_assign_day[(eid, d)].Not()
                ]).OnlyEnforceIf(ind.Not())
                self.v_indicator[key] = ind

    # Then in each constraint method, reuse self.v_indicator[(eid, emp_id, d)]
    # instead of creating a new BoolVar each time
```

This can reduce total BoolVar count by 5-10x and significantly speed up both model build and solve.

---

### CRIT-03: `_get_ml_affinity_scores` Iterates All Events x All Employees (O(N*M) DB Queries)

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 184-218

**Problem**: When ML is enabled, `_get_ml_affinity_scores()` calls `adapter.rank_employees()` for every event. Each `rank_employees()` call likely queries the database for feature extraction. With 80 events and 15 employees, this is 80 external calls, each processing 15 employees.

```python
for event in self.events:              # O(E)
    ranked = adapter.rank_employees(   # Each call may hit DB for features
        list(self.employees.values()),
        event,
        ...
    )
    for employee, score in ranked:     # O(M)
        scores[(event.project_ref_num, employee.id)] = score
```

**Impact**: With ML enabled, this can add 5-15 seconds of feature extraction and inference time before model building even starts. The ML adapter's `_fallback_rank_employees` is lightweight, but the primary ML path extracts features per-employee per-event.

**Fix**: Batch feature extraction. Pre-compute all employee features once, then score all (event, employee) pairs with vectorized operations.

```python
def _get_ml_affinity_scores(self):
    if not config.get('ML_ENABLED', False):
        return {}
    try:
        from app.ml.inference.ml_scheduler_adapter import MLSchedulerAdapter
        adapter = MLSchedulerAdapter(self.db, self.models, config)

        # Pre-extract employee features once
        employees_list = list(self.employees.values())
        # Use batch_rank if available, else fall back to per-event
        if hasattr(adapter, 'batch_rank_employees'):
            return adapter.batch_rank_employees(employees_list, self.events)

        # Existing fallback (per-event)
        scores = {}
        for event in self.events:
            ranked = adapter.rank_employees(employees_list, event,
                event.start_date if hasattr(event, 'start_date') else datetime.now())
            for employee, score in ranked:
                scores[(event.project_ref_num, employee.id)] = score
        return scores
    except Exception as e:
        logger.warning(f"ML affinity scoring failed: {e}")
        return {}
```

---

## High Findings

### HGH-01: `_post_solve_review` Cross-Run Conflict Check is O(N^2)

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 1833-1860

**Problem**: Check 2 (cross-run conflicts) iterates `core_pending` and for each item, scans ALL other items in `core_pending` to count same-employee/same-day conflicts:

```python
for ps in list(core_pending):          # O(N)
    new_count = sum(
        1 for other in core_pending    # O(N) inner scan
        if other.employee_id == ps.employee_id
        and other is not ps
        and ... == sd
    )
```

With 50 Core pending schedules, this is 2,500 comparisons. With 200, it is 40,000.

**Impact**: Quadratic growth. At 200 Core pending schedules, post-solve review adds noticeable latency (~100-500ms depending on Python overhead).

**Fix**: Pre-group by (employee_id, date) using a defaultdict, then iterate groups once.

```python
# Pre-group for O(N) total
emp_day_groups = defaultdict(list)
for ps in core_pending:
    sd = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
    emp_day_groups[(ps.employee_id, sd)].append(ps)

for (emp_id, day), ps_list in emp_day_groups.items():
    existing_count = self.existing_core_count_by_emp_day.get((emp_id, day), 0)
    total = existing_count + len(ps_list)
    if total > MAX_CORE_EVENTS_PER_DAY:
        excess = total - MAX_CORE_EVENTS_PER_DAY
        for ps in ps_list[-excess:]:
            ps.failure_reason = f"Post-review: conflicts with {existing_count} existing Core event(s)"
            ps.employee_id = None
            ps.schedule_datetime = None
            ps.schedule_time = None
            removed += 1
```

---

### HGH-02: `get_models()` Called Inside Approval Loop

**File**: `/home/elliot/flask-schedule-webapp/app/routes/auto_scheduler.py`, line 860

**Problem**: Inside the `approve_schedule()` loop that processes each pending schedule, `get_models()` is called per iteration:

```python
for pending in pending_schedules:        # Could be 30-80 items
    ...
    all_models = get_models()             # Called once per iteration
    schedule = all_models['Schedule'](...)
```

While `get_models()` likely caches its result internally, calling it inside a tight loop is a code smell and adds function call overhead. The `models` variable is already available at the top of the function (line 670, `models = get_models()`).

**Impact**: Minor per-call overhead (function dispatch + dict lookup), but compounds over 50-80 iterations. Estimated ~1-5ms wasted per run.

**Fix**: Use the `models` variable already obtained at the top of the function.

```python
# Line 860: Replace
all_models = get_models()
# With
# (already have `models` from line 670)
schedule = models['Schedule'](...)
```

---

### HGH-03: CP-SAT `_precompute_availability` Loads Unbounded `.query.all()` Tables

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 377-420

**Problem**: Three separate `.query.all()` calls load entire tables:
- `EmployeeWeeklyAvailability.query.all()` (line 385)
- `EmployeeAvailabilityOverride.query.all()` (line 395)
- `EmployeeTimeOff.query.all()` (line 413)

None are filtered by employee or date range. For EmployeeTimeOff in particular, historical records accumulate forever. Similarly, `LockedDay.query.all()` (line 308), `RotationAssignment.query.all()` (line 427), and `ScheduleException.query.all()` (line 435) load entire tables.

**Impact**: With 500+ historical time-off records and years of schedule exceptions, these queries load unnecessary data into memory and iterate over irrelevant rows. The nested loop on `valid_days` amplifies the cost.

**Fix**: Filter by date range at query time.

```python
# EmployeeTimeOff: only load records overlapping the scheduling horizon
if self.EmployeeTimeOff:
    earliest = self.valid_days[0] if self.valid_days else date.today()
    latest = self.valid_days[-1] if self.valid_days else date.today()
    for to in self.EmployeeTimeOff.query.filter(
        self.EmployeeTimeOff.end_date >= earliest,
        self.EmployeeTimeOff.start_date <= latest,
    ).all():
        for d in self.valid_days:
            if to.start_date <= d <= to.end_date:
                self.unavailable.add((to.employee_id, d))

# LockedDay: filter by date range
if self.LockedDay:
    for ld in self.LockedDay.query.filter(
        self.LockedDay.locked_date >= earliest,
        self.LockedDay.locked_date <= latest,
    ).all():
        self.locked_set.add(ld.locked_date)
```

---

### HGH-04: `_post_solve_review` Event Type Resolution is N+1

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 1797-1802

**Problem**: After the solve, `_post_solve_review` queries event type for each pending schedule individually, even though all events were already loaded during `_load_data()`:

```python
event_type_cache = {}
for ps in pending:
    if ps.event_ref_num not in event_type_cache:
        event = self.Event.query.filter_by(project_ref_num=ps.event_ref_num).first()
        event_type_cache[ps.event_ref_num] = event.event_type if event else 'Unknown'
```

**Impact**: With 80 pending schedules, this fires up to 80 individual queries. These events were already loaded and available in `self.events`.

**Fix**: Reuse the already-loaded event data.

```python
# Build event_type_cache from already-loaded events
event_type_cache = {}
for e in self.events:
    event_type_cache[e.project_ref_num] = self._get_event_type(e)
for s in self.supervisor_events:
    event_type_cache[s.project_ref_num] = 'Supervisor'
```

---

### HGH-05: Fix Wizard `_options_for_reassign` Queries Per Issue

**File**: `/home/elliot/flask-schedule-webapp/app/services/fix_wizard.py`, lines 222-281

**Problem**: For every reassignment issue, the service:
1. Queries the Schedule by ID (line 235)
2. Queries the Event by ref_num (line 239)
3. Instantiates a new `ConstraintValidator` (line 245) -- which itself loads models
4. Calls `get_available_employees()` which queries employees + availability
5. Calls `_score_employee()` for each of up to 8 candidates (line 253)

With 15 fixable issues of the reassign type, this creates 15 ConstraintValidator instances and runs ~120 scoring queries.

**Impact**: The Fix Wizard issues endpoint can take 2-5 seconds for a week with many issues.

**Fix**: Instantiate ConstraintValidator once and reuse across all issues. Cache available employee lists by date.

```python
def get_fixable_issues(self, start_date):
    # Pre-create shared validator
    self._validator = ConstraintValidator(self.db, self.models)
    # ... rest of method
```

---

## Medium Findings

### MED-01: Database Refresh Schedule Preservation Queries Inside Loop

**File**: `/home/elliot/flask-schedule-webapp/app/services/database_refresh_service.py`, lines 150-163

**Problem**: When preserving locally-approved schedules, each pending schedule triggers an individual query to find its matching Schedule record:

```python
for ps in approved_pending:
    existing_schedule = db.session.query(Schedule).filter_by(
        event_ref_num=ps.event_ref_num,
        employee_id=ps.employee_id
    ).first()
```

**Impact**: With 50 locally-approved schedules, this is 50 individual queries during refresh. Refresh is infrequent but user-facing.

**Fix**: Pre-load all schedules into a lookup dictionary.

```python
all_schedules = {(s.event_ref_num, s.employee_id): s for s in Schedule.query.all()}
for ps in approved_pending:
    existing_schedule = all_schedules.get((ps.event_ref_num, ps.employee_id))
```

---

### MED-02: Database Refresh Restoration Loop Queries Per Item

**File**: `/home/elliot/flask-schedule-webapp/app/services/database_refresh_service.py`, lines 238-275

**Problem**: The restoration loop queries `Event.query.filter_by(...)` and `Schedule.query.filter_by(...)` individually for each schedule being restored:

```python
for sched_data in local_schedules:
    event = Event.query.filter_by(project_ref_num=sched_data['event_ref_num']).first()
    ...
    existing = Schedule.query.filter_by(event_ref_num=sched_data['event_ref_num']).first()
```

**Impact**: With 50 restorations, 100 queries. Combined with MED-01, a refresh with many local schedules adds significant latency.

**Fix**: Pre-load both lookups before the loop.

---

### MED-03: AI Tools `_find_employee_fuzzy` Loads All Employees Per Call

**File**: `/home/elliot/flask-schedule-webapp/app/services/ai_tools.py`

**Problem**: AI tools using fuzzy employee matching (e.g., `_tool_reschedule_event`, `_tool_assign_employee_to_event`, `_tool_find_replacement`) likely load all employees and run SequenceMatcher against each name. This is called per tool invocation, and a single AI conversation can invoke multiple tools in sequence.

**Impact**: Each fuzzy match loads all employees (~15-30) and computes string similarity. Individually fast (~5ms), but can compound across multiple tool calls in a conversation turn. Not a major bottleneck at current scale.

**Fix**: Cache the employee list per AITools instance lifetime (it lives for one request).

---

### MED-04: `_valid_days_for_event` Called Repeatedly for Same Event

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`

**Problem**: `_valid_days_for_event(event)` is called multiple times for the same event across `_build_model()`, `_add_hard_constraints()`, `_add_objective()`, `_extract_solution()`, and `_log_solution_explanations()`. Each call recomputes a date list by iterating `self.valid_days`.

The method is called in:
- `_build_model` (line 674)
- `_add_hard_constraints` via H2 (line 739), H3 (implicit), H5/H6 (line 788)
- `_add_emp_day_limits` (indirect)
- `_add_objective` S4 (line 1314), S7 (line 1383), S8 (line 1414)
- `_extract_solution` (line 1648)
- `_log_solution_explanations` (line 1911, 1925, 1940, 1977)

That is roughly 8+ calls per event.

**Impact**: With 80 events and ~15 valid days each, this recomputes 80 x 8 x 15 = 9,600 date comparisons unnecessarily.

**Fix**: Memoize valid days per event during `_load_data()`.

```python
def _load_data(self):
    ...
    # After computing self.valid_days
    self._event_valid_days = {}
    for event in self.events:
        self._event_valid_days[event.id] = self._valid_days_for_event(event)

def _valid_days_for_event(self, event):
    cached = getattr(self, '_event_valid_days', {}).get(event.id)
    if cached is not None:
        return cached
    # ... existing computation ...
```

---

### MED-05: Fix Wizard Generates All Issues Upfront (No Pagination)

**File**: `/home/elliot/flask-schedule-webapp/app/services/fix_wizard.py`, lines 120-172
**File**: `/home/elliot/flask-schedule-webapp/app/routes/dashboard.py`, fix_wizard_issues endpoint

**Problem**: `get_fixable_issues()` runs full weekly validation and generates fix options for ALL issues at once. The endpoint returns the complete list as JSON. For a week with 30+ issues, each requiring database queries for candidate employees, this can be expensive.

**Impact**: First page load of Fix Wizard can take 3-8 seconds depending on issue count. All issues are loaded even though the UI shows them one-by-one.

**Fix**: Add pagination or lazy loading. Generate options on-demand per issue.

```python
# Endpoint: return issues without pre-computed options
@dashboard_bp.route('/api/fix-wizard/issues')
def fix_wizard_issues():
    ...
    issues = service.get_issues_summary(start_date)  # Lightweight
    return jsonify({'issues': issues, 'total': len(issues)})

# Separate endpoint for options
@dashboard_bp.route('/api/fix-wizard/options/<int:index>')
def fix_wizard_options(index):
    ...
    options = service.get_options_for_issue(index)
    return jsonify({'options': options})
```

---

### MED-06: AI Tools Module is 4,344 Lines with 40+ Tool Schemas Loaded Per Request

**File**: `/home/elliot/flask-schedule-webapp/app/services/ai_tools.py`

**Problem**: `get_tool_schemas()` returns a list of ~40 tool schema definitions (each a nested dictionary). These schemas are reconstructed as new Python objects on every call. The tool dispatch map in `execute_tool()` is also rebuilt per call.

**Impact**: ~1-2ms per request for schema construction. Negligible individually but adds up in AI-heavy workflows. The real concern is the serialization cost of sending 40 schemas to the Gemini API for every conversation turn.

**Fix**: Make schemas a class-level constant (computed once, reused).

```python
class AITools:
    _TOOL_SCHEMAS = None

    def get_tool_schemas(self):
        if AITools._TOOL_SCHEMAS is None:
            AITools._TOOL_SCHEMAS = self._build_schemas()
        return AITools._TOOL_SCHEMAS
```

---

### MED-07: `_compute_eligibility` Nested Loop is O(E x M)

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, lines 586-611

**Problem**: For each event, iterates all employees to check eligibility. This is O(events x employees). With 80 events and 15 employees = 1,200 iterations. Not severe at current scale but will degrade with more employees.

**Impact**: Minimal at current scale (~15 employees). Would become a concern with 50+ employees.

**Fix**: Pre-group employees by job title for O(1) lookups.

```python
def _compute_eligibility(self):
    # Pre-group employees by title
    by_title = defaultdict(set)
    for emp_id, emp in self.employees.items():
        by_title[emp.job_title].add(emp_id)

    for event in self.events:
        etype = self._get_event_type(event)
        if etype in JUICER_EVENT_TYPES:
            eligible = by_title.get('Juicer Barista', set()) | by_title.get('Club Supervisor', set())
            # Also add juicer_trained employees
            eligible |= {eid for eid, e in self.employees.items() if e.juicer_trained}
        elif etype in LEAD_ONLY_EVENT_TYPES:
            eligible = by_title.get('Lead Event Specialist', set()) | by_title.get('Club Supervisor', set())
        else:
            eligible = set(self.employees.keys())
        self.eligible_employees[event.id] = eligible
```

---

### MED-08: Frontend Fix Wizard Re-renders Entire DOM on Each Issue

**File**: `/home/elliot/flask-schedule-webapp/app/static/js/pages/fix-wizard.js`, line 159

**Problem**: `renderCurrentIssue()` replaces `root.innerHTML` on every issue transition (line 159). This destroys and recreates the entire DOM subtree, including the progress bar, options, and buttons. This causes a flash of unstyled content and GC pressure from orphaned DOM nodes.

**Impact**: Visible flicker on issue transitions. With 30 issues processed in sequence, 30 full DOM rebuilds. On mobile devices this can cause jank.

**Fix**: Use targeted DOM updates instead of full innerHTML replacement. Update only the changing elements (issue card, options, progress text/bar).

---

## Low Findings

### LOW-01: `to_local_time` Regex on Every Call

**File**: `/home/elliot/flask-schedule-webapp/app/utils/timezone.py`, line 37

**Problem**: `re.sub(r'\b0(\d)', r'\1', formatted)` is called on every datetime formatting. The regex is compiled implicitly each time.

**Impact**: Negligible (~microseconds per call). The `_get_tz` LRU cache is well-designed.

**Fix**: Pre-compile the regex at module level.

```python
_LEADING_ZERO_RE = re.compile(r'\b0(\d)')

def to_local_time(dt, fmt='%m/%d/%Y %I:%M %p', tz_name=None):
    ...
    formatted = _LEADING_ZERO_RE.sub(r'\1', formatted)
```

---

### LOW-02: `ConstraintModifier.__init__` Calls `get_models()` and `get_db()` Per Instantiation

**File**: `/home/elliot/flask-schedule-webapp/app/services/constraint_modifier.py`, lines 81-84

**Problem**: Each time a ConstraintModifier is created (e.g., from AI tool or CP-SAT scheduler), it calls `get_models()` and `get_db()`. These are likely cached, but the SystemSetting query in `get_multipliers()` is not.

**Impact**: Minor. Only called once per scheduler run and once per AI tool invocation.

---

### LOW-03: `Schedule` Model New Columns Lack Indexes

**File**: `/home/elliot/flask-schedule-webapp/app/models/schedule.py`, diff lines

**Problem**: New columns `was_completed`, `was_swapped`, `was_no_show`, and `solver_type` lack database indexes. Future queries filtering by these columns (e.g., ML training data export, outcome reporting) will require full table scans.

**Impact**: No current impact since no queries filter on these yet. Will matter when ML training data pipeline queries `WHERE was_completed = 1 AND solver_type = 'cpsat'`.

**Fix**: Add a composite index for ML training queries.

```python
__table_args__ = (
    ...
    db.Index('idx_schedules_outcomes', 'solver_type', 'was_completed'),
)
```

---

### LOW-04: Approval Workflow Commits Per-Schedule Instead of Batch

**File**: `/home/elliot/flask-schedule-webapp/app/routes/auto_scheduler.py`, approve_schedule function

**Problem**: The approval loop processes each pending schedule individually and relies on a single `db.session.commit()` at the end (implicit via the framework). However, individual API calls to Crossmark within the loop mean a failure partway through leaves some schedules committed and others not. The `sync_enabled=False` path does not commit per-item either, which is correct for batch consistency.

**Impact**: Not a performance issue per se. The risk is a partial-commit state if the process crashes mid-loop. With sync disabled, a crash would lose all approvals in that batch.

**Fix**: Consider explicit batch commit points or savepoints for resilience.

---

## Concurrency and Thread Safety

### CONC-01: CP-SAT Solver Uses `num_workers=4` Without Process Isolation

**File**: `/home/elliot/flask-schedule-webapp/app/services/cpsat_scheduler.py`, line 1614

**Problem**: `solver.parameters.num_workers = 4` enables parallel search within CP-SAT. This is fine for CPU utilization but means the solver will use 4 threads during the solve phase. If the Flask app runs with a threaded server (e.g., `gunicorn --threads 4`), a single solver invocation could starve other request threads.

**Impact**: During a solve (up to 60 seconds), 4 worker threads are consumed. Other requests may experience latency spikes.

**Recommendation**: Run CP-SAT scheduling in a Celery background task (already supported by the architecture) rather than in the request thread. Reduce `num_workers` to 2 for in-request execution.

---

### CONC-02: `ConstraintModifier.clear_all_preferences()` No Transaction Safety

**File**: `/home/elliot/flask-schedule-webapp/app/services/constraint_modifier.py`, lines 205-223

**Problem**: `clear_all_preferences()` iterates settings and deletes them one by one, then commits. If another request reads preferences between the loop start and commit, it may see a partial state.

**Impact**: Low. Preference modification is rare and typically single-user.

---

## Caching Opportunities

### CACHE-01: CP-SAT Data Loading Could Be Cached Across Close-in-Time Runs

**Problem**: Every scheduler run re-loads all employees, events, availability, rotations, and exceptions from scratch. If two runs happen within seconds (e.g., test then real), all data is re-queried.

**Recommendation**: For the immediate term, not critical. For future scale, consider caching the loaded data structures with a TTL of 30 seconds.

---

### CACHE-02: Fix Wizard Weekly Validation Not Cached

**Problem**: Each call to `/api/fix-wizard/issues` runs `WeeklyValidationService.validate_week()` from scratch. If the user refreshes the page or navigates away and back, the same validation runs again.

**Recommendation**: Cache validation results for 60 seconds keyed on `start_date`.

---

## Scalability Concerns

### SCALE-01: SQLite Under Concurrent Load

The application uses SQLite for development and potentially production. SQLite has a single-writer lock, meaning concurrent auto-scheduler runs, approval workflows, AI tool executions, and database refreshes will serialize at the write level. With multiple users, write contention becomes a bottleneck.

**Recommendation**: Migrate to PostgreSQL for production deployments. The existing `DATABASE_URL` configuration supports this.

### SCALE-02: CP-SAT Solver is Compute-Bound and Non-Interruptible

The 60-second solver timeout blocks the request thread. There is no progress reporting or early termination API exposed to the user. If the solver finds a feasible solution quickly but spends 58 more seconds trying to prove optimality, the user waits unnecessarily.

**Recommendation**: Add an intermediate callback that checks if a feasible solution has been found and returns it after a configurable "good enough" timeout (e.g., 10 seconds after first feasible solution).

---

## Recommendations Priority

| Priority | Finding | Estimated Effort | Impact |
|----------|---------|-----------------|--------|
| 1 | CRIT-01: N+1 in `_load_existing_schedules` | 15 min | Eliminate ~200 queries |
| 2 | HGH-04: N+1 in `_post_solve_review` | 10 min | Eliminate ~80 queries |
| 3 | CRIT-02: Shared indicator variables | 2 hours | 5-10x fewer BoolVars |
| 4 | HGH-01: O(N^2) post-solve review | 20 min | Linear from quadratic |
| 5 | HGH-02: `get_models()` outside loop | 5 min | Clean code, minor perf |
| 6 | HGH-03: Filter `.query.all()` by date | 30 min | Reduce memory + query size |
| 7 | MED-04: Memoize `_valid_days_for_event` | 15 min | Avoid redundant computation |
| 8 | HGH-05: Reuse ConstraintValidator | 20 min | Faster Fix Wizard |
| 9 | MED-05: Lazy-load Fix Wizard options | 1 hour | Faster first page load |
| 10 | CRIT-03: Batch ML scoring | 2 hours | 5-15s saved (ML enabled) |
