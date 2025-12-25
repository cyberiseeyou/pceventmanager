"""
Attendance API Blueprint
Handles all attendance-related API endpoints for tracking employee attendance
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime, date
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)

# Create blueprint
attendance_api_bp = Blueprint('attendance_api', __name__, url_prefix='/api/attendance')


def init_attendance_routes(db, models):
    """
    Initialize attendance routes with database and models

    Args:
        db: SQLAlchemy database instance
        models: Dictionary of model classes
    """
    EmployeeAttendance = models['EmployeeAttendance']
    Employee = models['Employee']
    Schedule = models['Schedule']
    Event = models['Event']

    @attendance_api_bp.route('', methods=['POST'])
    def create_or_update_attendance():
        """
        Create or update attendance record

        Request JSON:
        {
            "employee_id": "emp123",
            "attendance_date": "2025-10-17",  // YYYY-MM-DD format
            "status": "on_time",  // on_time, late, called_in, no_call_no_show, excused_absence
            "notes": "Optional notes"
        }

        Returns:
            JSON with success status and attendance record
        """
        try:
            data = request.get_json()

            employee_id = data.get('employee_id')
            attendance_date_str = data.get('attendance_date')
            status = data.get('status')
            notes = data.get('notes', '')

            # Validate required fields
            if not employee_id or not attendance_date_str or not status:
                return jsonify({'error': 'employee_id, attendance_date, and status are required'}), 400

            # Parse date
            try:
                attendance_date = datetime.strptime(attendance_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

            # Validate employee exists
            employee = Employee.query.get(employee_id)
            if not employee:
                return jsonify({'error': 'Employee not found'}), 404

            # Validate status
            if status not in EmployeeAttendance.VALID_STATUSES:
                return jsonify({
                    'error': f'Invalid status. Must be one of: {", ".join(EmployeeAttendance.VALID_STATUSES)}'
                }), 400

            # Check if attendance record already exists (UPSERT behavior)
            attendance = EmployeeAttendance.query.filter_by(
                employee_id=employee_id,
                attendance_date=attendance_date
            ).first()

            if attendance:
                # Update existing record
                attendance.status = status
                attendance.notes = notes
                attendance.updated_at = datetime.utcnow()
                action = 'updated'
                status_code = 200
            else:
                # Create new record
                attendance = EmployeeAttendance(
                    employee_id=employee_id,
                    attendance_date=attendance_date,
                    status=status,
                    notes=notes,
                    recorded_by=session.get('username', 'Unknown')
                )
                db.session.add(attendance)
                action = 'created'
                status_code = 201

            db.session.commit()

            logger.info(f"Attendance {action}: employee_id={employee_id}, date={attendance_date}, status={status}")

            return jsonify({
                'success': True,
                'action': action,
                'attendance': attendance.to_dict()
            }), status_code

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating/updating attendance: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @attendance_api_bp.route('/<employee_id>', methods=['GET'])
    def get_employee_attendance(employee_id):
        """
        Get attendance records for an employee, optionally filtered by month

        Query Parameters:
            month: Optional month filter in YYYY-MM format

        Returns:
            JSON with attendance records grouped by date
        """
        try:
            month_str = request.args.get('month')

            # Base query
            query = EmployeeAttendance.query.filter_by(employee_id=employee_id)

            # Apply month filter if provided
            if month_str:
                try:
                    year, month = map(int, month_str.split('-'))
                    last_day = monthrange(year, month)[1]

                    start_date = date(year, month, 1)
                    end_date = date(year, month, last_day)

                    query = query.filter(
                        EmployeeAttendance.attendance_date >= start_date,
                        EmployeeAttendance.attendance_date <= end_date
                    )
                except ValueError:
                    return jsonify({'error': 'Invalid month format. Use YYYY-MM'}), 400

            # Execute query
            records = query.order_by(EmployeeAttendance.attendance_date.desc()).all()

            # Group by date (for multiple events same day)
            attendance_by_date = {}
            for record in records:
                date_key = record.attendance_date.isoformat()
                if date_key not in attendance_by_date:
                    attendance_by_date[date_key] = []
                attendance_by_date[date_key].append(record.to_dict())

            # Flatten single-item lists for cleaner API response
            for date_key in attendance_by_date:
                if len(attendance_by_date[date_key]) == 1:
                    attendance_by_date[date_key] = attendance_by_date[date_key][0]

            logger.info(f"Retrieved {len(records)} attendance records for employee {employee_id}")

            return jsonify({
                'employee_id': employee_id,
                'month': month_str,
                'attendance_by_date': attendance_by_date,
                'total_records': len(records)
            })

        except Exception as e:
            logger.error(f"Error retrieving attendance: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @attendance_api_bp.route('/<int:record_id>', methods=['GET'])
    def get_attendance_record(record_id):
        """
        Get specific attendance record by ID

        Returns:
            JSON with attendance record details
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)
            return jsonify({
                'success': True,
                'attendance': attendance.to_dict()
            })
        except Exception as e:
            logger.error(f"Error retrieving attendance record {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 404

    @attendance_api_bp.route('/<int:record_id>', methods=['PUT'])
    def update_attendance(record_id):
        """
        Update existing attendance record

        Request JSON:
        {
            "status": "late",
            "notes": "Updated notes"
        }

        Returns:
            JSON with updated attendance record
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)

            data = request.get_json()
            status = data.get('status')
            notes = data.get('notes')

            # Update status if provided
            if status:
                if status not in EmployeeAttendance.VALID_STATUSES:
                    return jsonify({
                        'error': f'Invalid status. Must be one of: {", ".join(EmployeeAttendance.VALID_STATUSES)}'
                    }), 400
                attendance.status = status

            # Update notes if provided (allow empty string to clear notes)
            if notes is not None:
                attendance.notes = notes

            attendance.updated_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Updated attendance record {record_id}")

            return jsonify({
                'success': True,
                'attendance': attendance.to_dict()
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating attendance {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @attendance_api_bp.route('/<int:record_id>', methods=['DELETE'])
    def delete_attendance(record_id):
        """
        Delete attendance record

        Returns:
            JSON with success message
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)

            db.session.delete(attendance)
            db.session.commit()

            logger.info(f"Deleted attendance record {record_id}")

            return jsonify({
                'success': True,
                'message': 'Attendance record deleted successfully'
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting attendance {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @attendance_api_bp.route('/date/<date_str>', methods=['GET'])
    def get_attendance_by_date(date_str):
        """
        Get all attendance records for a specific date

        Useful for daily view to show attendance status on event cards

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            JSON with attendance records for the date
        """
        try:
            # Parse date
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Query attendance records
            records = EmployeeAttendance.query.filter_by(attendance_date=target_date).all()

            # Build response with schedule details
            attendance_data = []
            for record in records:
                attendance_dict = record.to_dict()

                # Add schedule and event details if available
                if record.schedule:
                    schedule = record.schedule
                    event = schedule.event if hasattr(schedule, 'event') else None

                    attendance_dict['schedule'] = {
                        'id': schedule.id,
                        'schedule_datetime': schedule.schedule_datetime.isoformat() if schedule.schedule_datetime else None,
                        'event_name': event.project_name if event else None,
                        'event_type': event.event_type if event else None
                    }

                attendance_data.append(attendance_dict)

            logger.info(f"Retrieved {len(records)} attendance records for date {date_str}")

            return jsonify({
                'date': date_str,
                'attendance_records': attendance_data,
                'count': len(records)
            })

        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        except Exception as e:
            logger.error(f"Error retrieving attendance for date {date_str}: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @attendance_api_bp.route('/month/<date_str>', methods=['GET'])
    def get_monthly_attendance(date_str):
        """
        Get attendance records for an entire month (Story 4.3)

        Returns attendance data grouped by date and employee for calendar view.

        Args:
            date_str: Date in YYYY-MM-DD format (any date in the target month)

        Query Parameters:
            employee_id: Optional filter by specific employee

        Returns:
            JSON with:
            - attendance_by_date: Dict of {date: {employee_name: [records]}}
            - statistics: Monthly summary stats
        """
        try:
            # Parse date to get month boundaries
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            year = target_date.year
            month = target_date.month

            # Calculate month boundaries
            start_of_month = date(year, month, 1)
            last_day = monthrange(year, month)[1]
            end_of_month = date(year, month, last_day)

            # Build base query
            query = EmployeeAttendance.query.filter(
                EmployeeAttendance.attendance_date >= start_of_month,
                EmployeeAttendance.attendance_date <= end_of_month
            )

            # Filter by employee if specified
            employee_id = request.args.get('employee_id')
            if employee_id:
                query = query.filter_by(employee_id=employee_id)

            # Execute query with employee join
            records = query.join(Employee).order_by(
                EmployeeAttendance.attendance_date.asc(),
                Employee.name.asc()
            ).all()

            # Group by date and employee
            attendance_by_date = {}
            statistics = {
                'total_records': 0,
                'on_time': 0,
                'late': 0,
                'called_in': 0,
                'no_call_no_show': 0,
                'excused_absence': 0
            }

            for record in records:
                date_key = record.attendance_date.isoformat()
                employee_name = record.employee.name if record.employee else 'Unknown'

                # Initialize date if not exists
                if date_key not in attendance_by_date:
                    attendance_by_date[date_key] = {}

                # Initialize employee list if not exists
                if employee_name not in attendance_by_date[date_key]:
                    attendance_by_date[date_key][employee_name] = []

                # Add record
                attendance_by_date[date_key][employee_name].append({
                    'id': record.id,
                    'employee_id': record.employee_id,
                    'status': record.status,
                    'status_label': record.STATUS_LABELS.get(record.status),
                    'notes': record.notes,
                    'recorded_by': record.recorded_by,
                    'recorded_at': record.recorded_at.isoformat() if record.recorded_at else None
                })

                # Update statistics
                statistics['total_records'] += 1
                if record.status == 'on_time':
                    statistics['on_time'] += 1
                elif record.status == 'late':
                    statistics['late'] += 1
                elif record.status == 'called_in':
                    statistics['called_in'] += 1
                elif record.status == 'no_call_no_show':
                    statistics['no_call_no_show'] += 1
                elif record.status == 'excused_absence':
                    statistics['excused_absence'] += 1

            # Calculate on-time rate
            if statistics['total_records'] > 0:
                on_time_rate = (statistics['on_time'] / statistics['total_records']) * 100
                statistics['on_time_rate'] = f"{on_time_rate:.1f}%"
            else:
                statistics['on_time_rate'] = "0%"

            logger.info(f"Retrieved monthly attendance for {year}-{month:02d}: {len(records)} records")

            return jsonify({
                'month': f"{year}-{month:02d}",
                'start_date': start_of_month.isoformat(),
                'end_date': end_of_month.isoformat(),
                'attendance_by_date': attendance_by_date,
                'statistics': statistics
            })

        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        except Exception as e:
            logger.error(f"Error retrieving monthly attendance: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @attendance_api_bp.route('/scheduled-employees/<date_str>', methods=['GET'])
    def get_scheduled_employees_with_attendance(date_str):
        """
        Get all employees scheduled for a specific date with their attendance status

        This endpoint returns:
        - All unique employees who have schedules on this date (shown once per employee)
        - Their earliest start time for the day
        - Their attendance status if recorded, or null if not recorded
        - Useful for displaying "who's scheduled today" with attendance tracking

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            JSON with list of employees and their attendance status
        """
        try:
            # Parse date
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Get all schedules for this date
            schedules = Schedule.query.filter(
                db.func.date(Schedule.schedule_datetime) == target_date
            ).join(Employee).order_by(Schedule.schedule_datetime.asc()).all()

            # Get unique employees from schedules with earliest start time
            employees_scheduled = {}
            for schedule in schedules:
                emp = schedule.employee
                if emp:
                    # If employee not yet in dict, add them with this schedule's time
                    if emp.id not in employees_scheduled:
                        employees_scheduled[emp.id] = {
                            'employee_id': emp.id,
                            'employee_name': emp.name,
                            'earliest_start_time': schedule.schedule_datetime.strftime('%I:%M %p'),
                            'attendance_status': None,
                            'attendance_notes': None,
                            'attendance_id': None
                        }
                    # Since schedules are ordered by time, first occurrence is earliest
                    # No need to update if employee already exists

            # Get attendance records for this date
            attendance_records = EmployeeAttendance.query.filter_by(
                attendance_date=target_date
            ).all()

            # Map attendance to employees
            for record in attendance_records:
                if record.employee_id in employees_scheduled:
                    employees_scheduled[record.employee_id]['attendance_status'] = record.status
                    employees_scheduled[record.employee_id]['attendance_notes'] = record.notes
                    employees_scheduled[record.employee_id]['attendance_id'] = record.id
                    employees_scheduled[record.employee_id]['status_label'] = record.STATUS_LABELS.get(record.status)

            # Convert to list and sort by earliest start time, then by employee name
            result = sorted(
                employees_scheduled.values(),
                key=lambda x: (x['earliest_start_time'], x['employee_name'])
            )

            logger.info(f"Retrieved {len(result)} scheduled employees for date {date_str}")

            return jsonify({
                'date': date_str,
                'scheduled_employees': result,
                'count': len(result)
            })

        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        except Exception as e:
            logger.error(f"Error retrieving scheduled employees: {str(e)}")
            return jsonify({'error': str(e)}), 500

    return attendance_api_bp
