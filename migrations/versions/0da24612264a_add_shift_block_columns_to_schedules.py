"""Add shift_block columns to schedules

Revision ID: 0da24612264a
Revises: 835aea74f5fd
Create Date: 2025-12-11 07:28:51.521882

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0da24612264a'
down_revision = '835aea74f5fd'
branch_labels = None
depends_on = None


def upgrade():
    # Add shift_block columns to schedules table
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shift_block', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('shift_block_assigned_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.drop_column('shift_block_assigned_at')
        batch_op.drop_column('shift_block')
