"""
Daily Validation Dashboard Blueprint
Provides visual overview of scheduling status and validation checks
"""
from flask import Blueprint, render_template, jsonify, current_app
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
from urllib.parse import quote

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/daily-validation')
def daily_validation():
    """
    Daily validation dashboard showing scheduling status for selected date

    Displays:
    - Event counts by type for selected date
    - Rotation assignments
    - Unscheduled events requiring attention
    - Validation warnings and errors
    - Quick action buttons

    Query Parameters:
    - date: Date to validate (YYYY-MM-DD format), defaults to today
    """
    from flask import request

    db = current_app.extensions['sqlalchemy']

    # Get models
    Event = current_app.config['Event']
    Schedule = current_app.config['Schedule']
    Employee = current_app.config['Employee']
    RotationAssignment = current_app.config['RotationAssignment']
    ScheduleException = current_app.config.get('ScheduleException')
    EmployeeTimeOff = current_app.config['EmployeeTimeOff']
    PendingSchedule = current_app.config.get('PendingSchedule')

    # Get selected date from query parameter or default to today
    date_param = request.args.get('date')
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()

    # Calculate relative dates based on selected date
    today = selected_date
    tomorrow = today + timedelta(days=1)
    three_days_ahead = today + timedelta(days=3)

    # ===== TODAY'S EVENT COUNTS BY TYPE =====
    today_events = _get_events_by_type(db, Event, Schedule, today)

    # ===== TOMORROW'S EVENT COUNTS BY TYPE =====
    tomorrow_events = _get_events_by_type(db, Event, Schedule, tomorrow)

    # ===== 3-DAY AHEAD EVENT COUNTS =====
    three_day_events = _get_events_by_type(db, Event, Schedule, three_days_ahead)

    # ===== ROTATION ASSIGNMENTS FOR TODAY =====
    day_of_week = today.weekday()

    # Get Juicer rotation
    juicer_rotation = None
    juicer_exception = None
    if ScheduleException:
        juicer_exception = db.session.query(ScheduleException).filter_by(
            exception_date=today,
            rotation_type='juicer'
        ).first()

    if juicer_exception:
        juicer_employee = db.session.query(Employee).get(juicer_exception.employee_id)
        juicer_rotation = {
            'employee_name': juicer_employee.name if juicer_employee else 'Unknown',
            'employee_id': juicer_exception.employee_id,
            'is_exception': True,
            'reason': juicer_exception.reason
        }
    else:
        rotation = db.session.query(RotationAssignment).filter_by(
            day_of_week=day_of_week,
            rotation_type='juicer'
        ).first()
        if rotation:
            employee = db.session.query(Employee).get(rotation.employee_id)
            juicer_rotation = {
                'employee_name': employee.name if employee else 'Unknown',
                'employee_id': rotation.employee_id,
                'is_exception': False,
                'reason': None
            }

    # Get Primary Lead rotation
    primary_lead_rotation = None
    primary_lead_exception = None
    if ScheduleException:
        primary_lead_exception = db.session.query(ScheduleException).filter_by(
            exception_date=today,
            rotation_type='primary_lead'
        ).first()

    if primary_lead_exception:
        lead_employee = db.session.query(Employee).get(primary_lead_exception.employee_id)
        primary_lead_rotation = {
            'employee_name': lead_employee.name if lead_employee else 'Unknown',
            'employee_id': primary_lead_exception.employee_id,
            'is_exception': True,
            'reason': primary_lead_exception.reason
        }
    else:
        rotation = db.session.query(RotationAssignment).filter_by(
            day_of_week=day_of_week,
            rotation_type='primary_lead'
        ).first()
        if rotation:
            employee = db.session.query(Employee).get(rotation.employee_id)
            primary_lead_rotation = {
                'employee_name': employee.name if employee else 'Unknown',
                'employee_id': rotation.employee_id,
                'is_exception': False,
                'reason': None
            }

    # ===== VALIDATION CHECKS =====
    validation_issues = []

    # Check 1: Unscheduled events due within 24 hours
    now = datetime.now()
    twenty_four_hours_from_now = now + timedelta(hours=24)
    urgent_unscheduled = db.session.query(Event).filter(
        Event.condition == 'Unstaffed',
        Event.due_datetime >= now,
        Event.due_datetime <= twenty_four_hours_from_now
    ).all()

    if urgent_unscheduled:
        # Generate search query for date range
        tomorrow = today + timedelta(days=1)
        date_search = f"d:{today.strftime('%m-%d-%y')} to {tomorrow.strftime('%m-%d-%y')}"

        validation_issues.append({
            'severity': 'critical',
            'type': 'unscheduled_urgent',
            'message': f'{len(urgent_unscheduled)} event(s) due within 24 hours are unscheduled',
            'count': len(urgent_unscheduled),
            'action': 'Schedule immediately',
            'url': f"/events?condition=unstaffed&search={quote(date_search)}"
        })

    # Check 2: Freeosk events today without assignments
    freeosk_today_unscheduled = db.session.query(Event).filter(
        Event.event_type == 'Freeosk',
        Event.start_datetime >= datetime.combine(today, datetime.min.time()),
        Event.start_datetime <= datetime.combine(today, datetime.max.time()),
        Event.condition == 'Unstaffed'
    ).count()

    if freeosk_today_unscheduled > 0:
        validation_issues.append({
            'severity': 'critical',
            'type': 'freeosk_unscheduled',
            'message': f'{freeosk_today_unscheduled} Freeosk event(s) today are unscheduled',
            'count': freeosk_today_unscheduled,
            'action': 'Assign to Primary Lead or Club Supervisor',
            'url': '/events?condition=unstaffed&event_type=Freeosk&date_filter=today'
        })

    # Check 3: Digital events today without assignments
    digital_today_unscheduled = db.session.query(Event).filter(
        Event.event_type == 'Digitals',
        Event.start_datetime >= datetime.combine(today, datetime.min.time()),
        Event.start_datetime <= datetime.combine(today, datetime.max.time()),
        Event.condition == 'Unstaffed'
    ).count()

    if digital_today_unscheduled > 0:
        validation_issues.append({
            'severity': 'critical',
            'type': 'digital_unscheduled',
            'message': f'{digital_today_unscheduled} Digital event(s) today are unscheduled',
            'count': digital_today_unscheduled,
            'action': 'Assign to Primary/Secondary Lead',
            'url': '/events?condition=unstaffed&event_type=Digitals&date_filter=today'
        })

    # Check 4: Core events without paired Supervisor events
    core_without_supervisor = []
    core_event_numbers = []
    core_events_scheduled = db.session.query(Event).join(
        Schedule, Event.project_ref_num == Schedule.event_ref_num
    ).filter(
        Event.event_type == 'Core',
        func.date(Schedule.schedule_datetime) >= today
    ).all()

    for core_event in core_events_scheduled:
        # Extract first 6 digits
        import re
        match = re.search(r'\d{6}', core_event.project_name)
        if match:
            event_number = match.group(0)
            # Look for Supervisor event with same number
            supervisor_event = db.session.query(Event).filter(
                Event.event_type == 'Supervisor',
                Event.project_name.contains(event_number)
            ).first()
            if not supervisor_event:
                core_without_supervisor.append(core_event)
                core_event_numbers.append(event_number)

    if core_without_supervisor:
        # Build search query with all event numbers
        search_query = ', '.join(core_event_numbers)
        validation_issues.append({
            'severity': 'warning',
            'type': 'missing_supervisor',
            'message': f'{len(core_without_supervisor)} Core event(s) missing paired Supervisor events',
            'count': len(core_without_supervisor),
            'action': 'Click to view these events and verify Supervisor events exist in MVRetail',
            'url': f'/events?condition=scheduled&event_type=Core&search={search_query}'
        })

    # Check 5: Employees scheduled during time off
    employees_with_conflicts = []
    today_schedules = db.session.query(Schedule, Employee).join(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        func.date(Schedule.schedule_datetime) == today
    ).all()

    for schedule, employee in today_schedules:
        time_off = db.session.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == employee.id,
            EmployeeTimeOff.start_date <= today,
            EmployeeTimeOff.end_date >= today
        ).first()
        if time_off:
            employees_with_conflicts.append({
                'employee_name': employee.name,
                'reason': time_off.reason
            })

    if employees_with_conflicts:
        validation_issues.append({
            'severity': 'critical',
            'type': 'time_off_conflict',
            'message': f'{len(employees_with_conflicts)} employee(s) scheduled during time off',
            'count': len(employees_with_conflicts),
            'details': employees_with_conflicts,
            'action': 'Reassign events immediately',
            'url': '/events?condition=scheduled&date_filter=today'
        })

    # Check 6: Rotation employee unavailable
    rotation_warnings = []
    if juicer_rotation:
        juicer_time_off = db.session.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == juicer_rotation['employee_id'],
            EmployeeTimeOff.start_date <= today,
            EmployeeTimeOff.end_date >= today
        ).first()
        if juicer_time_off and not juicer_rotation['is_exception']:
            rotation_warnings.append({
                'rotation_type': 'Juicer',
                'employee_name': juicer_rotation['employee_name'],
                'reason': juicer_time_off.reason
            })

    if primary_lead_rotation:
        lead_time_off = db.session.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == primary_lead_rotation['employee_id'],
            EmployeeTimeOff.start_date <= today,
            EmployeeTimeOff.end_date >= today
        ).first()
        if lead_time_off and not primary_lead_rotation['is_exception']:
            rotation_warnings.append({
                'rotation_type': 'Primary Lead',
                'employee_name': primary_lead_rotation['employee_name'],
                'reason': lead_time_off.reason
            })

    if rotation_warnings:
        validation_issues.append({
            'severity': 'warning',
            'type': 'rotation_unavailable',
            'message': f'{len(rotation_warnings)} rotation employee(s) have time off today',
            'count': len(rotation_warnings),
            'details': rotation_warnings,
            'action': 'Create Schedule Exception or reassign',
            'url': '/rotations'
        })

    # Check 7: Pending schedules awaiting approval
    # Only check if PendingSchedule model exists and is properly configured
    try:
        if PendingSchedule is not None:
            pending_count = db.session.query(PendingSchedule).filter(
                PendingSchedule.status == 'proposed'
            ).count()

            if pending_count > 0:
                validation_issues.append({
                    'severity': 'info',
                    'type': 'pending_approval',
                    'message': f'{pending_count} pending schedule(s) awaiting approval',
                    'count': pending_count,
                    'action': 'Review and approve in Auto-Scheduler',
                    'url': '/auto-schedule'
                })
    except Exception as e:
        # PendingSchedule table doesn't exist or has issues - skip this check
        current_app.logger.debug(f'Skipping pending schedules check: {e}')
        pass

    # Check 8: Events within 3-day window (should be scheduled)
    within_window_unscheduled = db.session.query(Event).filter(
        Event.condition == 'Unstaffed',
        Event.start_datetime >= datetime.combine(today, datetime.min.time()),
        Event.start_datetime <= datetime.combine(three_days_ahead, datetime.max.time())
    ).count()

    if within_window_unscheduled > 0:
        # Generate search query for 3-day window
        window_search = f"s:{today.strftime('%m-%d-%y')} to {three_days_ahead.strftime('%m-%d-%y')}"

        validation_issues.append({
            'severity': 'warning',
            'type': 'within_window',
            'message': f'{within_window_unscheduled} event(s) within 3-day window are unscheduled',
            'count': within_window_unscheduled,
            'action': 'Run auto-scheduler or manually assign',
            'url': f"/events?condition=unstaffed&search={quote(window_search)}"
        })

    # ===== SUMMARY STATISTICS =====
    total_events_today = sum([
        today_events['core']['scheduled'],
        today_events['juicer']['scheduled'],
        today_events['supervisor']['scheduled'],
        today_events['digitals']['scheduled'],
        today_events['freeosk']['scheduled'],
        today_events['other']['scheduled']
    ])

    total_unscheduled_today = sum([
        today_events['core']['unscheduled'],
        today_events['juicer']['unscheduled'],
        today_events['supervisor']['unscheduled'],
        today_events['digitals']['unscheduled'],
        today_events['freeosk']['unscheduled'],
        today_events['other']['unscheduled']
    ])

    active_employees = db.session.query(Employee).filter_by(is_active=True).count()

    # Calculate health score (0-100)
    health_score = _calculate_health_score(
        total_events_today,
        total_unscheduled_today,
        validation_issues
    )

    return render_template('dashboard/daily_validation.html',
                         today=today,
                         tomorrow=tomorrow,
                         three_days_ahead=three_days_ahead,
                         today_events=today_events,
                         tomorrow_events=tomorrow_events,
                         three_day_events=three_day_events,
                         juicer_rotation=juicer_rotation,
                         primary_lead_rotation=primary_lead_rotation,
                         validation_issues=validation_issues,
                         total_events_today=total_events_today,
                         total_unscheduled_today=total_unscheduled_today,
                         active_employees=active_employees,
                         health_score=health_score,
                         day_of_week=today.strftime('%A'))


