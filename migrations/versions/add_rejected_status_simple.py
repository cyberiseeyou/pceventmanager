"""Add rejected status to scheduler_run_history - simple version

Revision ID: add_rejected_simple
Revises: 58becd6c9441
Create Date: 2025-11-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rejected_simple'
down_revision = '58becd6c9441'
branch_labels = None
depends_on = None


def upgrade():
    # For PostgreSQL: modify the CHECK constraint in place using raw SQL
    # For SQLite: recreate the table (SQLite doesn't support ALTER CONSTRAINT)
    from sqlalchemy import inspect
    connection = op.get_bind()
    dialect = connection.dialect.name

    if dialect == 'postgresql':
        # PostgreSQL: Just drop and recreate the CHECK constraint
        connection.execute(sa.text('ALTER TABLE scheduler_run_history DROP CONSTRAINT IF EXISTS ck_valid_status'))
        connection.execute(sa.text('''
            ALTER TABLE scheduler_run_history
            ADD CONSTRAINT ck_valid_status
            CHECK (status IN ('running', 'completed', 'failed', 'crashed', 'rejected'))
        '''))
    else:
        # SQLite: Need to recreate the table
        # Create new table with updated constraint
        op.create_table('scheduler_run_history_new',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('run_type', sa.String(length=20), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('total_events_processed', sa.Integer(), nullable=True),
            sa.Column('events_scheduled', sa.Integer(), nullable=True),
            sa.Column('events_requiring_swaps', sa.Integer(), nullable=True),
            sa.Column('events_failed', sa.Integer(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('approved_by_user', sa.String(), nullable=True),
            sa.CheckConstraint("run_type IN ('automatic', 'manual')", name='ck_valid_run_type'),
            sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'crashed', 'rejected')", name='ck_valid_status'),
            sa.PrimaryKeyConstraint('id')
        )

        # Copy data from old table to new table
        connection.execute(sa.text('''
            INSERT INTO scheduler_run_history_new
            SELECT * FROM scheduler_run_history
        '''))

        # Drop old table and rename new one
        op.drop_table('scheduler_run_history')
        op.rename_table('scheduler_run_history_new', 'scheduler_run_history')


def downgrade():
    # Revert to old constraint without 'rejected' status
    connection = op.get_bind()
    dialect = connection.dialect.name

    if dialect == 'postgresql':
        # PostgreSQL: Just drop and recreate the CHECK constraint
        connection.execute(sa.text('ALTER TABLE scheduler_run_history DROP CONSTRAINT IF EXISTS ck_valid_status'))
        connection.execute(sa.text('''
            ALTER TABLE scheduler_run_history
            ADD CONSTRAINT ck_valid_status
            CHECK (status IN ('running', 'completed', 'failed', 'crashed'))
        '''))
    else:
        # SQLite: Need to recreate the table
        # Create new table with original constraint
        op.create_table('scheduler_run_history_old',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('run_type', sa.String(length=20), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('total_events_processed', sa.Integer(), nullable=True),
            sa.Column('events_scheduled', sa.Integer(), nullable=True),
            sa.Column('events_requiring_swaps', sa.Integer(), nullable=True),
            sa.Column('events_failed', sa.Integer(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('approved_by_user', sa.String(), nullable=True),
            sa.CheckConstraint("run_type IN ('automatic', 'manual')", name='ck_valid_run_type'),
            sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'crashed')", name='ck_valid_status'),
            sa.PrimaryKeyConstraint('id')
        )

        # Copy data from current table to old table
        connection.execute(sa.text('''
            INSERT INTO scheduler_run_history_old
            SELECT * FROM scheduler_run_history
        '''))

        # Drop current table and rename old one
        op.drop_table('scheduler_run_history')
        op.rename_table('scheduler_run_history_old', 'scheduler_run_history')
