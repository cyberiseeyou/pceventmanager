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

        avail = EmployeeWeeklyAvailability(
            employee_id='EMP001',
            monday=True, tuesday=False, wednesday=False,
            thursday=False, friday=False, saturday=False, sunday=False
        )
        db_session.add(avail)
        db_session.commit()

        from app.services.weekly_planning_service import WeeklyPlanningService
        service = WeeklyPlanningService(db_session, models)

        # 2026-02-23 is a Monday
        test_date = date(2026, 2, 23)
        result = service.get_available_employees(test_date, test_date)

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

        avail = EmployeeWeeklyAvailability(
            employee_id='EMP005',
            monday=True, tuesday=True, wednesday=True,
            thursday=True, friday=True, saturday=True, sunday=True
        )
        db_session.add(avail)

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
