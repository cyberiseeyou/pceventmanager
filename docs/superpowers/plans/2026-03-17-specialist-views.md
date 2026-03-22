# Specialist Views Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the specialist (non-lead employee) experience with a personal dashboard featuring a weekly calendar grid, a new monthly schedule page, and a locked-down sidebar showing only specialist-relevant pages.

**Architecture:** Six changes: (1) two new API endpoints on `api_bp` for weekly/monthly schedule data, (2) restructured sidebar in `base.html` from two-way to three-way role branching, (3) updated specialist mobile bottom nav, (4) redesigned dashboard template with weekly grid and stats, (5) route cleanup removing dead code and adding monthly page route, (6) CSS updates for the new weekly grid and monthly calendar. All changes use the factory pattern (`get_models()`) and existing auth decorators.

**Tech Stack:** Flask/Jinja2, vanilla JS, existing CSS design system (design-tokens.css variables), SQLAlchemy queries

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/routes/api.py` | Modify | Add `GET /api/my-schedule/weekly` and `GET /api/my-schedule/monthly` endpoints |
| `app/templates/base.html` | Modify | Restructure sidebar to three-way branch (specialist/lead/supervisor); update specialist mobile bottom nav |
| `app/templates/my_dashboard.html` | Modify | Redesign: remove quick actions, notes, upcoming list; add weekly grid, update stats, reorder sections |
| `app/routes/main.py` | Modify | Remove dead code from `my_dashboard()`; add `my_schedule_monthly()` route |
| `app/static/css/pages/my-dashboard.css` | Modify | Add weekly calendar grid styles, update stats for three columns |
| `app/templates/my_schedule_monthly.html` | Create | Monthly calendar page template |
| `app/static/css/pages/my-schedule-monthly.css` | Create | Monthly calendar page styles |

---

### Task 1: New API endpoints (`/api/my-schedule/weekly` and `/api/my-schedule/monthly`)

**Files:**
- Modify: `app/routes/api.py`

- [ ] **Step 1: Add weekly schedule endpoint**

At the end of `app/routes/api.py`, before the "Register modular API endpoint routes" comment block (line 6104), add:

```python
# ── Specialist Personal Schedule Endpoints ──

@api_bp.route('/my-schedule/weekly', methods=['GET'])
@require_authentication()
def my_schedule_weekly():
    """Return the logged-in employee's schedule for a Sun-Sat week.

    Query params:
        week_start: YYYY-MM-DD (defaults to current week's Sunday)

    Returns JSON with days dict, stats (total_hours, days_scheduled, event_count).
    """
    from app.routes.auth import get_current_user

    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Schedule = models['Schedule']
    Event = models['Event']

    user = get_current_user()
    employee_id = user.get('employee_id') if user else None
    if not employee_id:
        return jsonify({'error': 'Not authenticated'}), 401

    # Determine week boundaries (Sunday to Saturday)
    week_start_str = request.args.get('week_start')
    if week_start_str:
        try:
            week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid week_start format. Use YYYY-MM-DD'}), 400
        # Snap to Sunday
        week_start = week_start - timedelta(days=week_start.weekday() + 1) if week_start.weekday() != 6 else week_start
    else:
        today = date.today()
        # Calculate this week's Sunday
        week_start = today - timedelta(days=(today.weekday() + 1) % 7)

    week_end = week_start + timedelta(days=6)

    start_dt = datetime.combine(week_start, datetime.min.time())
    end_dt = datetime.combine(week_end, datetime.max.time())

    rows = db.session.query(Schedule, Event).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).filter(
        Schedule.employee_id == employee_id,
        Schedule.schedule_datetime >= start_dt,
        Schedule.schedule_datetime <= end_dt,
    ).order_by(Schedule.schedule_datetime).all()

    # Build days dict with all 7 days pre-populated
    days = {}
    for i in range(7):
        d = week_start + timedelta(days=i)
        days[d.isoformat()] = []

    total_minutes = 0
    scheduled_dates = set()

    for schedule, event in rows:
        d = schedule.schedule_datetime.date()
        duration = event.estimated_time or Event.get_default_duration(event.event_type)
        total_minutes += duration
        scheduled_dates.add(d)
        days[d.isoformat()].append({
            'schedule_id': schedule.id,
            'time': schedule.schedule_datetime.strftime('%I:%M %p'),
            'event_name': event.project_name,
            'event_type': event.event_type,
            'store_name': event.store_name,
            'estimated_time': duration,
        })

    return jsonify({
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'days': days,
        'stats': {
            'total_hours': round(total_minutes / 60, 1),
            'days_scheduled': len(scheduled_dates),
            'event_count': len(rows),
        },
    })


@api_bp.route('/my-schedule/monthly', methods=['GET'])
@require_authentication()
def my_schedule_monthly():
    """Return the logged-in employee's schedule for an entire month.

    Query params:
        month: YYYY-MM (defaults to current month)

    Returns JSON with month string and days dict.
    """
    from app.routes.auth import get_current_user
    import calendar

    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Schedule = models['Schedule']
    Event = models['Event']

    user = get_current_user()
    employee_id = user.get('employee_id') if user else None
    if not employee_id:
        return jsonify({'error': 'Not authenticated'}), 401

    month_str = request.args.get('month')
    if month_str:
        try:
            year, month = int(month_str.split('-')[0]), int(month_str.split('-')[1])
        except (ValueError, IndexError):
            return jsonify({'error': 'Invalid month format. Use YYYY-MM'}), 400
    else:
        today = date.today()
        year, month = today.year, today.month

    _, last_day = calendar.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    start_dt = datetime.combine(month_start, datetime.min.time())
    end_dt = datetime.combine(month_end, datetime.max.time())

    rows = db.session.query(Schedule, Event).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).filter(
        Schedule.employee_id == employee_id,
        Schedule.schedule_datetime >= start_dt,
        Schedule.schedule_datetime <= end_dt,
    ).order_by(Schedule.schedule_datetime).all()

    days = {}
    for schedule, event in rows:
        d = schedule.schedule_datetime.date().isoformat()
        if d not in days:
            days[d] = []
        duration = event.estimated_time or Event.get_default_duration(event.event_type)
        days[d].append({
            'schedule_id': schedule.id,
            'time': schedule.schedule_datetime.strftime('%I:%M %p'),
            'event_name': event.project_name,
            'event_type': event.event_type,
            'store_name': event.store_name,
            'estimated_time': duration,
        })

    return jsonify({
        'month': f'{year:04d}-{month:02d}',
        'days': days,
    })
