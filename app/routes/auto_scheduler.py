"""
Auto-scheduler routes
Handles scheduler runs, review, and approval workflow
"""
from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime, timedelta, date
from sqlalchemy import func

from app.services.scheduling_engine import SchedulingEngine
from app.routes.auth import require_authentication

auto_scheduler_bp = Blueprint('auto_scheduler', __name__, url_prefix='/auto-schedule')


@auto_scheduler_bp.route('/')
@require_authentication()
def index():
    """Main auto-scheduler page with scheduling progress"""
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']

    # Get today's date
    today = date.today()
    two_weeks_from_now = today + timedelta(days=14)

    # Calculate statistics with new logic
    # Total events within 2 weeks (from today to 2 weeks from now)
    total_events_2weeks = Event.query.filter(
        Event.start_datetime >= today,
        Event.start_datetime <= two_weeks_from_now,
        # Exclude canceled and expired
        ~Event.condition.in_(['Canceled', 'Expired'])
    ).count()

    # Scheduled events: Scheduled + Submitted conditions within date range
    scheduled_events_2weeks = Event.query.filter(
        Event.start_datetime >= today,
        Event.start_datetime <= two_weeks_from_now,
        Event.condition.in_(['Scheduled', 'Submitted'])
    ).count()

    # Get unscheduled events within 2 weeks - ONLY Unstaffed are truly unscheduled
    unscheduled_events_2weeks = Event.query.filter(
        Event.condition == 'Unstaffed',
        Event.start_datetime >= today,
        Event.start_datetime <= two_weeks_from_now
    ).order_by(
        Event.start_datetime.asc(),
        Event.due_datetime.asc()
    ).all()

    # Calculate scheduling percentage
    scheduling_percentage = 0
    if total_events_2weeks > 0:
        scheduling_percentage = round((scheduled_events_2weeks / total_events_2weeks) * 100, 1)

    # Get last scheduler run info
    last_run = db.session.query(SchedulerRunHistory).order_by(
        SchedulerRunHistory.started_at.desc()
    ).first()

    return render_template('auto_scheduler_main.html',
                         unscheduled_events_2weeks=unscheduled_events_2weeks,
                         total_events_2weeks=total_events_2weeks,
                         scheduled_events_2weeks=scheduled_events_2weeks,
                         scheduling_percentage=scheduling_percentage,
                         last_run=last_run,
                         today=today)


