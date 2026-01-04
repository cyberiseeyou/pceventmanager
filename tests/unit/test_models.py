"""
Unit tests for database models.

Tests cover:
- Model creation and field validation
- Model methods and computed properties
- Relationships between models
- Business logic embedded in models
"""
import pytest
from datetime import datetime, date, timedelta


class TestEmployeeModel:
    """Tests for the Employee model."""

    @pytest.mark.unit
    def test_create_employee(self, models, db):
        """Test creating a basic employee."""
        Employee = models['Employee']
        employee = Employee(
            id='EMP001',
            name='John Doe',
            email='john@example.com',
            phone='555-0100',
            job_title='Event Specialist'
        )
        db.session.add(employee)
        db.session.commit()

        assert employee.id == 'EMP001'
        assert employee.name == 'John Doe'
        assert employee.is_active is True  # Default
        assert employee.is_supervisor is False  # Default

    @pytest.mark.unit
    def test_employee_defaults(self, employee_factory):
        """Test that employee has correct default values."""
        employee = employee_factory()

        assert employee.is_active is True
        assert employee.is_supervisor is False
        assert employee.adult_beverage_trained is False
        assert employee.job_title == 'Event Specialist'
        assert employee.sync_status == 'pending'

    @pytest.mark.unit
    def test_employee_repr(self, employee_factory):
        """Test employee string representation."""
        employee = employee_factory(id='EMP123', name='Test Person')
        assert 'EMP123' in repr(employee)
        assert 'Test Person' in repr(employee)

    @pytest.mark.unit
    def test_can_work_event_type_core(self, employee_factory):
        """Test that all employees can work Core events."""
        specialist = employee_factory(job_title='Event Specialist')
        supervisor = employee_factory(job_title='Club Supervisor')

        assert specialist.can_work_event_type('Core') is True
        assert supervisor.can_work_event_type('Core') is True

    @pytest.mark.unit
    def test_can_work_event_type_supervisor_restricted(self, employee_factory):
        """Test that only supervisors/leads can work Supervisor events."""
        specialist = employee_factory(job_title='Event Specialist')
        supervisor = employee_factory(job_title='Club Supervisor')
        lead = employee_factory(job_title='Lead Event Specialist')

        assert specialist.can_work_event_type('Supervisor') is False
        assert supervisor.can_work_event_type('Supervisor') is True
        assert lead.can_work_event_type('Supervisor') is True

    @pytest.mark.unit
    def test_can_work_event_type_freeosk(self, employee_factory):
        """Test Freeosk event restrictions."""
        specialist = employee_factory(job_title='Event Specialist')
        supervisor = employee_factory(job_title='Club Supervisor')

        assert specialist.can_work_event_type('Freeosk') is False
        assert supervisor.can_work_event_type('Freeosk') is True

    @pytest.mark.unit
    def test_can_work_event_type_digitals(self, employee_factory):
        """Test Digitals event restrictions."""
        specialist = employee_factory(job_title='Event Specialist')
        lead = employee_factory(job_title='Lead Event Specialist')

        assert specialist.can_work_event_type('Digitals') is False
        assert lead.can_work_event_type('Digitals') is True

    @pytest.mark.unit
    def test_can_work_event_type_juicer(self, employee_factory):
        """Test Juicer event restrictions."""
        specialist = employee_factory(job_title='Event Specialist')
        barista = employee_factory(job_title='Juicer Barista')
        supervisor = employee_factory(job_title='Club Supervisor')

        # Juicer Production
        assert specialist.can_work_event_type('Juicer Production') is False
        assert barista.can_work_event_type('Juicer Production') is True
        assert supervisor.can_work_event_type('Juicer Production') is True

        # Juicer Survey
        assert specialist.can_work_event_type('Juicer Survey') is False
        assert barista.can_work_event_type('Juicer Survey') is True

        # Juicer Deep Clean
        assert specialist.can_work_event_type('Juicer Deep Clean') is False
        assert barista.can_work_event_type('Juicer Deep Clean') is True

    @pytest.mark.unit
    def test_can_work_event_type_other(self, employee_factory):
        """Test that all employees can work Other events."""
        specialist = employee_factory(job_title='Event Specialist')
        assert specialist.can_work_event_type('Other') is True

    @pytest.mark.unit
    def test_employee_termination_date(self, employee_factory):
        """Test employee termination date field."""
        employee = employee_factory(termination_date=date(2024, 12, 31))
        assert employee.termination_date == date(2024, 12, 31)

    @pytest.mark.unit
    def test_employee_unique_email(self, models, db):
        """Test that employee email must be unique."""
        Employee = models['Employee']

        emp1 = Employee(id='EMP001', name='John', email='same@example.com')
        db.session.add(emp1)
        db.session.commit()

        emp2 = Employee(id='EMP002', name='Jane', email='same@example.com')
        db.session.add(emp2)

        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()


