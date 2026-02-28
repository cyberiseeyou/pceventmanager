"""merge is_reissued and solver_type migration heads

Revision ID: c3c5508b5ab7
Revises: a1b2c3d4e5f6, b3d4e5f6a7b8
Create Date: 2026-02-28 11:33:52.100963

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3c5508b5ab7'
down_revision = ('a1b2c3d4e5f6', 'b3d4e5f6a7b8')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
