"""add event scheduling overrides table

Revision ID: add_event_scheduling_overrides
Revises: add_employee_termination_date
Create Date: 2025-10-14

Description:
    Adds event_scheduling_overrides table to support per-event auto-scheduler
    control (FR38 - Scenario 8: Auto-Scheduler Event Type Filtering).

    Allows marking specific events as "do not auto-schedule" for manual assignment.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_event_scheduling_overrides'
down_revision = 'add_employee_termination_date'
branch_labels = None
depends_on = None


def upgrade():
    """Create event_scheduling_overrides table"""
    op.create_table(
        'event_scheduling_overrides',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_ref_num', sa.Integer(), nullable=False),
        sa.Column('allow_auto_schedule', sa.Boolean(), nullable=False),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('set_by', sa.String(length=100), nullable=True),
        sa.Column('set_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['event_ref_num'], ['events.project_ref_num'], ),
        sa.UniqueConstraint('event_ref_num', name='uq_event_scheduling_override')
    )


def downgrade():
    """Drop event_scheduling_overrides table"""
    op.drop_table('event_scheduling_overrides')
