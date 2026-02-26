"""
Weekly Planning Service
Provides availability data for the Employee Availability and Available Schedule Blocks views.
"""
from datetime import date, timedelta
from sqlalchemy import func, and_, or_


# Event types that are always considered "main events" regardless of duration
MAIN_EVENT_TYPES = {'Core', 'Juicer Production', 'Juicer Deep Clean'}

# Minimum duration (minutes) for an event to be considered a "main event"
MAIN_EVENT_MIN_DURATION = 240

DAY_NAMES = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


class WeeklyPlanningService:
    """Service for computing employee availability and schedule block data."""

    def __init__(self, db_session, models):
        self.session = db_session
        self.Employee = models['Employee']
        self.EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
        self.EmployeeAvailabilityOverride = models['EmployeeAvailabilityOverride']
        self.EmployeeTimeOff = models['EmployeeTimeOff']
        self.CompanyHoliday = models['CompanyHoliday']
        self.Event = models['Event']
        self.Schedule = models['Schedule']

    def _get_holidays_in_range(self, start, end):
        """Return set of dates that are company holidays in the range."""
        return set(self.CompanyHoliday.get_holidays_in_range(start, end))

    def _get_active_employees(self):
        """Return all active employees."""
        return self.session.query(self.Employee).filter(
            self.Employee.is_active == True
        ).order_by(self.Employee.name).all()

    def _get_weekly_availability_map(self, employee_ids):
        """Return dict of employee_id -> EmployeeWeeklyAvailability record."""
        records = self.session.query(self.EmployeeWeeklyAvailability).filter(
            self.EmployeeWeeklyAvailability.employee_id.in_(employee_ids)
        ).all()
        return {r.employee_id: r for r in records}

    def _get_overrides_in_range(self, employee_ids, start, end):
        """Return list of EmployeeAvailabilityOverride records active in the range."""
        return self.session.query(self.EmployeeAvailabilityOverride).filter(
            self.EmployeeAvailabilityOverride.employee_id.in_(employee_ids),
            self.EmployeeAvailabilityOverride.start_date <= end,
            self.EmployeeAvailabilityOverride.end_date >= start
        ).all()

    def _get_time_off_in_range(self, employee_ids, start, end):
        """Return list of EmployeeTimeOff records overlapping the range."""
        return self.session.query(self.EmployeeTimeOff).filter(
            self.EmployeeTimeOff.employee_id.in_(employee_ids),
            self.EmployeeTimeOff.start_date <= end,
            self.EmployeeTimeOff.end_date >= start
        ).all()

    def _is_employee_available_on_date(self, emp_id, check_date, weekly_map, overrides_by_emp, time_off_by_emp):
        """Check if a single employee is available on a specific date."""
        weekday = check_date.weekday()  # 0=Mon, 6=Sun
        day_name = DAY_NAMES[weekday]

        # Check overrides first (highest priority)
        for override in overrides_by_emp.get(emp_id, []):
            if override.start_date <= check_date <= override.end_date:
                override_val = override.get_day_availability(weekday)
                if override_val is not None:
                    if not override_val:
                        return False
                    # override_val is True, skip weekly check for this day
                    break
        else:
            # No active override found - check weekly availability
            weekly = weekly_map.get(emp_id)
            if weekly and not getattr(weekly, day_name, True):
                return False

        # Check time off
        for to in time_off_by_emp.get(emp_id, []):
            if to.start_date <= check_date <= to.end_date:
                return False

        return True

    def get_available_employees(self, start, end):
        """
        Get available employees for each day in the date range.

        Returns:
            dict: {date -> [{'id': str, 'name': str}, ...]}
            Also includes a '_holidays' key with the set of holiday dates.
        """
        holidays = self._get_holidays_in_range(start, end)
        employees = self._get_active_employees()
        emp_ids = [e.id for e in employees]

        if not emp_ids:
            result = {}
            current = start
            while current <= end:
                result[current] = []
                current += timedelta(days=1)
            result['_holidays'] = holidays
            return result

        weekly_map = self._get_weekly_availability_map(emp_ids)
        overrides = self._get_overrides_in_range(emp_ids, start, end)
        time_offs = self._get_time_off_in_range(emp_ids, start, end)

        # Index overrides and time_off by employee_id
        overrides_by_emp = {}
        for o in overrides:
            overrides_by_emp.setdefault(o.employee_id, []).append(o)

        time_off_by_emp = {}
        for to in time_offs:
            time_off_by_emp.setdefault(to.employee_id, []).append(to)

        result = {}
        current = start
        while current <= end:
            if current in holidays:
                result[current] = []
            else:
                available = []
                for emp in employees:
                    if self._is_employee_available_on_date(
                        emp.id, current, weekly_map, overrides_by_emp, time_off_by_emp
                    ):
                        available.append({'id': emp.id, 'name': emp.name})
                result[current] = available
            current += timedelta(days=1)

        result['_holidays'] = holidays
        return result

    def get_available_for_main_events(self, start, end):
        """
        Get employees available for a main event assignment for each day.

        Filters out employees who are already scheduled to a "main event":
        - Event type in MAIN_EVENT_TYPES, OR
        - Event with estimated_time >= MAIN_EVENT_MIN_DURATION (240 min)

        Returns:
            dict: {date -> [{'id': str, 'name': str}, ...]}
            Also includes a '_holidays' key.
        """
        from datetime import datetime as dt

        available = self.get_available_employees(start, end)
        holidays = available.pop('_holidays', set())

        # Query all schedules in the date range that are for "main events"
        start_dt = dt.combine(start, dt.min.time())
        end_dt = dt.combine(end, dt.max.time())

        main_schedules = self.session.query(
            self.Schedule.employee_id,
            func.date(self.Schedule.schedule_datetime).label('sched_date')
        ).join(
            self.Event,
            self.Event.project_ref_num == self.Schedule.event_ref_num
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Event.condition.notin_(['Canceled', 'Cancelled', 'Expired']),
            or_(
                self.Event.event_type.in_(MAIN_EVENT_TYPES),
                and_(
                    self.Event.estimated_time.isnot(None),
                    self.Event.estimated_time >= MAIN_EVENT_MIN_DURATION
                )
            )
        ).all()

        # Build set of (employee_id, date) pairs with main events
        main_event_assignments = set()
        for row in main_schedules:
            sched_date = row.sched_date
            if isinstance(sched_date, str):
                sched_date = date.fromisoformat(sched_date)
            main_event_assignments.add((row.employee_id, sched_date))

        # Filter each day's available list
        result = {}
        for d, emps in available.items():
            result[d] = [
                e for e in emps
                if (e['id'], d) not in main_event_assignments
            ]

        result['_holidays'] = holidays
        return result
