"""Conformance tests for spec 07-other.md.

Covers spec branches O1–O6 and the cross-category invariant K7:
Club Supervisor is the FIRST choice for Other events (NOT a fallback),
Primary Lead is the fallback, and manual review is the final exit.
All assignments are at 12:00 PM.
"""
from datetime import datetime, time, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_employee(db, models, emp_id, name, *, job_title='Event Specialist'):
    Employee = models['Employee']
    emp = Employee(id=emp_id, name=name, job_title=job_title,
                   juicer_trained=False, is_active=True)
    db.add(emp)
    db.flush()
    return emp


def _mk_lead(db, models, emp_id, name):
    return _mk_employee(db, models, emp_id, name,
                        job_title='Lead Event Specialist')


def _mk_cs(db, models, emp_id='cs1', name='Grace'):
    return _mk_employee(db, models, emp_id, name,
                        job_title='Club Supervisor')


def _mk_primary_lead_rotation(db, models, dow, employee_id):
    RotationAssignment = models['RotationAssignment']
    db.add(RotationAssignment(
        day_of_week=dow, rotation_type='primary_lead',
        employee_id=employee_id,
    ))
    db.flush()


def _mk_other(db, models, ref_num, start_dt, *, due_days=2, name=None):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d}-Other-Generic',
        event_type='Other',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=60,
    )
    db.add(event)
    db.flush()
    return event


def _mk_core(db, models, ref_num, start_dt):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=f'{ref_num:06d}-Brand-CORE',
        event_type='Core',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=7),
        estimated_time=390,
    )
    db.add(event)
    db.flush()
    return event


def _mk_posted_schedule(db, models, event, emp_id, at_datetime):
    Schedule = models['Schedule']
    row = Schedule(event_ref_num=event.project_ref_num, employee_id=emp_id,
                   schedule_datetime=at_datetime)
    db.add(row)
    event.is_scheduled = True
    db.flush()
    return row


def _mk_pto(db, models, emp_id, day):
    EmployeeTimeOff = models['EmployeeTimeOff']
    db.add(EmployeeTimeOff(employee_id=emp_id, start_date=day, end_date=day,
                            status='approved', reason='Test PTO'))
    db.flush()


# ---------------------------------------------------------------------------
# O2/O3 — CS first choice
# ---------------------------------------------------------------------------


def test_o2_o3_cs_first_when_available(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O2+O3: CS available → Other goes to CS @ 12 PM."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    target = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, target.weekday(), 'L1')
    _mk_other(db_session, models, 1201001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1201001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target.date(), time(12, 0)),
    )


# ---------------------------------------------------------------------------
# K7 — Reversed priority (CS wins even when Primary Lead has a CORE)
# ---------------------------------------------------------------------------


def test_k7_cs_wins_over_primary_lead_with_core(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Cross-category K7: CS is ALWAYS the first choice for Other events,
    even when the Primary Lead has a primary event on target_date."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    target = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, target.weekday(), 'L1')
    core = _mk_core(db_session, models, 1202900, target)
    _mk_posted_schedule(db_session, models, core, 'L1',
                        datetime.combine(target.date(), time(10, 15)))

    _mk_other(db_session, models, 1202001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1202001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target.date(), time(12, 0)),
    )


# ---------------------------------------------------------------------------
# O4/O5 — Primary Lead fallback when CS unavailable
# ---------------------------------------------------------------------------


def test_o4_o5_primary_lead_fallback_when_cs_pto(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O4+O5: CS on PTO → Primary Lead gets the Other event.
    Note: spec does NOT require Primary Lead to have a primary event."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    target = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, target.weekday(), 'L1')
    _mk_pto(db_session, models, 'cs1', target.date())

    _mk_other(db_session, models, 1203001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1203001,
        employee_id='L1',
        scheduled_datetime=datetime.combine(target.date(), time(12, 0)),
    )


# ---------------------------------------------------------------------------
# O6 — Manual review when both unavailable
# ---------------------------------------------------------------------------


def test_o6_manual_review_when_both_unavailable(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O6: CS + Primary Lead both on PTO → manual review."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    target = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, target.weekday(), 'L1')
    _mk_pto(db_session, models, 'cs1', target.date())
    _mk_pto(db_session, models, 'L1', target.date())

    _mk_other(db_session, models, 1204001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=1204001,
        reason_contains='Club Supervisor on PTO and Primary Lead unavailable',
    )


# ---------------------------------------------------------------------------
# O6 no-CS case — no Club Supervisor employee exists at all
# ---------------------------------------------------------------------------


def test_o6_no_cs_no_primary_lead_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec O6: no CS employee + no primary lead rotation → manual review."""
    _mk_other(db_session, models, 1205001, future_datetime(5))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(run_id=run.id, event_ref_num=1205001)
