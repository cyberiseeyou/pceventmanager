# Lead Views Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create lead-specific dashboard additions (team time-off widget) and a new lead daily view page, with updated sidebar, mobile nav, and login routing so leads get a scoped experience distinct from both specialist and supervisor views.

**Architecture:** Builds on top of Spec 2's three-way sidebar branch and redesigned dashboard. Adds one conditional widget to the existing `my_dashboard.html`, creates a new server-rendered lead daily view page, adds one API endpoint for the daily schedule data, and updates the sidebar/mobile-nav lead block. All model access uses `get_models()`.

**Tech Stack:** Flask/Jinja2, vanilla JS, existing CSS design system (`my-dashboard.css` + new `lead-daily-view.css`), server-side rendering for daily view

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/routes/main.py:46-48` | Modify | Update `index()` and `dashboard()` to route leads to `/my-dashboard` |
| `app/routes/main.py:62-207` | Modify | Add `is_lead` to `my_dashboard()` context; add team time-off query; add lead daily view route |
| `app/routes/api.py` | Modify | Add `GET /api/lead/daily-schedule/<date>` endpoint |
| `app/templates/base.html:191-351` | Modify | Fill in the lead sidebar section (between specialist and supervisor blocks) |
| `app/templates/base.html:389-419` | Modify | Update lead mobile bottom nav |
| `app/templates/my_dashboard.html:150-151` | Modify | Add team time-off widget (inside `{% if is_lead %}`) |
| `app/static/css/pages/my-dashboard.css` | Modify | Add team time-off widget styles |
| `app/templates/lead/daily_view.html` | Create | Lead daily view template |
| `app/static/css/pages/lead-daily-view.css` | Create | Lead daily view styles |

---

### Task 1: Update login routing for leads

**Files:**
- Modify: `app/routes/main.py`

- [ ] **Step 1: Update `index()` to route leads to `/my-dashboard`**

In `app/routes/main.py`, replace lines 40-48:

```python
# Before (lines 40-48):
@main_bp.route('/')
@require_authentication()
def index():
    """Redirect to appropriate dashboard based on role"""
    from app.routes.auth import get_current_user
    user = get_current_user()
    if user and user.get('role') == 'specialist':
        return redirect(url_for('main.my_dashboard'))
    return redirect(url_for('dashboard.command_center'))

# After:
@main_bp.route('/')
@require_authentication()
def index():
    """Redirect to appropriate dashboard based on role"""
    from app.routes.auth import get_current_user
    user = get_current_user()
    if user and user.get('role') in ('specialist', 'lead'):
        return redirect(url_for('main.my_dashboard'))
    return redirect(url_for('dashboard.command_center'))
```

- [ ] **Step 2: Update `dashboard()` to route leads to `/my-dashboard`**

In `app/routes/main.py`, replace lines 51-59:

```python
# Before (lines 51-59):
@main_bp.route('/dashboard')
@require_authentication()
def dashboard():
    """Redirect to appropriate dashboard based on role"""
    from app.routes.auth import get_current_user
    user = get_current_user()
    if user and user.get('role') == 'specialist':
        return redirect(url_for('main.my_dashboard'))
    return redirect(url_for('dashboard.command_center'))

