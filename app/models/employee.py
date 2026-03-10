"""
Employee model and related database schema
Represents staff members who can be scheduled for events
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


def create_employee_model(db):
    """Factory function to create Employee model with db instance"""

    class Employee(db.Model):
        """
        Employee model representing schedulable staff members

        Attributes:
            id: Unique employee identifier (external system ID)
            name: Employee full name
            email: Contact email
            phone: Contact phone number
            is_active: Whether employee is currently active
            is_supervisor: Whether employee has supervisor privileges
            job_title: Employee's job role
            adult_beverage_trained: Required for certain event types
            juicer_trained: Can work Juicer events even if not a Juicer Barista
            external_id: ID in external scheduling system
            last_synced: Last successful sync timestamp
            sync_status: Current sync state (pending/synced/failed)
        """
        __tablename__ = 'employees'

        id = db.Column(db.String(50), primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        email = db.Column(db.String(120), unique=True)
        phone = db.Column(db.String(20))
        is_active = db.Column(db.Boolean, nullable=False, default=True)
        is_supervisor = db.Column(db.Boolean, nullable=False, default=False)
        job_title = db.Column(db.String(50), nullable=False, default='Event Specialist')
        adult_beverage_trained = db.Column(db.Boolean, nullable=False, default=False)
        juicer_trained = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        termination_date = db.Column(db.Date, nullable=True)  # FR34: Track employee termination date

        # Crossmark/MV Retail import fields
        mv_retail_employee_number = db.Column(db.String(50), nullable=True)
        crossmark_employee_id = db.Column(db.String(50), nullable=True, unique=True)

        # Employee self-service login fields
        pin_hash = db.Column(db.String(256), nullable=True)
        has_account = db.Column(db.Boolean, nullable=False, default=False)

        # Sync fields for API integration
        external_id = db.Column(db.String(100), unique=True)
        last_synced = db.Column(db.DateTime)
        sync_status = db.Column(db.String(20), default='pending')

        __table_args__ = (
            # Index for active employee queries
            db.Index('idx_employees_active', 'is_active'),

            # Index for job title filtering
            db.Index('idx_employees_job_title', 'job_title'),

            # Index for supervisor queries
            db.Index('idx_employees_supervisor', 'is_supervisor'),

            # Index for termination date queries
            db.Index('idx_employees_termination', 'termination_date'),

            # Index for case-insensitive name lookups (for duplicate detection)
            db.Index('ix_employee_name_lower', db.func.lower(db.Column('name'))),

            # Index for MV Retail employee number
            db.Index('ix_employees_mv_retail_employee_number', 'mv_retail_employee_number'),
        )

        def can_work_event_type(self, event_type):
            """
            Check if employee can work events of the given type based on job title

            Business Rules:
            - Supervisor, Freeosk, Digital Setup/Refresh/Teardown: Requires Club Supervisor or Lead Event Specialist
            - Juicer Production/Survey/Deep Clean: Requires Club Supervisor, Juicer Barista, or Juicer Trained
            - Core, Other: All employees can work these

            Args:
                event_type (str): Type of event to check

            Returns:
                bool: True if employee is qualified for this event type
            """
            # Restricted event types that require specific roles
            if event_type in ['Supervisor', 'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh', 'Digital Teardown']:
                return self.job_title in ['Club Supervisor', 'Lead Event Specialist']
            elif event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
                # Allow Club Supervisor, Juicer Barista, or employees marked as Juicer Trained
                return (self.job_title in ['Club Supervisor', 'Juicer Barista'] or
                        bool(self.juicer_trained))

            # All employees can work other event types (Core, Other)
            return True

        def set_pin(self, pin):
            """Hash and store a PIN for employee self-service login."""
            self.pin_hash = generate_password_hash(str(pin))
            self.has_account = True

        def check_pin(self, pin):
            """Verify PIN against stored hash."""
            if not self.pin_hash:
                return False
            return check_password_hash(self.pin_hash, str(pin))

        @property
        def role(self):
            """Map job_title to a simplified role for access control."""
            if self.job_title == 'Club Supervisor' or self.is_supervisor:
                return 'supervisor'
            elif self.job_title == 'Lead Event Specialist':
                return 'lead'
            else:
                return 'specialist'

        def __repr__(self):
            return f'<Employee {self.id}: {self.name}>'

    return Employee
