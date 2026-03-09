# Auto-Balance Weekly Schedule — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** One-click rebalance of Core events within a week — evening out employee workload and time slot distribution.

**Architecture:** New `ScheduleRebalancer` service performs two phases: (1) time slot rebalancing per day, (2) employee workload rebalancing across the week. Uses existing `ConstraintValidator` for move validation. Exposed via a single POST endpoint, triggered from the weekly validation page.

**Tech Stack:** Flask, SQLAlchemy, existing ConstraintValidator, ShiftBlockConfig, Jinja2 template, vanilla JS

---

### Task 1: Create ScheduleRebalancer service — time slot rebalancing

**Files:**
- Create: `app/services/schedule_rebalancer.py`
- Test: `tests/test_schedule_rebalancer.py`

**Step 1: Write the failing test for time slot rebalancing**

Create `tests/test_schedule_rebalancer.py`:

```python
"""Tests for ScheduleRebalancer service."""
import pytest
from datetime import datetime, date, timedelta
from app.models import get_models, get_db


class TestTimeSlotRebalancing:
    """Phase 1: Time slot rebalancing within a day."""

    def setup_method(self, method):
        """Common setup for time slot tests."""
        self.models = None
        self.db = None

    def _create_employee(self, db_session, models, emp_id, name, job_title='Event Specialist'):
        Employee = models['Employee']
        emp = Employee(id=emp_id, name=name, job_title=job_title, is_active=True)
        db_session.add(emp)
        db_session.flush()
        return emp

    def _create_event(self, db_session, models, ref_num, event_type='Core', estimated_time=60):
        Event = models['Event']
        evt = Event(
            project_ref_num=ref_num,
            project_name=f'Test Event {ref_num}',
            event_type=event_type,
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 13),
            estimated_time=estimated_time
        )
        db_session.add(evt)
        db_session.flush()
        return evt

    def _create_schedule(self, db_session, models, event, employee, schedule_dt):
        Schedule = models['Schedule']
        sched = Schedule(
            event_ref_num=event.project_ref_num,
            employee_id=employee.id,
            employee_name=employee.name,
            schedule_datetime=schedule_dt
        )
        db_session.add(sched)
        db_session.flush()
        return sched

    def test_rebalance_moves_events_from_overloaded_slot(self, app, db_session, models):
        """When one time slot has 3 Core events and another has 0, rebalance moves one."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        # Create 4 employees
        emp1 = self._create_employee(db_session, models, 'E1', 'Alice')
        emp2 = self._create_employee(db_session, models, 'E2', 'Bob')
        emp3 = self._create_employee(db_session, models, 'E3', 'Carol')
        emp4 = self._create_employee(db_session, models, 'E4', 'Dave')

        # Create 4 Core events
        evt1 = self._create_event(db_session, models, 1001)
        evt2 = self._create_event(db_session, models, 1002)
        evt3 = self._create_event(db_session, models, 1003)
        evt4 = self._create_event(db_session, models, 1004)

        target_date = date(2026, 3, 9)  # Monday

        # Schedule 3 events at 07:00 and 1 at 09:00 (imbalanced)
        self._create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt3, emp3, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt4, emp4, datetime(2026, 3, 9, 9, 0))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(target_date)

        assert result['time_slot_moves'] >= 1
        assert result['moves_made'] >= 1

    def test_no_moves_when_already_balanced(self, app, db_session, models):
        """When time slots are already balanced, no moves are made."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = self._create_employee(db_session, models, 'E1', 'Alice')
        emp2 = self._create_employee(db_session, models, 'E2', 'Bob')

        evt1 = self._create_event(db_session, models, 1001)
        evt2 = self._create_event(db_session, models, 1002)

        # One event per slot — balanced
        self._create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, 9, 0))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 9))

        assert result['time_slot_moves'] == 0

    def test_skips_locked_days(self, app, db_session, models):
        """Locked days are skipped entirely during rebalancing."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        LockedDay = models.get('LockedDay')
        if not LockedDay:
            pytest.skip('LockedDay model not available')

        target_date = date(2026, 3, 9)

        # Lock the day
        locked = LockedDay(date=target_date, reason='Test lock')
        db_session.add(locked)

        emp1 = self._create_employee(db_session, models, 'E1', 'Alice')
        emp2 = self._create_employee(db_session, models, 'E2', 'Bob')
        emp3 = self._create_employee(db_session, models, 'E3', 'Carol')

        evt1 = self._create_event(db_session, models, 1001)
        evt2 = self._create_event(db_session, models, 1002)
        evt3 = self._create_event(db_session, models, 1003)

        # Imbalanced — 3 at 07:00, 0 elsewhere
        self._create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt3, emp3, datetime(2026, 3, 9, 7, 0))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(target_date)

        # No moves because day is locked
        assert result['time_slot_moves'] == 0


class TestEmployeeWorkloadRebalancing:
    """Phase 2: Employee workload rebalancing across the week."""

    def _create_employee(self, db_session, models, emp_id, name, job_title='Event Specialist'):
        Employee = models['Employee']
        emp = Employee(id=emp_id, name=name, job_title=job_title, is_active=True)
        db_session.add(emp)
        db_session.flush()
        return emp

    def _create_event(self, db_session, models, ref_num, event_type='Core', estimated_time=60):
        Event = models['Event']
        evt = Event(
            project_ref_num=ref_num,
            project_name=f'Test Event {ref_num}',
            event_type=event_type,
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 13),
            estimated_time=estimated_time
        )
        db_session.add(evt)
        db_session.flush()
        return evt

    def _create_schedule(self, db_session, models, event, employee, schedule_dt):
        Schedule = models['Schedule']
        sched = Schedule(
            event_ref_num=event.project_ref_num,
            employee_id=employee.id,
            employee_name=employee.name,
            schedule_datetime=schedule_dt
        )
        db_session.add(sched)
        db_session.flush()
        return sched

    def test_rebalance_swaps_from_overloaded_to_underloaded(self, app, db_session, models):
        """Employee with 4 Core events should lose one to employee with 0."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp_heavy = self._create_employee(db_session, models, 'E1', 'Alice')
        emp_light = self._create_employee(db_session, models, 'E2', 'Bob')

        # 4 events all assigned to emp_heavy across different days
        for i, day_offset in enumerate([0, 1, 2, 3]):
            evt = self._create_event(db_session, models, 2000 + i)
            dt = datetime(2026, 3, 9 + day_offset, 7, 0)
            self._create_schedule(db_session, models, evt, emp_heavy, dt)

        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        week_start = date(2026, 3, 8)  # Sunday
        result = rebalancer.rebalance_week(week_start)

        assert result['employee_swaps'] >= 1

        # Verify distribution improved
        Schedule = models['Schedule']
        alice_count = db_session.query(Schedule).filter(
            Schedule.employee_id == 'E1'
        ).count()
        bob_count = db_session.query(Schedule).filter(
            Schedule.employee_id == 'E2'
        ).count()

        assert abs(alice_count - bob_count) <= 1

    def test_no_swaps_when_already_balanced(self, app, db_session, models):
        """When employees have equal Core counts, no swaps happen."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = self._create_employee(db_session, models, 'E1', 'Alice')
        emp2 = self._create_employee(db_session, models, 'E2', 'Bob')

        evt1 = self._create_event(db_session, models, 2001)
        evt2 = self._create_event(db_session, models, 2002)

        self._create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, 7, 0))
        self._create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, 9, 0))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        assert result['employee_swaps'] == 0

    def test_respects_max_one_core_per_day(self, app, db_session, models):
        """Won't assign a second Core event to an employee on the same day."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = self._create_employee(db_session, models, 'E1', 'Alice')
        emp2 = self._create_employee(db_session, models, 'E2', 'Bob')

        # Alice has 3 events on 3 different days
        for i in range(3):
            evt = self._create_event(db_session, models, 3000 + i)
            self._create_schedule(db_session, models, evt, emp1,
                                  datetime(2026, 3, 9 + i, 7, 0))

        # Bob already has a Core event on day 0
        evt_bob = self._create_event(db_session, models, 3010)
        self._create_schedule(db_session, models, evt_bob, emp2,
                              datetime(2026, 3, 9, 9, 0))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        # Bob can receive events on days 1 and 2, but NOT day 0 (already has one)
        Schedule = models['Schedule']
        bob_day0 = db_session.query(Schedule).filter(
            Schedule.employee_id == 'E2',
            Schedule.schedule_datetime >= datetime(2026, 3, 9),
            Schedule.schedule_datetime < datetime(2026, 3, 10)
        ).count()
        assert bob_day0 <= 1  # Max 1 Core per day


class TestRebalanceWeekIntegration:
    """Integration tests for full rebalance_week flow."""

    def _create_employee(self, db_session, models, emp_id, name, job_title='Event Specialist'):
        Employee = models['Employee']
        emp = Employee(id=emp_id, name=name, job_title=job_title, is_active=True)
        db_session.add(emp)
        db_session.flush()
        return emp

    def _create_event(self, db_session, models, ref_num, event_type='Core', estimated_time=60):
        Event = models['Event']
        evt = Event(
            project_ref_num=ref_num,
            project_name=f'Test Event {ref_num}',
            event_type=event_type,
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 13),
            estimated_time=estimated_time
        )
        db_session.add(evt)
        db_session.flush()
        return evt

    def _create_schedule(self, db_session, models, event, employee, schedule_dt):
        Schedule = models['Schedule']
        sched = Schedule(
            event_ref_num=event.project_ref_num,
            employee_id=employee.id,
            employee_name=employee.name,
            schedule_datetime=schedule_dt
        )
        db_session.add(sched)
        db_session.flush()
        return sched

    def test_rebalance_returns_expected_structure(self, app, db_session, models):
        """Result dict has all required keys."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        assert 'moves_made' in result
        assert 'time_slot_moves' in result
        assert 'employee_swaps' in result
        assert 'skipped_reasons' in result
        assert 'details' in result

    def test_only_core_events_are_moved(self, app, db_session, models):
        """Non-Core events should never be touched by the rebalancer."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = self._create_employee(db_session, models, 'E1', 'Alice')
        emp2 = self._create_employee(db_session, models, 'E2', 'Bob')

        # Create a Juicer event at an overloaded time slot
        juicer_evt = self._create_event(db_session, models, 5001, event_type='Juicer')
        self._create_schedule(db_session, models, juicer_evt, emp1, datetime(2026, 3, 9, 7, 0))

        # Create 3 Core events at same time to trigger imbalance
        for i in range(3):
            evt = self._create_event(db_session, models, 5010 + i)
            emp = self._create_employee(db_session, models, f'E{10+i}', f'Emp{10+i}')
            self._create_schedule(db_session, models, evt, emp, datetime(2026, 3, 9, 7, 0))

        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        # Juicer event should still be at original time with original employee
        Schedule = models['Schedule']
        juicer_sched = db_session.query(Schedule).filter(
            Schedule.event_ref_num == 5001
        ).first()
        assert juicer_sched.employee_id == 'E1'
        assert juicer_sched.schedule_datetime.hour == 7
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schedule_rebalancer.py -v`
Expected: FAIL with "No module named 'app.services.schedule_rebalancer'"

