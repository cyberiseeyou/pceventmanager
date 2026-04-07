"""
SyncChangeLog model - tracks changes detected by the background sync daemon
"""
from datetime import datetime

VALID_CHANGE_TYPES = ('new_event', 'cancelled', 'modified', 'conflict')


def create_sync_change_log_model(db):
    """Factory function to create SyncChangeLog model with db instance"""

    class SyncChangeLog(db.Model):
        """
        Records changes detected when the background sync daemon polls the
        Crossmark MVRetail API and compares upstream data against local state.

        Change types:
            new_event - New event found in Crossmark, inserted locally
            cancelled - Event removed/cancelled in Crossmark, updated locally
            modified - Safe fields changed in Crossmark, auto-applied locally
            conflict - Protected fields differ between local and Crossmark (not auto-applied)
        """
        __tablename__ = 'sync_change_log'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)

        # What changed
        change_type = db.Column(db.String(20), nullable=False)
        entity_type = db.Column(db.String(20), nullable=False, default='event')
        entity_id = db.Column(db.String(100), nullable=False)

        # Human-readable description
        summary = db.Column(db.Text, nullable=False)

        # JSON field diffs for modified/conflict types
        # Format: {"field_name": {"local": "value", "upstream": "value"}}
        field_changes = db.Column(db.Text, nullable=True)

        # Conflict flag - True means this needs manual investigation
        is_conflict = db.Column(db.Boolean, default=False, nullable=False)

        # Timestamps
        detected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

        # Resolution tracking (only meaningful for conflicts)
        resolved = db.Column(db.Boolean, default=False, nullable=False)
        resolved_at = db.Column(db.DateTime, nullable=True)
        resolution_notes = db.Column(db.Text, nullable=True)

        # Push delivery tracking
        push_sent = db.Column(db.Boolean, default=False, nullable=False)
        push_sent_at = db.Column(db.DateTime, nullable=True)

        __table_args__ = (
            db.CheckConstraint(
                "change_type IN ('new_event', 'cancelled', 'modified', 'conflict')",
                name='ck_sync_change_type'
            ),
            db.Index('idx_sync_changelog_type_status', 'change_type', 'resolved'),
            db.Index('idx_sync_changelog_detected', 'detected_at'),
            db.Index('idx_sync_changelog_conflicts', 'is_conflict', 'resolved'),
            db.Index('idx_sync_changelog_push_pending', 'push_sent', 'detected_at'),
        )

        def resolve(self, notes=''):
            """Mark this conflict as resolved, encapsulating the state transition."""
            self.resolved = True
            self.resolved_at = datetime.utcnow()
            self.resolution_notes = notes

        def to_dict(self):
            """Serialize for API responses"""
            return {
                'id': self.id,
                'change_type': self.change_type,
                'entity_type': self.entity_type,
                'entity_id': self.entity_id,
                'summary': self.summary,
                'field_changes': self.field_changes,
                'is_conflict': self.is_conflict,
                'detected_at': self.detected_at.isoformat() if self.detected_at else None,
                'resolved': self.resolved,
                'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
                'resolution_notes': self.resolution_notes,
                'push_sent': self.push_sent,
            }

        def __repr__(self):
            conflict = ' [CONFLICT]' if self.is_conflict else ''
            return f'<SyncChangeLog {self.id}: {self.change_type} {self.entity_type}/{self.entity_id}{conflict}>'

    return SyncChangeLog
