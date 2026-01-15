import pytest
from datetime import datetime, timedelta

def test_employee_can_work_event_type(models):
    """Test Employee.can_work_event_type logic."""
    Employee = models['Employee']
    
    # Create employees with different roles
    supervisor = Employee(id="sup", name="Super", job_title="Club Supervisor")
    lead = Employee(id="lead", name="Leader", job_title="Lead Event Specialist")
    barista = Employee(id="juice", name="Juicer", job_title="Juicer Barista")
    specialist = Employee(id="spec", name="Specialist", job_title="Event Specialist")

    # Test Supervisor events
    assert supervisor.can_work_event_type("Supervisor") is True
    assert lead.can_work_event_type("Supervisor") is True # Logic says Leads are OK
    assert specialist.can_work_event_type("Supervisor") is False

    # Test Juicer events
    assert supervisor.can_work_event_type("Juicer Production") is True
    assert barista.can_work_event_type("Juicer Production") is True
    assert specialist.can_work_event_type("Juicer Production") is False

    # Test Core events (everyone)
    assert specialist.can_work_event_type("Core") is True
    assert supervisor.can_work_event_type("Core") is True

def test_event_detect_event_type(models):
    """Test Event.detect_event_type logic."""
    Event = models['Event']

    e1 = Event(project_name="CORE Event 123")
    assert e1.detect_event_type() == "Core"

    e2 = Event(project_name="Digital Setup V2")
    assert e2.detect_event_type() == "Digitals"

    e3 = Event(project_name="JUICER-PRODUCTION-SPCLTY")
    assert e3.detect_event_type() == "Juicer Production"

    e4 = Event(project_name="JUICER SURVEY-SPCLTY")
    assert e4.detect_event_type() == "Juicer Survey"

    e5 = Event(project_name="Freeosk Demo")
    assert e5.detect_event_type() == "Freeosk"

    e6 = Event(project_name="Unknown Event")
    assert e6.detect_event_type() == "Other"

def test_event_default_duration(models):
    """Test Event duration logic."""
    Event = models['Event']
    
    e = Event(project_name="CORE Event", event_type="Core")
    e.set_default_duration()
    assert e.estimated_time == 390  # 6.5 hours

    e2 = Event(project_name="Supervisor Check", event_type="Supervisor")
    e2.set_default_duration()
    assert e2.estimated_time == 5   # 5 minutes