@auto_scheduler_bp.route('/run', methods=['POST'])
def run_scheduler():
    """Manually trigger auto-scheduler run"""
    db = current_app.extensions['sqlalchemy']
    models = {k: current_app.config[k] for k in [
        'Employee', 'Event', 'Schedule', 'SchedulerRunHistory',
        'PendingSchedule', 'RotationAssignment', 'ScheduleException',
        'EmployeeTimeOff', 'EmployeeAvailability', 'EmployeeWeeklyAvailability',
        'CompanyHoliday'
    ]}

    engine = SchedulingEngine(db.session, models)

    try:
        run = engine.run_auto_scheduler(run_type='manual')

        return jsonify({
            'success': True,
            'run_id': run.id,
            'message': 'Scheduler run completed',
            'stats': {
                'total_events_processed': run.total_events_processed,
                'events_scheduled': run.events_scheduled,
                'events_requiring_swaps': run.events_requiring_swaps,
                'events_failed': run.events_failed
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auto_scheduler_bp.route('/status/<int:run_id>', methods=['GET'])
def get_run_status(run_id):
    """Get status of a scheduler run"""
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']
    db = current_app.extensions['sqlalchemy']

    run = db.session.query(SchedulerRunHistory).get(run_id)

    if not run:
        return jsonify({'success': False, 'error': 'Run not found'}), 404

    return jsonify({
        'run_id': run.id,
        'status': run.status,
        'started_at': run.started_at.isoformat(),
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'total_events_processed': run.total_events_processed,
        'events_scheduled': run.events_scheduled,
        'events_requiring_swaps': run.events_requiring_swaps,
        'events_failed': run.events_failed,
        'error_message': run.error_message
    })


@auto_scheduler_bp.route('/review')
def review():
    """Render proposal review page"""
    db = current_app.extensions['sqlalchemy']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']

    # Get latest unapproved run
    latest_run = db.session.query(SchedulerRunHistory).filter(
        SchedulerRunHistory.approved_at.is_(None),
        SchedulerRunHistory.status == 'completed'
    ).order_by(SchedulerRunHistory.started_at.desc()).first()

    if not latest_run:
        return render_template('auto_schedule_review.html',
                             run=None,
                             message="No pending schedule proposals to review")

    return render_template('auto_schedule_review.html', run=latest_run)


@auto_scheduler_bp.route('/api/pending', methods=['GET'])
def get_pending_schedules():
    """Get pending schedule data for review (AJAX)"""
    from datetime import date, timedelta

    db = current_app.extensions['sqlalchemy']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']
    PendingSchedule = current_app.config['PendingSchedule']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']
    Schedule = current_app.config['Schedule']

    run_id = request.args.get('run_id', type=int)

    if run_id:
        run = db.session.query(SchedulerRunHistory).get(run_id)
    else:
        # Get latest unapproved run
        run = db.session.query(SchedulerRunHistory).filter(
            SchedulerRunHistory.approved_at.is_(None),
            SchedulerRunHistory.status == 'completed'
        ).order_by(SchedulerRunHistory.started_at.desc()).first()

    if not run:
        return jsonify({'success': False, 'error': 'No pending run found'}), 404

    # Get all pending schedules for this run
    pending = db.session.query(PendingSchedule).filter_by(scheduler_run_id=run.id).all()

    # Categorize schedules
    newly_scheduled = []
    swaps = []
    failed = []
    daily_preview = {}
    bumped_event_refs = set()  # Track events that are being bumped

    for ps in pending:
        event = db.session.query(Event).filter_by(project_ref_num=ps.event_ref_num).first()
        employee = db.session.query(Employee).get(ps.employee_id) if ps.employee_id else None

        ps_data = {
            'id': ps.id,
            'event_ref_num': ps.event_ref_num,
            'event_name': event.project_name if event else 'Unknown',
            'event_type': event.event_type if event else 'Unknown',
            'start_date': event.start_datetime.date().isoformat() if event and event.start_datetime else None,
            'end_date': event.due_datetime.date().isoformat() if event and event.due_datetime else None,
            'employee_id': ps.employee_id,
            'employee_name': employee.name if employee else 'Unassigned',
            'schedule_datetime': ps.schedule_datetime.isoformat() if ps.schedule_datetime else None,
            'schedule_date': ps.schedule_datetime.date().isoformat() if ps.schedule_datetime else None,
            'schedule_time': ps.schedule_time.strftime('%H:%M') if ps.schedule_time else None,
            'is_swap': ps.is_swap,
            'swap_reason': ps.swap_reason,
            'failure_reason': ps.failure_reason,
            'status': 'failed' if ps.failure_reason else ('swap' if ps.is_swap else 'proposed')
        }

        # Track bumped events
        if ps.is_swap and ps.bumped_event_ref_num:
            bumped_event_refs.add(ps.bumped_event_ref_num)

        if ps.failure_reason:
            failed.append(ps_data)
        elif ps.is_swap:
            # Get bumped event details
            if ps.bumped_event_ref_num:
                bumped_event = db.session.query(Event).filter_by(project_ref_num=ps.bumped_event_ref_num).first()
                ps_data['bumped_event_name'] = bumped_event.project_name if bumped_event else 'Unknown'
                ps_data['bumped_event_ref_num'] = ps.bumped_event_ref_num
            swaps.append(ps_data)
        else:
            newly_scheduled.append(ps_data)

        # Add to daily preview (proposed events)
        if ps.schedule_datetime:
            date_key = ps.schedule_datetime.date().isoformat()
            if date_key not in daily_preview:
                daily_preview[date_key] = []
            daily_preview[date_key].append(ps_data)

    # Get date range for fetching already-scheduled events
    if daily_preview:
        date_keys = list(daily_preview.keys())
        min_date = min(date_keys)
        max_date = max(date_keys)

        # Fetch already-scheduled events within this date range
        from datetime import datetime
        min_datetime = datetime.fromisoformat(min_date)
        max_datetime = datetime.fromisoformat(max_date).replace(hour=23, minute=59, second=59)

        existing_schedules = db.session.query(Schedule).filter(
            Schedule.schedule_datetime >= min_datetime,
            Schedule.schedule_datetime <= max_datetime
        ).all()

        # Add existing schedules to daily preview
        for sched in existing_schedules:
            event = db.session.query(Event).filter_by(project_ref_num=sched.event_ref_num).first()
            employee = db.session.query(Employee).get(sched.employee_id) if sched.employee_id else None

            # Determine status: existing, or being bumped
            if sched.event_ref_num in bumped_event_refs:
                status = 'bumped_from'
            else:
                status = 'existing'

            sched_data = {
                'event_ref_num': sched.event_ref_num,
                'event_name': event.project_name if event else 'Unknown',
                'event_type': event.event_type if event else 'Unknown',
                'employee_id': sched.employee_id,
                'employee_name': employee.name if employee else 'Unassigned',
                'schedule_datetime': sched.schedule_datetime.isoformat() if sched.schedule_datetime else None,
                'schedule_date': sched.schedule_datetime.date().isoformat() if sched.schedule_datetime else None,
                'schedule_time': sched.schedule_datetime.strftime('%H:%M') if sched.schedule_datetime else None,
                'status': status,
                'is_existing': True
            }

            date_key = sched.schedule_datetime.date().isoformat()
            if date_key not in daily_preview:
                daily_preview[date_key] = []
            daily_preview[date_key].append(sched_data)

    return jsonify({
        'run_id': run.id,
        'newly_scheduled': newly_scheduled,
        'swaps': swaps,
        'failed': failed,
        'daily_preview': daily_preview,
        'stats': {
            'total_events_processed': run.total_events_processed,
            'events_scheduled': run.events_scheduled,
            'events_requiring_swaps': run.events_requiring_swaps,
            'events_failed': run.events_failed
        }
    })


@auto_scheduler_bp.route('/api/pending/<int:pending_id>', methods=['PUT'])
def edit_pending_schedule(pending_id):
    """Edit a pending schedule before approval"""
    db = current_app.extensions['sqlalchemy']
    PendingSchedule = current_app.config['PendingSchedule']
    Employee = current_app.config['Employee']

    pending = db.session.query(PendingSchedule).get(pending_id)
    if not pending:
        return jsonify({'success': False, 'error': 'Pending schedule not found'}), 404

    data = request.get_json()

    # Update employee if provided
    if 'employee_id' in data:
        employee = db.session.query(Employee).get(data['employee_id'])
        if not employee:
            return jsonify({'success': False, 'error': 'Employee not found'}), 400
        pending.employee_id = data['employee_id']

    # Update datetime if provided
    if 'schedule_datetime' in data:
        try:
            pending.schedule_datetime = datetime.fromisoformat(data['schedule_datetime'])
            pending.schedule_time = pending.schedule_datetime.time()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid datetime format'}), 400

    pending.status = 'user_edited'
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Pending schedule updated',
        'updated_schedule': {
            'id': pending.id,
            'employee_id': pending.employee_id,
            'schedule_datetime': pending.schedule_datetime.isoformat() if pending.schedule_datetime else None
        }
    })


@auto_scheduler_bp.route('/api/pending/by-ref/<event_ref_num>', methods=['DELETE'])
def delete_pending_by_ref(event_ref_num):
    """Delete a pending schedule by event reference number after manual scheduling"""
    db = current_app.extensions['sqlalchemy']
    PendingSchedule = current_app.config['PendingSchedule']

    try:
        # Find pending schedules for this event reference number
        pending_records = db.session.query(PendingSchedule).filter_by(
            event_ref_num=event_ref_num
        ).all()

        if not pending_records:
            return jsonify({
                'success': True,
                'message': 'No pending schedule found (may already be cleaned up)',
                'deleted_count': 0
            })

        deleted_count = len(pending_records)
        for pending in pending_records:
            db.session.delete(pending)
        
        db.session.commit()

        current_app.logger.info(
            f"Deleted {deleted_count} pending schedule(s) for event {event_ref_num} after manual scheduling"
        )

        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} pending schedule(s)',
            'deleted_count': deleted_count
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting pending schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@auto_scheduler_bp.route('/approve', methods=['POST'])
def approve_schedule():
    """Approve proposed schedule and submit to Crossmark API"""
    from app.integrations.external_api.session_api_service import session_api as external_api

    db = current_app.extensions['sqlalchemy']

    models_needed = ['SchedulerRunHistory', 'PendingSchedule', 'Event',
                     'Schedule', 'Employee']
    models = {k: current_app.config[k] for k in models_needed}

    data = request.get_json()
    run_id = data.get('run_id')

    if not run_id:
        return jsonify({'success': False, 'error': 'No run_id provided'}), 400

    run = db.session.query(models['SchedulerRunHistory']).get(run_id)
    if not run:
        return jsonify({'success': False, 'error': 'Run not found'}), 404

    # Get all non-failed pending schedules
    pending_schedules = db.session.query(models['PendingSchedule']).filter(
        models['PendingSchedule'].scheduler_run_id == run_id,
        models['PendingSchedule'].failure_reason.is_(None)
    ).all()

    current_app.logger.info(f"Found {len(pending_schedules)} pending schedules to approve for run {run_id}")

    api_submitted = 0
    api_failed = 0
    failed_details = []

    try:
        for pending in pending_schedules:
            if not pending.employee_id or not pending.schedule_datetime:
                continue

            # Get event and employee details
            event = db.session.query(models['Event']).filter_by(
                project_ref_num=pending.event_ref_num
            ).first()

            employee = db.session.query(models['Employee']).filter_by(
                id=pending.employee_id
            ).first()

            if not event or not employee:
                current_app.logger.warning(f"Missing data: event={event}, employee={employee} for pending {pending.id}")
                failed_details.append({
                    'event_ref_num': pending.event_ref_num,
                    'employee_id': pending.employee_id,
                    'reason': 'Event or employee not found'
                })
                pending.status = 'api_failed'
                pending.api_error_details = 'Event or employee not found in database'
                api_failed += 1
                continue

            # Calculate end datetime (start + estimated_time)
            start_datetime = pending.schedule_datetime
            # Use event's estimated_time, or fall back to the event type's default duration
            estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
            end_datetime = start_datetime + timedelta(minutes=estimated_minutes)

            # CRITICAL VALIDATION: Ensure schedule is within event period
            # This prevents scheduling events outside their valid start/due date window
            if not (event.start_datetime <= start_datetime <= event.due_datetime):
                error_msg = (
                    f"Schedule datetime {start_datetime.strftime('%Y-%m-%d %H:%M')} is outside "
                    f"event period ({event.start_datetime.strftime('%Y-%m-%d')} to "
                    f"{event.due_datetime.strftime('%Y-%m-%d')})"
                )
                current_app.logger.error(
                    f"Validation failed for event {event.project_ref_num} ({event.project_name}): {error_msg}"
                )
                failed_details.append({
                    'event_ref_num': pending.event_ref_num,
                    'event_name': event.project_name,
                    'employee_name': employee.name,
                    'scheduled_time': start_datetime.isoformat(),
                    'event_period': f"{event.start_datetime.date()} to {event.due_datetime.date()}",
                    'reason': error_msg
                })
                pending.status = 'validation_failed'
                pending.api_error_details = error_msg
                api_failed += 1
                continue

            # Prepare data for Crossmark API
            # IMPORTANT: Use external_id (numeric API ID), NOT employee.id (US###### format)
            rep_id = str(employee.external_id) if employee.external_id else None

            mplan_id = str(event.external_id) if event.external_id else None
            location_id = str(event.location_mvid) if event.location_mvid else None

            current_app.logger.info(
                f"API field check for {event.project_name}: "
                f"rep_id={rep_id} (from {employee.id}), "
                f"mplan_id={mplan_id}, "
                f"location_id={location_id}"
            )

            # Validate required API fields
            if not rep_id:
                failed_details.append({
                    'event_ref_num': pending.event_ref_num,
                    'event_name': event.project_name,
                    'employee_name': employee.name,
                    'reason': f'Missing external_id for employee {employee.name} ({employee.id})'
                })
                pending.status = 'api_failed'
                pending.api_error_details = 'Missing employee external_id'
                api_failed += 1
                continue

            if not mplan_id:
                failed_details.append({
                    'event_ref_num': pending.event_ref_num,
                    'event_name': event.project_name,
                    'reason': 'Missing external_id for event'
                })
                pending.status = 'api_failed'
                pending.api_error_details = 'Missing event external_id'
                api_failed += 1
                continue

            if not location_id:
                failed_details.append({
                    'event_ref_num': pending.event_ref_num,
                    'event_name': event.project_name,
                    'reason': 'Missing location_mvid for event'
                })
                pending.status = 'api_failed'
                pending.api_error_details = 'Missing location_mvid'
                api_failed += 1
                continue

            # Submit to Crossmark API
            try:
                current_app.logger.info(
                    f"Submitting to Crossmark API: "
                    f"rep_id={rep_id}, mplan_id={mplan_id}, location_id={location_id}, "
                    f"start={start_datetime.isoformat()}, end={end_datetime.isoformat()}, "
                    f"event={event.project_name}, employee={employee.name}"
                )

                api_result = external_api.schedule_mplan_event(
                    rep_id=rep_id,
                    mplan_id=mplan_id,
                    location_id=location_id,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    planning_override=True
                )

                if api_result.get('success'):
                    # Extract the scheduled event ID from the API response
                    # The schedule_event_id is extracted by the API service using robust parsing
                    scheduled_event_id = api_result.get('schedule_event_id')

                    current_app.logger.info(f"Extracted scheduled_event_id: {scheduled_event_id}")

                    # If we can't get the ID, log a warning but still proceed
                    if not scheduled_event_id:
                        current_app.logger.warning(
                            f"Could not extract external_id from API response for event {event.project_ref_num}. "
                            f"Response: {api_result}. Will create schedule without external_id."
                        )

                    # API submission successful - create local schedule record
                    schedule = models['Schedule'](
                        event_ref_num=pending.event_ref_num,
                        employee_id=pending.employee_id,
                        schedule_datetime=pending.schedule_datetime,
                        external_id=str(scheduled_event_id) if scheduled_event_id else None,
                        last_synced=datetime.utcnow(),
                        sync_status='synced' if scheduled_event_id else 'pending_sync'
                    )
                    db.session.add(schedule)

                    # Mark event as scheduled
                    event.is_scheduled = True
                    event.condition = 'Scheduled'
                    event.sync_status = 'synced' if scheduled_event_id else 'pending_sync'
                    event.last_synced = datetime.utcnow()

                    # Update pending schedule status
                    pending.status = 'api_submitted'
                    pending.api_submitted_at = datetime.utcnow()
                    api_submitted += 1

                    current_app.logger.info(
                        f"Successfully scheduled event {event.project_ref_num} ({event.project_name}) "
                        f"to {employee.name} at {start_datetime}"
                    )

                    # AUTO-SCHEDULE SUPERVISOR EVENT if this is a Core event
                    if event.event_type == 'Core':
                        from app.routes.scheduling import auto_schedule_supervisor_event
                        scheduled_date = start_datetime.date()
                        supervisor_scheduled, supervisor_event_name = auto_schedule_supervisor_event(
                            db, models['Event'], models['Schedule'], models['Employee'],
                            event.project_ref_num,
                            scheduled_date,
                            pending.employee_id
                        )
                        if supervisor_scheduled:
                            current_app.logger.info(
                                f"Auto-scheduled supervisor event: {supervisor_event_name}"
                            )
                else:
                    # API submission failed
                    error_message = api_result.get('message', 'Unknown API error')
                    failed_details.append({
                        'event_ref_num': pending.event_ref_num,
                        'event_name': event.project_name,
                        'employee_name': employee.name,
                        'reason': error_message
                    })
                    pending.status = 'api_failed'
                    pending.api_error_details = error_message
                    api_failed += 1

                    current_app.logger.warning(
                        f"Failed to schedule event {event.project_ref_num} to Crossmark API: {error_message}"
                    )

            except Exception as api_error:
                # API call exception
                error_message = f"API exception: {str(api_error)}"
                failed_details.append({
                    'event_ref_num': pending.event_ref_num,
                    'event_name': event.project_name,
                    'employee_name': employee.name,
                    'reason': error_message
                })
                pending.status = 'api_failed'
                pending.api_error_details = error_message
                api_failed += 1

                current_app.logger.error(
                    f"Exception scheduling event {event.project_ref_num}: {str(api_error)}",
                    exc_info=True
                )

        # Mark run as approved
        run.approved_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Schedule approved: {api_submitted} submitted, {api_failed} failed',
            'api_submitted': api_submitted,
            'api_failed': api_failed,
            'failed_events': failed_details
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to approve schedule: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to approve schedule: {str(e)}'
        }), 500


