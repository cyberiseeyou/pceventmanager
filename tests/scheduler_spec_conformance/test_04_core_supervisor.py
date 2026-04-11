"""Conformance tests for spec 04-core-supervisor.md (integration level).

Unit tests for the slot allocator live in
`test_04_core_slot_allocator.py` — those cover branches C5, C9, C10, C11
at the slot-packing level. This file covers end-to-end scheduling
through the greedy engine: date window, employee priority, bumping,
and Supervisor pairing (branches C1–C16 + S1–S8).
"""
from datetime import datetime, time, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_employee(db, models, emp_id, name, *, job_title='Event Specialist',
                 juicer_trained=False):
    Employee = models['Employee']
    emp = Employee(id=emp_id, name=name, job_title=job_title,
                   juicer_trained=juicer_trained, is_active=True)
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
    row = RotationAssignment(
        day_of_week=dow,
        rotation_type='primary_lead',
        employee_id=employee_id,
        backup_employee_id=backup_employee_id,
    )
    db.add(row)
    db.flush()
    return row


def _mk_core(db, models, ref_num, start_dt, *, due_days=7, name=None,
             is_scheduled=False):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d}-Brand-CORE',
        event_type='Core',
        condition='Unstaffed' if not is_scheduled else 'Scheduled',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=390,
        is_scheduled=is_scheduled,
    )
    db.add(event)
    db.flush()
    return event


def _mk_supervisor(db, models, ref_num, start_dt, *, due_days=7, name=None):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d}-Brand-SUPERVISOR',
        event_type='Supervisor',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=5,
    )
    db.add(event)
    db.flush()
    return event


def _mk_posted_core_schedule(db, models, event, emp_id, at_datetime):
    Schedule = models['Schedule']
    row = Schedule(
        event_ref_num=event.project_ref_num,
        employee_id=emp_id,
        schedule_datetime=at_datetime,
    )
    db.add(row)
    event.is_scheduled = True
    db.flush()
    return row


def _mk_pto(db, models, emp_id, day):
    EmployeeTimeOff = models['EmployeeTimeOff']
    pto = EmployeeTimeOff(
        employee_id=emp_id,
        start_date=day,
        end_date=day,
        status='approved',
        reason='Test PTO',
    )
    db.add(pto)
    db.flush()
    return pto


# ---------------------------------------------------------------------------
# C1 — Due date sort order
# ---------------------------------------------------------------------------