class TestEventModel:
    """Tests for the Event model."""

    @pytest.mark.unit
    def test_create_event(self, models, db):
        """Test creating a basic event."""
        Event = models['Event']
        event = Event(
            project_name='Test CORE Event',
            project_ref_num=100001,
            store_number=1234,
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=7),
            event_type='Core'
        )
        db.session.add(event)
        db.session.commit()

        assert event.project_ref_num == 100001
        assert event.event_type == 'Core'
        assert event.is_scheduled is False

    @pytest.mark.unit
    def test_event_defaults(self, event_factory):
        """Test event default values."""
        event = event_factory()

        assert event.is_scheduled is False
        assert event.condition == 'Unstaffed'
        assert event.sync_status == 'pending'

    @pytest.mark.unit
    def test_event_repr(self, event_factory):
        """Test event string representation."""
        event = event_factory(project_ref_num=999999, project_name='My Event')
        assert '999999' in repr(event)
        assert 'My Event' in repr(event)

    @pytest.mark.unit
    def test_detect_event_type_core(self, event_factory):
        """Test Core event type detection."""
        event = event_factory(project_name='Weekly CORE Visit')
        assert event.detect_event_type() == 'Core'

    @pytest.mark.unit
    def test_detect_event_type_digital(self, event_factory):
        """Test Digital event type detection."""
        event = event_factory(project_name='DIGITAL Display Setup')
        assert event.detect_event_type() == 'Digitals'

    @pytest.mark.unit
    def test_detect_event_type_juicer_production(self, event_factory):
        """Test Juicer Production event type detection."""
        event = event_factory(project_name='JUICE Bar PRODUCTION-SPCLTY Event')
        assert event.detect_event_type() == 'Juicer Production'

    @pytest.mark.unit
    def test_detect_event_type_juicer_survey(self, event_factory):
        """Test Juicer Survey event type detection."""
        event = event_factory(project_name='JUICE Station SURVEY-SPCLTY')
        assert event.detect_event_type() == 'Juicer Survey'

    @pytest.mark.unit
    def test_detect_event_type_juicer_deep_clean(self, event_factory):
        """Test Juicer Deep Clean event type detection."""
        event = event_factory(project_name='JUICER DEEP CLEAN')
        assert event.detect_event_type() == 'Juicer Deep Clean'

    @pytest.mark.unit
    def test_detect_event_type_supervisor(self, event_factory):
        """Test Supervisor event type detection."""
        event1 = event_factory(project_name='Weekly SUPERVISOR Check')
        event2 = event_factory(project_name='V2-SUPER Visit')

        assert event1.detect_event_type() == 'Supervisor'
        assert event2.detect_event_type() == 'Supervisor'

    @pytest.mark.unit
    def test_detect_event_type_freeosk(self, event_factory):
        """Test Freeosk event type detection."""
        event = event_factory(project_name='FREEOSK Demo Event')
        assert event.detect_event_type() == 'Freeosk'

    @pytest.mark.unit
    def test_detect_event_type_other(self, event_factory):
        """Test Other event type detection for unknown projects."""
        event = event_factory(project_name='Some Random Project')
        assert event.detect_event_type() == 'Other'

    @pytest.mark.unit
    def test_detect_event_type_none_project_name(self, models, db):
        """Test event type detection with None project name."""
        Event = models['Event']
        event = Event(
            project_name=None,
            project_ref_num=999,
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=1)
        )
        # Don't commit - just test the method
        assert event.detect_event_type() == 'Other'

    @pytest.mark.unit
    def test_get_default_duration(self, models):
        """Test default duration retrieval for event types."""
        Event = models['Event']

        assert Event.get_default_duration('Core') == 390  # 6.5 hours
        assert Event.get_default_duration('Juicer Production') == 540  # 9 hours
        assert Event.get_default_duration('Juicer Survey') == 15
        assert Event.get_default_duration('Juicer Deep Clean') == 240  # 4 hours
        assert Event.get_default_duration('Supervisor') == 5
        assert Event.get_default_duration('Digitals') == 15
        assert Event.get_default_duration('Freeosk') == 15
        assert Event.get_default_duration('Other') == 15
        assert Event.get_default_duration('Unknown') == 15  # Default fallback

    @pytest.mark.unit
    def test_set_default_duration(self, event_factory):
        """Test setting default duration based on event type."""
        event = event_factory(event_type='Core', estimated_time=None)
        event.set_default_duration()
        assert event.estimated_time == 390

    @pytest.mark.unit
    def test_set_default_duration_preserves_existing(self, event_factory):
        """Test that set_default_duration doesn't override existing value."""
        event = event_factory(event_type='Core', estimated_time=120)
        event.set_default_duration()
        assert event.estimated_time == 120  # Preserved

    @pytest.mark.unit
    def test_calculate_end_datetime(self, event_factory):
        """Test end datetime calculation."""
        start = datetime(2024, 1, 15, 8, 0, 0)
        event = event_factory(estimated_time=120)  # 2 hours

        end = event.calculate_end_datetime(start)
        assert end == datetime(2024, 1, 15, 10, 0, 0)

    @pytest.mark.unit
    def test_calculate_end_datetime_uses_default(self, event_factory):
        """Test end datetime calculation uses default when no estimated_time."""
        start = datetime(2024, 1, 15, 8, 0, 0)
        event = event_factory(event_type='Supervisor', estimated_time=None)

        end = event.calculate_end_datetime(start)
        # Supervisor default is 5 minutes
        assert end == datetime(2024, 1, 15, 8, 5, 0)

    @pytest.mark.unit
    def test_event_unique_ref_num(self, models, db):
        """Test that project_ref_num must be unique."""
        Event = models['Event']

        event1 = Event(
            project_name='Event 1',
            project_ref_num=12345,
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=1)
        )
        db.session.add(event1)
        db.session.commit()

        event2 = Event(
            project_name='Event 2',
            project_ref_num=12345,  # Same ref num
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=1)
        )
        db.session.add(event2)

        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()


