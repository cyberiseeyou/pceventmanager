"""
Employees routes blueprint
Handles employee management, availability, and time off operations
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from app.models import get_models
from app.routes.auth import require_authentication
from datetime import datetime, timedelta
from sqlalchemy import func

# Create blueprint
employees_bp = Blueprint('employees', __name__)


@employees_bp.route('/employees')
def employees():
    """Display employee management page"""
    models = get_models()
    Employee = models['Employee']
    employees = Employee.query.order_by(Employee.name).all()
    return render_template('employees.html', employees=employees)


@employees_bp.route('/time-off')
def time_off_requests():
    """Display time off requests management page"""
    return render_template('time_off_requests.html')


@employees_bp.route('/api/employees/active', methods=['GET'])
def get_active_employees():
    """
    Get all active employees for dropdowns (reissue, assignment, etc.)

    Returns list of active employees with id, name, and job_title
    """
    models = get_models()
    Employee = models['Employee']

    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()

    return jsonify([
        {
            'id': emp.id,
            'name': emp.name,
            'job_title': emp.job_title or 'Event Specialist'
        }
        for emp in employees
    ])


@employees_bp.route('/api/employees', methods=['GET', 'POST'])
@employees_bp.route('/api/employees/<employee_id>', methods=['DELETE'])
def manage_employees(employee_id=None):
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']
    Schedule = models['Schedule']
    EmployeeAvailability = models['EmployeeAvailability']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

    if request.method == 'GET':
        # Get all employees with their weekly availability
        employees_data = []
        employees = Employee.query.order_by(Employee.name).all()

        for emp in employees:
            weekly_availability = EmployeeWeeklyAvailability.query.filter_by(employee_id=emp.id).first()
            employee_data = {
                'id': emp.id,
                'name': emp.name,
                'email': emp.email,
                'phone': emp.phone,
                'is_active': emp.is_active,
                'is_supervisor': emp.is_supervisor,
                'job_title': emp.job_title,
                'adult_beverage_trained': emp.adult_beverage_trained,
                'juicer_trained': emp.juicer_trained,
                'weekly_availability': {
                    'monday': weekly_availability.monday if weekly_availability else True,
                    'tuesday': weekly_availability.tuesday if weekly_availability else True,
                    'wednesday': weekly_availability.wednesday if weekly_availability else True,
                    'thursday': weekly_availability.thursday if weekly_availability else True,
                    'friday': weekly_availability.friday if weekly_availability else True,
                    'saturday': weekly_availability.saturday if weekly_availability else True,
                    'sunday': weekly_availability.sunday if weekly_availability else True,
                } if weekly_availability else {
                    'monday': True, 'tuesday': True, 'wednesday': True, 'thursday': True,
                    'friday': True, 'saturday': True, 'sunday': True
                }
            }
            employees_data.append(employee_data)

        return jsonify(employees_data)

    elif request.method == 'POST':
        # Add or update employee
        data = request.get_json()

        if not data.get('name'):
            return jsonify({'error': 'Employee name is required'}), 400

        # Use provided ID or generate from name if not provided
        employee_id = data.get('id') or data['name'].upper().replace(' ', '_')

        try:
            # Check if we're editing an existing employee (based on the editing flag)
            editing_employee_id = data.get('editing_employee_id')  # This will be set by frontend for edits

            if editing_employee_id and editing_employee_id != employee_id:
                # This is an ID change - need to handle it specially
                old_employee = Employee.query.filter_by(id=editing_employee_id).first()
                if old_employee:
                    # Check if new ID already exists
                    if Employee.query.filter_by(id=employee_id).first():
                        return jsonify({'error': f'Employee ID {employee_id} already exists'}), 400

                    # Update related records first
                    Schedule.query.filter_by(employee_id=editing_employee_id).update({'employee_id': employee_id})
                    EmployeeAvailability.query.filter_by(employee_id=editing_employee_id).update({'employee_id': employee_id})
                    EmployeeWeeklyAvailability.query.filter_by(employee_id=editing_employee_id).update({'employee_id': employee_id})

                    # Delete old employee record
                    db.session.delete(old_employee)

                    # Create new employee with new ID
                    employee = Employee(
                        id=employee_id,
                        name=data['name'],
                        email=data.get('email'),
                        phone=data.get('phone'),
                        is_active=data.get('is_active', True),
                        is_supervisor=data.get('is_supervisor', False),
                        job_title=data.get('job_title', 'Event Specialist'),
                        adult_beverage_trained=data.get('adult_beverage_trained', False),
                        juicer_trained=data.get('juicer_trained', False)
                    )
                    db.session.add(employee)
                else:
                    return jsonify({'error': 'Original employee not found'}), 404
            else:
                # Check if employee exists
                employee = Employee.query.filter_by(id=employee_id).first()

                if employee:
                    # Update existing employee
                    employee.name = data['name']
                    employee.email = data.get('email')
                    employee.phone = data.get('phone')
                    employee.is_active = data.get('is_active', True)
                    employee.is_supervisor = data.get('is_supervisor', False)
                    employee.job_title = data.get('job_title', 'Event Specialist')
                    employee.adult_beverage_trained = data.get('adult_beverage_trained', False)
                    employee.juicer_trained = data.get('juicer_trained', False)
                else:
                    # Create new employee
                    employee = Employee(
                        id=employee_id,
                        name=data['name'],
                        email=data.get('email'),
                        phone=data.get('phone'),
                        is_active=data.get('is_active', True),
                        is_supervisor=data.get('is_supervisor', False),
                        job_title=data.get('job_title', 'Event Specialist'),
                        adult_beverage_trained=data.get('adult_beverage_trained', False),
                        juicer_trained=data.get('juicer_trained', False)
                    )
                    db.session.add(employee)

            # Handle weekly availability
            if 'weekly_availability' in data:
                availability_data = data['weekly_availability']
                weekly_availability = EmployeeWeeklyAvailability.query.filter_by(employee_id=employee_id).first()

                if weekly_availability:
                    # Update existing availability
                    weekly_availability.monday = availability_data.get('monday', True)
                    weekly_availability.tuesday = availability_data.get('tuesday', True)
                    weekly_availability.wednesday = availability_data.get('wednesday', True)
                    weekly_availability.thursday = availability_data.get('thursday', True)
                    weekly_availability.friday = availability_data.get('friday', True)
                    weekly_availability.saturday = availability_data.get('saturday', True)
                    weekly_availability.sunday = availability_data.get('sunday', True)
                else:
                    # Create new weekly availability
                    weekly_availability = EmployeeWeeklyAvailability(
                        employee_id=employee_id,
                        monday=availability_data.get('monday', True),
                        tuesday=availability_data.get('tuesday', True),
                        wednesday=availability_data.get('wednesday', True),
                        thursday=availability_data.get('thursday', True),
                        friday=availability_data.get('friday', True),
                        saturday=availability_data.get('saturday', True),
                        sunday=availability_data.get('sunday', True)
                    )
                    db.session.add(weekly_availability)

            db.session.commit()
            return jsonify({'message': 'Employee saved successfully', 'employee_id': employee_id})

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Database error: {str(e)}'}), 500

    elif request.method == 'DELETE':
        # Delete employee
        if not employee_id:
            return jsonify({'error': 'Employee ID is required'}), 400

        try:
            # Find the employee
            employee = Employee.query.filter_by(id=employee_id).first()
            if not employee:
                return jsonify({'error': 'Employee not found'}), 404

            # Check if employee has any scheduled events
            scheduled_events = Schedule.query.filter_by(employee_id=employee_id).count()
            if scheduled_events > 0:
                return jsonify({'error': f'Cannot delete employee with {scheduled_events} scheduled events. Deactivate instead.'}), 400

            # Delete related records first
            EmployeeWeeklyAvailability.query.filter_by(employee_id=employee_id).delete()
            EmployeeAvailability.query.filter_by(employee_id=employee_id).delete()

            # Delete the employee
            db.session.delete(employee)
            db.session.commit()

            return jsonify({'message': f'Employee {employee.name} deleted successfully'})

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Database error: {str(e)}'}), 500


@employees_bp.route('/api/employees/<employee_id>/availability', methods=['GET', 'POST'])
def employee_availability(employee_id):
    """Manage specific date availability for an employee"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']
    EmployeeAvailability = models['EmployeeAvailability']

    employee = Employee.query.filter_by(id=employee_id).first()
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404

    if request.method == 'GET':
        # Get specific date availabilities for the employee
        availabilities = EmployeeAvailability.query.filter_by(employee_id=employee_id).all()
        availability_data = []
        for avail in availabilities:
            availability_data.append({
                'date': avail.date.isoformat(),
                'is_available': avail.is_available,
                'reason': avail.reason
            })
        return jsonify(availability_data)

    elif request.method == 'POST':
        # Set specific date availability
        data = request.get_json()
        date_str = data.get('date')
        is_available = data.get('is_available', True)
        reason = data.get('reason', '')

        if not date_str:
            return jsonify({'error': 'Date is required'}), 400

        try:
            parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Check if availability record exists for this date
            availability = EmployeeAvailability.query.filter_by(
                employee_id=employee_id,
                date=parsed_date
            ).first()

            if availability:
                # Update existing record
                availability.is_available = is_available
                availability.reason = reason
            else:
                # Create new record
                availability = EmployeeAvailability(
                    employee_id=employee_id,
                    date=parsed_date,
                    is_available=is_available,
                    reason=reason
                )
                db.session.add(availability)

            db.session.commit()
            return jsonify({'message': 'Availability updated successfully'})

        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Database error: {str(e)}'}), 500


