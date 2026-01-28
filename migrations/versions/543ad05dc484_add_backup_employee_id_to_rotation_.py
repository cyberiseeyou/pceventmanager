"""add backup_employee_id to rotation_assignments

Revision ID: 543ad05dc484
Revises: add_juicer_trained
Create Date: 2026-01-28 05:52:13.242330

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '543ad05dc484'
down_revision = 'add_juicer_trained'
branch_labels = None
depends_on = None


def upgrade():
    # Add backup_employee_id column to rotation_assignments table
    with op.batch_alter_table('rotation_assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('backup_employee_id', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_rotation_backup_employee', 'employees', ['backup_employee_id'], ['id'])


def downgrade():
    # Remove backup_employee_id column from rotation_assignments table
    with op.batch_alter_table('rotation_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_rotation_backup_employee', type_='foreignkey')
        batch_op.drop_column('backup_employee_id')
