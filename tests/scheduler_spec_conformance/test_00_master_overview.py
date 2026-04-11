"""Conformance tests for spec 00-master-overview.md."""


def test_m0_default_scheduler_is_greedy(app):
    """Spec: the production scheduler is the greedy engine.

    After plan 08 of the 2026-04-10 scheduler rewrite, CP-SAT is retired
    from the production code path entirely — the `CPSAT_ENABLED` config
    flag was removed. Greedy is the only scheduler, so the assertion is
    now "no CPSAT_ENABLED key exists in config".
    """
    assert 'CPSAT_ENABLED' not in app.config, (
        "CPSAT_ENABLED must be absent after plan 08 (retire CP-SAT). "
        "Greedy is the production scheduler."
    )


# --- Phase 1 input filter (M1–M3) --------------------------------------------
# These tests exercise _get_unscheduled_events directly rather than running
# the full scheduler. That keeps them independent of category handlers (which
# are refactored by plans 02–07) while still asserting the Phase 1 filter
# matches the spec.


def test_m1_phase1_skips_already_scheduled(greedy_scheduler, models,
                                            db_session, future_datetime):
    """Spec branch M1: events with is_scheduled=True are skipped entirely."""
    Event = models['Event']

    db_session.add(Event(
        project_ref_num=100001,
        project_name='100001-CORE-AlreadyScheduled',
        event_type='Core', condition='Scheduled', is_scheduled=True,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    ))
    db_session.add(Event(
        project_ref_num=100002,
        project_name='100002-CORE-Fresh',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    ))
    db_session.commit()

    events = greedy_scheduler._get_unscheduled_events()
    refs = {e.project_ref_num for e in events}

    assert 100001 not in refs, "is_scheduled=True event must be skipped"
    assert 100002 in refs, "Fresh unstaffed event must be included"


def test_m2_phase1_skips_canceled_and_expired(greedy_scheduler, models,
                                               db_session, future_datetime):
    """Spec branch M2: events with condition in (Canceled, Expired) are skipped."""
    Event = models['Event']

    db_session.add(Event(
        project_ref_num=100003,
        project_name='100003-CORE-Canceled',
        event_type='Core', condition='Canceled', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    ))
    db_session.add(Event(
        project_ref_num=100004,
        project_name='100004-CORE-Expired',
        event_type='Core', condition='Expired', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    ))
    db_session.commit()

    events = greedy_scheduler._get_unscheduled_events()
    refs = {e.project_ref_num for e in events}

    assert 100003 not in refs, "Canceled event must be skipped"
    assert 100004 not in refs, "Expired event must be skipped"


def test_m3_phase1_skips_past_due_window(greedy_scheduler, models,
                                          db_session, future_datetime):
    """Spec branch M3: events whose due_datetime falls within the
    Normal-mode buffer window (today + 3 days) are skipped entirely.

    The 3-day buffer means a Normal-mode run refuses to even consider events
    due tomorrow, 2 days out, or 3 days out — only events due >3 days in the
    future are eligible. Emergency mode flips the buffer to 0.
    """
    Event = models['Event']

    db_session.add(Event(
        project_ref_num=100005,
        project_name='100005-CORE-DueTomorrow',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(0),
        due_datetime=future_datetime(1),
        estimated_time=60,
    ))
    db_session.add(Event(
        project_ref_num=100006,
        project_name='100006-CORE-DueInThree',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(0),
        due_datetime=future_datetime(3),
        estimated_time=60,
    ))
    db_session.add(Event(
        project_ref_num=100007,
        project_name='100007-CORE-DueInTen',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    ))
    db_session.commit()

    events = greedy_scheduler._get_unscheduled_events()
    refs = {e.project_ref_num for e in events}

    assert 100005 not in refs, "Event due tomorrow must be inside Normal buffer"
    assert 100006 not in refs, "Event due in 3 days must be inside Normal buffer"
    assert 100007 in refs, "Event due well past the buffer must be included"


# --- Phase 2 CORE/Supervisor pairing (M4–M6) ---------------------------------


def test_m4_phase2_pairs_core_supervisor_by_6digit_and_name(
    db_session, models, future_datetime
):
    """Spec branch M4: CORE pairs with Supervisor that shares the same 6-digit
    number AND the same name prefix up to the type keyword."""
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    core = Event(
        project_ref_num=200001,
        project_name='260115-MAP-Brand-Product CORE',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    )
    sup = Event(
        project_ref_num=200002,
        project_name='260115-MAP-Brand-Product Supervisor',
        event_type='Supervisor', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=5,
    )
    db_session.add_all([core, sup])
    db_session.commit()

    pairs = pair_cores_and_supervisors([core, sup])
    assert pairs[core.id] is sup, (
        "CORE 260115 must pair with Supervisor 260115 by 6-digit + name prefix")


