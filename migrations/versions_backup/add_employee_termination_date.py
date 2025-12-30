"""add employee termination date field

Revision ID: add_employee_termination_date
Revises: add_employee_availability_overrides
Create Date: 2025-10-14

Description:
    Adds termination_date field to employees table to track when an employee's
    employment ended (FR34 - Scenario 4: Employee Termination).

    This enables automated workflow for handling future scheduled events when
    an employee is terminated.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_employee_termination_date'
down_revision = 'add_employee_availability_overrides'
branch_labels = None
depends_on = None


def upgrade():
    """Add termination_date column to employees table"""
    op.add_column('employees', sa.Column('termination_date', sa.Date(), nullable=True))


def downgrade():
    """Remove termination_date column from employees table"""
    op.drop_column('employees', 'termination_date')
