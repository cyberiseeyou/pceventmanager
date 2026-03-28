"""
Schedule Change Notifications API Blueprint
Endpoints for listing, reading, and managing schedule change notifications
for specialists and leads.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from app.routes.auth import require_authentication, get_current_user
import logging

logger = logging.getLogger(__name__)

api_schedule_changes_bp = Blueprint('api_schedule_changes', __name__, url_prefix='/api/schedule-changes')


def init_schedule_change_routes(db, models):
    """Initialize schedule change notification routes with database and models."""
    ScheduleChangeNotification = models['ScheduleChangeNotification']

    @api_schedule_changes_bp.route('', methods=['GET'])
    @require_authentication()
    def get_my_notifications():
        """
        Get schedule change notifications for the current employee.

        Query params:
            unread_only (bool): Only return unread notifications
            limit (int): Max results (default 50)

        Returns:
            JSON with notifications list and unread_count
        """
        user = get_current_user()
        if not user:
            return jsonify({'notifications': [], 'unread_count': 0})

        employee_id = user.get('employee_id')
        role = user.get('role')
        if not employee_id or role not in ('specialist', 'lead'):
            return jsonify({'notifications': [], 'unread_count': 0})

        try:
            limit = request.args.get('limit', 50, type=int)
            unread_only = request.args.get('unread_only', 'false').lower() == 'true'

            query = ScheduleChangeNotification.query.filter_by(
                employee_id=employee_id
            )
            if unread_only:
                query = query.filter_by(is_read=False)

            notifications = query.order_by(
                ScheduleChangeNotification.created_at.desc()
            ).limit(limit).all()

            unread_count = ScheduleChangeNotification.query.filter_by(
                employee_id=employee_id,
                is_read=False,
            ).count()

            return jsonify({
                'notifications': [n.to_dict() for n in notifications],
                'unread_count': unread_count,
            })
        except Exception as e:
            logger.error(f"Error fetching schedule change notifications: {e}")
            return jsonify({'error': str(e)}), 500

    @api_schedule_changes_bp.route('/unread-count', methods=['GET'])
    @require_authentication()
    def get_unread_count():
        """
        Lightweight endpoint for badge polling (60s interval).
        Returns only the unread notification count.
        """
        user = get_current_user()
        if not user:
            return jsonify({'unread_count': 0})

        employee_id = user.get('employee_id')
        role = user.get('role')
        if not employee_id or role not in ('specialist', 'lead'):
            return jsonify({'unread_count': 0})

        try:
            count = ScheduleChangeNotification.query.filter_by(
                employee_id=employee_id,
                is_read=False,
            ).count()
            return jsonify({'unread_count': count})
        except Exception as e:
            logger.error(f"Error fetching unread count: {e}")
            return jsonify({'unread_count': 0})

    @api_schedule_changes_bp.route('/<int:notification_id>/read', methods=['POST'])
    @require_authentication()
    def mark_as_read(notification_id):
        """Mark a single notification as read."""
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401

        employee_id = user.get('employee_id')
        if not employee_id:
            return jsonify({'error': 'No employee ID'}), 400

        try:
            notif = ScheduleChangeNotification.query.filter_by(
                id=notification_id,
                employee_id=employee_id,
            ).first()
            if not notif:
                return jsonify({'error': 'Notification not found'}), 404

            notif.is_read = True
            notif.read_at = datetime.utcnow()
            db.session.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marking notification as read: {e}")
            return jsonify({'error': str(e)}), 500

    @api_schedule_changes_bp.route('/read-all', methods=['POST'])
    @require_authentication()
    def mark_all_as_read():
        """Mark all notifications as read for current employee."""
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401

        employee_id = user.get('employee_id')
        if not employee_id:
            return jsonify({'error': 'No employee ID'}), 400

        try:
            now = datetime.utcnow()
            ScheduleChangeNotification.query.filter_by(
                employee_id=employee_id,
                is_read=False,
            ).update({'is_read': True, 'read_at': now})
            db.session.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marking all notifications as read: {e}")
            return jsonify({'error': str(e)}), 500

    return api_schedule_changes_bp