@auto_scheduler_bp.route('/approve-single/<int:pending_id>', methods=['POST'])
def approve_single_schedule(pending_id):
    """Approve and submit a single pending schedule to Crossmark API"""
    from app.integrations.external_api.session_api_service import session_api as external_api

    db = current_app.extensions['sqlalchemy']

    models_needed = ['PendingSchedule', 'Event', 'Schedule', 'Employee']
    models = {k: current_app.config[k] for k in models_needed}

    try:
        # Get the specific pending schedule with row-level lock to prevent race conditions
        pending = db.session.query(models['PendingSchedule']).with_for_update().get(pending_id)

        if not pending:
            return jsonify({
                'success': False,
                'error': 'Pending schedule not found'
            }), 404

        # Check if already processed (after lock acquired)
        if pending.status in ['api_submitted', 'api_failed', 'validation_failed']:
            db.session.rollback()  # Release lock
            return jsonify({
                'success': False,
                'error': f'Schedule already processed with status: {pending.status}'
            }), 409  # 409 Conflict

        # Check if this is a failed schedule
        if pending.failure_reason:
            return jsonify({
                'success': False,
                'error': f'Cannot approve failed schedule: {pending.failure_reason}'
            }), 400

        # Validate required fields
        if not pending.employee_id or not pending.schedule_datetime:
            return jsonify({
                'success': False,
                'error': 'Missing employee_id or schedule_datetime'
            }), 400

        # Get event and employee details
        event = db.session.query(models['Event']).filter_by(
            project_ref_num=pending.event_ref_num
        ).first()

        employee = db.session.query(models['Employee']).filter_by(
            id=pending.employee_id
        ).first()

        if not event or not employee:
            current_app.logger.warning(f"Missing data: event={event}, employee={employee} for pending {pending.id}")
            return jsonify({
                'success': False,
                'error': 'Event or employee not found in database',
                'event_ref_num': pending.event_ref_num,
                'employee_id': pending.employee_id
            }), 404

        # Calculate end datetime (start + estimated_time)
        start_datetime = pending.schedule_datetime
        # Use event's estimated_time, or fall back to the event type's default duration
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = start_datetime + timedelta(minutes=estimated_minutes)

        # CRITICAL VALIDATION: Ensure schedule is within event period
        # This prevents scheduling events outside their valid start/due date window
        if not (event.start_datetime <= start_datetime <= event.due_datetime):
            error_msg = (
                f"Schedule datetime {start_datetime.strftime('%Y-%m-%d %H:%M')} is outside "
                f"event period ({event.start_datetime.strftime('%Y-%m-%d')} to "
                f"{event.due_datetime.strftime('%Y-%m-%d')})"
            )
            current_app.logger.error(
                f"Validation failed for event {event.project_ref_num} ({event.project_name}): {error_msg}"
            )
            pending.status = 'validation_failed'
            pending.api_error_details = error_msg
            db.session.commit()

            return jsonify({
                'success': False,
                'error': error_msg,
                'event_ref_num': pending.event_ref_num,
                'event_name': event.project_name,
                'employee_name': employee.name,
                'scheduled_time': start_datetime.isoformat(),
                'event_period': f"{event.start_datetime.date()} to {event.due_datetime.date()}"
            }), 400

        # Prepare data for Crossmark API
        # IMPORTANT: Use external_id (numeric API ID), NOT employee.id (US###### format)
        rep_id = str(employee.external_id) if employee.external_id else None
        mplan_id = str(event.external_id) if event.external_id else None
        location_id = str(event.location_mvid) if event.location_mvid else None

        current_app.logger.info(
            f"API field check for {event.project_name}: "
            f"rep_id={rep_id} (from {employee.id}), "
            f"mplan_id={mplan_id}, "
            f"location_id={location_id}"
        )

        # Validate required API fields
        if not rep_id:
            error_msg = f'Missing external_id for employee {employee.name} ({employee.id})'
            pending.status = 'api_failed'
            pending.api_error_details = 'Missing employee external_id'
            db.session.commit()

            return jsonify({
                'success': False,
                'error': error_msg,
                'event_ref_num': pending.event_ref_num,
                'event_name': event.project_name,
                'employee_name': employee.name
            }), 400

        if not mplan_id:
            error_msg = 'Missing external_id for event'
            pending.status = 'api_failed'
            pending.api_error_details = 'Missing event external_id'
            db.session.commit()

            return jsonify({
                'success': False,
                'error': error_msg,
                'event_ref_num': pending.event_ref_num,
                'event_name': event.project_name
            }), 400

        if not location_id:
            error_msg = 'Missing location_mvid for event'
            pending.status = 'api_failed'
            pending.api_error_details = 'Missing location_mvid'
            db.session.commit()

            return jsonify({
                'success': False,
                'error': error_msg,
                'event_ref_num': pending.event_ref_num,
                'event_name': event.project_name
            }), 400

        # Submit to Crossmark API
        try:
            current_app.logger.info(
                f"Submitting to Crossmark API: "
                f"rep_id={rep_id}, mplan_id={mplan_id}, location_id={location_id}, "
                f"start={start_datetime.isoformat()}, end={end_datetime.isoformat()}, "
                f"event={event.project_name}, employee={employee.name}"
            )

            api_result = external_api.schedule_mplan_event(
                rep_id=rep_id,
                mplan_id=mplan_id,
                location_id=location_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                planning_override=True
            )

            if api_result.get('success'):
                # Extract the scheduled event ID from the API response
                # The schedule_event_id is extracted by the API service using robust parsing
                scheduled_event_id = api_result.get('schedule_event_id')

                current_app.logger.info(f"Extracted scheduled_event_id: {scheduled_event_id}")

                # If we can't get the ID, log a warning but still proceed
                # The event was scheduled successfully on the remote system
                if not scheduled_event_id:
                    current_app.logger.warning(
                        f"Could not extract external_id from API response for event {event.project_ref_num}. "
                        f"Response: {api_result}. Will create schedule without external_id."
                    )

                # API submission successful - create local schedule record
                schedule = models['Schedule'](
                    event_ref_num=pending.event_ref_num,
                    employee_id=pending.employee_id,
                    schedule_datetime=pending.schedule_datetime,
                    external_id=str(scheduled_event_id) if scheduled_event_id else None,
                    last_synced=datetime.utcnow(),
                    sync_status='synced' if scheduled_event_id else 'pending_sync'
                )
                db.session.add(schedule)

                # Mark event as scheduled
                event.is_scheduled = True
                event.condition = 'Scheduled'
                event.sync_status = 'synced'
                event.last_synced = datetime.utcnow()

                # Update pending schedule status
                pending.status = 'api_submitted'
                pending.api_submitted_at = datetime.utcnow()

                # COMMIT TRANSACTION BEFORE supervisor event creation
                # This ensures Core event is persisted even if supervisor scheduling fails
                db.session.commit()

                current_app.logger.info(
                    f"Successfully scheduled event {event.project_ref_num} ({event.project_name}) "
                    f"to {employee.name} at {start_datetime}"
                )

                # AUTO-SCHEDULE SUPERVISOR EVENT if this is a Core event
                # This happens OUTSIDE the main transaction to prevent rollback of Core event
                supervisor_scheduled = False
                supervisor_event_name = None
                if event.event_type == 'Core':
                    try:
                        from app.routes.scheduling import auto_schedule_supervisor_event
                        scheduled_date = start_datetime.date()
                        supervisor_scheduled, supervisor_event_name = auto_schedule_supervisor_event(
                            db, models['Event'], models['Schedule'], models['Employee'],
                            event.project_ref_num,
                            scheduled_date,
                            pending.employee_id
                        )
                        if supervisor_scheduled:
                            current_app.logger.info(
                                f"Auto-scheduled supervisor event: {supervisor_event_name}"
                            )
                        else:
                            current_app.logger.warning(
                                f"Failed to auto-schedule supervisor event for Core event {event.project_ref_num}"
                            )
                    except Exception as supervisor_error:
                        # Log supervisor event failure but don't fail the entire request
                        # Core event is already successfully scheduled
                        current_app.logger.error(
                            f"Exception auto-scheduling supervisor event for {event.project_ref_num}: {str(supervisor_error)}",
                            exc_info=True
                        )

                return jsonify({
                    'success': True,
                    'event_name': event.project_name,
                    'event_ref_num': event.project_ref_num,
                    'employee_name': employee.name,
                    'scheduled_time': start_datetime.isoformat(),
                    'supervisor_scheduled': supervisor_scheduled,
                    'supervisor_event_name': supervisor_event_name
                })
            else:
                # API submission failed
                error_message = api_result.get('message', 'Unknown API error')
                pending.status = 'api_failed'
                pending.api_error_details = error_message
                db.session.commit()

                current_app.logger.warning(
                    f"Failed to schedule event {event.project_ref_num} to Crossmark API: {error_message}"
                )

                return jsonify({
                    'success': False,
                    'error': error_message,
                    'event_ref_num': pending.event_ref_num,
                    'event_name': event.project_name,
                    'employee_name': employee.name
                }), 500

        except Exception as api_error:
            # API call exception
            error_message = f"API exception: {str(api_error)}"
            pending.status = 'api_failed'
            pending.api_error_details = error_message
            db.session.commit()

            current_app.logger.error(
                f"Exception scheduling event {event.project_ref_num}: {str(api_error)}",
                exc_info=True
            )

            return jsonify({
                'success': False,
                'error': error_message,
                'event_ref_num': pending.event_ref_num,
                'event_name': event.project_name,
                'employee_name': employee.name
            }), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to approve single schedule: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to approve schedule: {str(e)}'
        }), 500


