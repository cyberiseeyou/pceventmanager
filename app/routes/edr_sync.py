"""
EDR Sync Routes
===============

Backend API routes for synchronizing EDR event data from Walmart Retail Link.
Provides manual sync functionality with MFA authentication.
"""

from flask import Blueprint, jsonify, request, current_app
from datetime import datetime
import traceback

# Create blueprint
edr_sync_bp = Blueprint('edr_sync', __name__, url_prefix='/api/sync')


@edr_sync_bp.route('/retaillink', methods=['POST'])
def sync_retaillink():
    """
    Sync EDR event data from Walmart Retail Link.

    Requires MFA code for authentication.
    Fetches events from 1 month ago to 1 month ahead and caches them.

    Request JSON:
        {
            "mfa_code": "123456"
        }

    Returns:
        {
            "success": true/false,
            "message": "Status message",
            "details": "Additional details",
            "cache_stats": {...}  # Optional cache statistics
        }
    """
    try:
        # Import EDR functionality
        try:
            from edr.report_generator import EDRReportGenerator
        except ImportError as e:
            return jsonify({
                'success': False,
                'message': 'EDR module not available',
                'details': str(e)
            }), 500

        # Get MFA code from request
        data = request.get_json()
        if not data or 'mfa_code' not in data:
            return jsonify({
                'success': False,
                'message': 'MFA code required',
                'details': 'Please provide your MFA authentication code'
            }), 400

        mfa_code = data['mfa_code'].strip()
        if not mfa_code:
            return jsonify({
                'success': False,
                'message': 'Invalid MFA code',
                'details': 'MFA code cannot be empty'
            }), 400

        # Get credentials from system settings
        SystemSetting = current_app.config.get('SystemSetting')
        if not SystemSetting:
            return jsonify({
                'success': False,
                'message': 'System configuration error',
                'details': 'SystemSetting model not available'
            }), 500

        username_setting = SystemSetting.query.filter_by(setting_key='edr_username').first()
        password_setting = SystemSetting.query.filter_by(setting_key='edr_password').first()
        mfa_id_setting = SystemSetting.query.filter_by(setting_key='edr_mfa_credential_id').first()

        if not username_setting or not password_setting or not mfa_id_setting:
            return jsonify({
                'success': False,
                'message': 'Credentials not configured',
                'details': 'Please configure Retail Link credentials in settings first'
            }), 400

        # Initialize EDR generator with caching enabled
        generator = EDRReportGenerator(
            enable_caching=True,
            cache_max_age_hours=24
        )

        # Set credentials
        generator.username = username_setting.setting_value
        generator.password = password_setting.setting_value
        generator.mfa_credential_id = mfa_id_setting.setting_value

        # Authenticate with Retail Link using provided MFA code
        auth_success = generator.authenticate(mfa_code=mfa_code)

        if not auth_success:
            return jsonify({
                'success': False,
                'message': 'Authentication failed',
                'details': 'Could not authenticate with Retail Link. Please check your credentials and MFA code.'
            }), 401

        # Fetch and cache events (defaults to 1 month before/after)
        events_data = generator.browse_events_with_cache(force_refresh=True)

        if not events_data:
            return jsonify({
                'success': False,
                'message': 'No events found',
                'details': 'Successfully authenticated but no events were returned from the API'
            }), 200

        # Get cache statistics
        cache_stats = generator.get_cache_stats()

        return jsonify({
            'success': True,
            'message': f'Successfully synced {len(events_data)} event items',
            'details': f"Cache updated: {cache_stats.get('unique_events', 0)} unique events from {cache_stats.get('earliest_event_date')} to {cache_stats.get('latest_event_date')}",
            'cache_stats': cache_stats
        }), 200

    except Exception as e:
        # Log the full error
        error_trace = traceback.format_exc()
        current_app.logger.error(f"Retail Link sync error: {error_trace}")

        return jsonify({
            'success': False,
            'message': 'Sync failed with error',
            'details': str(e)
        }), 500


@edr_sync_bp.route('/mvretail', methods=['POST'])
def sync_mvretail():
    """
    Sync employee and schedule data from MVRetail system.

    Uses existing sync_engine functionality.

    Returns:
        {
            "success": true/false,
            "message": "Status message",
            "details": "Additional details"
        }
    """
    try:
        # Import sync engine
        try:
            from sync_engine import sync_engine
        except ImportError as e:
            return jsonify({
                'success': False,
                'message': 'Sync engine not available',
                'details': str(e)
            }), 500

        # Check if sync is enabled
        if not sync_engine.is_sync_enabled():
            return jsonify({
                'success': False,
                'message': 'MVRetail sync is disabled',
                'details': 'Enable sync in system configuration to use this feature'
            }), 400

        # Trigger full sync
        result = sync_engine.sync_all()

        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Successfully synchronized with MVRetail',
                'details': f"Synced {result.get('records_synced', 0)} records"
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'MVRetail sync failed',
                'details': result.get('error', 'Unknown error occurred')
            }), 500

    except Exception as e:
        # Log the full error
        error_trace = traceback.format_exc()
        current_app.logger.error(f"MVRetail sync error: {error_trace}")

        return jsonify({
            'success': False,
            'message': 'Sync failed with error',
            'details': str(e)
        }), 500


@edr_sync_bp.route('/status/retaillink', methods=['GET'])
def retaillink_status():
    """
    Get Retail Link cache status and statistics.

    Returns:
        {
            "success": true/false,
            "cache_enabled": true/false,
            "cache_stats": {...}
        }
    """
    try:
        from edr.report_generator import EDRReportGenerator

        generator = EDRReportGenerator(enable_caching=True)
        cache_stats = generator.get_cache_stats()

        return jsonify({
            'success': True,
            'cache_enabled': cache_stats.get('caching_enabled', False),
            'cache_stats': cache_stats
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Could not retrieve cache status',
            'details': str(e)
        }), 500
