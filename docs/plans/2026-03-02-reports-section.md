# Reports Section Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a 7-report Reports section with Chart.js visualizations, data tables, print/export support, and a sidebar link — replacing the Corporate Report button on the events page.

**Architecture:** New `reports_bp` blueprint at `/reports` with a hub page and 7 individual report pages. A `ReportService` class handles all database queries. Each report page is server-rendered with Chart.js charts initialized from template-embedded JSON data. Shared CSS in `reports.css`.

**Tech Stack:** Flask/Jinja2, SQLAlchemy, Chart.js 4.4.0, CSS `@media print`

---

### Task 1: Foundation — ReportService, Blueprint, Hub Page, Sidebar Link

This task creates the skeleton: the service class, the blueprint, the hub page, and wires everything together.

**Files:**
- Create: `app/services/report_service.py`
- Create: `app/routes/reports.py`
- Create: `app/templates/reports/index.html`
- Create: `app/static/css/pages/reports.css`
- Modify: `app/__init__.py` (register blueprint, around line 252)
- Modify: `app/templates/base.html` (sidebar link, Tools group)

**Step 1: Create the report service skeleton**

Create `app/services/report_service.py`:

```python
"""
Report Service
Provides data queries for all reports in the Reports section.
"""
from datetime import date, datetime, timedelta
from collections import defaultdict
from sqlalchemy import func, and_, or_


class ReportService:
    """Service for computing report data."""

    def __init__(self, db_session, models):
        self.session = db_session
        self.Event = models['Event']
        self.Employee = models['Employee']
        self.Schedule = models['Schedule']
        self.EmployeeAttendance = models['EmployeeAttendance']
        self.EmployeeTimeOff = models['EmployeeTimeOff']

    def get_event_statistics(self, start_date, end_date):
        """Report 1: Event Statistics — summary stats, by-condition breakdown, weekly detail."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        events = self.Event.query.filter(
            self.Event.start_datetime >= start_dt,
            self.Event.start_datetime <= end_dt
        ).order_by(self.Event.start_datetime.asc()).all()

        total = len(events)
        by_condition = {}
        for e in events:
            cond = e.condition or 'Unknown'
            by_condition[cond] = by_condition.get(cond, 0) + 1

        submitted = by_condition.get('Submitted', 0)
        scheduled_count = by_condition.get('Scheduled', 0) + by_condition.get('Staffed', 0)
        unstaffed = by_condition.get('Unstaffed', 0)
        completion_rate = round((submitted / total * 100), 1) if total > 0 else 0
        scheduled_pct = round((scheduled_count / total * 100), 1) if total > 0 else 0
        unstaffed_pct = round((unstaffed / total * 100), 1) if total > 0 else 0

        # Group by week (Sunday start)
        weeks = defaultdict(list)
        for event in events:
            event_date = event.start_datetime.date()
            days_since_sunday = (event_date.weekday() + 1) % 7
            week_start = event_date - timedelta(days=days_since_sunday)
            schedule = self.Schedule.query.filter_by(
                event_ref_num=event.project_ref_num
            ).first()
            emp_name = ''
            sched_date = ''
            if schedule:
                emp = self.session.get(self.Employee, schedule.employee_id)
                emp_name = emp.name if emp else ''
                sched_date = schedule.schedule_datetime.strftime('%m/%d/%Y') if schedule.schedule_datetime else ''

            days_available = (event.due_datetime.date() - event.start_datetime.date()).days

            weeks[week_start].append({
                'ref_num': event.project_ref_num,
                'name': event.project_name,
                'event_type': event.event_type,
                'condition': event.condition,
                'start_date': event.start_datetime.strftime('%m/%d/%Y'),
                'due_date': event.due_datetime.strftime('%m/%d/%Y'),
                'employee': emp_name,
                'schedule_date': sched_date,
                'days_available': days_available,
            })

        sorted_weeks = []
        for ws in sorted(weeks.keys()):
            we = ws + timedelta(days=6)
            sorted_weeks.append({
                'start': ws.strftime('%m/%d/%Y'),
                'end': we.strftime('%m/%d/%Y'),
                'count': len(weeks[ws]),
                'events': weeks[ws],
            })

        return {
            'total': total,
            'completion_rate': completion_rate,
            'scheduled_pct': scheduled_pct,
            'unstaffed_pct': unstaffed_pct,
            'by_condition': dict(sorted(by_condition.items())),
            'weeks': sorted_weeks,
        }

    def get_employee_schedules(self, start_date, end_date):
        """Report 2: Employee Schedule Details."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        schedules = self.session.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Event.project_ref_num == self.Schedule.event_ref_num
        ).join(
            self.Employee, self.Employee.id == self.Schedule.employee_id
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Employee.is_active == True
        ).order_by(
            self.Employee.name,
            self.Schedule.schedule_datetime
        ).all()

        employees = {}
        for sched, event, emp in schedules:
            if emp.id not in employees:
                employees[emp.id] = {
                    'name': emp.name,
                    'events': [],
                    'event_count': 0,
                    'days_scheduled': set(),
                }
            employees[emp.id]['events'].append({
                'name': event.project_name,
                'event_type': event.event_type,
                'start_date': event.start_datetime.strftime('%m/%d/%Y'),
                'end_date': event.due_datetime.strftime('%m/%d/%Y'),
                'schedule_date': sched.schedule_datetime.strftime('%m/%d/%Y'),
            })
            employees[emp.id]['event_count'] += 1
            employees[emp.id]['days_scheduled'].add(
                sched.schedule_datetime.date()
            )

        result = []
        for emp_id, data in sorted(employees.items(), key=lambda x: x[1]['name']):
            result.append({
                'name': data['name'],
                'events': data['events'],
                'event_count': data['event_count'],
                'days_scheduled': len(data['days_scheduled']),
            })

        return result

    def get_event_type_breakdown(self, start_date, end_date):
        """Report 3: Event Type Breakdown — count and percentage per type."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        rows = self.session.query(
            self.Event.event_type,
            func.count(self.Event.id).label('count')
        ).filter(
            self.Event.start_datetime >= start_dt,
            self.Event.start_datetime <= end_dt
        ).group_by(self.Event.event_type).all()

        total = sum(r.count for r in rows)
        types = []
        for r in sorted(rows, key=lambda x: x.count, reverse=True):
            types.append({
                'event_type': r.event_type,
                'count': r.count,
                'percentage': round((r.count / total * 100), 1) if total > 0 else 0,
            })

        return {'total': total, 'types': types}

    def get_employee_workload(self, start_date, end_date):
        """Report 4: Employee Workload — hours per employee."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        rows = self.session.query(
            self.Employee.name,
            func.count(self.Schedule.id).label('event_count'),
            func.coalesce(func.sum(self.Event.estimated_time), 0).label('total_minutes')
        ).join(
            self.Schedule, self.Schedule.employee_id == self.Employee.id
        ).join(
            self.Event, self.Event.project_ref_num == self.Schedule.event_ref_num
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Employee.is_active == True
        ).group_by(self.Employee.name).order_by(self.Employee.name).all()

        result = []
        for r in rows:
            hours = round(r.total_minutes / 60, 1)
            avg = round(hours / r.event_count, 1) if r.event_count > 0 else 0
            if r.event_count >= 19:
                status = 'Overloaded'
            elif r.event_count >= 13:
                status = 'High'
            else:
                status = 'Normal'
            result.append({
                'name': r.name,
                'event_count': r.event_count,
                'total_hours': hours,
                'avg_hours': avg,
                'status': status,
            })

        return result

    def get_attendance_report(self, start_date, end_date):
        """Report 5: Attendance Report."""
        rows = self.session.query(
            self.Employee.name,
            self.EmployeeAttendance.status,
            func.count(self.EmployeeAttendance.id).label('count')
        ).join(
            self.Employee, self.Employee.id == self.EmployeeAttendance.employee_id
        ).filter(
            self.EmployeeAttendance.attendance_date >= start_date,
            self.EmployeeAttendance.attendance_date <= end_date,
            self.Employee.is_active == True
        ).group_by(
            self.Employee.name,
            self.EmployeeAttendance.status
        ).all()

        employees = {}
        for r in rows:
            if r.name not in employees:
                employees[r.name] = {
                    'name': r.name,
                    'on_time': 0, 'late': 0, 'called_in': 0,
                    'no_call_no_show': 0, 'excused_absence': 0,
                    'total': 0,
                }
            employees[r.name][r.status] = r.count
            employees[r.name]['total'] += r.count

        result = []
        for name in sorted(employees.keys()):
            data = employees[name]
            on_time = data['on_time']
            rate = round((on_time / data['total'] * 100), 1) if data['total'] > 0 else 0
            data['attendance_rate'] = rate
            result.append(data)

        return result

    def get_scheduling_coverage(self, start_date, end_date):
        """Report 6: Scheduling Coverage — daily scheduled vs total."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        events = self.Event.query.filter(
            self.Event.start_datetime >= start_dt,
            self.Event.start_datetime <= end_dt,
            self.Event.condition.notin_(['Canceled', 'Cancelled', 'Expired'])
        ).all()

        by_day = defaultdict(lambda: {'total': 0, 'scheduled': 0})
        for e in events:
            d = e.start_datetime.date()
            by_day[d]['total'] += 1
            if e.is_scheduled:
                by_day[d]['scheduled'] += 1

        days = []
        current = start_date
        while current <= end_date:
            data = by_day.get(current, {'total': 0, 'scheduled': 0})
            unscheduled = data['total'] - data['scheduled']
            coverage = round((data['scheduled'] / data['total'] * 100), 1) if data['total'] > 0 else 100
            days.append({
                'date': current.strftime('%m/%d/%Y'),
                'date_short': current.strftime('%m/%d'),
                'day_name': current.strftime('%a'),
                'total': data['total'],
                'scheduled': data['scheduled'],
                'unscheduled': unscheduled,
                'coverage': coverage,
            })
            current += timedelta(days=1)

        overall_total = sum(d['total'] for d in days)
        overall_sched = sum(d['scheduled'] for d in days)
        overall_pct = round((overall_sched / overall_total * 100), 1) if overall_total > 0 else 100
        days_with_events = [d for d in days if d['total'] > 0]
        best = max(days_with_events, key=lambda d: d['coverage']) if days_with_events else None
        worst = min(days_with_events, key=lambda d: d['coverage']) if days_with_events else None

        return {
            'days': days,
            'overall_coverage': overall_pct,
            'overall_total': overall_total,
            'overall_scheduled': overall_sched,
            'best_day': best,
            'worst_day': worst,
        }

    def get_time_off_summary(self, start_date, end_date):
        """Report 7: Time Off Summary."""
        records = self.session.query(
            self.EmployeeTimeOff, self.Employee
        ).join(
            self.Employee, self.Employee.id == self.EmployeeTimeOff.employee_id
        ).filter(
            self.EmployeeTimeOff.start_date <= end_date,
            self.EmployeeTimeOff.end_date >= start_date,
            self.Employee.is_active == True
        ).order_by(
            self.Employee.name,
            self.EmployeeTimeOff.start_date
        ).all()

        result = []
        total_days = 0
        for to, emp in records:
            # Clamp to report range
            eff_start = max(to.start_date, start_date)
            eff_end = min(to.end_date, end_date)
            days = (eff_end - eff_start).days + 1
            total_days += days
            result.append({
                'name': emp.name,
                'start_date': to.start_date.strftime('%m/%d/%Y'),
                'end_date': to.end_date.strftime('%m/%d/%Y'),
                'days': days,
                'reason': to.reason or '',
            })

        return {'records': result, 'total_days': total_days}
```

