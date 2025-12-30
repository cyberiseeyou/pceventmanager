"""Add performance indexes to Schedule, Event, and Employee models

Revision ID: add_performance_indexes
Revises: (use the latest migration ID from your migrations/versions/)
Create Date: 2025-10-25

This migration adds database indexes to improve query performance:
- Schedule: employee_date, event, sync status indexes
- Event: scheduled, date_range, type, location, sync indexes
- Employee: active, job_title, supervisor, termination indexes
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_performance_indexes'
down_revision = 'add_event_scheduling_overrides'  # Points to Oct 14 migration
branch_labels = None
depends_on = None


def upgrade():
    """Add all performance indexes"""

    # ===========================================================================
    # Schedule table indexes
    # ===========================================================================

    # Composite index for employee + date queries (most common pattern)
    op.create_index(
        'idx_schedules_employee_date',
        'schedules',
        ['employee_id', 'schedule_datetime'],
        unique=False
    )

    # Index for event lookups
    op.create_index(
        'idx_schedules_event',
        'schedules',
        ['event_ref_num'],
        unique=False
    )

    # Index for sync status queries
    op.create_index(
        'idx_schedules_sync',
        'schedules',
        ['sync_status', 'last_synced'],
        unique=False
    )

    # ===========================================================================
    # Event table indexes
    # ===========================================================================

    # Index for filtering scheduled/unscheduled events
    op.create_index(
        'idx_events_scheduled',
        'events',
        ['is_scheduled', 'condition'],
        unique=False
    )

    # Index for date range queries (start/due date filtering)
    op.create_index(
        'idx_events_date_range',
        'events',
        ['start_datetime', 'due_datetime'],
        unique=False
    )

    # Index for event type filtering
    op.create_index(
        'idx_events_type',
        'events',
        ['event_type'],
        unique=False
    )

    # Index for location-based queries
    op.create_index(
        'idx_events_location',
        'events',
        ['location_mvid'],
        unique=False
    )

    # Index for sync operations
    op.create_index(
        'idx_events_sync',
        'events',
        ['sync_status'],
        unique=False
    )

    # ===========================================================================
    # Employee table indexes
    # ===========================================================================

    # Index for active employee queries
    op.create_index(
        'idx_employees_active',
        'employees',
        ['is_active'],
        unique=False
    )

    # Index for job title filtering
    op.create_index(
        'idx_employees_job_title',
        'employees',
        ['job_title'],
        unique=False
    )

    # Index for supervisor queries
    op.create_index(
        'idx_employees_supervisor',
        'employees',
        ['is_supervisor'],
        unique=False
    )

    # Index for termination date queries
    op.create_index(
        'idx_employees_termination',
        'employees',
        ['termination_date'],
        unique=False
    )


def downgrade():
    """Remove all performance indexes"""

    # Schedule table indexes
    op.drop_index('idx_schedules_employee_date', table_name='schedules')
    op.drop_index('idx_schedules_event', table_name='schedules')
    op.drop_index('idx_schedules_sync', table_name='schedules')

    # Event table indexes
    op.drop_index('idx_events_scheduled', table_name='events')
    op.drop_index('idx_events_date_range', table_name='events')
    op.drop_index('idx_events_type', table_name='events')
    op.drop_index('idx_events_location', table_name='events')
    op.drop_index('idx_events_sync', table_name='events')

    # Employee table indexes
    op.drop_index('idx_employees_active', table_name='employees')
    op.drop_index('idx_employees_job_title', table_name='employees')
    op.drop_index('idx_employees_supervisor', table_name='employees')
    op.drop_index('idx_employees_termination', table_name='employees')
