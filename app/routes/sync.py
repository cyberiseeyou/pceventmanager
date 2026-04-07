"""
Sync Dashboard Routes
Provides UI for viewing sync activity and resolving conflicts.
"""
from flask import Blueprint, render_template, jsonify, request
from app.routes.auth import require_authentication, get_current_user
from app.models import get_models, get_db
import logging

logger = logging.getLogger(__name__)

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')


@sync_bp.route('/changes')
@require_authentication()
def changes_page():
    """Activity feed of recent sync changes."""
    user = get_current_user()
    if not user or user.get('role') != 'supervisor':
        return 'Supervisor access required', 403

    models = get_models()
    SyncChangeLog = models['SyncChangeLog']

    page = request.args.get('page', 1, type=int)
    per_page = 50
    change_type = request.args.get('type')

    query = SyncChangeLog.query.order_by(SyncChangeLog.detected_at.desc())
    if change_type:
        query = query.filter_by(change_type=change_type)

    total = query.count()
    changes = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        'sync_changes.html',
        changes=changes,
        page=page,
        per_page=per_page,
        total=total,
        change_type=change_type,
    )


@sync_bp.route('/conflicts')
@require_authentication()
def conflicts_page():
    """Unresolved conflicts requiring investigation."""
    user = get_current_user()
    if not user or user.get('role') != 'supervisor':
        return 'Supervisor access required', 403

    models = get_models()
    SyncChangeLog = models['SyncChangeLog']

    show_resolved = request.args.get('show_resolved', 'false') == 'true'

    query = SyncChangeLog.query.filter_by(is_conflict=True)
    if not show_resolved:
        query = query.filter_by(resolved=False)

    conflicts = query.order_by(SyncChangeLog.detected_at.desc()).all()

    return render_template(
        'sync_conflicts.html',
        conflicts=conflicts,
        show_resolved=show_resolved,
    )


@sync_bp.route('/api/resolve/<int:log_id>', methods=['POST'])
@require_authentication()
def resolve_conflict(log_id):
    """Mark a conflict as resolved."""
    user = get_current_user()
    if not user or user.get('role') != 'supervisor':
        return jsonify({'error': 'Supervisor access required'}), 403

    models = get_models()
    db = get_db()
    SyncChangeLog = models['SyncChangeLog']

    log_entry = SyncChangeLog.query.get(log_id)
    if not log_entry:
        return jsonify({'error': 'Not found'}), 404

    from datetime import datetime
    data = request.get_json() or {}
    log_entry.resolved = True
    log_entry.resolved_at = datetime.utcnow()
    log_entry.resolution_notes = data.get('notes', '')

    db.session.commit()
    return jsonify({'status': 'success'})


@sync_bp.route('/api/status')
@require_authentication()
def sync_status():
    """Return daemon sync health info."""
    from app.services.sync_daemon import get_last_sync_time, is_daemon_healthy

    models = get_models()
    SystemSetting = models['SystemSetting']
    SyncChangeLog = models['SyncChangeLog']

    last_sync = get_last_sync_time()
    duration = SystemSetting.get_setting('last_sync_duration')
    unresolved = SyncChangeLog.query.filter_by(is_conflict=True, resolved=False).count()
    pending_changes = SyncChangeLog.query.filter_by(resolved=False).count()

    return jsonify({
        'healthy': is_daemon_healthy(),
        'last_sync': last_sync.isoformat() if last_sync else None,
        'duration': duration,
        'unresolved_conflicts': unresolved,
        'pending_changes': pending_changes,
    })
