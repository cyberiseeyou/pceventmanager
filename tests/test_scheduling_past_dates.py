import pytest
from datetime import datetime, timedelta, time
from app.services.scheduling_engine import SchedulingEngine

def test_juicer_event_past_start_date_uses_today(db_session, models):
    """Test that events with past start dates are scheduled for today"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    # Create juicer employee
    juicer = Employee(id="juicer1", name="Juicer", job_title="Juicer Barista")
    db_session.add(juicer)
    db_session.commit()

    # Create rotation for today
    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='juicer1'
    )
    db_session.add(rotation)
    db_session.commit()

    # Create event with start date 3 days in the past
    past_date = today - timedelta(days=3)
    future_due = today + timedelta(days=7)

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12345,
        start_datetime=past_date,
        due_datetime=future_due,
        event_type="Juicer Production",
        estimated_time=540
    )
    db_session.add(event)
    db_session.commit()

    # Run scheduler
    run = SchedulerRunHistory(run_type='manual')
    db_session.add(run)
    db_session.commit()

    engine = SchedulingEngine(db_session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Verify event was scheduled for today, not the past date
    assert event.is_scheduled
    pending = db_session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.schedule_datetime.date() == today.date()

def test_juicer_event_past_start_and_due_fails(db_session, models):
    """Test that events with both dates in past fail appropriately"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    juicer = Employee(id="juicer1", name="Juicer", job_title="Juicer Barista")
    db_session.add(juicer)
    db_session.commit()

    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='juicer1'
    )
    db_session.add(rotation)
    db_session.commit()

    # Both dates in the past
    past_start = today - timedelta(days=7)
    past_due = today - timedelta(days=2)

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12346,
        start_datetime=past_start,
        due_datetime=past_due,
        event_type="Juicer Production",
        estimated_time=540
    )
    db_session.add(event)
    db_session.commit()

    run = SchedulerRunHistory(run_type='manual')
    db_session.add(run)
    db_session.commit()

    engine = SchedulingEngine(db_session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should fail
    assert not event.is_scheduled
    pending = db_session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.failure_reason is not None
    assert "past" in pending.failure_reason.lower()

def test_juicer_event_future_start_date_unchanged(db_session, models):
    """Test that events with future start dates use the start date"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    juicer = Employee(id="juicer1", name="Juicer", job_title="Juicer Barista")
    db_session.add(juicer)
    db_session.commit()

    # Future date
    future_start = datetime.now() + timedelta(days=5)
    future_due = future_start + timedelta(days=7)

    rotation = RotationAssignment(
        day_of_week=future_start.weekday(),
        rotation_type='juicer',
        employee_id='juicer1'
    )
    db_session.add(rotation)
    db_session.commit()

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12347,
        start_datetime=future_start,
        due_datetime=future_due,
        event_type="Juicer Production",
        estimated_time=540
    )
    db_session.add(event)
    db_session.commit()

    run = SchedulerRunHistory(run_type='manual')
    db_session.add(run)
    db_session.commit()

    engine = SchedulingEngine(db_session, models)
    engine._schedule_juicer_event_wave2(run, event)

    # Should be scheduled on the future start date
    assert event.is_scheduled
    pending = db_session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.schedule_datetime.date() == future_start.date()
