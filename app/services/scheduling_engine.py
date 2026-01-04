"""
Scheduling Engine - Core Auto-Scheduler Logic
Orchestrates the automatic scheduling process
"""
from datetime import datetime, timedelta, time, date
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from flask import current_app

from .rotation_manager import RotationManager
from .constraint_validator import ConstraintValidator
from .conflict_resolver import ConflictResolver
from .validation_types import SchedulingDecision


class SchedulingEngine:
    """
    Core auto-scheduler orchestrator

    Process:
    1. Filter events within 3-week window
    2. Sort by priority (due date, event type)
    3. Phase 1: Schedule rotation-based events (Juicer, Digital)
    4. Phase 2: Schedule Core events (Leads first, then Specialists)
    5. Phase 3: Auto-pair Supervisor events with Core events
    6. Generate PendingSchedule records for user approval
    """

    # Event scheduling window in days
    SCHEDULING_WINDOW_DAYS = 3  # 3 days ahead

    # Event type priority order (lower = higher priority)
    EVENT_TYPE_PRIORITY = {
        'Juicer': 1,
        'Digital Setup': 2,
        'Digital Refresh': 3,
        'Freeosk': 4,
        'Digital Teardown': 5,
        'Core': 6,
        'Supervisor': 7,
        'Digitals': 8,
        'Other': 9
    }

    # Load scheduling times from database settings (with fallback defaults)
    @classmethod
    def _get_default_times(cls):
        """Get default scheduling times from database settings"""
        from app.services.event_time_settings import (
            get_freeosk_times, get_digital_setup_slots,
            get_supervisor_times, get_digital_teardown_slots, get_other_times
        )
        from app.services.shift_block_config import ShiftBlockConfig

        try:
            freeosk = get_freeosk_times()
            digital_setup_slots = get_digital_setup_slots()
            # Use new 8-block system for Core events
            shift_blocks = ShiftBlockConfig.get_all_blocks()
            supervisor = get_supervisor_times()
            digital_teardown_slots = get_digital_teardown_slots()
            other = get_other_times()

            # Default Core time is the first shift block's ARRIVE time (time stored in MVRetail)
            # on_floor time is only for EDR display
            core_start = shift_blocks[0]['arrive'] if shift_blocks else time(10, 15)

            return {
                'Juicer Production': time(9, 0),     # 9 AM - JUICER-PRODUCTION-SPCLTY
                'Juicer Survey': time(17, 0),        # 5 PM - Juicer Survey
                'Juicer': time(9, 0),                # 9 AM - Default for other Juicer events
                'Digital Setup': digital_setup_slots[0]['start'],
                'Digital Refresh': digital_setup_slots[0]['start'],
                'Freeosk': freeosk['start'],
                'Digital Teardown': digital_teardown_slots[0]['start'],
                'Core': core_start,
                'Supervisor': supervisor['start'],
                'Other': other['start']
            }
        except Exception as e:
            # Fallback to hard-coded defaults if settings not available
            return {
                'Juicer Production': time(9, 0),   # 480 min + 60 min lunch = 540 min
                'Juicer Survey': time(17, 0),      # 30 min
                'Juicer': time(9, 0),
                'Digital Setup': time(10, 15),     # 30 min
                'Digital Refresh': time(10, 15),   # 30 min
                'Freeosk': time(10, 0),            # 30 min
                'Digital Teardown': time(18, 0),   # 30 min
                'Core': time(10, 15),              # First shift block ARRIVE time
                'Supervisor': time(12, 0),         # 5 min
                'Other': time(11, 0)               # 60 min
            }

    @classmethod
    def _get_core_time_slots(cls):
        """Get Core event time slots from 8-block shift system"""
        from app.services.shift_block_config import ShiftBlockConfig

        try:
            # Use new 8-block system - arrive times are the scheduling times
            # on_floor times are only displayed on EDRs
            blocks = ShiftBlockConfig.get_all_blocks()
            # Return in sequential order (1-8) for first 8 assignments
            ordered_blocks = []
            for block_num in ShiftBlockConfig.BLOCK_SEQUENTIAL_ORDER:
                block = ShiftBlockConfig.get_block(block_num)
                if block:
                    ordered_blocks.append(block['arrive'])
            return ordered_blocks if ordered_blocks else [time(10, 15), time(10, 15), time(10, 45), time(10, 45),
                    time(11, 15), time(11, 15), time(11, 45), time(11, 45)]
        except Exception:
            # Fallback to hard-coded defaults matching arrive times
            return [time(10, 15), time(10, 15), time(10, 45), time(10, 45),
                    time(11, 15), time(11, 15), time(11, 45), time(11, 45)]

    @classmethod
    def _get_digital_time_slots(cls):
        """Get Digital Setup time slots from database settings"""
        from app.services.event_time_settings import get_digital_setup_slots

        try:
            slots = get_digital_setup_slots()
            return [slot['start'] for slot in slots]
        except Exception:
            # Fallback to hard-coded defaults (moved forward 1 hour from 9:15)
            return [time(10, 15), time(10, 30), time(10, 45), time(11, 0)]

    @classmethod
    def _get_teardown_time_slots(cls):
        """Get Digital Teardown time slots from database settings"""
        from app.services.event_time_settings import get_digital_teardown_slots

        try:
            slots = get_digital_teardown_slots()
            return [slot['start'] for slot in slots]
        except Exception:
            # Fallback to hard-coded defaults (moved forward 1 hour from 17:00)
            return [
                time(18, 0), time(18, 15), time(18, 30), time(18, 45),
                time(19, 0), time(19, 15), time(19, 30), time(19, 45)
            ]

    def __init__(self, db_session: Session, models: dict):
        """
        Initialize SchedulingEngine

        Args:
            db_session: SQLAlchemy database session
            models: Dictionary of model classes from app.config
        """
        self.db = db_session
        self.models = models

        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.Employee = models['Employee']
        self.SchedulerRunHistory = models['SchedulerRunHistory']
        self.PendingSchedule = models['PendingSchedule']
        self.EmployeeTimeOff = models['EmployeeTimeOff']
        self.EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

        # Initialize service dependencies
        self.rotation_manager = RotationManager(db_session, models)
        self.validator = ConstraintValidator(db_session, models)
        self.conflict_resolver = ConflictResolver(db_session, models)

        # Track bump count per event to prevent infinite loops
        # Key: event.project_ref_num, Value: bump count
        self.bump_count = {}
        self.MAX_BUMPS_PER_EVENT = 3  # Maximum times an event can be bumped

        # Track time slot rotation per day
        self.daily_time_slot_index = {}  # {date_str: slot_index} for Core events
        self.digital_time_slot_index = {}  # {date_str: slot_index} for Digital Setup/Refresh
        self.teardown_time_slot_index = {}  # {date_str: slot_index} for Digital Teardown

        # Load time settings from database
        self.DEFAULT_TIMES = self._get_default_times()
        self.CORE_TIME_SLOTS = self._get_core_time_slots()
        self.DIGITAL_TIME_SLOTS = self._get_digital_time_slots()
        self.TEARDOWN_TIME_SLOTS = self._get_teardown_time_slots()

    def run_auto_scheduler(self, run_type: str = 'manual') -> object:
        """
        Main entry point for auto-scheduler

        Scheduling Waves (CORRECTED - Juicer events scheduled FIRST):
        Wave 1: Juicer events → Juicer Baristas (rotation-based, can bump Core events)
        Wave 2: Core events → 3 Subwaves:
                2.1: Lead Event Specialists (priority - fill their available days first)
                2.2: Juicer Baristas (when not juicing that day)
                2.3: Event Specialists
                NOTE: Supervisor events are scheduled INLINE with Core events
        Wave 3: Freeosk → Primary Lead → Other Leads → Club Supervisor
        Wave 4: Digitals (Setup/Refresh/Teardown) → Primary/Secondary Lead → Club Supervisor
        Wave 5: Other events → Club Supervisor → ANY Lead Event Specialist

        Args:
            run_type: 'automatic' or 'manual'

        Returns:
            SchedulerRunHistory object
        """
        # Create run history record
        run = self.SchedulerRunHistory(
            run_type=run_type,
            started_at=datetime.utcnow(),
            status='running'
        )
        self.db.add(run)
        self.db.flush()

        # Set current run ID in validator to check pending schedules
        self.validator.set_current_run(run.id)

        try:
            # Get events to schedule
            events = self._get_unscheduled_events()
            run.total_events_processed = len(events)

            # Sort by priority (due date first, then event type)
            events = self._sort_events_by_priority(events)

            # CORRECTED WAVE ORDER (per user requirements - Juicer FIRST, then Core):

            # Wave 1: Juicer events (HIGHEST PRIORITY - can bump Core events if assigned)
            #         Uses _schedule_juicer_events_wave1() which has bumping logic
            self._schedule_juicer_events_wave1(run, events)

            # Wave 2: Core events (NEW day-by-day bump-first logic with cascading)
            #         Supervisor events are scheduled INLINE with Core events
            failed_core_events = self._schedule_core_events_wave2_new(run, events)

            # ORPHANED SUPERVISOR PASS: Schedule Supervisor events whose Core was scheduled previously
            current_app.logger.info("=== ORPHANED SUPERVISOR PASS: Scheduling remaining Supervisor events ===")
            self._schedule_orphaned_supervisor_events(run, events)

            # Wave 3: Freeosk events (9:00 AM to Leads)
            self._schedule_freeosk_events_wave3(run, events)

            # Wave 4: Digital events (Setup/Refresh at 9:15-10:00, Teardown at 5:00 PM+)
            self._schedule_digital_events_wave4(run, events)

            # Wave 5: Other events (Noon to Club Supervisor or Lead)
            self._schedule_other_events_wave5(run, events)

            # RESCUE PASS: Give failed urgent Core events another chance to bump less urgent ones
            # This handles the case where an urgent event was processed first (before less urgent
            # events were scheduled) and couldn't find anything to bump
            current_app.logger.info("=== RESCUE PASS: Attempting to schedule failed urgent Core events ===")
            self._rescue_pass_for_urgent_events(run, events)

            # Mark run as completed
            run.completed_at = datetime.utcnow()
            run.status = 'completed'
            self.db.commit()

            return run

        except Exception as e:
            run.status = 'failed'
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            self.db.commit()
            raise

    def _get_unscheduled_events(self) -> List[object]:
        """
        Get ALL unscheduled/unstaffed events that are not expired

        Returns all unscheduled events that:
        1. Are not scheduled/unstaffed
        2. Have not passed their due date (not expired)

        The scheduling logic will ensure the earliest assignment date is 3 days from today.

        Returns:
            List of Event objects that are unscheduled/unstaffed and not expired
        """
        today = datetime.now()

        events = self.db.query(self.Event).filter(
            and_(
                self.Event.is_scheduled == False,  # Only unscheduled events
                self.Event.condition == 'Unstaffed',  # Only unstaffed events
                self.Event.due_datetime >= today  # Only events that haven't expired yet
            )
        ).all()

        current_app.logger.info(f"Found {len(events)} unscheduled events (expired events filtered out)")
        return events

    def _sort_events_by_priority(self, events: List[object]) -> List[object]:
        """
        Sort events by priority (due date first, then event type)

        Args:
            events: List of Event objects

        Returns:
            Sorted list of Event objects
        """
        def priority_key(event):
            # Primary sort: due date (earlier = higher priority)
            days_until_due = (event.due_datetime - datetime.now()).days

            # Secondary sort: event type priority
            type_priority = self.EVENT_TYPE_PRIORITY.get(event.event_type, 99)

            return (days_until_due, type_priority)

        return sorted(events, key=priority_key)

    def _get_earliest_schedule_date(self, event: object) -> datetime:
        """
        Get the earliest date this event can be scheduled

        The earliest date is the later of:
        1. Event's start_datetime
        2. Today + SCHEDULING_WINDOW_DAYS (3 days from today)

        This ensures the auto-scheduler doesn't schedule events within the 3-day buffer.

        Args:
            event: Event object

        Returns:
            datetime: Earliest date this event can be scheduled
        """
        today = datetime.now().date()
        earliest_allowed = today + timedelta(days=self.SCHEDULING_WINDOW_DAYS)
        earliest_allowed_datetime = datetime.combine(earliest_allowed, time(0, 0))

        # Return the later of the two dates
        if event.start_datetime >= earliest_allowed_datetime:
            return event.start_datetime
        else:
            return earliest_allowed_datetime

    def _is_datetime_valid_for_event(self, event: object, schedule_datetime: datetime) -> bool:
        """
        Check if a schedule datetime is within the event's valid period

        STRICT RULES:
        - Schedule Date must be >= Start Date (on or after)
        - Schedule Date must be < Due Date (strictly before, not on)

        Args:
            event: Event object
            schedule_datetime: Proposed schedule datetime

        Returns:
            bool: True if the datetime is within [start_datetime, due_datetime), False otherwise
        """
        if not schedule_datetime:
            return False

        return event.start_datetime <= schedule_datetime < event.due_datetime

    def _try_move_event_forward(self, run: object, event_to_move: object, current_schedule: object,
                                 earliest_allowed_date: datetime, employee: object) -> bool:
        """
        Try to move a scheduled event to an earlier date (forward in time).

        This is called when a more urgent event needs the current slot. Instead of just
        unscheduling and hoping for the best, we proactively try to find an earlier slot
        for the less urgent event.

        Args:
            run: Current scheduler run
            event_to_move: Event that needs to be moved forward
            current_schedule: Current PendingSchedule for the event
            earliest_allowed_date: Earliest date to try (usually new_event's start_date)
            employee: Employee currently assigned to event_to_move

        Returns:
            bool: True if successfully moved to an earlier date, False otherwise
        """
        current_app.logger.info(
            f"FORWARD MOVE: Attempting to move event {event_to_move.project_ref_num} "
            f"forward from {current_schedule.schedule_datetime.strftime('%Y-%m-%d')} to an earlier date"
        )

        # Determine the date range to search
        # Start from the later of: earliest_allowed_date or event's start_date
        search_start = max(earliest_allowed_date, event_to_move.start_datetime)
        # End before the current schedule date (we're moving forward)
        search_end = current_schedule.schedule_datetime

        if search_start >= search_end:
            current_app.logger.info(
                f"FORWARD MOVE: No earlier dates available for event {event_to_move.project_ref_num}"
            )
            return False

        # Try each date from search_start to search_end
        current_date = search_start
        while current_date < search_end:
            # Try the same time slot as the current schedule
            time_slot = current_schedule.schedule_datetime.time()
            new_schedule_datetime = datetime.combine(current_date.date(), time_slot)

            # Check if this datetime is valid for the event
            if not self._is_datetime_valid_for_event(event_to_move, new_schedule_datetime):
                current_date += timedelta(days=1)
                continue

            # If employee is a Juicer, check they don't have a Juicer event on this day
            if employee.job_title == 'Juicer Barista':
                juicer_event_that_day = self.db.query(self.PendingSchedule).join(
                    self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    self.PendingSchedule.scheduler_run_id == run.id,
                    self.PendingSchedule.employee_id == employee.id,
                    func.date(self.PendingSchedule.schedule_datetime) == new_schedule_datetime.date(),
                    self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
                ).first()

                if juicer_event_that_day:
                    current_date += timedelta(days=1)
                    continue

            # Check if employee is available at this datetime
            validation = self.validator.validate_assignment(event_to_move, employee, new_schedule_datetime)
            if validation.is_valid:
                # Success! Move the event to this earlier date
                current_app.logger.info(
                    f"FORWARD MOVE: Successfully moving event {event_to_move.project_ref_num} "
                    f"from {current_schedule.schedule_datetime.strftime('%Y-%m-%d')} "
                    f"to {new_schedule_datetime.strftime('%Y-%m-%d %I:%M %p')}"
                )

                # Update the existing schedule to the new datetime
                old_date = current_schedule.schedule_datetime.date()
                current_schedule.schedule_datetime = new_schedule_datetime
                current_schedule.schedule_time = time_slot
                self.db.flush()

                # Also move any matching Supervisor event to the new date
                self._move_matching_supervisor_event(run, event_to_move, old_date, new_schedule_datetime.date())

                return True

            current_date += timedelta(days=1)

        current_app.logger.info(
            f"FORWARD MOVE: Could not find earlier slot for event {event_to_move.project_ref_num}"
        )
        return False

    def _move_matching_supervisor_event(self, run: object, core_event: object, old_date: date, new_date: date) -> None:
        """
        Move a Supervisor event that was paired with a Core event to a new date.

        When we move a Core event forward, we also need to move its matching Supervisor event.

        Args:
            run: Current scheduler run
            core_event: Core event that was moved
            old_date: Old date where Supervisor was scheduled
            new_date: New date to move Supervisor to
        """
        # Extract event number from Core event name
        core_event_number = self._extract_event_number(core_event.project_name)
        if not core_event_number:
            # No event number found - can't match Supervisor
            return

        # Find all Supervisor events that could match
        supervisor_events = self.db.query(self.Event).filter(
            self.Event.event_type == 'Supervisor',
            self.Event.is_scheduled == False,
            self.Event.start_datetime <= datetime.combine(new_date, time(0, 0)),
            self.Event.due_datetime >= datetime.combine(new_date, time(23, 59))
        ).all()

        # Find the one with matching event number
        supervisor_event = None
        for event in supervisor_events:
            supervisor_event_number = self._extract_event_number(event.project_name)
            if supervisor_event_number == core_event_number:
                supervisor_event = event
                break

        if not supervisor_event:
            # No matching Supervisor event found, that's OK
            return

        # Find if this Supervisor is currently scheduled on the old date
        supervisor_schedule = self.db.query(self.PendingSchedule).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.event_ref_num == supervisor_event.project_ref_num,
            func.date(self.PendingSchedule.schedule_datetime) == old_date
        ).first()

        if supervisor_schedule:
            # Move the Supervisor event to the new date (keep same time - noon)
            new_supervisor_datetime = datetime.combine(new_date, time(12, 0))
            current_app.logger.info(
                f"FORWARD MOVE: Also moving Supervisor event {supervisor_event.project_ref_num} "
                f"from {old_date} to {new_date}"
            )
            supervisor_schedule.schedule_datetime = new_supervisor_datetime
            supervisor_schedule.schedule_time = time(12, 0)
            self.db.flush()

    def _schedule_juicer_events_wave1(self, run: object, events: List[object]) -> None:
        """
        Wave 1: Schedule Juicer events (HIGHEST PRIORITY)

        Logic:
        - Juicer rotation employees MUST do Juicer events on their rotation days
        - If rotation Juicer has Core events scheduled, BUMP those Core events
        - Bumped Core events are unscheduled and will be rescheduled in later waves
        - Try rotation Juicer on event start date, then try next days until due date

        Scheduling times:
        - JUICER-PRODUCTION-SPCLTY: 9:00 AM
        - Juicer Survey: 5:00 PM
        - Other Juicer events: 9:00 AM
        """
        juicer_events = [e for e in events if e.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'] and not e.is_scheduled]

        for event in juicer_events:
            self._schedule_single_juicer_event_wave1(run, event)

    def _schedule_single_juicer_event_wave1(self, run: object, event: object) -> None:
        """Schedule a single Juicer event, bumping Core events if needed"""
        # Determine the appropriate time for this Juicer event
        juicer_time = self._get_juicer_time(event)

        # Try each day from earliest allowed date to due date
        current_date = self._get_earliest_schedule_date(event)

        while current_date < event.due_datetime:
            # Get rotation employee for this specific date
            employee = self.rotation_manager.get_rotation_employee(current_date, 'juicer')
            if not employee:
                # No Juicer assigned for this day in rotation
                current_date += timedelta(days=1)
                continue

            schedule_datetime = datetime.combine(current_date.date(), juicer_time)

            # Check if employee is available (time off, weekly availability, etc.)
            # But SKIP the daily Core events limit check - we'll bump Core events if needed
            validation = self.validator.validate_assignment(event, employee, schedule_datetime)

            # Check if employee has Core events scheduled on this day
            core_events_to_bump = self._get_core_events_for_employee_on_date(
                run, employee.id, current_date.date()
            )

            # Wave 1 special logic: We can BUMP Core events, so ignore DAILY_LIMIT and ALREADY_SCHEDULED constraints
            # Check if the ONLY violations are bumpable constraints
            from .validation_types import ConstraintType

            bumpable_constraints = {ConstraintType.DAILY_LIMIT, ConstraintType.ALREADY_SCHEDULED}
            blocking_violations = [v for v in validation.violations if v.constraint_type not in bumpable_constraints]

            is_actually_valid = len(blocking_violations) == 0

            if not is_actually_valid:
                # Has real blocking violations (TIME_OFF, AVAILABILITY, ROLE, DUE_DATE) - skip this date
                current_date += timedelta(days=1)
                continue

            # Employee is available (ignoring bumpable constraints) - bump any Core events and schedule Juicer
            if core_events_to_bump:
                self._bump_core_events(run, core_events_to_bump, employee, current_date.date())

            self._create_pending_schedule(run, event, employee, schedule_datetime, False, None, None)
            run.events_scheduled += 1
            current_app.logger.info(
                f"Wave 1: Scheduled Juicer event {event.project_ref_num} to {employee.name} on {current_date.date()}"
                + (f" (bumped {len(core_events_to_bump)} Core events)" if core_events_to_bump else "")
            )
            return

        # Failed to schedule
        self._create_failed_pending_schedule(run, event, "No available Juicer rotation employee before due date")
        run.events_failed += 1

    def _get_core_events_for_employee_on_date(self, run: object, employee_id: str, target_date: date) -> List[object]:
        """
        Get Core events scheduled for an employee on a specific date

        Checks BOTH:
        1. Pending schedules from current run
        2. Permanent schedules from previous runs (these will be unscheduled if bumped)

        Returns a list of objects that can be either PendingSchedule or Schedule instances
        """
        # Get pending Core events from current run
        pending_core_events = self.db.query(self.PendingSchedule).join(
            self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.employee_id == employee_id,
            func.date(self.PendingSchedule.schedule_datetime) == target_date,
            self.Event.event_type == 'Core',
            self.PendingSchedule.failure_reason == None  # Only successfully scheduled ones
        ).all()

        # ALSO get permanent Core schedules from previous runs
        permanent_core_schedules = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == employee_id,
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Event.event_type == 'Core'
        ).all()

        # Combine both lists
        return list(pending_core_events) + list(permanent_core_schedules)

    def _find_bumpable_core_event(self, run: object, new_event: object) -> tuple:
        """
        Find the best Core event to bump for a more urgent event.
        Returns (employee, schedule_datetime, existing_schedule, is_posted) if found, else (None, None, None, False)

        Looks for Core events with LATER due dates than new_event and picks the best one to bump.
        This searches BOTH:
        1. Events in current pending run (PendingSchedule table)
        2. Events already posted to external API (Schedule table)

        Only returns events that haven't been bumped too many times and could still be rescheduled.
        """
        # Find all Core events scheduled in THIS RUN with later due dates
        bumpable_pending = self.db.query(self.PendingSchedule).join(
            self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.Event.event_type == 'Core',
            self.PendingSchedule.failure_reason == None,
            self.Event.due_datetime > new_event.due_datetime  # Only events due AFTER this one
        ).all()

        # ALSO find Core events already posted to external API (Schedule table) with later due dates
        # STRICT SEARCH WINDOW: Only look at dates within the new event's VALID scheduling window
        # - Must be >= new_event.start_date (on or after)
        # - Must be < new_event.due_date (strictly before, not on)
        # - Must not be in the past
        today = datetime.now()

        # Search window: from start_date (or today if start is in past) to day before due_date
        search_start = max(new_event.start_datetime.date(), today.date())
        # Since we need schedule_datetime < due_datetime, we search up to but not including due date
        # The query will filter by date, so we use due_date - 1 day as the end
        search_end = new_event.due_datetime.date() - timedelta(days=1)

        # If search window is invalid (start > end), no bumpable events exist
        if search_start > search_end:
            current_app.logger.info(
                f"FIND BUMPABLE: No valid search window for event {new_event.project_ref_num} "
                f"(start: {search_start}, end: {search_end})"
            )
            bumpable_posted = []
        else:
            bumpable_posted = self.db.query(self.Schedule).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                self.Event.event_type == 'Core',
                self.Event.due_datetime > new_event.due_datetime,  # Only events due AFTER this one
                func.date(self.Schedule.schedule_datetime) >= search_start,
                func.date(self.Schedule.schedule_datetime) <= search_end
            ).all()

        current_app.logger.info(
            f"FIND BUMPABLE: Found {len(bumpable_pending)} pending + {len(bumpable_posted)} posted = "
            f"{len(bumpable_pending) + len(bumpable_posted)} total candidates for event {new_event.project_ref_num}"
        )

        if not bumpable_pending and not bumpable_posted:
            return None, None, None, False

        # Filter out events that:
        # 1. Have been bumped too many times already
        # 2. Are already expired (due_datetime has passed)
        today = datetime.now()
        valid_bumpable = []

        # Process pending schedules
        for schedule in bumpable_pending:
            bump_count = self.bump_count.get(schedule.event.project_ref_num, 0)
            if bump_count >= self.MAX_BUMPS_PER_EVENT:
                continue  # Already bumped too many times
            if schedule.event.due_datetime < today:
                continue  # Event has expired, can't be rescheduled
            valid_bumpable.append((schedule, False))  # False = not posted yet

        # Process posted schedules
        for schedule in bumpable_posted:
            bump_count = self.bump_count.get(schedule.event.project_ref_num, 0)
            if bump_count >= self.MAX_BUMPS_PER_EVENT:
                continue  # Already bumped too many times
            if schedule.event.due_datetime < today:
                continue  # Event has expired, can't be rescheduled
            valid_bumpable.append((schedule, True))  # True = already posted to external API

        if not valid_bumpable:
            current_app.logger.info(f"FIND BUMPABLE: No valid bumpable events after filtering")
            return None, None, None, False

        # Pick the event with the LATEST due date (least urgent) to bump first
        # But if there are multiple with the same latest due date, prefer the one scheduled earliest
        best_schedule, is_posted = max(valid_bumpable,
                                       key=lambda x: (x[0].event.due_datetime, -x[0].schedule_datetime.toordinal()))

        schedule_type = "POSTED" if is_posted else "PENDING"
        current_app.logger.info(
            f"FIND BUMPABLE: Found {len(valid_bumpable)} valid bumpable events for event {new_event.project_ref_num} (due {new_event.due_datetime.date()})"
        )
        current_app.logger.info(
            f"FIND BUMPABLE: Selected {schedule_type} event {best_schedule.event.project_ref_num} (due {best_schedule.event.due_datetime.date()}) "
            f"scheduled on {best_schedule.schedule_datetime.strftime('%Y-%m-%d %I:%M %p')} with {best_schedule.employee.name}"
        )

        return best_schedule.employee, best_schedule.schedule_datetime, best_schedule, is_posted

    def _try_cascading_bump_for_core(self, run: object, new_event: object, employee: object,
                                      schedule_datetime: datetime, events: List[object], wave_label: str,
                                      is_posted: bool = False) -> bool:
        """
        Try to bump a Core event with a later due date to make room for a Core event with earlier due date.
        Keeps same employee and time slot to avoid schedule confusion.
        Allows cascading: bumped event will try to reschedule and may bump another event.

        Args:
            run: Current scheduler run
            new_event: Event trying to be scheduled (earlier due date)
            employee: Employee who would be assigned
            schedule_datetime: Exact datetime slot we want
            events: List of all events (for supervisor scheduling)
            wave_label: Label for logging (e.g., "Wave 2.1")
            is_posted: If True, the schedule to bump is already posted to external API (Schedule table)

        Returns:
            True if successfully bumped and scheduled, False otherwise
        """
        from .validation_types import ConstraintType
        from datetime import timedelta

        # VALIDATION 1: Check if new_event can actually be scheduled at this datetime
        # STRICT RULES:
        # - Schedule Date must be >= Start Date (on or after)
        # - Schedule Date must be < Due Date (strictly before, not on)

        # Check if date is before start_date (HARD CONSTRAINT - NO EXCEPTIONS)
        if schedule_datetime < new_event.start_datetime:
            current_app.logger.info(
                f"{wave_label} BUMP: Cannot schedule event {new_event.project_ref_num} at {schedule_datetime.strftime('%Y-%m-%d')} "
                f"- before start date ({new_event.start_datetime.strftime('%Y-%m-%d')})"
            )
            return False

        # Check if date is on or after due_date (HARD CONSTRAINT - must be BEFORE due date)
        if schedule_datetime >= new_event.due_datetime:
            current_app.logger.info(
                f"{wave_label} BUMP: Cannot schedule event {new_event.project_ref_num} at {schedule_datetime.strftime('%Y-%m-%d')} "
                f"- on or after due date ({new_event.due_datetime.strftime('%Y-%m-%d')})"
            )
            return False

        # VALIDATION 2: If employee is a Juicer, check they don't have a Juicer event that day
        if employee.job_title == 'Juicer Barista':
            juicer_event_today = self.db.query(self.PendingSchedule).join(
                self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                self.PendingSchedule.scheduler_run_id == run.id,
                self.PendingSchedule.employee_id == employee.id,
                func.date(self.PendingSchedule.schedule_datetime) == schedule_datetime.date(),
                self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
            ).first()

            if juicer_event_today:
                current_app.logger.info(
                    f"{wave_label} BUMP: Cannot schedule Core event {new_event.project_ref_num} to {employee.name} on {schedule_datetime.strftime('%Y-%m-%d')} "
                    f"- Juicer has Juicer event {juicer_event_today.event.project_ref_num} scheduled that day"
                )
                return False

        # Find what Core event (if any) is scheduled for this employee at this exact time
        # Look in the correct table based on is_posted flag
        if is_posted:
            # Event is already posted to external API - query Schedule table
            existing_schedule = self.db.query(self.Schedule).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                self.Schedule.employee_id == employee.id,
                self.Schedule.schedule_datetime == schedule_datetime,
                self.Event.event_type == 'Core'
            ).first()
        else:
            # Event is in current pending run - query PendingSchedule table
            existing_schedule = self.db.query(self.PendingSchedule).join(
                self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                self.PendingSchedule.scheduler_run_id == run.id,
                self.PendingSchedule.employee_id == employee.id,
                self.PendingSchedule.schedule_datetime == schedule_datetime,
                self.Event.event_type == 'Core',
                self.PendingSchedule.failure_reason == None
            ).first()

        if not existing_schedule:
            # No Core event at this time slot, can't bump
            return False

        existing_event = existing_schedule.event

        # Compare due dates: only bump if new event is more urgent (earlier due date)
        if new_event.due_datetime >= existing_event.due_datetime:
            # New event is not more urgent, don't bump
            current_app.logger.info(
                f"{wave_label} BUMP: Cannot bump event {existing_event.project_ref_num} "
                f"(due {existing_event.due_datetime.date()}) for event {new_event.project_ref_num} "
                f"(due {new_event.due_datetime.date()}) - new event not more urgent"
            )
            return False

        # VALIDATION 2: Check if existing_event has been bumped too many times (prevent infinite loops)
        bump_count = self.bump_count.get(existing_event.project_ref_num, 0)
        if bump_count >= self.MAX_BUMPS_PER_EVENT:
            current_app.logger.warning(
                f"{wave_label} BUMP: Cannot bump event {existing_event.project_ref_num} - "
                f"already bumped {bump_count} times (max: {self.MAX_BUMPS_PER_EVENT})"
            )
            return False

        # STRATEGY 1: Try to move existing_event FORWARD to an earlier date
        # This strategy only works for PendingSchedule (not posted events)
        # Check if the current schedule date is within the new event's valid period
        if not is_posted and self._is_datetime_valid_for_event(new_event, schedule_datetime):
            # Try to move existing_event to an earlier date (new_event's start or later)
            if self._try_move_event_forward(run, existing_event, existing_schedule,
                                            new_event.start_datetime, employee):
                # Success! The existing event was moved forward
                # Now schedule the new event in the freed slot
                self._create_pending_schedule(run, new_event, employee, schedule_datetime, False, None, None)
                run.events_scheduled += 1
                current_app.logger.info(
                    f"{wave_label}: Scheduled Core event {new_event.project_ref_num} to {employee.name} "
                    f"(moved existing event {existing_event.project_ref_num} forward)"
                )

                # Schedule matching Supervisor event inline
                self._schedule_matching_supervisor_event(run, new_event, schedule_datetime.date(), events)

                return True

        # STRATEGY 2: Forward move failed (or is_posted=True), fall back to traditional bump (delete and reschedule)
        current_app.logger.info(
            f"{wave_label} BUMP: Forward move failed, using traditional bump for event {existing_event.project_ref_num} "
            f"(due {existing_event.due_datetime.date()}) from {employee.name} at {schedule_datetime.strftime('%Y-%m-%d %I:%M %p')} "
            f"to make room for event {new_event.project_ref_num} (due {new_event.due_datetime.date()})"
        )

        # Increment bump count for existing_event
        self.bump_count[existing_event.project_ref_num] = bump_count + 1

        # Delete the existing schedule (from appropriate table)
        if is_posted:
            # Event was posted to external API - need to unschedule it
            external_id = existing_schedule.external_id if hasattr(existing_schedule, 'external_id') else None
            current_app.logger.warning(
                f"{wave_label} BUMP POSTED: Bumping event {existing_event.project_ref_num} that was already posted to external API "
                f"(external_id: {external_id}). It will be deleted from Schedule table and marked for rescheduling."
            )
            # Delete from Schedule table
            self.db.delete(existing_schedule)
            # Also delete any matching Supervisor event that was posted
            # Find Supervisor by matching event number in project name
            core_event_number = self._extract_event_number(existing_event.project_name)
            if core_event_number:
                # Look for Supervisor events scheduled on the same date
                supervisor_schedules = self.db.query(self.Schedule).join(
                    self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    func.date(self.Schedule.schedule_datetime) == schedule_datetime.date(),
                    self.Event.event_type == 'Supervisor'
                ).all()

                # Check each Supervisor to see if it matches the Core event number
                for supervisor_schedule in supervisor_schedules:
                    supervisor_event_number = self._extract_event_number(supervisor_schedule.event.project_name)
                    if supervisor_event_number == core_event_number:
                        current_app.logger.info(
                            f"{wave_label} BUMP POSTED: Also deleting matching Supervisor event {supervisor_schedule.event.project_ref_num}"
                        )
                        self.db.delete(supervisor_schedule)
                        break
        else:
            # Event is in pending run - just delete from PendingSchedule
            self.db.delete(existing_schedule)

        existing_event.is_scheduled = False

        # Schedule the new event in its place
        self._create_pending_schedule(run, new_event, employee, schedule_datetime, False, None, None)
        run.events_scheduled += 1

        bump_type = "POSTED" if is_posted else "PENDING"
        current_app.logger.info(
            f"{wave_label}: Scheduled Core event {new_event.project_ref_num} to {employee.name} "
            f"(bumped {bump_type} event {existing_event.project_ref_num})"
        )

        # Schedule matching Supervisor event inline
        self._schedule_matching_supervisor_event(run, new_event, schedule_datetime.date(), events)

        # Now try to reschedule the bumped event (this may cascade to bump another event)
        current_app.logger.info(
            f"{wave_label} BUMP: Attempting to reschedule bumped event {existing_event.project_ref_num}"
        )

        # Try to reschedule using the same priority order (Lead -> Juicer -> Specialist)
        if employee.job_title == 'Lead Event Specialist':
            self._try_schedule_core_to_lead(run, existing_event, events)
        elif employee.job_title == 'Juicer Barista':
            if not self._try_schedule_core_to_juicer(run, existing_event, events):
                # If Juicer fails, try Specialist as fallback
                self._try_schedule_core_to_specialist(run, existing_event, events)
        else:  # Event Specialist
            self._try_schedule_core_to_specialist(run, existing_event, events)

        return True

    def _bump_core_events(self, run: object, schedules_to_bump: List[object], employee: object, date_obj: date) -> None:
        """
        Bump (unschedule) Core events from an employee to make room for Juicer rotation

        Args:
            run: Current scheduler run
            schedules_to_bump: List of PendingSchedule or Schedule objects to bump
            employee: Employee being bumped from
            date_obj: Date of the bump
        """
        for schedule in schedules_to_bump:
            # Check if it's a PendingSchedule or permanent Schedule
            is_pending = isinstance(schedule, self.PendingSchedule)

            if is_pending:
                # It's a PendingSchedule from current run
                event = schedule.event
                # Mark the event as unscheduled so it can be rescheduled
                event.is_scheduled = False
                # Delete the pending schedule
                self.db.delete(schedule)
                current_app.logger.info(
                    f"Wave 1: Bumped pending Core event {event.project_ref_num} from {employee.name} on {date_obj} "
                    f"(Juicer rotation takes priority)"
                )
            else:
                # It's a permanent Schedule from previous run
                event = self.db.query(self.Event).filter_by(project_ref_num=schedule.event_ref_num).first()
                if event:
                    # Mark the event as unscheduled so it can be rescheduled
                    event.is_scheduled = False
                    # Delete the permanent schedule
                    self.db.delete(schedule)
                    current_app.logger.info(
                        f"Wave 1: Bumped approved Core event {event.project_ref_num} from {employee.name} on {date_obj} "
                        f"(Juicer rotation takes priority - event will be rescheduled)"
                    )

    def _schedule_juicer_events_wave2(self, run: object, events: List[object]) -> None:
        """
        Wave 2: Schedule Juicer events to Juicer Baristas (rotation-based, can bump Core events)

        Logic:
        - Assign to rotation Juicer for the event's start date
        - If rotation Juicer has time off, try next day
        - Continue trying next days until due date or Juicer available
        - Respects Juicer availability constraints
        - Can bump Core events scheduled in Wave 1
        """
        juicer_events = [e for e in events if e.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'] and not e.is_scheduled]
        for event in juicer_events:
            self._schedule_juicer_event_wave2(run, event)

    def _schedule_freeosk_digital_events_wave3(self, run: object, events: List[object]) -> None:
        """
        Wave 3: Schedule Freeosk and Digital events

        Priority: Primary Lead → Other Leads → Club Supervisor
        """
        for event in events:
            if event.is_scheduled:
                continue

            # Handle Digitals events (detect subtype from name)
            if event.event_type == 'Digitals':
                event_name_upper = event.project_name.upper()

                # Digital Teardown goes to Secondary Lead (with Club Supervisor fallback)
                if 'TEARDOWN' in event_name_upper:
                    self._schedule_secondary_lead_event(run, event)
                # Digital Setup/Refresh goes to Primary Lead (with Club Supervisor fallback)
                elif 'SETUP' in event_name_upper or 'REFRESH' in event_name_upper:
                    self._schedule_primary_lead_event(run, event)
                else:
                    # Unknown Digital subtype - try Primary Lead as default
                    self._schedule_primary_lead_event(run, event)

            # Handle Freeosk events
            elif event.event_type == 'Freeosk':
                self._schedule_primary_lead_event(run, event)

    def _schedule_freeosk_events_wave3(self, run: object, events: List[object]) -> None:
        """
        Wave 3: Schedule Freeosk events ONLY

        Time: 9:00 AM
        Priority: Primary Lead → Other Leads → Club Supervisor
        """
        for event in events:
            if event.is_scheduled:
                continue

            if event.event_type == 'Freeosk':
                self._schedule_primary_lead_event(run, event)

    def _schedule_digital_events_wave4(self, run: object, events: List[object]) -> None:
        """
        Wave 4: Schedule Digital events ONLY

        Digital Setup/Refresh:
            - Times: 9:15, 9:30, 9:45, 10:00 (rotating)
            - Priority: Primary Lead → Other Leads → Club Supervisor

        Digital Teardown:
            - Times: 5:00 PM+ (15-min intervals)
            - Priority: Secondary Lead → Club Supervisor
        """
        for event in events:
            if event.is_scheduled:
                continue

            if event.event_type == 'Digitals':
                event_name_upper = event.project_name.upper()

                # Digital Teardown goes to Secondary Lead (with Club Supervisor fallback)
                if 'TEARDOWN' in event_name_upper:
                    self._schedule_secondary_lead_event(run, event)
                # Digital Setup/Refresh goes to Primary Lead (with Club Supervisor fallback)
                elif 'SETUP' in event_name_upper or 'REFRESH' in event_name_upper:
                    self._schedule_primary_lead_event(run, event)
                else:
                    # Unknown Digital subtype - try Primary Lead as default
                    self._schedule_primary_lead_event(run, event)

    def _schedule_other_events_wave5(self, run: object, events: List[object]) -> None:
        """
        Wave 5: Schedule Other events

        Priority: Club Supervisor first → ANY Lead Event Specialist fallback
        """
        for event in events:
            if event.is_scheduled:
                continue

            if event.event_type == 'Other':
                self._schedule_other_event_wave5(run, event)

    def _schedule_other_event_wave5(self, run: object, event: object) -> None:
        """
        Wave 5: Schedule Other events

        Priority: Club Supervisor (at noon) → ANY Lead Event Specialist fallback
        """
        # Use event's start date for scheduling
        current_date = self._get_earliest_schedule_date(event)

        # Schedule at noon
        schedule_time = time(12, 0)
        schedule_datetime = datetime.combine(current_date.date(), schedule_time)
        target_date = schedule_datetime.date()
        day_of_week = target_date.weekday()
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_column = day_names[day_of_week]

        # Try Club Supervisor first
        club_supervisor = self.db.query(self.Employee).filter_by(
            job_title='Club Supervisor',
            is_active=True
        ).first()

        if club_supervisor:
            # Check basic availability (time off and weekly availability only)
            # Time conflicts are ignored for Club Supervisor

            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == club_supervisor.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=club_supervisor.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    # Schedule to Club Supervisor (no time conflict checks)
                    self._create_pending_schedule(run, event, club_supervisor, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(f"Wave 5: Scheduled Other event {event.project_ref_num} to Club Supervisor")
                    return

        # Fallback to ANY Lead Event Specialist if Club Supervisor unavailable
        leads = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).all()

        for lead in leads:
            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == lead.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=lead.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    # Schedule to this Lead (no time conflict checks for Other events)
                    self._create_pending_schedule(run, event, lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(f"Wave 5: Scheduled Other event {event.project_ref_num} to Lead Event Specialist {lead.name}")
                    return

        # Failed to schedule
        self._create_failed_pending_schedule(run, event, "No Club Supervisor or Lead Event Specialist available")
        run.events_failed += 1

    def _get_juicer_time(self, event: object) -> time:
        """
        Determine the scheduling time for a Juicer event based on its name

        Returns:
            - 9:00 AM for JUICER-PRODUCTION-SPCLTY events
            - 5:00 PM for Juicer Survey events
            - 9:00 AM for other Juicer events (default)
        """
        event_name_upper = event.project_name.upper()

        if 'JUICER-PRODUCTION' in event_name_upper or 'PRODUCTION-SPCLTY' in event_name_upper:
            return self.DEFAULT_TIMES['Juicer Production']
        elif 'JUICER SURVEY' in event_name_upper or 'SURVEY' in event_name_upper:
            return self.DEFAULT_TIMES['Juicer Survey']
        else:
            return self.DEFAULT_TIMES['Juicer']

    def _schedule_juicer_event_wave2(self, run: object, event: object) -> None:
        """
        Wave 2: Schedule a Juicer event to the rotation-assigned Juicer Barista

        Logic:
        - Try rotation Juicer for event start date
        - If Juicer has time off or unavailable, try next day
        - Continue until due date
        - Can bump Core events from Wave 1 if needed

        Scheduling times:
        - JUICER-PRODUCTION-SPCLTY: 9:00 AM
        - Juicer Survey: 5:00 PM
        - Other Juicer events: 9:00 AM
        """
        # Determine the appropriate time for this Juicer event
        juicer_time = self._get_juicer_time(event)

        # Try each day from earliest allowed date to due date
        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            employee = self.rotation_manager.get_rotation_employee(current_date, 'juicer')
            if not employee:
                # No Juicer assigned for this day in rotation
                current_date += timedelta(days=1)
                continue

            schedule_datetime = datetime.combine(current_date.date(), juicer_time)
            validation = self.validator.validate_assignment(event, employee, schedule_datetime)

            if validation.is_valid:
                # Juicer is available - schedule it
                self._create_pending_schedule(run, event, employee, schedule_datetime, False, None, None)
                run.events_scheduled += 1
                current_app.logger.info(
                    f"Wave 2: Scheduled Juicer event {event.project_ref_num} to {employee.name} on {current_date.date()}"
                )
                return

            # Juicer not available (time off, already scheduled, etc.) - try next day
            current_date += timedelta(days=1)

        # Failed to schedule
        self._create_failed_pending_schedule(run, event, "No available Juicer rotation employee before due date")
        run.events_failed += 1

    def _schedule_core_events_wave2_new(self, run: object, events: List[object]) -> List[object]:
        """
        Wave 2: Schedule Core events using day-by-day bump-first logic with cascading

        NEW LOGIC:
        1. Process unstaffed Core events in due date order (earliest first)
        2. For each event, search day-by-day starting tomorrow:
           - Days 1-3: ONLY try to bump (short notice - no empty slot filling)
           - Day 4+: Try empty slots FIRST, then bump if no empty slots
        3. Cascading bumps: Bumped events re-inserted into queue and re-sorted by due date
        4. Failed events (reached due date without scheduling) returned for user review

        Employee Pool:
        - Leads: Always available (priority)
        - Specialists: Always available
        - Juicers: Only if they don't have a Juicer event that day (treated as Specialists)

        Returns:
            List of events that could not be scheduled (for user review)
        """
        current_app.logger.info("=== WAVE 2: Core Events (Day-by-Day Bump-First Logic) ===")

        # Get all unstaffed Core events and sort by due date
        unstaffed_core = [e for e in events if e.event_type == 'Core' and not e.is_scheduled]
        unstaffed_core.sort(key=lambda e: e.due_datetime)

        failed_events = []
        today = datetime.now()

        current_app.logger.info(f"Processing {len(unstaffed_core)} unstaffed Core events")

        while unstaffed_core:
            # Get most urgent event
            event = unstaffed_core.pop(0)

            current_app.logger.info(
                f"Processing Core event {event.project_ref_num} "
                f"(start: {event.start_datetime.date()}, due: {event.due_datetime.date()})"
            )

            scheduled = False

            # Day-by-day search from tomorrow to due date
            search_start = max(event.start_datetime, today + timedelta(days=1))
            search_end = event.due_datetime

            current_date = search_start

            while current_date < search_end and not scheduled:
                days_from_now = (current_date.date() - today.date()).days

                current_app.logger.info(
                    f"  Checking date {current_date.date()} (day {days_from_now} from now)"
                )

                # Days 1-3: SHORT NOTICE - Only try to bump
                if days_from_now <= 3:
                    current_app.logger.info("  Short notice window (days 1-3): BUMP ONLY")
                    bumped_event = self._try_bump_for_day(run, event, current_date, events)
                    if bumped_event:
                        # Success! Event scheduled, bumped event back to queue
                        scheduled = True
                        event.is_scheduled = True
                        # Re-insert bumped event and re-sort
                        unstaffed_core.append(bumped_event)
                        unstaffed_core.sort(key=lambda e: e.due_datetime)
                        current_app.logger.info(
                            f"  SUCCESS: Scheduled {event.project_ref_num}, "
                            f"bumped {bumped_event.project_ref_num} back to queue"
                        )

                # Day 4+: Try empty slots FIRST, then bump
                else:
                    current_app.logger.info("  Normal window (day 4+): Try empty slots first, then bump")

                    # Try empty slots first
                    if self._try_fill_empty_slot(run, event, current_date, events):
                        scheduled = True
                        event.is_scheduled = True
                        current_app.logger.info(f"  SUCCESS: Filled empty slot for {event.project_ref_num}")
                    else:
                        # No empty slots, try to bump
                        bumped_event = self._try_bump_for_day(run, event, current_date, events)
                        if bumped_event:
                            scheduled = True
                            event.is_scheduled = True
                            # Re-insert bumped event and re-sort
                            unstaffed_core.append(bumped_event)
                            unstaffed_core.sort(key=lambda e: e.due_datetime)
                            current_app.logger.info(
                                f"  SUCCESS: Scheduled {event.project_ref_num}, "
                                f"bumped {bumped_event.project_ref_num} back to queue"
                            )

                # Move to next day
                current_date += timedelta(days=1)

            # If not scheduled by due date, add to failed list
            if not scheduled:
                current_app.logger.warning(
                    f"FAILED: Could not schedule Core event {event.project_ref_num} "
                    f"(due {event.due_datetime.date()})"
                )
                failed_events.append(event)
                # Create failure record in PendingSchedule
                self._create_failed_pending_schedule(
                    run, event,
                    f"Could not find slot or event to bump within valid window (start: {event.start_datetime.date()}, due: {event.due_datetime.date()})"
                )
                run.events_failed += 1

        scheduled_count = run.events_scheduled
        current_app.logger.info(
            f"Wave 2 complete: {scheduled_count} scheduled, {len(failed_events)} failed"
        )

        return failed_events

    def _try_bump_for_day(self, run: object, event: object, target_date: datetime, events: List[object]) -> Optional[object]:
        """
        Try to bump a less urgent event on a specific day to make room for the given event

        Returns the bumped event if successful, None otherwise
        """
        target_date_obj = target_date.date()

        # Find all Core events scheduled on this day (both pending and posted)
        # Pending schedules
        pending_on_day = self.db.query(self.PendingSchedule).join(
            self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.Event.event_type == 'Core',
            self.PendingSchedule.failure_reason == None,
            func.date(self.PendingSchedule.schedule_datetime) == target_date_obj
        ).all()

        # Posted schedules
        posted_on_day = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Event.event_type == 'Core',
            func.date(self.Schedule.schedule_datetime) == target_date_obj
        ).all()

        # Find candidates with later due dates (less urgent)
        candidates = []
        for sched in pending_on_day:
            if sched.event.due_datetime > event.due_datetime:
                candidates.append((sched, False))  # False = not posted
        for sched in posted_on_day:
            if sched.event.due_datetime > event.due_datetime:
                candidates.append((sched, True))  # True = posted

        if not candidates:
            return None

        # Pick the one with the LATEST due date (least urgent)
        # Tie-breaker: earliest schedule time
        best_sched, is_posted = max(candidates,
                                    key=lambda x: (x[0].event.due_datetime, -x[0].schedule_datetime.toordinal()))

        # Perform the bump
        employee = best_sched.employee
        schedule_datetime = best_sched.schedule_datetime
        bumped_event = best_sched.event

        current_app.logger.info(
            f"    BUMPING: {bumped_event.project_ref_num} (due {bumped_event.due_datetime.date()}) "
            f"from {employee.name} at {schedule_datetime.strftime('%Y-%m-%d %I:%M %p')}"
        )

        # Delete the schedule
        if is_posted:
            current_app.logger.info(f"    Removing posted schedule from Schedule table")
            self.db.delete(best_sched)
            # Delete matching Supervisor if exists
            self._delete_matching_supervisor_posted(bumped_event, target_date_obj)
        else:
            current_app.logger.info(f"    Removing pending schedule")
            self.db.delete(best_sched)

        bumped_event.is_scheduled = False

        # Schedule the new event in its place
        self._create_pending_schedule(run, event, employee, schedule_datetime, False, None, None)
        run.events_scheduled += 1

        # Schedule matching Supervisor event
        self._schedule_matching_supervisor_event(run, event, schedule_datetime.date(), events)

        return bumped_event

    def _try_fill_empty_slot(self, run: object, event: object, target_date: datetime, events: List[object]) -> bool:
        """
        Try to fill an empty slot for the given event on a specific day

        Employee priority: Leads first, then Specialists/available Juicers
        Time slot selection: Prefer slot with fewest scheduled employees

        Returns True if successfully scheduled, False otherwise
        """
        target_date_obj = target_date.date()

        # Build employee pool
        employee_pool = []

        # Get Leads (priority)
        leads = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).all()
        employee_pool.extend([(emp, 'Lead') for emp in leads])

        # Get Specialists
        specialists = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Event Specialist',
            self.Employee.is_active == True
        ).all()
        employee_pool.extend([(emp, 'Specialist') for emp in specialists])

        # Get Juicers (only if not juicing that day)
        juicers = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Juicer Barista',
            self.Employee.is_active == True
        ).all()

        for juicer in juicers:
            if not self._has_juicer_event_on_day(run, juicer, target_date_obj):
                employee_pool.append((juicer, 'Juicer-as-Specialist'))

        current_app.logger.info(f"    Employee pool: {len(employee_pool)} available")

        # Try each employee (Leads first due to list order)
        for employee, role in employee_pool:
            # Find the time slot with fewest scheduled employees
            time_slot = self._find_least_busy_time_slot(run, target_date_obj)

            if not time_slot:
                current_app.logger.error(f"    ERROR: _find_least_busy_time_slot returned None for {target_date_obj}")
                continue

            schedule_datetime = datetime.combine(target_date_obj, time_slot)

            # Validate assignment
            validation = self.validator.validate_assignment(event, employee, schedule_datetime)

            if validation.is_valid:
                # Found empty slot!
                current_app.logger.info(
                    f"    EMPTY SLOT: Scheduling {event.project_ref_num} to {employee.name} ({role}) "
                    f"at {schedule_datetime.strftime('%Y-%m-%d %I:%M %p')}"
                )

                self._create_pending_schedule(run, event, employee, schedule_datetime, False, None, None)
                run.events_scheduled += 1

                # Schedule matching Supervisor event
                self._schedule_matching_supervisor_event(run, event, target_date_obj, events)

                return True

        return False

    def _has_juicer_event_on_day(self, run: object, juicer: object, target_date: date) -> bool:
        """Check if a Juicer has a Juicer event scheduled on a specific day"""
        # Check pending schedules
        pending_juicer = self.db.query(self.PendingSchedule).join(
            self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.employee_id == juicer.id,
            func.date(self.PendingSchedule.schedule_datetime) == target_date,
            self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
        ).first()

        if pending_juicer:
            return True

        # Check posted schedules
        posted_juicer = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == juicer.id,
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
        ).first()

        return posted_juicer is not None

    def _find_least_busy_time_slot(self, run: object, target_date: date) -> time:
        """Find the time slot with the fewest scheduled employees on a given day"""
        time_slots = self.CORE_TIME_SLOTS  # 8-block system: 10:15, 10:15, 10:45, 10:45, 11:15, 11:15, 11:45, 11:45

        if not time_slots:
            # Fallback to default time if CORE_TIME_SLOTS is empty (first 8-block slot)
            return time(10, 15)

        slot_counts = {}
        for slot in time_slots:
            schedule_datetime = datetime.combine(target_date, slot)

            # Count pending schedules at this time
            pending_count = self.db.query(self.PendingSchedule).filter(
                self.PendingSchedule.scheduler_run_id == run.id,
                self.PendingSchedule.schedule_datetime == schedule_datetime
            ).count()

            # Count posted schedules at this time
            posted_count = self.db.query(self.Schedule).filter(
                self.Schedule.schedule_datetime == schedule_datetime
            ).count()

            slot_counts[slot] = pending_count + posted_count

        # Return slot with minimum count (ties go to earliest slot due to dict order)
        return min(slot_counts.keys(), key=lambda s: slot_counts[s])

    def _delete_matching_supervisor_posted(self, core_event: object, target_date: date) -> None:
        """Delete a posted Supervisor event that matches a Core event on a specific date"""
        core_event_number = self._extract_event_number(core_event.project_name)
        if not core_event_number:
            return

        # Look for Supervisor events scheduled on the same date
        supervisor_schedules = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == target_date,
            self.Event.event_type == 'Supervisor'
        ).all()

        # Find matching Supervisor by event number
        for supervisor_schedule in supervisor_schedules:
            supervisor_event_number = self._extract_event_number(supervisor_schedule.event.project_name)
            if supervisor_event_number == core_event_number:
                current_app.logger.info(
                    f"    Also deleting posted Supervisor event {supervisor_schedule.event.project_ref_num}"
                )
                self.db.delete(supervisor_schedule)
                break

    def _schedule_core_events_wave1(self, run: object, events: List[object]) -> None:
        """
        Wave 2: Schedule Core events in 3 subwaves (after Juicer events)

        NOTE: This is the OLD logic - keeping for reference. New logic uses _schedule_core_events_wave2_new()

        Subwave 2.1: Lead Event Specialists (highest priority)
                    - Fill their available days first, even if event could start earlier
                    - If Lead has available day with no events, prioritize assigning to them
        Tries lead employees (excluding Juicers) at available time slots.

        Time slots rotate through 8-block system: 10:15 AM, 10:45 AM, 11:15 AM, 11:45 AM
        Priority order: Primary Lead first, then other leads.

        Also schedules matching Supervisor event inline.s
        """
        core_events = [e for e in events if e.event_type == 'Core' and not e.is_scheduled]

        # Subwave 1.1: Prioritize Lead Event Specialists
        for event in core_events:
            if event.is_scheduled:
                continue
            if self._try_schedule_core_to_lead(run, event, events):
                event.is_scheduled = True  # Mark to skip in later subwaves

        # Subwave 1.2: Try Juicer Baristas (when not juicing)
        for event in core_events:
            if event.is_scheduled:
                continue
            if self._try_schedule_core_to_juicer(run, event, events):
                event.is_scheduled = True  # Mark to skip in later subwaves

        # Subwave 1.3: Try Event Specialists
        for event in core_events:
            if event.is_scheduled:
                continue
            self._try_schedule_core_to_specialist(run, event, events)

    def _try_schedule_core_to_lead(self, run: object, event: object, events: List[object]) -> bool:
        """
        Subwave 1.1: Try to schedule Core event to a Lead Event Specialist

        Priority logic:
        1. FIRST: Try Primary Lead at 9:45 (highest priority)
        2. SECOND: Try other Leads at 9:45
        3. THIRD: Try other Leads at rotating time slots
        4. FOURTH: Try to bump a less urgent (later due date) Core event and take its slot

        Also schedules matching Supervisor event inline.

        IMPORTANT: Primary Lead Event Specialist for each day is ALWAYS scheduled at 9:45 for Core events
        """
        # Get all Lead Event Specialists
        leads = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).all()

        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            # STEP 1: Try Primary Lead at first 8-block slot (highest priority)
            first_slot = self.CORE_TIME_SLOTS[0] if self.CORE_TIME_SLOTS else time(10, 15)
            schedule_datetime_first = datetime.combine(current_date.date(), first_slot)

            # Get Primary Lead for this date
            primary_lead = self.rotation_manager.get_rotation_employee(current_date, 'primary_lead')

            # Try Primary Lead at first slot
            if primary_lead:
                validation = self.validator.validate_assignment(event, primary_lead, schedule_datetime_first)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, primary_lead, schedule_datetime_first, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 2.1: Scheduled Core event {event.project_ref_num} to Primary Lead {primary_lead.name} at {first_slot.strftime('%I:%M %p')}"
                    )

                    # Schedule matching Supervisor event inline
                    self._schedule_matching_supervisor_event(run, event, schedule_datetime_first.date(), events)

                    return True

            # STEP 2: Try other Leads at first slot
            for lead in leads:
                if primary_lead and lead.id == primary_lead.id:
                    continue  # Already tried primary lead

                validation = self.validator.validate_assignment(event, lead, schedule_datetime_first)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, lead, schedule_datetime_first, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 2.1: Scheduled Core event {event.project_ref_num} to Lead {lead.name} at {first_slot.strftime('%I:%M %p')}"
                    )

                    # Schedule matching Supervisor event inline
                    self._schedule_matching_supervisor_event(run, event, schedule_datetime_first.date(), events)

                    return True

            # STEP 3: If first slot not available, try other time slots for non-primary Leads
            time_slot = self._get_next_time_slot(current_date)
            schedule_datetime = datetime.combine(current_date.date(), time_slot)

            for lead in leads:
                # Don't use rotating slots for Primary Lead - they should only be at first slot
                if primary_lead and lead.id == primary_lead.id:
                    continue

                validation = self.validator.validate_assignment(event, lead, schedule_datetime)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 2.1: Scheduled Core event {event.project_ref_num} to Lead {lead.name} at {time_slot.strftime('%I:%M %p')}"
                    )

                    # Schedule matching Supervisor event inline
                    self._schedule_matching_supervisor_event(run, event, schedule_datetime.date(), events)

                    return True

            current_date += timedelta(days=1)

        # STEP 4: If no available slots found, try bumping a less urgent event
        bump_employee, bump_datetime, bump_schedule, is_posted = self._find_bumpable_core_event(run, event)
        if bump_employee:
            # Found a bumpable event - but if employee is a Primary Lead for that date, always use first slot
            bump_date_primary_lead = self.rotation_manager.get_rotation_employee(bump_datetime, 'primary_lead')
            first_slot = self.CORE_TIME_SLOTS[0] if self.CORE_TIME_SLOTS else time(10, 15)
            if bump_date_primary_lead and bump_employee.id == bump_date_primary_lead.id:
                bump_datetime = datetime.combine(bump_datetime.date(), first_slot)

            # Take that employee and time slot
            if self._try_cascading_bump_for_core(run, event, bump_employee, bump_datetime, events, "Wave 2.1", is_posted):
                return True

        return False

    def _try_schedule_core_to_juicer(self, run: object, event: object, events: List[object]) -> bool:
        """
        Subwave 1.2: Try to schedule Core event to a Juicer Barista (when not juicing)

        Priority logic:
        1. FIRST: Try to bump a less urgent (later due date) Core event and take its slot (ANY employee type)
        2. SECOND: Find an available empty slot

        Also schedules matching Supervisor event inline.
        """
        # STEP 1: Try to bump a less urgent event first (prioritizes due dates)
        bump_employee, bump_datetime, bump_schedule, is_posted = self._find_bumpable_core_event(run, event)
        if bump_employee:
            # Found a bumpable event - take that employee and time slot
            if self._try_cascading_bump_for_core(run, event, bump_employee, bump_datetime, events, "Wave 2.2", is_posted):
                return True

        # STEP 2: No bumpable events, try to find an empty slot
        # Get all Juicer Baristas
        juicers = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Juicer Barista',
            self.Employee.is_active == True
        ).all()

        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            time_slot = self._get_next_time_slot(current_date)
            schedule_datetime = datetime.combine(current_date.date(), time_slot)

            for juicer in juicers:
                # Check if this Juicer has a Juicer event scheduled for this day
                juicer_event_today = self.db.query(self.PendingSchedule).join(
                    self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    self.PendingSchedule.scheduler_run_id == run.id,
                    self.PendingSchedule.employee_id == juicer.id,
                    func.date(self.PendingSchedule.schedule_datetime) == schedule_datetime.date(),
                    self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
                ).first()

                # Only schedule if Juicer is NOT juicing this day
                if not juicer_event_today:
                    validation = self.validator.validate_assignment(event, juicer, schedule_datetime)
                    if validation.is_valid:
                        self._create_pending_schedule(run, event, juicer, schedule_datetime, False, None, None)
                        run.events_scheduled += 1
                        current_app.logger.info(
                            f"Wave 2.2: Scheduled Core event {event.project_ref_num} to Juicer {juicer.name}"
                        )

                        # Schedule matching Supervisor event inline
                        self._schedule_matching_supervisor_event(run, event, schedule_datetime.date(), events)

                        return True

            current_date += timedelta(days=1)

        return False

    def _try_schedule_core_to_specialist(self, run: object, event: object, events: List[object]) -> None:
        """
        Subwave 1.3: Try to schedule Core event to an Event Specialist

        Priority logic:
        1. FIRST: Try to bump a less urgent (later due date) Core event and take its slot (ANY employee type)
        2. SECOND: Find an available empty slot

        Also schedules matching Supervisor event inline.
        """
        # STEP 1: Try to bump a less urgent event first (prioritizes due dates)
        bump_employee, bump_datetime, bump_schedule, is_posted = self._find_bumpable_core_event(run, event)
        if bump_employee:
            # Found a bumpable event - take that employee and time slot
            if self._try_cascading_bump_for_core(run, event, bump_employee, bump_datetime, events, "Wave 2.3", is_posted):
                return

        # STEP 2: No bumpable events, try to find an empty slot
        # Get all Event Specialists
        specialists = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Event Specialist',
            self.Employee.is_active == True
        ).all()

        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            time_slot = self._get_next_time_slot(current_date)
            schedule_datetime = datetime.combine(current_date.date(), time_slot)

            for specialist in specialists:
                validation = self.validator.validate_assignment(event, specialist, schedule_datetime)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, specialist, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 2.3: Scheduled Core event {event.project_ref_num} to Specialist {specialist.name}"
                    )

                    # Schedule matching Supervisor event inline
                    self._schedule_matching_supervisor_event(run, event, schedule_datetime.date(), events)

                    return

            current_date += timedelta(days=1)

        # Failed to schedule
        self._create_failed_pending_schedule(run, event, "No available employees before due date")
        run.events_failed += 1

    def _get_next_digital_time_slot(self, date_obj: datetime) -> time:
        """Get next 15-min interval time slot for Digital Setup/Refresh"""
        date_str = date_obj.date().isoformat()
        if date_str not in self.digital_time_slot_index:
            self.digital_time_slot_index[date_str] = 0

        slot_index = self.digital_time_slot_index[date_str]
        time_slot = self.DIGITAL_TIME_SLOTS[slot_index % len(self.DIGITAL_TIME_SLOTS)]
        self.digital_time_slot_index[date_str] += 1
        return time_slot

    def _schedule_primary_lead_event(self, run: object, event: object) -> None:
        """
        Schedule Digital Setup/Refresh or Freeosk event to Primary Lead

        Wave 3 Priority: Primary Lead → Other Leads → Club Supervisor (fallback)
        IMPORTANT: Freeosk events MUST be scheduled on their start date
        """
        # Use event's start date - Freeosk/Digital events don't move to other days
        schedule_date = self._get_earliest_schedule_date(event)

        # Determine time slot based on event name
        event_name_upper = event.project_name.upper()
        if event.event_type == 'Digitals' and ('SETUP' in event_name_upper or 'REFRESH' in event_name_upper):
            schedule_time = self._get_next_digital_time_slot(schedule_date)
        else:
            schedule_time = self.DEFAULT_TIMES.get('Freeosk', time(10, 0))

        schedule_datetime = datetime.combine(schedule_date.date(), schedule_time)
        target_date = schedule_datetime.date()
        day_of_week = target_date.weekday()
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_column = day_names[day_of_week]

        # Try Primary Lead first (only check time off and weekly availability)
        primary_lead = self.rotation_manager.get_rotation_employee(schedule_date, 'primary_lead')
        if primary_lead:
            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == primary_lead.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=primary_lead.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    self._create_pending_schedule(run, event, primary_lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 3: Scheduled {event.event_type} event {event.project_ref_num} to Primary Lead {primary_lead.name}"
                    )
                    return

        # Try other Lead Event Specialists (only check time off and weekly availability)
        other_leads = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).all()

        for lead in other_leads:
            if primary_lead and lead.id == primary_lead.id:
                continue  # Skip primary lead (already tried)

            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == lead.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=lead.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    self._create_pending_schedule(run, event, lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 3: Scheduled {event.event_type} event {event.project_ref_num} to Lead {lead.name}"
                    )
                    return

        # Try Club Supervisor (only check time off and weekly availability, no time conflicts)
        club_supervisor = self.db.query(self.Employee).filter_by(
            job_title='Club Supervisor',
            is_active=True
        ).first()

        if club_supervisor:
            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == club_supervisor.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=club_supervisor.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    self._create_pending_schedule(run, event, club_supervisor, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 3: Scheduled {event.event_type} event {event.project_ref_num} to Club Supervisor (no leads available)"
                    )
                    return
                else:
                    current_app.logger.warning(
                        f"Wave 3: Club Supervisor NOT available on {day_column} for event {event.project_ref_num}"
                    )
            else:
                current_app.logger.warning(
                    f"Wave 3: Club Supervisor has time off on {target_date} for event {event.project_ref_num}"
                )

        # This should NEVER happen - log detailed info for debugging
        current_app.logger.error(
            f"Wave 3: CRITICAL - No Lead or Club Supervisor available for {event.event_type} event {event.project_ref_num} on {target_date} ({day_column})"
        )
        self._create_failed_pending_schedule(
            run,
            event,
            f"No Lead or Club Supervisor available on {day_column} - This should not happen!"
        )
        run.events_failed += 1

    def _get_next_teardown_time_slot(self, date_obj: datetime) -> time:
        """Get next 15-min interval time slot for Digital Teardown starting at 5 PM"""
        date_str = date_obj.date().isoformat()
        if date_str not in self.teardown_time_slot_index:
            self.teardown_time_slot_index[date_str] = 0

        slot_index = self.teardown_time_slot_index[date_str]
        time_slot = self.TEARDOWN_TIME_SLOTS[slot_index % len(self.TEARDOWN_TIME_SLOTS)]
        self.teardown_time_slot_index[date_str] += 1
        return time_slot

    def _schedule_secondary_lead_event(self, run: object, event: object) -> None:
        """
        Schedule Digital Teardown to Secondary Lead at rotating 15-min intervals from 5 PM

        Wave 3 Priority: Secondary Lead → Club Supervisor (fallback)
        IMPORTANT: Digital events MUST be scheduled on their start date
        """
        # Use event's start date - Digital events don't move to other days
        schedule_date = self._get_earliest_schedule_date(event)
        schedule_time = self._get_next_teardown_time_slot(schedule_date)
        schedule_datetime = datetime.combine(schedule_date.date(), schedule_time)
        target_date = schedule_datetime.date()
        day_of_week = target_date.weekday()
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_column = day_names[day_of_week]

        # Try Secondary Lead first (only check time off and weekly availability)
        secondary_lead = self.rotation_manager.get_secondary_lead(schedule_date)
        if secondary_lead:
            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == secondary_lead.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=secondary_lead.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    self._create_pending_schedule(run, event, secondary_lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 3: Scheduled Digital Teardown {event.project_ref_num} to Secondary Lead {secondary_lead.name}"
                    )
                    return

        # Try Club Supervisor (only check time off and weekly availability, no time conflicts)
        club_supervisor = self.db.query(self.Employee).filter_by(
            job_title='Club Supervisor',
            is_active=True
        ).first()

        if club_supervisor:
            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == club_supervisor.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if not time_off:
                # Check weekly availability
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=club_supervisor.id
                ).first()

                is_available = True
                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)

                if is_available:
                    self._create_pending_schedule(run, event, club_supervisor, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 3: Scheduled Digital Teardown {event.project_ref_num} to Club Supervisor (no secondary lead available)"
                    )
                    return
                else:
                    current_app.logger.warning(
                        f"Wave 3: Club Supervisor NOT available on {day_column} for Digital Teardown {event.project_ref_num}"
                    )
            else:
                current_app.logger.warning(
                    f"Wave 3: Club Supervisor has time off on {target_date} for Digital Teardown {event.project_ref_num}"
                )

        # This should NEVER happen - log detailed info for debugging
        current_app.logger.error(
            f"Wave 3: CRITICAL - No Secondary Lead or Club Supervisor available for Digital Teardown {event.project_ref_num} on {target_date} ({day_column})"
        )
        self._create_failed_pending_schedule(
            run,
            event,
            f"No Secondary Lead or Club Supervisor available on {day_column} - This should not happen!"
        )
        run.events_failed += 1

    def _schedule_core_events(self, run: object, events: List[object]) -> None:
        """
        Phase 2: Schedule Core events

        Priority: Lead Event Specialists first, then Event Specialists
        """
        core_events = [e for e in events if e.event_type == 'Core' and not e.is_scheduled]

        for event in core_events:
            self._schedule_core_event(run, event)

    def _get_next_time_slot(self, date_obj: datetime) -> time:
        """
        Get the next available time slot for a Core event on a date.
        Takes into account already-scheduled Core events in the database.
        
        Regular days: Rotates through CORE_TIME_SLOTS (block arrive times)
        Sundays: Rotates through ONLY 10:30, 11:00
        """
        from sqlalchemy import func
        
        date_str = date_obj.date().isoformat()
        
        # If we haven't initialized this date's slot index yet, check the database
        # for already-scheduled Core events to start from the right slot
        if date_str not in self.daily_time_slot_index:
            # Count Core events already scheduled on this date
            already_scheduled_count = self.db.query(func.count(self.Schedule.id)).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                func.date(self.Schedule.schedule_datetime) == date_obj.date(),
                self.Event.event_type == 'Core'
            ).scalar() or 0
            
            current_app.logger.debug(
                f"Initializing time slot for {date_str}: {already_scheduled_count} Core events already scheduled"
            )
            
            # Start from the slot index after already-scheduled events
            self.daily_time_slot_index[date_str] = already_scheduled_count

        # Check if it's Sunday (weekday() returns 6 for Sunday)
        is_sunday = date_obj.weekday() == 6

        if is_sunday:
            # Sunday: Only use 2 slots from 8-block system (10:45 and 11:15)
            sunday_slots = [time(10, 45), time(11, 15)]
            slot_index = self.daily_time_slot_index[date_str]
            time_slot = sunday_slots[slot_index % len(sunday_slots)]
        else:
            # Regular days: Use all 8 block slots
            slot_index = self.daily_time_slot_index[date_str]
            time_slot = self.CORE_TIME_SLOTS[slot_index % len(self.CORE_TIME_SLOTS)]

        # Increment for next event on this date
        self.daily_time_slot_index[date_str] += 1

        return time_slot

    def _schedule_core_event(self, run: object, event: object) -> None:
        """
        Schedule a single Core event

        Logic:
        - Primary Leads get first 8-block slot (10:15 AM)
        - Everyone else rotates through 8-block slots: 10:15, 10:45, 11:15, 11:45
        """
        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            # Check if Primary Lead is available at first 8-block slot
            first_slot = self.CORE_TIME_SLOTS[0] if self.CORE_TIME_SLOTS else time(10, 15)
            primary_lead_id = self.rotation_manager.get_rotation_employee_id(current_date, 'primary_lead')
            if primary_lead_id:
                primary_lead = self.db.query(self.Employee).get(primary_lead_id)
                schedule_datetime_first = datetime.combine(current_date.date(), first_slot)

                validation = self.validator.validate_assignment(event, primary_lead, schedule_datetime_first)
                if validation.is_valid:
                    # Check if Primary Lead doesn't already have an event at first slot
                    existing = self.db.query(self.Schedule).filter(
                        self.Schedule.employee_id == primary_lead_id,
                        self.Schedule.schedule_datetime == schedule_datetime_first
                    ).first()

                    if not existing:
                        self._create_pending_schedule(run, event, primary_lead, schedule_datetime_first, False, None, None)
                        run.events_scheduled += 1
                        return

            # Primary Lead not available or already has first slot - use rotating time slots
            time_slot = self._get_next_time_slot(current_date)
            schedule_datetime = datetime.combine(current_date.date(), time_slot)

            # Try Leads first
            leads = self._get_available_leads(event, schedule_datetime)
            for lead in leads:
                validation = self.validator.validate_assignment(event, lead, schedule_datetime)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    return

            # Try Event Specialists
            specialists = self._get_available_specialists(event, schedule_datetime)
            for specialist in specialists:
                validation = self.validator.validate_assignment(event, specialist, schedule_datetime)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, specialist, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    return

            # No one available - try conflict resolution
            swap = self._try_resolve_conflict(event, schedule_datetime)
            if swap:
                self._create_pending_schedule(run, event, None, schedule_datetime, True, swap.low_priority_event_ref, swap.reason)
                run.events_requiring_swaps += 1
                return

            current_date += timedelta(days=1)

        self._create_failed_pending_schedule(run, event, "No available employees or swap candidates")
        run.events_failed += 1

    def _extract_event_number(self, event_name: str) -> str:
        """Extract first 6 digits from event name"""
        import re
        match = re.search(r'\d{6}', event_name)
        return match.group(0) if match else None

    def _schedule_matching_supervisor_event(self, run: object, core_event: object, scheduled_date: date, events: List[object]) -> None:
        """
        Schedule the matching Supervisor event inline when a Core event is scheduled

        Args:
            run: Current scheduler run
            core_event: The Core event that was just scheduled
            scheduled_date: The date the Core event was scheduled for
            events: List of all events to search for matching Supervisor event
        """
        # Extract event number from Core event name
        core_event_number = self._extract_event_number(core_event.project_name)
        if not core_event_number:
            # No event number found - no Supervisor event to pair
            return

        # Find matching Supervisor event
        supervisor_event = None
        for event in events:
            if event.event_type == 'Supervisor' and not event.is_scheduled:
                supervisor_event_number = self._extract_event_number(event.project_name)
                if supervisor_event_number == core_event_number:
                    supervisor_event = event
                    break

        if not supervisor_event:
            # No matching Supervisor event found (this is OK - not all Core events have Supervisor events)
            return

        # Schedule Supervisor event at noon on the same date as the Core event
        supervisor_datetime = datetime.combine(scheduled_date, time(12, 0))
        target_date = supervisor_datetime.date()
        day_of_week = target_date.weekday()
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_column = day_names[day_of_week]

        # Try Club Supervisor first (ignore time conflicts, only check day availability)
        club_supervisor = self.db.query(self.Employee).filter_by(
            job_title='Club Supervisor',
            is_active=True
        ).first()

        if club_supervisor:
            day_available = True

            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == club_supervisor.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if time_off:
                day_available = False

            # Check weekly availability
            if day_available:
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=club_supervisor.id
                ).first()

                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)
                    if not is_available:
                        day_available = False

            if day_available:
                self._create_pending_schedule(run, supervisor_event, club_supervisor, supervisor_datetime, False, None, None)
                supervisor_event.is_scheduled = True  # Mark as scheduled
                run.events_scheduled += 1
                current_app.logger.info(
                    f"Wave 2 (inline): Scheduled Supervisor event {supervisor_event.project_ref_num} to Club Supervisor (paired with Core {core_event.project_ref_num})"
                )
                return

        # Fall back to Primary Lead Event Specialist (from rotation)
        primary_lead_id = self.rotation_manager.get_rotation_employee_id(supervisor_datetime, 'primary_lead')
        if primary_lead_id:
            primary_lead = self.db.query(self.Employee).get(primary_lead_id)
            if primary_lead:
                day_available = True

                # Check time off
                time_off = self.db.query(self.EmployeeTimeOff).filter(
                    self.EmployeeTimeOff.employee_id == primary_lead.id,
                    self.EmployeeTimeOff.start_date <= target_date,
                    self.EmployeeTimeOff.end_date >= target_date
                ).first()

                if time_off:
                    day_available = False

                # Check weekly availability
                if day_available:
                    weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                        employee_id=primary_lead.id
                    ).first()

                    if weekly_avail:
                        is_available = getattr(weekly_avail, day_column, True)
                        if not is_available:
                            day_available = False

                if day_available:
                    self._create_pending_schedule(run, supervisor_event, primary_lead, supervisor_datetime, False, None, None)
                    supervisor_event.is_scheduled = True  # Mark as scheduled
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 2 (inline): Scheduled Supervisor event {supervisor_event.project_ref_num} to Primary Lead {primary_lead.name} (paired with Core {core_event.project_ref_num})"
                    )
                    return

        # Failed to schedule Supervisor event
        self._create_failed_pending_schedule(run, supervisor_event, "Club Supervisor and Primary Lead unavailable on scheduled date")
        run.events_failed += 1

    def _schedule_orphaned_supervisor_events(self, run: object, events: List[object]) -> None:
        """
        Rescue pass for orphaned Supervisor events

        Finds unscheduled Supervisor events, looks up their matching Core event's
        scheduled date (from current run's pending schedules or permanent Schedule table),
        and schedules to Club Supervisor or Primary Lead.

        This handles cases where:
        1. Core was scheduled in a previous run but Supervisor wasn't
        2. Inline Supervisor scheduling failed for some reason
        """
        orphaned_supervisors = [e for e in events if e.event_type == 'Supervisor' and not e.is_scheduled]

        current_app.logger.info(f"ORPHANED SUPERVISOR: Found {len(orphaned_supervisors)} unscheduled Supervisor events")

        for supervisor_event in orphaned_supervisors:
            # Extract event number to find matching Core event
            event_number = self._extract_event_number(supervisor_event.project_name)
            if not event_number:
                current_app.logger.info(
                    f"ORPHANED SUPERVISOR: Skipping {supervisor_event.project_ref_num} - no event number in name"
                )
                continue

            # Find the scheduled Core event with matching event number
            core_schedule_date = self._find_scheduled_core_date(run, event_number)

            if core_schedule_date:
                current_app.logger.info(
                    f"ORPHANED SUPERVISOR: Found matching Core scheduled on {core_schedule_date} for {supervisor_event.project_ref_num}"
                )
                self._schedule_supervisor_for_date(run, supervisor_event, core_schedule_date)
            else:
                current_app.logger.info(
                    f"ORPHANED SUPERVISOR: No scheduled Core found for {supervisor_event.project_ref_num} (event# {event_number})"
                )

    def _find_scheduled_core_date(self, run: object, event_number: str) -> Optional[date]:
        """
        Find the scheduled date for a Core event by event number

        Searches:
        1. PendingSchedule table (current run) - only if run is provided
        2. Schedule table (permanent/approved schedules from previous runs)

        Returns the schedule date if found, None otherwise.
        """
        # Check PendingSchedule first (current run) - only if run is provided
        if run is not None:
            pending_schedules = self.db.query(self.PendingSchedule).join(
                self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                self.Event.event_type == 'Core',
                self.PendingSchedule.scheduler_run_id == run.id,
                self.PendingSchedule.failure_reason == None
            ).all()

            for p in pending_schedules:
                if self._extract_event_number(p.event.project_name) == event_number:
                    return p.schedule_datetime.date()

        # Check permanent Schedule table (already approved from previous runs)
        permanent_schedules = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Event.event_type == 'Core'
        ).all()

        for s in permanent_schedules:
            if self._extract_event_number(s.event.project_name) == event_number:
                return s.schedule_datetime.date()

        return None

    def _schedule_supervisor_for_date(self, run: object, supervisor_event: object, target_date: date) -> None:
        """
        Schedule a Supervisor event to a specific date

        Priority:
        1. Club Supervisor (if available that day)
        2. Primary Lead Event Specialist (fallback)
        """
        supervisor_datetime = datetime.combine(target_date, time(12, 0))
        day_of_week = target_date.weekday()
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_column = day_names[day_of_week]

        # Try Club Supervisor first
        club_supervisor = self.db.query(self.Employee).filter_by(
            job_title='Club Supervisor',
            is_active=True
        ).first()

        if club_supervisor:
            day_available = True

            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == club_supervisor.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if time_off:
                day_available = False

            # Check weekly availability
            if day_available:
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=club_supervisor.id
                ).first()

                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)
                    if not is_available:
                        day_available = False

            if day_available:
                self._create_pending_schedule(run, supervisor_event, club_supervisor, supervisor_datetime, False, None, None)
                supervisor_event.is_scheduled = True
                run.events_scheduled += 1
                current_app.logger.info(
                    f"ORPHANED SUPERVISOR: Scheduled {supervisor_event.project_ref_num} to Club Supervisor on {target_date}"
                )
                return

        # Fall back to Primary Lead Event Specialist
        primary_lead = self.rotation_manager.get_rotation_employee(supervisor_datetime, 'primary_lead')
        if primary_lead:
            day_available = True

            # Check time off
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == primary_lead.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if time_off:
                day_available = False

            # Check weekly availability
            if day_available:
                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                    employee_id=primary_lead.id
                ).first()

                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column, True)
                    if not is_available:
                        day_available = False

            if day_available:
                self._create_pending_schedule(run, supervisor_event, primary_lead, supervisor_datetime, False, None, None)
                supervisor_event.is_scheduled = True
                run.events_scheduled += 1
                current_app.logger.info(
                    f"ORPHANED SUPERVISOR: Scheduled {supervisor_event.project_ref_num} to Primary Lead {primary_lead.name} on {target_date}"
                )
                return

        # Failed to schedule
        self._create_failed_pending_schedule(run, supervisor_event, "Club Supervisor and Primary Lead unavailable on Core event date")
        run.events_failed += 1
        current_app.logger.info(
            f"ORPHANED SUPERVISOR: Failed to schedule {supervisor_event.project_ref_num} - no available employee on {target_date}"
        )

    def _schedule_supervisor_events_wave4(self, run: object, events: List[object]) -> None:
        """
        Wave 4: Auto-pair Supervisor events with their Core events

        Links Supervisor events to Core events based on first 6 digits of event name.
        Supervisor events scheduled to:
        1. Club Supervisor at Noon (priority #1, can have unlimited overlaps)
        2. Primary Lead Event Specialist (if Club Supervisor unavailable that day)

        Note: Time conflicts are IGNORED for Supervisor events - multiple can be at noon
        """
        supervisor_events = [e for e in events if e.event_type == 'Supervisor' and not e.is_scheduled]

        for supervisor_event in supervisor_events:
            # Extract event number from Supervisor event name
            supervisor_event_number = self._extract_event_number(supervisor_event.project_name)

            if not supervisor_event_number:
                self._create_failed_pending_schedule(run, supervisor_event, "Cannot extract event number from event name")
                run.events_failed += 1
                continue

            # Find Core event with matching event number
            core_event = None
            core_events = self.db.query(self.Event).filter_by(event_type='Core').all()
            for ce in core_events:
                ce_number = self._extract_event_number(ce.project_name)
                if ce_number == supervisor_event_number:
                    core_event = ce
                    break

            if not core_event:
                self._create_failed_pending_schedule(run, supervisor_event, f"No Core event found with event number {supervisor_event_number}")
                run.events_failed += 1
                continue

            # Get Core event's scheduled date
            core_schedule = self.db.query(self.Schedule).filter_by(
                event_ref_num=core_event.project_ref_num
            ).first()

            if not core_schedule:
                # Check if Core event has a pending schedule (from Wave 2)
                core_pending = self.db.query(self.PendingSchedule).filter_by(
                    event_ref_num=core_event.project_ref_num,
                    scheduler_run_id=run.id
                ).first()

                if core_pending and core_pending.schedule_datetime:
                    # Core event was successfully scheduled in Wave 2 - use that date
                    supervisor_datetime = datetime.combine(core_pending.schedule_datetime.date(), time(12, 0))
                elif core_pending and core_pending.failure_reason:
                    # Core event FAILED to schedule - Supervisor event cannot be scheduled
                    self._create_failed_pending_schedule(
                        run,
                        supervisor_event,
                        f"Core event failed to schedule: {core_pending.failure_reason}"
                    )
                    run.events_failed += 1
                    continue
                else:
                    # This shouldn't happen with wave system, but handle gracefully
                    self._create_failed_pending_schedule(run, supervisor_event, "Core event could not be scheduled")
                    run.events_failed += 1
                    continue
            else:
                # Use the existing schedule
                supervisor_datetime = datetime.combine(core_schedule.schedule_datetime.date(), time(12, 0))

            # Get the target date for availability checks
            target_date = supervisor_datetime.date()

            # Try Club Supervisor first (ignore time conflicts, only check day availability)
            club_supervisor = self.db.query(self.Employee).filter_by(
                job_title='Club Supervisor',
                is_active=True
            ).first()

            if club_supervisor:
                # Only check time-off and weekly availability, NOT schedule conflicts
                from .validation_types import ValidationResult
                day_available = True

                # Check time off
                time_off = self.db.query(self.EmployeeTimeOff).filter(
                    self.EmployeeTimeOff.employee_id == club_supervisor.id,
                    self.EmployeeTimeOff.start_date <= target_date,
                    self.EmployeeTimeOff.end_date >= target_date
                ).first()

                if time_off:
                    day_available = False

                # Check weekly availability
                if day_available:
                    day_of_week = supervisor_datetime.weekday()  # 0=Monday, 6=Sunday
                    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    day_column = day_names[day_of_week]

                    weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                        employee_id=club_supervisor.id
                    ).first()

                    if weekly_avail:
                        is_available = getattr(weekly_avail, day_column, True)
                        if not is_available:
                            day_available = False

                if day_available:
                    self._create_pending_schedule(run, supervisor_event, club_supervisor, supervisor_datetime, False, None, None)
                    run.events_scheduled += 1
                    continue

            # Fall back to Primary Lead Event Specialist (from rotation)
            primary_lead_id = self.rotation_manager.get_rotation_employee_id(supervisor_datetime, 'primary_lead')
            if primary_lead_id:
                primary_lead = self.db.query(self.Employee).get(primary_lead_id)
                if primary_lead:
                    # Check day availability (same as above)
                    day_available = True

                    # Check time off
                    time_off = self.db.query(self.EmployeeTimeOff).filter(
                        self.EmployeeTimeOff.employee_id == primary_lead.id,
                        self.EmployeeTimeOff.start_date <= target_date,
                        self.EmployeeTimeOff.end_date >= target_date
                    ).first()

                    if time_off:
                        day_available = False

                    # Check weekly availability
                    if day_available:
                        day_of_week = supervisor_datetime.weekday()
                        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        day_column = day_names[day_of_week]

                        weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter_by(
                            employee_id=primary_lead.id
                        ).first()

                        if weekly_avail:
                            is_available = getattr(weekly_avail, day_column, True)
                            if not is_available:
                                day_available = False

                    if day_available:
                        self._create_pending_schedule(run, supervisor_event, primary_lead, supervisor_datetime, False, None, None)
                        run.events_scheduled += 1
                        continue

            self._create_failed_pending_schedule(run, supervisor_event, "Club Supervisor and Primary Lead unavailable")
            run.events_failed += 1

    def _get_available_leads(self, event: object, schedule_datetime: datetime) -> List[object]:
        """
        Get available Lead Event Specialists for an event

        Note: Club Supervisor is excluded from Core events but can do other event types
        """
        # For Core events, only get Lead Event Specialists (exclude Club Supervisor)
        if event.event_type == 'Core':
            leads = self.db.query(self.Employee).filter(
                self.Employee.job_title == 'Lead Event Specialist',
                self.Employee.is_active == True
            ).all()
        else:
            # For other event types, include Club Supervisor
            leads = self.db.query(self.Employee).filter(
                self.Employee.job_title.in_(['Lead Event Specialist', 'Club Supervisor']),
                self.Employee.is_active == True
            ).all()

        available = []
        for lead in leads:
            validation = self.validator.validate_assignment(event, lead, schedule_datetime)
            if validation.is_valid:
                available.append(lead)

        return available

    def _get_available_specialists(self, event: object, schedule_datetime: datetime) -> List[object]:
        """Get available Event Specialists for an event"""
        specialists = self.db.query(self.Employee).filter_by(
            job_title='Event Specialist'
        ).all()

        available = []
        for specialist in specialists:
            validation = self.validator.validate_assignment(event, specialist, schedule_datetime)
            if validation.is_valid:
                available.append(specialist)

        return available

    def _try_resolve_conflict(self, event: object, schedule_datetime: datetime) -> Optional[object]:
        """
        Try to resolve a scheduling conflict by finding an event to bump

        Args:
            event: Event to schedule
            schedule_datetime: Desired datetime

        Returns:
            SwapProposal or None
        """
        # Find potential employees
        all_employees = self._get_available_leads(event, schedule_datetime)
        all_employees.extend(self._get_available_specialists(event, schedule_datetime))

        for employee in all_employees:
            swap = self.conflict_resolver.resolve_conflict(event, schedule_datetime, employee.id)
            if swap:
                return swap

        return None

    def _create_pending_schedule(self, run: object, event: object, employee: Optional[object],
                                 schedule_datetime: datetime, is_swap: bool,
                                 bumped_event_ref: Optional[int], swap_reason: Optional[str]) -> None:
        """Create a PendingSchedule record"""
        # CRITICAL VALIDATION: Ensure schedule_datetime is within event period
        # This should never happen if the scheduling logic is correct, but this is a safety check
        if schedule_datetime and not (event.start_datetime <= schedule_datetime <= event.due_datetime):
            current_app.logger.error(
                f"CRITICAL BUG: Attempting to schedule event {event.project_ref_num} ({event.project_name}) "
                f"at {schedule_datetime.strftime('%Y-%m-%d %H:%M')}, which is outside the event period "
                f"({event.start_datetime.strftime('%Y-%m-%d')} to {event.due_datetime.strftime('%Y-%m-%d')}). "
                f"This indicates a bug in the scheduling logic. Event will NOT be scheduled."
            )
            # Don't create the pending schedule - this would result in invalid data
            current_app.logger.error(
                f"Stack trace for debugging: Attempted by employee={employee.name if employee else 'None'}, "
                f"is_swap={is_swap}"
            )
            return

        pending = self.PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=event.project_ref_num,
            employee_id=employee.id if employee else None,
            schedule_datetime=schedule_datetime,
            schedule_time=schedule_datetime.time(),
            status='proposed',
            is_swap=is_swap,
            bumped_event_ref_num=bumped_event_ref,
            swap_reason=swap_reason
        )
        self.db.add(pending)
        self.db.flush()

    def _create_failed_pending_schedule(self, run: object, event: object, failure_reason: str) -> None:
        """Create a PendingSchedule record for a failed scheduling attempt"""
        pending = self.PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=event.project_ref_num,
            employee_id=None,
            schedule_datetime=None,
            schedule_time=None,
            status='proposed',
            failure_reason=failure_reason
        )
        self.db.add(pending)
        self.db.flush()

    def schedule_single_event(self, event: object) -> Optional[dict]:
        """
        Schedule a single event manually

        Used by the manual scheduling interface to schedule one event at a time.

        Args:
            event: Event object to schedule

        Returns:
            dict with 'employee_id' and 'employee_name' if successful, None if failed
        """
        # Determine appropriate time based on event type
        # Updated 2025-12-02: Times moved forward 1 hour for Digital/Freeosk/Other
        if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
            schedule_time = self._get_juicer_time(event)
        elif event.event_type in ['Digital Setup', 'Digital Refresh']:
            schedule_time = time(10, 15)  # 30 min duration, moved from 9:15
        elif event.event_type == 'Digital Teardown':
            schedule_time = time(18, 0)   # 30 min duration, moved from 17:00
        elif event.event_type == 'Freeosk':
            schedule_time = time(10, 0)   # 30 min duration, moved from 9:00
        elif event.event_type == 'Core':
            schedule_time = time(10, 15)   # First 8-block slot (390 min work)
        elif event.event_type == 'Supervisor':
            schedule_time = time(12, 0)   # 5 min
        else:
            schedule_time = time(11, 0)   # 60 min duration, moved from 10:00

        # Determine schedule date
        # For Supervisor events, use the paired Core event's scheduled date instead of their own start date
        if event.event_type == 'Supervisor':
            # Extract event number to find matching Core event
            event_number = self._extract_event_number(event.project_name)
            if event_number:
                # Find the scheduled Core event with matching event number
                core_schedule_date = self._find_scheduled_core_date(None, event_number)
                if core_schedule_date:
                    schedule_date = core_schedule_date
                    current_app.logger.info(
                        f"schedule_single_event: Using Core event's scheduled date {schedule_date} "
                        f"for Supervisor event {event.project_ref_num}"
                    )
                else:
                    # No Core schedule found - fall back to Supervisor's own start date
                    schedule_date = max(event.start_datetime.date(), datetime.now().date())
                    current_app.logger.warning(
                        f"schedule_single_event: No scheduled Core event found for Supervisor {event.project_ref_num}, "
                        f"using Supervisor's start date {schedule_date}"
                    )
            else:
                # Can't extract event number - fall back to Supervisor's own start date
                schedule_date = max(event.start_datetime.date(), datetime.now().date())
                current_app.logger.warning(
                    f"schedule_single_event: Cannot extract event number from Supervisor {event.project_ref_num}, "
                    f"using Supervisor's start date {schedule_date}"
                )
        else:
            # Use event's own start date for non-Supervisor events
            schedule_date = max(event.start_datetime.date(), datetime.now().date())
        
        schedule_datetime = datetime.combine(schedule_date, schedule_time)

        # Try to find an available employee based on event type
        employee = None

        if event.event_type in ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean']:
            # Try rotation Juicer
            employee = self.rotation_manager.get_rotation_employee(schedule_datetime, 'juicer')
        elif event.event_type in ['Digital Setup', 'Digital Refresh', 'Freeosk']:
            # Try Primary Lead first
            employee = self.rotation_manager.get_rotation_employee(schedule_datetime, 'primary_lead')
        elif event.event_type == 'Digital Teardown':
            # Try Secondary Lead
            employee = self.rotation_manager.get_secondary_lead(schedule_datetime)
        elif event.event_type == 'Core':
            # Try Lead Event Specialists
            leads = self.db.query(self.Employee).filter(
                self.Employee.job_title == 'Lead Event Specialist',
                self.Employee.is_active == True
            ).all()
            for lead in leads:
                validation = self.validator.validate_assignment(event, lead, schedule_datetime)
                if validation.is_valid:
                    employee = lead
                    break
        elif event.event_type == 'Supervisor':
            # Try Club Supervisor
            employee = self.db.query(self.Employee).filter_by(
                job_title='Club Supervisor',
                is_active=True
            ).first()

        # Fallback: Try any Lead Event Specialist
        if not employee:
            leads = self.db.query(self.Employee).filter(
                self.Employee.job_title == 'Lead Event Specialist',
                self.Employee.is_active == True
            ).all()
            for lead in leads:
                validation = self.validator.validate_assignment(event, lead, schedule_datetime)
                if validation.is_valid:
                    employee = lead
                    break

        # Fallback: Try any Event Specialist
        if not employee:
            specialists = self.db.query(self.Employee).filter(
                self.Employee.job_title == 'Event Specialist',
                self.Employee.is_active == True
            ).all()
            for specialist in specialists:
                validation = self.validator.validate_assignment(event, specialist, schedule_datetime)
                if validation.is_valid:
                    employee = specialist
                    break

        if employee:
            return {
                'employee_id': employee.id,
                'employee_name': employee.name,
                'schedule_datetime': schedule_datetime
            }

        return None

    def _is_rotation_juicer_on_date(self, employee_id: str, target_date: date) -> bool:
        """Check if employee is the rotation Juicer for a specific date"""
        day_of_week = target_date.weekday()
        # Convert Python weekday to SQLite format: Python 0=Monday, SQLite needed format depends on rotation_assignments table
        # rotation_assignments uses: 0=Monday through 6=Sunday (Python format)
        rotation_employee_id = self.rotation_manager.get_rotation_employee_id(
            datetime.combine(target_date, time(0, 0)),
            'juicer'
        )
        return rotation_employee_id == employee_id

    def _schedule_lead_core_events_wave2(self, run: object, events: List[object]) -> None:
        """
        Wave 2: Schedule Core events to Lead Event Specialists

        Ensures daily coverage by Lead Event Specialists.
        Avoids scheduling Leads who are rotation Juicers on that day.
        """
        core_events = [e for e in events if e.event_type == 'Core' and not e.is_scheduled]

        for event in core_events:
            if event.is_scheduled:
                continue
            if self._try_schedule_core_to_lead_avoiding_juicers(run, event):
                event.is_scheduled = True

    def _try_schedule_core_to_lead_avoiding_juicers(self, run: object, event: object) -> bool:
        """Try to schedule Core event to a Lead, avoiding rotation Juicers"""
        leads = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).all()

        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            time_slot = self._get_next_time_slot(current_date)
            schedule_datetime = datetime.combine(current_date.date(), time_slot)

            for lead in leads:
                # Skip if this Lead is the rotation Juicer for this day
                if self._is_rotation_juicer_on_date(lead.id, current_date.date()):
                    continue

                validation = self.validator.validate_assignment(event, lead, schedule_datetime)
                if validation.is_valid:
                    self._create_pending_schedule(run, event, lead, schedule_datetime, False, None, None)
                    run.events_scheduled += 1
                    current_app.logger.info(
                        f"Wave 2: Scheduled Core event {event.project_ref_num} to Lead {lead.name}"
                    )
                    return True

            current_date += timedelta(days=1)

        return False

    def _schedule_remaining_core_events_wave3(self, run: object, events: List[object]) -> None:
        """
        Wave 3: Schedule remaining Core events to any available employees

        Includes Juicer Baristas (when NOT on rotation that day) and Event Specialists.
        """
        core_events = [e for e in events if e.event_type == 'Core' and not e.is_scheduled]

        for event in core_events:
            if event.is_scheduled:
                continue

            # Try Juicer Baristas (when not juicing)
            if self._try_schedule_core_to_juicer_avoiding_rotation(run, event):
                event.is_scheduled = True
                continue

            # Try Event Specialists
            self._try_schedule_core_to_specialist(run, event)

    def _try_schedule_core_to_juicer_avoiding_rotation(self, run: object, event: object) -> bool:
        """Try to schedule Core event to a Juicer, but only on days they're NOT on rotation"""
        juicers = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Juicer Barista',
            self.Employee.is_active == True
        ).all()

        current_date = self._get_earliest_schedule_date(event)
        while current_date < event.due_datetime:
            time_slot = self._get_next_time_slot(current_date)
            schedule_datetime = datetime.combine(current_date.date(), time_slot)

            for juicer in juicers:
                # Skip if this Juicer is the rotation Juicer for this day
                if self._is_rotation_juicer_on_date(juicer.id, current_date.date()):
                    continue

                # Check if this Juicer has a Juicer event scheduled for this day
                juicer_event_today = self.db.query(self.PendingSchedule).join(
                    self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    self.PendingSchedule.scheduler_run_id == run.id,
                    self.PendingSchedule.employee_id == juicer.id,
                    func.date(self.PendingSchedule.schedule_datetime) == schedule_datetime.date(),
                    self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
                ).first()

                # Only schedule if Juicer is NOT juicing this day
                if not juicer_event_today:
                    validation = self.validator.validate_assignment(event, juicer, schedule_datetime)
                    if validation.is_valid:
                        self._create_pending_schedule(run, event, juicer, schedule_datetime, False, None, None)
                        run.events_scheduled += 1
                        current_app.logger.info(
                            f"Wave 3: Scheduled Core event {event.project_ref_num} to Juicer {juicer.name}"
                        )
                        return True

            current_date += timedelta(days=1)

        return False

    def _schedule_freeosk_digital_events_wave5(self, run: object, events: List[object]) -> None:
        """
        Wave 5: Schedule Freeosk and Digital events to Primary Leads

        Reassigned from old Wave 3.
        """
        # Reuse existing Wave 3 logic
        self._schedule_freeosk_digital_events_wave3(run, events)

    def _rescue_pass_for_urgent_events(self, run: object, events: List[object]) -> None:
        """
        Rescue Pass: Give failed urgent Core events another chance to bump less urgent ones.

        This handles the case where an urgent event was processed early (before less urgent
        events were scheduled) and couldn't find anything to bump at that time.

        Args:
            run: Current scheduler run
            events: All events being processed
        """
        # Find all failed Core events
        failed_schedules = self.db.query(self.PendingSchedule).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.failure_reason != None  # Only failed ones
        ).all()

        failed_core_events = []
        for failed_schedule in failed_schedules:
            # Get the event details
            event = self.db.query(self.Event).filter(
                self.Event.project_ref_num == failed_schedule.event_ref_num
            ).first()

            if event and event.event_type == 'Core':
                failed_core_events.append(event)

        if not failed_core_events:
            current_app.logger.info("RESCUE PASS: No failed Core events to rescue")
            return

        current_app.logger.info(f"RESCUE PASS: Found {len(failed_core_events)} failed Core events")

        # Sort by due date (most urgent first)
        failed_core_events.sort(key=lambda e: e.due_datetime)

        # Try to schedule each failed urgent event by bumping less urgent ones
        rescued_count = 0
        for event in failed_core_events:
            days_until_due = (event.due_datetime - datetime.now()).days

            # Only try to rescue urgent events (due within 7 days)
            if days_until_due > 7:
                continue

            current_app.logger.info(
                f"RESCUE PASS: Attempting to rescue urgent event {event.project_ref_num} "
                f"(due {event.due_datetime.date()}, {days_until_due} days away)"
            )

            # Try to find a bumpable event
            bump_employee, bump_datetime, bump_schedule, is_posted = self._find_bumpable_core_event(run, event)

            if bump_employee and bump_datetime:
                # Try to bump and schedule
                if self._try_cascading_bump_for_core(run, event, bump_employee, bump_datetime, events, "RESCUE PASS", is_posted):
                    # Success! Remove the failure record
                    failed_schedule = self.db.query(self.PendingSchedule).filter(
                        self.PendingSchedule.scheduler_run_id == run.id,
                        self.PendingSchedule.event_ref_num == event.project_ref_num,
                        self.PendingSchedule.failure_reason != None
                    ).first()

                    if failed_schedule:
                        self.db.delete(failed_schedule)
                        self.db.flush()

                    rescued_count += 1
                    run.events_scheduled += 1
                    if run.events_failed > 0:
                        run.events_failed -= 1

                    current_app.logger.info(
                        f"RESCUE PASS: Successfully rescued event {event.project_ref_num}!"
                    )
                else:
                    current_app.logger.info(
                        f"RESCUE PASS: Could not rescue event {event.project_ref_num} - bump failed"
                    )
            else:
                current_app.logger.info(
                    f"RESCUE PASS: Could not rescue event {event.project_ref_num} - no bumpable events found"
                )

        current_app.logger.info(f"RESCUE PASS: Successfully rescued {rescued_count} out of {len([e for e in failed_core_events if (e.due_datetime - datetime.now()).days <= 7])} urgent events")

    def _schedule_other_events_wave6(self, run: object, events: List[object]) -> None:
        """
        Wave 6: Schedule Other events to Club Supervisor or Lead

        Reassigned from old Wave 5.
        """
        # Reuse existing Wave 5 logic
        self._schedule_other_events_wave5(run, events)
