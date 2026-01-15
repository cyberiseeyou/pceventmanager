import pytest
from datetime import datetime, timedelta, time

def test_sort_events_by_priority(db_session, models):
    """Test priority sorting: Due Date -> Event Type."""
    from app.services.scheduling_engine import SchedulingEngine
    
    engine = SchedulingEngine(db_session, models)
    Event = models['Event']

    # Create events
    today = datetime.now()
    
    # Event A: Core, due in 5 days
    e_core_later = Event(project_ref_num=1, event_type="Core", due_datetime=today + timedelta(days=5))
    
    # Event B: Core, due in 2 days (More urgent than A)
    e_core_soon = Event(project_ref_num=2, event_type="Core", due_datetime=today + timedelta(days=2))
    
    # Event C: Juicer, due in 5 days (Same due date as A, but Juicer type is higher priority than Core)
    e_juicer_later = Event(project_ref_num=3, event_type="Juicer Production", due_datetime=today + timedelta(days=5))

    events = [e_core_later, e_core_soon, e_juicer_later]
    
    sorted_events = engine._sort_events_by_priority(events)
    
    # Expected order:
    # 1. e_core_soon (Due in 2 days - Earliest due date wins first)
    # 2. e_juicer_later (Due in 5 days, Type Priority 1)
    # 3. e_core_later (Due in 5 days, Type Priority 6)
    
    assert sorted_events[0] == e_core_soon
    assert sorted_events[1] == e_juicer_later
    assert sorted_events[2] == e_core_later

def test_schedule_juicer_event_basic(db_session, models):
    """Test basic scheduling of a Juicer event to a Juicer employee."""
    from app.services.scheduling_engine import SchedulingEngine
    from app.services.rotation_manager import RotationManager
    
    # Setup
    engine = SchedulingEngine(db_session, models)
    Employee = models['Employee']
    Event = models['Event']
    RotationAssignment = models['RotationAssignment']
    
    # Create Juicer Employee
    juicer = Employee(id="juicer1", name="Juicer One", job_title="Juicer Barista")
    db_session.add(juicer)
    
    # Setup Rotation for Juicer (assign them to today + 3 days)
    today = datetime.now()
    start_date = today + timedelta(days=3)
    target_date = start_date.date()
    
    # Mock RotationManager's get_rotation_employee behavior by populating DB
    # (The RotationManager reads from RotationAssignment table usually, or computed)
    # Let's verify RotationManager implementation briefly or rely on logic
    # RotationManager.get_rotation_employee usually checks rotation settings.
    # To simplify, we can mock the method on the engine instance.
    
    # Create Event
    event = Event(
        project_ref_num=100,
        project_name="JUICER-PRODUCTION-SPCLTY",
        event_type="Juicer Production",
        condition="Unstaffed",
        start_datetime=start_date,
        due_datetime=start_date + timedelta(days=2),
        estimated_time=540
    )
    db_session.add(event)
    db_session.commit()
    
    # Mock the rotation manager on the engine instance
    class MockRotationManager:
        def get_rotation_employee(self, date_obj, role_type):
            if role_type == 'juicer':
                return juicer
            return None
    
    engine.rotation_manager = MockRotationManager()
    
    # Run scheduling for this event
    run_history = engine.SchedulerRunHistory(run_type='manual', started_at=datetime.utcnow(), status='running')
    db_session.add(run_history)
    db_session.flush() # get ID
    
    engine._schedule_juicer_events_wave1(run_history, [event])
    
    # Verify assignment
    pending = db_session.query(models['PendingSchedule']).filter_by(
        event_ref_num=100
    ).first()
    
    assert pending is not None
    assert pending.employee_id == juicer.id
    assert pending.schedule_datetime.date() == target_date
