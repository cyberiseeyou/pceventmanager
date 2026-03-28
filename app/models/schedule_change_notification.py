"""
ScheduleChangeNotification model - tracks schedule changes sent to employees
"""
from datetime import datetime


def create_schedule_change_notification_model(db):
    """Factory function to create ScheduleChangeNotification model with db instance"""

    class ScheduleChangeNotification(db.Model):
        """
        Tracks notifications sent to specialists/leads when their schedule
        is changed within 7 days of today.

        Change types:
            event_added - New event assigned to employee
            event_removed - Event removed from employee's schedule
            time_changed - Event time was changed
            employee_swapped_in - Employee was assigned (replacing someone else)
            employee_swapped_out - Employee was removed (replaced by someone else)
        """
        __tablename__ = 'schedule_change_notifications'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)

        # What changed
        change_type = db.Column(db.String(30), nullable=False)

        # Event context (no store/club numbers)
        event_type = db.Column(db.String(50), nullable=False)
        event_date = db.Column(db.Date, nullable=False)

        # Human-readable description
        description = db.Column(db.Text, nullable=False)

        # JSON with before/after values for programmatic use
        change_details = db.Column(db.Text, nullable=True)

        # Read tracking
        is_read = db.Column(db.Boolean, default=False, nullable=False)
        read_at = db.Column(db.DateTime, nullable=True)

        # Push delivery tracking
        push_sent = db.Column(db.Boolean, default=False, nullable=False)
        push_sent_at = db.Column(db.DateTime, nullable=True)

        # Metadata
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        triggered_by = db.Column(db.String(100), nullable=True)

        __table_args__ = (
            db.Index('idx_scn_employee_read', 'employee_id', 'is_read'),
            db.Index('idx_scn_employee_created', 'employee_id', 'created_at'),
            db.Index('idx_scn_push_pending', 'push_sent', 'created_at'),
        )

        def to_dict(self):
            """Serialize for API responses"""
            return {
                'id': self.id,
                'employee_id': self.employee_id,
                'change_type': self.change_type,
                'event_type': self.event_type,
                'event_date': self.event_date.isoformat() if self.event_date else None,
                'description': self.description,
                'change_details': self.change_details,
                'is_read': self.is_read,
                'read_at': self.read_at.isoformat() if self.read_at else None,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'triggered_by': self.triggered_by,
            }

        def __repr__(self):
            return f'<ScheduleChangeNotification {self.id}: {self.change_type} for {self.employee_id}>'

    return ScheduleChangeNotification
