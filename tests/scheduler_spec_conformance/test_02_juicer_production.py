"""Conformance tests for spec 02-juicer-production.md.

Covers spec branches JP1–JP19 and the cross-category invariants K4, K5, M8
exercised when a Juicer Production bumps a CORE back into category 3.

Time determinism: every test in this directory runs with a frozen "now"
pinned to FROZEN_NOW (Wed Apr 15 2026 12:00) via the autouse fixture in
conftest.py. `future_datetime(N)` returns midnight N days from FROZEN_NOW,
so event start/due dates are stable across runs.
"""
from datetime import datetime, time, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_employee(db, models, emp_id, name, job_title='Juicer Barista',
                 juicer_trained=True):
    Employee = models['Employee']
    emp = Employee(id=emp_id, name=name, job_title=job_title,
                   juicer_trained=juicer_trained, is_active=True)
    db.add(emp)
    db.flush()
    return emp


def _mk_juicer_rotation(db, models, dow, employee_id, backup_employee_id=None):
    RotationAssignment = models['RotationAssignment']
    row = RotationAssignment(
        day_of_week=dow,
        rotation_type='juicer',
        employee_id=employee_id,
        backup_employee_id=backup_employee_id,
    )
    db.add(row)
    db.flush()
    return row


def _mk_juicer_production(db, models, ref_num, start_dt, *, due_days=5,
                          name=None):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d} JUICER-PRODUCTION-SPCLTY',
        event_type='Juicer Production',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=540,
        is_scheduled=False,
    )
    db.add(event)
    db.flush()
    return event


def _mk_juicer_survey(db, models, ref_num, start_dt, *, name=None):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d} JUICE SURVEY-SPCLTY',
        event_type='Juicer Survey',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=5),
        estimated_time=15,
        is_scheduled=False,
    )
    db.add(event)
    db.flush()
    return event


def _mk_core_event(db, models, ref_num, start_dt, *, due_days=7, name=None):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d}-Brand-CORE',
        event_type='Core',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=390,
        is_scheduled=False,
    )
    db.add(event)
    db.flush()
    return event


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


def _mk_posted_core_schedule(db, models, event, emp_id, at_datetime):
    """Post a Schedule row for an existing Core event (simulates prior-run
    assignment that now conflicts with a Juicer Production being placed)."""
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


# ---------------------------------------------------------------------------
# JP1 — Pool sorted by start_datetime ascending
# ---------------------------------------------------------------------------


