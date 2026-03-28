"""
Demo Goals API Blueprint

Endpoints for fetching and downloading Sam's Club demo goals.
"""
import logging

from flask import Blueprint, request, jsonify, make_response, current_app
from app.models import get_models

logger = logging.getLogger(__name__)

api_demo_goals_bp = Blueprint('api_demo_goals', __name__, url_prefix='/api')


def _resolve_club_number():
    """Get club_number from query param, falling back to SystemSetting."""
    club_number = request.args.get('club_number', '').strip()
    if not club_number:
        try:
            models = get_models()
            SystemSetting = models.get('SystemSetting')
            if SystemSetting:
                club_number = SystemSetting.get_setting('club_number', '') or ''
        except Exception:
            pass
    return club_number


@api_demo_goals_bp.route('/demo-goals/data', methods=['GET'])
def get_demo_goals_data():
    """
    Return demo goals as JSON for in-browser display.

    Query params:
        club_number (optional): Falls back to SystemSetting
    """
    club_number = _resolve_club_number()
    if not club_number:
        return jsonify({
            'status': 'error',
            'error': 'club_number parameter is required'
        }), 400

    try:
        from app.services.demo_goals_service import fetch_demo_goals
        timeout = current_app.config.get('EXTERNAL_API_TIMEOUT', 30)
        rows = fetch_demo_goals(club_number, timeout=timeout)

        return jsonify({
            'status': 'success',
            'data': rows,
            'club_number': club_number,
        })

    except Exception:
        logger.exception('Failed to fetch demo goals for club %s', club_number)
        return jsonify({
            'status': 'error',
            'error': 'Failed to fetch demo goals. Please try again later.'
        }), 500


@api_demo_goals_bp.route('/demo-goals/download', methods=['GET'])
def download_demo_goals():
    """
    Download demo goals Excel file for a given club number.

    Query params:
        club_number (required): The Sam's Club number to filter by
    """
    club_number = _resolve_club_number()
    if not club_number:
        return jsonify({
            'status': 'error',
            'error': 'club_number parameter is required'
        }), 400

    try:
        from app.services.demo_goals_service import get_demo_goals_excel
        timeout = current_app.config.get('EXTERNAL_API_TIMEOUT', 30)
        excel_bytes, filename = get_demo_goals_excel(club_number, timeout=timeout)

        response = make_response(excel_bytes)
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception:
        logger.exception('Failed to generate demo goals Excel for club %s', club_number)
        return jsonify({
            'status': 'error',
            'error': 'Failed to fetch demo goals. Please try again later.'
        }), 500
