"""
Employee Termination Workflow API Endpoints
FR34: Scenario 4 - Employee Termination

Automated workflow for handling employee terminations and reassigning future events.
"""
from flask import request, jsonify, current_app
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


def get_employee_future_events_endpoint(employee_id):
    """
    Get all future scheduled events for an employee after a specific date.

    Request: GET /api/employees/<employee_id>/future-events?after_date=2025-10-18

    Response: {
        "success": true,
        "employee_id": "EMP001",
        "employee_name": "John Doe",
        "future_events": [
            {
                "schedule_id": 123,
                "event_id": 606034,
                "event_name": "Super Pretzel Demo",
                "event_type": "Core",
                "scheduled_date": "2025-10-20",
                "scheduled_time": "09:45 AM",
                "location": "Store #1234"
            }
        ],
        "total_events": 8
    }
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        # Get employee
        employee = db.session.get(Employee, employee_id)
        if not employee:
            return jsonify({
                'success': False,
                'error': f'Employee not found: {employee_id}'
            }), 404

        # Parse after_date parameter
        after_date_str = request.args.get('after_date')
        if after_date_str:
            try:
                after_date = datetime.strptime(after_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid after_date format. Use YYYY-MM-DD.'
                }), 400
        else:
            after_date = date.today()

        # Query future schedules
        future_schedules = db.session.query(
            Schedule,
            Event
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee_id,
            db.func.date(Schedule.schedule_datetime) > after_date
        ).order_by(
            Schedule.schedule_datetime
        ).all()

        # Format events
        future_events = []
        for schedule, event in future_schedules:
            location = event.store_name or ''
            if event.store_number:
                location = f"Store #{event.store_number}" + (f" - {event.store_name}" if event.store_name else "")

            future_events.append({
                'schedule_id': schedule.id,
                'event_id': event.project_ref_num,
                'event_name': event.project_name,
                'event_type': event.event_type,
                'scheduled_date': schedule.schedule_datetime.strftime('%Y-%m-%d'),
                'scheduled_time': schedule.schedule_datetime.strftime('%I:%M %p'),
                'location': location
            })

        logger.info(
            f"Found {len(future_events)} future events for employee {employee_id} "
            f"after {after_date}"
        )

        return jsonify({
            'success': True,
            'employee_id': employee.id,
            'employee_name': employee.name,
            'after_date': after_date.strftime('%Y-%m-%d'),
            'future_events': future_events,
            'total_events': len(future_events)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching future events: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error fetching future events: {str(e)}'
        }), 500


def terminate_employee_endpoint():
    """
    Terminate an employee and handle their future scheduled events.

    Request: POST /api/employees/terminate
    Body: {
        "employee_id": "EMP001",
        "termination_date": "2025-10-18",
        "strategy": "mark_unscheduled",  // or "reassign_to" or "auto_suggest"
        "reassign_to_employee_id": "EMP002"  // Required if strategy is "reassign_to"
    }

    Response: {
        "success": true,
        "employee_id": "EMP001",
        "termination_date": "2025-10-18",
        "affected_events": 8,
        "message": "Employee terminated. 8 future events marked as unscheduled."
    }
    """
    db = current_app.extensions['sqlalchemy']
    Schedule = current_app.config['Schedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']

    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        termination_date_str = data.get('termination_date')
        strategy = data.get('strategy', 'mark_unscheduled')

        # Validate required fields
        if not employee_id or not termination_date_str:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: employee_id, termination_date'
            }), 400

        # Get employee
        employee = db.session.get(Employee, employee_id)
        if not employee:
            return jsonify({
                'success': False,
                'error': f'Employee not found: {employee_id}'
            }), 404

        # Parse termination date
        try:
            termination_date = datetime.strptime(termination_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid termination_date format. Use YYYY-MM-DD.'
            }), 400

        # Begin transaction
        try:
            with db.session.begin_nested():
                # Update employee record
                employee.is_active = False
                employee.termination_date = termination_date

                # Find all future schedules
                future_schedules = db.session.query(
                    Schedule
                ).join(
                    Event, Schedule.event_ref_num == Event.project_ref_num
                ).filter(
                    Schedule.employee_id == employee_id,
                    db.func.date(Schedule.schedule_datetime) > termination_date
                ).all()

                affected_count = len(future_schedules)

                if strategy == 'mark_unscheduled':
                    # Strategy 1: Mark all events as unscheduled
                    for schedule in future_schedules:
                        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
                        if event:
                            # Check if this is the only schedule for the event
                            remaining_schedules = Schedule.query.filter_by(
                                event_ref_num=event.project_ref_num
                            ).filter(Schedule.id != schedule.id).count()

                            if remaining_schedules == 0:
                                event.is_scheduled = False

                        db.session.delete(schedule)

                    message = f"Employee terminated. {affected_count} future events marked as unscheduled."

                elif strategy == 'reassign_to':
                    # Strategy 2: Reassign all events to specific employee
                    reassign_to_id = data.get('reassign_to_employee_id')
                    if not reassign_to_id:
                        return jsonify({
                            'success': False,
                            'error': 'reassign_to_employee_id required when strategy is "reassign_to"'
                        }), 400

                    # Verify target employee exists and is active
                    target_employee = db.session.get(Employee, reassign_to_id)
                    if not target_employee or not target_employee.is_active:
                        return jsonify({
                            'success': False,
                            'error': f'Target employee not found or inactive: {reassign_to_id}'
                        }), 404

                    # Reassign all schedules
                    for schedule in future_schedules:
                        schedule.employee_id = reassign_to_id

                    message = f"Employee terminated. {affected_count} future events reassigned to {target_employee.name}."

                else:
                    return jsonify({
                        'success': False,
                        'error': f'Invalid strategy: {strategy}. Use "mark_unscheduled" or "reassign_to".'
                    }), 400

            # Commit transaction
            db.session.commit()

            logger.info(
                f"Employee {employee_id} terminated with date {termination_date}. "
                f"Strategy: {strategy}. Affected events: {affected_count}"
            )

            return jsonify({
                'success': True,
                'employee_id': employee_id,
                'employee_name': employee.name,
                'termination_date': termination_date.strftime('%Y-%m-%d'),
                'affected_events': affected_count,
                'strategy': strategy,
                'message': message
            })

        except Exception as nested_error:
            db.session.rollback()
            raise nested_error

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during employee termination: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error terminating employee: {str(e)}'
        }), 500


def register_termination_routes(api_bp):
    """
    Register termination workflow routes with the API blueprint.

    Add this to api.py:
    from .api_employee_termination import register_termination_routes
    register_termination_routes(api_bp)
    """
    api_bp.add_url_rule('/employees/<employee_id>/future-events', 'get_employee_future_events',
                        get_employee_future_events_endpoint, methods=['GET'])
    api_bp.add_url_rule('/employees/terminate', 'terminate_employee',
                        terminate_employee_endpoint, methods=['POST'])
