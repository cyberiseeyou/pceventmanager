"""
Schedule Rebalancer Service

Rebalances Core events within a week across two dimensions:
1. Time slot balance: Even distribution across daily shift block start times
2. Employee workload balance: Even distribution of Core events across eligible employees

Uses ConstraintValidator to ensure all moves respect scheduling rules.
"""
from datetime import date, datetime, timedelta, time
from typing import Dict, List, Any

from flask import current_app
from sqlalchemy.orm import Session


class ScheduleRebalancer:
    """Rebalances posted Core schedules within a week."""

    def __init__(self, db_session: Session, models: dict):
        self.db = db_session
        self.Schedule = models['Schedule']
        self.Event = models['Event']
        self.Employee = models['Employee']
        self.LockedDay = models.get('LockedDay')
        self.models = models

    def rebalance_week(self, week_start: date) -> Dict[str, Any]:
        """
        Rebalance Core events for the given week.

        Args:
            week_start: First day of the week (will be aligned to Sunday)

        Returns:
            Dict with keys: moves_made, time_slot_moves, employee_swaps,
                           skipped_reasons, details
        """
        # Align to Sunday
        days_since_sunday = (week_start.weekday() + 1) % 7
        week_start = week_start - timedelta(days=days_since_sunday)
        week_dates = [week_start + timedelta(days=i) for i in range(7)]

        result = {
            'moves_made': 0,
            'time_slot_moves': 0,
            'employee_swaps': 0,
            'skipped_reasons': [],
            'details': []
        }

        locked_dates = self._get_locked_dates(week_dates)

        # Phase 1: Time slot rebalancing per day
        for day in week_dates:
            if day in locked_dates:
                result['skipped_reasons'].append(f'{day.isoformat()}: locked day')
                continue
            phase1_result = self._rebalance_time_slots(day)
            result['time_slot_moves'] += phase1_result['moves']
            result['moves_made'] += phase1_result['moves']
            result['details'].extend(phase1_result['details'])
            result['skipped_reasons'].extend(phase1_result['skipped'])

        # Phase 2: Employee workload rebalancing across week
        phase2_result = self._rebalance_employee_workload(week_dates, locked_dates)
        result['employee_swaps'] += phase2_result['swaps']
        result['moves_made'] += phase2_result['swaps']
        result['details'].extend(phase2_result['details'])
        result['skipped_reasons'].extend(phase2_result['skipped'])

        if result['moves_made'] > 0:
            self.db.commit()

        return result

    def _get_locked_dates(self, week_dates: List[date]) -> set:
        """Return set of locked dates in the given week."""
        if not self.LockedDay:
            return set()

        locked = set()
        for d in week_dates:
            if self.LockedDay.get_locked_day(d):
                locked.add(d)
        return locked

    def _get_core_schedules_for_date(self, target_date: date) -> list:
        """Get all posted Core schedules for a specific date."""
        start_dt = datetime.combine(target_date, time.min)
        end_dt = datetime.combine(target_date, time.max)

        schedules = self.db.query(self.Schedule).join(
            self.Event,
            self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Event.event_type == 'Core'
        ).all()

        return schedules

    def _get_available_start_times(self) -> List[time]:
        """Get the unique Core start times from shift block config."""
        try:
            from app.services.shift_block_config import ShiftBlockConfig
            blocks = ShiftBlockConfig.get_all_blocks()
            seen = set()
            times = []
            for block in blocks:
                if block['block'] <= 8:
                    t = block['arrive']
                    key = (t.hour, t.minute)
                    if key not in seen:
                        seen.add(key)
                        times.append(t)
            return sorted(times)
        except Exception:
            return [time(7, 0), time(9, 0), time(11, 0), time(13, 0)]

    def _rebalance_time_slots(self, target_date: date) -> Dict[str, Any]:
        """
        Phase 1: Rebalance Core events across time slots for a single day.

        Moves events from overloaded slots to underloaded slots.
        """
        result = {'moves': 0, 'details': [], 'skipped': []}

        core_schedules = self._get_core_schedules_for_date(target_date)
        if len(core_schedules) < 2:
            return result

        start_times = self._get_available_start_times()
        if len(start_times) < 2:
            return result

        # Group schedules by their start time slot
        slots = {t: [] for t in start_times}
        for sched in core_schedules:
            sched_time = sched.schedule_datetime.time()
            best_slot = min(start_times, key=lambda t: abs(
                (t.hour * 60 + t.minute) - (sched_time.hour * 60 + sched_time.minute)
            ))
            slots[best_slot].append(sched)

        total = len(core_schedules)
        target_per_slot = total / len(start_times)

        # Check if already balanced (spread <= 1)
        slot_counts = [len(s) for s in slots.values()]
        if max(slot_counts) - min(slot_counts) <= 1:
            return result

        # Sort slots: most overloaded first
        sorted_slots = sorted(slots.items(), key=lambda x: len(x[1]), reverse=True)

        for from_time, from_schedules in sorted_slots:
            if len(from_schedules) <= target_per_slot:
                continue

            for to_time, to_schedules in sorted(slots.items(), key=lambda x: len(x[1])):
                if len(to_schedules) >= target_per_slot:
                    continue
                if from_time == to_time:
                    continue

                for sched in list(from_schedules):
                    if len(from_schedules) <= target_per_slot:
                        break
                    if len(to_schedules) >= target_per_slot:
                        break

                    if self._can_move_to_time(sched, target_date, to_time):
                        old_time = sched.schedule_datetime.time()
                        new_dt = datetime.combine(target_date, to_time)
                        sched.schedule_datetime = new_dt

                        from_schedules.remove(sched)
                        to_schedules.append(sched)

                        result['moves'] += 1
                        result['details'].append(
                            f"Moved {sched.employee_name}'s Core event on {target_date} "
                            f"from {old_time.strftime('%H:%M')} to {to_time.strftime('%H:%M')}"
                        )
                    else:
                        result['skipped'].append(
                            f"Cannot move {sched.employee_name} on {target_date} "
                            f"from {from_time.strftime('%H:%M')} to {to_time.strftime('%H:%M')}: "
                            f"constraint violation"
                        )

        return result

    def _can_move_to_time(self, schedule, target_date: date, new_time: time) -> bool:
        """Check if a schedule can be moved to a new time on the same day."""
        employee = self.db.query(self.Employee).get(schedule.employee_id)
        event = self.db.query(self.Event).filter_by(
            project_ref_num=schedule.event_ref_num
        ).first()

        if not employee or not event:
            return False

        new_dt = datetime.combine(target_date, new_time)

        try:
            from app.services.constraint_validator import ConstraintValidator
            validator = ConstraintValidator(self.db, self.models)
            validation = validator.validate_assignment(
                event, employee, new_dt,
                exclude_schedule_ids=[schedule.id]
            )
            return len(validation.hard_violations) == 0
        except Exception as e:
            current_app.logger.warning(f"Constraint check failed: {e}")
            return False

    def _rebalance_employee_workload(self, week_dates: List[date],
                                      locked_dates: set) -> Dict[str, Any]:
        """
        Phase 2: Rebalance Core event assignments across employees for the week.

        Reassigns events from overloaded employees to underloaded ones.
        """
        result = {'swaps': 0, 'details': [], 'skipped': []}

        # Collect all Core schedules for the week (excluding locked days)
        all_core_schedules = []
        for day in week_dates:
            if day in locked_dates:
                continue
            all_core_schedules.extend(self._get_core_schedules_for_date(day))

        if not all_core_schedules:
            return result

        # Get eligible employees (active, can work Core)
        eligible = self.db.query(self.Employee).filter(
            self.Employee.is_active == True,
            self.Employee.job_title.in_(['Lead Event Specialist', 'Event Specialist'])
        ).all()

        if len(eligible) < 2:
            return result

        eligible_ids = {e.id for e in eligible}

        # Count Core events per employee this week
        emp_counts = {}
        emp_schedules = {}
        for sched in all_core_schedules:
            eid = sched.employee_id
            if eid not in eligible_ids:
                continue
            emp_counts[eid] = emp_counts.get(eid, 0) + 1
            emp_schedules.setdefault(eid, []).append(sched)

        # Include employees with 0 events
        for emp in eligible:
            if emp.id not in emp_counts:
                emp_counts[emp.id] = 0
                emp_schedules[emp.id] = []

        max_iterations = len(all_core_schedules) * 2
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            overloaded = max(emp_counts, key=emp_counts.get)
            underloaded = min(emp_counts, key=emp_counts.get)

            spread = emp_counts[overloaded] - emp_counts[underloaded]
            if spread <= 1:
                break

            moved = False
            for sched in list(emp_schedules.get(overloaded, [])):
                sched_date = sched.schedule_datetime.date()
                if sched_date in locked_dates:
                    continue

                underloaded_emp = self.db.query(self.Employee).get(underloaded)
                if not underloaded_emp:
                    continue

                # Check: does underloaded already have a Core on this day?
                has_core_same_day = any(
                    s.schedule_datetime.date() == sched_date
                    for s in emp_schedules.get(underloaded, [])
                )
                if has_core_same_day:
                    continue

                if self._can_reassign(sched, underloaded_emp):
                    old_emp_name = sched.employee_name
                    sched.employee_id = underloaded_emp.id
                    sched.employee_name = underloaded_emp.name

                    emp_schedules[overloaded].remove(sched)
                    emp_schedules.setdefault(underloaded, []).append(sched)
                    emp_counts[overloaded] -= 1
                    emp_counts[underloaded] += 1

                    result['swaps'] += 1
                    result['details'].append(
                        f"Reassigned Core event on {sched_date} "
                        f"from {old_emp_name} to {underloaded_emp.name}"
                    )
                    moved = True
                    break

            if not moved:
                result['skipped'].append(
                    f"Cannot rebalance {overloaded} (has {emp_counts[overloaded]}) -> "
                    f"{underloaded} (has {emp_counts[underloaded]}): no valid swaps"
                )
                break

        return result

    def _can_reassign(self, schedule, new_employee) -> bool:
        """Check if a schedule can be reassigned to a different employee."""
        event = self.db.query(self.Event).filter_by(
            project_ref_num=schedule.event_ref_num
        ).first()

        if not event:
            return False

        try:
            from app.services.constraint_validator import ConstraintValidator
            validator = ConstraintValidator(self.db, self.models)
            validation = validator.validate_assignment(
                event, new_employee, schedule.schedule_datetime,
                exclude_schedule_ids=[schedule.id]
            )
            return len(validation.hard_violations) == 0
        except Exception as e:
            current_app.logger.warning(f"Constraint check failed for reassign: {e}")
            return False