```

- [ ] **Step 2: Verify endpoints respond**

```bash
pytest -v -k "test_" --timeout=120 2>&1 | tail -5
```

Confirm no import errors or test regressions.

- [ ] **Step 3: Commit**

```bash
git add app/routes/api.py
git commit -m "feat: add /api/my-schedule/weekly and /api/my-schedule/monthly endpoints"
```

---

### Task 2: Restructure sidebar in `base.html` (three-way branch)

**Files:**
- Modify: `app/templates/base.html`

The sidebar currently uses a two-way branch: `if specialist / else`. This task restructures it to a three-way branch: `if specialist / elif lead / else (supervisor)`. The specialist block is locked down to only 4 items. The lead block (for Spec 3) and supervisor block remain unchanged.

- [ ] **Step 1: Replace the entire sidebar `<nav>` content**

In `app/templates/base.html`, replace lines 190-351 (the `<nav class="sidebar-nav">` through its closing `</nav>`) with:

```html
        <nav class="sidebar-nav">
            {% if current_user_role == 'specialist' %}
            {# ── SPECIALIST SIDEBAR (locked down — 4 items only) ── #}
            <a href="{{ url_for('main.my_dashboard') }}"
                class="sidebar-item {% if request.endpoint == 'main.my_dashboard' %}active{% endif %}">
                <span class="material-symbols-outlined">home</span>
                <span>My Dashboard</span>
            </a>
            <a href="{{ url_for('main.unscheduled_events') }}"
                class="sidebar-item {% if request.endpoint == 'main.unscheduled_events' %}active{% endif %}">
                <span class="material-symbols-outlined">list_alt</span>
                <span>My Events</span>
            </a>
            <a href="{{ url_for('main.my_schedule_monthly') }}"
                class="sidebar-item {% if request.endpoint == 'main.my_schedule_monthly' %}active{% endif %}">
                <span class="material-symbols-outlined">calendar_month</span>
                <span>Monthly Schedule</span>
            </a>
            <a href="{{ url_for('employees.time_off_requests') }}"
                class="sidebar-item {% if request.endpoint == 'employees.time_off_requests' %}active{% endif %}">
                <span class="material-symbols-outlined">event_busy</span>
                <span>Request Time Off</span>
            </a>

            {% elif current_user_role == 'lead' %}
            {# ── LEAD SIDEBAR (placeholder — Spec 3 will customize) ── #}
            <!-- Dashboard -->
            <a href="{{ url_for('dashboard.command_center') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.command_center' or request.endpoint == 'main.index' %}active{% endif %}">
                <span class="material-symbols-outlined">dashboard</span>
                <span>Dashboard</span>
            </a>

            <!-- Schedule Group -->
            <div class="sidebar-group-label">Schedule</div>
            <a href="/schedule/daily/{{ today_date }}"
                class="sidebar-item {% if request.endpoint == 'main.daily_schedule_view' %}active{% endif %}">
                <span class="material-symbols-outlined">today</span>
                <span>Daily View</span>
            </a>
            <a href="{{ url_for('main.calendar_view') }}"
                class="sidebar-item {% if request.endpoint == 'main.calendar_view' %}active{% endif %}">
                <span class="material-symbols-outlined">calendar_month</span>
                <span>Calendar</span>
            </a>

            <!-- Events Group -->
            <div class="sidebar-group-label">Events</div>
            <a href="{{ url_for('main.unscheduled_events') }}"
                class="sidebar-item {% if request.endpoint == 'main.unscheduled_events' %}active{% endif %}">
                <span class="material-symbols-outlined">list_alt</span>
                <span>All Events</span>
            </a>
            <a href="{{ url_for('main.unreported_events') }}"
                class="sidebar-item {% if request.endpoint == 'main.unreported_events' %}active{% endif %}">
                <span class="material-symbols-outlined">report</span>
                <span>Unreported Events</span>
            </a>
            <a href="{{ url_for('dashboard.approved_events') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.approved_events' %}active{% endif %}">
                <span class="material-symbols-outlined">fact_check</span>
                <span>Left in Approved</span>
            </a>
            <a href="{{ url_for('lost_demos.lost_demos_page') }}"
                class="sidebar-item {% if request.endpoint == 'lost_demos.lost_demos_page' %}active{% endif %}">
                <span class="material-symbols-outlined">event_busy</span>
                <span>Lost Demos</span>
            </a>

            <!-- Team Group -->
            <div class="sidebar-group-label">Team</div>
            <a href="{{ url_for('employees.employees') }}"
                class="sidebar-item {% if request.endpoint == 'employees.employees' %}active{% endif %}">
                <span class="material-symbols-outlined">group</span>
                <span>Employees</span>
            </a>
            <a href="{{ url_for('main.attendance_calendar') }}"
                class="sidebar-item {% if request.endpoint == 'main.attendance_calendar' %}active{% endif %}">
                <span class="material-symbols-outlined">how_to_reg</span>
                <span>Attendance</span>
            </a>
            <a href="{{ url_for('employees.time_off_requests') }}"
                class="sidebar-item {% if request.endpoint == 'employees.time_off_requests' %}active{% endif %}">
                <span class="material-symbols-outlined">event_busy</span>
                <span>Availability</span>
            </a>

            <!-- Tools Group -->
            <div class="sidebar-group-label">Tools</div>
            <a href="{{ url_for('printing.printing_home') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('printing.') %}active{% endif %}">
                <span class="material-symbols-outlined">print</span>
                <span>Printing</span>
            </a>

            {% else %}
            {# ── SUPERVISOR SIDEBAR (full access) ── #}
            <!-- Dashboard -->
            <a href="{{ url_for('dashboard.command_center') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.command_center' or request.endpoint == 'main.index' %}active{% endif %}">
                <span class="material-symbols-outlined">dashboard</span>
                <span>Dashboard</span>
            </a>

            <!-- Schedule Group -->
            <div class="sidebar-group-label">Schedule</div>
            <a href="/schedule/daily/{{ today_date }}"
                class="sidebar-item {% if request.endpoint == 'main.daily_schedule_view' %}active{% endif %}">
                <span class="material-symbols-outlined">today</span>
                <span>Daily View</span>
            </a>
            <a href="{{ url_for('main.calendar_view') }}"
                class="sidebar-item {% if request.endpoint == 'main.calendar_view' %}active{% endif %}">
                <span class="material-symbols-outlined">calendar_month</span>
                <span>Calendar</span>
            </a>
            <a href="{{ url_for('auto_scheduler.index') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('auto_scheduler.') and request.endpoint != 'auto_scheduler.notifications' %}active{% endif %}">
                <span class="material-symbols-outlined">smart_toy</span>
                <span>Auto-Scheduler</span>
            </a>
            <a href="{{ url_for('auto_scheduler.notifications') }}"
                class="sidebar-item {% if request.endpoint == 'auto_scheduler.notifications' %}active{% endif %}">
                <span class="material-symbols-outlined">notifications</span>
                <span>Notifications</span>
            </a>

            <!-- Events Group -->
            <div class="sidebar-group-label">Events</div>
            <a href="{{ url_for('main.unscheduled_events') }}"
                class="sidebar-item {% if request.endpoint == 'main.unscheduled_events' %}active{% endif %}">
                <span class="material-symbols-outlined">list_alt</span>
                <span>All Events</span>
            </a>
            <a href="{{ url_for('main.unreported_events') }}"
                class="sidebar-item {% if request.endpoint == 'main.unreported_events' %}active{% endif %}">
                <span class="material-symbols-outlined">report</span>
                <span>Unreported Events</span>
            </a>
            <a href="{{ url_for('dashboard.approved_events') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.approved_events' %}active{% endif %}">
                <span class="material-symbols-outlined">fact_check</span>
                <span>Left in Approved</span>
            </a>
            <a href="{{ url_for('lost_demos.lost_demos_page') }}"
                class="sidebar-item {% if request.endpoint == 'lost_demos.lost_demos_page' %}active{% endif %}">
                <span class="material-symbols-outlined">event_busy</span>
                <span>Lost Demos</span>
            </a>

            <!-- Team Group -->
            <div class="sidebar-group-label">Team</div>
            <a href="{{ url_for('employees.employees') }}"
                class="sidebar-item {% if request.endpoint == 'employees.employees' %}active{% endif %}">
                <span class="material-symbols-outlined">group</span>
                <span>Employees</span>
            </a>
            <a href="{{ url_for('main.attendance_calendar') }}"
                class="sidebar-item {% if request.endpoint == 'main.attendance_calendar' %}active{% endif %}">
                <span class="material-symbols-outlined">how_to_reg</span>
                <span>Attendance</span>
            </a>
            <a href="{{ url_for('employees.time_off_requests') }}"
                class="sidebar-item {% if request.endpoint == 'employees.time_off_requests' %}active{% endif %}">
                <span class="material-symbols-outlined">event_busy</span>
                <span>Availability</span>
            </a>
            <a href="{{ url_for('admin.employee_analytics') }}"
                class="sidebar-item {% if request.endpoint == 'admin.employee_analytics' %}active{% endif %}">
                <span class="material-symbols-outlined">analytics</span>
                <span>Analytics</span>
            </a>

            <!-- Tools Group -->
            <div class="sidebar-group-label">Tools</div>
            <a href="{{ url_for('printing.printing_home') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('printing.') %}active{% endif %}">
                <span class="material-symbols-outlined">print</span>
                <span>Printing</span>
            </a>
            <a href="{{ url_for('dashboard.weekly_validation') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.weekly_validation' %}active{% endif %}">
                <span class="material-symbols-outlined">verified</span>
                <span>Weekly Validation</span>
            </a>
            <a href="{{ url_for('dashboard.employee_availability') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.employee_availability' %}active{% endif %}">
                <span class="material-symbols-outlined">groups</span>
                <span>Employee Availability</span>
            </a>
            <a href="{{ url_for('dashboard.available_blocks') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.available_blocks' %}active{% endif %}">
                <span class="material-symbols-outlined">event_available</span>
                <span>Available Blocks</span>
            </a>
            <a href="{{ url_for('reports.index') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('reports.') %}active{% endif %}">
                <span class="material-symbols-outlined">bar_chart</span>
                <span>Reports</span>
            </a>
            <a href="{{ url_for('dashboard.scan_out_checklist') }}"
                class="sidebar-item {% if request.endpoint == 'dashboard.scan_out_checklist' %}active{% endif %}">
                <span class="material-symbols-outlined">checklist</span>
                <span>Scan-Out Checklist</span>
            </a>
            <a href="{{ url_for('inventory.index') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('inventory.') %}active{% endif %}">
                <span class="material-symbols-outlined">inventory_2</span>
                <span>Demo Supplies</span>
            </a>

            <!-- Admin Group -->
            <div class="sidebar-group-label">Admin</div>
            <a href="{{ url_for('admin.settings_page') }}"
                class="sidebar-item {% if request.endpoint == 'admin.settings_page' %}active{% endif %}">
                <span class="material-symbols-outlined">settings</span>
                <span>Settings</span>
            </a>
            <a href="{{ url_for('admin.event_times_page') }}"
                class="sidebar-item {% if request.endpoint == 'admin.event_times_page' %}active{% endif %}">
                <span class="material-symbols-outlined">schedule</span>
                <span>Event Time Settings</span>
            </a>
            <a href="{{ url_for('rotations.index') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('rotations.') %}active{% endif %}">
                <span class="material-symbols-outlined">sync</span>
                <span>Rotations</span>
            </a>
            <button class="sidebar-item" id="sidebarRefreshBtn" type="button">
                <span class="material-symbols-outlined">database</span>
                <span>Refresh Database</span>
            </button>
            {% endif %}
        </nav>
```

Key changes:
- **Specialist block**: Only 4 items — My Dashboard, My Events, Monthly Schedule, Request Time Off. No group labels needed (flat list). Monthly Schedule points to new `main.my_schedule_monthly` route.
- **Lead block**: New `elif` branch. Contains same items as old `else` block minus supervisor-only items (Auto-Scheduler, Notifications, Analytics, admin tools). Spec 3 will customize further.
- **Supervisor block**: `else` branch. Contains all items from the old `else` block, but now without the scattered `if current_user_role != 'specialist'` and `if current_user_role == 'supervisor'` conditionals (since we know it's supervisor in this branch).

- [ ] **Step 2: Commit**

```bash
git add app/templates/base.html
git commit -m "refactor: restructure sidebar to three-way branch (specialist/lead/supervisor)"
```

---

### Task 3: Update specialist mobile bottom nav

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 1: Replace the specialist mobile bottom nav block**

In `app/templates/base.html`, replace the specialist block in the mobile bottom nav (lines 363-388, the `{% if current_user_role == 'specialist' %}` block through the `{% elif current_user_role == 'lead' %}` line) with:

```html
        {% if current_user_role == 'specialist' %}
        {# Specialist: Home | My Events | Monthly | Time Off #}
        <a href="{{ url_for('main.my_dashboard') }}"
            class="bottom-nav-item {% if request.endpoint == 'main.my_dashboard' %}active{% endif %}"
            data-nav="home">
            <span class="material-symbols-outlined">home</span>
            <span class="bottom-nav-label">Home</span>
        </a>
        <a href="{{ url_for('main.unscheduled_events') }}"
            class="bottom-nav-item {% if request.endpoint == 'main.unscheduled_events' %}active{% endif %}"
            data-nav="events">
            <span class="material-symbols-outlined">list_alt</span>
            <span class="bottom-nav-label">My Events</span>
        </a>
        <a href="{{ url_for('main.my_schedule_monthly') }}"
            class="bottom-nav-item {% if request.endpoint == 'main.my_schedule_monthly' %}active{% endif %}"
            data-nav="monthly">
            <span class="material-symbols-outlined">calendar_month</span>
            <span class="bottom-nav-label">Monthly</span>
        </a>
        <a href="{{ url_for('employees.time_off_requests') }}"
            class="bottom-nav-item {% if request.endpoint == 'employees.time_off_requests' %}active{% endif %}"
            data-nav="timeoff">
            <span class="material-symbols-outlined">event_busy</span>
            <span class="bottom-nav-label">Time Off</span>
        </a>
        {% elif current_user_role == 'lead' %}
```

The change: The old Calendar link (`main.calendar_view`) is replaced with Monthly Schedule (`main.my_schedule_monthly`).

- [ ] **Step 2: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: update specialist mobile bottom nav with Monthly Schedule link"
```

---

### Task 4: Dashboard route cleanup in `main.py` (remove dead code, add monthly route)

**Files:**
- Modify: `app/routes/main.py`

- [ ] **Step 1: Remove dead code from `my_dashboard()` route**

In `app/routes/main.py`, replace the `my_dashboard()` function (lines 62-207) with the cleaned-up version. This removes:
- `upcoming_by_day` computation (lines 137-167) — replaced by weekly API
- `employee_notes` query (lines 191-195) — Notes section removed
- `Note` import (line 77) — no longer needed
- `upcoming_by_day` and `employee_notes` from `render_template()` call
- `time_off_requests` unused default (line 114)
- Fix: initialize `all_time_off_requests` outside the `if` block to prevent NameError

Replace lines 62-207:

```python
@main_bp.route('/my-dashboard')
@require_authentication()
def my_dashboard():
    """Personal dashboard for non-lead employees showing their own schedule,
    time off requests, and weekly stats."""
    from flask import current_app
    from app.models import get_models
    from app.routes.auth import get_current_user

    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Schedule = models['Schedule']
    Event = models['Event']
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']

    user = get_current_user()
    employee_id = user.get('employee_id') if user else None
    first_name = user.get('first_name', 'there') if user else 'there'

    today = date.today()
    now = datetime.now()

    # Greeting based on time of day
    hour = now.hour
    if hour < 12:
        greeting_label = 'Good morning'
    elif hour < 17:
        greeting_label = 'Good afternoon'
    else:
        greeting_label = 'Good evening'

    today_events = []
    next_event = None
    week_event_count = 0
    upcoming_days_working = 0
    scheduled_hours = 0.0
    all_time_off_requests = []

    if employee_id:
        # ── Today's events ──
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        today_schedules = db.session.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee_id,
            Schedule.schedule_datetime >= today_start,
            Schedule.schedule_datetime <= today_end
        ).order_by(Schedule.schedule_datetime).all()

        for schedule, event in today_schedules:
            today_events.append({
                'time': schedule.schedule_datetime.strftime('%I:%M %p'),
                'event_name': event.project_name,
                'event_type': event.event_type,
            })

        # ── Next upcoming event (if no events today) ──
        if not today_events:
            next_row = db.session.query(Schedule, Event).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == employee_id,
                Schedule.schedule_datetime > today_end
            ).order_by(Schedule.schedule_datetime).first()

            if next_row:
                schedule, event = next_row
                next_event = {
                    'date': schedule.schedule_datetime.strftime('%A, %B %-d'),
                    'time': schedule.schedule_datetime.strftime('%I:%M %p'),
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                }

        # ── Week stats (Sun-Sat containing today) ──
        week_start_date = today - timedelta(days=(today.weekday() + 1) % 7)
        week_end_date = week_start_date + timedelta(days=6)
        week_start = datetime.combine(week_start_date, datetime.min.time())
        week_end = datetime.combine(week_end_date, datetime.max.time())

        week_schedules = db.session.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee_id,
            Schedule.schedule_datetime >= week_start,
            Schedule.schedule_datetime <= week_end
        ).all()

        week_event_count = len(week_schedules)
        working_dates = set()
        total_minutes = 0
        for schedule, event in week_schedules:
            working_dates.add(schedule.schedule_datetime.date())
            total_minutes += event.estimated_time or Event.get_default_duration(event.event_type)
        upcoming_days_working = len(working_dates)
        scheduled_hours = round(total_minutes / 60, 1)

        # ── All time off requests (for status tracking) ──
        all_time_off_requests = EmployeeTimeOff.query.filter(
            EmployeeTimeOff.employee_id == employee_id,
            EmployeeTimeOff.end_date >= today
        ).order_by(EmployeeTimeOff.start_date).all()

    return render_template('my_dashboard.html',
        first_name=first_name,
        greeting_label=greeting_label,
        today=today,
        today_events=today_events,
        next_event=next_event,
        week_event_count=week_event_count,
        upcoming_days_working=upcoming_days_working,
        scheduled_hours=scheduled_hours,
        all_time_off_requests=all_time_off_requests,
    )
```

Changes from original:
- Removed `Note` model import (was line 77)
- Removed `upcoming_by_day` computation (was lines 137-167)
- Removed `employee_notes` query (was lines 191-195)
- Removed `upcoming_by_day` and `employee_notes` from render_template
- Added `next_event` computation (for "next upcoming event" when no events today)
- Added `scheduled_hours` stat (sum of estimated_time, converted to hours)
- Changed week stats to query `Schedule+Event` join to get `estimated_time`
- Fixed: `all_time_off_requests` initialized as `[]` outside `if` block
- Removed unused `time_off_requests` default variable

- [ ] **Step 2: Add monthly schedule route**

After the `my_dashboard()` function (and before the `my_schedule_updates()` route), add:

```python
@main_bp.route('/my-schedule/monthly')
@require_authentication()
def my_schedule_monthly():
    """Monthly calendar view for specialists showing their own schedule."""
    return render_template('my_schedule_monthly.html')
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/main.py
git commit -m "refactor: clean up my_dashboard route, add monthly schedule route"
```

---

### Task 5: Redesign dashboard template (`my_dashboard.html`)

**Files:**
- Modify: `app/templates/my_dashboard.html`

- [ ] **Step 1: Replace the entire template**

Replace the full contents of `app/templates/my_dashboard.html` with:

```html
{% extends "base.html" %}

{% block title %}My Dashboard - Product Connections{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/my-dashboard.css') }}">
{% endblock %}

{% block content %}
<div class="my-dash">

    {# ── 1. GREETING + TODAY/NEXT EVENT ── #}
    <div class="my-dash__greeting">
        <p class="my-dash__hello">{{ greeting_label }}</p>
        <h1 class="my-dash__name">{{ first_name }}</h1>
        <p class="my-dash__date">{{ today.strftime('%A, %B %-d, %Y') }}</p>
    </div>

    {% if today_events %}
    <div class="my-dash__today-banner">
        <p class="my-dash__today-label">Today's Schedule</p>
        <p class="my-dash__today-summary">
            {{ today_events|length }} event{{ 's' if today_events|length != 1 else '' }} scheduled
        </p>
        <ul class="my-dash__today-events">
            {% for item in today_events %}
            <li class="my-dash__today-event">
                <span class="my-dash__today-time">{{ item.time }}</span>
                <span class="my-dash__today-event-name">{{ item.event_name }}</span>
                <span class="my-dash__today-event-type">{{ item.event_type }}</span>
            </li>
            {% endfor %}
        </ul>
    </div>
    {% elif next_event %}
    <div class="my-dash__today-banner my-dash__today-banner--next">
        <p class="my-dash__today-label">Next Scheduled Event</p>
        <p class="my-dash__today-summary">{{ next_event.event_name }}</p>
        <div class="my-dash__next-details">
            <span class="my-dash__next-date">{{ next_event.date }}</span>
            <span class="my-dash__next-time">{{ next_event.time }}</span>
            <span class="my-dash__next-type">{{ next_event.event_type }}</span>
        </div>
    </div>
    {% else %}
    <div class="my-dash__today-banner my-dash__today-banner--off">
        <p class="my-dash__today-label">Today's Schedule</p>
        <p class="my-dash__today-summary">No events today</p>
        <p class="my-dash__today-detail">Enjoy your day off, or check Monthly Schedule for upcoming shifts.</p>
    </div>
    {% endif %}

    {# ── 2. STATS CARD — THIS WEEK ── #}
    <div class="my-dash__stats-card">
        <h3 class="my-dash__stats-title">
            <span class="material-symbols-outlined">bar_chart</span>
            This Week
        </h3>
        <div class="my-dash__stats-row">
            <div class="my-dash__stat">
                <span class="my-dash__stat-value">{{ scheduled_hours }}</span>
                <span class="my-dash__stat-label">Scheduled<br>Hours</span>
            </div>
            <div class="my-dash__stat">
                <span class="my-dash__stat-value">{{ upcoming_days_working }}</span>
                <span class="my-dash__stat-label">Days<br>Scheduled</span>
            </div>
            <div class="my-dash__stat">
                <span class="my-dash__stat-value">{{ week_event_count }}</span>
                <span class="my-dash__stat-label">Events</span>
            </div>
        </div>
    </div>

    {# ── 3. WEEKLY CALENDAR GRID ── #}
    <section class="my-dash__weekly">
        <div class="my-dash__section-header">
            <button class="my-dash__week-nav" id="weekPrev" aria-label="Previous week">
                <span class="material-symbols-outlined">chevron_left</span>
            </button>
            <h2 class="my-dash__section-title" id="weekLabel">This Week</h2>
            <button class="my-dash__week-nav" id="weekNext" aria-label="Next week">
                <span class="material-symbols-outlined">chevron_right</span>
            </button>
        </div>
        <div class="my-dash__week-grid" id="weekGrid">
            {# Populated by JavaScript #}
            <div class="my-dash__empty">
                <span class="material-symbols-outlined">hourglass_empty</span>
                Loading schedule...
            </div>
        </div>
    </section>

    {# ── 4. TIME-OFF REQUEST FORM + STATUS LIST ── #}
    <div class="my-dash__info-row">
        {# Request Time Off Card #}
        <div class="my-dash__info-card">
            <h3 class="my-dash__info-card-title">
                <span class="material-symbols-outlined">beach_access</span>
                Request Time Off
            </h3>
            <form id="timeOffForm" class="my-dash__timeoff-form">
                <div class="my-dash__form-row">
                    <div class="my-dash__form-group">
                        <label for="toStartDate" class="my-dash__form-label">From</label>
                        <input type="date" id="toStartDate" name="start_date" required
                               min="{{ today.strftime('%Y-%m-%d') }}" class="my-dash__form-input">
                    </div>
                    <div class="my-dash__form-group">
                        <label for="toEndDate" class="my-dash__form-label">To</label>
                        <input type="date" id="toEndDate" name="end_date" required
                               min="{{ today.strftime('%Y-%m-%d') }}" class="my-dash__form-input">
                    </div>
                </div>
                <div class="my-dash__form-group">
                    <label for="toReason" class="my-dash__form-label">Reason <span style="color:var(--color-neutral-400)">(optional)</span></label>
                    <input type="text" id="toReason" name="reason" maxlength="200"
                           placeholder="e.g. Family event, appointment..."
                           class="my-dash__form-input">
                </div>
                <div id="timeOffMessage" class="my-dash__form-message" hidden></div>
                <button type="submit" class="my-dash__submit-btn" id="timeOffSubmitBtn">
                    <span class="material-symbols-outlined" style="font-size:18px">send</span>
                    Submit Request
                </button>
            </form>
        </div>

        {# Time Off Status Card #}
        <div class="my-dash__info-card">
            <h3 class="my-dash__info-card-title">
                <span class="material-symbols-outlined">event_busy</span>
                My Time Off Requests
            </h3>
            <div id="timeOffRequestsList">
                {% if all_time_off_requests %}
                    {% for req in all_time_off_requests %}
                    <div class="my-dash__timeoff-req my-dash__timeoff-req--{{ req.status }}">
                        <div class="my-dash__timeoff-req-left">
                            <span class="my-dash__timeoff-status-dot"></span>
                            <div>
                                <p class="my-dash__timeoff-dates">
                                    {{ req.start_date.strftime('%b %-d') }}{% if req.start_date != req.end_date %} &ndash; {{ req.end_date.strftime('%b %-d, %Y') }}{% else %}, {{ req.start_date.strftime('%Y') }}{% endif %}
                                </p>
                                {% if req.reason %}
                                <p class="my-dash__timeoff-reason">{{ req.reason }}</p>
                                {% endif %}
                                {% if req.status == 'denied' and req.denial_reason %}
                                <p class="my-dash__timeoff-denial">Reason: {{ req.denial_reason }}</p>
                                {% endif %}
                            </div>
                        </div>
                        <span class="my-dash__timeoff-status-badge">{{ req.status | capitalize }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="my-dash__empty">
                        <span class="material-symbols-outlined">event_available</span>
                        No time off requests yet
                    </div>
                {% endif %}
            </div>
        </div>
    </div>

</div>
{% endblock %}

{% block scripts %}
<!-- Schedule Change Notifications (browser Notification API) -->
<script src="{{ url_for('static', filename='js/components/schedule-change-notifier.js') }}"></script>

<script>
(function() {
    // ===== TIME OFF FORM =====
    const form = document.getElementById('timeOffForm');
    const msgEl = document.getElementById('timeOffMessage');
    const submitBtn = document.getElementById('timeOffSubmitBtn');

    if (form) {
        const startInput = document.getElementById('toStartDate');
        const endInput = document.getElementById('toEndDate');
        startInput.addEventListener('change', function() {
            endInput.min = this.value;
            if (endInput.value && endInput.value < this.value) {
                endInput.value = this.value;
            }
        });

        function showMessage(text, type) {
            msgEl.hidden = false;
            msgEl.textContent = text;
            msgEl.className = 'my-dash__form-message my-dash__form-message--' + type;
        }

        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            msgEl.hidden = true;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting...';

            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

            try {
                const resp = await fetch('/api/my-time-off', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken || '',
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        start_date: startInput.value,
                        end_date: endInput.value,
                        reason: document.getElementById('toReason').value.trim(),
                    }),
                });

                const data = await resp.json();

                if (resp.ok) {
                    showMessage(data.message || 'Request submitted!', 'success');
                    form.reset();
                    setTimeout(() => location.reload(), 1200);
                } else {
                    showMessage(data.error || 'Something went wrong.', 'error');
                }
            } catch (err) {
                showMessage('Network error. Please try again.', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span class="material-symbols-outlined" style="font-size:18px">send</span> Submit Request';
            }
        });
    }

    // ===== WEEKLY CALENDAR GRID =====
    const weekGrid = document.getElementById('weekGrid');
    const weekLabel = document.getElementById('weekLabel');
    const weekPrev = document.getElementById('weekPrev');
    const weekNext = document.getElementById('weekNext');

    // Current week start (Sunday)
    const todayDate = new Date();
    todayDate.setHours(0, 0, 0, 0);
    let currentWeekStart = new Date(todayDate);
    const dayOfWeek = currentWeekStart.getDay(); // 0=Sun
    currentWeekStart.setDate(currentWeekStart.getDate() - dayOfWeek);

    const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    function formatDateISO(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + day;
    }

    function eventAccent(eventType) {
        const t = (eventType || '').toLowerCase();
        if (t.includes('core')) return 'core';
        if (t.includes('juicer')) return 'juicer';
        if (t.includes('digital')) return 'digital';
        if (t.includes('supervisor')) return 'supervisor';
        if (t.includes('freeosk')) return 'freeosk';
        return 'other';
    }

    function updateWeekLabel() {
        const endDate = new Date(currentWeekStart);
        endDate.setDate(endDate.getDate() + 6);

        const startMonth = currentWeekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        const endMonth = endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        weekLabel.textContent = startMonth + ' \u2013 ' + endMonth;
    }

    async function loadWeek() {
        const weekStartStr = formatDateISO(currentWeekStart);
        updateWeekLabel();

        weekGrid.innerHTML = '<div class="my-dash__empty"><span class="material-symbols-outlined">hourglass_empty</span>Loading schedule...</div>';

        try {
            const resp = await fetch('/api/my-schedule/weekly?week_start=' + weekStartStr);
            if (!resp.ok) throw new Error('Failed to load schedule');
            const data = await resp.json();
            renderWeekGrid(data);
        } catch (err) {
            weekGrid.innerHTML = '<div class="my-dash__empty"><span class="material-symbols-outlined">error</span>Error loading schedule</div>';
        }
    }

    function renderWeekGrid(data) {
        const todayStr = formatDateISO(todayDate);
        let html = '<div class="my-dash__week-header">';

        // Header row
        for (let i = 0; i < 7; i++) {
            const d = new Date(currentWeekStart);
            d.setDate(d.getDate() + i);
            const dateStr = formatDateISO(d);
            const isToday = dateStr === todayStr;
            html += '<div class="my-dash__week-day-header' + (isToday ? ' my-dash__week-day-header--today' : '') + '">';
            html += '<span class="my-dash__week-day-name">' + DAY_NAMES[i] + '</span>';
            html += '<span class="my-dash__week-day-num">' + d.getDate() + '</span>';
            html += '</div>';
        }
        html += '</div>';

        // Day cells
        html += '<div class="my-dash__week-cells">';
        for (let i = 0; i < 7; i++) {
            const d = new Date(currentWeekStart);
            d.setDate(d.getDate() + i);
            const dateStr = formatDateISO(d);
            const isToday = dateStr === todayStr;
            const events = data.days[dateStr] || [];

            html += '<div class="my-dash__week-cell' + (isToday ? ' my-dash__week-cell--today' : '') + '">';

            if (events.length === 0) {
                html += '<div class="my-dash__week-empty">&mdash;</div>';
            } else {
                for (const ev of events) {
                    const accent = eventAccent(ev.event_type);
                    const safeName = (ev.event_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    html += '<div class="my-dash__week-event my-dash__week-event--' + accent + '">';
                    html += '<span class="my-dash__week-event-time">' + ev.time + '</span>';
                    html += '<span class="my-dash__week-event-name">' + safeName + '</span>';
                    html += '</div>';
                }
            }

            html += '</div>';
        }
        html += '</div>';

        weekGrid.innerHTML = html;
    }

    // Navigation
    weekPrev.addEventListener('click', function() {
        currentWeekStart.setDate(currentWeekStart.getDate() - 7);
        loadWeek();
    });

    weekNext.addEventListener('click', function() {
        currentWeekStart.setDate(currentWeekStart.getDate() + 7);
        loadWeek();
    });

    // Initial load
    loadWeek();
})();
</script>
{% endblock %}
```

Changes from original:
- **Removed**: Quick Actions section (`.my-dash__actions`)
- **Removed**: Upcoming Schedule section (`upcoming_by_day` loop)
- **Removed**: Notes section (`employee_notes` loop)
- **Added**: "Next Event" banner when no events today (uses `next_event` context)
- **Added**: Three-column stats card (Scheduled Hours, Days Scheduled, Events)
- **Added**: Weekly calendar grid with JS (fetches from `/api/my-schedule/weekly`)
- **Reordered**: Greeting > Today/Next > Stats > Weekly Grid > Time Off
- **Moved**: Time off status list from standalone section into the info-row card alongside the form

- [ ] **Step 2: Commit**

```bash
git add app/templates/my_dashboard.html
git commit -m "feat: redesign specialist dashboard with weekly grid, stats, remove dead sections"
```

---

### Task 6: Dashboard CSS updates

**Files:**
- Modify: `app/static/css/pages/my-dashboard.css`

- [ ] **Step 1: Replace the full CSS file**

Replace the entire contents of `app/static/css/pages/my-dashboard.css` with:

```css
/**
 * My Dashboard - Employee Personal Dashboard
 * A warm, personal work-planner aesthetic for non-lead employees.
 */

/* =============================================
   LAYOUT & PAGE STRUCTURE
   ============================================= */

.my-dash {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--space-4) var(--space-4) var(--space-16);
}

/* =============================================
   GREETING HEADER
   ============================================= */

.my-dash__greeting {
  padding: var(--space-8) 0 var(--space-6);
}

.my-dash__hello {
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-primary-light);
  margin: 0 0 var(--space-1);
}

.my-dash__name {
  font-size: clamp(1.75rem, 5vw, 2.5rem);
  font-weight: 700;
  color: var(--color-neutral-900);
  margin: 0 0 var(--space-2);
  line-height: 1.15;
}

.my-dash__date {
  font-size: var(--font-size-base);
  color: var(--color-neutral-500);
  margin: 0;
  font-weight: 400;
}

/* =============================================
   TODAY BANNER — the hero section
   ============================================= */

.my-dash__today-banner {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  color: #fff;
  margin-bottom: var(--space-6);
  position: relative;
  overflow: hidden;
}

.my-dash__today-banner::after {
  content: '';
  position: absolute;
  top: -40%;
  right: -10%;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  pointer-events: none;
}

.my-dash__today-label {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  opacity: 0.7;
  margin: 0 0 var(--space-3);
}

.my-dash__today-summary {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin: 0 0 var(--space-1);
}

.my-dash__today-detail {
  font-size: var(--font-size-sm);
  opacity: 0.85;
  margin: 0;
}

/* No events state in hero */
.my-dash__today-banner--off {
  background: linear-gradient(135deg, #475569 0%, #64748b 100%);
}

/* Next event state in hero */
.my-dash__today-banner--next {
  background: linear-gradient(135deg, #0e7490 0%, #22d3ee 100%);
}

.my-dash__next-details {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-3);
  font-size: var(--font-size-sm);
  opacity: 0.9;
}

.my-dash__next-date {
  font-weight: 600;
}

.my-dash__next-time {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.my-dash__next-type {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  background: rgba(255, 255, 255, 0.2);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

/* =============================================
   TODAY'S EVENTS LIST (inside banner)
   ============================================= */

.my-dash__today-events {
  list-style: none;
  padding: 0;
  margin: var(--space-4) 0 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.my-dash__today-event {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  backdrop-filter: blur(4px);
}

.my-dash__today-time {
  font-size: var(--font-size-sm);
  font-weight: 700;
  white-space: nowrap;
  min-width: 72px;
  font-variant-numeric: tabular-nums;
}

.my-dash__today-event-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.my-dash__today-event-type {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  background: rgba(255, 255, 255, 0.2);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  white-space: nowrap;
}

/* =============================================
   SECTION HEADINGS
   ============================================= */

.my-dash__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.my-dash__section-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-neutral-800);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.my-dash__section-title .material-symbols-outlined {
  font-size: 20px;
  color: var(--color-primary-light);
}

.my-dash__section-link {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-primary-light);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 2px;
}

.my-dash__section-link:hover {
  text-decoration: underline;
}

/* =============================================
   STATS CARD (This Week — 3-column)
   ============================================= */

.my-dash__stats-card {
  background: var(--color-neutral-50);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  margin-bottom: var(--space-6);
}

.my-dash__stats-title {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-neutral-400);
  margin: 0 0 var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.my-dash__stats-title .material-symbols-outlined {
  font-size: 18px;
}

.my-dash__stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--space-4);
  text-align: center;
}

.my-dash__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
}

.my-dash__stat-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-neutral-900);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.my-dash__stat-label {
  font-size: var(--font-size-sm);
  color: var(--color-neutral-500);
  line-height: 1.3;
}

/* =============================================
   WEEKLY CALENDAR GRID
   ============================================= */

.my-dash__weekly {
  margin-bottom: var(--space-8);
}

.my-dash__weekly .my-dash__section-header {
  justify-content: center;
  gap: var(--space-3);
}

.my-dash__week-nav {
  background: none;
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  padding: var(--space-1);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-neutral-600);
  transition: all var(--transition-fast);
}

.my-dash__week-nav:hover {
  background: var(--color-neutral-100);
  border-color: var(--color-neutral-300);
}

.my-dash__week-nav .material-symbols-outlined {
  font-size: 20px;
}

.my-dash__week-header {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  margin-bottom: 1px;
}

.my-dash__week-day-header {
  text-align: center;
  padding: var(--space-2) var(--space-1);
  background: var(--color-neutral-100);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
}

.my-dash__week-day-header--today {
  background: var(--color-primary);
  color: #fff;
}

.my-dash__week-day-name {
  display: block;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-neutral-500);
}

.my-dash__week-day-header--today .my-dash__week-day-name {
  color: rgba(255, 255, 255, 0.7);
}

.my-dash__week-day-num {
  display: block;
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-neutral-800);
  line-height: 1.3;
}

.my-dash__week-day-header--today .my-dash__week-day-num {
  color: #fff;
}

.my-dash__week-cells {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--color-neutral-200);
  border: 1px solid var(--color-neutral-200);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  overflow: hidden;
}

.my-dash__week-cell {
  background: #fff;
  min-height: 80px;
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.my-dash__week-cell--today {
  background: rgba(27, 155, 216, 0.04);
  border-top: 2px solid var(--color-primary);
}

.my-dash__week-empty {
  font-size: var(--font-size-sm);
  color: var(--color-neutral-300);
  text-align: center;
  padding-top: var(--space-4);
}

/* Event chips inside day cells */
.my-dash__week-event {
  border-left: 3px solid var(--color-neutral-400);
  padding: 3px 6px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--color-neutral-50);
}

.my-dash__week-event--core { border-left-color: var(--color-core); }
.my-dash__week-event--juicer { border-left-color: var(--color-juicer); }
.my-dash__week-event--digital { border-left-color: var(--color-digital); }
.my-dash__week-event--supervisor { border-left-color: var(--color-supervisor); }
.my-dash__week-event--freeosk { border-left-color: var(--color-freeosk); }
.my-dash__week-event--other { border-left-color: var(--color-neutral-400); }

.my-dash__week-event-time {
  display: block;
  font-size: 0.65rem;
  font-weight: 700;
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}

.my-dash__week-event-name {
  display: block;
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--color-neutral-700);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* =============================================
   INFO CARDS ROW (Time Off Form + Status)
   ============================================= */

.my-dash__info-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  margin-bottom: var(--space-8);
}

@media (max-width: 600px) {
  .my-dash__info-row {
    grid-template-columns: 1fr;
  }
}

.my-dash__info-card {
  background: var(--color-neutral-50);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.my-dash__info-card-title {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-neutral-400);
  margin: 0 0 var(--space-3);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.my-dash__info-card-title .material-symbols-outlined {
  font-size: 18px;
}

/* =============================================
   TIME OFF REQUEST FORM
   ============================================= */

.my-dash__timeoff-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.my-dash__form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.my-dash__form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.my-dash__form-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-neutral-500);
}

.my-dash__form-input {
  font-family: var(--font-primary);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-neutral-300);
  border-radius: var(--radius-md);
  background: var(--color-neutral-50);
  color: var(--color-neutral-800);
  transition: border-color var(--transition-fast);
}

.my-dash__form-input:focus {
  outline: none;
  border-color: var(--color-primary-light);
  box-shadow: 0 0 0 3px rgba(27, 155, 216, 0.12);
}

.my-dash__submit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  font-family: var(--font-primary);
  border: none;
  background: var(--color-primary);
  color: #fff;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.my-dash__submit-btn:hover {
  background: var(--color-primary-dark);
}

.my-dash__submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.my-dash__form-message {
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  line-height: 1.4;
}

.my-dash__form-message--success {
  background: #D1FAE5;
  color: #065F46;
}

.my-dash__form-message--error {
  background: #FEE2E2;
  color: #991B1B;
}

/* =============================================
   TIME OFF REQUESTS LIST (status tracking)
   ============================================= */

.my-dash__timeoff-req {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  background: var(--color-neutral-50);
}

.my-dash__timeoff-req + .my-dash__timeoff-req {
  margin-top: var(--space-2);
}

.my-dash__timeoff-req-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.my-dash__timeoff-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.my-dash__timeoff-req--pending .my-dash__timeoff-status-dot { background: #F59E0B; }
.my-dash__timeoff-req--approved .my-dash__timeoff-status-dot { background: #10B981; }
.my-dash__timeoff-req--denied .my-dash__timeoff-status-dot { background: #EF4444; }

.my-dash__timeoff-dates {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-neutral-800);
  margin: 0;
}

.my-dash__timeoff-reason {
  font-size: 0.8rem;
  color: var(--color-neutral-500);
  margin: 2px 0 0;
}

.my-dash__timeoff-status-badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  white-space: nowrap;
  flex-shrink: 0;
}

.my-dash__timeoff-req--pending .my-dash__timeoff-status-badge {
  background: #FEF3C7;
  color: #92400E;
}

.my-dash__timeoff-req--approved .my-dash__timeoff-status-badge {
  background: #D1FAE5;
  color: #065F46;
}

.my-dash__timeoff-req--denied .my-dash__timeoff-status-badge {
  background: #FEE2E2;
  color: #991B1B;
}

.my-dash__timeoff-denial {
  font-size: 0.75rem;
  color: #991B1B;
  margin: 2px 0 0;
  font-style: italic;
}

/* =============================================
   EMPTY STATE
   ============================================= */

.my-dash__empty {
  text-align: center;
  padding: var(--space-6) var(--space-4);
  color: var(--color-neutral-400);
  font-size: var(--font-size-sm);
}

.my-dash__empty .material-symbols-outlined {
  font-size: 32px;
  display: block;
  margin: 0 auto var(--space-2);
  opacity: 0.5;
}

/* =============================================
   RESPONSIVE
   ============================================= */

@media (max-width: 768px) {
  .my-dash {
    padding: var(--space-3) var(--space-3) 100px;
  }

  .my-dash__greeting {
    padding: var(--space-5) 0 var(--space-4);
  }

  .my-dash__today-banner {
    border-radius: var(--radius-lg);
    padding: var(--space-5);
  }

  .my-dash__stats-row {
    gap: var(--space-2);
  }

  .my-dash__stat-value {
    font-size: var(--font-size-xl);
  }
}

@media (max-width: 480px) {
  /* Weekly grid: collapse to list view on very small screens */
  .my-dash__week-header {
    display: none;
  }

  .my-dash__week-cells {
    grid-template-columns: 1fr;
    gap: 0;
    border: none;
    background: transparent;
    border-radius: 0;
  }

  .my-dash__week-cell {
    min-height: auto;
    padding: var(--space-3);
    border-bottom: 1px solid var(--color-neutral-200);
  }

  .my-dash__week-cell::before {
    content: attr(data-day-label);
    display: block;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--color-neutral-500);
    margin-bottom: var(--space-1);
  }

  .my-dash__week-cell--today {
    border-top: none;
    background: rgba(27, 155, 216, 0.06);
    border-left: 3px solid var(--color-primary);
  }
}
```

Changes from original:
- **Removed**: `.my-dash__actions` (quick actions buttons)
- **Removed**: `.my-dash__upcoming`, `.my-dash__day-group`, `.my-dash__event-card`, `.my-dash__event-accent`, `.my-dash__event-body`, `.my-dash__event-top`, `.my-dash__event-title`, `.my-dash__event-time-badge`, `.my-dash__event-meta`, `.my-dash__event-type-label`, `.my-dash__event-store` (upcoming schedule cards)
- **Removed**: `.my-dash__notes`, `.my-dash__note-card`, `.my-dash__note-header`, `.my-dash__note-title`, `.my-dash__note-priority`, `.my-dash__note-content`, `.my-dash__note-due` (notes section)
- **Removed**: `.my-dash__timeoff-list`, `.my-dash__timeoff-item`, `.my-dash__timeoff-icon` (old time-off list format)
- **Added**: `.my-dash__today-banner--next`, `.my-dash__next-details`, `.my-dash__next-date`, `.my-dash__next-time`, `.my-dash__next-type` (next event banner)
- **Added**: `.my-dash__stats-card`, `.my-dash__stats-title`, `.my-dash__stats-row` (standalone 3-column stats card)
- **Added**: `.my-dash__weekly`, `.my-dash__week-nav`, `.my-dash__week-header`, `.my-dash__week-day-header`, `.my-dash__week-day-name`, `.my-dash__week-day-num`, `.my-dash__week-cells`, `.my-dash__week-cell`, `.my-dash__week-empty`, `.my-dash__week-event`, `.my-dash__week-event-time`, `.my-dash__week-event-name` (weekly calendar grid)
- **Added**: 480px mobile breakpoint: weekly grid collapses to stacked list view

- [ ] **Step 2: Commit**

```bash
git add app/static/css/pages/my-dashboard.css
git commit -m "feat: update dashboard CSS with weekly grid, stats card, remove dead sections"
```

---

### Task 7: Monthly schedule page (new template + route + CSS)

**Files:**
- Create: `app/templates/my_schedule_monthly.html`
- Create: `app/static/css/pages/my-schedule-monthly.css`

- [ ] **Step 1: Create monthly schedule template**

Create `app/templates/my_schedule_monthly.html`:

```html
{% extends "base.html" %}

{% block title %}Monthly Schedule - Product Connections{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/my-schedule-monthly.css') }}">
{% endblock %}

{% block content %}
<div class="monthly">
    <div class="monthly__header">
        <button class="monthly__nav" id="monthPrev" aria-label="Previous month">
            <span class="material-symbols-outlined">chevron_left</span>
        </button>
        <h1 class="monthly__title" id="monthTitle">Loading...</h1>
        <button class="monthly__nav" id="monthNext" aria-label="Next month">
            <span class="material-symbols-outlined">chevron_right</span>
        </button>
        <button class="monthly__today-btn" id="monthToday">Today</button>
    </div>

    <div class="monthly__grid-wrapper">
        {# Desktop: 7-column calendar grid #}
        <div class="monthly__day-names">
            <span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span>
        </div>
        <div class="monthly__grid" id="monthGrid">
            <div class="monthly__loading">
                <span class="material-symbols-outlined">hourglass_empty</span>
                Loading schedule...
            </div>
        </div>
    </div>

    {# Mobile: list view fallback #}
    <div class="monthly__list" id="monthList" style="display:none;"></div>

    {# Day detail expansion (shown when clicking a day) #}
    <div class="monthly__detail" id="dayDetail" hidden>
        <div class="monthly__detail-header">
            <h3 class="monthly__detail-title" id="detailTitle"></h3>
            <button class="monthly__detail-close" id="detailClose" aria-label="Close details">
                <span class="material-symbols-outlined">close</span>
            </button>
        </div>
        <div class="monthly__detail-body" id="detailBody"></div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
(function() {
    const monthGrid = document.getElementById('monthGrid');
    const monthList = document.getElementById('monthList');
    const monthTitle = document.getElementById('monthTitle');
    const monthPrev = document.getElementById('monthPrev');
    const monthNext = document.getElementById('monthNext');
    const monthToday = document.getElementById('monthToday');
    const dayDetail = document.getElementById('dayDetail');
    const detailTitle = document.getElementById('detailTitle');
    const detailBody = document.getElementById('detailBody');
    const detailClose = document.getElementById('detailClose');

    const todayDate = new Date();
    todayDate.setHours(0, 0, 0, 0);
    let currentYear = todayDate.getFullYear();
    let currentMonth = todayDate.getMonth(); // 0-based
    let monthData = {};

    const MONTH_NAMES = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];
    const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    function formatDateISO(y, m, d) {
        return y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
    }

    function eventAccent(eventType) {
        const t = (eventType || '').toLowerCase();
        if (t.includes('core')) return 'core';
        if (t.includes('juicer')) return 'juicer';
        if (t.includes('digital')) return 'digital';
        if (t.includes('supervisor')) return 'supervisor';
        if (t.includes('freeosk')) return 'freeosk';
        return 'other';
    }

    function isMobile() {
        return window.innerWidth <= 480;
    }

    async function loadMonth() {
        const monthStr = currentYear + '-' + String(currentMonth + 1).padStart(2, '0');
        monthTitle.textContent = MONTH_NAMES[currentMonth] + ' ' + currentYear;
        dayDetail.hidden = true;

        try {
            const resp = await fetch('/api/my-schedule/monthly?month=' + monthStr);
            if (!resp.ok) throw new Error('Failed to load');
            const data = await resp.json();
            monthData = data.days || {};

            if (isMobile()) {
                renderListView();
            } else {
                renderCalendarGrid();
            }
        } catch (err) {
            monthGrid.innerHTML = '<div class="monthly__loading"><span class="material-symbols-outlined">error</span>Error loading schedule</div>';
        }
    }

    function renderCalendarGrid() {
        monthGrid.style.display = '';
        monthList.style.display = 'none';

        const firstDay = new Date(currentYear, currentMonth, 1).getDay(); // 0=Sun
        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const todayStr = formatDateISO(todayDate.getFullYear(), todayDate.getMonth(), todayDate.getDate());

        let html = '';

        // Leading empty cells
        for (let i = 0; i < firstDay; i++) {
            html += '<div class="monthly__cell monthly__cell--empty"></div>';
        }

        // Day cells
        for (let d = 1; d <= daysInMonth; d++) {
            const dateStr = formatDateISO(currentYear, currentMonth, d);
            const isToday = dateStr === todayStr;
            const events = monthData[dateStr] || [];

            html += '<div class="monthly__cell' + (isToday ? ' monthly__cell--today' : '') + '" data-date="' + dateStr + '">';
            html += '<span class="monthly__cell-num">' + d + '</span>';

            if (events.length > 0) {
                html += '<span class="monthly__cell-badge">' + events.length + '</span>';
                html += '<div class="monthly__cell-dots">';
                // Show unique type dots (max 4)
                const types = [...new Set(events.map(e => eventAccent(e.event_type)))];
                for (const t of types.slice(0, 4)) {
                    html += '<span class="monthly__dot monthly__dot--' + t + '"></span>';
                }
                html += '</div>';
            }

            html += '</div>';
        }

        // Trailing empty cells to fill last row
        const totalCells = firstDay + daysInMonth;
        const remainder = totalCells % 7;
        if (remainder > 0) {
            for (let i = 0; i < 7 - remainder; i++) {
                html += '<div class="monthly__cell monthly__cell--empty"></div>';
            }
        }

        monthGrid.innerHTML = html;

        // Click handler for day cells
        monthGrid.querySelectorAll('.monthly__cell[data-date]').forEach(function(cell) {
            cell.addEventListener('click', function() {
                showDayDetail(this.dataset.date);
            });
        });
    }

    function renderListView() {
        monthGrid.style.display = 'none';
        monthList.style.display = '';

        const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
        const todayStr = formatDateISO(todayDate.getFullYear(), todayDate.getMonth(), todayDate.getDate());
        let html = '';
        let hasAny = false;

        for (let d = 1; d <= daysInMonth; d++) {
            const dateStr = formatDateISO(currentYear, currentMonth, d);
            const events = monthData[dateStr] || [];
            if (events.length === 0) continue;

            hasAny = true;
            const dayName = DAY_NAMES[new Date(currentYear, currentMonth, d).getDay()];
            const isToday = dateStr === todayStr;

            html += '<div class="monthly__list-day' + (isToday ? ' monthly__list-day--today' : '') + '">';
            html += '<div class="monthly__list-day-header">';
            html += '<span class="monthly__list-day-name">' + dayName + '</span>';
            html += '<span class="monthly__list-day-date">' + MONTH_NAMES[currentMonth] + ' ' + d + '</span>';
            html += '</div>';

            for (const ev of events) {
                const accent = eventAccent(ev.event_type);
                const safeName = (ev.event_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const safeStore = (ev.store_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                html += '<div class="monthly__list-event monthly__list-event--' + accent + '">';
                html += '<span class="monthly__list-event-time">' + ev.time + '</span>';
                html += '<span class="monthly__list-event-name">' + safeName + '</span>';
                if (safeStore) {
                    html += '<span class="monthly__list-event-store">' + safeStore + '</span>';
                }
                html += '</div>';
            }

            html += '</div>';
        }

        if (!hasAny) {
            html = '<div class="monthly__loading">No events scheduled this month</div>';
        }

        monthList.innerHTML = html;
    }

    function showDayDetail(dateStr) {
        const events = monthData[dateStr] || [];
        const d = new Date(dateStr + 'T00:00:00');
        detailTitle.textContent = DAY_NAMES[d.getDay()] + ', ' + MONTH_NAMES[d.getMonth()] + ' ' + d.getDate();

        if (events.length === 0) {
            detailBody.innerHTML = '<div class="monthly__loading">No events scheduled</div>';
        } else {
            let html = '';
            for (const ev of events) {
                const accent = eventAccent(ev.event_type);
                const safeName = (ev.event_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const safeStore = (ev.store_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const hours = ev.estimated_time ? (ev.estimated_time / 60).toFixed(1) + ' hrs' : '';

                html += '<div class="monthly__detail-event monthly__detail-event--' + accent + '">';
                html += '<div class="monthly__detail-event-time">' + ev.time + '</div>';
                html += '<div class="monthly__detail-event-info">';
                html += '<div class="monthly__detail-event-name">' + safeName + '</div>';
                html += '<div class="monthly__detail-event-meta">';
                html += '<span>' + (ev.event_type || '') + '</span>';
                if (safeStore) html += '<span>&middot; ' + safeStore + '</span>';
                if (hours) html += '<span>&middot; ' + hours + '</span>';
                html += '</div></div></div>';
            }
            detailBody.innerHTML = html;
        }

        dayDetail.hidden = false;
        dayDetail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Navigation
    monthPrev.addEventListener('click', function() {
        currentMonth--;
        if (currentMonth < 0) { currentMonth = 11; currentYear--; }
        loadMonth();
    });

    monthNext.addEventListener('click', function() {
        currentMonth++;
        if (currentMonth > 11) { currentMonth = 0; currentYear++; }
        loadMonth();
    });

    monthToday.addEventListener('click', function() {
        currentYear = todayDate.getFullYear();
        currentMonth = todayDate.getMonth();
        loadMonth();
    });

    detailClose.addEventListener('click', function() {
        dayDetail.hidden = true;
    });

    // Responsive: switch between grid and list on resize
    let lastMobile = isMobile();
    window.addEventListener('resize', function() {
        const nowMobile = isMobile();
        if (nowMobile !== lastMobile) {
            lastMobile = nowMobile;
            if (nowMobile) {
                renderListView();
            } else {
                renderCalendarGrid();
            }
        }
    });

    // Initial load
    loadMonth();
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Create monthly schedule CSS**

Create `app/static/css/pages/my-schedule-monthly.css`:

```css
/**
 * Monthly Schedule - Personal monthly calendar view for specialists
 */

/* =============================================
   LAYOUT
   ============================================= */

.monthly {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--space-4) var(--space-4) var(--space-16);
}

/* =============================================
   HEADER / NAVIGATION
   ============================================= */

.monthly__header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-6) 0 var(--space-4);
}

.monthly__title {
  font-size: clamp(1.25rem, 3vw, 1.75rem);
  font-weight: 700;
  color: var(--color-neutral-900);
  margin: 0;
  min-width: 200px;
  text-align: center;
}

.monthly__nav {
  background: none;
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  padding: var(--space-1);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-neutral-600);
  transition: all var(--transition-fast);
}

