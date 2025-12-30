"""AI RAG API endpoints - Local LLM with Ollama"""

from flask import Blueprint, request, jsonify, Response, stream_with_context, g
import logging

from .services.chat import SchedulerChatService
from .providers import ProviderFactory
from .config import ai_config
from app.extensions import db

logger = logging.getLogger(__name__)

# Use different name and prefix to coexist with existing ai_routes
ai_rag_bp = Blueprint('ai_rag', __name__, url_prefix='/api/ai/rag')


def get_chat_service() -> SchedulerChatService:
    """Get or create chat service for current request"""
    if 'chat_service' not in g:
        g.chat_service = SchedulerChatService(db.session)
    return g.chat_service


@ai_rag_bp.route('/health', methods=['GET'])
def health_check():
    """Check AI service health"""
    if not ai_config.enabled:
        return jsonify({
            "status": "disabled",
            "message": "AI features are disabled"
        }), 200

    try:
        health = ProviderFactory.health_check()

        status = "healthy" if health["primary"]["healthy"] else "unhealthy"
        status_code = 200 if health["primary"]["healthy"] else 503

        return jsonify({
            "status": status,
            "providers": health,
            "config": {
                "provider": ai_config.provider,
                "model": ai_config.ollama_model,
            }
        }), status_code
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 503


@ai_rag_bp.route('/chat', methods=['POST'])
def chat():
    """Process a chat message"""
    if not ai_config.enabled:
        return jsonify({
            "error": "AI features are disabled"
        }), 503

    data = request.get_json()

    if not data or 'message' not in data:
        return jsonify({
            "error": "Missing 'message' in request body"
        }), 400

    message = data['message'].strip()

    if not message:
        return jsonify({
            "error": "Message cannot be empty"
        }), 400

    if len(message) > 2000:
        return jsonify({
            "error": "Message too long (max 2000 characters)"
        }), 400

    service = get_chat_service()
    response = service.chat(message)

    return jsonify({
        "answer": response.answer,
        "metadata": {
            "query_type": response.query_type,
            "context_summary": response.context_summary,
            "confidence": response.confidence,
            "model": response.model_used,
            "processing_time_ms": response.processing_time_ms,
        },
        "error": response.error,
    })


@ai_rag_bp.route('/chat/stream', methods=['POST'])
def chat_stream():
    """Stream chat response"""
    if not ai_config.enabled:
        return jsonify({"error": "AI features are disabled"}), 503

    data = request.get_json()

    if not data or 'message' not in data:
        return jsonify({"error": "Missing 'message' in request body"}), 400

    message = data['message'].strip()
    service = get_chat_service()

    def generate():
        for chunk in service.chat_stream(message):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@ai_rag_bp.route('/chat/clear', methods=['POST'])
def clear_chat():
    """Clear conversation history"""
    service = get_chat_service()
    service.clear_history()

    return jsonify({
        "status": "success",
        "message": "Conversation history cleared"
    })


@ai_rag_bp.route('/suggestions', methods=['GET'])
def get_suggestions():
    """Get AI suggestions for current scheduling state"""
    if not ai_config.enabled:
        return jsonify({"error": "AI features are disabled"}), 503

    service = get_chat_service()

    # Generate proactive suggestions
    suggestions_prompt = """Review the current scheduling data and provide:
    1. Any potential conflicts or issues that need attention
    2. Employees who might be overworked this week
    3. Events that still need staff assignments
    4. General optimization suggestions

    Keep the response brief and actionable."""

    response = service.chat(suggestions_prompt)

    return jsonify({
        "suggestions": response.answer,
        "generated_at": response.processing_time_ms,
    })
