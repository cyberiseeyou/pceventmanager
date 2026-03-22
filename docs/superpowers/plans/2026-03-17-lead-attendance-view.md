# Lead Attendance View Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a lead-specific attendance page at `/lead/attendance` that mirrors the supervisor's attendance calendar but enforces locking rules — leads can submit new records but cannot edit or delete existing ones.

**Architecture:** New route in `main.py` with `@require_role('lead')`, new Jinja template extending `base.html`, new CSS file reusing the supervisor attendance calendar design system, new JS file that renders a monthly calendar grid, fetches scheduled employees per date, and submits new records via `POST /api/attendance`. Existing API endpoints are reused — locking is enforced server-side by Spec 4.

**Tech Stack:** Flask/Jinja2, vanilla JS (class-based like `AttendanceCalendar`), existing CSS design tokens, existing REST API endpoints (`/api/attendance/month/<date>`, `/api/attendance/scheduled-employees/<date>`, `POST /api/attendance`)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/routes/main.py` | Modify | Add `/lead/attendance` and `/lead/attendance/<date>` routes |
| `app/templates/lead/attendance.html` | Create | Lead attendance page template (calendar grid + day detail panel) |
| `app/static/css/pages/lead-attendance.css` | Create | Lead attendance styles (based on `attendance-calendar.css`) |
| `app/static/js/pages/lead-attendance.js` | Create | Lead attendance JS (calendar rendering, day selection, submit new records) |

---

### Task 1: Add lead attendance route in main.py

**Files:**
- Modify: `app/routes/main.py` (lines 1-13 for imports, after line 1113 for new route)

- [ ] **Step 1: Add `require_role` import**

At line 7 of `app/routes/main.py`, change:

```python
# Before:
from app.routes.auth import require_authentication

# After:
from app.routes.auth import require_authentication, require_role
```

- [ ] **Step 2: Add the lead attendance route**

After line 1113 (end of `attendance_calendar` function), add the new route:

```python
@main_bp.route('/lead/attendance')
@main_bp.route('/lead/attendance/<date>')
@require_authentication()
@require_role('lead')
def lead_attendance(date=None):
    """
    Lead attendance calendar view.

    Spec 5: Lead-specific attendance page. Same visual layout as supervisor's
    attendance calendar but leads can only submit new records — existing records
    are read-only (locking enforced by API via Spec 4).

    Args:
        date: Optional date string in 'YYYY-MM-DD' format for month selection
    """
    from app.models import get_models
    from app.routes.auth import get_current_user
    models = get_models()

    # Get models
    Employee = models['Employee']

    # Parse date parameter for month selection
    if date:
        try:
            selected_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        date_str = request.args.get('date')
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = date.today()
        else:
            selected_date = date.today()

    # Calculate month boundaries
    start_of_month = selected_date.replace(day=1)
    if start_of_month.month == 12:
        end_of_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        end_of_month = start_of_month.replace(month=start_of_month.month + 1)

    # Get all active employees for the filter selector
    all_employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()

    # Get selected employee if specified via query param
    selected_employee = None
    employee_id = request.args.get('employee_id')
    if employee_id:
        selected_employee = Employee.query.get(employee_id)

    # Calculate previous and next months
    if start_of_month.month == 1:
        prev_month = start_of_month.replace(year=start_of_month.year - 1, month=12)
    else:
        prev_month = start_of_month.replace(month=start_of_month.month - 1)

    if start_of_month.month == 12:
        next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        next_month = start_of_month.replace(month=start_of_month.month + 1)

    # Get current user info for template
    user = get_current_user()

    return render_template('lead/attendance.html',
                         selected_date=selected_date,
                         start_of_month=start_of_month,
                         end_of_month=end_of_month,
                         prev_month=prev_month,
                         next_month=next_month,
                         all_employees=all_employees,
                         selected_employee=selected_employee,
                         current_username=user.get('username', 'Unknown') if user else 'Unknown')
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/main.py
git commit -m "feat: add lead attendance route at /lead/attendance"
```

---

### Task 2: Create lead attendance HTML template

**Files:**
- Create: `app/templates/lead/attendance.html`

First, create the `lead/` template directory:

```bash
mkdir -p app/templates/lead
```

- [ ] **Step 1: Create the template file**

Create `app/templates/lead/attendance.html` with the following complete content:

```html
{% extends "base.html" %}

{% block title %}Attendance Calendar - {{ selected_date.strftime('%B %Y') }}{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/lead-attendance.css') }}?v={{ config.get('VERSION', '1.0') }}">
{% endblock %}

{% block content %}
<div class="lead-attendance-container" data-selected-date="{{ selected_date.strftime('%Y-%m-%d') }}" data-username="{{ current_username }}">
  <!-- Header Section -->
  <div class="attendance-header">
    <div class="header-row">
      <h1 class="page-title">Attendance Calendar</h1>

      <!-- Employee Selector -->
      <div class="employee-selector-container">
        <label for="employee-selector" class="selector-label">View Employee:</label>
        <select id="employee-selector" class="employee-selector" aria-label="Select employee to view attendance">
          <option value="">All Employees</option>
          {% for employee in all_employees %}
          <option value="{{ employee.id }}" {% if selected_employee and selected_employee.id == employee.id %}selected{% endif %}>
            {{ employee.name|title }}
          </option>
          {% endfor %}
        </select>
      </div>
    </div>

    <!-- Month Navigation -->
    <div class="month-navigation">
      <a href="?date={{ prev_month.strftime('%Y-%m-%d') }}{% if selected_employee %}&employee_id={{ selected_employee.id }}{% endif %}"
         class="btn-nav btn-nav-prev"
         aria-label="Previous month">
        &larr; {{ prev_month.strftime('%B') }}
      </a>

      <h2 class="current-month">
        {{ selected_date.strftime('%B %Y').upper() }}
      </h2>

      <a href="?date={{ next_month.strftime('%Y-%m-%d') }}{% if selected_employee %}&employee_id={{ selected_employee.id }}{% endif %}"
         class="btn-nav btn-nav-next"
         aria-label="Next month">
        {{ next_month.strftime('%B') }} &rarr;
      </a>
    </div>
  </div>

  <!-- Legend Section -->
  <div class="attendance-legend">
    <h3 class="legend-title">Attendance Status Legend:</h3>
    <div class="legend-items">
      <div class="legend-item">
        <span class="legend-badge legend-badge--on_time"></span>
        <span class="legend-label">On-Time</span>
      </div>
      <div class="legend-item">
        <span class="legend-badge legend-badge--late"></span>
        <span class="legend-label">Late</span>
      </div>
      <div class="legend-item">
        <span class="legend-badge legend-badge--called_in"></span>
        <span class="legend-label">Called-In</span>
      </div>
      <div class="legend-item">
        <span class="legend-badge legend-badge--no_call_no_show"></span>
        <span class="legend-label">No-Call-No-Show</span>
      </div>
      <div class="legend-item">
        <span class="legend-badge legend-badge--excused_absence"></span>
        <span class="legend-label">Excused Absence</span>
      </div>
      <div class="legend-item">
        <span class="legend-badge legend-badge--no_data"></span>
        <span class="legend-label">No Data</span>
      </div>
    </div>
  </div>

  <!-- Statistics Summary -->
  <div id="attendance-stats" class="attendance-stats">
    <div class="loading-spinner" role="status" aria-live="polite">
      <span class="sr-only">Loading statistics...</span>
      Loading...
    </div>
  </div>

  <!-- Calendar Grid -->
  <div class="calendar-container">
    <div class="calendar-header">
      <div class="calendar-day-name">Sun</div>
      <div class="calendar-day-name">Mon</div>
      <div class="calendar-day-name">Tue</div>
      <div class="calendar-day-name">Wed</div>
      <div class="calendar-day-name">Thu</div>
      <div class="calendar-day-name">Fri</div>
      <div class="calendar-day-name">Sat</div>
    </div>

    <div id="calendar-grid" class="calendar-grid">
      <div class="loading-spinner" role="status" aria-live="polite">
        <span class="sr-only">Loading calendar...</span>
        Loading calendar...
      </div>
    </div>
  </div>

  <!-- Day Detail Panel (populated by JS when a date is clicked) -->
  <div id="date-detail-container" class="date-detail-container" style="display: none;">
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/pages/lead-attendance.js') }}?v={{ config.get('VERSION', '1.0') }}" defer></script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/lead/attendance.html
git commit -m "feat: create lead attendance HTML template"
```

---

### Task 3: Create lead attendance CSS

**Files:**
- Create: `app/static/css/pages/lead-attendance.css`

- [ ] **Step 1: Create the CSS file**

This file reuses the visual design of the supervisor attendance calendar (`attendance-calendar.css`) but scoped to `.lead-attendance-container`. It also adds styles for the locked-record indicator, the submit-attendance form in the day detail panel, and the audit trail display.

Create `app/static/css/pages/lead-attendance.css` with the following complete content:

```css
/**
 * LEAD ATTENDANCE CALENDAR VIEW (Spec 5)
 *
 * Lead-specific attendance page styles.
 * Based on the supervisor attendance calendar design but with:
 * - No edit/delete button styles
 * - Lock icon on existing records
 * - Submit form for new records
 * - Audit trail display (recorded by, modified by)
 */

/* ===================================================================
   Container & Layout
   =================================================================== */

.lead-attendance-container {
    padding: 24px;
    max-width: 1400px;
    margin: 0 auto;
}

/* ===================================================================
   Header Section
   =================================================================== */

.attendance-header {
    margin-bottom: 32px;
}

.header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
}

