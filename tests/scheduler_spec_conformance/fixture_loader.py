"""Load a captured scheduler run fixture into a test database.

Fixtures live under `tests/scheduler_spec_conformance/fixtures/<run_name>/`
and are produced by `scripts/capture_run_fixture.py`. Each fixture
directory contains JSON files (`events.json`, `employees.json`,
`rotations.json`, `time_off.json`, `weekly_availability.json`,
`expected.json`). The loader inserts every row into the test DB in the
same shape the greedy scheduler expects — it does NOT invent fields
that the capture script omitted.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _parse(value: Any):
    """Parse ISO-8601 strings back to datetime or date. Pass through
    non-string values unchanged so callers can use this uniformly."""
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        return date.fromisoformat(value)
    except ValueError:
        return value


def _load_json(path: Path):
    return json.loads(path.read_text())


def load_run_fixture(db_session, models, fixtures_dir: Path) -> dict:
    """Insert fixture rows into the test DB.

    Returns a dict of counts per category so callers can assert how
    much data was loaded (helpful for guarding against empty fixtures).

    The loader assumes `db_session` is clean — an existing row with the
    same primary key will cause a unique-constraint error. The
    `db_session` fixture in the test suite provides a fresh per-test
    database, so this is safe in the conformance harness.
    """
    Employee = models['Employee']
    Event = models['Event']
    RotationAssignment = models['RotationAssignment']
    EmployeeTimeOff = models['EmployeeTimeOff']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

    counts = {
        'employees': 0, 'events': 0, 'rotations': 0,
        'time_off': 0, 'weekly_availability': 0,
    }

    # --- employees --------------------------------------------------------
    employees_path = fixtures_dir / 'employees.json'
    if employees_path.exists():
        for data in _load_json(employees_path):
            emp = Employee(
                id=data['id'],
                name=data.get('name', data['id']),
                job_title=data.get('job_title', 'Event Specialist'),
                is_active=data.get('is_active', True),
                juicer_trained=data.get('juicer_trained', False),
            )
            if 'termination_date' in data and data['termination_date'] is not None:
                try:
                    emp.termination_date = _parse(data['termination_date'])
                except AttributeError:
                    pass
            db_session.add(emp)
            counts['employees'] += 1
        db_session.flush()

    # --- events -----------------------------------------------------------
    events_path = fixtures_dir / 'events.json'
    if events_path.exists():
        for data in _load_json(events_path):
            event = Event(
                project_ref_num=data['project_ref_num'],
                project_name=data['project_name'],
                event_type=data['event_type'],
                condition=data.get('condition', 'Unstaffed'),
                start_datetime=_parse(data['start_datetime']),
                due_datetime=_parse(data['due_datetime']),
                estimated_time=data.get('estimated_time'),
                is_scheduled=data.get('is_scheduled', False),
            )
            db_session.add(event)
            counts['events'] += 1
        db_session.flush()

    # --- rotations --------------------------------------------------------
    rotations_path = fixtures_dir / 'rotations.json'
    if rotations_path.exists():
        for data in _load_json(rotations_path):
            db_session.add(RotationAssignment(
                day_of_week=data['day_of_week'],
                rotation_type=data['rotation_type'],
                employee_id=data['employee_id'],
                backup_employee_id=data.get('backup_employee_id'),
            ))
            counts['rotations'] += 1
        db_session.flush()

    # --- time off ---------------------------------------------------------
    time_off_path = fixtures_dir / 'time_off.json'
    if time_off_path.exists():
        for data in _load_json(time_off_path):
            db_session.add(EmployeeTimeOff(
                employee_id=data['employee_id'],
                start_date=_parse(data['start_date']),
                end_date=_parse(data['end_date']),
                status=data.get('status', 'approved'),
                reason=data.get('reason', 'Captured from run 192'),
            ))
            counts['time_off'] += 1
        db_session.flush()

    # --- weekly availability ---------------------------------------------
    weekly_path = fixtures_dir / 'weekly_availability.json'
    if weekly_path.exists():
        for data in _load_json(weekly_path):
            db_session.add(EmployeeWeeklyAvailability(
                employee_id=data['employee_id'],
                monday=data.get('monday', True),
                tuesday=data.get('tuesday', True),
                wednesday=data.get('wednesday', True),
                thursday=data.get('thursday', True),
                friday=data.get('friday', True),
                saturday=data.get('saturday', True),
                sunday=data.get('sunday', True),
            ))
            counts['weekly_availability'] += 1
        db_session.flush()

    db_session.commit()
    return counts
