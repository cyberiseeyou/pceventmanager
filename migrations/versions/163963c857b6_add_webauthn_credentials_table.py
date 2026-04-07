"""add webauthn_credentials table

Revision ID: 163963c857b6
Revises: 5ec4e6b73908
Create Date: 2026-04-07 00:15:13.188442

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '163963c857b6'
down_revision = '5ec4e6b73908'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('webauthn_credentials',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('credential_id', sa.LargeBinary(), nullable=False),
        sa.Column('public_key', sa.LargeBinary(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('device_name', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('credential_id'),
    )
    with op.batch_alter_table('webauthn_credentials', schema=None) as batch_op:
        batch_op.create_index('idx_webauthn_employee', ['employee_id', 'is_active'], unique=False)


def downgrade():
    with op.batch_alter_table('webauthn_credentials', schema=None) as batch_op:
        batch_op.drop_index('idx_webauthn_employee')
    op.drop_table('webauthn_credentials')