class TestScheduleModel:
    """Tests for the Schedule model."""

    @pytest.mark.unit
    def test_create_schedule(self, schedule_factory):
        """Test creating a basic schedule."""
        schedule = schedule_factory()

        assert schedule.id is not None
        assert schedule.employee_id is not None
        assert schedule.event_ref_num is not None
        assert schedule.sync_status == 'pending'

    @pytest.mark.unit
    def test_schedule_relationships(self, schedule_factory, employee_factory, event_factory):
        """Test schedule relationships to employee and event."""
        employee = employee_factory(id='REL_EMP', name='Related Employee')
        event = event_factory(project_ref_num=888888)

        schedule = schedule_factory(employee=employee, event=event)

        assert schedule.employee.name == 'Related Employee'
        assert schedule.event.project_ref_num == 888888

    @pytest.mark.unit
    def test_schedule_repr(self, schedule_factory, employee_factory, event_factory):
        """Test schedule string representation."""
        employee = employee_factory(id='SCH_EMP')
        event = event_factory(project_ref_num=777777)
        schedule = schedule_factory(employee=employee, event=event)

        repr_str = repr(schedule)
        assert '777777' in repr_str
        assert 'SCH_EMP' in repr_str

    @pytest.mark.unit
    def test_schedule_shift_block(self, schedule_factory):
        """Test schedule shift block assignment."""
        schedule = schedule_factory(shift_block=3)
        assert schedule.shift_block == 3


class TestEmployeeWeeklyAvailability:
    """Tests for EmployeeWeeklyAvailability model."""

    @pytest.mark.unit
    def test_create_weekly_availability(self, models, db, employee_factory):
        """Test creating weekly availability."""
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
        employee = employee_factory()

        availability = EmployeeWeeklyAvailability(
            employee_id=employee.id,
            monday=True,
            tuesday=True,
            wednesday=False,
            thursday=True,
            friday=True,
            saturday=False,
            sunday=False
        )
        db.session.add(availability)
        db.session.commit()

        assert availability.monday is True
        assert availability.wednesday is False
        assert availability.saturday is False

    @pytest.mark.unit
    def test_weekly_availability_defaults(self, models, db, employee_factory):
        """Test weekly availability default values (all days true)."""
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
        employee = employee_factory()

        availability = EmployeeWeeklyAvailability(employee_id=employee.id)
        db.session.add(availability)
        db.session.commit()

        # All days default to True
        assert availability.monday is True
        assert availability.tuesday is True
        assert availability.wednesday is True
        assert availability.thursday is True
        assert availability.friday is True
        assert availability.saturday is True
        assert availability.sunday is True


