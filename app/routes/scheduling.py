"""
Scheduling routes blueprint
Handles event scheduling, rescheduling, and schedule management operations
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, abort
from app.routes.auth import require_authentication
from datetime import datetime, timedelta

# Create blueprint
scheduling_bp = Blueprint('scheduling', __name__)


@scheduling_bp.route('/schedule/<int:event_id>')
def schedule_event(event_id):
    """Display scheduling form for an event"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    # Determine the action type based on event condition
    action_type = "Schedule"
    action_verb = "schedule"

    if event.condition == 'Scheduled':
        action_type = "Reschedule"
        action_verb = "reschedule"
    elif event.condition == 'Submitted':
        action_type = "Reissue"
        action_verb = "reissue"
    elif event.condition == 'Reissued':
        action_type = "Reschedule"
        action_verb = "reschedule"

    # Get return_url from query params (where to go after scheduling)
    return_url = request.args.get('return_url', '')

    return render_template('schedule.html',
                         event=event,
                         action_type=action_type,
                         action_verb=action_verb,
                         return_url=return_url)


def get_allowed_times_for_event_type(event_type, project_name=None):
    """Get allowed times for a specific event type from database settings"""
    from app.services.event_time_settings import get_allowed_times_for_event_type as get_times

    try:
        return get_times(event_type, project_name)
    except Exception as e:
        current_app.logger.error(f"Error loading event times for {event_type}: {e}")
        # Fallback to default times if settings not available
        time_restrictions = {
            'Core': ['09:45', '10:30', '11:00', '11:30'],
            'Supervisor': ['12:00'],
            'Freeosk': ['09:00', '12:00'],
            'Digitals': ['09:15', '09:30', '09:45', '10:00']
        }
        return time_restrictions.get(event_type, None)


def is_valid_time_for_event_type(event_type, time_obj, project_name=None):
    """Check if a time is valid for a specific event type"""
    allowed_times = get_allowed_times_for_event_type(event_type, project_name)

    # If no restrictions, all times are valid
    if not allowed_times:
        return True

    # Convert time object to string format for comparison
    time_str = time_obj.strftime('%H:%M')

    return time_str in allowed_times


