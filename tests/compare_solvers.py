#!/usr/bin/env python3
"""
Compare Greedy vs CP-SAT scheduler and validate all scheduling rules.

Rules validated (from docs/scheduling-rules-by-event-type.md):
  HARD CONSTRAINTS:
    RULE-001 / H11: Max 1 Core per employee per day (Club Supervisor exempt)
    RULE-005 / H18: Support events need base event same day (Club Supervisor exempt)
    RULE-006 / H13: Juicer-Core mutual exclusion per employee per day
    RULE-007 / H16: Core must have paired Supervisor on same day
    RULE-009 / H17: Juicer Production paired with Survey same day, same employee
    RULE-015 / H14: No Juicer Deep Clean on day with Juicer Production (global)
    RULE-016 / H5+H6: No scheduling outside availability / time-off
    RULE-018 / H12: Max 6 Core per employee per week
    RULE-019:       Max 5 Juicer Production per employee per week
    RULE-020:       Same product not on same day
    H20:            Full-day events block Core/Juicer same day same employee
    H21:            One employee per Core block per day
  SOFT CONSTRAINTS:
    RULE-003 / S7:  Primary Lead at Block 1
    RULE-004:       Club Supervisor preferred for Supervisor events
    RULE-017 / S9:  Fairness in distribution
"""

import os, sys, time, re
from datetime import datetime, timedelta, date, time as dtime
from collections import Counter, defaultdict
import statistics

os.environ['FLASK_ENV'] = 'development'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import get_models


# ── Helpers ──────────────────────────────────────────────────────────────────

JUICER_EVENT_TYPES = {'Juicer', 'Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'}
LEAD_ONLY_EVENT_TYPES = {'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh',
                         'Digital Teardown', 'Other'}
SUPPORT_EVENT_TYPES = {'Freeosk', 'Digitals', 'Digital Setup', 'Digital Refresh',
                       'Digital Teardown'}
BASE_EVENT_TYPES = {'Core', 'Juicer', 'Juicer Production'}


def extract_product_number(name):
    """Extract the 6-digit product number from a project name."""
    if not name:
        return None
    m = re.search(r'(\d{6})', name)
    return m.group(1) if m else None


def iso_week_key(d):
    """Return (year, iso_week) for Sunday–Saturday week grouping."""
    # Shift so Sunday=0 aligns with our week boundary
    adjusted = d + timedelta(days=1)
    return adjusted.isocalendar()[:2]


def sunday_saturday_week(d):
    """Return the Sunday date that starts the week containing d."""
    days_since_sunday = (d.weekday() + 1) % 7
    return d - timedelta(days=days_since_sunday)


# ── Rule Validator ───────────────────────────────────────────────────────────

