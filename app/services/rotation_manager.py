"""
Rotation Manager Service
Manages weekly rotation assignments and one-time exceptions
"""
from datetime import datetime, date
from typing import Optional, Dict, List, Tuple
from sqlalchemy.orm import Session


class RotationManager:
    """
    Manages rotation assignments for Juicers and Primary Leads

    Handles:
    - Weekly rotation lookups with exception support
    - Rotation CRUD operations
    - Exception management for one-time overrides
    """

    def __init__(self, db_session: Session, models: dict):
        """
        Initialize RotationManager

        Args:
            db_session: SQLAlchemy database session
            models: Dictionary of model classes from app.config
        """
        self.db = db_session
        self.RotationAssignment = models['RotationAssignment']
        self.ScheduleException = models['ScheduleException']
        self.Employee = models['Employee']

    def get_rotation_employee(self, target_date: datetime, rotation_type: str) -> Optional[object]:
        """
        Get the assigned employee for a given date and rotation type

        Checks for exceptions first, falls back to weekly rotation

        Args:
            target_date: The date to check
            rotation_type: 'juicer' or 'primary_lead'

        Returns:
            Employee object or None if no assignment
        """
        # Check for one-time exception first
        exception = self.db.query(self.ScheduleException).filter_by(
            exception_date=target_date.date(),
            rotation_type=rotation_type
        ).first()

        if exception:
            return exception.employee

        # Fall back to weekly rotation
        day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday

        rotation = self.db.query(self.RotationAssignment).filter_by(
            day_of_week=day_of_week,
            rotation_type=rotation_type
        ).first()

        return rotation.employee if rotation else None

    def get_rotation_employee_id(self, target_date: datetime, rotation_type: str) -> Optional[str]:
        """
        Get the employee ID for a rotation assignment

        Args:
            target_date: The date to check
            rotation_type: 'juicer' or 'primary_lead'

        Returns:
            Employee ID string or None
        """
        employee = self.get_rotation_employee(target_date, rotation_type)
        return employee.id if employee else None

    def set_rotation(self, day_of_week: int, rotation_type: str, employee_id: str) -> bool:
        """
        Set or update a rotation assignment

        Args:
            day_of_week: 0=Monday, 6=Sunday
            rotation_type: 'juicer' or 'primary_lead'
            employee_id: Employee ID to assign

        Returns:
            True if successful, False otherwise
        """
        if day_of_week < 0 or day_of_week > 6:
            return False

        # Check if employee exists
        employee = self.db.query(self.Employee).get(employee_id)
        if not employee:
            return False

        # Check for existing rotation
        existing = self.db.query(self.RotationAssignment).filter_by(
            day_of_week=day_of_week,
            rotation_type=rotation_type
        ).first()

        if existing:
            existing.employee_id = employee_id
        else:
            rotation = self.RotationAssignment(
                day_of_week=day_of_week,
                rotation_type=rotation_type,
                employee_id=employee_id
            )
            self.db.add(rotation)

        self.db.commit()
        return True

    def get_all_rotations(self) -> Dict[str, Dict[int, str]]:
        """
        Get all rotation assignments grouped by type

        Returns:
            Dict with rotation_type as keys, each containing day->employee_id mapping
            Example: {
                'juicer': {0: 'EMP001', 1: 'EMP002', ...},
                'primary_lead': {0: 'LEAD001', ...}
            }
        """
        rotations = self.db.query(self.RotationAssignment).all()

        result = {
            'juicer': {},
            'primary_lead': {}
        }

        for rotation in rotations:
            result[rotation.rotation_type][rotation.day_of_week] = rotation.employee_id

        return result

    def set_all_rotations(self, rotations: Dict[str, Dict[int, str]]) -> Tuple[bool, List[str]]:
        """
        Set multiple rotation assignments at once

        Args:
            rotations: Dict of rotation_type -> {day_of_week: employee_id}

        Returns:
            Tuple of (success: bool, errors: List[str])
        """
        errors = []

        try:
            # Delete existing rotations
            self.db.query(self.RotationAssignment).delete()

            # Add new rotations
            for rotation_type, assignments in rotations.items():
                if rotation_type not in ['juicer', 'primary_lead']:
                    errors.append(f"Invalid rotation type: {rotation_type}")
                    continue

                for day_of_week, employee_id in assignments.items():
                    if day_of_week < 0 or day_of_week > 6:
                        errors.append(f"Invalid day: {day_of_week}")
                        continue

                    # Verify employee exists
                    employee = self.db.query(self.Employee).get(employee_id)
                    if not employee:
                        errors.append(f"Employee not found: {employee_id}")
                        continue

                    rotation = self.RotationAssignment(
                        day_of_week=day_of_week,
                        rotation_type=rotation_type,
                        employee_id=employee_id
                    )
                    self.db.add(rotation)

            if errors:
                self.db.rollback()
                return False, errors

            self.db.commit()
            return True, []

        except Exception as e:
            self.db.rollback()
            return False, [str(e)]

    def add_exception(self, exception_date: date, rotation_type: str,
                     employee_id: str, reason: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Add a one-time rotation exception

        Args:
            exception_date: Date for the exception
            rotation_type: 'juicer' or 'primary_lead'
            employee_id: Employee to assign for this date only
            reason: Optional reason for the exception

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            # Check if employee exists
            employee = self.db.query(self.Employee).get(employee_id)
            if not employee:
                return False, f"Employee not found: {employee_id}"

            # Check for existing exception
            existing = self.db.query(self.ScheduleException).filter_by(
                exception_date=exception_date,
                rotation_type=rotation_type
            ).first()

            if existing:
                existing.employee_id = employee_id
                existing.reason = reason
            else:
                exception = self.ScheduleException(
                    exception_date=exception_date,
                    rotation_type=rotation_type,
                    employee_id=employee_id,
                    reason=reason
                )
                self.db.add(exception)

            self.db.commit()
            return True, None

        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def get_exceptions(self, start_date: date, end_date: date) -> List[object]:
        """
        Get all exceptions within a date range

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of ScheduleException objects
        """
        return self.db.query(self.ScheduleException).filter(
            self.ScheduleException.exception_date >= start_date,
            self.ScheduleException.exception_date <= end_date
        ).all()

    def delete_exception(self, exception_id: int) -> bool:
        """
        Delete a schedule exception

        Args:
            exception_id: ID of the exception to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            exception = self.db.query(self.ScheduleException).get(exception_id)
            if exception:
                self.db.delete(exception)
                self.db.commit()
                return True
            return False
        except Exception:
            self.db.rollback()
            return False

    def get_secondary_lead(self, target_date: datetime) -> Optional[object]:
        """
        Get the secondary lead for a given date

        Secondary lead is any Lead Event Specialist who is NOT the primary lead

        Args:
            target_date: The date to check

        Returns:
            Employee object (Lead) or None
        """
        primary_lead = self.get_rotation_employee(target_date, 'primary_lead')
        primary_lead_id = primary_lead.id if primary_lead else None

        # Find available Lead Event Specialists (excluding primary)
        query = self.db.query(self.Employee).filter(
            self.Employee.job_title.in_(['Lead Event Specialist', 'Club Supervisor'])
        )

        if primary_lead_id:
            query = query.filter(self.Employee.id != primary_lead_id)

        # Return first available lead (could be enhanced with availability checking)
        return query.first()
