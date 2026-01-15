"""
API endpoints for managing locked days.

Locked days prevent any schedule modifications for that date,
ensuring finalized schedules (with printed paperwork) aren't accidentally changed.
"""
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, date

api_locked_days_bp = Blueprint('api_locked_days', __name__, url_prefix='/api/locked-days')


def get_locked_day_model():
    """Get the LockedDay model from app config"""
    return current_app.config.get('LockedDay')


@api_locked_days_bp.route('', methods=['GET'])
def list_locked_days():
    """
    List all locked days

    Query params:
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
    """
    LockedDay = get_locked_day_model()
    if not LockedDay:
        return jsonify({'success': False, 'error': 'LockedDay model not available'}), 500

    try:
        query = LockedDay.query.order_by(LockedDay.locked_date)

        # Apply date filters if provided
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(LockedDay.locked_date >= start)

        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(LockedDay.locked_date <= end)

        locked_days = query.all()

        return jsonify({
            'success': True,
            'locked_days': [{
                'id': ld.id,
                'date': ld.locked_date.isoformat(),
                'locked_at': ld.locked_at.isoformat() if ld.locked_at else None,
                'locked_by': ld.locked_by,
                'reason': ld.reason
            } for ld in locked_days]
        })
    except Exception as e:
        current_app.logger.error(f"Error listing locked days: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_locked_days_bp.route('/<date_str>', methods=['GET'])
def check_locked_day(date_str):
    """
    Check if a specific date is locked

    Args:
        date_str: Date in YYYY-MM-DD format
    """
    LockedDay = get_locked_day_model()
    if not LockedDay:
        return jsonify({'success': False, 'error': 'LockedDay model not available'}), 500

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        locked_day = LockedDay.get_locked_day(target_date)

        if locked_day:
            return jsonify({
                'success': True,
                'is_locked': True,
                'locked_day': {
                    'id': locked_day.id,
                    'date': locked_day.locked_date.isoformat(),
                    'locked_at': locked_day.locked_at.isoformat() if locked_day.locked_at else None,
                    'locked_by': locked_day.locked_by,
                    'reason': locked_day.reason
                }
            })
        else:
            return jsonify({
                'success': True,
                'is_locked': False
            })
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        current_app.logger.error(f"Error checking locked day: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_locked_days_bp.route('', methods=['POST'])
def lock_day():
    """
    Lock a specific date

    Request body:
        date: Date to lock (YYYY-MM-DD)
        reason: Optional reason for locking
    """
    from app.extensions import db

    LockedDay = get_locked_day_model()
    if not LockedDay:
        return jsonify({'success': False, 'error': 'LockedDay model not available'}), 500

    try:
        data = request.get_json()

        if not data or not data.get('date'):
            return jsonify({'success': False, 'error': 'Date is required'}), 400

        target_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        reason = data.get('reason')
        locked_by = data.get('locked_by', 'System')  # Could get from session/auth

        # Check if already locked
        existing = LockedDay.get_locked_day(target_date)
        if existing:
            return jsonify({
                'success': False,
                'error': f'Date {target_date} is already locked',
                'locked_day': {
                    'id': existing.id,
                    'date': existing.locked_date.isoformat(),
                    'locked_at': existing.locked_at.isoformat() if existing.locked_at else None,
                    'locked_by': existing.locked_by,
                    'reason': existing.reason
                }
            }), 409  # Conflict

        # Lock the day
        locked_day = LockedDay.lock_day(target_date, locked_by=locked_by, reason=reason)
        db.session.commit()

        current_app.logger.info(f"Locked day {target_date} by {locked_by}: {reason}")

        return jsonify({
            'success': True,
            'message': f'Day {target_date} has been locked',
            'locked_day': {
                'id': locked_day.id,
                'date': locked_day.locked_date.isoformat(),
                'locked_at': locked_day.locked_at.isoformat() if locked_day.locked_at else None,
                'locked_by': locked_day.locked_by,
                'reason': locked_day.reason
            }
        })
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error locking day: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_locked_days_bp.route('/<date_str>', methods=['DELETE'])
def unlock_day(date_str):
    """
    Unlock a specific date

    Args:
        date_str: Date to unlock in YYYY-MM-DD format
    """
    from app.extensions import db

    LockedDay = get_locked_day_model()
    if not LockedDay:
        return jsonify({'success': False, 'error': 'LockedDay model not available'}), 500

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Check if locked
        locked_day = LockedDay.get_locked_day(target_date)
        if not locked_day:
            return jsonify({
                'success': False,
                'error': f'Date {target_date} is not locked'
            }), 404

        # Unlock the day
        LockedDay.unlock_day(target_date)
        db.session.commit()

        current_app.logger.info(f"Unlocked day {target_date}")

        return jsonify({
            'success': True,
            'message': f'Day {target_date} has been unlocked'
        })
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error unlocking day: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_locked_days_bp.route('/check-range', methods=['POST'])
def check_locked_range():
    """
    Check which days in a date range are locked

    Request body:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of locked dates in the range
    """
    LockedDay = get_locked_day_model()
    if not LockedDay:
        return jsonify({'success': False, 'error': 'LockedDay model not available'}), 500

    try:
        data = request.get_json()

        if not data or not data.get('start_date') or not data.get('end_date'):
            return jsonify({'success': False, 'error': 'start_date and end_date are required'}), 400

        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

        locked_days = LockedDay.query.filter(
            LockedDay.locked_date >= start_date,
            LockedDay.locked_date <= end_date
        ).order_by(LockedDay.locked_date).all()

        return jsonify({
            'success': True,
            'locked_dates': [ld.locked_date.isoformat() for ld in locked_days],
            'locked_days': [{
                'id': ld.id,
                'date': ld.locked_date.isoformat(),
                'locked_at': ld.locked_at.isoformat() if ld.locked_at else None,
                'locked_by': ld.locked_by,
                'reason': ld.reason
            } for ld in locked_days]
        })
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        current_app.logger.error(f"Error checking locked range: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# Helper function for other modules to check locked days
def is_day_locked(target_date):
    """
    Helper function to check if a day is locked.
    Can be imported by other modules.

    Args:
        target_date: datetime or date object

    Returns:
        True if locked, False otherwise
    """
    LockedDay = get_locked_day_model()
    if not LockedDay:
        return False
    return LockedDay.is_day_locked(target_date)


def get_locked_day_info(target_date):
    """
    Helper function to get locked day info.
    Can be imported by other modules.

    Args:
        target_date: datetime or date object

    Returns:
        LockedDay object if locked, None otherwise
    """
    LockedDay = get_locked_day_model()
    if not LockedDay:
        return None
    return LockedDay.get_locked_day(target_date)
