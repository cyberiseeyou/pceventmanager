"""Add bumped_posted_schedule_id to pending_schedules

Revision ID: f3a9b8e12345
Revises: ecb50f08c222
Create Date: 2026-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a9b8e12345'
down_revision = 'ecb50f08c222'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column already exists before adding
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('pending_schedules')}

    # Only add the column if it doesn't exist
    if 'bumped_posted_schedule_id' not in existing_columns:
        with op.batch_alter_table('pending_schedules', schema=None, recreate='never') as batch_op:
            batch_op.add_column(sa.Column('bumped_posted_schedule_id', sa.Integer(), nullable=True))


def downgrade():
    # Check if column exists before dropping
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('pending_schedules')}

    # Only drop the column if it exists
    if 'bumped_posted_schedule_id' in existing_columns:
        with op.batch_alter_table('pending_schedules', schema=None, recreate='never') as batch_op:
            batch_op.drop_column('bumped_posted_schedule_id')
