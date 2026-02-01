"""
Auto-Scheduler Settings API Endpoints
FR38: Scenario 8 - Auto-Scheduler Event Type Filtering

Provides configuration management for auto-scheduler behavior including
event type filtering and per-event overrides.
"""
from flask import request, jsonify, current_app
from app.models import get_models
import json
import logging

logger = logging.getLogger(__name__)


def get_auto_scheduler_settings_endpoint():
    """
    Get current auto-scheduler configuration settings.

    Request: GET /api/auto-scheduler/settings

    Response: {
        "success": true,
        "settings": {
            "enabled_event_types": ["Core", "Juicer", "Digitals"],
            "scheduling_window_days": 3,
            "require_approval": true
        }
    }
    """
    SystemSetting = current_app.config['SystemSetting']

    try:
        # Get settings from database (stored as JSON)
        settings_json = SystemSetting.get_setting('auto_scheduler_config', '{}')

        if isinstance(settings_json, str):
            settings = json.loads(settings_json)
        else:
            settings = settings_json

        # Provide defaults if not set
        default_settings = {
            'enabled_event_types': ['Core', 'Juicer', 'Freeosk', 'Digitals', 'Supervisor', 'Other'],
            'scheduling_window_days': 3,
            'require_approval': True,
            'auto_schedule_on_import': False
        }

        # Merge with defaults
        for key, default_value in default_settings.items():
            if key not in settings:
                settings[key] = default_value

        return jsonify({
            'success': True,
            'settings': settings
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching auto-scheduler settings: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error fetching settings: {str(e)}'
        }), 500


def update_auto_scheduler_settings_endpoint():
    """
    Update auto-scheduler configuration settings.

    Request: PUT /api/auto-scheduler/settings
    Body: {
        "enabled_event_types": ["Core", "Juicer"],
        "scheduling_window_days": 3,
        "require_approval": true
    }

    Response: {
        "success": true,
        "message": "Settings updated successfully"
    }
    """
    SystemSetting = current_app.config['SystemSetting']

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'No settings provided'
            }), 400

        # Validate enabled_event_types if provided
        if 'enabled_event_types' in data:
            valid_types = ['Core', 'Juicer', 'Freeosk', 'Digitals', 'Supervisor', 'Other']
            enabled_types = data['enabled_event_types']

            if not isinstance(enabled_types, list):
                return jsonify({
                    'success': False,
                    'error': 'enabled_event_types must be an array'
                }), 400

            for event_type in enabled_types:
                if event_type not in valid_types:
                    return jsonify({
                        'success': False,
                        'error': f'Invalid event type: {event_type}'
                    }), 400

        # Get current settings
        current_settings_json = SystemSetting.get_setting('auto_scheduler_config', '{}')

        if isinstance(current_settings_json, str):
            current_settings = json.loads(current_settings_json)
        else:
            current_settings = current_settings_json

        # Update with new values
        current_settings.update(data)

        # Save back to database
        SystemSetting.set_setting(
            'auto_scheduler_config',
            json.dumps(current_settings),
            setting_type='string',
            user='admin',
            description='Auto-scheduler configuration settings'
        )

        logger.info(f"Updated auto-scheduler settings: {data}")

        return jsonify({
            'success': True,
            'message': 'Settings updated successfully',
            'settings': current_settings
        })

    except Exception as e:
        current_app.logger.error(f"Error updating auto-scheduler settings: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating settings: {str(e)}'
        }), 500


