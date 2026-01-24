"""Merge migration heads

Revision ID: 5d395586f2b4
Revises: f3e8a1b2c4d5, f3a9b8e12345
Create Date: 2026-01-22 17:47:57.933118

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5d395586f2b4'
down_revision = ('f3e8a1b2c4d5', 'f3a9b8e12345')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
