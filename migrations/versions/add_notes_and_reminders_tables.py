"""Add notes and recurring_reminders tables

Revision ID: b5e7a9c12345
Revises: ad24a4cc07d2
Create Date: 2026-01-04 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5e7a9c12345'
down_revision = 'ad24a4cc07d2'
branch_labels = None
depends_on = None


def upgrade():
    # Create notes table
    op.create_table('notes',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('note_type', sa.String(length=20), nullable=False, server_default='task'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('due_time', sa.Time(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('linked_employee_id', sa.String(length=50), nullable=True),
        sa.Column('linked_event_ref_num', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for notes table
    op.create_index('idx_notes_type', 'notes', ['note_type'], unique=False)
    op.create_index('idx_notes_incomplete', 'notes', ['is_completed'], unique=False)
    op.create_index('idx_notes_due_date', 'notes', ['due_date'], unique=False)
    op.create_index('idx_notes_employee', 'notes', ['linked_employee_id'], unique=False)
    op.create_index('idx_notes_event', 'notes', ['linked_event_ref_num'], unique=False)
    op.create_index('idx_notes_pending_tasks', 'notes', ['is_completed', 'due_date'], unique=False)

    # Create recurring_reminders table
    op.create_table('recurring_reminders',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('frequency', sa.String(length=20), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('time_of_day', sa.Time(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_triggered', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop recurring_reminders table
    op.drop_table('recurring_reminders')

    # Drop notes table indexes
    op.drop_index('idx_notes_pending_tasks', table_name='notes')
    op.drop_index('idx_notes_event', table_name='notes')
    op.drop_index('idx_notes_employee', table_name='notes')
    op.drop_index('idx_notes_due_date', table_name='notes')
    op.drop_index('idx_notes_incomplete', table_name='notes')
    op.drop_index('idx_notes_type', table_name='notes')

    # Drop notes table
    op.drop_table('notes')
