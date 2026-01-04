"""
Pytest configuration and fixtures for Flask Schedule Webapp tests.

This module provides shared fixtures for:
- Flask application with test configuration
- Database setup and teardown
- Model factories for creating test data
- Common test utilities
"""
import pytest
from datetime import datetime, date, timedelta
from flask import Flask

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope='session')
def app():
    """
    Create application for the tests.

    Uses TestingConfig with in-memory SQLite database.
    Scope is 'session' to reuse the same app across all tests.
    """
    app = create_app('testing')
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
        'RATELIMIT_ENABLED': False,  # Disable rate limiting for tests
    })

    return app


@pytest.fixture(scope='function')
def db(app):
    """
    Create database for the tests.

    Creates all tables before each test function and drops them after.
    This ensures test isolation.
    """
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='function')
def session(db):
    """
    Creates a new database session for a test.

    Wraps each test in a transaction that is rolled back after the test.
    """
    connection = db.engine.connect()
    transaction = connection.begin()

    # Create a session bound to the connection
    session = db.session

    yield session

    # Rollback the transaction
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope='function')
def client(app, db):
    """
    Create a test client for the app.

    The client can be used to make requests to the application.
    """
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture(scope='function')
def models(app, db):
    """
    Get all models from the app config and model registry.

    Models are already initialized by create_app(), so we retrieve them
    from app.config where they are stored.
    """
    with app.app_context():
        from app.models import get_models
        all_models = get_models()
        return {
            'Employee': app.config['Employee'],
            'Event': app.config['Event'],
            'Schedule': app.config['Schedule'],
            'EmployeeWeeklyAvailability': app.config['EmployeeWeeklyAvailability'],
            'EmployeeAvailability': app.config['EmployeeAvailability'],
            'EmployeeTimeOff': app.config['EmployeeTimeOff'],
            'RotationAssignment': app.config['RotationAssignment'],
            'PendingSchedule': app.config['PendingSchedule'],
            'SchedulerRunHistory': app.config['SchedulerRunHistory'],
            'ScheduleException': app.config['ScheduleException'],
            'SystemSetting': app.config['SystemSetting'],
            'EmployeeAttendance': app.config['EmployeeAttendance'],
            'PaperworkTemplate': app.config['PaperworkTemplate'],
            'UserSession': app.config['UserSession'],
            'CompanyHoliday': app.config['CompanyHoliday'],
            'EmployeeAvailabilityOverride': all_models.get('EmployeeAvailabilityOverride'),
        }


# =============================================================================
# Model Factories
# =============================================================================

@pytest.fixture
def employee_factory(models, db):
    """
    Factory for creating Employee instances.

    Usage:
        employee = employee_factory(name="John Doe")
        employee = employee_factory(is_supervisor=True)
    """
    def _create_employee(**kwargs):
        Employee = models['Employee']
        defaults = {
            'id': f'EMP{datetime.now().timestamp()}',
            'name': 'Test Employee',
            'email': f'test{datetime.now().timestamp()}@example.com',
            'phone': '555-0100',
            'is_active': True,
            'is_supervisor': False,
            'job_title': 'Event Specialist',
            'adult_beverage_trained': False,
        }
        defaults.update(kwargs)
        employee = Employee(**defaults)
        db.session.add(employee)
        db.session.commit()
        return employee

    return _create_employee


@pytest.fixture
def event_factory(models, db):
    """
    Factory for creating Event instances.

    Usage:
        event = event_factory(project_name="Core Event")
        event = event_factory(event_type="Juicer Production")
    """
    counter = [0]  # Use list to allow mutation in closure

    def _create_event(**kwargs):
        Event = models['Event']
        counter[0] += 1
        defaults = {
            'project_name': f'Test Project {counter[0]}',
            'project_ref_num': 100000 + counter[0],
            'store_number': 1234,
            'store_name': 'Test Store',
            'start_datetime': datetime.now(),
            'due_datetime': datetime.now() + timedelta(days=7),
            'estimated_time': 60,
            'is_scheduled': False,
            'event_type': 'Core',
            'condition': 'Unstaffed',
        }
        defaults.update(kwargs)
        event = Event(**defaults)
        db.session.add(event)
        db.session.commit()
        return event

    return _create_event


@pytest.fixture
def schedule_factory(models, db, employee_factory, event_factory):
    """
    Factory for creating Schedule instances.

    Creates associated employee and event if not provided.

    Usage:
        schedule = schedule_factory()
        schedule = schedule_factory(employee=my_employee, event=my_event)
    """
    def _create_schedule(employee=None, event=None, **kwargs):
        Schedule = models['Schedule']

        if employee is None:
            employee = employee_factory()
        if event is None:
            event = event_factory()

        defaults = {
            'event_ref_num': event.project_ref_num,
            'employee_id': employee.id,
            'schedule_datetime': datetime.now(),
            'shift_block': 'AM',
        }
        defaults.update(kwargs)
        schedule = Schedule(**defaults)
        db.session.add(schedule)
        db.session.commit()
        return schedule

    return _create_schedule


@pytest.fixture
def availability_factory(models, db, employee_factory):
    """
    Factory for creating EmployeeWeeklyAvailability instances.
    """
    def _create_availability(employee=None, **kwargs):
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

        if employee is None:
            employee = employee_factory()

        defaults = {
            'employee_id': employee.id,
            'day_of_week': 0,  # Monday
            'start_time': '08:00',
            'end_time': '17:00',
            'is_available': True,
        }
        defaults.update(kwargs)
        availability = EmployeeWeeklyAvailability(**defaults)
        db.session.add(availability)
        db.session.commit()
        return availability

    return _create_availability


@pytest.fixture
def time_off_factory(models, db, employee_factory):
    """
    Factory for creating EmployeeTimeOff instances.
    """
    def _create_time_off(employee=None, **kwargs):
        EmployeeTimeOff = models['EmployeeTimeOff']

        if employee is None:
            employee = employee_factory()

        defaults = {
            'employee_id': employee.id,
            'start_date': date.today(),
            'end_date': date.today() + timedelta(days=5),
            'reason': 'Vacation',
        }
        defaults.update(kwargs)
        time_off = EmployeeTimeOff(**defaults)
        db.session.add(time_off)
        db.session.commit()
        return time_off

    return _create_time_off


# =============================================================================
# Helper Fixtures
# =============================================================================

@pytest.fixture
def sample_employee(employee_factory):
    """Create a single sample employee for simple tests."""
    return employee_factory(
        id='EMP001',
        name='John Doe',
        email='john.doe@example.com',
        job_title='Event Specialist'
    )


@pytest.fixture
def sample_supervisor(employee_factory):
    """Create a sample supervisor employee."""
    return employee_factory(
        id='SUP001',
        name='Jane Smith',
        email='jane.smith@example.com',
        job_title='Club Supervisor',
        is_supervisor=True
    )


@pytest.fixture
def sample_event(event_factory):
    """Create a single sample event for simple tests."""
    return event_factory(
        project_name='Test CORE Event',
        project_ref_num=999001,
        event_type='Core'
    )


@pytest.fixture
def sample_juicer_event(event_factory):
    """Create a sample Juicer Production event."""
    return event_factory(
        project_name='Juice PRODUCTION-SPCLTY Event',
        project_ref_num=999002,
        event_type='Juicer Production'
    )