**Step 3: Write the ScheduleRebalancer service**

Create `app/services/schedule_rebalancer.py`:

```python
"""
Schedule Rebalancer Service

Rebalances Core events within a week across two dimensions:
1. Time slot balance: Even distribution across daily shift block start times
2. Employee workload balance: Even distribution of Core events across eligible employees

Uses ConstraintValidator to ensure all moves respect scheduling rules.
"""
from datetime import date, datetime, timedelta, time
from typing import Dict, List, Any, Optional, Tuple

from flask import current_app
from sqlalchemy.orm import Session

from app.models import get_models


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

        # Get locked days for the week
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
            # Get unique arrive times from blocks 1-8 (active blocks)
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
            # Fallback to common Core times
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
            # Find closest matching slot
            best_slot = min(start_times, key=lambda t: abs(
                (t.hour * 60 + t.minute) - (sched_time.hour * 60 + sched_time.minute)
            ))
            slots[best_slot].append(sched)

        total = len(core_schedules)
        target_per_slot = total / len(start_times)

        # Sort slots: most overloaded first
        sorted_slots = sorted(slots.items(), key=lambda x: len(x[1]), reverse=True)

        for from_time, from_schedules in sorted_slots:
            if len(from_schedules) <= target_per_slot:
                continue

            # Find underloaded slots
            for to_time, to_schedules in sorted(slots.items(), key=lambda x: len(x[1])):
                if len(to_schedules) >= target_per_slot:
                    continue
                if from_time == to_time:
                    continue

                # Try to move one schedule from overloaded to underloaded
                for sched in list(from_schedules):
                    if len(from_schedules) <= target_per_slot:
                        break
                    if len(to_schedules) >= target_per_slot:
                        break

                    # Validate the move
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
            result = validator.validate_assignment(
                event, employee, new_dt,
                exclude_schedule_ids=[schedule.id]
            )
            # Only check hard constraint violations
            hard_violations = [v for v in result.violations
                              if v.severity.value == 'hard']
            return len(hard_violations) == 0
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

        target = len(all_core_schedules) / len(eligible)
        max_iterations = len(all_core_schedules) * 2  # Safety limit
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # Find most overloaded and most underloaded
            overloaded = max(emp_counts, key=emp_counts.get)
            underloaded = min(emp_counts, key=emp_counts.get)

            spread = emp_counts[overloaded] - emp_counts[underloaded]
            if spread <= 1:
                break  # Already balanced

            # Try to move one event from overloaded to underloaded
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

                # Validate via ConstraintValidator
                if self._can_reassign(sched, underloaded_emp):
                    old_emp_name = sched.employee_name
                    sched.employee_id = underloaded_emp.id
                    sched.employee_name = underloaded_emp.name

                    # Update tracking
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
                # No valid move found for this pair, mark and try excluding
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
            result = validator.validate_assignment(
                event, new_employee, schedule.schedule_datetime,
                exclude_schedule_ids=[schedule.id]
            )
            hard_violations = [v for v in result.violations
                              if v.severity.value == 'hard']
            return len(hard_violations) == 0
        except Exception as e:
            current_app.logger.warning(f"Constraint check failed for reassign: {e}")
            return False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schedule_rebalancer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app/services/schedule_rebalancer.py tests/test_schedule_rebalancer.py
git commit -m "feat: add ScheduleRebalancer service with time slot and employee workload rebalancing"
```