# After:
@main_bp.route('/dashboard')
@require_authentication()
def dashboard():
    """Redirect to appropriate dashboard based on role"""
    from app.routes.auth import get_current_user
    user = get_current_user()
    if user and user.get('role') in ('specialist', 'lead'):
        return redirect(url_for('main.my_dashboard'))
    return redirect(url_for('dashboard.command_center'))
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/main.py
git commit -m "feat: route leads to /my-dashboard instead of command center"
```

---

### Task 2: Add lead sidebar section in base.html

**Files:**
- Modify: `app/templates/base.html`

This task assumes Spec 2 has already restructured the sidebar into a three-way branch (`{% if current_user_role == 'specialist' %}` / `{% elif current_user_role == 'lead' %}` / `{% else %}`). This task fills in the lead block with the correct items.

- [ ] **Step 1: Replace the lead sidebar section**

After Spec 2, the sidebar in `base.html` will have a `{% elif current_user_role == 'lead' %}` block. The lead sidebar content should be:

```html
{% elif current_user_role == 'lead' %}
            <!-- Lead Navigation -->
            <a href="{{ url_for('main.my_dashboard') }}"
                class="sidebar-item {% if request.endpoint == 'main.my_dashboard' %}active{% endif %}">
                <span class="material-symbols-outlined">home</span>
                <span>My Dashboard</span>
            </a>
            <a href="/lead/daily/{{ today_date }}"
                class="sidebar-item {% if request.endpoint == 'main.lead_daily_view' %}active{% endif %}">
                <span class="material-symbols-outlined">today</span>
                <span>Team Daily View</span>
            </a>
            <a href="/lead/attendance"
                class="sidebar-item {% if request.endpoint == 'main.lead_attendance' %}active{% endif %}">
                <span class="material-symbols-outlined">how_to_reg</span>
                <span>Lead Attendance</span>
            </a>
            <a href="{{ url_for('main.unscheduled_events') }}"
                class="sidebar-item {% if request.endpoint == 'main.unscheduled_events' %}active{% endif %}">
                <span class="material-symbols-outlined">list_alt</span>
                <span>My Events</span>
            </a>
            <a href="/my-schedule/monthly"
                class="sidebar-item {% if request.endpoint == 'main.my_schedule_monthly' %}active{% endif %}">
                <span class="material-symbols-outlined">calendar_month</span>
                <span>Monthly Schedule</span>
            </a>
            <a href="{{ url_for('employees.time_off_requests') }}"
                class="sidebar-item {% if request.endpoint == 'employees.time_off_requests' %}active{% endif %}">
                <span class="material-symbols-outlined">event_busy</span>
                <span>Request Time Off</span>
            </a>
