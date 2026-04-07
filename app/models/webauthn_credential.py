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
            db.Index('idx_webauthn_employee', 'employee_id', 'is_active'),
        )

        def __repr__(self):
            return f'<WebAuthnCredential {self.id}: employee={self.employee_id} device={self.device_name}>'

    return WebAuthnCredential
