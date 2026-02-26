"""Add solver_type to scheduler_run_history

Revision ID: b3d4e5f6a7b8
Revises: 6a96501dd084
Create Date: 2026-02-19 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3d4e5f6a7b8'
down_revision = '6a96501dd084'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('scheduler_run_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('solver_type', sa.String(20), nullable=True))


def downgrade():
    with op.batch_alter_table('scheduler_run_history', schema=None) as batch_op:
        batch_op.drop_column('solver_type')
