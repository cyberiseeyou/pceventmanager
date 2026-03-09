"""Add employee_name to schedules and make employee_id nullable

Revision ID: d7e8f9a0b1c2
Revises: f3a9b8e12345
Create Date: 2026-03-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7e8f9a0b1c2'
down_revision = 'c3c5508b5ab7'
branch_labels = None
depends_on = None


def upgrade():
    # Add employee_name column
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('employee_name', sa.String(length=100), nullable=True))

    # Backfill employee_name from employees table
    op.execute(
        "UPDATE schedules SET employee_name = ("
        "SELECT name FROM employees WHERE employees.id = schedules.employee_id"
        ") WHERE employee_id IS NOT NULL"
    )

    # Make employee_id nullable (SQLite requires batch mode)
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.alter_column('employee_id',
                              existing_type=sa.String(length=50),
                              nullable=True)


def downgrade():
    with op.batch_alter_table('schedules', schema=None) as batch_op:
        batch_op.alter_column('employee_id',
                              existing_type=sa.String(length=50),
                              nullable=False)
        batch_op.drop_column('employee_name')
