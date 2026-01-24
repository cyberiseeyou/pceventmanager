"""
Rotation management routes
Handles weekly rotation assignments for Juicers and Primary Leads
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from app.services.rotation_manager import RotationManager

rotations_bp = Blueprint('rotations', __name__, url_prefix='/rotations')


@rotations_bp.route('/')
def index():
    """Render rotation assignments page"""
    db = current_app.extensions['sqlalchemy']
    models = {
        'RotationAssignment': current_app.config['RotationAssignment'],
        'ScheduleException': current_app.config['ScheduleException'],
        'Employee': current_app.config['Employee']
    }

    rotation_mgr = RotationManager(db.session, models)

    # Get current rotations
    rotations = rotation_mgr.get_all_rotations()

    # Get all employees for dropdowns
    Employee = current_app.config['Employee']
    all_employees = db.session.query(Employee).order_by(Employee.name).all()

    # Filter employees by role for dropdowns
    # Include Juicer Baristas and employees marked as Juicer Trained
    juicers = [e for e in all_employees if e.job_title == 'Juicer Barista' or e.juicer_trained]
    leads = [e for e in all_employees if e.job_title in ['Lead Event Specialist', 'Club Supervisor']]

    return render_template('rotations.html',
                         rotations=rotations,
                         juicers=juicers,
                         leads=leads,
                         day_names=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])


@rotations_bp.route('/api/rotations', methods=['GET'])
def get_rotations():
    """Get current rotation assignments (AJAX)"""
    db = current_app.extensions['sqlalchemy']
    models = {
        'RotationAssignment': current_app.config['RotationAssignment'],
        'ScheduleException': current_app.config['ScheduleException'],
        'Employee': current_app.config['Employee']
    }

    rotation_mgr = RotationManager(db.session, models)
    rotations = rotation_mgr.get_all_rotations()

    # Convert to JSON-friendly format
    result = {
        'juicer': {str(day): emp_id for day, emp_id in rotations['juicer'].items()},
        'primary_lead': {str(day): emp_id for day, emp_id in rotations['primary_lead'].items()}
    }

    return jsonify(result)


@rotations_bp.route('/api/rotations', methods=['POST'])
def save_rotations():
    """Save rotation assignments (AJAX)"""
    db = current_app.extensions['sqlalchemy']
    models = {
        'RotationAssignment': current_app.config['RotationAssignment'],
        'ScheduleException': current_app.config['ScheduleException'],
        'Employee': current_app.config['Employee']
    }

    rotation_mgr = RotationManager(db.session, models)

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    # Convert string keys back to integers
    rotations = {}
    for rotation_type in ['juicer', 'primary_lead']:
        if rotation_type in data:
            rotations[rotation_type] = {
                int(day): emp_id
                for day, emp_id in data[rotation_type].items()
                if emp_id  # Skip empty values
            }

    success, errors = rotation_mgr.set_all_rotations(rotations)

    if success:
        return jsonify({'success': True, 'message': 'Rotations saved successfully'})
    else:
        return jsonify({'success': False, 'errors': errors}), 400


@rotations_bp.route('/api/exceptions', methods=['POST'])
def add_exception():
    """Add a rotation exception for a specific date"""
    db = current_app.extensions['sqlalchemy']
    models = {
        'RotationAssignment': current_app.config['RotationAssignment'],
        'ScheduleException': current_app.config['ScheduleException'],
        'Employee': current_app.config['Employee']
    }

    rotation_mgr = RotationManager(db.session, models)

    data = request.get_json()

    from datetime import datetime
    try:
        exception_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        return jsonify({'success': False, 'error': 'Invalid date format'}), 400

    rotation_type = data.get('rotation_type')
    employee_id = data.get('employee_id')
    reason = data.get('reason', '')

    if rotation_type not in ['juicer', 'primary_lead']:
        return jsonify({'success': False, 'error': 'Invalid rotation type'}), 400

    success, error = rotation_mgr.add_exception(exception_date, rotation_type, employee_id, reason)

    if success:
        return jsonify({'success': True, 'message': 'Exception added successfully'})
    else:
        return jsonify({'success': False, 'error': error}), 400


@rotations_bp.route('/api/exceptions', methods=['GET'])
def get_exceptions():
    """Get rotation exceptions for a date range"""
    db = current_app.extensions['sqlalchemy']
    models = {
        'RotationAssignment': current_app.config['RotationAssignment'],
        'ScheduleException': current_app.config['ScheduleException'],
        'Employee': current_app.config['Employee']
    }

    rotation_mgr = RotationManager(db.session, models)

    from datetime import datetime, timedelta

    # Default to next 4 weeks
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=28)

    # Allow query params to override
    if request.args.get('start_date'):
        start_date = datetime.strptime(request.args['start_date'], '%Y-%m-%d').date()
    if request.args.get('end_date'):
        end_date = datetime.strptime(request.args['end_date'], '%Y-%m-%d').date()

    exceptions = rotation_mgr.get_exceptions(start_date, end_date)

    result = [{
        'id': exc.id,
        'date': exc.exception_date.isoformat(),
        'rotation_type': exc.rotation_type,
        'employee_id': exc.employee_id,
        'employee_name': exc.employee.name,
        'reason': exc.reason
    } for exc in exceptions]

    return jsonify(result)


@rotations_bp.route('/api/exceptions/<int:exception_id>', methods=['DELETE'])
def delete_exception(exception_id):
    """Delete a rotation exception"""
    db = current_app.extensions['sqlalchemy']
    models = {
        'RotationAssignment': current_app.config['RotationAssignment'],
        'ScheduleException': current_app.config['ScheduleException'],
        'Employee': current_app.config['Employee']
    }

    rotation_mgr = RotationManager(db.session, models)

    success = rotation_mgr.delete_exception(exception_id)

    if success:
        return jsonify({'success': True, 'message': 'Exception deleted'})
    else:
        return jsonify({'success': False, 'error': 'Exception not found'}), 404
