"""Scheduler invariants that must hold for every run, regardless of spec branch."""
from datetime import datetime, timedelta


def test_every_event_produces_exactly_one_pending_schedule(
    greedy_scheduler, models, db_session, future_datetime
):
    """Invariant: no silent drops, no duplicates.

    Run the scheduler against 3 events of different types; assert each
    has exactly one PendingSchedule in the run.
    """
    Event = models['Event']
    Employee = models['Employee']
    PendingSchedule = models['PendingSchedule']

    # Create a minimal employee + rotation context
    emp = Employee(id='jb1', name='Frank', job_title='Juicer Barista',
                   juicer_trained=True)
    db_session.add(emp)
    db_session.flush()

    # Add 3 events: one Juicer, one CORE, one Freeosk.
    events = [
        Event(project_ref_num=900001, project_name='900001-JUICER-PRODUCTION-Test',
              event_type='Juicer Production', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(7),
              estimated_time=540),
        Event(project_ref_num=900002, project_name='900002-CORE-Test',
              event_type='Core', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(12),
              estimated_time=390),
        Event(project_ref_num=900003, project_name='900003-FSK-Daily Service-11AM',
              event_type='Freeosk', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(6),
              estimated_time=60),
    ]
    for e in events:
        db_session.add(e)
    db_session.commit()

    # Run the greedy scheduler
    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Invariant: every event has exactly one PendingSchedule
    for e in events:
        count = (db_session.query(PendingSchedule)
                 .filter_by(scheduler_run_id=run.id,
                            event_ref_num=e.project_ref_num)
                 .count())
        assert count == 1, (
            f"Event {e.project_ref_num} has {count} PendingSchedule rows "
            f"in run {run.id}, expected exactly 1")


def test_pending_schedule_null_employee_requires_failure_reason(
    greedy_scheduler, models, db_session, future_datetime
):
    """Invariant: PendingSchedule(employee_id=None) MUST have failure_reason."""
    Event = models['Event']
    PendingSchedule = models['PendingSchedule']

    # Create an unschedulable event: no employees at all
    e = Event(project_ref_num=900010, project_name='900010-CORE-Impossible',
              event_type='Core', condition='Unstaffed',
              start_datetime=future_datetime(5), due_datetime=future_datetime(7),
              estimated_time=390)
    db_session.add(e)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    ps = (db_session.query(PendingSchedule)
          .filter_by(scheduler_run_id=run.id, event_ref_num=900010)
          .one())
    assert ps.employee_id is None
    assert ps.failure_reason is not None, (
        "Invariant violated: PendingSchedule with employee_id=None must "
        "have a failure_reason set")