**Step 2: Create the reports blueprint**

Create `app/routes/reports.py`:

```python
"""
Reports Blueprint
Provides report pages with charts and data tables.
"""
from flask import Blueprint, render_template, request, current_app, make_response
from datetime import datetime, date, timedelta
from app.models import get_models
from app.routes.auth import require_authentication
from app.services.report_service import ReportService
import csv
import io

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


def _get_service():
    """Create a ReportService instance."""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    return ReportService(db.session, models)


def _parse_dates(default_start=None, default_end=None):
    """Parse start_date and end_date from query params, with defaults."""
    today = date.today()
    if default_start is None:
        days_since_sunday = (today.weekday() + 1) % 7
        default_start = today - timedelta(days=days_since_sunday)
    if default_end is None:
        default_end = default_start + timedelta(days=6)

    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')

    try:
        start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else default_start
    except ValueError:
        start = default_start
    try:
        end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else default_end
    except ValueError:
        end = default_end

    return start, end


@reports_bp.route('/')
def index():
    """Reports hub page."""
    return render_template('reports/index.html')


@reports_bp.route('/event-statistics')
def event_statistics():
    """Report 1: Event Statistics."""
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_event_statistics(start, end)
    return render_template('reports/event_statistics.html',
                         data=data, start_date=start, end_date=end)


@reports_bp.route('/employee-schedules')
def employee_schedules():
    """Report 2: Employee Schedule Details."""
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_employee_schedules(start, end)
    return render_template('reports/employee_schedules.html',
                         data=data, start_date=start, end_date=end)


@reports_bp.route('/event-type-breakdown')
def event_type_breakdown():
    """Report 3: Event Type Breakdown."""
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_event_type_breakdown(start, end)
    return render_template('reports/event_type_breakdown.html',
                         data=data, start_date=start, end_date=end)


@reports_bp.route('/employee-workload')
def employee_workload():
    """Report 4: Employee Workload."""
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_employee_workload(start, end)
    return render_template('reports/employee_workload.html',
                         data=data, start_date=start, end_date=end)


@reports_bp.route('/attendance')
def attendance():
    """Report 5: Attendance Report."""
    today = date.today()
    start, end = _parse_dates(
        default_start=today.replace(day=1),
        default_end=today
    )
    service = _get_service()
    data = service.get_attendance_report(start, end)
    return render_template('reports/attendance.html',
                         data=data, start_date=start, end_date=end)


@reports_bp.route('/scheduling-coverage')
def scheduling_coverage():
    """Report 6: Scheduling Coverage."""
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_scheduling_coverage(start, end)
    return render_template('reports/scheduling_coverage.html',
                         data=data, start_date=start, end_date=end)


@reports_bp.route('/time-off')
def time_off():
    """Report 7: Time Off Summary."""
    today = date.today()
    start, end = _parse_dates(
        default_start=today.replace(day=1),
        default_end=today
    )
    service = _get_service()
    data = service.get_time_off_summary(start, end)
    return render_template('reports/time_off.html',
                         data=data, start_date=start, end_date=end)
```

