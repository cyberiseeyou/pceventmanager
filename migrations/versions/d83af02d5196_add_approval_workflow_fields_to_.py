"""add approval workflow fields to employee_time_off

Revision ID: d83af02d5196
Revises: 7ee425a7df36
Create Date: 2026-03-17 02:08:21.253935

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd83af02d5196'
down_revision = '7ee425a7df36'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('employee_time_off', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=20), server_default='approved', nullable=False))
        batch_op.add_column(sa.Column('reviewed_by', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('denial_reason', sa.String(length=500), nullable=True))
        batch_op.create_index('idx_employee_time_off_status', ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('employee_time_off', schema=None) as batch_op:
        batch_op.drop_index('idx_employee_time_off_status')
        batch_op.drop_column('denial_reason')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('status')
