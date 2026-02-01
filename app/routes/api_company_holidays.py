"""
Company Holidays API Routes
Manages company-wide holidays/closed days
"""
from flask import Blueprint, request, jsonify, current_app
from app.models import get_models
from datetime import datetime, date
from app.routes.auth import require_authentication

api_company_holidays_bp = Blueprint('api_company_holidays', __name__, url_prefix='/api/company-holidays')


@api_company_holidays_bp.route('/', methods=['GET'])
@require_authentication()
def get_holidays():
    """Get all company holidays"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        # Get query parameters
        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
        year = request.args.get('year', type=int)

        query = db.session.query(CompanyHoliday)

        if not include_inactive:
            query = query.filter(CompanyHoliday.is_active == True)

        if year:
            # Filter by year
            start_of_year = date(year, 1, 1)
            end_of_year = date(year, 12, 31)
            query = query.filter(
                CompanyHoliday.holiday_date >= start_of_year,
                CompanyHoliday.holiday_date <= end_of_year
            )

        holidays = query.order_by(CompanyHoliday.holiday_date).all()

        return jsonify({
            'success': True,
            'holidays': [h.to_dict() for h in holidays]
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching holidays: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/', methods=['POST'])
@require_authentication()
def create_holiday():
    """Create a new company holiday"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        data = request.get_json()

        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Holiday name is required'}), 400

        if not data.get('holiday_date'):
            return jsonify({'success': False, 'error': 'Holiday date is required'}), 400

        # Parse date
        try:
            holiday_date = datetime.strptime(data['holiday_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Check for duplicate
        existing = db.session.query(CompanyHoliday).filter(
            CompanyHoliday.holiday_date == holiday_date,
            CompanyHoliday.name == data['name']
        ).first()

        if existing:
            return jsonify({
                'success': False,
                'error': f"Holiday '{data['name']}' already exists for {holiday_date}"
            }), 409

        # Create holiday
        holiday = CompanyHoliday(
            name=data['name'],
            holiday_date=holiday_date,
            is_recurring=data.get('is_recurring', False),
            recurring_month=holiday_date.month if data.get('is_recurring') else None,
            recurring_day=holiday_date.day if data.get('is_recurring') else None,
            recurring_rule=data.get('recurring_rule'),
            notes=data.get('notes'),
            is_active=True
        )

        db.session.add(holiday)
        db.session.commit()

        current_app.logger.info(f"Created company holiday: {holiday.name} on {holiday.holiday_date}")

        return jsonify({
            'success': True,
            'holiday': holiday.to_dict(),
            'message': f"Holiday '{holiday.name}' created successfully"
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating holiday: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/<int:holiday_id>', methods=['GET'])
@require_authentication()
def get_holiday(holiday_id):
    """Get a specific holiday"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        holiday = db.session.query(CompanyHoliday).get(holiday_id)

        if not holiday:
            return jsonify({'success': False, 'error': 'Holiday not found'}), 404

        return jsonify({
            'success': True,
            'holiday': holiday.to_dict()
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching holiday: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/<int:holiday_id>', methods=['PUT'])
@require_authentication()
def update_holiday(holiday_id):
    """Update a company holiday"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        holiday = db.session.query(CompanyHoliday).get(holiday_id)

        if not holiday:
            return jsonify({'success': False, 'error': 'Holiday not found'}), 404

        data = request.get_json()

        if 'name' in data:
            holiday.name = data['name']

        if 'holiday_date' in data:
            try:
                holiday.holiday_date = datetime.strptime(data['holiday_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        if 'is_recurring' in data:
            holiday.is_recurring = data['is_recurring']
            if data['is_recurring'] and holiday.holiday_date:
                holiday.recurring_month = holiday.holiday_date.month
                holiday.recurring_day = holiday.holiday_date.day
            else:
                holiday.recurring_month = None
                holiday.recurring_day = None

        if 'recurring_rule' in data:
            holiday.recurring_rule = data['recurring_rule']

        if 'notes' in data:
            holiday.notes = data['notes']

        if 'is_active' in data:
            holiday.is_active = data['is_active']

        db.session.commit()

        current_app.logger.info(f"Updated company holiday: {holiday.name}")

        return jsonify({
            'success': True,
            'holiday': holiday.to_dict(),
            'message': f"Holiday '{holiday.name}' updated successfully"
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating holiday: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/<int:holiday_id>', methods=['DELETE'])
@require_authentication()
def delete_holiday(holiday_id):
    """Delete a company holiday"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        holiday = db.session.query(CompanyHoliday).get(holiday_id)

        if not holiday:
            return jsonify({'success': False, 'error': 'Holiday not found'}), 404

        name = holiday.name
        db.session.delete(holiday)
        db.session.commit()

        current_app.logger.info(f"Deleted company holiday: {name}")

        return jsonify({
            'success': True,
            'message': f"Holiday '{name}' deleted successfully"
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting holiday: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/check', methods=['GET'])
@require_authentication()
def check_holiday():
    """Check if a specific date is a holiday"""
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({'success': False, 'error': 'Date parameter required'}), 400

        try:
            check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        holiday = CompanyHoliday.is_holiday(check_date)

        return jsonify({
            'success': True,
            'date': check_date.isoformat(),
            'is_holiday': holiday is not None,
            'holiday': holiday.to_dict() if holiday else None
        })

    except Exception as e:
        current_app.logger.error(f"Error checking holiday: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/upcoming', methods=['GET'])
@require_authentication()
def get_upcoming_holidays():
    """Get upcoming holidays"""
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        days_ahead = request.args.get('days', 30, type=int)
        holidays = CompanyHoliday.get_upcoming_holidays(days_ahead)

        return jsonify({
            'success': True,
            'holidays': [h.to_dict() for h in holidays]
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching upcoming holidays: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_company_holidays_bp.route('/range', methods=['GET'])
@require_authentication()
def get_holidays_in_range():
    """Get all holiday dates in a range"""
    models = get_models()
    CompanyHoliday = models['CompanyHoliday']

    try:
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')

        if not start_str or not end_str:
            return jsonify({'success': False, 'error': 'start_date and end_date required'}), 400

        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        holiday_dates = CompanyHoliday.get_holidays_in_range(start_date, end_date)

        return jsonify({
            'success': True,
            'holiday_dates': [d.isoformat() for d in holiday_dates]
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching holidays in range: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