**Step 3: Create shared reports CSS**

Create `app/static/css/pages/reports.css`:

```css
/* Reports Section Styles */
.report-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%);
    color: white;
    padding: 24px 32px;
    border-radius: 12px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.report-header h1 { font-size: 24px; font-weight: 700; margin: 0; }
.report-header .subtitle { opacity: 0.9; margin-top: 4px; font-size: 14px; }
.report-actions { display: flex; gap: 8px; align-items: center; }
.report-actions .btn {
    background: rgba(255,255,255,0.2); color: white;
    padding: 8px 16px; border-radius: 6px;
    text-decoration: none; font-weight: 500; border: none; cursor: pointer;
    font-size: 14px;
}
.report-actions .btn:hover { background: rgba(255,255,255,0.3); }

/* Date range form */
.date-range-form {
    display: flex; gap: 10px; align-items: center;
    margin-bottom: 24px; flex-wrap: wrap;
}
.date-range-form label {
    font-size: 13px; font-weight: 600; color: #6b7280;
}
.date-range-form input[type="date"] {
    padding: 6px 10px; border: 1px solid #d1d5db;
    border-radius: 6px; font-size: 14px;
}
.date-range-form .btn-generate {
    padding: 8px 20px; border-radius: 6px; border: none;
    background: #1e3a5f; color: white; font-weight: 600;
    cursor: pointer; font-size: 14px;
}
.date-range-form .btn-generate:hover { background: #2d5a8e; }

/* Summary stat cards */
.stats-row {
    display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap;
}
.stat-card {
    background: white; padding: 20px 24px; border-radius: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex: 1; min-width: 150px;
}
.stat-card .value { font-size: 32px; font-weight: 700; color: #1e3a5f; }
.stat-card .label { font-size: 13px; color: #6b7280; margin-top: 4px; }

/* Chart container */
.chart-container {
    background: white; padding: 24px; border-radius: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px;
}
.chart-container h3 { margin: 0 0 16px 0; font-size: 16px; color: #374151; }

/* Data table */
.report-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.report-table th {
    background: #f8f9fa; padding: 10px 12px; text-align: left;
    font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb;
    position: sticky; top: 0;
}
.report-table td {
    padding: 8px 12px; border-bottom: 1px solid #f3f4f6; color: #4b5563;
}
.report-table tr:hover td { background: #f9fafb; }
.report-table .week-header {
    background: #eef2ff; font-weight: 600; color: #1e3a5f;
}
.report-table .week-header td { padding: 10px 12px; border-bottom: 2px solid #c7d2fe; }

/* Employee section (for employee schedule details) */
.employee-section {
    background: white; border-radius: 10px; padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
}
.employee-section h3 {
    margin: 0 0 4px 0; font-size: 16px; color: #1e3a5f;
}
.employee-section .summary {
    font-size: 13px; color: #6b7280; margin-bottom: 12px;
}

/* Status badges */
.status-badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
}
.status-normal { background: #d1fae5; color: #065f46; }
.status-high { background: #fef3c7; color: #92400e; }
.status-overloaded { background: #fee2e2; color: #991b1b; }

/* Hub page report cards */
.reports-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 20px; margin-bottom: 24px;
}
.report-card {
    background: white; border-radius: 10px; padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    transition: box-shadow 0.2s;
    display: flex; flex-direction: column;
}
.report-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.report-card .icon { font-size: 28px; margin-bottom: 12px; }
.report-card h3 { margin: 0 0 8px 0; font-size: 16px; color: #1e3a5f; }
.report-card p { font-size: 13px; color: #6b7280; margin: 0 0 16px 0; flex: 1; }
.report-card .open-link {
    color: #2d5a8e; font-weight: 600; font-size: 14px;
    text-decoration: none;
}
.report-card .open-link:hover { text-decoration: underline; }

/* Print styles */
@media print {
    .sidebar, .sidebar-overlay, .top-bar, .report-actions,
    .date-range-form, .no-print { display: none !important; }
    .report-header {
        border-radius: 0; margin-bottom: 12px; padding: 12px 16px;
        print-color-adjust: exact; -webkit-print-color-adjust: exact;
    }
    .stat-card { box-shadow: none; border: 1px solid #ddd; }
    .chart-container { box-shadow: none; border: 1px solid #ddd; break-inside: avoid; }
    .employee-section { box-shadow: none; border: 1px solid #ddd; break-inside: avoid; }
    .container-fluid { padding: 0 !important; }
    body { padding: 0; margin: 0; }
}
```

