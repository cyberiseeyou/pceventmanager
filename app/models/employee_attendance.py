"""
Employee Attendance Model
Tracks when employees showed up for scheduled events
"""
from datetime import datetime


def create_employee_attendance_model(db):
    """
    Factory function to create EmployeeAttendance model with database instance

    Args:
        db: SQLAlchemy database instance

    Returns:
        EmployeeAttendance: Model class for attendance tracking
    """

    class EmployeeAttendance(db.Model):
        """
        Employee Attendance model representing daily attendance records for employees

        Tracks whether employees showed up on time, late, called in, no-call-no-showed, or had an excused absence.
        One attendance record per employee per day (enforced by UNIQUE constraint on employee_id + attendance_date).

        This is separate from event scheduling to allow events to be rescheduled without affecting attendance data.

        Attributes:
            id: Primary key
            employee_id: Foreign key to employees table
            attendance_date: Date of attendance (UNIQUE with employee_id)
            status: Attendance status (on_time, late, called_in, no_call_no_show, excused_absence)
            notes: Optional notes about attendance (e.g., "Traffic delay, 15 min late" or "Emergency - family illness")
            recorded_by: Username of supervisor who recorded attendance
            recorded_at: Timestamp when record was created
            updated_at: Timestamp when record was last updated
        """
        __tablename__ = 'employee_attendance'

        # Primary key
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)

        # Foreign keys
        employee_id = db.Column(
            db.String(50),
            db.ForeignKey('employees.id', ondelete='CASCADE'),
            nullable=False,
            index=True
        )

        # Attendance data
        attendance_date = db.Column(db.Date, nullable=False, index=True)
        status = db.Column(
            db.String(20),
            nullable=False,
            index=True
        )  # on_time, late, called_in, no_call_no_show
        notes = db.Column(db.Text, nullable=True)

        # Audit fields
        recorded_by = db.Column(db.String(100), nullable=True)
        recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

        # Table constraints
        __table_args__ = (
            db.UniqueConstraint('employee_id', 'attendance_date', name='uix_employee_date'),
        )

        # Relationships
        employee = db.relationship('Employee', backref='attendance_records', lazy=True)

        # Status constants
        STATUS_ON_TIME = 'on_time'
        STATUS_LATE = 'late'
        STATUS_CALLED_IN = 'called_in'
        STATUS_NO_CALL_NO_SHOW = 'no_call_no_show'
        STATUS_EXCUSED_ABSENCE = 'excused_absence'

        VALID_STATUSES = [STATUS_ON_TIME, STATUS_LATE, STATUS_CALLED_IN, STATUS_NO_CALL_NO_SHOW, STATUS_EXCUSED_ABSENCE]

        STATUS_LABELS = {
            STATUS_ON_TIME: '🟢 On-Time',
            STATUS_LATE: '🟡 Late',
            STATUS_CALLED_IN: '📞 Called-In',
            STATUS_NO_CALL_NO_SHOW: '🔴 No-Call-No-Show',
            STATUS_EXCUSED_ABSENCE: '🔵 Excused Absence'
        }

        def to_dict(self):
            """
            Convert attendance record to dictionary for JSON serialization

            Returns:
                dict: Attendance record as dictionary
            """
            return {
                'id': self.id,
                'employee_id': self.employee_id,
                'employee_name': self.employee.name if self.employee else None,
                'attendance_date': self.attendance_date.isoformat() if self.attendance_date else None,
                'status': self.status,
                'status_label': self.STATUS_LABELS.get(self.status, self.status),
                'notes': self.notes,
                'recorded_by': self.recorded_by,
                'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }

        def __repr__(self):
            """String representation of attendance record"""
            return f'<EmployeeAttendance {self.id}: {self.employee_id} on {self.attendance_date} - {self.status}>'

    return EmployeeAttendance
