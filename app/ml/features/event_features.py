"""
Event feature extraction for ML models.

Extracts features about event characteristics, urgency, and context
for bumping decisions and feasibility prediction.
"""

from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class EventFeatureExtractor:
    """Extract event-related features for ML models."""

    def __init__(self, db_session, models):
        """
        Initialize feature extractor.

        Args:
            db_session: SQLAlchemy database session
            models: Model registry from get_models()
        """
        self.db = db_session
        self.models = models

    def extract_for_bumping(self, event, current_datetime: datetime) -> Dict[str, Any]:
        """
        Extract features for bumping decision optimization.

        Args:
            event: Event model instance (candidate to be bumped)
            current_datetime: Current datetime for temporal calculations

        Returns:
            Dictionary of features for bump cost prediction
        """
        features = {}

        # Event Urgency Features (8 features)
        if event.due_datetime:
            days_until_due = (event.due_datetime - current_datetime).days
            features['days_until_due'] = max(days_until_due, 0)
            features['is_urgent'] = 1.0 if days_until_due <= 3 else 0.0
        else:
            features['days_until_due'] = 14
            features['is_urgent'] = 0.0

        if event.start_datetime and event.due_datetime:
            window_size = (event.due_datetime - event.start_datetime).days
            features['window_size'] = max(window_size, 1)
            features['window_remaining_ratio'] = days_until_due / window_size if window_size > 0 else 0.0
        else:
            features['window_size'] = 14
            features['window_remaining_ratio'] = 0.5

        # Urgency score (inverse of days until due)
        features['urgency_score'] = 1.0 / (features['days_until_due'] + 1)

        # Times bumped count (if tracked)
        PendingSchedule = self.models['PendingSchedule']
        times_bumped = self.db.query(PendingSchedule).filter(
            PendingSchedule.event_ref_num == event.ref_num,
            PendingSchedule.is_swap == True,
            PendingSchedule.status.in_(['pending_approval', 'approved'])
        ).count()
        features['times_bumped_count'] = min(times_bumped / 3.0, 1.0)
        features['has_been_bumped'] = 1.0 if times_bumped > 0 else 0.0

        # Event priority
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

        # Assignment Context Features (6 features)
        Schedule = self.models['Schedule']
        schedule_record = self.db.query(Schedule).filter(
            Schedule.event_ref_num == event.ref_num
        ).first()

        if schedule_record:
            features['is_posted_schedule'] = 1.0
            days_since_scheduled = (current_datetime - schedule_record.schedule_datetime).days
            features['days_since_scheduled'] = min(days_since_scheduled / 14.0, 1.0)

            # Employee workload (simplified)
            employee_events = self.db.query(Schedule).filter(
                Schedule.employee_id == schedule_record.employee_id,
                Schedule.schedule_datetime >= current_datetime,
                Schedule.schedule_datetime < current_datetime + timedelta(days=7)
            ).count()
            features['employee_workload_percentile'] = min(employee_events / 6.0, 1.0)
        else:
            features['is_posted_schedule'] = 0.0
            features['days_since_scheduled'] = 0.0
            features['employee_workload_percentile'] = 0.5

        # Schedule Stability Features (6 features)
        # Has paired supervisor event
        if event.event_type == 'Core':
            paired_supervisor = self.db.query(Schedule).filter(
                Schedule.club_num == event.club_num,
                Schedule.event_type == 'Supervisor',
                Schedule.schedule_datetime == schedule_record.schedule_datetime if schedule_record else None
            ).first() is not None
            features['has_paired_supervisor_event'] = 1.0 if paired_supervisor else 0.0
        else:
            features['has_paired_supervisor_event'] = 0.0

        # Is rotation event
        rotation_types = ['Juicer', 'Digital Setup', 'Digital Refresh', 'Digital Teardown']
        features['is_rotation_event'] = 1.0 if event.event_type in rotation_types else 0.0
        features['would_leave_gap_in_rotation'] = features['is_rotation_event']

        # Employee consecutive days (if scheduled)
        if schedule_record:
            consecutive = self.db.query(Schedule).filter(
                Schedule.employee_id == schedule_record.employee_id,
                Schedule.schedule_datetime >= schedule_record.schedule_datetime - timedelta(days=3),
                Schedule.schedule_datetime <= schedule_record.schedule_datetime + timedelta(days=3)
            ).count()
            features['employee_consecutive_days_worked'] = min(consecutive / 5.0, 1.0)
        else:
            features['employee_consecutive_days_worked'] = 0.0

        # Event complexity (requires lead)
        features['requires_lead_only'] = 1.0 if event.event_type in ['Core', 'Supervisor'] else 0.0

        # Historical Patterns (placeholder - would need deeper analysis)
        features['historical_bump_frequency_for_event_type'] = 0.2
        features['avg_days_bumped_events_rescheduled'] = 3.0
        features['time_slot_scarcity'] = 0.5

        return features

    def extract_for_feasibility(self, event, current_datetime: datetime) -> Dict[str, Any]:
        """
        Extract features for schedule feasibility prediction.

        Args:
            event: Event model instance
            current_datetime: Current datetime

        Returns:
            Dictionary of features for feasibility prediction
        """
        features = {}

        # Event Characteristics (8 features)
        event_type_encoding = {
            'Juicer': 0,
            'Digital Setup': 1,
            'Digital Refresh': 2,
            'Freeosk': 3,
            'Digital Teardown': 4,
            'Core': 5,
            'Supervisor': 6,
            'Digitals': 7,
            'Other': 8
        }
        features['event_type_encoded'] = event_type_encoding.get(event.event_type, 8)

        # Estimated hours (3 hours default)
        features['estimated_hours'] = 3.0

        # Window size
        if event.start_datetime and event.due_datetime:
            window_days = (event.due_datetime - event.start_datetime).days
            features['window_size_days'] = max(window_days, 1)
        else:
            features['window_size_days'] = 14

        # Requires lead only
        features['requires_lead_only'] = 1.0 if event.event_type in ['Core', 'Supervisor'] else 0.0

        # Days until start
        if event.start_datetime:
            days_until_start = (event.start_datetime - current_datetime).days
            features['days_until_start'] = max(days_until_start, 0)
        else:
            features['days_until_start'] = 0

        # Days until due
        if event.due_datetime:
            days_until_due = (event.due_datetime - current_datetime).days
            features['days_until_due'] = max(days_until_due, 0)
        else:
            features['days_until_due'] = 14

        # Is rotation event
        rotation_types = ['Juicer', 'Digital Setup', 'Digital Refresh', 'Digital Teardown']
        features['is_rotation_event'] = 1.0 if event.event_type in rotation_types else 0.0

        # Club characteristics (placeholder)
        features['club_difficulty_score'] = 0.5

        # Employee Pool Availability (7 features)
        Employee = self.models['Employee']

        # Available leads
        leads = self.db.query(Employee).filter(
            Employee.role == 'Lead',
            Employee.is_active == True
        ).count()
        features['available_leads_count'] = leads

        # Available specialists
        specialists = self.db.query(Employee).filter(
            Employee.role == 'Specialist',
            Employee.is_active == True
        ).count()
        features['available_specialists_count'] = specialists

        # Total pool size
        total_pool = self.db.query(Employee).filter(
            Employee.is_active == True
        ).count()
        features['total_pool_size'] = total_pool

        # Pool capacity utilization
        Schedule = self.models['Schedule']
        if event.start_datetime:
            scheduled_in_window = self.db.query(Schedule).filter(
                Schedule.schedule_datetime >= event.start_datetime,
                Schedule.schedule_datetime <= event.due_datetime if event.due_datetime else event.start_datetime + timedelta(days=14)
            ).count()
            features['pool_capacity_utilization'] = scheduled_in_window / (total_pool * features['window_size_days']) if total_pool > 0 else 0.0
        else:
            features['pool_capacity_utilization'] = 0.3

        # Leads to events ratio
        features['leads_to_events_ratio'] = leads / max(total_pool, 1)

        # Available rotation employees
        rotation_employees = self.db.query(Employee).filter(
            Employee.role.in_(['Juicer', 'Lead', 'Specialist']),
            Employee.is_active == True
        ).count()
        features['rotation_employees_count'] = rotation_employees

        # Pool saturation
        features['pool_saturation'] = features['pool_capacity_utilization']

        # Scheduling Context (6 features)
        # Competing events same week
        if event.start_datetime:
            week_start = event.start_datetime - timedelta(days=event.start_datetime.weekday())
            week_end = week_start + timedelta(days=7)
            competing = self.db.query(self.models['Event']).filter(
                self.models['Event'].ref_num != event.ref_num,
                self.models['Event'].start_datetime >= week_start,
                self.models['Event'].start_datetime < week_end,
                self.models['Event'].is_cancelled == False
            ).count()
            features['competing_events_same_week'] = min(competing / 20.0, 1.0)
        else:
            features['competing_events_same_week'] = 0.3

        # Locked days in window (placeholder - would need locked day data)
        features['locked_days_in_window'] = 0

        # Available time slots (8 possible Core slots)
        features['available_time_slots'] = 8

        # Is holiday week
        features['is_holiday_week'] = 0.0

        # Scheduling density (events per day in window)
        features['scheduling_density'] = features['competing_events_same_week'] / max(features['window_size_days'], 1)

        # Historical success rate (placeholder)
        features['similar_events_success_rate'] = 0.85
        features['success_rate_this_club'] = 0.85

        return features