.monthly__nav:hover {
  background: var(--color-neutral-100);
  border-color: var(--color-neutral-300);
}

.monthly__nav .material-symbols-outlined {
  font-size: 20px;
}

.monthly__today-btn {
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  font-family: var(--font-primary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.monthly__today-btn:hover {
  background: var(--color-primary);
  color: #fff;
}

/* =============================================
   DAY NAMES HEADER
   ============================================= */

.monthly__day-names {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  margin-bottom: 1px;
}

.monthly__day-names span {
  text-align: center;
  padding: var(--space-2);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-neutral-500);
  background: var(--color-neutral-100);
}

/* =============================================
   CALENDAR GRID
   ============================================= */

.monthly__grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--color-neutral-200);
  border: 1px solid var(--color-neutral-200);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  overflow: hidden;
}

.monthly__cell {
  background: #fff;
  min-height: 90px;
  padding: var(--space-2);
  cursor: pointer;
  position: relative;
  transition: background var(--transition-fast);
}

.monthly__cell:hover {
  background: var(--color-neutral-50);
}

.monthly__cell--empty {
  background: var(--color-neutral-50);
  cursor: default;
}

.monthly__cell--today {
  background: rgba(27, 155, 216, 0.05);
  box-shadow: inset 0 0 0 2px var(--color-primary);
}

