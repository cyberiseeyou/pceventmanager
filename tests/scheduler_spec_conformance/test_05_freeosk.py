"""Conformance tests for spec 05-freeosk.md.

Covers spec branches F1–F11: subcategory partitioning by name pattern,
strict processing order (daily service → changeover → troubleshooting),
fixed time per subcategory, and the shared Primary Lead → Backup Lead →
CS unconditional fallback decision tree.
"""
from datetime import datetime, time, timedelta


from app.services.scheduler_helpers import freeosk_subcategory


# ---------------------------------------------------------------------------
# F1 / F2 — Subcategory classifier unit tests
# ---------------------------------------------------------------------------


def test_f1_classifier_daily_service():
    assert freeosk_subcategory(
        '191001-FSK-Daily Service-11AM-Brand'
    ) == 'daily_service'


def test_f1_classifier_changeover():
    assert freeosk_subcategory('191002-CO-11AM-Brand-Product') == 'changeover'


def test_f1_classifier_troubleshooting():
    assert freeosk_subcategory(
        '191003-FSK-Troubleshooting-Visit'
    ) == 'troubleshooting'


def test_f2_classifier_unrecognized_returns_none():
    assert freeosk_subcategory('191004-FSK-Unknown-Format') is None


def test_f1_classifier_empty_returns_none():
    assert freeosk_subcategory('') is None
    assert freeosk_subcategory(None) is None


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


def _mk_freeosk(db, models, ref_num, start_dt, name, *, due_days=2):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name,
        event_type='Freeosk',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=15,
    )
    db.add(event)
    db.flush()
    return event


def _mk_core(db, models, ref_num, start_dt, *, is_scheduled=False):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=f'{ref_num:06d}-Brand-CORE',
        event_type='Core',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=7),
        estimated_time=390,
        is_scheduled=is_scheduled,
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
# F2 — Unrecognized pattern goes to manual review
# ---------------------------------------------------------------------------


def test_f2_unrecognized_name_goes_to_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F2: a Freeosk event with a name not matching any pattern
    produces a manual-review PendingSchedule."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_freeosk(db_session, models, 1001001, start,
                name='1001001-FSK-Unknown-Format')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=1001001,
        reason_contains='unrecognized name pattern',
    )


# ---------------------------------------------------------------------------
# F3 / F4 — Strict subcategory processing order
# ---------------------------------------------------------------------------


def test_f3_f4_subcategory_processing_order(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec F3/F4: events are processed daily_service → changeover →
    troubleshooting regardless of DB insertion order or start date."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')

    # Insert in reverse order: Troubleshooting first, then Changeover,
    # then Daily Service
    _mk_freeosk(db_session, models, 1002001, start,
                name='1002001-FSK-Troubleshooting-Test')
    _mk_freeosk(db_session, models, 1002002, start,
                name='1002002-CO-11AM-Test')
    _mk_freeosk(db_session, models, 1002003, start,
                name='1002003-FSK-Daily Service-11AM-Test')
    db_session.commit()

    observed: list[int] = []
    orig = greedy_scheduler._schedule_single_freeosk

    def spy(event, sub_name, run):
        observed.append((event.project_ref_num, sub_name))
        return orig(event, sub_name, run)

    greedy_scheduler._schedule_single_freeosk = spy
    greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Expected order: daily_service first, then changeover, then trouble
    assert observed == [
        (1002003, 'daily_service'),
        (1002002, 'changeover'),
        (1002001, 'troubleshooting'),
    ]


# ---------------------------------------------------------------------------
# F6 — Time per subcategory
# ---------------------------------------------------------------------------


def test_f6_daily_service_at_10am(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F6: Daily Service assigned at exactly 10:00 AM."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_freeosk(db_session, models, 1003001, start,
                name='1003001-FSK-Daily Service-11AM-Brand')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1003001,
        employee_id='cs1',  # no primary event → CS unconditional (F10)
        scheduled_datetime=datetime.combine(start.date(), time(10, 0)),
    )


def test_f6_troubleshooting_at_noon(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F6: Troubleshooting assigned at exactly 12:00 PM."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_freeosk(db_session, models, 1004001, start,
                name='1004001-FSK-Troubleshooting')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1004001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(start.date(), time(12, 0)),
    )


# ---------------------------------------------------------------------------
# F7 — Primary Lead with primary event
# ---------------------------------------------------------------------------


def test_f7_primary_lead_with_primary_event_assigned(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F7: Primary Lead available + has primary event on target date
    → gets the Freeosk."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    # Give L1 a posted CORE on target so has_primary_event = True.
    core = _mk_core(db_session, models, 1005900, start)
    _mk_posted_schedule(
        db_session, models, core, 'L1',
        datetime.combine(start.date(), time(10, 15)),
    )

    _mk_freeosk(db_session, models, 1005001, start,
                name='1005001-FSK-Daily Service-11AM-Brand')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1005001,
        employee_id='L1',
        scheduled_datetime=datetime.combine(start.date(), time(10, 0)),
    )


# ---------------------------------------------------------------------------
# F9 — Backup Lead with primary event
# ---------------------------------------------------------------------------


def test_f9_backup_lead_with_primary_event(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F8/F9: Primary Lead has no primary event → fall through to
    Backup Lead (who does)."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_lead(db_session, models, 'L2', 'Bob')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1',
                               backup_employee_id='L2')
    # Only L2 has a posted CORE
    core = _mk_core(db_session, models, 1006900, start)
    _mk_posted_schedule(
        db_session, models, core, 'L2',
        datetime.combine(start.date(), time(10, 15)),
    )

    _mk_freeosk(db_session, models, 1006001, start,
                name='1006001-CO-11AM-Brand')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1006001,
        employee_id='L2',
        scheduled_datetime=datetime.combine(start.date(), time(10, 0)),
    )


# ---------------------------------------------------------------------------
# F10 — CS unconditional fallback
# ---------------------------------------------------------------------------


def test_f10_cs_unconditional_fallback(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F10: neither Lead qualifies → CS unconditional (CS has no
    primary event required)."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    # No primary events for anyone today.

    _mk_freeosk(db_session, models, 1007001, start,
                name='1007001-FSK-Daily Service-11AM-Brand')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=1007001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(start.date(), time(10, 0)),
    )


# ---------------------------------------------------------------------------
# F11 — CS on PTO → manual review
# ---------------------------------------------------------------------------


def test_f11_cs_on_pto_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec F11: Leads have no primary event, CS is on PTO → manual review."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_pto(db_session, models, 'cs1', start.date())

    _mk_freeosk(db_session, models, 1008001, start,
                name='1008001-FSK-Daily Service-11AM-Brand')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=1008001,
        reason_contains='Club Supervisor unavailable',
    )
