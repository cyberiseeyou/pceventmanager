"""
PushSubscription model - stores Web Push API subscriptions per employee/device
"""
from datetime import datetime


def create_push_subscription_model(db):
    """Factory function to create PushSubscription model with db instance"""

    class PushSubscription(db.Model):
        """
        Stores Web Push API subscriptions for delivering device-level notifications.
        One employee can have multiple subscriptions (phone, tablet, desktop).
        """
        __tablename__ = 'push_subscriptions'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)

        # Web Push subscription data
        endpoint = db.Column(db.Text, nullable=False)
        p256dh_key = db.Column(db.Text, nullable=False)
        auth_key = db.Column(db.Text, nullable=False)

        # Metadata
        user_agent = db.Column(db.String(500), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        last_used_at = db.Column(db.DateTime, nullable=True)
        is_active = db.Column(db.Boolean, default=True, nullable=False)

        __table_args__ = (
            db.Index('idx_push_sub_employee', 'employee_id', 'is_active'),
            db.UniqueConstraint('endpoint', name='uq_push_endpoint'),
        )

        def __repr__(self):
            return f'<PushSubscription {self.id}: employee={self.employee_id} active={self.is_active}>'

    return PushSubscription
