"""
Fix Wizard Service

Translates VerificationIssue objects from the weekly validation system into
actionable FixOption objects. Provides apply_fix() to execute chosen fixes
via direct DB operations.

Usage:
    service = FixWizardService(db.session, models)
    issues = service.get_fixable_issues(start_date)
    result = service.apply_fix('reassign', {'schedule_id': 1, 'new_employee_id': 'E001'})
"""
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import func
import logging
import re

logger = logging.getLogger(__name__)


class FixActionType(str, Enum):
    REASSIGN = "reassign"
    UNSCHEDULE = "unschedule"
    RESCHEDULE = "reschedule"
    TRADE = "trade"
    ASSIGN_SUPERVISOR = "assign_supervisor"
    IGNORE = "ignore"


@dataclass
class FixOption:
    action_type: str
    description: str
    confidence: int          # 0-100
    target: Dict[str, Any]   # Payload for apply_fix()
    is_recommended: bool = False

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'description': self.description,
            'confidence': self.confidence,
            'target': self.target,
            'is_recommended': self.is_recommended,
        }


@dataclass
class FixableIssue:
    index: int
    issue: Dict[str, Any]       # VerificationIssue.to_dict()
    options: List[FixOption]
    date: Optional[str] = None  # ISO date for daily issues
    category: str = "daily"     # "daily" or "weekly"

    def to_dict(self):
        return {
            'index': self.index,
            'issue': self.issue,
            'options': [o.to_dict() for o in self.options],
            'date': self.date,
            'category': self.category,
        }


# Maps rule_name to the generator method suffix
_RULE_DISPATCHER = {
    'Employee Time Off': '_options_for_reassign',
    'Employee Availability': '_options_for_reassign',
    'Supervisor Assignment': '_options_for_supervisor_pairing',
    'Core-Supervisor Pairing': '_options_for_supervisor_pairing',
    'Freeosk Assignment': '_options_for_reassign',
    'Digital Event Assignment': '_options_for_reassign',
    'Juicer Qualification': '_options_for_reassign',
    'Club Supervisor on Core Event': '_options_for_reassign',
    'Club Supervisor on Digital Event': '_options_for_reassign',
    'Core Event Limit': '_options_for_core_limit',
    'Juicer-Core Conflict': '_options_for_juicer_core_conflict',
    'Juicer Rotation': '_options_for_reassign',
    'Core Event Time': '_options_for_reschedule_time',
    'Weekly Core Event Limit': '_options_for_weekly_limit',
    'Weekly Juicer Production Limit': '_options_for_weekly_limit',
    'Duplicate Product': '_options_for_duplicate_product',
    'Primary Lead Not Scheduled': '_options_for_reassign',
    'Primary Lead Block Assignment': '_options_for_reschedule_time',
    'Time Slot Distribution': '_options_for_time_slot_distribution',
}

# Rules that are info-only or not actionable
_IGNORE_ONLY_RULES = {
    'Shift Balance', 'Schedule Randomization', 'Event Due Tomorrow',
    'Juicer Deep Clean Conflict',
}

# Severity sort order (critical first)
_SEVERITY_ORDER = {'critical': 0, 'warning': 1, 'info': 2}


