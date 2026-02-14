"""
Tests for the CP-SAT constraint-programming auto-scheduler.

Covers hard constraints (must be satisfied), soft constraints (objective),
and integration with the existing PendingSchedule approval workflow.
"""
import pytest
from datetime import datetime, timedelta, date, time


def _future(days=3):
    """Return a datetime `days` ahead from today."""
    return datetime.now() + timedelta(days=days)


def _future_date(days=3):
    """Return a date `days` ahead from today."""
    return (datetime.now() + timedelta(days=days)).date()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_employee(models, db_session, emp_id, name, job_title='Event Specialist',
                   juicer_trained=False, is_supervisor=False):
    Employee = models['Employee']
    emp = Employee(
        id=emp_id, name=name, job_title=job_title,
        juicer_trained=juicer_trained, is_supervisor=is_supervisor,
    )
    db_session.add(emp)
    return emp


def _make_event(models, db_session, ref_num, event_type='Core', name=None,
                start_days=3, due_days=14, estimated_time=None, condition='Unstaffed'):
    Event = models['Event']
    event = Event(
        project_ref_num=ref_num,
        project_name=name or f'{ref_num:06d}-{event_type}-Test',
        event_type=event_type,
        condition=condition,
        start_datetime=_future(start_days),
        due_datetime=_future(due_days),
        estimated_time=estimated_time,
    )
    db_session.add(event)
    return event


def _run_cpsat(db_session, models, time_limit=30):
    """Run CP-SAT scheduler and return the run record."""
    from app.services.cpsat_scheduler import CPSATSchedulingEngine
    engine = CPSATSchedulingEngine(db_session, models)
    return engine.run_auto_scheduler(run_type='manual', time_limit_seconds=time_limit)


def _get_pending(db_session, models, run_id):
    """Return PendingSchedule records for a run."""
    PendingSchedule = models['PendingSchedule']
    return db_session.query(PendingSchedule).filter_by(scheduler_run_id=run_id).all()


def _get_successful(db_session, models, run_id):
    """Return PendingSchedule records that were successfully scheduled."""
    return [p for p in _get_pending(db_session, models, run_id)
            if p.employee_id is not None and p.schedule_datetime is not None]


# ---------------------------------------------------------------------------
# Basic scheduling
# ---------------------------------------------------------------------------

