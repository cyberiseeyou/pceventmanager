"""Add locked_days table for schedule protection

Revision ID: ecb50f08c222
Revises: c7f8b2d34567
Create Date: 2026-01-10 15:41:13.839925

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ecb50f08c222'
down_revision = 'c7f8b2d34567'
branch_labels = None
depends_on = None


def upgrade():
    # Create locked_days table
    op.create_table('locked_days',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('locked_date', sa.Date(), nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=False),
        sa.Column('locked_by', sa.String(length=100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('locked_date')
    )
    op.create_index('idx_locked_days_date', 'locked_days', ['locked_date'], unique=False)


def downgrade():
    op.drop_index('idx_locked_days_date', table_name='locked_days')
    op.drop_table('locked_days')