class ScheduleValidator:
    """Validate a set of PendingSchedule records against all scheduling rules."""

    def __init__(self, session, models, pending_records, solver_name):
        self.session = session
        self.models = models
        self.solver = solver_name
        self.pending = pending_records
        self.violations = []  # (rule_id, severity, message)

        # Build lookups
        Event = models['Event']
        Employee = models['Employee']

        self.events_by_ref = {}
        for ps in self.pending:
            if ps.event_ref_num not in self.events_by_ref:
                ev = session.query(Event).filter_by(
                    project_ref_num=ps.event_ref_num).first()
                if ev:
                    self.events_by_ref[ps.event_ref_num] = ev

        self.employees = {}
        for emp in session.query(Employee).filter_by(is_active=True).all():
            self.employees[emp.id] = emp

        # Scheduled records only (have employee + datetime)
        self.scheduled = [ps for ps in self.pending
                          if ps.employee_id and ps.schedule_datetime]

        # Index: (employee_id, date) -> list of (ps, event)
        self.emp_day_index = defaultdict(list)
        for ps in self.scheduled:
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            ev = self.events_by_ref.get(ps.event_ref_num)
            if ev:
                self.emp_day_index[(ps.employee_id, d)].append((ps, ev))

        # Index: date -> list of (ps, event)
        self.day_index = defaultdict(list)
        for ps in self.scheduled:
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            ev = self.events_by_ref.get(ps.event_ref_num)
            if ev:
                self.day_index[d].append((ps, ev))

    def validate_all(self):
        """Run all rule validations and return violations."""
        self.violations = []
        self._rule_001_h11_one_core_per_day()
        self._rule_005_h18_support_needs_base()
        self._rule_006_h13_juicer_core_exclusion()
        self._rule_007_h16_core_supervisor_pairing()
        self._rule_009_h17_juicer_prod_survey_pairing()
        self._rule_015_h14_deep_clean_production_exclusion()
        self._rule_016_h5h6_availability()
        self._rule_018_h12_max_core_per_week()
        self._rule_019_max_juicer_per_week()
        self._rule_020_duplicate_product()
        self._h20_fullday_exclusivity()
        self._h21_block_uniqueness()
        # Soft checks
        self._rule_004_supervisor_assignment()
        self._s9_fairness()
        return self.violations

    def _add(self, rule_id, severity, msg):
        self.violations.append((rule_id, severity, msg))

    # ── Hard constraint checks ───────────────────────────────────────────

    def _rule_001_h11_one_core_per_day(self):
        """RULE-001/H11: Max 1 Core per employee per day (Club Supervisor exempt)."""
        for (emp_id, d), entries in self.emp_day_index.items():
            emp = self.employees.get(emp_id)
            if emp and emp.job_title == 'Club Supervisor':
                continue
            core_count = sum(1 for _, ev in entries if ev.event_type == 'Core')
            if core_count > 1:
                name = emp.name if emp else emp_id
                self._add('RULE-001/H11', 'CRITICAL',
                          f'{name} has {core_count} Core events on {d}')

    def _rule_005_h18_support_needs_base(self):
        """RULE-005/H18: Support events require base event same day (Club Sup exempt)."""
        for (emp_id, d), entries in self.emp_day_index.items():
            emp = self.employees.get(emp_id)
            if emp and emp.job_title == 'Club Supervisor':
                continue
            has_support = any(ev.event_type in SUPPORT_EVENT_TYPES for _, ev in entries)
            has_base = any(ev.event_type in BASE_EVENT_TYPES for _, ev in entries)
            if has_support and not has_base:
                name = emp.name if emp else emp_id
                support_types = [ev.event_type for _, ev in entries
                                 if ev.event_type in SUPPORT_EVENT_TYPES]
                self._add('RULE-005/H18', 'CRITICAL',
                          f'{name} has {support_types} on {d} without Core/Juicer base')

    def _rule_006_h13_juicer_core_exclusion(self):
        """RULE-006/H13: Juicer and Core cannot be on same day for same employee."""
        for (emp_id, d), entries in self.emp_day_index.items():
            types = {ev.event_type for _, ev in entries}
            has_juicer = bool(types & {'Juicer', 'Juicer Production'})
            has_core = 'Core' in types
            if has_juicer and has_core:
                emp = self.employees.get(emp_id)
                name = emp.name if emp else emp_id
                self._add('RULE-006/H13', 'CRITICAL',
                          f'{name} has both Juicer and Core on {d}')

    def _rule_007_h16_core_supervisor_pairing(self):
        """RULE-007/H16: Core events must have paired Supervisor on same day."""
        # Build map of scheduled Core by product number + date
        core_by_num_date = {}
        sup_by_num_date = {}

        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev:
                continue
            num = extract_product_number(ev.project_name)
            if not num:
                continue
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            if ev.event_type == 'Core':
                core_by_num_date[(num, d)] = (ps, ev)
            elif ev.event_type == 'Supervisor':
                sup_by_num_date[(num, d)] = (ps, ev)

        for (num, d), (ps, ev) in core_by_num_date.items():
            if (num, d) not in sup_by_num_date:
                self._add('RULE-007/H16', 'WARNING',
                          f'Core {num} on {d} has no paired Supervisor')

    def _rule_009_h17_juicer_prod_survey_pairing(self):
        """RULE-009/H17: Juicer Production paired with Survey same day, same employee."""
        prod_by_num = {}
        survey_by_num = {}

        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev:
                continue
            num = extract_product_number(ev.project_name)
            if not num:
                continue
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            if ev.event_type == 'Juicer Production':
                prod_by_num[num] = (ps.employee_id, d)
            elif ev.event_type == 'Juicer Survey':
                survey_by_num[num] = (ps.employee_id, d)

        for num, (emp, d) in prod_by_num.items():
            if num in survey_by_num:
                s_emp, s_d = survey_by_num[num]
                if s_d != d:
                    self._add('RULE-009/H17', 'CRITICAL',
                              f'Juicer Prod {num} on {d} but Survey on {s_d}')
                if s_emp != emp:
                    self._add('RULE-009/H17', 'CRITICAL',
                              f'Juicer Prod {num}: emp={emp} but Survey emp={s_emp}')

    def _rule_015_h14_deep_clean_production_exclusion(self):
        """RULE-015/H14: No Juicer Deep Clean on day with Juicer Production (global)."""
        for d, entries in self.day_index.items():
            types = {ev.event_type for _, ev in entries}
            if 'Juicer Deep Clean' in types and 'Juicer Production' in types:
                self._add('RULE-015/H14', 'CRITICAL',
                          f'Juicer Deep Clean AND Production both on {d}')

    def _rule_016_h5h6_availability(self):
        """RULE-016/H5+H6: No scheduling outside availability or during time-off."""
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        EmployeeWeeklyAvailability = self.models['EmployeeWeeklyAvailability']

        # Load time-off
        time_off_records = self.session.query(EmployeeTimeOff).all()
        time_off_ranges = defaultdict(list)
        for to in time_off_records:
            time_off_ranges[to.employee_id].append((to.start_date, to.end_date))

        # Load weekly availability
        weekly_avail = {}
        day_attrs = ['monday', 'tuesday', 'wednesday', 'thursday',
                     'friday', 'saturday', 'sunday']
        for wa in self.session.query(EmployeeWeeklyAvailability).all():
            weekly_avail[wa.employee_id] = wa

        count = 0
        for ps in self.scheduled:
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            emp_id = ps.employee_id

            # Check time-off
            for start, end in time_off_ranges.get(emp_id, []):
                if start <= d <= end:
                    emp = self.employees.get(emp_id)
                    name = emp.name if emp else emp_id
                    self._add('RULE-016/H5', 'CRITICAL',
                              f'{name} scheduled on {d} during time-off ({start} to {end})')
                    count += 1
                    break

            # Check weekly availability
            if emp_id in weekly_avail:
                wa = weekly_avail[emp_id]
                dow = d.weekday()
                if not getattr(wa, day_attrs[dow], True):
                    emp = self.employees.get(emp_id)
                    name = emp.name if emp else emp_id
                    self._add('RULE-016/H6', 'CRITICAL',
                              f'{name} scheduled on {d} ({day_attrs[dow]}) but unavailable')
                    count += 1

    def _rule_018_h12_max_core_per_week(self):
        """RULE-018/H12: Max 6 Core per employee per week (Sun-Sat)."""
        emp_week_core = defaultdict(int)
        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev or ev.event_type != 'Core':
                continue
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            week_sun = sunday_saturday_week(d)
            emp_week_core[(ps.employee_id, week_sun)] += 1

        for (emp_id, week_sun), cnt in emp_week_core.items():
            if cnt > 6:
                emp = self.employees.get(emp_id)
                name = emp.name if emp else emp_id
                self._add('RULE-018/H12', 'CRITICAL',
                          f'{name} has {cnt} Core events in week of {week_sun}')

    def _rule_019_max_juicer_per_week(self):
        """RULE-019: Max 5 Juicer Production per employee per week."""
        emp_week_juicer = defaultdict(int)
        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev or ev.event_type != 'Juicer Production':
                continue
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            week_sun = sunday_saturday_week(d)
            emp_week_juicer[(ps.employee_id, week_sun)] += 1

        for (emp_id, week_sun), cnt in emp_week_juicer.items():
            if cnt > 5:
                emp = self.employees.get(emp_id)
                name = emp.name if emp else emp_id
                self._add('RULE-019', 'CRITICAL',
                          f'{name} has {cnt} Juicer Production events in week of {week_sun}')

    def _rule_020_duplicate_product(self):
        """RULE-020: Same product not on same day."""
        day_products = defaultdict(list)
        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev:
                continue
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            # Normalize product name - strip the 6-digit prefix and type suffix
            name = ev.project_name or ''
            num = extract_product_number(name)
            # Get the product portion (after the 6-digit number, before the type)
            parts = name.split('-', 2)
            product_key = parts[1].strip().upper() if len(parts) > 1 else name.upper()
            # Only flag duplicate same-type events (not Core+Supervisor pairs)
            day_products[(d, product_key, ev.event_type)].append(ps)

        for (d, prod, etype), records in day_products.items():
            if len(records) > 1 and etype == 'Core':
                refs = [str(r.event_ref_num) for r in records]
                self._add('RULE-020', 'WARNING',
                          f'Duplicate product "{prod}" ({etype}) on {d}: refs {refs}')

    def _h20_fullday_exclusivity(self):
        """H20: Full-day events (>=480 min) block Core/Juicer same day same employee."""
        for (emp_id, d), entries in self.emp_day_index.items():
            full_day_ids = set()
            core_juicer_ids = set()
            for ps, ev in entries:
                if ev.estimated_time and ev.estimated_time >= 480:
                    full_day_ids.add(ev.id)
                if ev.event_type in ('Core', 'Juicer', 'Juicer Production'):
                    core_juicer_ids.add(ev.id)

            # Check if there's a full-day event AND a different Core/Juicer event
            other_core_juicer = core_juicer_ids - full_day_ids
            if full_day_ids and other_core_juicer:
                emp = self.employees.get(emp_id)
                name = emp.name if emp else emp_id
                self._add('H20', 'CRITICAL',
                          f'{name} has full-day event + Core/Juicer on {d}')

    def _h21_block_uniqueness(self):
        """H21: One employee per Core shift block per day.

        Blocks come in pairs with the same arrive time (1&2=10:15, 3&4=10:45,
        5&6=11:15, 7&8=11:45), so up to 2 Core events at the same time is valid.
        More than 2 at the same time means a block collision.
        Also checks total Core events per day doesn't exceed 8 (max blocks).
        """
        # Group Core events by (date, time)
        day_time_emps = defaultdict(list)
        day_core_count = defaultdict(int)
        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev or ev.event_type != 'Core':
                continue
            d = ps.schedule_datetime.date() if isinstance(
                ps.schedule_datetime, datetime) else ps.schedule_datetime
            t = ps.schedule_datetime.time() if isinstance(
                ps.schedule_datetime, datetime) else dtime(10, 15)
            day_time_emps[(d, t)].append(ps.employee_id)
            day_core_count[d] += 1

        for (d, t), emps in day_time_emps.items():
            # 2 blocks share each time slot, so >2 is a real violation
            if len(emps) > 2:
                self._add('H21', 'CRITICAL',
                          f'{len(emps)} employees at Core time {t} on {d} (max 2 per slot): {emps}')

        for d, count in day_core_count.items():
            if count > 8:
                self._add('H21', 'CRITICAL',
                          f'{count} Core events on {d} exceeds 8 blocks')

    # ── Soft constraint checks ───────────────────────────────────────────

    def _rule_004_supervisor_assignment(self):
        """RULE-004: Club Supervisor preferred for Supervisor events."""
        sup_total = 0
        sup_club = 0
        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if not ev or ev.event_type != 'Supervisor':
                continue
            sup_total += 1
            emp = self.employees.get(ps.employee_id)
            if emp and emp.job_title == 'Club Supervisor':
                sup_club += 1
        if sup_total:
            pct = sup_club / sup_total * 100
            self._add('RULE-004', 'INFO',
                      f'Supervisor assignment: {sup_club}/{sup_total} to Club Supervisor ({pct:.0f}%)')

    def _s9_fairness(self):
        """S9: Fairness in Core distribution across employees."""
        emp_core = Counter()
        for ps in self.scheduled:
            ev = self.events_by_ref.get(ps.event_ref_num)
            if ev and ev.event_type == 'Core':
                emp_core[ps.employee_id] += 1

        if len(emp_core) < 2:
            return

        vals = list(emp_core.values())
        mn, mx = min(vals), max(vals)
        std = statistics.stdev(vals) if len(vals) > 1 else 0
        spread = mx - mn

        lines = []
        for emp_id, cnt in sorted(emp_core.items(), key=lambda x: -x[1]):
            emp = self.employees.get(emp_id)
            name = emp.name[:18] if emp else emp_id
            lines.append(f'    {name}: {cnt}')

        detail = '\n'.join(lines)
        self._add('S9-Fairness', 'INFO',
                  f'Core spread: min={mn}, max={mx}, stdev={std:.1f}\n{detail}')


