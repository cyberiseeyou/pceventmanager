"""
API routes blueprint
Handles all API endpoints for schedule operations, imports, exports, and AJAX calls
"""
from flask import Blueprint, request, jsonify, current_app, make_response
from app.routes.auth import require_authentication
from datetime import datetime, timedelta, date
import csv
import io
import logging
import re
import time
from io import StringIO

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# Import route registration functions for modular API endpoints
from app.routes.api_availability_overrides import register_availability_override_routes
from app.routes.api_employee_termination import register_termination_routes
from app.routes.api_auto_scheduler_settings import register_auto_scheduler_settings_routes


@api_bp.route('/daily-summary/<date>', methods=['GET'])
def get_daily_summary(date):
    """
    Get event type counts and timeslot coverage for a specific date.

    This endpoint provides summary statistics for the daily view dashboard,
    including event type distribution and shift block employee coverage.
    
    Updated to use 8-block shift system.

    Args:
        date: Date string in 'YYYY-MM-DD' format (URL path parameter)

    Returns:
        JSON response with event_types dict, total_events count,
        shift_blocks (new 8-block format), and legacy timeslot_coverage

    Response Format:
    {
        "event_types": { "Core": 5, "Juicer": 2, ... },
        "total_events": 11,
        "shift_blocks": [
            {
                "block": 1,
                "arrive": "10:15",
                "on_floor": "10:30",
                "lunch_begin": "12:30",
                "lunch_end": "13:00",
                "off_floor": "16:30",
                "depart": "16:45",
                "employees": [
                    {
                        "name": "NANCY DINKINS",
                        "events": [
                            {
                                "schedule_id": 123,
                                "event_name": "192647-Trilliant-Nurri-V2-CORE",
                                "event_ref": 192647,
                                "start_date": "12/01/2025",
                                "due_date": "12/15/2025",
                                "status": "Scheduled"
                            }
                        ]
                    }
                ]
            },
            ...
        ],
        "timeslot_coverage": { ... }  // Legacy format for backward compatibility
    }
    """
    from sqlalchemy import func, and_
    from app.utils.validators import validate_date_param
    from app.utils.db_helpers import get_models, get_date_range

    # Validate and parse date using utility
    selected_date = validate_date_param(date)

    # Get models and date range for efficient querying
    m = get_models()
    db = m['db']
    Schedule = m['Schedule']
    Event = m['Event']
    Employee = m['Employee']
    date_start, date_end = get_date_range(selected_date)

    # OPTIMIZED: Query event type counts using date range instead of func.date()
    event_types_query = db.session.query(
        Event.event_type,
        func.count(Schedule.id).label('count')
    ).join(
        Schedule, Event.project_ref_num == Schedule.event_ref_num
    ).filter(
        Schedule.schedule_datetime >= date_start,
        Schedule.schedule_datetime < date_end
    ).group_by(Event.event_type).all()

    # Build event_types dictionary
    type_counts = {event_type: count for event_type, count in event_types_query}

    # Ensure all expected event types are present (even if count is 0)
    for event_type in ['Setup', 'Demo', 'Juicer', 'Other', 'Core']:
        if event_type not in type_counts:
            type_counts[event_type] = 0

    # Calculate total events
    total_events = sum(type_counts.values())
    
    # ===== NEW: 8-Block Shift System =====
    # PERFORMANCE: Query all Core schedules ONCE, then group in Python
    # Previously: 8 separate queries (1 per block)
    # Now: 1 query + O(n) grouping
    try:
        from app.services.shift_block_config import ShiftBlockConfig
        from collections import defaultdict
        
        all_blocks = ShiftBlockConfig.get_all_blocks()
        
        # Create a map of on_floor_time -> block_num for O(1) lookups
        time_to_block = {}
        for block in all_blocks:
            time_to_block[block['on_floor']] = block['block']
        
        # SINGLE QUERY: Get all Core schedules for the day
        all_core_schedules = db.session.query(
            Schedule, Event, Employee
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            and_(
                Schedule.schedule_datetime >= date_start,
                Schedule.schedule_datetime < date_end,
                Event.event_type == 'Core'
            )
        ).all()
        
        # Group schedules by block in Python (O(n))
        schedules_by_block = defaultdict(list)
        for schedule, event, employee in all_core_schedules:
            schedule_time = schedule.schedule_datetime.time()
            block_num = time_to_block.get(schedule_time)
            if block_num:
                schedules_by_block[block_num].append((schedule, event, employee))
        
        # Build shift_blocks response
        shift_blocks = []
        for block in all_blocks:
            block_num = block['block']
            
            # Group by employee (from pre-fetched data)
            employee_events = {}
            for schedule, event, employee in schedules_by_block.get(block_num, []):
                if employee.id not in employee_events:
                    employee_events[employee.id] = {
                        'name': employee.name,
                        'employee_id': employee.id,
                        'events': []
                    }
                employee_events[employee.id]['events'].append({
                    'schedule_id': schedule.id,
                    'event_name': event.project_name,
                    'event_ref': event.project_ref_num,
                    'start_date': event.start_datetime.strftime('%m/%d/%Y') if event.start_datetime else None,
                    'due_date': event.due_datetime.strftime('%m/%d/%Y') if event.due_datetime else None,
                    'status': event.condition or 'Scheduled',
                    'shift_block': schedule.shift_block
                })
            
            shift_blocks.append({
                'block': block_num,
                'arrive': block['arrive_str'],
                'on_floor': block['on_floor_str'],
                'lunch_begin': block['lunch_begin_str'],
                'lunch_end': block['lunch_end_str'],
                'off_floor': block['off_floor_str'],
                'depart': block['depart_str'],
                'employees': list(employee_events.values())
            })
            
    except ImportError:
        shift_blocks = []  # Fallback if ShiftBlockConfig not available

    # ===== LEGACY: Keep old timeslot_coverage for backward compatibility =====
    from app.services.event_time_settings import EventTimeSettings
    
    try:
        # NEW: Try to get core slots from ShiftBlockConfig first (8-block system)
        from app.services.shift_block_config import ShiftBlockConfig
        blocks = ShiftBlockConfig.get_all_blocks()
        
        core_slots = []
        if blocks:
            # Build core slots from shift blocks (use unique arrive times)
            seen_times = set()
            slot_num = 1
            for block in blocks:
                # Use arrive time (start time)
                start = block['arrive']
                start_str = f"{start.hour:02d}:{start.minute:02d}"
                
                # Only add unique times
                if start_str not in seen_times:
                    seen_times.add(start_str)
                    
                    core_slots.append({
                        'slot': slot_num,
                        'start': block['arrive'],
                        'lunch_begin': block['lunch_begin'],
                        'lunch_end': block['lunch_end'],
                        'end': block['depart'] # Use depart as end
                    })
                    slot_num += 1
        else:
            # Fallback
            core_slots = EventTimeSettings.get_core_slots()
    except Exception:
        core_slots = []
        
    core_timeslots = []
    timeslot_metadata = {}
    
    for slot in core_slots:
        start_time = slot['start']
        time_str = f"{start_time.hour:02d}:{start_time.minute:02d}:00"
        core_timeslots.append(time_str)
        timeslot_metadata[time_str] = {
            'slot': slot['slot'],
            'start': f"{start_time.hour:02d}:{start_time.minute:02d}",
            'label': f"{start_time.hour}:{start_time.minute:02d} {'AM' if start_time.hour < 12 else 'PM'}" if start_time.hour <= 12 else f"{start_time.hour - 12}:{start_time.minute:02d} PM",
            'lunch_begin': f"{slot['lunch_begin'].hour:02d}:{slot['lunch_begin'].minute:02d}",
            'lunch_end': f"{slot['lunch_end'].hour:02d}:{slot['lunch_end'].minute:02d}",
            'end': f"{slot['end'].hour:02d}:{slot['end'].minute:02d}"
        }
        
    timeslot_coverage = {}
    
    for timeslot in core_timeslots:
        from datetime import time as dt_time
        parts = timeslot.split(':')
        slot_time = dt_time(int(parts[0]), int(parts[1]), int(parts[2]))
        
        slot_start = datetime.combine(selected_date, slot_time)
        slot_end = slot_start + timedelta(minutes=1)
        
        employees = db.session.query(
            Employee.name
        ).join(
            Schedule, Schedule.employee_id == Employee.id
        ).filter(
            and_(
                Schedule.schedule_datetime >= slot_start,
                Schedule.schedule_datetime < slot_end,
                Schedule.employee_id.isnot(None)
            )
        ).distinct().all()
        
        employee_names = [emp.name for emp in employees]
        timeslot_coverage[timeslot] = {
            'count': len(employee_names),
            'employees': employee_names
        }

    return jsonify({
        'event_types': type_counts,
        'total_events': total_events,
        'shift_blocks': shift_blocks,  # NEW: 8-block format
        'timeslot_coverage': timeslot_coverage,  # LEGACY: Old 4-slot format
        'timeslot_metadata': timeslot_metadata  # LEGACY: Old slot metadata
    }), 200


@api_bp.route('/daily-events/<date>', methods=['GET'])
def get_daily_events(date):
    """
    Get all scheduled events for a specific date.

    This endpoint retrieves all events scheduled for a given date, including
    employee assignments, time ranges, event details, and status information
    for display in the daily view event cards.

    Args:
        date: Date string in 'YYYY-MM-DD' format (URL path parameter)

    Returns:
        JSON response with events array containing schedule and event details

    Response Format:
    {
        "events": [
            {
                "schedule_id": 1,
                "event_id": 123456,
                "employee_id": "EMP001",
                "employee_name": "John Doe",
                "start_time": "08:00 AM",
                "end_time": "10:00 AM",
                "event_type": "Setup",
                "event_name": "Setup - Walmart Store #1234",
                "location": "Walmart Store #1234",
                "sales_tool_url": null,
                "reporting_status": "scheduled",
                "is_overdue": false
            }
        ]
    }

    Example:
        GET /api/daily-events/2025-10-15

    Note:
        - Events sorted chronologically by schedule_datetime ASC
        - End time calculated as start_time + event.estimated_time (default 120 min)
        - Unassigned employees return null employee_id with "Unassigned" name
        - Uses eager loading to prevent N+1 queries (optimized)
        - reporting_status and sales_tool_url will be added in Story 3.4
    """
    from sqlalchemy.orm import joinedload
    from app.utils.validators import validate_date_param, handle_validation_errors
    from app.utils.db_helpers import get_models, get_date_range

    # Validate and parse date using utility
    selected_date = validate_date_param(date)

    # Get models and date range for efficient querying
    m = get_models()
    db = m['db']
    Schedule = m['Schedule']
    date_start, date_end = get_date_range(selected_date)

    # OPTIMIZED: Use eager loading with joinedload to prevent N+1 queries
    # This loads all related data in a single query instead of N+2 queries
    schedules = db.session.query(Schedule).options(
        joinedload(Schedule.event),
        joinedload(Schedule.employee)
    ).filter(
        Schedule.schedule_datetime >= date_start,
        Schedule.schedule_datetime < date_end
    ).order_by(
        Schedule.schedule_datetime.asc()
    ).all()

    # Build result array with Core-Supervisor pairing
    # Events are sorted: by time, then Core events immediately followed by their paired Supervisor
    result = []
    processed_ids = set()  # Track processed schedule IDs to avoid duplicates

    # Helper function to build event dict (defined once, not per iteration)
    def build_event_dict(sched, evt, emp):
        duration = evt.estimated_time or evt.get_default_duration(evt.event_type)
        end_dt = sched.schedule_datetime + timedelta(minutes=duration)
        rep_status = 'submitted' if evt.condition == 'Submitted' else 'scheduled'
        return {
            'schedule_id': sched.id,
            'event_id': evt.project_ref_num,
            'employee_id': emp.id if emp else None,
            'employee_name': emp.name if emp else 'Unassigned',
            'start_time': sched.schedule_datetime.strftime('%I:%M %p'),
            'end_time': end_dt.strftime('%I:%M %p'),
            'event_type': evt.event_type,
            'event_name': evt.project_name,
            'location': evt.store_name,
            'start_date': evt.start_datetime.strftime('%m/%d/%Y') if evt.start_datetime else None,
            'due_date': evt.due_datetime.strftime('%m/%d/%Y') if evt.due_datetime else None,
            'sales_tool_url': getattr(evt, 'sales_tool_url', None),
            'reporting_status': rep_status,
            'is_overdue': _is_event_overdue(sched.schedule_datetime, rep_status)
        }

    # PERFORMANCE: Pre-index Supervisor schedules by 6-digit event number: O(n)
    # This replaces the O(n²) nested loop with O(1) lookups
    # For 50 events: 2,500 comparisons → ~100 operations
    supervisor_index = {}
    for schedule in schedules:
        if schedule.event.event_type == 'Supervisor':
            match = re.match(r'^(\d{6})-', schedule.event.project_name or '')
            if match:
                supervisor_index[match.group(1)] = schedule

    # Process all schedules with O(1) Supervisor lookups
    for schedule in schedules:
        # Skip if already processed (e.g., as part of a Core-Supervisor pair)
        if schedule.id in processed_ids:
            continue

        event = schedule.event
        processed_ids.add(schedule.id)

        # Add current event
        result.append(build_event_dict(schedule, event, schedule.employee))

        # If this is a Core event, find and add its paired Supervisor immediately after
        # Event naming patterns:
        #   Core: "615625-AF-StroopWafel... - V2-CORE" or "XXXXXX-CORE-..."
        #   Supervisor: "615625-AF-StroopWafel... - V2-Supervisor" or "XXXXXX-Supervisor-..."
        if event.event_type == 'Core':
            # Extract the 6-digit event number from start of event name
            match = re.match(r'^(\d{6})-', event.project_name or '')
            if match:
                event_number = match.group(1)
                # O(1) lookup instead of O(n) nested loop
                sup_schedule = supervisor_index.get(event_number)
                if sup_schedule and sup_schedule.id not in processed_ids:
                    # Found paired Supervisor - add it immediately after Core
                    processed_ids.add(sup_schedule.id)
                    result.append(build_event_dict(sup_schedule, sup_schedule.event, sup_schedule.employee))

    return jsonify({'events': result}), 200


def _is_event_overdue(schedule_datetime, reporting_status):
    """
    Check if event is overdue (>24 hours past and not submitted).

    Args:
        schedule_datetime: Scheduled datetime of the event
        reporting_status: Current reporting status (scheduled, submitted)

    Returns:
        bool: True if overdue, False otherwise

    Note:
        This is a helper function for Story 3.3.
        Story 3.4 will add the reporting_status field to events table.
    """
    if reporting_status == 'submitted':
        return False

    threshold = datetime.now() - timedelta(hours=24)
    return schedule_datetime < threshold


@api_bp.route('/daily-employees/<date>', methods=['GET'])
def get_daily_employees(date):
    """
    Get all employees scheduled for a specific date with their earliest event time.

    This endpoint groups employees by their earliest scheduled event for the day,
    ensuring each employee appears only once regardless of how many events they have.
    This is useful for attendance tracking where you need to know when each employee
    needs to report to work.

    Args:
        date: Date string in 'YYYY-MM-DD' format (URL path parameter)

    Returns:
        JSON response with employees array containing employee details and earliest time

    Response Format:
    {
        "employees": [
            {
                "employee_id": "EMP001",
                "employee_name": "John Doe",
                "earliest_time": "08:00 AM",
                "earliest_datetime": "2025-10-15T08:00:00",
                "event_count": 3,
                "attendance_status": "on_time",  // or null if not recorded
                "attendance_id": 123  // or null if not recorded
            }
        ],
        "date": "2025-10-15",
        "total_employees": 5
    }

    Example:
        GET /api/daily-employees/2025-10-15
    """
    from sqlalchemy import func
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Employee = current_app.config['Employee']
    EmployeeAttendance = current_app.config['EmployeeAttendance']

    # Parse and validate date
    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Query all schedules for the selected date with employee details
    # Group by employee and find earliest time
    schedules_query = db.session.query(
        Employee.id.label('employee_id'),
        Employee.name.label('employee_name'),
        func.min(Schedule.schedule_datetime).label('earliest_datetime'),
        func.count(Schedule.id).label('event_count')
    ).join(
        Schedule, Employee.id == Schedule.employee_id
    ).filter(
        func.date(Schedule.schedule_datetime) == selected_date,
        Schedule.employee_id.isnot(None)  # Only include assigned employees
    ).group_by(
        Employee.id,
        Employee.name
    ).order_by(
        func.min(Schedule.schedule_datetime).asc()
    ).all()

    # Build result array
    result = []
    for row in schedules_query:
        # Get attendance record if exists (query by employee and date)
        # Since we want one attendance record per employee per day,
        # we'll look for any attendance record for this employee on this date
        attendance = EmployeeAttendance.query.filter_by(
            employee_id=row.employee_id,
            attendance_date=selected_date
        ).first()

        result.append({
            'employee_id': row.employee_id,
            'employee_name': row.employee_name,
            'earliest_time': row.earliest_datetime.strftime('%I:%M %p'),
            'earliest_datetime': row.earliest_datetime.isoformat(),
            'event_count': row.event_count,
            'attendance_status': attendance.status if attendance else None,
            'attendance_id': attendance.id if attendance else None,
            'attendance_notes': attendance.notes if attendance else None
        })

    return jsonify({
        'employees': result,
        'date': date,
        'total_employees': len(result)
    }), 200


@api_bp.route('/event-by-ref/<ref_num>')
def get_event_by_ref(ref_num):
    """
    Get event details by project reference number.
    
    This endpoint is used to look up an event's internal ID using its 
    project_ref_num, which is needed for scheduling operations.
    
    Args:
        ref_num: Project reference number (URL path parameter)
        
    Returns:
        JSON with event id and basic details, or 404 if not found
    """
    Event = current_app.config['Event']
    
    event = Event.query.filter_by(project_ref_num=ref_num).first()
    
    if not event:
        return jsonify({'error': f'Event not found with ref: {ref_num}'}), 404
    
    return jsonify({
        'id': event.id,
        'project_ref_num': event.project_ref_num,
        'project_name': event.project_name,
        'event_type': event.event_type,
        'start_datetime': event.start_datetime.isoformat() if event.start_datetime else None,
        'due_datetime': event.due_datetime.isoformat() if event.due_datetime else None,
        'condition': event.condition
    }), 200


