"""
Push Subscription API Blueprint
Endpoints for managing Web Push API subscriptions.
"""
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import require_authentication, get_current_user
import logging

logger = logging.getLogger(__name__)

api_push_bp = Blueprint('api_push', __name__, url_prefix='/api/push')


def init_push_routes(db, models):
    """Initialize push subscription routes with database and models."""
    PushSubscription = models['PushSubscription']

    @api_push_bp.route('/subscribe', methods=['POST'])
    @require_authentication()
    def subscribe():
        """
        Store a push subscription for the current employee.
        Expects Web Push subscription JSON from pushManager.subscribe().
        """
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401

        employee_id = user.get('employee_id')
        role = user.get('role')
        if not employee_id or role not in ('specialist', 'lead'):
            return jsonify({'error': 'Push notifications not available for this role'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No subscription data provided'}), 400

        endpoint = data.get('endpoint')
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')

        if not endpoint or not p256dh or not auth:
            return jsonify({'error': 'Missing subscription fields (endpoint, keys.p256dh, keys.auth)'}), 400

        try:
            # Upsert: update existing subscription or create new one
            existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
            if existing:
                existing.employee_id = employee_id
                existing.p256dh_key = p256dh
                existing.auth_key = auth
                existing.is_active = True
                existing.user_agent = request.headers.get('User-Agent', '')[:500]
            else:
                sub = PushSubscription(
                    employee_id=employee_id,
                    endpoint=endpoint,
                    p256dh_key=p256dh,
                    auth_key=auth,
                    user_agent=request.headers.get('User-Agent', '')[:500],
                )
                db.session.add(sub)

            db.session.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving push subscription: {e}")
            return jsonify({'error': str(e)}), 500

    @api_push_bp.route('/unsubscribe', methods=['POST'])
    @require_authentication()
    def unsubscribe():
        """Deactivate a push subscription by endpoint."""
        data = request.get_json()
        if not data or not data.get('endpoint'):
            return jsonify({'error': 'Missing endpoint'}), 400

        try:
            sub = PushSubscription.query.filter_by(
                endpoint=data['endpoint']
            ).first()
            if sub:
                sub.is_active = False
                db.session.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deactivating push subscription: {e}")
            return jsonify({'error': str(e)}), 500

    @api_push_bp.route('/vapid-public-key', methods=['GET'])
    @require_authentication()
    def get_vapid_public_key():
        """Return the VAPID public key for client-side subscription."""
        public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        if not public_key:
            return jsonify({'error': 'VAPID not configured'}), 503
        return jsonify({'public_key': public_key})

    return api_push_bp