@auto_scheduler_bp.route('/mark-approved/<int:run_id>', methods=['POST'])
def mark_run_approved(run_id):
    """Mark a scheduler run as approved after all schedules are processed"""
    db = current_app.extensions['sqlalchemy']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']

    try:
        run = db.session.query(SchedulerRunHistory).get(run_id)

        if not run:
            return jsonify({
                'success': False,
                'error': 'Run not found'
            }), 404

        # Mark run as approved
        run.approved_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Scheduler run marked as approved'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to mark run as approved: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to mark run as approved: {str(e)}'
        }), 500


@auto_scheduler_bp.route('/reject', methods=['POST'])
def reject_schedule():
    """Reject/discard ALL pending schedule proposals"""
    db = current_app.extensions['sqlalchemy']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']
    PendingSchedule = current_app.config['PendingSchedule']
    Event = current_app.config['Event']

    data = request.get_json() or {}
    reject_all = data.get('reject_all', True)  # Default to rejecting all

    try:
        if reject_all:
            # Get all pending runs (completed but not approved)
            pending_runs = db.session.query(SchedulerRunHistory).filter(
                SchedulerRunHistory.approved_at.is_(None),
                SchedulerRunHistory.status == 'completed'
            ).all()

            if not pending_runs:
                return jsonify({
                    'success': True,
                    'message': 'No pending proposals to reject'
                })

            events_reset = 0
            for run in pending_runs:
                # CRITICAL: Reset is_scheduled flag on all events that had pending schedules
                # This ensures they are picked up by _get_unscheduled_events() on next run
                pending_schedules = db.session.query(PendingSchedule).filter_by(
                    scheduler_run_id=run.id
                ).all()

                for ps in pending_schedules:
                    event = db.session.query(Event).filter_by(
                        project_ref_num=ps.event_ref_num
                    ).first()
                    if event and event.is_scheduled:
                        event.is_scheduled = False
                        event.condition = 'Unstaffed'
                        events_reset += 1

                # Now delete all pending schedules for this run
                db.session.query(PendingSchedule).filter_by(
                    scheduler_run_id=run.id
                ).delete()

                # Mark run as rejected
                run.status = 'rejected'
                if not run.completed_at:
                    run.completed_at = datetime.utcnow()

            db.session.commit()

            current_app.logger.info(f"Rejected {len(pending_runs)} proposal(s), reset {events_reset} events")

            return jsonify({
                'success': True,
                'message': f'{len(pending_runs)} schedule proposal(s) rejected and discarded',
                'events_reset': events_reset
            })
        else:
            # Reject specific run only
            run_id = data.get('run_id')
            if not run_id:
                return jsonify({'success': False, 'error': 'No run_id provided'}), 400

            run = db.session.query(SchedulerRunHistory).get(run_id)
            if not run:
                return jsonify({'success': False, 'error': 'Run not found'}), 404

            # CRITICAL: Reset is_scheduled flag on all events that had pending schedules
            pending_schedules = db.session.query(PendingSchedule).filter_by(
                scheduler_run_id=run_id
            ).all()

            events_reset = 0
            for ps in pending_schedules:
                event = db.session.query(Event).filter_by(
                    project_ref_num=ps.event_ref_num
                ).first()
                if event and event.is_scheduled:
                    event.is_scheduled = False
                    event.condition = 'Unstaffed'
                    events_reset += 1

            # Now delete all pending schedules for this run
            db.session.query(PendingSchedule).filter_by(
                scheduler_run_id=run_id
            ).delete()

            # Mark run as rejected
            run.status = 'rejected'
            if not run.completed_at:
                run.completed_at = datetime.utcnow()

            db.session.commit()

            current_app.logger.info(f"Rejected run {run_id}, reset {events_reset} events")

            return jsonify({
                'success': True,
                'message': 'Schedule proposal rejected and discarded',
                'events_reset': events_reset
            })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to reject schedule: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to reject schedule: {str(e)}'
        }), 500


