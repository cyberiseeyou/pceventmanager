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


# Keep these in sync with
# docs/superpowers/specs/2026-04-10-scheduler-rewrite/01-key-concepts.md
PRIMARY_EVENT_TYPES = frozenset({'Core', 'Juicer Production'})


class RunCache:
    """Per-run scheduler state cache.

    Holds precomputed availability, rotation, and schedule-state data for a
    single SchedulerRunHistory row. Mutated as the run progresses to reflect
    newly-proposed PendingSchedule rows.
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
        key = (emp_id, d)
        if key in self._available:
            return self._available[key]
        result = self._compute_available(emp_id, d)
        self._available[key] = result
        return result

    def _compute_available(self, emp_id: str, d: date) -> bool:
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        EmployeeWeeklyAvailability = self.models['EmployeeWeeklyAvailability']
        EmployeeAvailabilityOverride = self.models.get('EmployeeAvailabilityOverride')

        # Approved time off?
        off = (self.db.query(EmployeeTimeOff.id)
               .filter(EmployeeTimeOff.employee_id == emp_id,
                       EmployeeTimeOff.status == 'approved',
                       EmployeeTimeOff.start_date <= d,
                       EmployeeTimeOff.end_date >= d)
               .first())
        if off:
            return False

        day_cols = ['monday', 'tuesday', 'wednesday', 'thursday',
                    'friday', 'saturday', 'sunday']
        col = day_cols[d.weekday()]

        if EmployeeAvailabilityOverride is not None:
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
        """Record that a newly-scheduled primary event exists for (emp, day)."""
        if event_type not in PRIMARY_EVENT_TYPES:
            return
        self._events_by_emp_day[(emp_id, d)].append((event_ref_num, event_type))
        week_start = self._sun_sat_week_start(d)
        self._primaries_by_week[(emp_id, week_start)] += 1

    def has_primary_event(self, emp_id: str, d: date) -> bool:
        """True iff this employee has at least one primary event on day d,
        counting both posted Schedule rows and in-run PendingSchedule rows."""
        key = (emp_id, d)
        if key in self._events_by_emp_day:
            for (_ref, etype) in self._events_by_emp_day[key]:
                if etype in PRIMARY_EVENT_TYPES:
                    return True
        # Fall through to DB check for posted schedules not yet loaded
        return self._query_has_primary_from_db(emp_id, d)

    def _query_has_primary_from_db(self, emp_id: str, d: date) -> bool:
        from sqlalchemy import func
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
        from sqlalchemy import func
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
