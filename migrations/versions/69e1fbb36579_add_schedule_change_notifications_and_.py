"""add schedule_change_notifications and push_subscriptions tables

Revision ID: 69e1fbb36579
Revises: 8a05b405f5fa
Create Date: 2026-03-24 14:49:02.568307

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '69e1fbb36579'
down_revision = '8a05b405f5fa'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('schedule_change_notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('change_type', sa.String(length=30), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('change_details', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('push_sent', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('push_sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('triggered_by', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('schedule_change_notifications', schema=None) as batch_op:
        batch_op.create_index('idx_scn_employee_read', ['employee_id', 'is_read'])
        batch_op.create_index('idx_scn_employee_created', ['employee_id', 'created_at'])
        batch_op.create_index('idx_scn_push_pending', ['push_sent', 'created_at'])

    op.create_table('push_subscriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh_key', sa.Text(), nullable=False),
        sa.Column('auth_key', sa.Text(), nullable=False),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint', name='uq_push_endpoint'),
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index('idx_push_sub_employee', ['employee_id', 'is_active'])


def downgrade():
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_index('idx_push_sub_employee')
    op.drop_table('push_subscriptions')

    with op.batch_alter_table('schedule_change_notifications', schema=None) as batch_op:
        batch_op.drop_index('idx_scn_push_pending')
        batch_op.drop_index('idx_scn_employee_created')
        batch_op.drop_index('idx_scn_employee_read')
    op.drop_table('schedule_change_notifications')