**Step 4: Create the hub page**

Create `app/templates/reports/index.html`:

```html
{% extends "base.html" %}

{% block title %}Reports{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/reports.css') }}">
{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="report-header">
        <div>
            <h1><i class="fas fa-chart-bar" style="margin-right: 8px;"></i>Reports</h1>
            <div class="subtitle">Generate reports with charts, tables, and export options</div>
        </div>
    </div>

    <div class="reports-grid">
        <div class="report-card">
            <div class="icon">📊</div>
            <h3>Event Statistics</h3>
            <p>Summary stats, completion rate, events by condition grouped by week.</p>
            <a href="{{ url_for('reports.event_statistics') }}" class="open-link">Open Report →</a>
        </div>
        <div class="report-card">
            <div class="icon">👥</div>
            <h3>Employee Schedule Details</h3>
            <p>Each employee's assigned events with dates and totals.</p>
            <a href="{{ url_for('reports.employee_schedules') }}" class="open-link">Open Report →</a>
        </div>
        <div class="report-card">
            <div class="icon">🍩</div>
            <h3>Event Type Breakdown</h3>
            <p>Count and percentage of each event type with donut chart.</p>
            <a href="{{ url_for('reports.event_type_breakdown') }}" class="open-link">Open Report →</a>
        </div>
        <div class="report-card">
            <div class="icon">⚖️</div>
            <h3>Employee Workload</h3>
            <p>Hours per employee with overload status indicators.</p>
            <a href="{{ url_for('reports.employee_workload') }}" class="open-link">Open Report →</a>
        </div>
        <div class="report-card">
            <div class="icon">✅</div>
            <h3>Attendance Report</h3>
            <p>On-time, late, and absence tracking per employee.</p>
            <a href="{{ url_for('reports.attendance') }}" class="open-link">Open Report →</a>
        </div>
        <div class="report-card">
            <div class="icon">📈</div>
            <h3>Scheduling Coverage</h3>
            <p>Daily coverage percentage — scheduled vs total events.</p>
            <a href="{{ url_for('reports.scheduling_coverage') }}" class="open-link">Open Report →</a>
        </div>
        <div class="report-card">
            <div class="icon">🏖️</div>
            <h3>Time Off Summary</h3>
            <p>Employee time-off blocks with timeline and totals.</p>
            <a href="{{ url_for('reports.time_off') }}" class="open-link">Open Report →</a>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 5: Register blueprint in `app/__init__.py`**

After the `api_locked_days_bp` registration (line 252), add:

```python
    from app.routes.reports import reports_bp
    app.register_blueprint(reports_bp)
