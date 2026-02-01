"""
Walmart Retail Link API Routes
================================

Flask API endpoints for Walmart Retail Link integration.

**IMPORTANT: WALMART SYSTEMS ONLY**
This module provides API access to Walmart's Event Management System.
It is completely separate from Crossmark systems and handles:
- Authentication with Walmart Retail Link
- EDR (Event Detail Report) data retrieval
- PDF generation for Walmart event documentation

API Endpoints:
--------------
Authentication:
    POST   /api/walmart/auth/request-mfa        - Request MFA code to user's phone
    POST   /api/walmart/auth/authenticate       - Complete authentication with MFA code
    POST   /api/walmart/auth/logout             - End current session
    GET    /api/walmart/auth/session-status     - Get current session information

EDR Reports:
    GET    /api/walmart/edr/<event_id>          - Get EDR data for specific event
    POST   /api/walmart/edr/batch-download      - Batch download EDR PDFs for multiple events

Health:
    GET    /api/walmart/health                  - Service health check

Session Management:
-------------------
- Sessions automatically timeout after 10 minutes of inactivity
- Each user gets their own independent session
- Session timeout refreshes automatically on any API call
- MFA authentication required before accessing EDR data

Security:
---------
- All endpoints except /health require Flask-Login authentication
- Walmart credentials stored in app.config (environment variables)
- Session isolation per user prevents cross-user interference

Version: 1.0
Author: Schedule Management System
"""

from flask import Blueprint, request, jsonify, current_app, send_file
from datetime import datetime
import os
import logging
import re
from typing import Dict, List, Optional, Tuple

from .session_manager import session_manager
from .authenticator import EDRAuthenticator
from app.integrations.edr.pdf_generator import EDRPDFGenerator
from app.routes.auth import require_authentication, get_current_user
from app.services.approved_events_service import ApprovedEventsService

# Initialize Blueprint and logger
walmart_bp = Blueprint('walmart_api', __name__, url_prefix='/api/walmart')
logger = logging.getLogger(__name__)

# Initialize PDF generator
pdf_generator = EDRPDFGenerator()

# Helper function to get models from app config
def get_models():
    """Get database models from current app config."""
    from app.models import get_models as app_get_models
    models = app_get_models()
    return {
        'Event': models['Event'],
        'Schedule': models['Schedule'],
        'Employee': models['Employee'],
        'db': current_app.extensions['sqlalchemy']
    }


