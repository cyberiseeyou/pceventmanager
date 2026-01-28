import pytest
from datetime import datetime
from app.services.rotation_manager import RotationManager

def test_get_rotation_employee_returns_backup_when_requested(db_session, models):
    """Test that get_rotation_employee returns backup when try_backup=True"""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    # Create employees
    primary = Employee(id="emp1", name="Primary Juicer", job_title="Juicer Barista")
    backup = Employee(id="emp2", name="Backup Juicer", job_title="Juicer Barista")
    db_session.add_all([primary, backup])
    db_session.commit()

    # Create rotation with backup
    rotation = RotationAssignment(
        day_of_week=0,  # Monday
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    db_session.add(rotation)
    db_session.commit()

    # Test primary
    manager = RotationManager(db_session, models)
    monday = datetime(2026, 2, 2)  # A Monday

    primary_emp = manager.get_rotation_employee(monday, 'juicer', try_backup=False)
    assert primary_emp.id == 'emp1'

    # Test backup
    backup_emp = manager.get_rotation_employee(monday, 'juicer', try_backup=True)
    assert backup_emp.id == 'emp2'

def test_get_rotation_employee_returns_primary_when_no_backup_configured(db_session, models):
    """Test fallback to primary when backup not configured"""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    primary = Employee(id="emp1", name="Primary", job_title="Juicer Barista")
    db_session.add(primary)
    db_session.commit()

    rotation = RotationAssignment(
        day_of_week=0,
        rotation_type='juicer',
        employee_id='emp1',
        backup_employee_id=None  # No backup
    )
    db_session.add(rotation)
    db_session.commit()

    manager = RotationManager(db_session, models)
    monday = datetime(2026, 2, 2)

    # Both should return primary
    emp1 = manager.get_rotation_employee(monday, 'juicer', try_backup=False)
    emp2 = manager.get_rotation_employee(monday, 'juicer', try_backup=True)
    assert emp1.id == 'emp1'
    assert emp2.id == 'emp1'

def test_get_rotation_with_backup_returns_both(db_session, models):
    """Test get_rotation_with_backup returns (primary, backup) tuple"""
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    primary = Employee(id="emp1", name="Primary", job_title="Lead Event Specialist")
    backup = Employee(id="emp2", name="Backup", job_title="Lead Event Specialist")
    db_session.add_all([primary, backup])
    db_session.commit()

    rotation = RotationAssignment(
        day_of_week=1,  # Tuesday
        rotation_type='primary_lead',
        employee_id='emp1',
        backup_employee_id='emp2'
    )
    db_session.add(rotation)
    db_session.commit()

    manager = RotationManager(db_session, models)
    tuesday = datetime(2026, 2, 3)

    primary_emp, backup_emp = manager.get_rotation_with_backup(tuesday, 'primary_lead')
    assert primary_emp.id == 'emp1'
    assert backup_emp.id == 'emp2'
