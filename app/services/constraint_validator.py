"""
Constraint Validator Service
Validates scheduling assignments against business rules
"""
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from .validation_types import (
    ValidationResult,
    ConstraintViolation,
    ConstraintType,
    ConstraintSeverity
)


class ConstraintValidator:
    """
    Validates proposed schedule assignments against all constraints

    Handles:
    - Availability window checking
    - Time-off request validation
    - Role-based event restrictions
    - Daily event limits
    - Already-scheduled conflicts
    """

    # Event types requiring Lead or Supervisor
    LEAD_ONLY_EVENT_TYPES = ['Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh', 'Digital Teardown', 'Other']

    # Max core events per employee per day
    MAX_CORE_EVENTS_PER_DAY = 1

    # Max core events per employee per week (Sunday-Saturday)
    MAX_CORE_EVENTS_PER_WEEK = 6

    def __init__(self, db_session: Session, models: dict):
        """
        Initialize ConstraintValidator

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
        self.PendingSchedule = models.get('PendingSchedule')
        self.CompanyHoliday = models.get('CompanyHoliday')
        self.SchedulerRunHistory = models.get('SchedulerRunHistory')
        self.current_run_id = None  # Track current scheduler run
        self._active_run_ids_cache = None  # Cache for active run IDs

    def set_current_run(self, run_id: int) -> None:
        """
        Set the current scheduler run ID to check pending schedules

        Args:
            run_id: The scheduler run ID to track pending assignments
        """
        self.current_run_id = run_id
        # Invalidate cache when run changes
        self._active_run_ids_cache = None

    def _get_active_run_ids(self) -> list:
        """
        Get all active (unapproved) scheduler run IDs with caching

        Returns:
            list: List of active run IDs
        """
        # Return cached value if available
        if self._active_run_ids_cache is not None:
            return self._active_run_ids_cache

        # Query active runs
        if self.SchedulerRunHistory:
            active_runs = self.db.query(self.SchedulerRunHistory.id).filter(
                self.SchedulerRunHistory.approved_at.is_(None),
                self.SchedulerRunHistory.status.in_(['completed', 'running'])
            ).all()
            self._active_run_ids_cache = [r.id for r in active_runs]
        else:
            self._active_run_ids_cache = []

        return self._active_run_ids_cache

    def validate_assignment(self, event: object, employee: object,
                           schedule_datetime: datetime, duration_minutes: int = None,
                           exclude_schedule_ids: list = None) -> ValidationResult:
        """
        Validate a proposed schedule assignment against all constraints

        Args:
            event: Event model instance
            employee: Employee model instance
            schedule_datetime: Proposed datetime for the event
            duration_minutes: Event duration in minutes (uses event's duration if not provided)
            exclude_schedule_ids: List of schedule IDs to exclude from conflict checking (for trade operations)

        Returns:
            ValidationResult with is_valid flag and list of violations
        """
        result = ValidationResult(is_valid=True)

        # Get duration from event if not provided
        if duration_minutes is None:
            duration_minutes = event.estimated_time or event.get_default_duration(event.event_type)

        # Check all constraints (past-date first as a safety net)
        self._check_past_date(schedule_datetime, result)
        self._check_company_holiday(schedule_datetime, result)
        self._check_time_off(employee, schedule_datetime, result)
        self._check_availability(employee, schedule_datetime, result)
        self._check_role_requirements(event, employee, result)
        self._check_daily_limit(event, employee, schedule_datetime, result, exclude_schedule_ids)
        self._check_weekly_limit(event, employee, schedule_datetime, result, exclude_schedule_ids)
        self._check_already_scheduled(event, employee, schedule_datetime, duration_minutes, result, exclude_schedule_ids)
        self._check_due_date(event, schedule_datetime, result)

        return result

    def _check_company_holiday(self, schedule_datetime: datetime,
                               result: ValidationResult) -> None:
        """Check if the date is a company holiday (everyone off)"""
        if not self.CompanyHoliday:
            return

        target_date = schedule_datetime.date()
        holiday = self.CompanyHoliday.is_holiday(target_date)

        if holiday:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.TIME_OFF,  # Reuse TIME_OFF type for holidays
                message=f"Cannot schedule on {target_date} - Company Holiday: {holiday.name}",
                severity=ConstraintSeverity.HARD,
                details={
                    'holiday_id': holiday.id,
                    'holiday_name': holiday.name,
                    'date': str(target_date),
                    'is_company_holiday': True
                }
            ))

    def _check_time_off(self, employee: object, schedule_datetime: datetime,
                       result: ValidationResult) -> None:
        """Check if employee has requested time off"""
        target_date = schedule_datetime.date()

        time_off = self.db.query(self.EmployeeTimeOff).filter(
            self.EmployeeTimeOff.employee_id == employee.id,
            self.EmployeeTimeOff.start_date <= target_date,
            self.EmployeeTimeOff.end_date >= target_date
        ).first()

        if time_off:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.TIME_OFF,
                message=f"Employee {employee.name} has requested time off on {target_date}",
                severity=ConstraintSeverity.HARD,
                details={'time_off_id': time_off.id, 'date': str(target_date)}
            ))

    def _check_availability(self, employee: object, schedule_datetime: datetime,
                           result: ValidationResult) -> None:
        """Check if schedule_datetime falls within employee's availability window"""
        # Check weekly availability pattern
        if self.EmployeeWeeklyAvailability:
            day_of_week = schedule_datetime.weekday()  # 0=Monday, 6=Sunday

            # Map day_of_week to column name
            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_column = day_names[day_of_week]

            weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                employee_id=employee.id
            ).first()

            if weekly_avail:
                # Check if employee is available on this day
                is_available = getattr(weekly_avail, day_column, True)

                if not is_available:
                    result.add_violation(ConstraintViolation(
                        constraint_type=ConstraintType.AVAILABILITY,
                        message=f"Employee {employee.name} not available on {day_column.capitalize()}",
                        severity=ConstraintSeverity.HARD,
                        details={'day_of_week': day_of_week, 'day_name': day_column}
                    ))

    def _check_role_requirements(self, event: object, employee: object,
                                 result: ValidationResult) -> None:
        """Check if employee's role is authorized for this event type"""
        # Juicer events require Juicer Barista or Club Supervisor role
        if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
            if employee.job_title not in ['Juicer Barista', 'Club Supervisor']:
                result.add_violation(ConstraintViolation(
                    constraint_type=ConstraintType.ROLE,
                    message=f"Employee {employee.name} is not a Juicer Barista or Club Supervisor",
                    severity=ConstraintSeverity.HARD,
                    details={'event_type': event.event_type, 'employee_role': employee.job_title}
                ))

        # Lead-only event types
        if event.event_type in self.LEAD_ONLY_EVENT_TYPES:
            if employee.job_title not in ['Lead Event Specialist', 'Club Supervisor']:
                result.add_violation(ConstraintViolation(
                    constraint_type=ConstraintType.ROLE,
                    message=f"Event type '{event.event_type}' requires Lead or Supervisor role",
                    severity=ConstraintSeverity.HARD,
                    details={'event_type': event.event_type, 'employee_role': employee.job_title}
                ))

        # Club Supervisor should not be scheduled to regular events (but can do Juicer events)
        juicer_types = ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']
        allowed_for_supervisor = ['Supervisor', 'Digitals', 'Freeosk'] + juicer_types
        if employee.job_title == 'Club Supervisor' and event.event_type not in allowed_for_supervisor:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.ROLE,
                message="Club Supervisor should not be assigned to regular events",
                severity=ConstraintSeverity.SOFT,  # Soft constraint
                details={'event_type': event.event_type}
            ))

    def _check_daily_limit(self, event: object, employee: object, schedule_datetime: datetime,
                          result: ValidationResult, exclude_schedule_ids: list = None) -> None:
        """
        Check if employee already has max core events for this day

        Args:
            exclude_schedule_ids: List of schedule IDs to exclude from count (for trade operations)

        Note: Juicer events are handled separately - if employee has Core event and needs to do Juicer,
        the Core event will be bumped/unscheduled in Wave 1.
        """
        # Only apply Core event limit when scheduling a Core event
        if event.event_type != 'Core':
            return

        target_date = schedule_datetime.date()

        # Count existing core events for this employee on this day
        query = self.db.query(func.count(self.Schedule.id)).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == employee.id,
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Event.event_type == 'Core'
        )

        # Exclude schedules being traded
        if exclude_schedule_ids:
            query = query.filter(~self.Schedule.id.in_(exclude_schedule_ids))

        core_events_count = query.scalar()

        # Also count pending core events from ALL unapproved runs (not just current run)
        # This prevents scheduling conflicts when multiple scheduler runs have pending schedules
        if self.PendingSchedule and self.SchedulerRunHistory:
            # Get all unapproved/active scheduler runs (cached)
            active_run_ids = self._get_active_run_ids()

            if active_run_ids:
                pending_core_count = self.db.query(func.count(self.PendingSchedule.id)).join(
                    self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    self.PendingSchedule.scheduler_run_id.in_(active_run_ids),
                    self.PendingSchedule.employee_id == employee.id,
                    func.date(self.PendingSchedule.schedule_datetime) == target_date,
                    self.Event.event_type == 'Core',
                    self.PendingSchedule.failure_reason.is_(None),  # Exclude failed pending schedules
                    self.PendingSchedule.status != 'superseded'  # Exclude superseded schedules
                ).scalar()

                core_events_count += pending_core_count

        if core_events_count >= self.MAX_CORE_EVENTS_PER_DAY:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.DAILY_LIMIT,
                message=f"Employee {employee.name} already has {core_events_count} core event(s) on {target_date}",
                severity=ConstraintSeverity.HARD,
                details={'date': str(target_date), 'current_count': core_events_count}
            ))

    def _check_weekly_limit(self, event: object, employee: object, schedule_datetime: datetime,
                           result: ValidationResult, exclude_schedule_ids: list = None) -> None:
        """
        Check if employee already has max core events for this week (Sunday-Saturday)

        Args:
            exclude_schedule_ids: List of schedule IDs to exclude from count (for trade operations)
        """
        # Only apply Core event limit when scheduling a Core event
        if event.event_type != 'Core':
            return

        from datetime import timedelta

        target_date = schedule_datetime.date()

        # Calculate week boundaries (Sunday-Saturday)
        # weekday() returns 0=Monday, 6=Sunday
        # We want Sunday=0, so adjust: (weekday + 1) % 7
        days_since_sunday = (target_date.weekday() + 1) % 7
        week_start = target_date - timedelta(days=days_since_sunday)  # Sunday
        week_end = week_start + timedelta(days=6)  # Saturday

        # Count existing core events for this employee in this week
        query = self.db.query(func.count(self.Schedule.id)).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == employee.id,
            func.date(self.Schedule.schedule_datetime) >= week_start,
            func.date(self.Schedule.schedule_datetime) <= week_end,
            self.Event.event_type == 'Core'
        )

        # Exclude schedules being traded
        if exclude_schedule_ids:
            query = query.filter(~self.Schedule.id.in_(exclude_schedule_ids))

        core_events_count = query.scalar()

        # Also count pending core events from ALL unapproved runs (cached)
        if self.PendingSchedule and self.SchedulerRunHistory:
            active_run_ids = self._get_active_run_ids()

            if active_run_ids:
                pending_core_count = self.db.query(func.count(self.PendingSchedule.id)).join(
                    self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    self.PendingSchedule.scheduler_run_id.in_(active_run_ids),
                    self.PendingSchedule.employee_id == employee.id,
                    func.date(self.PendingSchedule.schedule_datetime) >= week_start,
                    func.date(self.PendingSchedule.schedule_datetime) <= week_end,
                    self.Event.event_type == 'Core',
                    self.PendingSchedule.failure_reason.is_(None),
                    self.PendingSchedule.status != 'superseded'  # Exclude superseded schedules
                ).scalar()

                core_events_count += pending_core_count

        if core_events_count >= self.MAX_CORE_EVENTS_PER_WEEK:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.DAILY_LIMIT,  # Reuse DAILY_LIMIT type for weekly
                message=f"Employee {employee.name} already has {core_events_count} core event(s) this week ({week_start} to {week_end})",
                severity=ConstraintSeverity.HARD,
                details={
                    'week_start': str(week_start),
                    'week_end': str(week_end),
                    'current_count': core_events_count,
                    'max_per_week': self.MAX_CORE_EVENTS_PER_WEEK
                }
            ))

    def _check_already_scheduled(self, event: object, employee: object, schedule_datetime: datetime,
                                 duration_minutes: int, result: ValidationResult,
                                 exclude_schedule_ids: list = None) -> None:
        """
        Check if employee already has a schedule that overlaps with the proposed time

        Args:
            event: Event being scheduled (used to skip checks for Supervisor events)
            exclude_schedule_ids: List of schedule IDs to exclude from conflict checking (for trade operations)
        """
        # Supervisor events are expected to overlap with Core events - skip overlap check
        if event.event_type == 'Supervisor':
            return

        from datetime import timedelta

        # Calculate proposed event's end time
        proposed_end = schedule_datetime + timedelta(minutes=duration_minutes)

        # Check existing schedules for overlaps
        existing_schedules = self.db.query(self.Schedule).filter_by(
            employee_id=employee.id
        ).all()

        for existing in existing_schedules:
            # Skip schedules that are being excluded (e.g., during trade operations)
            if exclude_schedule_ids and existing.id in exclude_schedule_ids:
                continue

            # Get the existing event to determine its duration
            existing_event = self.db.query(self.Event).filter_by(
                project_ref_num=existing.event_ref_num
            ).first()

            if existing_event:
                # Only CORE and Juicer Production events cause scheduling conflicts
                # Other event types (Supervisor, Freeosk, Digitals, etc.) don't block scheduling
                if existing_event.event_type not in ['Core', 'Juicer Production']:
                    continue

                existing_duration = existing_event.estimated_time or existing_event.get_default_duration(existing_event.event_type)
                existing_end = existing.schedule_datetime + timedelta(minutes=existing_duration)

                # Check if times overlap:
                # Overlap if: (proposed_start < existing_end) AND (proposed_end > existing_start)
                if schedule_datetime < existing_end and proposed_end > existing.schedule_datetime:
                    result.add_violation(ConstraintViolation(
                        constraint_type=ConstraintType.ALREADY_SCHEDULED,
                        message=f"Employee {employee.name} already scheduled for {existing_event.project_name} from {existing.schedule_datetime.strftime('%I:%M %p')} to {existing_end.strftime('%I:%M %p')}",
                        severity=ConstraintSeverity.HARD,
                        details={
                            'schedule_id': existing.id,
                            'datetime': str(schedule_datetime),
                            'conflicting_event': existing_event.project_name,
                            'conflicting_time': f"{existing.schedule_datetime.strftime('%I:%M %p')} - {existing_end.strftime('%I:%M %p')}"
                        }
                    ))
                    return  # Found a conflict, no need to check further

        # Check pending schedules from ALL unapproved runs for overlaps
        # This prevents scheduling conflicts when multiple scheduler runs have pending schedules
        if self.PendingSchedule and self.SchedulerRunHistory:
            # Get all unapproved/active scheduler runs
            active_run_ids = self.db.query(self.SchedulerRunHistory.id).filter(
                self.SchedulerRunHistory.approved_at.is_(None),
                self.SchedulerRunHistory.status.in_(['completed', 'running'])
            ).all()
            active_run_ids = [r.id for r in active_run_ids]

            if active_run_ids:
                pending_schedules = self.db.query(self.PendingSchedule).filter(
                    self.PendingSchedule.scheduler_run_id.in_(active_run_ids),
                    self.PendingSchedule.employee_id == employee.id,
                    self.PendingSchedule.failure_reason.is_(None),  # Exclude failed pending schedules
                    self.PendingSchedule.status != 'superseded'  # Exclude superseded schedules
                ).all()

                for pending in pending_schedules:
                    # Skip if no schedule datetime (should not happen for valid pending schedules)
                    if not pending.schedule_datetime:
                        continue

                    # Get the pending event to determine its duration
                    pending_event = self.db.query(self.Event).filter_by(
                        project_ref_num=pending.event_ref_num
                    ).first()

                    if pending_event:
                        # Only CORE and Juicer Production events cause scheduling conflicts
                        # Other event types (Supervisor, Freeosk, Digitals, etc.) don't block scheduling
                        if pending_event.event_type not in ['Core', 'Juicer Production']:
                            continue

                        pending_duration = pending_event.estimated_time or pending_event.get_default_duration(pending_event.event_type)
                        pending_end = pending.schedule_datetime + timedelta(minutes=pending_duration)

                        # Check if times overlap
                        if schedule_datetime < pending_end and proposed_end > pending.schedule_datetime:
                            result.add_violation(ConstraintViolation(
                                constraint_type=ConstraintType.ALREADY_SCHEDULED,
                                message=f"Employee {employee.name} already assigned to {pending_event.project_name} from {pending.schedule_datetime.strftime('%I:%M %p')} to {pending_end.strftime('%I:%M %p')} (pending approval)",
                                severity=ConstraintSeverity.HARD,
                                details={
                                    'pending_schedule_id': pending.id,
                                    'datetime': str(schedule_datetime),
                                    'conflicting_event': pending_event.project_name,
                                    'conflicting_time': f"{pending.schedule_datetime.strftime('%I:%M %p')} - {pending_end.strftime('%I:%M %p')}"
                                }
                            ))
                            return  # Found a conflict, no need to check further

    def _check_past_date(self, schedule_datetime: datetime,
                        result: ValidationResult) -> None:
        """Reject scheduling in the past — safety net for all code paths"""
        from zoneinfo import ZoneInfo
        from flask import current_app
        tz_name = current_app.config.get(
            'EXTERNAL_API_TIMEZONE', 'America/Indiana/Indianapolis'
        )
        local_today = datetime.now(ZoneInfo(tz_name)).date()
        if schedule_datetime.date() < local_today:
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.PAST_DATE,
                message=f"Cannot schedule in the past ({schedule_datetime.date()})",
                severity=ConstraintSeverity.HARD,
                details={
                    'proposed_date': str(schedule_datetime.date()),
                    'today': str(local_today)
                }
            ))

    def _check_due_date(self, event: object, schedule_datetime: datetime,
                       result: ValidationResult) -> None:
        """Check if scheduled date is before the due date"""
        if schedule_datetime.date() >= event.due_datetime.date():
            result.add_violation(ConstraintViolation(
                constraint_type=ConstraintType.DUE_DATE,
                message=f"Event must be scheduled before due date {event.due_datetime.date()}",
                severity=ConstraintSeverity.HARD,
                details={
                    'due_date': str(event.due_datetime.date()),
                    'proposed_date': str(schedule_datetime.date())
                }
            ))

    def get_available_employees(self, event: object, schedule_datetime: datetime) -> List[object]:
        """
        Get list of employees who can be assigned to this event at this time

        Filters by:
        - Role requirements
        - Time off
        - Daily limits
        - Availability

        Args:
            event: Event to schedule
            schedule_datetime: Proposed datetime

        Returns:
            List of Employee objects who pass all constraints
        """
        # Start with all employees
        all_employees = self.db.query(self.Employee).all()

        available = []
        for employee in all_employees:
            validation = self.validate_assignment(event, employee, schedule_datetime)
            if validation.is_valid:
                available.append(employee)

        return available

    def get_available_employee_ids(self, event: object, schedule_datetime: datetime) -> List[str]:
        """
        Get list of employee IDs who can be assigned to this event

        Args:
            event: Event to schedule
            schedule_datetime: Proposed datetime

        Returns:
            List of employee ID strings
        """
        employees = self.get_available_employees(event, schedule_datetime)
        return [emp.id for emp in employees]
