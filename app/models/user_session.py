"""
User Session Model - Persistent, scalable session management

Replaces the in-memory session_store with database-backed sessions.
Provides thread-safe, persistent session storage that works across
multiple workers and server restarts.

Benefits over in-memory sessions:
- Thread-safe
- Persistent across restarts
- Scales horizontally (multiple workers/servers)
- Automatic cleanup via indexes
- Audit trail of user activity
"""
from datetime import datetime, timedelta
import secrets
from typing import Optional, Dict, Any


def create_user_session_model(db):
    """Factory function to create UserSession model with db instance"""

    class UserSession(db.Model):
        """
        Persistent user session storage

        Stores authenticated user sessions with automatic expiration
        and cleanup capabilities.
        """
        __tablename__ = 'user_sessions'

        session_id = db.Column(db.String(64), primary_key=True)
        user_id = db.Column(db.String(100), nullable=False, index=True)
        session_data = db.Column(db.JSON, nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        expires_at = db.Column(db.DateTime, nullable=False, index=True)
        last_activity = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        # Crossmark-specific fields
        phpsessid = db.Column(db.String(100))
        crossmark_authenticated = db.Column(db.Boolean, default=False)

        __table_args__ = (
            # Index for efficient cleanup of expired sessions
            db.Index('idx_sessions_cleanup', 'expires_at'),
            # Composite index for user activity queries
            db.Index('idx_sessions_user_activity', 'user_id', 'last_activity'),
        )

        @classmethod
        def create_session(
            cls,
            user_id: str,
            session_data: Dict[str, Any],
            duration_hours: int = 24,
            phpsessid: Optional[str] = None
        ) -> 'UserSession':
            """
            Create new user session

            Args:
                user_id: Unique user identifier
                session_data: Dictionary of session data to store
                duration_hours: How many hours until session expires
                phpsessid: Optional Crossmark PHP session ID

            Returns:
                UserSession: New session instance (not yet committed)

            Example:
                >>> session = UserSession.create_session(
                ...     user_id='john.doe',
                ...     session_data={'user_info': {...}},
                ...     duration_hours=24
                ... )
                >>> db.session.add(session)
                >>> db.session.commit()
            """
            session_id = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)

            session = cls(
                session_id=session_id,
                user_id=user_id,
                session_data=session_data,
                expires_at=expires_at,
                phpsessid=phpsessid,
                crossmark_authenticated=bool(phpsessid)
            )

            return session

        @classmethod
        def get_valid_session(cls, session_id: str) -> Optional['UserSession']:
            """
            Get session if valid and not expired

            Args:
                session_id: Session ID to look up

            Returns:
                UserSession if found and valid, None otherwise

            Example:
                >>> session = UserSession.get_valid_session('abc123...')
                >>> if session:
                ...     print(f"User {session.user_id} is authenticated")
            """
            return cls.query.filter(
                cls.session_id == session_id,
                cls.expires_at > datetime.utcnow()
            ).first()

        @classmethod
        def cleanup_expired(cls, db_session) -> int:
            """
            Remove all expired sessions from database

            Should be called periodically (e.g., daily cron job or on app startup)

            Args:
                db_session: SQLAlchemy database session

            Returns:
                Number of sessions deleted

            Example:
                >>> # In a background task or cron job:
                >>> count = UserSession.cleanup_expired(db.session)
                >>> print(f"Cleaned up {count} expired sessions")
            """
            count = cls.query.filter(
                cls.expires_at <= datetime.utcnow()
            ).delete()

            db_session.commit()
            return count

        @classmethod
        def get_user_sessions(cls, user_id: str, active_only: bool = True):
            """
            Get all sessions for a specific user

            Args:
                user_id: User to get sessions for
                active_only: Only return non-expired sessions

            Returns:
                List of UserSession objects

            Example:
                >>> sessions = UserSession.get_user_sessions('john.doe')
                >>> print(f"User has {len(sessions)} active sessions")
            """
            query = cls.query.filter(cls.user_id == user_id)

            if active_only:
                query = query.filter(cls.expires_at > datetime.utcnow())

            return query.order_by(cls.last_activity.desc()).all()

        @classmethod
        def revoke_user_sessions(cls, user_id: str, db_session, except_session_id: Optional[str] = None) -> int:
            """
            Revoke all sessions for a user (e.g., after password change)

            Args:
                user_id: User whose sessions to revoke
                db_session: SQLAlchemy database session
                except_session_id: Optional session ID to keep (e.g., current session)

            Returns:
                Number of sessions revoked

            Example:
                >>> # Revoke all sessions except current one after password change
                >>> count = UserSession.revoke_user_sessions(
                ...     user_id='john.doe',
                ...     db_session=db.session,
                ...     except_session_id=current_session_id
                ... )
            """
            query = cls.query.filter(cls.user_id == user_id)

            if except_session_id:
                query = query.filter(cls.session_id != except_session_id)

            count = query.delete()
            db_session.commit()
            return count

        def refresh(self):
            """
            Update last activity timestamp

            Call this on each request to track user activity and
            prevent session timeout for active users.

            Example:
                >>> session = UserSession.get_valid_session(session_id)
                >>> if session:
                ...     session.refresh()
                ...     db.session.commit()
            """
            self.last_activity = datetime.utcnow()

        def extend(self, hours: int = 24):
            """
            Extend session expiration time

            Args:
                hours: How many hours to extend from now

            Example:
                >>> session.extend(hours=48)  # Extend to 48 hours from now
                >>> db.session.commit()
            """
            self.expires_at = datetime.utcnow() + timedelta(hours=hours)

        def is_expired(self) -> bool:
            """Check if session has expired"""
            return datetime.utcnow() >= self.expires_at

        def time_until_expiry(self) -> timedelta:
            """Get time remaining until session expires"""
            return self.expires_at - datetime.utcnow()

        def __repr__(self):
            return f'<UserSession {self.session_id[:8]}... user={self.user_id}>'

    return UserSession
