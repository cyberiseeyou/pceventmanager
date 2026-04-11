"""Conformance tests for spec 03-juicer-survey.md.

Covers spec branches JS1–JS17 plus cross-category invariant K4 (secondary
events never bump primary events). Paired surveys are handled by plan 02;
plan 03 owns the standalone decision tree with CS unconditional fallback.
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
    )
    db.add(event)
    db.flush()
    return event


def _mk_juicer_survey(db, models, ref_num, start_dt, *, due_days=2, name=None):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d} JUICE SURVEY-SPCLTY',
        event_type='Juicer Survey',
        condition='Unstaffed',
        start_datetime=start_dt,
        due_datetime=start_dt + timedelta(days=due_days),
        estimated_time=15,
    )
    db.add(event)
    db.flush()
    return event


def _mk_core_event(db, models, ref_num, start_dt, *, due_days=7, name=None,
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


def _mk_posted_schedule(db, models, event, emp_id, at_datetime):
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
# JS1 / JS2 — Paired survey skipped
# ---------------------------------------------------------------------------


def test_js1_js2_paired_survey_skipped(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec JS1 + JS2: matching Production pair auto-scheduled the Survey in
    plan 02 (JP15). Plan 03 must NOT re-create a second PendingSchedule."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    _mk_juicer_production(
        db_session, models, 801001, target,
        name='801001 BrandX JUICER-PRODUCTION-SPCLTY',
    )
    survey = _mk_juicer_survey(
        db_session, models, 801002, target,
        name='801001 BrandX JUICE SURVEY-SPCLTY',
    )
    db_session.commit()
    survey_ref = survey.project_ref_num

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    PendingSchedule = models['PendingSchedule']
    count = (db_session.query(PendingSchedule)
             .filter_by(scheduler_run_id=run.id, event_ref_num=survey_ref)
             .count())
    assert count == 1, f"Expected 1 PendingSchedule for paired survey, got {count}"
    ps = (db_session.query(PendingSchedule)
          .filter_by(scheduler_run_id=run.id, event_ref_num=survey_ref)
          .one())
    assert ps.employee_id == 'jb1'
    assert ps.schedule_datetime == datetime.combine(target.date(), time(17, 0))


# ---------------------------------------------------------------------------
# JS3 — Survey whose matching Production failed → standalone
# ---------------------------------------------------------------------------


def test_js3_survey_of_failed_production_treated_standalone(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS3: if the matching Production went to manual review, the
    Survey should still run through the standalone tree — the Survey's
    ref_num has no PendingSchedule yet, so the standalone path naturally
    applies."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'cs1', 'Grace', job_title='Club Supervisor',
                 juicer_trained=False)
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    # Primary has PTO and no backup → Production goes to manual review.
    _mk_pto(db_session, models, 'jb1', target.date())
    # Narrow window forces manual review immediately.
    _mk_juicer_production(
        db_session, models, 802001, target, due_days=1,
        name='802001 BrandX JUICER-PRODUCTION-SPCLTY',
    )
    _mk_juicer_survey(
        db_session, models, 802002, target,
        name='802001 BrandX JUICE SURVEY-SPCLTY',
    )
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    # Production is manual review
    spec_assert.manual_review(
        run_id=run.id, event_ref_num=802001,
        reason_contains='both unavailable',
    )

    # Survey falls to CS unconditional fallback
    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=802002,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS4 — Standalone survey, no matching Production
# ---------------------------------------------------------------------------


def test_js4_standalone_survey_no_matching_production(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS4: Survey with no matching Production at all → runs through
    standalone tree from the top."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    # Give jb1 a posted Core so has_primary_event is True.
    core = _mk_core_event(db_session, models, 803001, target)
    _mk_posted_schedule(db_session, models, core, 'jb1',
                        datetime.combine(target.date(), time(10, 15)))

    _mk_juicer_survey(db_session, models, 803002, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=803002,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS8 — Primary available + has primary event → assign
# ---------------------------------------------------------------------------


def test_js8_primary_with_primary_event_assigned(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS8: standalone Survey, primary juicer available AND has a
    primary event (Core or Juicer Production) on the target date → assign
    Survey to primary @ 5 PM."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')

    core = _mk_core_event(db_session, models, 804001, target)
    _mk_posted_schedule(db_session, models, core, 'jb1',
                        datetime.combine(target.date(), time(10, 15)))

    _mk_juicer_survey(db_session, models, 804002, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=804002,
        employee_id='jb1',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS9 — Primary available WITHOUT primary event → fall through to backup
# ---------------------------------------------------------------------------


def test_js9_primary_without_primary_event_falls_through(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS9: primary available but no primary event on target date
    → fall through to backup (who has a primary event)."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')

    # Only jb2 has a posted Core on target
    core = _mk_core_event(db_session, models, 805001, target)
    _mk_posted_schedule(db_session, models, core, 'jb2',
                        datetime.combine(target.date(), time(10, 15)))

    _mk_juicer_survey(db_session, models, 805002, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=805002,
        employee_id='jb2',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS10 — Primary on PTO → fall through to backup
# ---------------------------------------------------------------------------


def test_js10_primary_pto_falls_through_to_backup(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS10: primary on PTO → try backup (who is available AND has
    primary event)."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')
    _mk_pto(db_session, models, 'jb1', target.date())

    core = _mk_core_event(db_session, models, 806001, target)
    _mk_posted_schedule(db_session, models, core, 'jb2',
                        datetime.combine(target.date(), time(10, 15)))

    _mk_juicer_survey(db_session, models, 806002, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=806002,
        employee_id='jb2',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS13/JS14 — Backup without primary event → CS unconditional fallback
# ---------------------------------------------------------------------------


def test_js13_js14_backup_without_primary_event_falls_to_cs(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS13 + JS14 + JS15: neither juicer qualifies (neither has a
    primary event on target date) → Club Supervisor unconditional fallback."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'jb2', 'Leo')
    _mk_employee(db_session, models, 'cs1', 'Grace',
                 job_title='Club Supervisor', juicer_trained=False)
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1',
                        backup_employee_id='jb2')

    # No primary events for either juicer today.
    _mk_juicer_survey(db_session, models, 807001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=807001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS15 — CS unconditional (CS has no primary event)
# ---------------------------------------------------------------------------


def test_js15_cs_unconditional_fallback(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS15: CS fallback is unconditional w.r.t. "has primary event".
    The CS can have no primary event that day and still get the Survey."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'cs1', 'Grace',
                 job_title='Club Supervisor', juicer_trained=False)
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')
    _mk_pto(db_session, models, 'jb1', target.date())

    _mk_juicer_survey(db_session, models, 808001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.exact_assignment(
        run_id=run.id, event_ref_num=808001,
        employee_id='cs1',
        scheduled_datetime=datetime.combine(target.date(), time(17, 0)),
    )


# ---------------------------------------------------------------------------
# JS16 — CS on PTO → manual review
# ---------------------------------------------------------------------------


def test_js16_cs_on_pto_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS16: CS is on PTO → manual review."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'cs1', 'Grace',
                 job_title='Club Supervisor', juicer_trained=False)
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')
    _mk_pto(db_session, models, 'jb1', target.date())
    _mk_pto(db_session, models, 'cs1', target.date())

    _mk_juicer_survey(db_session, models, 809001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.manual_review(
        run_id=run.id, event_ref_num=809001,
        reason_contains='Club Supervisor',
    )


# ---------------------------------------------------------------------------
# JS17 — No CS employee → manual review
# ---------------------------------------------------------------------------


def test_js17_no_cs_employee_manual_review(
    greedy_scheduler, models, db_session, future_datetime, spec_assert
):
    """Spec JS17: no Club Supervisor employee exists → manual review."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')
    _mk_pto(db_session, models, 'jb1', target.date())

    _mk_juicer_survey(db_session, models, 810001, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    spec_assert.manual_review(
        run_id=run.id, event_ref_num=810001,
        reason_contains='Club Supervisor',
    )


# ---------------------------------------------------------------------------
# K4 — Secondary events do NOT bump primary events
# ---------------------------------------------------------------------------


def test_k4_juicer_survey_does_not_bump_core(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec K4: Juicer Survey (a secondary event) must never bump a posted
    CORE. If no juicer qualifies, fall to CS — do NOT touch the CORE."""
    _mk_employee(db_session, models, 'jb1', 'Frank')
    _mk_employee(db_session, models, 'cs1', 'Grace',
                 job_title='Club Supervisor', juicer_trained=False)
    target = future_datetime(5)
    _mk_juicer_rotation(db_session, models, target.weekday(), 'jb1')

    # CS has a posted CORE
    core = _mk_core_event(db_session, models, 811001, target)
    _mk_posted_schedule(db_session, models, core, 'cs1',
                        datetime.combine(target.date(), time(10, 15)))

    # Primary on PTO so survey falls all the way to CS
    _mk_pto(db_session, models, 'jb1', target.date())
    _mk_juicer_survey(db_session, models, 811002, target)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    Schedule = models['Schedule']
    PendingSchedule = models['PendingSchedule']

    # Original CORE Schedule row must still be present — not bumped.
    remaining = (db_session.query(Schedule)
                 .filter_by(event_ref_num=811001)
                 .first())
    assert remaining is not None, \
        'Juicer Survey must not bump the posted CORE (K4 violation)'

    # No swap PendingSchedule for the CORE
    swap_count = (db_session.query(PendingSchedule)
                  .filter_by(scheduler_run_id=run.id,
                             event_ref_num=811001, is_swap=True)
                  .count())
    assert swap_count == 0, \
        'No bump PendingSchedule should exist for the CORE (K4 violation)'
