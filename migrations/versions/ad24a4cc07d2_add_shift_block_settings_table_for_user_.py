"""Add shift_block_settings table for user-configurable shift blocks

Revision ID: ad24a4cc07d2
Revises: 417d3f098412
Create Date: 2026-01-04 23:27:05.489707

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ad24a4cc07d2'
down_revision = '417d3f098412'
branch_labels = None
depends_on = None


def upgrade():
    # Create shift_block_settings table for user-configurable shift blocks
    op.create_table('shift_block_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('block_number', sa.Integer(), nullable=False),
        sa.Column('arrive', sa.Time(), nullable=False),
        sa.Column('on_floor', sa.Time(), nullable=False),
        sa.Column('lunch_begin', sa.Time(), nullable=False),
        sa.Column('lunch_end', sa.Time(), nullable=False),
        sa.Column('off_floor', sa.Time(), nullable=False),
        sa.Column('depart', sa.Time(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('block_number')
    )


def downgrade():
    op.drop_table('shift_block_settings')