class TestEmployeeTimeOff:
    """Tests for EmployeeTimeOff model."""

    @pytest.mark.unit
    def test_create_time_off(self, time_off_factory):
        """Test creating time off record."""
        time_off = time_off_factory(
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 7),
            reason='Summer vacation'
        )

        assert time_off.start_date == date(2024, 6, 1)
        assert time_off.end_date == date(2024, 6, 7)
        assert time_off.reason == 'Summer vacation'

    @pytest.mark.unit
    def test_time_off_repr(self, time_off_factory, employee_factory):
        """Test time off string representation."""
        employee = employee_factory(id='TO_EMP')
        time_off = time_off_factory(
            employee=employee,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5)
        )

        repr_str = repr(time_off)
        assert 'TO_EMP' in repr_str


class TestEmployeeAvailabilityOverride:
    """Tests for EmployeeAvailabilityOverride model."""

    @pytest.mark.unit
    def test_create_override(self, models, db, employee_factory):
        """Test creating availability override."""
        EmployeeAvailabilityOverride = models['EmployeeAvailabilityOverride']
        employee = employee_factory()

        override = EmployeeAvailabilityOverride(
            employee_id=employee.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            monday=True,
            tuesday=True,
            wednesday=False,  # Not available on Wednesdays
            thursday=True,
            friday=True,
            saturday=None,  # No override for Saturday
            sunday=None,    # No override for Sunday
            reason='College class schedule'
        )
        db.session.add(override)
        db.session.commit()

        assert override.wednesday is False
        assert override.saturday is None

    @pytest.mark.unit
    def test_override_is_active(self, models, db, employee_factory):
        """Test is_active method."""
        EmployeeAvailabilityOverride = models['EmployeeAvailabilityOverride']
        employee = employee_factory()

        today = date.today()
        override = EmployeeAvailabilityOverride(
            employee_id=employee.id,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=5)
        )
        db.session.add(override)
        db.session.commit()

        # Should be active for today
        assert override.is_active(today) is True

        # Should not be active for dates outside range
        assert override.is_active(today - timedelta(days=10)) is False
        assert override.is_active(today + timedelta(days=10)) is False

    @pytest.mark.unit
    def test_override_get_day_availability(self, models, db, employee_factory):
        """Test get_day_availability method."""
        EmployeeAvailabilityOverride = models['EmployeeAvailabilityOverride']
        employee = employee_factory()

        override = EmployeeAvailabilityOverride(
            employee_id=employee.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            monday=True,
            tuesday=False,
            wednesday=None  # No override
        )
        db.session.add(override)
        db.session.commit()

        assert override.get_day_availability(0) is True   # Monday
        assert override.get_day_availability(1) is False  # Tuesday
        assert override.get_day_availability(2) is None   # Wednesday (no override)


class TestModelRelationships:
    """Tests for relationships between models."""

    @pytest.mark.unit
    def test_employee_schedules_backref(self, schedule_factory, employee_factory, event_factory, db):
        """Test that employee has backref to schedules."""
        employee = employee_factory(id='BACKREF_EMP')
        event1 = event_factory(project_ref_num=111111)
        event2 = event_factory(project_ref_num=222222)

        schedule1 = schedule_factory(employee=employee, event=event1)
        schedule2 = schedule_factory(employee=employee, event=event2)

        db.session.refresh(employee)
        assert len(employee.schedules) == 2

    @pytest.mark.unit
    def test_event_schedules_backref(self, schedule_factory, employee_factory, event_factory, db):
        """Test that event has backref to schedules."""
        event = event_factory(project_ref_num=333333)
        emp1 = employee_factory()
        emp2 = employee_factory()

        schedule_factory(employee=emp1, event=event)
        schedule_factory(employee=emp2, event=event)

        db.session.refresh(event)
        assert len(event.schedules) == 2
