"""
Daily Validation Dashboard Blueprint
Provides visual overview of scheduling status and validation checks
"""
from flask import Blueprint, render_template, jsonify, current_app, redirect, url_for
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
from urllib.parse import quote

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/command-center')
def command_center():
    """
    Morning Command Center - Unified view of everything that needs attention.

    Shows:
    - Deadline countdown (if Fri/Sat/EOM)
    - Quick stats bar
    - Deadline events (LIA needing scan-out)
    - Unscheduled urgent events
    - Pending tasks and notes
    - Employee issues (time-off, notes)
    - Today's rotation assignments
    """
    from app.services.command_center_service import CommandCenterService
    from app.models import get_models

    try:
        db = current_app.extensions['sqlalchemy']
        models = get_models()

        service = CommandCenterService(db, models)
        dashboard_data = service.get_dashboard_data()

        return render_template(
            'dashboard/command_center.html',
            data=dashboard_data
        )
    except Exception as e:
        current_app.logger.error(f"Command center error: {str(e)}")
        # Fallback to daily schedule if command center fails
        return redirect(url_for('main.today'))


@dashboard_bp.route('/api/command-center')
def command_center_api():
    """API endpoint for command center data (for AJAX refresh)"""
    from app.services.command_center_service import CommandCenterService
    from app.models import get_models

    try:
        db = current_app.extensions['sqlalchemy']
        models = get_models()

        service = CommandCenterService(db, models)
        data = service.get_dashboard_data()

        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        current_app.logger.error(f"Command center API error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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
    Event = models['Event']
    Schedule = models['Schedule']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    ScheduleException = current_app.config.get('ScheduleException')
    EmployeeTimeOff = models['EmployeeTimeOff']
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

    # Check 6: Rotation employee unavailable AND actually scheduled
    # Only warn if the rotation employee has time off AND has events scheduled for today
    rotation_warnings = []
    if juicer_rotation:
        juicer_time_off = db.session.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == juicer_rotation['employee_id'],
            EmployeeTimeOff.start_date <= today,
            EmployeeTimeOff.end_date >= today
        ).first()
        
        # Check if this employee is actually scheduled for today
        juicer_scheduled_today = db.session.query(Schedule).filter(
            Schedule.employee_id == juicer_rotation['employee_id'],
            func.date(Schedule.schedule_datetime) == today
        ).first()
        
        if juicer_time_off and not juicer_rotation['is_exception'] and juicer_scheduled_today:
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
        
        # Check if this employee is actually scheduled for today
        lead_scheduled_today = db.session.query(Schedule).filter(
            Schedule.employee_id == primary_lead_rotation['employee_id'],
            func.date(Schedule.schedule_datetime) == today
        ).first()
        
        if lead_time_off and not primary_lead_rotation['is_exception'] and lead_scheduled_today:
            rotation_warnings.append({
                'rotation_type': 'Primary Lead',
                'employee_name': primary_lead_rotation['employee_name'],
                'reason': lead_time_off.reason
            })

    if rotation_warnings:
        validation_issues.append({
            'severity': 'warning',
            'type': 'rotation_unavailable',
            'message': f'{len(rotation_warnings)} rotation employee(s) have time off today but are still scheduled',
            'count': len(rotation_warnings),
            'details': rotation_warnings,
            'action': 'Reassign their scheduled events',
            'url': '/rotations'
        })

    # Check 7: Pending schedules awaiting approval
    # Only check if PendingSchedule model exists and is properly configured
    # Filter to only include pending schedules for events within active date range
    try:
        if PendingSchedule is not None:
            # Only count pending schedules for events starting within the next 2 weeks
            two_weeks_ahead = today + timedelta(days=14)
            
            pending_count = db.session.query(PendingSchedule).join(
                Event, PendingSchedule.event_ref_num == Event.project_ref_num
            ).filter(
                PendingSchedule.status == 'proposed',
                Event.start_datetime >= datetime.combine(today, datetime.min.time()),
                Event.start_datetime <= datetime.combine(two_weeks_ahead, datetime.max.time())
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
    Event = models['Event']
    Schedule = models['Schedule']

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


@dashboard_bp.route('/weekly-validation')
def weekly_validation():
    """
    Weekly validation dashboard showing 7-day schedule validation overview

    Displays:
    - Week health score
    - Daily validation summaries with issue counts
    - Cross-day (weekly) validation issues
    - Drill-down capability to daily view

    Query Parameters:
    - start_date: First day of week to validate (YYYY-MM-DD format), defaults to today
    """
    from flask import request
    from app.services.weekly_validation import WeeklyValidationService
    from app.models import get_models

    db = current_app.extensions['sqlalchemy']
    all_models = get_models()

    # Build models dictionary for WeeklyValidationService
    models = {
        'Event': all_models['Event'],
        'Schedule': all_models['Schedule'],
        'Employee': all_models['Employee'],
        'EmployeeTimeOff': all_models['EmployeeTimeOff'],
        'EmployeeAvailability': all_models.get('EmployeeAvailability'),
        'EmployeeWeeklyAvailability': all_models.get('EmployeeWeeklyAvailability'),
        'EmployeeAttendance': all_models.get('EmployeeAttendance'),
        'RotationAssignment': all_models['RotationAssignment'],
        'ScheduleException': all_models.get('ScheduleException'),
        'PendingSchedule': all_models.get('PendingSchedule'),
        'IgnoredValidationIssue': all_models.get('IgnoredValidationIssue')
    }

    # Get start date from query parameter or default to the start of the current week (Sunday)
    date_param = request.args.get('start_date')
    if date_param:
        try:
            start_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            start_date = date.today()
    else:
        start_date = date.today()

    # Align to Sunday (start of week) - weekday() returns 0=Monday, so Sunday is 6
    # Move back to the previous Sunday (or stay if already Sunday)
    days_since_sunday = (start_date.weekday() + 1) % 7  # Sunday=0, Monday=1, ..., Saturday=6
    start_date = start_date - timedelta(days=days_since_sunday)

    # Run weekly validation
    service = WeeklyValidationService(db.session, models)
    result = service.validate_week(start_date)

    return render_template('dashboard/weekly_validation.html',
                         result=result,
                         start_date=start_date,
                         end_date=result.week_end,
                         timedelta=timedelta)


@dashboard_bp.route('/api/weekly-validation')
def weekly_validation_api():
    """
    API endpoint for weekly validation (JSON)

    Query Parameters:
    - start_date: First day of week (YYYY-MM-DD format), defaults to today

    Returns:
        JSON with weekly validation results
    """
    from flask import request
    from app.services.weekly_validation import WeeklyValidationService
    from app.models import get_models

    db = current_app.extensions['sqlalchemy']
    all_models = get_models()

    # Build models dictionary for WeeklyValidationService
    models = {
        'Event': all_models['Event'],
        'Schedule': all_models['Schedule'],
        'Employee': all_models['Employee'],
        'EmployeeTimeOff': all_models['EmployeeTimeOff'],
        'EmployeeAvailability': all_models.get('EmployeeAvailability'),
        'EmployeeWeeklyAvailability': all_models.get('EmployeeWeeklyAvailability'),
        'EmployeeAttendance': all_models.get('EmployeeAttendance'),
        'RotationAssignment': all_models['RotationAssignment'],
        'ScheduleException': all_models.get('ScheduleException'),
        'PendingSchedule': all_models.get('PendingSchedule'),
        'IgnoredValidationIssue': all_models.get('IgnoredValidationIssue')
    }

    # Get start date
    date_param = request.args.get('start_date')
    if date_param:
        try:
            start_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            start_date = date.today()
    else:
        start_date = date.today()

    # Align to Sunday (start of week) - weekday() returns 0=Monday, so Sunday is 6
    # Move back to the previous Sunday (or stay if already Sunday)
    days_since_sunday = (start_date.weekday() + 1) % 7  # Sunday=0, Monday=1, ..., Saturday=6
    start_date = start_date - timedelta(days=days_since_sunday)

    # Run validation
    service = WeeklyValidationService(db.session, models)
    result = service.validate_week(start_date)

    return jsonify(result.to_dict())


@dashboard_bp.route('/api/validation/ignore', methods=['POST'])
def ignore_validation_issue():
    """
    Ignore a validation issue so it won't appear in future validations
    
    Request body:
    - rule_name: Name of the validation rule
    - details: Details dict from the issue (used to generate hash)
    - message: The issue message (for display)
    - severity: Issue severity
    - reason: Optional reason for ignoring
    - expires_days: Optional number of days until ignore expires (null = never)
    """
    from flask import request
    from datetime import datetime, timedelta
    
    db = current_app.extensions['sqlalchemy']
    IgnoredValidationIssue = current_app.config.get('IgnoredValidationIssue')
    
    if not IgnoredValidationIssue:
        return jsonify({'error': 'IgnoredValidationIssue model not available'}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    rule_name = data.get('rule_name')
    details = data.get('details', {})
    message = data.get('message', '')
    severity = data.get('severity', 'warning')
    reason = data.get('reason', '')
    expires_days = data.get('expires_days')
    
    if not rule_name:
        return jsonify({'error': 'rule_name is required'}), 400
    
    # Generate hash for this issue
    issue_hash = IgnoredValidationIssue.generate_hash(rule_name, details)
    
    # Check if already ignored
    existing = db.session.query(IgnoredValidationIssue).filter_by(issue_hash=issue_hash).first()
    if existing:
        return jsonify({'success': True, 'message': 'Issue already ignored', 'id': existing.id})
    
    # Calculate expiration
    expires_at = None
    if expires_days:
        expires_at = datetime.now() + timedelta(days=int(expires_days))
    
    # Create ignored issue record
    ignored = IgnoredValidationIssue(
        rule_name=rule_name,
        issue_hash=issue_hash,
        issue_date=details.get('date') if details.get('date') else None,
        schedule_id=details.get('schedule_id'),
        employee_id=details.get('employee_id'),
        event_id=details.get('event_id'),
        message=message,
        severity=severity,
        reason=reason,
        expires_at=expires_at
    )
    
    # Handle date field properly
    if ignored.issue_date and isinstance(ignored.issue_date, str):
        try:
            ignored.issue_date = datetime.strptime(ignored.issue_date, '%Y-%m-%d').date()
        except ValueError:
            ignored.issue_date = None
    
    db.session.add(ignored)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Issue ignored successfully',
        'id': ignored.id,
        'hash': issue_hash
    })


