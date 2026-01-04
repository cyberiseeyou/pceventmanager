"""Add ignored_validation_issues table

Revision ID: 417d3f098412
Revises: 0da24612264a
Create Date: 2026-01-02 12:24:01.210099

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '417d3f098412'
down_revision = '0da24612264a'
branch_labels = None
depends_on = None


def upgrade():
    # Create ignored_validation_issues table
    op.create_table('ignored_validation_issues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_name', sa.String(length=100), nullable=False),
        sa.Column('issue_hash', sa.String(length=255), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=True),
        sa.Column('schedule_id', sa.Integer(), nullable=True),
        sa.Column('employee_id', sa.String(length=50), nullable=True),
        sa.Column('event_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('ignored_by', sa.String(length=100), nullable=True),
        sa.Column('ignored_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ignored_validation_issues_issue_hash', 'ignored_validation_issues', ['issue_hash'], unique=False)
    op.create_index('ix_ignored_validation_issues_rule_name', 'ignored_validation_issues', ['rule_name'], unique=False)


def downgrade():
    op.drop_index('ix_ignored_validation_issues_rule_name', table_name='ignored_validation_issues')
    op.drop_index('ix_ignored_validation_issues_issue_hash', table_name='ignored_validation_issues')
    op.drop_table('ignored_validation_issues')