@scheduling_bp.route('/api/available_employees/<date>')
@scheduling_bp.route('/api/available_employees/<date>/<int:event_id>')
def available_employees(date, event_id=None):
    """Get list of available employees for a specific date and event"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']
    Employee = current_app.config['Employee']
    Event = current_app.config['Event']
    Schedule = current_app.config['Schedule']
    EmployeeAvailability = current_app.config['EmployeeAvailability']
    EmployeeTimeOff = current_app.config['EmployeeTimeOff']
    EmployeeWeeklyAvailability = current_app.config['EmployeeWeeklyAvailability']

    # Check if override constraints is enabled
    override_constraints = request.args.get('override', 'false').lower() == 'true'

    # Validate date format
    try:
        parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    # Get all active employees
    all_employees = Employee.query.filter_by(is_active=True).all()

    # If override is enabled, skip all availability filtering and only check role-based restrictions
    if override_constraints:
        current_app.logger.info(
            f"[AVAILABLE_EMPLOYEES] Override enabled - showing all qualified employees for date {date}"
        )

        # Get event type for role-based filtering
        event_type = None
        if event_id:
            event = db.session.get(Event, event_id)
            if event:
                event_type = event.event_type

        # Only filter by role - show all employees who CAN work this event type
        available_employees_list = []
        for emp in all_employees:
            # Check role-based restrictions if we have an event type
            if event_type and not emp.can_work_event_type(event_type):
                continue

            available_employees_list.append({
                'id': emp.id,
                'name': emp.name,
                'is_supervisor': emp.is_supervisor,
                'job_title': emp.job_title,
                'adult_beverage_trained': emp.adult_beverage_trained
            })

        current_app.logger.info(
            f"[AVAILABLE_EMPLOYEES] Override mode: {len(available_employees_list)} employees qualified by role"
        )

        return jsonify(available_employees_list)

    # Get employees scheduled for Core events on the specified date
    # Also query the schedule datetime for debugging
    core_scheduled_employees = db.session.query(
        Schedule.employee_id,
        Schedule.schedule_datetime,
        Event.project_name
    ).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).filter(
        db.func.date(Schedule.schedule_datetime) == parsed_date,
        Event.event_type == 'Core'
    ).all()

    core_scheduled_employee_ids = {emp[0] for emp in core_scheduled_employees}

    # Debug: Log which employees are scheduled for Core events
    if core_scheduled_employee_ids:
        current_app.logger.info(
            f"[AVAILABLE_EMPLOYEES] Core scheduled employees on {date}: {list(core_scheduled_employee_ids)}"
        )
        # Log each schedule for debugging
        for emp_id, sched_dt, event_name in core_scheduled_employees:
            current_app.logger.info(
                f"[AVAILABLE_EMPLOYEES]   - {emp_id} has Core event '{event_name}' at {sched_dt}"
            )

    # Get employees marked as unavailable on the specified date
    unavailable_employees = db.session.query(EmployeeAvailability.employee_id).filter(
        EmployeeAvailability.date == parsed_date,
        EmployeeAvailability.is_available == False
    ).all()

    unavailable_employee_ids = {emp[0] for emp in unavailable_employees}

    # Get employees who have time off on the specified date
    time_off_employees = db.session.query(EmployeeTimeOff.employee_id).filter(
        EmployeeTimeOff.start_date <= parsed_date,
        EmployeeTimeOff.end_date >= parsed_date
    ).all()

    time_off_employee_ids = {emp[0] for emp in time_off_employees}

    # Get day of week for weekly availability check
    day_of_week = parsed_date.weekday()
    day_columns = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    day_column = day_columns[day_of_week]

    # Get weekly availability for all employees
    weekly_availability_query = db.session.query(
        EmployeeWeeklyAvailability.employee_id,
        getattr(EmployeeWeeklyAvailability, day_column).label('is_available_weekly')
    ).all()

    weekly_unavailable_ids = {
        emp[0] for emp in weekly_availability_query
        if not emp[1]  # is_available_weekly is False
    }

    # Debug: Log which employees are weekly unavailable
    if weekly_unavailable_ids:
        current_app.logger.info(
            f"[AVAILABLE_EMPLOYEES] Weekly unavailable on {day_column}: {list(weekly_unavailable_ids)}"
        )

    # Get event type for role-based filtering
    event_type = None
    if event_id:
        event = db.session.get(Event, event_id)
        if event:
            event_type = event.event_type

    # Debug logging
    current_app.logger.info(
        f"[AVAILABLE_EMPLOYEES] Date: {date}, Event ID: {event_id}, Event Type: {event_type}, "
        f"Day: {day_column}, Total Active Employees: {len(all_employees)}"
    )
    current_app.logger.info(
        f"[AVAILABLE_EMPLOYEES] Filters - Core scheduled: {len(core_scheduled_employee_ids)}, "
        f"Unavailable: {len(unavailable_employee_ids)}, Time off: {len(time_off_employee_ids)}, "
        f"Weekly unavailable: {len(weekly_unavailable_ids)}"
    )

    # Filter available employees
    available_employees_list = []
    for emp in all_employees:
        # Track why each employee is excluded
        exclusion_reason = None

        # Only apply Core event one-per-day restriction when scheduling a Core event
        if event_type == 'Core' and emp.id in core_scheduled_employee_ids:
            exclusion_reason = "already scheduled for Core event"
        elif emp.id in unavailable_employee_ids:
            exclusion_reason = "marked unavailable on this date"
        elif emp.id in time_off_employee_ids:
            exclusion_reason = "has time off on this date"
        elif emp.id in weekly_unavailable_ids:
            exclusion_reason = f"weekly unavailable on {day_column}"
        elif event_type == 'Other' and emp.job_title not in ['Lead Event Specialist', 'Club Supervisor']:
            exclusion_reason = f"job title '{emp.job_title}' cannot work Other events"
        elif event_type and not emp.can_work_event_type(event_type):
            exclusion_reason = f"job title '{emp.job_title}' cannot work {event_type} events"

        if exclusion_reason:
            current_app.logger.debug(
                f"[AVAILABLE_EMPLOYEES] Excluded {emp.name} ({emp.id}): {exclusion_reason}"
            )
        else:
            current_app.logger.info(
                f"[AVAILABLE_EMPLOYEES] [OK] Available: {emp.name} ({emp.id}) - {emp.job_title}"
            )
            available_employees_list.append({
                'id': emp.id,
                'name': emp.name,
                'is_supervisor': emp.is_supervisor,
                'job_title': emp.job_title,
                'adult_beverage_trained': emp.adult_beverage_trained
            })

    current_app.logger.info(
        f"[AVAILABLE_EMPLOYEES] Result: {len(available_employees_list)} available employees"
    )

    return jsonify(available_employees_list)


@scheduling_bp.route('/api/check_conflicts', methods=['POST'])
def check_scheduling_conflicts():
    """
    Check for potential scheduling conflicts in real-time.

    Uses ConflictValidator service for validation logic.
    Refactored from inline validation code as part of Epic 1, Story 1.1.
    """
    from flask import current_app
    from app.services.conflict_validation import ConflictValidator

    db = current_app.extensions['sqlalchemy']

    # Get all models
    models = {
        'Employee': current_app.config['Employee'],
        'Event': current_app.config['Event'],
        'Schedule': current_app.config['Schedule'],
        'EmployeeAvailability': current_app.config.get('EmployeeAvailability'),
        'EmployeeTimeOff': current_app.config['EmployeeTimeOff'],
        'EmployeeWeeklyAvailability': current_app.config.get('EmployeeWeeklyAvailability')
    }

    # Get parameters
    data = request.get_json()
    employee_id = data.get('employee_id')
    scheduled_date = data.get('scheduled_date')
    scheduled_time = data.get('scheduled_time')
    event_id = data.get('event_id')

    # Validate required parameters
    if not all([employee_id, scheduled_date, scheduled_time, event_id]):
        return jsonify({'error': 'Missing required parameters'}), 400

    try:
        # Parse datetime
        parsed_datetime = datetime.strptime(
            f"{scheduled_date} {scheduled_time}",
            '%Y-%m-%d %H:%M'
        )
    except ValueError:
        return jsonify({'error': 'Invalid date or time format'}), 400

    try:
        # Initialize validator
        validator = ConflictValidator(db.session, models)

        # Validate schedule
        result = validator.validate_schedule(
            employee_id=employee_id,
            event_id=event_id,
            schedule_datetime=parsed_datetime,
            duration_minutes=data.get('duration_minutes', 120)
        )

        # Map ValidationResult to API response format
        conflicts = []
        warnings = []

        for violation in result.violations:
            violation_dict = {
                'type': violation.details.get('type', violation.constraint_type.value),
                'severity': 'error' if violation.severity.value == 'hard' else 'warning',
                'message': violation.message,
                'detail': violation.details.get('detail', '')
            }

            if violation.severity.value == 'hard':
                conflicts.append(violation_dict)
            else:
                warnings.append(violation_dict)

        return jsonify({
            'has_conflicts': len(conflicts) > 0,
            'has_warnings': len(warnings) > 0,
            'conflicts': conflicts,
            'warnings': warnings,
            'can_proceed': len(conflicts) == 0  # Can proceed if only warnings
        })

    except ValueError as e:
        # Employee or event not found
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        # Log unexpected errors
        current_app.logger.error(f"Error in check_scheduling_conflicts: {str(e)}")
        return jsonify({'error': 'An error occurred during validation'}), 500


def auto_schedule_supervisor_event(db, Event, Schedule, Employee, core_project_ref_num, core_date, core_employee_id):
    """
    Auto-schedule the corresponding Supervisor event when a Core event is scheduled

    Args:
        db: SQLAlchemy database instance
        Event: Event model class
        Schedule: Schedule model class
        Employee: Employee model class
        core_project_ref_num: Project reference number of the Core event
        core_date: Date the Core event is scheduled (date object)
        core_employee_id: Employee ID assigned to the Core event

    Returns:
        Tuple: (success: bool, supervisor_event_name: str or None)
    """
    try:
        # Get the CORE event to extract its 6-digit event number
        from app.utils.event_helpers import extract_event_number

        core_event = Event.query.filter_by(project_ref_num=core_project_ref_num).first()
        if not core_event:
            return False, None

        # Extract the 6-digit event number from the CORE event name
        event_number = extract_event_number(core_event.project_name)
        if not event_number:
            # Can't extract event number, can't find supervisor event
            return False, None

        # Find Supervisor event with the same 6-digit event number
        # Search for event names that start with the event number and contain "Supervisor"
        supervisor_events = Event.query.filter(
            Event.event_type == 'Supervisor',
            Event.project_name.like(f'{event_number}%')
        ).all()

        # Filter to get the one that actually matches (in case of partial matches)
        supervisor_event = None
        for event in supervisor_events:
            event_num = extract_event_number(event.project_name)
            if event_num == event_number:
                supervisor_event = event
                break

        if not supervisor_event:
            # No corresponding supervisor event found
            return False, None

        # Check if supervisor event is already scheduled
        existing_supervisor_schedule = Schedule.query.filter_by(
            event_ref_num=supervisor_event.project_ref_num
        ).first()

        if existing_supervisor_schedule:
            # Already scheduled, skip
            return False, None

        # Determine who to assign the supervisor event to
        # Priority: Lead with CORE event that day > Club Supervisor
        # This ensures Leads only get Supervisor events if they have a CORE event (full day's work)

        assigned_employee_id = None

        # First, check if the employee assigned to the CORE event is a Lead
        core_employee = db.session.get(Employee, core_employee_id)
        if core_employee and core_employee.job_title == 'Lead Event Specialist':
            # The CORE event is assigned to a Lead, so assign the Supervisor to them too
            assigned_employee_id = core_employee.id
        else:
            # The CORE event is not assigned to a Lead
            # Check if any other Lead has a CORE event scheduled on this date
            lead_with_core = db.session.query(Employee).join(
                Schedule, Employee.id == Schedule.employee_id
            ).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Employee.job_title == 'Lead Event Specialist',
                Employee.is_active == True,
                db.func.date(Schedule.schedule_datetime) == core_date,
                Event.event_type == 'Core'
            ).first()

            if lead_with_core:
                # Found a Lead with a CORE event that day, assign to them
                assigned_employee_id = lead_with_core.id
            else:
                # No Lead has a CORE event that day, fallback to Club Supervisor
                club_supervisor = Employee.query.filter_by(
                    job_title='Club Supervisor',
                    is_active=True
                ).first()
                if club_supervisor:
                    assigned_employee_id = club_supervisor.id

        if not assigned_employee_id:
            # No suitable employee found
            return False, None

        # Create schedule for Supervisor event at 12:00 (noon)
        from datetime import datetime, time
        supervisor_datetime = datetime.combine(core_date, time(12, 0))  # 12:00 PM

        new_supervisor_schedule = Schedule(
            event_ref_num=supervisor_event.project_ref_num,
            employee_id=assigned_employee_id,
            schedule_datetime=supervisor_datetime
        )
        db.session.add(new_supervisor_schedule)

        # Update supervisor event status
        supervisor_event.is_scheduled = True
        supervisor_event.condition = 'Scheduled'

        return True, supervisor_event.project_name

    except Exception as e:
        # Log error but don't fail the main scheduling operation
        from flask import current_app
        current_app.logger.error(f"Error auto-scheduling supervisor event: {str(e)}")
        return False, None


@scheduling_bp.route('/save_schedule', methods=['POST'])
def save_schedule():
    """Save a new schedule assignment"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']
    Employee = current_app.config['Employee']
    Event = current_app.config['Event']
    Schedule = current_app.config['Schedule']

    # Get form data
    event_id = request.form.get('event_id')
    employee_id = request.form.get('employee_id')
    scheduled_date = request.form.get('scheduled_date')
    start_time = request.form.get('start_time')
    start_time_dropdown = request.form.get('start_time_dropdown')
    override_constraints = request.form.get('override_constraints') == 'true'
    return_url = request.form.get('return_url')  # URL to return to after scheduling

    # Use dropdown time if available, otherwise use regular time input
    actual_start_time = start_time_dropdown if start_time_dropdown else start_time

    # Validate required fields
    if not all([event_id, employee_id, scheduled_date, actual_start_time]):
        flash('All fields are required.', 'error')
        return redirect(url_for('scheduling.schedule_event', event_id=event_id or 0))

    try:
        # Convert event_id to integer
        event_id = int(event_id)

        # Get the event
        event = db.session.get(Event, event_id)
        if not event:
            flash('Event not found.', 'error')
            return redirect(url_for('main.dashboard'))

        # Parse and validate date
        try:
            parsed_date = datetime.strptime(scheduled_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Validate date is within event range (skip if override enabled)
        event_start_date = event.start_datetime.date()
        event_due_date = event.due_datetime.date()

        if not override_constraints and not (event_start_date <= parsed_date <= event_due_date):
            flash(f'Date must be between {event_start_date} and {event_due_date}.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # CHECK LOCKED DAYS: Cannot schedule to a locked day
        LockedDay = current_app.config.get('LockedDay')
        if LockedDay:
            locked_info = LockedDay.get_locked_day(parsed_date)
            if locked_info:
                reason = locked_info.reason or 'No reason provided'
                flash(f'Cannot schedule event: {parsed_date.isoformat()} is locked ({reason}). Unlock the day first.', 'error')
                return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Parse start time
        try:
            parsed_time = datetime.strptime(actual_start_time, '%H:%M').time()
        except ValueError:
            flash('Invalid time format.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Validate time restrictions for specific event types (skip if override enabled)
        if not override_constraints and not is_valid_time_for_event_type(event.event_type, parsed_time, event.project_name):
            allowed_times = get_allowed_times_for_event_type(event.event_type, event.project_name)
            if allowed_times:
                flash(f'{event.event_type} events can only be scheduled at: {", ".join(allowed_times)}', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Combine date and time
        schedule_datetime = datetime.combine(parsed_date, parsed_time)

        # Verify employee exists
        employee = db.session.get(Employee, employee_id)
        if not employee:
            flash('Employee not found.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Check if employee can work this event type based on their role (skip if override enabled)
        if not override_constraints and not employee.can_work_event_type(event.event_type):
            if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
                flash(f'{employee.name} cannot work {event.event_type} events. Only Club Supervisors and Juicer Baristas can work Juicer events.', 'error')
            elif event.event_type in ['Supervisor', 'Freeosk', 'Digitals']:
                flash(f'{employee.name} cannot work {event.event_type} events. Only Club Supervisors and Lead Event Specialists can work this type of event.', 'error')
            else:
                flash(f'{employee.name} cannot work {event.event_type} events.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Check if employee is already scheduled for a Core event on this date (skip if override enabled)
        if not override_constraints and event.event_type == 'Core':
            existing_core_schedule = Schedule.query.join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == employee_id,
                db.func.date(Schedule.schedule_datetime) == parsed_date,
                Event.event_type == 'Core'
            ).first()

            if existing_core_schedule:
                flash(f'{employee.name} is already scheduled for a Core event on {parsed_date}. Core events are limited to one per employee per day.', 'error')
                return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Submit to Crossmark API BEFORE creating local record
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Calculate end datetime using event's default duration if not set
        end_datetime = event.calculate_end_datetime(schedule_datetime)

        # Prepare API data
        rep_id = str(employee.external_id) if employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        # Validate required API fields
        if not rep_id:
            flash(f'Cannot schedule: Missing Crossmark employee ID for {employee.name}. Please contact administrator.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        if not mplan_id:
            flash('Cannot schedule: Missing Crossmark event ID. Please contact administrator.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        if not location_id:
            flash('Cannot schedule: Missing Crossmark location ID. Please contact administrator.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                flash('Failed to authenticate with Crossmark API. Please try again or contact administrator.', 'error')
                return redirect(url_for('scheduling.schedule_event', event_id=event_id))
        except Exception as auth_error:
            current_app.logger.error(f"Authentication error: {str(auth_error)}")
            flash('Failed to authenticate with Crossmark API. Please try again later.', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # Submit to external API
        try:
            current_app.logger.info(
                f"Submitting manual schedule to Crossmark API: "
                f"rep_id={rep_id}, mplan_id={mplan_id}, location_id={location_id}, "
                f"start={schedule_datetime.isoformat()}, end={end_datetime.isoformat()}"
            )

            api_result = external_api.schedule_mplan_event(
                rep_id=rep_id,
                mplan_id=mplan_id,
                location_id=location_id,
                start_datetime=schedule_datetime,
                end_datetime=end_datetime,
                planning_override=True
            )

            if not api_result.get('success'):
                error_message = api_result.get('message', 'Unknown API error')
                current_app.logger.error(f"Crossmark API error: {error_message}")
                flash(f'Failed to submit to Crossmark: {error_message}', 'error')
                return redirect(url_for('scheduling.schedule_event', event_id=event_id))

            current_app.logger.info(f"Successfully submitted to Crossmark API")

            # Extract the scheduled event ID from the API response
            # First try the direct field, then fall back to response_data
            scheduled_event_id = api_result.get('schedule_event_id')

            if not scheduled_event_id:
                response_data = api_result.get('response_data', {})
                if response_data:
                    scheduled_event_id = (
                        response_data.get('scheduleEventID') or
                        response_data.get('id') or
                        response_data.get('scheduledEventId') or
                        response_data.get('ID')
                    )

            current_app.logger.info(f"Extracted scheduled_event_id: {scheduled_event_id}")

        except Exception as api_error:
            current_app.logger.error(f"API submission error: {str(api_error)}")
            flash(f'Failed to submit to Crossmark API: {str(api_error)}', 'error')
            return redirect(url_for('scheduling.schedule_event', event_id=event_id))

        # API submission successful - now create local record
        new_schedule = Schedule(
            event_ref_num=event.project_ref_num,
            employee_id=employee_id,
            schedule_datetime=schedule_datetime,
            external_id=str(scheduled_event_id) if scheduled_event_id else None,
            last_synced=datetime.utcnow(),
            sync_status='synced'
        )
        db.session.add(new_schedule)

        # Update event status based on condition
        event.is_scheduled = True
        event.sync_status = 'synced'
        event.last_synced = datetime.utcnow()

        if event.condition == 'Submitted':
            event.condition = 'Reissued'
            action_message = f'Successfully reissued {event.project_name} and assigned to {employee.name} on {parsed_date} at {parsed_time}.'
        elif event.condition == 'Reissued':
            event.condition = 'Scheduled'
            action_message = f'Successfully rescheduled {event.project_name} for {employee.name} on {parsed_date} at {parsed_time}.'
        elif event.condition == 'Scheduled':
            action_message = f'Successfully rescheduled {event.project_name} for {employee.name} on {parsed_date} at {parsed_time}.'
        else:
            event.condition = 'Scheduled'
            action_message = f'Successfully scheduled {employee.name} for {event.project_name} on {parsed_date} at {parsed_time}.'

        # AUTO-SCHEDULE SUPERVISOR EVENT if this is a Core event
        supervisor_scheduled = False
        supervisor_event_name = None
        if event.event_type == 'Core':
            supervisor_scheduled, supervisor_event_name = auto_schedule_supervisor_event(
                db, Event, Schedule, Employee,
                event.project_ref_num,
                parsed_date,
                employee_id
            )

        # Commit changes
        db.session.commit()

        # Update flash message if supervisor was auto-scheduled
        if supervisor_scheduled:
            action_message += f' Supervisor event "{supervisor_event_name}" was automatically scheduled.'

        flash(action_message, 'success')

        # Redirect back to the return URL if provided, otherwise to dashboard
        if return_url:
            return redirect(return_url)
        else:
            return redirect(url_for('main.unscheduled_events'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving schedule: {str(e)}")
        flash('An error occurred while saving the schedule. Please try again.', 'error')
        return redirect(url_for('scheduling.schedule_event', event_id=event_id))
