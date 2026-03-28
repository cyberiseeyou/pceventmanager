"""
Employee Calloff Model
Tracks same-day and next-day employee calloffs with supervisor review workflow.
"""
from datetime import datetime


def create_calloff_models(db):
    """Factory function to create EmployeeCalloff and CalloffAttachment models."""

    class EmployeeCalloff(db.Model):
        """
        Tracks when an employee reports a same-day or next-day absence.

        Lifecycle: pending → excused / unexcused (set by supervisor).
        Auto-creates an EmployeeAttendance record with status 'called_in' on submission.
        """
        __tablename__ = 'employee_calloffs'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(
            db.String(50),
            db.ForeignKey('employees.id', ondelete='CASCADE'),
            nullable=False,
        )
        calloff_date = db.Column(db.Date, nullable=False)
        reason = db.Column(db.String(50), nullable=False)  # sick, family_emergency, personal, other
        notes = db.Column(db.Text, nullable=True)

        # Review workflow
        status = db.Column(db.String(20), nullable=False, default='pending')  # pending, excused, unexcused
        reviewed_by = db.Column(db.String(100), nullable=True)
        reviewed_at = db.Column(db.DateTime, nullable=True)
        supervisor_comments = db.Column(db.Text, nullable=True)

        # Linked attendance record
        attendance_id = db.Column(db.Integer, db.ForeignKey('employee_attendance.id'), nullable=True)

        # Timestamps
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        notified_at = db.Column(db.DateTime, nullable=True)

        # Reason constants
        REASON_SICK = 'sick'
        REASON_FAMILY_EMERGENCY = 'family_emergency'
        REASON_PERSONAL = 'personal'
        REASON_OTHER = 'other'
        VALID_REASONS = [REASON_SICK, REASON_FAMILY_EMERGENCY, REASON_PERSONAL, REASON_OTHER]

        REASON_LABELS = {
            REASON_SICK: 'Sick / Illness',
            REASON_FAMILY_EMERGENCY: 'Family Emergency',
            REASON_PERSONAL: 'Personal',
            REASON_OTHER: 'Other',
        }

        # Status constants
        STATUS_PENDING = 'pending'
        STATUS_EXCUSED = 'excused'
        STATUS_UNEXCUSED = 'unexcused'
        VALID_STATUSES = [STATUS_PENDING, STATUS_EXCUSED, STATUS_UNEXCUSED]

        __table_args__ = (
            db.UniqueConstraint('employee_id', 'calloff_date', name='uq_calloff_employee_date'),
            db.Index('idx_calloff_status_created', 'status', 'created_at'),
            db.Index('idx_calloff_employee_created', 'employee_id', 'created_at'),
        )

        # Relationships
        employee = db.relationship('Employee', backref='calloffs', lazy=True)
        attendance = db.relationship('EmployeeAttendance', backref='calloff', lazy=True)
        attachments = db.relationship('CalloffAttachment', backref='calloff', lazy=True, cascade='all, delete-orphan')

        def to_dict(self, include_attachments=False):
            result = {
                'id': self.id,
                'employee_id': self.employee_id,
                'employee_name': self.employee.name if self.employee else None,
                'calloff_date': self.calloff_date.isoformat() if self.calloff_date else None,
                'reason': self.reason,
                'reason_label': self.REASON_LABELS.get(self.reason, self.reason),
                'notes': self.notes,
                'status': self.status,
                'reviewed_by': self.reviewed_by,
                'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
                'supervisor_comments': self.supervisor_comments,
                'created_at': self.created_at.isoformat() if self.created_at else None,
            }
            if include_attachments:
                result['attachments'] = [a.to_dict() for a in self.attachments]
            return result

        def __repr__(self):
            return f'<EmployeeCalloff {self.id}: {self.employee_id} on {self.calloff_date} ({self.reason}) [{self.status}]>'

    class CalloffAttachment(db.Model):
        """File attachment linked to a calloff (doctor's notes, photos, etc.)."""
        __tablename__ = 'calloff_attachments'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        calloff_id = db.Column(
            db.Integer,
            db.ForeignKey('employee_calloffs.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        )
        filename = db.Column(db.String(255), nullable=False)
        file_path = db.Column(db.String(500), nullable=False)
        file_type = db.Column(db.String(100), nullable=True)
        uploaded_by = db.Column(db.String(100), nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        def to_dict(self):
            return {
                'id': self.id,
                'calloff_id': self.calloff_id,
                'filename': self.filename,
                'file_type': self.file_type,
                'uploaded_by': self.uploaded_by,
                'created_at': self.created_at.isoformat() if self.created_at else None,
            }

        def __repr__(self):
            return f'<CalloffAttachment {self.id}: {self.filename}>'

    return EmployeeCalloff, CalloffAttachment