```

**Step 6: Add sidebar link in `base.html`**

In the Tools group, after the "Available Blocks" link and before the "Scan-Out Checklist" link, add:

```html
            <a href="{{ url_for('reports.index') }}"
                class="sidebar-item {% if request.endpoint and request.endpoint.startswith('reports.') %}active{% endif %}">
                <span class="material-symbols-outlined">bar_chart</span>
                <span>Reports</span>
            </a>
```

**Step 7: Remove Corporate Report button from unscheduled.html**

In `app/templates/unscheduled.html`, remove the Corporate Report link (the `<a>` tag with `export_corporate_report`).

**Step 8: Commit**

```bash
git add app/services/report_service.py app/routes/reports.py \
  app/templates/reports/index.html app/static/css/pages/reports.css \
  app/__init__.py app/templates/base.html app/templates/unscheduled.html
git commit -m "feat: add reports section foundation — service, blueprint, hub page, sidebar link"
```

---

### Task 2: Event Statistics Report (Report 1)

**Files:**
- Create: `app/templates/reports/event_statistics.html`

**Step 1: Create the template**

This page shows summary stat cards, a pie chart of events by condition, and a weekly grouped table.

Create `app/templates/reports/event_statistics.html` with:
- Extends `base.html`, loads `reports.css` and Chart.js CDN
- Date range form (start_date/end_date inputs + Generate button)
- 4 stat cards: Total Events, Completion Rate, Scheduled %, Unscheduled %
- Chart.js pie chart using `data.by_condition` (labels = condition names, data = counts)
- Table grouped by week with week header rows, event detail rows
- Print button (using `data-action="print"`) and back link to hub

**Step 2: Test by navigating to `/reports/event-statistics`**

**Step 3: Commit**

```bash
git add app/templates/reports/event_statistics.html
git commit -m "feat: add Event Statistics report with pie chart and weekly table"
```

---

### Task 3: Employee Schedule Details Report (Report 2)

**Files:**
- Create: `app/templates/reports/employee_schedules.html`

**Step 1: Create the template**

- Date range form
- Chart.js horizontal bar chart: events per employee
- Per-employee sections: name, summary line (X events, Y days), table of events sorted by schedule date
- Print button

**Step 2: Test by navigating to `/reports/employee-schedules`**

**Step 3: Commit**

```bash
git add app/templates/reports/employee_schedules.html
git commit -m "feat: add Employee Schedule Details report with bar chart"
```

---

### Task 4: Event Type Breakdown Report (Report 3)

**Files:**
- Create: `app/templates/reports/event_type_breakdown.html`

**Step 1: Create the template**

- Date range form
- Stat card: Total Events
- Chart.js donut chart: each type's share (use distinct colors per type)
- Table: Event Type, Count, Percentage (sorted by count desc)
- Print button

**Step 2: Test by navigating to `/reports/event-type-breakdown`**

**Step 3: Commit**

```bash
git add app/templates/reports/event_type_breakdown.html
git commit -m "feat: add Event Type Breakdown report with donut chart"
```

---

### Task 5: Employee Workload Report (Report 4)

**Files:**
- Create: `app/templates/reports/employee_workload.html`

**Step 1: Create the template**

- Date range form
- Chart.js horizontal bar chart: hours per employee (color-coded by status)
- Table: Employee, Event Count, Total Hours, Avg Hours/Event, Status badge
- Status badges: Normal (green), High (yellow), Overloaded (red)
- Print button

**Step 2: Test by navigating to `/reports/employee-workload`**

**Step 3: Commit**

```bash
git add app/templates/reports/employee_workload.html
git commit -m "feat: add Employee Workload report with bar chart and status badges"
```

---

### Task 6: Attendance Report (Report 5)

**Files:**
- Create: `app/templates/reports/attendance.html`

**Step 1: Create the template**

- Date range form (defaults to current month)
- Chart.js stacked bar chart: per employee (on_time, late, called_in, no_call_no_show, excused_absence)
- Table: Employee, Days Tracked, On-Time, Late, Called-In, NCNS, Excused, Attendance Rate %
- Print button

**Step 2: Test by navigating to `/reports/attendance`**

**Step 3: Commit**

```bash
git add app/templates/reports/attendance.html
git commit -m "feat: add Attendance report with stacked bar chart"
```

---

### Task 7: Scheduling Coverage Report (Report 6)

**Files:**
- Create: `app/templates/reports/scheduling_coverage.html`

**Step 1: Create the template**

- Date range form
- 3 stat cards: Overall Coverage %, Best Day, Worst Day
- Chart.js line chart: coverage % per day over the range
- Table: Date, Day, Total Events, Scheduled, Unscheduled, Coverage %
- Print button

**Step 2: Test by navigating to `/reports/scheduling-coverage`**

**Step 3: Commit**

```bash
git add app/templates/reports/scheduling_coverage.html
git commit -m "feat: add Scheduling Coverage report with line chart"
```

---

### Task 8: Time Off Summary Report (Report 7)

**Files:**
- Create: `app/templates/reports/time_off.html`

**Step 1: Create the template**

- Date range form (defaults to current month)
- Stat card: Total Time-Off Days
- Chart.js horizontal bar chart: days off per employee (as a simple timeline proxy)
- Table: Employee, Start Date, End Date, Days Off, Reason
- Print button

**Step 2: Test by navigating to `/reports/time-off`**

**Step 3: Commit**

```bash
git add app/templates/reports/time_off.html
git commit -m "feat: add Time Off Summary report with bar chart"
```

---

### Task 9: CSV Export for All Reports

**Files:**
- Modify: `app/routes/reports.py` (add export routes)

**Step 1: Add CSV export routes**

For each report, add a `/reports/<name>/export` route that generates a CSV download using the same service method. Pattern:

```python
@reports_bp.route('/event-statistics/export')
def export_event_statistics():
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_event_statistics(start, end)
    # Build CSV from data
    output = io.StringIO()
    writer = csv.writer(output)
    # ... write headers and rows
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=event_statistics_{start}_{end}.csv'
    return response
