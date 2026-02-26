"""
CP-SAT Constraint-Programming Auto-Scheduler
=============================================

Replaces the greedy wave-based heuristic with Google OR-Tools CP-SAT solver
for globally optimal (or near-optimal) schedule generation.

The solver models all events, employees, days, and shift blocks as decision
variables, with hard constraints (must satisfy) and soft constraints
(objective penalties/bonuses). It finds the assignment that maximizes events
scheduled while respecting all business rules.

Usage:
    engine = CPSATSchedulingEngine(db_session, models)
    run = engine.run_auto_scheduler(run_type='manual')
"""

import logging
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from ortools.sat.python import cp_model

from app.constants import INACTIVE_CONDITIONS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Objective weights (tuned for business priority)
# ---------------------------------------------------------------------------
WEIGHT_UNSCHEDULED = 1000        # S1: Penalty per unscheduled event
WEIGHT_URGENCY = 10              # S2: Per-day urgency bonus multiplier
WEIGHT_TYPE_PRIORITY = 5         # S3: Per-priority-level bonus
WEIGHT_ROTATION = 50             # S4: Bonus for rotation employee match
WEIGHT_SUPERVISOR_MISUSE = 200   # S5: Penalty for Club Supervisor on wrong type (escalating)
WEIGHT_SUP_ASSIGNMENT = 20       # S6: Bonus for correct Supervisor assignment
WEIGHT_LEAD_BLOCK1 = 25          # S7: Bonus for Primary Lead on Block 1
WEIGHT_LEAD_DAILY = 20           # S8: Bonus for Primary Lead on Freeosk/Refresh
WEIGHT_FAIRNESS = 5              # S9: Penalty per imbalance unit
WEIGHT_JUICER_WEEKLY = 100       # S10: Penalty per over-limit Juicer event
WEIGHT_DUPLICATE_PRODUCT = 75    # S11: Penalty per duplicate product on day
WEIGHT_PROXIMITY = 15            # S12: Penalty per time-proximity violation
WEIGHT_SHIFT_BALANCE = 10        # S13: Penalty per imbalanced day
WEIGHT_BUMP = 200                # S14: Penalty per bumped existing schedule
WEIGHT_ML_AFFINITY = 8           # S15: Bonus for ML-predicted employee-event affinity

# ---------------------------------------------------------------------------
# Scheduling constants
# ---------------------------------------------------------------------------
SCHEDULING_WINDOW_DAYS = 3
MAX_CORE_EVENTS_PER_DAY = 1
MAX_CORE_EVENTS_PER_WEEK = 6
MAX_JUICER_PRODUCTION_PER_WEEK = 5
FULL_DAY_MINUTES = 480
MAX_WEEKLY_MINUTES = 2400               # 40 hours × 60 minutes
NUM_CORE_BLOCKS = 8

EVENT_TYPE_PRIORITY = {
    'Juicer': 1, 'Juicer Production': 1, 'Juicer Survey': 1,
    'Juicer Deep Clean': 1,
    'Digital Setup': 2, 'Digital Refresh': 3, 'Freeosk': 4,
    'Digital Teardown': 5, 'Core': 6, 'Supervisor': 7,
    'Digitals': 8, 'Other': 9,
}

# Job titles that qualify for specific event types
JUICER_TITLES = {'Juicer Barista', 'Club Supervisor'}
LEAD_TITLES = {'Lead Event Specialist', 'Club Supervisor'}
JUICER_EVENT_TYPES = {'Juicer', 'Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'}
LEAD_ONLY_EVENT_TYPES = {'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh',
                         'Digital Teardown', 'Other'}
SUPERVISOR_PREFERRED_TYPES = {'Supervisor', 'Digitals', 'Freeosk',
                              'Juicer', 'Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'}