---

### Task 2: Add API endpoint for rebalancing

**Files:**
- Modify: `app/routes/api.py` (add endpoint at end of file)
- Test: `tests/test_schedule_rebalancer.py` (add API test class)

**Step 1: Write the failing test**

Append to `tests/test_schedule_rebalancer.py`:

```python
class TestRebalanceAPI:
    """Test the /api/rebalance-week endpoint."""

    def test_rebalance_endpoint_returns_200(self, client, app, db_session, models):
        """POST /api/rebalance-week returns 200 with result summary."""
        response = client.post('/api/rebalance-week', json={
            'week_start': '2026-03-08'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert 'moves_made' in data['data']
        assert 'time_slot_moves' in data['data']
        assert 'employee_swaps' in data['data']

    def test_rebalance_endpoint_missing_date(self, client, app):
        """POST /api/rebalance-week without week_start returns 400."""
        response = client.post('/api/rebalance-week', json={})
        assert response.status_code == 400

    def test_rebalance_endpoint_invalid_date(self, client, app):
        """POST /api/rebalance-week with invalid date returns 400."""
        response = client.post('/api/rebalance-week', json={
            'week_start': 'not-a-date'
        })
        assert response.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schedule_rebalancer.py::TestRebalanceAPI -v`
Expected: FAIL with 404 (endpoint doesn't exist yet)

**Step 3: Add the endpoint to api.py**

Add at the end of `app/routes/api.py`, before the final lines:

```python
@api_bp.route('/rebalance-week', methods=['POST'])
def rebalance_week():
    """Rebalance Core events for a given week."""
    from app.services.schedule_rebalancer import ScheduleRebalancer

    db = current_app.extensions['sqlalchemy']
    models_dict = {k: current_app.config[k] for k in [
        'Schedule', 'Event', 'Employee', 'LockedDay',
        'EmployeeTimeOff', 'EmployeeAvailability',
        'EmployeeWeeklyAvailability', 'CompanyHoliday',
        'PendingSchedule', 'SchedulerRunHistory'
    ] if current_app.config.get(k)}

    data = request.get_json(silent=True) or {}
    week_start_str = data.get('week_start')

    if not week_start_str:
        return jsonify({'status': 'error', 'error': 'week_start is required'}), 400

    try:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    try:
        rebalancer = ScheduleRebalancer(db.session, models_dict)
        result = rebalancer.rebalance_week(week_start)

        return jsonify({
            'status': 'success',
            'data': result
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Rebalance failed: {e}", exc_info=True)
        return jsonify({'status': 'error', 'error': str(e)}), 500
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schedule_rebalancer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app/routes/api.py tests/test_schedule_rebalancer.py
git commit -m "feat: add POST /api/rebalance-week endpoint"
```

---

### Task 3: Add Rebalance button to weekly validation UI

**Files:**
- Modify: `app/templates/dashboard/weekly_validation.html` (lines 449-462, header nav area)
- Modify: `app/static/js/pages/weekly-validation.js` (add click handler at end)

**Step 1: Add the button to the template**

In `app/templates/dashboard/weekly_validation.html`, after the Fix Wizard link (line 461), add the Rebalance button inside the `.nav-btns` div:

```html
            <button type="button" id="rebalance-week-btn"
                    class="rebalance-btn{% if result.weekly_issues %} rebalance-btn--has-issues{% endif %}"
                    data-week-start="{{ start_date.isoformat() }}"
                    title="Rebalance Core events for this week">
                <i class="fas fa-balance-scale"></i> Rebalance
            </button>
```

Add CSS for the button in the `<style>` block:

```css
    .rebalance-btn {
        background: rgba(255, 255, 255, 0.2);
        color: white;
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: 500;
        border: none;
        cursor: pointer;
        font-size: inherit;
        font-family: inherit;
    }

    .rebalance-btn:hover {
        background: rgba(255, 255, 255, 0.3);
    }

    .rebalance-btn--has-issues {
        background: rgba(255, 193, 7, 0.4);
        border: 1px solid rgba(255, 193, 7, 0.6);
    }

    .rebalance-btn--has-issues:hover {
        background: rgba(255, 193, 7, 0.5);
    }

    .rebalance-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
```

**Step 2: Add the JavaScript click handler**

Append to `app/static/js/pages/weekly-validation.js`:

```javascript
// ===== REBALANCE WEEK =====
var rebalanceBtn = document.getElementById('rebalance-week-btn');
if (rebalanceBtn) {
    rebalanceBtn.addEventListener('click', async function () {
        var weekStart = rebalanceBtn.getAttribute('data-week-start');

        if (!confirm('Rebalance Core events for this week? This will immediately move events to balance time slots and employee workloads.')) {
            return;
        }

        rebalanceBtn.disabled = true;
        rebalanceBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rebalancing...';

        try {
            var response = await fetch('/api/rebalance-week', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ week_start: weekStart })
            });

            var data = await response.json();

            if (response.ok && data.status === 'success') {
                var r = data.data;
                var msg = 'Rebalance complete: ';
                var parts = [];
                if (r.time_slot_moves > 0) parts.push(r.time_slot_moves + ' time slot move(s)');
                if (r.employee_swaps > 0) parts.push(r.employee_swaps + ' employee swap(s)');
                if (parts.length === 0) parts.push('no changes needed');
                msg += parts.join(', ');

                alert(msg);

                if (r.moves_made > 0) {
                    location.reload();
                }
            } else {
                alert('Rebalance failed: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            alert('Rebalance error: ' + err.message);
        } finally {
            rebalanceBtn.disabled = false;
            rebalanceBtn.innerHTML = '<i class="fas fa-balance-scale"></i> Rebalance';
        }
    });
}
```

**Step 3: Verify manually**

Run: `python wsgi.py` and navigate to Weekly Validation page.
Expected: "Rebalance" button visible in header. Highlighted when issues exist.

**Step 4: Run full test suite**

Run: `pytest -v --ignore=tests/test_ml_scheduling_adapter.py --ignore=tests/test_ml_training_pipeline.py --ignore=tests/test_ml_feature_engineering.py --ignore=tests/test_ml_integration.py`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app/templates/dashboard/weekly_validation.html app/static/js/pages/weekly-validation.js
git commit -m "feat: add Rebalance Week button to weekly validation UI"
```

---

### Task 4: Run full test suite and verify

**Step 1: Run all tests**

Run: `pytest -v --ignore=tests/test_ml_scheduling_adapter.py --ignore=tests/test_ml_training_pipeline.py --ignore=tests/test_ml_feature_engineering.py --ignore=tests/test_ml_integration.py`
Expected: All tests PASS (262+ existing + new rebalancer tests)

**Step 2: Manual smoke test**

1. Start server: `python wsgi.py`
2. Navigate to Weekly Validation for a week with scheduled Core events
3. Click "Rebalance" button
4. Verify confirmation dialog appears
5. Confirm and verify toast message shows results
6. Page reloads with updated validation (fewer/no imbalance warnings)
