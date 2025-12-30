"""
Shift Block Configuration Service
Loads and manages 8 active shift blocks + 4 legacy slots from environment variables

The 8 active shift blocks are used for new Core event scheduling.
The 4 legacy slots are for backward compatibility display of events scheduled
before this system was implemented.
"""
import os
from datetime import time
from typing import List, Dict, Optional
from decouple import Config, RepositoryEnv
import logging

logger = logging.getLogger(__name__)

# Create a decouple Config that explicitly uses the .env file from project root
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
config = Config(RepositoryEnv(_ENV_PATH))


class ShiftBlockConfig:
    """
    Load and manage shift blocks from environment variables.
    
    Active blocks (1-8): Used for scheduling new Core events
    Legacy slots (1-4): Display-only for backward compatibility
    
    Block Assignment Order:
    - First 8 events: Sequential order 1, 2, 3, 4, 5, 6, 7, 8
    - Overflow (9+ events): Priority order 1, 3, 5, 7, 2, 4, 6, 8
    """
    
    # Sequential order for first 8 assignments
    BLOCK_SEQUENTIAL_ORDER = [1, 2, 3, 4, 5, 6, 7, 8]
    
    # Priority order for overflow assignments (9+ events on same day)
    # Odd blocks first (different arrive times), then even blocks
    BLOCK_OVERFLOW_ORDER = [1, 3, 5, 7, 2, 4, 6, 8]
    
    # Cache for loaded blocks
    _blocks_cache: Optional[List[Dict]] = None
    _legacy_cache: Optional[List[Dict]] = None
    
    # ===== Active Blocks (1-8) - Schedulable =====
    
    @classmethod
    def get_all_blocks(cls) -> List[Dict]:
        """
        Get all 8 active shift blocks with their times.
        
        Returns:
            List of dicts with keys: block, arrive, on_floor, lunch_begin, 
            lunch_end, off_floor, depart
        """
        if cls._blocks_cache is not None:
            return cls._blocks_cache
        
        blocks = []
        for block_num in range(1, 9):
            block = cls._load_block(block_num)
            if block:
                blocks.append(block)
            else:
                logger.warning(f"Shift block {block_num} not fully configured in .env")
        
        cls._blocks_cache = blocks
        return blocks
    
    @classmethod
    def _load_block(cls, block_num: int) -> Optional[Dict]:
        """Load a single shift block from environment variables."""
        prefix = f"SHIFT_{block_num}_"
        
        try:
            arrive = config(f"{prefix}ARRIVE", default=None)
            on_floor = config(f"{prefix}ON_FLOOR", default=None)
            lunch_begin = config(f"{prefix}LUNCH_BEGIN", default=None)
            lunch_end = config(f"{prefix}LUNCH_END", default=None)
            off_floor = config(f"{prefix}OFF_FLOOR", default=None)
            depart = config(f"{prefix}DEPART", default=None)
            
            if not all([arrive, on_floor, lunch_begin, lunch_end, off_floor, depart]):
                return None
            
            return {
                'block': block_num,
                'arrive': cls._parse_time(arrive),
                'on_floor': cls._parse_time(on_floor),
                'lunch_begin': cls._parse_time(lunch_begin),
                'lunch_end': cls._parse_time(lunch_end),
                'off_floor': cls._parse_time(off_floor),
                'depart': cls._parse_time(depart),
                # String versions for display
                'arrive_str': arrive,
                'on_floor_str': on_floor,
                'lunch_begin_str': lunch_begin,
                'lunch_end_str': lunch_end,
                'off_floor_str': off_floor,
                'depart_str': depart,
            }
        except Exception as e:
            logger.error(f"Error loading shift block {block_num}: {e}")
            return None
    
    @classmethod
    def get_block(cls, block_number: int) -> Optional[Dict]:
        """
        Get a specific shift block (1-8).
        
        Args:
            block_number: Block number 1-8
            
        Returns:
            Block dict or None if not found
        """
        if not 1 <= block_number <= 8:
            return None
        
        blocks = cls.get_all_blocks()
        for block in blocks:
            if block['block'] == block_number:
                return block
        return None
    
    @classmethod
    def get_available_blocks(cls, target_date, db_session=None, Schedule=None) -> List[int]:
        """
        Get shift blocks not yet assigned for a specific date.
        
        Only considers Core events when determining which blocks are assigned.
        
        Args:
            target_date: Date to check
            db_session: SQLAlchemy session (optional, will use registry if not provided)
            Schedule: Schedule model class (optional)
            
        Returns:
            List of available block numbers (1-8)
        """
        from datetime import datetime, timedelta
        
        # Get session and model if not provided
        if db_session is None or Schedule is None:
            try:
                from app.models.registry import get_db, get_models
                db_session = get_db().session
                models = get_models()
                Schedule = models['Schedule']
                Event = models['Event']
            except Exception as e:
                logger.error(f"Error getting database session: {e}")
                return list(range(1, 9))  # Return all blocks if can't check
        else:
            # Get Event model if we have Schedule
            try:
                from app.models.registry import get_models
                Event = get_models()['Event']
            except Exception:
                logger.error("Could not get Event model")
                return list(range(1, 9))
        
        # Query assigned blocks for this date - ONLY for Core events
        start_of_day = datetime.combine(target_date, time(0, 0))
        end_of_day = datetime.combine(target_date, time(23, 59, 59))
        
        # Join with Event to filter by Core events only
        assigned_blocks = db_session.query(Schedule.shift_block).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.schedule_datetime >= start_of_day,
            Schedule.schedule_datetime <= end_of_day,
            Schedule.shift_block.isnot(None),
            Event.event_type == 'Core'  # Only Core events use shift blocks
        ).distinct().all()
        
        assigned_set = {b[0] for b in assigned_blocks if b[0] is not None}
        num_assigned = len(assigned_set)
        
        logger.debug(f"Found {num_assigned} Core events with shift blocks on {target_date}: {assigned_set}")
        
        # First 8 assignments: use sequential order 1, 2, 3, 4, 5, 6, 7, 8
        # After all 8 are assigned (overflow): use priority order 1, 3, 5, 7, 2, 4, 6, 8
        if num_assigned < 8:
            # Still filling initial 8 - return available in sequential order
            available = [b for b in cls.BLOCK_SEQUENTIAL_ORDER if b not in assigned_set]
        else:
            # Overflow - all 8 blocks used at least once, use priority order for 9+ events
            available = list(cls.BLOCK_OVERFLOW_ORDER)
        
        return available
    
    @classmethod
    def assign_next_available_block(cls, schedule, target_date, primary_lead_id=None) -> Optional[int]:
        """
        Assign the next available shift block to a schedule and update the database.
        
        The Primary Lead Event Specialist (if specified) always gets block 1.
        Other employees get blocks 2, 3, 4, etc.
        
        Args:
            schedule: Schedule model instance to update
            target_date: Date of the schedule
            primary_lead_id: Optional employee ID of the Primary Lead (gets block 1)
            
        Returns:
            Assigned block number (1-8) or None if all full
        """
        from datetime import datetime
        
        # If this employee is the Primary Lead, they get block 1
        if primary_lead_id and schedule.employee_id == primary_lead_id:
            schedule.shift_block = 1
            schedule.shift_block_assigned_at = datetime.utcnow()
            logger.info(f"Assigned shift block 1 to Primary Lead schedule {schedule.id}")
            return 1
        
        available = cls.get_available_blocks(target_date)
        
        if not available:
            logger.warning(f"No available shift blocks for {target_date}")
            return None
        
        # If there's a primary lead, don't give block 1 to non-primary-lead employees
        # (reserve block 1 for the primary lead even if they haven't been processed yet)
        if primary_lead_id and 1 in available:
            available = [b for b in available if b != 1]
            if not available:
                logger.warning(f"No available shift blocks for non-primary-lead on {target_date}")
                return None
        
        # Get the first available block
        block_num = available[0]
        
        # Update the schedule's shift_block column
        schedule.shift_block = block_num
        schedule.shift_block_assigned_at = datetime.utcnow()
        
        logger.info(f"Assigned shift block {block_num} to schedule {schedule.id}")
        return block_num
    
    @classmethod
    def get_schedule_datetime_for_block(cls, target_date, block_number: int):
        """
        Get the schedule datetime for a specific block on a given date.
        
        Uses the block's ARRIVE time as the schedule time (the time stored in MVRetail).
        The on_floor time is only used for display on EDRs.
        
        Args:
            target_date: Date for the schedule
            block_number: Block number (1-8)
            
        Returns:
            datetime object or None if block not found
        """
        from datetime import datetime
        
        block = cls.get_block(block_number)
        if not block:
            return None
        
        return datetime.combine(target_date, block['arrive'])
    
    # ===== Legacy Slots (1-4) - Display Only =====
    
    @classmethod
    def get_legacy_slots(cls) -> List[Dict]:
        """
        Get all 4 legacy slots for backward compatibility display.
        
        Returns:
            List of dicts with keys: slot, start, lunch_begin, lunch_end, end
        """
        if cls._legacy_cache is not None:
            return cls._legacy_cache
        
        slots = []
        for slot_num in range(1, 5):
            slot = cls._load_legacy_slot(slot_num)
            if slot:
                slots.append(slot)
            else:
                logger.warning(f"Legacy slot {slot_num} not fully configured in .env")
        
        cls._legacy_cache = slots
        return slots
    
    @classmethod
    def _load_legacy_slot(cls, slot_num: int) -> Optional[Dict]:
        """Load a single legacy slot from environment variables."""
        prefix = f"LEGACY_SLOT_{slot_num}_"
        
        try:
            start = config(f"{prefix}START", default=None)
            lunch_begin = config(f"{prefix}LUNCH_BEGIN", default=None)
            lunch_end = config(f"{prefix}LUNCH_END", default=None)
            end = config(f"{prefix}END", default=None)
            
            if not all([start, lunch_begin, lunch_end, end]):
                return None
            
            return {
                'slot': slot_num,
                'start': cls._parse_time(start),
                'lunch_begin': cls._parse_time(lunch_begin),
                'lunch_end': cls._parse_time(lunch_end),
                'end': cls._parse_time(end),
                # String versions for display
                'start_str': start,
                'lunch_begin_str': lunch_begin,
                'lunch_end_str': lunch_end,
                'end_str': end,
                'legacy': True,
            }
        except Exception as e:
            logger.error(f"Error loading legacy slot {slot_num}: {e}")
            return None
    
    @classmethod
    def get_legacy_slot(cls, slot_number: int) -> Optional[Dict]:
        """
        Get a specific legacy slot (1-4).
        
        Args:
            slot_number: Slot number 1-4
            
        Returns:
            Slot dict or None if not found
        """
        if not 1 <= slot_number <= 4:
            return None
        
        slots = cls.get_legacy_slots()
        for slot in slots:
            if slot['slot'] == slot_number:
                return slot
        return None
    
    @classmethod
    def find_legacy_slot_by_time(cls, schedule_time: time) -> Optional[Dict]:
        """
        Find the legacy slot matching a scheduled start time.
        
        Used for displaying times on events scheduled before the shift block update.
        
        Args:
            schedule_time: The scheduled start time to match
            
        Returns:
            Matching legacy slot dict or None if no match
        """
        slots = cls.get_legacy_slots()
        
        for slot in slots:
            # Match if hours and minutes are the same
            if (slot['start'].hour == schedule_time.hour and 
                slot['start'].minute == schedule_time.minute):
                return slot
        
        return None
    
    @classmethod
    def find_block_by_on_floor_time(cls, on_floor_time: time) -> Optional[Dict]:
        """
        Find an active shift block by its on_floor (start) time.
        
        Args:
            on_floor_time: The on_floor time to match
            
        Returns:
            Matching block dict or None if no match
        """
        blocks = cls.get_all_blocks()
        
        for block in blocks:
            if (block['on_floor'].hour == on_floor_time.hour and
                block['on_floor'].minute == on_floor_time.minute):
                return block
        
        return None
    
    @classmethod
    def find_block_by_arrive_time(cls, arrive_time: time) -> Optional[Dict]:
        """
        Find an active shift block by its arrive time (the scheduling time).
        
        This is the primary lookup method since arrive time is stored in MVRetail.
        
        Args:
            arrive_time: The arrive time to match
            
        Returns:
            Matching block dict or None if no match. If multiple blocks share the
            same arrive time, returns the first one in priority order.
        """
        # Search in sequential order to get the correct block
        for block_num in cls.BLOCK_SEQUENTIAL_ORDER:
            block = cls.get_block(block_num)
            if block and (block['arrive'].hour == arrive_time.hour and
                         block['arrive'].minute == arrive_time.minute):
                return block
        
        return None
    
    # ===== Utility Methods =====
    
    @classmethod
    def _parse_time(cls, time_str: str) -> time:
        """
        Parse time string (HH:MM) to time object.
        
        Args:
            time_str: Time string in HH:MM format
            
        Returns:
            time object
        """
        try:
            parts = time_str.split(':')
            return time(int(parts[0]), int(parts[1]))
        except Exception as e:
            logger.error(f"Error parsing time '{time_str}': {e}")
            return time(9, 0)  # Default to 9:00 AM
    
    @classmethod
    def format_time_12h(cls, t: time) -> str:
        """
        Format time object to 12-hour string.
        
        Args:
            t: time object
            
        Returns:
            Formatted string like "10:30 AM" or "4:45 PM"
        """
        hour = t.hour
        minute = t.minute
        
        if hour == 0:
            return f"12:{minute:02d} AM"
        elif hour < 12:
            return f"{hour}:{minute:02d} AM"
        elif hour == 12:
            return f"12:{minute:02d} PM"
        else:
            return f"{hour - 12}:{minute:02d} PM"
    
    @classmethod
    def clear_cache(cls):
        """Clear cached blocks (useful for testing or config reload)."""
        cls._blocks_cache = None
        cls._legacy_cache = None


