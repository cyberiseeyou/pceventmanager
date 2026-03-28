"""
Calloff API Blueprint
Endpoints for employee calloff submission and supervisor management.
"""
import os
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename

from app.routes.auth import require_authentication, require_role, get_current_user
from app.services.calloff_service import get_calloff_service

logger = logging.getLogger(__name__)

api_calloffs_bp = Blueprint('api_calloffs', __name__, url_prefix='/api/calloffs')

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'heic', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Employee Endpoints ──────────────────────────────────────────

@api_calloffs_bp.route('', methods=['POST'])
@require_authentication()
def submit_calloff():
    """Submit a calloff (specialist/lead only)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    role = user.get('role')
    if role not in ('specialist', 'lead'):
        return jsonify({'error': 'Only specialists and leads can submit calloffs'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    calloff_date = data.get('calloff_date')
    reason = data.get('reason')
    notes = data.get('notes')

    if not calloff_date or not reason:
        return jsonify({'error': 'calloff_date and reason are required'}), 400

    try:
        svc = get_calloff_service()
        result = svc.submit_calloff(
            employee_id=user.get('employee_id'),
            calloff_date=calloff_date,
            reason=reason,
            notes=notes,
        )
        return jsonify({'status': 'success', **result}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error submitting calloff: {e}", exc_info=True)
        return jsonify({'error': 'Failed to submit calloff'}), 500


@api_calloffs_bp.route('/my', methods=['GET'])
@require_authentication()
def my_calloffs():
    """Get the authenticated employee's calloff history."""
    user = get_current_user()
    if not user or not user.get('employee_id'):
        return jsonify({'error': 'Not authenticated'}), 401

    from app.models import get_models
    models = get_models()
    EmployeeCalloff = models['EmployeeCalloff']

    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    calloffs = EmployeeCalloff.query.filter_by(
        employee_id=user['employee_id']
    ).order_by(
        EmployeeCalloff.created_at.desc()
    ).offset(offset).limit(limit).all()

    return jsonify({
        'status': 'success',
        'calloffs': [c.to_dict() for c in calloffs],
    })


@api_calloffs_bp.route('/affected-events', methods=['GET'])
@require_authentication()
def affected_events():
    """Preview scheduled events that would be affected by a calloff on a given date."""
    user = get_current_user()
    if not user or not user.get('employee_id'):
        return jsonify({'error': 'Not authenticated'}), 401

    calloff_date = request.args.get('date')
    if not calloff_date:
        return jsonify({'error': 'date parameter required'}), 400

    try:
        svc = get_calloff_service()
        events = svc.get_affected_events(user['employee_id'], calloff_date)
        return jsonify({'status': 'success', 'events': events})
    except Exception as e:
        logger.error(f"Error fetching affected events: {e}")
        return jsonify({'error': str(e)}), 500


# ── Supervisor Endpoints ────────────────────────────────────────

@api_calloffs_bp.route('', methods=['GET'])
@require_authentication()
@require_role('supervisor')
def list_calloffs():
    """List all calloffs with optional filters."""
    from app.models import get_models
    from datetime import date, timedelta

    models = get_models()
    EmployeeCalloff = models['EmployeeCalloff']

    query = EmployeeCalloff.query

    # Filters
    employee_id = request.args.get('employee_id')
    if employee_id:
        query = query.filter_by(employee_id=employee_id)

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    reason = request.args.get('reason')
    if reason:
        query = query.filter_by(reason=reason)

    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(EmployeeCalloff.calloff_date >= date_from)

    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(EmployeeCalloff.calloff_date <= date_to)

    calloffs = query.order_by(EmployeeCalloff.created_at.desc()).all()

    # Enrich with pattern data
    svc = get_calloff_service()
    results = []
    for c in calloffs:
        data = c.to_dict(include_attachments=True)
        patterns = svc.check_patterns(c.employee_id)
        data['calloff_count_30d'] = patterns['count']
        data['pattern_alert'] = patterns['alert']
        # Affected events for pending calloffs
        if c.status == 'pending':
            data['affected_events'] = svc.get_affected_events(c.employee_id, c.calloff_date)
        results.append(data)

    return jsonify({'status': 'success', 'calloffs': results})


@api_calloffs_bp.route('/<int:calloff_id>', methods=['GET'])
@require_authentication()
@require_role('supervisor')
def get_calloff(calloff_id):
    """Get a single calloff with attachments and pattern data."""
    from app.models import get_models
    models = get_models()
    EmployeeCalloff = models['EmployeeCalloff']

    calloff = EmployeeCalloff.query.get(calloff_id)
    if not calloff:
        return jsonify({'error': 'Calloff not found'}), 404

    svc = get_calloff_service()
    data = calloff.to_dict(include_attachments=True)
    data['patterns'] = svc.check_patterns(calloff.employee_id)
    data['affected_events'] = svc.get_affected_events(calloff.employee_id, calloff.calloff_date)

    return jsonify({'status': 'success', 'calloff': data})


@api_calloffs_bp.route('/<int:calloff_id>/review', methods=['PUT'])
@require_authentication()
@require_role('supervisor')
def review_calloff(calloff_id):
    """Mark a calloff as excused or unexcused."""
    user = get_current_user()
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'error': 'status is required (excused or unexcused)'}), 400

    try:
        svc = get_calloff_service()
        result = svc.review_calloff(
            calloff_id=calloff_id,
            status=data['status'],
            supervisor_name=user.get('username', 'Supervisor'),
            comments=data.get('supervisor_comments'),
        )
        return jsonify({'status': 'success', 'calloff': result})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error reviewing calloff: {e}", exc_info=True)
        return jsonify({'error': 'Failed to review calloff'}), 500


