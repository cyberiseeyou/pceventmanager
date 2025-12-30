"""
Walmart Retail Link API Integration Module.

This module provides API endpoints for interacting with Walmart's Retail Link Event Management
System. It is completely separate from Crossmark's internal systems and handles:
    - MFA authentication with Walmart Retail Link
    - Event Detail Report (EDR) retrieval
    - PDF generation for events
    - User session management with automatic timeout

IMPORTANT: This is for WALMART systems only. For Crossmark internal operations, use the
appropriate Crossmark services in scheduler_app/services/.

Session Management:
    - 10-minute session timeout per user
    - Automatic refresh on API interaction
    - Separate sessions for each authenticated user
    - Automatic cleanup of expired sessions

Author: Schedule Management System
Version: 1.0
"""

from .routes import walmart_bp
from .session_manager import session_manager

__all__ = ['walmart_bp', 'session_manager']
