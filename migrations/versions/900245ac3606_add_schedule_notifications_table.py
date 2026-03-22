"""add schedule_notifications table

Revision ID: 900245ac3606
Revises: 9569a75b5dc4
Create Date: 2026-03-12 18:53:42.558564

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '900245ac3606'
down_revision = '9569a75b5dc4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('schedule_notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scheduler_run_id', sa.Integer(), nullable=False),
        sa.Column('event_ref_num', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.String(), nullable=False),
        sa.Column('schedule_date', sa.Date(), nullable=False),
        sa.Column('schedule_time', sa.Time(), nullable=False),
        sa.Column('days_notice', sa.Integer(), nullable=False),
        sa.Column('notified', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('notified_at', sa.DateTime(), nullable=True),
        sa.Column('notified_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['scheduler_run_id'], ['scheduler_run_history.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_ref_num'], ['events.project_ref_num']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('schedule_notifications', schema=None) as batch_op:
        batch_op.create_index('idx_schedule_notifications_run', ['scheduler_run_id'])
        batch_op.create_index('idx_schedule_notifications_notified', ['notified'])


def downgrade():
    with op.batch_alter_table('schedule_notifications', schema=None) as batch_op:
        batch_op.drop_index('idx_schedule_notifications_notified')
        batch_op.drop_index('idx_schedule_notifications_run')

    op.drop_table('schedule_notifications')
