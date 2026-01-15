"""
Inventory Service

Business logic for supply tracking, order management, and inventory alerts.
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class InventoryService:
    """
    Service for managing inventory, supplies, and purchase orders.
    Provides alerting for low stock and order management.
    """

    def __init__(self, db, models: Dict):
        """
        Initialize with database and models.

        Args:
            db: SQLAlchemy database instance
            models: Dictionary of model classes
        """
        self.db = db
        self.SupplyCategory = models.get('SupplyCategory')
        self.Supply = models.get('Supply')
        self.SupplyAdjustment = models.get('SupplyAdjustment')
        self.PurchaseOrder = models.get('PurchaseOrder')
        self.OrderItem = models.get('OrderItem')
        self.InventoryReminder = models.get('InventoryReminder')

    # =====================
    # Category Management
    # =====================

    def get_categories(self) -> List[Dict]:
        """Get all supply categories."""
        if not self.SupplyCategory:
            return []

        categories = self.db.session.query(self.SupplyCategory).order_by(
            self.SupplyCategory.sort_order,
            self.SupplyCategory.name
        ).all()

        return [c.to_dict() for c in categories]

    def create_category(self, name: str, description: str = None, sort_order: int = 0) -> Dict:
        """Create a new category."""
        category = self.SupplyCategory(
            name=name,
            description=description,
            sort_order=sort_order
        )
        self.db.session.add(category)
        self.db.session.commit()
        return category.to_dict()

    def update_category(self, category_id: int, **kwargs) -> Optional[Dict]:
        """Update a category."""
        category = self.db.session.query(self.SupplyCategory).get(category_id)
        if not category:
            return None

        for key, value in kwargs.items():
            if hasattr(category, key):
                setattr(category, key, value)

        self.db.session.commit()
        return category.to_dict()

    def delete_category(self, category_id: int) -> bool:
        """Delete a category (only if no supplies are linked)."""
        category = self.db.session.query(self.SupplyCategory).get(category_id)
        if not category:
            return False

        if category.supplies.count() > 0:
            return False

        self.db.session.delete(category)
        self.db.session.commit()
        return True

    # =====================
    # Supply Management
    # =====================

    def get_supplies(self, active_only: bool = True, category_id: int = None) -> List[Dict]:
        """Get all supplies, optionally filtered."""
        if not self.Supply:
            return []

        query = self.db.session.query(self.Supply)

        if active_only:
            query = query.filter(self.Supply.is_active == True)

        if category_id:
            query = query.filter(self.Supply.category_id == category_id)

        supplies = query.order_by(self.Supply.name).all()
        return [s.to_dict() for s in supplies]

    def get_supply(self, supply_id: int) -> Optional[Dict]:
        """Get a single supply by ID."""
        supply = self.db.session.query(self.Supply).get(supply_id)
        return supply.to_dict() if supply else None

    def create_supply(self, name: str, **kwargs) -> Dict:
        """Create a new supply item."""
        supply = self.Supply(name=name, **kwargs)
        self.db.session.add(supply)
        self.db.session.commit()
        return supply.to_dict()

    def update_supply(self, supply_id: int, **kwargs) -> Optional[Dict]:
        """Update a supply item."""
        supply = self.db.session.query(self.Supply).get(supply_id)
        if not supply:
            return None

        for key, value in kwargs.items():
            if hasattr(supply, key) and key not in ('id', 'created_at'):
                setattr(supply, key, value)

        supply.updated_at = datetime.utcnow()
        self.db.session.commit()
        return supply.to_dict()

    def adjust_supply_quantity(self, supply_id: int, amount: int,
                                reason: str = None, user: str = None) -> Optional[Dict]:
        """Adjust supply quantity (positive to add, negative to subtract)."""
        supply = self.db.session.query(self.Supply).get(supply_id)
        if not supply:
            return None

        supply.adjust_quantity(amount, reason, user)
        self.db.session.commit()
        return supply.to_dict()

    def set_supply_quantity(self, supply_id: int, quantity: int,
                            reason: str = None, user: str = None) -> Optional[Dict]:
        """Set exact supply quantity (for inventory counts)."""
        supply = self.db.session.query(self.Supply).get(supply_id)
        if not supply:
            return None

        supply.set_quantity(quantity, reason, user)
        self.db.session.commit()
        return supply.to_dict()

    def get_supply_history(self, supply_id: int, limit: int = 50) -> List[Dict]:
        """Get adjustment history for a supply."""
        if not self.SupplyAdjustment:
            return []

        adjustments = self.db.session.query(self.SupplyAdjustment).filter(
            self.SupplyAdjustment.supply_id == supply_id
        ).order_by(
            self.SupplyAdjustment.created_at.desc()
        ).limit(limit).all()

        return [a.to_dict() for a in adjustments]

    def delete_supply(self, supply_id: int) -> bool:
        """Soft delete a supply (marks as inactive)."""
        supply = self.db.session.query(self.Supply).get(supply_id)
        if not supply:
            return False

        supply.is_active = False
        supply.updated_at = datetime.utcnow()
        self.db.session.commit()
        return True

    # =====================
    # Alerts & Notifications
    # =====================

    def get_low_stock_items(self) -> List[Dict]:
        """Get all items that are below reorder threshold."""
        if not self.Supply:
            return []

        supplies = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.reorder_threshold.isnot(None),
            self.Supply.current_quantity <= self.Supply.reorder_threshold
        ).order_by(
            # Critical first, then low
            (self.Supply.current_quantity <= self.Supply.reorder_threshold / 2).desc(),
            self.Supply.current_quantity.asc()
        ).all()

        return [s.to_dict() for s in supplies]

    def get_out_of_stock_items(self) -> List[Dict]:
        """Get all items that are completely out of stock."""
        if not self.Supply:
            return []

        supplies = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.current_quantity <= 0
        ).order_by(self.Supply.name).all()

        return [s.to_dict() for s in supplies]

    def get_inventory_summary(self) -> Dict[str, Any]:
        """Get overall inventory summary for dashboard."""
        if not self.Supply:
            return {
                'total_items': 0,
                'out_of_stock': 0,
                'low_stock': 0,
                'ok_stock': 0,
                'needs_reorder': []
            }

        total = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True
        ).count()

        out = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.current_quantity <= 0
        ).count()

        low = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.reorder_threshold.isnot(None),
            self.Supply.current_quantity > 0,
            self.Supply.current_quantity <= self.Supply.reorder_threshold
        ).count()

        needs_reorder = self.get_low_stock_items()[:5]  # Top 5 most critical

        return {
            'total_items': total,
            'out_of_stock': out,
            'low_stock': low,
            'ok_stock': total - out - low,
            'needs_reorder': needs_reorder
        }

    def get_pending_notifications(self) -> List[Dict]:
        """Get items needing attention (for browser notifications)."""
        notifications = []

        # Out of stock items
        out_of_stock = self.get_out_of_stock_items()
        for item in out_of_stock:
            notifications.append({
                'type': 'out_of_stock',
                'priority': 'urgent',
                'title': f"Out of Stock: {item['name']}",
                'message': f"{item['name']} is completely out of stock!",
                'supply_id': item['id']
            })

        # Low stock items
        low_stock = self.get_low_stock_items()
        for item in low_stock:
            if item['current_quantity'] > 0:  # Don't duplicate out of stock
                notifications.append({
                    'type': 'low_stock',
                    'priority': 'warning' if item['stock_status'] == 'low' else 'urgent',
                    'title': f"Low Stock: {item['name']}",
                    'message': f"{item['name']} has only {item['current_quantity']} {item['unit']} remaining",
                    'supply_id': item['id']
                })

        # Pending orders
        pending_orders = self.get_orders_by_status('ordered')
        for order in pending_orders:
            if order.get('expected_date'):
                expected = datetime.fromisoformat(order['expected_date']).date()
                if expected <= date.today():
                    notifications.append({
                        'type': 'order_expected',
                        'priority': 'info',
                        'title': f"Order {order['order_number']} Expected",
                        'message': f"Order was expected on {order['expected_date']}",
                        'order_id': order['id']
                    })

        return notifications

    # =====================
    # Order Management
    # =====================

    def get_orders(self, status: str = None, limit: int = 50) -> List[Dict]:
        """Get purchase orders, optionally filtered by status."""
        if not self.PurchaseOrder:
            return []

        query = self.db.session.query(self.PurchaseOrder)

        if status:
            query = query.filter(self.PurchaseOrder.status == status)

        orders = query.order_by(
            self.PurchaseOrder.created_at.desc()
        ).limit(limit).all()

        return [o.to_dict(include_items=True) for o in orders]

    def get_orders_by_status(self, status: str) -> List[Dict]:
        """Get orders by specific status."""
        return self.get_orders(status=status)

    def get_order(self, order_id: int) -> Optional[Dict]:
        """Get a single order with items."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        return order.to_dict(include_items=True) if order else None

    def create_order(self, vendor: str = None, notes: str = None,
                     expected_date: date = None, created_by: str = None) -> Dict:
        """Create a new draft purchase order."""
        order = self.PurchaseOrder(
            status='draft',
            vendor=vendor,
            notes=notes,
            expected_date=expected_date,
            created_by=created_by
        )
        self.db.session.add(order)
        self.db.session.commit()
        return order.to_dict(include_items=True)

    def add_order_item(self, order_id: int, supply_id: int,
                       quantity: int, notes: str = None) -> Optional[Dict]:
        """Add an item to a purchase order."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status not in ('draft', 'pending'):
            return None

        supply = self.db.session.query(self.Supply).get(supply_id)
        if not supply:
            return None

        # Check if item already exists
        existing = self.db.session.query(self.OrderItem).filter(
            self.OrderItem.order_id == order_id,
            self.OrderItem.supply_id == supply_id
        ).first()

        if existing:
            existing.quantity_ordered += quantity
            if notes:
                existing.notes = notes
        else:
            item = self.OrderItem(
                order_id=order_id,
                supply_id=supply_id,
                quantity_ordered=quantity,
                notes=notes
            )
            self.db.session.add(item)

        self.db.session.commit()
        return self.get_order(order_id)

    def remove_order_item(self, order_id: int, item_id: int) -> bool:
        """Remove an item from a purchase order."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status not in ('draft', 'pending'):
            return False

        item = self.db.session.query(self.OrderItem).filter(
            self.OrderItem.id == item_id,
            self.OrderItem.order_id == order_id
        ).first()

        if not item:
            return False

        self.db.session.delete(item)
        self.db.session.commit()
        return True

    def update_order_item_quantity(self, order_id: int, item_id: int, quantity: int) -> Optional[Dict]:
        """Update the quantity of an order item."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status not in ('draft', 'pending'):
            return None

        item = self.db.session.query(self.OrderItem).filter(
            self.OrderItem.id == item_id,
            self.OrderItem.order_id == order_id
        ).first()

        if not item:
            return None

        item.quantity_ordered = quantity
        self.db.session.commit()
        return self.get_order(order_id)

    def submit_order(self, order_id: int) -> Optional[Dict]:
        """Submit a draft order (mark as ordered)."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status != 'draft':
            return None

        if order.total_items == 0:
            return None

        order.mark_ordered()
        self.db.session.commit()
        return order.to_dict(include_items=True)

    def receive_order_item(self, order_id: int, item_id: int,
                           quantity: int = None, auto_adjust: bool = True) -> Optional[Dict]:
        """Mark an order item as received and optionally adjust inventory."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status in ('cancelled', 'draft'):
            return None

        item = self.db.session.query(self.OrderItem).filter(
            self.OrderItem.id == item_id,
            self.OrderItem.order_id == order_id
        ).first()

        if not item:
            return None

        item.mark_received(quantity, auto_adjust)
        self.db.session.commit()
        return order.to_dict(include_items=True)

    def receive_all_items(self, order_id: int, auto_adjust: bool = True) -> Optional[Dict]:
        """Mark all items in an order as received."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status in ('cancelled', 'draft'):
            return None

        for item in order.items.all():
            if not item.is_received:
                item.mark_received(auto_adjust_inventory=auto_adjust)

        self.db.session.commit()
        return order.to_dict(include_items=True)

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a purchase order."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status in ('received', 'cancelled'):
            return False

        order.status = 'cancelled'
        self.db.session.commit()
        return True

    def delete_order(self, order_id: int) -> bool:
        """Delete a draft order."""
        order = self.db.session.query(self.PurchaseOrder).get(order_id)
        if not order or order.status != 'draft':
            return False

        self.db.session.delete(order)
        self.db.session.commit()
        return True

    # =====================
    # Quick Order Creation
    # =====================

    def create_reorder_list(self, created_by: str = None) -> Optional[Dict]:
        """Create an order from all low-stock items that need reordering."""
        low_stock = self.get_low_stock_items()
        if not low_stock:
            return None

        order = self.create_order(
            notes="Auto-generated reorder list",
            created_by=created_by
        )

        for item in low_stock:
            if item['quantity_needed'] > 0:
                self.add_order_item(
                    order_id=order['id'],
                    supply_id=item['id'],
                    quantity=item['quantity_needed']
                )

        return self.get_order(order['id'])

    # =====================
    # Inventory Reminders
    # =====================

    def get_reminders(self, active_only: bool = True) -> List[Dict]:
        """Get inventory reminders."""
        if not self.InventoryReminder:
            return []

        query = self.db.session.query(self.InventoryReminder)

        if active_only:
            query = query.filter(self.InventoryReminder.is_active == True)

        reminders = query.order_by(self.InventoryReminder.title).all()
        return [r.to_dict() for r in reminders]

    def get_due_reminders(self) -> List[Dict]:
        """Get reminders that are due today or overdue."""
        if not self.InventoryReminder:
            return []

        today = date.today()
        reminders = self.db.session.query(self.InventoryReminder).filter(
            self.InventoryReminder.is_active == True,
            self.InventoryReminder.next_due <= today
        ).all()

        return [r.to_dict() for r in reminders]

    def create_reminder(self, title: str, frequency: str = 'weekly',
                        day_of_week: int = None, day_of_month: int = None,
                        time_of_day: str = None, description: str = None) -> Dict:
        """Create an inventory reminder."""
        from datetime import time as time_type

        time_obj = None
        if time_of_day:
            parts = time_of_day.split(':')
            time_obj = time_type(int(parts[0]), int(parts[1]))

        reminder = self.InventoryReminder(
            title=title,
            description=description,
            frequency=frequency,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            time_of_day=time_obj
        )

        # Calculate next due date
        reminder.next_due = self._calculate_next_due(reminder)

        self.db.session.add(reminder)
        self.db.session.commit()
        return reminder.to_dict()

    def _calculate_next_due(self, reminder) -> date:
        """Calculate the next due date for a reminder."""
        today = date.today()

        if reminder.frequency == 'daily':
            return today + timedelta(days=1)

        elif reminder.frequency == 'weekly':
            target_day = reminder.day_of_week or 4  # Default Friday
            days_ahead = target_day - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

        elif reminder.frequency == 'biweekly':
            target_day = reminder.day_of_week or 4
            days_ahead = target_day - today.weekday()
            if days_ahead <= 0:
                days_ahead += 14
            return today + timedelta(days=days_ahead)

        elif reminder.frequency == 'monthly':
            target_day = reminder.day_of_month or 1
            next_month = today.replace(day=1) + timedelta(days=32)
            next_month = next_month.replace(day=1)
            try:
                return next_month.replace(day=target_day)
            except ValueError:
                # Handle months with fewer days
                return next_month.replace(day=28)

        return today + timedelta(days=7)

    def mark_reminder_complete(self, reminder_id: int) -> Optional[Dict]:
        """Mark a reminder as triggered and calculate next due date."""
        reminder = self.db.session.query(self.InventoryReminder).get(reminder_id)
        if not reminder:
            return None

        reminder.last_triggered = datetime.utcnow()
        reminder.next_due = self._calculate_next_due(reminder)

        self.db.session.commit()
        return reminder.to_dict()

    def delete_reminder(self, reminder_id: int) -> bool:
        """Delete an inventory reminder."""
        reminder = self.db.session.query(self.InventoryReminder).get(reminder_id)
        if not reminder:
            return False

        self.db.session.delete(reminder)
        self.db.session.commit()
        return True
