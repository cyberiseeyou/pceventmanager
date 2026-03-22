"""add attendance audit fields modified_by and modified_at

Revision ID: 8a05b405f5fa
Revises: d83af02d5196
Create Date: 2026-03-17 17:16:12.873732

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a05b405f5fa'
down_revision = 'd83af02d5196'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('employee_attendance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modified_by', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('modified_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('employee_attendance', schema=None) as batch_op:
        batch_op.drop_column('modified_at')
        batch_op.drop_column('modified_by')