class FixWizardService:
    """
    Generates fix options for validation issues and applies selected fixes.

    Reuses:
    - WeeklyValidationService for issue detection
    - ConstraintValidator for employee filtering
    - _score_employee() from api_suggest_employees for ranking
    """

    def __init__(self, db_session, models: dict):
        self.db = db_session
        self.models = models
        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.Employee = models['Employee']
        self.IgnoredValidationIssue = models.get('IgnoredValidationIssue')

    def get_fixable_issues(self, start_date: date) -> List[FixableIssue]:
        """
        Run weekly validation and generate fix options for each issue.

        Args:
            start_date: Sunday of the week to validate

        Returns:
            Flat list of FixableIssue sorted by severity (critical first)
        """
        from app.services.weekly_validation import WeeklyValidationService

        service = WeeklyValidationService(self.db, self.models)
        result = service.validate_week(start_date)

        fixable = []
        idx = 0

        # Process daily issues
        for date_str, day_result in result.daily_results.items():
            for issue in day_result.issues:
                options = self._generate_options(issue, date_str)
                if options:
                    fixable.append(FixableIssue(
                        index=idx,
                        issue=issue.to_dict(),
                        options=options,
                        date=date_str,
                        category='daily',
                    ))
                    idx += 1

        # Process weekly issues
        for issue in result.weekly_issues:
            options = self._generate_options(issue, None)
            if options:
                fixable.append(FixableIssue(
                    index=idx,
                    issue=issue.to_dict(),
                    options=options,
                    date=None,
                    category='weekly',
                ))
                idx += 1

        # Sort: critical first, then warning, then info
        fixable.sort(key=lambda f: _SEVERITY_ORDER.get(f.issue['severity'], 9))

        # Re-index after sorting
        for i, f in enumerate(fixable):
            f.index = i

        return fixable

    def _generate_options(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Dispatch to the appropriate option generator based on rule_name.
        Every issue with options gets an IGNORE option appended.
        """
        rule = issue.rule_name

        if rule in _IGNORE_ONLY_RULES:
            return [self._ignore_option(issue, date_str)]

        method_name = _RULE_DISPATCHER.get(rule)
        if not method_name:
            # Unknown rule — offer ignore only
            return [self._ignore_option(issue, date_str)]

        generator = getattr(self, method_name, None)
        if not generator:
            return [self._ignore_option(issue, date_str)]

        options = generator(issue, date_str)

        # Mark highest-confidence option as recommended
        if options:
            best = max(options, key=lambda o: o.confidence)
            best.is_recommended = True

        # Always append ignore as last option
        options.append(self._ignore_option(issue, date_str))
        return options

    def _ignore_option(self, issue, date_str: Optional[str]) -> FixOption:
        return FixOption(
            action_type=FixActionType.IGNORE,
            description="Ignore this issue",
            confidence=0,
            target={
                'rule_name': issue.rule_name,
                'details': issue.details,
                'date': date_str,
                'message': issue.message,
                'severity': issue.severity,
            },
        )

    # ------------------------------------------------------------------
    # Option Generators
    # ------------------------------------------------------------------

    def _options_for_reassign(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Generate reassign options for issues where the current employee
        is invalid (time off, availability, role mismatch).
        """
        from app.services.constraint_validator import ConstraintValidator
        from app.routes.api_suggest_employees import _score_employee

        details = issue.details
        schedule_id = details.get('schedule_id')
        if not schedule_id:
            return [self._unschedule_option_from_details(details)]

        schedule = self.db.query(self.Schedule).get(schedule_id)
        if not schedule:
            return []

        event = self.db.query(self.Event).filter_by(
            project_ref_num=schedule.event_ref_num
        ).first()
        if not event:
            return []

        validator = ConstraintValidator(self.db, self.models)
        available = validator.get_available_employees(event, schedule.schedule_datetime)

        # Exclude the currently assigned employee
        available = [e for e in available if str(e.id) != str(schedule.employee_id)]

        options = []
        for emp in available[:8]:  # Limit to top 8 candidates
            score, reason = _score_employee(
                emp, event, schedule.schedule_datetime, self.db, self.models
            )
            options.append(FixOption(
                action_type=FixActionType.REASSIGN,
                description=f"Reassign to {emp.name} ({emp.job_title}, score: {score})",
                confidence=min(score, 100),
                target={
                    'schedule_id': schedule_id,
                    'new_employee_id': str(emp.id),
                    'employee_name': emp.name,
                },
            ))

        # Sort by confidence descending
        options.sort(key=lambda o: o.confidence, reverse=True)

        # Fallback: unschedule
        options.append(FixOption(
            action_type=FixActionType.UNSCHEDULE,
            description=f"Unschedule this event (set to Unstaffed)",
            confidence=10,
            target={
                'schedule_id': schedule_id,
                'event_ref_num': schedule.event_ref_num,
            },
        ))

        return options

    def _unschedule_option_from_details(self, details: dict) -> FixOption:
        schedule_id = details.get('schedule_id')
        return FixOption(
            action_type=FixActionType.UNSCHEDULE,
            description="Unschedule this event (set to Unstaffed)",
            confidence=10,
            target={
                'schedule_id': schedule_id,
                'event_ref_num': details.get('event_id'),
            },
        )

    def _options_for_core_limit(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Employee has too many Core events on a single day.
        Offer to unschedule or reassign each extra Core event.
        """
        details = issue.details
        employee_id = details.get('employee_id')
        if not employee_id or not date_str:
            return []

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Get all Core schedules for this employee on this date
        core_schedules = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Schedule.employee_id == employee_id,
            self.Event.event_type == 'Core',
        ).order_by(self.Schedule.schedule_datetime).all()

        if len(core_schedules) <= 1:
            return []

        # Keep the first one, offer to unschedule the rest
        options = []
        for sched in core_schedules[1:]:
            event = self.db.query(self.Event).filter_by(
                project_ref_num=sched.event_ref_num
            ).first()
            event_name = event.project_name if event else f"Event #{sched.event_ref_num}"

            options.append(FixOption(
                action_type=FixActionType.UNSCHEDULE,
                description=f"Unschedule extra Core: {event_name}",
                confidence=60,
                target={
                    'schedule_id': sched.id,
                    'event_ref_num': sched.event_ref_num,
                },
            ))

        return options

    def _options_for_supervisor_pairing(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Core event is missing its paired Supervisor event.
        Offer to auto-assign a Supervisor.
        """
        details = issue.details
        core_event_ref = details.get('core_event_ref') or details.get('event_id')
        if not core_event_ref:
            return []

        options = [
            FixOption(
                action_type=FixActionType.ASSIGN_SUPERVISOR,
                description="Auto-assign Supervisor event to best available employee",
                confidence=75,
                target={
                    'core_event_ref': core_event_ref,
                    'date': date_str,
                },
            ),
        ]
        return options

    def _options_for_juicer_core_conflict(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Employee has both Juicer and Core on the same day.
        Offer to unschedule either one.
        """
        details = issue.details
        options = []

        juicer_schedule_id = details.get('juicer_schedule_id')
        core_schedule_id = details.get('core_schedule_id') or details.get('schedule_id')

        if juicer_schedule_id:
            options.append(FixOption(
                action_type=FixActionType.UNSCHEDULE,
                description="Unschedule the Juicer event",
                confidence=40,
                target={
                    'schedule_id': juicer_schedule_id,
                },
            ))

        if core_schedule_id:
            options.append(FixOption(
                action_type=FixActionType.UNSCHEDULE,
                description="Unschedule the Core event",
                confidence=50,
                target={
                    'schedule_id': core_schedule_id,
                },
            ))

        return options

    def _options_for_reschedule_time(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Event is at the wrong time (e.g., Primary Lead not in Block 1).
        Offer to reschedule to valid time slots.
        """
        from app.services.shift_block_config import ShiftBlockConfig

        details = issue.details
        schedule_id = details.get('schedule_id')

        # For Primary Lead issues, find the schedule
        if not schedule_id and details.get('employee_id') and date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            sched = self.db.query(self.Schedule).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                func.date(self.Schedule.schedule_datetime) == target_date,
                self.Schedule.employee_id == details['employee_id'],
                self.Event.event_type == 'Core',
            ).first()
            if sched:
                schedule_id = sched.id

        if not schedule_id:
            return []

        schedule = self.db.query(self.Schedule).get(schedule_id)
        if not schedule:
            return []

        options = []
        blocks = ShiftBlockConfig.get_all_blocks()

        for block in blocks[:8]:  # Only standard blocks
            block_time = block.get('arrive')
            if not block_time:
                continue

            # Skip current time
            current_time = schedule.schedule_datetime.time()
            if (block_time.hour == current_time.hour and
                    block_time.minute == current_time.minute):
                continue

            new_dt = datetime.combine(schedule.schedule_datetime.date(), block_time)
            time_str = block_time.strftime('%I:%M %p')
            block_num = block.get('block', '?')

            # Block 1 gets higher confidence for Primary Lead issues
            confidence = 70 if block_num == 1 else 40

            options.append(FixOption(
                action_type=FixActionType.RESCHEDULE,
                description=f"Reschedule to Block {block_num} ({time_str})",
                confidence=confidence,
                target={
                    'schedule_id': schedule_id,
                    'new_datetime': new_dt.isoformat(),
                },
            ))

        return options

    def _options_for_weekly_limit(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Employee exceeds weekly Core or Juicer limit.
        Offer to unschedule individual events from the week.
        """
        details = issue.details
        employee_id = details.get('employee_id')
        week_start = details.get('week_start')
        week_end = details.get('week_end')

        if not employee_id or not week_start or not week_end:
            return []

        start = datetime.strptime(week_start, '%Y-%m-%d').date()
        end = datetime.strptime(week_end, '%Y-%m-%d').date()

        # Determine event type from rule
        event_type = 'Core' if 'Core' in issue.rule_name else 'Juicer Production'

        schedules = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) >= start,
            func.date(self.Schedule.schedule_datetime) <= end,
            self.Schedule.employee_id == employee_id,
            self.Event.event_type == event_type,
        ).order_by(self.Schedule.schedule_datetime).all()

        options = []
        for sched in schedules:
            event = self.db.query(self.Event).filter_by(
                project_ref_num=sched.event_ref_num
            ).first()
            event_name = event.project_name if event else f"Event #{sched.event_ref_num}"
            sched_date = sched.schedule_datetime.strftime('%a %m/%d')

            options.append(FixOption(
                action_type=FixActionType.UNSCHEDULE,
                description=f"Unschedule {event_name} ({sched_date})",
                confidence=45,
                target={
                    'schedule_id': sched.id,
                    'event_ref_num': sched.event_ref_num,
                },
            ))

        return options

    def _options_for_duplicate_product(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Same product scheduled multiple times on the same day.
        Offer to unschedule duplicates.
        """
        details = issue.details
        events_list = details.get('events', [])

        if len(events_list) < 2:
            return []

        options = []
        # Keep the first, offer to unschedule the rest
        for ev in events_list[1:]:
            options.append(FixOption(
                action_type=FixActionType.UNSCHEDULE,
                description=f"Unschedule duplicate: {ev.get('event_name', 'Unknown')}",
                confidence=55,
                target={
                    'schedule_id': ev.get('schedule_id'),
                    'event_ref_num': ev.get('event_id'),
                },
            ))

        return options

    def _options_for_time_slot_distribution(self, issue, date_str: Optional[str]) -> List[FixOption]:
        """
        Core events are unevenly distributed across time slots.
        Identifies overstaffed slots and offers to reschedule those
        schedules into understaffed slots.

        The ideal pattern is non-increasing counts with at most 1
        difference between adjacent slots (e.g. [2,2,2,1] not [3,1,2,1]).
        """
        from app.services.shift_block_config import ShiftBlockConfig
        from collections import defaultdict

        details = issue.details
        if not date_str:
            return []

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        distribution = details.get('distribution', {})  # {'10:15': 3, '11:30': 1, ...}
        total_events = details.get('total_events', 0)

        if not distribution or total_events == 0:
            return []

        # Get all Core schedules for this date grouped by time
        core_schedules = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Event.event_type == 'Core',
        ).order_by(self.Schedule.schedule_datetime).all()

        if not core_schedules:
            return []

        # Build the ideal distribution: fill 2 per slot in order, then repeat
        all_blocks = ShiftBlockConfig.get_all_blocks()[:8]
        block_times = []
        seen = set()
        for b in all_blocks:
            arrive = b.get('arrive')
            if arrive:
                time_key = arrive.strftime('%H:%M')
                if time_key not in seen:
                    seen.add(time_key)
                    block_times.append((time_key, arrive))

        num_slots = len(block_times) if block_times else 4
        ideal = [0] * num_slots
        remaining = total_events
        while remaining > 0:
            for i in range(num_slots):
                if remaining <= 0:
                    break
                ideal[i] += 1
                remaining -= 1

        # Map current time slots to their counts
        slot_order = sorted(distribution.keys())
        current = {s: distribution[s] for s in slot_order}

        # Find overstaffed slots (more than ideal) and understaffed slots
        # Pair slot_order positions with ideal positions
        overstaffed_slots = []
        understaffed_slots = []
        for i, slot_key in enumerate(slot_order):
            ideal_count = ideal[i] if i < len(ideal) else 0
            actual_count = current[slot_key]
            if actual_count > ideal_count:
                overstaffed_slots.append((slot_key, actual_count - ideal_count))
            elif actual_count < ideal_count:
                understaffed_slots.append((slot_key, ideal_count - actual_count))

        # Also add block times that have zero events (not in distribution at all)
        for i, (time_key, _) in enumerate(block_times):
            if time_key not in current and i < len(ideal) and ideal[i] > 0:
                understaffed_slots.append((time_key, ideal[i]))

        if not overstaffed_slots or not understaffed_slots:
            return []

        # Group schedules by time slot
        schedules_by_slot = defaultdict(list)
        for sched in core_schedules:
            time_key = sched.schedule_datetime.strftime('%H:%M')
            schedules_by_slot[time_key].append(sched)

        # For each excess schedule in overstaffed slots, offer to move
        # it to an understaffed slot
        options = []
        for over_slot, excess in overstaffed_slots:
            slot_schedules = schedules_by_slot.get(over_slot, [])
            # Take the last N schedules from this slot (keep the earlier ones)
            movable = slot_schedules[-excess:]

            for sched in movable:
                event = self.db.query(self.Event).filter_by(
                    project_ref_num=sched.event_ref_num
                ).first()
                event_name = event.project_name if event else f"Event #{sched.event_ref_num}"
                from_time = sched.schedule_datetime.strftime('%I:%M %p')

                for under_slot, _ in understaffed_slots:
                    # Find the actual time object for this slot
                    to_time_obj = None
                    for time_key, arrive in block_times:
                        if time_key == under_slot:
                            to_time_obj = arrive
                            break

                    if not to_time_obj:
                        # Parse from the slot key
                        h, m = under_slot.split(':')
                        from datetime import time as dt_time
                        to_time_obj = dt_time(int(h), int(m))

                    new_dt = datetime.combine(target_date, to_time_obj)
                    to_time_str = to_time_obj.strftime('%I:%M %p')

                    options.append(FixOption(
                        action_type=FixActionType.RESCHEDULE,
                        description=f"Move {event_name} from {from_time} to {to_time_str}",
                        confidence=65,
                        target={
                            'schedule_id': sched.id,
                            'new_datetime': new_dt.isoformat(),
                        },
                    ))

        return options

    # ------------------------------------------------------------------
    # Apply Fix
    # ------------------------------------------------------------------

    def apply_fix(self, action_type: str, target: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a chosen fix option.

        Args:
            action_type: One of FixActionType values
            target: Payload dict from FixOption.target

        Returns:
            {'success': True/False, 'message': '...'}
        """
        try:
            if action_type == FixActionType.REASSIGN:
                return self._apply_reassign(target)
            elif action_type == FixActionType.UNSCHEDULE:
                return self._apply_unschedule(target)
            elif action_type == FixActionType.RESCHEDULE:
                return self._apply_reschedule(target)
            elif action_type == FixActionType.ASSIGN_SUPERVISOR:
                return self._apply_assign_supervisor(target)
            elif action_type == FixActionType.IGNORE:
                return self._apply_ignore(target)
            else:
                return {'success': False, 'message': f'Unknown action type: {action_type}'}
        except Exception as e:
            self.db.rollback()
            logger.error(f"apply_fix failed: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}

    def _apply_reassign(self, target: dict) -> dict:
        schedule_id = target.get('schedule_id')
        new_employee_id = target.get('new_employee_id')

        if not schedule_id or not new_employee_id:
            return {'success': False, 'message': 'schedule_id and new_employee_id required'}

        schedule = self.db.query(self.Schedule).get(schedule_id)
        if not schedule:
            return {'success': False, 'message': f'Schedule {schedule_id} not found'}

        old_employee_id = schedule.employee_id
        schedule.employee_id = new_employee_id
        self.db.commit()

        new_emp = self.db.query(self.Employee).get(new_employee_id)
        emp_name = new_emp.name if new_emp else new_employee_id

        return {
            'success': True,
            'message': f'Reassigned to {emp_name}',
            'old_employee_id': old_employee_id,
            'new_employee_id': new_employee_id,
        }

    def _apply_unschedule(self, target: dict) -> dict:
        schedule_id = target.get('schedule_id')
        if not schedule_id:
            return {'success': False, 'message': 'schedule_id required'}

        schedule = self.db.query(self.Schedule).get(schedule_id)
        if not schedule:
            return {'success': False, 'message': f'Schedule {schedule_id} not found'}

        event_ref = schedule.event_ref_num

        # Check for paired Supervisor — if unscheduling a Core, also unschedule its Supervisor
        event = self.db.query(self.Event).filter_by(
            project_ref_num=event_ref
        ).first()

        self.db.delete(schedule)

        # Reset event status
        if event:
            event.condition = 'Unstaffed'
            event.is_scheduled = False

            # If Core, find and unschedule paired Supervisor
            if event.event_type == 'Core':
                match = re.search(r'\d{6}', event.project_name or '')
                if match:
                    event_number = match.group(0)
                    sup_event = self.db.query(self.Event).filter(
                        self.Event.event_type == 'Supervisor',
                        self.Event.project_name.contains(event_number),
                    ).first()
                    if sup_event:
                        sup_sched = self.db.query(self.Schedule).filter_by(
                            event_ref_num=sup_event.project_ref_num
                        ).first()
                        if sup_sched:
                            self.db.delete(sup_sched)
                        sup_event.condition = 'Unstaffed'
                        sup_event.is_scheduled = False

        self.db.commit()
        return {'success': True, 'message': 'Schedule removed'}

    def _apply_reschedule(self, target: dict) -> dict:
        schedule_id = target.get('schedule_id')
        new_datetime_str = target.get('new_datetime')

        if not schedule_id or not new_datetime_str:
            return {'success': False, 'message': 'schedule_id and new_datetime required'}

        schedule = self.db.query(self.Schedule).get(schedule_id)
        if not schedule:
            return {'success': False, 'message': f'Schedule {schedule_id} not found'}

        new_dt = datetime.fromisoformat(new_datetime_str)
        old_dt = schedule.schedule_datetime
        schedule.schedule_datetime = new_dt
        self.db.commit()

        return {
            'success': True,
            'message': f'Rescheduled from {old_dt.strftime("%I:%M %p")} to {new_dt.strftime("%I:%M %p")}',
        }

    def _apply_assign_supervisor(self, target: dict) -> dict:
        """
        Assign a Supervisor event for a Core event.
        Logic extracted from dashboard.py:assign_supervisor_event.
        """
        core_event_ref = target.get('core_event_ref')
        date_str = target.get('date')

        if not core_event_ref or not date_str:
            return {'success': False, 'message': 'core_event_ref and date required'}

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        core_event = self.db.query(self.Event).filter_by(
            project_ref_num=core_event_ref
        ).first()
        if not core_event:
            return {'success': False, 'message': 'Core event not found'}

        # Extract 6-digit event number
        match = re.search(r'\d{6}', core_event.project_name or '')
        if not match:
            return {'success': False, 'message': 'Could not extract event number'}

        event_number = match.group(0)

        sup_event = self.db.query(self.Event).filter(
            self.Event.event_type == 'Supervisor',
            self.Event.project_name.contains(event_number),
        ).first()
        if not sup_event:
            return {'success': False, 'message': f'No Supervisor event found for {event_number}'}

        # Check if already scheduled
        existing = self.db.query(self.Schedule).filter_by(
            event_ref_num=sup_event.project_ref_num
        ).first()
        if existing:
            return {'success': False, 'message': 'Supervisor event already scheduled'}

        # Get Core schedule for timing
        core_sched = self.db.query(self.Schedule).filter_by(
            event_ref_num=core_event_ref
        ).first()
        if not core_sched:
            return {'success': False, 'message': 'Core event not scheduled'}

        sup_datetime = core_sched.schedule_datetime + timedelta(minutes=30)

        # Find best employee: Club Supervisor > Lead > Core employee
        EmployeeTimeOff = self.models.get('EmployeeTimeOff')
        RotationAssignment = self.models.get('RotationAssignment')

        def _is_available(emp):
            if EmployeeTimeOff:
                on_off = self.db.query(EmployeeTimeOff).filter(
                    EmployeeTimeOff.employee_id == emp.id,
                    EmployeeTimeOff.start_date <= target_date,
                    EmployeeTimeOff.end_date >= target_date,
                ).first()
                if on_off:
                    return False
            return True

        sup_employee = None

        # Try Club Supervisor
        club_sup = self.db.query(self.Employee).filter_by(
            job_title='Club Supervisor', is_active=True
        ).first()
        if club_sup and _is_available(club_sup):
            sup_employee = club_sup

        # Try rotation Primary Lead
        if not sup_employee and RotationAssignment:
            rot = self.db.query(RotationAssignment).filter_by(
                day_of_week=target_date.weekday(),
                rotation_type='primary_lead',
            ).first()
            if rot:
                lead = self.db.query(self.Employee).get(rot.employee_id)
                if lead and _is_available(lead):
                    sup_employee = lead

        # Fallback to Core employee
        if not sup_employee and core_sched.employee_id:
            core_emp = self.db.query(self.Employee).get(core_sched.employee_id)
            if core_emp:
                sup_employee = core_emp

        if not sup_employee:
            return {'success': False, 'message': 'No suitable employee for Supervisor event'}

        new_sched = self.Schedule(
            event_ref_num=sup_event.project_ref_num,
            employee_id=sup_employee.id,
            schedule_datetime=sup_datetime,
        )
        self.db.add(new_sched)
        sup_event.condition = 'Scheduled'
        sup_event.is_scheduled = True
        self.db.commit()

        return {
            'success': True,
            'message': f'Supervisor assigned to {sup_employee.name}',
        }

    def _apply_ignore(self, target: dict) -> dict:
        """Create an IgnoredValidationIssue record."""
        if not self.IgnoredValidationIssue:
            return {'success': True, 'message': 'Issue skipped (no ignore model)'}

        rule_name = target.get('rule_name', '')
        details = target.get('details', {})
        issue_hash = self.IgnoredValidationIssue.generate_hash(rule_name, details)

        # Check if already ignored
        existing = self.db.query(self.IgnoredValidationIssue).filter_by(
            issue_hash=issue_hash
        ).first()
        if existing:
            return {'success': True, 'message': 'Already ignored'}

        record = self.IgnoredValidationIssue(
            rule_name=rule_name,
            issue_hash=issue_hash,
            message=target.get('message'),
            severity=target.get('severity'),
            issue_date=datetime.strptime(target['date'], '%Y-%m-%d').date() if target.get('date') else None,
            schedule_id=details.get('schedule_id'),
            employee_id=details.get('employee_id'),
            event_id=details.get('event_id'),
        )
        self.db.add(record)
        self.db.commit()

        return {'success': True, 'message': 'Issue ignored'}
