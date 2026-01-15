"""
Shift Block Settings Model
Manages the 8 active shift blocks configuration stored in database
Replaces environment variable-based configuration for user editability
"""
import logging
from datetime import datetime, time
from sqlalchemy import Column, Integer, String, Time, DateTime, Boolean

logger = logging.getLogger(__name__)


def create_shift_block_setting_model(db):
    """
    Factory function to create ShiftBlockSetting model

    Args:
        db: SQLAlchemy database instance

    Returns:
        ShiftBlockSetting model class
    """

    class ShiftBlockSetting(db.Model):
        __tablename__ = 'shift_block_settings'

        id = Column(Integer, primary_key=True)
        block_number = Column(Integer, unique=True, nullable=False)  # 1-8

        # Time fields for the shift block
        arrive = Column(Time, nullable=False)
        on_floor = Column(Time, nullable=False)
        lunch_begin = Column(Time, nullable=False)
        lunch_end = Column(Time, nullable=False)
        off_floor = Column(Time, nullable=False)
        depart = Column(Time, nullable=False)

        # Metadata
        is_active = Column(Boolean, default=True)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        updated_by = Column(String(100))

        def to_dict(self):
            """Convert to dictionary format matching ShiftBlockConfig structure"""
            return {
                'block': self.block_number,
                'arrive': self.arrive,
                'on_floor': self.on_floor,
                'lunch_begin': self.lunch_begin,
                'lunch_end': self.lunch_end,
                'off_floor': self.off_floor,
                'depart': self.depart,
                # String versions for display
                'arrive_str': self.arrive.strftime('%H:%M') if self.arrive else None,
                'on_floor_str': self.on_floor.strftime('%H:%M') if self.on_floor else None,
                'lunch_begin_str': self.lunch_begin.strftime('%H:%M') if self.lunch_begin else None,
                'lunch_end_str': self.lunch_end.strftime('%H:%M') if self.lunch_end else None,
                'off_floor_str': self.off_floor.strftime('%H:%M') if self.off_floor else None,
                'depart_str': self.depart.strftime('%H:%M') if self.depart else None,
                'is_active': self.is_active,
            }

        def to_json(self):
            """Convert to JSON-serializable dictionary"""
            return {
                'block': self.block_number,
                'arrive': self.arrive.strftime('%H:%M') if self.arrive else None,
                'on_floor': self.on_floor.strftime('%H:%M') if self.on_floor else None,
                'lunch_begin': self.lunch_begin.strftime('%H:%M') if self.lunch_begin else None,
                'lunch_end': self.lunch_end.strftime('%H:%M') if self.lunch_end else None,
                'off_floor': self.off_floor.strftime('%H:%M') if self.off_floor else None,
                'depart': self.depart.strftime('%H:%M') if self.depart else None,
                'is_active': self.is_active,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'updated_by': self.updated_by
            }

        @classmethod
        def get_all_blocks(cls):
            """
            Get all 8 shift blocks ordered by block number.

            Returns:
                List of ShiftBlockSetting objects
            """
            return cls.query.filter_by(is_active=True).order_by(cls.block_number).all()

        @classmethod
        def get_block(cls, block_number):
            """
            Get a specific shift block.

            Args:
                block_number: Block number 1-8

            Returns:
                ShiftBlockSetting object or None
            """
            return cls.query.filter_by(block_number=block_number, is_active=True).first()

        @classmethod
        def set_block(cls, block_number, arrive, on_floor, lunch_begin, lunch_end,
                      off_floor, depart, user='admin'):
            """
            Create or update a shift block.

            Args:
                block_number: Block number 1-8
                arrive: Arrive time (string HH:MM or time object)
                on_floor: On floor time
                lunch_begin: Lunch begin time
                lunch_end: Lunch end time
                off_floor: Off floor time
                depart: Depart time
                user: User making the change

            Returns:
                ShiftBlockSetting object
            """
            block = cls.query.filter_by(block_number=block_number).first()

            # Parse times if they're strings
            def parse_time(t):
                if isinstance(t, time):
                    return t
                if isinstance(t, str):
                    parts = t.split(':')
                    return time(int(parts[0]), int(parts[1]))
                return t

            arrive = parse_time(arrive)
            on_floor = parse_time(on_floor)
            lunch_begin = parse_time(lunch_begin)
            lunch_end = parse_time(lunch_end)
            off_floor = parse_time(off_floor)
            depart = parse_time(depart)

            if block:
                # Update existing
                block.arrive = arrive
                block.on_floor = on_floor
                block.lunch_begin = lunch_begin
                block.lunch_end = lunch_end
                block.off_floor = off_floor
                block.depart = depart
                block.updated_by = user
                block.updated_at = datetime.utcnow()
            else:
                # Create new
                block = cls(
                    block_number=block_number,
                    arrive=arrive,
                    on_floor=on_floor,
                    lunch_begin=lunch_begin,
                    lunch_end=lunch_end,
                    off_floor=off_floor,
                    depart=depart,
                    updated_by=user
                )
                db.session.add(block)

            db.session.commit()
            return block

        @classmethod
        def initialize_from_env(cls, force=False):
            """
            Initialize shift blocks from environment variables if not already set.

            Args:
                force: If True, overwrite existing blocks

            Returns:
                Number of blocks initialized
            """
            from decouple import config

            count = 0
            for block_num in range(1, 9):
                # Check if block already exists
                existing = cls.query.filter_by(block_number=block_num).first()
                if existing and not force:
                    continue

                prefix = f"SHIFT_{block_num}_"
                try:
                    arrive = config(f"{prefix}ARRIVE", default=None)
                    on_floor = config(f"{prefix}ON_FLOOR", default=None)
                    lunch_begin = config(f"{prefix}LUNCH_BEGIN", default=None)
                    lunch_end = config(f"{prefix}LUNCH_END", default=None)
                    off_floor = config(f"{prefix}OFF_FLOOR", default=None)
                    depart = config(f"{prefix}DEPART", default=None)

                    if all([arrive, on_floor, lunch_begin, lunch_end, off_floor, depart]):
                        cls.set_block(
                            block_number=block_num,
                            arrive=arrive,
                            on_floor=on_floor,
                            lunch_begin=lunch_begin,
                            lunch_end=lunch_end,
                            off_floor=off_floor,
                            depart=depart,
                            user='system_init'
                        )
                        count += 1
                        logger.info(f"Initialized shift block {block_num} from environment")
                except Exception as e:
                    logger.warning(f"Could not initialize block {block_num} from env: {e}")

            return count

    return ShiftBlockSetting