.page-title {
    font-size: 28px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
    margin: 0;
}

/* Employee Selector */
.employee-selector-container {
    display: flex;
    align-items: center;
    gap: 12px;
}

.selector-label {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-neutral-700, #374151);
    white-space: nowrap;
}

.employee-selector {
    padding: 8px 16px;
    font-size: 14px;
    border: 1px solid var(--color-neutral-300, #D1D5DB);
    border-radius: 6px;
    background: white;
    color: var(--color-neutral-900, #111827);
    cursor: pointer;
    min-width: 200px;
    transition: border-color 0.2s ease;
}

.employee-selector:hover {
    border-color: var(--color-primary-500, #3B82F6);
}

.employee-selector:focus {
    outline: 2px solid var(--color-primary-500, #3B82F6);
    outline-offset: 2px;
    border-color: var(--color-primary-500, #3B82F6);
}

/* Month Navigation */
.month-navigation {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 24px;
    padding: 16px 0;
}

.current-month {
    font-size: 24px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
    margin: 0;
    min-width: 200px;
    text-align: center;
}

.btn-nav {
    padding: 10px 20px;
    font-size: 16px;
    font-weight: 600;
    color: var(--color-primary-600, #2563EB);
    background: var(--color-primary-50, #EFF6FF);
    border: 1px solid var(--color-primary-300, #93C5FD);
    border-radius: 8px;
    text-decoration: none;
    transition: all 0.2s ease;
    cursor: pointer;
}

.btn-nav:hover {
    background: var(--color-primary-100, #DBEAFE);
    border-color: var(--color-primary-400, #60A5FA);
    transform: translateY(-1px);
}

.btn-nav:focus {
    outline: 2px solid var(--color-primary-500, #3B82F6);
    outline-offset: 2px;
}

/* ===================================================================
   Legend Section
   =================================================================== */

.attendance-legend {
    background: var(--color-neutral-50, #F9FAFB);
    border: 1px solid var(--color-neutral-200, #E5E7EB);
    border-radius: 8px;
    padding: 16px 24px;
    margin-bottom: 24px;
}

.legend-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-neutral-700, #374151);
    margin: 0 0 12px 0;
}

.legend-items {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
}

.legend-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 4px;
    font-size: 14px;
}

.legend-badge--on_time {
    background: #D1FAE5;
    border: 1px solid #10B981;
}

.legend-badge--late {
    background: #FEF3C7;
    border: 1px solid #F59E0B;
}

.legend-badge--called_in {
    background: #FED7AA;
    border: 1px solid #FB923C;
}

.legend-badge--no_call_no_show {
    background: #FEE2E2;
    border: 1px solid #DC2626;
}

.legend-badge--excused_absence {
    background: #DBEAFE;
    border: 1px solid #3B82F6;
}

.legend-badge--no_data {
    background: #F3F4F6;
    border: 1px solid #9CA3AF;
}

.legend-label {
    font-size: 14px;
    color: var(--color-neutral-700, #374151);
}

/* ===================================================================
   Statistics Section
   =================================================================== */

.attendance-stats {
    margin-bottom: 32px;
}

.stats-title {
    font-size: 18px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
    margin: 0 0 16px 0;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 16px;
}

.stat-card {
    background: white;
    border: 1px solid var(--color-neutral-200, #E5E7EB);
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-value {
    font-size: 32px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
    margin-bottom: 8px;
}

.stat-label {
    font-size: 14px;
    color: var(--color-neutral-600, #4B5563);
}

.stat-card--total {
    border-left: 4px solid var(--color-primary-500, #3B82F6);
}

.stat-card--on-time {
    border-left: 4px solid #10B981;
}

.stat-card--late {
    border-left: 4px solid #F59E0B;
}

.stat-card--called-in {
    border-left: 4px solid #FB923C;
}

.stat-card--no-call {
    border-left: 4px solid #DC2626;
}

.stat-card--excused {
    border-left: 4px solid #3B82F6;
}

.stat-card--rate {
    border-left: 4px solid var(--color-primary-500, #3B82F6);
}

.stats-empty {
    text-align: center;
    padding: 40px;
    color: var(--color-neutral-500, #6B7280);
    font-style: italic;
}

/* ===================================================================
   Calendar Container
   =================================================================== */

.calendar-container {
    background: white;
    border: 1px solid var(--color-neutral-200, #E5E7EB);
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* Calendar Header (Day Names) */
.calendar-header {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 8px;
    margin-bottom: 16px;
    padding-bottom: 16px;
    border-bottom: 2px solid var(--color-neutral-200, #E5E7EB);
}

.calendar-day-name {
    text-align: center;
    font-size: 14px;
    font-weight: 700;
    color: var(--color-neutral-700, #374151);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Calendar Grid */
.calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 8px;
    min-height: 400px;
}

/* Calendar Day Cell */
.calendar-day {
    aspect-ratio: 1;
    background: var(--color-neutral-50, #F9FAFB);
    border: 2px solid var(--color-neutral-200, #E5E7EB);
    border-radius: 8px;
    padding: 12px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
}

.calendar-day:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    border-color: var(--color-primary-400, #60A5FA);
}

.calendar-day:focus {
    outline: 3px solid var(--color-primary-500, #3B82F6);
    outline-offset: 2px;
}

.calendar-day--empty {
    background: transparent;
    border: none;
    cursor: default;
    pointer-events: none;
}

.calendar-day--empty:hover {
    transform: none;
    box-shadow: none;
}

/* Day Number */
.calendar-day-number {
    font-size: 18px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
    margin-bottom: 8px;
}

/* Day Content */
.calendar-day-count {
    font-size: 12px;
    color: var(--color-neutral-600, #4B5563);
    text-align: center;
    margin-top: auto;
}

.calendar-day-no-data {
    font-size: 11px;
    color: var(--color-neutral-400, #9CA3AF);
    text-align: center;
    margin-top: auto;
    font-style: italic;
}

/* Today Indicator */
.calendar-day--today {
    border-color: var(--color-primary-500, #3B82F6);
    border-width: 3px;
}

.calendar-day--today .calendar-day-number {
    color: var(--color-primary-600, #2563EB);
}

/* Status Color Coding */
.calendar-day--on_time {
    background: linear-gradient(135deg, #D1FAE5 0%, #ECFDF5 100%);
    border-color: #10B981;
}

.calendar-day--late {
    background: linear-gradient(135deg, #FEF3C7 0%, #FFFBEB 100%);
    border-color: #F59E0B;
}

.calendar-day--called_in {
    background: linear-gradient(135deg, #FED7AA 0%, #FFEDD5 100%);
    border-color: #FB923C;
}

.calendar-day--no_call_no_show {
    background: linear-gradient(135deg, #FEE2E2 0%, #FEF2F2 100%);
    border-color: #DC2626;
}

.calendar-day--excused_absence {
    background: linear-gradient(135deg, #DBEAFE 0%, #EFF6FF 100%);
    border-color: #3B82F6;
}

.calendar-day--no_data {
    background: var(--color-neutral-50, #F9FAFB);
    border-color: var(--color-neutral-200, #E5E7EB);
}

/* ===================================================================
   Date Detail Panel
   =================================================================== */

.date-detail-container {
    margin-top: 32px;
    background: white;
    border: 1px solid var(--color-neutral-200, #E5E7EB);
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.date-detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 2px solid var(--color-neutral-200, #E5E7EB);
}

.date-detail-title {
    font-size: 22px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
    margin: 0;
}

.btn-close-detail {
    background: var(--color-neutral-100, #F3F4F6);
    border: 1px solid var(--color-neutral-300, #D1D5DB);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 20px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.btn-close-detail:hover {
    background: var(--color-neutral-200, #E5E7EB);
}

.btn-close-detail:focus {
    outline: 2px solid var(--color-primary-500, #3B82F6);
    outline-offset: 2px;
}

.date-detail-empty {
    text-align: center;
    padding: 40px;
    color: var(--color-neutral-500, #6B7280);
    font-style: italic;
}

/* Employee Attendance Card */
.employee-attendance-card {
    background: var(--color-neutral-50, #F9FAFB);
    border: 1px solid var(--color-neutral-200, #E5E7EB);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}

.employee-attendance-card:last-child {
    margin-bottom: 0;
}

.employee-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.employee-card-name {
    font-size: 16px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
}

.employee-card-time {
    font-size: 13px;
    color: var(--color-neutral-500, #6B7280);
}

/* Attendance Status Badge */
.attendance-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
}

.attendance-badge--on_time {
    background: #D1FAE5;
    color: #065F46;
    border: 1px solid #10B981;
}

.attendance-badge--late {
    background: #FEF3C7;
    color: #92400E;
    border: 1px solid #F59E0B;
}

.attendance-badge--called_in {
    background: #FED7AA;
    color: #9A3412;
    border: 1px solid #FB923C;
}

.attendance-badge--no_call_no_show {
    background: #FEE2E2;
    color: #991B1B;
    border: 1px solid #DC2626;
}

.attendance-badge--excused_absence {
    background: #DBEAFE;
    color: #1E40AF;
    border: 1px solid #3B82F6;
}

/* Lock Icon for existing records */
.lock-indicator {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--color-neutral-500, #6B7280);
    margin-left: 8px;
}

.lock-indicator .material-symbols-outlined {
    font-size: 16px;
}

/* Audit Trail Display */
.audit-info {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--color-neutral-200, #E5E7EB);
}

.audit-recorded-by {
    font-size: 12px;
    color: var(--color-neutral-500, #6B7280);
    margin-bottom: 2px;
}

.audit-modified-by {
    font-size: 12px;
    color: var(--color-neutral-500, #6B7280);
    font-style: italic;
}

.record-notes {
    font-size: 13px;
    color: var(--color-neutral-700, #374151);
    margin-top: 6px;
    line-height: 1.5;
}

/* ===================================================================
   Submit Attendance Form (for employees without existing records)
   =================================================================== */

.submit-attendance-form {
    background: #FFFBEB;
    border: 1px dashed #F59E0B;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}

.submit-attendance-form:last-child {
    margin-bottom: 0;
}

.submit-form-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.submit-form-name {
    font-size: 16px;
    font-weight: 700;
    color: var(--color-neutral-900, #111827);
}

.submit-form-time {
    font-size: 13px;
    color: var(--color-neutral-500, #6B7280);
}

.submit-form-label {
    font-size: 12px;
    color: #B45309;
    font-weight: 600;
    margin-bottom: 8px;
    display: block;
}

.submit-form-controls {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    flex-wrap: wrap;
}

.submit-form-select {
    padding: 8px 12px;
    font-size: 14px;
    border: 1px solid var(--color-neutral-300, #D1D5DB);
    border-radius: 6px;
    background: white;
    color: var(--color-neutral-900, #111827);
    cursor: pointer;
    min-width: 180px;
    transition: border-color 0.2s ease;
}

.submit-form-select:hover {
    border-color: var(--color-primary-500, #3B82F6);
}

.submit-form-select:focus {
    outline: 2px solid var(--color-primary-500, #3B82F6);
    outline-offset: 2px;
    border-color: var(--color-primary-500, #3B82F6);
}

.submit-form-notes {
    padding: 8px 12px;
    font-size: 14px;
    border: 1px solid var(--color-neutral-300, #D1D5DB);
    border-radius: 6px;
    background: white;
    color: var(--color-neutral-900, #111827);
    font-family: inherit;
    resize: vertical;
    min-height: 38px;
    flex: 1;
    min-width: 150px;
    transition: border-color 0.2s ease;
}

.submit-form-notes:focus {
    outline: 2px solid var(--color-primary-500, #3B82F6);
    outline-offset: 0;
    border-color: var(--color-primary-500, #3B82F6);
}

.btn-submit-attendance {
    padding: 8px 20px;
    font-size: 14px;
    font-weight: 600;
    background: var(--color-primary-600, #2563EB);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
}

.btn-submit-attendance:hover {
    background: var(--color-primary-700, #1D4ED8);
}

.btn-submit-attendance:focus {
    outline: 2px solid var(--color-primary-500, #3B82F6);
    outline-offset: 2px;
}

.btn-submit-attendance:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* Error/Success messages inline */
.submit-result {
    margin-top: 8px;
    font-size: 13px;
    padding: 6px 10px;
    border-radius: 4px;
}

.submit-result--success {
    background: #D1FAE5;
    color: #065F46;
    border: 1px solid #10B981;
}

.submit-result--error {
    background: #FEE2E2;
    color: #991B1B;
    border: 1px solid #DC2626;
}

/* ===================================================================
   Loading Spinner
   =================================================================== */

.loading-spinner {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 40px;
    color: var(--color-neutral-500, #6B7280);
}

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
}

/* ===================================================================
   Tooltip
   =================================================================== */

.attendance-tooltip {
    position: absolute;
    background: white;
    border: 1px solid var(--color-neutral-300, #D1D5DB);
    border-radius: 8px;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    padding: 12px;
    z-index: 9998;
    min-width: 180px;
    max-width: 250px;
    opacity: 0;
    transform: translateY(-4px);
    transition: opacity 0.2s ease, transform 0.2s ease;
    pointer-events: none;
}

.attendance-tooltip.tooltip-visible {
    opacity: 1;
    transform: translateY(0);
}

.tooltip-header {
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--color-neutral-200, #E5E7EB);
}

.tooltip-header strong {
    font-size: 14px;
    color: var(--color-neutral-900, #111827);
}

.tooltip-body {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.tooltip-item {
    font-size: 13px;
    color: var(--color-neutral-700, #374151);
    display: flex;
    align-items: center;
    gap: 6px;
}

.tooltip-footer {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--color-neutral-200, #E5E7EB);
    font-size: 11px;
    color: var(--color-neutral-500, #6B7280);
    text-align: center;
    font-style: italic;
}

/* ===================================================================
   Responsive Styles
   =================================================================== */

@media (max-width: 1024px) {
    .stats-grid {
        grid-template-columns: repeat(3, 1fr);
    }
}

@media (max-width: 767px) {
    .lead-attendance-container {
        padding: 16px;
    }

    .header-row {
        flex-direction: column;
        align-items: flex-start;
    }

    .page-title {
        font-size: 22px;
    }

    .employee-selector-container {
        width: 100%;
    }

    .employee-selector {
        width: 100%;
    }

    .month-navigation {
        flex-direction: column;
        gap: 16px;
    }

    .current-month {
        font-size: 20px;
        order: -1;
    }

    .stats-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .calendar-container {
        padding: 16px;
    }

    .calendar-header {
        gap: 4px;
    }

    .calendar-day-name {
        font-size: 11px;
    }

    .calendar-grid {
        gap: 4px;
    }

    .calendar-day {
        padding: 8px;
        aspect-ratio: 1;
    }

    .calendar-day-number {
        font-size: 14px;
    }

    .calendar-day-count {
        font-size: 10px;
    }

    .date-detail-container {
        padding: 16px;
    }

    .date-detail-title {
        font-size: 18px;
    }

    .submit-form-controls {
        flex-direction: column;
    }

    .submit-form-select,
    .submit-form-notes {
        width: 100%;
        min-width: unset;
    }

    .btn-submit-attendance {
        width: 100%;
        min-height: 44px;
    }
}

@media (max-width: 480px) {
    .btn-nav {
        min-height: 44px;
    }
    .employee-selector {
        min-height: 44px;
    }
    .legend-item {
        font-size: 12px;
    }
    .lead-attendance-container {
        padding: 8px;
    }
    .calendar-container {
        padding: 8px;
    }
    .calendar-day {
        min-width: unset !important;
        padding: 4px 2px;
        aspect-ratio: auto;
        min-height: 40px;
    }
    .calendar-day-no-data,
    .calendar-day-count {
        font-size: 8px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .calendar-day-name {
        min-width: unset !important;
        font-size: 9px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .calendar-header {
        grid-template-columns: repeat(7, 1fr) !important;
        overflow: hidden;
    }
    .legend-items {
        flex-wrap: wrap;
        gap: 8px;
    }
}

@media (max-width: 375px) {
    .stats-grid {
        grid-template-columns: 1fr;
    }

    .calendar-day-name {
        font-size: 10px;
    }

    .calendar-day {
        padding: 4px;
    }

    .calendar-day-number {
        font-size: 12px;
    }

    .calendar-day-count {
        font-size: 9px;
    }
}

/* ===================================================================
   Accessibility
   =================================================================== */

@media (prefers-contrast: high) {
    .calendar-day:focus {
        outline-width: 4px;
    }

    .btn-nav:focus {
        outline-width: 3px;
    }

    .calendar-day {
        border-width: 3px;
    }
}

@media (prefers-reduced-motion: reduce) {
    .calendar-day,
    .stat-card,
    .btn-nav,
    .btn-submit-attendance,
    .attendance-tooltip {
        transition: none;
    }

    .calendar-day:hover,
    .stat-card:hover {
        transform: none;
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/css/pages/lead-attendance.css
git commit -m "feat: create lead attendance CSS styles"
```

---

### Task 4: Create lead attendance JavaScript

**Files:**
- Create: `app/static/js/pages/lead-attendance.js`

- [ ] **Step 1: Create the JS file**

This file follows the same class-based pattern as `attendance-calendar.js` but:
- Uses `GET /api/attendance/scheduled-employees/<date>` for day detail (shows employees with/without records)
- Uses `GET /api/attendance/month/<date>` for calendar rendering and stats
- Uses `POST /api/attendance` to submit new records
- Does NOT include edit/delete functionality
- Shows lock icon and audit trail on existing records

Create `app/static/js/pages/lead-attendance.js` with the following complete content:

```javascript
/**
 * LEAD ATTENDANCE CALENDAR VIEW (Spec 5)
 *
 * JavaScript for the lead attendance calendar.
 * Leads can view attendance and submit new records, but cannot edit or delete existing ones.
 * Locking is enforced server-side by Spec 4 API rules.
 */

class LeadAttendanceCalendar {
    constructor() {
        this.container = document.querySelector('.lead-attendance-container');
        if (!this.container) {
            console.error('[LeadAttendance] Container not found');
            return;
        }

        this.selectedDate = this.container.getAttribute('data-selected-date');
        this.username = this.container.getAttribute('data-username') || 'Unknown';
        this.selectedEmployeeId = this.getSelectedEmployeeId();
        this.attendanceData = {};
        this.statisticsData = {};

        this.STATUS_LABELS = {
            'on_time': 'On-Time',
            'late': 'Late',
            'called_in': 'Called-In',
            'no_call_no_show': 'No-Call-No-Show',
            'excused_absence': 'Excused Absence'
        };

        this.STATUS_ICONS = {
            'on_time': 'check_circle',
            'late': 'schedule',
            'called_in': 'phone',
            'no_call_no_show': 'cancel',
            'excused_absence': 'event_busy'
        };

        this.init();
    }

    /**
     * Initialize the calendar
     */
    async init() {
        console.log('[LeadAttendance] Initializing...');

        this.attachEventListeners();

        await this.loadAttendanceData();
        this.renderCalendar();
        this.renderStatistics();

        console.log('[LeadAttendance] Initialized successfully');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Employee selector change
        var employeeSelector = document.getElementById('employee-selector');
        if (employeeSelector) {
            employeeSelector.addEventListener('change', function(e) {
                this.handleEmployeeChange(e.target.value);
            }.bind(this));
        }

        // Close detail panel when clicking outside
        document.addEventListener('click', function(e) {
            var detailContainer = document.getElementById('date-detail-container');
            var calendarGrid = document.getElementById('calendar-grid');

            if (detailContainer &&
                detailContainer.style.display !== 'none' &&
                !detailContainer.contains(e.target) &&
                calendarGrid && !calendarGrid.contains(e.target)) {
                this.closeDateDetail();
            }
        }.bind(this));
    }

    /**
     * Get selected employee ID from URL
     */
    getSelectedEmployeeId() {
        var urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('employee_id') || null;
    }

    /**
     * Handle employee selector change
     */
    handleEmployeeChange(employeeId) {
        var url = window.location.pathname;
        var params = new URLSearchParams(window.location.search);

        if (employeeId) {
            params.set('employee_id', employeeId);
        } else {
            params.delete('employee_id');
        }

        if (params.toString()) {
            window.location.href = url + '?' + params.toString();
        } else {
            window.location.href = url;
        }
    }

    /**
     * Parse the selected date string into {year, month}
     */
    parseSelectedDate() {
        var parts = this.selectedDate.split('-');
        return {
            year: parseInt(parts[0], 10),
            month: parseInt(parts[1], 10) - 1 // 0-indexed
        };
    }

    /**
     * Load attendance data from API
     */
    async loadAttendanceData() {
        console.log('[LeadAttendance] Loading attendance data...');

        try {
            var parsed = this.parseSelectedDate();
            var monthStr = parsed.year + '-' + String(parsed.month + 1).padStart(2, '0') + '-01';

            var apiUrl = '/api/attendance/month/' + monthStr;
            if (this.selectedEmployeeId) {
                apiUrl += '?employee_id=' + this.selectedEmployeeId;
            }

            var response = await fetch(apiUrl, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error('API error: ' + response.status);
            }

            var data = await response.json();
            this.attendanceData = data.attendance_by_date || {};
            this.statisticsData = data.statistics || {};

        } catch (error) {
            console.error('[LeadAttendance] Failed to load attendance:', error);
            this.showNotification('Failed to load attendance data', 'error');
            this.attendanceData = {};
            this.statisticsData = {};
        }
    }

    /**
     * Render the calendar grid
     */
    renderCalendar() {
        var calendarGrid = document.getElementById('calendar-grid');
        if (!calendarGrid) return;

        var parsed = this.parseSelectedDate();
        var year = parsed.year;
        var month = parsed.month;

        var firstDay = new Date(year, month, 1);
        var lastDay = new Date(year, month + 1, 0);
        var startDayOfWeek = firstDay.getDay();
        var totalDays = lastDay.getDate();

        var calendarHTML = '';

        // Empty cells before month starts
        for (var i = 0; i < startDayOfWeek; i++) {
            calendarHTML += '<div class="calendar-day calendar-day--empty"></div>';
        }

        // Day cells
        for (var day = 1; day <= totalDays; day++) {
            var dateStr = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
            var dayData = this.attendanceData[dateStr] || {};
            var hasData = Object.keys(dayData).length > 0;

            var status = this.getDominantStatus(dayData);
            var statusClass = status ? 'calendar-day--' + status : 'calendar-day--no-data';

            var today = new Date();
            var isToday = (year === today.getFullYear() && month === today.getMonth() && day === today.getDate());

            calendarHTML +=
                '<div class="calendar-day ' + statusClass + (isToday ? ' calendar-day--today' : '') + '"' +
                ' data-date="' + dateStr + '"' +
                ' role="button"' +
                ' tabindex="0"' +
                ' aria-label="' + this.getDateAriaLabel(day, dateStr, dayData) + '">' +
                '<div class="calendar-day-number">' + day + '</div>' +
                (hasData ? this.renderDayBadges(dayData) : '<div class="calendar-day-no-data">No records</div>') +
                '</div>';
        }

        calendarGrid.innerHTML = calendarHTML;

        // Attach click + keyboard listeners
        var self = this;
        calendarGrid.querySelectorAll('.calendar-day[data-date]').forEach(function(dayCell) {
            dayCell.addEventListener('click', function(e) {
                var ds = e.currentTarget.getAttribute('data-date');
                if (ds) self.showDateDetail(ds);
            });

            dayCell.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    var ds = e.currentTarget.getAttribute('data-date');
                    if (ds) self.showDateDetail(ds);
                }
            });

            // Tooltip on hover
            var ds = dayCell.getAttribute('data-date');
            if (ds) {
                dayCell.addEventListener('mouseenter', function(e) {
                    self.showTooltip(e.currentTarget, ds);
                });
                dayCell.addEventListener('mouseleave', function() {
                    self.hideTooltip();
                });
            }
        });
    }

    /**
     * Get dominant attendance status for a date
     */
    getDominantStatus(dayData) {
        if (!dayData || Object.keys(dayData).length === 0) return null;

        var statusCounts = {
            no_call_no_show: 0,
            late: 0,
            called_in: 0,
            excused_absence: 0,
            on_time: 0
        };

        Object.values(dayData).forEach(function(records) {
            if (!Array.isArray(records)) records = [records];
            records.forEach(function(record) {
                if (statusCounts.hasOwnProperty(record.status)) {
                    statusCounts[record.status]++;
                }
            });
        });

        // Priority: no_call_no_show > late > called_in > excused_absence > on_time
        if (statusCounts.no_call_no_show > 0) return 'no_call_no_show';
        if (statusCounts.late > 0) return 'late';
        if (statusCounts.called_in > 0) return 'called_in';
        if (statusCounts.excused_absence > 0) return 'excused_absence';
        if (statusCounts.on_time > 0) return 'on_time';

        return null;
    }

    /**
     * Render day badges (record count)
     */
    renderDayBadges(dayData) {
        if (!dayData || Object.keys(dayData).length === 0) {
            return '<div class="calendar-day-no-data">No records</div>';
        }

        var totalRecords = 0;
        Object.values(dayData).forEach(function(records) {
            if (Array.isArray(records)) {
                totalRecords += records.length;
            } else {
                totalRecords += 1;
            }
        });

        return '<div class="calendar-day-count">' + totalRecords + ' record' + (totalRecords !== 1 ? 's' : '') + '</div>';
    }

    /**
     * Get ARIA label for a date cell
     */
    getDateAriaLabel(day, dateStr, dayData) {
        var parts = dateStr.split('-');
        var date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        var dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
        var monthName = date.toLocaleDateString('en-US', { month: 'long' });

        var label = dayName + ', ' + monthName + ' ' + day;

        if (dayData && Object.keys(dayData).length > 0) {
            var totalRecords = 0;
            Object.values(dayData).forEach(function(records) {
                if (Array.isArray(records)) {
                    totalRecords += records.length;
                } else {
                    totalRecords += 1;
                }
            });
            label += ', ' + totalRecords + ' attendance record' + (totalRecords !== 1 ? 's' : '');
        } else {
            label += ', No attendance records';
        }

        return label;
    }

    /**
     * Show date detail panel — fetches scheduled employees for the date
     */
    async showDateDetail(dateStr) {
        console.log('[LeadAttendance] Showing detail for:', dateStr);

        var detailContainer = document.getElementById('date-detail-container');
        if (!detailContainer) return;

        // Show loading state
        var parts = dateStr.split('-');
        var date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        var formattedDate = date.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });

        detailContainer.innerHTML =
            '<div class="date-detail-header">' +
            '<h3 class="date-detail-title">' + formattedDate + '</h3>' +
            '<button class="btn-close-detail" aria-label="Close detail panel">&times;</button>' +
            '</div>' +
            '<div class="loading-spinner">Loading scheduled employees...</div>';
        detailContainer.style.display = 'block';

        // Attach close button
        var self = this;
        var closeBtn = detailContainer.querySelector('.btn-close-detail');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() { self.closeDateDetail(); });
        }

        // Fetch scheduled employees with attendance
        try {
            var response = await fetch('/api/attendance/scheduled-employees/' + dateStr, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error('API error: ' + response.status);
            }

            var data = await response.json();
            this.renderDateDetail(detailContainer, formattedDate, dateStr, data.scheduled_employees || []);

        } catch (error) {
            console.error('[LeadAttendance] Failed to load scheduled employees:', error);
            detailContainer.innerHTML =
                '<div class="date-detail-header">' +
                '<h3 class="date-detail-title">' + formattedDate + '</h3>' +
                '<button class="btn-close-detail" aria-label="Close detail panel">&times;</button>' +
                '</div>' +
                '<div class="date-detail-empty">Error loading employee data. Please try again.</div>';

            closeBtn = detailContainer.querySelector('.btn-close-detail');
            if (closeBtn) {
                closeBtn.addEventListener('click', function() { self.closeDateDetail(); });
            }
        }

        // Scroll into view
        detailContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    /**
     * Render the date detail panel with scheduled employees
     */
    renderDateDetail(container, formattedDate, dateStr, scheduledEmployees) {
        var self = this;
        var html =
            '<div class="date-detail-header">' +
            '<h3 class="date-detail-title">' + formattedDate + '</h3>' +
            '<button class="btn-close-detail" aria-label="Close detail panel">&times;</button>' +
            '</div>';

        if (scheduledEmployees.length === 0) {
            html += '<div class="date-detail-empty">No employees scheduled for this date.</div>';
        } else {
            // Filter by selected employee if set
            var filtered = scheduledEmployees;
            if (this.selectedEmployeeId) {
                filtered = scheduledEmployees.filter(function(emp) {
                    return emp.employee_id === self.selectedEmployeeId;
                });
            }

            if (filtered.length === 0) {
                html += '<div class="date-detail-empty">No matching employees scheduled for this date.</div>';
            } else {
                html += '<div class="date-detail-records">';

                filtered.forEach(function(emp) {
                    if (emp.attendance_status) {
                        // Employee HAS an existing record — show read-only with lock
                        html += self.renderExistingRecord(emp);
                    } else {
                        // Employee has NO record — show submit form
                        html += self.renderSubmitForm(emp, dateStr);
                    }
                });

                html += '</div>';
            }
        }

        container.innerHTML = html;

        // Re-attach close button
        var closeBtn = container.querySelector('.btn-close-detail');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() { self.closeDateDetail(); });
        }

        // Attach submit button listeners
        container.querySelectorAll('[data-action="submit-attendance"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                var employeeId = e.currentTarget.getAttribute('data-employee-id');
                self.submitAttendance(employeeId, dateStr, e.currentTarget);
            });
        });
    }

    /**
     * Render an existing attendance record (read-only with lock icon)
     */
    renderExistingRecord(emp) {
        var statusLabel = this.STATUS_LABELS[emp.attendance_status] || emp.attendance_status;
        var statusIcon = this.STATUS_ICONS[emp.attendance_status] || 'help';
        var employeeName = typeof toTitleCase === 'function' ? toTitleCase(emp.employee_name) : emp.employee_name;
        var escapedName = typeof escapeHtml === 'function' ? escapeHtml(employeeName) : employeeName;

        var html =
            '<div class="employee-attendance-card">' +
            '<div class="employee-card-header">' +
            '<span class="employee-card-name">' + escapedName + '</span>' +
            '<span class="employee-card-time">Start: ' + (typeof escapeHtml === 'function' ? escapeHtml(emp.earliest_start_time) : emp.earliest_start_time) + '</span>' +
            '</div>' +
            '<div>' +
            '<span class="attendance-badge attendance-badge--' + emp.attendance_status + '">' +
            '<span class="material-symbols-outlined" style="font-size: 16px;">' + statusIcon + '</span> ' +
            statusLabel +
            '</span>' +
            '<span class="lock-indicator">' +
            '<span class="material-symbols-outlined">lock</span> Locked' +
            '</span>' +
            '</div>';

        // Notes
        if (emp.attendance_notes) {
            html += '<div class="record-notes">' + (typeof escapeHtml === 'function' ? escapeHtml(emp.attendance_notes) : emp.attendance_notes) + '</div>';
        }

        // Audit trail
        html += '<div class="audit-info">';

        if (emp.recorded_by) {
            html += '<div class="audit-recorded-by">Recorded by ' + (typeof escapeHtml === 'function' ? escapeHtml(emp.recorded_by) : emp.recorded_by) + '</div>';
        }

        if (emp.is_modified && emp.modified_by) {
            var modifiedAt = emp.modified_at ? new Date(emp.modified_at).toLocaleString('en-US', {
                month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true
            }) : '';
            html += '<div class="audit-modified-by">Modified by ' +
                (typeof escapeHtml === 'function' ? escapeHtml(emp.modified_by) : emp.modified_by) +
                (modifiedAt ? ' on ' + modifiedAt : '') +
                '</div>';
        }

        html += '</div>'; // .audit-info
        html += '</div>'; // .employee-attendance-card

        return html;
    }

    /**
     * Render submit attendance form for an employee without a record
     */
    renderSubmitForm(emp, dateStr) {
        var employeeName = typeof toTitleCase === 'function' ? toTitleCase(emp.employee_name) : emp.employee_name;
        var escapedName = typeof escapeHtml === 'function' ? escapeHtml(employeeName) : employeeName;
        var escapedId = typeof escapeHtml === 'function' ? escapeHtml(emp.employee_id) : emp.employee_id;

        return (
            '<div class="submit-attendance-form" id="form-' + emp.employee_id + '">' +
            '<div class="submit-form-header">' +
            '<span class="submit-form-name">' + escapedName + '</span>' +
            '<span class="submit-form-time">Start: ' + (typeof escapeHtml === 'function' ? escapeHtml(emp.earliest_start_time) : emp.earliest_start_time) + '</span>' +
            '</div>' +
            '<label class="submit-form-label">No attendance recorded &mdash; select status to submit:</label>' +
            '<div class="submit-form-controls">' +
            '<select class="submit-form-select" id="status-' + emp.employee_id + '" aria-label="Attendance status for ' + escapedName + '">' +
            '<option value="">-- Select Status --</option>' +
            '<option value="on_time">On-Time</option>' +
            '<option value="late">Late</option>' +
            '<option value="called_in">Called-In</option>' +
            '<option value="no_call_no_show">No-Call-No-Show</option>' +
            '<option value="excused_absence">Excused Absence</option>' +
            '</select>' +
            '<input type="text" class="submit-form-notes" id="notes-' + emp.employee_id + '"' +
            ' placeholder="Notes (optional)" aria-label="Attendance notes for ' + escapedName + '">' +
            '<button class="btn-submit-attendance" data-action="submit-attendance"' +
            ' data-employee-id="' + escapedId + '"' +
            ' aria-label="Submit attendance for ' + escapedName + '">Submit</button>' +
            '</div>' +
            '<div id="result-' + emp.employee_id + '"></div>' +
            '</div>'
        );
    }

    /**
     * Submit attendance record for an employee
     */
    async submitAttendance(employeeId, dateStr, buttonEl) {
        var statusSelect = document.getElementById('status-' + employeeId);
        var notesInput = document.getElementById('notes-' + employeeId);
        var resultDiv = document.getElementById('result-' + employeeId);

        if (!statusSelect || !statusSelect.value) {
            this.showInlineResult(resultDiv, 'Please select an attendance status.', 'error');
            return;
        }

        var status = statusSelect.value;
        var notes = notesInput ? notesInput.value.trim() : '';

        // Disable button during submission
        buttonEl.disabled = true;
        buttonEl.textContent = 'Submitting...';

        try {
            var response = await fetch('/api/attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({
                    employee_id: employeeId,
                    attendance_date: dateStr,
                    status: status,
                    notes: notes
                })
            });

            var data = await response.json();

            if (response.ok && data.success) {
                this.showInlineResult(resultDiv, 'Attendance recorded successfully!', 'success');
                this.showNotification('Attendance submitted', 'success');

                // Reload data and refresh calendar
                await this.loadAttendanceData();
                this.renderCalendar();
                this.renderStatistics();

                // Refresh detail panel after a brief delay
                var self = this;
                setTimeout(function() {
                    self.showDateDetail(dateStr);
                }, 500);

            } else if (response.status === 403) {
                // Locking enforcement from Spec 4
                this.showInlineResult(resultDiv, data.error || 'This record is locked. Only the supervisor can modify it.', 'error');
                buttonEl.disabled = false;
                buttonEl.textContent = 'Submit';
            } else {
                throw new Error(data.error || 'Failed to submit attendance');
            }

        } catch (error) {
            console.error('[LeadAttendance] Submit failed:', error);
            this.showInlineResult(resultDiv, error.message || 'Failed to submit attendance. Please try again.', 'error');
            buttonEl.disabled = false;
            buttonEl.textContent = 'Submit';
        }
    }

    /**
     * Show inline result message in a form
     */
    showInlineResult(resultDiv, message, type) {
        if (!resultDiv) return;
        var escaped = typeof escapeHtml === 'function' ? escapeHtml(message) : message;
        resultDiv.innerHTML = '<div class="submit-result submit-result--' + type + '">' + escaped + '</div>';

        // Auto-clear after 5 seconds for errors
        if (type === 'error') {
            setTimeout(function() {
                resultDiv.innerHTML = '';
            }, 5000);
        }
    }

    /**
     * Close date detail panel
     */
    closeDateDetail() {
        var detailContainer = document.getElementById('date-detail-container');
        if (detailContainer) {
            detailContainer.style.display = 'none';
            detailContainer.innerHTML = '';
        }
    }

    /**
     * Render statistics
     */
    renderStatistics() {
        var statsContainer = document.getElementById('attendance-stats');
        if (!statsContainer) return;

        if (!this.statisticsData || Object.keys(this.statisticsData).length === 0) {
            statsContainer.innerHTML = '<div class="stats-empty">No attendance data for this period.</div>';
            return;
        }

        var stats = this.statisticsData;

        statsContainer.innerHTML =
            '<h3 class="stats-title">Monthly Summary</h3>' +
            '<div class="stats-grid">' +
            '<div class="stat-card stat-card--total">' +
            '<div class="stat-value">' + (stats.total_records || 0) + '</div>' +
            '<div class="stat-label">Total Records</div>' +
            '</div>' +
            '<div class="stat-card stat-card--on-time">' +
            '<div class="stat-value">' + (stats.on_time || 0) + '</div>' +
            '<div class="stat-label">On-Time</div>' +
            '</div>' +
            '<div class="stat-card stat-card--late">' +
            '<div class="stat-value">' + (stats.late || 0) + '</div>' +
            '<div class="stat-label">Late</div>' +
            '</div>' +
            '<div class="stat-card stat-card--called-in">' +
            '<div class="stat-value">' + (stats.called_in || 0) + '</div>' +
            '<div class="stat-label">Called-In</div>' +
            '</div>' +
            '<div class="stat-card stat-card--no-call">' +
            '<div class="stat-value">' + (stats.no_call_no_show || 0) + '</div>' +
            '<div class="stat-label">No-Call-No-Show</div>' +
            '</div>' +
            '<div class="stat-card stat-card--rate">' +
            '<div class="stat-value">' + (stats.on_time_rate || '0%') + '</div>' +
            '<div class="stat-label">On-Time Rate</div>' +
            '</div>' +
            '</div>';
    }

    /**
     * Show tooltip on hover
     */
    showTooltip(element, dateStr) {
        this.hideTooltip();

        var dayData = this.attendanceData[dateStr] || {};
        if (Object.keys(dayData).length === 0) return;

        var statusCounts = {
            on_time: 0,
            late: 0,
            called_in: 0,
            no_call_no_show: 0,
            excused_absence: 0
        };

        var totalRecords = 0;
        Object.values(dayData).forEach(function(records) {
            if (!Array.isArray(records)) records = [records];
            records.forEach(function(record) {
                if (statusCounts.hasOwnProperty(record.status)) {
                    statusCounts[record.status]++;
                }
                totalRecords++;
            });
        });

        var tooltipHTML =
            '<div class="attendance-tooltip" role="tooltip">' +
            '<div class="tooltip-header">' +
            '<strong>' + totalRecords + ' Record' + (totalRecords !== 1 ? 's' : '') + '</strong>' +
            '</div>' +
            '<div class="tooltip-body">' +
            (statusCounts.on_time > 0 ? '<div class="tooltip-item">On-Time: ' + statusCounts.on_time + '</div>' : '') +
            (statusCounts.late > 0 ? '<div class="tooltip-item">Late: ' + statusCounts.late + '</div>' : '') +
            (statusCounts.called_in > 0 ? '<div class="tooltip-item">Called-In: ' + statusCounts.called_in + '</div>' : '') +
            (statusCounts.no_call_no_show > 0 ? '<div class="tooltip-item">No-Call-No-Show: ' + statusCounts.no_call_no_show + '</div>' : '') +
            (statusCounts.excused_absence > 0 ? '<div class="tooltip-item">Excused: ' + statusCounts.excused_absence + '</div>' : '') +
            '</div>' +
            '<div class="tooltip-footer">Click for details</div>' +
            '</div>';

        var tooltip = document.createElement('div');
        tooltip.innerHTML = tooltipHTML;
        var tooltipElement = tooltip.firstElementChild;
        document.body.appendChild(tooltipElement);

        // Position below element
        var rect = element.getBoundingClientRect();
        var tooltipRect = tooltipElement.getBoundingClientRect();

        var top = rect.bottom + window.scrollY + 8;
        var left = rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2);

        if (left + tooltipRect.width > window.innerWidth) {
            left = window.innerWidth - tooltipRect.width - 16;
        }
        if (left < 16) {
            left = 16;
        }
        if (top + tooltipRect.height > window.innerHeight + window.scrollY) {
            top = rect.top + window.scrollY - tooltipRect.height - 8;
        }

        tooltipElement.style.top = top + 'px';
        tooltipElement.style.left = left + 'px';

        setTimeout(function() {
            tooltipElement.classList.add('tooltip-visible');
        }, 10);
    }

    /**
     * Hide tooltip
     */
    hideTooltip() {
        var tooltip = document.querySelector('.attendance-tooltip');
        if (tooltip) {
            tooltip.classList.remove('tooltip-visible');
            setTimeout(function() {
                tooltip.remove();
            }, 200);
        }
    }

    /**
     * Show notification via toaster
     */
    showNotification(message, type) {
        if (window.toaster) {
            window.toaster.show(message, type);
        } else {
            console.log('[LeadAttendance] ' + type + ': ' + message);
        }
    }

    /**
     * Get CSRF token
     */
    getCsrfToken() {
        if (typeof window.getCsrfToken === 'function') {
            return window.getCsrfToken();
        }
        var metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].trim().split('=');
            if (parts[0] === 'csrf_token') {
                return parts[1];
            }
        }
        return '';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('[LeadAttendance] DOM ready, initializing...');
    new LeadAttendanceCalendar();
});
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/pages/lead-attendance.js
git commit -m "feat: create lead attendance JavaScript with calendar, detail panel, and submit logic"
```

---

### Task 5: Update scheduled-employees API to include audit trail fields

**Files:**
- Modify: `app/routes/api_attendance.py` (lines 488-493 in `get_scheduled_employees_with_attendance`)

The `GET /api/attendance/scheduled-employees/<date>` endpoint currently returns `attendance_status`, `attendance_notes`, `attendance_id`, and `status_label` but does NOT include `recorded_by`, `modified_by`, `modified_at`, or `is_modified`. The lead attendance JS needs these fields for the audit trail display.

**Note:** Spec 4 adds `modified_by` and `modified_at` columns to the model but does NOT update this endpoint. We need to add all four fields here.

- [ ] **Step 1: Add audit trail fields to the scheduled-employees response**

In `app/routes/api_attendance.py`, find the block at lines 488-493 (inside `get_scheduled_employees_with_attendance`):

```python
# Before:
            # Map attendance to employees
            for record in attendance_records:
                if record.employee_id in employees_scheduled:
                    employees_scheduled[record.employee_id]['attendance_status'] = record.status
                    employees_scheduled[record.employee_id]['attendance_notes'] = record.notes
                    employees_scheduled[record.employee_id]['attendance_id'] = record.id
                    employees_scheduled[record.employee_id]['status_label'] = record.STATUS_LABELS.get(record.status)

# After:
            # Map attendance to employees
            for record in attendance_records:
                if record.employee_id in employees_scheduled:
                    employees_scheduled[record.employee_id]['attendance_status'] = record.status
                    employees_scheduled[record.employee_id]['attendance_notes'] = record.notes
                    employees_scheduled[record.employee_id]['attendance_id'] = record.id
                    employees_scheduled[record.employee_id]['status_label'] = record.STATUS_LABELS.get(record.status)
                    employees_scheduled[record.employee_id]['recorded_by'] = record.recorded_by
                    employees_scheduled[record.employee_id]['modified_by'] = getattr(record, 'modified_by', None)
                    modified_at = getattr(record, 'modified_at', None)
                    employees_scheduled[record.employee_id]['modified_at'] = modified_at.isoformat() if modified_at else None
                    employees_scheduled[record.employee_id]['is_modified'] = getattr(record, 'modified_by', None) is not None
```

We use `getattr()` with a fallback so this code works even before Spec 4's migration has been applied (graceful degradation).

- [ ] **Step 2: Commit**

```bash
git add app/routes/api_attendance.py
git commit -m "feat: add audit trail fields to scheduled-employees API response"
```

---

### Task 6: Verification

- [ ] **Step 1: Run full test suite**

```bash
pytest -v --timeout=120
```

Expected: All tests pass (308+). No regressions.

- [ ] **Step 2: Verify file structure**

Confirm all new files exist:

```bash
ls -la app/templates/lead/attendance.html
ls -la app/static/css/pages/lead-attendance.css
ls -la app/static/js/pages/lead-attendance.js
```

- [ ] **Step 3: Manual smoke test checklist**

1. Start dev server: `python wsgi.py`
2. **Log in as lead** — verify `/lead/attendance` loads with monthly calendar grid
3. Verify calendar cells are color-coded by attendance status (same colors as supervisor view)
4. Click a date — verify day detail panel shows scheduled employees
5. For employees WITHOUT existing records: verify status dropdown and submit button appear
6. Submit a new attendance record — verify success message, card updates to show locked record
7. For employees WITH existing records: verify status badge, lock icon, no edit/delete buttons
8. Verify "Recorded by {name}" appears on each existing record
9. If a record has been modified (Spec 4): verify "Modified by {name} on {date}" appears
10. Change employee filter dropdown — verify calendar reloads for that employee
11. Navigate months via prev/next arrows — verify calendar updates
12. Verify monthly statistics section shows correct counts and on-time rate
13. **Log in as supervisor** — verify `/lead/attendance` returns 403
14. **Log in as specialist** — verify `/lead/attendance` returns 403
15. Verify supervisor's existing attendance page (`/attendance`) is unchanged
16. Try submitting attendance for an employee+date that already has a record — verify 403 error from API (Spec 4 locking)

- [ ] **Step 4: Accessibility checks**

1. Tab through calendar — verify all day cells are focusable
2. Press Enter on a day cell — verify detail panel opens
3. Screen reader: verify ARIA labels on day cells include date and record count
4. Verify employee filter has proper label association
5. Verify submit buttons have descriptive aria-labels