.monthly__cell-num {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-neutral-600);
  display: block;
  margin-bottom: var(--space-1);
}

.monthly__cell--today .monthly__cell-num {
  color: var(--color-primary);
  font-weight: 700;
}

.monthly__cell-badge {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--color-primary);
  color: #fff;
  font-size: 0.65rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}

.monthly__cell-dots {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  margin-top: var(--space-1);
}

.monthly__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.monthly__dot--core { background: var(--color-core); }
.monthly__dot--juicer { background: var(--color-juicer); }
.monthly__dot--digital { background: var(--color-digital); }
.monthly__dot--supervisor { background: var(--color-supervisor); }
.monthly__dot--freeosk { background: var(--color-freeosk); }
.monthly__dot--other { background: var(--color-neutral-400); }

/* =============================================
   DAY DETAIL EXPANSION
   ============================================= */

.monthly__detail {
  margin-top: var(--space-4);
  background: var(--color-neutral-50);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.monthly__detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background: var(--color-neutral-100);
  border-bottom: 1px solid var(--color-neutral-200);
}

.monthly__detail-title {
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-neutral-800);
  margin: 0;
}

.monthly__detail-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-neutral-500);
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
}

.monthly__detail-close:hover {
  background: var(--color-neutral-200);
}

.monthly__detail-body {
  padding: var(--space-3) var(--space-4);
}

