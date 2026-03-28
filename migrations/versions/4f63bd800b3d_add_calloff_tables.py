"""add calloff tables

Revision ID: 4f63bd800b3d
Revises: 69e1fbb36579
Create Date: 2026-03-28 16:28:50.860520

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4f63bd800b3d'
down_revision = '69e1fbb36579'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('employee_calloffs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('calloff_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', sa.String(length=100), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('supervisor_comments', sa.Text(), nullable=True),
        sa.Column('attendance_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('notified_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['attendance_id'], ['employee_attendance.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'calloff_date', name='uq_calloff_employee_date'),
    )
    op.create_index('idx_calloff_status_created', 'employee_calloffs', ['status', 'created_at'])
    op.create_index('idx_calloff_employee_created', 'employee_calloffs', ['employee_id', 'created_at'])

    op.create_table('calloff_attachments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('calloff_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_type', sa.String(length=100), nullable=True),
        sa.Column('uploaded_by', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.ForeignKeyConstraint(['calloff_id'], ['employee_calloffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calloff_attachments_calloff_id', 'calloff_attachments', ['calloff_id'])


def downgrade():
    op.drop_table('calloff_attachments')
    op.drop_table('employee_calloffs')
