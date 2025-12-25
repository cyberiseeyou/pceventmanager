"""add_missing_parent_event_ref_num

Revision ID: 835aea74f5fd
Revises: 1c249d0dfbb5
Create Date: 2025-11-22 11:07:01.411125

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '835aea74f5fd'
down_revision = '1c249d0dfbb5'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column already exists before adding
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('events')}

    # Only add the column if it doesn't exist
    if 'parent_event_ref_num' not in existing_columns:
        with op.batch_alter_table('events', schema=None, recreate='never') as batch_op:
            batch_op.add_column(sa.Column('parent_event_ref_num', sa.Integer(), nullable=True))


def downgrade():
    # Check if column exists before dropping
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {col['name'] for col in inspector.get_columns('events')}

    # Only drop the column if it exists
    if 'parent_event_ref_num' in existing_columns:
        with op.batch_alter_table('events', schema=None, recreate='never') as batch_op:
            batch_op.drop_column('parent_event_ref_num')
