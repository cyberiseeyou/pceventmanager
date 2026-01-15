"""Add edr_status fields to events table for tracking Walmart EDR status

Revision ID: f3e8a1b2c4d5
Revises: ecb50f08c222
Create Date: 2026-01-13 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3e8a1b2c4d5'
down_revision = 'ecb50f08c222'
branch_labels = None
depends_on = None


def upgrade():
    # Add edr_status column to events table
    # This stores the status from Walmart EDR API (e.g., 'Cancelled', 'Active', 'Completed')
    op.add_column('events', sa.Column('edr_status', sa.String(length=50), nullable=True))

    # Add edr_status_updated column to track when the status was last fetched
    op.add_column('events', sa.Column('edr_status_updated', sa.DateTime(), nullable=True))

    # Create index for querying events by EDR status (useful for finding cancelled events)
    op.create_index('idx_events_edr_status', 'events', ['edr_status'], unique=False)


def downgrade():
    op.drop_index('idx_events_edr_status', table_name='events')
    op.drop_column('events', 'edr_status_updated')
    op.drop_column('events', 'edr_status')