# Convenience functions for direct access

def get_all_shift_blocks() -> List[Dict]:
    """Get all 8 active shift blocks."""
    return ShiftBlockConfig.get_all_blocks()


def get_shift_block(block_number: int) -> Optional[Dict]:
    """Get a specific shift block (1-8)."""
    return ShiftBlockConfig.get_block(block_number)


def get_available_shift_blocks(target_date) -> List[int]:
    """Get available shift blocks for a date."""
    return ShiftBlockConfig.get_available_blocks(target_date)


def get_legacy_slots() -> List[Dict]:
    """Get all 4 legacy slots."""
    return ShiftBlockConfig.get_legacy_slots()


def find_legacy_slot_by_time(schedule_time: time) -> Optional[Dict]:
    """Find legacy slot matching a scheduled time."""
    return ShiftBlockConfig.find_legacy_slot_by_time(schedule_time)


def find_block_by_time(on_floor_time: time) -> Optional[Dict]:
    """Find active block by on_floor time (legacy compatibility)."""
    return ShiftBlockConfig.find_block_by_on_floor_time(on_floor_time)


def find_block_by_arrive_time(arrive_time: time) -> Optional[Dict]:
    """Find active block by arrive time (primary scheduling time)."""
    return ShiftBlockConfig.find_block_by_arrive_time(arrive_time)


def get_block_sequential_order() -> List[int]:
    """Get the sequential block order for first 8 assignments: 1,2,3,4,5,6,7,8."""
    return ShiftBlockConfig.BLOCK_SEQUENTIAL_ORDER


def get_block_overflow_order() -> List[int]:
    """Get the overflow block order for 9+ assignments: 1,3,5,7,2,4,6,8."""
    return ShiftBlockConfig.BLOCK_OVERFLOW_ORDER
