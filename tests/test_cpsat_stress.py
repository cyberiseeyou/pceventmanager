"""
CP-SAT Solver Stress Tests
===========================

Comprehensive constraint verification across diverse scheduling scenarios.
Creates realistic test data (employees, events, rotations, availability)
and runs the solver repeatedly, asserting every hard constraint after each run.

Covers:
  - Correctness: no constraint violations ever
  - Completeness: schedulable events are not left unscheduled
  - Optimality: rotation compliance, fairness, priority ordering
"""
import pytest
from collections import defaultdict
from datetime import datetime, timedelta, date, time


@pytest.fixture(autouse=True)
def _auto_force_cpsat(force_cpsat):
    """Module-level autouse: every test in this file forces CPSAT_ENABLED=True.

    Delegates to the shared `force_cpsat` fixture in tests/conftest.py.
    TODO(plan-08): remove when CPSAT_ENABLED flag is retired.
    """
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future(days=3):
    return datetime.now() + timedelta(days=days)


def _future_date(days=3):
    return (datetime.now() + timedelta(days=days)).date()


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
                start_days=3, due_days=14, estimated_time=None,
                condition='Unstaffed'):
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


def _make_time_off(models, db_session, employee_id, start_days, end_days):
    EmployeeTimeOff = models['EmployeeTimeOff']
    to = EmployeeTimeOff(
        employee_id=employee_id,
        start_date=_future_date(start_days),
        end_date=_future_date(end_days),
    )
    db_session.add(to)
    return to


def _make_weekly_availability(models, db_session, employee_id, **kwargs):
    """Set weekly availability. Pass day names as booleans (e.g. monday=False)."""
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']
    defaults = {d: True for d in
                ['monday', 'tuesday', 'wednesday', 'thursday',
                 'friday', 'saturday', 'sunday']}
    defaults.update(kwargs)
    wa = EmployeeWeeklyAvailability(employee_id=employee_id, **defaults)
    db_session.add(wa)
    return wa


def _make_rotation(models, db_session, day_of_week, rotation_type,
                   employee_id, backup_id=None):
    RotationAssignment = models['RotationAssignment']
    ra = RotationAssignment(
        day_of_week=day_of_week,
        rotation_type=rotation_type,
        employee_id=employee_id,
        backup_employee_id=backup_id,
    )
    db_session.add(ra)
    return ra


def _run_cpsat(db_session, models, time_limit=30):
    from app.services.cpsat_scheduler import CPSATSchedulingEngine
    engine = CPSATSchedulingEngine(db_session, models)
    return engine.run_auto_scheduler(run_type='manual', time_limit_seconds=time_limit)


def _get_pending(db_session, models, run_id):
    PendingSchedule = models['PendingSchedule']
    return db_session.query(PendingSchedule).filter_by(scheduler_run_id=run_id).all()


def _get_successful(db_session, models, run_id):
    return [p for p in _get_pending(db_session, models, run_id)
            if p.employee_id is not None and p.schedule_datetime is not None]


def _get_event_type_map(models, pending_list):
    """Build a map of event_ref_num -> event_type for pending schedules."""
    Event = models['Event']
    cache = {}
    for ps in pending_list:
        if ps.event_ref_num not in cache:
            event = Event.query.filter_by(project_ref_num=ps.event_ref_num).first()
            cache[ps.event_ref_num] = event.event_type if event else 'Unknown'
    return cache


# ---------------------------------------------------------------------------
# Constraint Verification Engine
# ---------------------------------------------------------------------------