```

Add one export route per report. Each template's "Export CSV" button links to the export URL with the same date params.

**Step 2: Test by clicking Export CSV on each report**

**Step 3: Commit**

```bash
git add app/routes/reports.py
git commit -m "feat: add CSV export for all 7 reports"
```

---

### Task 10: Tests and Final Verification

**Files:**
- Create: `tests/test_reports.py`

**Step 1: Write tests**

Test that each report route returns 200, that the service methods return the expected structure, and that CSV exports work.

```python
import pytest
from datetime import date, timedelta


class TestReportRoutes:
    """Test that all report pages load successfully."""

    def test_reports_hub(self, client):
        resp = client.get('/reports/')
        assert resp.status_code == 200

    def test_event_statistics(self, client, db_session):
        resp = client.get('/reports/event-statistics')
        assert resp.status_code == 200

    def test_employee_schedules(self, client, db_session):
        resp = client.get('/reports/employee-schedules')
        assert resp.status_code == 200

    def test_event_type_breakdown(self, client, db_session):
        resp = client.get('/reports/event-type-breakdown')
        assert resp.status_code == 200

    def test_employee_workload(self, client, db_session):
        resp = client.get('/reports/employee-workload')
        assert resp.status_code == 200

    def test_attendance(self, client, db_session):
        resp = client.get('/reports/attendance')
        assert resp.status_code == 200

    def test_scheduling_coverage(self, client, db_session):
        resp = client.get('/reports/scheduling-coverage')
        assert resp.status_code == 200

    def test_time_off(self, client, db_session):
        resp = client.get('/reports/time-off')
        assert resp.status_code == 200


class TestReportExports:
    """Test CSV exports return downloadable files."""

    def test_event_statistics_export(self, client, db_session):
        resp = client.get('/reports/event-statistics/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'
```

**Step 2: Run tests**

Run: `pytest tests/test_reports.py -v`

**Step 3: Run full test suite**

Run: `pytest -v --ignore=tests/test_ml_scheduling_adapter.py --ignore=tests/test_ml_training_pipeline.py --ignore=tests/test_ml_feature_engineering.py --ignore=tests/test_ml_integration.py`

**Step 4: Commit**

```bash
git add tests/test_reports.py
git commit -m "test: add report route and export tests"
```