def test_m4_phase2_does_not_pair_on_mismatched_name_prefix(
    db_session, models, future_datetime
):
    """Spec branch M4 (negative): same 6-digit but different name prefix
    means NO pairing. Both events are left unpaired."""
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    core = Event(
        project_ref_num=200010,
        project_name='260200-MAP-Brand-Foo CORE',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    )
    sup = Event(
        project_ref_num=200011,
        project_name='260200-MAP-Brand-Bar Supervisor',
        event_type='Supervisor', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=5,
    )
    db_session.add_all([core, sup])
    db_session.commit()

    pairs = pair_cores_and_supervisors([core, sup])
    assert core.id not in pairs, (
        "CORE and Supervisor with mismatched name prefix must not pair")


def test_m5_phase2_unpaired_core_processes_alone(
    db_session, models, future_datetime
):
    """Spec branch M5: CORE with no matching Supervisor is returned without
    a pair. The caller is expected to process it alone."""
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    core = Event(
        project_ref_num=200003,
        project_name='260116-MAP-Lonely CORE',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    )
    db_session.add(core)
    db_session.commit()

    pairs = pair_cores_and_supervisors([core])
    assert core.id not in pairs, "Unpaired CORE must not appear in pairs map"
    assert pairs == {}, "Unpaired CORE must produce an empty pairs map"


def test_m6_phase2_unpaired_supervisor_is_logged_and_skipped(
    db_session, models, caplog, future_datetime
):
    """Spec branch M6: Supervisor with no matching CORE is logged as a
    warning and excluded from the result."""
    import logging
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    sup = Event(
        project_ref_num=200004,
        project_name='260117-MAP-Orphan Supervisor',
        event_type='Supervisor', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=5,
    )
    db_session.add(sup)
    db_session.commit()

    with caplog.at_level(logging.WARNING, logger='app.services.scheduler_pairing'):
        pairs = pair_cores_and_supervisors([sup])

    assert pairs == {}, "Orphan Supervisor must not produce a pairing entry"
    assert any(
        'Unpaired Supervisor' in rec.message and '260117' in rec.message
        for rec in caplog.records
    ), "Orphan Supervisor must be logged as a WARNING with its ref num"


def test_m4_phase2_pairs_by_parenthesized_unique_id_across_version_suffixes(
    db_session, models, future_datetime
):
    """Regression test for 2026-04-11 Supervisor pairing bug: real-world
    production event names include a trailing version suffix (V2 / V2.1)
    that differs between a CORE and its matching Supervisor, even though
    both names contain the same parenthesized unique event ID.

    Before the fix, the pairing regex used "6-digit + lazy name prefix
    ending in CORE/Supervisor" which captured the version suffix into
    the prefix, so keys diverged and pairs vanished. The fix uses the
    parenthesized unique ID as the primary pairing key.
    """
    from app.services.scheduler_pairing import pair_cores_and_supervisors
    Event = models['Event']

    core = Event(
        project_ref_num=900100,
        project_name='622055-MAP-Gatorade Low Sugar Variety Pack (260209543468)  - V2.1-CORE',
        event_type='Core', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=60,
    )
    sup = Event(
        project_ref_num=900101,
        project_name='622055-MAP-Gatorade Low Sugar Variety Pack (260209543468)  - V2-Supervisor',
        event_type='Supervisor', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(10),
        estimated_time=5,
    )
    db_session.add_all([core, sup])
    db_session.commit()

    pairs = pair_cores_and_supervisors([core, sup])
    assert pairs.get(core.id) is sup, (
        "CORE and Supervisor that share the same parenthesized unique ID "
        "must pair even when their version suffixes differ (V2.1 vs V2)"
    )


