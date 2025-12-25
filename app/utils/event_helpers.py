"""
Event Helper Utilities
=======================

Utility functions for event processing and data extraction.

These helpers are used throughout the application to standardize event
data handling, especially for integration with external systems like
Walmart RetailLink.
"""

import re
from typing import Optional
from datetime import datetime, date


def extract_event_number(project_name):
    """
    Extract the first 6 digits from a Core event's project name.

    This event number is used as the EDR ID in Walmart's RetailLink system.

    Args:
        project_name (str): Event project name (e.g., "606034-JJSF-Super Pretzel King Size")

    Returns:
        str: 6-digit event number or None if not found

    Examples:
        >>> extract_event_number("606034-JJSF-Super Pretzel King Size")
        '606034'
        >>> extract_event_number("Invalid-Event-Name")
        None
    """
    if not project_name:
        return None

    # Look for 6-digit numbers at the start of the project name
    match = re.match(r'^(\d{6})', project_name)
    if match:
        return match.group(1)

    # If no match at start, look for any 6-digit sequence
    match = re.search(r'(\d{6})', project_name)
    if match:
        return match.group(1)

    return None


def parse_event_date(date_str: str) -> Optional[date]:
    """
    Parse event date from various string formats

    Supports multiple date formats commonly used in the system:
    - YYYY-MM-DD (ISO format)
    - MM/DD/YYYY (US format)
    - MM-DD-YYYY (US format with dashes)
    - YYYY/MM/DD (ISO with slashes)

    Args:
        date_str: Date string to parse

    Returns:
        Python date object or None if parsing failed
    """
    if not date_str:
        return None

    # Try various formats
    formats = [
        '%Y-%m-%d',      # 2025-10-05
        '%m/%d/%Y',      # 10/05/2025
        '%m-%d-%Y',      # 10-05-2025
        '%Y/%m/%d',      # 2025/10/05
        '%Y%m%d',        # 20251005
        '%m%d%Y',        # 10052025
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def format_event_date(date_obj: date, format_type: str = 'display') -> str:
    """
    Format date object for display or API

    Args:
        date_obj: Python date object
        format_type: Type of format
            - 'display': MM-DD-YYYY (e.g., "10-05-2025")
            - 'iso': YYYY-MM-DD (e.g., "2025-10-05")
            - 'api': YYYY-MM-DD (same as iso, for API calls)
            - 'filename': YYYYMMDD (e.g., "20251005")

    Returns:
        Formatted date string
    """
    if not date_obj:
        return ''

    format_map = {
        'display': '%m-%d-%Y',
        'iso': '%Y-%m-%d',
        'api': '%Y-%m-%d',
        'filename': '%Y%m%d',
    }

    fmt = format_map.get(format_type, '%Y-%m-%d')
    return date_obj.strftime(fmt)


def is_core_event(event) -> bool:
    """
    Check if event is a Core event type

    Core events require EDR (Event Detail Report) generation
    from Walmart RetailLink.

    Args:
        event: Event model instance

    Returns:
        True if Core event, False otherwise
    """
    if not event:
        return False

    return getattr(event, 'event_type', '') == 'Core'


def is_juicer_production_event(event) -> bool:
    """
    Check if event is a Juicer Production event

    Juicer Production events should be included in schedules
    but do not require EDR generation.

    Args:
        event: Event model instance

    Returns:
        True if Juicer Production event, False otherwise
    """
    if not event:
        return False

    # Check event type
    if getattr(event, 'event_type', '') != 'Juicer':
        return False

    # Check if production event (contains 'Production' in name)
    project_name = getattr(event, 'project_name', '').lower()
    if 'production' not in project_name:
        return False

    # Exclude survey events
    if 'survey' in project_name:
        return False

    return True


def should_include_in_daily_schedule(event) -> bool:
    """
    Determine if event should be included in daily schedule

    Daily schedules include Core and Juicer Production events.

    Args:
        event: Event model instance

    Returns:
        True if event should be included, False otherwise
    """
    return is_core_event(event) or is_juicer_production_event(event)


def sanitize_event_name(event_name: str) -> str:
    """
    Sanitize event name for use in filenames

    Removes or replaces characters that are invalid in filenames.

    Args:
        event_name: Original event name

    Returns:
        Sanitized event name safe for filenames
    """
    if not event_name:
        return 'Unknown_Event'

    # Replace invalid filename characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', event_name)

    # Replace multiple spaces/underscores with single underscore
    sanitized = re.sub(r'[\s_]+', '_', sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')

    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]

    return sanitized or 'Unknown_Event'


def validate_event_number(event_number: str) -> bool:
    """
    Validate that event number is in correct format

    Walmart event numbers must be exactly 6 digits.

    Args:
        event_number: Event number to validate

    Returns:
        True if valid, False otherwise
    """
    if not event_number:
        return False

    # Must be exactly 6 digits
    return bool(re.match(r'^\d{6}$', event_number))


# ============================================================================
# CORE-Supervisor Event Pairing Functions (Calendar Redesign - Sprint 2)
# ============================================================================

def get_supervisor_event(core_event):
    """
    Find Supervisor event paired with CORE event.

    The pairing is based on a 6-digit event number prefix. For example:
    - CORE event: "606001-CORE-Super Pretzel"
    - Supervisor event: "606001-Supervisor-Super Pretzel"

    Args:
        core_event: Event object with project_name containing "-CORE-"

    Returns:
        Event object or None if no matching Supervisor found

    Example:
        >>> core_event = Event.query.filter_by(event_id=1001).first()
        >>> supervisor = get_supervisor_event(core_event)
        >>> if supervisor:
        ...     print(f"Found supervisor: {supervisor.project_name}")
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get Event model from the model class of core_event
    Event = type(core_event)
    from sqlalchemy import inspect

    # Try to get db session from the event
    try:
        db_session = inspect(core_event).session
    except:
        # Fallback: try to import from app context
        try:
            from flask import current_app
            Event = current_app.config.get('Event')
            if not Event:
                from models import Event
        except:
            logger.error("Could not get Event model - unable to query Supervisor")
            return None

    if not core_event:
        logger.warning("get_supervisor_event called with None core_event")
        return None

    # Extract 6-digit event number using regex (case-insensitive)
    match = re.search(r'(\d{6})-CORE-', core_event.project_name, re.IGNORECASE)

    if not match:
        logger.warning(
            f"Could not extract event number from: {core_event.project_name}. "
            f"Expected format: XXXXXX-CORE-ProductName"
        )
        return None

    event_number = match.group(1)
    logger.debug(f"Extracted event number: {event_number} from CORE event {core_event.id}")

    # Find matching Supervisor event (case-insensitive search)
    supervisor_event = Event.query.filter(
        Event.project_name.ilike(f'{event_number}-Supervisor-%')
    ).first()

    if not supervisor_event:
        logger.info(
            f"No Supervisor event found for CORE event {core_event.id} "
            f"(event number: {event_number}). This may be expected."
        )
        return None

    logger.debug(f"Found Supervisor event {supervisor_event.id} for CORE event {core_event.id}")
    return supervisor_event


def get_supervisor_status(core_event):
    """
    Get detailed status of paired Supervisor event.

    Returns comprehensive status information useful for decision-making
    in reschedule/unschedule operations.

    Args:
        core_event: Event object with project_name containing "-CORE-"

    Returns:
        dict: {
            'exists': bool - Whether a Supervisor event exists
            'event': Event object or None
            'is_scheduled': bool - Whether Supervisor is currently scheduled
            'start_datetime': datetime or None - When Supervisor is scheduled
            'condition': str or None - Current condition ('Scheduled' or 'Unstaffed')
        }

    Example:
        >>> core_event = Event.query.filter_by(event_id=1001).first()
        >>> status = get_supervisor_status(core_event)
        >>> if status['exists'] and status['is_scheduled']:
        ...     print(f"Supervisor scheduled for {status['start_datetime']}")
    """
    supervisor = get_supervisor_event(core_event)

    if not supervisor:
        return {
            'exists': False,
            'event': None,
            'is_scheduled': False,
            'start_datetime': None,
            'condition': None
        }

    return {
        'exists': True,
        'event': supervisor,
        'is_scheduled': supervisor.condition == 'Scheduled',
        'start_datetime': supervisor.start_datetime,
        'condition': supervisor.condition
    }


def is_core_event_redesign(event):
    """
    Check if an event is a CORE event based on project_name (for Calendar Redesign).

    This is different from is_core_event() which checks event_type.
    This function checks if the project_name contains "-CORE-".

    Args:
        event: Event object

    Returns:
        bool: True if event is a CORE event, False otherwise

    Example:
        >>> event = Event.query.filter_by(event_id=1001).first()
        >>> if is_core_event_redesign(event):
        ...     print("This is a CORE event")
    """
    if not event or not event.project_name:
        return False

    return '-CORE-' in event.project_name.upper()


def is_supervisor_event(event):
    """
    Check if an event is a Supervisor event based on project_name.

    Args:
        event: Event object

    Returns:
        bool: True if event is a Supervisor event, False otherwise

    Example:
        >>> event = Event.query.filter_by(event_id=1002).first()
        >>> if is_supervisor_event(event):
        ...     print("This is a Supervisor event")
    """
    if not event or not event.project_name:
        return False

    return '-SUPERVISOR-' in event.project_name.upper()


def validate_event_pairing(core_event, supervisor_event):
    """
    Validate that CORE and Supervisor events are properly paired.

    Checks:
    - Both events exist
    - Event numbers match
    - CORE event has "-CORE-" in name
    - Supervisor event has "-Supervisor-" in name

    Args:
        core_event: Event object (expected to be CORE)
        supervisor_event: Event object (expected to be Supervisor)

    Returns:
        tuple: (is_valid: bool, error_message: str or None)

    Example:
        >>> core = Event.query.filter_by(event_id=1001).first()
        >>> supervisor = Event.query.filter_by(event_id=1002).first()
        >>> is_valid, error = validate_event_pairing(core, supervisor)
        >>> if not is_valid:
        ...     print(f"Pairing error: {error}")
    """
    if not core_event:
        return False, "CORE event is None"

    if not supervisor_event:
        return False, "Supervisor event is None"

    if not is_core_event_redesign(core_event):
        return False, f"Event {core_event.id} is not a CORE event"

    if not is_supervisor_event(supervisor_event):
        return False, f"Event {supervisor_event.id} is not a Supervisor event"

    # Extract event numbers from both
    core_match = re.search(r'(\d{6})-CORE-', core_event.project_name, re.IGNORECASE)
    supervisor_match = re.search(r'(\d{6})-SUPERVISOR-', supervisor_event.project_name, re.IGNORECASE)

    if not core_match:
        return False, f"Could not extract event number from CORE: {core_event.project_name}"

    if not supervisor_match:
        return False, f"Could not extract event number from Supervisor: {supervisor_event.project_name}"

    core_number = core_match.group(1)
    supervisor_number = supervisor_match.group(1)

    if core_number != supervisor_number:
        return False, f"Event numbers don't match: CORE={core_number}, Supervisor={supervisor_number}"

    return True, None