.monthly__detail-event {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-left: 3px solid var(--color-neutral-400);
  padding-left: var(--space-3);
}

.monthly__detail-event + .monthly__detail-event {
  border-top: 1px solid var(--color-neutral-200);
}

.monthly__detail-event--core { border-left-color: var(--color-core); }
.monthly__detail-event--juicer { border-left-color: var(--color-juicer); }
.monthly__detail-event--digital { border-left-color: var(--color-digital); }
.monthly__detail-event--supervisor { border-left-color: var(--color-supervisor); }
.monthly__detail-event--freeosk { border-left-color: var(--color-freeosk); }
.monthly__detail-event--other { border-left-color: var(--color-neutral-400); }

.monthly__detail-event-time {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-primary);
  min-width: 72px;
  font-variant-numeric: tabular-nums;
}

.monthly__detail-event-info {
  flex: 1;
  min-width: 0;
}

.monthly__detail-event-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-neutral-800);
}

.monthly__detail-event-meta {
  font-size: 0.8rem;
  color: var(--color-neutral-500);
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-top: 2px;
}

/* =============================================
   MOBILE LIST VIEW (480px fallback)
   ============================================= */

.monthly__list {
  padding-top: var(--space-2);
}

.monthly__list-day {
  margin-bottom: var(--space-4);
}

