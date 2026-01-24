"""
Historical feature extraction for ML models.

Extracts features from historical scheduling patterns, success rates,
and aggregate statistics.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class HistoricalFeatureExtractor:
    """Extract historical pattern features for ML models."""

    def __init__(self, db_session, models):
        """
        Initialize feature extractor.

        Args:
            db_session: SQLAlchemy database session
            models: Model registry from get_models()
        """
        self.db = db_session
        self.models = models

    def extract_employee_history(self, employee_id: int, as_of_date: datetime,
                                 lookback_days: int = 90) -> Dict[str, Any]:
        """
        Extract historical features for a specific employee.

        Args:
            employee_id: Employee ID
            as_of_date: Calculate features as of this date (avoid data leakage)
            lookback_days: How far back to look for history

        Returns:
            Dictionary of historical features
        """
        Schedule = self.models['Schedule']
        PendingSchedule = self.models['PendingSchedule']

        features = {}
        lookback_start = as_of_date - timedelta(days=lookback_days)

        # Total assignments
        total_assignments = self.db.query(Schedule).filter(
            Schedule.employee_id == employee_id,
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).count()
        features['total_assignments_lookback'] = total_assignments

        # Success rate (assignments completed vs failed)
        failed_attempts = self.db.query(PendingSchedule).filter(
            PendingSchedule.employee_id == employee_id,
            PendingSchedule.status == 'failed',
            PendingSchedule.created_at >= lookback_start,
            PendingSchedule.created_at < as_of_date
        ).count()

        total_attempts = total_assignments + failed_attempts
        features['success_rate_lookback'] = total_assignments / total_attempts if total_attempts > 0 else 0.5

        # Average assignments per week
        weeks = lookback_days / 7.0
        features['avg_assignments_per_week'] = total_assignments / weeks if weeks > 0 else 0.0

        # Event type diversity (number of different event types worked)
        event_types = self.db.query(Schedule.event_type).filter(
            Schedule.employee_id == employee_id,
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).distinct().count()
        features['event_type_diversity'] = min(event_types / 5.0, 1.0)

        # Times bumped
        times_bumped = self.db.query(PendingSchedule).filter(
            PendingSchedule.bumped_event_ref_num.isnot(None),
            PendingSchedule.employee_id == employee_id,
            PendingSchedule.created_at >= lookback_start,
            PendingSchedule.created_at < as_of_date
        ).count()
        features['times_bumped_lookback'] = min(times_bumped / 5.0, 1.0)

        return features

    def extract_event_type_history(self, event_type: str, as_of_date: datetime,
                                   lookback_days: int = 180) -> Dict[str, Any]:
        """
        Extract historical success patterns for an event type.

        Args:
            event_type: Event type string
            as_of_date: Calculate features as of this date
            lookback_days: How far back to look

        Returns:
            Dictionary of event type historical features
        """
        Schedule = self.models['Schedule']
        PendingSchedule = self.models['PendingSchedule']
        Event = self.models['Event']

        features = {}
        lookback_start = as_of_date - timedelta(days=lookback_days)

        # Total events of this type attempted
        total_attempted = self.db.query(PendingSchedule).join(
            Event, PendingSchedule.event_ref_num == Event.ref_num
        ).filter(
            Event.event_type == event_type,
            PendingSchedule.created_at >= lookback_start,
            PendingSchedule.created_at < as_of_date
        ).count()

        # Successful schedules
        successful = self.db.query(Schedule).filter(
            Schedule.event_type == event_type,
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).count()

        # Success rate for this event type
        features['event_type_success_rate'] = successful / total_attempted if total_attempted > 0 else 0.8

        # Average time to schedule (days from creation to schedule)
        # Placeholder - would need created_at on Event model
        features['avg_days_to_schedule'] = 2.0

        # Bump frequency for this type
        bumped_events = self.db.query(PendingSchedule).join(
            Event, PendingSchedule.event_ref_num == Event.ref_num
        ).filter(
            Event.event_type == event_type,
            PendingSchedule.is_swap == True,
            PendingSchedule.created_at >= lookback_start,
            PendingSchedule.created_at < as_of_date
        ).count()
        features['event_type_bump_frequency'] = bumped_events / total_attempted if total_attempted > 0 else 0.1

        # Most common day of week for this type
        # Placeholder - would need aggregation query
        features['event_type_common_day_of_week'] = 2  # Wednesday

        return features

    def extract_club_history(self, club_num: str, as_of_date: datetime,
                            lookback_days: int = 180) -> Dict[str, Any]:
        """
        Extract historical scheduling patterns for a specific club.

        Args:
            club_num: Club number
            as_of_date: Calculate features as of this date
            lookback_days: How far back to look

        Returns:
            Dictionary of club historical features
        """
        Schedule = self.models['Schedule']
        Event = self.models['Event']

        features = {}
        lookback_start = as_of_date - timedelta(days=lookback_days)

        # Total events at this club
        total_events = self.db.query(Schedule).filter(
            Schedule.club_num == club_num,
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).count()
        features['club_total_events'] = total_events

        # Events per month
        months = lookback_days / 30.0
        features['club_events_per_month'] = total_events / months if months > 0 else 0.0

        # Unique employees worked at club
        unique_employees = self.db.query(Schedule.employee_id).filter(
            Schedule.club_num == club_num,
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).distinct().count()
        features['club_unique_employees'] = min(unique_employees / 10.0, 1.0)

        # Cancellation rate (placeholder - would need cancellation tracking)
        features['club_cancellation_rate'] = 0.05

        return features

    def extract_time_slot_patterns(self, time_slot: Optional[str], as_of_date: datetime,
                                   lookback_days: int = 90) -> Dict[str, Any]:
        """
        Extract historical patterns for specific time slots.

        Args:
            time_slot: Time slot string (e.g., "8a-11a")
            as_of_date: Calculate features as of this date
            lookback_days: How far back to look

        Returns:
            Dictionary of time slot features
        """
        Schedule = self.models['Schedule']

        features = {}
        lookback_start = as_of_date - timedelta(days=lookback_days)

        if not time_slot:
            features['time_slot_popularity'] = 0.5
            features['time_slot_success_rate'] = 0.85
            return features

        # Count assignments in this time slot
        # Note: This assumes schedule_time field exists
        assignments_in_slot = self.db.query(Schedule).filter(
            Schedule.schedule_time == time_slot,
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).count()

        # Total assignments
        total_assignments = self.db.query(Schedule).filter(
            Schedule.schedule_datetime >= lookback_start,
            Schedule.schedule_datetime < as_of_date
        ).count()

        # Popularity (proportion of assignments)
        features['time_slot_popularity'] = assignments_in_slot / total_assignments if total_assignments > 0 else 0.125

        # Success rate (placeholder - would need failure tracking)
        features['time_slot_success_rate'] = 0.85

        return features

    def extract_seasonal_patterns(self, as_of_date: datetime) -> Dict[str, Any]:
        """
        Extract seasonal and temporal patterns.

        Args:
            as_of_date: Current date for temporal calculations

        Returns:
            Dictionary of seasonal features
        """
        features = {}

        # Month of year
        features['month_of_year'] = as_of_date.month

        # Quarter
        features['quarter'] = (as_of_date.month - 1) // 3 + 1

        # Is end of month
        import calendar
        last_day = calendar.monthrange(as_of_date.year, as_of_date.month)[1]
        features['is_end_of_month'] = 1.0 if as_of_date.day >= last_day - 3 else 0.0

        # Is start of month
        features['is_start_of_month'] = 1.0 if as_of_date.day <= 3 else 0.0

        # Days until end of quarter
        quarter_end_month = features['quarter'] * 3
        quarter_end = datetime(as_of_date.year, quarter_end_month,
                              calendar.monthrange(as_of_date.year, quarter_end_month)[1])
        features['days_until_quarter_end'] = (quarter_end - as_of_date).days

        return features
