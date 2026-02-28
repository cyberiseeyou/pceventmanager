"""Add is_reissued flag to events table

Revision ID: a1b2c3d4e5f6
Revises: f3a9b8e12345
Create Date: 2026-02-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f3a9b8e12345'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column already exists before adding
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('events')}

    if 'is_reissued' not in existing_columns:
        with op.batch_alter_table('events', schema=None, recreate='never') as batch_op:
            batch_op.add_column(sa.Column('is_reissued', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    # Backfill any NULLs
    op.execute("UPDATE events SET is_reissued = 0 WHERE is_reissued IS NULL")


def downgrade():
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('events')}

    if 'is_reissued' in existing_columns:
        with op.batch_alter_table('events', schema=None, recreate='never') as batch_op:
            batch_op.drop_column('is_reissued')