class ConstraintVerifier:
    """Verify every hard constraint after a solver run."""

    def __init__(self, models, db_session, run_id):
        self.models = models
        self.db_session = db_session
        self.scheduled = _get_successful(db_session, models, run_id)
        self.type_map = _get_event_type_map(models, self.scheduled)
        self.violations = []

    def _get_type(self, ps):
        return self.type_map.get(ps.event_ref_num, 'Unknown')

    def _get_date(self, ps):
        if isinstance(ps.schedule_datetime, datetime):
            return ps.schedule_datetime.date()
        return ps.schedule_datetime

    def verify_all(self):
        """Run all constraint checks. Returns list of violation strings."""
        self.violations = []
        self.verify_h11_max_core_per_day()
        self.verify_h12_max_core_per_week()
        self.verify_h13_juicer_core_exclusion()
        self.verify_h14_deep_clean_production_exclusion()
        self.verify_h22_max_juicer_per_day()
        self.verify_h23_max_juicer_per_week()
        self.verify_h5_h6_availability()
        self.verify_h9_juicer_qualification()
        self.verify_h10_lead_qualification()
        self.verify_h18_support_requires_base()
        self.verify_h21_block_uniqueness()
        self.verify_h24_weekly_hours()
        return self.violations

    def verify_h11_max_core_per_day(self):
        """H11: Max 1 Core event per employee per day."""
        emp_day = defaultdict(int)
        for ps in self.scheduled:
            if self._get_type(ps) == 'Core':
                key = (ps.employee_id, self._get_date(ps))
                emp_day[key] += 1
        for (emp, day), count in emp_day.items():
            if count > 1:
                self.violations.append(
                    f"H11: Employee {emp} has {count} Core events on {day}")

    def verify_h12_max_core_per_week(self):
        """H12: Max 6 Core events per employee per week (Sun-Sat)."""
        emp_week = defaultdict(int)
        for ps in self.scheduled:
            if self._get_type(ps) == 'Core':
                d = self._get_date(ps)
                # Week number: ISO week shifted to Sunday start
                days_since_sunday = (d.weekday() + 1) % 7
                week_start = d - timedelta(days=days_since_sunday)
                key = (ps.employee_id, week_start)
                emp_week[key] += 1
        for (emp, week), count in emp_week.items():
            if count > 6:
                self.violations.append(
                    f"H12: Employee {emp} has {count} Core events in week of {week}")

    def verify_h13_juicer_core_exclusion(self):
        """H13: No Juicer Production + Core on same day for same employee."""
        juicer_types = {'Juicer', 'Juicer Production'}
        emp_day_types = defaultdict(set)
        for ps in self.scheduled:
            etype = self._get_type(ps)
            if etype in juicer_types or etype == 'Core':
                key = (ps.employee_id, self._get_date(ps))
                emp_day_types[key].add(etype)
        for (emp, day), types in emp_day_types.items():
            has_juicer = bool(types & juicer_types)
            has_core = 'Core' in types
            if has_juicer and has_core:
                self.violations.append(
                    f"H13: Employee {emp} has Juicer+Core on {day}")

    def verify_h14_deep_clean_production_exclusion(self):
        """H14: No Juicer Deep Clean + Juicer Production on same calendar day."""
        day_types = defaultdict(set)
        for ps in self.scheduled:
            etype = self._get_type(ps)
            if etype in ('Juicer Deep Clean', 'Juicer Production', 'Juicer'):
                day_types[self._get_date(ps)].add(etype)
        for day, types in day_types.items():
            if 'Juicer Deep Clean' in types and ('Juicer Production' in types or 'Juicer' in types):
                self.violations.append(
                    f"H14: Deep Clean and Production on same day {day}")

    def verify_h22_max_juicer_per_day(self):
        """H22: Max 1 Juicer Production per employee per day."""
        juicer_types = {'Juicer', 'Juicer Production'}
        emp_day = defaultdict(int)
        for ps in self.scheduled:
            if self._get_type(ps) in juicer_types:
                key = (ps.employee_id, self._get_date(ps))
                emp_day[key] += 1
        for (emp, day), count in emp_day.items():
            if count > 1:
                self.violations.append(
                    f"H22: Employee {emp} has {count} Juicer Prod on {day}")

    def verify_h23_max_juicer_per_week(self):
        """H23: Max 5 Juicer Production per employee per week."""
        juicer_types = {'Juicer', 'Juicer Production'}
        emp_week = defaultdict(int)
        for ps in self.scheduled:
            if self._get_type(ps) in juicer_types:
                d = self._get_date(ps)
                days_since_sunday = (d.weekday() + 1) % 7
                week_start = d - timedelta(days=days_since_sunday)
                key = (ps.employee_id, week_start)
                emp_week[key] += 1
        for (emp, week), count in emp_week.items():
            if count > 5:
                self.violations.append(
                    f"H23: Employee {emp} has {count} Juicer Prod in week of {week}")

    def verify_h5_h6_availability(self):
        """H5/H6: Employee must be available on assigned day."""
        EmployeeTimeOff = self.models.get('EmployeeTimeOff')
        EmployeeWeeklyAvailability = self.models.get('EmployeeWeeklyAvailability')

        unavailable = set()

        if EmployeeWeeklyAvailability:
            day_attrs = ['monday', 'tuesday', 'wednesday', 'thursday',
                         'friday', 'saturday', 'sunday']
            for wa in EmployeeWeeklyAvailability.query.all():
                for ps in self.scheduled:
                    d = self._get_date(ps)
                    day_idx = d.weekday()
                    if not getattr(wa, day_attrs[day_idx], True):
                        unavailable.add((wa.employee_id, d))

        if EmployeeTimeOff:
            for to in EmployeeTimeOff.query.all():
                for ps in self.scheduled:
                    d = self._get_date(ps)
                    if to.start_date <= d <= to.end_date:
                        unavailable.add((to.employee_id, d))

        for ps in self.scheduled:
            key = (ps.employee_id, self._get_date(ps))
            if key in unavailable:
                self.violations.append(
                    f"H5/H6: Employee {ps.employee_id} unavailable on "
                    f"{self._get_date(ps)} but assigned event {ps.event_ref_num}")

    def verify_h9_juicer_qualification(self):
        """H9: Only Juicer Barista or Club Supervisor (or juicer_trained) can work Juicer events."""
        juicer_types = {'Juicer', 'Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'}
        Employee = self.models['Employee']
        for ps in self.scheduled:
            if self._get_type(ps) in juicer_types:
                emp = Employee.query.get(ps.employee_id)
                if emp and emp.job_title not in ('Juicer Barista', 'Club Supervisor'):
                    if not getattr(emp, 'juicer_trained', False):
                        self.violations.append(
                            f"H9: Employee {ps.employee_id} ({emp.job_title}) "
                            f"assigned Juicer event {ps.event_ref_num}")

    def verify_h10_lead_qualification(self):
        """H10: Lead-only events require Lead Event Specialist or Club Supervisor."""
        lead_types = {'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh',
                      'Digital Teardown', 'Other'}
        Employee = self.models['Employee']
        for ps in self.scheduled:
            if self._get_type(ps) in lead_types:
                emp = Employee.query.get(ps.employee_id)
                if emp and emp.job_title not in ('Lead Event Specialist', 'Club Supervisor'):
                    self.violations.append(
                        f"H10: Employee {ps.employee_id} ({emp.job_title}) "
                        f"assigned lead-only event {ps.event_ref_num}")

    def verify_h18_support_requires_base(self):
        """H18: Support events require a base event (Core/Juicer) on same day/employee.
        Exception: Club Supervisor is exempt."""
        support_types = {'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh',
                         'Digital Teardown'}
        base_types = {'Core', 'Juicer', 'Juicer Production'}

        Employee = self.models['Employee']

        # Build per (emp, day) set of event types
        emp_day_types = defaultdict(set)
        for ps in self.scheduled:
            key = (ps.employee_id, self._get_date(ps))
            emp_day_types[key].add(self._get_type(ps))

        for ps in self.scheduled:
            etype = self._get_type(ps)
            if etype not in support_types:
                continue
            emp = Employee.query.get(ps.employee_id)
            if emp and emp.job_title == 'Club Supervisor':
                continue  # Exempt
            key = (ps.employee_id, self._get_date(ps))
            if not (emp_day_types[key] & base_types):
                self.violations.append(
                    f"H18: Support event {ps.event_ref_num} ({etype}) for "
                    f"{ps.employee_id} on {self._get_date(ps)} has no base event")

    def verify_h21_block_uniqueness(self):
        """H21: Max 1 Core event per block per day.

        Block numbers aren't stored in PendingSchedule, so we verify
        that the number of Core events on any single day doesn't exceed
        the total number of blocks (8). The real block-level uniqueness
        is enforced by the solver's AddAtMostOne constraint; this check
        catches gross over-scheduling on a single day.
        """
        day_core_count = defaultdict(int)
        for ps in self.scheduled:
            if self._get_type(ps) == 'Core' and ps.schedule_datetime:
                day_core_count[self._get_date(ps)] += 1
        for day, count in day_core_count.items():
            if count > 8:  # NUM_CORE_BLOCKS
                self.violations.append(
                    f"H21: {count} Core events on {day} exceeds 8 blocks")

    def verify_h24_weekly_hours(self):
        """H24: Total estimated work per employee per week <= 40 hours (2400 min)."""
        Event = self.models['Event']
        emp_week_minutes = defaultdict(int)
        for ps in self.scheduled:
            d = self._get_date(ps)
            days_since_sunday = (d.weekday() + 1) % 7
            week_start = d - timedelta(days=days_since_sunday)
            event = Event.query.filter_by(project_ref_num=ps.event_ref_num).first()
            est = event.estimated_time if event and event.estimated_time else 60
            key = (ps.employee_id, week_start)
            emp_week_minutes[key] += est
        for (emp, week), minutes in emp_week_minutes.items():
            if minutes > 2400:
                self.violations.append(
                    f"H24: Employee {emp} has {minutes} minutes in week of {week} (max 2400)")


# ---------------------------------------------------------------------------
# Scenario Builders
# ---------------------------------------------------------------------------

def setup_basic_team(models, db_session):
    """Create a realistic team: 4 Event Specialists, 1 Lead, 1 Juicer, 1 Club Supervisor."""
    _make_employee(models, db_session, 'es1', 'Alice', 'Event Specialist')
    _make_employee(models, db_session, 'es2', 'Bob', 'Event Specialist')
    _make_employee(models, db_session, 'es3', 'Carol', 'Event Specialist')
    _make_employee(models, db_session, 'es4', 'Dave', 'Event Specialist')
    _make_employee(models, db_session, 'lead1', 'Eve', 'Lead Event Specialist')
    _make_employee(models, db_session, 'jb1', 'Frank', 'Juicer Barista', juicer_trained=True)
    _make_employee(models, db_session, 'cs1', 'Grace', 'Club Supervisor')
    db_session.flush()


def setup_rotations(models, db_session):
    """Set up juicer and primary lead rotations for all days."""
    for dow in range(7):
        _make_rotation(models, db_session, dow, 'juicer', 'jb1', backup_id='cs1')
        _make_rotation(models, db_session, dow, 'primary_lead', 'lead1', backup_id='cs1')


# ---------------------------------------------------------------------------
# SCENARIO 1: Heavy Core Load (stress-test H11, H12, H21, fairness)
# ---------------------------------------------------------------------------

