"""
Simplified employee feature extraction that matches actual database schema.

This version uses only features that exist in the actual schema:
- Employee: job_title, is_supervisor, created_at, is_active
- Schedule: via relationship to Event for event_type
- Event: event_type, due_datetime, start_datetime
- PendingSchedule: status, schedule_datetime
"""

from datetime import datetime, timedelta
from typing import Dict, Any
import logging
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)


class SimpleEmployeeFeatureExtractor:
    """Extract basic employee features using actual database schema."""

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
        Extract simple features for employee-event pair.

        Args:
            employee: Employee model instance
            event: Event model instance
            schedule_datetime: Proposed schedule datetime

        Returns:
            Dictionary of features with numeric values
        """
        features = {}
        Schedule = self.models['Schedule']
        PendingSchedule = self.models['PendingSchedule']
        Event = self.models['Event']

        try:
            # Historical performance (simple counts)
            thirty_days_ago = schedule_datetime - timedelta(days=30)

            recent_schedules = self.db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.schedule_datetime >= thirty_days_ago,
                Schedule.schedule_datetime < schedule_datetime
            ).count()
            features['events_last_30_days'] = min(recent_schedules / 10.0, 1.0)

            ninety_days_ago = schedule_datetime - timedelta(days=90)
            long_term_schedules = self.db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.schedule_datetime >= ninety_days_ago,
                Schedule.schedule_datetime < schedule_datetime
            ).count()
            features['events_last_90_days'] = min(long_term_schedules / 30.0, 1.0)

            # Workload features
            week_start = schedule_datetime - timedelta(days=schedule_datetime.weekday())
            week_end = week_start + timedelta(days=7)

            events_this_week = self.db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.schedule_datetime >= week_start,
                Schedule.schedule_datetime < week_end
            ).count()

            pending_this_week = self.db.query(PendingSchedule).filter(
                PendingSchedule.employee_id == employee.id,
                PendingSchedule.status.in_(['api_submitted', 'proposed']),
                PendingSchedule.schedule_datetime >= week_start,
                PendingSchedule.schedule_datetime < week_end
            ).count()

            total_this_week = events_this_week + pending_this_week
            features['workload_this_week'] = min(total_this_week / 6.0, 1.0)

            # Event context features
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
            features['event_priority'] = priority_map.get(event.event_type, 0.5)

            if event.due_datetime:
                days_until_due = (event.due_datetime - schedule_datetime).days
                features['days_until_due'] = min(max(days_until_due, 0) / 14.0, 1.0)
            else:
                features['days_until_due'] = 0.5

            # Temporal features
            features['day_of_week'] = schedule_datetime.weekday() / 6.0
            features['is_weekend'] = 1.0 if schedule_datetime.weekday() >= 5 else 0.0

            # Employee experience (has worked this event type before)
            # Need to join with Event to access event_type
            has_worked_type = self.db.query(Schedule).join(Event).filter(
                Schedule.employee_id == employee.id,
                Event.event_type == event.event_type
            ).first() is not None
            features['has_worked_event_type'] = 1.0 if has_worked_type else 0.0

            # Employee role features (from actual schema)
            features['is_supervisor'] = 1.0 if employee.is_supervisor else 0.0
            features['is_active'] = 1.0 if employee.is_active else 0.0

            # Employee experience (derived from created_at)
            if employee.created_at:
                days_employed = (schedule_datetime - employee.created_at).days
                features['days_employed'] = min(days_employed / 1825.0, 1.0)  # Normalize by 5 years
            else:
                features['days_employed'] = 0.5

            # Derived features
            features['success_rate_proxy'] = features['events_last_90_days']
            features['workload_status'] = features['workload_this_week']

        except Exception as e:
            logger.error(f"Error extracting features for employee {employee.id}: {e}", exc_info=True)
            # Return minimal feature set with defaults
            features = {
                'events_last_30_days': 0.5,
                'events_last_90_days': 0.5,
                'workload_this_week': 0.5,
                'event_priority': 0.5,
                'days_until_due': 0.5,
                'day_of_week': 0.5,
                'is_weekend': 0.0,
                'has_worked_event_type': 0.0,
                'is_supervisor': 0.0,
                'is_active': 1.0,
                'days_employed': 0.5,
                'success_rate_proxy': 0.5,
                'workload_status': 0.5
            }

        return features
