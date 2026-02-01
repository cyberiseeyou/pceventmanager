"""
Employee Availability Override API Endpoints
FR32: Scenario 2 - Temporary Availability Change

These endpoints should be added to api.py or imported into the api blueprint.
"""
from flask import request, jsonify, current_app
from app.models import get_models
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


def create_availability_override_endpoint():
    """
    Create a new temporary availability override for an employee.

    Request: POST /api/availability-overrides
    Body: {
        "employee_id": "EMP001",
        "start_date": "2025-10-15",
        "end_date": "2025-11-04",
        "monday": false,
        "tuesday": true,
        "wednesday": false,
        "thursday": true,
        "friday": false,
        "saturday": null,
        "sunday": null,
        "reason": "College class schedule"
    }
    """
    db = current_app.extensions['sqlalchemy']
    EmployeeAvailabilityOverride = current_app.config['EmployeeAvailabilityOverride']
    models = get_models()
    Employee = models['Employee']

    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        reason = data.get('reason', '')

        if not employee_id or not start_date_str or not end_date_str:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: employee_id, start_date, end_date'
            }), 400

        employee = db.session.get(Employee, employee_id)
        if not employee:
            return jsonify({'success': False, 'error': f'Employee not found: {employee_id}'}), 404

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        if end_date < start_date:
            return jsonify({'success': False, 'error': 'End date must be after or equal to start date'}), 400

        override = EmployeeAvailabilityOverride(
            employee_id=employee_id,
            start_date=start_date,
            end_date=end_date,
            monday=data.get('monday'),
            tuesday=data.get('tuesday'),
            wednesday=data.get('wednesday'),
            thursday=data.get('thursday'),
            friday=data.get('friday'),
            saturday=data.get('saturday'),
            sunday=data.get('sunday'),
            reason=reason,
            created_by='admin'
        )

        db.session.add(override)
        db.session.commit()

        logger.info(f"Created availability override for employee {employee_id} from {start_date} to {end_date}")

        return jsonify({
            'success': True,
            'override_id': override.id,
            'message': 'Availability override created successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating availability override: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Error creating override: {str(e)}'}), 500


def get_availability_overrides_endpoint(employee_id):
    """
    Get all availability overrides for an employee.

    Request: GET /api/availability-overrides/EMP001?include_expired=false
    """
    db = current_app.extensions['sqlalchemy']
    EmployeeAvailabilityOverride = current_app.config['EmployeeAvailabilityOverride']
    models = get_models()
    Employee = models['Employee']

    try:
        employee = db.session.get(Employee, employee_id)
        if not employee:
            return jsonify({'success': False, 'error': f'Employee not found: {employee_id}'}), 404

        include_expired = request.args.get('include_expired', 'false').lower() == 'true'

        query = EmployeeAvailabilityOverride.query.filter_by(employee_id=employee_id)

        if not include_expired:
            today = date.today()
            query = query.filter(EmployeeAvailabilityOverride.end_date >= today)

        overrides = query.order_by(EmployeeAvailabilityOverride.start_date).all()

        formatted_overrides = []
        for override in overrides:
            formatted_overrides.append({
                'id': override.id,
                'start_date': override.start_date.strftime('%Y-%m-%d'),
                'end_date': override.end_date.strftime('%Y-%m-%d'),
                'monday': override.monday,
                'tuesday': override.tuesday,
                'wednesday': override.wednesday,
                'thursday': override.thursday,
                'friday': override.friday,
                'saturday': override.saturday,
                'sunday': override.sunday,
                'reason': override.reason or '',
                'is_active': override.is_active(),
                'created_at': override.created_at.isoformat()
            })

        return jsonify({
            'success': True,
            'employee_id': employee_id,
            'employee_name': employee.name,
            'overrides': formatted_overrides
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching availability overrides: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Error fetching overrides: {str(e)}'}), 500


def update_availability_override_endpoint(override_id):
    """
    Update an existing availability override.

    Request: PUT /api/availability-overrides/123
    """
    db = current_app.extensions['sqlalchemy']
    EmployeeAvailabilityOverride = current_app.config['EmployeeAvailabilityOverride']

    try:
        override = db.session.get(EmployeeAvailabilityOverride, override_id)
        if not override:
            return jsonify({'success': False, 'error': f'Override not found: {override_id}'}), 404

        data = request.get_json()

        if 'start_date' in data:
            try:
                override.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid start_date format. Use YYYY-MM-DD.'}), 400

        if 'end_date' in data:
            try:
                override.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid end_date format. Use YYYY-MM-DD.'}), 400

        if override.end_date < override.start_date:
            return jsonify({'success': False, 'error': 'End date must be after or equal to start date'}), 400

        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            if day in data:
                setattr(override, day, data[day])

        if 'reason' in data:
            override.reason = data['reason']

        db.session.commit()

        logger.info(f"Updated availability override {override_id}")

        return jsonify({'success': True, 'message': 'Availability override updated successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating availability override: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Error updating override: {str(e)}'}), 500


def delete_availability_override_endpoint(override_id):
    """
    Delete an availability override.

    Request: DELETE /api/availability-overrides/123
    """
    db = current_app.extensions['sqlalchemy']
    EmployeeAvailabilityOverride = current_app.config['EmployeeAvailabilityOverride']

    try:
        override = db.session.get(EmployeeAvailabilityOverride, override_id)
        if not override:
            return jsonify({'success': False, 'error': f'Override not found: {override_id}'}), 404

        db.session.delete(override)
        db.session.commit()

        logger.info(f"Deleted availability override {override_id}")

        return jsonify({'success': True, 'message': 'Availability override deleted successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting availability override: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Error deleting override: {str(e)}'}), 500


def register_availability_override_routes(api_bp):
    """
    Register availability override routes with the API blueprint.

    Add this to api.py:
    from .api_availability_overrides import register_availability_override_routes
    register_availability_override_routes(api_bp)
    """
    api_bp.add_url_rule('/availability-overrides', 'create_availability_override',
                        create_availability_override_endpoint, methods=['POST'])
    api_bp.add_url_rule('/availability-overrides/<employee_id>', 'get_availability_overrides',
                        get_availability_overrides_endpoint, methods=['GET'])
    api_bp.add_url_rule('/availability-overrides/<int:override_id>', 'update_availability_override',
                        update_availability_override_endpoint, methods=['PUT'])
    api_bp.add_url_rule('/availability-overrides/<int:override_id>', 'delete_availability_override',
                        delete_availability_override_endpoint, methods=['DELETE'])