class CPSATSchedulingEngine:
    """
    Constraint-programming scheduler using Google OR-Tools CP-SAT.

    Builds a model with decision variables for event-day, event-employee,
    and event-block assignments, adds hard constraints from business rules,
    and maximizes an objective that rewards scheduling events while
    penalizing constraint violations.
    """

    def __init__(self, db_session, models: dict):
        self.db = db_session
        self.models = models
        self.emergency_mode = False  # When True, reduces scheduling buffer to 0 days

        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.Employee = models['Employee']
        self.SchedulerRunHistory = models['SchedulerRunHistory']
        self.PendingSchedule = models['PendingSchedule']
        self.EmployeeTimeOff = models.get('EmployeeTimeOff')
        self.EmployeeWeeklyAvailability = models.get('EmployeeWeeklyAvailability')
        self.EmployeeAvailabilityOverride = models.get('EmployeeAvailabilityOverride')
        self.CompanyHoliday = models.get('CompanyHoliday')
        self.LockedDay = models.get('LockedDay')
        self.RotationAssignment = models.get('RotationAssignment')
        self.ScheduleException = models.get('ScheduleException')
        self.EventSchedulingOverride = models.get('EventSchedulingOverride')
        self.EventTypeOverride = models.get('EventTypeOverride')

        # Load time settings
        self._load_time_settings()

        # Load user preference multipliers from SystemSetting
        self.user_pref_multipliers = self._load_user_preferences()

    # ------------------------------------------------------------------
    # Time settings
    # ------------------------------------------------------------------

    def _load_time_settings(self):
        """Load event time settings and shift block configuration."""
        from app.services.event_time_settings import (
            get_freeosk_times, get_digital_setup_slots,
            get_supervisor_times, get_digital_teardown_slots, get_other_times,
        )
        from app.services.shift_block_config import ShiftBlockConfig

        try:
            self.shift_blocks = ShiftBlockConfig.get_all_blocks()
        except Exception:
            self.shift_blocks = []

        try:
            freeosk = get_freeosk_times()
            supervisor = get_supervisor_times()
            other_times = get_other_times()
            digital_setup_slots = get_digital_setup_slots()
            digital_teardown_slots = get_digital_teardown_slots()
        except Exception:
            freeosk = {'start': time(10, 0)}
            supervisor = {'start': time(12, 0)}
            other_times = {'start': time(11, 0)}
            digital_setup_slots = [{'start': time(10, 15)}]
            digital_teardown_slots = [{'start': time(17, 0)}]

        self.default_times = {
            'Juicer Production': time(9, 0),
            'Juicer Survey': time(17, 0),
            'Juicer': time(9, 0),
            'Juicer Deep Clean': time(9, 0),
            'Digital Setup': digital_setup_slots[0]['start'],
            'Digital Refresh': digital_setup_slots[0]['start'],
            'Freeosk': freeosk['start'],
            'Digital Teardown': digital_teardown_slots[0]['start'],
            'Core': self.shift_blocks[0]['arrive'] if self.shift_blocks else time(10, 15),
            'Supervisor': supervisor['start'],
            'Other': other_times['start'],
            'Digitals': digital_setup_slots[0]['start'],
        }

        # Build block arrive-time mapping: block_num -> time
        self.block_arrive_time = {}
        for b in self.shift_blocks:
            self.block_arrive_time[b['block']] = b['arrive']

    def _load_user_preferences(self):
        """
        Load scheduling preference multipliers from SystemSetting.
        These are set by the AI assistant's modify_scheduling_preference tool.

        Returns:
            dict mapping weight name (e.g. 'WEIGHT_FAIRNESS') to float multiplier
        """
        try:
            from app.services.constraint_modifier import ConstraintModifier
            modifier = ConstraintModifier()
            return modifier.get_multipliers()
        except Exception as e:
            logger.warning(f"Could not load user preferences: {e}")
            return {}

    def _get_effective_weight(self, base_weight, weight_name):
        """Apply user preference multiplier to a base weight."""
        multiplier = self.user_pref_multipliers.get(weight_name, 1.0)
        return int(base_weight * multiplier)

    def _get_ml_affinity_scores(self):
        """
        Get ML affinity scores for all (event, employee) pairs.
        Gated by ML_ENABLED config flag. Returns empty dict on failure.

        Returns:
            dict[(event_ref_num, employee_id)] -> float (0.0 to 1.0)
        """
        from flask import current_app
        config = current_app.config if current_app else {}

        if not config.get('ML_ENABLED', False):
            return {}

        try:
            from app.ml.inference.ml_scheduler_adapter import MLSchedulerAdapter
            adapter = MLSchedulerAdapter(self.db, self.models, config)

            scores = {}
            for event in self.events:
                ranked = adapter.rank_employees(
                    list(self.employees.values()),
                    event,
                    event.start_date if hasattr(event, 'start_date') else datetime.now()
                )
                for employee, score in ranked:
                    scores[(event.project_ref_num, employee.id)] = score

            logger.info(f"ML affinity: got {len(scores)} scores for "
                        f"{len(self.events)} events × {len(self.employees)} employees")
            return scores

        except Exception as e:
            logger.warning(f"ML affinity scoring failed (graceful fallback): {e}")
            return {}

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self):
        """Load all data needed for the solver into plain data structures."""
        from sqlalchemy import or_, and_

        today = date.today()
        buffer_days = 0 if self.emergency_mode else SCHEDULING_WINDOW_DAYS
        earliest = today + timedelta(days=buffer_days)
        horizon_end = today + timedelta(weeks=3)

        # --- Employees ---
        employees = self.Employee.query.filter(
            self.Employee.is_active == True,
            or_(
                self.Employee.termination_date.is_(None),
                self.Employee.termination_date > today,
            ),
        ).all()
        self.employees = {e.id: e for e in employees}
        self.employee_ids = list(self.employees.keys())

        # --- Events to schedule ---
        # Only unscheduled, active events within the scheduling horizon
        all_events = self.Event.query.filter(
            self.Event.is_scheduled == False,
            ~self.Event.condition.in_(list(INACTIVE_CONDITIONS)),
            self.Event.due_datetime > earliest,
            self.Event.start_datetime <= horizon_end,
        ).all()

        # Apply EventTypeOverride
        overrides = {}
        if self.EventTypeOverride:
            for ov in self.EventTypeOverride.query.all():
                overrides[ov.project_ref_num] = ov.override_event_type

        # Apply EventSchedulingOverride (skip events not allowed)
        skip_refs = set()
        if self.EventSchedulingOverride:
            for ov in self.EventSchedulingOverride.query.filter_by(allow_auto_schedule=False).all():
                skip_refs.add(ov.event_ref_num)

        self.events = []
        self.supervisor_events = []
        for e in all_events:
            if e.project_ref_num in skip_refs:
                continue
            # Apply type override
            if e.project_ref_num in overrides:
                e._override_event_type = overrides[e.project_ref_num]
            else:
                e._override_event_type = None
            etype = e._override_event_type or e.event_type

            if etype == 'Supervisor':
                self.supervisor_events.append(e)
            else:
                self.events.append(e)

        # Index supervisor events by 6-digit event number for pairing
        self.supervisor_by_number = {}
        for sup in self.supervisor_events:
            num = self._extract_event_number(sup.project_name)
            if num:
                self.supervisor_by_number[num] = sup

        # --- Valid days per event ---
        self.all_days = []
        d = earliest
        while d <= horizon_end:
            self.all_days.append(d)
            d += timedelta(days=1)

        # Pre-compute holiday set
        self.holiday_set = set()
        if self.CompanyHoliday:
            try:
                self.holiday_set = set(
                    self.CompanyHoliday.get_holidays_in_range(earliest, horizon_end)
                )
            except Exception:
                pass

        # Pre-compute locked day set
        self.locked_set = set()
        if self.LockedDay:
            for ld in self.LockedDay.query.all():
                self.locked_set.add(ld.locked_date)

        # Exclude holidays and locked days
        self.valid_days = [
            d for d in self.all_days
            if d not in self.holiday_set and d not in self.locked_set
        ]
        self.day_index = {d: i for i, d in enumerate(self.valid_days)}

        # --- Employee availability pre-computation ---
        self._precompute_availability()

        # --- Rotation assignments ---
        self._load_rotations()

        # --- Existing schedules (for bump penalty and conflict avoidance) ---
        self._load_existing_schedules()

        # --- Week boundaries (Sunday-Saturday) ---
        self._compute_weeks()

        # --- Existing Core counts for H11/H12 constraint adjustments ---
        self._compute_existing_core_counts()

        # --- Core-Supervisor pairing ---
        self._compute_pairings()

        # --- Eligible employees per event (domain filtering) ---
        self._compute_eligibility()

        # --- Product keys for duplicate-product penalty (S11/RULE-020) ---
        self._compute_product_groups()

    def _get_event_type(self, event):
        """Get effective event type considering overrides."""
        return getattr(event, '_override_event_type', None) or event.event_type

    def _extract_event_number(self, project_name):
        """Extract the unique event identifier from a project name.

        Uses the full parenthesized ref number (e.g. '(260115542007)') for precise matching.
        Falls back to first 6 digits only if no parenthesized number exists.
        """
        if not project_name:
            return None
        paren_match = re.search(r'\((\d{9,12})\)', project_name)
        if paren_match:
            return paren_match.group(1)
        match = re.search(r'(\d{6})', project_name)
        return match.group(1) if match else None

    def _extract_product_key(self, project_name):
        """Extract the brand/product key from a project name.

        Names follow the pattern: '{ref}-{Brand}-{Description} ({code}) - V{n}-TYPE'
        e.g. '619044-LKD-AF-CherryPistachSalad (251208539497) - V2-CORE'
        Returns the brand segment (e.g. 'LKD', 'CF', 'Trilliant').
        """
        if not project_name:
            return None
        # Strip the 6-digit ref number prefix
        stripped = re.sub(r'^\d{6,}-', '', project_name)
        if not stripped:
            return None
        # Take the first segment (brand) before the next hyphen or space
        match = re.match(r'([A-Za-z0-9]+)', stripped)
        return match.group(1).upper() if match else None

    def _precompute_availability(self):
        """Build a set of (employee_id, date) pairs where employee is UNAVAILABLE."""
        self.unavailable = set()  # (emp_id, date)

        # Weekly availability
        if self.EmployeeWeeklyAvailability:
            day_attrs = ['monday', 'tuesday', 'wednesday', 'thursday',
                         'friday', 'saturday', 'sunday']
            for wa in self.EmployeeWeeklyAvailability.query.all():
                for d in self.valid_days:
                    day_idx = d.weekday()  # 0=Mon, 6=Sun
                    if not getattr(wa, day_attrs[day_idx], True):
                        self.unavailable.add((wa.employee_id, d))

        # Availability overrides (takes priority over weekly)
        if self.EmployeeAvailabilityOverride:
            day_attrs = ['monday', 'tuesday', 'wednesday', 'thursday',
                         'friday', 'saturday', 'sunday']
            for ov in self.EmployeeAvailabilityOverride.query.all():
                for d in self.valid_days:
                    if ov.start_date <= d <= ov.end_date:
                        day_idx = d.weekday()
                        val = getattr(ov, day_attrs[day_idx], None)
                        if val is not None:
                            if val:
                                # Override says available — remove unavailability
                                self.unavailable.discard((ov.employee_id, d))
                            else:
                                # Override says unavailable
                                self.unavailable.add((ov.employee_id, d))

        # Time off
        # TODO Fix #3: When EmployeeTimeOff gains an 'approved' or 'status'
        # column, filter here: .filter_by(status='approved') or
        # .filter(EmployeeTimeOff.approved == True)
        if self.EmployeeTimeOff:
            for to in self.EmployeeTimeOff.query.all():
                # TODO Fix #2: When partial-day time-off is supported
                # (start_time/end_time fields), only block the employee for
                # events whose scheduled time overlaps the time-off window
                # instead of blocking the entire day.
                for d in self.valid_days:
                    if to.start_date <= d <= to.end_date:
                        self.unavailable.add((to.employee_id, d))

    def _load_rotations(self):
        """Load rotation assignments and exceptions into lookup dicts."""
        # rotation_lookup[(day_of_week, type)] -> (employee_id, backup_id)
        self.rotation_lookup = {}
        if self.RotationAssignment:
            for ra in self.RotationAssignment.query.all():
                self.rotation_lookup[(ra.day_of_week, ra.rotation_type)] = (
                    ra.employee_id, ra.backup_employee_id
                )

        # exception_lookup[(date, type)] -> employee_id
        self.exception_lookup = {}
        if self.ScheduleException:
            for se in self.ScheduleException.query.all():
                self.exception_lookup[(se.exception_date, se.rotation_type)] = se.employee_id

    def _get_rotation_employee(self, target_date, rotation_type):
        """Get rotation employee for a date, checking exceptions first."""
        d = target_date if isinstance(target_date, date) else target_date.date()
        # Check exception first
        exc_emp = self.exception_lookup.get((d, rotation_type))
        if exc_emp and exc_emp in self.employees:
            return exc_emp, None

        # Weekly rotation (day_of_week: 0=Mon in our model)
        dow = d.weekday()
        entry = self.rotation_lookup.get((dow, rotation_type))
        if entry:
            primary, backup = entry
            p = primary if primary in self.employees else None
            b = backup if backup and backup in self.employees else None
            return p, b
        return None, None

    def _load_existing_schedules(self):
        """Load existing (posted) schedules for bump penalty and conflict detection."""
        self.existing_schedules = []  # list of (event_ref_num, employee_id, date, block)
        self.existing_by_emp_day = defaultdict(list)  # (emp_id, date) -> [(event_ref, type)]

        for s in self.Schedule.query.all():
            if not s.schedule_datetime:
                continue
            sd = s.schedule_datetime.date() if isinstance(s.schedule_datetime, datetime) else s.schedule_datetime
            self.existing_schedules.append({
                'event_ref': s.event_ref_num,
                'employee_id': s.employee_id,
                'date': sd,
                'block': getattr(s, 'shift_block', None),
            })

            # Track by employee+day for conflict checks
            event = self.Event.query.filter_by(project_ref_num=s.event_ref_num).first()
            etype = event.event_type if event else 'Unknown'
            est_time = (event.estimated_time if event and event.estimated_time else 60)
            self.existing_by_emp_day[(s.employee_id, sd)].append({
                'event_ref': s.event_ref_num,
                'event_type': etype,
                'estimated_time': est_time,
            })

    def _compute_weeks(self):
        """Compute Sunday-Saturday week boundaries for valid days."""
        self.week_of_day = {}  # date -> week_index
        self.weeks = {}  # week_index -> list of dates

        if not self.valid_days:
            return

        # Find the Sunday at or before the first valid day
        first = self.valid_days[0]
        # weekday(): Mon=0 ... Sun=6. We want Sunday-Saturday weeks.
        # Days since last Sunday
        days_since_sunday = (first.weekday() + 1) % 7
        week_start = first - timedelta(days=days_since_sunday)

        week_idx = 0
        for d in self.valid_days:
            # Check if we've moved to a new week
            days_since = (d - week_start).days
            w = days_since // 7
            if w not in self.weeks:
                self.weeks[w] = []
            self.weeks[w].append(d)
            self.week_of_day[d] = w

        self.num_weeks = max(self.weeks.keys()) + 1 if self.weeks else 0

    def _compute_existing_core_counts(self):
        """Pre-compute existing event counts per employee per day/week.

        Tracks Core counts (for H11/H12), Juicer counts (for H22/H23),
        and total estimated minutes (for H24 weekly hours cap).
        """
        self.existing_core_count_by_emp_day = defaultdict(int)   # (emp_id, date) -> int
        self.existing_core_count_by_emp_week = defaultdict(int)  # (emp_id, week_idx) -> int
        self.existing_juicer_count_by_emp_day = defaultdict(int)
        self.existing_juicer_count_by_emp_week = defaultdict(int)
        self.existing_minutes_by_emp_week = defaultdict(int)

        # Compute week_start reference (same as _compute_weeks) so we can map
        # any date to a week index, not just valid_days.
        if not self.valid_days:
            return
        first = self.valid_days[0]
        days_since_sunday = (first.weekday() + 1) % 7
        week_start = first - timedelta(days=days_since_sunday)

        for (emp_id, day), entries in self.existing_by_emp_day.items():
            core_count = sum(1 for e in entries if e['event_type'] == 'Core')
            juicer_count = sum(1 for e in entries if e['event_type'] in JUICER_EVENT_TYPES)
            total_minutes = sum(e.get('estimated_time', 60) for e in entries)

            if core_count > 0:
                self.existing_core_count_by_emp_day[(emp_id, day)] = core_count
            if juicer_count > 0:
                self.existing_juicer_count_by_emp_day[(emp_id, day)] = juicer_count

            # Compute week index for this date using the same reference
            days_since = (day - week_start).days
            if days_since >= 0:
                week_idx = days_since // 7
                if week_idx in self.weeks:
                    if core_count > 0:
                        self.existing_core_count_by_emp_week[(emp_id, week_idx)] += core_count
                    if juicer_count > 0:
                        self.existing_juicer_count_by_emp_week[(emp_id, week_idx)] += juicer_count
                    self.existing_minutes_by_emp_week[(emp_id, week_idx)] += total_minutes

    def _compute_pairings(self):
        """Match Core events to their Supervisor events."""
        self.core_sup_pairs = {}  # core_event.id -> supervisor_event

        for event in self.events:
            etype = self._get_event_type(event)
            if etype != 'Core':
                continue
            num = self._extract_event_number(event.project_name)
            if num and num in self.supervisor_by_number:
                sup = self.supervisor_by_number[num]
                self.core_sup_pairs[event.id] = sup

        # Juicer Production-Survey pairing
        self.juicer_prod_survey_pairs = {}  # prod_event.id -> survey_event
        juicer_prods = [e for e in self.events
                        if self._get_event_type(e) == 'Juicer Production']
        juicer_surveys = [e for e in self.events
                          if self._get_event_type(e) == 'Juicer Survey']

        # Match by event number
        survey_by_num = {}
        for s in juicer_surveys:
            num = self._extract_event_number(s.project_name)
            if num:
                survey_by_num[num] = s

        for p in juicer_prods:
            num = self._extract_event_number(p.project_name)
            if num and num in survey_by_num:
                self.juicer_prod_survey_pairs[p.id] = survey_by_num[num]
                # Remove the survey from the main events list (handled via pairing)
                survey = survey_by_num[num]
                if survey in self.events:
                    self.events.remove(survey)

    def _compute_eligibility(self):
        """Pre-compute which employees can work each event type."""
        self.eligible_employees = {}  # event.id -> set of employee_ids

        for event in self.events:
            etype = self._get_event_type(event)
            eligible = set()

            for emp_id, emp in self.employees.items():
                if etype in JUICER_EVENT_TYPES:
                    if emp.job_title not in JUICER_TITLES and not emp.juicer_trained:
                        continue
                elif etype in LEAD_ONLY_EVENT_TYPES:
                    if emp.job_title not in LEAD_TITLES:
                        continue
                eligible.add(emp_id)

            self.eligible_employees[event.id] = eligible

        # Supervisor events: only Club Supervisor or Lead Event Specialist
        for sup in self.supervisor_events:
            eligible = set()
            for emp_id, emp in self.employees.items():
                if emp.job_title in ('Club Supervisor', 'Lead Event Specialist'):
                    eligible.add(emp_id)
            self.eligible_employees[sup.id] = eligible

    def _compute_product_groups(self):
        """Group events by product key for RULE-020 duplicate-product penalty.

        Only groups Core events since that's where duplicate products matter
        (support events are inherently tied to the same day as their base).
        """
        self.product_groups = defaultdict(list)  # product_key -> [event, ...]
        for event in self.events:
            if self._get_event_type(event) != 'Core':
                continue
            key = self._extract_product_key(event.project_name)
            if key:
                self.product_groups[key].append(event)

        # Only keep groups with 2+ events (no penalty for unique products)
        self.product_groups = {
            k: v for k, v in self.product_groups.items() if len(v) >= 2
        }

    def _valid_days_for_event(self, event):
        """Return list of valid days for a specific event."""
        today = date.today()
        buffer_days = 0 if self.emergency_mode else SCHEDULING_WINDOW_DAYS
        earliest = today + timedelta(days=buffer_days)

        e_start = event.start_datetime
        if isinstance(e_start, datetime):
            e_start = e_start.date()
        e_due = event.due_datetime
        if isinstance(e_due, datetime):
            e_due = e_due.date()

        start = max(e_start, earliest)
        return [d for d in self.valid_days if start <= d < e_due]

    # ------------------------------------------------------------------
    # Model building
    # ------------------------------------------------------------------

    def _build_model(self):
        """Build the CP-SAT model with all constraints and objective."""
        model = cp_model.CpModel()

        # ======== Decision Variables ========

        # assign_day[(event_id, day)] = BoolVar: event scheduled on day
        self.v_assign_day = {}
        # assign_emp[(event_id, emp_id)] = BoolVar: employee assigned to event
        self.v_assign_emp = {}
        # assign_block[(event_id, block)] = BoolVar: Core event gets block
        self.v_assign_block = {}
        # scheduled[event_id] = BoolVar: event is scheduled at all
        self.v_scheduled = {}

        # Variables for supervisor events (co-scheduled with Core)
        self.v_sup_day = {}
        self.v_sup_emp = {}
        self.v_sup_scheduled = {}

        for event in self.events:
            etype = self._get_event_type(event)
            eid = event.id
            valid_days = self._valid_days_for_event(event)

            if not valid_days:
                # No valid days — event can't be scheduled
                self.v_scheduled[eid] = model.NewConstant(0)
                continue

            eligible = self.eligible_employees.get(eid, set())
            if not eligible:
                self.v_scheduled[eid] = model.NewConstant(0)
                continue

            # Filter eligible employees by day availability
            valid_emp_days = set()
            for emp_id in eligible:
                for d in valid_days:
                    if (emp_id, d) not in self.unavailable:
                        valid_emp_days.add((emp_id, d))

            if not valid_emp_days:
                self.v_scheduled[eid] = model.NewConstant(0)
                continue

            # Create scheduled variable
            self.v_scheduled[eid] = model.NewBoolVar(f'sched_{eid}')

            # Day variables (only for valid days)
            for d in valid_days:
                self.v_assign_day[(eid, d)] = model.NewBoolVar(f'day_{eid}_{d}')

            # Employee variables (only for eligible employees)
            for emp_id in eligible:
                self.v_assign_emp[(eid, emp_id)] = model.NewBoolVar(f'emp_{eid}_{emp_id}')

            # Block variables (Core events only)
            if etype == 'Core':
                for b in range(1, NUM_CORE_BLOCKS + 1):
                    self.v_assign_block[(eid, b)] = model.NewBoolVar(f'blk_{eid}_{b}')

        # Supervisor variables — tied to Core events
        for core_id, sup_event in self.core_sup_pairs.items():
            sid = sup_event.id
            if core_id not in self.v_scheduled:
                continue
            # Supervisor scheduled iff Core is scheduled
            self.v_sup_scheduled[sid] = self.v_scheduled[core_id]

        # ======== Hard Constraints ========
        self._add_hard_constraints(model)

        # ======== Soft Constraints (Objective) ========
        self._add_objective(model)

        return model

    def _add_hard_constraints(self, model):
        """Add all hard constraints (H1-H21) to the model."""

        # H2: Exactly one day per scheduled event
        for event in self.events:
            eid = event.id
            if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                continue

            day_vars = [self.v_assign_day[(eid, d)]
                        for d in self._valid_days_for_event(event)
                        if (eid, d) in self.v_assign_day]

            if day_vars:
                model.Add(sum(day_vars) == self.v_scheduled[eid])
            else:
                model.Add(self.v_scheduled[eid] == 0)

        # H3: Exactly one employee per scheduled event
        for event in self.events:
            eid = event.id
            if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                continue

            eligible = self.eligible_employees.get(eid, set())
            emp_vars = [self.v_assign_emp[(eid, emp_id)]
                        for emp_id in eligible
                        if (eid, emp_id) in self.v_assign_emp]

            if emp_vars:
                model.Add(sum(emp_vars) == self.v_scheduled[eid])
            else:
                model.Add(self.v_scheduled[eid] == 0)

        # H4: Exactly one block per scheduled Core event
        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)
            if etype != 'Core':
                continue
            if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                continue

            block_vars = [self.v_assign_block[(eid, b)]
                          for b in range(1, NUM_CORE_BLOCKS + 1)
                          if (eid, b) in self.v_assign_block]

            if block_vars:
                model.Add(sum(block_vars) == self.v_scheduled[eid])

        # H5 + H6: Employee availability (pre-filtered via domain, but also
        # enforce that if emp is assigned, they must be available on the assigned day)
        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)
            if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                continue

            eligible = self.eligible_employees.get(eid, set())
            valid_days = self._valid_days_for_event(event)

            for emp_id in eligible:
                if (eid, emp_id) not in self.v_assign_emp:
                    continue
                for d in valid_days:
                    if (eid, d) not in self.v_assign_day:
                        continue
                    if (emp_id, d) in self.unavailable:
                        # If employee is on this day AND assigned to event,
                        # they can't both be true
                        # assign_emp[e, emp] + assign_day[e, d] <= 1
                        model.Add(
                            self.v_assign_emp[(eid, emp_id)] +
                            self.v_assign_day[(eid, d)] <= 1
                        )

        # H11: Max 1 Core event per employee per day
        core_events = [e for e in self.events if self._get_event_type(e) == 'Core']
        self._add_emp_day_limits(model, core_events, MAX_CORE_EVENTS_PER_DAY)

        # H12: Max 6 Core events per employee per week
        self._add_emp_week_limits(model, core_events, MAX_CORE_EVENTS_PER_WEEK)

        # H13: Juicer-Core mutual exclusion (same day, same employee)
        juicer_prod_events = [e for e in self.events
                              if self._get_event_type(e) in ('Juicer Production', 'Juicer')]
        self._add_mutual_exclusion_per_day(model, juicer_prod_events, core_events)

        # H22: Max 1 Juicer event per employee per day
        juicer_all_events = [e for e in self.events
                             if self._get_event_type(e) in JUICER_EVENT_TYPES]
        self._add_emp_day_limits(
            model, juicer_all_events, 1,
            existing_counts=self.existing_juicer_count_by_emp_day,
        )

        # H23: Max 5 Juicer events per employee per week (HARD — was soft S10)
        self._add_emp_week_limits(
            model, juicer_all_events, MAX_JUICER_PRODUCTION_PER_WEEK,
            existing_counts=self.existing_juicer_count_by_emp_week,
        )

        # H24: 40-hour weekly cap per employee
        self._add_weekly_hours_cap(model)

        # H14: Juicer Deep Clean and Production can't be on same calendar day
        deep_clean_events = [e for e in self.events
                             if self._get_event_type(e) == 'Juicer Deep Clean']
        self._add_day_exclusion(model, deep_clean_events, juicer_prod_events)

        # H16: Core-Supervisor pairing (same day)
        self._add_core_supervisor_pairing(model)

        # H17: Juicer Production-Survey pairing (same day, same employee)
        self._add_juicer_prod_survey_pairing(model)

        # H18: Support event requires base event (same day, same employee)
        self._add_support_requires_base(model)

        # H20: Full-day event exclusivity
        self._add_full_day_exclusivity(model)

        # H21: Shift block uniqueness per day (one employee per block per day)
        self._add_block_uniqueness(model)

        # Note (Fix #11): Block ordering (consecutive blocks for same employee)
        # is not needed because H11 limits Core to 1/employee/day. If that
        # limit is ever raised, add a constraint here enforcing block
        # contiguity (e.g. blocks {3,4} allowed but not {2,5}).

    def _add_emp_day_limits(self, model, typed_events, limit, existing_counts=None):
        """Limit events of a type per employee per day.

        Accounts for already-posted schedules so that if an employee already
        has `existing` events on a day, the solver can only assign
        `limit - existing` more (possibly zero).
        """
        if existing_counts is None:
            existing_counts = self.existing_core_count_by_emp_day
        for emp_id in self.employee_ids:
            for d in self.valid_days:
                existing = existing_counts.get((emp_id, d), 0)
                effective_limit = limit - existing

                indicators = []
                for event in typed_events:
                    eid = event.id
                    if (eid, emp_id) not in self.v_assign_emp:
                        continue
                    if (eid, d) not in self.v_assign_day:
                        continue
                    # Create indicator: event assigned to emp on day d
                    ind = model.NewBoolVar(f'ind_{eid}_{emp_id}_{d}')
                    model.AddBoolAnd([
                        self.v_assign_emp[(eid, emp_id)],
                        self.v_assign_day[(eid, d)]
                    ]).OnlyEnforceIf(ind)
                    model.AddBoolOr([
                        self.v_assign_emp[(eid, emp_id)].Not(),
                        self.v_assign_day[(eid, d)].Not()
                    ]).OnlyEnforceIf(ind.Not())
                    indicators.append(ind)

                if not indicators:
                    continue

                if effective_limit <= 0:
                    # Employee already at/over limit — forbid all new assignments
                    for ind in indicators:
                        model.Add(ind == 0)
                else:
                    model.Add(sum(indicators) <= effective_limit)

    def _add_emp_week_limits(self, model, typed_events, limit, existing_counts=None):
        """Limit events of a type per employee per week.

        Accounts for already-posted schedules so that if an employee already
        has `existing` events in a week, the solver can only assign
        `limit - existing` more.
        """
        if existing_counts is None:
            existing_counts = self.existing_core_count_by_emp_week
        for emp_id in self.employee_ids:
            for w_idx, week_days in self.weeks.items():
                existing = existing_counts.get((emp_id, w_idx), 0)
                effective_limit = limit - existing

                indicators = []
                for event in typed_events:
                    eid = event.id
                    if (eid, emp_id) not in self.v_assign_emp:
                        continue
                    for d in week_days:
                        if (eid, d) not in self.v_assign_day:
                            continue
                        ind = model.NewBoolVar(f'wk_{eid}_{emp_id}_{w_idx}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        indicators.append(ind)

                if not indicators:
                    continue

                if effective_limit <= 0:
                    for ind in indicators:
                        model.Add(ind == 0)
                else:
                    model.Add(sum(indicators) <= effective_limit)

    def _add_weekly_hours_cap(self, model):
        """H24: Total estimated work per employee per week <= 40 hours.

        Sums estimated_time (minutes) for every event assigned to an employee
        within a week, including already-posted schedules, and caps at
        MAX_WEEKLY_MINUTES.
        """
        for emp_id in self.employee_ids:
            for w_idx, week_days in self.weeks.items():
                existing_minutes = self.existing_minutes_by_emp_week.get(
                    (emp_id, w_idx), 0
                )
                remaining = MAX_WEEKLY_MINUTES - existing_minutes
                if remaining <= 0:
                    # Already at/over cap — forbid all new assignments this week
                    for event in self.events:
                        eid = event.id
                        if (eid, emp_id) not in self.v_assign_emp:
                            continue
                        for d in week_days:
                            if (eid, d) not in self.v_assign_day:
                                continue
                            ind = model.NewBoolVar(f'wh_{eid}_{emp_id}_{w_idx}_{d}')
                            model.AddBoolAnd([
                                self.v_assign_emp[(eid, emp_id)],
                                self.v_assign_day[(eid, d)]
                            ]).OnlyEnforceIf(ind)
                            model.AddBoolOr([
                                self.v_assign_emp[(eid, emp_id)].Not(),
                                self.v_assign_day[(eid, d)].Not()
                            ]).OnlyEnforceIf(ind.Not())
                            model.Add(ind == 0)
                    continue

                # Sum estimated_time × indicator for all events in this week
                time_terms = []
                for event in self.events:
                    eid = event.id
                    est = event.estimated_time or 60
                    if (eid, emp_id) not in self.v_assign_emp:
                        continue
                    for d in week_days:
                        if (eid, d) not in self.v_assign_day:
                            continue
                        ind = model.NewBoolVar(f'wh_{eid}_{emp_id}_{w_idx}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        time_terms.append(ind * est)

                if time_terms:
                    model.Add(sum(time_terms) <= remaining)

    def _add_mutual_exclusion_per_day(self, model, type_a_events, type_b_events):
        """H13: Two event types can't share the same employee on the same day."""
        for emp_id in self.employee_ids:
            for d in self.valid_days:
                a_inds = []
                for event in type_a_events:
                    eid = event.id
                    if (eid, emp_id) in self.v_assign_emp and (eid, d) in self.v_assign_day:
                        ind = model.NewBoolVar(f'mx_a_{eid}_{emp_id}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        a_inds.append(ind)

                b_inds = []
                for event in type_b_events:
                    eid = event.id
                    if (eid, emp_id) in self.v_assign_emp and (eid, d) in self.v_assign_day:
                        ind = model.NewBoolVar(f'mx_b_{eid}_{emp_id}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        b_inds.append(ind)

                if a_inds and b_inds:
                    has_a = model.NewBoolVar(f'has_a_{emp_id}_{d}')
                    has_b = model.NewBoolVar(f'has_b_{emp_id}_{d}')
                    model.AddMaxEquality(has_a, a_inds)
                    model.AddMaxEquality(has_b, b_inds)
                    model.Add(has_a + has_b <= 1)

    def _add_day_exclusion(self, model, type_a_events, type_b_events):
        """H14: Two event types can't share the same calendar day (global)."""
        for d in self.valid_days:
            a_vars = [self.v_assign_day[(e.id, d)]
                      for e in type_a_events if (e.id, d) in self.v_assign_day]
            b_vars = [self.v_assign_day[(e.id, d)]
                      for e in type_b_events if (e.id, d) in self.v_assign_day]

            if a_vars and b_vars:
                has_a = model.NewBoolVar(f'dc_a_{d}')
                has_b = model.NewBoolVar(f'dc_b_{d}')
                model.AddMaxEquality(has_a, a_vars)
                model.AddMaxEquality(has_b, b_vars)
                model.Add(has_a + has_b <= 1)

    def _add_core_supervisor_pairing(self, model):
        """H16: Core and Supervisor must be on the same day."""
        for core_id, sup_event in self.core_sup_pairs.items():
            core_event = None
            for e in self.events:
                if e.id == core_id:
                    core_event = e
                    break
            if not core_event:
                continue

            # For each valid day, supervisor is scheduled on d iff core is on d
            for d in self.valid_days:
                core_var = self.v_assign_day.get((core_id, d))
                # Supervisor follows core's day assignment — no separate day var needed
                # The supervisor's employee/time are derived from the core assignment

    def _add_juicer_prod_survey_pairing(self, model):
        """H17: Juicer Production and Survey must be same day, same employee."""
        for prod_id, survey_event in self.juicer_prod_survey_pairs.items():
            prod_event = None
            for e in self.events:
                if e.id == prod_id:
                    prod_event = e
                    break
            if not prod_event:
                continue

            # Survey is not in self.events (removed during pairing computation).
            # When production is scheduled, survey is implicitly scheduled
            # on the same day with the same employee. We just need to count it
            # for output. No separate variables needed.

    def _add_support_requires_base(self, model):
        """H18: Support events (Freeosk, Digital, etc.) require a base event
        (Core or Juicer) on the same day for the same employee.
        Exception: Club Supervisor is exempt."""
        support_types = {'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh',
                         'Digital Teardown'}
        base_types = {'Core', 'Juicer', 'Juicer Production'}

        support_events = [e for e in self.events if self._get_event_type(e) in support_types]
        base_events = [e for e in self.events if self._get_event_type(e) in base_types]

        if not support_events or not base_events:
            return

        for emp_id in self.employee_ids:
            emp = self.employees[emp_id]
            if emp.job_title == 'Club Supervisor':
                continue  # Exempt

            for d in self.valid_days:
                # Indicators for support events assigned to emp on d
                sup_inds = []
                for event in support_events:
                    eid = event.id
                    if (eid, emp_id) in self.v_assign_emp and (eid, d) in self.v_assign_day:
                        ind = model.NewBoolVar(f'sup_req_{eid}_{emp_id}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        sup_inds.append(ind)

                if not sup_inds:
                    continue

                # Indicators for base events assigned to emp on d
                base_inds = []
                for event in base_events:
                    eid = event.id
                    if (eid, emp_id) in self.v_assign_emp and (eid, d) in self.v_assign_day:
                        ind = model.NewBoolVar(f'base_{eid}_{emp_id}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        base_inds.append(ind)

                if not base_inds:
                    # No base events possible on this day for this employee
                    # → support events cannot be assigned
                    for ind in sup_inds:
                        model.Add(ind == 0)
                    continue

                # has_support => has_base
                has_support = model.NewBoolVar(f'has_sup_{emp_id}_{d}')
                model.AddMaxEquality(has_support, sup_inds)
                has_base = model.NewBoolVar(f'has_base_{emp_id}_{d}')
                model.AddMaxEquality(has_base, base_inds)
                model.AddImplication(has_support, has_base)

    def _add_full_day_exclusivity(self, model):
        """H20: Full-day events (>= 480 min) block Core/Juicer on same day."""
        full_day_events = [e for e in self.events
                           if e.estimated_time and e.estimated_time >= FULL_DAY_MINUTES]
        core_juicer_events = [e for e in self.events
                              if self._get_event_type(e) in ('Core', 'Juicer', 'Juicer Production')]

        if not full_day_events:
            return

        for emp_id in self.employee_ids:
            for d in self.valid_days:
                fd_inds = []
                for event in full_day_events:
                    eid = event.id
                    if (eid, emp_id) in self.v_assign_emp and (eid, d) in self.v_assign_day:
                        ind = model.NewBoolVar(f'fd_{eid}_{emp_id}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                        fd_inds.append(ind)

                if not fd_inds:
                    continue

                has_fd = model.NewBoolVar(f'has_fd_{emp_id}_{d}')
                model.AddMaxEquality(has_fd, fd_inds)

                # If has full-day, no OTHER Core/Juicer on same day
                fd_event_ids = {e.id for e in full_day_events}
                for event in core_juicer_events:
                    eid = event.id
                    if eid in fd_event_ids:
                        continue  # Don't block a full-day event against itself
                    if (eid, emp_id) in self.v_assign_emp and (eid, d) in self.v_assign_day:
                        cj_ind = model.NewBoolVar(f'cj_{eid}_{emp_id}_{d}')
                        model.AddBoolAnd([
                            self.v_assign_emp[(eid, emp_id)],
                            self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(cj_ind)
                        model.AddBoolOr([
                            self.v_assign_emp[(eid, emp_id)].Not(),
                            self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(cj_ind.Not())
                        model.Add(has_fd + cj_ind <= 1)

                # At most 1 full-day event per employee per day
                if len(fd_inds) > 1:
                    model.Add(sum(fd_inds) <= 1)

    def _add_block_uniqueness(self, model):
        """H21: Each block on a day can be assigned to at most one Core event."""
        core_events = [e for e in self.events if self._get_event_type(e) == 'Core']

        for d in self.valid_days:
            for b in range(1, NUM_CORE_BLOCKS + 1):
                # Collect all Core events that could use this block on this day
                block_users = []
                for event in core_events:
                    eid = event.id
                    if (eid, b) not in self.v_assign_block:
                        continue
                    if (eid, d) not in self.v_assign_day:
                        continue
                    # Indicator: event uses block b on day d
                    ind = model.NewBoolVar(f'bu_{eid}_{d}_{b}')
                    model.AddBoolAnd([
                        self.v_assign_block[(eid, b)],
                        self.v_assign_day[(eid, d)]
                    ]).OnlyEnforceIf(ind)
                    model.AddBoolOr([
                        self.v_assign_block[(eid, b)].Not(),
                        self.v_assign_day[(eid, d)].Not()
                    ]).OnlyEnforceIf(ind.Not())
                    block_users.append(ind)

                if len(block_users) > 1:
                    model.AddAtMostOne(block_users)

    # ------------------------------------------------------------------
    # Objective (soft constraints)
    # ------------------------------------------------------------------

    def _add_objective(self, model):
        """Build objective function from soft constraints S1-S15."""
        terms = []
        today = date.today()

        # S1: Maximize events scheduled (penalty for unscheduled)
        for event in self.events:
            eid = event.id
            if eid not in self.v_scheduled:
                continue
            svar = self.v_scheduled[eid]
            if isinstance(svar, int):
                continue
            # Reward scheduling
            terms.append(svar * self._get_effective_weight(WEIGHT_UNSCHEDULED, 'WEIGHT_UNSCHEDULED'))

        # S2: Due date urgency bonus
        for event in self.events:
            eid = event.id
            if eid not in self.v_scheduled:
                continue
            svar = self.v_scheduled[eid]
            if isinstance(svar, int):
                continue

            due = event.due_datetime
            if isinstance(due, datetime):
                due = due.date()
            days_until = (due - today).days
            max_days = 21  # 3-week horizon
            urgency = max(0, max_days - days_until)
            if urgency > 0:
                terms.append(svar * (self._get_effective_weight(WEIGHT_URGENCY, 'WEIGHT_URGENCY') * urgency))

        # S3: Event type priority bonus
        for event in self.events:
            eid = event.id
            if eid not in self.v_scheduled:
                continue
            svar = self.v_scheduled[eid]
            if isinstance(svar, int):
                continue

            etype = self._get_event_type(event)
            priority = EVENT_TYPE_PRIORITY.get(etype, 9)
            # Higher priority (lower number) = higher bonus
            bonus = (10 - priority) * WEIGHT_TYPE_PRIORITY
            if bonus > 0:
                terms.append(svar * bonus)

        # S4: Rotation compliance bonus
        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)
            if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                continue

            rot_type = None
            if etype in ('Juicer', 'Juicer Production'):
                rot_type = 'juicer'
            elif etype == 'Core':
                rot_type = 'primary_lead'

            if not rot_type:
                continue

            valid_days = self._valid_days_for_event(event)
            for d in valid_days:
                if (eid, d) not in self.v_assign_day:
                    continue
                primary, backup = self._get_rotation_employee(d, rot_type)
                if primary and (eid, primary) in self.v_assign_emp:
                    # Bonus if rotation employee is assigned AND event is on this day
                    ind = model.NewBoolVar(f'rot_{eid}_{d}_{primary}')
                    model.AddBoolAnd([
                        self.v_assign_emp[(eid, primary)],
                        self.v_assign_day[(eid, d)]
                    ]).OnlyEnforceIf(ind)
                    model.AddBoolOr([
                        self.v_assign_emp[(eid, primary)].Not(),
                        self.v_assign_day[(eid, d)].Not()
                    ]).OnlyEnforceIf(ind.Not())
                    terms.append(ind * self._get_effective_weight(WEIGHT_ROTATION, 'WEIGHT_ROTATION'))

                # Smaller bonus for backup rotation employee
                if backup and backup != primary and (eid, backup) in self.v_assign_emp:
                    ind_bk = model.NewBoolVar(f'rot_bk_{eid}_{d}_{backup}')
                    model.AddBoolAnd([
                        self.v_assign_emp[(eid, backup)],
                        self.v_assign_day[(eid, d)]
                    ]).OnlyEnforceIf(ind_bk)
                    model.AddBoolOr([
                        self.v_assign_emp[(eid, backup)].Not(),
                        self.v_assign_day[(eid, d)].Not()
                    ]).OnlyEnforceIf(ind_bk.Not())
                    terms.append(ind_bk * (self._get_effective_weight(WEIGHT_ROTATION, 'WEIGHT_ROTATION') // 2))

        # S5: Club Supervisor misuse penalty (escalating)
        # Tier k costs k × WEIGHT, so 1st misuse = -W, 2nd = -2W, 3rd = -3W, etc.
        club_sup_ids = [eid for eid, e in self.employees.items()
                        if e.job_title == 'Club Supervisor']
        for cs_id in club_sup_ids:
            misuse_vars = []
            for event in self.events:
                eid = event.id
                etype = self._get_event_type(event)
                if etype in SUPERVISOR_PREFERRED_TYPES:
                    continue
                if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                    continue
                if (eid, cs_id) in self.v_assign_emp:
                    misuse_vars.append(self.v_assign_emp[(eid, cs_id)])

            if not misuse_vars:
                continue

            count = model.NewIntVar(0, len(misuse_vars), f'cs_misuse_{cs_id}')
            model.Add(count == sum(misuse_vars))

            max_tiers = min(len(misuse_vars), 5)
            for k in range(1, max_tiers + 1):
                at_least_k = model.NewBoolVar(f'cs_tier_{cs_id}_{k}')
                model.Add(count >= k).OnlyEnforceIf(at_least_k)
                model.Add(count <= k - 1).OnlyEnforceIf(at_least_k.Not())
                terms.append(at_least_k * (-self._get_effective_weight(WEIGHT_SUPERVISOR_MISUSE, 'WEIGHT_SUPERVISOR_MISUSE') * k))

        # S7: Primary Lead gets Block 1
        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)
            if etype != 'Core':
                continue
            if (eid, 1) not in self.v_assign_block:
                continue

            valid_days = self._valid_days_for_event(event)
            for d in valid_days:
                if (eid, d) not in self.v_assign_day:
                    continue
                primary, _ = self._get_rotation_employee(d, 'primary_lead')
                if primary and (eid, primary) in self.v_assign_emp:
                    # Bonus if primary lead gets block 1 on this day
                    ind = model.NewBoolVar(f'lb1_{eid}_{d}')
                    model.AddBoolAnd([
                        self.v_assign_emp[(eid, primary)],
                        self.v_assign_day[(eid, d)],
                        self.v_assign_block[(eid, 1)]
                    ]).OnlyEnforceIf(ind)
                    # Relaxation: if any one is false, ind is 0
                    model.AddBoolOr([
                        self.v_assign_emp[(eid, primary)].Not(),
                        self.v_assign_day[(eid, d)].Not(),
                        self.v_assign_block[(eid, 1)].Not()
                    ]).OnlyEnforceIf(ind.Not())
                    terms.append(ind * WEIGHT_LEAD_BLOCK1)

        # S8: Primary Lead on Freeosk/Digital Refresh
        lead_daily_types = {'Freeosk', 'Digital Refresh'}
        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)
            if etype not in lead_daily_types:
                continue
            if eid not in self.v_scheduled or isinstance(self.v_scheduled[eid], int):
                continue

            valid_days = self._valid_days_for_event(event)
            for d in valid_days:
                if (eid, d) not in self.v_assign_day:
                    continue
                primary, _ = self._get_rotation_employee(d, 'primary_lead')
                if primary and (eid, primary) in self.v_assign_emp:
                    ind = model.NewBoolVar(f'ld_{eid}_{d}_{primary}')
                    model.AddBoolAnd([
                        self.v_assign_emp[(eid, primary)],
                        self.v_assign_day[(eid, d)]
                    ]).OnlyEnforceIf(ind)
                    model.AddBoolOr([
                        self.v_assign_emp[(eid, primary)].Not(),
                        self.v_assign_day[(eid, d)].Not()
                    ]).OnlyEnforceIf(ind.Not())
                    terms.append(ind * WEIGHT_LEAD_DAILY)

        # S9: Fairness — minimize max-min spread of Core assignments per employee
        core_events = [e for e in self.events if self._get_event_type(e) == 'Core']
        if core_events and len(self.employee_ids) > 1:
            emp_core_counts = {}
            core_eligible_emps = set()
            for emp_id in self.employee_ids:
                emp = self.employees[emp_id]
                # Only count employees who can work Core events
                if emp.job_title == 'Club Supervisor':
                    continue
                count_vars = []
                for event in core_events:
                    eid = event.id
                    if (eid, emp_id) in self.v_assign_emp:
                        count_vars.append(self.v_assign_emp[(eid, emp_id)])
                if count_vars:
                    emp_count = model.NewIntVar(0, len(core_events), f'cc_{emp_id}')
                    model.Add(emp_count == sum(count_vars))
                    emp_core_counts[emp_id] = emp_count
                    core_eligible_emps.add(emp_id)

            if len(emp_core_counts) >= 2:
                max_core = model.NewIntVar(0, len(core_events), 'max_core')
                min_core = model.NewIntVar(0, len(core_events), 'min_core')
                model.AddMaxEquality(max_core, list(emp_core_counts.values()))
                model.AddMinEquality(min_core, list(emp_core_counts.values()))
                spread = model.NewIntVar(0, len(core_events), 'core_spread')
                model.Add(spread == max_core - min_core)
                terms.append(spread * (-self._get_effective_weight(WEIGHT_FAIRNESS, 'WEIGHT_FAIRNESS')))

        # S10: Weekly Juicer Production limit (soft penalty for > 5)
        # Note: H23 now enforces this as a hard constraint. S10 remains as a
        # secondary signal but the hard constraint prevents actual violations.
        juicer_prod_events = [e for e in self.events
                              if self._get_event_type(e) in ('Juicer Production', 'Juicer')]
        if juicer_prod_events:
            for emp_id in self.employee_ids:
                for w_idx, week_days in self.weeks.items():
                    indicators = []
                    for event in juicer_prod_events:
                        eid = event.id
                        if (eid, emp_id) not in self.v_assign_emp:
                            continue
                        for d in week_days:
                            if (eid, d) not in self.v_assign_day:
                                continue
                            ind = model.NewBoolVar(f'jp_{eid}_{emp_id}_{w_idx}_{d}')
                            model.AddBoolAnd([
                                self.v_assign_emp[(eid, emp_id)],
                                self.v_assign_day[(eid, d)]
                            ]).OnlyEnforceIf(ind)
                            model.AddBoolOr([
                                self.v_assign_emp[(eid, emp_id)].Not(),
                                self.v_assign_day[(eid, d)].Not()
                            ]).OnlyEnforceIf(ind.Not())
                            indicators.append(ind)

                    if len(indicators) > MAX_JUICER_PRODUCTION_PER_WEEK:
                        excess = model.NewIntVar(
                            0, len(indicators), f'jp_excess_{emp_id}_{w_idx}'
                        )
                        model.Add(
                            excess >= sum(indicators) - MAX_JUICER_PRODUCTION_PER_WEEK
                        )
                        terms.append(excess * (-self._get_effective_weight(WEIGHT_JUICER_WEEKLY, 'WEIGHT_JUICER_WEEKLY')))

        # S11: Duplicate product penalty (RULE-020)
        # Penalize scheduling events from the same product/brand on the same day
        for product_key, group_events in self.product_groups.items():
            if len(group_events) < 2:
                continue
            for d in self.valid_days:
                # Collect indicators for "event is scheduled on this day"
                day_indicators = []
                for event in group_events:
                    eid = event.id
                    if (eid, d) not in self.v_assign_day:
                        continue
                    if eid not in self.v_scheduled:
                        continue
                    svar = self.v_scheduled[eid]
                    if isinstance(svar, int) and svar == 0:
                        continue
                    # Indicator: event is both scheduled and assigned to this day
                    ind = model.NewBoolVar(f'dp_{eid}_{d}')
                    if isinstance(svar, int):
                        # Constant 1 — always scheduled
                        model.Add(self.v_assign_day[(eid, d)] == 1).OnlyEnforceIf(ind)
                        model.Add(self.v_assign_day[(eid, d)] == 0).OnlyEnforceIf(ind.Not())
                    else:
                        model.AddBoolAnd([
                            svar, self.v_assign_day[(eid, d)]
                        ]).OnlyEnforceIf(ind)
                        model.AddBoolOr([
                            svar.Not(), self.v_assign_day[(eid, d)].Not()
                        ]).OnlyEnforceIf(ind.Not())
                    day_indicators.append(ind)

                if len(day_indicators) >= 2:
                    # Penalty for each event beyond the first on this day
                    excess = model.NewIntVar(
                        0, len(day_indicators), f'dp_excess_{product_key}_{d}'
                    )
                    model.Add(excess >= sum(day_indicators) - 1)
                    terms.append(excess * (-self._get_effective_weight(WEIGHT_DUPLICATE_PRODUCT, 'WEIGHT_DUPLICATE_PRODUCT')))

        # S13: Daily shift balance — penalize uneven event distribution across days
        for w_idx, week_days in self.weeks.items():
            if len(week_days) < 2:
                continue
            day_counts = {}
            for d in week_days:
                day_vars = []
                for event in self.events:
                    eid = event.id
                    if (eid, d) in self.v_assign_day:
                        day_vars.append(self.v_assign_day[(eid, d)])
                if day_vars:
                    dc = model.NewIntVar(0, len(self.events), f'dc_{w_idx}_{d}')
                    model.Add(dc == sum(day_vars))
                    day_counts[d] = dc

            if len(day_counts) >= 2:
                max_day = model.NewIntVar(0, len(self.events), f'max_day_{w_idx}')
                min_day = model.NewIntVar(0, len(self.events), f'min_day_{w_idx}')
                model.AddMaxEquality(max_day, list(day_counts.values()))
                model.AddMinEquality(min_day, list(day_counts.values()))
                spread = model.NewIntVar(0, len(self.events), f'day_spread_{w_idx}')
                model.Add(spread == max_day - min_day)
                terms.append(spread * (-self._get_effective_weight(WEIGHT_SHIFT_BALANCE, 'WEIGHT_SHIFT_BALANCE')))

        # S14: Minimize bumps of existing schedules
        for existing in self.existing_schedules:
            eref = existing['event_ref']
            emp_id = existing['employee_id']
            sd = existing['date']

            # Find the event in our model
            matched_event = None
            for event in self.events:
                if event.project_ref_num == eref:
                    matched_event = event
                    break
            if not matched_event:
                continue

            eid = matched_event.id
            if (eid, sd) in self.v_assign_day and (eid, emp_id) in self.v_assign_emp:
                # Bonus for keeping existing assignment
                kept = model.NewBoolVar(f'kept_{eid}_{emp_id}_{sd}')
                model.AddBoolAnd([
                    self.v_assign_day[(eid, sd)],
                    self.v_assign_emp[(eid, emp_id)]
                ]).OnlyEnforceIf(kept)
                model.AddBoolOr([
                    self.v_assign_day[(eid, sd)].Not(),
                    self.v_assign_emp[(eid, emp_id)].Not()
                ]).OnlyEnforceIf(kept.Not())
                terms.append(kept * self._get_effective_weight(WEIGHT_BUMP, 'WEIGHT_BUMP'))

        # S15: ML affinity bonus — nudge assignments toward ML-predicted matches
        affinity_scores = self._get_ml_affinity_scores()
        if affinity_scores:
            ml_weight = self._get_effective_weight(WEIGHT_ML_AFFINITY, 'WEIGHT_ML_AFFINITY')
            for (eid, emp_id), score in affinity_scores.items():
                key = (eid, emp_id)
                if key in self.v_assign_emp:
                    weight = int(score * ml_weight)
                    if weight > 0:
                        terms.append(self.v_assign_emp[key] * weight)

        # Final objective: maximize
        if terms:
            model.Maximize(sum(terms))

    # ------------------------------------------------------------------
    # Solver execution
    # ------------------------------------------------------------------

    def _solve(self, model, time_limit_seconds=60):
        """Run the CP-SAT solver and return status."""
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.num_workers = 4
        solver.parameters.log_search_progress = False

        status = solver.Solve(model)
        return solver, status

    # ------------------------------------------------------------------
    # Solution extraction
    # ------------------------------------------------------------------

    def _extract_solution(self, solver, run):
        """Extract solved assignments and create PendingSchedule records."""
        scheduled_count = 0
        failed_count = 0
        swap_count = 0

        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)

            svar = self.v_scheduled.get(eid)
            if svar is None or isinstance(svar, int):
                # Event couldn't be scheduled (no valid days/employees)
                self._create_pending_failure(run, event, "No valid days or eligible employees")
                failed_count += 1
                continue

            if solver.Value(svar) == 0:
                self._create_pending_failure(run, event, "Solver could not schedule within constraints")
                failed_count += 1
                continue

            # Find assigned day
            assigned_day = None
            for d in self._valid_days_for_event(event):
                if (eid, d) in self.v_assign_day and solver.Value(self.v_assign_day[(eid, d)]):
                    assigned_day = d
                    break

            # Find assigned employee
            assigned_emp = None
            eligible = self.eligible_employees.get(eid, set())
            for emp_id in eligible:
                if (eid, emp_id) in self.v_assign_emp and solver.Value(self.v_assign_emp[(eid, emp_id)]):
                    assigned_emp = emp_id
                    break

            if not assigned_day or not assigned_emp:
                self._create_pending_failure(run, event, "Solution extraction failed")
                failed_count += 1
                continue

            # Find assigned block (Core events only)
            assigned_block = None
            if etype == 'Core':
                for b in range(1, NUM_CORE_BLOCKS + 1):
                    if (eid, b) in self.v_assign_block and solver.Value(self.v_assign_block[(eid, b)]):
                        assigned_block = b
                        break

            # Determine schedule time
            schedule_time = self._get_schedule_time(event, etype, assigned_block)
            schedule_dt = datetime.combine(assigned_day, schedule_time)

            # Check if this bumps an existing schedule
            is_swap = False
            bumped_ref = None
            bumped_posted_id = None
            for existing in self.existing_schedules:
                if existing['event_ref'] == event.project_ref_num:
                    if existing['date'] != assigned_day or existing['employee_id'] != assigned_emp:
                        is_swap = True
                        bumped_ref = existing['event_ref']
                        break

            if is_swap:
                swap_count += 1

            self._create_pending_schedule(
                run, event, assigned_emp, schedule_dt,
                is_swap=is_swap,
                bumped_event_ref_num=bumped_ref,
                shift_block=assigned_block,
            )
            scheduled_count += 1

            # Handle paired Supervisor event
            if etype == 'Core' and eid in self.core_sup_pairs:
                sup_event = self.core_sup_pairs[eid]
                sup_time = self.default_times.get('Supervisor', time(12, 0))
                sup_dt = datetime.combine(assigned_day, sup_time)

                # Find the right employee: Club Supervisor first, then Primary Lead
                sup_emp = self._find_supervisor_employee(assigned_day, sup_dt)
                if sup_emp:
                    self._create_pending_schedule(
                        run, sup_event, sup_emp, sup_dt,
                    )
                    scheduled_count += 1
                else:
                    self._create_pending_failure(
                        run, sup_event,
                        "No Club Supervisor or Lead Event Specialist available"
                    )
                    failed_count += 1

            # Handle paired Juicer Survey
            if eid in self.juicer_prod_survey_pairs:
                survey_event = self.juicer_prod_survey_pairs[eid]
                survey_time = self.default_times.get('Juicer Survey', time(17, 0))
                survey_dt = datetime.combine(assigned_day, survey_time)
                self._create_pending_schedule(
                    run, survey_event, assigned_emp, survey_dt,
                )
                scheduled_count += 1

        return scheduled_count, failed_count, swap_count

    def _find_supervisor_employee(self, assigned_day, sup_dt):
        """Find the best employee for a Supervisor event.

        Priority:
        1. Club Supervisor (if available on the day)
        2. Primary Lead Event Specialist from rotation (if available)
        3. Any Lead Event Specialist (if available)

        Note: Time conflicts at noon are ignored for Supervisor events
        (multiple Supervisor events can stack at noon).
        """
        # 1. Try Club Supervisor first
        for emp_id, emp in self.employees.items():
            if emp.job_title == 'Club Supervisor':
                if (emp_id, assigned_day) not in self.unavailable:
                    return emp_id

        # 2. Try Primary Lead from rotation assignments
        primary, backup = self._get_rotation_employee(assigned_day, 'primary_lead')
        if primary and (primary, assigned_day) not in self.unavailable:
            emp = self.employees.get(primary)
            if emp and emp.job_title == 'Lead Event Specialist':
                return primary
        if backup and (backup, assigned_day) not in self.unavailable:
            emp = self.employees.get(backup)
            if emp and emp.job_title == 'Lead Event Specialist':
                return backup

        # 3. Fallback: any available Lead Event Specialist
        for emp_id, emp in self.employees.items():
            if emp.job_title == 'Lead Event Specialist':
                if (emp_id, assigned_day) not in self.unavailable:
                    return emp_id

        return None

    def _get_schedule_time(self, event, etype, block=None):
        """Determine the schedule time for an event based on type and block."""
        if etype == 'Core' and block and block in self.block_arrive_time:
            return self.block_arrive_time[block]

        return self.default_times.get(etype, time(11, 0))

    def _post_solve_review(self, run):
        """Defensive post-solve review to catch any remaining Core double-bookings.

        Runs after _extract_solution() and before commit. Scans all proposed
        PendingSchedule records for this run and removes violations:
          1. Same-run duplicates: 2+ Core events for same (emp, day) in this run
          2. Cross-run conflicts: new Core conflicts with an existing posted Schedule
          3. Weekly excess: total Core count (new + existing) exceeds weekly limit

        Removed assignments get failure_reason set, employee/datetime cleared.
        Returns count of removed assignments.
        """
        removed = 0

        # Gather all proposed (non-failed) PendingSchedules from this run
        pending = self.PendingSchedule.query.filter_by(
            scheduler_run_id=run.id,
        ).filter(
            self.PendingSchedule.employee_id.isnot(None),
            self.PendingSchedule.schedule_datetime.isnot(None),
        ).all()

        # Resolve event types for each pending schedule
        event_type_cache = {}
        for ps in pending:
            if ps.event_ref_num not in event_type_cache:
                event = self.Event.query.filter_by(project_ref_num=ps.event_ref_num).first()
                event_type_cache[ps.event_ref_num] = event.event_type if event else 'Unknown'

        core_pending = [ps for ps in pending if event_type_cache.get(ps.event_ref_num) == 'Core']

        # --- Check 1: Same-run duplicates (2+ Core for same emp+day) ---
        emp_day_cores = defaultdict(list)
        for ps in core_pending:
            sd = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
            emp_day_cores[(ps.employee_id, sd)].append(ps)

        for (emp_id, day), ps_list in emp_day_cores.items():
            if len(ps_list) <= MAX_CORE_EVENTS_PER_DAY:
                continue
            # Keep first (highest priority by insertion order), remove rest
            for ps in ps_list[MAX_CORE_EVENTS_PER_DAY:]:
                logger.warning(
                    f"POST-REVIEW: Removing same-run duplicate Core for "
                    f"employee={emp_id} day={day} event={ps.event_ref_num}"
                )
                ps.failure_reason = (
                    f"Post-review: duplicate Core on {day} (same run). "
                    f"Limit is {MAX_CORE_EVENTS_PER_DAY} per day."
                )
                ps.employee_id = None
                ps.schedule_datetime = None
                ps.schedule_time = None
                removed += 1

        # Refresh core_pending to exclude just-removed ones
        core_pending = [ps for ps in core_pending if ps.employee_id is not None]

        # --- Check 2: Cross-run conflicts with posted schedules ---
        for ps in list(core_pending):
            sd = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
            existing_count = self.existing_core_count_by_emp_day.get((ps.employee_id, sd), 0)
            # Count how many new Core events for this emp+day are still alive (before this one)
            new_count = sum(
                1 for other in core_pending
                if other.employee_id == ps.employee_id
                and other is not ps
                and (other.schedule_datetime.date() if isinstance(other.schedule_datetime, datetime) else other.schedule_datetime) == sd
            )
            # This pending + others already counted + existing
            total = existing_count + new_count + 1
            if total > MAX_CORE_EVENTS_PER_DAY:
                logger.warning(
                    f"POST-REVIEW: Removing cross-run conflict Core for "
                    f"employee={ps.employee_id} day={sd} event={ps.event_ref_num} "
                    f"(existing={existing_count}, new={new_count + 1})"
                )
                ps.failure_reason = (
                    f"Post-review: conflicts with {existing_count} existing posted "
                    f"Core event(s) on {sd}. Limit is {MAX_CORE_EVENTS_PER_DAY} per day."
                )
                ps.employee_id = None
                ps.schedule_datetime = None
                ps.schedule_time = None
                core_pending.remove(ps)
                removed += 1

        # --- Check 3: Weekly excess ---
        emp_week_new_cores = defaultdict(list)
        for ps in core_pending:
            sd = ps.schedule_datetime.date() if isinstance(ps.schedule_datetime, datetime) else ps.schedule_datetime
            week_idx = self.week_of_day.get(sd)
            if week_idx is not None:
                emp_week_new_cores[(ps.employee_id, week_idx)].append(ps)

        for (emp_id, week_idx), ps_list in emp_week_new_cores.items():
            existing_week = self.existing_core_count_by_emp_week.get((emp_id, week_idx), 0)
            total = existing_week + len(ps_list)
            if total > MAX_CORE_EVENTS_PER_WEEK:
                excess = total - MAX_CORE_EVENTS_PER_WEEK
                # Remove from the end (lower priority by insertion order)
                for ps in ps_list[-excess:]:
                    logger.warning(
                        f"POST-REVIEW: Removing weekly excess Core for "
                        f"employee={emp_id} week={week_idx} event={ps.event_ref_num}"
                    )
                    ps.failure_reason = (
                        f"Post-review: weekly Core limit exceeded "
                        f"(existing={existing_week}, new={len(ps_list)}, "
                        f"limit={MAX_CORE_EVENTS_PER_WEEK})"
                    )
                    ps.employee_id = None
                    ps.schedule_datetime = None
                    ps.schedule_time = None
                    removed += 1

        return removed

    def _log_solution_explanations(self, solver):
        """Post-solve explainability: log why each assignment was made.

        Examines solver variable values to explain:
        - Why a specific employee was chosen (rotation, only eligible, best fit)
        - Why a specific day was chosen (only valid day, closest to due date)
        - Why an event failed to schedule (no employees, constraint blocked)
        """
        explanations = []

        for event in self.events:
            eid = event.id
            etype = self._get_event_type(event)
            svar = self.v_scheduled.get(eid)

            if svar is None or isinstance(svar, int):
                reasons = []
                eligible = self.eligible_employees.get(eid, set())
                valid_days = self._valid_days_for_event(event)
                if not valid_days:
                    reasons.append("no valid days in scheduling window")
                if not eligible:
                    reasons.append(f"no eligible employees for {etype}")
                explanations.append(
                    f"  SKIP {etype} ref={event.project_ref_num}: "
                    f"{'; '.join(reasons) or 'pre-filtered'}"
                )
                continue

            if solver.Value(svar) == 0:
                # Analyze why it couldn't be scheduled
                eligible = self.eligible_employees.get(eid, set())
                valid_days = self._valid_days_for_event(event)
                available_combos = sum(
                    1 for e in eligible for d in valid_days
                    if (e, d) not in self.unavailable
                )
                explanations.append(
                    f"  FAIL {etype} ref={event.project_ref_num}: "
                    f"solver rejected ({len(eligible)} eligible employees, "
                    f"{len(valid_days)} valid days, {available_combos} combos) "
                    f"— blocked by hard constraints"
                )
                continue

            # Find assigned day and employee
            assigned_day = None
            for d in self._valid_days_for_event(event):
                if (eid, d) in self.v_assign_day and solver.Value(self.v_assign_day[(eid, d)]):
                    assigned_day = d
                    break

            assigned_emp = None
            eligible = self.eligible_employees.get(eid, set())
            for emp_id in eligible:
                if (eid, emp_id) in self.v_assign_emp and solver.Value(self.v_assign_emp[(eid, emp_id)]):
                    assigned_emp = emp_id
                    break

            if not assigned_day or not assigned_emp:
                continue

            # Explain employee choice
            emp_reasons = []
            emp = self.employees.get(assigned_emp)
            emp_name = emp.name if emp else assigned_emp

            # Check rotation match
            rot_type = None
            if etype in ('Juicer', 'Juicer Production'):
                rot_type = 'juicer'
            elif etype == 'Core':
                rot_type = 'primary_lead'
            if rot_type:
                primary, backup = self._get_rotation_employee(assigned_day, rot_type)
                if assigned_emp == primary:
                    emp_reasons.append("rotation primary")
                elif assigned_emp == backup:
                    emp_reasons.append("rotation backup")

            if len(eligible) == 1:
                emp_reasons.append("only eligible employee")

            # Explain day choice
            valid_days = self._valid_days_for_event(event)
            day_reason = ""
            if len(valid_days) == 1:
                day_reason = " (only valid day)"

            block_str = ""
            if etype == 'Core':
                for b in range(1, NUM_CORE_BLOCKS + 1):
                    if (eid, b) in self.v_assign_block and solver.Value(self.v_assign_block[(eid, b)]):
                        block_str = f" block={b}"
                        break

            explanations.append(
                f"  OK   {etype} ref={event.project_ref_num} -> "
                f"{emp_name} on {assigned_day}{day_reason}{block_str}"
                f"{' [' + ', '.join(emp_reasons) + ']' if emp_reasons else ''}"
            )

        if explanations:
            logger.info(
                f"CP-SAT Solution Explanations ({len(explanations)} events):\n"
                + "\n".join(explanations)
            )

    def _create_pending_schedule(self, run, event, employee_id, schedule_dt,
                                  is_swap=False, bumped_event_ref_num=None,
                                  swap_reason=None, shift_block=None):
        """Create a PendingSchedule record."""
        ps = self.PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=event.project_ref_num,
            employee_id=employee_id,
            schedule_datetime=schedule_dt,
            schedule_time=schedule_dt.time() if schedule_dt else None,
            status='proposed',
            is_swap=is_swap,
            bumped_event_ref_num=bumped_event_ref_num,
            swap_reason=swap_reason or ('CP-SAT solver reassignment' if is_swap else None),
        )
        self.db.add(ps)
        return ps

    def _create_pending_failure(self, run, event, reason):
        """Create a PendingSchedule failure record."""
        ps = self.PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=event.project_ref_num,
            employee_id=None,
            schedule_datetime=None,
            schedule_time=None,
            status='proposed',
            failure_reason=reason,
        )
        self.db.add(ps)
        return ps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_auto_scheduler(self, run_type='manual', time_limit_seconds=60):
        """
        Run the CP-SAT auto-scheduler.

        Args:
            run_type: 'manual' or 'automatic'
            time_limit_seconds: Maximum solver time (default 60s)

        Returns:
            SchedulerRunHistory record with results
        """
        # Create run history record
        run = self.SchedulerRunHistory(
            run_type=run_type,
            status='running',
            solver_type='cpsat',
        )
        self.db.add(run)
        self.db.flush()

        try:
            logger.info("CP-SAT Scheduler: Loading data...")
            self._load_data()

            total_events = len(self.events)
            # Count paired events that will also be scheduled
            paired_sup = len(self.core_sup_pairs)
            paired_survey = len(self.juicer_prod_survey_pairs)

            logger.info(
                f"CP-SAT Scheduler: {total_events} events to schedule, "
                f"{len(self.employee_ids)} employees, "
                f"{len(self.valid_days)} valid days, "
                f"{paired_sup} Core-Supervisor pairs, "
                f"{paired_survey} Juicer Prod-Survey pairs"
            )

            if total_events == 0:
                run.status = 'completed'
                run.completed_at = datetime.utcnow()
                run.total_events_processed = 0
                run.events_scheduled = 0
                run.events_failed = 0
                run.events_requiring_swaps = 0
                self.db.commit()
                return run

            logger.info("CP-SAT Scheduler: Building model...")
            model = self._build_model()

            logger.info(f"CP-SAT Scheduler: Solving (time limit: {time_limit_seconds}s)...")
            solver, status = self._solve(model, time_limit_seconds)

            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                quality = "optimal" if status == cp_model.OPTIMAL else "feasible"
                logger.info(
                    f"CP-SAT Scheduler: Solution found ({quality}), "
                    f"objective={solver.ObjectiveValue():.0f}"
                )

                scheduled, failed, swaps = self._extract_solution(solver, run)

                # Post-solve explainability logging
                self._log_solution_explanations(solver)

                # Post-solve validation: catch any remaining double-bookings
                removed = self._post_solve_review(run)
                if removed > 0:
                    scheduled -= removed
                    failed += removed
                    logger.info(f"CP-SAT post-review: removed {removed} duplicate/excess assignments")

                run.status = 'completed'
                run.completed_at = datetime.utcnow()
                run.total_events_processed = total_events + paired_sup + paired_survey
                run.events_scheduled = scheduled
                run.events_failed = failed
                run.events_requiring_swaps = swaps
                self.db.commit()

                logger.info(
                    f"CP-SAT Scheduler: Done. Scheduled={scheduled}, "
                    f"Failed={failed}, Swaps={swaps}"
                )

            elif status == cp_model.INFEASIBLE:
                logger.warning("CP-SAT Scheduler: Model is infeasible — no valid solution exists")
                run.status = 'failed'
                run.completed_at = datetime.utcnow()
                run.error_message = 'CP-SAT solver found the model infeasible. Constraints may be too restrictive.'
                run.total_events_processed = total_events
                run.events_scheduled = 0
                run.events_failed = total_events
                run.events_requiring_swaps = 0
                self.db.commit()

            else:
                logger.warning(f"CP-SAT Scheduler: Solver returned status {status}")
                run.status = 'failed'
                run.completed_at = datetime.utcnow()
                run.error_message = f'CP-SAT solver did not find a solution (status: {status})'
                run.total_events_processed = total_events
                run.events_scheduled = 0
                run.events_failed = total_events
                run.events_requiring_swaps = 0
                self.db.commit()

        except Exception as e:
            logger.exception(f"CP-SAT Scheduler: Error - {e}")
            run.status = 'crashed'
            run.completed_at = datetime.utcnow()
            run.error_message = str(e)
            run.total_events_processed = 0
            run.events_scheduled = 0
            run.events_failed = 0
            run.events_requiring_swaps = 0
            self.db.commit()
            raise

        return run