# ── Runner ───────────────────────────────────────────────────────────────────

def run_greedy(session, route_models):
    """Run the greedy scheduler and return (run, pending_records, elapsed)."""
    from app.services.scheduling_engine import SchedulingEngine
    t0 = time.time()
    engine = SchedulingEngine(session, route_models)
    run = engine.run_auto_scheduler(run_type='manual')
    elapsed = time.time() - t0
    PendingSchedule = route_models['PendingSchedule']
    pending = session.query(PendingSchedule).filter_by(scheduler_run_id=run.id).all()
    return run, pending, elapsed


def run_cpsat(session, route_models, app_config, time_limit):
    """Run the CP-SAT scheduler and return (run, pending_records, elapsed)."""
    from app.services.cpsat_scheduler import CPSATSchedulingEngine
    cpsat_models = dict(route_models)
    for extra in ['LockedDay', 'EventSchedulingOverride', 'EventTypeOverride',
                  'EmployeeAvailabilityOverride']:
        if extra in app_config:
            cpsat_models[extra] = app_config[extra]

    t0 = time.time()
    engine = CPSATSchedulingEngine(session, cpsat_models)
    run = engine.run_auto_scheduler(run_type='manual', time_limit_seconds=time_limit)
    elapsed = time.time() - t0
    PendingSchedule = route_models['PendingSchedule']
    pending = session.query(PendingSchedule).filter_by(scheduler_run_id=run.id).all()
    return run, pending, elapsed


