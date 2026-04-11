"""Conformance tests for spec 06-digitals.md.

Covers spec branches D1–D15: subcategory partitioning by name
ends-with, Saturday-only Setup restriction, +15 min offsets, Setup/
Refresh shared Primary Lead → Backup Lead → CS chain, and Teardown's
unique "non-Primary Lead scheduled that day" logic.
"""
from datetime import datetime, time, timedelta


from app.services.scheduler_helpers import digital_subcategory

# Mirrors the pinned frozen clock in conftest.py — Wed Apr 15 2026 @ noon.
FROZEN_NOW = datetime(2026, 4, 15, 12, 0, 0)


# ---------------------------------------------------------------------------
# Subcategory classifier unit tests (D1, D6, D10)
# ---------------------------------------------------------------------------


def test_d1_classifier_setup_ends_with():
    assert digital_subcategory('191001-Brand-Digital Demo Setup') == 'setup'


def test_d6_classifier_refresh_ends_with():
    assert digital_subcategory('191002-Digital Demo Refresh') == 'refresh'


def test_d10_classifier_teardown_ends_with():
    assert digital_subcategory(
        '191003-Brand Digital Demo Tear Down'
    ) == 'teardown'


def test_classifier_unknown_returns_none():
    assert digital_subcategory('191004-Generic Digitals Event') is None
    assert digital_subcategory('') is None
    assert digital_subcategory(None) is None


# ---------------------------------------------------------------------------
# Date helpers — find a future Saturday and a future non-Saturday
# ---------------------------------------------------------------------------


def _next_saturday_after(base_date) -> datetime:
    """Return the first Saturday at midnight strictly after `base_date`."""
    from datetime import date as date_cls
    d = base_date.date() if hasattr(base_date, 'date') else base_date
    if not isinstance(d, date_cls):
        d = d.date()
    while d.weekday() != 5:
        d = d + timedelta(days=1)
    if d <= (base_date.date() if hasattr(base_date, 'date') else base_date):
        d = d + timedelta(days=7)
    return datetime.combine(d, time(0, 0))


def _next_non_saturday_after(base_date) -> datetime:
    from datetime import date as date_cls
    d = base_date.date() if hasattr(base_date, 'date') else base_date
    if not isinstance(d, date_cls):
        d = d.date()
    d = d + timedelta(days=1)
    while d.weekday() == 5:
        d = d + timedelta(days=1)
    return datetime.combine(d, time(0, 0))


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


def _mk_primary_lead_rotation(db, models, dow, employee_id,
                               backup_employee_id=None):
    RotationAssignment = models['RotationAssignment']
    db.add(RotationAssignment(
        day_of_week=dow, rotation_type='primary_lead',
        employee_id=employee_id, backup_employee_id=backup_employee_id,
    ))
    db.flush()


def _mk_digital(db, models, ref_num, start_dt, name, *, event_type='Digitals',
                due_days=2):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name,
        event_type=event_type,
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=15,
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


def _mk_freeosk(db, models, ref_num, start_dt, name='FSK-Daily Service-11AM'):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=f'{ref_num:06d}-{name}',
        event_type='Freeosk',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=2),
        estimated_time=15,
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
# D2/D3 — Setup Saturday restriction
# ---------------------------------------------------------------------------


def test_d3_setup_non_saturday_manual_review(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D3: Setup with a non-Saturday start_date goes to manual review."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    non_sat = _next_non_saturday_after(FROZEN_NOW + timedelta(days=5))
    _mk_primary_lead_rotation(db_session, models, non_sat.weekday(), 'L1')
    _mk_digital(db_session, models, 1101001, non_sat,
                name='1101001-Brand-Digital Demo Setup')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=1101001,
        reason_contains='must be on Saturdays',
    )


def test_d2_setup_saturday_allowed(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D2: Setup with a Saturday start_date proceeds to assignment."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    sat = _next_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, sat.weekday(), 'L1')
    _mk_digital(db_session, models, 1102001, sat,
                name='1102001-Brand-Digital Demo Setup')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1102001,
        employee_id='cs1',  # no primary → CS unconditional
        scheduled_datetime=datetime.combine(sat.date(), time(10, 15)),
    )


# ---------------------------------------------------------------------------
# D4 — Setup +15 min offsets
# ---------------------------------------------------------------------------