```

Note: The `/lead/attendance` route will be created by Spec 5 — the sidebar link is placed now so it's ready. The endpoint name `main.lead_attendance` will be a no-op highlight until Spec 5 is implemented.

Note: `/my-schedule/monthly` is the monthly schedule page created by Spec 2. The endpoint name `main.my_schedule_monthly` matches what Spec 2 creates.

- [ ] **Step 2: Verify the three-way branch structure**

After this change, the sidebar `<nav class="sidebar-nav">` should have this structure:

```
{% if current_user_role == 'specialist' %}
    ... (Spec 2 specialist items)
{% elif current_user_role == 'lead' %}
    ... (this task's lead items)
{% else %}
    ... (existing supervisor items, unchanged)
{% endif %}
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add lead sidebar with scoped navigation items"
```

---

### Task 3: Update lead mobile bottom nav

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 1: Replace the lead mobile bottom nav section**

In `app/templates/base.html`, replace the `{% elif current_user_role == 'lead' %}` block in the mobile bottom nav (lines 389-419) with:

```html
        {% elif current_user_role == 'lead' %}
        {# Lead: Home | Team Daily | Attendance | My Events | More #}
        <a href="{{ url_for('main.my_dashboard') }}"
            class="bottom-nav-item {% if request.endpoint == 'main.my_dashboard' %}active{% endif %}"
            data-nav="home">
            <span class="material-symbols-outlined">home</span>
            <span class="bottom-nav-label">Home</span>
        </a>
        <a href="/lead/daily/{{ today_date }}"
            class="bottom-nav-item {% if request.endpoint == 'main.lead_daily_view' %}active{% endif %}"
            data-nav="daily">
            <span class="material-symbols-outlined">today</span>
            <span class="bottom-nav-label">Team Daily</span>
        </a>
        <a href="/lead/attendance"
            class="bottom-nav-item {% if request.endpoint == 'main.lead_attendance' %}active{% endif %}"
            data-nav="attendance">
            <span class="material-symbols-outlined">how_to_reg</span>
            <span class="bottom-nav-label">Attendance</span>
        </a>
        <a href="{{ url_for('main.unscheduled_events') }}"
            class="bottom-nav-item {% if request.endpoint == 'main.unscheduled_events' %}active{% endif %}"
            data-nav="events">
            <span class="material-symbols-outlined">list_alt</span>
            <span class="bottom-nav-label">My Events</span>
        </a>
        <button class="bottom-nav-item" id="bottomNavMore" data-nav="more" aria-label="More options"
            aria-expanded="false">
            <span class="material-symbols-outlined">more_horiz</span>
            <span class="bottom-nav-label">More</span>
        </button>
```

This fixes the pre-existing bug where the lead bottom nav linked to `main.attendance` (a nonexistent endpoint) and replaces generic items with lead-specific navigation.

- [ ] **Step 2: Commit**

```bash
git add app/templates/base.html
git commit -m "fix: update lead mobile bottom nav with correct routes"
```

---

### Task 4: Add team time-off widget to dashboard

**Files:**
- Modify: `app/routes/main.py` (add `is_lead` flag and team time-off query to dashboard context)
- Modify: `app/templates/my_dashboard.html` (add widget HTML)
- Modify: `app/static/css/pages/my-dashboard.css` (add widget styles)

- [ ] **Step 1: Add `is_lead` flag and team time-off query to `my_dashboard()` route**

In `app/routes/main.py`, update the `my_dashboard()` function. After the existing `EmployeeTimeOff` import at line 76, and after the `employee_notes` query block (lines 192-195), add the team time-off query. Then update the `render_template()` call.

Replace the render_template call (lines 197-207):

```python
# Before (lines 197-207):
    return render_template('my_dashboard.html',
        first_name=first_name,
        greeting_label=greeting_label,
        today=today,
        today_events=today_events,
        upcoming_by_day=upcoming_by_day,
        week_event_count=week_event_count,
        upcoming_days_working=upcoming_days_working,
        all_time_off_requests=all_time_off_requests,
        employee_notes=employee_notes,
    )

# After:
    # ── Lead-only: team time off ──
    user_role = user.get('role', '') if user else ''
    is_lead = user_role == 'lead'
    team_time_off = []

    if is_lead and employee_id:
        team_time_off_query = EmployeeTimeOff.query.join(
            Employee, EmployeeTimeOff.employee_id == Employee.id
        ).filter(
            EmployeeTimeOff.status == 'approved',
            EmployeeTimeOff.end_date >= today,
            EmployeeTimeOff.employee_id != employee_id
        ).order_by(EmployeeTimeOff.start_date.asc()).limit(11).all()

        for req in team_time_off_query[:10]:
            emp = Employee.query.get(req.employee_id)
            emp_name = emp.name if emp else 'Unknown'
            team_time_off.append({
                'employee_name': emp_name,
                'start_date': req.start_date,
                'end_date': req.end_date,
            })

    has_more_team_time_off = is_lead and len(team_time_off_query) > 10 if is_lead and employee_id else False

    return render_template('my_dashboard.html',
        first_name=first_name,
        greeting_label=greeting_label,
        today=today,
        today_events=today_events,
        upcoming_by_day=upcoming_by_day,
        week_event_count=week_event_count,
        upcoming_days_working=upcoming_days_working,
        all_time_off_requests=all_time_off_requests,
        employee_notes=employee_notes,
        is_lead=is_lead,
        team_time_off=team_time_off,
        has_more_team_time_off=has_more_team_time_off,
    )
```

Note: We query 11 records but only display 10, so we can determine if there are more (for the "View all" link). The `team_time_off_query` variable is only defined inside the `if is_lead` block, so we guard the `has_more_team_time_off` with that same condition.

- [ ] **Step 2: Add team time-off widget HTML to dashboard template**

In `app/templates/my_dashboard.html`, add the team time-off widget after the time-off section (after line 150, before the upcoming schedule section). Insert between `</section>` (end of time-off requests section) and the `{# -- UPCOMING SCHEDULE -- #}` comment:

```html
    {# ── TEAM TIME OFF (lead only) ── #}
    {% if is_lead %}
    <section class="my-dash__team-timeoff">
        <div class="my-dash__section-header">
            <h2 class="my-dash__section-title">
                <span class="material-symbols-outlined">event_busy</span>
                Team Time Off
            </h2>
        </div>
        {% if team_time_off %}
            {% for item in team_time_off %}
            <div class="my-dash__team-timeoff-item">
                <span class="my-dash__team-timeoff-dot"></span>
                <div class="my-dash__team-timeoff-details">
                    <p class="my-dash__team-timeoff-name">{{ item.employee_name | title }}</p>
                    <p class="my-dash__team-timeoff-dates">
                        {{ item.start_date.strftime('%b %-d') }}{% if item.start_date != item.end_date %} &ndash; {{ item.end_date.strftime('%b %-d, %Y') }}{% else %}, {{ item.start_date.strftime('%Y') }}{% endif %}
                    </p>
                </div>
            </div>
            {% endfor %}
            {% if has_more_team_time_off %}
            <a href="{{ url_for('employees.time_off_requests') }}" class="my-dash__team-timeoff-viewall">
                View all
                <span class="material-symbols-outlined" style="font-size:16px">chevron_right</span>
            </a>
            {% endif %}
        {% else %}
            <div class="my-dash__empty">
                <span class="material-symbols-outlined">event_available</span>
                No upcoming team time off
            </div>
        {% endif %}
    </section>
    {% endif %}
```

- [ ] **Step 3: Add team time-off widget CSS**

Append the following styles to the end of `app/static/css/pages/my-dashboard.css` (before the responsive section, or at the very end):

```css
/* =============================================
   TEAM TIME OFF WIDGET (Lead only)
   ============================================= */

.my-dash__team-timeoff {
  margin-bottom: var(--space-8);
}

.my-dash__team-timeoff-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  background: var(--color-neutral-50);
}

.my-dash__team-timeoff-item + .my-dash__team-timeoff-item {
  margin-top: var(--space-2);
}

.my-dash__team-timeoff-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #10B981;
  flex-shrink: 0;
}

.my-dash__team-timeoff-details {
  min-width: 0;
}

.my-dash__team-timeoff-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-neutral-800);
  margin: 0;
}

.my-dash__team-timeoff-dates {
  font-size: 0.8rem;
  color: var(--color-neutral-500);
  margin: 2px 0 0;
}

.my-dash__team-timeoff-viewall {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-top: var(--space-3);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-primary-light);
  text-decoration: none;
}

.my-dash__team-timeoff-viewall:hover {
  text-decoration: underline;
}
```

- [ ] **Step 4: Commit**

```bash
git add app/routes/main.py app/templates/my_dashboard.html app/static/css/pages/my-dashboard.css
git commit -m "feat: add team time-off widget to lead dashboard"
```

---

### Task 5: Create lead daily view route and API endpoint

**Files:**
- Modify: `app/routes/main.py` (add lead daily view route)
- Modify: `app/routes/api.py` (add `GET /api/lead/daily-schedule/<date>` endpoint)

- [ ] **Step 1: Add the lead daily view route to `main.py`**

Add the following route after the `my_dashboard()` function (after the new render_template block from Task 4). Add the `require_role` import at the top of the file if not already present:

At the top of `app/routes/main.py`, add `require_role` to imports. Find line 7:

```python
# Before (line 7):
from app.routes.auth import require_authentication

# After:
from app.routes.auth import require_authentication, require_role
```

Then add the route (after the `my_dashboard()` function):

```python
@main_bp.route('/lead/daily/<date>')
@require_authentication()
@require_role('lead', 'supervisor')
def lead_daily_view(date):
    """Lead daily view - read-only schedule for all employees on a given date."""
    from app.models import get_models
    from app.routes.auth import get_current_user

    # Validate date format
    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Invalid date format', 'error')
        return redirect(url_for('main.my_dashboard'))

    today_dt = datetime.now().date()
    prev_date = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (selected_date + timedelta(days=1)).strftime('%Y-%m-%d')
    today_str = today_dt.strftime('%Y-%m-%d')
    day_label = selected_date.strftime('%A, %B %-d, %Y')

    return render_template('lead/daily_view.html',
        selected_date=date,
        day_label=day_label,
        prev_date=prev_date,
        next_date=next_date,
        today_str=today_str,
        is_today=(selected_date == today_dt),
    )
```

- [ ] **Step 2: Add the API endpoint to `api.py`**

At the end of `app/routes/api.py` (before any route registration function calls), add:

```python
@api_bp.route('/lead/daily-schedule/<date>', methods=['GET'])
@require_authentication()
@require_role('lead', 'supervisor')
def lead_daily_schedule(date):
    """Get all employee schedules for a given date (lead/supervisor only).
    Returns a simple list of employee name, event name, and scheduled time."""
    from app.routes.auth import get_current_user

    models = get_models()
    Schedule = models['Schedule']
    Event = models['Event']
    Employee = models['Employee']
    db = current_app.extensions['sqlalchemy']

    # Validate date format
    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    day_start = datetime.combine(selected_date, datetime.min.time())
    day_end = datetime.combine(selected_date, datetime.max.time())

    rows = db.session.query(Schedule, Event, Employee).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).outerjoin(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        Schedule.schedule_datetime >= day_start,
        Schedule.schedule_datetime <= day_end
    ).order_by(Schedule.schedule_datetime).all()

    schedules = []
    for schedule, event, employee in rows:
        emp_name = employee.name if employee else (schedule.employee_name or 'Unassigned')
        schedules.append({
            'employee_name': emp_name,
            'event_name': event.project_name,
            'time': schedule.schedule_datetime.strftime('%I:%M %p').lstrip('0'),
        })

    day_label = selected_date.strftime('%A, %B %-d, %Y')

    return jsonify({
        'date': date,
        'day_label': day_label,
        'schedules': schedules,
    })
```

Also ensure `require_role` is imported at the top of `api.py`. Find the auth import line:

```python
# Before:
from app.routes.auth import require_authentication

# After:
from app.routes.auth import require_authentication, require_role
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/main.py app/routes/api.py
git commit -m "feat: add lead daily view route and API endpoint"
```

---

### Task 6: Create lead daily view template and CSS

**Files:**
- Create: `app/templates/lead/daily_view.html`
- Create: `app/static/css/pages/lead-daily-view.css`

- [ ] **Step 1: Create the lead template directory**

```bash
mkdir -p app/templates/lead
```

- [ ] **Step 2: Create `app/templates/lead/daily_view.html`**

```html
{% extends "base.html" %}

{% block title %}Team Daily View - {{ day_label }}{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/lead-daily-view.css') }}">
{% endblock %}

{% block content %}
<div class="lead-daily">

    {# ── HEADER ── #}
    <div class="lead-daily__header">
        <h1 class="lead-daily__title">{{ day_label }}</h1>
        {% if is_today %}
        <span class="lead-daily__today-badge">Today</span>
        {% endif %}
    </div>

    {# ── DATE NAVIGATION ── #}
    <div class="lead-daily__nav">
        <a href="/lead/daily/{{ prev_date }}" class="lead-daily__nav-btn" aria-label="Previous day">
            <span class="material-symbols-outlined">chevron_left</span>
            Prev
        </a>
        {% if not is_today %}
        <a href="/lead/daily/{{ today_str }}" class="lead-daily__nav-btn lead-daily__nav-btn--today">
            Today
        </a>
        {% endif %}
        <a href="/lead/daily/{{ next_date }}" class="lead-daily__nav-btn" aria-label="Next day">
            Next
            <span class="material-symbols-outlined">chevron_right</span>
        </a>
    </div>

    {# ── SCHEDULE TABLE ── #}
    <div class="lead-daily__content">
        <div id="lead-daily-loading" class="lead-daily__loading">
            <div class="lead-daily__spinner"></div>
            Loading schedule...
        </div>
        <div id="lead-daily-error" class="lead-daily__error" hidden>
            <span class="material-symbols-outlined">error</span>
            <p>Error loading schedule. Please try again.</p>
        </div>
        <div id="lead-daily-empty" class="lead-daily__empty" hidden>
            <span class="material-symbols-outlined">event_busy</span>
            <p>No events scheduled for this date</p>
        </div>
        <table id="lead-daily-table" class="lead-daily__table" hidden>
            <thead>
                <tr>
                    <th class="lead-daily__th">Employee</th>
                    <th class="lead-daily__th">Event</th>
                    <th class="lead-daily__th lead-daily__th--time">Time</th>
                </tr>
            </thead>
            <tbody id="lead-daily-tbody">
            </tbody>
        </table>
    </div>

</div>
{% endblock %}

{% block scripts %}
<script>
(function() {
    const selectedDate = '{{ selected_date }}';

    async function loadSchedule() {
        const loading = document.getElementById('lead-daily-loading');
        const error = document.getElementById('lead-daily-error');
        const empty = document.getElementById('lead-daily-empty');
        const table = document.getElementById('lead-daily-table');
        const tbody = document.getElementById('lead-daily-tbody');

        loading.hidden = false;
        error.hidden = true;
        empty.hidden = true;
        table.hidden = true;

        try {
            const response = await fetch('/api/lead/daily-schedule/' + selectedDate);
            if (!response.ok) throw new Error('Failed to load schedule');

            const data = await response.json();
            loading.hidden = true;

            if (!data.schedules || data.schedules.length === 0) {
                empty.hidden = false;
                return;
            }

            tbody.innerHTML = data.schedules.map(function(s) {
                return '<tr class="lead-daily__row">' +
                    '<td class="lead-daily__td lead-daily__td--employee">' + escapeHtml(toTitleCase(s.employee_name)) + '</td>' +
                    '<td class="lead-daily__td lead-daily__td--event">' + escapeHtml(s.event_name) + '</td>' +
                    '<td class="lead-daily__td lead-daily__td--time">' + escapeHtml(s.time) + '</td>' +
                    '</tr>';
            }).join('');

            table.hidden = false;
        } catch (err) {
            console.error('Error loading lead daily schedule:', err);
            loading.hidden = true;
            error.hidden = false;
        }
    }

    document.addEventListener('DOMContentLoaded', loadSchedule);
})();
</script>
{% endblock %}
```

Note: `escapeHtml` and `toTitleCase` are globally available from `text-utils.js` which is loaded in `base.html`.

- [ ] **Step 3: Create `app/static/css/pages/lead-daily-view.css`**

```css
/**
 * Lead Daily View - Read-only schedule view for leads
 */

/* =============================================
   LAYOUT
   ============================================= */

.lead-daily {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--space-4) var(--space-4) var(--space-16);
}

/* =============================================
   HEADER
   ============================================= */

.lead-daily__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-6) 0 var(--space-2);
}

.lead-daily__title {
  font-size: clamp(1.25rem, 4vw, 1.75rem);
  font-weight: 700;
  color: var(--color-neutral-900);
  margin: 0;
  line-height: 1.2;
}

.lead-daily__today-badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
}

/* =============================================
   DATE NAVIGATION
   ============================================= */

.lead-daily__nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-neutral-200);
}

.lead-daily__nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  font-family: var(--font-primary);
  text-decoration: none;
  border: 1px solid var(--color-neutral-200);
  background: var(--color-neutral-50);
  color: var(--color-neutral-700);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.lead-daily__nav-btn:hover {
  background: var(--color-neutral-100);
  border-color: var(--color-neutral-300);
  box-shadow: var(--shadow-xs);
}

.lead-daily__nav-btn .material-symbols-outlined {
  font-size: 18px;
}

.lead-daily__nav-btn--today {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.lead-daily__nav-btn--today:hover {
  background: var(--color-primary-dark);
  border-color: var(--color-primary-dark);
  color: #fff;
}

/* =============================================
   CONTENT STATES
   ============================================= */

.lead-daily__loading {
  text-align: center;
  padding: var(--space-8) var(--space-4);
  color: var(--color-neutral-400);
  font-size: var(--font-size-sm);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}

.lead-daily__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-neutral-200);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: lead-daily-spin 0.8s linear infinite;
}

@keyframes lead-daily-spin {
  to { transform: rotate(360deg); }
}

.lead-daily__error {
  text-align: center;
  padding: var(--space-8) var(--space-4);
  color: #991B1B;
  font-size: var(--font-size-sm);
}

.lead-daily__error .material-symbols-outlined {
  font-size: 32px;
  display: block;
  margin: 0 auto var(--space-2);
  opacity: 0.6;
}

.lead-daily__error p {
  margin: 0;
}

.lead-daily__empty {
  text-align: center;
  padding: var(--space-8) var(--space-4);
  color: var(--color-neutral-400);
  font-size: var(--font-size-sm);
}

.lead-daily__empty .material-symbols-outlined {
  font-size: 32px;
  display: block;
  margin: 0 auto var(--space-2);
  opacity: 0.5;
}

.lead-daily__empty p {
  margin: 0;
}

/* =============================================
   SCHEDULE TABLE
   ============================================= */

.lead-daily__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.lead-daily__th {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-neutral-400);
  border-bottom: 2px solid var(--color-neutral-200);
}

.lead-daily__th--time {
  text-align: right;
  white-space: nowrap;
}

.lead-daily__row {
  transition: background var(--transition-fast);
}

.lead-daily__row:hover {
  background: var(--color-neutral-50);
}

.lead-daily__td {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-neutral-100);
  color: var(--color-neutral-700);
}

.lead-daily__td--employee {
  font-weight: 600;
  color: var(--color-neutral-800);
  white-space: nowrap;
}

.lead-daily__td--event {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lead-daily__td--time {
  text-align: right;
  white-space: nowrap;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-primary);
}

/* =============================================
   RESPONSIVE
   ============================================= */

@media (max-width: 768px) {
  .lead-daily {
    padding: var(--space-3) var(--space-3) 100px;
  }

  .lead-daily__header {
    padding: var(--space-4) 0 var(--space-2);
  }

  .lead-daily__th,
  .lead-daily__td {
    padding: var(--space-2) var(--space-3);
  }

  .lead-daily__td--event {
    max-width: 160px;
  }
}

@media (max-width: 480px) {
  .lead-daily__table {
    font-size: 0.8rem;
  }

  .lead-daily__th,
  .lead-daily__td {
    padding: var(--space-2);
  }

  .lead-daily__td--employee {
    min-width: 80px;
  }

  .lead-daily__td--event {
    max-width: 120px;
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/lead/daily_view.html app/static/css/pages/lead-daily-view.css
git commit -m "feat: create lead daily view template and styles"
```

---

### Task 7: Verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v --timeout=120`
Expected: All tests pass (308+).

- [ ] **Step 2: Manual smoke test checklist**

1. Start dev server: `python wsgi.py`
2. **Lead login routing:**
   - Log in as lead
   - Verify redirect goes to `/my-dashboard` (not command center)
3. **Lead sidebar:**
   - Verify sidebar shows exactly: My Dashboard, Team Daily View, Lead Attendance, My Events, Monthly Schedule, Request Time Off
   - Verify NO supervisor items visible (Dashboard, Calendar, Auto-Scheduler, Notifications, Unreported Events, etc.)
   - Click each sidebar item and verify correct page loads (Lead Attendance may 404 until Spec 5)
4. **Lead mobile bottom nav:**
   - Resize to mobile width (< 768px)
   - Verify bottom nav shows: Home, Team Daily, Attendance, My Events, More
   - Verify "More" button opens sidebar
   - Verify no broken links (no `main.attendance` 500 error)
5. **Lead dashboard - team time-off widget:**
   - On `/my-dashboard` as lead, verify "Team Time Off" section appears below "My Time Off Requests"
   - If approved time-off exists for other employees, verify entries show name (title case) and date range
   - Verify NO reason is displayed (privacy)
   - Verify lead's OWN time off is NOT in the team widget
   - If more than 10 entries, verify "View all" link appears
   - If no team time off, verify "No upcoming team time off" empty state
6. **Specialist dashboard - no team time-off widget:**
   - Log in as specialist
   - Navigate to `/my-dashboard`
   - Verify "Team Time Off" section is NOT present
7. **Lead daily view:**
   - As lead, click "Team Daily View" in sidebar
   - Verify page shows today's date with day-of-week (e.g., "Monday, March 17, 2026")
   - Verify "Today" badge is visible
   - Verify schedule table shows Employee, Event, Time columns
   - Verify data loads via API and displays correctly
   - Click "Prev" — verify previous day loads, "Today" button appears
   - Click "Next" — verify next day loads
   - Click "Today" — verify return to today
   - Navigate to a date with no events — verify empty state
8. **Lead daily view - read only:**
   - Verify NO edit buttons, no reassign actions, no delete, no condition tracking
   - Verify page is purely informational
9. **API endpoint:**
   - Hit `/api/lead/daily-schedule/2026-03-17` as lead — verify JSON with date, day_label, schedules array
   - Hit same endpoint as specialist — verify 403 forbidden
10. **Supervisor unchanged:**
    - Log in as supervisor
    - Verify supervisor still sees full sidebar (unchanged)
    - Verify supervisor still goes to command center on login
    - Verify supervisor CAN access `/lead/daily/<date>` (dual role access)

- [ ] **Step 3: Verify acceptance criteria**

- [ ] Lead login redirects to `/my-dashboard` (not command center)
- [ ] Lead sidebar shows only: My Dashboard, Team Daily View, Lead Attendance, My Events, Monthly Schedule, Request Time Off
- [ ] Lead mobile bottom nav updated to match sidebar
- [ ] Lead dashboard shows personal stats, weekly grid, time-off (same as specialist)
- [ ] Lead dashboard additionally shows "Team Time Off" widget with approved time-off (no reason)
- [ ] Specialist dashboard does NOT show the team time-off widget
- [ ] Lead daily view shows: employee name, event name, scheduled time — nothing else
- [ ] Lead daily view has prev/next day navigation
- [ ] Lead daily view is read-only (no edit/reassign/delete actions)
- [ ] Supervisor views are unchanged
