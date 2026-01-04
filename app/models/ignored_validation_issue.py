"""
Ignored Validation Issue Model

Stores validation issues that users have chosen to ignore/dismiss.
Issues can be ignored by:
- Specific issue (rule_name + unique identifier like schedule_id or employee_id+date)
- Rule-wide (ignore all issues of a certain rule type)
"""


def create_ignored_validation_issue_model(db):
    """Create IgnoredValidationIssue model with the provided db instance"""

    class IgnoredValidationIssue(db.Model):
        """
        Tracks validation issues that have been ignored/dismissed by users.
        
        Ignored issues will be filtered out from the weekly validation display
        until they are un-ignored or expire.
        """
        __tablename__ = 'ignored_validation_issues'

        id = db.Column(db.Integer, primary_key=True)
        
        # Issue identification - used to match against validation results
        rule_name = db.Column(db.String(100), nullable=False, index=True)
        issue_hash = db.Column(db.String(255), nullable=False, index=True)  # Unique hash of issue details
        
        # Context for the issue
        issue_date = db.Column(db.Date, nullable=True)  # The date the issue refers to (null for weekly issues)
        schedule_id = db.Column(db.Integer, nullable=True)  # If issue is for a specific schedule
        employee_id = db.Column(db.String(50), nullable=True)  # If issue is for a specific employee
        event_id = db.Column(db.Integer, nullable=True)  # If issue is for a specific event
        
        # Ignore details
        reason = db.Column(db.String(500), nullable=True)  # Optional reason for ignoring
        ignored_by = db.Column(db.String(100), nullable=True)  # Who ignored it
        ignored_at = db.Column(db.DateTime, default=db.func.now())
        
        # Expiration - null means never expires
        expires_at = db.Column(db.DateTime, nullable=True)
        
        # Message stored for display
        message = db.Column(db.Text, nullable=True)
        severity = db.Column(db.String(20), nullable=True)

        def __repr__(self):
            return f'<IgnoredValidationIssue {self.rule_name} hash={self.issue_hash[:20]}>'

        @classmethod
        def generate_hash(cls, rule_name: str, details: dict) -> str:
            """
            Generate a unique hash for an issue based on its rule and details.
            This is used to identify the same issue across validation runs.
            """
            import hashlib
            import json
            
            # Build a stable string from the key identifying fields
            key_parts = [rule_name]
            
            # Add relevant detail fields that make this issue unique
            for field in ['schedule_id', 'employee_id', 'event_id', 'date', 'employee_name']:
                if field in details and details[field]:
                    key_parts.append(f"{field}:{details[field]}")
            
            key_str = '|'.join(sorted(key_parts))
            return hashlib.sha256(key_str.encode()).hexdigest()[:64]

        @classmethod
        def is_ignored(cls, rule_name: str, details: dict, db_session) -> bool:
            """Check if a specific issue is currently ignored"""
            issue_hash = cls.generate_hash(rule_name, details)
            
            from datetime import datetime
            ignored = db_session.query(cls).filter(
                cls.issue_hash == issue_hash,
                db.or_(
                    cls.expires_at.is_(None),
                    cls.expires_at > datetime.now()
                )
            ).first()
            
            return ignored is not None

    return IgnoredValidationIssue