@dashboard_bp.route('/api/validation/unignore', methods=['POST'])
def unignore_validation_issue():
    """
    Remove an issue from the ignored list
    
    Request body:
    - issue_hash: Hash of the issue to unignore
    OR
    - id: ID of the ignored issue record
    """
    from flask import request
    
    db = current_app.extensions['sqlalchemy']
    IgnoredValidationIssue = current_app.config.get('IgnoredValidationIssue')
    
    if not IgnoredValidationIssue:
        return jsonify({'error': 'IgnoredValidationIssue model not available'}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    issue_hash = data.get('issue_hash')
    issue_id = data.get('id')
    
    if issue_hash:
        ignored = db.session.query(IgnoredValidationIssue).filter_by(issue_hash=issue_hash).first()
    elif issue_id:
        ignored = db.session.query(IgnoredValidationIssue).get(issue_id)
    else:
        return jsonify({'error': 'Either issue_hash or id is required'}), 400
    
    if not ignored:
        return jsonify({'error': 'Ignored issue not found'}), 404
    
    db.session.delete(ignored)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Issue unignored successfully'})


@dashboard_bp.route('/api/validation/ignored')
def list_ignored_issues():
    """
    Get list of all currently ignored validation issues
    """
    from datetime import datetime
    
    db = current_app.extensions['sqlalchemy']
    IgnoredValidationIssue = current_app.config.get('IgnoredValidationIssue')
    
    if not IgnoredValidationIssue:
        return jsonify({'error': 'IgnoredValidationIssue model not available'}), 500
    
    # Get all non-expired ignored issues
    ignored_list = db.session.query(IgnoredValidationIssue).filter(
        or_(
            IgnoredValidationIssue.expires_at.is_(None),
            IgnoredValidationIssue.expires_at > datetime.now()
        )
    ).all()
    
    return jsonify({
        'ignored_issues': [
            {
                'id': i.id,
                'rule_name': i.rule_name,
                'issue_hash': i.issue_hash,
                'message': i.message,
                'severity': i.severity,
                'reason': i.reason,
                'ignored_at': i.ignored_at.isoformat() if i.ignored_at else None,
                'expires_at': i.expires_at.isoformat() if i.expires_at else None
            }
            for i in ignored_list
        ]
    })


@dashboard_bp.route('/api/validation/assign-supervisor', methods=['POST'])
def assign_supervisor_event():
    """
    Automatically assign a Supervisor event for a Core event.

    This endpoint finds the matching Supervisor event for a Core event
    and schedules it to the appropriate person (Club Supervisor or Primary Lead).

    Request body:
    - core_event_ref: Reference number of the Core event
    - date: Date string (YYYY-MM-DD)
    """
    from flask import request
    from datetime import datetime
    import re

    db = current_app.extensions['sqlalchemy']
    Event = models['Event']
    Schedule = models['Schedule']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    EmployeeTimeOff = models['EmployeeTimeOff']
    EmployeeWeeklyAvailability = current_app.config.get('EmployeeWeeklyAvailability')

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    core_event_ref = data.get('core_event_ref')
    date_str = data.get('date')

    if not core_event_ref or not date_str:
        return jsonify({'error': 'core_event_ref and date are required'}), 400

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Get the Core event
    core_event = db.session.query(Event).filter_by(project_ref_num=core_event_ref).first()
    if not core_event:
        return jsonify({'error': 'Core event not found'}), 404

    # Extract 6-digit event number from Core event name
    match = re.search(r'\d{6}', core_event.project_name)
    if not match:
        return jsonify({'error': 'Could not extract event number from Core event name'}), 400

    event_number = match.group(0)

    # Find the matching Supervisor event
    supervisor_event = db.session.query(Event).filter(
        Event.event_type == 'Supervisor',
        Event.project_name.contains(event_number)
    ).first()

    if not supervisor_event:
        return jsonify({'error': f'No Supervisor event found matching event number {event_number}'}), 404

    # Check if Supervisor event is already scheduled
    existing_schedule = db.session.query(Schedule).filter_by(
        event_ref_num=supervisor_event.project_ref_num
    ).first()

    if existing_schedule:
        return jsonify({'error': 'Supervisor event is already scheduled', 'schedule_id': existing_schedule.id}), 400

    # Get the Core event's schedule to get the time
    core_schedule = db.session.query(Schedule).filter_by(
        event_ref_num=core_event_ref
    ).first()

    if not core_schedule:
        return jsonify({'error': 'Core event is not scheduled'}), 400

    # Supervisor event should be scheduled 30 minutes after Core event starts
    supervisor_datetime = core_schedule.schedule_datetime + timedelta(minutes=30)

    # Find the best employee for the Supervisor event
    # Priority: Club Supervisor > Primary Lead for the day > Core event employee
    supervisor_employee = None

    # Helper function to check availability
    def is_employee_available(employee, check_date):
        # Check time off
        time_off = db.session.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == employee.id,
            EmployeeTimeOff.start_date <= check_date,
            EmployeeTimeOff.end_date >= check_date
        ).first()
        if time_off:
            return False

        # Check weekly availability
        if EmployeeWeeklyAvailability:
            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_column = day_names[check_date.weekday()]
            weekly_avail = db.session.query(EmployeeWeeklyAvailability).filter_by(
                employee_id=employee.id
            ).first()
            if weekly_avail:
                if not getattr(weekly_avail, day_column, True):
                    return False

        return True

    # Try Club Supervisor first
    club_supervisor = db.session.query(Employee).filter_by(
        job_title='Club Supervisor',
        is_active=True
    ).first()

    if club_supervisor and is_employee_available(club_supervisor, target_date):
        supervisor_employee = club_supervisor

    # Try Primary Lead for the day
    if not supervisor_employee:
        day_of_week = target_date.weekday()
        primary_lead_rotation = db.session.query(RotationAssignment).filter_by(
            day_of_week=day_of_week,
            rotation_type='primary_lead'
        ).first()

        if primary_lead_rotation:
            primary_lead = db.session.query(Employee).get(primary_lead_rotation.employee_id)
            if primary_lead and is_employee_available(primary_lead, target_date):
                supervisor_employee = primary_lead

    # Fallback to the Core event's employee
    if not supervisor_employee and core_schedule.employee_id:
        core_employee = db.session.query(Employee).get(core_schedule.employee_id)
        if core_employee:
            supervisor_employee = core_employee

    if not supervisor_employee:
        return jsonify({'error': 'No suitable employee found for Supervisor event'}), 400

    # Create the schedule
    try:
        new_schedule = Schedule(
            event_ref_num=supervisor_event.project_ref_num,
            employee_id=supervisor_employee.id,
            schedule_datetime=supervisor_datetime
        )
        db.session.add(new_schedule)

        # Update event condition
        supervisor_event.condition = 'Scheduled'

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Supervisor event scheduled to {supervisor_employee.name}',
            'schedule_id': new_schedule.id,
            'employee_name': supervisor_employee.name,
            'datetime': supervisor_datetime.isoformat()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error assigning supervisor event: {e}')
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/approved-events')
def approved_events():
    """
    Approved Events Dashboard for Walmart scan-out tracking.

    Displays APPROVED events from Walmart Retail Link merged with local
    database status to help users:
    - See which events need scheduling
    - See which events need API submission
    - See which events need scan-out in Walmart

    Business Rule: APPROVED events must be scanned out by 6 PM on:
    - Fridays
    - Saturdays
    - Last day of the month

    Query Parameters:
        club: Optional default club number to pre-populate
    """
    from flask import request

    # Get optional club parameter
    club = request.args.get('club', '8135')

    return render_template('dashboard/approved_events.html', club=club)
