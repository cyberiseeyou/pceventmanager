"""
Employee availability models
Tracks when employees can/cannot work
"""
from datetime import datetime


def create_availability_models(db):
    """Factory function to create availability models with db instance"""

    class EmployeeWeeklyAvailability(db.Model):
        """
        Weekly availability pattern for employees
        Defines which days of the week an employee typically works
        """
        __tablename__ = 'employee_weekly_availability'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)
        monday = db.Column(db.Boolean, nullable=False, default=True)
        tuesday = db.Column(db.Boolean, nullable=False, default=True)
        wednesday = db.Column(db.Boolean, nullable=False, default=True)
        thursday = db.Column(db.Boolean, nullable=False, default=True)
        friday = db.Column(db.Boolean, nullable=False, default=True)
        saturday = db.Column(db.Boolean, nullable=False, default=True)
        sunday = db.Column(db.Boolean, nullable=False, default=True)

        __table_args__ = (
            db.UniqueConstraint('employee_id', name='unique_employee_weekly_availability'),
        )

        def __repr__(self):
            return f'<EmployeeWeeklyAvailability {self.employee_id}>'

    class EmployeeAvailability(db.Model):
        """
        Specific date availability for employees
        Overrides weekly pattern for specific dates
        """
        __tablename__ = 'employee_availability'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)
        date = db.Column(db.Date, nullable=False)
        is_available = db.Column(db.Boolean, nullable=False, default=True)
        reason = db.Column(db.String(200))  # Optional reason for unavailability

        __table_args__ = (
            db.UniqueConstraint('employee_id', 'date', name='unique_employee_date_availability'),
        )

        def __repr__(self):
            status = "available" if self.is_available else "unavailable"
            return f'<EmployeeAvailability {self.employee_id} on {self.date}: {status}>'

    class EmployeeTimeOff(db.Model):
        """
        Time off requests and scheduled absences
        Employees are unavailable during these date ranges
        """
        __tablename__ = 'employee_time_off'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)
        start_date = db.Column(db.Date, nullable=False)
        end_date = db.Column(db.Date, nullable=False)
        reason = db.Column(db.String(200))
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        __table_args__ = (
            db.Index('idx_employee_time_off_dates', 'employee_id', 'start_date', 'end_date'),
        )

        def __repr__(self):
            return f'<EmployeeTimeOff {self.employee_id}: {self.start_date} to {self.end_date}>'

    class EmployeeAvailabilityOverride(db.Model):
        """
        Temporary weekly availability overrides for employees
        Overrides the standard weekly availability pattern for a specific date range

        Example: Employee normally works Mon-Fri, but for 3 weeks they can only work Tue/Thu
        After the end_date, the override automatically expires and standard weekly pattern resumes

        Priority: Overrides are checked FIRST, then weekly availability pattern
        FR32: Scenario 2 - Temporary Availability Change
        """
        __tablename__ = 'employee_availability_overrides'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)
        start_date = db.Column(db.Date, nullable=False)
        end_date = db.Column(db.Date, nullable=False)
        monday = db.Column(db.Boolean, nullable=True)  # NULL = no override for this day
        tuesday = db.Column(db.Boolean, nullable=True)
        wednesday = db.Column(db.Boolean, nullable=True)
        thursday = db.Column(db.Boolean, nullable=True)
        friday = db.Column(db.Boolean, nullable=True)
        saturday = db.Column(db.Boolean, nullable=True)
        sunday = db.Column(db.Boolean, nullable=True)
        reason = db.Column(db.String(500))  # Why the temporary change (e.g., "College class schedule")
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        created_by = db.Column(db.String(100))  # User who created the override

        __table_args__ = (
            db.Index('idx_employee_override_dates', 'employee_id', 'start_date', 'end_date'),
            db.CheckConstraint('end_date >= start_date', name='check_override_date_range'),
        )

        def __repr__(self):
            return f'<EmployeeAvailabilityOverride {self.employee_id}: {self.start_date} to {self.end_date}>'

        def is_active(self, check_date=None):
            """
            Check if this override is currently active

            Args:
                check_date: Date to check (default: today)

            Returns:
                bool: True if override is active for the given date
            """
            if check_date is None:
                check_date = datetime.utcnow().date()
            return self.start_date <= check_date <= self.end_date

        def get_day_availability(self, day_of_week):
            """
            Get availability for a specific day of the week

            Args:
                day_of_week: 0=Monday, 1=Tuesday, ... 6=Sunday

            Returns:
                bool or None: True if available, False if not, None if no override for this day
            """
            day_map = {
                0: self.monday,
                1: self.tuesday,
                2: self.wednesday,
                3: self.thursday,
                4: self.friday,
                5: self.saturday,
                6: self.sunday
            }
            return day_map.get(day_of_week)

    return EmployeeWeeklyAvailability, EmployeeAvailability, EmployeeTimeOff, EmployeeAvailabilityOverride
