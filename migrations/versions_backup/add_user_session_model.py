"""Add UserSession model for database-backed sessions

Revision ID: add_user_session_model
Revises:
Create Date: 2025-10-29

Replaces in-memory session_store with persistent database sessions.
Provides thread-safe, scalable session management that works across
multiple workers and survives server restarts.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_session_model'
down_revision = 'add_performance_indexes'  # Points to Oct 25 migration
branch_labels = None
depends_on = None


def upgrade():
    """Create user_sessions table"""
    op.create_table(
        'user_sessions',
        sa.Column('session_id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('session_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_activity', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('phpsessid', sa.String(100), nullable=True),
        sa.Column('crossmark_authenticated', sa.Boolean(), default=False),
    )

    # Create indexes for efficient querying
    op.create_index('idx_sessions_cleanup', 'user_sessions', ['expires_at'])
    op.create_index('idx_sessions_user_activity', 'user_sessions', ['user_id', 'last_activity'])
    op.create_index('idx_user_sessions_user_id', 'user_sessions', ['user_id'])


def downgrade():
    """Drop user_sessions table"""
    op.drop_index('idx_sessions_user_activity', 'user_sessions')
    op.drop_index('idx_sessions_cleanup', 'user_sessions')
    op.drop_index('idx_user_sessions_user_id', 'user_sessions')
    op.drop_table('user_sessions')
