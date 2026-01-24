"""Add event_type_overrides table for persistent manual changes

Revision ID: 9a8b7c6d5e4f
Revises: 5d395586f2b4
Create Date: 2026-01-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a8b7c6d5e4f'
down_revision = '5d395586f2b4'
branch_labels = None
depends_on = None


def upgrade():
    # Create event_type_overrides table
    op.create_table('event_type_overrides',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('project_ref_num', sa.Integer(), nullable=False),
        sa.Column('override_event_type', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('event_name_snapshot', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_ref_num'),
        sa.CheckConstraint(
            "override_event_type IN ('Core', 'Juicer Production', 'Juicer Survey', "
            "'Juicer Deep Clean', 'Digital Setup', 'Digital Refresh', 'Digital Teardown', "
            "'Freeosk', 'Supervisor', 'Digitals', 'Other')",
            name='ck_valid_event_type'
        )
    )
    op.create_index('idx_event_type_overrides_ref', 'event_type_overrides', ['project_ref_num'], unique=True)


def downgrade():
    op.drop_index('idx_event_type_overrides_ref', table_name='event_type_overrides')
    op.drop_table('event_type_overrides')
