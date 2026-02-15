"""
Real-Time Schedule Validation API Endpoint

Provides AJAX endpoint for validating schedule assignments in real-time.
Returns conflicts (HARD violations) and warnings (SOFT violations).

Epic 1, Story 1.2: Real-Time Validation API Endpoint
"""
from flask import request, jsonify, current_app
from app.models import get_models
from datetime import datetime
import logging
import time

from app.services.conflict_validation import ConflictValidator
from app.services.validation_types import ConstraintSeverity

logger = logging.getLogger(__name__)


def format_violation(violation):
    """
    Format a ConstraintViolation object for JSON API response.

    Args:
        violation: ConstraintViolation object

    Returns:
        dict: Formatted violation with type, severity, message, detail
    """
    return {
        'type': violation.details.get('type', violation.constraint_type.value),
        'severity': 'error' if violation.severity == ConstraintSeverity.HARD else 'warning',
        'message': violation.message,
        'detail': violation.details.get('detail', '')
    }


def validate_schedule_endpoint():
    """
    POST /api/validate-schedule - Validate schedule assignment in real-time.

    Request Body (JSON):
        {
            "employee_id": "EMP001",
            "event_id": 606034,
            "schedule_datetime": "2025-10-15T09:00:00",
            "duration_minutes": 120
        }

    Response (JSON):
        {
            "success": true,
            "valid": true/false,
            "conflicts": [{type, severity, message, detail}],
            "warnings": [{type, severity, message, detail}],
            "severity": "error"|"warning"|"success"
        }

    Returns:
        JSON response with 200 OK status (even for validation failures)
    """
    start_time = time.time()

    try:
        # Parse request data
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Invalid JSON in request body'
            }), 200

        # Extract required parameters
        employee_id = data.get('employee_id')
        event_id = data.get('event_id')
        schedule_datetime_str = data.get('schedule_datetime')
        duration_minutes = data.get('duration_minutes', 120)

        # Validate required fields
        if not employee_id:
            return jsonify({
                'success': False,
                'error': 'Missing required field: employee_id'
            }), 200

        if not event_id:
            return jsonify({
                'success': False,
                'error': 'Missing required field: event_id'
            }), 200

        if not schedule_datetime_str:
            return jsonify({
                'success': False,
                'error': 'Missing required field: schedule_datetime'
            }), 200

        # Parse datetime
        try:
            schedule_datetime = datetime.fromisoformat(schedule_datetime_str)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid datetime format. Use ISO format: YYYY-MM-DDTHH:MM:SS'
            }), 200

        # Validate duration_minutes
        if not isinstance(duration_minutes, int) or duration_minutes <= 0:
            return jsonify({
                'success': False,
                'error': 'duration_minutes must be a positive integer'
            }), 200

        logger.debug(
            f"Validation request: employee={employee_id}, event={event_id}, "
            f"datetime={schedule_datetime}, duration={duration_minutes}min"
        )

        # Get database session and models
        db = current_app.extensions['sqlalchemy']
        all_models = get_models()
        models = {
            'Employee': all_models['Employee'],
            'Event': all_models['Event'],
            'Schedule': all_models['Schedule'],
            'EmployeeAvailability': all_models.get('EmployeeAvailability'),
            'EmployeeTimeOff': all_models['EmployeeTimeOff'],
            'EmployeeWeeklyAvailability': all_models.get('EmployeeWeeklyAvailability')
        }

        # Initialize validator
        validator = ConflictValidator(db.session, models)

        # Perform validation
        result = validator.validate_schedule(
            employee_id=employee_id,
            event_id=event_id,
            schedule_datetime=schedule_datetime,
            duration_minutes=duration_minutes
        )

        # Map ValidationResult to API response
        conflicts = []
        warnings = []

        for violation in result.violations:
            formatted = format_violation(violation)

            if violation.severity == ConstraintSeverity.HARD:
                conflicts.append(formatted)
            else:
                warnings.append(formatted)

        # Determine overall severity
        if conflicts:
            severity = 'error'
        elif warnings:
            severity = 'warning'
        else:
            severity = 'success'

        # Calculate elapsed time
        elapsed_ms = (time.time() - start_time) * 1000

        # Log slow queries
        if elapsed_ms > 200:
            logger.warning(
                f"Slow validation query: {elapsed_ms:.0f}ms for "
                f"employee={employee_id}, event={event_id}"
            )
        else:
            logger.info(
                f"Validation complete in {elapsed_ms:.0f}ms: "
                f"valid={result.is_valid}, conflicts={len(conflicts)}, warnings={len(warnings)}"
            )

        return jsonify({
            'success': True,
            'valid': result.is_valid,
            'conflicts': conflicts,
            'warnings': warnings,
            'severity': severity
        }), 200

    except ValueError as e:
        # Employee or Event not found
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"Validation error ({elapsed_ms:.0f}ms): {str(e)}")

        return jsonify({
            'success': False,
            'error': str(e)
        }), 200

    except Exception as e:
        # Internal server error
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"Internal error during validation ({elapsed_ms:.0f}ms): {str(e)}", exc_info=True)

        return jsonify({
            'success': False,
            'error': 'An internal error occurred during validation'
        }), 200
