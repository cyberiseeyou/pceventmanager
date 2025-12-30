"""
Main application routes blueprint
Handles dashboard, events list, and calendar views
"""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from app.routes.auth import require_authentication
from app.models import init_models
from datetime import datetime, date, timedelta

# Create blueprint
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@require_authentication()
def index():
    """Redirect to daily schedule view for today"""
    from datetime import date
    today = date.today()
    return redirect(url_for('main.daily_schedule_view', date=today.strftime('%Y-%m-%d')))


@main_bp.route('/dashboard')
@require_authentication()
def dashboard():
    """Redirect to today's daily schedule view"""
    today = date.today()
    return redirect(url_for('main.daily_schedule_view', date=today.strftime('%Y-%m-%d')))


@main_bp.route('/events')
@main_bp.route('/unscheduled')  # Keep old route for compatibility
def unscheduled_events():
    """Events list view with filtering by condition and type"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']

    # Get filter parameters
    condition_filter = request.args.get('condition', 'all')  # Default to all events
    event_type_filter = request.args.get('event_type', '')
    date_filter = request.args.get('date_filter', '')  # New: today, tomorrow, week, etc.
    search_query = request.args.get('search', '').strip()  # Smart search query

    # Map condition display names
    condition_display_map = {
        'all': 'All',
        'unstaffed': 'Unscheduled',
        'scheduled': 'Scheduled',
        'submitted': 'Submitted',
        'paused': 'Paused',
        'reissued': 'Reissued'
    }

    # Build query based on condition
    if condition_filter == 'all':
        # All events regardless of condition
        query = Event.query
    elif condition_filter == 'unstaffed':
        # Only Unstaffed events are truly unscheduled
        query = Event.query.filter_by(condition='Unstaffed')
    elif condition_filter == 'scheduled':
        # Scheduled condition events
        query = Event.query.filter_by(condition='Scheduled')
    elif condition_filter == 'submitted':
        # Submitted condition events
        query = Event.query.filter_by(condition='Submitted')
    elif condition_filter == 'paused':
        # Paused condition events
        query = Event.query.filter_by(condition='Paused')
    elif condition_filter == 'reissued':
        # Reissued condition events
        query = Event.query.filter_by(condition='Reissued')
    else:
        # Default to all events
        query = Event.query

    # Apply event type filter if specified
    if event_type_filter and event_type_filter != '':
        query = query.filter_by(event_type=event_type_filter)

    # Apply date filter if specified
    today = date.today()
    if date_filter == 'today':
        query = query.filter(
            Event.start_datetime >= datetime.combine(today, datetime.min.time()),
            Event.start_datetime <= datetime.combine(today, datetime.max.time())
        )
    elif date_filter == 'tomorrow':
        tomorrow = today + timedelta(days=1)
        query = query.filter(
            Event.start_datetime >= datetime.combine(tomorrow, datetime.min.time()),
            Event.start_datetime <= datetime.combine(tomorrow, datetime.max.time())
        )
    elif date_filter == 'week':
        week_from_now = today + timedelta(days=7)
        query = query.filter(
            Event.start_datetime >= datetime.combine(today, datetime.min.time()),
            Event.start_datetime <= datetime.combine(week_from_now, datetime.max.time())
        )

    # Apply intelligent search if specified
    if search_query:
        import re
        from sqlalchemy import or_, and_

        # Split search by commas for multiple criteria
        search_terms = [term.strip() for term in search_query.split(',') if term.strip()]

        Schedule = current_app.config['Schedule']
        Employee = current_app.config['Employee']

        search_conditions = []

        # Helper function to parse dates
        def parse_search_date(date_str, year_hint=today.year):
            """Parse date string in various formats (MM/DD, MM-DD, MM/DD/YY, etc.)"""
            date_str = date_str.strip()
            # Try different separators
            for sep in ['/', '-']:
                if sep in date_str:
                    parts = date_str.split(sep)
                    if len(parts) == 2:
                        month, day = int(parts[0]), int(parts[1])
                        return date(year_hint, month, day)
                    elif len(parts) == 3:
                        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                        # Handle 2-digit years
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        return date(year, month, day)
            return None

        for term in search_terms:
            term_conditions = []

            # Determine default date type based on current tab/condition
            default_date_type = {
                'scheduled': 'scheduled',
                'unstaffed': 'start',
                'submitted': 'submitted',
                'paused': 'scheduled',
                'reissued': 'scheduled'
            }.get(condition_filter, 'start')

            # Check for date prefix (s:, sc:, e:, d:)
            date_prefix = None
            date_type = default_date_type
            original_term = term

            if term.startswith('s:') and not term.startswith('sc:'):
                date_prefix = 's:'
                date_type = 'start'
                term = term[2:].strip()
            elif term.startswith('sc:'):
                date_prefix = 'sc:'
                date_type = 'scheduled'
                term = term[3:].strip()
            elif term.startswith('e:') or term.startswith('d:'):
                date_prefix = term[:2]
                date_type = 'due'
                term = term[2:].strip()

            # Check for date range (with " to ")
            if ' to ' in term.lower():
                try:
                    parts = re.split(r'\s+to\s+', term, flags=re.IGNORECASE)
                    if len(parts) == 2:
                        start_date = parse_search_date(parts[0])
                        end_date = parse_search_date(parts[1])

                        if start_date and end_date:
                            if date_type == 'scheduled':
                                # Search by scheduled date
                                scheduled_event_refs = db.session.query(Schedule.event_ref_num).filter(
                                    db.func.date(Schedule.schedule_datetime) >= start_date,
                                    db.func.date(Schedule.schedule_datetime) <= end_date
                                ).distinct()
                                term_conditions.append(Event.project_ref_num.in_(scheduled_event_refs))
                            elif date_type == 'start':
                                # Search by start date
                                term_conditions.append(and_(
                                    db.func.date(Event.start_datetime) >= start_date,
                                    db.func.date(Event.start_datetime) <= end_date
                                ))
                            elif date_type == 'due':
                                # Search by due date
                                term_conditions.append(and_(
                                    db.func.date(Event.due_datetime) >= start_date,
                                    db.func.date(Event.due_datetime) <= end_date
                                ))
                except (ValueError, IndexError, AttributeError):
                    pass  # If date parsing fails, continue to next check

            # Check if it's a single date (contains / or -)
            elif '/' in term or '-' in term:
                try:
                    search_date = parse_search_date(term)

                    if search_date:
                        if date_type == 'scheduled':
                            # Search by scheduled date
                            scheduled_event_refs = db.session.query(Schedule.event_ref_num).filter(
                                db.func.date(Schedule.schedule_datetime) == search_date
                            ).distinct()
                            term_conditions.append(Event.project_ref_num.in_(scheduled_event_refs))
                        elif date_type == 'start':
                            # Search by start date
                            term_conditions.append(
                                db.func.date(Event.start_datetime) == search_date
                            )
                        elif date_type == 'due':
                            # Search by due date
                            term_conditions.append(
                                db.func.date(Event.due_datetime) == search_date
                            )
                except (ValueError, IndexError, AttributeError):
                    pass  # If date parsing fails, skip this term

            # Check if it's all uppercase (employee name) - only if no date prefix
            elif not date_prefix and original_term.isupper() and len(original_term) > 1:
                # Only search by employee for scheduled events
                if condition_filter in ['scheduled', 'submitted', 'reissued']:
                    # Subquery to find events assigned to this employee
                    employee_ids = db.session.query(Employee.id).filter(
                        Employee.name.ilike(f'%{original_term}%')
                    )
                    scheduled_by_employee = db.session.query(Schedule.event_ref_num).filter(
                        Schedule.employee_id.in_(employee_ids)
                    ).distinct()
                    term_conditions.append(Event.project_ref_num.in_(scheduled_by_employee))

            # Check if it's all digits (event number) - only if no date prefix
            elif not date_prefix and original_term.isdigit():
                term_conditions.append(Event.project_name.contains(original_term))

            # Otherwise, search in event name - only if no date prefix
            elif not date_prefix:
                term_conditions.append(Event.project_name.ilike(f'%{original_term}%'))

            # Add this term's conditions to the overall search (OR within term)
            if term_conditions:
                search_conditions.append(or_(*term_conditions))

        # Apply all search conditions (AND between different terms)
        if search_conditions:
            query = query.filter(and_(*search_conditions))

    # Order results
    events = query.order_by(
        Event.start_datetime.asc(),
        Event.due_datetime.asc()
    ).all()

    # Calculate priority for each event (for visual coding)
    # Also fetch schedule/employee info for scheduled events
    Schedule = current_app.config['Schedule']
    Employee = current_app.config['Employee']

    today = date.today()
    events_with_priority = []
    for event in events:
        days_remaining = (event.due_datetime.date() - today).days
        if days_remaining <= 1:
            priority = 'critical'
            priority_color = 'red'
        elif days_remaining <= 7:
            priority = 'urgent'
            priority_color = 'yellow'
        else:
            priority = 'normal'
            priority_color = 'green'

        # Add priority attributes to event object
        event.priority = priority
        event.priority_color = priority_color
        event.days_remaining = days_remaining

        # For scheduled events, fetch schedule and employee information
        if condition_filter in ['all', 'scheduled', 'submitted', 'reissued']:
            schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).all()
            if schedules:
                # Get employee names and times for all schedules
                schedule_info = []
                for schedule in schedules:
                    employee = Employee.query.get(schedule.employee_id)
                    if employee:
                        schedule_info.append({
                            'employee_name': employee.name,
                            'schedule_datetime': schedule.schedule_datetime,
                            'schedule_time': schedule.schedule_datetime.strftime('%I:%M %p') if schedule.schedule_datetime else 'N/A'
                        })
                event.schedule_info = schedule_info
            else:
                event.schedule_info = []
        else:
            event.schedule_info = []

        events_with_priority.append(event)

    # Get all distinct event types for the filter dropdown
    event_types = db.session.query(Event.event_type).distinct().order_by(Event.event_type).all()
    event_types = [et[0] for et in event_types]

    # Map date filter display names
    date_filter_display = {
        'today': "Today's",
        'tomorrow': "Tomorrow's",
        'week': "This Week's",
        '': 'All'
    }

    return render_template('unscheduled.html',
                         events=events_with_priority,
                         event_types=event_types,
                         selected_event_type=event_type_filter,
                         condition=condition_filter,
                         condition_display=condition_display_map.get(condition_filter, 'Unscheduled'),
                         date_filter=date_filter,
                         date_filter_display=date_filter_display.get(date_filter, 'All'))


@main_bp.route('/unreported-events')
@require_authentication()
def unreported_events():
    """Display unreported events from the last 2 weeks"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']

    Event = current_app.config['Event']
    Schedule = current_app.config['Schedule']
    Employee = current_app.config['Employee']

    today = date.today()
    two_weeks_ago = today - timedelta(days=14)

    # Get unreported events scheduled in the last 2 weeks
    # Unreported = scheduled in the past but not marked as Submitted
    unreported = db.session.query(
        Event,
        Schedule,
        Employee
    ).join(
        Schedule, Event.project_ref_num == Schedule.event_ref_num
    ).join(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        Schedule.schedule_datetime >= datetime.combine(two_weeks_ago, datetime.min.time()),
        Schedule.schedule_datetime < datetime.combine(today, datetime.min.time()),
        Event.condition.in_(['Scheduled', 'Staffed', 'In Progress', 'Paused'])
    ).order_by(
        Schedule.schedule_datetime.desc()
    ).all()

    # Calculate days overdue for each event
    unreported_with_days = []
    for event, schedule, employee in unreported:
        schedule_date = schedule.schedule_datetime.date()
        days_overdue = (today - schedule_date).days

        unreported_with_days.append({
            'event': event,
            'schedule': schedule,
            'employee': employee,
            'days_overdue': days_overdue,
            'schedule_date': schedule_date,
            'schedule_time': schedule.schedule_datetime.strftime('%I:%M %p')
        })

    return render_template('unreported_events.html',
                         unreported_events=unreported_with_days,
                         total_count=len(unreported_with_days),
                         timedelta=timedelta)


