"""
Event Time Settings Service
Provides functions to load and manage configurable event times from database
"""
from datetime import time
from typing import List, Dict, Optional, Tuple
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class EventTimeSettings:
    """
    Service class for managing event time settings
    Provides caching and fallback to defaults if settings not configured
    """

    _cache = {}
    _cache_initialized = False

    @classmethod
    def _get_setting(cls, key: str, default: str = None) -> Optional[str]:
        """
        Get a setting value from database with caching

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        from app.models.registry import get_models

        # Return cached value if available
        if cls._cache_initialized and key in cls._cache:
            return cls._cache[key]

        try:
            models = get_models()
            SystemSetting = models['SystemSetting']
            value = SystemSetting.get_setting(key, default)
            cls._cache[key] = value
            return value
        except Exception as e:
            logger.warning(f"Error loading setting {key}: {e}")
            return default

    @classmethod
    def clear_cache(cls):
        """Clear the settings cache"""
        cls._cache = {}
        cls._cache_initialized = False

    @classmethod
    def initialize_cache(cls):
        """Pre-load all event time settings into cache"""
        if cls._cache_initialized:
            return

        try:
            # Load all event time settings
            for event_type in ['freeosk', 'supervisor', 'other']:
                cls._get_setting(f'{event_type}_start_time')
                cls._get_setting(f'{event_type}_end_time')

            for slot in range(1, 5):
                for event_type in ['digital_setup', 'digital_teardown']:
                    cls._get_setting(f'{event_type}_{slot}_start_time')
                    cls._get_setting(f'{event_type}_{slot}_end_time')

                # Core slots have lunch times too
                cls._get_setting(f'core_{slot}_start_time')
                cls._get_setting(f'core_{slot}_lunch_begin_time')
                cls._get_setting(f'core_{slot}_lunch_end_time')
                cls._get_setting(f'core_{slot}_end_time')

            cls._cache_initialized = True
        except Exception as e:
            logger.error(f"Error initializing event time settings cache: {e}")

    @classmethod
    def are_settings_configured(cls) -> Tuple[bool, List[str]]:
        """
        Check if all required event time settings are configured

        Returns:
            Tuple of (all_configured: bool, missing_settings: List[str])
        """
        missing = []

        # Check single-slot events
        for event_type in ['freeosk', 'supervisor', 'other']:
            if not cls._get_setting(f'{event_type}_start_time'):
                missing.append(f'{event_type}_start_time')
            if not cls._get_setting(f'{event_type}_end_time'):
                missing.append(f'{event_type}_end_time')

        # Check multi-slot events
        for slot in range(1, 5):
            for event_type in ['digital_setup', 'digital_teardown']:
                if not cls._get_setting(f'{event_type}_{slot}_start_time'):
                    missing.append(f'{event_type}_{slot}_start_time')
                if not cls._get_setting(f'{event_type}_{slot}_end_time'):
                    missing.append(f'{event_type}_{slot}_end_time')

            # Core slots
            if not cls._get_setting(f'core_{slot}_start_time'):
                missing.append(f'core_{slot}_start_time')
            if not cls._get_setting(f'core_{slot}_lunch_begin_time'):
                missing.append(f'core_{slot}_lunch_begin_time')
            if not cls._get_setting(f'core_{slot}_lunch_end_time'):
                missing.append(f'core_{slot}_lunch_end_time')
            if not cls._get_setting(f'core_{slot}_end_time'):
                missing.append(f'core_{slot}_end_time')

        return len(missing) == 0, missing

    @classmethod
    def get_freeosk_times(cls) -> Dict[str, time]:
        """Get Freeosk event times"""
        start = cls._get_setting('freeosk_start_time', '10:00')
        end = cls._get_setting('freeosk_end_time', '10:30')
        return {
            'start': cls._parse_time(start),
            'end': cls._parse_time(end)
        }

    @classmethod
    def get_digital_setup_slots(cls) -> List[Dict[str, time]]:
        """Get Digital Setup time slots (4 slots) - 30 min each starting at 10:15"""
        # Default times moved forward 1 hour from original 9:15
        defaults = [
            {'start': '10:15', 'end': '10:45'},
            {'start': '10:30', 'end': '11:00'},
            {'start': '10:45', 'end': '11:15'},
            {'start': '11:00', 'end': '11:30'},
        ]
        slots = []
        for slot in range(1, 5):
            default = defaults[slot - 1]
            start = cls._get_setting(f'digital_setup_{slot}_start_time', default['start'])
            end = cls._get_setting(f'digital_setup_{slot}_end_time', default['end'])
            slots.append({
                'slot': slot,
                'start': cls._parse_time(start),
                'end': cls._parse_time(end)
            })
        return slots

    @classmethod
    def get_core_slots(cls) -> List[Dict[str, time]]:
        """Get Core event time slots (4 slots with lunch breaks)"""
        # Default times
        defaults = [
            {'start': '09:45', 'lunch_begin': '13:00', 'lunch_end': '13:30', 'end': '16:15'},
            {'start': '10:30', 'lunch_begin': '13:45', 'lunch_end': '14:15', 'end': '17:00'},
            {'start': '11:00', 'lunch_begin': '14:15', 'lunch_end': '14:45', 'end': '17:30'},
            {'start': '11:30', 'lunch_begin': '14:45', 'lunch_end': '15:15', 'end': '18:00'},
        ]

        slots = []
        for slot in range(1, 5):
            default = defaults[slot - 1]
            start = cls._get_setting(f'core_{slot}_start_time', default['start'])
            lunch_begin = cls._get_setting(f'core_{slot}_lunch_begin_time', default['lunch_begin'])
            lunch_end = cls._get_setting(f'core_{slot}_lunch_end_time', default['lunch_end'])
            end = cls._get_setting(f'core_{slot}_end_time', default['end'])

            slots.append({
                'slot': slot,
                'start': cls._parse_time(start),
                'lunch_begin': cls._parse_time(lunch_begin),
                'lunch_end': cls._parse_time(lunch_end),
                'end': cls._parse_time(end)
            })
        return slots

    @classmethod
    def get_supervisor_times(cls) -> Dict[str, time]:
        """Get Supervisor event times"""
        start = cls._get_setting('supervisor_start_time', '12:00')
        end = cls._get_setting('supervisor_end_time', '12:05')
        return {
            'start': cls._parse_time(start),
            'end': cls._parse_time(end)
        }

    @classmethod
    def get_digital_teardown_slots(cls) -> List[Dict[str, time]]:
        """Get Digital Teardown time slots (4 slots) - 30 min each starting at 17:00"""
        # Default times at 5:00 PM - 5:45 PM
        defaults = [
            {'start': '17:00', 'end': '17:30'},
            {'start': '17:15', 'end': '17:45'},
            {'start': '17:30', 'end': '18:00'},
            {'start': '17:45', 'end': '18:15'},
        ]
        slots = []
        for slot in range(1, 5):
            default = defaults[slot - 1]
            start = cls._get_setting(f'digital_teardown_{slot}_start_time', default['start'])
            end = cls._get_setting(f'digital_teardown_{slot}_end_time', default['end'])
            slots.append({
                'slot': slot,
                'start': cls._parse_time(start),
                'end': cls._parse_time(end)
            })
        return slots

    @classmethod
    def get_other_times(cls) -> Dict[str, time]:
        """Get Other event type times - 60 min duration"""
        start = cls._get_setting('other_start_time', '11:00')
        end = cls._get_setting('other_end_time', '12:00')
        return {
            'start': cls._parse_time(start),
            'end': cls._parse_time(end)
        }

    @classmethod
    def get_allowed_times_for_event_type(cls, event_type: str, project_name: str = None) -> List[str]:
        """
        Get allowed start times for an event type

        Args:
            event_type: Event type name
            project_name: Optional project name for detecting sub-types (e.g., Digital Teardown)

        Returns:
            List of allowed time strings (HH:MM format)
        """
        event_type_lower = event_type.lower()
        project_name_lower = (project_name or '').lower()

        if 'core' in event_type_lower:
            slots = cls.get_core_slots()
            return [cls._time_to_str(slot['start']) for slot in slots]

        elif 'supervisor' in event_type_lower:
            times = cls.get_supervisor_times()
            return [cls._time_to_str(times['start'])]

        elif 'freeosk' in event_type_lower:
            times = cls.get_freeosk_times()
            # Include both default Freeosk time AND noon for troubleshooting events
            allowed = [cls._time_to_str(times['start'])]
            if '12:00' not in allowed:
                allowed.append('12:00')  # Noon for troubleshooting events
            return allowed

        elif event_type_lower == 'digitals' or 'digital' in event_type_lower:
            # Check project name for teardown detection
            if 'tear down' in project_name_lower or 'teardown' in project_name_lower:
                slots = cls.get_digital_teardown_slots()
                return [cls._time_to_str(slot['start']) for slot in slots]
            elif 'digital teardown' in event_type_lower:
                slots = cls.get_digital_teardown_slots()
                return [cls._time_to_str(slot['start']) for slot in slots]
            else:
                # Digital Setup/Refresh
                slots = cls.get_digital_setup_slots()
                return [cls._time_to_str(slot['start']) for slot in slots]

        elif 'other' in event_type_lower:
            times = cls.get_other_times()
            return [cls._time_to_str(times['start'])]

        else:
            # Default - return an empty list or common times
            return []

    @classmethod
    def _parse_time(cls, time_str: str) -> time:
        """
        Parse time string to time object

        Args:
            time_str: Time string in HH:MM format

        Returns:
            time object
        """
        try:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            return time(hour, minute)
        except Exception as e:
            logger.error(f"Error parsing time '{time_str}': {e}")
            return time(9, 0)  # Default to 9:00 AM

    @classmethod
    def _time_to_str(cls, time_obj: time) -> str:
        """
        Convert time object to HH:MM string

        Args:
            time_obj: time object

        Returns:
            Time string in HH:MM format
        """
        return f'{time_obj.hour:02d}:{time_obj.minute:02d}'


# Convenience functions for direct access
def get_freeosk_times() -> Dict[str, time]:
    """Get Freeosk event times"""
    return EventTimeSettings.get_freeosk_times()


def get_digital_setup_slots() -> List[Dict[str, time]]:
    """Get Digital Setup time slots"""
    return EventTimeSettings.get_digital_setup_slots()


def get_core_slots() -> List[Dict[str, time]]:
    """Get Core event time slots"""
    return EventTimeSettings.get_core_slots()


def get_supervisor_times() -> Dict[str, time]:
    """Get Supervisor event times"""
    return EventTimeSettings.get_supervisor_times()


def get_digital_teardown_slots() -> List[Dict[str, time]]:
    """Get Digital Teardown time slots"""
    return EventTimeSettings.get_digital_teardown_slots()


def get_other_times() -> Dict[str, time]:
    """Get Other event type times"""
    return EventTimeSettings.get_other_times()


def get_allowed_times_for_event_type(event_type: str, project_name: str = None) -> List[str]:
    """Get allowed start times for an event type"""
    return EventTimeSettings.get_allowed_times_for_event_type(event_type, project_name)


def are_event_times_configured() -> Tuple[bool, List[str]]:
    """Check if all event time settings are configured"""
    return EventTimeSettings.are_settings_configured()


def clear_event_time_cache():
    """Clear the event time settings cache"""
    EventTimeSettings.clear_cache()