def test_jp1_juicer_production_sorted_by_start_date(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec JP1: events are handed to the handler in start_datetime order,
    regardless of DB insertion order."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    for dow in range(7):
        _mk_juicer_rotation(db_session, models, dow, 'jb1')

    starts = [future_datetime(8), future_datetime(5), future_datetime(6)]
    for i, start in enumerate(starts):
        _mk_juicer_production(db_session, models, 500100 + i, start)
    db_session.commit()

    observed: list[int] = []
    orig = greedy_scheduler._schedule_single_juicer_production

    def spy(event, run, target_date=None):
        observed.append(event.project_ref_num)
        return orig(event, run, target_date=target_date)

    greedy_scheduler._schedule_single_juicer_production = spy
    greedy_scheduler.run_auto_scheduler(run_type='manual')

    # 500101 has start=future_datetime(5), 500102 has start=future_datetime(6),
    # 500100 has start=future_datetime(8)
    assert observed == [500101, 500102, 500100]


# ---------------------------------------------------------------------------
# JP2 — target_date = event.start_datetime.date()
# ---------------------------------------------------------------------------


def test_jp2_juicer_production_uses_start_date_as_target(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP2: PendingSchedule uses start_datetime.date() @ 9 AM by default."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    start = future_datetime(5)
    _mk_juicer_rotation(db_session, models, start.weekday(), 'jb1')
    _mk_juicer_production(db_session, models, 502001, start)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=502001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(start.date(), time(9, 0)),
    )


# ---------------------------------------------------------------------------
# JP3 / JP4 — Rotation lookup with ScheduleException override
# ---------------------------------------------------------------------------


def test_jp3_jp4_rotation_lookup_with_exception(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec JP3 + JP4: ScheduleException for the target date overrides the
    standing RotationAssignment."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')

    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')

    ScheduleException = models['ScheduleException']
    db_session.add(ScheduleException(
        exception_date=target.date(),
        rotation_type='juicer',
        employee_id='jb2',
        reason='One-off swap',
    ))
    _mk_juicer_production(db_session, models, 503001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    PendingSchedule = models['PendingSchedule']
    ps = (db_session.query(PendingSchedule)
          .filter_by(scheduler_run_id=run.id, event_ref_num=503001)
          .one())
    assert ps.employee_id == 'jb2', \
        'ScheduleException must override RotationAssignment'
    assert ps.schedule_datetime == datetime.combine(target.date(), time(9, 0))


# ---------------------------------------------------------------------------
# JP5 — Primary juicer PTO detected (falls to backup)
# ---------------------------------------------------------------------------


def test_jp5_primary_juicer_pto_falls_to_backup(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP5: primary with approved PTO is 'unavailable'; flow reaches the
    backup juicer check (JP9)."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    _mk_pto(db_session, models, 'jb1', target.date())
    _mk_juicer_production(db_session, models, 504001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=504001,
        employee_id='jb2',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
    )


# ---------------------------------------------------------------------------
# JP7 — Primary available, no CORE → assign @ 9 AM directly
# ---------------------------------------------------------------------------


def test_jp7_primary_juicer_assigned_no_bump(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP7: primary available with no CORE conflict → assign @ 9 AM."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')
    _mk_juicer_production(db_session, models, 505001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=505001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
        is_swap=False,
        bumped_event_ref_num=None,
    )


# ---------------------------------------------------------------------------
# JP6 / JP17 — Primary bumps a posted CORE, bumped CORE re-enters category 3
# ---------------------------------------------------------------------------


def test_jp6_jp17_primary_juicer_bumps_posted_core(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP6 + JP17 + K4 + K5 + M8: primary has a posted CORE on the
    target date. The CORE's Schedule row is deleted, a swap-marker
    PendingSchedule is created for the CORE with employee/datetime cleared,
    and the CORE event is re-enqueued into the core_supervisor pool sorted
    by due_datetime. The Juicer Production still assigns to the primary."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    core = _mk_core_event(db_session, models, 601001, target, due_days=10)
    posted = _mk_posted_core_schedule(
        db_session, models, core, 'jb1',
        datetime.combine(target.date(), time(10, 15)),
    )
    posted_id = posted.id

    _mk_juicer_production(db_session, models, 506001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Juicer Production assigned to primary @ 9 AM, is_swap=False
    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=506001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
        is_swap=False,
    )

    # Posted CORE Schedule row deleted
    Schedule = models['Schedule']
    remaining = (db_session.query(Schedule)
                 .filter_by(event_ref_num=601001)
                 .first())
    assert remaining is None, \
        'Posted CORE Schedule must be deleted when bumped'

    # Swap-marker PendingSchedule created for the CORE. Invariant 1
    # requires exactly one row per event per run, so `.one()` without an
    # is_swap filter must succeed.
    PendingSchedule = models['PendingSchedule']
    core_swap = (db_session.query(PendingSchedule)
                 .filter_by(scheduler_run_id=run.id, event_ref_num=601001)
                 .one())
    assert core_swap.is_swap is True
    assert core_swap.employee_id is None
    assert core_swap.schedule_datetime is None
    assert core_swap.bumped_posted_schedule_id == posted_id

    # Event.is_scheduled cleared so category 3 can re-process it
    Event = models['Event']
    core_row = db_session.query(Event).filter_by(project_ref_num=601001).one()
    assert core_row.is_scheduled is False

    # K5: bumped CORE present in core_supervisor pool, sorted by due_datetime
    pool = greedy_scheduler.category_pools['core_supervisor']
    assert core_row in pool
    due_dates = [e.due_datetime for e in pool]
    assert due_dates == sorted(due_dates), \
        'core_supervisor pool must stay sorted by due_datetime'


def test_jp19_primary_bumps_in_run_pending_core(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP19 + JP18: the Juicer Production handler must detect a CORE
    that was already scheduled earlier in this same run (as a PendingSchedule)
    and bump it by clearing its employee/datetime and re-queueing into
    category 3.

    In practice the category dispatcher runs Juicer Production before CORE,
    so this branch is only exercised when an in-run PendingSchedule CORE
    already exists on the target day. We synthesize that state by pre-inserting
    a PendingSchedule after the run is created but before the Juicer
    Production handler runs."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    # Pre-existing CORE and Juicer Production
    core = _mk_core_event(db_session, models, 602001, target, due_days=10)
    _mk_juicer_production(db_session, models, 519001, target)
    db_session.commit()

    PendingSchedule = models['PendingSchedule']

    # Intercept the handler to plant an in-run PendingSchedule CORE row
    # for jb1 on the target date BEFORE the handler runs. This simulates
    # the "CORE scheduled earlier in this run" condition from JP19.
    orig_process = greedy_scheduler._process_juicer_production

    def hook(pool, run):
        db_session.add(PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=602001,
            employee_id='jb1',
            schedule_datetime=datetime.combine(target.date(), time(10, 15)),
            schedule_time=time(10, 15),
            status='proposed',
            is_swap=False,
        ))
        core.is_scheduled = True
        db_session.flush()
        return orig_process(pool, run)

    greedy_scheduler._process_juicer_production = hook
    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # The pre-planted CORE PendingSchedule must now be "re-opened" —
    # employee_id and schedule_datetime cleared, is_swap=True. Invariant 1
    # (exactly one PendingSchedule per event per run) must still hold: the
    # plan-04 stub skips events that already have a PendingSchedule, so
    # the bumped CORE should still have exactly one row.
    core_ps = (db_session.query(PendingSchedule)
               .filter_by(scheduler_run_id=run.id, event_ref_num=602001)
               .one())
    assert core_ps.employee_id is None
    assert core_ps.schedule_datetime is None
    assert core_ps.is_swap is True


# ---------------------------------------------------------------------------
# JP8 / JP9 — Backup juicer ONLY on primary PTO, NOT on CORE conflict
# ---------------------------------------------------------------------------


def test_jp8_jp9_backup_used_only_on_primary_pto(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP8 + JP9 ("Do NOT" rule): when the primary has a CORE conflict
    we BUMP the CORE and keep the primary. Backup is only used when the
    primary is on PTO."""
    # Scenario A: primary has CORE, no PTO → primary wins (bump CORE)
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    core = _mk_core_event(db_session, models, 603001, target)
    _mk_posted_core_schedule(db_session, models, core, 'jb1',
                             datetime.combine(target.date(), time(10, 15)))
    _mk_juicer_production(db_session, models, 507001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=507001,
        employee_id='jb1',  # primary wins; CORE got bumped
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
    )


# ---------------------------------------------------------------------------
# JP10 — Backup bumps CORE
# ---------------------------------------------------------------------------


def test_jp10_backup_juicer_bumps_core(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP10: primary on PTO, backup has a posted CORE on target date →
    backup gets the Juicer Production and their CORE is bumped."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    _mk_pto(db_session, models, 'jb1', target.date())

    core = _mk_core_event(db_session, models, 604001, target)
    _mk_posted_core_schedule(db_session, models, core, 'jb2',
                             datetime.combine(target.date(), time(10, 15)))

    _mk_juicer_production(db_session, models, 508001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=508001,
        employee_id='jb2',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
    )

    # Invariant 1: exactly one PendingSchedule row for the bumped CORE.
    PendingSchedule = models['PendingSchedule']
    core_swap = (db_session.query(PendingSchedule)
                 .filter_by(scheduler_run_id=run.id, event_ref_num=604001)
                 .one())
    assert core_swap.is_swap is True
    assert core_swap.employee_id is None


# ---------------------------------------------------------------------------
# JP11 — Backup assigned @ 9 AM, no CORE
# ---------------------------------------------------------------------------


def test_jp11_backup_juicer_assigned_no_bump(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP11: primary on PTO, backup available and no CORE → backup
    assigned @ 9 AM."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    _mk_pto(db_session, models, 'jb1', target.date())
    _mk_juicer_production(db_session, models, 509001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=509001,
        employee_id='jb2',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
    )


# ---------------------------------------------------------------------------
# JP12 / JP13 — Both unavailable on D → retry D+1
# ---------------------------------------------------------------------------


def test_jp12_jp13_both_unavailable_retry_next_day(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP12 + JP13: primary and backup both unavailable on day D but
    available on D+1 → retry on D+1 and assign @ 9 AM."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    next_day = target + timedelta(days=1)

    # Same rotation both days (jb1 primary, jb2 backup)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    _mk_juicer_rotation(db_session, models, next_day.weekday(), 'jb1',
                        backup_employee_id='jb2')

    # Both on PTO on day D only
    _mk_pto(db_session, models, 'jb1', target.date())
    _mk_pto(db_session, models, 'jb2', target.date())

    _mk_juicer_production(db_session, models, 510001, target, due_days=5)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=510001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(next_day.date(), time(9, 0)),
    )


# ---------------------------------------------------------------------------
# JP14 — Retry exhausted → manual review
# ---------------------------------------------------------------------------


def test_jp14_past_due_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP14: narrow window with primary+backup both unavailable across
    every day in [start, due) → manual review entry with failure reason
    mentioning 'both unavailable'."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    # Also cover next day in case the retry reaches it
    next_day = target + timedelta(days=1)
    _mk_juicer_rotation(db_session, models, next_day.weekday(), 'jb1',
                        backup_employee_id='jb2')

    # PTO spans the entire window
    _mk_pto(db_session, models, 'jb1', target.date())
    _mk_pto(db_session, models, 'jb1', next_day.date())
    _mk_pto(db_session, models, 'jb2', target.date())
    _mk_pto(db_session, models, 'jb2', next_day.date())

    _mk_juicer_production(db_session, models, 511001, target, due_days=2)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.manual_review(
        run_id=run.id,
        event_ref_num=511001,
        reason_contains='both unavailable',
    )


# ---------------------------------------------------------------------------
# JP15 — Matching Juicer Survey paired @ 5 PM
# ---------------------------------------------------------------------------


def test_jp15_matching_survey_paired_at_5pm(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP15: after a successful Juicer Production assignment, a matching
    Juicer Survey (same 6-digit prefix) must be auto-assigned to the same
    employee on the same day @ 5 PM."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    _mk_juicer_production(
        db_session, models, 512001, target,
        name='512001 BrandX JUICER-PRODUCTION-SPCLTY',
    )
    survey = _mk_juicer_survey(
        db_session, models, 512002, target,
        name='512001 BrandX JUICE SURVEY-SPCLTY',
    )
    db_session.commit()
    survey_ref = survey.project_ref_num

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=512001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
    )

    PendingSchedule = models['PendingSchedule']
    survey_ps = (db_session.query(PendingSchedule)
                 .filter_by(scheduler_run_id=run.id, event_ref_num=survey_ref)
                 .one())
    assert survey_ps.employee_id == 'jb1'
    assert survey_ps.schedule_datetime == \
        datetime.combine(target.date(), time(17, 0))
    assert survey_ps.failure_reason is None


def test_jp16_no_matching_survey_no_action(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JP16: no matching Survey → Production still scheduled, no Survey
    action. (The Survey category handler stub may still create its own
    manual-review entry, but the Production handler itself must not create
    a second PendingSchedule for a Survey.)"""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')
    _mk_juicer_production(db_session, models, 513001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Production scheduled normally
    spec_assert.exact_assignment(
        run_id=run.id,
        event_ref_num=513001,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(target.date(), time(9, 0)),
    )
