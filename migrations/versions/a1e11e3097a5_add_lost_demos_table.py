"""add lost_demos table

Revision ID: a1e11e3097a5
Revises: d7e8f9a0b1c2
Create Date: 2026-03-05 11:24:33.545804

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1e11e3097a5'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('lost_demos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_ref_num', sa.Integer(), nullable=False),
        sa.Column('week_start_date', sa.Date(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['event_ref_num'], ['events.project_ref_num'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_ref_num')
    )
    with op.batch_alter_table('lost_demos', schema=None) as batch_op:
        batch_op.create_index('idx_lost_demos_week', ['week_start_date'], unique=False)


def downgrade():
    with op.batch_alter_table('lost_demos', schema=None) as batch_op:
        batch_op.drop_index('idx_lost_demos_week')

    op.drop_table('lost_demos')
