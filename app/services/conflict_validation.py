"""
Conflict Validation Service for Real-Time Schedule Validation

This service validates scheduling assignments in real-time, checking for conflicts
such as double-booking, time-off, role mismatches, and event date ranges.

Used by:
- AJAX validation endpoints for inline warnings
- Manual scheduling forms
- Quick action modals

Extracted from: scheduler_app/routes/scheduling.py:167-318
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from .validation_types import (
    ValidationResult,
    ConstraintViolation,
    ConstraintType,
    ConstraintSeverity
)


logger = logging.getLogger(__name__)


class ConflictValidator:
    """
    Validates scheduling assignments against business constraints for real-time conflict detection.

    Performs validation checks for:
    - Core event one-per-day rule
    - Employee time-off and availability
    - Role-based event type restrictions
    - Event scheduling window validation
    - Time proximity conflicts (events within 2 hours)

    This differs from ConstraintValidator which is used by the auto-scheduler.
    ConflictValidator is specifically for real-time validation during manual scheduling.
    """

    # Time proximity window (in hours)
    TIME_PROXIMITY_HOURS = 2

    def __init__(self, db_session: Session, models: dict):
        """
        Initialize ConflictValidator.

        Args:
            db_session: SQLAlchemy database session
            models: Dictionary of model classes from app.config
        """
        self.db = db_session
        self.Employee = models['Employee']
        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.EmployeeTimeOff = models['EmployeeTimeOff']
        self.EmployeeAvailability = models.get('EmployeeAvailability')
        self.EmployeeWeeklyAvailability = models.get('EmployeeWeeklyAvailability')
        logger.debug("ConflictValidator initialized")

    def validate_schedule(
        self,
        employee_id: str,
        event_id: int,
        schedule_datetime: datetime,
        duration_minutes: int = 120
    ) -> ValidationResult:
        """
        Validate if employee can be scheduled for event at given datetime.

        Args:
            employee_id: Employee identifier (e.g., 'EMP001' or 'US863735')
            event_id: Event ID (primary key) or project_ref_num
            schedule_datetime: Proposed schedule datetime
            duration_minutes: Event duration in minutes (default 120)

        Returns:
            ValidationResult with violations (HARD=conflicts, SOFT=warnings)

        Raises:
            ValueError: If employee or event not found
        """
        logger.info(
            f"Validating schedule: employee={employee_id}, event={event_id}, "
            f"datetime={schedule_datetime}, duration={duration_minutes}min"
        )

        # Initialize result
        result = ValidationResult(is_valid=True)

        # Get employee and event
        employee = self.db.query(self.Employee).filter_by(id=employee_id).first()
        if not employee:
            logger.error(f"Employee not found: {employee_id}")
            raise ValueError(f"Employee not found: {employee_id}")

        # Try to find event by id first, then by project_ref_num as fallback
        event = self.db.query(self.Event).filter_by(id=event_id).first()
        if not event:
            # Fallback: try project_ref_num (for backwards compatibility)
            event = self.db.query(self.Event).filter_by(
                project_ref_num=event_id
            ).first()
        if not event:
            logger.error(f"Event not found by id or project_ref_num: {event_id}")
            raise ValueError(f"Event not found: {event_id}")

        # Get actual duration from event if not provided
        if duration_minutes is None or duration_minutes == 120:
            duration_minutes = event.estimated_time or event.get_default_duration(event.event_type)

        # Run all validation checks
        self._check_core_event_duplicate(employee, event, schedule_datetime, result)
        self._check_employee_unavailability(employee, schedule_datetime, result)
        self._check_time_off(employee, schedule_datetime, result)
        self._check_weekly_availability(employee, schedule_datetime, result)
        self._check_role_restrictions(employee, event, result)
        self._check_time_proximity(employee, schedule_datetime, duration_minutes, result, event.event_type)
        self._check_event_date_range(event, schedule_datetime, result)

        logger.info(
            f"Validation complete: is_valid={result.is_valid}, "
            f"hard_violations={len(result.hard_violations)}, "
            f"soft_violations={len(result.soft_violations)}"
        )

        return result

    def _check_core_event_duplicate(
        self,
        employee: object,
        event: object,
        schedule_datetime: datetime,
        result: ValidationResult
    ) -> None:
        """
        Check 1: Employee already scheduled for Core event on same day.

        Source: scheduler_app/routes/scheduling.py:202-217
        """
        if event.event_type != 'Core':
            return  # Only check for Core events

        target_date = schedule_datetime.date()

        existing_core = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == employee.id,
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Event.event_type == 'Core'
        ).first()

        if existing_core:
            # Get conflicting event details
            conflicting_event = self.db.query(self.Event).filter_by(
                project_ref_num=existing_core.event_ref_num
            ).first()

            logger.debug(
                f"Core event duplicate detected: {employee.name} already has "
                f"Core event on {target_date}"
            )
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.ALREADY_SCHEDULED,
                message=(
                    f"{employee.name} is already scheduled for a Core event on "
                    f"{target_date.strftime('%Y-%m-%d')}"
                ),
                severity=ConstraintSeverity.HARD,
                details={
                    'type': 'core_already_scheduled',
                    'date': str(target_date),
                    'detail': 'Employees can only work one Core event per day',
                    'conflicting_event_id': existing_core.event_ref_num,
                    'conflicting_event_name': conflicting_event.project_name if conflicting_event else 'Unknown Event',
                    'conflicting_employee_name': employee.name,
                    'conflicting_time_range': f"{existing_core.schedule_datetime.strftime('%I:%M %p')} - {(existing_core.schedule_datetime + timedelta(minutes=120)).strftime('%I:%M %p')}"
                }
            ))

    def _check_employee_unavailability(
        self,
        employee: object,
        schedule_datetime: datetime,
        result: ValidationResult
    ) -> None:
        """
        Check 2: Employee marked as unavailable on specific date.

        Source: scheduler_app/routes/scheduling.py:219-232
        """
        if not self.EmployeeAvailability:
            return

        target_date = schedule_datetime.date()

        unavailable = self.db.query(self.EmployeeAvailability).filter(
            self.EmployeeAvailability.employee_id == employee.id,
            self.EmployeeAvailability.date == target_date,
            self.EmployeeAvailability.is_available == False
        ).first()

        if unavailable:
            logger.debug(
                f"Employee unavailability detected: {employee.name} "
                f"unavailable on {target_date}"
            )
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.AVAILABILITY,
                message=(
                    f"{employee.name} is marked as unavailable on "
                    f"{target_date.strftime('%Y-%m-%d')}"
                ),
                severity=ConstraintSeverity.HARD,
                details={
                    'type': 'employee_unavailable',
                    'date': str(target_date),
                    'detail': 'Employee has explicitly marked this date as unavailable'
                }
            ))

    def _check_time_off(
        self,
        employee: object,
        schedule_datetime: datetime,
        result: ValidationResult
    ) -> None:
        """
        Check 3: Employee has approved time-off.

        Source: scheduler_app/routes/scheduling.py:234-247
        """
        target_date = schedule_datetime.date()

        time_off = self.db.query(self.EmployeeTimeOff).filter(
            self.EmployeeTimeOff.employee_id == employee.id,
            self.EmployeeTimeOff.start_date <= target_date,
            self.EmployeeTimeOff.end_date >= target_date
        ).first()

        if time_off:
            logger.debug(
                f"Time-off conflict detected: {employee.name} has time-off "
                f"from {time_off.start_date} to {time_off.end_date}"
            )
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.TIME_OFF,
                message=(
                    f"{employee.name} has time off from "
                    f"{time_off.start_date.strftime('%Y-%m-%d')} to "
                    f"{time_off.end_date.strftime('%Y-%m-%d')}"
                ),
                severity=ConstraintSeverity.HARD,
                details={
                    'type': 'time_off',
                    'start_date': str(time_off.start_date),
                    'end_date': str(time_off.end_date),
                    'detail': 'Employee has approved time off for this date'
                }
            ))

    def _check_weekly_availability(
        self,
        employee: object,
        schedule_datetime: datetime,
        result: ValidationResult
    ) -> None:
        """
        Check 4: Employee not available on day of week.

        Source: scheduler_app/routes/scheduling.py:249-264
        """
        if not self.EmployeeWeeklyAvailability:
            return

        day_of_week = schedule_datetime.weekday()
        day_columns = [
            'monday', 'tuesday', 'wednesday', 'thursday',
            'friday', 'saturday', 'sunday'
        ]
        day_column = day_columns[day_of_week]

        weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter(
            self.EmployeeWeeklyAvailability.employee_id == employee.id
        ).first()

        if weekly_avail and not getattr(weekly_avail, day_column):
            logger.debug(
                f"Weekly availability warning: {employee.name} typically not "
                f"available on {day_column.capitalize()}s"
            )
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.AVAILABILITY,
                message=(
                    f"{employee.name} is typically not available on "
                    f"{day_column.capitalize()}s"
                ),
                severity=ConstraintSeverity.SOFT,  # Warning, not error
                details={
                    'type': 'weekly_unavailable',
                    'day_of_week': day_column,
                    'detail': 'Check with employee before scheduling'
                }
            ))

    def _check_role_restrictions(
        self,
        employee: object,
        event: object,
        result: ValidationResult
    ) -> None:
        """
        Check 5: Employee lacks required role or training for event type.

        Source: scheduler_app/routes/scheduling.py:266-274
        """
        if not hasattr(employee, 'can_work_event_type'):
            logger.warning(
                "Employee model missing can_work_event_type method, "
                "skipping role check"
            )
            return

        if not employee.can_work_event_type(event.event_type):
            # Determine the requirement type
            role_requirement = (
                'supervisor role' if event.event_type == 'Supervisor'
                else 'adult beverage training'
            )

            logger.debug(
                f"Role restriction detected: {employee.name} cannot work "
                f"{event.event_type} events"
            )
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.ROLE,
                message=f"{employee.name} cannot work {event.event_type} events",
                severity=ConstraintSeverity.HARD,
                details={
                    'type': 'role_restriction',
                    'event_type': event.event_type,
                    'detail': f'Employee does not have required {role_requirement}'
                }
            ))

    def _check_time_proximity(
        self,
        employee: object,
        schedule_datetime: datetime,
        duration_minutes: int,
        result: ValidationResult,
        event_type: str = None
    ) -> None:
        """
        Check 6: Overlapping or nearby events (within 2 hours).

        Source: scheduler_app/routes/scheduling.py:276-295
        
        Note: Skips check for Supervisor events since they are expected to
        overlap with Core events at the same time.
        """
        # Skip time proximity check for Supervisor events
        if event_type and event_type.lower() == 'supervisor':
            logger.debug(f"Skipping time_proximity check for Supervisor event")
            return
        # Calculate proposed event's end time
        proposed_end = schedule_datetime + timedelta(minutes=duration_minutes)

        time_window_start = schedule_datetime - timedelta(
            hours=self.TIME_PROXIMITY_HOURS
        )
        time_window_end = schedule_datetime + timedelta(
            hours=self.TIME_PROXIMITY_HOURS
        )

        nearby_schedules = self.db.query(self.Schedule, self.Event).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == employee.id,
            self.Schedule.schedule_datetime.between(
                time_window_start, time_window_end
            )
        ).all()

        for schedule, nearby_event in nearby_schedules:
            # Get actual duration of the nearby event
            nearby_duration = nearby_event.estimated_time or nearby_event.get_default_duration(nearby_event.event_type)
            nearby_end_time = schedule.schedule_datetime + timedelta(minutes=nearby_duration)

            # Check for actual time overlap
            # Overlap if: (proposed_start < nearby_end) AND (proposed_end > nearby_start)
            if schedule_datetime < nearby_end_time and proposed_end > schedule.schedule_datetime:
                # Events actually overlap
                time_diff_minutes = abs(int((schedule.schedule_datetime - schedule_datetime).total_seconds() / 60))

                logger.debug(
                    f"Time proximity warning: {employee.name} has event "
                    f"{time_diff_minutes} minutes away"
                )
                result.add_violation(ConstraintViolation(
                    constraint_type=ConstraintType.ALREADY_SCHEDULED,
                    message=(
                        f"{employee.name} has another event scheduled "
                        f"{time_diff_minutes} minutes away"
                    ),
                    severity=ConstraintSeverity.SOFT,  # Warning, not error
                    details={
                        'type': 'time_proximity',
                        'nearby_event': nearby_event.project_name,
                        'nearby_time': schedule.schedule_datetime.strftime('%I:%M %p'),
                        'detail': (
                            f"{nearby_event.project_name} at "
                            f"{schedule.schedule_datetime.strftime('%I:%M %p')}"
                        ),
                        'conflicting_event_id': schedule.event_ref_num,
                        'conflicting_event_name': nearby_event.project_name,
                        'conflicting_employee_name': employee.name,
                        'conflicting_time_range': f"{schedule.schedule_datetime.strftime('%I:%M %p')} - {nearby_end_time.strftime('%I:%M %p')}",
                        'time_diff_minutes': time_diff_minutes
                    }
                ))

    def _check_event_date_range(
        self,
        event: object,
        schedule_datetime: datetime,
        result: ValidationResult
    ) -> None:
        """
        Check 7: Schedule date outside event start/due window.

        Source: scheduler_app/routes/scheduling.py:297-310
        """
        schedule_date = schedule_datetime.date()
        event_start_date = event.start_datetime.date()
        event_due_date = event.due_datetime.date()

        if not (event_start_date <= schedule_date <= event_due_date):
            logger.debug(
                f"Event date range violation: schedule date {schedule_date} "
                f"outside range {event_start_date} to {event_due_date}"
            )
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.DUE_DATE,
                message='Selected date is outside event window',
                severity=ConstraintSeverity.HARD,
                details={
                    'type': 'date_out_of_range',
                    'start_date': str(event_start_date),
                    'due_date': str(event_due_date),
                    'detail': (
                        f"Event must be scheduled between "
                        f"{event_start_date.strftime('%Y-%m-%d')} and "
                        f"{event_due_date.strftime('%Y-%m-%d')}"
                    )
                }
            ))
