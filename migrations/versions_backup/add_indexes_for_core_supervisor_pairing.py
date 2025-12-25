"""add_indexes_for_core_supervisor_pairing

Revision ID: f3d8a1b2c4e5
Revises: 0be04acd9951
Create Date: 2025-10-13 00:00:00.000000

Description:
Add database indexes to optimize CORE-Supervisor event pairing queries.
These indexes improve performance for LIKE queries on project_name and
foreign key lookups used in the Calendar Redesign feature (Sprint 2).

Indexes added:
- events.project_name: For LIKE queries matching CORE/Supervisor patterns
- events.project_ref_num: For event lookups and joins
- schedule.event_ref_num: For schedule lookups by event reference

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3d8a1b2c4e5'
down_revision = '0be04acd9951'
branch_labels = None
depends_on = None


def upgrade():
    """Add indexes for CORE-Supervisor pairing performance optimization."""

    # Index on events.project_name for LIKE queries
    # Used by: get_supervisor_event() - searching for paired Supervisor events
    # Pattern: Event.query.filter(Event.project_name.ilike(f'{event_number}-Supervisor-%'))
    op.create_index(
        'idx_events_project_name',
        'events',
        ['project_name'],
        unique=False
    )

    # Index on events.project_ref_num for event lookups
    # Used by: Event.query.filter_by(project_ref_num=...)
    # Improves foreign key join performance
    op.create_index(
        'idx_events_project_ref_num',
        'events',
        ['project_ref_num'],
        unique=True  # project_ref_num is unique per event
    )

    # Index on schedule.event_ref_num for schedule lookups
    # Used by: Schedule.query.filter_by(event_ref_num=...)
    # Improves schedule lookups when finding paired Supervisor schedules
    op.create_index(
        'idx_schedule_event_ref_num',
        'schedule',
        ['event_ref_num'],
        unique=False  # Multiple schedules can exist per event
    )


def downgrade():
    """Remove indexes for CORE-Supervisor pairing."""

    op.drop_index('idx_schedule_event_ref_num', table_name='schedule')
    op.drop_index('idx_events_project_ref_num', table_name='events')
    op.drop_index('idx_events_project_name', table_name='events')