def _fetch_approved_events_with_session(session, auth_token, club_numbers, start_date, end_date, event_types=None):
    """
    Fetch approved events using an existing authenticated session.

    This allows sharing the global authenticator from printing.py.

    Args:
        session: requests.Session with authenticated cookies
        auth_token: Authentication token from Event Management
        club_numbers: List of club/store numbers (uses first one)
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        event_types: Optional list of event type IDs

    Returns:
        List of approved events or None if request fails
    """
    if not auth_token:
        logger.error("No auth token - cannot fetch approved events")
        return None

    if not session:
        logger.error("No session object - cannot fetch approved events")
        return None

    # Convert club numbers to list of integers for API
    club_list = []
    for club in club_numbers:
        try:
            club_list.append(int(club))
        except (ValueError, TypeError):
            pass

    if not club_list:
        logger.error("No valid club numbers provided")
        return None

    base_url = "https://retaillink2.wal-mart.com/EventManagement"
    # Use the daily-schedule-report API (returns event-level data, not item-level)
    url = f"{base_url}/api/store-event/daily-schedule-report"

    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'origin': 'https://retaillink2.wal-mart.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'referer': f"{base_url}/daily-scheduled-report"
    }

    # Default to all event types if not specified
    if event_types is None:
        event_types = [1,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57]

    # Payload format for daily-schedule-report API
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "eventType": event_types,
        "clubList": club_list,
        "walmartWeekYear": ""
    }

    logger.info(f"Fetching events for clubs {club_list} from {start_date} to {end_date}")
    logger.info(f"Auth token present: {bool(auth_token)}, Session cookies: {len(session.cookies)}")

    try:
        response = session.post(url, headers=headers, json=payload, timeout=60)
        logger.info(f"Walmart API response status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Walmart API error: status={response.status_code}, body={response.text[:500]}")
            return None

        all_events = response.json()
        logger.info(f"Walmart API returned {len(all_events)} total events")

        # Log first event's keys for debugging
        if all_events:
            logger.info(f"Event fields available: {list(all_events[0].keys())}")

        # Get status from either 'status' or 'eventStatus' field
        def get_status(event):
            return (event.get('status') or event.get('eventStatus') or '').strip().upper()

        # Log unique statuses for debugging
        statuses = set(get_status(event) for event in all_events)
        logger.info(f"Event statuses found: {statuses}")

        # Filter for APPROVED status only
        approved_events = [
            event for event in all_events
            if get_status(event) == 'APPROVED'
        ]

        logger.info(f"Found {len(approved_events)} APPROVED (LIA) events out of {len(all_events)} total")
        return approved_events

    except Exception as e:
        logger.error(f"Failed to fetch approved events: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


@walmart_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.

    Returns service status and configuration without requiring authentication.
    Useful for monitoring and deployment verification.

    Returns:
        JSON response with:
        - status: 'healthy' if service is operational
        - walmart_configured: Whether Walmart credentials are configured
        - active_sessions: Number of active user sessions

    Example Response:
        {
            "status": "healthy",
            "walmart_configured": true,
            "active_sessions": 3
        }
    """
    try:
        # Check if Walmart credentials are configured (from SystemSetting or .env)
        SystemSetting = current_app.config.get('SystemSetting')

        if SystemSetting:
            has_credentials = all([
                SystemSetting.get_setting('edr_username') or current_app.config.get('WALMART_EDR_USERNAME'),
                SystemSetting.get_setting('edr_password') or current_app.config.get('WALMART_EDR_PASSWORD'),
                SystemSetting.get_setting('edr_mfa_credential_id') or current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID')
            ])
        else:
            has_credentials = all([
                current_app.config.get('WALMART_EDR_USERNAME'),
                current_app.config.get('WALMART_EDR_PASSWORD'),
                current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID')
            ])

        return jsonify({
            'status': 'healthy',
            'walmart_configured': has_credentials,
            'active_sessions': session_manager.get_active_session_count()
        }), 200

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@walmart_bp.route('/auth/request-mfa', methods=['POST'])
@require_authentication()
def request_mfa():
    """
    Request MFA authentication code.

    Initiates the Walmart authentication flow by:
    1. Getting Walmart credentials from app config
    2. Creating a new authenticator instance
    3. Submitting password (Step 1)
    4. Requesting MFA code to be sent to registered phone (Step 2)
    5. Creating session for this user

    The MFA code will be sent to the phone number registered with Walmart
    for the configured account.

    Required Authentication:
        Flask-Login session (logged in user)

    Returns:
        JSON response with:
        - success: Boolean indicating if MFA request succeeded
        - message: Status message
        - session_info: Session details (expires_at, time_remaining)

    Status Codes:
        200: MFA code requested successfully
        400: Missing Walmart configuration
        500: Authentication flow failed

    Example Response:
        {
            "success": true,
            "message": "MFA code sent to registered phone",
            "session_info": {
                "user_id": "user123",
                "created_at": "2025-10-05T12:00:00",
                "expires_at": "2025-10-05T12:10:00",
                "time_remaining_seconds": 600,
                "is_authenticated": false
            }
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401

        user_id = user.get('username', user.get('userId', 'unknown'))

        # Get Walmart credentials from SystemSetting database (with .env fallback)
        SystemSetting = current_app.config.get('SystemSetting')

        if SystemSetting:
            username = SystemSetting.get_setting('edr_username') or current_app.config.get('WALMART_EDR_USERNAME')
            password = SystemSetting.get_setting('edr_password') or current_app.config.get('WALMART_EDR_PASSWORD')
            mfa_credential_id = SystemSetting.get_setting('edr_mfa_credential_id') or current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID')
        else:
            # Fallback to .env config if SystemSetting not available
            username = current_app.config.get('WALMART_EDR_USERNAME')
            password = current_app.config.get('WALMART_EDR_PASSWORD')
            mfa_credential_id = current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID')

        if not all([username, password, mfa_credential_id]):
            logger.error("Walmart credentials not configured")
            return jsonify({
                'success': False,
                'message': 'Walmart credentials not configured in system settings'
            }), 400

        # Create new authenticator instance
        authenticator = EDRAuthenticator(username, password, mfa_credential_id)

        # Execute authentication steps 1-2
        logger.info(f"User {user_id} requesting MFA code")

        if not authenticator.step1_submit_password():
            logger.error(f"Password submission failed for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'Failed to authenticate with Walmart credentials'
            }), 500

        if not authenticator.step2_request_mfa_code():
            logger.error(f"MFA code request failed for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'Failed to request MFA code'
            }), 500

        # Create session for this user
        session = session_manager.create_session(str(user_id), authenticator)

        logger.info(f"MFA code requested successfully for user {user_id}")

        return jsonify({
            'success': True,
            'message': 'MFA code sent to registered phone',
            'session_info': session_manager.get_session_info(str(user_id))
        }), 200

    except Exception as e:
        user = get_current_user()
        user_id = user.get('username', 'unknown') if user else 'unknown'
        logger.error(f"MFA request failed for user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'MFA request failed: {str(e)}'
        }), 500


