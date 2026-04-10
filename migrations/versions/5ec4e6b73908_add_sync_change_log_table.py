"""add sync_change_log table

Revision ID: 5ec4e6b73908
Revises: 4f63bd800b3d
Create Date: 2026-04-06 23:01:56.206581

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5ec4e6b73908'
down_revision = '4f63bd800b3d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sync_change_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('change_type', sa.String(length=20), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False, server_default='event'),
        sa.Column('entity_id', sa.String(length=100), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('field_changes', sa.Text(), nullable=True),
        sa.Column('is_conflict', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('push_sent', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('push_sent_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sync_change_log', schema=None) as batch_op:
        batch_op.create_index('idx_sync_changelog_type_status', ['change_type', 'resolved'], unique=False)
        batch_op.create_index('idx_sync_changelog_detected', ['detected_at'], unique=False)
        batch_op.create_index('idx_sync_changelog_conflicts', ['is_conflict', 'resolved'], unique=False)
        batch_op.create_index('idx_sync_changelog_push_pending', ['push_sent', 'detected_at'], unique=False)


def downgrade():
    with op.batch_alter_table('sync_change_log', schema=None) as batch_op:
        batch_op.drop_index('idx_sync_changelog_push_pending')
        batch_op.drop_index('idx_sync_changelog_conflicts')
        batch_op.drop_index('idx_sync_changelog_detected')
        batch_op.drop_index('idx_sync_changelog_type_status')
    op.drop_table('sync_change_log')
