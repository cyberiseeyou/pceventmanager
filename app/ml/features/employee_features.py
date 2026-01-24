"""
Employee feature extraction for ML models.

Extracts features about employee historical performance, workload,
role, and temporal context for predictive scheduling.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class EmployeeFeatureExtractor:
    """Extract employee-related features for ML models."""

    def __init__(self, db_session, models):
        """
        Initialize feature extractor.

        Args:
            db_session: SQLAlchemy database session
            models: Model registry from get_models()
        """
        self.db = db_session
        self.models = models

    def extract(self, employee, event, schedule_datetime: datetime) -> Dict[str, Any]:
        """
        Extract all employee features for a given assignment scenario.

        Args:
            employee: Employee model instance
            event: Event model instance
            schedule_datetime: Proposed schedule datetime

        Returns:
            Dictionary of features with numeric values
        """
        features = {}

        # Historical Performance Features (10 features)
        features.update(self._extract_historical_performance(employee, schedule_datetime))

        # Current Workload Features (8 features)
        features.update(self._extract_current_workload(employee, schedule_datetime))

        # Role & Experience Features (5 features)
        features.update(self._extract_role_experience(employee))

        # Event Context Features (7 features)
        features.update(self._extract_event_context(employee, event, schedule_datetime))

        # Temporal Features (5 features)
        features.update(self._extract_temporal_features(schedule_datetime))

        return features

    def _extract_historical_performance(self, employee, as_of_date: datetime) -> Dict[str, float]:
        """Extract historical performance metrics."""
        Schedule = self.models['Schedule']
        PendingSchedule = self.models['PendingSchedule']
        EmployeeAttendance = self.models.get('EmployeeAttendance')

        features = {}

        # Success rate last 30 days
        thirty_days_ago = as_of_date - timedelta(days=30)
        recent_schedules = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.schedule_datetime >= thirty_days_ago,
            Schedule.schedule_datetime < as_of_date
        ).count()

        features['success_rate_last_30_days'] = min(recent_schedules / 10.0, 1.0) if recent_schedules > 0 else 0.5

        # Success rate last 90 days
        ninety_days_ago = as_of_date - timedelta(days=90)
        long_term_schedules = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.schedule_datetime >= ninety_days_ago,
            Schedule.schedule_datetime < as_of_date
        ).count()

        features['success_rate_last_90_days'] = min(long_term_schedules / 30.0, 1.0) if long_term_schedules > 0 else 0.5

        # Attendance metrics (if available)
        if EmployeeAttendance:
            try:
                attendance_records = self.db.query(EmployeeAttendance).filter(
                    EmployeeAttendance.employee_id == employee.id,
                    EmployeeAttendance.attendance_date >= thirty_days_ago.date(),
                    EmployeeAttendance.attendance_date < as_of_date.date()
                ).all()

                if attendance_records:
                    on_time_count = sum(1 for a in attendance_records if a.status == 'on_time')
                    features['attendance_on_time_rate'] = on_time_count / len(attendance_records)
                else:
                    features['attendance_on_time_rate'] = 0.9  # Neutral assumption
            except Exception:
                features['attendance_on_time_rate'] = 0.9  # Fallback if attendance not available
        else:
            features['attendance_on_time_rate'] = 0.9

        # Total events completed
        total_completed = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.schedule_datetime < as_of_date
        ).count()
        features['total_events_completed'] = min(total_completed / 100.0, 1.0)  # Normalize

        # Consecutive success streak
        recent_failed = self.db.query(PendingSchedule).filter(
            PendingSchedule.employee_id == employee.id,
            PendingSchedule.status == 'failed',
            PendingSchedule.created_at >= thirty_days_ago,
            PendingSchedule.created_at < as_of_date
        ).count()
        features['consecutive_success_streak'] = 1.0 if recent_failed == 0 else 0.5

        # Fill remaining performance features with defaults
        features['avg_event_duration_hours'] = 3.0  # Placeholder
        features['completion_rate'] = features['success_rate_last_90_days']
        features['cancellation_rate'] = 1.0 - features['success_rate_last_90_days']
        features['reschedule_rate'] = 0.1  # Placeholder
        features['late_arrival_rate'] = 1.0 - features['attendance_on_time_rate']

        return features

    def _extract_current_workload(self, employee, as_of_date: datetime) -> Dict[str, float]:
        """Extract current workload metrics."""
        Schedule = self.models['Schedule']
        PendingSchedule = self.models['PendingSchedule']

        features = {}

        # Events scheduled this week
        week_start = as_of_date - timedelta(days=as_of_date.weekday())
        week_end = week_start + timedelta(days=7)

        events_this_week = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.schedule_datetime >= week_start,
            Schedule.schedule_datetime < week_end
        ).count()

        pending_this_week = self.db.query(PendingSchedule).filter(
            PendingSchedule.employee_id == employee.id,
            PendingSchedule.status == 'pending_approval',
            PendingSchedule.schedule_datetime >= week_start,
            PendingSchedule.schedule_datetime < week_end
        ).count()

        total_this_week = events_this_week + pending_this_week
        features['events_scheduled_this_week'] = min(total_this_week / 6.0, 1.0)  # Normalize by max 6

        # Hours scheduled (estimated at 3 hours per event)
        features['hours_scheduled'] = min(total_this_week * 3.0 / 18.0, 1.0)  # Normalize by 18 hours

        # Workload status (0=low, 0.5=normal, 1.0=high)
        if total_this_week >= 5:
            features['workload_status'] = 1.0
        elif total_this_week >= 3:
            features['workload_status'] = 0.5
        else:
            features['workload_status'] = 0.0

        # Events in next 7 days
        future_events = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.schedule_datetime >= as_of_date,
            Schedule.schedule_datetime < as_of_date + timedelta(days=7)
        ).count()
        features['events_next_7_days'] = min(future_events / 6.0, 1.0)

        # Days since last assignment
        last_schedule = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.schedule_datetime < as_of_date
        ).order_by(Schedule.schedule_datetime.desc()).first()

        if last_schedule:
            days_since = (as_of_date - last_schedule.schedule_datetime).days
            features['days_since_last_assignment'] = min(days_since / 7.0, 1.0)
        else:
            features['days_since_last_assignment'] = 1.0

        # Fill remaining workload features
        features['consecutive_days_worked'] = min(total_this_week / 5.0, 1.0)
        features['avg_daily_hours'] = features['hours_scheduled'] / 7.0
        features['is_overloaded'] = 1.0 if total_this_week >= 6 else 0.0

        return features

    def _extract_role_experience(self, employee) -> Dict[str, float]:
        """Extract role and experience features."""
        features = {}

        # Role indicators
        features['is_lead'] = 1.0 if employee.role == 'Lead' else 0.0
        features['is_specialist'] = 1.0 if employee.role == 'Specialist' else 0.0
        features['is_juicer'] = 1.0 if employee.role == 'Juicer' else 0.0

        # Experience (if available)
        if hasattr(employee, 'years_experience') and employee.years_experience:
            features['years_experience'] = min(employee.years_experience / 10.0, 1.0)
        else:
            features['years_experience'] = 0.5  # Neutral assumption

        # Event type specialization (placeholder - would need historical analysis)
        features['event_type_specialization_score'] = 0.5

        return features

    def _extract_event_context(self, employee, event, schedule_datetime: datetime) -> Dict[str, float]:
        """Extract event context features."""
        features = {}

        # Event priority mapping
        priority_map = {
            'Juicer': 1.0,
            'Digital Setup': 0.9,
            'Digital Refresh': 0.8,
            'Freeosk': 0.7,
            'Digital Teardown': 0.6,
            'Core': 0.5,
            'Supervisor': 0.4,
            'Digitals': 0.3,
            'Other': 0.1
        }
        features['event_priority_level'] = priority_map.get(event.event_type, 0.5)

        # Days until due
        if event.due_datetime:
            days_until_due = (event.due_datetime - schedule_datetime).days
            features['days_until_due'] = min(days_until_due / 14.0, 1.0)  # Normalize by 2 weeks
        else:
            features['days_until_due'] = 0.5

        # Is rotation event
        rotation_types = ['Juicer', 'Digital Setup', 'Digital Refresh', 'Digital Teardown']
        features['is_rotation_event'] = 1.0 if event.event_type in rotation_types else 0.0

        # Time slot preference match (placeholder - would need preference data)
        features['time_slot_preference_match'] = 0.5

        # Event requires lead
        features['event_requires_lead'] = 1.0 if event.event_type in ['Core', 'Supervisor'] else 0.0

        # Window size
        if event.start_datetime and event.due_datetime:
            window_days = (event.due_datetime - event.start_datetime).days
            features['event_window_size_days'] = min(window_days / 14.0, 1.0)
        else:
            features['event_window_size_days'] = 0.5

        # Previously worked this event type
        Schedule = self.models['Schedule']
        has_worked_type = self.db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.event_type == event.event_type
        ).first() is not None
        features['has_worked_event_type'] = 1.0 if has_worked_type else 0.0

        return features

    def _extract_temporal_features(self, schedule_datetime: datetime) -> Dict[str, float]:
        """Extract temporal features."""
        features = {}

        # Day of week (0=Monday, 6=Sunday)
        features['day_of_week'] = schedule_datetime.weekday() / 6.0

        # Week of year
        features['week_of_year'] = schedule_datetime.isocalendar()[1] / 52.0

        # Is weekend
        features['is_weekend'] = 1.0 if schedule_datetime.weekday() >= 5 else 0.0

        # Season (0=winter, 0.25=spring, 0.5=summer, 0.75=fall)
        month = schedule_datetime.month
        if month in [12, 1, 2]:
            features['season'] = 0.0
        elif month in [3, 4, 5]:
            features['season'] = 0.25
        elif month in [6, 7, 8]:
            features['season'] = 0.5
        else:
            features['season'] = 0.75

        # Is holiday week (placeholder - would need holiday calendar)
        features['is_holiday_week'] = 0.0

        return features
