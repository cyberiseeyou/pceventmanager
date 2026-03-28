"""
Reports Blueprint
Provides report pages with charts and data tables.
"""
from flask import Blueprint, render_template, request, current_app, make_response
from datetime import datetime, date, timedelta
from app.models import get_models
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
    """Parse start_date and end_date from query params, with defaults.

    Enforces a floor of 30 days ago — the external API only fetches events
    within a 30-day lookback window, so older data is unreliable.
    """
    today = date.today()
    earliest_allowed = today - timedelta(days=30)

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

    # Clamp start date to 30-day lookback floor
    if start < earliest_allowed:
        start = earliest_allowed

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


@reports_bp.route('/weekly-scheduled-hours')
def weekly_scheduled_hours():
    """Report 8: Weekly Scheduled Hours (excludes Club Supervisors)."""
    today = date.today()
    # Default to current week (Sunday through Saturday)
    days_since_sunday = (today.weekday() + 1) % 7
    default_start = today - timedelta(days=days_since_sunday)
    default_end = default_start + timedelta(days=6)
    start, end = _parse_dates(default_start=default_start, default_end=default_end)
    service = _get_service()
    data = service.get_weekly_scheduled_hours(start, end)
    return render_template('reports/weekly_scheduled_hours.html',
                         data=data, start_date=start, end_date=end)


# --- CSV Export Routes ---

@reports_bp.route('/event-statistics/export')
def export_event_statistics():
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_event_statistics(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Event Statistics Report', f'{start} to {end}'])
    writer.writerow([f'Total: {data["total"]}', f'Completion Rate: {data["completion_rate"]}%',
                     f'Scheduled: {data["scheduled_pct"]}%', f'Unstaffed: {data["unstaffed_pct"]}%',
                     f'Lost Demo Rate: {data["lost_rate"]}%'])
    writer.writerow([])
    for week in data['weeks']:
        writer.writerow([f'Week of {week["start"]} - {week["end"]} ({week["count"]} events)'])
        writer.writerow(['Event #', 'Name', 'Type', 'Status', 'Start', 'Due', 'Employee', 'Scheduled', 'Days Available'])
        for e in week['events']:
            writer.writerow([e['ref_num'], e['name'], e['event_type'], e['condition'],
                           e['start_date'], e['due_date'], e['employee'], e['schedule_date'], e['days_available']])
        writer.writerow([])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=event_statistics_{start}_{end}.csv'
    return resp


@reports_bp.route('/employee-schedules/export')
def export_employee_schedules():
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_employee_schedules(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Employee Schedule Details', f'{start} to {end}'])
    writer.writerow([])
    for emp in data:
        writer.writerow([emp['name'], f'{emp["event_count"]} events', f'{emp["days_scheduled"]} days'])
        writer.writerow(['Event Name', 'Type', 'Start', 'End', 'Scheduled'])
        for e in emp['events']:
            writer.writerow([e['name'], e['event_type'], e['start_date'], e['end_date'], e['schedule_date']])
        writer.writerow([])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=employee_schedules_{start}_{end}.csv'
    return resp


@reports_bp.route('/event-type-breakdown/export')
def export_event_type_breakdown():
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_event_type_breakdown(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Event Type Breakdown', f'{start} to {end}', f'Total: {data["total"]}'])
    writer.writerow(['Event Type', 'Count', 'Percentage'])
    for t in data['types']:
        writer.writerow([t['event_type'], t['count'], f'{t["percentage"]}%'])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=event_type_breakdown_{start}_{end}.csv'
    return resp


@reports_bp.route('/employee-workload/export')
def export_employee_workload():
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_employee_workload(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Employee Workload', f'{start} to {end}'])
    writer.writerow(['Employee', 'Events', 'Total Hours', 'Avg Hours', 'Status'])
    for e in data:
        writer.writerow([e['name'], e['event_count'], e['total_hours'], e['avg_hours'], e['status']])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=employee_workload_{start}_{end}.csv'
    return resp


@reports_bp.route('/attendance/export')
def export_attendance():
    today = date.today()
    start, end = _parse_dates(default_start=today.replace(day=1), default_end=today)
    service = _get_service()
    data = service.get_attendance_report(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Attendance Report', f'{start} to {end}'])
    writer.writerow(['Employee', 'Days Tracked', 'On-Time', 'Late', 'Called-In', 'NCNS', 'Excused', 'Rate %'])
    for e in data:
        writer.writerow([e['name'], e['total'], e['on_time'], e['late'], e['called_in'],
                        e['no_call_no_show'], e['excused_absence'], f'{e["attendance_rate"]}%'])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=attendance_{start}_{end}.csv'
    return resp


@reports_bp.route('/scheduling-coverage/export')
def export_scheduling_coverage():
    start, end = _parse_dates()
    service = _get_service()
    data = service.get_scheduling_coverage(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Scheduling Coverage', f'{start} to {end}', f'Overall: {data["overall_coverage"]}%'])
    writer.writerow(['Date', 'Day', 'Total', 'Scheduled', 'Unscheduled', 'Coverage %'])
    for d in data['days']:
        writer.writerow([d['date'], d['day_name'], d['total'], d['scheduled'], d['unscheduled'], f'{d["coverage"]}%'])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=scheduling_coverage_{start}_{end}.csv'
    return resp


@reports_bp.route('/time-off/export')
def export_time_off():
    today = date.today()
    start, end = _parse_dates(default_start=today.replace(day=1), default_end=today)
    service = _get_service()
    data = service.get_time_off_summary(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Time Off Summary', f'{start} to {end}', f'Total Days: {data["total_days"]}'])
    writer.writerow(['Employee', 'Start', 'End', 'Days', 'Reason'])
    for r in data['records']:
        writer.writerow([r['name'], r['start_date'], r['end_date'], r['days'], r['reason']])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=time_off_{start}_{end}.csv'
    return resp


@reports_bp.route('/weekly-scheduled-hours/export')
def export_weekly_scheduled_hours():
    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7
    default_start = today - timedelta(days=days_since_sunday)
    default_end = default_start + timedelta(days=6)
    start, end = _parse_dates(default_start=default_start, default_end=default_end)
    service = _get_service()
    data = service.get_weekly_scheduled_hours(start, end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Weekly Scheduled Hours (excl. Club Supervisors)', f'{start} to {end}'])
    writer.writerow(['Team Avg Weekly: {0}h'.format(data['team_avg_weekly']),
                     'Per Employee Avg: {0}h'.format(data['per_employee_avg_weekly'])])
    writer.writerow([])
    header = ['Employee', 'Job Title'] + data['weeks'] + ['Total Hours', 'Avg Weekly Hours']
    writer.writerow(header)
    for e in data['employees']:
        row = [e['name'], e['job_title']] + [str(h) for h in e['weekly_hours']] + [e['total_hours'], e['avg_weekly_hours']]
        writer.writerow(row)
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=weekly_scheduled_hours_{start}_{end}.csv'
    return resp