@walmart_bp.route('/auth/authenticate', methods=['POST'])
@require_authentication()
def authenticate():
    """
    Complete authentication with MFA code.

    Completes the Walmart authentication flow by:
    1. Retrieving user's session
    2. Validating the provided MFA code (Step 3)
    3. Registering page access (Step 4)
    4. Navigating to Event Management (Step 5)
    5. Getting authentication token (Step 6)
    6. Marking session as authenticated

    Required Authentication:
        Flask-Login session (logged in user)
        Active Walmart session (from request-mfa)

    Request Body:
        {
            "mfa_code": "123456"
        }

    Returns:
        JSON response with:
        - success: Boolean indicating authentication success
        - message: Status message
        - session_info: Updated session details

    Status Codes:
        200: Authentication successful
        400: Missing MFA code or session
        401: Invalid MFA code
        500: Authentication flow failed

    Example Response:
        {
            "success": true,
            "message": "Authentication successful",
            "session_info": {
                "user_id": "user123",
                "is_authenticated": true,
                "time_remaining_seconds": 600
            }
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401

        user_id = user.get('username', user.get('userId', 'unknown'))

        # Get MFA code from request
        data = request.get_json()
        if not data or 'mfa_code' not in data:
            return jsonify({
                'success': False,
                'message': 'MFA code is required'
            }), 400

        mfa_code = data['mfa_code'].strip()

        # Validate MFA code format (6 digits)
        if not re.match(r'^\d{6}$', mfa_code):
            return jsonify({
                'success': False,
                'message': 'MFA code must be 6 digits'
            }), 400

        # Get user's session
        session = session_manager.get_session(str(user_id))
        if not session:
            logger.error(f"No active session for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'No active session. Please request MFA code first.'
            }), 400

        authenticator = session.authenticator

        # Execute authentication steps 3-6
        logger.info(f"User {user_id} attempting authentication with MFA code")

        if not authenticator.step3_validate_mfa_code(mfa_code):
            logger.error(f"Invalid MFA code for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'Invalid MFA code'
            }), 401

        # Complete remaining authentication steps
        authenticator.step4_register_page_access()
        authenticator.step5_navigate_to_event_management()

        if not authenticator.step6_authenticate_event_management():
            logger.error(f"Event Management authentication failed for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'Failed to authenticate with Event Management system'
            }), 500

        # Mark session as authenticated
        session.mark_authenticated()

        logger.info(f"User {user_id} authenticated successfully")

        return jsonify({
            'success': True,
            'message': 'Authentication successful',
            'session_info': session_manager.get_session_info(str(user_id))
        }), 200

    except Exception as e:
        user = get_current_user()
        user_id = user.get('username', 'unknown') if user else 'unknown'
        logger.error(f"Authentication failed for user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Authentication failed: {str(e)}'
        }), 500


@walmart_bp.route('/auth/logout', methods=['POST'])
@require_authentication()
def logout():
    """
    End Walmart session.

    Removes the user's active Walmart session, effectively logging them out
    of the Walmart Retail Link system.

    Required Authentication:
        Flask-Login session (logged in user)

    Returns:
        JSON response with:
        - success: Boolean indicating logout success
        - message: Status message

    Status Codes:
        200: Logout successful (even if no session existed)

    Example Response:
        {
            "success": true,
            "message": "Logged out successfully"
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if user:
            user_id = user.get('username', user.get('userId', 'unknown'))
            session_manager.remove_session(str(user_id))
            logger.info(f"User {user_id} logged out of Walmart session")

        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200

    except Exception as e:
        user = get_current_user()
        user_id = user.get('username', 'unknown') if user else 'unknown'
        logger.error(f"Logout failed for user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Logout failed: {str(e)}'
        }), 500


