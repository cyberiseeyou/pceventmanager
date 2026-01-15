"""
Inventory Models

Models for tracking demo supplies and managing purchase orders.
"""
from datetime import datetime, date
from typing import Dict, Any, List, Optional


def create_inventory_models(db):
    """Factory function to create inventory models with database instance."""

    class SupplyCategory(db.Model):
        """Categories for organizing supply items."""
        __tablename__ = 'supply_categories'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        name = db.Column(db.String(100), nullable=False, unique=True)
        description = db.Column(db.String(255), nullable=True)
        sort_order = db.Column(db.Integer, nullable=False, default=0)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        # Relationship
        supplies = db.relationship('Supply', backref='category', lazy='dynamic')

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'name': self.name,
                'description': self.description,
                'sort_order': self.sort_order,
                'supply_count': self.supplies.count()
            }

    class Supply(db.Model):
        """Individual supply items with quantity tracking."""
        __tablename__ = 'supplies'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        name = db.Column(db.String(200), nullable=False)
        description = db.Column(db.Text, nullable=True)
        category_id = db.Column(db.Integer, db.ForeignKey('supply_categories.id'), nullable=True)

        # Quantity tracking
        current_quantity = db.Column(db.Integer, nullable=False, default=0)
        unit = db.Column(db.String(50), nullable=False, default='each')  # each, pack, case, box
        par_level = db.Column(db.Integer, nullable=True)  # Ideal quantity to maintain
        reorder_threshold = db.Column(db.Integer, nullable=True)  # Alert when below this

        # Status
        is_active = db.Column(db.Boolean, nullable=False, default=True)
        last_counted_at = db.Column(db.DateTime, nullable=True)
        last_adjusted_at = db.Column(db.DateTime, nullable=True)

        # Metadata
        notes = db.Column(db.Text, nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

        # Relationships
        adjustments = db.relationship('SupplyAdjustment', backref='supply', lazy='dynamic', order_by='desc(SupplyAdjustment.created_at)')
        order_items = db.relationship('OrderItem', backref='supply', lazy='dynamic')

        @property
        def is_low_stock(self) -> bool:
            """Check if supply is below reorder threshold."""
            if self.reorder_threshold is None:
                return False
            return self.current_quantity <= self.reorder_threshold

        @property
        def stock_status(self) -> str:
            """Get stock status: ok, low, critical, out."""
            if self.current_quantity <= 0:
                return 'out'
            if self.reorder_threshold is not None:
                if self.current_quantity <= self.reorder_threshold // 2:
                    return 'critical'
                if self.current_quantity <= self.reorder_threshold:
                    return 'low'
            return 'ok'

        @property
        def quantity_needed(self) -> int:
            """Calculate how many to order to reach par level."""
            if self.par_level is None:
                return 0
            return max(0, self.par_level - self.current_quantity)

        def adjust_quantity(self, amount: int, reason: str = None, user: str = None) -> 'SupplyAdjustment':
            """Adjust quantity and create adjustment record."""
            old_quantity = self.current_quantity
            self.current_quantity += amount
            self.last_adjusted_at = datetime.utcnow()

            adjustment = SupplyAdjustment(
                supply_id=self.id,
                adjustment_type='add' if amount > 0 else 'subtract',
                quantity_change=abs(amount),
                quantity_before=old_quantity,
                quantity_after=self.current_quantity,
                reason=reason,
                adjusted_by=user
            )
            db.session.add(adjustment)
            return adjustment

        def set_quantity(self, new_quantity: int, reason: str = None, user: str = None) -> 'SupplyAdjustment':
            """Set exact quantity (for inventory counts)."""
            old_quantity = self.current_quantity
            self.current_quantity = new_quantity
            self.last_counted_at = datetime.utcnow()
            self.last_adjusted_at = datetime.utcnow()

            adjustment = SupplyAdjustment(
                supply_id=self.id,
                adjustment_type='count',
                quantity_change=abs(new_quantity - old_quantity),
                quantity_before=old_quantity,
                quantity_after=new_quantity,
                reason=reason or 'Inventory count',
                adjusted_by=user
            )
            db.session.add(adjustment)
            return adjustment

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'name': self.name,
                'description': self.description,
                'category_id': self.category_id,
                'category_name': self.category.name if self.category else None,
                'current_quantity': self.current_quantity,
                'unit': self.unit,
                'par_level': self.par_level,
                'reorder_threshold': self.reorder_threshold,
                'is_active': self.is_active,
                'is_low_stock': self.is_low_stock,
                'stock_status': self.stock_status,
                'quantity_needed': self.quantity_needed,
                'last_counted_at': self.last_counted_at.isoformat() if self.last_counted_at else None,
                'last_adjusted_at': self.last_adjusted_at.isoformat() if self.last_adjusted_at else None,
                'notes': self.notes,
                'created_at': self.created_at.isoformat(),
                'updated_at': self.updated_at.isoformat()
            }

    class SupplyAdjustment(db.Model):
        """Log of all quantity changes to supplies."""
        __tablename__ = 'supply_adjustments'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
        adjustment_type = db.Column(db.String(20), nullable=False)  # add, subtract, count
        quantity_change = db.Column(db.Integer, nullable=False)
        quantity_before = db.Column(db.Integer, nullable=False)
        quantity_after = db.Column(db.Integer, nullable=False)
        reason = db.Column(db.String(255), nullable=True)
        adjusted_by = db.Column(db.String(100), nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'supply_id': self.supply_id,
                'supply_name': self.supply.name if self.supply else None,
                'adjustment_type': self.adjustment_type,
                'quantity_change': self.quantity_change,
                'quantity_before': self.quantity_before,
                'quantity_after': self.quantity_after,
                'reason': self.reason,
                'adjusted_by': self.adjusted_by,
                'created_at': self.created_at.isoformat()
            }

    class PurchaseOrder(db.Model):
        """Purchase orders for supplies."""
        __tablename__ = 'purchase_orders'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        order_number = db.Column(db.String(50), nullable=True, unique=True)

        # Status: draft, pending, ordered, partial, received, cancelled
        status = db.Column(db.String(20), nullable=False, default='draft')

        # Dates
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        ordered_at = db.Column(db.DateTime, nullable=True)
        expected_date = db.Column(db.Date, nullable=True)
        received_at = db.Column(db.DateTime, nullable=True)

        # Details
        vendor = db.Column(db.String(200), nullable=True)
        notes = db.Column(db.Text, nullable=True)
        created_by = db.Column(db.String(100), nullable=True)

        # Relationships
        items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')

        @property
        def total_items(self) -> int:
            return self.items.count()

        @property
        def received_items(self) -> int:
            return self.items.filter(OrderItem.is_received == True).count()

        @property
        def all_received(self) -> bool:
            return self.total_items > 0 and self.received_items == self.total_items

        def generate_order_number(self):
            """Generate unique order number."""
            today = date.today()
            prefix = f"PO-{today.strftime('%Y%m%d')}"

            # Find highest order number for today
            existing = db.session.query(PurchaseOrder).filter(
                PurchaseOrder.order_number.like(f"{prefix}-%")
            ).order_by(PurchaseOrder.order_number.desc()).first()

            if existing and existing.order_number:
                try:
                    last_num = int(existing.order_number.split('-')[-1])
                    self.order_number = f"{prefix}-{last_num + 1:03d}"
                except (ValueError, IndexError):
                    self.order_number = f"{prefix}-001"
            else:
                self.order_number = f"{prefix}-001"

        def mark_ordered(self):
            """Mark order as submitted."""
            self.status = 'ordered'
            self.ordered_at = datetime.utcnow()
            if not self.order_number:
                self.generate_order_number()

        def update_status(self):
            """Update status based on received items."""
            if self.status in ('cancelled', 'draft'):
                return

            if self.total_items == 0:
                return

            if self.all_received:
                self.status = 'received'
                if not self.received_at:
                    self.received_at = datetime.utcnow()
            elif self.received_items > 0:
                self.status = 'partial'
            elif self.ordered_at:
                self.status = 'ordered'

        def to_dict(self, include_items: bool = False) -> Dict[str, Any]:
            result = {
                'id': self.id,
                'order_number': self.order_number,
                'status': self.status,
                'created_at': self.created_at.isoformat(),
                'ordered_at': self.ordered_at.isoformat() if self.ordered_at else None,
                'expected_date': self.expected_date.isoformat() if self.expected_date else None,
                'received_at': self.received_at.isoformat() if self.received_at else None,
                'vendor': self.vendor,
                'notes': self.notes,
                'created_by': self.created_by,
                'total_items': self.total_items,
                'received_items': self.received_items,
                'all_received': self.all_received
            }

            if include_items:
                result['items'] = [item.to_dict() for item in self.items.all()]

            return result

    class OrderItem(db.Model):
        """Individual items on a purchase order."""
        __tablename__ = 'order_items'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
        supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)

        quantity_ordered = db.Column(db.Integer, nullable=False)
        quantity_received = db.Column(db.Integer, nullable=False, default=0)
        is_received = db.Column(db.Boolean, nullable=False, default=False)
        received_at = db.Column(db.DateTime, nullable=True)

        notes = db.Column(db.String(255), nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        def mark_received(self, quantity: int = None, auto_adjust_inventory: bool = True):
            """Mark item as received and optionally adjust inventory."""
            if quantity is None:
                quantity = self.quantity_ordered

            self.quantity_received = quantity
            self.is_received = True
            self.received_at = datetime.utcnow()

            if auto_adjust_inventory and self.supply:
                self.supply.adjust_quantity(
                    quantity,
                    reason=f"Received from order {self.order.order_number}",
                    user='system'
                )

            # Update parent order status
            self.order.update_status()

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'order_id': self.order_id,
                'supply_id': self.supply_id,
                'supply_name': self.supply.name if self.supply else None,
                'supply_unit': self.supply.unit if self.supply else None,
                'quantity_ordered': self.quantity_ordered,
                'quantity_received': self.quantity_received,
                'is_received': self.is_received,
                'received_at': self.received_at.isoformat() if self.received_at else None,
                'notes': self.notes
            }

    class InventoryReminder(db.Model):
        """Scheduled reminders for inventory counts."""
        __tablename__ = 'inventory_reminders'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        title = db.Column(db.String(200), nullable=False)
        description = db.Column(db.Text, nullable=True)

        # Schedule: daily, weekly, biweekly, monthly
        frequency = db.Column(db.String(20), nullable=False, default='weekly')
        day_of_week = db.Column(db.Integer, nullable=True)  # 0=Monday, 6=Sunday (for weekly)
        day_of_month = db.Column(db.Integer, nullable=True)  # 1-31 (for monthly)
        time_of_day = db.Column(db.Time, nullable=True)

        is_active = db.Column(db.Boolean, nullable=False, default=True)
        last_triggered = db.Column(db.DateTime, nullable=True)
        next_due = db.Column(db.Date, nullable=True)

        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'title': self.title,
                'description': self.description,
                'frequency': self.frequency,
                'day_of_week': self.day_of_week,
                'day_of_month': self.day_of_month,
                'time_of_day': self.time_of_day.isoformat() if self.time_of_day else None,
                'is_active': self.is_active,
                'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
                'next_due': self.next_due.isoformat() if self.next_due else None
            }

    return {
        'SupplyCategory': SupplyCategory,
        'Supply': Supply,
        'SupplyAdjustment': SupplyAdjustment,
        'PurchaseOrder': PurchaseOrder,
        'OrderItem': OrderItem,
        'InventoryReminder': InventoryReminder
    }
