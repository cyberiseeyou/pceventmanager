"""Add inventory tables for supplies and orders

Revision ID: c7f8b2d34567
Revises: b5e7a9c12345
Create Date: 2026-01-05 00:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7f8b2d34567'
down_revision = 'b5e7a9c12345'
branch_labels = None
depends_on = None


def upgrade():
    # Create supply_categories table
    op.create_table('supply_categories',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create supplies table
    op.create_table('supplies',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('current_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(length=50), nullable=False, server_default='each'),
        sa.Column('par_level', sa.Integer(), nullable=True),
        sa.Column('reorder_threshold', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_counted_at', sa.DateTime(), nullable=True),
        sa.Column('last_adjusted_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['category_id'], ['supply_categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for supplies
    op.create_index('idx_supplies_category', 'supplies', ['category_id'], unique=False)
    op.create_index('idx_supplies_active', 'supplies', ['is_active'], unique=False)
    op.create_index('idx_supplies_low_stock', 'supplies', ['current_quantity', 'reorder_threshold'], unique=False)

    # Create supply_adjustments table
    op.create_table('supply_adjustments',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('supply_id', sa.Integer(), nullable=False),
        sa.Column('adjustment_type', sa.String(length=20), nullable=False),
        sa.Column('quantity_change', sa.Integer(), nullable=False),
        sa.Column('quantity_before', sa.Integer(), nullable=False),
        sa.Column('quantity_after', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('adjusted_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['supply_id'], ['supplies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index for adjustment history
    op.create_index('idx_adjustments_supply', 'supply_adjustments', ['supply_id'], unique=False)
    op.create_index('idx_adjustments_date', 'supply_adjustments', ['created_at'], unique=False)

    # Create purchase_orders table
    op.create_table('purchase_orders',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('order_number', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('ordered_at', sa.DateTime(), nullable=True),
        sa.Column('expected_date', sa.Date(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('vendor', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_number')
    )

    # Create indexes for purchase orders
    op.create_index('idx_orders_status', 'purchase_orders', ['status'], unique=False)
    op.create_index('idx_orders_date', 'purchase_orders', ['created_at'], unique=False)

    # Create order_items table
    op.create_table('order_items',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('supply_id', sa.Integer(), nullable=False),
        sa.Column('quantity_ordered', sa.Integer(), nullable=False),
        sa.Column('quantity_received', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_received', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supply_id'], ['supplies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for order items
    op.create_index('idx_order_items_order', 'order_items', ['order_id'], unique=False)
    op.create_index('idx_order_items_supply', 'order_items', ['supply_id'], unique=False)

    # Create inventory_reminders table
    op.create_table('inventory_reminders',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('frequency', sa.String(length=20), nullable=False, server_default='weekly'),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('time_of_day', sa.Time(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_triggered', sa.DateTime(), nullable=True),
        sa.Column('next_due', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop inventory_reminders table
    op.drop_table('inventory_reminders')

    # Drop order_items table
    op.drop_index('idx_order_items_supply', table_name='order_items')
    op.drop_index('idx_order_items_order', table_name='order_items')
    op.drop_table('order_items')

    # Drop purchase_orders table
    op.drop_index('idx_orders_date', table_name='purchase_orders')
    op.drop_index('idx_orders_status', table_name='purchase_orders')
    op.drop_table('purchase_orders')

    # Drop supply_adjustments table
    op.drop_index('idx_adjustments_date', table_name='supply_adjustments')
    op.drop_index('idx_adjustments_supply', table_name='supply_adjustments')
    op.drop_table('supply_adjustments')

    # Drop supplies table
    op.drop_index('idx_supplies_low_stock', table_name='supplies')
    op.drop_index('idx_supplies_active', table_name='supplies')
    op.drop_index('idx_supplies_category', table_name='supplies')
    op.drop_table('supplies')

    # Drop supply_categories table
    op.drop_table('supply_categories')
