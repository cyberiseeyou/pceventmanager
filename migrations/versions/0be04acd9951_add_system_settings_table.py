"""add_system_settings_table

Revision ID: 0be04acd9951
Revises: 62eca6d029af
Create Date: 2025-10-02 02:41:35.800282

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0be04acd9951'
down_revision = '62eca6d029af'
branch_labels = None
depends_on = None


def upgrade():
    # Use inspection to check if table already exists (handles fresh PostgreSQL databases
    # where SQLAlchemy's create_all() may have already created the table)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'system_settings' not in existing_tables:
        # Create system_settings table
        op.create_table(
            'system_settings',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('setting_key', sa.String(length=100), nullable=False),
            sa.Column('setting_value', sa.Text(), nullable=True),
            sa.Column('setting_type', sa.String(length=50), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('updated_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('setting_key')
        )

    # Insert default settings (use ON CONFLICT to handle existing rows)
    op.execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_type, description, updated_by)
        VALUES
        ('edr_username', '', 'string', 'Walmart Retail-Link EDR Username', 'system'),
        ('edr_password', '', 'encrypted', 'Walmart Retail-Link EDR Password', 'system'),
        ('edr_mfa_credential_id', '', 'string', 'Walmart Retail-Link MFA Credential ID', 'system'),
        ('auto_scheduler_enabled', 'true', 'boolean', 'Enable automatic scheduler runs', 'system'),
        ('auto_scheduler_require_approval', 'true', 'boolean', 'Require user approval before scheduling changes', 'system')
        ON CONFLICT (setting_key) DO NOTHING
    """)


def downgrade():
    op.drop_table('system_settings')