@api_bp.route('/event/<int:schedule_id>/unschedule', methods=['POST'])
def unschedule_event_quick(schedule_id):
    """
    Remove employee assignment from event by deleting schedule (Story 3.5).

    This endpoint deletes a schedule record, effectively unscheduling an event
    by removing the employee assignment. If an attendance record exists for
    this schedule, it will be cascade deleted (if configured) and a warning
    flag is returned.

    Args:
        schedule_id: Schedule ID to delete (integer, path parameter)

    Returns:
        JSON response with success status and warning flag

    Response Format:
        {
            "success": true,
            "schedule_id": 123,
            "had_attendance": false,
            "message": "Event unscheduled successfully"
        }

    Example:
        POST /api/event/123/unschedule

    Status Codes:
        200: Success
        404: Schedule not found
        500: Database error

    Note:
        - Schedule deletion cascades to attendance records if cascade configured
        - Event remains in events table, just becomes unassigned
        - had_attendance flag indicates if attendance record existed
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']

    # Query schedule
    schedule = Schedule.query.get(schedule_id)

    if not schedule:
        return jsonify({
            'error': 'Schedule not found',
            'schedule_id': schedule_id
        }), 404

    # Note: Attendance is now tracked by employee+date, not by schedule_id
    # Unscheduling an event does NOT delete attendance records since attendance
    # is tied to the employee's day, not to specific events/schedules
    has_attendance = False

    # Store employee and event info for logging before deletion
    employee_name = schedule.employee.name if schedule.employee else 'Unassigned'
    event_name = schedule.event.project_name if schedule.event else 'Unknown Event'

    try:
        # Call Crossmark API BEFORE deleting local record
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Ensure session is authenticated
        if schedule.external_id:
            try:
                if not external_api.ensure_authenticated():
                    error_msg = f'Failed to authenticate with Crossmark API for schedule {schedule_id}'
                    logger.error(error_msg)
                    return jsonify({
                        'error': 'Authentication failed',
                        'details': 'Could not authenticate with Crossmark API. Please check credentials.'
                    }), 500

                logger.info(f"Submitting unschedule to Crossmark API: schedule_id={schedule.external_id}, external_id={schedule.external_id}")
                api_result = external_api.unschedule_mplan_event(str(schedule.external_id))

                logger.info(f"API result: success={api_result.get('success')}, message={api_result.get('message')}")

                if not api_result.get('success'):
                    error_message = api_result.get('message', 'Unknown API error')
                    logger.error(f"Crossmark API error: {error_message}")
                    return jsonify({
                        'error': 'Failed to unschedule in Crossmark',
                        'details': error_message
                    }), 500

                logger.info(f"Successfully unscheduled event in Crossmark API")

            except Exception as api_error:
                logger.error(f"API submission error: {str(api_error)}", exc_info=True)
                return jsonify({
                    'error': 'Failed to submit to Crossmark API',
                    'details': str(api_error)
                }), 500
        else:
            logger.warning(f"Schedule {schedule_id} has no external_id, skipping Crossmark API call")

        # Get the event for CORE-Supervisor pairing check
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()

        # Track supervisor schedule_id for frontend removal
        unscheduled_supervisor_id = None

        # BEGIN NESTED TRANSACTION for CORE-Supervisor pairing
        try:
            with db.session.begin_nested():
                # NEW: Check if this is a CORE event and unschedule Supervisor (Sprint 2)
                from app.utils.event_helpers import is_core_event_redesign, get_supervisor_status

                if event and is_core_event_redesign(event):
                    logger.info(f"CORE event detected: {event.project_name}. Checking for paired Supervisor...")

                    supervisor_status = get_supervisor_status(event)

                    if supervisor_status['exists'] and supervisor_status['is_scheduled']:
                        supervisor_event = supervisor_status['event']
                        logger.info(
                            f"Found paired Supervisor: {supervisor_event.project_name} (ID: {supervisor_event.project_ref_num})"
                        )

                        # Find Supervisor's schedule
                        supervisor_schedule = Schedule.query.filter_by(
                            event_ref_num=supervisor_event.project_ref_num
                        ).first()

                        if supervisor_schedule:
                            # Store supervisor schedule_id BEFORE deletion for frontend sync
                            unscheduled_supervisor_id = supervisor_schedule.id
                            
                            # Call Crossmark API to unschedule Supervisor
                            if supervisor_schedule.external_id:
                                logger.info(
                                    f"Calling Crossmark API to unschedule Supervisor: schedule_id={supervisor_schedule.external_id}"
                                )

                                supervisor_api_result = external_api.unschedule_mplan_event(str(supervisor_schedule.external_id))

                                if not supervisor_api_result.get('success'):
                                    error_msg = supervisor_api_result.get('message', 'Unknown API error')
                                    logger.error(f"Supervisor unschedule API call failed: {error_msg}")
                                    raise Exception(f"Failed to unschedule Supervisor in Crossmark: {error_msg}")

                                logger.info(f"Successfully unscheduled Supervisor in Crossmark API")

                            # Delete Supervisor schedule record
                            db.session.delete(supervisor_schedule)

                            # Check if Supervisor has other schedules
                            remaining_supervisor_schedules = Schedule.query.filter_by(
                                event_ref_num=supervisor_event.project_ref_num
                            ).count()
                            if remaining_supervisor_schedules == 0:
                                supervisor_event.is_scheduled = False
                                supervisor_event.condition = 'Unstaffed'

                            logger.info(
                                f"✅ Successfully auto-unscheduled Supervisor event {supervisor_event.project_ref_num}"
                            )
                        else:
                            logger.warning(f"Supervisor schedule not found for event {supervisor_event.project_ref_num}")
                    elif supervisor_status['exists']:
                        logger.info(
                            f"Supervisor event exists but is not scheduled (condition: {supervisor_status['condition']}). "
                            f"No auto-unschedule needed."
                        )
                    else:
                        logger.info("No paired Supervisor event found for this CORE event.")

                # Delete the CORE schedule
                db.session.delete(schedule)

            # COMMIT TRANSACTION
            db.session.commit()

            logger.info(
                f'Schedule {schedule_id} deleted. Employee: {employee_name}, '
                f'Event: {event_name}, Had attendance: {has_attendance}'
            )

            return jsonify({
                'success': True,
                'schedule_id': schedule_id,
                'had_attendance': has_attendance,
                'unscheduled_supervisor_id': unscheduled_supervisor_id,
                'message': 'Event unscheduled successfully' + (f' (Supervisor also unscheduled)' if unscheduled_supervisor_id else '')
            }), 200

        except Exception as nested_error:
            db.session.rollback()
            logger.error(f"Transaction failed during unschedule: {str(nested_error)}", exc_info=True)
            raise nested_error

    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete schedule {schedule_id}: {e}', exc_info=True)

        return jsonify({
            'error': 'Failed to unschedule event',
            'details': str(e)
        }), 500


@api_bp.route('/core_employees_for_trade/<date>/<int:current_schedule_id>')
def core_employees_for_trade(date, current_schedule_id):
    """Get employees with Core events on the same date for trading"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Get other Core events scheduled on the same date (excluding current schedule)
    core_schedules = db.session.query(Schedule, Event, Employee).join(
        Event, Schedule.event_ref_num == Event.project_ref_num
    ).join(
        Employee, Schedule.employee_id == Employee.id
    ).filter(
        db.func.date(Schedule.schedule_datetime) == parsed_date,
        Event.event_type == 'Core',
        Schedule.id != current_schedule_id
    ).order_by(Schedule.schedule_datetime).all()

    employees_data = []
    for schedule, event, employee in core_schedules:
        employees_data.append({
            'schedule_id': schedule.id,
            'employee_name': employee.name,
            'employee_id': employee.id,
            'event_name': event.project_name,
            'time': schedule.schedule_datetime.strftime('%I:%M %p')
        })

    return jsonify(employees_data)


@api_bp.route('/available_employees_for_change/<date>/<event_type>')
def available_employees_for_change(date, event_type):
    """Get available employees for changing event assignment with proper role-based filtering"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']
    EmployeeAvailability = current_app.config['EmployeeAvailability']
    EmployeeTimeOff = current_app.config['EmployeeTimeOff']
    EmployeeWeeklyAvailability = current_app.config['EmployeeWeeklyAvailability']

    try:
        parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Get optional parameters for current employee (for reschedule)
    from flask import request
    current_employee_id = request.args.get('current_employee_id', type=str)
    current_date_str = request.args.get('current_date', type=str)
    current_date = None
    if current_date_str:
        try:
            current_date = datetime.strptime(current_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # Get all active employees
    all_employees = Employee.query.filter_by(is_active=True).all()
    
    # Check override
    override = request.args.get('override') == 'true'
    if override:
         # Return all active employees without further filtering
         employees_data = []
         for emp in all_employees:
             employees_data.append({
                 'id': emp.id,
                 'name': emp.name,
                 'job_title': emp.job_title
             })
         return jsonify(employees_data)

    # For Core events, get employees already scheduled for Core events that day
    if event_type == 'Core':
        core_scheduled_employees = db.session.query(Schedule.employee_id).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            db.func.date(Schedule.schedule_datetime) == parsed_date,
            Event.event_type == 'Core'
        ).all()
        core_scheduled_employee_ids = {emp[0] for emp in core_scheduled_employees}
    else:
        core_scheduled_employee_ids = set()

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

    weekly_availability_query = db.session.query(
        EmployeeWeeklyAvailability.employee_id,
        getattr(EmployeeWeeklyAvailability, day_column).label('is_available_weekly')
    ).all()

    weekly_unavailable_ids = {
        emp[0] for emp in weekly_availability_query
        if not emp[1]
    }

    # Filter available employees
    available_employees_list = []
    for emp in all_employees:
        # Special exception for current employee when rescheduling
        is_current_employee = (current_employee_id and emp.id == current_employee_id)
        is_same_day = (current_date and current_date == parsed_date)

        # Allow current employee if it's the same day OR a day they're not scheduled
        allow_current_employee = False
        if is_current_employee:
            if is_same_day:
                # Same day - always allow
                allow_current_employee = True
            else:
                # Different day - only allow if they're not scheduled for a Core event on the new date
                allow_current_employee = (emp.id not in core_scheduled_employee_ids)

        # Normal availability checks (skip for allowed current employee on same day)
        if not (is_current_employee and is_same_day):
            if (emp.id in core_scheduled_employee_ids or
                emp.id in unavailable_employee_ids or
                emp.id in time_off_employee_ids or
                emp.id in weekly_unavailable_ids):
                # Skip unless this is the current employee being allowed
                if not allow_current_employee:
                    continue

        # Role-based restrictions
        # Special handling for "Other" events - only Lead Event Specialist and Club Supervisor
        if event_type == 'Other':
            if emp.job_title not in ['Lead Event Specialist', 'Club Supervisor']:
                continue
        # Check role-based restrictions for the event type
        elif not emp.can_work_event_type(event_type):
            continue

        available_employees_list.append({
            'id': emp.id,
            'name': emp.name,
            'job_title': emp.job_title
        })

    # For Digital Teardown and Digitals events, sort by role priority:
    # 1. Secondary Lead (Lead Event Specialist)
    # 2. Primary Lead (if separate from Secondary, otherwise same as Lead Event Specialist)
    # 3. Club Supervisor
    # 4. Everyone else alphabetically
    if event_type.lower() in ['digitals', 'digital teardown', 'digital setup', 'digital refresh']:
        def role_priority(emp):
            job_title = (emp.get('job_title') or '').lower()
            if 'secondary' in job_title or 'lead event specialist' in job_title:
                return (0, emp['name'])  # Highest priority
            elif 'lead' in job_title and 'secondary' not in job_title:
                return (1, emp['name'])  # Primary lead
            elif 'supervisor' in job_title:
                return (2, emp['name'])  # Club Supervisor
            else:
                return (3, emp['name'])  # Everyone else
        
        available_employees_list.sort(key=role_priority)

    return jsonify(available_employees_list)


@api_bp.route('/event-default-time/<event_type>')
def get_event_default_time(event_type):
    """
    Get the default start time for an event type based on settings.

    Used by the schedule modal to set a sensible default time.

    Args:
        event_type: Event type (Core, Juicer, Freeosk, Digitals, Supervisor, Other)

    Returns:
        JSON with default_time in HH:MM format
    """
    from app.services.event_time_settings import EventTimeSettings

    try:
        event_type_lower = event_type.lower()

        if event_type_lower == 'core':
            # Get first Core slot start time
            slots = EventTimeSettings.get_core_slots()
            if slots:
                default_time = slots[0]['start']
                return jsonify({
                    'success': True,
                    'default_time': f"{default_time.hour:02d}:{default_time.minute:02d}"
                })
        elif event_type_lower == 'freeosk':
            times = EventTimeSettings.get_freeosk_times()
            default_time = times['start']
            return jsonify({
                'success': True,
                'default_time': f"{default_time.hour:02d}:{default_time.minute:02d}"
            })
        elif event_type_lower == 'supervisor':
            times = EventTimeSettings.get_supervisor_times()
            default_time = times['start']
            return jsonify({
                'success': True,
                'default_time': f"{default_time.hour:02d}:{default_time.minute:02d}"
            })
        elif event_type_lower in ['digitals', 'digital setup', 'digital refresh']:
            # Get first Digital Setup slot
            slots = EventTimeSettings.get_digital_setup_slots()
            if slots:
                default_time = slots[0]['start']
                return jsonify({
                    'success': True,
                    'default_time': f"{default_time.hour:02d}:{default_time.minute:02d}"
                })
        elif event_type_lower == 'digital teardown':
            slots = EventTimeSettings.get_digital_teardown_slots()
            if slots:
                default_time = slots[0]['start']
                return jsonify({
                    'success': True,
                    'default_time': f"{default_time.hour:02d}:{default_time.minute:02d}"
                })
        elif event_type_lower == 'other':
            times = EventTimeSettings.get_other_times()
            default_time = times['start']
            return jsonify({
                'success': True,
                'default_time': f"{default_time.hour:02d}:{default_time.minute:02d}"
            })
        elif event_type_lower in ['juicer', 'juicer production', 'juicer survey', 'juicer deep clean']:
            # Juicer types use 9 AM start
            return jsonify({
                'success': True,
                'default_time': '09:00'
            })

        # Fallback to 09:00
        return jsonify({
            'success': True,
            'default_time': '09:00'
        })

    except Exception as e:
        logger.error(f"Error getting default time for {event_type}: {e}")
        return jsonify({
            'success': False,
            'default_time': '09:00',
            'error': str(e)
        })


@api_bp.route('/event-allowed-times/<event_type>')
def get_event_allowed_times(event_type):
    """
    Get the allowed scheduling times for an event type based on settings.

    Used by reschedule modal to populate time dropdown with valid options.

    Args:
        event_type: Event type (Core, Juicer, Freeosk, Digitals, Supervisor, Other)

    Returns:
        JSON with allowed_times array in HH:MM format
    """
    from app.services.event_time_settings import EventTimeSettings

    try:
        event_type_lower = event_type.lower()
        allowed_times = []

        if event_type_lower == 'core':
            # Get 4 unique times from 8-block ShiftBlockConfig (Arrive times)
            from app.services.shift_block_config import ShiftBlockConfig
            blocks = ShiftBlockConfig.get_all_blocks()
            if blocks:
                for block in blocks:
                    arrive = block['arrive']
                    allowed_times.append(f"{arrive.hour:02d}:{arrive.minute:02d}")
            else:
                # Fallback to old EventTimeSettings
                slots = EventTimeSettings.get_core_slots()
                for slot in slots:
                    start = slot['start']
                    allowed_times.append(f"{start.hour:02d}:{start.minute:02d}")
        elif event_type_lower == 'freeosk':
            times = EventTimeSettings.get_freeosk_times()
            allowed_times.append(f"{times['start'].hour:02d}:{times['start'].minute:02d}")
        elif event_type_lower == 'supervisor':
            times = EventTimeSettings.get_supervisor_times()
            allowed_times.append(f"{times['start'].hour:02d}:{times['start'].minute:02d}")
        elif event_type_lower in ['digitals', 'digital setup', 'digital refresh']:
            slots = EventTimeSettings.get_digital_setup_slots()
            for slot in slots:
                start = slot['start']
                allowed_times.append(f"{start.hour:02d}:{start.minute:02d}")
        elif event_type_lower == 'digital teardown':
            slots = EventTimeSettings.get_digital_teardown_slots()
            for slot in slots:
                start = slot['start']
                allowed_times.append(f"{start.hour:02d}:{start.minute:02d}")
        elif event_type_lower == 'other':
            times = EventTimeSettings.get_other_times()
            allowed_times.append(f"{times['start'].hour:02d}:{times['start'].minute:02d}")
        elif event_type_lower in ['juicer', 'juicer production', 'juicer survey', 'juicer deep clean']:
            # Juicer events don't have time restrictions - allow any time
            # Return empty list to indicate no restrictions (free-form input)
            pass

        # Remove duplicates while preserving order
        seen = set()
        unique_times = []
        for t in allowed_times:
            if t not in seen:
                seen.add(t)
                unique_times.append(t)
        
        # Calculate counts if date provided
        date_str = request.args.get('date')
        time_details = []
        
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                db = current_app.extensions['sqlalchemy']
                Schedule = current_app.config['Schedule']
                
                for t_str in unique_times:
                    from datetime import time as dt_time
                    h, m = map(int, t_str.split(':'))
                    dt = datetime.combine(target_date, dt_time(h, m))
                    
                    count = db.session.query(Schedule).filter(
                        Schedule.schedule_datetime == dt
                    ).count()
                    
                    # Format label
                    t_obj = dt_time(h, m)
                    hour_12 = t_obj.hour % 12 or 12
                    am_pm = 'AM' if t_obj.hour < 12 else 'PM'
                    label = f"{hour_12}:{t_obj.minute:02d} {am_pm}"
                    
                    time_details.append({
                        'value': t_str,
                        'label': f"{label} ({count} scheduled)",
                        'count': count
                    })
            except Exception as e:
                logger.error(f"Error counting schedules: {e}")
                # Fallback to simple list
                time_details = [{'value': t, 'label': t} for t in unique_times]
        else:
            # No date, just return times
            # Frontend handles formatting slightly differently if just strings, 
            # but we'll return objects for consistency if main.js is updated
             for t_str in unique_times:
                h, m = map(int, t_str.split(':'))
                hour_12 = h % 12 or 12
                am_pm = 'AM' if h < 12 else 'PM'
                label = f"{hour_12}:{m:02d} {am_pm}"
                time_details.append({
                    'value': t_str,
                    'label': label,
                    'count': 0
                })

        return jsonify({
            'success': True,
            'event_type': event_type,
            'allowed_times': unique_times, # Keep for backward compat
            'time_details': time_details,   # New detailed list
            'has_restrictions': len(unique_times) > 0
        })

    except Exception as e:
        logger.error(f"Error getting allowed times for {event_type}: {e}")
        return jsonify({
            'success': False,
            'allowed_times': [],
            'has_restrictions': False,
            'error': str(e)
        })


@api_bp.route('/event-time-settings')
def get_event_time_settings():
    """
    Get all event time settings for the scheduler.

    Returns core timeslots for populating schedule time dropdowns.
    Used by reissue modal and other scheduling interfaces.
    
    NOTE: This returns 4 slots for external API compatibility.
    The 8-block shift system is used for daily view and EDR printing only.

    Returns:
        JSON with core_slots array containing slot info
    """
    from app.services.event_time_settings import EventTimeSettings

    try:
        # Get core slots (4 unique times from 8-block system)
        from app.services.shift_block_config import ShiftBlockConfig
        blocks = ShiftBlockConfig.get_all_blocks()
        
        core_slots = []
        if blocks:
            # Build core slots from shift blocks (use unique arrive times as requested)
            seen_times = set()
            slot_num = 1
            for block in blocks:
                # Use expected Arrive time
                arrive = block['arrive']
                start_str = f"{arrive.hour:02d}:{arrive.minute:02d}"
                
                # Only add unique times
                if start_str not in seen_times:
                    seen_times.add(start_str)
                    # Format readable label
                    hour_12 = arrive.hour % 12 or 12
                    am_pm = 'AM' if arrive.hour < 12 else 'PM'
                    label = f"{hour_12}:{arrive.minute:02d} {am_pm}"
                    
                    core_slots.append({
                        'slot': slot_num,
                        'start': start_str,
                        'label': label
                    })
                    slot_num += 1
        else:
             # Fallback
             core_slots_raw = EventTimeSettings.get_core_slots()
             for slot in core_slots_raw:
                start = slot['start']
                start_str = f"{start.hour:02d}:{start.minute:02d}"
                hour_12 = start.hour % 12 or 12
                am_pm = 'AM' if start.hour < 12 else 'PM'
                label = f"{hour_12}:{start.minute:02d} {am_pm}"
                core_slots.append({
                    'slot': slot['slot'],
                    'start': start_str,
                    'label': label
                })

        return jsonify({
            'success': True,
            'core_slots': core_slots
        })

    except Exception as e:
        logger.error(f"Error getting event time settings: {e}")
        # Return default core slots as fallback
        return jsonify({
            'success': False,
            'core_slots': [
                {'slot': 1, 'start': '10:45', 'label': '10:45 AM'},
                {'slot': 2, 'start': '11:15', 'label': '11:15 AM'},
                {'slot': 3, 'start': '11:45', 'label': '11:45 AM'},
                {'slot': 4, 'start': '12:15', 'label': '12:15 PM'}
            ],
            'error': str(e)
        })


@api_bp.route('/validate_schedule_for_export')
def validate_schedule_for_export():
    """Validate scheduled events before export and return any errors"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        today = date.today()

        # Query scheduled events with JOIN, filtering for current day and future
        scheduled_events = db.session.query(
            Schedule.id.label('schedule_id'),
            Event.project_name,
            Event.project_ref_num,
            Event.start_datetime,
            Event.due_datetime,
            Event.event_type,
            Employee.name.label('employee_name'),
            Schedule.schedule_datetime
        ).join(
            Schedule, Event.project_ref_num == Schedule.event_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            db.func.date(Schedule.schedule_datetime) >= today
        ).order_by(Schedule.schedule_datetime).all()

        # Validate each event's schedule date is within its start/due date range
        validation_errors = []

        for event in scheduled_events:
            schedule_date = event.schedule_datetime.date()
            start_date = event.start_datetime.date()
            due_date = event.due_datetime.date()

            # Check if scheduled date is within the event's valid date range
            if not (start_date <= schedule_date <= due_date):
                validation_errors.append({
                    'schedule_id': event.schedule_id,
                    'project_name': event.project_name,
                    'project_ref_num': event.project_ref_num,
                    'event_type': event.event_type,
                    'employee_name': event.employee_name,
                    'scheduled_date': schedule_date.strftime('%Y-%m-%d'),
                    'scheduled_time': event.schedule_datetime.strftime('%H:%M'),
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'due_date': due_date.strftime('%Y-%m-%d'),
                    'error_type': 'date_range_violation',
                    'error_message': f'Scheduled for {schedule_date.strftime("%m/%d/%Y")} but valid range is {start_date.strftime("%m/%d/%Y")} to {due_date.strftime("%m/%d/%Y")}'
                })

        # Format errors for the frontend
        formatted_errors = []
        for error in validation_errors:
            formatted_errors.append({
                'schedule_id': error['schedule_id'],
                'project_name': error['project_name'],
                'event_type': error['event_type'],
                'scheduled_date': error['scheduled_date'],
                'valid_start': error['start_date'],
                'valid_end': error['due_date'],
                'error': error['error_message']
            })

        return jsonify({
            'valid': len(validation_errors) == 0,
            'errors': formatted_errors,
            'total_events': len(scheduled_events),
            'valid_events': len(scheduled_events) - len(validation_errors)
        })

    except Exception as e:
        return jsonify({'error': f'Error validating schedule: {str(e)}'}), 500


