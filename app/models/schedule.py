"""
Schedule model - links events to employees with specific datetime
"""
from datetime import datetime
import sqlalchemy as sa


def create_schedule_model(db):
    """Factory function to create Schedule model with db instance"""

    class Schedule(db.Model):
        """
        Schedule model representing an event assigned to an employee

        This is the core scheduling entity that links Events and Employees
        with a specific datetime for when the work should be performed.
        """
        __tablename__ = 'schedules'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        event_ref_num = db.Column(db.Integer, db.ForeignKey('events.project_ref_num'), nullable=False)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)
        schedule_datetime = db.Column(db.DateTime, nullable=False)

        # Sync fields for API integration
        external_id = db.Column(db.String(100), unique=True)
        last_synced = db.Column(db.DateTime)
        sync_status = db.Column(db.String(20), default='pending')

        # Shift block assignment (1-8) for Core events
        # Assigned when EDR is generated or during scheduling
        # Cleared when event status becomes "Submitted"
        shift_block = db.Column(db.Integer, nullable=True)
        shift_block_assigned_at = db.Column(db.DateTime, nullable=True)

        # Outcome tracking for ML training data
        was_completed = db.Column(db.Boolean, default=False, server_default=sa.text('0'))
        was_swapped = db.Column(db.Boolean, default=False, server_default=sa.text('0'))
        was_no_show = db.Column(db.Boolean, default=False, server_default=sa.text('0'))
        completion_notes = db.Column(db.Text, nullable=True)
        solver_type = db.Column(db.String(20), nullable=True)  # 'cpsat', 'greedy', 'manual'

        __table_args__ = (
            # Existing index
            db.Index('idx_schedules_date', 'schedule_datetime'),

            # NEW: Composite index for common query pattern (employee + date)
            db.Index('idx_schedules_employee_date', 'employee_id', 'schedule_datetime'),

            # NEW: Index for event lookups
            db.Index('idx_schedules_event', 'event_ref_num'),

            # NEW: Index for sync status queries
            db.Index('idx_schedules_sync', 'sync_status', 'last_synced'),
        )

        # Relationships
        employee = db.relationship('Employee', backref='schedules', lazy=True)
        event = db.relationship('Event', foreign_keys=[event_ref_num],
                               primaryjoin="Schedule.event_ref_num==Event.project_ref_num",
                               backref='schedules', lazy=True)

        def __repr__(self):
            return f'<Schedule {self.id}: Event {self.event_ref_num} -> Employee {self.employee_id}>'

    return Schedule
