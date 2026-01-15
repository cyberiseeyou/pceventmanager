"""
Inventory Routes

Flask routes for inventory management including supplies and purchase orders.
"""
from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime, date
import logging

from app.extensions import db
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


def get_inventory_service():
    """Get inventory service instance."""
    models = {
        'SupplyCategory': current_app.config.get('SupplyCategory'),
        'Supply': current_app.config.get('Supply'),
        'SupplyAdjustment': current_app.config.get('SupplyAdjustment'),
        'PurchaseOrder': current_app.config.get('PurchaseOrder'),
        'OrderItem': current_app.config.get('OrderItem'),
        'InventoryReminder': current_app.config.get('InventoryReminder')
    }
    return InventoryService(db, models)


# =====================
# Page Routes
# =====================

@inventory_bp.route('/')
def index():
    """Main inventory page."""
    service = get_inventory_service()

    categories = service.get_categories()
    supplies = service.get_supplies(active_only=True)
    summary = service.get_inventory_summary()
    low_stock = service.get_low_stock_items()

    return render_template('inventory/index.html',
                           categories=categories,
                           supplies=supplies,
                           summary=summary,
                           low_stock=low_stock)


@inventory_bp.route('/orders')
def orders():
    """Purchase orders page."""
    service = get_inventory_service()

    status_filter = request.args.get('status', None)
    orders = service.get_orders(status=status_filter)

    # Group by status
    orders_by_status = {
        'draft': [],
        'pending': [],
        'ordered': [],
        'partial': [],
        'received': [],
        'cancelled': []
    }

    for order in orders:
        if order['status'] in orders_by_status:
            orders_by_status[order['status']].append(order)

    return render_template('inventory/orders.html',
                           orders=orders,
                           orders_by_status=orders_by_status,
                           status_filter=status_filter)


@inventory_bp.route('/order/<int:order_id>')
def order_detail(order_id):
    """Single order detail page."""
    service = get_inventory_service()
    order = service.get_order(order_id)

    if not order:
        return render_template('errors/404.html'), 404

    supplies = service.get_supplies(active_only=True)

    return render_template('inventory/order_detail.html',
                           order=order,
                           supplies=supplies)


# =====================
# API - Categories
# =====================

@inventory_bp.route('/api/categories', methods=['GET'])
def api_get_categories():
    """Get all categories."""
    service = get_inventory_service()
    categories = service.get_categories()
    return jsonify({'success': True, 'categories': categories})


