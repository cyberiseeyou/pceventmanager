"""add juicer_trained field to employees

Revision ID: add_juicer_trained
Revises: 9a8b7c6d5e4f
Create Date: 2026-01-23 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_juicer_trained'
down_revision = '9a8b7c6d5e4f'
branch_labels = None
depends_on = None


def upgrade():
    # Add juicer_trained column to employees table
    op.add_column('employees', sa.Column('juicer_trained', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    # Remove juicer_trained column
    op.drop_column('employees', 'juicer_trained')
