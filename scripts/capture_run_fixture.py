"""Capture a scheduler-run fixture from the current DB state.

Usage:
    python scripts/capture_run_fixture.py --run-id 192 --out tests/scheduler_spec_conformance/fixtures/run_192

This script reads the dev DB (instance/scheduler.db via the 'development' Flask
config) and captures the exact set of events that were in a scheduler run's
scope, plus all supporting data (rotations, time-off, weekly availability,
employees) needed to deterministically replay the run in a regression test.

The events captured are EXACTLY those that appeared as PendingSchedule rows
under the given run_id — we join against pending_schedules rather than
re-computing "open events at run time" because that is the only reliable way
to recover the historical input set.

The script is read-only. It does not modify the DB.
"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from app import create_app
from app.models import get_models, get_db


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def capture(run_id: int, out_dir: Path):
    app = create_app('development')
    with app.app_context():
        models = get_models()
        db = get_db()
        Event = models['Event']
        RotationAssignment = models['RotationAssignment']
        EmployeeTimeOff = models['EmployeeTimeOff']
        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
        Employee = models['Employee']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        run = SchedulerRunHistory.query.get(run_id)
        if not run:
            raise SystemExit(f"No run {run_id}")

        # Capture the EXACT events that were in run N's scope by joining
        # against pending_schedules for that run_id. This is authoritative —
        # any other filter (e.g. "unscheduled events with due_date > run.started_at")
        # would capture a different set than what the scheduler actually processed.
        pending_in_run = db.session.query(
            PendingSchedule.event_ref_num
        ).filter_by(scheduler_run_id=run_id).distinct().all()
        event_refs_in_run = {r[0] for r in pending_in_run}
        events = (
            Event.query
            .filter(Event.project_ref_num.in_(event_refs_in_run))
            .order_by(Event.event_type, Event.start_datetime)
            .all()
        )
        events_data = [{
            'project_ref_num': e.project_ref_num,
            'project_name': e.project_name,
            'event_type': e.event_type,
            'condition': e.condition,
            'start_datetime': e.start_datetime,
            'due_datetime': e.due_datetime,
            'estimated_time': e.estimated_time,
        } for e in events]

        rotations = RotationAssignment.query.order_by(
            RotationAssignment.rotation_type, RotationAssignment.day_of_week
        ).all()
        rot_data = [{
            'day_of_week': r.day_of_week,
            'rotation_type': r.rotation_type,
            'employee_id': r.employee_id,
            'backup_employee_id': r.backup_employee_id,
        } for r in rotations]

        time_off = (
            EmployeeTimeOff.query
            .filter_by(status='approved')
            .order_by(EmployeeTimeOff.employee_id, EmployeeTimeOff.start_date)
            .all()
        )
        to_data = [{
            'employee_id': t.employee_id,
            'start_date': t.start_date,
            'end_date': t.end_date,
        } for t in time_off]

        weekly = (
            EmployeeWeeklyAvailability.query
            .order_by(EmployeeWeeklyAvailability.employee_id)
            .all()
        )
        wa_data = [{
            'employee_id': w.employee_id,
            'monday': w.monday, 'tuesday': w.tuesday,
            'wednesday': w.wednesday, 'thursday': w.thursday,
            'friday': w.friday, 'saturday': w.saturday, 'sunday': w.sunday,
        } for w in weekly]

        employees = Employee.query.order_by(Employee.id).all()
        emp_data = [{
            'id': e.id,
            'name': e.name,
            'job_title': e.job_title,
            'is_active': e.is_active,
            'juicer_trained': e.juicer_trained,
            'termination_date': e.termination_date,
        } for e in employees]

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'events.json').write_text(
            json.dumps(events_data, default=_serialize, indent=2))
        (out_dir / 'rotations.json').write_text(
            json.dumps(rot_data, default=_serialize, indent=2))
        (out_dir / 'time_off.json').write_text(
            json.dumps(to_data, default=_serialize, indent=2))
        (out_dir / 'weekly_availability.json').write_text(
            json.dumps(wa_data, default=_serialize, indent=2))
        (out_dir / 'employees.json').write_text(
            json.dumps(emp_data, default=_serialize, indent=2))
        print(
            f"Wrote {len(events_data)} events, {len(rot_data)} rotations, "
            f"{len(to_data)} time-off, {len(wa_data)} weekly availability, "
            f"{len(emp_data)} employees to {out_dir}"
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--out', type=str, required=True)
    args = parser.parse_args()
    capture(args.run_id, Path(args.out))