@employees_bp.route('/api/populate_employees', methods=['POST'])
def populate_employees():
    """Populate employees from the provided JSON data"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

    try:
        employees_data = request.get_json()

        if not isinstance(employees_data, list):
            return jsonify({'error': 'Expected a list of employees'}), 400

        added_count = 0
        updated_count = 0

        for emp_data in employees_data:
            if not emp_data.get('name'):
                continue

            # Generate employee ID from name
            employee_id = emp_data['name'].upper().replace(' ', '_')

            # Check if employee exists
            employee = Employee.query.filter_by(id=employee_id).first()

            if employee:
                # Update existing employee
                employee.is_supervisor = emp_data.get('is_supervisor', False)
                updated_count += 1
            else:
                # Create new employee
                employee = Employee(
                    id=employee_id,
                    name=emp_data['name'],
                    is_supervisor=emp_data.get('is_supervisor', False),
                    is_active=True
                )
                db.session.add(employee)
                added_count += 1

            # Handle weekly availability
            if 'availability' in emp_data:
                availability_data = emp_data['availability']
                weekly_availability = EmployeeWeeklyAvailability.query.filter_by(employee_id=employee_id).first()

                # Map day names to lowercase
                day_mapping = {
                    'Monday': 'monday', 'Tuesday': 'tuesday', 'Wednesday': 'wednesday',
                    'Thursday': 'thursday', 'Friday': 'friday', 'Saturday': 'saturday', 'Sunday': 'sunday'
                }

                if weekly_availability:
                    # Update existing availability
                    for day_name, available in availability_data.items():
                        if day_name in day_mapping:
                            setattr(weekly_availability, day_mapping[day_name], available)
                else:
                    # Create new weekly availability
                    availability_kwargs = {'employee_id': employee_id}
                    for day_name, available in availability_data.items():
                        if day_name in day_mapping:
                            availability_kwargs[day_mapping[day_name]] = available

                    weekly_availability = EmployeeWeeklyAvailability(**availability_kwargs)
                    db.session.add(weekly_availability)

        db.session.commit()
        return jsonify({
            'message': f'Successfully processed {len(employees_data)} employees',
            'added': added_count,
            'updated': updated_count
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error processing employees: {str(e)}'}), 500


@employees_bp.route('/api/employees/<employee_id>/time_off', methods=['GET', 'POST'])
def manage_employee_time_off(employee_id):
    """Manage time off requests for a specific employee"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']

    employee = Employee.query.filter_by(id=employee_id).first()
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404

    if request.method == 'GET':
        # Get all time off requests for the employee
        time_off_requests = EmployeeTimeOff.query.filter_by(employee_id=employee_id).order_by(EmployeeTimeOff.start_date.desc()).all()

        requests_data = []
        for req in time_off_requests:
            requests_data.append({
                'id': req.id,
                'start_date': req.start_date.isoformat(),
                'end_date': req.end_date.isoformat(),
                'reason': req.reason,
                'created_at': req.created_at.isoformat()
            })

        return jsonify(requests_data)

    elif request.method == 'POST':
        # Add new time off request
        data = request.get_json()

        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        reason = data.get('reason', '')

        if not start_date_str or not end_date_str:
            return jsonify({'error': 'Start date and end date are required'}), 400

        try:
            from datetime import datetime, date
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            if start_date > end_date:
                return jsonify({'error': 'Start date cannot be after end date'}), 400

            # Check for overlapping time off requests
            overlapping = EmployeeTimeOff.query.filter(
                EmployeeTimeOff.employee_id == employee_id,
                EmployeeTimeOff.start_date <= end_date,
                EmployeeTimeOff.end_date >= start_date
            ).first()

            if overlapping:
                return jsonify({'error': f'Time off request overlaps with existing request from {overlapping.start_date} to {overlapping.end_date}'}), 400

            # Check for conflicting scheduled events
            Schedule = models['Schedule']
            Event = models['Event']
            
            conflicting_schedules = Schedule.query.filter(
                Schedule.employee_id == employee_id,
                func.date(Schedule.schedule_datetime) >= start_date,
                func.date(Schedule.schedule_datetime) <= end_date
            ).all()
            
            # If conflicts exist and user hasn't confirmed unschedule, return warning
            if conflicting_schedules and not data.get('unschedule_conflicts', False):
                conflicts = []
                for sched in conflicting_schedules:
                    event = Event.query.filter_by(project_ref_num=sched.event_ref_num).first()
                    conflicts.append({
                        'schedule_id': sched.id,
                        'event_name': event.project_name if event else 'Unknown Event',
                        'event_type': event.event_type if event else 'Unknown',
                        'date': sched.schedule_datetime.strftime('%Y-%m-%d'),
                        'time': sched.schedule_datetime.strftime('%I:%M %p')
                    })
                return jsonify({
                    'warning': 'Employee has scheduled events during this time off period',
                    'conflicts': conflicts,
                    'can_unschedule': True
                }), 409
            
            # If user confirmed unschedule, handle conflicting schedules
            if conflicting_schedules and data.get('unschedule_conflicts', False):
                from app.integrations.external_api.session_api_service import session_api as external_api
                
                unscheduled_events = []
                schedule_ids_to_delete = [s.id for s in conflicting_schedules]
                current_app.logger.info(f"Attempting to delete {len(schedule_ids_to_delete)} schedules: {schedule_ids_to_delete}")
                
                for sched in conflicting_schedules:
                    event = Event.query.filter_by(project_ref_num=sched.event_ref_num).first()
                    
                    # Call Crossmark API to unschedule if external_id exists
                    if sched.external_id:
                        try:
                            if external_api.ensure_authenticated():
                                api_result = external_api.unschedule_mplan_event(str(sched.external_id))
                                if not api_result.get('success'):
                                    current_app.logger.warning(
                                        f"Failed to unschedule in Crossmark: {api_result.get('message')}"
                                    )
                        except Exception as api_error:
                            current_app.logger.error(f"Crossmark API error: {str(api_error)}")
                    
                    # Update event status
                    if event:
                        event.is_scheduled = False
                        event.condition = 'Unstaffed'
                        unscheduled_events.append(event.project_name)
                
                # Delete schedules using bulk delete to ensure they're removed
                deleted_count = Schedule.query.filter(Schedule.id.in_(schedule_ids_to_delete)).delete(synchronize_session='fetch')
                current_app.logger.info(f"Deleted {deleted_count} schedule records from database")
                
                current_app.logger.info(
                    f"Unscheduled {len(unscheduled_events)} events for {employee.name} due to time-off request"
                )

            # Create new time off request
            time_off_request = EmployeeTimeOff(
                employee_id=employee_id,
                start_date=start_date,
                end_date=end_date,
                reason=reason
            )

            db.session.add(time_off_request)
            db.session.commit()
            
            # Build response message
            message = f'Time off request added for {employee.name} from {start_date} to {end_date}'
            if conflicting_schedules and data.get('unschedule_conflicts', False):
                message += f'. {len(conflicting_schedules)} event(s) were unscheduled.'

            return jsonify({
                'message': message,
                'id': time_off_request.id,
                'events_unscheduled': len(conflicting_schedules) if conflicting_schedules and data.get('unschedule_conflicts', False) else 0
            })

        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Database error: {str(e)}'}), 500