@walmart_bp.route('/auth/session-status', methods=['GET'])
@require_authentication()
def session_status():
    """
    Get current session status.

    Retrieves information about the user's current Walmart session,
    including authentication status and time remaining.

    Required Authentication:
        Flask-Login session (logged in user)

    Returns:
        JSON response with:
        - has_session: Boolean indicating if session exists
        - session_info: Session details if exists, null otherwise

    Status Codes:
        200: Status retrieved successfully

    Example Response (with active session):
        {
            "has_session": true,
            "session_info": {
                "user_id": "user123",
                "created_at": "2025-10-05T12:00:00",
                "last_activity": "2025-10-05T12:05:00",
                "expires_at": "2025-10-05T12:15:00",
                "is_authenticated": true,
                "time_remaining_seconds": 300
            }
        }

    Example Response (no session):
        {
            "has_session": false,
            "session_info": null
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'has_session': False,
                'session_info': None
            }), 200

        user_id = user.get('username', user.get('userId', 'unknown'))
        session_info = session_manager.get_session_info(str(user_id))

        return jsonify({
            'has_session': session_info is not None,
            'session_info': session_info
        }), 200

    except Exception as e:
        user = get_current_user()
        user_id = user.get('username', 'unknown') if user else 'unknown'
        logger.error(f"Session status check failed for user {user_id}: {str(e)}")
        return jsonify({
            'has_session': False,
            'session_info': None,
            'error': str(e)
        }), 500


@walmart_bp.route('/edr/<event_id>', methods=['GET'])
@require_authentication()
def get_edr_report(event_id: str):
    """
    Get EDR (Event Detail Report) data for a specific event.

    Retrieves the Event Detail Report from Walmart Retail Link for the
    specified event ID. Requires active authenticated session.

    Required Authentication:
        Flask-Login session (logged in user)
        Active authenticated Walmart session

    URL Parameters:
        event_id (str): Walmart event ID (project_ref_num)

    Returns:
        JSON response with EDR data or error message

    Status Codes:
        200: EDR data retrieved successfully
        400: No authenticated session
        404: Event not found in Walmart system
        500: Retrieval failed

    Example Response:
        {
            "success": true,
            "event_id": "12345",
            "edr_data": {
                "demoId": "12345",
                "demoName": "Product Demo Event",
                "demoDate": "2025-10-05",
                "demoClassCode": "45",
                "demoStatusCode": "2",
                "itemDetails": [...]
            }
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401

        user_id = user.get('username', user.get('userId', 'unknown'))

        # Get user's authenticated session
        session = session_manager.get_session(str(user_id))
        if not session:
            logger.error(f"No active session for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'No active session. Please authenticate first.'
            }), 400

        if not session.is_authenticated:
            logger.error(f"Session not authenticated for user {user_id}")
            return jsonify({
                'success': False,
                'message': 'Session not authenticated. Please complete MFA authentication.'
            }), 400

        # Refresh session timeout on access
        session.refresh()

        # Get EDR report from Walmart
        authenticator = session.authenticator
        logger.info(f"User {user_id} requesting EDR for event {event_id}")

        edr_data = authenticator.get_edr_report(event_id)

        if not edr_data:
            logger.error(f"EDR data not found for event {event_id}")
            return jsonify({
                'success': False,
                'message': f'EDR data not found for event {event_id}'
            }), 404

        logger.info(f"EDR retrieved successfully for event {event_id}")

        return jsonify({
            'success': True,
            'event_id': event_id,
            'edr_data': edr_data
        }), 200

    except Exception as e:
        logger.error(f"EDR retrieval failed for event {event_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'EDR retrieval failed: {str(e)}'
        }), 500


