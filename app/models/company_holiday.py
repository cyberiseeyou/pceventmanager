"""
Company Holiday Model
Manages company-wide holidays/closed days when no one is working
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, Text


def create_company_holiday_model(db):
    """
    Factory function to create CompanyHoliday model

    Args:
        db: SQLAlchemy database instance

    Returns:
        CompanyHoliday model class
    """

    class CompanyHoliday(db.Model):
        __tablename__ = 'company_holidays'

        id = Column(Integer, primary_key=True)
        name = Column(String(100), nullable=False)  # e.g., "Christmas", "Thanksgiving"
        holiday_date = Column(Date, nullable=False)
        is_recurring = Column(Boolean, default=False)  # True if it repeats yearly
        recurring_month = Column(Integer, nullable=True)  # 1-12 for recurring holidays
        recurring_day = Column(Integer, nullable=True)  # Day of month for recurring
        recurring_rule = Column(String(100), nullable=True)  # e.g., "4th Thursday of November"
        notes = Column(Text, nullable=True)
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        created_by = Column(String(100), nullable=True)

        def to_dict(self):
            """Convert to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'name': self.name,
                'holiday_date': self.holiday_date.isoformat() if self.holiday_date else None,
                'is_recurring': self.is_recurring,
                'recurring_month': self.recurring_month,
                'recurring_day': self.recurring_day,
                'recurring_rule': self.recurring_rule,
                'notes': self.notes,
                'is_active': self.is_active,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }

        @classmethod
        def is_holiday(cls, check_date):
            """
            Check if a given date is a company holiday

            Args:
                check_date: date object to check

            Returns:
                CompanyHoliday object if it's a holiday, None otherwise
            """
            if isinstance(check_date, datetime):
                check_date = check_date.date()

            # Check for exact date match (for non-recurring or current year recurring)
            holiday = cls.query.filter(
                cls.holiday_date == check_date,
                cls.is_active == True
            ).first()

            if holiday:
                return holiday

            # Check for recurring holidays by month/day
            recurring = cls.query.filter(
                cls.is_recurring == True,
                cls.recurring_month == check_date.month,
                cls.recurring_day == check_date.day,
                cls.is_active == True
            ).first()

            return recurring

        @classmethod
        def get_holidays_in_range(cls, start_date, end_date):
            """
            Get all holidays within a date range

            Args:
                start_date: Start of date range
                end_date: End of date range

            Returns:
                List of dates that are holidays
            """
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            holiday_dates = []

            # Get explicit holidays in range
            explicit_holidays = cls.query.filter(
                cls.holiday_date >= start_date,
                cls.holiday_date <= end_date,
                cls.is_active == True
            ).all()

            for h in explicit_holidays:
                holiday_dates.append(h.holiday_date)

            # Get recurring holidays and check each year in range
            recurring_holidays = cls.query.filter(
                cls.is_recurring == True,
                cls.is_active == True
            ).all()

            for h in recurring_holidays:
                if h.recurring_month and h.recurring_day:
                    # Check each year in the range
                    for year in range(start_date.year, end_date.year + 1):
                        try:
                            recurring_date = date(year, h.recurring_month, h.recurring_day)
                            if start_date <= recurring_date <= end_date:
                                if recurring_date not in holiday_dates:
                                    holiday_dates.append(recurring_date)
                        except ValueError:
                            # Invalid date (e.g., Feb 30)
                            pass

            return sorted(holiday_dates)

        @classmethod
        def get_upcoming_holidays(cls, days_ahead=30):
            """
            Get holidays in the next N days

            Args:
                days_ahead: Number of days to look ahead

            Returns:
                List of CompanyHoliday objects
            """
            from datetime import timedelta
            today = date.today()
            end_date = today + timedelta(days=days_ahead)

            return cls.query.filter(
                cls.holiday_date >= today,
                cls.holiday_date <= end_date,
                cls.is_active == True
            ).order_by(cls.holiday_date).all()

    return CompanyHoliday