def test_orphan_supervisor_matches_posted_core_schedule(
    greedy_scheduler, models, db_session, future_datetime
):
    """Supervisor events whose matching CORE is already posted (from a
    prior approved run) must still be scheduled on the same day as the
    posted CORE — the scheduler looks up the CORE's posted Schedule row
    via the pairing key and assigns the Supervisor to that date.
    """
    from datetime import datetime, time
    Event = models['Event']
    Schedule = models['Schedule']
    Employee = models['Employee']
    RotationAssignment = models['RotationAssignment']

    # Set up a Primary Lead so the CS fallback path has an alternative
    # and the test doesn't depend on CS availability math.
    lead = Employee(id='L1', name='Lead', email='l1@ex.com',
                     is_active=True, job_title='Lead Event Specialist')
    cs = Employee(id='CS1', name='Mat', email='cs@ex.com',
                   is_active=True, job_title='Club Supervisor')
    db_session.add_all([lead, cs])
    db_session.flush()

    # CORE is already posted to lead L1 on day+5, at 10:15. The Event
    # row is marked is_scheduled=True, so it WILL NOT appear in this
    # run's input pool — it's a "posted" event from a previous run.
    core_day = future_datetime(5).date()
    core_event = Event(
        project_ref_num=900200,
        project_name='623888-MAP-Cookies (260301545555)  - V2.1-CORE',
        event_type='Core', condition='Scheduled', is_scheduled=True,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(12),
        estimated_time=60,
    )
    db_session.add(core_event)
    db_session.flush()
    posted_core = Schedule(
        event_ref_num=900200,
        employee_id='L1',
        schedule_datetime=datetime.combine(core_day, time(10, 15)),
    )
    db_session.add(posted_core)

    # Supervisor is unscheduled, CORE is not in this run's event pool.
    # The scheduler must look up the posted CORE by pairing key and
    # place the Supervisor on the same day @ 12 PM (S4 via CS fallback
    # is fine — no has-primary-event check on CS).
    orphan_sup = Event(
        project_ref_num=900201,
        project_name='623888-MAP-Cookies (260301545555)  - V2-Supervisor',
        event_type='Supervisor', condition='Unstaffed', is_scheduled=False,
        start_datetime=future_datetime(5),
        due_datetime=future_datetime(12),
        estimated_time=5,
    )
    db_session.add(orphan_sup)
    db_session.commit()

    run = greedy_scheduler.run_auto_scheduler(run_type='manual')

    PendingSchedule = models['PendingSchedule']
    ps = (
        db_session.query(PendingSchedule)
        .filter_by(scheduler_run_id=run.id, event_ref_num=900201)
        .first()
    )
    assert ps is not None, (
        "Orphan Supervisor must have a PendingSchedule row in the run")
    assert ps.employee_id is not None, (
        "Orphan Supervisor must be assigned an employee, not left in manual "
        f"review (failure_reason={ps.failure_reason!r})")
    assert ps.schedule_datetime.date() == core_day, (
        f"Orphan Supervisor must be scheduled on the CORE's posted date "
        f"({core_day}), got {ps.schedule_datetime.date()}")
    assert ps.schedule_datetime.time() == time(12, 0), (
        f"Supervisor events must be scheduled at 12 PM, got "
        f"{ps.schedule_datetime.time()}")


# --- Phase 3 category dispatcher (M7) ----------------------------------------


def test_m7_phase3_strict_category_order(
    greedy_scheduler, models, db_session, future_datetime
):
    """Spec branch M7: Phase 3 dispatches categories in strict order
    regardless of event count per category.

    The expected order is defined by `SchedulingEngine.CATEGORY_ORDER`.
    This test creates one event per category and spies on the dispatcher
    to record the order in which categories are processed.
    """
    Event = models['Event']

    # One event per category so we can witness dispatch order. The
    # Supervisor event pairs with CORE 300003 (same 6-digit prefix).
    events_data = [
        (300001, 'Juicer Production', '300001-JUICER-PRODUCTION-Test'),
        (300002, 'Juicer Survey', '300002-JUICER-SURVEY-Test'),
        (300003, 'Core', '300003-MAP-Brand-Product CORE'),
        (300004, 'Supervisor', '300003-MAP-Brand-Product Supervisor'),
        (300005, 'Freeosk', '300005-FSK-Daily Service-11AM'),
        (300006, 'Digital Setup', '300006-Digital Demo Refresh'),
        (300007, 'Other', '300007-Other-Test'),
    ]
    for ref, etype, name in events_data:
        db_session.add(Event(
            project_ref_num=ref, project_name=name, event_type=etype,
            condition='Unstaffed', is_scheduled=False,
            start_datetime=future_datetime(5),
            due_datetime=future_datetime(10),
            estimated_time=60,
        ))
    db_session.commit()

    # Spy on the dispatcher to record order.
    seen_order = []
    original = greedy_scheduler._process_category

    def spy(category_name, run):
        seen_order.append(category_name)
        return original(category_name, run)

    greedy_scheduler._process_category = spy

    greedy_scheduler.run_auto_scheduler(run_type='manual')

    assert seen_order == list(greedy_scheduler.CATEGORY_ORDER), (
        f"Category dispatch order wrong: {seen_order}")
