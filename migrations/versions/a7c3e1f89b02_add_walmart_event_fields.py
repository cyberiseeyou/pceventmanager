"""Add walmart_event_id, billing_only, walmart_items to events table

Revision ID: a7c3e1f89b02
Revises: 5d395586f2b4
Create Date: 2026-02-15 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e1f89b02'
down_revision = '543ad05dc484'
branch_labels = None
depends_on = None


def upgrade():
    # Add walmart_event_id column (6-digit Walmart event number)
    op.add_column('events', sa.Column('walmart_event_id', sa.String(10), nullable=True))
    op.create_index('idx_events_walmart_event_id', 'events', ['walmart_event_id'])

    # Add billing_only flag (for non-staffed Walmart-only events)
    # server_default ensures existing rows get False; model enforces nullable=False
    op.add_column('events', sa.Column('billing_only', sa.Boolean(), nullable=False, server_default='0'))

    # Add walmart_items (JSON array of item details)
    op.add_column('events', sa.Column('walmart_items', sa.Text(), nullable=True))

    # Backfill: Extract 6-digit prefix from Core/Supervisor project_name
    # Pattern: "621455-MAP-..." -> walmart_event_id = "621455"
    op.execute("""
        UPDATE events
        SET walmart_event_id = SUBSTR(project_name, 1, 6)
        WHERE walmart_event_id IS NULL
          AND event_type IN ('Core', 'Supervisor')
          AND LENGTH(project_name) >= 7
          AND SUBSTR(project_name, 7, 1) = '-'
          AND SUBSTR(project_name, 1, 1) GLOB '[0-9]'
          AND SUBSTR(project_name, 2, 1) GLOB '[0-9]'
          AND SUBSTR(project_name, 3, 1) GLOB '[0-9]'
          AND SUBSTR(project_name, 4, 1) GLOB '[0-9]'
          AND SUBSTR(project_name, 5, 1) GLOB '[0-9]'
          AND SUBSTR(project_name, 6, 1) GLOB '[0-9]'
    """)


def downgrade():
    op.drop_index('idx_events_walmart_event_id', table_name='events')
    op.drop_column('events', 'walmart_items')
    op.drop_column('events', 'billing_only')
    op.drop_column('events', 'walmart_event_id')
