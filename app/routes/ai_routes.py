"""
AI Assistant API Routes

Handles natural language queries and AI assistant interactions
"""
from flask import Blueprint, request, jsonify, current_app, session
from app.routes.auth import require_authentication
from datetime import datetime
import logging

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')
logger = logging.getLogger(__name__)


@ai_bp.route('/query', methods=['POST'])
@require_authentication()
def process_query():
    """
    Process natural language query

    Request Body:
        {
            "query": "Verify tomorrow's schedule",
            "conversation_id": "optional-session-id",
            "history": [...],  # Optional conversation history
            "context": {...}   # Optional page context (e.g. current view info)
        }

    Returns:
        {
            "response": "Natural language response",
            "data": {...},
            "actions": [...],
            "requires_confirmation": bool,
            "confirmation_data": {...},
            "conversation_id": "session-id",
            "context_used": {...}
        }
    """
    try:
        data = request.get_json()
        query = data.get('query')
        conversation_id = data.get('conversation_id')
        history = data.get('history', [])
        page_context = data.get('context', {})

        if not query:
            return jsonify({'error': 'Missing query parameter'}), 400

        # Get AI provider settings from SystemSettings first, then config/environment
        SystemSetting = current_app.config.get('SystemSetting')
        if SystemSetting:
            provider = SystemSetting.get_setting('ai_provider') or current_app.config.get('AI_PROVIDER', 'gemini')
            api_key = SystemSetting.get_setting('ai_api_key') or current_app.config.get('AI_API_KEY')
        else:
            provider = current_app.config.get('AI_PROVIDER', 'gemini')
            api_key = current_app.config.get('AI_API_KEY')

        if not api_key:
            return jsonify({
                'error': 'AI assistant not configured. Please configure AI settings in Settings page or set AI_API_KEY in environment.'
            }), 503

        # Get database session and models
        from app.utils.db_helpers import get_models
        models = get_models()
        db = models['db']

        # Initialize AI assistant
        from app.services.ai_assistant import AIAssistant
        assistant = AIAssistant(
            provider=provider,
            api_key=api_key,
            db_session=db.session,
            models=models
        )

        # Process query with context
        result = assistant.process_query(query, history, context=page_context)

        # Store conversation in session if needed
        if not conversation_id:
            conversation_id = f"conv_{datetime.now().timestamp()}"

        # Build response
        response = {
            'response': result.response,
            'data': result.data,
            'actions': result.actions,
            'requires_confirmation': result.requires_confirmation,
            'confirmation_data': result.confirmation_data,
            'conversation_id': conversation_id,
            'context_used': result.context_used
        }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error processing AI query: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to process query',
            'details': str(e)
        }), 500


@ai_bp.route('/confirm', methods=['POST'])
@require_authentication()
def confirm_action():
    """
    Confirm and execute a pending action

    Request Body:
        {
            "confirmation_data": {...}
        }

    Returns:
        {
            "response": "Natural language response",
            "data": {...},
            "actions": [...]
        }
    """
    try:
        data = request.get_json()
        confirmation_data = data.get('confirmation_data')

        if not confirmation_data:
            return jsonify({'error': 'Missing confirmation_data'}), 400

        # Get AI provider settings from SystemSettings first, then config/environment
        SystemSetting = current_app.config.get('SystemSetting')
        if SystemSetting:
            provider = SystemSetting.get_setting('ai_provider') or current_app.config.get('AI_PROVIDER', 'openai')
            api_key = SystemSetting.get_setting('ai_api_key') or current_app.config.get('AI_API_KEY')
        else:
            provider = current_app.config.get('AI_PROVIDER', 'openai')
            api_key = current_app.config.get('AI_API_KEY')

        if not api_key:
            return jsonify({
                'error': 'AI assistant not configured. Please configure AI settings in Settings page or set AI_API_KEY in environment.'
            }), 503

        # Get database session and models
        from app.utils.db_helpers import get_models
        models = get_models()
        db = models['db']

        # Initialize AI assistant
        from app.services.ai_assistant import AIAssistant
        assistant = AIAssistant(
            provider=provider,
            api_key=api_key,
            db_session=db.session,
            models=models
        )

        # Execute confirmed action
        result = assistant.confirm_action(confirmation_data)

        response = {
            'response': result.response,
            'data': result.data,
            'actions': result.actions
        }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error confirming action: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to confirm action',
            'details': str(e)
        }), 500