def _get_events_by_type(db, Event, Schedule, target_date):
    """
    Get event counts by type for a specific date

    Returns dict with scheduled and unscheduled counts per type
    """
    event_types = ['Core', 'Juicer', 'Supervisor', 'Digitals', 'Freeosk', 'Other']
    result = {}

    for event_type in event_types:
        # Scheduled events (have Schedule record for this date AND condition is Scheduled or Submitted)
        scheduled_count = db.session.query(Event).join(
            Schedule, Event.project_ref_num == Schedule.event_ref_num
        ).filter(
            Event.event_type == event_type,
            func.date(Schedule.schedule_datetime) == target_date,
            Event.condition.in_(['Scheduled', 'Submitted'])
        ).count()

        # Unscheduled events (start_date is target_date, condition is Unstaffed)
        unscheduled_count = db.session.query(Event).filter(
            Event.event_type == event_type,
            Event.condition == 'Unstaffed',
            Event.start_datetime >= datetime.combine(target_date, datetime.min.time()),
            Event.start_datetime <= datetime.combine(target_date, datetime.max.time())
        ).count()

        result[event_type.lower()] = {
            'scheduled': scheduled_count,
            'unscheduled': unscheduled_count,
            'total': scheduled_count + unscheduled_count
        }

    return result


def _calculate_health_score(total_events, total_unscheduled, validation_issues):
    """
    Calculate scheduling health score (0-100)

    Factors:
    - Scheduling completion rate (50 points)
    - Number of critical issues (30 points)
    - Number of warnings (20 points)
    """
    score = 100

    # Factor 1: Scheduling completion (50 points max)
    if total_events > 0:
        completion_rate = (total_events - total_unscheduled) / total_events
        score -= (1 - completion_rate) * 50

    # Factor 2: Critical issues (10 points per issue, up to 30 points)
    critical_issues = [issue for issue in validation_issues if issue['severity'] == 'critical']
    score -= min(len(critical_issues) * 10, 30)

    # Factor 3: Warnings (5 points per warning, up to 20 points)
    warnings = [issue for issue in validation_issues if issue['severity'] == 'warning']
    score -= min(len(warnings) * 5, 20)

    return max(0, int(score))


