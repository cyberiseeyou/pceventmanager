"""
Employee Suggestion API Endpoint

Suggests alternative employees when scheduling conflicts occur.
Uses ConstraintValidator to find available employees and ranks them by suitability.

Epic 1, Story 1.5: Add Conflict Details with Actionable Context
Task 2: Create Employee Suggestion Endpoint
"""
import logging
import time
from datetime import datetime
from flask import jsonify, request, current_app
from app.services.constraint_validator import ConstraintValidator

logger = logging.getLogger(__name__)


def suggest_employees_endpoint():
    """
    GET /api/suggest-employees

    Find and rank available employees for an event at a given date/time.

    Query Parameters:
        - event_id (required): Event ID (project_ref_num)
        - date (required): Date in YYYY-MM-DD format
        - time (required): Time in HH:MM format
        - duration_minutes (optional): Duration in minutes (default: 120)
        - limit (optional): Max suggestions to return (default: 3)

    Returns:
        JSON response with suggested employees ranked by suitability.

    Response Format:
        {
            "success": true,
            "suggestions": [
                {
                    "employee_id": "EMP002",
                    "employee_name": "Jane Smith",
                    "employee_role": "Lead Event Specialist",
                    "score": 95,
                    "reason": "Available, correct role"
                }
            ]
        }
    """
    start_time = time.time()

    try:
        # Parse query parameters
        event_id = request.args.get('event_id')
        date_str = request.args.get('date')
        time_str = request.args.get('time')
        duration_minutes = int(request.args.get('duration_minutes', 120))
        limit = int(request.args.get('limit', 3))

        # Validate required parameters
        if not event_id:
            logger.warning("Missing required parameter: event_id")
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: event_id'
            }), 200

        if not date_str:
            logger.warning("Missing required parameter: date")
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: date'
            }), 200

        if not time_str:
            logger.warning("Missing required parameter: time")
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: time'
            }), 200

        # Parse datetime
        try:
            event_id_int = int(event_id)
            schedule_datetime = datetime.strptime(
                f"{date_str} {time_str}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError as e:
            logger.error(f"Invalid date/time format: {e}")
            return jsonify({
                'success': False,
                'error': f'Invalid date/time format: {e}'
            }), 200

        logger.debug(
            f"Fetching employee suggestions for event={event_id}, "
            f"datetime={schedule_datetime}, limit={limit}"
        )

        # Get models and db from app config
        db = current_app.extensions['sqlalchemy']
        models = current_app.config['models']

        # Get event
        Event = models['Event']
        event = db.session.query(Event).filter_by(
            project_ref_num=event_id_int
        ).first()

        if not event:
            logger.error(f"Event not found: {event_id}")
            return jsonify({
                'success': False,
                'error': f'Event not found: {event_id}'
            }), 200

        # Initialize constraint validator
        validator = ConstraintValidator(db.session, models)

        # Get available employees
        available_employees = validator.get_available_employees(
            event,
            schedule_datetime
        )

        logger.info(
            f"Found {len(available_employees)} available employees for "
            f"event {event_id} at {schedule_datetime}"
        )

        # Score and rank employees
        suggestions = []
        for employee in available_employees[:limit * 2]:  # Get extra for ranking
            score, reason = _score_employee(employee, event, schedule_datetime, db.session, models)
            suggestions.append({
                'employee_id': employee.id,
                'employee_name': employee.name,
                'employee_role': getattr(employee, 'job_title', 'Unknown'),
                'score': score,
                'reason': reason
            })

        # Sort by score descending and take top N
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        suggestions = suggestions[:limit]

        # Log performance
        elapsed = (time.time() - start_time) * 1000
        logger.info(
            f"Employee suggestion completed in {elapsed:.2f}ms, "
            f"returning {len(suggestions)} suggestions"
        )

        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'count': len(suggestions)
        }), 200

    except Exception as e:
        logger.error(f"Error in suggest_employees_endpoint: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 200


def _score_employee(employee, event, schedule_datetime, db_session, models):
    """
    Score an employee's suitability for an event.

    Scoring Factors:
    - Role match: +30 points
    - Recent performance: +20 points (if available)
    - Schedule density: +15 points (fewer scheduled events)
    - Event type experience: +10 points
    - Base score: 25 points

    Args:
        employee: Employee object
        event: Event object
        schedule_datetime: Proposed datetime
        db_session: Database session
        models: Model dictionary

    Returns:
        Tuple of (score, reason_string)
    """
    score = 25  # Base score
    reasons = []

    # Role match
    role_match = False
    if event.event_type == 'Core':
        if hasattr(employee, 'job_title') and employee.job_title in ['Event Specialist', 'Lead Event Specialist']:
            role_match = True
            score += 30
            reasons.append("matches event role")
    elif event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
        if hasattr(employee, 'job_title') and employee.job_title == 'Juicer Barista':
            role_match = True
            score += 30
            reasons.append("juicer certified")
    elif event.event_type in ['Freeosk', 'Digitals']:
        if hasattr(employee, 'job_title') and employee.job_title in ['Lead Event Specialist', 'Club Supervisor']:
            role_match = True
            score += 30
            reasons.append("has required lead role")
    else:
        # Default role match
        role_match = True
        score += 20
        reasons.append("meets basic requirements")

    # Check schedule density (fewer events = higher score)
    Schedule = models['Schedule']
    target_date = schedule_datetime.date()

    try:
        from sqlalchemy import func
        events_on_day = db_session.query(func.count(Schedule.id)).filter(
            Schedule.employee_id == employee.id,
            func.date(Schedule.schedule_datetime) == target_date
        ).scalar() or 0

        if events_on_day == 0:
            score += 15
            reasons.append("no other events this day")
        elif events_on_day == 1:
            score += 10
            reasons.append("light schedule")
        else:
            score += 5
    except Exception as e:
        logger.warning(f"Could not check schedule density: {e}")

    # Event type experience (check past schedules)
    try:
        Event = models['Event']
        past_events = db_session.query(func.count(Schedule.id)).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee.id,
            Event.event_type == event.event_type
        ).scalar() or 0

        if past_events > 10:
            score += 10
            reasons.append(f"experienced with {event.event_type} events")
        elif past_events > 5:
            score += 7
            reasons.append(f"familiar with {event.event_type} events")
        elif past_events > 0:
            score += 3
    except Exception as e:
        logger.warning(f"Could not check event experience: {e}")

    # Build reason string
    if not reasons:
        reason = "Available for this time slot"
    else:
        reason = ", ".join(reasons).capitalize()

    return score, reason
