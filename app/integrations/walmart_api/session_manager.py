"""
Walmart API Session Manager.

Manages user sessions for Walmart Retail Link authentication with automatic timeout
and cleanup. Each user gets their own session with an independent authenticator instance.

Features:
    - 10-minute session timeout per user
    - Automatic refresh on activity
    - Thread-safe session storage
    - Automatic cleanup of expired sessions
    - Per-user authentication state

Session Lifecycle:
    1. User requests MFA code -> Session created
    2. User authenticates -> Session updated with auth token
    3. User makes API calls -> Session timeout refreshed
    4. Session expires after 10 minutes of inactivity -> Auto-cleanup

Author: Schedule Management System
Version: 1.0
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import threading
import logging


class WalmartSession:
    """
    Represents a single user's Walmart Retail Link session.

    Attributes:
        user_id (str): Unique identifier for the user
        authenticator: EDRAuthenticator instance for this user
        created_at (datetime): When the session was created
        last_activity (datetime): Last time the session was accessed
        expires_at (datetime): When the session will expire
        is_authenticated (bool): Whether MFA authentication completed
    """

    def __init__(self, user_id: str, authenticator):
        """
        Initialize a new Walmart session.

        Args:
            user_id: Unique identifier for the user
            authenticator: EDRAuthenticator instance
        """
        self.user_id = user_id
        self.authenticator = authenticator
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(minutes=10)
        self.is_authenticated = False

    def refresh(self):
        """Refresh session timeout - extends expiry by 10 minutes from now."""
        self.last_activity = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(minutes=10)

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at

    def mark_authenticated(self):
        """Mark session as fully authenticated (MFA completed)."""
        self.is_authenticated = True
        self.refresh()

    def get_time_remaining(self) -> int:
        """
        Get remaining session time in seconds.

        Returns:
            int: Seconds until session expires (0 if expired)
        """
        if self.is_expired():
            return 0
        delta = self.expires_at - datetime.utcnow()
        return int(delta.total_seconds())


class WalmartSessionManager:
    """
    Manages Walmart API sessions for all users.

    Thread-safe session storage with automatic cleanup of expired sessions.
    Each user can have only one active session at a time.

    Attributes:
        sessions (Dict[str, WalmartSession]): Active sessions by user_id
        lock (threading.Lock): Thread lock for safe concurrent access
        logger (logging.Logger): Logger instance
    """

    def __init__(self):
        """Initialize the session manager."""
        self.sessions: Dict[str, WalmartSession] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def create_session(self, user_id: str, authenticator) -> WalmartSession:
        """
        Create or replace a session for a user.

        If a session already exists for this user, it will be replaced.

        Args:
            user_id: Unique identifier for the user
            authenticator: EDRAuthenticator instance

        Returns:
            WalmartSession: The newly created session
        """
        with self.lock:
            session = WalmartSession(user_id, authenticator)
            self.sessions[user_id] = session
            self.logger.info(f"Created Walmart session for user {user_id}")
            return session

    def get_session(self, user_id: str) -> Optional[WalmartSession]:
        """
        Get active session for a user.

        Args:
            user_id: Unique identifier for the user

        Returns:
            Optional[WalmartSession]: Session if exists and not expired, None otherwise
        """
        with self.lock:
            session = self.sessions.get(user_id)

            if session is None:
                return None

            # Check if session expired
            if session.is_expired():
                self.logger.info(f"Session expired for user {user_id}")
                del self.sessions[user_id]
                return None

            # Refresh session timeout on access
            session.refresh()
            return session

    def remove_session(self, user_id: str):
        """
        Remove a user's session.

        Args:
            user_id: Unique identifier for the user
        """
        with self.lock:
            if user_id in self.sessions:
                del self.sessions[user_id]
                self.logger.info(f"Removed Walmart session for user {user_id}")

    def cleanup_expired_sessions(self):
        """
        Remove all expired sessions.

        Should be called periodically (e.g., every minute) to clean up
        old sessions and free memory.

        Returns:
            int: Number of sessions cleaned up
        """
        with self.lock:
            expired_users = [
                user_id for user_id, session in self.sessions.items()
                if session.is_expired()
            ]

            for user_id in expired_users:
                del self.sessions[user_id]

            if expired_users:
                self.logger.info(f"Cleaned up {len(expired_users)} expired Walmart sessions")

            return len(expired_users)

    def get_active_session_count(self) -> int:
        """
        Get count of active sessions.

        Returns:
            int: Number of active sessions
        """
        with self.lock:
            return len(self.sessions)

    def get_session_info(self, user_id: str) -> Optional[Dict]:
        """
        Get information about a user's session.

        Args:
            user_id: Unique identifier for the user

        Returns:
            Optional[Dict]: Session info if exists, None otherwise
        """
        session = self.get_session(user_id)
        if session is None:
            return None

        return {
            'user_id': session.user_id,
            'created_at': session.created_at.isoformat(),
            'last_activity': session.last_activity.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'is_authenticated': session.is_authenticated,
            'time_remaining_seconds': session.get_time_remaining()
        }


# Global session manager instance
session_manager = WalmartSessionManager()
