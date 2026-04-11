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
