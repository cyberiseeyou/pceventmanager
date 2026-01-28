import pytest
from datetime import datetime, timedelta
from app.services.scheduling_engine import SchedulingEngine

def test_backup_used_when_primary_unavailable(db_session, models):
    """Test that backup employee is used when primary has time-off"""
    Event = models['Event']
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    # Create employees
    primary = Employee(id="emp1", name="Primary Juicer", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup Juicer", job_title="Juicer Barista")
    db_session.add_all([primary, backup])
    db_session.commit()

    # Create rotation with backup
    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    db_session.add(rotation)
    db_session.commit()

    # Primary has time off today
    time_off = EmployeeTimeOff(
        employee_id='emp1',
        start_date=today.date(),
        end_date=today.date()
    )
    db_session.add(time_off)
    db_session.commit()

    # Create juicer event for today
    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12348,
        start_datetime=today,
        due_datetime=today + timedelta(days=1),
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

    # Should be scheduled to backup, not primary
    assert event.is_scheduled
    pending = db_session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending is not None
    assert pending.employee_id == 'emp2'  # Backup employee

def test_primary_preferred_when_both_available(db_session, models):
    """Test that primary is used when both primary and backup are available"""
    Event = models['Event']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    primary = Employee(id="emp1", name="Primary", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup", job_title="Juicer Barista")
    db_session.add_all([primary, backup])
    db_session.commit()

    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    db_session.add(rotation)
    db_session.commit()

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12349,
        start_datetime=today,
        due_datetime=today + timedelta(days=1),
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

    # Should use primary
    assert event.is_scheduled
    pending = db_session.query(models['PendingSchedule']).filter_by(
        event_ref_num=event.project_ref_num
    ).first()
    assert pending.employee_id == 'emp1'  # Primary

def test_both_unavailable_creates_failed_schedule(db_session, models):
    """Test failure when both primary and backup are unavailable"""
    Event = models['Event']
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']
    RotationAssignment = models['RotationAssignment']
    SchedulerRunHistory = models['SchedulerRunHistory']

    primary = Employee(id="emp1", name="Primary", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup", job_title="Juicer Barista")
    db_session.add_all([primary, backup])
    db_session.commit()

    today = datetime.now()
    rotation = RotationAssignment(
        day_of_week=today.weekday(),
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    db_session.add(rotation)
    db_session.commit()

    # Both have time off
    for emp_id in ['emp1', 'emp2']:
        time_off = EmployeeTimeOff(
            employee_id=emp_id,
            start_date=today.date(),
            end_date=today.date()
        )
        db_session.add(time_off)
    db_session.commit()

    event = Event(
        project_name="JUICER-PRODUCTION-SPCLTY",
        project_ref_num=12350,
        start_datetime=today,
        due_datetime=today + timedelta(days=1),
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
    assert pending.failure_reason is not None