@employees_bp.route('/api/time_off/<int:time_off_id>', methods=['DELETE'])
def delete_time_off(time_off_id):
    """Delete a time off request"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']
    EmployeeTimeOff = models['EmployeeTimeOff']

    time_off_request = EmployeeTimeOff.query.get(time_off_id)

    if not time_off_request:
        return jsonify({'error': 'Time off request not found'}), 404

    try:
        employee_name = Employee.query.get(time_off_request.employee_id).name
        db.session.delete(time_off_request)
        db.session.commit()

        return jsonify({
            'message': f'Time off request deleted for {employee_name} ({time_off_request.start_date} to {time_off_request.end_date})'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500


@employees_bp.route('/api/get_available_reps', methods=['GET'])
def get_available_reps():
    """
    Get available representatives from MVRetail/Crossmark API and compare with local database.

    Returns:
        - existing_employees: Employees already in local DB (with sync status)
        - new_employees: Employees from MVRetail not in local DB (available to import)
        - updated_count: Number of existing employees that were updated
    """
    from app.integrations.external_api.session_api_service import session_api as external_api

    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']

    try:
        # Get available representatives from the API
        reps_data = external_api.get_available_representatives()

        if not reps_data:
            return jsonify({'error': 'Failed to fetch representatives from MVRetail. Please check your session.'}), 500

        # Parse the response - Crossmark API returns 'reps' as an object with repId keys
        representatives = []
        if isinstance(reps_data, dict):
            if 'reps' in reps_data:
                reps_obj = reps_data['reps']
                if isinstance(reps_obj, dict):
                    representatives = list(reps_obj.values())
                else:
                    representatives = reps_obj if isinstance(reps_obj, list) else []
            elif 'representatives' in reps_data:
                representatives = reps_data['representatives']
            elif 'data' in reps_data:
                representatives = reps_data['data']
            elif 'records' in reps_data:
                representatives = reps_data['records']
            else:
                representatives = list(reps_data.values()) if reps_data else []
        elif isinstance(reps_data, list):
            representatives = reps_data

        # Get all local employees for comparison
        local_employees = Employee.query.all()

        # Build lookup dictionaries for matching
        # Match by: external_id (repId), crossmark_employee_id (employeeId), or name
        local_by_external_id = {emp.external_id: emp for emp in local_employees if emp.external_id}
        local_by_crossmark_id = {emp.crossmark_employee_id: emp for emp in local_employees if emp.crossmark_employee_id}
        local_by_name = {emp.name.upper(): emp for emp in local_employees}

        existing_employees = []
        new_employees = []
        updated_count = 0

        for rep in representatives:
            if not isinstance(rep, dict):
                continue

            # Extract MVRetail data
            rep_id = str(rep.get('repId') or rep.get('id') or '')
            title = rep.get('title') or rep.get('name') or ''
            employee_id = rep.get('employeeId') or rep.get('repMvid') or ''

            if not rep_id or not title:
                continue

            # Try to find matching local employee
            local_employee = None
            match_type = None

            # Priority 1: Match by external_id (repId)
            if rep_id and rep_id in local_by_external_id:
                local_employee = local_by_external_id[rep_id]
                match_type = 'external_id'
            # Priority 2: Match by crossmark_employee_id (employeeId)
            elif employee_id and employee_id in local_by_crossmark_id:
                local_employee = local_by_crossmark_id[employee_id]
                match_type = 'crossmark_id'
            # Priority 3: Match by name (case-insensitive)
            elif title.upper() in local_by_name:
                local_employee = local_by_name[title.upper()]
                match_type = 'name'

            if local_employee:
                # Employee exists - check if we need to update any fields
                needs_update = False
                updates = []

                # Check if external_id (repId) needs update
                if local_employee.external_id != rep_id:
                    updates.append(f"external_id: {local_employee.external_id} -> {rep_id}")
                    local_employee.external_id = rep_id
                    needs_update = True

                # Check if crossmark_employee_id needs update
                if local_employee.crossmark_employee_id != employee_id:
                    updates.append(f"crossmark_employee_id: {local_employee.crossmark_employee_id} -> {employee_id}")
                    local_employee.crossmark_employee_id = employee_id
                    needs_update = True

                # Check if name needs update (must match title exactly, including case)
                if local_employee.name != title:
                    updates.append(f"name: {local_employee.name} -> {title}")
                    local_employee.name = title
                    needs_update = True

                if needs_update:
                    local_employee.last_synced = datetime.utcnow()
                    local_employee.sync_status = 'synced'
                    updated_count += 1
                    current_app.logger.info(f"Updated employee {local_employee.id}: {', '.join(updates)}")

                existing_employees.append({
                    'id': local_employee.id,
                    'name': local_employee.name,
                    'external_id': rep_id,
                    'crossmark_employee_id': employee_id,
                    'match_type': match_type,
                    'was_updated': needs_update,
                    'updates': updates if needs_update else []
                })
            else:
                # New employee - not in local database
                new_employees.append({
                    'rep_id': rep_id,
                    'name': title,
                    'employee_id': employee_id,
                    'email': rep.get('email') or rep.get('Email'),
                    'phone': rep.get('phone') or rep.get('Phone'),
                })

        # Commit any updates to existing employees
        if updated_count > 0:
            db.session.commit()
            current_app.logger.info(f"Committed updates to {updated_count} existing employees")

        current_app.logger.info(
            f"MVRetail sync: {len(representatives)} total reps, "
            f"{len(existing_employees)} existing, {len(new_employees)} new, "
            f"{updated_count} updated"
        )

        return jsonify({
            'success': True,
            'existing_employees': existing_employees,
            'new_employees': new_employees,
            'updated_count': updated_count,
            'total_from_api': len(representatives)
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error getting available reps: {str(e)}")
        return jsonify({'error': f'Error fetching representatives: {str(e)}'}), 500


@employees_bp.route('/api/lookup_employee_id', methods=['POST'])
def lookup_employee_id():
    """
    Lookup employee's external_id (numeric ID for scheduling) from MVRetail API
    This is called after saving an employee to get their scheduling ID
    """
    from app.integrations.external_api.session_api_service import session_api as external_api

    data = request.get_json()
    employee_name = data.get('name')
    employee_id = data.get('employee_id')  # The US###### ID

    if not employee_name:
        return jsonify({'error': 'Employee name is required'}), 400

    try:
        # Get available representatives
        reps_data = external_api.get_available_representatives()

        if not reps_data:
            return jsonify({
                'found': False,
                'message': 'Unable to connect to MVRetail'
            })

        # Parse representatives - same logic as get_available_reps
        representatives = []
        if isinstance(reps_data, dict):
            # Crossmark API returns 'reps' as an object with repId keys
            if 'reps' in reps_data:
                reps_obj = reps_data['reps']
                # Convert object with numeric keys to list
                if isinstance(reps_obj, dict):
                    representatives = list(reps_obj.values())
                else:
                    representatives = reps_obj if isinstance(reps_obj, list) else []
            elif 'representatives' in reps_data:
                representatives = reps_data['representatives']
            elif 'data' in reps_data:
                representatives = reps_data['data']
            elif 'records' in reps_data:
                representatives = reps_data['records']
        elif isinstance(reps_data, list):
            representatives = reps_data

        # Search for the employee by name or employee_id
        for rep in representatives:
            if isinstance(rep, dict):
                rep_name = rep.get('name') or rep.get('Name') or f"{rep.get('FirstName', '')} {rep.get('LastName', '')}".strip()
                rep_id_field = rep.get('RepID') or rep.get('EmployeeID') or rep.get('employeeId')

                # Match by name (case-insensitive) or employee ID
                name_match = rep_name.lower() == employee_name.lower()
                id_match = employee_id and str(rep_id_field) == str(employee_id)

                if name_match or id_match:
                    external_id = rep.get('repId') or rep.get('id') or rep.get('RepID')

                    return jsonify({
                        'found': True,
                        'external_id': external_id,
                        'name': rep_name,
                        'email': rep.get('email') or rep.get('Email'),
                        'phone': rep.get('phone') or rep.get('Phone')
                    })

        # Employee not found
        return jsonify({
            'found': False,
            'message': f'Employee "{employee_name}" not found in MVRetail system'
        })

    except Exception as e:
        current_app.logger.error(f"Error looking up employee ID: {str(e)}")
        return jsonify({
            'found': False,
            'message': f'Error looking up employee: {str(e)}'
        })


@employees_bp.route('/api/import_employees', methods=['POST'])
def import_employees():
    """
    Import selected employees from MVRetail.
    Creates new employees with proper external_id (repId) and crossmark_employee_id (employeeId).
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Employee = models['Employee']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

    data = request.get_json()
    selected_employees = data.get('employees', [])

    if not selected_employees:
        return jsonify({'error': 'No employees selected'}), 400

    try:
        imported_count = 0
        errors = []

        for emp_data in selected_employees:
            rep_id = emp_data.get('rep_id')  # Numeric scheduling ID (external_id)
            name = emp_data.get('name')  # Full name from title field
            employee_id = emp_data.get('employee_id')  # US###### ID - this is the primary ID

            if not name or not rep_id:
                errors.append(f'Missing required fields for employee: {name or "Unknown"}')
                continue

            # Use the MVRetail employee_id (US######) as the primary ID
            # Fall back to name-based ID if employee_id is not available
            local_id = employee_id if employee_id else name.upper().replace(' ', '_')

            # Check if employee already exists by local ID or by external_id
            existing = Employee.query.filter(
                (Employee.id == local_id) | (Employee.external_id == rep_id)
            ).first()
            if existing:
                errors.append(f'Employee "{name}" already exists with ID: {existing.id}')
                continue

            # Create new employee
            employee = Employee(
                id=local_id,
                name=name,
                email=emp_data.get('email'),
                phone=emp_data.get('phone'),
                external_id=rep_id,  # The repId for scheduling
                crossmark_employee_id=employee_id,  # The US###### ID (same as id)
                is_active=True,
                job_title='Event Specialist',  # Default
                sync_status='synced',
                last_synced=datetime.utcnow()
            )
            db.session.add(employee)
            # Flush to ensure employee exists before adding availability (for FK constraint)
            db.session.flush()

            # Create default weekly availability (all days available)
            weekly_availability = EmployeeWeeklyAvailability(
                employee_id=local_id,
                monday=True,
                tuesday=True,
                wednesday=True,
                thursday=True,
                friday=True,
                saturday=True,
                sunday=True
            )
            db.session.add(weekly_availability)

            imported_count += 1
            current_app.logger.info(f"Imported employee: {name} (external_id={rep_id}, crossmark_id={employee_id})")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Successfully imported {imported_count} employee(s)',
            'imported': imported_count,
            'errors': errors
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing employees: {str(e)}")
        return jsonify({'error': f'Error importing employees: {str(e)}'}), 500