@walmart_bp.route('/edr/batch-download', methods=['POST'])
@require_authentication()
def batch_download_edrs():
    """
    Batch download EDR PDFs for multiple events.

    Downloads EDR data from Walmart and generates PDF files for multiple events.
    Events can be specified either by date (all events on that date) or by
    explicit list of event IDs.

    PDFs are saved to: uploads/walmart_edrs/{YYYYMMDD}/

    Required Authentication:
        Flask-Login session (logged in user)
        Active authenticated Walmart session

    Request Body (Option 1 - By Date):
        {
            "date": "2025-10-05"  // YYYY-MM-DD format
        }

    Request Body (Option 2 - By Event IDs):
        {
            "event_ids": ["12345", "12346", "12347"]
        }

    Returns:
        JSON response with:
        - success: Overall success status
        - total: Total number of events processed
        - successful: Number of successful downloads
        - failed: Number of failed downloads
        - results: List of individual results
        - output_directory: Where PDFs were saved

    Status Codes:
        200: Batch processing completed (check individual results)
        400: Invalid request or no authenticated session
        500: Batch processing failed

    Example Response:
        {
            "success": true,
            "total": 3,
            "successful": 2,
            "failed": 1,
            "results": [
                {
                    "event_id": "12345",
                    "success": true,
                    "filename": "EDR_12345_John_Doe.pdf",
                    "employee_name": "John Doe"
                },
                {
                    "event_id": "12346",
                    "success": true,
                    "filename": "EDR_12346_Jane_Smith.pdf",
                    "employee_name": "Jane Smith"
                },
                {
                    "event_id": "12347",
                    "success": false,
                    "error": "EDR data not found"
                }
            ],
            "output_directory": "uploads/walmart_edrs/20251005"
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401

        user_id = user.get('username', user.get('userId', 'unknown'))

        # Get user's authenticated session
        session = session_manager.get_session(str(user_id))
        if not session:
            return jsonify({
                'success': False,
                'message': 'No active session. Please authenticate first.'
            }), 400

        if not session.is_authenticated:
            return jsonify({
                'success': False,
                'message': 'Session not authenticated. Please complete MFA authentication.'
            }), 400

        # Refresh session timeout
        session.refresh()

        # Get models for database queries
        models = get_models()
        Event = models['Event']
        Schedule = models['Schedule']
        Employee = models['Employee']
        db = models['db']

        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Request body is required'
            }), 400

        # Get events to process
        events_to_process = []

        if 'date' in data:
            # Option 1: Get events by date
            try:
                target_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid date format. Use YYYY-MM-DD'
                }), 400

            # Query database for scheduled events on this date
            schedules = Schedule.query.filter(
                db.func.date(Schedule.schedule_datetime) == target_date
            ).all()

            event_ids = [str(s.event_ref_num) for s in schedules]

            logger.info(f"Found {len(event_ids)} events for date {target_date}")

        elif 'event_ids' in data:
            # Option 2: Use provided event IDs
            event_ids = data['event_ids']

            if not isinstance(event_ids, list):
                return jsonify({
                    'success': False,
                    'message': 'event_ids must be a list'
                }), 400

        else:
            return jsonify({
                'success': False,
                'message': 'Either "date" or "event_ids" must be provided'
            }), 400

        if not event_ids:
            return jsonify({
                'success': False,
                'message': 'No events found to process'
            }), 400

        # Create output directory
        date_str = datetime.now().strftime('%Y%m%d')
        output_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'walmart_edrs', date_str)
        os.makedirs(output_dir, exist_ok=True)

        # Process each event
        authenticator = session.authenticator
        results = []
        successful = 0
        failed = 0

        logger.info(f"Starting batch EDR download for {len(event_ids)} events")

        for event_id in event_ids:
            try:
                # Get event from database to find employee name
                event = Event.query.filter_by(project_ref_num=int(event_id)).first()
                employee_name = 'N/A'

                if event:
                    schedule = Schedule.query.filter_by(event_ref_num=event.project_ref_num).first()
                    if schedule:
                        employee = Employee.query.get(schedule.employee_id)
                        if employee:
                            employee_name = employee.name

                # Get EDR data from Walmart
                edr_data = authenticator.get_edr_report(str(event_id))

                if not edr_data:
                    results.append({
                        'event_id': str(event_id),
                        'success': False,
                        'error': 'EDR data not found'
                    })
                    failed += 1
                    continue

                # Generate PDF filename
                safe_name = re.sub(r'[^\w\s-]', '', employee_name).strip().replace(' ', '_')
                pdf_filename = f"EDR_{event_id}_{safe_name}.pdf"
                pdf_path = os.path.join(output_dir, pdf_filename)

                # Generate PDF
                if pdf_generator.generate_pdf(edr_data, pdf_path, employee_name):
                    results.append({
                        'event_id': str(event_id),
                        'success': True,
                        'filename': pdf_filename,
                        'employee_name': employee_name
                    })
                    successful += 1
                    logger.info(f"Generated PDF for event {event_id}")
                else:
                    results.append({
                        'event_id': str(event_id),
                        'success': False,
                        'error': 'PDF generation failed'
                    })
                    failed += 1

            except Exception as e:
                logger.error(f"Failed to process event {event_id}: {str(e)}")
                results.append({
                    'event_id': str(event_id),
                    'success': False,
                    'error': str(e)
                })
                failed += 1

        logger.info(f"Batch EDR download completed: {successful} successful, {failed} failed")

        return jsonify({
            'success': True,
            'total': len(event_ids),
            'successful': successful,
            'failed': failed,
            'results': results,
            'output_directory': output_dir
        }), 200

    except Exception as e:
        logger.error(f"Batch EDR download failed: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Batch download failed: {str(e)}'
        }), 500


@walmart_bp.route('/events/approved', methods=['GET'])
@require_authentication()
def get_approved_events():
    """
    Get APPROVED events from Walmart merged with local database status.

    Retrieves events with APPROVED status from Walmart's Daily Scheduled Report
    and merges them with local database status to show:
    - Which events need scheduling
    - Which events need API submission
    - Which events need scan-out in Walmart

    Business Rule: APPROVED events must be scanned out by 6 PM on:
    - Fridays
    - Saturdays
    - Last day of the month

    Required Authentication:
        Flask-Login session (logged in user)
        Active authenticated Walmart session

    Query Parameters:
        club (required): Club/store number (e.g., 8135)
        start_date (optional): Start date YYYY-MM-DD (default: 1st of previous month)
        end_date (optional): End date YYYY-MM-DD (default: today)
        include_core_events (optional): Set to 'true' to include matching Core events from local DB

    Returns:
        JSON response with:
        - success: Boolean
        - events: List of merged event data
        - summary: Counts by local status
        - scanout_warning: Warning info for Fri/Sat/EOM
        - date_range: The date range used for the query

    Status Codes:
        200: Events retrieved successfully
        400: Missing club parameter or no authenticated session
        500: Retrieval failed

    Example Response:
        {
            "success": true,
            "events": [
                {
                    "event_id": 615801,
                    "event_name": "01.04-Smucker-Grape&StrawberryUncrustables",
                    "scheduled_date": "2026-01-04",
                    "walmart_status": "APPROVED",
                    "local_status": "scheduled",
                    "local_status_label": "Scheduled",
                    "local_status_icon": "✅",
                    "required_action": "Submit to API",
                    "assigned_employee_name": "John Doe",
                    "schedule_datetime": "2026-01-04T10:30:00",
                    "api_submitted_at": null
                }
            ],
            "summary": {
                "total": 15,
                "not_in_db": 2,
                "unscheduled": 3,
                "scheduled": 5,
                "api_submitted": 5,
                "api_failed": 0
            },
            "scanout_warning": {
                "show_warning": true,
                "reason": "Friday",
                "urgency": "warning",
                "deadline": "6:00 PM"
            },
            "date_range": {
                "start_date": "2025-12-01",
                "end_date": "2026-01-04"
            }
        }
    """
    try:
        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401

        user_id = user.get('username', user.get('userId', 'unknown'))

        # Get club parameter (required)
        club = request.args.get('club')
        if not club:
            return jsonify({
                'success': False,
                'message': 'Club parameter is required'
            }), 400

        # Get date range (optional, defaults to previous month start to today)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            default_start, default_end = ApprovedEventsService.get_date_range_for_approved_events()
            start_date = start_date or default_start
            end_date = end_date or default_end

        # Try multiple authentication sources in order of preference
        walmart_events = None
        auth_source = None

        # 1. First try session-based authenticator (from this page's MFA flow)
        user_session = session_manager.get_session(str(user_id))
        if user_session and user_session.is_authenticated:
            user_session.refresh()
            authenticator = user_session.authenticator
            if authenticator and authenticator.auth_token:
                logger.info(f"Using session-based authenticator for user {user_id}")
                auth_source = "session"
                walmart_events = _fetch_approved_events_with_session(
                    authenticator.session,
                    authenticator.auth_token,
                    club_numbers=[club],
                    start_date=start_date,
                    end_date=end_date
                )

        # 2. If session auth didn't work, try global authenticator from printing module
        if walmart_events is None:
            try:
                from app.routes.printing import edr_authenticator as global_authenticator
                if global_authenticator and global_authenticator.auth_token:
                    logger.info(f"Using global EDR authenticator for user {user_id}")
                    auth_source = "global"
                    walmart_events = _fetch_approved_events_with_session(
                        global_authenticator.session,
                        global_authenticator.auth_token,
                        club_numbers=[club],
                        start_date=start_date,
                        end_date=end_date
                    )
            except ImportError:
                logger.warning("Printing module not available for global authenticator")

        # 3. If still no events, return appropriate error
        if walmart_events is None:
            if not user_session or not user_session.is_authenticated:
                return jsonify({
                    'success': False,
                    'message': 'Not authenticated. Please click "Request MFA Code" to authenticate.'
                }), 400
            else:
                logger.error(f"Failed to fetch events for user {user_id}, auth_source={auth_source}")
                return jsonify({
                    'success': False,
                    'message': 'Failed to fetch events from Walmart. The session may have expired. Please try authenticating again.'
                }), 500

        # Get models for database queries
        models = get_models()
        Event = models['Event']
        Schedule = models['Schedule']
        Employee = models['Employee']
        db = models['db']

        # Try to get PendingSchedule model (may not exist in all setups)
        PendingSchedule = current_app.config.get('PendingSchedule')

        # Merge with local database status
        service = ApprovedEventsService(db, Event, Schedule, Employee, PendingSchedule)
        merged_events = service.merge_with_local_status(walmart_events)

        # Optionally enrich with Core event data from local database
        include_core_events = request.args.get('include_core_events', '').lower() == 'true'
        if include_core_events:
            merged_events = service.enrich_with_core_event_data(merged_events)

        # Get summary counts
        summary = service.get_summary_counts(merged_events)

        # Check for scan-out warning
        scanout_warning = ApprovedEventsService.should_show_scanout_warning()

        logger.info(f"Returning {len(merged_events)} approved events for club {club}")

        return jsonify({
            'success': True,
            'events': merged_events,
            'summary': summary,
            'scanout_warning': scanout_warning,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            },
            'session_info': session_manager.get_session_info(str(user_id))
        }), 200

    except Exception as e:
        logger.error(f"Failed to get approved events: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to get approved events: {str(e)}'
        }), 500


@walmart_bp.route('/events/roll', methods=['POST'])
@require_authentication()
def roll_event():
    """
    Roll an event to a new scheduled date in Walmart.

    This endpoint allows rolling events directly from the application by making
    an authenticated API call to Walmart's Event Management system.

    Required Authentication:
        - Flask-Login session (logged in user)
        - Active Walmart session (via MFA or global authenticator)

    Request Body (JSON):
        - event_id (str): Walmart event ID (required)
        - scheduled_date (str): Target date in YYYY-MM-DD format (required)
        - club_id (str): Club/store number (optional, defaults to '8135')

    Returns:
        JSON response with:
        - success: Boolean indicating if roll was successful
        - message: Success or error message
        - event_id: The event ID that was rolled
        - scheduled_date: The date it was rolled to

    Status Codes:
        200: Event rolled successfully
        400: Missing required parameters or not authenticated
        500: Roll operation failed

    Example Request:
        POST /api/walmart/events/roll
        {
            "event_id": "619688",
            "scheduled_date": "2026-01-11",
            "club_id": "8135"
        }

    Example Response:
        {
            "success": true,
            "message": "Event 619688 rolled to 2026-01-11",
            "event_id": "619688",
            "scheduled_date": "2026-01-11"
        }
    """
    try:
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401

        user_id = user.get('username', user.get('userId', 'unknown'))

        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Request body required'
            }), 400

        event_id = data.get('event_id')
        scheduled_date = data.get('scheduled_date')
        club_id = data.get('club_id', '8135')

        if not event_id or not scheduled_date:
            return jsonify({
                'success': False,
                'message': 'event_id and scheduled_date are required'
            }), 400

        # Get Walmart user ID from config (required for API call)
        try:
            from app.models import SystemSetting
            walmart_user_id = SystemSetting.get_setting('walmart_user_id')
        except:
            walmart_user_id = None

        if not walmart_user_id:
            walmart_user_id = current_app.config.get('WALMART_USER_ID')

        if not walmart_user_id:
            return jsonify({
                'success': False,
                'message': 'Walmart user ID not configured. Please set walmart_user_id in system settings.'
            }), 500

        # Try to get authenticated session
        authenticator = None

        # 1. Try session-based authenticator
        user_session = session_manager.get_session(str(user_id))
        if user_session and user_session.is_authenticated:
            user_session.refresh()
            authenticator = user_session.authenticator

        # 2. Try global authenticator from printing module
        if not authenticator or not authenticator.auth_token:
            try:
                from app.routes.printing import edr_authenticator as global_authenticator
                if global_authenticator and global_authenticator.auth_token:
                    authenticator = global_authenticator
            except ImportError:
                pass

        if not authenticator or not authenticator.auth_token:
            return jsonify({
                'success': False,
                'message': 'Not authenticated with Walmart. Please authenticate first.'
            }), 400

        # Call roll_event method
        result = authenticator.roll_event(event_id, scheduled_date, club_id, walmart_user_id)

        if result['success']:
            logger.info(f"User {user_id} rolled event {event_id} to {scheduled_date}")
            return jsonify({
                'success': True,
                'message': f'Event {event_id} rolled to {scheduled_date}',
                'event_id': event_id,
                'scheduled_date': scheduled_date
            }), 200
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Failed to roll event {event_id}: {error_msg}")
            return jsonify({
                'success': False,
                'message': f'Failed to roll event: {error_msg}'
            }), 500

    except Exception as e:
        logger.error(f"Roll event error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500


@walmart_bp.route('/events/search-core/<event_id>', methods=['GET'])
@require_authentication()
def search_core_events(event_id: str):
    """
    Search for Core events in local database by event ID.

    Searches the local Event table for events where project_name contains
    the given event ID. Prioritizes Core events over Supervisor events.

    This endpoint mirrors the search behavior of the all events page -
    when searching by event ID, it finds matching events in the local database.

    Required Authentication:
        Flask-Login session (logged in user)

    URL Parameters:
        event_id (str): The 6-digit event ID to search for

    Returns:
        JSON response with:
        - success: Boolean
        - event_id: The searched event ID
        - matches: List of matching local events with details
        - count: Number of matches found

    Status Codes:
        200: Search completed successfully
        400: Invalid event ID format

    Example Response:
        {
            "success": true,
            "event_id": "615801",
            "matches": [
                {
                    "event_id": 12345,
                    "project_name": "615801 Core Event Name",
                    "event_type": "Core",
                    "is_scheduled": true,
                    "assigned_employee_name": "John Doe",
                    "schedule_datetime": "2026-01-04T10:30:00"
                },
                {
                    "event_id": 12346,
                    "project_name": "615801 Supervisor Event Name",
                    "event_type": "Supervisor",
                    "is_scheduled": true,
                    "assigned_employee_name": "Jane Smith",
                    "schedule_datetime": "2026-01-04T10:30:00"
                }
            ],
            "count": 2
        }
    """
    try:
        # Validate event ID format
        if not event_id or not event_id.isdigit():
            return jsonify({
                'success': False,
                'message': 'Event ID must be numeric'
            }), 400

        # Get models for database queries
        models = get_models()
        Event = models['Event']
        Schedule = models['Schedule']
        Employee = models['Employee']
        db = models['db']

        # Try to get PendingSchedule model (may not exist in all setups)
        PendingSchedule = current_app.config.get('PendingSchedule')

        # Search for matching Core events
        service = ApprovedEventsService(db, Event, Schedule, Employee, PendingSchedule)
        matches = service.find_core_events_by_event_id(int(event_id))

        logger.info(f"Core event search for {event_id}: found {len(matches)} matches")

        return jsonify({
            'success': True,
            'event_id': event_id,
            'matches': matches,
            'count': len(matches)
        }), 200

    except Exception as e:
        logger.error(f"Core event search failed for {event_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Search failed: {str(e)}'
        }), 500


@walmart_bp.route('/events/scanout-status', methods=['GET'])
def get_scanout_status():
    """
    Get scan-out warning status without requiring authentication.

    This endpoint can be called without a Walmart session to check if
    today is a scan-out deadline day (Friday, Saturday, or last day of month).

    Returns:
        JSON response with scan-out warning info

    Status Codes:
        200: Status retrieved successfully

    Example Response:
        {
            "show_warning": true,
            "reason": "Friday",
            "urgency": "warning",
            "deadline": "6:00 PM",
            "is_friday": true,
            "is_saturday": false,
            "is_last_day_of_month": false,
            "current_hour": 14
        }
    """
    return jsonify(ApprovedEventsService.should_show_scanout_warning()), 200


# Error handlers for the blueprint
@walmart_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors within the Walmart API blueprint."""
    return jsonify({
        'success': False,
        'message': 'Endpoint not found'
    }), 404


@walmart_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors within the Walmart API blueprint."""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500