.monthly__list-day--today {
  border-left: 3px solid var(--color-primary);
  padding-left: var(--space-3);
}

.monthly__list-day-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.monthly__list-day-name {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.monthly__list-day-date {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-neutral-700);
}

.monthly__list-event {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-neutral-50);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-neutral-400);
}

.monthly__list-event + .monthly__list-event {
  margin-top: var(--space-1);
}

.monthly__list-event--core { border-left-color: var(--color-core); }
.monthly__list-event--juicer { border-left-color: var(--color-juicer); }
.monthly__list-event--digital { border-left-color: var(--color-digital); }
.monthly__list-event--supervisor { border-left-color: var(--color-supervisor); }
.monthly__list-event--freeosk { border-left-color: var(--color-freeosk); }
.monthly__list-event--other { border-left-color: var(--color-neutral-400); }

.monthly__list-event-time {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-primary);
  min-width: 72px;
  font-variant-numeric: tabular-nums;
}

.monthly__list-event-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-neutral-700);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.monthly__list-event-store {
  font-size: 0.75rem;
  color: var(--color-neutral-500);
  white-space: nowrap;
}

/* =============================================
   LOADING / EMPTY STATE
   ============================================= */

.monthly__loading {
  text-align: center;
  padding: var(--space-8) var(--space-4);
  color: var(--color-neutral-400);
  font-size: var(--font-size-sm);
  grid-column: 1 / -1;
}

