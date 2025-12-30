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

# Initialize Blueprint and logger
walmart_bp = Blueprint('walmart_api', __name__, url_prefix='/api/walmart')
logger = logging.getLogger(__name__)

# Initialize PDF generator
pdf_generator = EDRPDFGenerator()

# Helper function to get models from app config
def get_models():
    """Get database models from current app config."""
    return {
        'Event': current_app.config['Event'],
        'Schedule': current_app.config['Schedule'],
        'Employee': current_app.config['Employee'],
        'db': current_app.extensions['sqlalchemy']
    }


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
        # Check if Walmart credentials are configured
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

        # Get Walmart credentials from app configuration
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
