# Weekly Planning Views Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add two new weekly dashboard views - Employee Availability (capacity planning) and Available Schedule Blocks (scheduling action) - to help forecast staffing needs and manually fill remaining events.

**Architecture:** A new service (`weekly_planning_service.py`) handles all availability/scheduling queries. Two new routes in the existing `dashboard_bp` blueprint render server-side templates using the same visual patterns as Weekly Validation. Both views share a 7-column Sun-Sat grid layout with week navigation.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, existing CSS patterns from weekly_validation.html

---

### Task 1: Create WeeklyPlanningService - availability logic

**Files:**
- Create: `app/services/weekly_planning_service.py`
- Test: `tests/test_weekly_planning.py`

**Step 1: Write the failing test for get_available_employees**

Create `tests/test_weekly_planning.py`:

```python
"""Tests for WeeklyPlanningService"""
import pytest
from datetime import date, datetime, timedelta


class TestGetAvailableEmployees:
    """Tests for the availability calculation logic"""

    def test_active_employee_with_availability_shows(self, app, db_session, models):
        """An active employee with weekly availability for a day should appear"""
        Employee = models['Employee']
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

        emp = Employee(id='EMP001', name='Alice Smith', is_active=True)
        db_session.add(emp)
        db_session.flush()

        # Set availability: available Monday only
        avail = EmployeeWeeklyAvailability(
            employee_id='EMP001',
            monday=True, tuesday=False, wednesday=False,
            thursday=False, friday=False, saturday=False, sunday=False
        )
        db_session.add(avail)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        # Find a Monday within a test range
        # Use a known Monday: 2026-02-23 is a Monday
        test_date = date(2026, 2, 23)
        start = test_date
        end = test_date

        result = service.get_available_employees(start, end)

        assert test_date in result
        emp_ids = [e['id'] for e in result[test_date]]
        assert 'EMP001' in emp_ids

    def test_inactive_employee_excluded(self, app, db_session, models):
        """Inactive employees should not appear"""
        Employee = models['Employee']

        emp = Employee(id='EMP002', name='Bob Inactive', is_active=False)
        db_session.add(emp)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        test_date = date(2026, 2, 23)
        result = service.get_available_employees(test_date, test_date)

        emp_ids = [e['id'] for e in result.get(test_date, [])]
        assert 'EMP002' not in emp_ids

    def test_employee_on_time_off_excluded(self, app, db_session, models):
        """Employee with time off on a day should not appear"""
        Employee = models['Employee']
        EmployeeTimeOff = models['EmployeeTimeOff']

        emp = Employee(id='EMP003', name='Carol TimeOff', is_active=True)
        db_session.add(emp)
        db_session.flush()

        time_off = EmployeeTimeOff(
            employee_id='EMP003',
            start_date=date(2026, 2, 23),
            end_date=date(2026, 2, 25),
            reason='Vacation'
        )
        db_session.add(time_off)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        result = service.get_available_employees(date(2026, 2, 23), date(2026, 2, 25))

        for d in [date(2026, 2, 23), date(2026, 2, 24), date(2026, 2, 25)]:
            emp_ids = [e['id'] for e in result.get(d, [])]
            assert 'EMP003' not in emp_ids

    def test_store_closure_marks_holiday(self, app, db_session, models):
        """Days with CompanyHoliday should be flagged as store closures"""
        CompanyHoliday = models['CompanyHoliday']

        holiday = CompanyHoliday(
            name='Test Holiday',
            holiday_date=date(2026, 2, 23),
            is_active=True
        )
        db_session.add(holiday)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        result = service.get_available_employees(date(2026, 2, 23), date(2026, 2, 23))

        # Holiday dates should have empty employee list
        assert result.get(date(2026, 2, 23), []) == []

    def test_weekly_unavailable_day_excluded(self, app, db_session, models):
        """Employee marked unavailable on a weekday should not appear that day"""
        Employee = models['Employee']
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

        emp = Employee(id='EMP004', name='Dave NoTuesday', is_active=True)
        db_session.add(emp)
        db_session.flush()

        avail = EmployeeWeeklyAvailability(
            employee_id='EMP004',
            monday=True, tuesday=False, wednesday=True,
            thursday=True, friday=True, saturday=True, sunday=True
        )
        db_session.add(avail)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        # 2026-02-24 is a Tuesday
        tuesday = date(2026, 2, 24)
        monday = date(2026, 2, 23)
        result = service.get_available_employees(monday, tuesday)

        monday_ids = [e['id'] for e in result.get(monday, [])]
        tuesday_ids = [e['id'] for e in result.get(tuesday, [])]

        assert 'EMP004' in monday_ids
        assert 'EMP004' not in tuesday_ids

    def test_override_trumps_weekly(self, app, db_session, models):
        """EmployeeAvailabilityOverride should override weekly availability"""
        Employee = models['Employee']
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
        EmployeeAvailabilityOverride = models['EmployeeAvailabilityOverride']

        emp = Employee(id='EMP005', name='Eve Override', is_active=True)
        db_session.add(emp)
        db_session.flush()

        # Normally available Monday
        avail = EmployeeWeeklyAvailability(
            employee_id='EMP005',
            monday=True, tuesday=True, wednesday=True,
            thursday=True, friday=True, saturday=True, sunday=True
        )
        db_session.add(avail)

        # Override: NOT available Monday for this date range
        override = EmployeeAvailabilityOverride(
            employee_id='EMP005',
            start_date=date(2026, 2, 22),
            end_date=date(2026, 2, 28),
            monday=False, tuesday=True, wednesday=True,
            thursday=True, friday=True, saturday=True, sunday=True
        )
        db_session.add(override)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        monday = date(2026, 2, 23)
        result = service.get_available_employees(monday, monday)

        emp_ids = [e['id'] for e in result.get(monday, [])]
        assert 'EMP005' not in emp_ids


class TestGetAvailableForMainEvents:
    """Tests for available-for-main-event filtering"""

    def test_unscheduled_employee_shows(self, app, db_session, models):
        """Employee with no schedules should appear"""
        Employee = models['Employee']

        emp = Employee(id='EMP010', name='Frank Free', is_active=True)
        db_session.add(emp)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        monday = date(2026, 2, 23)
        result = service.get_available_for_main_events(monday, monday)

        emp_ids = [e['id'] for e in result.get(monday, [])]
        assert 'EMP010' in emp_ids

    def test_employee_with_core_event_excluded(self, app, db_session, models):
        """Employee scheduled to Core event should NOT appear"""
        Employee = models['Employee']
        Event = models['Event']
        Schedule = models['Schedule']

        emp = Employee(id='EMP011', name='Grace Core', is_active=True)
        db_session.add(emp)

        event = Event(
            project_ref_num=9001,
            project_name='CORE EVENT TEST',
            event_type='Core',
            start_datetime=datetime(2026, 2, 23, 10, 0),
            due_datetime=datetime(2026, 2, 23, 16, 30),
            estimated_time=390,
            condition='Scheduled'
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=9001,
            employee_id='EMP011',
            schedule_datetime=datetime(2026, 2, 23, 10, 15)
        )
        db_session.add(schedule)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        monday = date(2026, 2, 23)
        result = service.get_available_for_main_events(monday, monday)

        emp_ids = [e['id'] for e in result.get(monday, [])]
        assert 'EMP011' not in emp_ids

    def test_employee_with_short_event_still_shows(self, app, db_session, models):
        """Employee scheduled to a short event (Digital Setup, Freeosk etc) should still appear"""
        Employee = models['Employee']
        Event = models['Event']
        Schedule = models['Schedule']

        emp = Employee(id='EMP012', name='Hank Short', is_active=True)
        db_session.add(emp)

        event = Event(
            project_ref_num=9002,
            project_name='DIGITAL SETUP TEST',
            event_type='Digital Setup',
            start_datetime=datetime(2026, 2, 23, 10, 0),
            due_datetime=datetime(2026, 2, 23, 10, 15),
            estimated_time=15,
            condition='Scheduled'
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=9002,
            employee_id='EMP012',
            schedule_datetime=datetime(2026, 2, 23, 10, 0)
        )
        db_session.add(schedule)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        monday = date(2026, 2, 23)
        result = service.get_available_for_main_events(monday, monday)

        emp_ids = [e['id'] for e in result.get(monday, [])]
        assert 'EMP012' in emp_ids

    def test_employee_with_long_other_event_excluded(self, app, db_session, models):
        """Employee scheduled to an 'Other' event >= 240 min should NOT appear"""
        Employee = models['Employee']
        Event = models['Event']
        Schedule = models['Schedule']

        emp = Employee(id='EMP013', name='Irene Long', is_active=True)
        db_session.add(emp)

        event = Event(
            project_ref_num=9003,
            project_name='BERRY PRODUCTION-SPCLTY',
            event_type='Other',
            start_datetime=datetime(2026, 2, 23, 8, 0),
            due_datetime=datetime(2026, 2, 23, 16, 0),
            estimated_time=480,
            condition='Scheduled'
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=9003,
            employee_id='EMP013',
            schedule_datetime=datetime(2026, 2, 23, 8, 0)
        )
        db_session.add(schedule)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        monday = date(2026, 2, 23)
        result = service.get_available_for_main_events(monday, monday)

        emp_ids = [e['id'] for e in result.get(monday, [])]
        assert 'EMP013' not in emp_ids
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_weekly_planning.py -v`
Expected: FAIL with ModuleNotFoundError (weekly_planning_service doesn't exist yet)

**Step 3: Write the service implementation**

Create `app/services/weekly_planning_service.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_weekly_planning.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app/services/weekly_planning_service.py tests/test_weekly_planning.py
git commit -m "feat: add WeeklyPlanningService for availability and schedule block queries"
```

---

### Task 2: Add dashboard routes

**Files:**
- Modify: `app/routes/dashboard.py` (add two new routes at end of file)

**Step 1: Write route test**

Append to `tests/test_weekly_planning.py`:

```python
class TestRoutes:
    """Test the dashboard routes return 200"""

    def test_employee_availability_route(self, client, db_session):
        response = client.get('/dashboard/employee-availability')
        assert response.status_code == 200

    def test_employee_availability_with_date(self, client, db_session):
        response = client.get('/dashboard/employee-availability?start_date=2026-02-22')
        assert response.status_code == 200

    def test_available_blocks_route(self, client, db_session):
        response = client.get('/dashboard/available-blocks')
        assert response.status_code == 200

    def test_available_blocks_with_date(self, client, db_session):
        response = client.get('/dashboard/available-blocks?start_date=2026-02-22')
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_weekly_planning.py::TestRoutes -v`
Expected: FAIL with 404 (routes don't exist yet)

**Step 3: Add routes to dashboard.py**

Add these two routes at the end of `app/routes/dashboard.py` (before any final helper functions, but after the last route):

```python
@dashboard_bp.route('/employee-availability')
def employee_availability():
    """
    Employee Availability weekly view - capacity planning tool.

    Shows all available employees per day for the selected week.
    Used to forecast whether there are enough people for upcoming events.

    Query Parameters:
    - start_date: First day of week (YYYY-MM-DD), defaults to today's week
    """
    from flask import request
    from app.models import get_models
    from app.services.weekly_planning_service import WeeklyPlanningService

    db = current_app.extensions['sqlalchemy']
    models = get_models()

    # Parse and align to Sunday
    date_param = request.args.get('start_date')
    if date_param:
        try:
            start_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            start_date = date.today()
    else:
        start_date = date.today()

    days_since_sunday = (start_date.weekday() + 1) % 7
    start_date = start_date - timedelta(days=days_since_sunday)
    end_date = start_date + timedelta(days=6)

    service = WeeklyPlanningService(db.session, models)
    availability = service.get_available_employees(start_date, end_date)
    holidays = availability.pop('_holidays', set())

    # Build ordered list of days
    days = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        days.append({
            'date': d,
            'employees': availability.get(d, []),
            'is_holiday': d in holidays,
            'count': len(availability.get(d, []))
        })

    total_available = sum(day['count'] for day in days)

    return render_template('dashboard/employee_availability.html',
                         days=days,
                         start_date=start_date,
                         end_date=end_date,
                         total_available=total_available,
                         timedelta=timedelta)


@dashboard_bp.route('/available-blocks')
def available_blocks():
    """
    Available Schedule Blocks weekly view - scheduling action tool.

    Shows employees still open for main event assignment each day.
    Used to manually fill remaining events by seeing who is free.

    Query Parameters:
    - start_date: First day of week (YYYY-MM-DD), defaults to today's week
    """
    from flask import request
    from app.models import get_models
    from app.services.weekly_planning_service import WeeklyPlanningService

    db = current_app.extensions['sqlalchemy']
    models = get_models()

    # Parse and align to Sunday
    date_param = request.args.get('start_date')
    if date_param:
        try:
            start_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            start_date = date.today()
    else:
        start_date = date.today()

    days_since_sunday = (start_date.weekday() + 1) % 7
    start_date = start_date - timedelta(days=days_since_sunday)
    end_date = start_date + timedelta(days=6)

    service = WeeklyPlanningService(db.session, models)
    blocks = service.get_available_for_main_events(start_date, end_date)
    holidays = blocks.pop('_holidays', set())

    # Build ordered list of days
    days = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        days.append({
            'date': d,
            'employees': blocks.get(d, []),
            'is_holiday': d in holidays,
            'count': len(blocks.get(d, []))
        })

    total_available = sum(day['count'] for day in days)

    return render_template('dashboard/available_blocks.html',
                         days=days,
                         start_date=start_date,
                         end_date=end_date,
                         total_available=total_available,
                         timedelta=timedelta)
```

**Step 4: Create stub templates so routes don't error**

Create minimal placeholder templates (will be replaced in Task 3):

`app/templates/dashboard/employee_availability.html`:
```html
{% extends "base.html" %}
{% block title %}Employee Availability{% endblock %}
{% block content %}<div>Placeholder</div>{% endblock %}
```

`app/templates/dashboard/available_blocks.html`:
```html
{% extends "base.html" %}
{% block title %}Available Schedule Blocks{% endblock %}
{% block content %}<div>Placeholder</div>{% endblock %}
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_weekly_planning.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add app/routes/dashboard.py app/templates/dashboard/employee_availability.html app/templates/dashboard/available_blocks.html tests/test_weekly_planning.py
git commit -m "feat: add employee-availability and available-blocks dashboard routes"
```

---

### Task 3: Create Employee Availability template

**Files:**
- Modify: `app/templates/dashboard/employee_availability.html`

**Step 1: Write the full template**

Replace the placeholder with the full template. Match the existing weekly_validation.html visual style (purple gradient header, week nav buttons, card-based layout). Use a 7-column responsive grid where each column is a day showing employee names with a count header.

Reference `app/templates/dashboard/weekly_validation.html` for the header/nav pattern. The key context variables are:
- `days` - list of 7 dicts with `date`, `employees` (list of `{id, name}`), `is_holiday`, `count`
- `start_date`, `end_date` - date objects
- `total_available` - int
- `timedelta` - Python timedelta class for date arithmetic in template

Template content:
```html
{% extends "base.html" %}

{% block title %}Employee Availability{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
    integrity="sha384-iw3OoTErCYJJB9mCa8LNS2hbsQ7M3C0EpIsO/H5+EGAkPGc6rk+V8i04oW/K5xq0" crossorigin="anonymous" />
<style>
    .planning-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 24px 32px;
        border-radius: 12px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .planning-header h1 { font-size: 24px; font-weight: 700; margin: 0; }
    .planning-header .date-range { opacity: 0.9; margin-top: 4px; }
    .nav-btns { display: flex; gap: 8px; }
    .nav-btns a {
        background: rgba(255,255,255,0.2); color: white;
        padding: 8px 16px; border-radius: 6px;
        text-decoration: none; font-weight: 500;
    }
    .nav-btns a:hover { background: rgba(255,255,255,0.3); }

    .stats-row { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .stat-item {
        background: white; padding: 16px 24px; border-radius: 8px;
        display: flex; align-items: center; gap: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .stat-item .count { font-size: 28px; font-weight: 700; color: #667eea; }
    .stat-item .label { color: #666; font-size: 13px; }

    .week-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }
    @media (max-width: 992px) {
        .week-grid { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 576px) {
        .week-grid { grid-template-columns: 1fr; }
    }

    .day-column {
        background: white;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        overflow: hidden;
    }
    .day-header {
        padding: 12px 16px;
        background: #f8f9fa;
        border-bottom: 2px solid #e5e7eb;
        text-align: center;
    }
    .day-header .day-name {
        font-size: 11px; text-transform: uppercase;
        font-weight: 600; color: #666; letter-spacing: 0.5px;
    }
    .day-header .day-date { font-size: 20px; font-weight: 700; color: #1f2937; }
    .day-header .day-count {
        font-size: 12px; font-weight: 600;
        color: #667eea; margin-top: 2px;
    }
    .day-header.today { background: #f0f4ff; border-bottom-color: #667eea; }
    .day-header.holiday { background: #fef2f2; border-bottom-color: #dc2626; }

    .day-body { padding: 8px 12px; min-height: 120px; }
    .employee-row {
        padding: 6px 8px; border-radius: 6px;
        font-size: 13px; color: #374151;
    }
    .employee-row:hover { background: #f3f4f6; }
    .holiday-notice {
        text-align: center; padding: 24px 8px;
        color: #dc2626; font-weight: 600; font-size: 14px;
    }
    .holiday-notice i { display: block; font-size: 24px; margin-bottom: 8px; }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="planning-header">
        <div>
            <h1><i class="fas fa-users me-2"></i>Employee Availability</h1>
            <div class="date-range">{{ start_date.strftime('%B %d') }} - {{ end_date.strftime('%B %d, %Y') }}</div>
        </div>
        <div class="nav-btns">
            <a href="{{ url_for('dashboard.employee_availability', start_date=(start_date - timedelta(days=7)).isoformat()) }}">
                <i class="fas fa-chevron-left"></i> Prev
            </a>
            <a href="{{ url_for('dashboard.employee_availability') }}">Today</a>
            <a href="{{ url_for('dashboard.employee_availability', start_date=(start_date + timedelta(days=7)).isoformat()) }}">
                Next <i class="fas fa-chevron-right"></i>
            </a>
        </div>
    </div>

    <div class="stats-row">
        <div class="stat-item">
            <div class="count">{{ total_available }}</div>
            <div class="label">Total Available<br>Slots This Week</div>
        </div>
    </div>

    <div class="week-grid">
        {% for day in days %}
        <div class="day-column">
            <div class="day-header {% if day.date == today_date %}today{% endif %}{% if day.is_holiday %} holiday{% endif %}">
                <div class="day-name">{{ day.date.strftime('%a') }}</div>
                <div class="day-date">{{ day.date.strftime('%b %d') }}</div>
                {% if day.is_holiday %}
                <div class="day-count" style="color: #dc2626;">Closed</div>
                {% else %}
                <div class="day-count">{{ day.count }} available</div>
                {% endif %}
            </div>
            <div class="day-body">
                {% if day.is_holiday %}
                <div class="holiday-notice">
                    <i class="fas fa-store-slash"></i>
                    Store Closed
                </div>
                {% elif day.employees %}
                    {% for emp in day.employees %}
                    <div class="employee-row">{{ emp.name }}</div>
                    {% endfor %}
                {% else %}
                <div class="holiday-notice" style="color: #666;">
                    <i class="fas fa-user-slash"></i>
                    No one available
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

Note: The template references `today_date` for highlighting today's column. Update the route in `dashboard.py` to pass `today_date=date.today()` in the `render_template` call:

```python
return render_template('dashboard/employee_availability.html',
                     days=days,
                     start_date=start_date,
                     end_date=end_date,
                     total_available=total_available,
                     today_date=date.today(),
                     timedelta=timedelta)
```

**Step 2: Verify in browser**

Run: `python wsgi.py`
Visit: `http://localhost:5000/dashboard/employee-availability`
Expected: Purple header with week nav, 7-column grid showing employee names per day

**Step 3: Commit**

```bash
git add app/templates/dashboard/employee_availability.html app/routes/dashboard.py
git commit -m "feat: add Employee Availability template with weekly grid layout"
```

---

### Task 4: Create Available Schedule Blocks template

**Files:**
- Modify: `app/templates/dashboard/available_blocks.html`

**Step 1: Write the full template**

Same grid layout as View 1, but with a green accent instead of purple to visually distinguish it, and different header text.

```html
{% extends "base.html" %}

{% block title %}Available Schedule Blocks{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
    integrity="sha384-iw3OoTErCYJJB9mCa8LNS2hbsQ7M3C0EpIsO/H5+EGAkPGc6rk+V8i04oW/K5xq0" crossorigin="anonymous" />
<style>
    .planning-header {
        background: linear-gradient(135deg, #059669 0%, #047857 100%);
        color: white;
        padding: 24px 32px;
        border-radius: 12px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .planning-header h1 { font-size: 24px; font-weight: 700; margin: 0; }
    .planning-header .date-range { opacity: 0.9; margin-top: 4px; }
    .nav-btns { display: flex; gap: 8px; }
    .nav-btns a {
        background: rgba(255,255,255,0.2); color: white;
        padding: 8px 16px; border-radius: 6px;
        text-decoration: none; font-weight: 500;
    }
    .nav-btns a:hover { background: rgba(255,255,255,0.3); }

    .stats-row { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .stat-item {
        background: white; padding: 16px 24px; border-radius: 8px;
        display: flex; align-items: center; gap: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .stat-item .count { font-size: 28px; font-weight: 700; color: #059669; }
    .stat-item .label { color: #666; font-size: 13px; }

    .week-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }
    @media (max-width: 992px) {
        .week-grid { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 576px) {
        .week-grid { grid-template-columns: 1fr; }
    }

    .day-column {
        background: white;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        overflow: hidden;
    }
    .day-header {
        padding: 12px 16px;
        background: #f8f9fa;
        border-bottom: 2px solid #e5e7eb;
        text-align: center;
    }
    .day-header .day-name {
        font-size: 11px; text-transform: uppercase;
        font-weight: 600; color: #666; letter-spacing: 0.5px;
    }
    .day-header .day-date { font-size: 20px; font-weight: 700; color: #1f2937; }
    .day-header .day-count {
        font-size: 12px; font-weight: 600;
        color: #059669; margin-top: 2px;
    }
    .day-header.today { background: #ecfdf5; border-bottom-color: #059669; }
    .day-header.holiday { background: #fef2f2; border-bottom-color: #dc2626; }

    .day-body { padding: 8px 12px; min-height: 120px; }
    .employee-row {
        padding: 6px 8px; border-radius: 6px;
        font-size: 13px; color: #374151;
    }
    .employee-row:hover { background: #f3f4f6; }
    .holiday-notice {
        text-align: center; padding: 24px 8px;
        color: #dc2626; font-weight: 600; font-size: 14px;
    }
    .holiday-notice i { display: block; font-size: 24px; margin-bottom: 8px; }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="planning-header">
        <div>
            <h1><i class="fas fa-calendar-check me-2"></i>Available Schedule Blocks</h1>
            <div class="date-range">{{ start_date.strftime('%B %d') }} - {{ end_date.strftime('%B %d, %Y') }}</div>
        </div>
        <div class="nav-btns">
            <a href="{{ url_for('dashboard.available_blocks', start_date=(start_date - timedelta(days=7)).isoformat()) }}">
                <i class="fas fa-chevron-left"></i> Prev
            </a>
            <a href="{{ url_for('dashboard.available_blocks') }}">Today</a>
            <a href="{{ url_for('dashboard.available_blocks', start_date=(start_date + timedelta(days=7)).isoformat()) }}">
                Next <i class="fas fa-chevron-right"></i>
            </a>
        </div>
    </div>

    <div class="stats-row">
        <div class="stat-item">
            <div class="count">{{ total_available }}</div>
            <div class="label">Open Slots<br>For Main Events</div>
        </div>
    </div>

    <div class="week-grid">
        {% for day in days %}
        <div class="day-column">
            <div class="day-header {% if day.date == today_date %}today{% endif %}{% if day.is_holiday %} holiday{% endif %}">
                <div class="day-name">{{ day.date.strftime('%a') }}</div>
                <div class="day-date">{{ day.date.strftime('%b %d') }}</div>
                {% if day.is_holiday %}
                <div class="day-count" style="color: #dc2626;">Closed</div>
                {% else %}
                <div class="day-count">{{ day.count }} open</div>
                {% endif %}
            </div>
            <div class="day-body">
                {% if day.is_holiday %}
                <div class="holiday-notice">
                    <i class="fas fa-store-slash"></i>
                    Store Closed
                </div>
                {% elif day.employees %}
                    {% for emp in day.employees %}
                    <div class="employee-row">{{ emp.name }}</div>
                    {% endfor %}
                {% else %}
                <div class="holiday-notice" style="color: #d97706;">
                    <i class="fas fa-calendar-xmark"></i>
                    Fully booked
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

Also update the `available_blocks` route to pass `today_date=date.today()`:

```python
return render_template('dashboard/available_blocks.html',
                     days=days,
                     start_date=start_date,
                     end_date=end_date,
                     total_available=total_available,
                     today_date=date.today(),
                     timedelta=timedelta)
```

**Step 2: Verify in browser**

Run: `python wsgi.py`
Visit: `http://localhost:5000/dashboard/available-blocks`
Expected: Green header with week nav, 7-column grid showing only employees open for main events

**Step 3: Commit**

```bash
git add app/templates/dashboard/available_blocks.html app/routes/dashboard.py
git commit -m "feat: add Available Schedule Blocks template with green accent"
```

---

### Task 5: Add navigation links

**Files:**
- Modify: `app/templates/base.html` (around line 105, between "Weekly Validation" and "Left in Approved")

**Step 1: Add the nav links**

After the Weekly Validation link (line ~105) and before the "Left in Approved" link, insert:

```html
                            <a href="{{ url_for('dashboard.employee_availability') }}"
                                class="nav-dropdown-item {% if request.endpoint == 'dashboard.employee_availability' %}active{% endif %}">
                                Employee Availability
                            </a>
                            <a href="{{ url_for('dashboard.available_blocks') }}"
                                class="nav-dropdown-item {% if request.endpoint == 'dashboard.available_blocks' %}active{% endif %}">
                                Available Blocks
                            </a>
```

**Step 2: Verify in browser**

Run: `python wsgi.py`
Navigate to any page, open the scheduling dropdown menu.
Expected: "Employee Availability" and "Available Blocks" links appear between "Weekly Validation" and "Left in Approved"

**Step 3: Run all tests**

Run: `pytest tests/test_weekly_planning.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add Employee Availability and Available Blocks to nav menu"
```

---

### Task 6: Final verification

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: All existing tests still pass, plus new tests pass

**Step 2: Manual browser verification**

1. Visit `/dashboard/employee-availability` - should show 7-day grid with available employees
2. Click Prev/Next/Today navigation - should change weeks
3. Visit `/dashboard/available-blocks` - should show filtered grid (no employees with main events)
4. Check navigation menu - both links should appear and highlight when active
5. Test with `?start_date=` parameter - should align to Sunday and show correct week
