"""Conformance tests for spec 00-master-overview.md."""


def test_m0_default_scheduler_is_greedy(app):
    """Spec: the production scheduler is the greedy engine, not CP-SAT.

    Verified indirectly via the CPSAT_ENABLED config default.
    """
    assert app.config['CPSAT_ENABLED'] is False, (
        "CPSAT_ENABLED must default to False. Greedy is the "
        "production scheduler per the 2026-04-10 rewrite.")


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
