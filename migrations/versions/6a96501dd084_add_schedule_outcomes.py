"""add schedule outcome columns for ML training

Revision ID: 6a96501dd084
Revises: a7c3e1f89b02
Create Date: 2026-02-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6a96501dd084'
down_revision = 'a7c3e1f89b02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('schedules', sa.Column('was_completed', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('was_swapped', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('was_no_show', sa.Boolean(), nullable=True, server_default=sa.text('0')))
    op.add_column('schedules', sa.Column('completion_notes', sa.Text(), nullable=True))
    op.add_column('schedules', sa.Column('solver_type', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('schedules', 'solver_type')
    op.drop_column('schedules', 'completion_notes')
    op.drop_column('schedules', 'was_no_show')
    op.drop_column('schedules', 'was_swapped')
    op.drop_column('schedules', 'was_completed')
