"""
Event model and related database schema
Represents scheduled work/visits that need to be assigned to employees
"""
from datetime import datetime


def create_event_model(db):
    """Factory function to create Event model with db instance"""

    class Event(db.Model):
        """
        Event model representing work visits/tasks to be scheduled

        Events are imported from external systems and scheduled to employees.
        They have date constraints (start_datetime to due_datetime) and specific
        requirements (event_type) that determine which employees can work them.
        """
        __tablename__ = 'events'

        # Default durations (in minutes) for each event type
        DEFAULT_DURATIONS = {
            'Core': 390,              # 6.5 hours
            'Juicer Production': 540, # 9 hours
            'Juicer Survey': 15,      # 15 minutes
            'Juicer Deep Clean': 240, # 4 hours
            'Supervisor': 5,          # 5 minutes
            'Digital Setup': 15,      # 15 minutes
            'Digital Refresh': 15,    # 15 minutes
            'Digital Teardown': 15,   # 15 minutes
            'Freeosk': 15,            # 15 minutes
            'Other': 15               # 15 minutes
        }

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        project_name = db.Column(db.Text, nullable=False)
        project_ref_num = db.Column(db.Integer, nullable=False, unique=True)
        location_mvid = db.Column(db.Text)
        store_number = db.Column(db.Integer)
        store_name = db.Column(db.Text)
        start_datetime = db.Column(db.DateTime, nullable=False)
        due_datetime = db.Column(db.DateTime, nullable=False)
        estimated_time = db.Column(db.Integer)  # Duration in minutes
        is_scheduled = db.Column(db.Boolean, nullable=False, default=False)
        event_type = db.Column(db.String(20), nullable=False, default='Other')
        condition = db.Column(db.String(20), default='Unstaffed')

        # Sync fields for API integration
        external_id = db.Column(db.String(100), unique=True)
        last_synced = db.Column(db.DateTime)
        sync_status = db.Column(db.String(20), default='pending')

        # Sales tools document URL for Core events
        sales_tools_url = db.Column(db.Text)

        # EDR (Event Detail Report) status from Walmart API
        # Stores the status code from Walmart EDR system (e.g., 'Cancelled', 'Active', 'Completed')
        # This is separate from the local 'condition' field which tracks internal workflow status
        edr_status = db.Column(db.String(50), nullable=True)
        edr_status_updated = db.Column(db.DateTime, nullable=True)

        # Auto-scheduler: Link supervisor events to their corresponding core event
        parent_event_ref_num = db.Column(
            db.Integer,
            db.ForeignKey('events.project_ref_num'),
            nullable=True
        )

        __table_args__ = (
            # Index for filtering scheduled/unscheduled events
            db.Index('idx_events_scheduled', 'is_scheduled', 'condition'),

            # Index for date range queries (start/due date filtering)
            db.Index('idx_events_date_range', 'start_datetime', 'due_datetime'),

            # Index for event type filtering
            db.Index('idx_events_type', 'event_type'),

            # Index for location-based queries
            db.Index('idx_events_location', 'location_mvid'),

            # Index for sync operations
            db.Index('idx_events_sync', 'sync_status'),
        )

        def detect_event_type(self):
            """
            Automatically detect event type based on project name and estimated time.

            Event types determine which employees can be assigned:
            - Core: Standard events, all employees (390 minutes / 6.5 hours)
            - Digital Setup: Digital display setup, requires supervisor/lead
            - Digital Refresh: Digital display refresh, requires supervisor/lead
            - Digital Teardown: Digital display teardown, requires supervisor/lead
            - Juicer Production: Juice bar production (juice + Production-SPCLTY)
            - Juicer Survey: Juice bar surveys (juice + Survey-SPCLTY)
            - Juicer Deep Clean: Deep cleaning (Juicer Deep Clean)
            - Supervisor: Requires supervisor/lead (5 minutes)
            - Freeosk: Kiosk events, requires supervisor/lead
            - Other: Catch-all for unclassified events

            Detection Priority:
            1. Keyword matching in project_name (primary method)
            2. Fallback to estimated_time for events with unique durations:
               - 390 minutes -> Core
               - 5 minutes -> Supervisor
            This fallback helps when event names are truncated and keywords are cut off.

            Returns:
                str: Detected event type
            """
            detected_type = 'Other'
            
            if self.project_name:
                project_name_upper = self.project_name.upper()

                if 'CORE' in project_name_upper:
                    detected_type = 'Core'
                # Digital types - use generic "Digitals" category
                # (specific types like Digital Setup/Refresh/Teardown can be set via manual overrides)
                elif 'DIGITAL' in project_name_upper:
                    detected_type = 'Digitals'
                # Juicer types - check specific patterns
                elif 'JUICER DEEP CLEAN' in project_name_upper:
                    detected_type = 'Juicer Deep Clean'
                elif 'JUICE' in project_name_upper and 'PRODUCTION-SPCLTY' in project_name_upper:
                    detected_type = 'Juicer Production'
                elif 'JUICE' in project_name_upper and 'SURVEY-SPCLTY' in project_name_upper:
                    detected_type = 'Juicer Survey'
                elif 'SUPERVISOR' in project_name_upper or 'V2-SUPER' in project_name_upper or 'SUPERVISO' in project_name_upper:
                    detected_type = 'Supervisor'
                elif 'FREEOSK' in project_name_upper:
                    detected_type = 'Freeosk'
            
            # Fallback: Use estimated_time to detect event type when keyword matching fails
            # This handles cases where event names are truncated and keywords are cut off
            if detected_type == 'Other' and self.estimated_time:
                # Core events have duration of 360 or 390 minutes (6-6.5 hours)
                if self.estimated_time in (360, 390):
                    detected_type = 'Core'
                # Supervisor events have unique duration of 5 minutes
                elif self.estimated_time == 5:
                    detected_type = 'Supervisor'
                # Juicer Production has durations of 480 (8hr) or 540 (9hr) minutes
                elif self.estimated_time in (480, 540):
                    detected_type = 'Juicer Production'
                # Juicer Deep Clean has unique duration of 240 minutes (4 hours)
                elif self.estimated_time == 240:
                    detected_type = 'Juicer Deep Clean'
            
            return detected_type

        @classmethod
        def get_default_duration(cls, event_type):
            """
            Get the default duration in minutes for a given event type

            Args:
                event_type (str): The event type

            Returns:
                int: Duration in minutes
            """
            return cls.DEFAULT_DURATIONS.get(event_type, 15)

        def set_default_duration(self):
            """
            Set the estimated_time field to the default duration for this event's type

            This should be called when creating new events or when event_type changes.
            Only sets the duration if estimated_time is not already set.
            """
            if not self.estimated_time:
                self.estimated_time = self.get_default_duration(self.event_type)

        def calculate_end_datetime(self, start_datetime):
            """
            Calculate the end datetime based on start datetime and estimated duration

            Args:
                start_datetime (datetime): The start datetime of the event

            Returns:
                datetime: The calculated end datetime
            """
            from datetime import timedelta
            duration_minutes = self.estimated_time or self.get_default_duration(self.event_type)
            return start_datetime + timedelta(minutes=duration_minutes)

        def __repr__(self):
            return f'<Event {self.project_ref_num}: {self.project_name}>'

    return Event