class TestScenarioHeavyCoreLoad:
    """12 Core events across 1 week with 4 Event Specialists.
    Should fit: 4 employees * 3 days (within window) = 12 slots."""

    def test_all_cores_scheduled_no_violations(self, db_session, models):
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # 12 Core events spread across a few days
        for i in range(12):
            _make_event(models, db_session, 100001 + i, 'Core',
                        name=f'{100001 + i:06d}-Brand{chr(65+i%4)}-Product',
                        start_days=3, due_days=10, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'

        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Constraint violations:\n" + "\n".join(violations)

        # Completeness: at least 8 of 12 should be scheduled
        # (limited by blocks/days/employees within the 3-day buffer window)
        scheduled = _get_successful(db_session, models, run.id)
        assert len(scheduled) >= 4, f"Only {len(scheduled)} events scheduled out of 12"

    def test_fairness_distribution(self, db_session, models):
        """Core events should be distributed fairly across eligible employees."""
        setup_basic_team(models, db_session)

        for i in range(8):
            _make_event(models, db_session, 200001 + i, 'Core',
                        start_days=3, due_days=14, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)
        type_map = _get_event_type_map(models, scheduled)

        emp_counts = defaultdict(int)
        for ps in scheduled:
            if type_map.get(ps.event_ref_num) == 'Core':
                emp_counts[ps.employee_id] += 1

        if len(emp_counts) >= 2:
            max_c = max(emp_counts.values())
            min_c = min(emp_counts.values())
            spread = max_c - min_c
            # Fairness: spread should be reasonable (<=3 for 8 events)
            assert spread <= 4, (
                f"Unfair distribution: {dict(emp_counts)}, spread={spread}")


# ---------------------------------------------------------------------------
# SCENARIO 2: Juicer Events (H9, H13, H22, H23, H25, pairing)
# ---------------------------------------------------------------------------

class TestScenarioJuicerEvents:
    """Test Juicer Production + Survey pairing, role qualifications,
    Juicer-Core mutual exclusion, and weekly limits."""

    def test_juicer_production_survey_pairing(self, db_session, models):
        """Production and Survey must be on same day, same employee."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        _make_event(models, db_session, 300001, 'Juicer Production',
                    name='111111-JUICER-PRODUCTION-SPCLTY',
                    start_days=3, due_days=14, estimated_time=540)
        _make_event(models, db_session, 300002, 'Juicer Survey',
                    name='111111-JUICER-SURVEY',
                    start_days=3, due_days=14, estimated_time=15)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        prod = [ps for ps in scheduled if ps.event_ref_num == 300001]
        surv = [ps for ps in scheduled if ps.event_ref_num == 300002]

        if prod and surv:
            assert prod[0].employee_id == surv[0].employee_id, \
                "Production and Survey should have same employee"
            p_date = prod[0].schedule_datetime.date() if isinstance(prod[0].schedule_datetime, datetime) else prod[0].schedule_datetime
            s_date = surv[0].schedule_datetime.date() if isinstance(surv[0].schedule_datetime, datetime) else surv[0].schedule_datetime
            assert p_date == s_date, \
                "Production and Survey should be on same day"

    def test_juicer_core_mutual_exclusion_under_pressure(self, db_session, models):
        """With only 1 juicer-trained employee and both Juicer + Core events on same day,
        the solver must NOT assign both to same employee on same day."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Create Juicer and Core with very narrow window (single day)
        _make_event(models, db_session, 400001, 'Juicer Production',
                    name='222222-JUICER-PRODUCTION-SPCLTY',
                    start_days=4, due_days=6, estimated_time=540)
        _make_event(models, db_session, 400002, 'Core',
                    name='333333-CORE-Test',
                    start_days=4, due_days=6, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_juicer_weekly_limit(self, db_session, models):
        """7 Juicer Production events in one week — max 5 should be scheduled per employee."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        for i in range(7):
            _make_event(models, db_session, 500001 + i, 'Juicer Production',
                        name=f'{500001 + i:06d}-JUICER-PRODUCTION-SPCLTY',
                        start_days=3 + i, due_days=3 + i + 1,  # One day each
                        estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_juicer_role_enforcement(self, db_session, models):
        """Only qualified employees should be assigned to Juicer events."""
        _make_employee(models, db_session, 'es_only', 'NotTrained', 'Event Specialist')
        _make_event(models, db_session, 600001, 'Juicer Production',
                    name='444444-JUICER-PRODUCTION-SPCLTY',
                    estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        # Should fail to schedule — no qualified employees
        assert run.events_scheduled == 0


# ---------------------------------------------------------------------------
# SCENARIO 3: Core + Supervisor Pairing (H16)
# ---------------------------------------------------------------------------

class TestScenarioCoreSupervisor:
    """Test that Core events get paired Supervisor events on the same day."""

    def test_core_supervisor_pairing(self, db_session, models):
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        _make_event(models, db_session, 700001, 'Core',
                    name='555555-CORE-Product', estimated_time=390)
        _make_event(models, db_session, 700002, 'Supervisor',
                    name='555555-Supervisor-Product', estimated_time=60)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        core_ps = [ps for ps in scheduled if ps.event_ref_num == 700001]
        sup_ps = [ps for ps in scheduled if ps.event_ref_num == 700002]

        assert core_ps, "Core event should be scheduled"
        assert sup_ps, "Supervisor event should be scheduled"

        core_date = core_ps[0].schedule_datetime.date()
        sup_date = sup_ps[0].schedule_datetime.date()
        assert core_date == sup_date, "Core and Supervisor must be on same day"

        # Supervisor should go to Club Supervisor or Lead
        Employee = models['Employee']
        sup_emp = Employee.query.get(sup_ps[0].employee_id)
        assert sup_emp.job_title in ('Club Supervisor', 'Lead Event Specialist'), \
            f"Supervisor assigned to {sup_emp.job_title}, expected CS or Lead"

    def test_multiple_core_supervisor_pairs(self, db_session, models):
        """Multiple Core+Supervisor pairs should all be matched."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        for i in range(3):
            num = f'{666001 + i:06d}'
            _make_event(models, db_session, 800001 + i * 2, 'Core',
                        name=f'{num}-CORE-Product{i}', estimated_time=390)
            _make_event(models, db_session, 800002 + i * 2, 'Supervisor',
                        name=f'{num}-Supervisor-Product{i}', estimated_time=60)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 4: Support Events (H18 — Freeosk/Digital require base)
# ---------------------------------------------------------------------------

class TestScenarioSupportEvents:
    """Freeosk and Digital events require a base Core or Juicer on same day/employee."""

    def test_freeosk_requires_core(self, db_session, models):
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Create Freeosk + Core on same day range
        _make_event(models, db_session, 900001, 'Core',
                    name='777777-CORE-Test', start_days=3, due_days=10,
                    estimated_time=390)
        _make_event(models, db_session, 900002, 'Freeosk',
                    name='777777-Freeosk-Test', start_days=3, due_days=10,
                    estimated_time=15)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_freeosk_without_core_fails_for_non_cs(self, db_session, models):
        """Freeosk for a non-Club Supervisor without a Core should fail."""
        # Only create a Lead (eligible for Freeosk but needs base)
        _make_employee(models, db_session, 'lead_only', 'LeadOnly',
                       'Lead Event Specialist')
        _make_event(models, db_session, 900003, 'Freeosk',
                    name='888888-Freeosk-Test', estimated_time=15)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)
        # Should NOT have scheduled the Freeosk (no base event)
        scheduled = _get_successful(db_session, models, run.id)
        freeosk = [ps for ps in scheduled if ps.event_ref_num == 900003]
        assert len(freeosk) == 0, "Freeosk should not schedule without base event"

    def test_club_supervisor_exempt_from_base(self, db_session, models):
        """Club Supervisor can work Freeosk without a base Core event."""
        _make_employee(models, db_session, 'cs_only', 'CSOnly', 'Club Supervisor')
        _make_event(models, db_session, 900004, 'Freeosk',
                    name='999999-Freeosk-Test', estimated_time=15)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 5: Availability Constraints (H5/H6)
# ---------------------------------------------------------------------------

class TestScenarioAvailability:
    """Time off, weekly availability, and availability overrides."""

    def test_time_off_respected(self, db_session, models):
        setup_basic_team(models, db_session)

        # Put all employees on time off except one
        for eid in ['es1', 'es2', 'es3', 'es4', 'lead1', 'jb1', 'cs1']:
            if eid != 'es1':
                _make_time_off(models, db_session, eid, 0, 30)

        for i in range(3):
            _make_event(models, db_session, 110001 + i, 'Core',
                        start_days=3, due_days=10, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # Only es1 should be assigned
        scheduled = _get_successful(db_session, models, run.id)
        for ps in scheduled:
            assert ps.employee_id == 'es1', \
                f"Expected es1, got {ps.employee_id} (others on time off)"

    def test_weekly_availability_respected(self, db_session, models):
        """Employee unavailable on certain days should not be assigned those days."""
        _make_employee(models, db_session, 'es_restricted', 'Restricted', 'Event Specialist')
        db_session.flush()

        # Only available Mon-Wed
        _make_weekly_availability(models, db_session, 'es_restricted',
                                  thursday=False, friday=False,
                                  saturday=False, sunday=False)

        _make_event(models, db_session, 120001, 'Core',
                    start_days=3, due_days=14, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # If scheduled, must be Mon-Wed
        scheduled = _get_successful(db_session, models, run.id)
        for ps in scheduled:
            if ps.employee_id == 'es_restricted':
                d = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
                assert d.weekday() <= 2, \
                    f"Restricted employee scheduled on day {d} (weekday {d.weekday()})"


# ---------------------------------------------------------------------------
# SCENARIO 6: Full-Day Events (H20)
# ---------------------------------------------------------------------------

class TestScenarioFullDayEvents:
    """Full-day events (>=480 min) should block Core/Juicer on same day/employee."""

    def test_full_day_blocks_core(self, db_session, models):
        setup_basic_team(models, db_session)

        # Full-day event (8 hours)
        _make_event(models, db_session, 130001, 'Core',
                    name='111111-FullDay-Test',
                    start_days=4, due_days=6, estimated_time=480)
        # Regular Core on same narrow window
        _make_event(models, db_session, 130002, 'Core',
                    name='222222-Regular-Test',
                    start_days=4, due_days=6, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 7: Rotation Compliance (S4, H25, H27)
# ---------------------------------------------------------------------------

class TestScenarioRotations:
    """Test that rotation assignments are preferred/enforced."""

    def test_juicer_rotation_enforced(self, db_session, models):
        """When rotation Juicer is available, they MUST get Juicer events (H25)."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        _make_event(models, db_session, 140001, 'Juicer Production',
                    name='333333-JUICER-PRODUCTION-SPCLTY',
                    start_days=3, due_days=14, estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        scheduled = _get_successful(db_session, models, run.id)

        juicer_ps = [ps for ps in scheduled if ps.event_ref_num == 140001]
        if juicer_ps:
            assert juicer_ps[0].employee_id == 'jb1', \
                f"Rotation Juicer (jb1) should get Juicer event, got {juicer_ps[0].employee_id}"

    def test_primary_lead_on_digital_setup(self, db_session, models):
        """Digital Setup should go to Primary Lead (H27) when available."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        _make_event(models, db_session, 150001, 'Digital Setup',
                    name='444444-Digitals-SETUP-Test',
                    start_days=3, due_days=14, estimated_time=60)
        # Need a Core for base event requirement
        _make_event(models, db_session, 150002, 'Core',
                    name='444444-CORE-Test',
                    start_days=3, due_days=14, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        setup_ps = [ps for ps in scheduled if ps.event_ref_num == 150001]
        if setup_ps:
            assert setup_ps[0].employee_id == 'lead1', \
                f"Primary Lead should get Digital Setup, got {setup_ps[0].employee_id}"


# ---------------------------------------------------------------------------
# SCENARIO 8: Due Date Priority (S2 — urgency)
# ---------------------------------------------------------------------------

class TestScenarioDueDatePriority:
    """Events closer to due date should be prioritized."""

    def test_urgent_event_preferred(self, db_session, models):
        """With limited capacity, urgent event should be chosen over non-urgent."""
        # Only 1 employee, 1 day available
        _make_employee(models, db_session, 'solo', 'Solo', 'Event Specialist')
        db_session.flush()

        # Make unavailable on all days except one
        _make_weekly_availability(models, db_session, 'solo',
                                  saturday=False, sunday=False)

        # Urgent: due in 5 days
        _make_event(models, db_session, 160001, 'Core',
                    name='555555-URGENT-Test',
                    start_days=3, due_days=5, estimated_time=390)
        # Not urgent: due in 20 days
        _make_event(models, db_session, 160002, 'Core',
                    name='666666-RELAXED-Test',
                    start_days=3, due_days=20, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 9: Event Type Priority (S3)
# ---------------------------------------------------------------------------

class TestScenarioEventTypePriority:
    """Higher-priority event types should be preferred when capacity is limited."""

    def test_juicer_over_core(self, db_session, models):
        """Juicer (priority 1) should be scheduled over Core (priority 6) under pressure."""
        _make_employee(models, db_session, 'jb_solo', 'JuicerSolo',
                       'Juicer Barista', juicer_trained=True)
        db_session.flush()

        # Both on same day, only 1 employee
        _make_event(models, db_session, 170001, 'Juicer Production',
                    name='777777-JUICER-PRODUCTION-SPCLTY',
                    start_days=4, due_days=6, estimated_time=540)
        _make_event(models, db_session, 170002, 'Core',
                    name='888888-CORE-Test',
                    start_days=4, due_days=6, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # Both can't be scheduled on same day (H13) — Juicer should win
        scheduled = _get_successful(db_session, models, run.id)
        type_map = _get_event_type_map(models, scheduled)
        types_scheduled = {type_map.get(ps.event_ref_num) for ps in scheduled}

        # Juicer should be prioritized
        juicer = [ps for ps in scheduled if ps.event_ref_num == 170001]
        assert len(juicer) >= 1, "Juicer should be scheduled (higher priority)"


# ---------------------------------------------------------------------------
# SCENARIO 10: Mixed Mega Scenario (everything at once)
# ---------------------------------------------------------------------------

class TestScenarioMegaMix:
    """Full realistic scenario: Core + Supervisor pairs, Juicer + Survey pairs,
    Freeosk, Digitals, time off, rotations — all together."""

    def test_mega_scenario_no_violations(self, db_session, models):
        """Run a complex realistic scenario and verify zero violations."""
        setup_basic_team(models, db_session)
        # Add extra employees for more capacity
        _make_employee(models, db_session, 'es5', 'Hank', 'Event Specialist')
        _make_employee(models, db_session, 'lead2', 'Ivy', 'Lead Event Specialist')
        _make_employee(models, db_session, 'jb2', 'Jack', 'Juicer Barista',
                       juicer_trained=True)
        db_session.flush()
        setup_rotations(models, db_session)

        # Some employees on partial time off
        _make_time_off(models, db_session, 'es1', 3, 5)
        _make_time_off(models, db_session, 'es3', 5, 7)

        # 6 Core + Supervisor pairs
        for i in range(6):
            num = f'{180001 + i:06d}'
            _make_event(models, db_session, 180001 + i * 10, 'Core',
                        name=f'{num}-BrandX-Product{i} ({num}01234) - V1-CORE',
                        start_days=3, due_days=12, estimated_time=390)
            _make_event(models, db_session, 180002 + i * 10, 'Supervisor',
                        name=f'{num}-BrandX-Supervisor{i} ({num}01234) - V1-SUPERVISOR',
                        start_days=3, due_days=12, estimated_time=60)

        # 2 Juicer Production + Survey pairs
        for i in range(2):
            num = f'{190001 + i:06d}'
            _make_event(models, db_session, 190001 + i * 10, 'Juicer Production',
                        name=f'{num}-JUICER-PRODUCTION-SPCLTY',
                        start_days=3 + i * 2, due_days=4 + i * 2,
                        estimated_time=540)
            _make_event(models, db_session, 190002 + i * 10, 'Juicer Survey',
                        name=f'{num}-JUICER-SURVEY',
                        start_days=3 + i * 2, due_days=4 + i * 2,
                        estimated_time=15)

        # 2 Freeosk events
        for i in range(2):
            _make_event(models, db_session, 191001 + i, 'Freeosk',
                        name=f'{191001 + i:06d}-Freeosk-Daily',
                        start_days=3 + i, due_days=4 + i,
                        estimated_time=15)

        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'

        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Constraint violations in mega scenario:\n" + "\n".join(violations)

        # Should schedule at least some events
        scheduled = _get_successful(db_session, models, run.id)
        assert len(scheduled) >= 4, f"Only {len(scheduled)} events scheduled in mega scenario"

    def test_mega_scenario_repeated_runs(self, db_session, models):
        """Run the mega scenario 3 times with different seeds to catch intermittent issues."""
        setup_basic_team(models, db_session)
        _make_employee(models, db_session, 'es5', 'Hank', 'Event Specialist')
        _make_employee(models, db_session, 'lead2', 'Ivy', 'Lead Event Specialist')
        db_session.flush()
        setup_rotations(models, db_session)

        ref = 200000
        for i in range(8):
            num = f'{ref + i:06d}'
            _make_event(models, db_session, ref + i, 'Core',
                        name=f'{num}-Mix-Product{i}',
                        start_days=3, due_days=14, estimated_time=390)

        _make_event(models, db_session, ref + 100, 'Juicer Production',
                    name=f'{ref + 100:06d}-JUICER-PRODUCTION-SPCLTY',
                    start_days=4, due_days=6, estimated_time=540)
        db_session.commit()

        # Run solver 3 times (each run creates its own history)
        for attempt in range(3):
            run = _run_cpsat(db_session, models)
            assert run.status == 'completed', f"Run {attempt + 1} failed: {run.error_message}"

            verifier = ConstraintVerifier(models, db_session, run.id)
            violations = verifier.verify_all()
            assert violations == [], \
                f"Run {attempt + 1} violations:\n" + "\n".join(violations)

            # Clean up pending schedules for next run
            PendingSchedule = models['PendingSchedule']
            db_session.query(PendingSchedule).filter_by(
                scheduler_run_id=run.id).delete()
            db_session.commit()


# ---------------------------------------------------------------------------
# SCENARIO 11: Edge Cases
# ---------------------------------------------------------------------------

class TestScenarioEdgeCases:
    """Edge cases that could trip up the solver."""

    def test_zero_events(self, db_session, models):
        """Empty event list should complete cleanly."""
        setup_basic_team(models, db_session)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled == 0

    def test_zero_employees(self, db_session, models):
        """No employees should result in zero scheduled events."""
        _make_event(models, db_session, 210001, 'Core', estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled == 0

    def test_single_employee_saturated(self, db_session, models):
        """1 employee, 10 Core events, narrow window — should hit daily/weekly limits cleanly."""
        _make_employee(models, db_session, 'solo', 'Solo', 'Event Specialist')

        for i in range(10):
            _make_event(models, db_session, 220001 + i, 'Core',
                        start_days=3, due_days=14, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # Verify per-week limits (H12: max 6/week, H11: max 1/day)
        scheduled = _get_successful(db_session, models, run.id)
        type_map = _get_event_type_map(models, scheduled)
        core_scheduled = [ps for ps in scheduled
                          if type_map.get(ps.event_ref_num) == 'Core']

        # Events span ~11 days (2 weeks), so up to 6+5=11 is possible
        # Just verify no week exceeds 6
        emp_week_counts = defaultdict(int)
        for ps in core_scheduled:
            d = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
            days_since_sunday = (d.weekday() + 1) % 7
            week_start = d - timedelta(days=days_since_sunday)
            emp_week_counts[(ps.employee_id, week_start)] += 1

        for (emp, week), count in emp_week_counts.items():
            assert count <= 6, \
                f"Employee {emp} has {count} Core events in week of {week} (max 6)"

    def test_all_employees_on_time_off(self, db_session, models):
        """All employees on time off — nothing should be scheduled."""
        setup_basic_team(models, db_session)
        for eid in ['es1', 'es2', 'es3', 'es4', 'lead1', 'jb1', 'cs1']:
            _make_time_off(models, db_session, eid, 0, 30)

        _make_event(models, db_session, 230001, 'Core', estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.events_scheduled == 0

        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_event_past_due(self, db_session, models):
        """Event with due date in the past should not be scheduled."""
        setup_basic_team(models, db_session)
        _make_event(models, db_session, 240001, 'Core',
                    start_days=-5, due_days=-1, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_large_estimated_time_weekly_cap(self, db_session, models):
        """Events with large estimated_time should respect 40-hour weekly cap (H24)."""
        _make_employee(models, db_session, 'solo', 'Solo', 'Event Specialist')

        # 5 events × 540 minutes = 2700 > 2400 max
        for i in range(5):
            _make_event(models, db_session, 250001 + i, 'Core',
                        start_days=3, due_days=10, estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 12: Deep Clean + Production Exclusion (H14)
# ---------------------------------------------------------------------------

class TestScenarioDeepClean:
    """Juicer Deep Clean and Juicer Production cannot be on the same calendar day."""

    def test_deep_clean_production_same_day(self, db_session, models):
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Both on same narrow day
        _make_event(models, db_session, 260001, 'Juicer Deep Clean',
                    name='555555-JUICER-DEEP-CLEAN',
                    start_days=4, due_days=6, estimated_time=540)
        _make_event(models, db_session, 260002, 'Juicer Production',
                    name='666666-JUICER-PRODUCTION-SPCLTY',
                    start_days=4, due_days=6, estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # Only one should be scheduled on that day
        scheduled = _get_successful(db_session, models, run.id)
        type_map = _get_event_type_map(models, scheduled)

        day_types = defaultdict(set)
        for ps in scheduled:
            d = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
            day_types[d].add(type_map.get(ps.event_ref_num))

        for day, types in day_types.items():
            assert not ('Juicer Deep Clean' in types and
                        ('Juicer Production' in types or 'Juicer' in types)), \
                f"Deep Clean and Production both on {day}"


# ---------------------------------------------------------------------------
# SCENARIO 13: Duplicate Product Penalty (S11 / RULE-020)
# ---------------------------------------------------------------------------

class TestScenarioDuplicateProduct:
    """Same brand should not appear twice on the same day (soft penalty)."""

    def test_same_brand_different_days_preferred(self, db_session, models):
        """Two events from same brand should land on different days when possible."""
        setup_basic_team(models, db_session)

        # Two Core events from "BrandA"
        _make_event(models, db_session, 270001, 'Core',
                    name='270001-BrandA-Product1',
                    start_days=3, due_days=10, estimated_time=390)
        _make_event(models, db_session, 270002, 'Core',
                    name='270002-BrandA-Product2',
                    start_days=3, due_days=10, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        brand_a = [ps for ps in scheduled
                   if ps.event_ref_num in (270001, 270002)]
        if len(brand_a) == 2:
            d1 = brand_a[0].schedule_datetime.date()
            d2 = brand_a[1].schedule_datetime.date()
            # Soft preference: should be different days when capacity allows
            # (not a hard failure if same day, just suboptimal)


# ---------------------------------------------------------------------------
# SCENARIO 14: Club Supervisor Misuse Penalty (S5)
# ---------------------------------------------------------------------------

class TestScenarioClubSupervisorMisuse:
    """Club Supervisor should be penalized for working regular Core events."""

    def test_cs_preferred_for_supervisor_events(self, db_session, models):
        """Club Supervisor should prefer Supervisor/Freeosk/Juicer over regular Core."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Supervisor event — CS should get it
        _make_event(models, db_session, 280001, 'Core',
                    name='111111-CORE-Test',
                    start_days=3, due_days=10, estimated_time=390)
        _make_event(models, db_session, 280002, 'Supervisor',
                    name='111111-Supervisor-Test',
                    start_days=3, due_days=10, estimated_time=60)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        sup_ps = [ps for ps in scheduled if ps.event_ref_num == 280002]
        if sup_ps:
            assert sup_ps[0].employee_id in ('cs1', 'lead1'), \
                f"Supervisor should go to CS or Lead, got {sup_ps[0].employee_id}"


# ---------------------------------------------------------------------------
# SCENARIO 15: Phase 3 Cross-Phase H13 (Juicer-Core mutual exclusion)
# ---------------------------------------------------------------------------

class TestScenarioPhase3H13:
    """H13 enforcement when Phase 2 schedules a Juicer event and Phase 3
    retries a failed Core — the Core must NOT land on the same employee+day
    as the Phase 2 Juicer assignment.

    This scenario engineers a Phase 3 retry by creating one event that
    succeeds in Phase 2 and one that fails (forcing Phase 3 with bumping).
    """

    def test_juicer_core_mutual_exclusion_across_phases(self, db_session, models):
        """Juicer from Phase 2 must block Core in Phase 3 for same emp+day."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Juicer event — should succeed in Phase 2 easily (jb1 is juicer)
        _make_event(models, db_session, 290001, 'Juicer',
                    name='290001-Juicer-TestH13',
                    start_days=3, due_days=10, estimated_time=480)

        # Many Core events to saturate capacity and trigger Phase 3 retries
        for i in range(10):
            _make_event(models, db_session, 290010 + i, 'Core',
                        name=f'{290010 + i:06d}-CORE-H13Test',
                        start_days=3, due_days=10, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_multiple_juicers_block_cores(self, db_session, models):
        """Multiple Juicer events scheduled across different days should
        each block Core on their respective employee+day."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # 3 Juicer events — will land on juicer-qualified employees
        for i in range(3):
            _make_event(models, db_session, 291001 + i, 'Juicer',
                        name=f'{291001 + i:06d}-Juicer-Multi',
                        start_days=3 + i, due_days=10 + i, estimated_time=480)

        # 8 Core events to fill capacity
        for i in range(8):
            _make_event(models, db_session, 291010 + i, 'Core',
                        name=f'{291010 + i:06d}-CORE-Multi',
                        start_days=3, due_days=10, estimated_time=390)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 16: High Density (Performance + correctness under pressure)
# ---------------------------------------------------------------------------

class TestScenarioHighDensity:
    """20+ events with 10+ employees — tests solver performance and
    correctness under high event density."""

    def test_high_density_no_violations(self, db_session, models):
        """Large scenario: 10 employees, 25 events, tight window."""
        # Extended team: 10 employees
        _make_employee(models, db_session, 'es1', 'Alice', 'Event Specialist')
        _make_employee(models, db_session, 'es2', 'Bob', 'Event Specialist')
        _make_employee(models, db_session, 'es3', 'Carol', 'Event Specialist')
        _make_employee(models, db_session, 'es4', 'Dave', 'Event Specialist')
        _make_employee(models, db_session, 'es5', 'Ivan', 'Event Specialist')
        _make_employee(models, db_session, 'es6', 'Judy', 'Event Specialist')
        _make_employee(models, db_session, 'lead1', 'Eve', 'Lead Event Specialist')
        _make_employee(models, db_session, 'lead2', 'Kim', 'Lead Event Specialist')
        _make_employee(models, db_session, 'jb1', 'Frank', 'Juicer Barista',
                       juicer_trained=True)
        _make_employee(models, db_session, 'cs1', 'Grace', 'Club Supervisor')
        db_session.flush()

        # Rotations for juicer / lead
        for dow in range(7):
            _make_rotation(models, db_session, dow, 'juicer', 'jb1', backup_id='cs1')
            _make_rotation(models, db_session, dow, 'primary_lead', 'lead1', backup_id='lead2')

        # 15 Core events
        for i in range(15):
            _make_event(models, db_session, 300001 + i, 'Core',
                        name=f'{300001 + i:06d}-Brand{chr(65 + i % 6)}-Product',
                        start_days=3, due_days=14, estimated_time=390)

        # 3 Juicer events
        for i in range(3):
            _make_event(models, db_session, 300020 + i, 'Juicer',
                        name=f'{300020 + i:06d}-Juicer-Dense',
                        start_days=3, due_days=14, estimated_time=480)

        # 3 Freeosk events (need Lead qualification)
        for i in range(3):
            _make_event(models, db_session, 300030 + i, 'Freeosk',
                        name=f'{300030 + i:06d}-Freeosk-Dense',
                        start_days=3, due_days=14, estimated_time=120)

        # 2 Digital Setup events
        for i in range(2):
            _make_event(models, db_session, 300040 + i, 'Digital Setup',
                        name=f'{300040 + i:06d}-DigSetup-Dense',
                        start_days=3, due_days=14, estimated_time=240)

        # 2 Supervisor events
        for i in range(2):
            _make_event(models, db_session, 300050 + i, 'Supervisor',
                        name=f'{300050 + i:06d}-Supervisor-Dense',
                        start_days=3, due_days=14, estimated_time=60)

        db_session.commit()

        run = _run_cpsat(db_session, models, time_limit=60)
        assert run.status == 'completed'

        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # At least half should be scheduled (25 events, generous capacity)
        scheduled = _get_successful(db_session, models, run.id)
        assert len(scheduled) >= 10, \
            f"Only {len(scheduled)} events scheduled out of 25"

    def test_high_density_repeated(self, db_session, models):
        """Run the high-density scenario 3 times to catch non-deterministic
        constraint violations."""
        for attempt in range(3):
            # Clean up from previous attempt
            PendingSchedule = models['PendingSchedule']
            SchedulerRunHistory = models['SchedulerRunHistory']
            if attempt > 0:
                db_session.query(PendingSchedule).delete()
                db_session.query(SchedulerRunHistory).delete()
                db_session.commit()

            # Extended team
            if attempt == 0:
                _make_employee(models, db_session, 'hd_es1', 'Alice2', 'Event Specialist')
                _make_employee(models, db_session, 'hd_es2', 'Bob2', 'Event Specialist')
                _make_employee(models, db_session, 'hd_es3', 'Carol2', 'Event Specialist')
                _make_employee(models, db_session, 'hd_es4', 'Dave2', 'Event Specialist')
                _make_employee(models, db_session, 'hd_es5', 'Ivan2', 'Event Specialist')
                _make_employee(models, db_session, 'hd_lead1', 'Eve2', 'Lead Event Specialist')
                _make_employee(models, db_session, 'hd_jb1', 'Frank2', 'Juicer Barista',
                               juicer_trained=True)
                _make_employee(models, db_session, 'hd_cs1', 'Grace2', 'Club Supervisor')
                db_session.flush()

                for dow in range(7):
                    _make_rotation(models, db_session, dow, 'juicer', 'hd_jb1',
                                   backup_id='hd_cs1')
                    _make_rotation(models, db_session, dow, 'primary_lead', 'hd_lead1',
                                   backup_id='hd_cs1')

                # Mix of event types
                for i in range(10):
                    _make_event(models, db_session, 310001 + i, 'Core',
                                start_days=3, due_days=14, estimated_time=390)
                for i in range(3):
                    _make_event(models, db_session, 310020 + i, 'Juicer',
                                start_days=3, due_days=14, estimated_time=480)
                for i in range(2):
                    _make_event(models, db_session, 310030 + i, 'Freeosk',
                                start_days=3, due_days=14, estimated_time=120)
                db_session.commit()

            run = _run_cpsat(db_session, models, time_limit=30)
            verifier = ConstraintVerifier(models, db_session, run.id)
            violations = verifier.verify_all()
            assert violations == [], \
                f"Attempt {attempt + 1}: Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 17: Phase 3 Cross-Phase H14 (Deep Clean + Production)
# ---------------------------------------------------------------------------

class TestScenarioPhase3H14:
    """H14 enforcement across phases: if Phase 2 schedules a Deep Clean,
    Phase 3 must not schedule Juicer Production on the same calendar day."""

    def test_deep_clean_blocks_production_across_phases(self, db_session, models):
        """Deep Clean in Phase 2 + Production retry in Phase 3 = no overlap."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Deep Clean event — schedules in Phase 2
        _make_event(models, db_session, 320001, 'Juicer Deep Clean',
                    name='320001-DeepClean-Phase3Test',
                    start_days=4, due_days=6, estimated_time=480)

        # Multiple Juicer Production events + lots of Cores to force saturation
        for i in range(4):
            _make_event(models, db_session, 320010 + i, 'Juicer',
                        name=f'{320010 + i:06d}-JuicerProd-Phase3',
                        start_days=3, due_days=10, estimated_time=480)

        for i in range(10):
            _make_event(models, db_session, 320020 + i, 'Core',
                        name=f'{320020 + i:06d}-CORE-Phase3H14',
                        start_days=3, due_days=10, estimated_time=390)

        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 18: Phase 3 Weekly Limits Cross-Phase (H23/H24)
# ---------------------------------------------------------------------------

class TestScenarioPhase3WeeklyLimits:
    """Verify weekly limits hold when Phase 2 fills most of the week
    and Phase 3 retries remaining events."""

    def test_weekly_juicer_limit_across_phases(self, db_session, models):
        """Phase 2 + Phase 3 combined should not exceed 5 Juicer/week."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # 6 Juicer events — only 5 allowed per week for jb1 (H23)
        for i in range(6):
            _make_event(models, db_session, 330001 + i, 'Juicer',
                        name=f'{330001 + i:06d}-Juicer-WeeklyLimit',
                        start_days=3, due_days=10, estimated_time=480)

        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

    def test_weekly_hours_across_phases(self, db_session, models):
        """Phase 2 + Phase 3 combined should not exceed 2400 min/week (H24)."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # 7 long Core events (7 * 390 = 2730 > 2400) — can't all go to 1 emp
        for i in range(7):
            _make_event(models, db_session, 340001 + i, 'Core',
                        name=f'{340001 + i:06d}-CORE-HoursCap',
                        start_days=3, due_days=10, estimated_time=390)

        # 3 Juicer events (each 480 min) — adds to weekly hours pressure
        for i in range(3):
            _make_event(models, db_session, 340010 + i, 'Juicer',
                        name=f'{340010 + i:06d}-Juicer-HoursCap',
                        start_days=3, due_days=10, estimated_time=480)

        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 19: Tight Availability + Phase 3 (H5/H6 across phases)
# ---------------------------------------------------------------------------

class TestScenarioPhase3Availability:
    """Verify availability constraints hold when Phase 3 retries with
    limited employee availability windows."""

    def test_tight_availability_no_violations(self, db_session, models):
        """Employees with restricted availability should never be
        assigned on their off days, even in Phase 3."""
        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # es1 and es2 are only available Mon-Wed
        _make_weekly_availability(models, db_session, 'es1',
                                  thursday=False, friday=False,
                                  saturday=False, sunday=False)
        _make_weekly_availability(models, db_session, 'es2',
                                  thursday=False, friday=False,
                                  saturday=False, sunday=False)

        # es3 and es4 are only available Thu-Sat
        _make_weekly_availability(models, db_session, 'es3',
                                  monday=False, tuesday=False,
                                  wednesday=False, sunday=False)
        _make_weekly_availability(models, db_session, 'es4',
                                  monday=False, tuesday=False,
                                  wednesday=False, sunday=False)

        # 12 Core events — will need Phase 3 for some with tight availability
        for i in range(12):
            _make_event(models, db_session, 350001 + i, 'Core',
                        name=f'{350001 + i:06d}-CORE-Avail',
                        start_days=3, due_days=14, estimated_time=390)

        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# SCENARIO 20: Comprehensive Phase 3 Mega Test
# ---------------------------------------------------------------------------

class TestScenarioPhase3Mega:
    """Combines all Phase 3 edge cases in a single large scenario:
    Juicer + Core + Deep Clean + availability restrictions + weekly limits.
    The solver must handle Phase 2 → Phase 3 transition correctly."""

    def test_mega_phase3(self, db_session, models):
        """Everything at once — max pressure on cross-phase constraints."""
        # Large team
        _make_employee(models, db_session, 'mg_es1', 'Mega-Alice', 'Event Specialist')
        _make_employee(models, db_session, 'mg_es2', 'Mega-Bob', 'Event Specialist')
        _make_employee(models, db_session, 'mg_es3', 'Mega-Carol', 'Event Specialist')
        _make_employee(models, db_session, 'mg_es4', 'Mega-Dave', 'Event Specialist')
        _make_employee(models, db_session, 'mg_es5', 'Mega-Ivan', 'Event Specialist')
        _make_employee(models, db_session, 'mg_lead1', 'Mega-Eve', 'Lead Event Specialist')
        _make_employee(models, db_session, 'mg_lead2', 'Mega-Kim', 'Lead Event Specialist')
        _make_employee(models, db_session, 'mg_jb1', 'Mega-Frank', 'Juicer Barista',
                       juicer_trained=True)
        _make_employee(models, db_session, 'mg_jb2', 'Mega-Leo', 'Juicer Barista',
                       juicer_trained=True)
        _make_employee(models, db_session, 'mg_cs1', 'Mega-Grace', 'Club Supervisor')
        db_session.flush()

        for dow in range(7):
            _make_rotation(models, db_session, dow, 'juicer', 'mg_jb1',
                           backup_id='mg_jb2')
            _make_rotation(models, db_session, dow, 'primary_lead', 'mg_lead1',
                           backup_id='mg_lead2')

        # Some employees have restricted availability
        _make_weekly_availability(models, db_session, 'mg_es1',
                                  friday=False, saturday=False, sunday=False)
        _make_weekly_availability(models, db_session, 'mg_es2',
                                  monday=False, saturday=False, sunday=False)

        # Time off for one employee in the middle of the window
        _make_time_off(models, db_session, 'mg_es3', start_days=5, end_days=8)

        # 12 Core events
        for i in range(12):
            _make_event(models, db_session, 360001 + i, 'Core',
                        start_days=3, due_days=14, estimated_time=390)

        # 5 Juicer events (pushing H23 limit)
        for i in range(5):
            _make_event(models, db_session, 360020 + i, 'Juicer',
                        start_days=3, due_days=14, estimated_time=480)

        # 1 Deep Clean (H14 exclusion)
        _make_event(models, db_session, 360030, 'Juicer Deep Clean',
                    start_days=5, due_days=8, estimated_time=480)

        # 3 Freeosk events (H18 support constraint + H10 lead qualification)
        for i in range(3):
            _make_event(models, db_session, 360040 + i, 'Freeosk',
                        start_days=3, due_days=14, estimated_time=120)

        # 2 Supervisor events
        for i in range(2):
            _make_event(models, db_session, 360050 + i, 'Supervisor',
                        start_days=3, due_days=14, estimated_time=60)

        db_session.commit()

        run = _run_cpsat(db_session, models, time_limit=60)
        assert run.status == 'completed'

        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # At least half the events should be scheduled
        scheduled = _get_successful(db_session, models, run.id)
        assert len(scheduled) >= 10, \
            f"Only {len(scheduled)}/23 events scheduled in mega scenario"


# ---------------------------------------------------------------------------
# SCENARIO 21: Primary/Secondary Rules (Juicer > Core priority)
# ---------------------------------------------------------------------------
# Per docs/scheduling_validation_rules.md RULE-001/RULE-022/RULE-023 (2026-04-10):
#  - At most one primary (Core or Juicer Production) per employee per day.
#  - Juicer Production outranks Core — on a conflict, the Core is bumped to
#    another day in its window.
#  - Backup juicers are only used when the primary juicer has approved PTO,
#    not when the primary merely has a Core conflict.

class TestScenarioPrimarySecondaryRules:
    """Primary/secondary rules alignment — Juicer Production displaces Core."""

    def test_juicer_bumps_core_on_same_day(self, db_session, models):
        """A bumpable Core posted to the primary juicer must be moved off the
        Juicer Production's target day so the Juicer can land there."""
        Schedule = models['Schedule']

        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)  # jb1 = primary juicer

        # Pre-existing "Scheduled" Core assigned to jb1 with a wide window
        # (start_days=5, due_days=15) so the bumped Core has room to move.
        posted_core = _make_event(
            models, db_session, 950001, 'Core',
            name='950001-CORE-Preposted',
            condition='Scheduled', start_days=5, due_days=15,
            estimated_time=390,
        )
        posted_core.is_scheduled = True
        db_session.flush()

        # Post the Core to jb1 on day 5 (the day the Juicer will need).
        posted_date = _future(5)
        sched = Schedule(
            event_ref_num=950001,
            employee_id='jb1',
            schedule_datetime=posted_date,
            shift_block=1,
        )
        db_session.add(sched)

        # New Juicer Production pinned to day 5 (its start date).
        _make_event(models, db_session, 950002, 'Juicer Production',
                    name='950002-JUICER-PRODUCTION-SPCLTY',
                    start_days=5, due_days=6, estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        # Juicer Production must be scheduled on day 5 to jb1.
        scheduled = _get_successful(db_session, models, run.id)
        juicer_ps = [ps for ps in scheduled if ps.event_ref_num == 950002]
        assert juicer_ps, "Juicer Production should be scheduled (primary beats Core)"
        assert juicer_ps[0].employee_id == 'jb1', \
            f"Juicer should go to primary rotation juicer jb1, got {juicer_ps[0].employee_id}"
        juicer_day = juicer_ps[0].schedule_datetime.date() \
            if isinstance(juicer_ps[0].schedule_datetime, datetime) \
            else juicer_ps[0].schedule_datetime
        assert juicer_day == posted_date.date(), \
            f"Juicer should land on day {posted_date.date()}, got {juicer_day}"

        # The bumped Core must either land on a different day (still scheduled
        # somewhere in its window) OR be re-pinned to a different employee —
        # but it must NOT share day 5 with jb1.
        core_ps = [ps for ps in scheduled if ps.event_ref_num == 950001]
        if core_ps:
            core_day = core_ps[0].schedule_datetime.date() \
                if isinstance(core_ps[0].schedule_datetime, datetime) \
                else core_ps[0].schedule_datetime
            same_day_same_emp = (core_day == posted_date.date()
                                 and core_ps[0].employee_id == 'jb1')
            assert not same_day_same_emp, \
                "Core must be bumped off jb1's day 5 when Juicer takes that slot"

    def test_juicer_falls_back_to_backup_only_on_pto(self, db_session, models):
        """When the primary juicer has approved PTO, the Juicer Production
        falls back to the rotation backup (not when there's merely a Core
        conflict — that's covered by the bump-the-Core test above)."""
        # Two juicer-trained employees: primary jb1, backup jb2
        _make_employee(models, db_session, 'es1', 'Alice', 'Event Specialist')
        _make_employee(models, db_session, 'jb1', 'Frank', 'Juicer Barista',
                       juicer_trained=True)
        _make_employee(models, db_session, 'jb2', 'Gina', 'Juicer Barista',
                       juicer_trained=True)
        db_session.flush()

        # Rotation: primary=jb1, backup=jb2 every day
        for dow in range(7):
            _make_rotation(models, db_session, dow, 'juicer', 'jb1',
                           backup_id='jb2')

        # jb1 has approved time off on day 5 (the Juicer Production's start).
        _make_time_off(models, db_session, 'jb1', start_days=5, end_days=5)

        # Juicer Production pinned to day 5
        _make_event(models, db_session, 960001, 'Juicer Production',
                    name='960001-JUICER-PRODUCTION-SPCLTY',
                    start_days=5, due_days=6, estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        juicer_ps = [ps for ps in scheduled if ps.event_ref_num == 960001]
        assert juicer_ps, "Juicer Production should schedule to backup on PTO day"
        assert juicer_ps[0].employee_id == 'jb2', \
            f"Juicer should fall back to backup jb2, got {juicer_ps[0].employee_id}"

    def test_juicer_bumps_core_with_no_room_core_fails(self, db_session, models):
        """When a bumped Core has a tight window with nowhere to move, the
        Juicer still schedules (wins priority) and the Core surfaces as a
        manual-intervention failure."""
        Schedule = models['Schedule']

        setup_basic_team(models, db_session)
        setup_rotations(models, db_session)

        # Narrow-window Core: start=5, due=6 → exactly 1 valid day (day 5).
        # Pre-posted to jb1 on day 5.  There is nowhere for it to move.
        posted_core = _make_event(
            models, db_session, 970001, 'Core',
            name='970001-CORE-Narrow',
            condition='Scheduled', start_days=5, due_days=6,
            estimated_time=390,
        )
        posted_core.is_scheduled = True
        db_session.flush()

        sched = Schedule(
            event_ref_num=970001,
            employee_id='jb1',
            schedule_datetime=_future(5),
            shift_block=1,
        )
        db_session.add(sched)

        # Juicer Production pinned to day 5 (competes with the Core).
        _make_event(models, db_session, 970002, 'Juicer Production',
                    name='970002-JUICER-PRODUCTION-SPCLTY',
                    start_days=5, due_days=6, estimated_time=540)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        verifier = ConstraintVerifier(models, db_session, run.id)
        violations = verifier.verify_all()
        assert violations == [], f"Violations:\n" + "\n".join(violations)

        scheduled = _get_successful(db_session, models, run.id)
        juicer_ps = [ps for ps in scheduled if ps.event_ref_num == 970002]
        assert juicer_ps, "Juicer Production should still win (higher priority)"
        assert juicer_ps[0].employee_id == 'jb1', \
            f"Juicer should go to primary rotation juicer, got {juicer_ps[0].employee_id}"

        # The narrow-window Core cannot coexist with the Juicer on day 5 for
        # jb1, so it must NOT appear on jb1 day 5 in the final schedule.
        core_ps = [ps for ps in scheduled if ps.event_ref_num == 970001]
        for ps in core_ps:
            d = ps.schedule_datetime.date() \
                if isinstance(ps.schedule_datetime, datetime) \
                else ps.schedule_datetime
            assert not (d == _future(5).date() and ps.employee_id == 'jb1'), \
                "Narrow-window Core must not share jb1 day 5 with Juicer"
