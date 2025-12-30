"""add employee availability overrides table

Revision ID: add_employee_availability_overrides
Revises: add_indexes_for_core_supervisor_pairing
Create Date: 2025-10-14

Description:
    Adds employee_availability_overrides table to support temporary weekly
    availability overrides (FR32 - Scenario 2: Temporary Availability Change).

    Example use case: Employee can only work Tue/Thu for 3 weeks due to
    class schedule, then returns to normal Mon-Fri availability.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_employee_availability_overrides'
down_revision = 'add_indexes_for_core_supervisor_pairing'
branch_labels = None
depends_on = None


def upgrade():
    """Create employee_availability_overrides table"""
    op.create_table(
        'employee_availability_overrides',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('monday', sa.Boolean(), nullable=True),
        sa.Column('tuesday', sa.Boolean(), nullable=True),
        sa.Column('wednesday', sa.Boolean(), nullable=True),
        sa.Column('thursday', sa.Boolean(), nullable=True),
        sa.Column('friday', sa.Boolean(), nullable=True),
        sa.Column('saturday', sa.Boolean(), nullable=True),
        sa.Column('sunday', sa.Boolean(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.CheckConstraint('end_date >= start_date', name='check_override_date_range')
    )

    # Create index for faster queries by employee and date range
    op.create_index(
        'idx_employee_override_dates',
        'employee_availability_overrides',
        ['employee_id', 'start_date', 'end_date'],
        unique=False
    )


def downgrade():
    """Drop employee_availability_overrides table"""
    op.drop_index('idx_employee_override_dates', table_name='employee_availability_overrides')
    op.drop_table('employee_availability_overrides')