@api_calloffs_bp.route('/<int:calloff_id>/resolve', methods=['POST'])
@require_authentication()
@require_role('supervisor')
def resolve_calloff(calloff_id):
    """Unschedule events affected by a calloff."""
    data = request.get_json() or {}
    action = data.get('action', 'unschedule_all')
    schedule_ids = data.get('schedule_ids')

    try:
        svc = get_calloff_service()
        result = svc.resolve_calloff_events(calloff_id, action, schedule_ids)
        return jsonify({'status': 'success', **result})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error resolving calloff: {e}", exc_info=True)
        return jsonify({'error': 'Failed to resolve calloff events'}), 500


# ── Attachments ─────────────────────────────────────────────────

@api_calloffs_bp.route('/<int:calloff_id>/attachments', methods=['POST'])
@require_authentication()
@require_role('supervisor')
def upload_attachment(calloff_id):
    """Upload a file attachment to a calloff."""
    from app.models import get_models, get_db
    models = get_models()
    db = get_db()
    EmployeeCalloff = models['EmployeeCalloff']
    CalloffAttachment = models['CalloffAttachment']

    calloff = EmployeeCalloff.query.get(calloff_id)
    if not calloff:
        return jsonify({'error': 'Calloff not found'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    if not _allowed_file(file.filename):
        return jsonify({'error': f'File type not allowed. Accepted: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'error': 'File exceeds 10 MB limit'}), 400

    # Build storage path
    upload_root = current_app.config.get('CALLOFF_UPLOAD_FOLDER', 'uploads/calloffs')
    month_dir = calloff.calloff_date.strftime('%Y-%m')
    upload_dir = os.path.join(upload_root, month_dir, str(calloff_id))
    os.makedirs(upload_dir, exist_ok=True)

    # Secure filename with timestamp prefix
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    safe_name = secure_filename(file.filename)
    stored_name = f"{timestamp}_{safe_name}"
    file_path = os.path.join(upload_dir, stored_name)
    file.save(file_path)

    user = get_current_user()
    attachment = CalloffAttachment(
        calloff_id=calloff_id,
        filename=file.filename,
        file_path=file_path,
        file_type=file.content_type,
        uploaded_by=user.get('username', 'Supervisor'),
    )
    db.session.add(attachment)
    db.session.commit()

    return jsonify({'status': 'success', 'attachment': attachment.to_dict()}), 201


@api_calloffs_bp.route('/<int:calloff_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@require_authentication()
@require_role('supervisor')
def delete_attachment(calloff_id, attachment_id):
    """Delete an attachment from a calloff."""
    from app.models import get_models, get_db
    models = get_models()
    db = get_db()
    CalloffAttachment = models['CalloffAttachment']

    attachment = CalloffAttachment.query.filter_by(
        id=attachment_id, calloff_id=calloff_id
    ).first()
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    # Remove file from disk
    if os.path.exists(attachment.file_path):
        os.remove(attachment.file_path)

    db.session.delete(attachment)
    db.session.commit()

    return jsonify({'status': 'success'})


@api_calloffs_bp.route('/<int:calloff_id>/attachments/<int:attachment_id>/download', methods=['GET'])
@require_authentication()
@require_role('supervisor')
def download_attachment(calloff_id, attachment_id):
    """Download an attachment file."""
    from app.models import get_models
    models = get_models()
    CalloffAttachment = models['CalloffAttachment']

    attachment = CalloffAttachment.query.filter_by(
        id=attachment_id, calloff_id=calloff_id
    ).first()
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    if not os.path.exists(attachment.file_path):
        return jsonify({'error': 'File not found on disk'}), 404

    return send_file(
        attachment.file_path,
        download_name=attachment.filename,
        as_attachment=True,
    )


# ── Patterns ────────────────────────────────────────────────────

@api_calloffs_bp.route('/patterns', methods=['GET'])
@require_authentication()
@require_role('supervisor')
def calloff_patterns():
    """Get calloff patterns and alerts for all employees."""
    days = request.args.get('days', 30, type=int)
    if days not in (30, 60, 90):
        days = 30

    svc = get_calloff_service()
    result = svc.get_all_patterns(window_days=days)
    return jsonify({'status': 'success', **result})


# ── SMS Resend ──────────────────────────────────────────────────

@api_calloffs_bp.route('/<int:calloff_id>/notify-sms', methods=['POST'])
@require_authentication()
@require_role('supervisor')
def resend_sms(calloff_id):
    """Resend SMS notification for a calloff (behind feature flag)."""
    from app.models import get_models
    from app.services.sms_service import send_calloff_sms
    models = get_models()
    EmployeeCalloff = models['EmployeeCalloff']
    Employee = models['Employee']

    calloff = EmployeeCalloff.query.get(calloff_id)
    if not calloff:
        return jsonify({'error': 'Calloff not found'}), 404

    employee = Employee.query.get(calloff.employee_id)
    svc = get_calloff_service()
    affected = svc.get_affected_events(calloff.employee_id, calloff.calloff_date)

    try:
        send_calloff_sms(
            employee_name=employee.name if employee else 'Unknown',
            calloff_date=calloff.calloff_date,
            reason=calloff.REASON_LABELS.get(calloff.reason, calloff.reason),
            affected_count=len(affected),
        )
        return jsonify({'status': 'success', 'message': 'SMS sent'})
    except Exception as e:
        return jsonify({'error': f'SMS failed: {str(e)}'}), 500