def test_d4_setup_15min_offsets(
    greedy_scheduler, models, db_session
):
    """Spec D4: multiple Setups on the same Saturday get unique times
    at +15 min offsets starting from 10:15."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    sat = _next_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, sat.weekday(), 'L1')

    for i, ref in enumerate([1103001, 1103002, 1103003]):
        _mk_digital(db_session, models, ref, sat,
                    name=f'{ref:06d}-Brand-Digital Demo Setup')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    rows = (db_session.query(PendingSchedule)
            .filter_by(scheduler_run_id=run.id)
            .filter(PendingSchedule.event_ref_num.in_(
                [1103001, 1103002, 1103003]))
            .order_by(PendingSchedule.schedule_datetime)
            .all())
    times = [r.schedule_datetime.time() for r in rows]
    assert times == [time(10, 15), time(10, 30), time(10, 45)]


# ---------------------------------------------------------------------------
# D5 — Setup employee priority
# ---------------------------------------------------------------------------


def test_d5_setup_primary_lead_with_primary_event(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D5: Primary Lead with primary event gets the Setup."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    sat = _next_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, sat.weekday(), 'L1')

    core = _mk_core(db_session, models, 1104900, sat)
    _mk_posted_schedule(db_session, models, core, 'L1',
                        datetime.combine(sat.date(), time(10, 15)))

    _mk_digital(db_session, models, 1104001, sat,
                name='1104001-Brand-Digital Demo Setup')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1104001,
        employee_id='L1',
        scheduled_datetime=datetime.combine(sat.date(), time(10, 15)),
    )


# ---------------------------------------------------------------------------
# D7/D8 — Refresh any-day and Saturday vs other-day base time
# ---------------------------------------------------------------------------


def test_d8_refresh_non_saturday_at_1015(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D8: Refresh on a non-Saturday uses base time 10:15."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    non_sat = _next_non_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, non_sat.weekday(), 'L1')

    _mk_digital(db_session, models, 1105001, non_sat,
                name='1105001-Brand-Digital Demo Refresh')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1105001,
        employee_id='cs1',  # no primary → CS
        scheduled_datetime=datetime.combine(non_sat.date(), time(10, 15)),
    )


def test_d8_refresh_saturday_at_noon(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D8: Refresh on a Saturday uses base time 12:00."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    sat = _next_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, sat.weekday(), 'L1')

    _mk_digital(db_session, models, 1106001, sat,
                name='1106001-Brand-Digital Demo Refresh')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1106001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(sat.date(), time(12, 0)),
    )


# ---------------------------------------------------------------------------
# D11/D12 — Teardown any-day and 5 PM base time
# ---------------------------------------------------------------------------


def test_d11_d12_teardown_any_day_at_5pm_with_offsets(
    greedy_scheduler, models, db_session
):
    """Spec D11/D12: Teardown on any day (here Tuesday) at 5:00 PM with
    +15 min offsets across multiple events on the same day."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_lead(db_session, models, 'L2', 'Bob')
    _mk_cs(db_session, models)
    tue = _next_non_saturday_after(FROZEN_NOW + timedelta(days=4))
    # Ensure L2 is the scheduled lead on target date (for D13 scheduling)
    _mk_primary_lead_rotation(db_session, models, tue.weekday(), 'L1')
    # L2 has a Freeosk on target → counts as "scheduled that day"
    _mk_freeosk(db_session, models, 1107900, tue)
    PendingSchedule = models['PendingSchedule']
    # Pre-plant a posted Schedule for L2 on target (any event type works)
    Schedule = models['Schedule']
    fsk = (db_session.query(models['Event'])
           .filter_by(project_ref_num=1107900).one())
    db_session.add(Schedule(event_ref_num=1107900, employee_id='L2',
                             schedule_datetime=datetime.combine(
                                 tue.date(), time(10, 0))))
    fsk.is_scheduled = True

    for ref in [1107001, 1107002]:
        _mk_digital(db_session, models, ref, tue,
                    name=f'{ref:06d}-Brand Digital Demo Tear Down')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    rows = (db_session.query(PendingSchedule)
            .filter_by(scheduler_run_id=run.id)
            .filter(PendingSchedule.event_ref_num.in_([1107001, 1107002]))
            .order_by(PendingSchedule.schedule_datetime)
            .all())
    assert [r.schedule_datetime.time() for r in rows] == \
        [time(17, 0), time(17, 15)]
    # D13: both assigned to L2 (non-primary lead scheduled that day)
    assert all(r.employee_id == 'L2' for r in rows)


# ---------------------------------------------------------------------------
# D13 — Teardown assigns to non-Primary Lead scheduled that day
# ---------------------------------------------------------------------------


def test_d13_teardown_non_primary_lead_scheduled(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D13: a non-Primary Lead who is scheduled (any event type) on
    target_date gets the Teardown — NOT the Primary Lead."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_lead(db_session, models, 'L2', 'Bob')
    _mk_cs(db_session, models)
    tue = _next_non_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, tue.weekday(), 'L1')

    # Both L1 (primary lead) and L2 (non-primary lead) have something
    # posted that day. L2 should win because D13 excludes the Primary Lead.
    c1 = _mk_core(db_session, models, 1108901, tue)
    _mk_posted_schedule(db_session, models, c1, 'L1',
                        datetime.combine(tue.date(), time(10, 15)))
    c2 = _mk_core(db_session, models, 1108902, tue)
    _mk_posted_schedule(db_session, models, c2, 'L2',
                        datetime.combine(tue.date(), time(10, 45)))

    _mk_digital(db_session, models, 1108001, tue,
                name='1108001-Brand Digital Demo Tear Down')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1108001,
        employee_id='L2',
        scheduled_datetime=datetime.combine(tue.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# D15 — Teardown CS unconditional fallback
# ---------------------------------------------------------------------------


def test_d15_teardown_cs_fallback_unconditional(
    greedy_scheduler, models, db_session, spec_assert
):
    """Spec D15: no non-Primary Lead scheduled that day → CS gets Teardown."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    tue = _next_non_saturday_after(FROZEN_NOW + timedelta(days=4))
    _mk_primary_lead_rotation(db_session, models, tue.weekday(), 'L1')

    # Only the Primary Lead has something scheduled — D13 excludes them,
    # so the Teardown falls through to CS.
    core = _mk_core(db_session, models, 1109900, tue)
    _mk_posted_schedule(db_session, models, core, 'L1',
                        datetime.combine(tue.date(), time(10, 15)))

    _mk_digital(db_session, models, 1109001, tue,
                name='1109001-Brand Digital Demo Tear Down')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1109001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(tue.date(), time(17, 0)),
    )
