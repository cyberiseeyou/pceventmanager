import pytest
from datetime import datetime, date, time, timedelta

def _next_weekday(weekday):
    """Return a future date for the given weekday (0=Mon, 1=Tue, etc.), at least 7 days out."""
    today = date.today()
    future = today + timedelta(days=7)
    days_ahead = weekday - future.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return future + timedelta(days=days_ahead)

def test_validator_availability(db_session, models):
    """Test availability validation."""
    from app.services.constraint_validator import ConstraintValidator, ConstraintType

    validator = ConstraintValidator(db_session, models)
    Employee = models['Employee']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
    Event = models['Event']

    # Setup
    emp = Employee(id="test_emp", name="Test Emp", job_title="Event Specialist")
    db_session.add(emp)
    db_session.commit() # Commit employee first

    # Available on Monday (0), Unavailable on Tuesday (1)
    avail = EmployeeWeeklyAvailability(employee_id=emp.id, monday=True, tuesday=False)
    db_session.add(avail)

    # Use future dates to avoid past-date validation
    future_monday = _next_weekday(0)  # Monday
    future_tuesday = future_monday + timedelta(days=1)  # Tuesday
    event = Event(project_ref_num=999, project_name="Test Event", event_type="Core", estimated_time=60)
    event.start_datetime = datetime.combine(future_monday - timedelta(days=7), time(0, 0))
    event.due_datetime = datetime.combine(future_tuesday + timedelta(days=7), time(0, 0))
    db_session.add(event)
    db_session.commit()

    # Test Monday - employee is available
    monday = datetime.combine(future_monday, time(10, 0))
    result = validator.validate_assignment(event, emp, monday)
    assert result.is_valid is True

    # Test Tuesday - employee is NOT available
    tuesday = datetime.combine(future_tuesday, time(10, 0))
    result = validator.validate_assignment(event, emp, tuesday)
    assert result.is_valid is False
    assert len(result.violations) == 1
    assert result.violations[0].constraint_type == ConstraintType.AVAILABILITY

def test_validator_daily_limit(db_session, models):
    """Test daily limit (max 1 Core event)."""
    from app.services.constraint_validator import ConstraintValidator, ConstraintType

    validator = ConstraintValidator(db_session, models)
    Employee = models['Employee']
    Event = models['Event']
    Schedule = models['Schedule']

    # Setup
    emp = Employee(id="test_emp_limit", name="Test Emp Limit", job_title="Event Specialist")
    db_session.add(emp)

    # Existing Core event
    event1 = Event(project_ref_num=101, project_name="Core 1", event_type="Core", 
                   start_datetime=datetime(2026, 1, 5), due_datetime=datetime(2026, 1, 6))
    db_session.add(event1)
    
    sched1 = Schedule(event_ref_num=101, employee_id=emp.id, 
                      schedule_datetime=datetime(2026, 1, 5, 10, 0))
    db_session.add(sched1)

    # New Core event proposed for same day
    event2 = Event(project_ref_num=102, project_name="Core 2", event_type="Core",
                   start_datetime=datetime(2026, 1, 5), due_datetime=datetime(2026, 1, 6))
    db_session.add(event2)
    db_session.commit()

    # Validate
    result = validator.validate_assignment(event2, emp, datetime(2026, 1, 5, 14, 0))
    assert result.is_valid is False
    assert any(v.constraint_type == ConstraintType.DAILY_LIMIT for v in result.violations)

def test_validator_role_check(db_session, models):
    """Test role requirements."""
    from app.services.constraint_validator import ConstraintValidator, ConstraintType

    validator = ConstraintValidator(db_session, models)
    Employee = models['Employee']
    Event = models['Event']

    emp = Employee(id="spec", name="Specialist", job_title="Event Specialist")
    db_session.add(emp)

    # Juicer event requires Juicer Barista
    event = Event(project_ref_num=888, project_name="Juicer Prod", event_type="Juicer Production", 
                  start_datetime=datetime(2026, 1, 1), due_datetime=datetime(2026, 1, 10))
    db_session.add(event)
    db_session.commit()

    result = validator.validate_assignment(event, emp, datetime(2026, 1, 5, 9, 0))
    assert result.is_valid is False
    assert any(v.constraint_type == ConstraintType.ROLE for v in result.violations)
