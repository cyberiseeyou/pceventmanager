"""Add PIN authentication fields to Employee model

Revision ID: 9569a75b5dc4
Revises: a1e11e3097a5
Create Date: 2026-03-10 02:32:47.437446

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9569a75b5dc4'
down_revision = 'a1e11e3097a5'
branch_labels = None
depends_on = None


def upgrade():
    # Use raw ALTER TABLE to avoid SQLite batch mode FK issues
    op.add_column('employees', sa.Column('pin_hash', sa.String(length=256), nullable=True))
    op.add_column('employees', sa.Column('has_account', sa.Boolean(), nullable=True, server_default=sa.text('0')))

    # Backfill has_account to False for all existing rows
    op.execute("UPDATE employees SET has_account = 0 WHERE has_account IS NULL")


def downgrade():
    op.drop_column('employees', 'has_account')
    op.drop_column('employees', 'pin_hash')