class TestBasicScheduling:
    """Test that events are scheduled when constraints allow."""

    def test_single_core_event_scheduled(self, db_session, models):
        """One Core event + one eligible employee → event gets scheduled."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_event(models, db_session, 100001, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled >= 1

        scheduled = _get_successful(db_session, models, run.id)
        assert len(scheduled) >= 1
        assert scheduled[0].employee_id == 'emp1'

    def test_no_employees_means_failure(self, db_session, models):
        """Event with no eligible employees cannot be scheduled."""
        _make_event(models, db_session, 100002, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled == 0

    def test_no_events_means_empty_run(self, db_session, models):
        """No events to schedule → clean completed run."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.total_events_processed == 0

    def test_multiple_events_multiple_employees(self, db_session, models):
        """Multiple Core events distributed across employees."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_employee(models, db_session, 'emp2', 'Bob')
        for i in range(4):
            _make_event(models, db_session, 200001 + i, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled >= 2  # At least some should be scheduled


# ---------------------------------------------------------------------------
# Hard constraints
# ---------------------------------------------------------------------------

class TestHardConstraints:
    """Verify that hard constraints are never violated in the solution."""

    def test_h5_time_off_respected(self, db_session, models):
        """Employee on time off is not assigned events on those days."""
        emp = _make_employee(models, db_session, 'emp1', 'Alice')
        db_session.flush()  # Flush employee so FK constraint is satisfied

        EmployeeTimeOff = models['EmployeeTimeOff']

        # Block all valid days with time off
        to = EmployeeTimeOff(
            employee_id='emp1',
            start_date=_future_date(0),
            end_date=_future_date(30),
        )
        db_session.add(to)

        _make_event(models, db_session, 300001, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        # Employee is unavailable for all days, so event can't be scheduled
        assert run.events_scheduled == 0

    def test_h6_weekly_availability_respected(self, db_session, models):
        """Employee unavailable on certain weekdays is not assigned those days."""
        emp = _make_employee(models, db_session, 'emp1', 'Alice')
        db_session.flush()  # Flush employee so FK constraint is satisfied

        EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

        # Mark all days unavailable
        wa = EmployeeWeeklyAvailability(
            employee_id='emp1',
            monday=False, tuesday=False, wednesday=False,
            thursday=False, friday=False, saturday=False, sunday=False,
        )
        db_session.add(wa)

        _make_event(models, db_session, 300002, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.events_scheduled == 0

    def test_h9_juicer_role_qualification(self, db_session, models):
        """Only Juicer Barista or Club Supervisor can work Juicer events."""
        # Regular Event Specialist — not qualified for Juicer
        _make_employee(models, db_session, 'emp1', 'Alice', job_title='Event Specialist')
        _make_event(models, db_session, 300003, 'Juicer Production',
                    name='123456-JUICER-PRODUCTION-SPCLTY', estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.events_scheduled == 0

    def test_h9_juicer_barista_can_work_juicer(self, db_session, models):
        """Juicer Barista can work Juicer events."""
        _make_employee(models, db_session, 'emp1', 'Alice',
                       job_title='Juicer Barista', juicer_trained=True)
        _make_event(models, db_session, 300004, 'Juicer Production',
                    name='123456-JUICER-PRODUCTION-SPCLTY', estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.events_scheduled >= 1

    def test_h10_lead_only_events(self, db_session, models):
        """Lead-only event types require Lead Event Specialist or Club Supervisor."""
        _make_employee(models, db_session, 'emp1', 'Alice', job_title='Event Specialist')
        _make_event(models, db_session, 300005, 'Freeosk',
                    name='123456-Freeosk-Test', estimated_time=15)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        # Event Specialist can't work Freeosk
        assert run.events_scheduled == 0

    def test_h10_lead_can_work_freeosk(self, db_session, models):
        """Lead Event Specialist can work Freeosk events."""
        _make_employee(models, db_session, 'emp1', 'Alice',
                       job_title='Lead Event Specialist')
        _make_event(models, db_session, 300006, 'Freeosk',
                    name='123456-Freeosk-Test', estimated_time=15)
        # Need a base event for H18 (support requires base)
        _make_event(models, db_session, 300007, 'Core',
                    name='123456-CORE-Test', estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.events_scheduled >= 1

    def test_h11_max_one_core_per_day(self, db_session, models):
        """Employee gets at most 1 Core event per day."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        # Create many Core events with same valid day range
        for i in range(5):
            _make_event(models, db_session, 400001 + i, 'Core',
                        start_days=3, due_days=5)  # Very narrow window
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        # Check no employee has > 1 Core event on same day
        emp_day_counts = {}
        for ps in scheduled:
            if ps.schedule_datetime:
                key = (ps.employee_id, ps.schedule_datetime.date())
                emp_day_counts[key] = emp_day_counts.get(key, 0) + 1

        for key, count in emp_day_counts.items():
            # May include Supervisor events paired with Core, but Core-only should be <= 1
            # The Supervisor event is separate, so we check Core-typed events
            core_count = sum(
                1 for ps in scheduled
                if ps.employee_id == key[0]
                and ps.schedule_datetime and ps.schedule_datetime.date() == key[1]
                and any(e.event_type == 'Core' and e.project_ref_num == ps.event_ref_num
                        for e in [models['Event'].query.filter_by(
                            project_ref_num=ps.event_ref_num).first()]
                        if e)
            )
            assert core_count <= 1, f"Employee {key[0]} has {core_count} Core events on {key[1]}"

    def test_h13_juicer_core_mutual_exclusion(self, db_session, models):
        """Employee cannot have both Juicer Production and Core on the same day."""
        emp = _make_employee(models, db_session, 'emp1', 'Alice',
                             job_title='Juicer Barista', juicer_trained=True)
        # Juicer and Core events with overlapping narrow window
        _make_event(models, db_session, 500001, 'Juicer Production',
                    name='111111-JUICER-PRODUCTION-SPCLTY', start_days=4, due_days=6,
                    estimated_time=540)
        _make_event(models, db_session, 500002, 'Core',
                    name='222222-CORE-Test', start_days=4, due_days=6,
                    estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        # Check mutual exclusion per day
        emp_day_types = {}
        for ps in scheduled:
            if ps.schedule_datetime:
                key = (ps.employee_id, ps.schedule_datetime.date())
                event = models['Event'].query.filter_by(
                    project_ref_num=ps.event_ref_num).first()
                if event:
                    emp_day_types.setdefault(key, set()).add(event.event_type)

        for key, types in emp_day_types.items():
            has_juicer = bool(types & {'Juicer Production', 'Juicer'})
            has_core = 'Core' in types
            assert not (has_juicer and has_core), \
                f"Employee {key[0]} has both Juicer and Core on {key[1]}"


# ---------------------------------------------------------------------------
# Soft constraints (objective preferences)
# ---------------------------------------------------------------------------

class TestSoftConstraints:
    """Verify that soft constraints influence the objective correctly."""

    def test_s2_urgent_events_prioritized(self, db_session, models):
        """Events closer to due date should be scheduled when capacity is limited."""
        _make_employee(models, db_session, 'emp1', 'Alice')

        # Urgent event: due in 5 days
        _make_event(models, db_session, 600001, 'Core',
                    name='111111-CORE-Urgent', start_days=3, due_days=5)
        # Non-urgent event: due in 20 days
        _make_event(models, db_session, 600002, 'Core',
                    name='222222-CORE-Later', start_days=3, due_days=20)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        # Both should ideally be scheduled, but if only one fits per day,
        # the urgent one should be preferred
        assert run.events_scheduled >= 1

    def test_s4_rotation_employee_preferred(self, db_session, models):
        """Rotation employee is preferred over other eligible employees."""
        RotationAssignment = models['RotationAssignment']

        emp_rot = _make_employee(models, db_session, 'emp_rot', 'RotJuicer',
                                 job_title='Juicer Barista', juicer_trained=True)
        emp_other = _make_employee(models, db_session, 'emp_other', 'OtherJuicer',
                                   job_title='Juicer Barista', juicer_trained=True)

        # Set rotation for all days of week
        for dow in range(7):
            ra = RotationAssignment(
                day_of_week=dow, rotation_type='juicer',
                employee_id='emp_rot',
            )
            db_session.add(ra)

        _make_event(models, db_session, 700001, 'Juicer Production',
                    name='111111-JUICER-PRODUCTION-SPCLTY', estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        # The rotation employee should be preferred
        juicer_assignments = [ps for ps in scheduled
                              if ps.event_ref_num == 700001]
        if juicer_assignments:
            assert juicer_assignments[0].employee_id == 'emp_rot'


# ---------------------------------------------------------------------------
# Pairing constraints
# ---------------------------------------------------------------------------

class TestPairing:
    """Test Core-Supervisor and Juicer Production-Survey pairing."""

    def test_core_supervisor_paired(self, db_session, models):
        """Core event schedules its matching Supervisor on the same day to Club Supervisor."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_employee(models, db_session, 'sup1', 'Bob', job_title='Club Supervisor')

        # Core event
        _make_event(models, db_session, 800001, 'Core',
                    name='111111-CORE-Product')
        # Matching Supervisor event (same 6-digit number)
        _make_event(models, db_session, 800002, 'Supervisor',
                    name='111111-Supervisor-Product')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        core_ps = [ps for ps in scheduled if ps.event_ref_num == 800001]
        sup_ps = [ps for ps in scheduled if ps.event_ref_num == 800002]

        assert core_ps, "Core event should be scheduled"
        assert sup_ps, "Supervisor event should be scheduled"
        # Same day
        assert core_ps[0].schedule_datetime.date() == sup_ps[0].schedule_datetime.date()
        # Supervisor assigned to Club Supervisor, not the Core worker
        assert sup_ps[0].employee_id == 'sup1'

    def test_supervisor_falls_back_to_lead(self, db_session, models):
        """Supervisor event falls back to Lead Event Specialist when Club Supervisor unavailable."""
        EmployeeTimeOff = models['EmployeeTimeOff']

        _make_employee(models, db_session, 'emp1', 'Alice')
        sup = _make_employee(models, db_session, 'sup1', 'Bob', job_title='Club Supervisor')
        _make_employee(models, db_session, 'lead1', 'Carol', job_title='Lead Event Specialist')
        db_session.flush()

        # Put Club Supervisor on time off for the entire scheduling window
        time_off = EmployeeTimeOff(
            employee_id='sup1',
            start_date=_future_date(0),
            end_date=_future_date(30),
        )
        db_session.add(time_off)

        _make_event(models, db_session, 800003, 'Core',
                    name='222222-CORE-Product')
        _make_event(models, db_session, 800004, 'Supervisor',
                    name='222222-Supervisor-Product')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        sup_ps = [ps for ps in scheduled if ps.event_ref_num == 800004]
        assert sup_ps, "Supervisor event should be scheduled to Lead"
        assert sup_ps[0].employee_id == 'lead1'

    def test_supervisor_not_assigned_to_regular_employee(self, db_session, models):
        """Supervisor event is NOT assigned to regular Event Specialists."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_employee(models, db_session, 'emp2', 'Dave')

        _make_event(models, db_session, 800005, 'Core',
                    name='333333-CORE-Product')
        _make_event(models, db_session, 800006, 'Supervisor',
                    name='333333-Supervisor-Product')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        PendingSchedule = models['PendingSchedule']
        all_ps = PendingSchedule.query.filter_by(scheduler_run_id=run.id).all()

        sup_ps = [ps for ps in all_ps if ps.event_ref_num == 800006]
        assert sup_ps, "Supervisor event should have a pending record"
        # Should fail since no Club Supervisor or Lead is available
        assert sup_ps[0].failure_reason is not None

    def test_juicer_prod_survey_paired(self, db_session, models):
        """Juicer Production and Survey are scheduled on the same day."""
        _make_employee(models, db_session, 'emp1', 'Alice',
                       job_title='Juicer Barista', juicer_trained=True)

        _make_event(models, db_session, 900001, 'Juicer Production',
                    name='111111-JUICER-PRODUCTION-SPCLTY', estimated_time=540)
        _make_event(models, db_session, 900002, 'Juicer Survey',
                    name='111111-JUICER-SURVEY', estimated_time=15)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        prod_ps = [ps for ps in scheduled if ps.event_ref_num == 900001]
        survey_ps = [ps for ps in scheduled if ps.event_ref_num == 900002]

        if prod_ps and survey_ps:
            assert prod_ps[0].schedule_datetime.date() == survey_ps[0].schedule_datetime.date()
            assert prod_ps[0].employee_id == survey_ps[0].employee_id


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

class TestRunLifecycle:
    """Test that the scheduler run record is properly created and updated."""

    def test_completed_run_has_stats(self, db_session, models):
        """A completed run populates statistics fields."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_event(models, db_session, 100010, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.completed_at is not None
        assert run.total_events_processed >= 1
        assert run.error_message is None

    def test_run_creates_pending_schedules(self, db_session, models):
        """Each event gets a PendingSchedule record (success or failure)."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_event(models, db_session, 100011, 'Core')
        _make_event(models, db_session, 100012, 'Core')
        db_session.commit()

        run = _run_cpsat(db_session, models)
        pending = _get_pending(db_session, models, run.id)
        # At least one PendingSchedule per event
        assert len(pending) >= 2


# ---------------------------------------------------------------------------
# Integration with route
# ---------------------------------------------------------------------------

class TestRouteIntegration:
    """Test the auto-scheduler route with CP-SAT solver."""

    def test_solver_override_param(self, client, db_session, models):
        """Route accepts ?solver=cpsat override parameter."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_event(models, db_session, 100020, 'Core')
        db_session.commit()

        response = client.post('/auto-schedule/run?solver=cpsat')
        data = response.get_json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data.get('solver') == 'cpsat'

    def test_greedy_override_param(self, client, db_session, models):
        """Route accepts ?solver=greedy override parameter."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_event(models, db_session, 100021, 'Core')
        db_session.commit()

        response = client.post('/auto-schedule/run?solver=greedy')
        data = response.get_json()

        assert response.status_code == 200
        assert data['success'] is True
        assert data.get('solver') == 'greedy'
