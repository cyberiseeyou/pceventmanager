"""Per-run caches and helpers for the greedy scheduler.

The scheduler makes many repeated queries of the form
"is employee X available on day D" and "does employee X have a primary
event on day D". Answering those from the DB per-call makes the scheduler
O(events × days × employees × 3 queries). This module wraps them in an
in-memory cache populated once at the start of each run and updated
incrementally as each PendingSchedule is proposed.

Primary events = Core + Juicer Production (per spec 01-key-concepts.md K1).
Week = Sunday through Saturday inclusive (per spec 01-key-concepts.md K9).
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func


# Keep these in sync with
# docs/superpowers/specs/2026-04-10-scheduler-rewrite/01-key-concepts.md
PRIMARY_EVENT_TYPES = frozenset({'Core', 'Juicer Production'})

# Secondary events (spec K2) — require a primary event on the same day
# for the same employee in order to be assigned (except via CS fallback).
SECONDARY_EVENT_TYPES = frozenset({
    'Juicer Survey',
    'Supervisor',
    'Freeosk',
    'Digital Setup',
    'Digital Refresh',
})


def lookup_rotation(db, models, target_date: date, rotation_type: str):
    """Look up (primary_emp_id, backup_emp_id) for a date + rotation type.

    Per spec branches JP3 + JP4 + DF1 (and analogous branches in other specs),
    a `ScheduleException` row for the exact (`target_date`, `rotation_type`)
    pair fully overrides the standing `RotationAssignment`. Exception rows
    have no backup slot, so callers receive `(override_emp, None)`.

    If no exception is present, fall back to the standing `RotationAssignment`
    for the target date's day-of-week. Returns `(None, None)` when neither
    source has a row.

    Args:
        db: SQLAlchemy session.
        models: Model registry (as returned by `get_models()`).
        target_date: The date for which to look up rotation.
        rotation_type: E.g., `'juicer'`, `'primary_lead'`.

    Returns:
        Tuple of `(primary_employee_id, backup_employee_id)`. Either or both
        elements may be `None`.
    """
    ScheduleException = models['ScheduleException']
    RotationAssignment = models['RotationAssignment']
    exc = (db.query(ScheduleException)
           .filter_by(exception_date=target_date, rotation_type=rotation_type)
           .first())
    if exc is not None:
        return (exc.employee_id, None)
    row = (db.query(RotationAssignment)
           .filter_by(day_of_week=target_date.weekday(),
                      rotation_type=rotation_type)
           .first())
    if row is None:
        return (None, None)
    return (row.employee_id, row.backup_employee_id)


def classify_event(event_type: str) -> str:
    """Classify an event type per spec 01-key-concepts.md branches K1–K3.

    Returns one of:
      - 'primary'          — Core, Juicer Production (K1)
      - 'secondary'        — Juicer Survey, Supervisor, Freeosk,
                             Digital Setup, Digital Refresh (K2)
      - 'teardown_bucket'  — Digital Teardown (K3) — its own bucket,
                             neither primary nor secondary
      - 'other'            — anything else (e.g., the 'Other' category,
                             'Juicer Deep Clean', unknown types)
    """
    if event_type in PRIMARY_EVENT_TYPES:
        return 'primary'
    if event_type in SECONDARY_EVENT_TYPES:
        return 'secondary'
    if event_type == 'Digital Teardown':
        return 'teardown_bucket'
    return 'other'

# Day-of-week column names in the order matching Python's date.weekday() (Mon=0..Sun=6)
_WEEKDAY_COLUMNS = ('monday', 'tuesday', 'wednesday', 'thursday',
                    'friday', 'saturday', 'sunday')


class RunCache:
    """Per-run scheduler state cache.

    Holds precomputed availability, rotation, and schedule-state data for a
    single SchedulerRunHistory row. Mutated as the run progresses to reflect
    newly-proposed PendingSchedule rows.

    The `run_id` parameter is stored for use by plans 02-07 category handlers,
    which may need to cross-reference in-run PendingSchedule rows by run id.
    """

    def __init__(self, db_session, models, run_id: int):
        self.db = db_session
        self.models = models
        self.run_id = run_id

        # (emp_id, date) → bool
        self._available: dict[tuple[str, date], bool] = {}
        # (emp_id, date) → list of (event_ref_num, event_type) tuples
        self._events_by_emp_day: dict[tuple[str, date], list[tuple[int, str]]] = defaultdict(list)
        # (emp_id, week_start) → int count of primary events
        self._primaries_by_week: dict[tuple[str, date], int] = defaultdict(int)

    # -------- availability --------

    def is_available(self, emp_id: str, d: date) -> bool:
        if emp_id is None:
            return False
        key = (emp_id, d)
        if key in self._available:
            return self._available[key]
        result = self._compute_available(emp_id, d)
        self._available[key] = result
        return result

    def _compute_available(self, emp_id: str, d: date) -> bool:
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        EmployeeWeeklyAvailability = self.models['EmployeeWeeklyAvailability']
        EmployeeAvailabilityOverride = self.models['EmployeeAvailabilityOverride']

        # Approved time off?
        off = (self.db.query(EmployeeTimeOff.id)
               .filter(EmployeeTimeOff.employee_id == emp_id,
                       EmployeeTimeOff.status == 'approved',
                       EmployeeTimeOff.start_date <= d,
                       EmployeeTimeOff.end_date >= d)
               .first())
        if off:
            return False

        col = _WEEKDAY_COLUMNS[d.weekday()]

        ov = (self.db.query(EmployeeAvailabilityOverride)
              .filter(EmployeeAvailabilityOverride.employee_id == emp_id,
                      EmployeeAvailabilityOverride.start_date <= d,
                      EmployeeAvailabilityOverride.end_date >= d)
              .first())
        if ov is not None:
            val = getattr(ov, col)
            if val is False:
                return False
            if val is True:
                return True

        wa = (self.db.query(EmployeeWeeklyAvailability)
              .filter_by(employee_id=emp_id)
              .first())
        if wa and getattr(wa, col) is False:
            return False

        return True

    # -------- primary events --------

    def record_primary(self, emp_id: str, d: date, event_type: str, event_ref_num: int) -> None:
        """Record that a newly-scheduled primary event exists for (emp, day).

        INVARIANT: callers must only pass newly-proposed PendingSchedule assignments
        from the current run. Never pass rows already in Schedule — `primaries_this_week`
        sums the in-run cache AND the DB, so passing a posted Schedule here would
        cause double-counting.
        """
        if event_type not in PRIMARY_EVENT_TYPES:
            return
        self._events_by_emp_day[(emp_id, d)].append((event_ref_num, event_type))
        week_start = self._sun_sat_week_start(d)
        self._primaries_by_week[(emp_id, week_start)] += 1

    def has_primary_event(self, emp_id: str, d: date) -> bool:
        """True iff this employee has at least one primary event on day d,
        counting both posted Schedule rows and in-run PendingSchedule rows."""
        if emp_id is None:
            return False
        key = (emp_id, d)
        if key in self._events_by_emp_day:
            for (_ref, etype) in self._events_by_emp_day[key]:
                if etype in PRIMARY_EVENT_TYPES:
                    return True
        # Fall through to DB check for posted schedules not yet loaded
        return self._query_has_primary_from_db(emp_id, d)

    def _query_has_primary_from_db(self, emp_id: str, d: date) -> bool:
        Schedule = self.models['Schedule']
        Event = self.models['Event']
        posted = (self.db.query(Schedule.id)
                  .join(Event, Schedule.event_ref_num == Event.project_ref_num)
                  .filter(Schedule.employee_id == emp_id,
                          func.date(Schedule.schedule_datetime) == d,
                          Event.event_type.in_(tuple(PRIMARY_EVENT_TYPES)))
                  .first())
        return posted is not None

    def primaries_this_week(self, emp_id: str, d: date) -> int:
        """Count of primary events for emp in the Sun-Sat week containing d."""
        week_start = self._sun_sat_week_start(d)
        from_cache = self._primaries_by_week.get((emp_id, week_start), 0)
        from_db = self._query_primaries_this_week_from_db(emp_id, week_start)
        return from_cache + from_db

    def _query_primaries_this_week_from_db(self, emp_id: str, week_start: date) -> int:
        Schedule = self.models['Schedule']
        Event = self.models['Event']
        week_end = week_start + timedelta(days=6)
        count = (self.db.query(func.count(Schedule.id))
                 .join(Event, Schedule.event_ref_num == Event.project_ref_num)
                 .filter(Schedule.employee_id == emp_id,
                         func.date(Schedule.schedule_datetime) >= week_start,
                         func.date(Schedule.schedule_datetime) <= week_end,
                         Event.event_type.in_(tuple(PRIMARY_EVENT_TYPES)))
                 .scalar()) or 0
        return count

    # -------- week math --------

    @staticmethod
    def _sun_sat_week_start(d: date) -> date:
        """Return the Sunday of the Sun-Sat week containing d.

        Python's date.weekday() has Mon=0..Sun=6. Convert to Sun=0..Sat=6
        via (weekday() + 1) % 7.
        """
        days_since_sunday = (d.weekday() + 1) % 7
        return d - timedelta(days=days_since_sunday)
