"""Add employee import fields

Revision ID: add_emp_import_fields
Revises: add_rejected_simple
Create Date: 2025-11-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_emp_import_fields'
down_revision = 'add_rejected_simple'
branch_labels = None
depends_on = None


def upgrade():
    # Use inspection to check what exists before creating
    # This avoids PostgreSQL transaction failures from try/except
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    # Get existing columns and indexes
    existing_columns = {col['name'] for col in inspector.get_columns('employees')}
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('employees')}

    # Add new employee import fields
    if 'mv_retail_employee_number' not in existing_columns:
        op.add_column('employees', sa.Column('mv_retail_employee_number', sa.String(length=50), nullable=True))

    if 'crossmark_employee_id' not in existing_columns:
        op.add_column('employees', sa.Column('crossmark_employee_id', sa.String(length=50), nullable=True))

    # Add indexes (only if columns exist now)
    # Re-check columns after potential addition
    existing_columns = {col['name'] for col in inspector.get_columns('employees')}

    if 'ix_employees_mv_retail_employee_number' not in existing_indexes and 'mv_retail_employee_number' in existing_columns:
        op.create_index('ix_employees_mv_retail_employee_number', 'employees', ['mv_retail_employee_number'], unique=False)

    # Add unique index for crossmark_employee_id
    if 'uq_employees_crossmark_employee_id' not in existing_indexes and 'crossmark_employee_id' in existing_columns:
        op.create_index('uq_employees_crossmark_employee_id', 'employees', ['crossmark_employee_id'], unique=True)

    # Case-insensitive name index - check by name
    if 'ix_employee_name_lower' not in existing_indexes:
        op.create_index('ix_employee_name_lower', 'employees', [sa.text('lower(name)')], unique=False)


def downgrade():
    # Use inspection to check what exists before dropping
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('employees')}
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('employees')}

    # Remove indexes first
    if 'ix_employee_name_lower' in existing_indexes:
        op.drop_index('ix_employee_name_lower', table_name='employees')

    if 'uq_employees_crossmark_employee_id' in existing_indexes:
        op.drop_index('uq_employees_crossmark_employee_id', table_name='employees')

    if 'ix_employees_mv_retail_employee_number' in existing_indexes:
        op.drop_index('ix_employees_mv_retail_employee_number', table_name='employees')

    # Remove columns using batch mode (required for SQLite DROP COLUMN)
    with op.batch_alter_table('employees', schema=None) as batch_op:
        if 'crossmark_employee_id' in existing_columns:
            batch_op.drop_column('crossmark_employee_id')
        if 'mv_retail_employee_number' in existing_columns:
            batch_op.drop_column('mv_retail_employee_number')