def print_section(title):
    width = 70
    print()
    print('=' * width)
    print(f'  {title}')
    print('=' * width)


def print_run_summary(name, run, pending, elapsed, models, session):
    """Print summary stats for a solver run."""
    scheduled = [ps for ps in pending if ps.employee_id and ps.schedule_datetime]
    failed = [ps for ps in pending if not ps.employee_id or not ps.schedule_datetime]

    print(f'  Status: {run.status}')
    print(f'  Solve time: {elapsed:.1f}s')
    print(f'  Events processed: {run.total_events_processed}')
    print(f'  Scheduled: {run.events_scheduled}')
    print(f'  Swaps: {run.events_requiring_swaps}')
    print(f'  Failed: {run.events_failed}')

    Event = models['Event']
    Employee = models['Employee']

    # By type
    type_counts = Counter()
    for ps in scheduled:
        ev = session.query(Event).filter_by(project_ref_num=ps.event_ref_num).first()
        if ev:
            type_counts[ev.event_type] += 1
    print(f'\n  Scheduled by type:')
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f'    {t:<25} {c:>4}')

    # Failed by type
    fail_types = Counter()
    for ps in failed:
        ev = session.query(Event).filter_by(project_ref_num=ps.event_ref_num).first()
        if ev:
            fail_types[ev.event_type] += 1
    if fail_types:
        print(f'\n  Failed by type:')
        for t, c in sorted(fail_types.items(), key=lambda x: -x[1]):
            print(f'    {t:<25} {c:>4}')

    # Employee workload
    emp_counts = Counter()
    for ps in scheduled:
        emp = session.query(Employee).get(ps.employee_id) if ps.employee_id else None
        name = emp.name if emp else ps.employee_id
        emp_counts[name] += 1

    print(f'\n  Employee workload:')
    for name, cnt in sorted(emp_counts.items(), key=lambda x: -x[1]):
        bar = '#' * (cnt // 2)
        print(f'    {name:<22} {cnt:>3}  {bar}')

    return scheduled, failed


def print_violations(violations, solver_name):
    """Print rule violations grouped by severity."""
    if not violations:
        print(f'\n  >> ALL RULES PASSED <<')
        return

    by_severity = defaultdict(list)
    for rule, sev, msg in violations:
        by_severity[sev].append((rule, msg))

    for sev in ['CRITICAL', 'WARNING', 'INFO']:
        items = by_severity.get(sev, [])
        if not items:
            continue
        print(f'\n  [{sev}] ({len(items)}):')
        for rule, msg in items:
            for i, line in enumerate(msg.split('\n')):
                if i == 0:
                    print(f'    {rule:<18} {line}')
                else:
                    print(f'    {"":18} {line}')


def print_comparison(greedy_data, cpsat_runs):
    """Print side-by-side comparison table."""
    print_section('COMPARISON TABLE')

    # Header
    cpsat_headers = [f'CP-SAT {t}s' for t in cpsat_runs.keys()]
    hdr = f'{"Metric":<28} {"Greedy":>10}'
    for h in cpsat_headers:
        hdr += f' {h:>12}'
    print(hdr)
    print('-' * (28 + 10 + 12 * len(cpsat_runs) + len(cpsat_runs)))

    g_run, g_pend, g_time = greedy_data[:3]
    g_sched = [ps for ps in g_pend if ps.employee_id and ps.schedule_datetime]

    def row(label, g_val, c_vals, fmt='d'):
        line = f'  {label:<26} '
        if fmt == 'f':
            line += f'{g_val:>10.1f}'
        else:
            line += f'{g_val:>10}'
        for cv in c_vals:
            if fmt == 'f':
                line += f' {cv:>12.1f}'
            else:
                line += f' {cv:>12}'
        print(line)

    c_vals_time = [d[2] for d in cpsat_runs.values()]
    c_vals_proc = [d[0].total_events_processed for d in cpsat_runs.values()]
    c_vals_sched = [d[0].events_scheduled for d in cpsat_runs.values()]
    c_vals_swap = [d[0].events_requiring_swaps for d in cpsat_runs.values()]
    c_vals_fail = [d[0].events_failed for d in cpsat_runs.values()]

    row('Solve time (s)', g_time, c_vals_time, 'f')
    row('Events processed', g_run.total_events_processed, c_vals_proc)
    row('Events scheduled', g_run.events_scheduled, c_vals_sched)
    row('Swaps proposed', g_run.events_requiring_swaps, c_vals_swap)
    row('Events failed', g_run.events_failed, c_vals_fail)

    # Violation counts
    print()
    g_violations = greedy_data[3] if len(greedy_data) > 3 else []
    g_crit = sum(1 for _, s, _ in g_violations if s == 'CRITICAL')
    g_warn = sum(1 for _, s, _ in g_violations if s == 'WARNING')

    c_crits = []
    c_warns = []
    for tl, (_, _, _, violations) in cpsat_runs.items():
        c_crits.append(sum(1 for _, s, _ in violations if s == 'CRITICAL'))
        c_warns.append(sum(1 for _, s, _ in violations if s == 'WARNING'))

    row('Rule violations (CRIT)', g_crit, c_crits)
    row('Rule violations (WARN)', g_warn, c_warns)

    # Fairness
    print()
    emp_counts = Counter(ps.employee_id for ps in g_sched)
    g_std = statistics.stdev(emp_counts.values()) if len(emp_counts) > 1 else 0

    c_stds = []
    for tl, (_, pend, _, _) in cpsat_runs.items():
        sched = [ps for ps in pend if ps.employee_id and ps.schedule_datetime]
        ec = Counter(ps.employee_id for ps in sched)
        c_stds.append(statistics.stdev(ec.values()) if len(ec) > 1 else 0)

    row('Workload stdev (lower=fair)', g_std, c_stds, 'f')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = create_app('development')

    time_limits = [15, 30, 60, 120]

    with app.app_context():
        models = get_models()
        session = db.session

        route_models = {k: app.config[k] for k in [
            'Employee', 'Event', 'Schedule', 'SchedulerRunHistory',
            'PendingSchedule', 'RotationAssignment', 'ScheduleException',
            'EmployeeTimeOff', 'EmployeeAvailability', 'EmployeeWeeklyAvailability',
            'CompanyHoliday'
        ]}

        # ── Greedy ───────────────────────────────────────────────────────
        print_section('GREEDY SOLVER')
        g_run, g_pending, g_elapsed = run_greedy(session, route_models)
        g_scheduled, g_failed = print_run_summary(
            'Greedy', g_run, g_pending, g_elapsed, models, session)

        print(f'\n  --- Rule Validation ---')
        g_validator = ScheduleValidator(session, models, g_pending, 'Greedy')
        g_violations = g_validator.validate_all()
        print_violations(g_violations, 'Greedy')

        greedy_data = (g_run, g_pending, g_elapsed, g_violations)

        session.rollback()

        # ── CP-SAT at various time limits ────────────────────────────────
        cpsat_results = {}

        for tl in time_limits:
            print_section(f'CP-SAT SOLVER (time_limit={tl}s)')
            c_run, c_pending, c_elapsed = run_cpsat(
                session, route_models, app.config, tl)
            c_scheduled, c_failed = print_run_summary(
                f'CP-SAT {tl}s', c_run, c_pending, c_elapsed, models, session)

            print(f'\n  --- Rule Validation ---')
            c_validator = ScheduleValidator(session, models, c_pending, f'CP-SAT {tl}s')
            c_violations = c_validator.validate_all()
            print_violations(c_violations, f'CP-SAT {tl}s')

            cpsat_results[tl] = (c_run, c_pending, c_elapsed, c_violations)
            session.rollback()

        # ── Comparison ───────────────────────────────────────────────────
        print_comparison(greedy_data, cpsat_results)

        # ── CP-SAT improvement over time limits ──────────────────────────
        print_section('CP-SAT SCALING: DOES MORE TIME HELP?')
        print(f'  {"Time Limit":>12} {"Scheduled":>10} {"Failed":>8} {"Swaps":>8} {"Solve(s)":>10} {"CRIT":>6} {"WARN":>6}')
        print(f'  {"-"*12} {"-"*10} {"-"*8} {"-"*8} {"-"*10} {"-"*6} {"-"*6}')
        for tl in time_limits:
            r, p, e, v = cpsat_results[tl]
            crit = sum(1 for _, s, _ in v if s == 'CRITICAL')
            warn = sum(1 for _, s, _ in v if s == 'WARNING')
            print(f'  {tl:>10}s {r.events_scheduled:>10} {r.events_failed:>8} '
                  f'{r.events_requiring_swaps:>8} {e:>10.1f} {crit:>6} {warn:>6}')

        session.rollback()
        print('\n(All runs rolled back — no changes persisted to database)')


if __name__ == '__main__':
    main()
