"""
Conflict Resolver Service
Handles scheduling conflicts and implements bumping strategy
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from .validation_types import SwapProposal


class ConflictResolver:
    """
    Resolves scheduling conflicts by finding events to bump/reschedule

    Strategy:
    - Calculate priority scores based on due date urgency
    - Find bumpable events (furthest from due date)
    - Never bump events within 2 days of due date
    - Propose swaps that preserve business rules
    """

    # Don't bump events within this many days of their due date
    MIN_DAYS_TO_DUE_DATE = 2

    def __init__(self, db_session: Session, models: dict):
        """
        Initialize ConflictResolver

        Args:
            db_session: SQLAlchemy database session
            models: Dictionary of model classes from app.config
        """
        self.db = db_session
        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.Employee = models['Employee']

    def calculate_priority_score(self, event: object, reference_date: datetime = None) -> float:
        """
        Calculate priority score for an event (lower = higher urgency)

        Score = days until due date
        Events closer to due date get lower scores (higher priority)

        Args:
            event: Event model instance
            reference_date: Reference date for calculation (default: now)

        Returns:
            Priority score (float)
        """
        if reference_date is None:
            reference_date = datetime.now()

        days_until_due = (event.due_datetime - reference_date).days

        # Ensure score is never negative
        return max(0, days_until_due)

    def find_bumpable_events(self, target_date: datetime, employee_id: Optional[str] = None) -> List[Tuple[object, float]]:
        """
        Find events that could be bumped/rescheduled

        Args:
            target_date: Date to search for bumpable events
            employee_id: Optional employee ID to filter by

        Returns:
            List of tuples (event, priority_score) sorted by score (highest first)
        """
        # Query existing schedules for this date
        query = self.db.query(self.Schedule, self.Event).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == target_date.date()
        )

        if employee_id:
            query = query.filter(self.Schedule.employee_id == employee_id)

        schedules = query.all()

        bumpable = []
        now = datetime.now()

        for schedule, event in schedules:
            # Don't bump events too close to due date
            days_until_due = (event.due_datetime - now).days
            if days_until_due < self.MIN_DAYS_TO_DUE_DATE:
                continue

            # Calculate priority score
            priority_score = self.calculate_priority_score(event, now)

            # Don't bump Supervisor events (they're paired with Core events)
            if event.event_type == 'Supervisor':
                continue

            bumpable.append((event, priority_score))

        # Sort by priority score (highest = furthest from due date = most bumpable)
        bumpable.sort(key=lambda x: x[1], reverse=True)

        return bumpable

    def resolve_conflict(self, high_priority_event: object, target_date: datetime,
                        employee_id: str) -> Optional[SwapProposal]:
        """
        Find an event to bump to make room for a higher priority event

        Args:
            high_priority_event: Event that needs to be scheduled
            target_date: Date to schedule the high priority event
            employee_id: Employee who would be assigned

        Returns:
            SwapProposal or None if no suitable event to bump
        """
        bumpable_events = self.find_bumpable_events(target_date, employee_id)

        if not bumpable_events:
            return None

        # Take the most bumpable event (furthest from due date)
        low_priority_event, score = bumpable_events[0]

        # Verify the swap makes sense
        high_priority_score = self.calculate_priority_score(high_priority_event)
        low_priority_score = self.calculate_priority_score(low_priority_event)

        if low_priority_score <= high_priority_score:
            # The "bumpable" event is actually higher priority - don't swap
            return None

        # Create swap proposal
        swap = SwapProposal(
            high_priority_event_ref=high_priority_event.project_ref_num,
            low_priority_event_ref=low_priority_event.project_ref_num,
            reason=f"Event {high_priority_event.project_ref_num} due in {int(high_priority_score)} days, "
                   f"Event {low_priority_event.project_ref_num} due in {int(low_priority_score)} days",
            employee_id=employee_id,
            proposed_date=target_date.date().isoformat()
        )

        return swap

    def validate_swap(self, high_priority_event: object, low_priority_event: object) -> bool:
        """
        Validate that a proposed swap is safe and makes sense

        Args:
            high_priority_event: Event to be scheduled
            low_priority_event: Event to be bumped

        Returns:
            True if swap is valid, False otherwise
        """
        # Check priority order
        high_score = self.calculate_priority_score(high_priority_event)
        low_score = self.calculate_priority_score(low_priority_event)

        if low_score <= high_score:
            return False

        # Check that low priority event has enough time to be rescheduled
        days_until_due = (low_priority_event.due_datetime - datetime.now()).days
        if days_until_due < self.MIN_DAYS_TO_DUE_DATE:
            return False

        return True

    def find_alternative_dates(self, event: object, employee_id: str,
                              exclude_dates: List[datetime] = None) -> List[datetime]:
        """
        Find alternative dates when an employee could work an event

        Args:
            event: Event to reschedule
            employee_id: Employee ID
            exclude_dates: Dates to exclude from consideration

        Returns:
            List of potential datetime slots
        """
        if exclude_dates is None:
            exclude_dates = []

        alternatives = []

        # Search between start_datetime and due_datetime
        current_date = event.start_datetime
        while current_date < event.due_datetime:
            # Skip excluded dates
            if current_date.date() in [d.date() for d in exclude_dates]:
                current_date += timedelta(days=1)
                continue

            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # Check if employee has existing schedule on this date
            existing = self.db.query(self.Schedule).filter_by(
                employee_id=employee_id,
                schedule_datetime=current_date
            ).first()

            if not existing:
                alternatives.append(current_date)

            current_date += timedelta(days=1)

        return alternatives

    def get_capacity_status(self, target_date: datetime) -> dict:
        """
        Get capacity information for a specific date

        Args:
            target_date: Date to check

        Returns:
            Dict with capacity statistics
        """
        # Count scheduled events
        scheduled_count = self.db.query(func.count(self.Schedule.id)).filter(
            func.date(self.Schedule.schedule_datetime) == target_date.date()
        ).scalar()

        # Count available employees (simplified - could be enhanced)
        total_employees = self.db.query(func.count(self.Employee.id)).filter(
            self.Employee.job_title.in_(['Event Specialist', 'Lead Event Specialist'])
        ).scalar()

        return {
            'date': target_date.date().isoformat(),
            'scheduled_events': scheduled_count,
            'total_employees': total_employees,
            'capacity_used': scheduled_count / max(1, total_employees),
            'is_overbooked': scheduled_count > total_employees
        }
