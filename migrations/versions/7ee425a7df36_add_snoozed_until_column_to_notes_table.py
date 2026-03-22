"""add snoozed_until column to notes table

Revision ID: 7ee425a7df36
Revises: 900245ac3606
Create Date: 2026-03-13 23:38:10.119619

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7ee425a7df36'
down_revision = '900245ac3606'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('snoozed_until', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.drop_column('snoozed_until')