@auto_scheduler_bp.route('/api/dashboard-status', methods=['GET'])
def dashboard_status():
    """Check if there are pending scheduler runs for dashboard notification"""
    db = current_app.extensions['sqlalchemy']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']

    # Count runs that are completed but not approved and not rejected
    pending_count = db.session.query(func.count(SchedulerRunHistory.id)).filter(
        SchedulerRunHistory.approved_at.is_(None),
        SchedulerRunHistory.status == 'completed'
    ).scalar()

    return jsonify({
        'has_pending': pending_count > 0,
        'pending_count': pending_count
    })


@auto_scheduler_bp.route('/api/verify/<int:run_id>', methods=['GET'])
def verify_pending_run(run_id):
    """Verify pending schedules for a scheduler run (pre-approval)"""
    from app.services.schedule_verification import ScheduleVerificationService

    db = current_app.extensions['sqlalchemy']
    SchedulerRunHistory = current_app.config['SchedulerRunHistory']
    PendingSchedule = current_app.config['PendingSchedule']

    try:
        # Get the scheduler run
        run = db.session.query(SchedulerRunHistory).get(run_id)
        if not run:
            return jsonify({'success': False, 'error': 'Run not found'}), 404

        # Get date range from pending schedules
        pending_dates = db.session.query(
            func.min(func.date(PendingSchedule.schedule_datetime)).label('start_date'),
            func.max(func.date(PendingSchedule.schedule_datetime)).label('end_date')
        ).filter(
            PendingSchedule.scheduler_run_id == run_id
        ).first()

        if not pending_dates.start_date:
            return jsonify({
                'success': True,
                'critical_issues': [],
                'warnings': [],
                'info': [{'message': 'No pending schedules to verify'}],
                'stats': {}
            })

        # Initialize verification service
        models = {k: current_app.config[k] for k in [
            'Event', 'Schedule', 'PendingSchedule', 'Employee',
            'EmployeeTimeOff', 'EmployeeAvailability', 'EmployeeWeeklyAvailability',
            'RotationAssignment', 'ScheduleException'
        ]}

        verifier = ScheduleVerificationService(db.session, models)

        # Run verification (include pending schedules)
        result = verifier.verify_date_range(
            start_date=pending_dates.start_date,
            end_date=pending_dates.end_date,
            include_pending=True,
            run_id=run_id
        )

        result['success'] = True
        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"Verification failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auto_scheduler_bp.route('/api/verify-date', methods=['GET'])