@main_bp.route('/calendar')
def calendar_view():
    """Display calendar view of scheduled events"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    # Get the date from query params, default to today
    date_str = request.args.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()

    # Get all scheduled events for the selected month
    start_of_month = selected_date.replace(day=1)
    if start_of_month.month == 12:
        end_of_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        end_of_month = start_of_month.replace(month=start_of_month.month + 1)

    # Get scheduled events for the month
    scheduled_events = db.session.query(Schedule, Event, Employee).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).join(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        db.func.date(Schedule.schedule_datetime) >= start_of_month,
        db.func.date(Schedule.schedule_datetime) < end_of_month
    ).order_by(Schedule.schedule_datetime).all()

    # Group events by date (convert dates to strings for JSON serialization)
    events_by_date = {}
    event_counts_by_date = {}  # New: Track counts by type

    for schedule, event, employee in scheduled_events:
        event_date = schedule.schedule_datetime.date()
        date_str = event_date.strftime('%Y-%m-%d')

        if date_str not in events_by_date:
            events_by_date[date_str] = []
            event_counts_by_date[date_str] = {
                'Core': 0, 'Juicer Production': 0, 'Juicer Survey': 0, 'Juicer Deep Clean': 0,
                'Supervisor': 0, 'Freeosk': 0, 'Digitals': 0, 'Other': 0
            }

        events_by_date[date_str].append({
            'id': schedule.id,
            'event_name': event.project_name,
            'event_type': event.event_type,
            'employee_name': employee.name,
            'time': schedule.schedule_datetime.strftime('%I:%M %p'),
            'store_name': event.store_name,
            'estimated_time': event.estimated_time
        })

        # Increment count for this event type
        if event.event_type in event_counts_by_date[date_str]:
            event_counts_by_date[date_str][event.event_type] += 1
        else:
            event_counts_by_date[date_str]['Other'] += 1

    # Get unscheduled events by date for warning indicators
    unscheduled_by_date = {}
    unscheduled_events = Event.query.filter(
        Event.condition == 'Unstaffed',
        db.or_(
            db.and_(
                Event.start_datetime >= start_of_month,
                Event.start_datetime < end_of_month
            ),
            db.and_(
                Event.due_datetime >= start_of_month,
                Event.due_datetime < end_of_month
            )
        )
    ).all()

    for event in unscheduled_events:
        # Use due_datetime as the primary date for warnings
        warning_date = event.due_datetime.date() if event.due_datetime else event.start_datetime.date()
        date_str = warning_date.strftime('%Y-%m-%d')

        if date_str not in unscheduled_by_date:
            unscheduled_by_date[date_str] = 0
        unscheduled_by_date[date_str] += 1

    return render_template('calendar.html',
                         selected_date=selected_date,
                         events_by_date=events_by_date,
                         event_counts_by_date=event_counts_by_date,
                         unscheduled_by_date=unscheduled_by_date)


@main_bp.route('/calendar/day/<date>')
def calendar_day_view(date):
    """Get events for a specific day (AJAX endpoint)"""
    from flask import current_app
    import re
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Get Primary Lead for this date (Lead scheduled for any event)
    primary_lead = None
    lead_schedule = db.session.query(
        Employee
    ).join(
        Schedule, Schedule.employee_id == Employee.id
    ).filter(
        db.func.date(Schedule.schedule_datetime) == selected_date,
        Employee.job_title == 'Lead',
        Employee.is_active == True
    ).first()
    if lead_schedule:
        primary_lead = lead_schedule.name

    # Get Juicer for this date (Employee scheduled for Juicer Production)
    juicer = None
    juicer_schedule = db.session.query(
        Employee, Event
    ).join(
        Schedule, Schedule.employee_id == Employee.id
    ).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).filter(
        db.func.date(Schedule.schedule_datetime) == selected_date,
        Event.event_type == 'Juicer Production',
        Employee.is_active == True
    ).first()
    if juicer_schedule:
        juicer = juicer_schedule[0].name

    # Get scheduled events for the specific day
    scheduled_events = db.session.query(Schedule, Event, Employee).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).join(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        db.func.date(Schedule.schedule_datetime) == selected_date
    ).order_by(Schedule.schedule_datetime).all()

    # Build events data with Supervisor pairing info for Core events
    events_data = []
    for schedule, event, employee in scheduled_events:
        event_dict = {
            'id': schedule.id,
            'event_name': event.project_name,
            'event_type': event.event_type,
            'employee_name': employee.name,
            'employee_id': employee.id,
            'time': schedule.schedule_datetime.strftime('%I:%M %p'),
            'datetime': schedule.schedule_datetime.isoformat(),
            'store_name': event.store_name,
            'estimated_time': event.estimated_time,
            'start_date': event.start_datetime.strftime('%m/%d/%Y'),
            'due_date': event.due_datetime.strftime('%m/%d/%Y')
        }

        # For Core events, check if there's a paired Supervisor event
        if event.event_type == 'Core':
            # Extract first 6 digits from event name
            match = re.search(r'\d{6}', event.project_name)
            if match:
                event_number = match.group(0)
                # Look for Supervisor event with same number scheduled on same date
                supervisor_event = db.session.query(Schedule, Event, Employee).join(
                    Event, Schedule.event_ref_num == Event.project_ref_num
                ).join(
                    Employee, Schedule.employee_id == Employee.id
                ).filter(
                    Event.event_type == 'Supervisor',
                    Event.project_name.contains(event_number),
                    db.func.date(Schedule.schedule_datetime) == selected_date
                ).first()

                if supervisor_event:
                    supervisor_schedule, supervisor_evt, supervisor_emp = supervisor_event
                    event_dict['supervisor_name'] = supervisor_emp.name
                    event_dict['supervisor_time'] = supervisor_schedule.schedule_datetime.strftime('%I:%M %p')

        events_data.append(event_dict)

    return jsonify({
        'date': selected_date.strftime('%Y-%m-%d'),
        'formatted_date': selected_date.strftime('%A, %B %d, %Y'),
        'primary_lead': primary_lead,
        'juicer': juicer,
        'events': events_data
    })


@main_bp.route('/employees/workload')
@require_authentication()
def workload_dashboard():
    """
    Employee workload dashboard page.

    Epic 2, Story 2.6: Create Workload Dashboard Frontend View
    """
    return render_template('workload_dashboard.html')


@main_bp.route('/schedule/daily/<date>')
@require_authentication()
def daily_schedule_view(date: str) -> str:
    """
    Display full-screen daily schedule view.

    This route provides a comprehensive view of all events, employee assignments,
    and role rotations for a specific date. Replaces the cramped calendar popup
    with a dedicated full-screen page.

    Args:
        date: Date string in 'YYYY-MM-DD' format

    Returns:
        Rendered daily_view.html template with context

    Example:
        GET /schedule/daily/2025-10-15

    Note:
        - Validates date format, redirects to calendar on error
        - Queries RotationAssignment for Juicer and Primary Lead
        - Calculates prev/next dates for navigation
    """
    from flask import current_app
    db = current_app.extensions['sqlalchemy']

    # Get models
    RotationAssignment = current_app.config.get('RotationAssignment')
    Employee = current_app.config.get('Employee')

    # Parse and validate date
    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
        return redirect(url_for('main.calendar_view'))

    # Get role assignments for selected date
    # Note: RotationAssignment uses day_of_week (0-6), so we need to get the day of week
    # and query by that, then check if there's a matching employee
    day_of_week = selected_date.weekday()  # 0=Monday, 6=Sunday

    juicer = None
    primary_lead = None

    if RotationAssignment:
        # Create a simple object to match the template expectation
        class AssignmentWrapper:
            def __init__(self, employee):
                self.employee = employee

        # Query for Juicer assignment
        juicer_assignment = RotationAssignment.query.filter_by(
            day_of_week=day_of_week,
            rotation_type='juicer'
        ).first()

        if juicer_assignment and juicer_assignment.employee:
            juicer = AssignmentWrapper(juicer_assignment.employee)

        # Query for Primary Lead assignment
        primary_lead_assignment = RotationAssignment.query.filter_by(
            day_of_week=day_of_week,
            rotation_type='primary_lead'
        ).first()

        if primary_lead_assignment and primary_lead_assignment.employee:
            primary_lead = AssignmentWrapper(primary_lead_assignment.employee)

    # Calculate previous and next dates for navigation
    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)

    # Get all employees for bulk reassignment dropdown (active employees only)
    employees = []
    if Employee:
        employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()

    # Render template with context
    return render_template('daily_view.html',
        selected_date=selected_date,
        juicer=juicer,
        primary_lead=primary_lead,
        prev_date=prev_date,
        next_date=next_date,
        employees=employees
    )


@main_bp.route('/attendance')
@main_bp.route('/attendance/<employee_id>')
@require_authentication()
def attendance_calendar(employee_id=None):
    """
    Employee attendance calendar view.

    Epic 4, Story 4.3: Display monthly attendance calendar for employees.
    Supervisors can view attendance records, navigate months, and filter by employee.

    Args:
        employee_id: Optional employee ID to filter attendance view

    Query params:
        date: Date string in 'YYYY-MM-DD' format for month selection
    """
    from flask import current_app
    db = current_app.extensions['sqlalchemy']

    # Get models
    Employee = current_app.config['Employee']
    EmployeeAttendance = current_app.config['EmployeeAttendance']
    Schedule = current_app.config['Schedule']

    # Parse date parameter for month selection
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

    # Get all active employees for the selector
    all_employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()

    # Get selected employee if specified
    selected_employee = None
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

    return render_template('attendance.html',
                         selected_date=selected_date,
                         start_of_month=start_of_month,
                         end_of_month=end_of_month,
                         prev_month=prev_month,
                         next_month=next_month,
                         all_employees=all_employees,
                         selected_employee=selected_employee)


@main_bp.route('/api/schedule/print/<date>')
@require_authentication()
def print_schedule_by_date(date):
    """Get schedule data for printing for a specific date"""
    from flask import current_app
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Get Core and Juicer Production events for the specific day
    scheduled_events = db.session.query(Schedule, Event, Employee).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).join(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        db.func.date(Schedule.schedule_datetime) == selected_date,
        db.or_(
            Event.event_type == 'Core',
            Event.event_type == 'Juicer Production'
        )
    ).order_by(Schedule.schedule_datetime).all()

    events_data = []
    for schedule, event, employee in scheduled_events:
        events_data.append({
            'employee_name': employee.name,
            'time': schedule.schedule_datetime.strftime('%I:%M %p'),
            'event_name': event.project_name,
            'event_type': event.event_type,
            'minutes': schedule.schedule_datetime.hour * 60 + schedule.schedule_datetime.minute
        })

    return jsonify({
        'date': selected_date.strftime('%Y-%m-%d'),
        'formatted_date': selected_date.strftime('%A, %B %d, %Y'),
        'events': events_data
    })
