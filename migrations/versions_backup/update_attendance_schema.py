"""
Migration: Update attendance schema to track by employee+date instead of schedule_id

This migration:
1. Drops the old attendance table (if exists) to avoid conflicts
2. Recreates it with employee_id + attendance_date unique constraint
3. Removes the schedule_id foreign key

WARNING: This will delete existing attendance data.
If you need to preserve data, modify this migration to migrate the data first.
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'update_attendance_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade to new attendance schema (employee+date based)
    """
    # Drop old table if exists (WARNING: This deletes data!)
    op.execute("DROP TABLE IF EXISTS employee_attendance")

    # Create new table with updated schema
    op.create_table(
        'employee_attendance',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('employee_id', sa.String(50), nullable=False),
        sa.Column('attendance_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by', sa.String(100), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=True),

        # Foreign key
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),

        # Unique constraint: one record per employee per day
        sa.UniqueConstraint('employee_id', 'attendance_date', name='uix_employee_date'),
    )

    # Create indexes for performance
    op.create_index('ix_employee_attendance_employee_id', 'employee_attendance', ['employee_id'])
    op.create_index('ix_employee_attendance_attendance_date', 'employee_attendance', ['attendance_date'])
    op.create_index('ix_employee_attendance_status', 'employee_attendance', ['status'])


def downgrade():
    """
    Downgrade back to schedule-based attendance (recreates old schema)
    """
    # Drop new table
    op.drop_table('employee_attendance')

    # Recreate old table structure
    op.create_table(
        'employee_attendance',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('employee_id', sa.String(50), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('attendance_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by', sa.String(100), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=True),

        # Foreign keys
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['schedule_id'], ['schedules.id'], ondelete='CASCADE'),
    )

    # Create indexes
    op.create_index('ix_employee_attendance_employee_id', 'employee_attendance', ['employee_id'])
    op.create_index('ix_employee_attendance_attendance_date', 'employee_attendance', ['attendance_date'])
    op.create_index('ix_employee_attendance_status', 'employee_attendance', ['status'])