@inventory_bp.route('/api/categories', methods=['POST'])
def api_create_category():
    """Create a new category."""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    service = get_inventory_service()
    try:
        category = service.create_category(
            name=data['name'],
            description=data.get('description'),
            sort_order=data.get('sort_order', 0)
        )
        return jsonify({'success': True, 'category': category})
    except Exception as e:
        logger.error(f"Error creating category: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/categories/<int:category_id>', methods=['PUT'])
def api_update_category(category_id):
    """Update a category."""
    data = request.get_json()
    service = get_inventory_service()

    category = service.update_category(category_id, **data)
    if not category:
        return jsonify({'success': False, 'error': 'Category not found'}), 404

    return jsonify({'success': True, 'category': category})


@inventory_bp.route('/api/categories/<int:category_id>', methods=['DELETE'])
def api_delete_category(category_id):
    """Delete a category."""
    service = get_inventory_service()

    if service.delete_category(category_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Cannot delete category with supplies'}), 400


# =====================
# API - Supplies
# =====================

@inventory_bp.route('/api/supplies', methods=['GET'])
def api_get_supplies():
    """Get all supplies."""
    service = get_inventory_service()

    active_only = request.args.get('active', 'true').lower() == 'true'
    category_id = request.args.get('category_id', type=int)

    supplies = service.get_supplies(active_only=active_only, category_id=category_id)
    return jsonify({'success': True, 'supplies': supplies})


@inventory_bp.route('/api/supplies/<int:supply_id>', methods=['GET'])
def api_get_supply(supply_id):
    """Get a single supply."""
    service = get_inventory_service()
    supply = service.get_supply(supply_id)

    if not supply:
        return jsonify({'success': False, 'error': 'Supply not found'}), 404

    return jsonify({'success': True, 'supply': supply})


@inventory_bp.route('/api/supplies', methods=['POST'])
def api_create_supply():
    """Create a new supply."""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    service = get_inventory_service()
    try:
        supply = service.create_supply(**data)
        return jsonify({'success': True, 'supply': supply})
    except Exception as e:
        logger.error(f"Error creating supply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/supplies/<int:supply_id>', methods=['PUT'])
def api_update_supply(supply_id):
    """Update a supply."""
    data = request.get_json()
    service = get_inventory_service()

    supply = service.update_supply(supply_id, **data)
    if not supply:
        return jsonify({'success': False, 'error': 'Supply not found'}), 404

    return jsonify({'success': True, 'supply': supply})


@inventory_bp.route('/api/supplies/<int:supply_id>', methods=['DELETE'])
def api_delete_supply(supply_id):
    """Soft delete a supply."""
    service = get_inventory_service()

    if service.delete_supply(supply_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Supply not found'}), 404


@inventory_bp.route('/api/supplies/<int:supply_id>/adjust', methods=['POST'])
def api_adjust_supply(supply_id):
    """Adjust supply quantity."""
    data = request.get_json()
    if not data or 'amount' not in data:
        return jsonify({'success': False, 'error': 'Amount is required'}), 400

    service = get_inventory_service()
    supply = service.adjust_supply_quantity(
        supply_id,
        amount=data['amount'],
        reason=data.get('reason'),
        user=data.get('user')
    )

    if not supply:
        return jsonify({'success': False, 'error': 'Supply not found'}), 404

    return jsonify({'success': True, 'supply': supply})


@inventory_bp.route('/api/supplies/<int:supply_id>/set-quantity', methods=['POST'])
def api_set_supply_quantity(supply_id):
    """Set exact supply quantity (for inventory counts)."""
    data = request.get_json()
    if not data or 'quantity' not in data:
        return jsonify({'success': False, 'error': 'Quantity is required'}), 400

    service = get_inventory_service()
    supply = service.set_supply_quantity(
        supply_id,
        quantity=data['quantity'],
        reason=data.get('reason', 'Inventory count'),
        user=data.get('user')
    )

    if not supply:
        return jsonify({'success': False, 'error': 'Supply not found'}), 404

    return jsonify({'success': True, 'supply': supply})


@inventory_bp.route('/api/supplies/<int:supply_id>/history', methods=['GET'])
def api_get_supply_history(supply_id):
    """Get adjustment history for a supply."""
    service = get_inventory_service()
    limit = request.args.get('limit', 50, type=int)

    history = service.get_supply_history(supply_id, limit=limit)
    return jsonify({'success': True, 'history': history})


# =====================
# API - Alerts & Summary
# =====================

@inventory_bp.route('/api/summary', methods=['GET'])
def api_get_summary():
    """Get inventory summary."""
    service = get_inventory_service()
    summary = service.get_inventory_summary()
    return jsonify({'success': True, 'summary': summary})


@inventory_bp.route('/api/low-stock', methods=['GET'])
def api_get_low_stock():
    """Get low stock items."""
    service = get_inventory_service()
    items = service.get_low_stock_items()
    return jsonify({'success': True, 'items': items})


@inventory_bp.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    """Get pending notifications."""
    service = get_inventory_service()
    notifications = service.get_pending_notifications()
    return jsonify({'success': True, 'notifications': notifications})


# =====================
# API - Orders
# =====================

@inventory_bp.route('/api/orders', methods=['GET'])
def api_get_orders():
    """Get all orders."""
    service = get_inventory_service()

    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)

    orders = service.get_orders(status=status, limit=limit)
    return jsonify({'success': True, 'orders': orders})


@inventory_bp.route('/api/orders/<int:order_id>', methods=['GET'])
def api_get_order(order_id):
    """Get a single order."""
    service = get_inventory_service()
    order = service.get_order(order_id)

    if not order:
        return jsonify({'success': False, 'error': 'Order not found'}), 404

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders', methods=['POST'])
def api_create_order():
    """Create a new order."""
    data = request.get_json() or {}

    service = get_inventory_service()

    expected_date = None
    if data.get('expected_date'):
        expected_date = datetime.fromisoformat(data['expected_date']).date()

    order = service.create_order(
        vendor=data.get('vendor'),
        notes=data.get('notes'),
        expected_date=expected_date,
        created_by=data.get('created_by')
    )

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders/<int:order_id>/items', methods=['POST'])
def api_add_order_item(order_id):
    """Add an item to an order."""
    data = request.get_json()
    if not data or not data.get('supply_id') or not data.get('quantity'):
        return jsonify({'success': False, 'error': 'supply_id and quantity are required'}), 400

    service = get_inventory_service()
    order = service.add_order_item(
        order_id,
        supply_id=data['supply_id'],
        quantity=data['quantity'],
        notes=data.get('notes')
    )

    if not order:
        return jsonify({'success': False, 'error': 'Order not found or not editable'}), 404

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders/<int:order_id>/items/<int:item_id>', methods=['DELETE'])
def api_remove_order_item(order_id, item_id):
    """Remove an item from an order."""
    service = get_inventory_service()

    if service.remove_order_item(order_id, item_id):
        order = service.get_order(order_id)
        return jsonify({'success': True, 'order': order})

    return jsonify({'success': False, 'error': 'Item not found or order not editable'}), 404


@inventory_bp.route('/api/orders/<int:order_id>/items/<int:item_id>/quantity', methods=['PUT'])
def api_update_item_quantity(order_id, item_id):
    """Update order item quantity."""
    data = request.get_json()
    if not data or 'quantity' not in data:
        return jsonify({'success': False, 'error': 'Quantity is required'}), 400

    service = get_inventory_service()
    order = service.update_order_item_quantity(order_id, item_id, data['quantity'])

    if not order:
        return jsonify({'success': False, 'error': 'Item not found or order not editable'}), 404

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders/<int:order_id>/submit', methods=['POST'])
def api_submit_order(order_id):
    """Submit a draft order."""
    service = get_inventory_service()
    order = service.submit_order(order_id)

    if not order:
        return jsonify({'success': False, 'error': 'Order not found, empty, or already submitted'}), 400

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders/<int:order_id>/receive-item/<int:item_id>', methods=['POST'])
def api_receive_item(order_id, item_id):
    """Receive a single order item."""
    data = request.get_json() or {}

    service = get_inventory_service()
    order = service.receive_order_item(
        order_id,
        item_id,
        quantity=data.get('quantity'),
        auto_adjust=data.get('auto_adjust', True)
    )

    if not order:
        return jsonify({'success': False, 'error': 'Item not found or order not receivable'}), 404

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders/<int:order_id>/receive-all', methods=['POST'])
def api_receive_all(order_id):
    """Receive all items in an order."""
    data = request.get_json() or {}

    service = get_inventory_service()
    order = service.receive_all_items(
        order_id,
        auto_adjust=data.get('auto_adjust', True)
    )

    if not order:
        return jsonify({'success': False, 'error': 'Order not found or not receivable'}), 404

    return jsonify({'success': True, 'order': order})


@inventory_bp.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
def api_cancel_order(order_id):
    """Cancel an order."""
    service = get_inventory_service()

    if service.cancel_order(order_id):
        return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Order not found or already completed'}), 400


@inventory_bp.route('/api/orders/<int:order_id>', methods=['DELETE'])
def api_delete_order(order_id):
    """Delete a draft order."""
    service = get_inventory_service()

    if service.delete_order(order_id):
        return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Only draft orders can be deleted'}), 400


@inventory_bp.route('/api/orders/create-reorder', methods=['POST'])
def api_create_reorder():
    """Create order from low-stock items."""
    data = request.get_json() or {}

    service = get_inventory_service()
    order = service.create_reorder_list(created_by=data.get('created_by'))

    if not order:
        return jsonify({'success': False, 'error': 'No items need reordering'}), 400

    return jsonify({'success': True, 'order': order})


# =====================
# API - Reminders
# =====================

@inventory_bp.route('/api/reminders', methods=['GET'])
def api_get_reminders():
    """Get inventory reminders."""
    service = get_inventory_service()
    active_only = request.args.get('active', 'true').lower() == 'true'

    reminders = service.get_reminders(active_only=active_only)
    return jsonify({'success': True, 'reminders': reminders})


@inventory_bp.route('/api/reminders/due', methods=['GET'])
def api_get_due_reminders():
    """Get reminders due today or overdue."""
    service = get_inventory_service()
    reminders = service.get_due_reminders()
    return jsonify({'success': True, 'reminders': reminders})


@inventory_bp.route('/api/reminders', methods=['POST'])
def api_create_reminder():
    """Create an inventory reminder."""
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'success': False, 'error': 'Title is required'}), 400

    service = get_inventory_service()
    try:
        reminder = service.create_reminder(
            title=data['title'],
            frequency=data.get('frequency', 'weekly'),
            day_of_week=data.get('day_of_week'),
            day_of_month=data.get('day_of_month'),
            time_of_day=data.get('time_of_day'),
            description=data.get('description')
        )
        return jsonify({'success': True, 'reminder': reminder})
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/reminders/<int:reminder_id>/complete', methods=['POST'])
def api_complete_reminder(reminder_id):
    """Mark a reminder as complete."""
    service = get_inventory_service()
    reminder = service.mark_reminder_complete(reminder_id)

    if not reminder:
        return jsonify({'success': False, 'error': 'Reminder not found'}), 404

    return jsonify({'success': True, 'reminder': reminder})


@inventory_bp.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
def api_delete_reminder(reminder_id):
    """Delete a reminder."""
    service = get_inventory_service()

    if service.delete_reminder(reminder_id):
        return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Reminder not found'}), 404