def test_c1_core_pool_sorted_by_due_date(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec C1: CORE events processed in due-date order, earliest first."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    start = future_datetime(5)
    # Add in reverse order to verify sorting
    _mk_core(db_session, models, 901001, start, due_days=14)
    _mk_core(db_session, models, 901002, start, due_days=7)
    _mk_core(db_session, models, 901003, start, due_days=10)
    db_session.commit()

    observed: list[int] = []
    orig = greedy_scheduler._schedule_single_core

    def spy(event, run):
        observed.append(event.project_ref_num)
        return orig(event, run)

    greedy_scheduler._schedule_single_core = spy
    greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Earliest due first: 901002 (due_days=7), 901003 (10), 901001 (14).
    assert observed == [901002, 901003, 901001]


# ---------------------------------------------------------------------------
# C5 — Primary Lead @ 10:15
# ---------------------------------------------------------------------------


def test_c5_primary_lead_gets_core_at_1015(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec C5: Primary Lead gets exactly 10:15 AM on their first CORE
    of the day."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_lead(db_session, models, 'L2', 'Bob')
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_core(db_session, models, 902001, start)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=902001,
        employee_id='L1',
        scheduled_datetime=datetime.combine(start.date(), time(10, 15)),
    )


# ---------------------------------------------------------------------------
# C6 — Other Leads when Primary Lead unavailable
# ---------------------------------------------------------------------------


def test_c6_other_lead_when_primary_unavailable(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec C6: Primary Lead on PTO → next Lead in id order gets the CORE."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_lead(db_session, models, 'L2', 'Bob')
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_pto(db_session, models, 'L1', start.date())
    _mk_core(db_session, models, 903001, start)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    ps = (db_session.query(PendingSchedule)
          .filter_by(scheduler_run_id=run.id, event_ref_num=903001)
          .one())
    assert ps.employee_id == 'L2'
    # Other Lead uses allocator (not primary_lead=True) — 10:15 block 1
    assert ps.schedule_datetime.time() == time(10, 15)


# ---------------------------------------------------------------------------
# C7/C8 — Fewest primaries this week tiebreaker
# ---------------------------------------------------------------------------


def test_c7_c8_fewest_primaries_this_week(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec C7/C8: when no Lead qualifies, pick the employee with the
    fewest primary events this week (Sun–Sat). Tie by employee_id."""
    _mk_employee(db_session, models, 'S1', 'Sam')
    _mk_employee(db_session, models, 'S2', 'Tina')
    _mk_employee(db_session, models, 'S3', 'Uma')
    start = future_datetime(5)  # Mon Apr 20

    # Pre-populate posted CORE events to tilt primaries-this-week counts.
    # Week = Sun Apr 19 – Sat Apr 25.
    week_sunday = start - timedelta(days=start.weekday() + 1)  # Sun
    # S1: 2 posted CORE this week
    c_a = _mk_core(db_session, models, 904100,
                   week_sunday + timedelta(days=1), due_days=3)
    _mk_posted_core_schedule(
        db_session, models, c_a, 'S1',
        datetime.combine(week_sunday.date() + timedelta(days=1), time(10, 15)),
    )
    c_b = _mk_core(db_session, models, 904101,
                   week_sunday + timedelta(days=2), due_days=3)
    _mk_posted_core_schedule(
        db_session, models, c_b, 'S1',
        datetime.combine(week_sunday.date() + timedelta(days=2), time(10, 15)),
    )
    # S2: 1 posted CORE this week
    c_c = _mk_core(db_session, models, 904102,
                   week_sunday + timedelta(days=1), due_days=3)
    _mk_posted_core_schedule(
        db_session, models, c_c, 'S2',
        datetime.combine(week_sunday.date() + timedelta(days=1), time(10, 45)),
    )
    # S3: 0 posted CORE this week → wins

    # The event to schedule
    _mk_core(db_session, models, 904001, start)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    ps = (db_session.query(PendingSchedule)
          .filter_by(scheduler_run_id=run.id, event_ref_num=904001)
          .one())
    assert ps.employee_id == 'S3'


# ---------------------------------------------------------------------------
# C9 integration — Fill 2 per slot across multiple CORE events
# ---------------------------------------------------------------------------


def test_c9_integration_four_cores_fill_two_per_slot(
    greedy_scheduler, models, db_session, future_datetime
):
    """Integration test for C9: 4 CORE events on the same day with 4
    different Leads → first two @ 10:15, next two @ 10:45."""
    for i in range(4):
        _mk_lead(db_session, models, f'L{i+1}', f'Lead{i+1}')
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    for i, ref in enumerate([905001, 905002, 905003, 905004]):
        _mk_core(db_session, models, ref, start, due_days=5 + i)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    rows = (db_session.query(PendingSchedule)
            .filter_by(scheduler_run_id=run.id)
            .filter(PendingSchedule.event_ref_num.in_(
                [905001, 905002, 905003, 905004]))
            .order_by(PendingSchedule.schedule_datetime)
            .all())

    times = [r.schedule_datetime.time() for r in rows]
    # Expected: 2 at 10:15 (L1 Primary first, then 1 Other Lead),
    # 2 at 10:45 (other Leads). Note that Primary Lead path always
    # puts the Primary at 10:15 block 1, while the non-primary path
    # fills 10:15 block 2 next, then advances to 10:45 block 3, 4.
    assert times.count(time(10, 15)) == 2
    assert times.count(time(10, 45)) == 2


# ---------------------------------------------------------------------------
# C12/C13 — Bump CORE with latest due date
# ---------------------------------------------------------------------------


def test_c12_c13_bump_core_with_latest_due_date(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec C12 + C13: no employee available on target day, but there is
    a CORE on that day with a later due date → bump that CORE, take its
    slot. Tiebreak by LATEST due date, then largest project_ref_num."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')

    # Pre-populated CORE posted to L1 on `start` with a much later due
    # date. That's the only employee available (no other leads, no specs).
    old_core = _mk_core(db_session, models, 906900, start, due_days=20)
    _mk_posted_core_schedule(
        db_session, models, old_core, 'L1',
        datetime.combine(start.date(), time(10, 15)),
    )
    # Also a second old CORE with a less-late but still-later due date
    old_core2 = _mk_core(db_session, models, 906901, start, due_days=12)
    _mk_posted_core_schedule(
        db_session, models, old_core2, 'L1',
        datetime.combine(start.date(), time(10, 45)),
    )

    # New CORE due sooner than both
    _mk_core(db_session, models, 906001, start, due_days=6)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']

    # New CORE placed
    new_ps = (db_session.query(PendingSchedule)
              .filter_by(scheduler_run_id=run.id, event_ref_num=906001)
              .one())
    assert new_ps.employee_id == 'L1'
    assert new_ps.schedule_datetime.date() == start.date()

    # The CORE with the LATEST due date (906900, due_days=20) is bumped,
    # not 906901 (due_days=12). Its Schedule row deleted and a
    # swap-marker PendingSchedule created.
    Schedule = models['Schedule']
    remaining_906900 = (db_session.query(Schedule)
                        .filter_by(event_ref_num=906900).first())
    assert remaining_906900 is None, 'CORE 906900 Schedule should be deleted'
    remaining_906901 = (db_session.query(Schedule)
                        .filter_by(event_ref_num=906901).first())
    assert remaining_906901 is not None, \
        'CORE 906901 should NOT be bumped (not the latest due)'


# ---------------------------------------------------------------------------
# C15 — Manual review when window exhausted
# ---------------------------------------------------------------------------


def test_c15_manual_review_when_window_exhausted(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec C15: no employee available on any day in the window, no
    bumpable CORE → manual review."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    # Narrow window: due = start + 1 day. L1 on PTO for that single day.
    _mk_pto(db_session, models, 'L1', start.date())
    _mk_core(db_session, models, 907001, start, due_days=1)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=907001,
        reason_contains='no employee available',
    )


# ---------------------------------------------------------------------------
# C16 — Bumped CORE from plan 02 re-enters and is scheduled
# ---------------------------------------------------------------------------


def test_c16_bumped_core_from_plan_02_rescheduled(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec C16 + JP17: a CORE bumped by Juicer Production in plan 02
    must be re-scheduled here in plan 04, updating the swap-marker row
    in place. Invariant 1 holds: exactly one PendingSchedule per event."""
    _mk_employee(db_session, models, 'jb1', 'Frank',
                 job_title='Juicer Barista', juicer_trained=True)
    _mk_lead(db_session, models, 'L1', 'Alice')
    start = future_datetime(5)

    RotationAssignment = models['RotationAssignment']
    db_session.add(RotationAssignment(
        day_of_week=start.weekday(),
        rotation_type='juicer',
        employee_id='jb1',
    ))

    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')

    # Juicer Production on `start` — will bump jb1's posted CORE.
    core = _mk_core(db_session, models, 908001, start, due_days=10)
    _mk_posted_core_schedule(
        db_session, models, core, 'jb1',
        datetime.combine(start.date(), time(10, 15)),
    )
    _mk_juicer_prod = models['Event']
    db_session.add(_mk_juicer_prod(
        project_ref_num=908900,
        project_name='908900 JUICER-PRODUCTION-SPCLTY',
        event_type='Juicer Production',
        condition='Unstaffed',
        start_datetime=start,
        due_datetime=start + timedelta(days=3),
        estimated_time=540,
    ))
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    PendingSchedule = models['PendingSchedule']
    # Invariant 1: exactly one row for the bumped CORE
    rows = (db_session.query(PendingSchedule)
            .filter_by(scheduler_run_id=run.id, event_ref_num=908001)
            .all())
    assert len(rows) == 1, \
        f"CORE 908001 should have exactly 1 PendingSchedule, got {len(rows)}"
    ps = rows[0]

    # CORE was re-scheduled (employee and datetime populated) and
    # is_swap is preserved as True (bump metadata retained).
    assert ps.employee_id is not None
    assert ps.schedule_datetime is not None
    assert ps.is_swap is True
    # Assigned to Primary Lead on any day within its window (L1 is
    # available every day and Primary Lead on start.weekday()).


# ---------------------------------------------------------------------------
# S1/S2/S3 — Supervisor paired and scheduled @ 12 PM
# ---------------------------------------------------------------------------


def test_s1_s3_paired_supervisor_scheduled_at_noon(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec S1/S3: every successfully-scheduled CORE with a paired
    Supervisor generates a second PendingSchedule for the Supervisor
    @ 12 PM on the CORE's assigned date."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')

    _mk_core(db_session, models, 909001, start,
             name='909001-Brand-CORE')
    _mk_supervisor(db_session, models, 909002, start,
                   name='909001-Brand-SUPERVISOR')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    core_ps = (db_session.query(PendingSchedule)
               .filter_by(scheduler_run_id=run.id, event_ref_num=909001)
               .one())
    sup_ps = (db_session.query(PendingSchedule)
              .filter_by(scheduler_run_id=run.id, event_ref_num=909002)
              .one())
    assert sup_ps.schedule_datetime == \
        datetime.combine(core_ps.schedule_datetime.date(), time(12, 0))
    # S4: CS is first choice for Supervisor when available
    assert sup_ps.employee_id == 'cs1'


# ---------------------------------------------------------------------------
# S4 — Club Supervisor first, no has_primary_event required
# ---------------------------------------------------------------------------


def test_s4_cs_first_no_primary_required(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec S4: CS gets the Supervisor even when CS has no CORE that day."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')

    # The pair: L1 gets the CORE; CS has no CORE but is available and
    # should still be assigned the Supervisor under S4.
    _mk_core(db_session, models, 910001, start, name='910001-Brand-CORE')
    _mk_supervisor(db_session, models, 910002, start,
                   name='910001-Brand-SUPERVISOR')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    sup_ps = (db_session.query(PendingSchedule)
              .filter_by(scheduler_run_id=run.id, event_ref_num=910002)
              .one())
    assert sup_ps.employee_id == 'cs1'


# ---------------------------------------------------------------------------
# S5 — Primary Lead gets Supervisor when CS unavailable
# ---------------------------------------------------------------------------


def test_s5_primary_lead_with_core_assigned(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec S5: CS on PTO, Primary Lead has the CORE on target_date →
    Primary Lead gets the Supervisor @ 12 PM."""
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_pto(db_session, models, 'cs1', start.date())

    _mk_core(db_session, models, 911001, start, name='911001-Brand-CORE')
    _mk_supervisor(db_session, models, 911002, start,
                   name='911001-Brand-SUPERVISOR')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')
    PendingSchedule = models['PendingSchedule']
    sup_ps = (db_session.query(PendingSchedule)
              .filter_by(scheduler_run_id=run.id, event_ref_num=911002)
              .one())
    assert sup_ps.employee_id == 'L1'
    assert sup_ps.schedule_datetime.time() == time(12, 0)


# ---------------------------------------------------------------------------
# S8 — Manual review when CS on PTO and no Lead has CORE
# ---------------------------------------------------------------------------


def test_s8_supervisor_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec S8: CS on PTO, Primary Lead has no CORE that day → manual review."""
    # Use a specialist (not a Lead) so the CORE doesn't land on a Lead.
    # That way no Lead has a CORE on target_date, and the Supervisor
    # has nowhere to go except manual review.
    _mk_employee(db_session, models, 'S1', 'Sam')
    _mk_lead(db_session, models, 'L1', 'Alice')
    _mk_cs(db_session, models)
    start = future_datetime(5)
    _mk_primary_lead_rotation(db_session, models, start.weekday(), 'L1')
    _mk_pto(db_session, models, 'L1', start.date())  # Lead on PTO → specialist gets CORE
    _mk_pto(db_session, models, 'cs1', start.date())

    # Also prevent L1 from getting the CORE via primary-lead branch
    # (PTO handles that). Specialist S1 becomes the only candidate.
    _mk_core(db_session, models, 912001, start, name='912001-Brand-CORE')
    _mk_supervisor(db_session, models, 912002, start,
                   name='912001-Brand-SUPERVISOR')
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # CORE placed (on specialist)
    PendingSchedule = models['PendingSchedule']
    core_ps = (db_session.query(PendingSchedule)
               .filter_by(scheduler_run_id=run.id, event_ref_num=912001)
               .one())
    assert core_ps.employee_id == 'S1'

    # Supervisor → manual review (CS on PTO, no Lead has CORE)
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=912002,
        reason_contains='no Club Supervisor',
    )