@api_bp.route('/schedule/<int:schedule_id>')
def get_schedule_details(schedule_id):
    """Get details for a specific schedule"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']

    try:
        schedule = db.session.get(Schedule, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get the event details to include event type
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        return jsonify({
            'id': schedule.id,
            'event_ref_num': schedule.event_ref_num,
            'employee_id': schedule.employee_id,
            'schedule_datetime': schedule.schedule_datetime.isoformat(),
            'event_type': event.event_type,
            'start_date': event.start_datetime.date().isoformat(),
            'due_date': event.due_datetime.date().isoformat()
        })

    except Exception as e:
        return jsonify({'error': f'Error fetching schedule: {str(e)}'}), 500


@api_bp.route('/reschedule', methods=['POST'])
def reschedule():
    """Reschedule an event - handles both JSON and FormData"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Handle both JSON and FormData requests
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()

        schedule_id = data.get('schedule_id')
        new_date = data.get('new_date')
        new_time = data.get('new_time')
        new_employee_id = data.get('employee_id')

        # Get the current schedule
        schedule = db.session.get(Schedule, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get the event to check type for validation
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Parse and validate new date and time
        parsed_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        parsed_time = datetime.strptime(new_time, '%H:%M').time()
        new_datetime = datetime.combine(parsed_date, parsed_time)

        # CRITICAL VALIDATION: Ensure new datetime is within event period
        # This prevents rescheduling events outside their valid start/due date window
        override = str(data.get('override')).lower() == 'true'
        
        if not override and not (event.start_datetime <= new_datetime <= event.due_datetime):
            return jsonify({
                'error': f'Cannot reschedule: New date/time {new_datetime.strftime("%Y-%m-%d %H:%M")} '
                         f'is outside the event period '
                         f'({event.start_datetime.strftime("%Y-%m-%d")} to {event.due_datetime.strftime("%Y-%m-%d")})'
            }), 400

        # Check if new employee can work this event type
        new_employee = db.session.get(Employee, new_employee_id)
        if not new_employee:
             return jsonify({'error': 'Employee not found'}), 404
             
        if not override and not new_employee.can_work_event_type(event.event_type):
            if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
                return jsonify({'error': 'Employee cannot work Juicer events. Only Club Supervisors and Juicer Baristas can work Juicer events.'}), 400
            elif event.event_type in ['Supervisor', 'Freeosk', 'Digitals']:
                return jsonify({'error': f'Employee cannot work {event.event_type} events. Only Club Supervisors and Lead Event Specialists can work this type of event.'}), 400
            else:
                return jsonify({'error': 'Employee cannot work this event type'}), 400

        # For Core events, check if new employee already has a Core event that day
        if not override and event.event_type == 'Core':
            existing_core = Schedule.query.join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == new_employee_id,
                db.func.date(Schedule.schedule_datetime) == parsed_date,
                Event.event_type == 'Core',
                Schedule.id != schedule_id
            ).first()

            if existing_core:
                return jsonify({'error': 'Employee already has a Core event scheduled that day'}), 400

        # Submit to Crossmark API BEFORE updating local record
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Calculate end datetime
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = new_datetime + timedelta(minutes=estimated_minutes)

        # Prepare API data
        rep_id = str(new_employee.external_id) if new_employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        # Validate required API fields
        if not rep_id:
            return jsonify({'error': f'Missing Crossmark employee ID for {new_employee.name}'}), 400

        if not mplan_id:
            return jsonify({'error': 'Missing Crossmark event ID'}), 400

        if not location_id:
            return jsonify({'error': 'Missing Crossmark location ID'}), 400

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            current_app.logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Submit to external API
        try:
            current_app.logger.info(
                f"Submitting reschedule to Crossmark API: "
                f"rep_id={rep_id}, mplan_id={mplan_id}, location_id={location_id}, "
                f"start={new_datetime.isoformat()}, end={end_datetime.isoformat()}"
            )

            api_result = external_api.schedule_mplan_event(
                rep_id=rep_id,
                mplan_id=mplan_id,
                location_id=location_id,
                start_datetime=new_datetime,
                end_datetime=end_datetime,
                planning_override=True
            )

            if not api_result.get('success'):
                error_message = api_result.get('message', 'Unknown API error')
                current_app.logger.error(f"Crossmark API error: {error_message}")
                return jsonify({'error': f'Failed to submit to Crossmark: {error_message}'}), 500

            current_app.logger.info(f"Successfully submitted reschedule to Crossmark API")

        except Exception as api_error:
            current_app.logger.error(f"API submission error: {str(api_error)}")
            return jsonify({'error': f'Failed to submit to Crossmark API: {str(api_error)}'}), 500

        # API submission successful - now update local record with transaction
        try:
            # BEGIN NESTED TRANSACTION for CORE-Supervisor pairing
            with db.session.begin_nested():
                # Update CORE event schedule
                schedule.employee_id = new_employee_id
                schedule.schedule_datetime = new_datetime

                # Update event sync status
                event.sync_status = 'synced'
                event.last_synced = datetime.utcnow()

                # NEW: Check if this is a CORE event and reschedule Supervisor (Calendar Redesign - Sprint 2)
                from app.utils.event_helpers import is_core_event_redesign, get_supervisor_status

                # Check both event_type and project name for Core detection
                is_core = event.event_type == 'Core' or is_core_event_redesign(event)
                
                if is_core:
                    current_app.logger.info(f"CORE event detected (type={event.event_type}): {event.project_name}. Checking for paired Supervisor...")

                    supervisor_status = get_supervisor_status(event)

                    if supervisor_status['exists']:
                        supervisor_event = supervisor_status['event']
                        current_app.logger.info(
                            f"Found paired Supervisor: {supervisor_event.project_name} (ID: {supervisor_event.project_ref_num})"
                        )

                        # Get Supervisor time from settings instead of hardcoded offset
                        from app.services.event_time_settings import EventTimeSettings
                        supervisor_times = EventTimeSettings.get_supervisor_times()
                        supervisor_start_time = supervisor_times['start']
                        
                        # Use the configured supervisor time on the same date as the Core event
                        supervisor_new_datetime = datetime.combine(
                            new_datetime.date(),
                            supervisor_start_time
                        )

                        if supervisor_status['is_scheduled']:
                            # Supervisor is already scheduled - reschedule it
                            supervisor_schedule = Schedule.query.filter_by(
                                event_ref_num=supervisor_event.project_ref_num
                            ).first()

                            if supervisor_schedule:
                                # Get Supervisor employee
                                supervisor_employee = db.session.get(Employee, supervisor_schedule.employee_id)

                                if supervisor_employee:
                                    # Prepare Supervisor API data
                                    supervisor_rep_id = str(supervisor_employee.external_id) if supervisor_employee.external_id else None
                                    supervisor_mplan_id = str(supervisor_event.external_id) if supervisor_event.external_id else None
                                    supervisor_location_id = str(supervisor_event.location_mvid) if supervisor_event.location_mvid else None

                                    # Validate Supervisor API fields
                                    if all([supervisor_rep_id, supervisor_mplan_id, supervisor_location_id]):
                                        # Calculate Supervisor end datetime
                                        supervisor_estimated_minutes = supervisor_event.estimated_time or supervisor_event.get_default_duration(supervisor_event.event_type)
                                        supervisor_end_datetime = supervisor_new_datetime + timedelta(minutes=supervisor_estimated_minutes)

                                        # Call Crossmark API for Supervisor
                                        current_app.logger.info(
                                            f"Rescheduling Supervisor at configured time: {supervisor_new_datetime.isoformat()}"
                                        )

                                        supervisor_api_result = external_api.schedule_mplan_event(
                                            rep_id=supervisor_rep_id,
                                            mplan_id=supervisor_mplan_id,
                                            location_id=supervisor_location_id,
                                            start_datetime=supervisor_new_datetime,
                                            end_datetime=supervisor_end_datetime,
                                            planning_override=True
                                        )

                                        if not supervisor_api_result.get('success'):
                                            error_msg = supervisor_api_result.get('message', 'Unknown API error')
                                            current_app.logger.error(f"Supervisor API call failed: {error_msg}")
                                            raise Exception(f"Failed to reschedule Supervisor in Crossmark: {error_msg}")

                                        # Update Supervisor schedule
                                        supervisor_schedule.schedule_datetime = supervisor_new_datetime

                                        # Update Supervisor event sync status
                                        supervisor_event.sync_status = 'synced'
                                        supervisor_event.last_synced = datetime.utcnow()

                                        current_app.logger.info(
                                            f"✅ Successfully auto-rescheduled Supervisor event {supervisor_event.project_ref_num} "
                                            f"to {supervisor_new_datetime.isoformat()}"
                                        )
                                    else:
                                        current_app.logger.warning(
                                            f"Supervisor API fields incomplete for {supervisor_event.project_name}. "
                                            f"Skipping Supervisor reschedule."
                                        )
                                else:
                                    current_app.logger.warning(f"Supervisor employee not found for schedule {supervisor_schedule.id}")
                            else:
                                current_app.logger.warning(f"Supervisor schedule not found for event {supervisor_event.project_ref_num}")
                        else:
                            # Supervisor exists but is not scheduled - schedule it now
                            current_app.logger.info(
                                f"Supervisor event not scheduled. Scheduling at {supervisor_new_datetime.isoformat()}"
                            )
                            
                            # Find Club Supervisor first, then Primary Lead fallback
                            # Priority: Club Supervisor → Primary Lead Event Specialist (from rotation)
                            target_date = supervisor_new_datetime.date()
                            day_of_week = target_date.weekday()
                            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                            day_column = day_names[day_of_week]
                            
                            supervisor_employee = None
                            
                            # Try Club Supervisor first
                            club_supervisor = Employee.query.filter_by(
                                job_title='Club Supervisor',
                                is_active=True
                            ).first()
                            
                            if club_supervisor:
                                # Check time off
                                time_off = EmployeeTimeOff.query.filter(
                                    EmployeeTimeOff.employee_id == club_supervisor.id,
                                    EmployeeTimeOff.start_date <= target_date,
                                    EmployeeTimeOff.end_date >= target_date
                                ).first()
                                
                                if not time_off:
                                    # Check weekly availability
                                    weekly_avail = EmployeeWeeklyAvailability.query.filter_by(
                                        employee_id=club_supervisor.id
                                    ).first()
                                    
                                    is_available = True
                                    if weekly_avail:
                                        is_available = getattr(weekly_avail, day_column, True)
                                    
                                    if is_available:
                                        supervisor_employee = club_supervisor
                                        current_app.logger.info(f"Supervisor event will be assigned to Club Supervisor: {club_supervisor.name}")
                            
                            # Fallback to Primary Lead for that day if Club Supervisor not available
                            if not supervisor_employee:
                                from app.services.rotation_manager import RotationManager
                                rotation_manager = RotationManager(db.session)
                                
                                # Get the Primary Lead assigned for this specific date
                                primary_lead = rotation_manager.get_rotation_employee(supervisor_new_datetime, 'primary_lead')
                                
                                if primary_lead:
                                    # Check time off
                                    time_off = EmployeeTimeOff.query.filter(
                                        EmployeeTimeOff.employee_id == primary_lead.id,
                                        EmployeeTimeOff.start_date <= target_date,
                                        EmployeeTimeOff.end_date >= target_date
                                    ).first()
                                    
                                    if not time_off:
                                        # Check weekly availability
                                        weekly_avail = EmployeeWeeklyAvailability.query.filter_by(
                                            employee_id=primary_lead.id
                                        ).first()
                                        
                                        is_available = True
                                        if weekly_avail:
                                            is_available = getattr(weekly_avail, day_column, True)
                                        
                                        if is_available:
                                            supervisor_employee = primary_lead
                                            current_app.logger.info(f"Supervisor event will be assigned to Primary Lead: {primary_lead.name}")
                            
                            if not supervisor_employee:
                                current_app.logger.warning("No Club Supervisor or Primary Lead available for Supervisor event. Using Core employee as fallback.")
                                # Fallback to Core employee
                                supervisor_employee = Employee.query.filter_by(id=new_employee_id).first()
                            
                            supervisor_rep_id = str(supervisor_employee.external_id) if supervisor_employee and supervisor_employee.external_id else None
                            supervisor_mplan_id = str(supervisor_event.external_id) if supervisor_event.external_id else None
                            supervisor_location_id = str(supervisor_event.location_mvid) if supervisor_event.location_mvid else None

                            if all([supervisor_rep_id, supervisor_mplan_id, supervisor_location_id]):
                                supervisor_estimated_minutes = supervisor_event.estimated_time or supervisor_event.get_default_duration(supervisor_event.event_type)
                                supervisor_end_datetime = supervisor_new_datetime + timedelta(minutes=supervisor_estimated_minutes)

                                supervisor_api_result = external_api.schedule_mplan_event(
                                    rep_id=supervisor_rep_id,
                                    mplan_id=supervisor_mplan_id,
                                    location_id=supervisor_location_id,
                                    start_datetime=supervisor_new_datetime,
                                    end_datetime=supervisor_end_datetime,
                                    planning_override=True
                                )

                                if supervisor_api_result.get('success'):
                                    # Create new Supervisor schedule
                                    supervisor_schedule = Schedule(
                                        event_ref_num=supervisor_event.project_ref_num,
                                        employee_id=supervisor_employee.id,
                                        schedule_datetime=supervisor_new_datetime
                                    )
                                    db.session.add(supervisor_schedule)
                                    
                                    supervisor_event.is_scheduled = True
                                    supervisor_event.condition = 'Scheduled'
                                    supervisor_event.sync_status = 'synced'
                                    supervisor_event.last_synced = datetime.utcnow()
                                    
                                    current_app.logger.info(
                                        f"✅ Successfully auto-scheduled Supervisor event {supervisor_event.project_ref_num} to {supervisor_employee.name}"
                                    )
                                else:
                                    current_app.logger.warning(f"Failed to schedule Supervisor: {supervisor_api_result.get('message')}")
                            else:
                                current_app.logger.warning("Supervisor API fields incomplete. Skipping.")
                    else:
                        current_app.logger.info("No paired Supervisor event found for this CORE event.")

            # COMMIT TRANSACTION
            db.session.commit()

            return jsonify({'success': True, 'message': 'Event rescheduled successfully'})

        except Exception as nested_error:
            db.session.rollback()
            current_app.logger.error(f"Transaction failed during reschedule: {str(nested_error)}", exc_info=True)
            raise nested_error

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/event/<int:schedule_id>/reschedule', methods=['POST'])
@require_authentication()
def reschedule_event_with_validation(schedule_id):
    """
    Reschedule an event with conflict validation (Story 3.6).

    This endpoint reschedules an event to a new date/time while validating
    against conflicts using the ConstraintValidator service.

    Args:
        schedule_id: Schedule ID to reschedule (path parameter)

    Request Body:
        {
            "new_date": "2025-10-20",
            "new_time": "10:30"
        }

    Returns:
        JSON response with success status or conflict details

    Response Format (Success):
        {
            "success": true,
            "message": "Event rescheduled successfully",
            "schedule_id": 123,
            "new_datetime": "2025-10-20T10:30:00"
        }

    Response Format (Conflict):
        {
            "error": "Reschedule would create conflicts",
            "conflicts": [
                {
                    "type": "time_off",
                    "message": "Employee has requested time off on 2025-10-20",
                    "severity": "hard"
                }
            ]
        }

    Status Codes:
        200: Success
        404: Schedule not found
        409: Conflict - reschedule blocked by constraints
        400: Invalid request data
        500: Server error
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Get request data
        data = request.get_json()
        new_date_str = data.get('new_date')
        new_time_str = data.get('new_time')
        new_employee_id = data.get('employee_id')  # Optional: change employee
        override_conflicts = data.get('override_conflicts', False)

        # Validate required fields
        if not new_date_str or not new_time_str:
            return jsonify({'error': 'Missing required fields: new_date and new_time'}), 400

        # Get the schedule
        schedule = Schedule.query.get(schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get related event and employee
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # If new employee_id provided, use that; otherwise use existing employee
        if new_employee_id:
            employee = Employee.query.get(new_employee_id)
            if not employee:
                return jsonify({'error': f'Employee not found: {new_employee_id}'}), 404
        else:
            employee = Employee.query.get(schedule.employee_id)
            if not employee:
                return jsonify({'error': 'Employee not found'}), 404

        # Parse new date and time
        try:
            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            new_time = datetime.strptime(new_time_str, '%H:%M').time()
            new_datetime = datetime.combine(new_date, new_time)
        except ValueError as e:
            return jsonify({'error': f'Invalid date or time format: {str(e)}'}), 400

        # Validate using ConstraintValidator
        from app.services.constraint_validator import ConstraintValidator

        models = {
            'Employee': Employee,
            'Event': Event,
            'Schedule': Schedule,
            'EmployeeTimeOff': current_app.config.get('EmployeeTimeOff'),
            'EmployeeAvailability': current_app.config.get('EmployeeAvailability'),
            'EmployeeWeeklyAvailability': current_app.config.get('EmployeeWeeklyAvailability'),
            'PendingSchedule': current_app.config.get('PendingSchedule')
        }

        validator = ConstraintValidator(db.session, models)
        # Exclude current schedule from conflict checking - otherwise it flags itself as a conflict
        validation_result = validator.validate_assignment(
            event, employee, new_datetime, 
            exclude_schedule_ids=[schedule_id]
        )

        # Check for conflicts (only block if override is not set)
        if not validation_result.is_valid and not override_conflicts:
            conflicts = []
            for violation in validation_result.violations:
                conflicts.append({
                    'type': violation.constraint_type.value if hasattr(violation.constraint_type, 'value') else str(violation.constraint_type),
                    'message': violation.message,
                    'severity': violation.severity.value if hasattr(violation.severity, 'value') else str(violation.severity),
                    'details': violation.details
                })

            return jsonify({
                'error': 'Reschedule would create conflicts',
                'conflicts': conflicts,
                'can_override': True
            }), 409

        # No conflicts (or overridden) - submit to external API BEFORE updating local database
        from app.integrations.external_api.session_api_service import session_api as external_api
        from datetime import timedelta

        # Calculate end datetime
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = new_datetime + timedelta(minutes=estimated_minutes)

        # Prepare API data
        rep_id = str(employee.external_id) if employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        # Validate required API fields
        if not rep_id:
            return jsonify({'error': f'Missing Crossmark employee ID for {employee.name}'}), 400

        if not mplan_id:
            return jsonify({'error': 'Missing Crossmark event ID'}), 400

        if not location_id:
            return jsonify({'error': 'Missing Crossmark location ID'}), 400

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Submit to external API
        try:
            logger.info(
                f"Submitting reschedule to Crossmark API: "
                f"rep_id={rep_id}, mplan_id={mplan_id}, location_id={location_id}, "
                f"start={new_datetime.isoformat()}, end={end_datetime.isoformat()}"
            )

            api_result = external_api.schedule_mplan_event(
                rep_id=rep_id,
                mplan_id=mplan_id,
                location_id=location_id,
                start_datetime=new_datetime,
                end_datetime=end_datetime,
                planning_override=True
            )

            if not api_result.get('success'):
                error_message = api_result.get('message', 'Unknown API error')
                logger.error(f"Crossmark API error: {error_message}")
                return jsonify({'error': f'Failed to submit to Crossmark: {error_message}'}), 500

            logger.info(f"Successfully submitted reschedule to Crossmark API")

        except Exception as api_error:
            logger.error(f"API submission error: {str(api_error)}")
            return jsonify({'error': f'Failed to submit to Crossmark API: {str(api_error)}'}), 500

        # API submission successful - now update local database with transaction
        from app.integrations.external_api.session_api_service import session_api as external_api

        try:
            with db.session.begin_nested():
                old_datetime = schedule.schedule_datetime
                old_employee_id = schedule.employee_id
                schedule.schedule_datetime = new_datetime
                
                # Update employee if a new one was provided
                if new_employee_id:
                    schedule.employee_id = new_employee_id

                # Update event sync status
                event.sync_status = 'synced'
                event.last_synced = datetime.utcnow()

                # Log if conflicts were overridden
                if not validation_result.is_valid and override_conflicts:
                    logger.warning(
                        f'Schedule {schedule_id} rescheduled with conflict override: '
                        f'{len(validation_result.violations)} conflict(s) ignored'
                    )

                # NEW: Check if this is a CORE event and reschedule Supervisor (Sprint 2)
                from app.utils.event_helpers import is_core_event_redesign, get_supervisor_status

                supervisor_rescheduled = False
                # Check both event_type and project name pattern for Core detection
                is_core = event.event_type == 'Core' or is_core_event_redesign(event)
                if is_core:
                    logger.info(f"CORE event detected (type={event.event_type}): {event.project_name}. Checking for paired Supervisor...")

                    supervisor_status = get_supervisor_status(event)

                    if supervisor_status['exists']:
                        supervisor_event = supervisor_status['event']
                        logger.info(
                            f"Found paired Supervisor: {supervisor_event.project_name} (ID: {supervisor_event.project_ref_num})"
                        )

                        # Calculate supervisor datetime using configured time from settings
                        from app.services.event_time_settings import EventTimeSettings
                        supervisor_times = EventTimeSettings.get_supervisor_times()
                        supervisor_start_time = supervisor_times['start']
                        supervisor_new_datetime = datetime.combine(new_datetime.date(), supervisor_start_time)
                        
                        logger.info(f"Scheduling Supervisor at {supervisor_new_datetime.isoformat()}")

                        # Find Supervisor's existing schedule (if any)
                        Schedule = current_app.config['Schedule']
                        Employee = current_app.config['Employee']
                        EmployeeTimeOff = current_app.config['EmployeeTimeOff']
                        EmployeeWeeklyAvailability = current_app.config['EmployeeWeeklyAvailability']
                        
                        supervisor_schedule = Schedule.query.filter_by(
                            event_ref_num=supervisor_event.project_ref_num
                        ).first()

                        # Find Club Supervisor first, then Primary Lead fallback
                        target_date = supervisor_new_datetime.date()
                        day_of_week = target_date.weekday()
                        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        day_column = day_names[day_of_week]
                        
                        supervisor_employee = None
                        
                        # Try Club Supervisor first
                        club_supervisor = Employee.query.filter_by(
                            job_title='Club Supervisor',
                            is_active=True
                        ).first()
                        
                        if club_supervisor:
                            time_off = EmployeeTimeOff.query.filter(
                                EmployeeTimeOff.employee_id == club_supervisor.id,
                                EmployeeTimeOff.start_date <= target_date,
                                EmployeeTimeOff.end_date >= target_date
                            ).first()
                            
                            if not time_off:
                                weekly_avail = EmployeeWeeklyAvailability.query.filter_by(
                                    employee_id=club_supervisor.id
                                ).first()
                                is_available = True
                                if weekly_avail:
                                    is_available = getattr(weekly_avail, day_column, True)
                                if is_available:
                                    supervisor_employee = club_supervisor
                                    logger.info(f"Supervisor will be assigned to Club Supervisor: {club_supervisor.name}")
                        
                        # Fallback to Primary Lead for that day
                        if not supervisor_employee:
                            from app.services.rotation_manager import RotationManager
                            rotation_manager = RotationManager(db.session)
                            primary_lead = rotation_manager.get_rotation_employee(supervisor_new_datetime, 'primary_lead')
                            
                            if primary_lead:
                                time_off = EmployeeTimeOff.query.filter(
                                    EmployeeTimeOff.employee_id == primary_lead.id,
                                    EmployeeTimeOff.start_date <= target_date,
                                    EmployeeTimeOff.end_date >= target_date
                                ).first()
                                
                                if not time_off:
                                    weekly_avail = EmployeeWeeklyAvailability.query.filter_by(
                                        employee_id=primary_lead.id
                                    ).first()
                                    is_available = True
                                    if weekly_avail:
                                        is_available = getattr(weekly_avail, day_column, True)
                                    if is_available:
                                        supervisor_employee = primary_lead
                                        logger.info(f"Supervisor will be assigned to Primary Lead: {primary_lead.name}")
                        
                        if not supervisor_employee:
                            logger.warning("No Club Supervisor or Primary Lead available. Using Core employee as fallback.")
                            supervisor_employee = db.session.get(Employee, schedule.employee_id)
                        
                        if supervisor_employee:
                            supervisor_rep_id = str(supervisor_employee.external_id) if supervisor_employee.external_id else None
                            supervisor_mplan_id = str(supervisor_event.external_id) if supervisor_event.external_id else None
                            supervisor_location_id = str(supervisor_event.location_mvid) if supervisor_event.location_mvid else None
                            
                            if all([supervisor_rep_id, supervisor_mplan_id, supervisor_location_id]):
                                supervisor_estimated_minutes = supervisor_event.estimated_time or supervisor_event.get_default_duration(supervisor_event.event_type)
                                supervisor_end_datetime = supervisor_new_datetime + timedelta(minutes=supervisor_estimated_minutes)
                                
                                logger.info(f"Calling Crossmark API for Supervisor: rep_id={supervisor_rep_id}, mplan_id={supervisor_mplan_id}")
                                
                                supervisor_api_result = external_api.schedule_mplan_event(
                                    rep_id=supervisor_rep_id,
                                    mplan_id=supervisor_mplan_id,
                                    location_id=supervisor_location_id,
                                    start_datetime=supervisor_new_datetime,
                                    end_datetime=supervisor_end_datetime,
                                    planning_override=True
                                )
                                
                                if supervisor_api_result.get('success'):
                                    if supervisor_schedule:
                                        # Update existing schedule
                                        supervisor_schedule.schedule_datetime = supervisor_new_datetime
                                        supervisor_schedule.employee_id = supervisor_employee.id
                                    else:
                                        # Create new Schedule record
                                        new_supervisor_schedule = Schedule(
                                            event_ref_num=supervisor_event.project_ref_num,
                                            employee_id=supervisor_employee.id,
                                            schedule_datetime=supervisor_new_datetime
                                        )
                                        db.session.add(new_supervisor_schedule)
                                    
                                    supervisor_event.is_scheduled = True
                                    supervisor_event.condition = 'Scheduled'
                                    supervisor_event.sync_status = 'synced'
                                    supervisor_event.last_synced = datetime.utcnow()
                                    
                                    supervisor_rescheduled = True
                                    logger.info(f"✅ Supervisor {supervisor_event.project_ref_num} scheduled to {supervisor_employee.name} at {supervisor_new_datetime.isoformat()}")
                                else:
                                    logger.warning(f"Failed to schedule Supervisor: {supervisor_api_result.get('message')}")
                            else:
                                logger.warning(f"Supervisor API fields incomplete. rep_id={supervisor_rep_id}, mplan_id={supervisor_mplan_id}, location_id={supervisor_location_id}")

            # COMMIT TRANSACTION
            db.session.commit()

            # Build log message
            log_parts = [f'Schedule {schedule_id} rescheduled from {old_datetime} to {new_datetime}']
            if new_employee_id and new_employee_id != old_employee_id:
                log_parts.append(f'employee changed to {employee.name}')
            else:
                log_parts.append(f'for employee {employee.name}')
            log_parts.append(f'on event {event.project_name}')
            logger.info(' '.join(log_parts))

            # Build success message
            message = 'Event rescheduled successfully'
            if new_employee_id and new_employee_id != old_employee_id:
                message += f'. Employee changed to {employee.name}.'
            if supervisor_rescheduled:
                message += ' Supervisor event was also rescheduled.'

            return jsonify({
                'success': True,
                'message': message,
                'schedule_id': schedule_id,
                'new_datetime': new_datetime.isoformat(),
                'new_employee_id': employee.id,
                'new_employee_name': employee.name,
                'supervisor_rescheduled': supervisor_rescheduled
            }), 200

        except Exception as nested_error:
            db.session.rollback()
            logger.error(f"Transaction failed during reschedule: {str(nested_error)}", exc_info=True)
            raise nested_error

    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to reschedule event {schedule_id}: {e}', exc_info=True)
        return jsonify({
            'error': 'Failed to reschedule event',
            'details': str(e)
        }), 500


@api_bp.route('/event/<int:schedule_id>/change-employee', methods=['POST'])
@require_authentication()
def change_employee_assignment(schedule_id):
    """
    Change employee assignment for an event (Story 3.7).

    This endpoint changes the employee assigned to an event while keeping
    the same date and time. Validates against conflicts using ConstraintValidator.

    Args:
        schedule_id: Schedule ID to update (path parameter)

    Request Body:
        {
            "new_employee_id": "EMP002"
        }

    Returns:
        JSON response with success status or conflict details

    Response Format (Success):
        {
            "success": true,
            "message": "Employee changed successfully",
            "schedule_id": 123,
            "new_employee_id": "EMP002",
            "new_employee_name": "Jane Smith"
        }

    Response Format (Conflict):
        {
            "error": "Employee change would create conflicts",
            "conflicts": [...]
        }

    Status Codes:
        200: Success
        404: Schedule or employee not found
        409: Conflict - employee change blocked by constraints
        400: Invalid request data
        500: Server error
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Get request data
        data = request.get_json()
        new_employee_id = data.get('new_employee_id')
        override_conflicts = data.get('override_conflicts', False)

        # Validate required fields
        if not new_employee_id:
            return jsonify({'error': 'Missing required field: new_employee_id'}), 400

        # Get the schedule
        schedule = Schedule.query.get(schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get related event
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Get new employee
        new_employee = Employee.query.get(new_employee_id)
        if not new_employee:
            return jsonify({'error': f'Employee not found: {new_employee_id}'}), 404

        # Use existing schedule datetime
        schedule_datetime = schedule.schedule_datetime

        # Validate using ConstraintValidator
        from app.services.constraint_validator import ConstraintValidator

        models = {
            'Employee': Employee,
            'Event': Event,
            'Schedule': Schedule,
            'EmployeeTimeOff': current_app.config.get('EmployeeTimeOff'),
            'EmployeeAvailability': current_app.config.get('EmployeeAvailability'),
            'EmployeeWeeklyAvailability': current_app.config.get('EmployeeWeeklyAvailability'),
            'PendingSchedule': current_app.config.get('PendingSchedule')
        }

        validator = ConstraintValidator(db.session, models)
        validation_result = validator.validate_assignment(event, new_employee, schedule_datetime)

        # Check for conflicts (only block if override is not set)
        if not validation_result.is_valid and not override_conflicts:
            conflicts = []
            for violation in validation_result.violations:
                conflicts.append({
                    'type': violation.constraint_type.value if hasattr(violation.constraint_type, 'value') else str(violation.constraint_type),
                    'message': violation.message,
                    'severity': violation.severity.value if hasattr(violation.severity, 'value') else str(violation.severity),
                    'details': violation.details
                })

            return jsonify({
                'error': 'Employee change would create conflicts',
                'conflicts': conflicts,
                'can_override': True
            }), 409

        # No conflicts (or overridden) - submit to external API BEFORE updating local database
        from app.integrations.external_api.session_api_service import session_api as external_api
        from datetime import timedelta

        # Calculate end datetime
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = schedule_datetime + timedelta(minutes=estimated_minutes)

        # Prepare API data
        rep_id = str(new_employee.external_id) if new_employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        # Validate required API fields
        if not rep_id:
            return jsonify({'error': f'Missing Crossmark employee ID for {new_employee.name}'}), 400

        if not mplan_id:
            return jsonify({'error': 'Missing Crossmark event ID'}), 400

        if not location_id:
            return jsonify({'error': 'Missing Crossmark location ID'}), 400

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Submit to external API
        try:
            logger.info(
                f"Submitting employee change to Crossmark API: "
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
                logger.error(f"Crossmark API error: {error_message}")
                return jsonify({'error': f'Failed to submit to Crossmark: {error_message}'}), 500

            logger.info(f"Successfully submitted employee change to Crossmark API")

        except Exception as api_error:
            logger.error(f"API submission error: {str(api_error)}")
            return jsonify({'error': f'Failed to submit to Crossmark API: {str(api_error)}'}), 500

        # API submission successful - now update local database
        old_employee_id = schedule.employee_id
        old_employee = Employee.query.get(old_employee_id)
        schedule.employee_id = new_employee_id

        # Update event sync status
        event.sync_status = 'synced'
        event.last_synced = datetime.utcnow()

        db.session.commit()

        # Log if conflicts were overridden
        if not validation_result.is_valid and override_conflicts:
            logger.warning(
                f'Schedule {schedule_id} employee changed with conflict override: '
                f'{len(validation_result.violations)} conflict(s) ignored'
            )
        else:
            logger.info(
                f'Schedule {schedule_id} employee changed from {old_employee_id} to {new_employee_id} '
                f'for event {event.project_name} at {schedule_datetime}'
            )

        return jsonify({
            'success': True,
            'message': 'Employee changed successfully',
            'schedule_id': schedule_id,
            'new_employee_id': new_employee_id,
            'new_employee_name': new_employee.name,
            'old_employee_name': old_employee.name if old_employee else None
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to change employee for schedule {schedule_id}: {e}', exc_info=True)
        return jsonify({
            'error': 'Failed to change employee',
            'details': str(e)
        }), 500


@api_bp.route('/reschedule_event', methods=['POST'])
def reschedule_event():
    """
    DEPRECATED: This endpoint is deprecated and redirects to /api/reschedule

    This endpoint lacked CORE-Supervisor pairing logic and has been replaced by /api/reschedule.
    It now serves as a compatibility layer that transforms old-style parameters to new-style
    and forwards to the correct endpoint.
    """
    try:
        # Get data from request
        data = request.get_json()

        # Transform old parameter names to new ones
        transformed_data = {
            'schedule_id': data.get('schedule_id'),
            'new_date': data.get('date'),  # OLD: 'date' -> NEW: 'new_date'
            'new_time': data.get('time'),  # OLD: 'time' -> NEW: 'new_time'
            'employee_id': data.get('employee_id')
        }

        # Log deprecation warning
        current_app.logger.warning(
            f"DEPRECATED ENDPOINT USED: /api/reschedule_event is deprecated. "
            f"Please update to use /api/reschedule with parameters 'new_date' and 'new_time'. "
            f"Forwarding request to /api/reschedule."
        )

        # Forward to the correct endpoint
        from flask import Flask
        with current_app.test_request_context(
            '/api/reschedule',
            method='POST',
            json=transformed_data
        ):
            return reschedule()

    except Exception as e:
        return jsonify({'error': f'Error in deprecated endpoint: {str(e)}'}), 500


@api_bp.route('/unschedule/<int:schedule_id>', methods=['DELETE'])
def unschedule_event(schedule_id):
    """Unschedule an event - calls Crossmark API first, then deletes schedule and marks event as unscheduled"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']

    try:
        # Get the schedule
        schedule = db.session.get(Schedule, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get the related event
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            return jsonify({'error': 'Related event not found'}), 404

        # Call Crossmark API BEFORE deleting local record
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            current_app.logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # BEGIN NESTED TRANSACTION for CORE-Supervisor pairing (Calendar Redesign - Sprint 2)
        try:
            with db.session.begin_nested():
                # Call API to delete/unschedule the CORE event
                if schedule.external_id:
                    try:
                        current_app.logger.info(
                            f"Submitting unschedule to Crossmark API: schedule_id={schedule.external_id}"
                        )

                        api_result = external_api.unschedule_mplan_event(str(schedule.external_id))

                        if not api_result.get('success'):
                            error_message = api_result.get('message', 'Unknown API error')
                            current_app.logger.error(f"Crossmark API error: {error_message}")
                            raise Exception(f'Failed to unschedule in Crossmark: {error_message}')

                        current_app.logger.info(f"Successfully unscheduled event in Crossmark API")

                    except Exception as api_error:
                        current_app.logger.error(f"API submission error: {str(api_error)}")
                        raise Exception(f'Failed to submit to Crossmark API: {str(api_error)}')

                # NEW: Check if this is a CORE event and unschedule Supervisor (Calendar Redesign - Sprint 2)
                from app.utils.event_helpers import is_core_event_redesign, get_supervisor_status

                if is_core_event_redesign(event):
                    current_app.logger.info(f"CORE event detected: {event.project_name}. Checking for paired Supervisor...")

                    supervisor_status = get_supervisor_status(event)

                    if supervisor_status['exists'] and supervisor_status['is_scheduled']:
                        supervisor_event = supervisor_status['event']
                        current_app.logger.info(
                            f"Found paired Supervisor: {supervisor_event.project_name} (ID: {supervisor_event.project_ref_num})"
                        )

                        # Find Supervisor's schedule
                        supervisor_schedule = Schedule.query.filter_by(
                            event_ref_num=supervisor_event.project_ref_num
                        ).first()

                        if supervisor_schedule:
                            # Call Crossmark API to unschedule Supervisor
                            if supervisor_schedule.external_id:
                                current_app.logger.info(
                                    f"Calling Crossmark API to unschedule Supervisor: schedule_id={supervisor_schedule.external_id}"
                                )

                                supervisor_api_result = external_api.unschedule_mplan_event(str(supervisor_schedule.external_id))

                                if not supervisor_api_result.get('success'):
                                    error_msg = supervisor_api_result.get('message', 'Unknown API error')
                                    current_app.logger.error(f"Supervisor unschedule API call failed: {error_msg}")
                                    raise Exception(f"Failed to unschedule Supervisor in Crossmark: {error_msg}")

                                current_app.logger.info(f"Successfully unscheduled Supervisor in Crossmark API")

                            # Delete Supervisor schedule record
                            db.session.delete(supervisor_schedule)

                            # Check if Supervisor has other schedules
                            remaining_supervisor_schedules = Schedule.query.filter_by(
                                event_ref_num=supervisor_event.project_ref_num
                            ).count()
                            if remaining_supervisor_schedules == 0:
                                supervisor_event.is_scheduled = False

                            # Update Supervisor event sync status
                            supervisor_event.sync_status = 'synced'
                            supervisor_event.last_synced = datetime.utcnow()

                            current_app.logger.info(
                                f"✅ Successfully auto-unscheduled Supervisor event {supervisor_event.project_ref_num}"
                            )
                        else:
                            current_app.logger.warning(f"Supervisor schedule not found for event {supervisor_event.project_ref_num}")
                    elif supervisor_status['exists']:
                        current_app.logger.info(
                            f"Supervisor event exists but is not scheduled (condition: {supervisor_status['condition']}). "
                            f"No auto-unschedule needed."
                        )
                    else:
                        current_app.logger.info("No paired Supervisor event found for this CORE event.")

                # Delete CORE event schedule record
                db.session.delete(schedule)

                # Check if this was the only schedule for the CORE event
                remaining_schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).count()
                if remaining_schedules == 0:
                    event.is_scheduled = False

                # Update CORE event sync status
                event.sync_status = 'synced'
                event.last_synced = datetime.utcnow()

            # COMMIT TRANSACTION
            db.session.commit()

            return jsonify({'success': True, 'message': 'Event unscheduled successfully. Event moved back to unscheduled status.'})

        except Exception as nested_error:
            db.session.rollback()
            current_app.logger.error(f"Transaction failed during unschedule: {str(nested_error)}", exc_info=True)
            raise nested_error

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/unschedule_event/<int:event_id>', methods=['POST'])
@require_authentication()
def unschedule_event_by_id(event_id):
    """
    Unschedule all schedules for an event by event ID.

    This is a convenience endpoint for the events list page where we have the event_id
    but not the schedule_id. It will unschedule all schedule assignments for this event.

    Args:
        event_id: Event ID (from events.id, not project_ref_num)

    Returns:
        JSON response with success status
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']

    try:
        # Get the event
        event = db.session.get(Event, event_id)
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Get all schedules for this event (using project_ref_num)
        schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).all()

        if not schedules:
            return jsonify({'error': 'No schedules found for this event'}), 404

        # Call Crossmark API BEFORE deleting local records
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                current_app.logger.warning(f'Failed to authenticate with Crossmark API for event {event_id}')
        except Exception as auth_error:
            current_app.logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Unschedule each schedule
        for schedule in schedules:
            # Call API to delete/unschedule if external_id exists
            if schedule.external_id:
                try:
                    current_app.logger.info(f"Submitting unschedule to Crossmark API: schedule_id={schedule.external_id}")
                    api_result = external_api.unschedule_mplan_event(str(schedule.external_id))

                    if not api_result.get('success'):
                        error_message = api_result.get('message', 'Unknown API error')
                        current_app.logger.error(f"Crossmark API error: {error_message}")
                        return jsonify({
                            'error': 'Failed to unschedule in Crossmark',
                            'details': error_message
                        }), 500

                    current_app.logger.info(f"Successfully unscheduled schedule {schedule.external_id} in Crossmark API")

                except Exception as api_error:
                    current_app.logger.error(f"API submission error: {str(api_error)}")
                    return jsonify({
                        'error': 'Failed to submit to Crossmark API',
                        'details': str(api_error)
                    }), 500

            # Delete the schedule
            db.session.delete(schedule)

        # NEW: Check if this is a CORE event and unschedule Supervisor (Sprint 2)
        from app.utils.event_helpers import is_core_event_redesign, get_supervisor_status

        supervisor_unscheduled = False
        if is_core_event_redesign(event):
            current_app.logger.info(f"CORE event detected: {event.project_name}. Checking for paired Supervisor...")

            supervisor_status = get_supervisor_status(event)

            if supervisor_status['exists'] and supervisor_status['is_scheduled']:
                supervisor_event = supervisor_status['event']
                current_app.logger.info(
                    f"Found paired Supervisor: {supervisor_event.project_name} (ID: {supervisor_event.project_ref_num})"
                )

                # Find Supervisor's schedule
                supervisor_schedule = Schedule.query.filter_by(
                    event_ref_num=supervisor_event.project_ref_num
                ).first()

                if supervisor_schedule:
                    # Call Crossmark API to unschedule Supervisor
                    if supervisor_schedule.external_id:
                        current_app.logger.info(
                            f"Calling Crossmark API to unschedule Supervisor: schedule_id={supervisor_schedule.external_id}"
                        )

                        supervisor_api_result = external_api.unschedule_mplan_event(str(supervisor_schedule.external_id))

                        if not supervisor_api_result.get('success'):
                            error_msg = supervisor_api_result.get('message', 'Unknown API error')
                            current_app.logger.error(f"Supervisor unschedule API call failed: {error_msg}")
                            # Don't fail the whole operation, just log and continue
                        else:
                            current_app.logger.info(f"Successfully unscheduled Supervisor in Crossmark API")

                    # Delete Supervisor schedule record
                    db.session.delete(supervisor_schedule)

                    # Mark Supervisor as unscheduled
                    supervisor_event.is_scheduled = False
                    supervisor_unscheduled = True

                    current_app.logger.info(
                        f"✅ Successfully auto-unscheduled Supervisor event {supervisor_event.project_ref_num}"
                    )

        # Mark event as unscheduled
        event.is_scheduled = False
        event.condition = 'Unstaffed'

        db.session.commit()

        message = f'Event unscheduled successfully. Removed {len(schedules)} schedule(s).'
        if supervisor_unscheduled:
            message += ' Supervisor event was also unscheduled.'

        return jsonify({
            'success': True,
            'message': message,
            'schedules_removed': len(schedules),
            'supervisor_unscheduled': supervisor_unscheduled
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error unscheduling event {event_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/trade-events', methods=['POST'])
@require_authentication()
def trade_events():
    """
    Swap employee assignments between two events (Story 3.8 & 3.9).

    This endpoint swaps the employee assignments between two scheduled events.
    Works for same-day or cross-day trades. Validates both assignments for
    conflicts before performing the atomic swap.

    Request Body:
        {
            "schedule_1_id": 123,  # First schedule ID
            "schedule_2_id": 456   # Second schedule ID
        }

    Returns:
        JSON response with success status

    Response Format (Success):
        {
            "success": true,
            "message": "Events traded successfully"
        }

    Response Format (Conflict):
        {
            "error": "Trade would create conflicts",
            "conflicts": [...]
        }

    Status Codes:
        200: Success - events traded
        400: Invalid request
        404: Schedule not found
        409: Conflict - trade would create conflicts
        500: Server error

    Note:
        - This endpoint handles BOTH same-day and cross-day trades
        - No date parameters needed - uses schedule_datetime from each Schedule
        - Validates conflicts for both employees at their respective dates/times
        - Performs atomic swap in single database transaction
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Get request data
        data = request.get_json()
        schedule_1_id = data.get('schedule_1_id')
        schedule_2_id = data.get('schedule_2_id')

        # Validate required fields
        if not schedule_1_id or not schedule_2_id:
            return jsonify({'error': 'Missing required fields: schedule_1_id and schedule_2_id'}), 400

        # Get both schedules
        schedule1 = Schedule.query.get(schedule_1_id)
        schedule2 = Schedule.query.get(schedule_2_id)

        if not schedule1 or not schedule2:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get related events
        event1 = Event.query.filter_by(project_ref_num=schedule1.event_ref_num).first()
        event2 = Event.query.filter_by(project_ref_num=schedule2.event_ref_num).first()

        if not event1 or not event2:
            return jsonify({'error': 'Event not found'}), 404

        # Validate that both events are Core events (only Core events can be traded)
        if event1.event_type != 'Core' or event2.event_type != 'Core':
            return jsonify({
                'error': 'Only Core events can be traded',
                'event1_type': event1.event_type,
                'event2_type': event2.event_type
            }), 400

        # Get employees
        employee1 = Employee.query.get(schedule1.employee_id)
        employee2 = Employee.query.get(schedule2.employee_id)

        if not employee1 or not employee2:
            return jsonify({'error': 'Employee not found'}), 404

        # Validate using ConstraintValidator
        # Check if employee2 can work event1's time, and employee1 can work event2's time
        from app.services.constraint_validator import ConstraintValidator

        models = {
            'Employee': Employee,
            'Event': Event,
            'Schedule': Schedule,
            'EmployeeTimeOff': current_app.config.get('EmployeeTimeOff'),
            'EmployeeAvailability': current_app.config.get('EmployeeAvailability'),
            'EmployeeWeeklyAvailability': current_app.config.get('EmployeeWeeklyAvailability'),
            'PendingSchedule': current_app.config.get('PendingSchedule')
        }

        validator = ConstraintValidator(db.session, models)

        # Validate employee2 -> event1's time (exclude both schedules being traded)
        validation1 = validator.validate_assignment(
            event1,
            employee2,
            schedule1.schedule_datetime,
            exclude_schedule_ids=[schedule_1_id, schedule_2_id]
        )

        # Validate employee1 -> event2's time (exclude both schedules being traded)
        validation2 = validator.validate_assignment(
            event2,
            employee1,
            schedule2.schedule_datetime,
            exclude_schedule_ids=[schedule_1_id, schedule_2_id]
        )

        # Collect all conflicts
        all_conflicts = []

        if not validation1.is_valid:
            for violation in validation1.violations:
                all_conflicts.append({
                    'type': violation.constraint_type.value if hasattr(violation.constraint_type, 'value') else str(violation.constraint_type),
                    'message': f'{employee2.name} -> Event 1: {violation.message}',
                    'severity': violation.severity.value if hasattr(violation.severity, 'value') else str(violation.severity),
                    'details': violation.details
                })

        if not validation2.is_valid:
            for violation in validation2.violations:
                all_conflicts.append({
                    'type': violation.constraint_type.value if hasattr(violation.constraint_type, 'value') else str(violation.constraint_type),
                    'message': f'{employee1.name} -> Event 2: {violation.message}',
                    'severity': violation.severity.value if hasattr(violation.severity, 'value') else str(violation.severity),
                    'details': violation.details
                })

        # If any conflicts, return 409
        if all_conflicts:
            return jsonify({
                'error': 'Trade would create conflicts',
                'conflicts': all_conflicts
            }), 409

        # No conflicts - submit to external API BEFORE performing swap
        from app.integrations.external_api.session_api_service import session_api as external_api
        from datetime import timedelta

        # Calculate end datetimes for both events
        estimated_minutes1 = event1.estimated_time or event1.get_default_duration(event1.event_type)
        estimated_minutes2 = event2.estimated_time or event2.get_default_duration(event2.event_type)
        end_datetime1 = schedule1.schedule_datetime + timedelta(minutes=estimated_minutes1)
        end_datetime2 = schedule2.schedule_datetime + timedelta(minutes=estimated_minutes2)

        # Prepare API data for both swaps
        # Employee2 takes over Event1
        rep2_id = str(employee2.external_id) if employee2.external_id else None
        mplan1_id = str(event1.external_id) if event1.external_id else None
        location1_id = str(event1.location_mvid) if event1.location_mvid else None

        # Employee1 takes over Event2
        rep1_id = str(employee1.external_id) if employee1.external_id else None
        mplan2_id = str(event2.external_id) if event2.external_id else None
        location2_id = str(event2.location_mvid) if event2.location_mvid else None

        # Validate required API fields for first swap
        if not rep2_id:
            return jsonify({'error': f'Missing Crossmark employee ID for {employee2.name}'}), 400
        if not mplan1_id:
            return jsonify({'error': f'Missing Crossmark event ID for {event1.project_name}'}), 400
        if not location1_id:
            return jsonify({'error': f'Missing Crossmark location ID for {event1.project_name}'}), 400

        # Validate required API fields for second swap
        if not rep1_id:
            return jsonify({'error': f'Missing Crossmark employee ID for {employee1.name}'}), 400
        if not mplan2_id:
            return jsonify({'error': f'Missing Crossmark event ID for {event2.project_name}'}), 400
        if not location2_id:
            return jsonify({'error': f'Missing Crossmark location ID for {event2.project_name}'}), 400

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Submit both swaps to external API
        try:
            # First swap: Employee2 -> Event1
            logger.info(
                f"Submitting trade swap 1 to Crossmark API: {employee2.name} -> {event1.project_name} "
                f"(rep_id={rep2_id}, mplan_id={mplan1_id}, location_id={location1_id})"
            )

            api_result1 = external_api.schedule_mplan_event(
                rep_id=rep2_id,
                mplan_id=mplan1_id,
                location_id=location1_id,
                start_datetime=schedule1.schedule_datetime,
                end_datetime=end_datetime1,
                planning_override=True
            )

            if not api_result1.get('success'):
                error_message = api_result1.get('message', 'Unknown API error')
                logger.error(f"Crossmark API error (swap 1): {error_message}")
                return jsonify({'error': f'Failed to submit swap 1 to Crossmark: {error_message}'}), 500

            # Second swap: Employee1 -> Event2
            logger.info(
                f"Submitting trade swap 2 to Crossmark API: {employee1.name} -> {event2.project_name} "
                f"(rep_id={rep1_id}, mplan_id={mplan2_id}, location_id={location2_id})"
            )

            api_result2 = external_api.schedule_mplan_event(
                rep_id=rep1_id,
                mplan_id=mplan2_id,
                location_id=location2_id,
                start_datetime=schedule2.schedule_datetime,
                end_datetime=end_datetime2,
                planning_override=True
            )

            if not api_result2.get('success'):
                error_message = api_result2.get('message', 'Unknown API error')
                logger.error(f"Crossmark API error (swap 2): {error_message}")
                return jsonify({'error': f'Failed to submit swap 2 to Crossmark: {error_message}'}), 500

            logger.info(f"Successfully submitted both trade swaps to Crossmark API")

        except Exception as api_error:
            logger.error(f"API submission error during trade: {str(api_error)}")
            return jsonify({'error': f'Failed to submit to Crossmark API: {str(api_error)}'}), 500

        # API submission successful - now perform atomic swap in local database
        original_emp1_id = schedule1.employee_id
        original_emp2_id = schedule2.employee_id

        schedule1.employee_id = original_emp2_id
        schedule2.employee_id = original_emp1_id

        # Update event sync status for both events
        event1.sync_status = 'synced'
        event1.last_synced = datetime.utcnow()
        event2.sync_status = 'synced'
        event2.last_synced = datetime.utcnow()

        db.session.commit()

        logger.info(
            f'Events traded successfully: Schedule {schedule_1_id} ({event1.project_name}) '
            f'now has {employee2.name}, Schedule {schedule_2_id} ({event2.project_name}) '
            f'now has {employee1.name}'
        )

        return jsonify({
            'success': True,
            'message': 'Events traded successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to trade events: {e}', exc_info=True)
        return jsonify({
            'error': 'Failed to trade events',
            'details': str(e)
        }), 500


# Legacy endpoint for backward compatibility
@api_bp.route('/trade_events', methods=['POST'])
def trade_events_legacy():
    """Legacy trade events endpoint - redirects to new endpoint"""
    data = request.get_json()

    # Transform legacy parameters to new format
    new_data = {
        'schedule_1_id': data.get('schedule_id'),
        'schedule_2_id': data.get('trade_with_schedule_id')
    }

    # Make internal request to new endpoint
    request._cached_json = (new_data, new_data)
    return trade_events()


@api_bp.route('/bulk-reassign-supervisor-events', methods=['POST'])
@require_authentication()
def bulk_reassign_supervisor_events():
    """
    Bulk reassign all Supervisor, Freeosk, Digitals events for a specific date to a different employee.

    This endpoint finds all supervisor-level events (Supervisor, Freeosk, Digitals, etc.) for a given date
    and reassigns them to a different Lead or Supervisor by calling the external API's scheduleMplan
    for each event with the new employee's repID.

    Request Body:
        {
            "date": "2025-01-15",  # Date in YYYY-MM-DD format
            "new_employee_id": 5   # ID of the employee to reassign events to
        }

    Returns:
        JSON response with success status and details of reassigned events

    Response Format (Success):
        {
            "success": true,
            "message": "Successfully reassigned X supervisor events",
            "reassigned_count": X,
            "details": [...]
        }

    Response Format (Error):
        {
            "error": "Error message",
            "details": "..."
        }

    Status Codes:
        200: Success - events reassigned
        400: Invalid request or employee cannot work supervisor events
        404: No supervisor events found or employee not found
        500: Server error
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Get request data
        data = request.get_json()
        target_date_str = data.get('date')
        new_employee_id = data.get('new_employee_id')

        # Validate required fields with specific error messages
        missing_fields = []
        if not target_date_str:
            missing_fields.append('date')
        if not new_employee_id:  # Handles None, empty string, etc.
            missing_fields.append('new_employee_id')

        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        # Parse date
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Get the new employee
        new_employee = db.session.get(Employee, new_employee_id)
        if not new_employee:
            return jsonify({'error': 'Employee not found'}), 404

        # Validate that the new employee can work supervisor events
        # Supervisor events can only be worked by Club Supervisors or Lead Event Specialists
        if new_employee.job_title not in ['Club Supervisor', 'Lead Event Specialist']:
            return jsonify({
                'error': f'Employee {new_employee.name} cannot work supervisor events. Only Club Supervisors and Lead Event Specialists can work these events.',
                'employee_job_title': new_employee.job_title
            }), 400

        # Define supervisor event types
        supervisor_event_types = ['Supervisor', 'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh', 'Digital Teardown', 'Other']

        # Find all supervisor events scheduled for the target date
        supervisor_schedules = db.session.query(Schedule).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            db.func.date(Schedule.schedule_datetime) == target_date,
            Event.event_type.in_(supervisor_event_types)
        ).all()

        if not supervisor_schedules:
            return jsonify({
                'error': 'No supervisor events found for this date',
                'date': target_date_str
            }), 404

        # Initialize external API
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Process each supervisor event
        reassigned_events = []
        failed_events = []

        for schedule in supervisor_schedules:
            # Get the event details
            event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
            if not event:
                failed_events.append({
                    'schedule_id': schedule.id,
                    'error': 'Event not found'
                })
                continue

            # Get the new employee's external ID
            rep_id = str(new_employee.external_id) if new_employee.external_id else None
            mplan_id = str(event.external_id) if event.external_id else None
            location_id = str(event.location_mvid) if event.location_mvid else None

            # Validate required API fields
            if not rep_id:
                failed_events.append({
                    'schedule_id': schedule.id,
                    'event_name': event.project_name,
                    'error': f'Missing Crossmark employee ID for {new_employee.name}'
                })
                continue

            if not mplan_id:
                failed_events.append({
                    'schedule_id': schedule.id,
                    'event_name': event.project_name,
                    'error': f'Missing Crossmark event ID'
                })
                continue

            if not location_id:
                failed_events.append({
                    'schedule_id': schedule.id,
                    'event_name': event.project_name,
                    'error': f'Missing Crossmark location ID'
                })
                continue

            # Calculate end datetime
            estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
            end_datetime = schedule.schedule_datetime + timedelta(minutes=estimated_minutes)

            # Call external API to schedule the event with the new employee
            try:
                logger.info(
                    f"Reassigning {event.project_name} (schedule_id={schedule.id}) to {new_employee.name} "
                    f"on {schedule.schedule_datetime.strftime('%Y-%m-%d %H:%M')}"
                )

                api_result = external_api.schedule_mplan_event(
                    rep_id=rep_id,
                    mplan_id=mplan_id,
                    location_id=location_id,
                    start_datetime=schedule.schedule_datetime,
                    end_datetime=end_datetime,
                    planning_override=True
                )

                if not api_result.get('success'):
                    error_message = api_result.get('message', 'Unknown API error')
                    logger.error(f"Crossmark API error for schedule {schedule.id}: {error_message}")
                    failed_events.append({
                        'schedule_id': schedule.id,
                        'event_name': event.project_name,
                        'old_employee': schedule.employee.name if schedule.employee else 'Unknown',
                        'error': f'API error: {error_message}'
                    })
                    continue

                # Update local database with new employee assignment
                old_employee_name = schedule.employee.name if schedule.employee else 'Unknown'
                schedule.employee_id = new_employee_id

                # Update sync status
                event.sync_status = 'synced'
                event.last_synced = datetime.utcnow()

                reassigned_events.append({
                    'schedule_id': schedule.id,
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'datetime': schedule.schedule_datetime.strftime('%Y-%m-%d %H:%M'),
                    'old_employee': old_employee_name,
                    'new_employee': new_employee.name
                })

                logger.info(f"Successfully reassigned schedule {schedule.id} from {old_employee_name} to {new_employee.name}")

            except Exception as api_error:
                logger.error(f"API submission error for schedule {schedule.id}: {str(api_error)}")
                failed_events.append({
                    'schedule_id': schedule.id,
                    'event_name': event.project_name,
                    'error': f'Exception: {str(api_error)}'
                })

        # Commit all database changes
        db.session.commit()

        # Prepare response
        response_data = {
            'success': len(reassigned_events) > 0,
            'message': f'Successfully reassigned {len(reassigned_events)} supervisor event(s)',
            'reassigned_count': len(reassigned_events),
            'failed_count': len(failed_events),
            'reassigned_events': reassigned_events
        }

        if failed_events:
            response_data['failed_events'] = failed_events
            response_data['message'] += f', {len(failed_events)} failed'

        status_code = 200 if len(reassigned_events) > 0 else 500
        return jsonify(response_data), status_code

    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to bulk reassign supervisor events: {e}', exc_info=True)
        return jsonify({
            'error': 'Failed to bulk reassign supervisor events',
            'details': str(e)
        }), 500


@api_bp.route('/change_employee', methods=['POST'])
def change_employee():
    """Change the employee for an event (keeping same date and time)"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        data = request.get_json()
        schedule_id = data.get('schedule_id')
        new_employee_id = data.get('employee_id')

        # Get the schedule
        schedule = db.session.get(Schedule, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get the event to check type for validation
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Check if new employee can work this event type
        new_employee = db.session.get(Employee, new_employee_id)
        if not new_employee or not new_employee.can_work_event_type(event.event_type):
            if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
                return jsonify({'error': 'Employee cannot work Juicer events. Only Club Supervisors and Juicer Baristas can work Juicer events.'}), 400
            elif event.event_type in ['Supervisor', 'Freeosk', 'Digitals']:
                return jsonify({'error': f'Employee cannot work {event.event_type} events. Only Club Supervisors and Lead Event Specialists can work this type of event.'}), 400
            else:
                return jsonify({'error': 'Employee cannot work this event type'}), 400

        # For Core events, check if new employee already has a Core event that day
        if event.event_type == 'Core':
            event_date = schedule.schedule_datetime.date()
            existing_core = Schedule.query.join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == new_employee_id,
                db.func.date(Schedule.schedule_datetime) == event_date,
                Event.event_type == 'Core',
                Schedule.id != schedule_id
            ).first()

            if existing_core:
                return jsonify({'error': 'Employee already has a Core event scheduled that day'}), 400

        # Submit to Crossmark API BEFORE updating local record
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Calculate end datetime
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = schedule.schedule_datetime + timedelta(minutes=estimated_minutes)

        # Prepare API data
        rep_id = str(new_employee.external_id) if new_employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        # Validate required API fields
        if not rep_id:
            return jsonify({'error': f'Missing Crossmark employee ID for {new_employee.name}'}), 400

        if not mplan_id:
            return jsonify({'error': 'Missing Crossmark event ID'}), 400

        if not location_id:
            return jsonify({'error': 'Missing Crossmark location ID'}), 400

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            current_app.logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'error': 'Failed to authenticate with Crossmark API'}), 500

        # Submit to external API
        try:
            current_app.logger.info(
                f"Submitting employee change to Crossmark API: "
                f"rep_id={rep_id}, mplan_id={mplan_id}, location_id={location_id}, "
                f"start={schedule.schedule_datetime.isoformat()}, end={end_datetime.isoformat()}"
            )

            api_result = external_api.schedule_mplan_event(
                rep_id=rep_id,
                mplan_id=mplan_id,
                location_id=location_id,
                start_datetime=schedule.schedule_datetime,
                end_datetime=end_datetime,
                planning_override=True
            )

            if not api_result.get('success'):
                error_message = api_result.get('message', 'Unknown API error')
                current_app.logger.error(f"Crossmark API error: {error_message}")
                return jsonify({'error': f'Failed to submit to Crossmark: {error_message}'}), 500

            current_app.logger.info(f"Successfully submitted employee change to Crossmark API")

        except Exception as api_error:
            current_app.logger.error(f"API submission error: {str(api_error)}")
            return jsonify({'error': f'Failed to submit to Crossmark API: {str(api_error)}'}), 500

        # API submission successful - now update local record
        schedule.employee_id = new_employee_id

        # Update event sync status
        event.sync_status = 'synced'
        event.last_synced = datetime.utcnow()

        db.session.commit()

        return jsonify({'success': True, 'message': 'Employee changed successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/export/schedule')
def export_schedule():
    """Export scheduled events to CalendarSchedule.csv (from today forward only)"""
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Check if only valid events should be exported
        valid_only = request.args.get('valid_only') == 'true'

        # Get current date to filter out past events
        today = date.today()

        # Query scheduled events with JOIN, filtering for current day and future
        scheduled_events = db.session.query(
            Event.project_name,
            Event.project_ref_num,
            Event.location_mvid,
            Event.store_number,
            Event.store_name,
            Event.start_datetime,
            Event.due_datetime,
            Event.estimated_time,
            Employee.name.label('rep_name'),
            Employee.id.label('employee_id'),
            Schedule.schedule_datetime
        ).join(
            Schedule, Event.project_ref_num == Schedule.event_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            db.func.date(Schedule.schedule_datetime) >= today
        ).order_by(Schedule.schedule_datetime).all()

        # Validate each event's schedule date is within its start/due date range
        valid_events = []
        invalid_events = []

        for event in scheduled_events:
            schedule_date = event.schedule_datetime.date()
            start_date = event.start_datetime.date()
            due_date = event.due_datetime.date()

            # Check if scheduled date is within the event's valid date range
            if start_date <= schedule_date <= due_date:
                valid_events.append(event)
            else:
                invalid_events.append({
                    'project_name': event.project_name,
                    'project_ref_num': event.project_ref_num,
                    'scheduled_date': schedule_date,
                    'start_date': start_date,
                    'due_date': due_date,
                    'employee': event.rep_name
                })

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write headers in correct order
        writer.writerow([
            'Project Name', 'Project Reference Number', 'Location MVID',
            'Store Number', 'Store Name', 'Start Date/Time', 'Due Date/Time',
            'Estimated Time', 'Rep Name', 'Employee ID', 'Schedule Date/Time'
        ])

        # Add validation summary comment rows if there are invalid events (unless valid_only is true)
        if invalid_events and not valid_only:
            writer.writerow([])  # Empty row
            writer.writerow(['# VALIDATION WARNINGS - The following events were EXCLUDED due to invalid schedule dates:'])
            writer.writerow(['# Project Name', 'Project Ref', 'Scheduled Date', 'Valid Range Start', 'Valid Range End', 'Assigned Employee'])
            for invalid in invalid_events:
                writer.writerow([
                    f"# {invalid['project_name'][:50]}...",
                    f"# {invalid['project_ref_num']}",
                    f"# {invalid['scheduled_date']}",
                    f"# {invalid['start_date']}",
                    f"# {invalid['due_date']}",
                    f"# {invalid['employee']}"
                ])
            writer.writerow(['# END VALIDATION WARNINGS'])
            writer.writerow([])  # Empty row

        # Write only valid data rows
        for event in valid_events:
            writer.writerow([
                event.project_name,
                event.project_ref_num,
                event.location_mvid or '',
                event.store_number or '',
                event.store_name or '',
                event.start_datetime.strftime('%m/%d/%Y %I:%M:%S %p'),
                event.due_datetime.strftime('%m/%d/%Y %I:%M:%S %p'),
                event.estimated_time or '',
                event.rep_name,
                event.employee_id,
                event.schedule_datetime.strftime('%m/%d/%Y %I:%M:%S %p')
            ])

        # Prepare response
        output.seek(0)
        csv_data = output.getvalue()
        output.close()

        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=CalendarSchedule.csv'

        return response

    except Exception as e:
        return jsonify({'error': f'Error generating export: {str(e)}'}), 500


@api_bp.route('/import/events', methods=['POST'])
def import_events():
    """Import unscheduled events from WorkBankVisits.csv file"""
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Check if file is provided
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate file extension
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'File must be a CSV file'}), 400

        # Read and parse CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)

        # Validate CSV headers
        expected_headers = {
            'Project Name', 'Project Reference Number', 'Location MVID',
            'Store Number', 'Store Name', 'Start Date/Time', 'Due Date/Time',
            'Estimated Time', 'Employee ID', 'Rep Name'
        }

        csv_headers = set(csv_reader.fieldnames)
        missing_headers = expected_headers - csv_headers
        if missing_headers:
            return jsonify({'error': f'Missing required CSV headers: {", ".join(missing_headers)}'}), 400

        imported_count = 0
        employees_added = set()

        # Begin database transaction
        try:
            for row in csv_reader:
                # First, ensure employee exists
                employee_id = row['Employee ID'].strip() if row['Employee ID'] else ''
                rep_name = row['Rep Name'].strip() if row['Rep Name'] else ''

                if employee_id and rep_name and employee_id not in employees_added:
                    existing_employee = Employee.query.filter_by(id=employee_id).first()
                    if not existing_employee:
                        new_employee = Employee(id=employee_id, name=rep_name)
                        db.session.add(new_employee)
                        employees_added.add(employee_id)

                # Parse and validate event data
                project_ref_num = int(row['Project Reference Number'])

                # Check for duplicate
                existing_event = Event.query.filter_by(project_ref_num=project_ref_num).first()
                if existing_event:
                    continue  # Skip duplicates

                # Parse dates with correct format for MM/DD/YYYY HH:MM:SS AM/PM
                start_datetime = datetime.strptime(row['Start Date/Time'], '%m/%d/%Y %I:%M:%S %p')
                due_datetime = datetime.strptime(row['Due Date/Time'], '%m/%d/%Y %I:%M:%S %p')

                # Create new event
                new_event = Event(
                    project_name=row['Project Name'].strip() if row['Project Name'] else '',
                    project_ref_num=project_ref_num,
                    location_mvid=row['Location MVID'].strip() if row['Location MVID'] else None,
                    store_number=int(row['Store Number']) if row['Store Number'] else None,
                    store_name=row['Store Name'].strip() if row['Store Name'] else None,
                    start_datetime=start_datetime,
                    due_datetime=due_datetime,
                    estimated_time=int(row['Estimated Time']) if row['Estimated Time'] else None,
                    is_scheduled=False
                )

                # Auto-detect and set event type
                new_event.event_type = new_event.detect_event_type()

                # Set default duration if estimated_time is not set
                new_event.set_default_duration()

                db.session.add(new_event)
                imported_count += 1

            # Commit all changes
            db.session.commit()

            return jsonify({
                'imported_count': imported_count,
                'message': f'Successfully imported {imported_count} events'
            }), 200

        except Exception as e:
            # Rollback transaction on error
            db.session.rollback()
            return jsonify({'error': f'Database error during import: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'Error processing CSV file: {str(e)}'}), 400


@api_bp.route('/import/scheduled', methods=['POST'])
def import_scheduled_events():
    """Import already scheduled events from CSV file"""
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']
    Schedule = current_app.config['Schedule']
    EmployeeWeeklyAvailability = current_app.config['EmployeeWeeklyAvailability']

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'File must be a CSV'}), 400

    try:
        # Read CSV file
        content = file.read().decode('utf-8')
        csv_data = list(csv.DictReader(StringIO(content)))

        imported_count = 0

        try:
            for row in csv_data:
                # Parse dates
                start_datetime = datetime.strptime(row['Start Date/Time'], '%m/%d/%Y %I:%M:%S %p')
                due_datetime = datetime.strptime(row['Due Date/Time'], '%m/%d/%Y %I:%M:%S %p')
                schedule_datetime = datetime.strptime(row['Schedule Date/Time'], '%m/%d/%Y %I:%M:%S %p')

                # Get or create the event first
                project_ref_num = row['Project Reference Number'].strip() if row['Project Reference Number'] else None

                # Check if event already exists
                existing_event = Event.query.filter_by(project_ref_num=project_ref_num).first()

                if not existing_event:
                    # Create new event
                    new_event = Event(
                        project_name=row['Project Name'].strip() if row['Project Name'] else '',
                        project_ref_num=project_ref_num,
                        location_mvid=row['Location MVID'].strip() if row['Location MVID'] else None,
                        store_number=int(row['Store Number']) if row['Store Number'] else None,
                        store_name=row['Store Name'].strip() if row['Store Name'] else None,
                        start_datetime=start_datetime,
                        due_datetime=due_datetime,
                        estimated_time=int(row['Estimated Time']) if row['Estimated Time'] else None,
                        is_scheduled=True
                    )

                    # Auto-detect and set event type
                    new_event.event_type = new_event.detect_event_type()

                    # Set default duration if estimated_time is not set
                    new_event.set_default_duration()

                    db.session.add(new_event)
                    db.session.flush()  # Get the ID
                    event = new_event
                else:
                    # Update existing event to be scheduled
                    existing_event.is_scheduled = True
                    event = existing_event

                # Get or create the employee
                employee_id = row['Employee ID'].strip() if row['Employee ID'] else None
                employee_name = row['Rep Name'].strip() if row['Rep Name'] else None

                if employee_id:
                    employee = Employee.query.filter_by(id=employee_id).first()
                    if not employee:
                        # Create new employee if not exists
                        employee = Employee(
                            id=employee_id,
                            name=employee_name or f'Employee {employee_id}',
                            is_active=True,
                            is_supervisor=False,
                            job_title='Event Specialist',  # Default job title
                            adult_beverage_trained=False
                        )
                        db.session.add(employee)

                        # Add default weekly availability (available all days)
                        availability = EmployeeWeeklyAvailability(
                            employee_id=employee_id,
                            monday=True,
                            tuesday=True,
                            wednesday=True,
                            thursday=True,
                            friday=True,
                            saturday=True,
                            sunday=True
                        )
                        db.session.add(availability)

                    # Create the schedule entry
                    existing_schedule = Schedule.query.filter_by(
                        event_ref_num=event.project_ref_num,
                        employee_id=employee_id
                    ).first()

                    if not existing_schedule:
                        new_schedule = Schedule(
                            event_ref_num=event.project_ref_num,
                            employee_id=employee_id,
                            schedule_datetime=schedule_datetime
                        )
                        db.session.add(new_schedule)
                        db.session.flush()  # Get the ID for shift block assignment
                        
                        # NEW: Assign shift block for Core events
                        if event.event_type == 'Core':
                            try:
                                from app.services.shift_block_config import ShiftBlockConfig
                                ShiftBlockConfig.assign_next_available_block(
                                    new_schedule, 
                                    schedule_datetime.date()
                                )
                            except Exception as e:
                                logger.warning(f"Could not assign shift block during import: {e}")

                    # AUTO-SCHEDULE SUPERVISOR EVENT if this is a Core event
                    if event.event_type == 'Core' and not existing_schedule:
                        from routes.scheduling import auto_schedule_supervisor_event
                        scheduled_date = schedule_datetime.date()
                        auto_schedule_supervisor_event(
                            db, Event, Schedule, Employee,
                            event.project_ref_num,
                            scheduled_date,
                            employee_id
                        )

                imported_count += 1

            # Commit all changes
            db.session.commit()

            return jsonify({
                'imported_count': imported_count,
                'message': f'Successfully imported {imported_count} scheduled events'
            }), 200

        except Exception as e:
            # Rollback transaction on error
            db.session.rollback()
            return jsonify({'error': f'Database error during import: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'Error processing CSV file: {str(e)}'}), 400


@api_bp.route('/validate-schedule', methods=['POST'])
def validate_schedule():
    """
    Real-time schedule validation endpoint for AJAX conflict checking.

    Epic 1, Story 1.2: Real-Time Validation API Endpoint

    Request: POST /api/validate-schedule
    Body: {"employee_id": "EMP001", "event_id": 123, "schedule_datetime": "2025-10-15T09:00:00", "duration_minutes": 120}

    Response: {"success": true, "valid": bool, "conflicts": [], "warnings": [], "severity": "error"|"warning"|"success"}
    """
    from .api_validate_schedule import validate_schedule_endpoint
    return validate_schedule_endpoint()


@api_bp.route('/suggest-employees', methods=['GET'])
def suggest_employees():
    """
    Employee suggestion endpoint for conflict resolution.

    Epic 1, Story 1.5: Add Conflict Details with Actionable Context
    Task 2: Create Employee Suggestion Endpoint

    Request: GET /api/suggest-employees?event_id=123&date=2025-10-15&time=09:00&limit=3

    Response: {"success": true, "suggestions": [{"employee_id": "EMP002", "employee_name": "Jane", "score": 95, "reason": "..."}]}
    """
    from .api_suggest_employees import suggest_employees_endpoint
    return suggest_employees_endpoint()


@api_bp.route('/schedule-event', methods=['POST'])
def schedule_event():
    """
    Schedule an event via AJAX from the dashboard.

    Epic 2, Story 2.4: Add AJAX Form Submission

    Request: POST /api/schedule-event
    Body: {"employee_id": "EMP001", "event_id": 606034, "schedule_datetime": "2025-10-15T09:00:00", "duration_minutes": 120}

    Response: {"success": true, "message": "Event scheduled successfully", "schedule_id": 123}
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Get request data
        data = request.get_json()
        employee_id = data.get('employee_id')
        event_id = data.get('event_id')
        schedule_datetime_str = data.get('schedule_datetime')
        duration_minutes_param = data.get('duration_minutes')  # May be None

        # Validate required fields
        if not employee_id or not event_id or not schedule_datetime_str:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        # Get the event
        event = Event.query.filter_by(project_ref_num=event_id).first()
        if not event:
            return jsonify({'success': False, 'error': 'Event not found'}), 404

        # Calculate duration: use param if provided, else event's estimated_time, else type default
        if duration_minutes_param:
            duration_minutes = duration_minutes_param
        else:
            duration_minutes = event.estimated_time or event.get_default_duration(event.event_type)

        # Get the employee
        employee = db.session.get(Employee, employee_id)
        if not employee:
            return jsonify({'success': False, 'error': 'Employee not found'}), 404

        # Parse schedule datetime
        try:
            schedule_datetime = datetime.fromisoformat(schedule_datetime_str)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid datetime format'}), 400

        # Validate date is within event range
        schedule_date = schedule_datetime.date()
        if not (event.start_datetime.date() <= schedule_date <= event.due_datetime.date()):
            return jsonify({'success': False, 'error': 'Date must be within event date range'}), 400

        # Check if employee can work this event type
        if not employee.can_work_event_type(event.event_type):
            if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
                return jsonify({'success': False, 'error': 'Employee cannot work Juicer events. Only Club Supervisors and Juicer Baristas can work Juicer events.'}), 400
            elif event.event_type in ['Supervisor', 'Freeosk', 'Digitals']:
                return jsonify({'success': False, 'error': f'Employee cannot work {event.event_type} events. Only Club Supervisors and Lead Event Specialists can work this type of event.'}), 400
            else:
                return jsonify({'success': False, 'error': 'Employee cannot work this event type'}), 400

        # For Core events, check if employee already has a Core event that day
        if event.event_type == 'Core':
            existing_core = Schedule.query.join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == employee_id,
                db.func.date(Schedule.schedule_datetime) == schedule_date,
                Event.event_type == 'Core'
            ).first()

            if existing_core:
                return jsonify({'success': False, 'error': 'Employee already has a Core event scheduled that day'}), 400

        # Check if event is already scheduled
        existing_schedule = Schedule.query.filter_by(event_ref_num=event_id).first()
        if existing_schedule:
            return jsonify({'success': False, 'error': 'Event is already scheduled'}), 400

        # Submit to Crossmark API BEFORE creating local record
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Calculate end datetime
        end_datetime = schedule_datetime + timedelta(minutes=duration_minutes)

        # Prepare API data
        rep_id = str(employee.external_id) if employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        # Validate required API fields
        if not rep_id:
            return jsonify({'success': False, 'error': f'Missing Crossmark employee ID for {employee.name}'}), 400

        if not mplan_id:
            return jsonify({'success': False, 'error': 'Missing Crossmark event ID'}), 400

        if not location_id:
            return jsonify({'success': False, 'error': 'Missing Crossmark location ID'}), 400

        # Ensure session is authenticated
        try:
            if not external_api.ensure_authenticated():
                return jsonify({'success': False, 'error': 'Failed to authenticate with Crossmark API'}), 500
        except Exception as auth_error:
            current_app.logger.error(f"Authentication error: {str(auth_error)}")
            return jsonify({'success': False, 'error': 'Failed to authenticate with Crossmark API'}), 500

        # Submit to external API
        try:
            current_app.logger.info(
                f"Submitting schedule to Crossmark API: "
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
                return jsonify({'success': False, 'error': f'Failed to submit to Crossmark: {error_message}'}), 500

            current_app.logger.info(f"Successfully submitted schedule to Crossmark API")

        except Exception as api_error:
            current_app.logger.error(f"API submission error: {str(api_error)}")
            return jsonify({'success': False, 'error': f'Failed to submit to Crossmark API: {str(api_error)}'}), 500

        # API submission successful - now create local record with transaction
        try:
            # BEGIN NESTED TRANSACTION for CORE-Supervisor pairing
            with db.session.begin_nested():
                # Create CORE event schedule
                new_schedule = Schedule(
                    event_ref_num=event_id,
                    employee_id=employee_id,
                    schedule_datetime=schedule_datetime
                )
                db.session.add(new_schedule)
                db.session.flush()  # Get the ID

                # Update event status
                event.is_scheduled = True
                event.sync_status = 'synced'
                event.last_synced = datetime.utcnow()
                
                # NEW: Assign shift block for Core events
                if event.event_type == 'Core':
                    try:
                        from app.services.shift_block_config import ShiftBlockConfig
                        block_num = ShiftBlockConfig.assign_next_available_block(
                            new_schedule, 
                            schedule_datetime.date()
                        )
                        if block_num:
                            current_app.logger.info(f"Assigned shift block {block_num} to Core schedule {new_schedule.id}")
                    except Exception as e:
                        current_app.logger.warning(f"Could not assign shift block: {e}")

                # NEW: Check if this is a CORE event and auto-schedule Supervisor (Calendar Redesign - Sprint 2)
                from app.utils.event_helpers import is_core_event_redesign, get_supervisor_status

                # Check both event_type and project name for Core detection
                is_core = event.event_type == 'Core' or is_core_event_redesign(event)
                
                if is_core:
                    current_app.logger.info(f"CORE event detected (type={event.event_type}): {event.project_name}. Checking for paired Supervisor...")

                    supervisor_status = get_supervisor_status(event)

                    if supervisor_status['exists'] and not supervisor_status['is_scheduled']:
                        supervisor_event = supervisor_status['event']
                        current_app.logger.info(
                            f"Found unscheduled Supervisor: {supervisor_event.project_name} (ID: {supervisor_event.project_ref_num})"
                        )

                        # Get Supervisor time from settings instead of hardcoded offset
                        from app.services.event_time_settings import EventTimeSettings
                        supervisor_times = EventTimeSettings.get_supervisor_times()
                        supervisor_start_time = supervisor_times['start']
                        
                        # Use the configured supervisor time on the same date as the Core event
                        supervisor_schedule_datetime = datetime.combine(
                            schedule_datetime.date(),
                            supervisor_start_time
                        )
                        
                        current_app.logger.info(
                            f"Scheduling Supervisor at configured time: {supervisor_schedule_datetime.isoformat()}"
                        )

                        # Prepare Supervisor API data
                        supervisor_rep_id = rep_id  # Same employee for now
                        supervisor_mplan_id = str(supervisor_event.external_id) if supervisor_event.external_id else None
                        supervisor_location_id = str(supervisor_event.location_mvid) if supervisor_event.location_mvid else None

                        # Validate Supervisor API fields
                        if all([supervisor_rep_id, supervisor_mplan_id, supervisor_location_id]):
                            # Calculate Supervisor end datetime
                            supervisor_estimated_minutes = supervisor_event.estimated_time or supervisor_event.get_default_duration(supervisor_event.event_type)
                            supervisor_end_datetime = supervisor_schedule_datetime + timedelta(minutes=supervisor_estimated_minutes)

                            # Call Crossmark API for Supervisor
                            current_app.logger.info(
                                f"Calling Crossmark API for Supervisor: "
                                f"rep_id={supervisor_rep_id}, mplan_id={supervisor_mplan_id}, "
                                f"start={supervisor_schedule_datetime.isoformat()}"
                            )

                            supervisor_api_result = external_api.schedule_mplan_event(
                                rep_id=supervisor_rep_id,
                                mplan_id=supervisor_mplan_id,
                                location_id=supervisor_location_id,
                                start_datetime=supervisor_schedule_datetime,
                                end_datetime=supervisor_end_datetime,
                                planning_override=True
                            )

                            if not supervisor_api_result.get('success'):
                                error_msg = supervisor_api_result.get('message', 'Unknown API error')
                                current_app.logger.error(f"Supervisor API call failed: {error_msg}")
                                raise Exception(f"Failed to schedule Supervisor in Crossmark: {error_msg}")

                            # Create Supervisor schedule
                            supervisor_schedule = Schedule(
                                event_ref_num=supervisor_event.project_ref_num,
                                employee_id=employee_id,
                                schedule_datetime=supervisor_schedule_datetime
                            )
                            db.session.add(supervisor_schedule)

                            # Update Supervisor event status
                            supervisor_event.is_scheduled = True
                            supervisor_event.sync_status = 'synced'
                            supervisor_event.last_synced = datetime.utcnow()

                            current_app.logger.info(
                                f"✅ Successfully auto-scheduled Supervisor event {supervisor_event.project_ref_num} "
                                f"at {supervisor_schedule_datetime.isoformat()}"
                            )
                        else:
                            current_app.logger.warning(
                                f"Supervisor API fields incomplete for {supervisor_event.project_name}. "
                                f"Skipping Supervisor schedule."
                            )
                    elif supervisor_status['exists']:
                        current_app.logger.info(
                            f"Supervisor event exists but is already scheduled (condition: {supervisor_status['condition']}). "
                            f"No auto-schedule needed."
                        )
                    else:
                        current_app.logger.info("No paired Supervisor event found for this CORE event.")

            # COMMIT TRANSACTION
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Event scheduled successfully',
                'schedule_id': new_schedule.id
            })

        except Exception as nested_error:
            db.session.rollback()
            current_app.logger.error(f"Transaction failed during schedule: {str(nested_error)}", exc_info=True)
            raise nested_error

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error scheduling event: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/workload', methods=['GET'])
def get_workload():
    """
    Get employee workload data for date range.

    Epic 2, Story 2.5: Create Workload Dashboard Backend API

    Request: GET /api/workload?start_date=2025-10-15&end_date=2025-10-22

    Response: {
        "employees": [{"id": 123, "name": "John", "event_count": 15, "total_hours": 42.5, "status": "normal"}],
        "thresholds": {"normal_max_events": 12, "high_max_events": 18, "overload_max_events": 20}
    }
    """
    from app.services.workload_analytics import WorkloadAnalytics

    try:
        db = current_app.extensions['sqlalchemy']

        # Parse query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Default to current week (Monday-Sunday)
        if not start_date_str or not end_date_str:
            today = date.today()
            # Calculate Monday of current week
            start_date = today - timedelta(days=today.weekday())
            # Calculate Sunday of current week
            end_date = start_date + timedelta(days=6)
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        # Validate date range
        if end_date < start_date:
            return jsonify({'error': 'End date must be after start date'}), 400

        # Get workload data
        analytics = WorkloadAnalytics(db)
        workload_data = analytics.get_workload_data(start_date, end_date)

        return jsonify(workload_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching workload data: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error fetching workload data: {str(e)}'}), 500


@api_bp.route('/employee-schedule-details', methods=['GET'])
def get_employee_schedule_details():
    """
    Get detailed schedule information for a specific employee.

    Epic 2, Story 2.6: Workload Dashboard Drill-Down
    Priority 1 Blocker: Required for workload dashboard drill-down modal

    Request: GET /api/employee-schedule-details?employee_id=EMP001&start_date=2025-10-15&end_date=2025-10-22

    Response: {
        "success": true,
        "employee_id": "EMP001",
        "employee_name": "John Doe",
        "schedules": [
            {
                "date": "2025-10-15",
                "time": "09:45 AM",
                "event_name": "Super Pretzel Demo",
                "event_type": "Core",
                "location": "Store #1234",
                "duration": "2 hours"
            }
        ]
    }
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Parse query parameters
        employee_id = request.args.get('employee_id')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Validate required parameters
        if not employee_id:
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: employee_id'
            }), 400

        if not start_date_str or not end_date_str:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters: start_date and end_date'
            }), 400

        # Parse dates
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD.'
            }), 400

        # Get employee
        employee = db.session.get(Employee, employee_id)
        if not employee:
            return jsonify({
                'success': False,
                'error': f'Employee not found: {employee_id}'
            }), 404

        # Query schedules for the employee within date range
        schedules = db.session.query(
            Schedule,
            Event
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee_id,
            db.func.date(Schedule.schedule_datetime) >= start_date,
            db.func.date(Schedule.schedule_datetime) <= end_date
        ).order_by(
            Schedule.schedule_datetime
        ).all()

        # Format schedules for response
        formatted_schedules = []
        for schedule, event in schedules:
            # Calculate duration
            duration_minutes = event.estimated_time or event.get_default_duration(event.event_type)
            hours = duration_minutes // 60
            minutes = duration_minutes % 60
            if minutes > 0:
                duration_str = f"{hours} hour{'' if hours == 1 else 's'} {minutes} min"
            else:
                duration_str = f"{hours} hour{'' if hours == 1 else 's'}"

            # Format location
            location = event.store_name or ''
            if event.store_number:
                location = f"Store #{event.store_number}" + (f" - {event.store_name}" if event.store_name else "")

            formatted_schedules.append({
                'date': schedule.schedule_datetime.strftime('%Y-%m-%d'),
                'time': schedule.schedule_datetime.strftime('%I:%M %p'),
                'event_name': event.project_name,
                'event_type': event.event_type,
                'location': location,
                'duration': duration_str
            })

        logger.info(
            f"Fetched {len(formatted_schedules)} schedule details for employee {employee_id} "
            f"from {start_date} to {end_date}"
        )

        return jsonify({
            'success': True,
            'employee_id': employee.id,
            'employee_name': employee.name,
            'schedules': formatted_schedules,
            'total_events': len(formatted_schedules)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching employee schedule details: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error fetching schedule details: {str(e)}'
        }), 500


@api_bp.route('/event/<int:schedule_id>/change-employee', methods=['POST'])
@require_authentication()
def change_event_employee(schedule_id):
    """
    Change employee assignment for an event.

    This endpoint allows supervisors to change the employee assigned to a
    scheduled event. It validates the new assignment for conflicts using
    ConflictValidator before making the change.

    Args:
        schedule_id: Schedule ID (integer, path parameter)

    Request Body:
        {
            "employee_id": "EMP001"
        }

    Returns:
        JSON response with success status and updated employee IDs

    Response Format (Success):
        {
            "success": true,
            "schedule_id": 123,
            "old_employee_id": "EMP001",
            "old_employee_name": "John Doe",
            "new_employee_id": "EMP002",
            "new_employee_name": "Jane Smith"
        }

    Response Format (Conflict):
        {
            "error": "Conflict detected for selected employee",
            "conflicts": [
                {
                    "type": "time_off",
                    "severity": "error",
                    "message": "Jane Smith has approved time-off on Oct 15"
                }
            ]
        }

    Status Codes:
        200: Success - employee changed
        400: Invalid request (missing employee_id)
        404: Schedule not found or employee not found
        409: Conflict - new employee has conflicts at this datetime
        500: Server error

    Example:
        POST /api/event/123/change-employee
        Body: {"employee_id": "EMP002"}

    Note:
        - Uses ConflictValidator from Epic 1 for conflict checking
        - Returns 409 Conflict if validation fails
        - Does not perform change if conflicts detected
    """
    from app.services.conflict_validation import ConflictValidator

    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    # Get schedule
    schedule = db.session.get(Schedule, schedule_id)
    if not schedule:
        return jsonify({'error': f'Schedule not found: {schedule_id}'}), 404

    # Parse request body
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    new_employee_id = data.get('employee_id')

    if not new_employee_id:
        return jsonify({'error': 'employee_id is required'}), 400

    # Get new employee
    new_employee = db.session.get(Employee, new_employee_id)
    if not new_employee:
        return jsonify({'error': f'Employee not found: {new_employee_id}'}), 404

    # Get old employee info before change
    old_employee = schedule.employee
    old_employee_id = old_employee.id if old_employee else None
    old_employee_name = old_employee.name if old_employee else 'Unassigned'

    # Validate conflicts for new employee using ConflictValidator
    try:
        # Initialize ConflictValidator with models dict
        models = {
            'Employee': Employee,
            'Event': Event,
            'Schedule': Schedule,
            'EmployeeTimeOff': current_app.config.get('EmployeeTimeOff'),
            'EmployeeAvailability': current_app.config.get('EmployeeAvailability'),
            'EmployeeWeeklyAvailability': current_app.config.get('EmployeeWeeklyAvailability'),
        }

        validator = ConflictValidator(db.session, models)

        # Calculate duration from event estimated_time or use event type default
        if schedule.event and schedule.event.estimated_time:
            duration_minutes = schedule.event.estimated_time
        elif schedule.event:
            duration_minutes = schedule.event.get_default_duration(schedule.event.event_type)
        else:
            duration_minutes = 60  # Fallback if no event

        # Validate new employee assignment
        validation_result = validator.validate_schedule(
            employee_id=new_employee_id,
            event_id=schedule.event.project_ref_num if schedule.event else None,
            schedule_datetime=schedule.schedule_datetime,
            duration_minutes=duration_minutes
        )

        # Check for conflicts
        if not validation_result.is_valid:
            # Format conflicts for response
            conflicts = [
                {
                    'type': violation.constraint_type.value,
                    'severity': 'error' if violation.severity.value == 'HARD' else 'warning',
                    'message': violation.message,
                    'details': violation.details
                }
                for violation in validation_result.violations
            ]

            logger.warning(
                f"Change employee conflict: schedule={schedule_id}, "
                f"new_employee={new_employee_id}, conflicts={len(conflicts)}"
            )

            return jsonify({
                'error': 'Conflict detected for selected employee',
                'conflicts': conflicts
            }), 409

    except Exception as e:
        logger.error(f"Validation error for schedule {schedule_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to validate employee assignment',
            'details': str(e)
        }), 500

    # No conflicts - proceed with change
    try:
        # Update schedule with new employee
        schedule.employee_id = new_employee_id

        db.session.commit()

        logger.info(
            f"Employee changed: schedule={schedule_id}, "
            f"old={old_employee_id}, new={new_employee_id}"
        )

        return jsonify({
            'success': True,
            'schedule_id': schedule_id,
            'old_employee_id': old_employee_id,
            'old_employee_name': old_employee_name,
            'new_employee_id': new_employee_id,
            'new_employee_name': new_employee.name
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to change employee for schedule {schedule_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to update employee assignment',
            'details': str(e)
        }), 500


@api_bp.route('/available-employees', methods=['GET'])
@require_authentication()
def get_available_employees():
    """
    Get list of employees available for a specific date/time.

    This endpoint returns employees who have no conflicts at the specified
    datetime, suitable for display in the change employee dropdown.

    Query Parameters:
        date: Date string in 'YYYY-MM-DD' format (required)
        time: Time string in 'HH:MM' format (required)
        duration: Event duration in minutes (optional, default 120)
        event_id: Event project_ref_num (optional, for role validation)
        exclude_schedule_id: Schedule ID to exclude from conflict check (optional)

    Returns:
        JSON response with array of available employees

    Response Format:
        {
            "available_employees": [
                {
                    "employee_id": "EMP001",
                    "employee_name": "John Doe",
                    "is_active": true
                },
                {
                    "employee_id": "EMP002",
                    "employee_name": "Jane Smith",
                    "is_active": true
                }
            ]
        }

    Example:
        GET /api/available-employees?date=2025-10-15&time=10:00&duration=120

    Note:
        - Queries all active employees
        - Filters out employees with conflicts at specified datetime
        - Uses ConflictValidator to check each employee
        - Returns only conflict-free employees
    """
    from app.services.conflict_validation import ConflictValidator

    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    # Parse query parameters
    date_str = request.args.get('date')
    time_str = request.args.get('time')
    duration = int(request.args.get('duration', 120))
    event_id = request.args.get('event_id')
    exclude_schedule_id = request.args.get('exclude_schedule_id')

    # Validate required parameters
    if not date_str or not time_str:
        return jsonify({'error': 'date and time parameters are required'}), 400

    # Parse datetime
    try:
        datetime_str = f"{date_str} {time_str}"
        target_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
    except ValueError as e:
        return jsonify({'error': f'Invalid date/time format: {e}'}), 400

    # Get event if event_id provided (for role validation)
    event = None
    if event_id:
        event = db.session.query(Event).filter_by(project_ref_num=int(event_id)).first()

    # Query all active employees
    all_employees = db.session.query(Employee).filter_by(is_active=True).all()

    # Initialize ConflictValidator
    try:
        models = {
            'Employee': Employee,
            'Event': Event,
            'Schedule': Schedule,
            'EmployeeTimeOff': current_app.config.get('EmployeeTimeOff'),
            'EmployeeAvailability': current_app.config.get('EmployeeAvailability'),
            'EmployeeWeeklyAvailability': current_app.config.get('EmployeeWeeklyAvailability'),
        }

        validator = ConflictValidator(db.session, models)

        # Filter employees by checking conflicts
        available_employees = []

        for employee in all_employees:
            try:
                # If event_id is provided, do full validation
                if event_id and event:
                    validation_result = validator.validate_schedule(
                        employee_id=employee.id,
                        event_id=int(event_id),
                        schedule_datetime=target_datetime,
                        duration_minutes=duration
                    )

                    # Only include if no conflicts
                    if validation_result.is_valid:
                        available_employees.append({
                            'employee_id': employee.id,
                            'employee_name': employee.name,
                            'is_active': employee.is_active
                        })
                else:
                    # No event_id provided - just check basic time conflicts
                    # Check if employee has any schedule at this exact time
                    existing_schedule = db.session.query(Schedule).filter_by(
                        employee_id=employee.id,
                        schedule_datetime=target_datetime
                    ).first()

                    if not existing_schedule:
                        available_employees.append({
                            'employee_id': employee.id,
                            'employee_name': employee.name,
                            'is_active': employee.is_active
                        })

            except ValueError as e:
                # Event not found - skip this employee
                logger.debug(f"Skipping employee {employee.id}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Validation failed for employee {employee.id}: {e}")
                # Skip this employee if validation fails
                continue

        logger.info(
            f"Available employees query: date={date_str}, time={time_str}, "
            f"found={len(available_employees)}/{len(all_employees)}"
        )

        return jsonify({
            'available_employees': available_employees
        }), 200

    except Exception as e:
        logger.error(f"Failed to get available employees: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to retrieve available employees',
            'details': str(e)
        }), 500


@api_bp.route('/reissue-event', methods=['POST'])
@require_authentication()
def reissue_event():
    """
    Reissue an event to Crossmark system (two-step process)

    Step 1: Call createPendingWork to reissue with the new employee
    Step 2: Call scheduleMplanEvent to schedule the event to that employee

    Request JSON:
    {
        "schedule_id": int,         # Schedule ID to reissue
        "employee_id": str,         # Employee ID (defaults to currently scheduled employee)
        "include_responses": bool,  # Include previous responses (default: false)
        "expiration_date": str,     # Optional expiration date (YYYY-MM-DD)
        "schedule_date": str,       # Optional schedule date (YYYY-MM-DD), defaults to original
        "schedule_time": str        # Optional schedule time (HH:MM), defaults to original
    }

    Returns:
        JSON response with success status and message
    """
    try:
        data = request.get_json()
        schedule_id = data.get('schedule_id')
        employee_id = data.get('employee_id')
        include_responses = data.get('include_responses', False)
        expiration_date_str = data.get('expiration_date')
        schedule_date_str = data.get('schedule_date')
        schedule_time_str = data.get('schedule_time')

        if not schedule_id:
            return jsonify({'error': 'schedule_id is required'}), 400

        # Get models
        db = current_app.extensions['sqlalchemy']
        Schedule = current_app.config['Schedule']
        Event = current_app.config['Event']
        Employee = current_app.config['Employee']

        # Get the schedule
        schedule = db.session.query(Schedule).filter_by(id=schedule_id).first()
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404

        # Get the event
        event = db.session.query(Event).filter_by(
            project_ref_num=schedule.event_ref_num
        ).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Get employee (use provided or default to scheduled employee)
        if employee_id is None:
            employee_id = schedule.employee_id

        logger.info(f"Reissue: using employee_id={employee_id} (original schedule employee_id={schedule.employee_id})")

        employee = db.session.query(Employee).filter_by(id=employee_id).first()
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404

        # Parse expiration date or use event due date + 1 day
        if expiration_date_str:
            try:
                expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid expiration_date format. Use YYYY-MM-DD'}), 400
        else:
            expiration_date = event.due_datetime + timedelta(days=1)

        # Parse schedule date/time or use original
        if schedule_date_str and schedule_time_str:
            try:
                schedule_datetime = datetime.strptime(f"{schedule_date_str} {schedule_time_str}", '%Y-%m-%d %H:%M')
            except ValueError:
                return jsonify({'error': 'Invalid schedule_date or schedule_time format'}), 400
        else:
            schedule_datetime = schedule.schedule_datetime

        # Get SessionAPIService instance
        session_api = current_app.config.get('SESSION_API_SERVICE')
        if not session_api:
            return jsonify({'error': 'External API service not configured'}), 500

        if not session_api.ensure_authenticated():
            return jsonify({'error': 'Failed to authenticate with external system'}), 500

        # Get the employee's external ID (rep ID in Crossmark system)
        rep_id = employee.external_id if employee.external_id else employee.id

        # Get store ID and mPlan ID
        store_id = str(event.store_number) if event.store_number else (str(event.location_mvid) if event.location_mvid else '')
        mplan_id = str(event.project_ref_num) if event.project_ref_num else ''

        # Get workLogEntryID from the schedule's external_id (the Crossmark scheduled event ID)
        work_log_entry_id = schedule.external_id if schedule.external_id else ''

        # Common headers for both API calls
        request_headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://crossmark.mvretail.com',
            'referer': 'https://crossmark.mvretail.com/planning/',
            'x-requested-with': 'XMLHttpRequest'
        }

        # ========================================
        # STEP 1: Create Pending Work (Reissue)
        # ========================================
        reissue_data = {
            'workLogEntryID': work_log_entry_id,
            'storeID': store_id,
            'mPlanID': mplan_id,
            'reissueBulkJson': '[]',
            'action': 'reissue',
            'includeResponses': 'true' if include_responses else 'false',
            'pendingWorkReasonComments': '',
            'public': 'true',
            'excludeReps': 'false',
            'excludedRepIDs': '[]',
            'overrideReps': 'true',
            'overriddenRepIDs': f'[{rep_id}]',
            'expirationDate': expiration_date.strftime('%Y-%m-%dT00:00:00'),
            'additionalEmail': ''
        }

        logger.info(f"[REISSUE STEP 1] createPendingWork: workLogEntryID={work_log_entry_id}, storeID={store_id}, mPlanID={mplan_id}, repID={rep_id}")
        print(f"[REISSUE STEP 1] createPendingWork: workLogEntryID={work_log_entry_id}, storeID={store_id}, mPlanID={mplan_id}, repID={rep_id}")

        try:
            response1 = session_api.make_request(
                'POST',
                '/pendingworkextcontroller/createPendingWork/',
                data=reissue_data,
                headers=request_headers
            )

            logger.info(f"[REISSUE STEP 1] Response: status={response1.status_code}, body={response1.text[:500]}")
            print(f"[REISSUE STEP 1] Response: status={response1.status_code}, body={response1.text[:500]}")

            if response1.status_code not in [200, 201]:
                logger.error(f"Step 1 failed: {response1.status_code} - {response1.text}")
                return jsonify({
                    'error': 'Failed to create pending work (Step 1)',
                    'details': response1.text
                }), 500

            # Check for success in response body
            try:
                response1_json = response1.json()
                if not response1_json.get('success', True):  # Default to True if not present
                    return jsonify({
                        'error': 'Pending work creation failed',
                        'details': response1_json.get('message', response1.text)
                    }), 500
            except Exception:
                pass  # Response might not be JSON, continue if status was 200/201

            # ========================================
            # STEP 2: Schedule the mPlan Event
            # ========================================
            # Calculate start and end times with timezone offset
            # Using Eastern Time offset (-05:00)
            start_datetime = schedule_datetime
            # End is typically the next day at midnight for full-day events
            end_datetime = start_datetime + timedelta(days=1)

            schedule_data = {
                'ClassName': 'MVScheduledmPlan',
                'RepID': str(rep_id),
                'mPlanID': mplan_id,
                'LocationID': store_id,
                'Start': start_datetime.strftime('%Y-%m-%dT%H:%M:%S') + '-05:00',
                'End': end_datetime.strftime('%Y-%m-%dT00:00:00') + '-05:00',
                'hash': '',
                'v': '3.0.1',
                'PlanningOverride': 'true'
            }

            logger.info(f"[REISSUE STEP 2] scheduleMplanEvent: RepID={rep_id}, mPlanID={mplan_id}, LocationID={store_id}, Start={schedule_data['Start']}")
            print(f"[REISSUE STEP 2] scheduleMplanEvent: RepID={rep_id}, mPlanID={mplan_id}, LocationID={store_id}, Start={schedule_data['Start']}")

            response2 = session_api.make_request(
                'POST',
                '/planningextcontroller/scheduleMplanEvent',
                data=schedule_data,
                headers=request_headers
            )

            logger.info(f"[REISSUE STEP 2] Response: status={response2.status_code}, body={response2.text[:500]}")
            print(f"[REISSUE STEP 2] Response: status={response2.status_code}, body={response2.text[:500]}")

            if response2.status_code not in [200, 201]:
                logger.error(f"Step 2 failed: {response2.status_code} - {response2.text}")
                return jsonify({
                    'error': 'Failed to schedule event (Step 2)',
                    'details': response2.text
                }), 500

            # ========================================
            # Update local database
            # ========================================
            event.condition = 'Reissued'

            # Update schedule with new employee and datetime
            request_employee_id = str(employee_id) if employee_id is not None else None
            current_employee_id = str(schedule.employee_id) if schedule.employee_id is not None else None

            if request_employee_id is not None and request_employee_id != current_employee_id:
                logger.info(f"Updating schedule employee from {current_employee_id} to {request_employee_id}")
                schedule.employee_id = employee_id

            # Update schedule datetime if changed
            if schedule_datetime != schedule.schedule_datetime:
                schedule.schedule_datetime = schedule_datetime

            # Try to extract new external_id from response
            try:
                response2_json = response2.json()
                new_external_id = (
                    response2_json.get('scheduleEventID') or
                    response2_json.get('id') or
                    response2_json.get('scheduledEventId') or
                    response2_json.get('ID')
                )
                if new_external_id:
                    schedule.external_id = str(new_external_id)
                    logger.info(f"Updated schedule external_id to {new_external_id}")
            except Exception:
                pass

            schedule.last_synced = datetime.utcnow()
            schedule.sync_status = 'synced'
            db.session.commit()

            logger.info(f"Successfully reissued event {event.project_name} (ID: {event.id}) to {employee.name}")

            return jsonify({
                'success': True,
                'message': f'Successfully reissued {event.project_name} to {employee.name}',
                'event_id': event.id,
                'employee_name': employee.name
            }), 200

        except Exception as api_error:
            logger.error(f"API request failed: {api_error}", exc_info=True)
            return jsonify({
                'error': 'Failed to communicate with external system',
                'details': str(api_error)
            }), 500

    except Exception as e:
        logger.error(f"Failed to reissue event: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'error': 'Failed to reissue event',
            'details': str(e)
        }), 500


@api_bp.route('/verify-schedule', methods=['POST'])
@require_authentication()
def verify_schedule():
    """
    Verify schedule for a specific date

    Runs 8 validation rules to check for scheduling issues:
    1. Juicer event verification
    2. Core events per person limit
    3. Supervisor event assignment
    4. Supervisor event time
    5. Shift balance across 4 timeslots
    6. Lead Event Specialist coverage
    7. Employee work limits
    8. Event date range validation

    Request Body:
        {
            "date": "2025-11-04"  # Date to verify in YYYY-MM-DD format
        }

    Returns:
        JSON response with verification results:
        {
            "status": "pass" | "warning" | "fail",
            "issues": [
                {
                    "severity": "critical" | "warning" | "info",
                    "rule_name": "Rule name",
                    "message": "Descriptive message",
                    "details": {...}
                }
            ],
            "summary": {
                "date": "2025-11-04",
                "total_issues": 3,
                "critical_issues": 1,
                "warnings": 2,
                "total_events": 12,
                "total_employees": 8
            }
        }

    Example:
        POST /api/verify-schedule
        Body: {"date": "2025-11-04"}
    """
    from app.services.schedule_verification import ScheduleVerificationService
    from app.utils.db_helpers import get_models

    try:
        # Get date from request
        data = request.get_json()
        if not data or 'date' not in data:
            return jsonify({'error': 'Missing required field: date'}), 400

        date_str = data['date']

        # Parse date
        try:
            verify_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        # Get models and db session
        m = get_models()
        db = m['db']

        # Create service
        service = ScheduleVerificationService(db.session, m)

        # Run verification
        result = service.verify_schedule(verify_date)

        # Return results
        return jsonify(result.to_dict()), 200

    except Exception as e:
        logger.error(f"Failed to verify schedule: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to verify schedule',
            'details': str(e)
        }), 500


# Register modular API endpoint routes
# Priority 3: Workflow Gaps - FR32, FR34, FR38
register_availability_override_routes(api_bp)  # FR32: Temporary Availability Change
register_termination_routes(api_bp)  # FR34: Employee Termination Workflow
register_auto_scheduler_settings_routes(api_bp)  # FR38: Auto-Scheduler Event Type Filtering