.monthly__loading .material-symbols-outlined {
  font-size: 32px;
  display: block;
  margin: 0 auto var(--space-2);
  opacity: 0.5;
}

/* =============================================
   RESPONSIVE
   ============================================= */

@media (max-width: 768px) {
  .monthly {
    padding: var(--space-3) var(--space-3) 100px;
  }

  .monthly__cell {
    min-height: 70px;
    padding: var(--space-1);
  }

  .monthly__cell-badge {
    top: var(--space-1);
    right: var(--space-1);
  }
}

@media (max-width: 480px) {
  .monthly__grid-wrapper {
    display: none;
  }

  .monthly__list {
    display: block !important;
  }

  .monthly__detail {
    margin-top: var(--space-2);
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/my_schedule_monthly.html app/static/css/pages/my-schedule-monthly.css
git commit -m "feat: add monthly schedule page with calendar grid and mobile list view"
```

---

### Task 8: Verification

- [ ] **Step 1: Run full test suite**

```bash
pytest -v --timeout=120
```

Expected: All tests pass (308+). No regressions from template/route changes.

- [ ] **Step 2: Check for template rendering errors**

```bash
python -c "
from app import create_app
app = create_app()
with app.test_client() as client:
    # These should redirect to login (302), not crash (500)
    r1 = client.get('/my-dashboard')
    r2 = client.get('/my-schedule/monthly')
    r3 = client.get('/api/my-schedule/weekly')
    r4 = client.get('/api/my-schedule/monthly')
    print(f'my-dashboard: {r1.status_code}')
    print(f'my-schedule/monthly: {r2.status_code}')
    print(f'api/weekly: {r3.status_code}')
    print(f'api/monthly: {r4.status_code}')
    assert all(r.status_code in (200, 302) for r in [r1, r2, r3, r4]), 'Unexpected status code!'
    print('All routes accessible (no 500 errors)')
"
```

- [ ] **Step 3: Manual smoke test checklist**

1. Start dev server: `python wsgi.py`
2. Log in as specialist
3. Verify sidebar shows only: My Dashboard, My Events, Monthly Schedule, Request Time Off
4. Verify mobile bottom nav shows: Home, My Events, Monthly, Time Off
5. Verify dashboard shows:
   - Greeting + today's events OR next event banner
   - Stats card with Scheduled Hours, Days Scheduled, Events
   - Weekly calendar grid with events in correct day cells
   - Current day highlighted
   - Week prev/next navigation works
   - Time-off request form submits correctly
   - Time-off status list shows requests with badges
6. Verify NO: Quick Actions, Notes section, Upcoming Schedule list
7. Navigate to Monthly Schedule:
   - Month grid renders with events as dots + count badges
   - Click a day to see event details expand below
   - Month prev/next navigation works
   - "Today" button returns to current month
   - Current day highlighted with border
8. Resize to 480px:
   - Weekly grid collapses to stacked list
   - Monthly grid switches to list view
9. Log in as supervisor - verify full sidebar unchanged
10. Log in as lead - verify lead sidebar renders (same as old supervisor minus admin)
