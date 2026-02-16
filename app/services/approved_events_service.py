"""
Approved Events Service

Merges Walmart Left In Approved events with local database status to provide
a unified view of events that need attention (scheduling, API submission, or scan-out).

Business Rule: Left In Approved events must be scanned out by 6 PM on:
- Fridays
- Saturdays
- Last day of the month
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from calendar import monthrange
from app.constants import CANCELLED_VARIANTS
from sqlalchemy import or_
import logging

logger = logging.getLogger(__name__)


class ApprovedEventsService:
    """
    Service to merge Walmart Left In Approved events with local database status.

    Provides a unified view showing:
    - Event details from Walmart
    - Local scheduling status
    - Assigned employee (if scheduled)
    - Submission status and dates
    - Required actions
    """

    # Local status constants
    STATUS_NOT_IN_DB = 'not_in_db'
    STATUS_UNSCHEDULED = 'unscheduled'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_API_SUBMITTED = 'api_submitted'
    STATUS_API_FAILED = 'api_failed'

    # Status display info
    STATUS_DISPLAY = {
        'not_in_db': {'label': 'Not in DB', 'icon': '❌', 'action': 'Import Event'},
        'unscheduled': {'label': 'Unscheduled', 'icon': '⚠️', 'action': 'Schedule Event'},
        'scheduled': {'label': 'Scheduled', 'icon': '✅', 'action': 'Submit to API'},
        'api_submitted': {'label': 'API Submitted', 'icon': '🔄', 'action': 'Scan Out in Walmart'},
        'api_failed': {'label': 'API Failed', 'icon': '🔴', 'action': 'Retry API Submit'},
    }

    def __init__(self, db, Event, Schedule, Employee, PendingSchedule=None):
        """
        Initialize the service with database models.

        Args:
            db: SQLAlchemy database instance
            Event: Event model class
            Schedule: Schedule model class
            Employee: Employee model class
            PendingSchedule: PendingSchedule model class (optional)
        """
        self.db = db
        self.Event = Event
        self.Schedule = Schedule
        self.Employee = Employee
        self.PendingSchedule = PendingSchedule

    def merge_with_local_status(self, walmart_events: List[Dict]) -> List[Dict]:
        """
        Merge Walmart APPROVED events with local database status.

        Args:
            walmart_events: List of events from Walmart API

        Returns:
            List of merged event dictionaries with local status added
        """
        if not walmart_events:
            return []

        # Remove duplicates from Walmart events (based on eventId)
        # Keep the first occurrence of each event
        # Note: Walmart API returns multiple items per event (one per product)
        seen_event_ids = set()
        unique_walmart_events = []
        duplicate_count = 0

        for event in walmart_events:
            # Try both field names and convert to string for consistent comparison
            event_id = event.get('eventId') or event.get('event_id')
            if event_id:
                event_id_str = str(event_id)
                if event_id_str not in seen_event_ids:
                    seen_event_ids.add(event_id_str)
                    unique_walmart_events.append(event)
                else:
                    duplicate_count += 1

        logger.info(f"Deduplication: {len(walmart_events)} total -> {len(unique_walmart_events)} unique (removed {duplicate_count} duplicates)")

        # Extract unique event IDs from deduplicated Walmart data
        # Note: Walmart browse-event API returns 'eventId' field
        event_ids = set()
        event_id_to_walmart_event = {}
        for event in unique_walmart_events:
            event_id = event.get('eventId')
            if event_id:
                try:
                    event_id_int = int(event_id)
                    event_ids.add(event_id_int)
                    event_id_to_walmart_event[event_id_int] = event
                except (ValueError, TypeError):
                    pass

        # Batch query local data
        # NOTE: We search by project_name containing the Walmart event ID
        # because local events store the Walmart ID in the name like "615849-Tyson-..."
        # while project_ref_num contains the Crossmark internal ID
        local_events = {}
        local_schedules = {}
        local_pending = {}

        if event_ids:
            # Search for events where project_name contains the Walmart event ID
            # ONLY look at CORE events that are NOT cancelled
            for event_id in event_ids:
                event_id_str = str(event_id)
                
                # First, let's see ALL events that match this ID for debugging
                all_matching = self.Event.query.filter(
                    self.Event.project_name.contains(event_id_str)
                ).all()
                
                if all_matching:
                    logger.info(f"Event {event_id}: Found {len(all_matching)} total matches in DB")
                    for e in all_matching:
                        logger.info(f"  - {e.project_ref_num}: type={e.event_type}, condition={e.condition}, edr_status={e.edr_status}, is_scheduled={e.is_scheduled}")
                
                # Filter: Only Core events, exclude cancelled events (check both condition AND edr_status)
                # Note: DB uses "Canceled" (American) spelling, handle both variants
                cancelled_values = list(CANCELLED_VARIANTS)
                matching_events = self.Event.query.filter(
                    self.Event.project_name.contains(event_id_str),
                    self.Event.event_type == 'Core',
                    self.Event.condition.notin_(cancelled_values),
                    or_(
                        self.Event.edr_status.is_(None),
                        self.Event.edr_status.notin_(cancelled_values)
                    )
                ).all()
                
                logger.info(f"Event {event_id}: After Core + not-cancelled filter: {len(matching_events)} matches")

                # If no Core match found, try Juicer Production events (for Juicer events)
                if not matching_events:
                    walmart_event = event_id_to_walmart_event.get(event_id)
                    if walmart_event:
                        event_name = walmart_event.get('eventName') or walmart_event.get('event_name', '')
                        
                        # Check if this is a Juicer event by name
                        # Walmart calls them "Juice Production" not "Juicer Production"
                        if event_name and ('Juicer' in event_name or 'Juice Production' in event_name or 'Juice Survey' in event_name or 'JUICER' in event_name.upper()):
                            logger.info(f"Event {event_id}: Detected as Juicer event, trying date-based matching")
                            
                            # Try matching by date + event type
                            # Get Walmart event date
                            walmart_date_str = walmart_event.get('eventDate') or walmart_event.get('demoDate', '')
                            if walmart_date_str:
                                try:
                                    from datetime import datetime
                                    walmart_date = datetime.strptime(walmart_date_str, '%Y-%m-%d').date()
                                    
                                    # Detect Juicer event type from name
                                    # Walmart uses "Juice Production" not "Juicer Production"
                                    juicer_type = None
                                    event_name_upper = event_name.upper()
                                    if 'DEEP CLEAN' in event_name_upper or 'DEEPCLEAN' in event_name_upper:
                                        juicer_type = 'Juicer Deep Clean'
                                    elif 'SURVEY' in event_name_upper:
                                        juicer_type = 'Juicer Survey'
                                    elif 'PRODUCTION' in event_name_upper or 'JUICE PRODUCTION' in event_name_upper:
                                        juicer_type = 'Juicer Production'
                                    
                                    logger.info(f"Event {event_id}: Searching for Juicer event on {walmart_date}, type={juicer_type}")
                                    
                                    # Search for Juicer events on this date
                                    # Note: DB uses "Canceled" (American) spelling, handle both variants
                                    cancelled_values = list(CANCELLED_VARIANTS)
                                    query = self.Event.query.filter(
                                        self.Event.event_type.like('Juicer%'),
                                        self.Event.condition.notin_(cancelled_values),
                                        or_(
                                            self.Event.edr_status.is_(None),
                                            self.Event.edr_status.notin_(cancelled_values)
                                        )
                                    )
                                    
                                    # Filter by specific type if detected
                                    if juicer_type:
                                        query = query.filter(self.Event.event_type == juicer_type)
                                    
                                    # Get all Juicer events and filter by date
                                    all_juicer_events = query.all()
                                    
                                    # Log what we're looking for
                                    logger.info(f"Event {event_id}: Found {len(all_juicer_events)} Juicer events of type {juicer_type}")
                                    
                                    # Try matching by start_datetime date
                                    matching_events = [
                                        e for e in all_juicer_events 
                                        if e.start_datetime and e.start_datetime.date() == walmart_date
                                    ]
                                    
                                    logger.info(f"Event {event_id}: Looking for walmart_date={walmart_date}")
                                    if all_juicer_events:
                                        sample_dates = [(e.project_ref_num, e.start_datetime.date() if e.start_datetime else None, e.due_datetime.date() if e.due_datetime else None) for e in all_juicer_events[:3]]
                                        logger.info(f"Event {event_id}: Sample dates - {sample_dates}")
                                    
                                    # If no match by start_datetime, try matching by due_datetime
                                    if not matching_events:
                                        logger.info(f"Event {event_id}: No match by start_datetime, trying due_datetime")
                                        matching_events = [
                                            e for e in all_juicer_events 
                                            if e.due_datetime and e.due_datetime.date() == walmart_date
                                        ]
                                    
                                    if matching_events:
                                        logger.info(f"Event {event_id}: Matched {len(matching_events)} Juicer event(s) by date+type")
                                        for match in matching_events:
                                            logger.info(f"  - {match.project_ref_num}: {match.project_name}, scheduled={match.is_scheduled}")
                                    else:
                                        # Log available dates for debugging
                                        available_dates = [e.start_datetime.date() if e.start_datetime else None for e in all_juicer_events[:5]]
                                        logger.warning(f"Event {event_id}: No Juicer events found for date {walmart_date}, type={juicer_type}")
                                        logger.warning(f"  Available dates: {available_dates}")
                                        
                                except (ValueError, AttributeError) as e:
                                    logger.error(f"Event {event_id}: Failed to parse Juicer event date: {e}")
                            else:
                                logger.warning(f"Event {event_id}: Juicer event has no date, cannot match")
                                
                        # If still no match, log that we couldn't find this Juicer event
                        if not matching_events:
                            logger.warning(f"Event {event_id}: Juicer event '{event_name}' could not be matched to local database")

                # If multiple matches remain, prioritize scheduled ones
                if matching_events:
                    # Sort by scheduled status (scheduled first)
                    matching_events.sort(key=lambda e: (
                        0 if e.condition == 'Scheduled' else (1 if e.is_scheduled else 2)
                    ))
                    # Use the first (highest priority) match
                    best_match = matching_events[0]
                    logger.info(f"Event {event_id}: Selected best match = {best_match.project_ref_num} ({best_match.project_name[:50]}...)")
                    local_events[event_id] = best_match

                    # Get schedule for this event using its actual project_ref_num
                    schedule = self.Schedule.query.filter_by(
                        event_ref_num=best_match.project_ref_num
                    ).first()
                    if schedule:
                        local_schedules[event_id] = schedule
                        logger.info(f"Event {event_id}: Found schedule with employee_id={schedule.employee_id}")
                    else:
                        logger.warning(f"Event {event_id}: No schedule found for project_ref_num={best_match.project_ref_num}")

            # Get pending schedules if model available
            if self.PendingSchedule:
                # For each matched event, get its pending schedules
                for event_id, local_event in local_events.items():
                    pending_list = self.PendingSchedule.query.filter_by(
                        event_ref_num=local_event.project_ref_num
                    ).order_by(self.PendingSchedule.created_at.desc()).all()
                    if pending_list:
                        local_pending[event_id] = pending_list[0]

        # Merge data (using deduplicated events)
        merged_events = []
        for walmart_event in unique_walmart_events:
            event_id = walmart_event.get('eventId')
            if not event_id:
                continue

            try:
                event_id = int(event_id)
            except (ValueError, TypeError):
                continue

            local_event = local_events.get(event_id)
            schedule = local_schedules.get(event_id)
            pending = local_pending.get(event_id)
            
            # Debug logging for Juicer events
            walmart_event_name = walmart_event.get('eventName') or walmart_event.get('event_name', '')
            if 'Juicer' in walmart_event_name or 'Juice Production' in walmart_event_name or 'JUICER' in walmart_event_name.upper():
                logger.info(f"Processing Walmart Juicer event {event_id}: {walmart_event_name}")
                logger.info(f"  Local event found: {local_event is not None}")
                if local_event:
                    logger.info(f"    - Local ref: {local_event.project_ref_num}, type: {local_event.event_type}, scheduled: {local_event.is_scheduled}")
                logger.info(f"  Schedule found: {schedule is not None}")
                if schedule:
                    logger.info(f"    - Employee ID: {schedule.employee_id}")
                logger.info(f"  Pending found: {pending is not None}")
                if pending:
                    logger.info(f"    - Employee ID: {pending.employee_id}")

            # Determine local status
            local_status = self._determine_local_status(local_event, schedule, pending)
            status_info = self.STATUS_DISPLAY.get(local_status, {})

            # Get employee info from Schedule record only
            # Don't use stale PendingSchedule data for unscheduled events
            employee_name = None
            employee_id = None
            if schedule and schedule.employee_id:
                employee = self.Employee.query.get(schedule.employee_id)
                if employee:
                    employee_name = employee.name
                    employee_id = employee.id

            # Check if event needs rolling (Walmart date != scheduled date)
            needs_rolling = False
            walmart_date_str = walmart_event.get('eventDate') or walmart_event.get('demoDate', '')
            if schedule and schedule.schedule_datetime and walmart_date_str:
                try:
                    from datetime import datetime
                    walmart_date = datetime.strptime(walmart_date_str, '%Y-%m-%d').date()
                    scheduled_date = schedule.schedule_datetime.date()
                    needs_rolling = (walmart_date != scheduled_date)
                except (ValueError, AttributeError):
                    pass

            # Field names from Walmart daily-schedule-report API
            # Support both camelCase and snake_case variations
            merged = {
                # Walmart data (using actual API field names)
                'event_id': event_id,
                'event_name': walmart_event.get('eventName') or walmart_event.get('event_name', ''),
                'scheduled_date': walmart_event.get('demoDate') or walmart_event.get('eventDate') or walmart_event.get('demo_date', ''),
                'walmart_status': walmart_event.get('status') or walmart_event.get('eventStatus', 'APPROVED'),
                'walmart_event_type': walmart_event.get('eventType') or walmart_event.get('event_type', ''),
                'item_number': walmart_event.get('itemNbr') or walmart_event.get('item_nbr', ''),
                'item_description': walmart_event.get('itemDesc') or walmart_event.get('item_desc', ''),
                'vendor_number': walmart_event.get('vendorBilledNbr') or walmart_event.get('vendor_billed_nbr', ''),
                'dept_number': walmart_event.get('deptNbr') or walmart_event.get('dept_nbr', ''),

                # Local status
                'local_status': local_status,
                'local_status_label': status_info.get('label', 'Unknown'),
                'local_status_icon': status_info.get('icon', '❓'),
                'required_action': status_info.get('action', 'Unknown'),

                # Local event data
                'in_local_db': local_event is not None,
                'is_scheduled': local_event.is_scheduled if local_event else False,
                'local_event_type': local_event.event_type if local_event else None,
                'condition': local_event.condition if local_event else None,
                'due_datetime': local_event.due_datetime.isoformat() if local_event and local_event.due_datetime else None,
                'start_datetime': local_event.start_datetime.isoformat() if local_event and local_event.start_datetime else None,
                'walmart_event_id': getattr(local_event, 'walmart_event_id', None) if local_event else None,

                # Schedule data - only from actual Schedule records
                'assigned_employee_id': employee_id,
                'assigned_employee_name': employee_name,
                'schedule_datetime': (
                    schedule.schedule_datetime.isoformat() if schedule and schedule.schedule_datetime
                    else None
                ),
                'schedule_sync_status': schedule.sync_status if schedule else None,
                'last_synced': schedule.last_synced.isoformat() if schedule and schedule.last_synced else None,
                'needs_rolling': needs_rolling,

                # Pending schedule data
                'pending_status': pending.status if pending else None,
                'api_submitted_at': pending.api_submitted_at.isoformat() if pending and pending.api_submitted_at else None,
                'api_error': pending.api_error_details if pending else None,
            }

            merged_events.append(merged)

        return merged_events

    def _determine_local_status(self, event, schedule, pending) -> str:
        """
        Determine the local status of an event.

        Args:
            event: Local Event model instance or None
            schedule: Local Schedule model instance or None
            pending: Local PendingSchedule model instance or None

        Returns:
            Status string constant
        """
        if event is None:
            return self.STATUS_NOT_IN_DB

        # Check pending schedule status first (may have data even if Event.is_scheduled is False)
        if pending:
            if pending.status == 'api_submitted':
                return self.STATUS_API_SUBMITTED
            elif pending.status == 'api_failed':
                return self.STATUS_API_FAILED

        if not event.is_scheduled and schedule is None and pending is None:
            return self.STATUS_UNSCHEDULED

        # Check schedule sync status
        if schedule:
            if schedule.sync_status == 'synced':
                return self.STATUS_API_SUBMITTED
            elif schedule.sync_status == 'failed':
                return self.STATUS_API_FAILED

        return self.STATUS_SCHEDULED

    def get_summary_counts(self, merged_events: List[Dict]) -> Dict[str, int]:
        """
        Get summary counts by local status.

        Args:
            merged_events: List of merged event dictionaries

        Returns:
            Dictionary with counts per status
        """
        counts = {
            'total': len(merged_events),
            'not_in_db': 0,
            'unscheduled': 0,
            'scheduled': 0,
            'api_submitted': 0,
            'api_failed': 0,
        }

        for event in merged_events:
            status = event.get('local_status', 'unknown')
            if status in counts:
                counts[status] += 1

        return counts

    @staticmethod
    def should_show_scanout_warning() -> Dict[str, Any]:
        """
        Check if scan-out warning should be displayed.

        Business Rule: Left In Approved events must be scanned out by 6 PM on:
        - Fridays
        - Saturdays
        - Last day of the month

        Returns:
            Dictionary with warning info:
            - show_warning: Boolean
            - reason: Why warning is shown
            - urgency: 'normal', 'warning', 'urgent'
            - deadline: '6:00 PM'
        """
        now = datetime.now()
        today = now.date()
        current_hour = now.hour

        is_friday = today.weekday() == 4
        is_saturday = today.weekday() == 5

        # Check if last day of month
        _, last_day = monthrange(today.year, today.month)
        is_last_day = today.day == last_day

        is_scanout_day = is_friday or is_saturday or is_last_day

        if not is_scanout_day:
            return {
                'show_warning': False,
                'reason': None,
                'urgency': 'normal',
                'deadline': None
            }

        # Determine reason
        reasons = []
        if is_friday:
            reasons.append('Friday')
        if is_saturday:
            reasons.append('Saturday')
        if is_last_day:
            reasons.append('Last day of month')

        reason = ' & '.join(reasons)

        # Determine urgency based on time
        if current_hour >= 17:  # 5 PM or later
            urgency = 'urgent'
        elif current_hour >= 14:  # 2 PM or later
            urgency = 'warning'
        else:
            urgency = 'normal'

        return {
            'show_warning': True,
            'reason': reason,
            'urgency': urgency,
            'deadline': '6:00 PM',
            'is_friday': is_friday,
            'is_saturday': is_saturday,
            'is_last_day_of_month': is_last_day,
            'current_hour': current_hour
        }

    @staticmethod
    def get_date_range_for_approved_events() -> tuple:
        """
        Get the recommended date range for fetching approved events.

        Returns:
            Tuple of (start_date, end_date) in YYYY-MM-DD format
            - start_date: First day of previous month
            - end_date: Today
        """
        today = date.today()

        # First day of previous month
        if today.month == 1:
            start_date = today.replace(year=today.year - 1, month=12, day=1)
        else:
            start_date = today.replace(month=today.month - 1, day=1)

        return (start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))

    def find_core_events_by_event_id(self, event_id: int) -> List[Dict]:
        """
        Search for Core events in the local database by event ID.

        Mimics the search behavior of the all events page - searches for events
        where the project_name contains the event ID. Prioritizes Core events
        over Supervisor events.

        Args:
            event_id: The 6-digit event ID from Walmart

        Returns:
            List of matching events with their details:
            - event_id: The project_ref_num
            - project_name: The event name
            - event_type: Core, Supervisor, etc.
            - is_scheduled: Whether the event is scheduled
            - assigned_employee_name: Name of assigned employee (if scheduled)
            - schedule_datetime: Scheduled datetime (if scheduled)
        """
        from sqlalchemy import case

        # Search for events where project_name contains the event ID
        event_id_str = str(event_id)
        matching_events = self.Event.query.filter(
            self.Event.project_name.contains(event_id_str)
        ).order_by(
            # Prioritize Core events over Supervisor over others
            case(
                (self.Event.event_type == 'Core', 0),
                (self.Event.event_type == 'Supervisor', 1),
                else_=2
            )
        ).all()

        results = []
        for event in matching_events:
            # Get schedule info if exists
            schedule = self.Schedule.query.filter_by(
                event_ref_num=event.project_ref_num
            ).first()

            employee_name = None
            schedule_datetime = None
            if schedule:
                employee = self.Employee.query.get(schedule.employee_id)
                employee_name = employee.name if employee else None
                schedule_datetime = schedule.schedule_datetime.isoformat() if schedule.schedule_datetime else None

            results.append({
                'event_id': event.project_ref_num,
                'project_name': event.project_name,
                'event_type': event.event_type,
                'is_scheduled': event.is_scheduled,
                'assigned_employee_name': employee_name,
                'schedule_datetime': schedule_datetime,
                'condition': event.condition,
            })

        logger.info(f"Found {len(results)} local events matching event ID {event_id}")
        return results

    def enrich_with_core_event_data(self, merged_events: List[Dict]) -> List[Dict]:
        """
        Enrich merged Walmart events with matching Core event data from local database.

        For each Walmart event, searches for matching Core events in the local database
        and adds the core_events field with matching local event data.

        Args:
            merged_events: List of merged event dictionaries (from merge_with_local_status)

        Returns:
            The same list with added core_events field for each event
        """
        for event in merged_events:
            event_id = event.get('event_id')
            if event_id:
                core_events = self.find_core_events_by_event_id(event_id)
                event['core_events'] = core_events
                event['core_event_count'] = len(core_events)

        return merged_events