def verify_date():
    """Verify schedules for a specific date (dashboard widget)"""
    from app.services.schedule_verification import ScheduleVerificationService
    from datetime import datetime

    db = current_app.extensions['sqlalchemy']

    try:
        # Get date parameter (defaults to today)
        date_str = request.args.get('date')
        if date_str:
            verify_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            verify_date = date.today()

        # Initialize verification service
        models = {k: current_app.config[k] for k in [
            'Event', 'Schedule', 'PendingSchedule', 'Employee',
            'EmployeeTimeOff', 'EmployeeAvailability', 'EmployeeWeeklyAvailability',
            'RotationAssignment', 'ScheduleException', 'EmployeeAttendance'
        ]}

        verifier = ScheduleVerificationService(db.session, models)

        # Run daily verification
        result = verifier.verify_schedule(verify_date)

        return jsonify({
            'success': True,
            'date': verify_date.isoformat(),
            'status': result.status,
            'issues': [issue.to_dict() for issue in result.issues],
            'summary': result.summary
        })

    except Exception as e:
        current_app.logger.error(f"Date verification failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auto_scheduler_bp.route('/api/verify-date-range', methods=['GET'])
def verify_date_range_endpoint():
    """Verify schedules for a date range (post-approval audit)"""
    from app.services.schedule_verification import ScheduleVerificationService
    from datetime import datetime

    db = current_app.extensions['sqlalchemy']

    try:
        # Get date parameters
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')

        if not start_str or not end_str:
            return jsonify({
                'success': False,
                'error': 'start_date and end_date parameters required'
            }), 400

        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()

        # Initialize verification service
        models = {k: current_app.config[k] for k in [
            'Event', 'Schedule', 'PendingSchedule', 'Employee',
            'EmployeeTimeOff', 'EmployeeAvailability', 'EmployeeWeeklyAvailability',
            'RotationAssignment', 'ScheduleException'
        ]}

        verifier = ScheduleVerificationService(db.session, models)

        # Run range verification (post-approval, no pending)
        result = verifier.verify_date_range(
            start_date=start_date,
            end_date=end_date,
            include_pending=False
        )

        result['success'] = True
        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"Date range verification failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
