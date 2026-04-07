"""
WebAuthnCredential model - stores FIDO2/WebAuthn credentials for biometric unlock
"""
from datetime import datetime


def create_webauthn_credential_model(db):
    """Factory function to create WebAuthnCredential model with db instance"""

    class WebAuthnCredential(db.Model):
        """
        Stores WebAuthn/FIDO2 credentials registered by users for biometric
        app lock screen unlock (fingerprint, face ID, etc).
        One user can have multiple credentials (one per device).
        """
        __tablename__ = 'webauthn_credentials'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        employee_id = db.Column(db.String(50), db.ForeignKey('employees.id'), nullable=False)

        # WebAuthn credential data
        credential_id = db.Column(db.LargeBinary, nullable=False, unique=True)
        public_key = db.Column(db.LargeBinary, nullable=False)
        sign_count = db.Column(db.Integer, nullable=False, default=0)

        # Human-readable label for the credential (e.g., "iPhone", "Pixel")
        device_name = db.Column(db.String(100), nullable=True)

        # Metadata
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        last_used_at = db.Column(db.DateTime, nullable=True)
        is_active = db.Column(db.Boolean, default=True, nullable=False)

        __table_args__ = (
            db.CheckConstraint('sign_count >= 0', name='ck_webauthn_sign_count_positive'),
            db.Index('idx_webauthn_employee', 'employee_id', 'is_active'),
        )

        def update_sign_count(self, new_count):
            """Update sign count with monotonicity enforcement (WebAuthn replay detection)."""
            if new_count < self.sign_count:
                raise ValueError(
                    f"sign_count regression: {self.sign_count} -> {new_count} "
                    f"(possible cloned authenticator)"
                )
            self.sign_count = new_count
            self.last_used_at = datetime.utcnow()

        def to_safe_dict(self):
            """Serialize for API responses, excluding cryptographic material."""
            return {
                'id': self.id,
                'device_name': self.device_name or 'Unnamed Device',
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            }

        def __repr__(self):
            return f'<WebAuthnCredential {self.id}: employee={self.employee_id} device={self.device_name}>'

    return WebAuthnCredential