@dashboard_bp.route('/api/validation-summary')
def validation_summary_api():
    """
    API endpoint for validation summary (for widgets or external monitoring)
    """
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']
    Schedule = current_app.config['Schedule']

    today = date.today()

    # Get today's events
    today_events = _get_events_by_type(db, Event, Schedule, today)

    total_events_today = sum([
        today_events['core']['scheduled'],
        today_events['juicer']['scheduled'],
        today_events['supervisor']['scheduled'],
        today_events['digitals']['scheduled'],
        today_events['freeosk']['scheduled'],
        today_events['other']['scheduled']
    ])

    total_unscheduled_today = sum([
        today_events['core']['unscheduled'],
        today_events['juicer']['unscheduled'],
        today_events['supervisor']['unscheduled'],
        today_events['digitals']['unscheduled'],
        today_events['freeosk']['unscheduled'],
        today_events['other']['unscheduled']
    ])

    # Count critical issues
    now = datetime.now()
    twenty_four_hours_from_now = now + timedelta(hours=24)
    urgent_unscheduled = db.session.query(Event).filter(
        Event.condition == 'Unstaffed',
        Event.due_datetime >= now,
        Event.due_datetime <= twenty_four_hours_from_now
    ).count()

    return jsonify({
        'date': today.isoformat(),
        'total_events_today': total_events_today,
        'total_unscheduled_today': total_unscheduled_today,
        'urgent_unscheduled': urgent_unscheduled,
        'health_score': _calculate_health_score(total_events_today, total_unscheduled_today, []),
        'events_by_type': today_events
    })