def get_event_scheduling_override_endpoint(event_id):
    """
    Get scheduling override for a specific event.

    Request: GET /api/events/<event_id>/scheduling-override

    Response: {
        "success": true,
        "event_id": 606034,
        "override": {
            "allow_auto_schedule": false,
            "reason": "VIP client - requires manual assignment",
            "set_by": "admin",
            "set_at": "2025-10-14T10:00:00"
        }
    }
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Event = models['Event']
    EventSchedulingOverride = current_app.config['EventSchedulingOverride']

    try:
        # Verify event exists
        event = Event.query.filter_by(project_ref_num=event_id).first()
        if not event:
            return jsonify({
                'success': False,
                'error': f'Event not found: {event_id}'
            }), 404

        # Get override if exists
        override = EventSchedulingOverride.query.filter_by(event_ref_num=event_id).first()

        if override:
            return jsonify({
                'success': True,
                'event_id': event_id,
                'has_override': True,
                'override': {
                    'allow_auto_schedule': override.allow_auto_schedule,
                    'reason': override.override_reason or '',
                    'set_by': override.set_by or '',
                    'set_at': override.set_at.isoformat()
                }
            })
        else:
            return jsonify({
                'success': True,
                'event_id': event_id,
                'has_override': False,
                'override': None
            })

    except Exception as e:
        current_app.logger.error(f"Error fetching event override: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error fetching override: {str(e)}'
        }), 500


def set_event_scheduling_override_endpoint():
    """
    Set or update scheduling override for a specific event.

    Request: POST /api/events/scheduling-override
    Body: {
        "event_id": 606034,
        "allow_auto_schedule": false,
        "reason": "VIP client - requires manual assignment"
    }

    Response: {
        "success": true,
        "message": "Override set successfully"
    }
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Event = models['Event']
    EventSchedulingOverride = current_app.config['EventSchedulingOverride']

    try:
        data = request.get_json()
        event_id = data.get('event_id')
        allow_auto_schedule = data.get('allow_auto_schedule', False)
        reason = data.get('reason', '')

        if not event_id:
            return jsonify({
                'success': False,
                'error': 'Missing required field: event_id'
            }), 400

        # Verify event exists
        event = Event.query.filter_by(project_ref_num=event_id).first()
        if not event:
            return jsonify({
                'success': False,
                'error': f'Event not found: {event_id}'
            }), 404

        # Get or create override
        override = EventSchedulingOverride.query.filter_by(event_ref_num=event_id).first()

        if override:
            # Update existing
            override.allow_auto_schedule = allow_auto_schedule
            override.override_reason = reason
            override.set_by = 'admin'  # TODO: Get from current user session
            message = 'Override updated successfully'
        else:
            # Create new
            override = EventSchedulingOverride(
                event_ref_num=event_id,
                allow_auto_schedule=allow_auto_schedule,
                override_reason=reason,
                set_by='admin'
            )
            db.session.add(override)
            message = 'Override created successfully'

        db.session.commit()

        logger.info(
            f"Set scheduling override for event {event_id}: "
            f"allow_auto_schedule={allow_auto_schedule}, reason={reason}"
        )

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting event override: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error setting override: {str(e)}'
        }), 500


def delete_event_scheduling_override_endpoint(event_id):
    """
    Delete scheduling override for a specific event.

    Request: DELETE /api/events/<event_id>/scheduling-override

    Response: {
        "success": true,
        "message": "Override deleted successfully"
    }
    """
    db = current_app.extensions['sqlalchemy']
    EventSchedulingOverride = current_app.config['EventSchedulingOverride']

    try:
        # Get override
        override = EventSchedulingOverride.query.filter_by(event_ref_num=event_id).first()

        if not override:
            return jsonify({
                'success': False,
                'error': f'Override not found for event: {event_id}'
            }), 404

        db.session.delete(override)
        db.session.commit()

        logger.info(f"Deleted scheduling override for event {event_id}")

        return jsonify({
            'success': True,
            'message': 'Override deleted successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting event override: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error deleting override: {str(e)}'
        }), 500


def register_auto_scheduler_settings_routes(api_bp):
    """
    Register auto-scheduler settings routes with the API blueprint.

    Add this to api.py:
    from .api_auto_scheduler_settings import register_auto_scheduler_settings_routes
    register_auto_scheduler_settings_routes(api_bp)
    """
    api_bp.add_url_rule('/auto-scheduler/settings', 'get_auto_scheduler_settings',
                        get_auto_scheduler_settings_endpoint, methods=['GET'])
    api_bp.add_url_rule('/auto-scheduler/settings', 'update_auto_scheduler_settings',
                        update_auto_scheduler_settings_endpoint, methods=['PUT'])
    api_bp.add_url_rule('/events/<int:event_id>/scheduling-override', 'get_event_scheduling_override',
                        get_event_scheduling_override_endpoint, methods=['GET'])
    api_bp.add_url_rule('/events/scheduling-override', 'set_event_scheduling_override',
                        set_event_scheduling_override_endpoint, methods=['POST'])
    api_bp.add_url_rule('/events/<int:event_id>/scheduling-override', 'delete_event_scheduling_override',
                        delete_event_scheduling_override_endpoint, methods=['DELETE'])