@ai_bp.route('/suggestions', methods=['GET'])
@require_authentication()
def get_suggestions():
    """
    Get suggested queries/actions for the user

    Returns:
        {
            "suggestions": [
                {"label": "Verify tomorrow's schedule", "query": "verify schedule for tomorrow"},
                ...
            ]
        }
    """
    from datetime import date, timedelta

    tomorrow = date.today() + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%A')

    # Core suggestions - always shown
    core_suggestions = [
        {
            'label': f'Daily roster for {tomorrow_str}',
            'query': f'show daily roster for tomorrow',
            'icon': '📋',
            'category': 'daily'
        },
        {
            'label': f'Verify {tomorrow_str}\'s schedule',
            'query': 'verify schedule for tomorrow',
            'icon': '🔍',
            'category': 'daily'
        },
        {
            'label': 'Check overtime risk',
            'query': 'who is at risk for overtime this week',
            'icon': '⚠️',
            'category': 'analytics'
        },
        {
            'label': 'Urgent unscheduled events',
            'query': 'what events are due soon but not scheduled',
            'icon': '🚨',
            'category': 'events'
        },
        {
            'label': 'Check Lead coverage',
            'query': f'check lead coverage for tomorrow',
            'icon': '👥',
            'category': 'coverage'
        },
        {
            'label': 'Workload summary',
            'query': 'show workload summary for this week',
            'icon': '📊',
            'category': 'analytics'
        }
    ]

    # Additional suggestions based on context
    additional_suggestions = [
        {
            'label': f'Print {tomorrow_str}\'s paperwork',
            'query': 'print paperwork for tomorrow',
            'icon': '🖨️',
            'category': 'daily'
        },
        {
            'label': 'View rotation schedule',
            'query': 'show rotation schedule for this week',
            'icon': '🔄',
            'category': 'coverage'
        },
        {
            'label': 'Time-off requests',
            'query': 'show upcoming time off requests',
            'icon': '📅',
            'category': 'availability'
        },
        {
            'label': 'Scheduling rules',
            'query': 'what are the scheduling rules',
            'icon': '📚',
            'category': 'help'
        },
        {
            'label': 'Upcoming holidays',
            'query': 'what company holidays are coming up',
            'icon': '🎉',
            'category': 'company'
        },
        {
            'label': 'Unscheduled events',
            'query': 'list unscheduled events',
            'icon': '📌',
            'category': 'events'
        }
    ]

    # Combine and return top suggestions
    all_suggestions = core_suggestions + additional_suggestions

    return jsonify({'suggestions': all_suggestions}), 200


@ai_bp.route('/health', methods=['GET'])
def health_check():
    """
    Check if AI assistant is properly configured

    Returns:
        {
            "status": "ok" | "error",
            "provider": "openai" | "anthropic",
            "configured": bool
        }
    """
    provider = current_app.config.get('AI_PROVIDER', 'openai')
    api_key = current_app.config.get('AI_API_KEY')

    return jsonify({
        'status': 'ok' if api_key else 'error',
        'provider': provider,
        'configured': bool(api_key),
        'message': 'AI assistant ready' if api_key else 'AI_API_KEY not configured'
    }), 200


@ai_bp.route('/current-model', methods=['GET'])
@require_authentication()
def get_current_model():
    """
    Get the currently configured AI model/provider

    Returns:
        {
            "provider": "openai" | "anthropic" | "gemini",
            "configured": bool
        }
    """
    try:
        # Get AI provider settings from SystemSettings first, then config/environment
        SystemSetting = current_app.config.get('SystemSetting')
        if SystemSetting:
            provider = SystemSetting.get_setting('ai_provider') or current_app.config.get('AI_PROVIDER', 'openai')
            api_key = SystemSetting.get_setting('ai_api_key') or current_app.config.get('AI_API_KEY')
        else:
            provider = current_app.config.get('AI_PROVIDER', 'openai')
            api_key = current_app.config.get('AI_API_KEY')

        return jsonify({
            'provider': provider,
            'configured': bool(api_key)
        }), 200

    except Exception as e:
        logger.error(f"Error getting current model: {str(e)}")
        return jsonify({
            'provider': 'openai',
            'configured': False,
            'error': str(e)
        }), 500
