"""
Audit Log models
Tracks automated daily audits and system health checks
"""
from datetime import datetime


def create_audit_models(db):
    """Factory function to create audit models with db instance"""

    class AuditLog(db.Model):
        """
        Audit log for daily system checks

        Stores results of automated daily audits including:
        - Issue counts by severity
        - Detailed issue information
        - Summary of findings
        """
        __tablename__ = 'audit_logs'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        audit_date = db.Column(db.Date, nullable=False, index=True)
        audit_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        # Issue counts
        total_issues = db.Column(db.Integer, default=0)
        critical_issues = db.Column(db.Integer, default=0)
        warning_issues = db.Column(db.Integer, default=0)
        info_issues = db.Column(db.Integer, default=0)

        # Summary and details
        summary = db.Column(db.Text)
        details_json = db.Column(db.Text)  # JSON string of issue details

        # Notification tracking
        notification_sent = db.Column(db.Boolean, default=False)
        notification_sent_at = db.Column(db.DateTime)

        # Resolution tracking
        resolved = db.Column(db.Boolean, default=False)
        resolved_at = db.Column(db.DateTime)
        resolved_by = db.Column(db.String(100))  # Future: user ID

        __table_args__ = (
            db.Index('idx_audit_date_timestamp', 'audit_date', 'audit_timestamp'),
        )

        def __repr__(self):
            return f'<AuditLog {self.audit_date}: {self.total_issues} issues>'

    class AuditNotificationSettings(db.Model):
        """
        Configuration for audit notifications

        Controls who gets notified about audit results and when
        """
        __tablename__ = 'audit_notification_settings'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)

        # Notification recipients
        email_recipients = db.Column(db.Text)  # Comma-separated email addresses

        # Notification thresholds
        notify_on_critical = db.Column(db.Boolean, default=True)
        notify_on_warning = db.Column(db.Boolean, default=False)
        notify_on_info = db.Column(db.Boolean, default=False)

        # Notification schedule
        notification_time = db.Column(db.Time, default=datetime.strptime('06:00', '%H:%M').time())
        notification_days = db.Column(db.String(50), default='1,2,3,4,5')  # Weekdays (1=Monday, 7=Sunday)

        # Notification format
        include_details = db.Column(db.Boolean, default=True)
        include_action_items = db.Column(db.Boolean, default=True)

        # Status
        is_active = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        def __repr__(self):
            return f'<AuditNotificationSettings {self.id}>'

    return AuditLog, AuditNotificationSettings
