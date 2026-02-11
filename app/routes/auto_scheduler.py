"""
Auto-scheduler routes
Handles scheduler runs, review, and approval workflow
"""
import csv
from io import StringIO

from flask import Blueprint, render_template, request, jsonify, current_app, Response
from app.models import get_models
from app.constants import INACTIVE_CONDITIONS, CONDITION_SCHEDULED, CONDITION_SUBMITTED
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
    models = get_models()
    Event = models['Event']
    SchedulerRunHistory = models['SchedulerRunHistory']

    # Get today's date
    today = date.today()
    display_horizon = today + timedelta(days=120)  # 4 months

    # Calculate statistics with new logic
    # Total events within 4 months (from today to 4 months from now)
    total_events_display = Event.query.filter(
        Event.start_datetime >= today,
        Event.start_datetime <= display_horizon,
        # Exclude canceled and expired
        ~Event.condition.in_(list(INACTIVE_CONDITIONS))
    ).count()

    # Scheduled events: Scheduled + Submitted conditions within date range
    scheduled_events_display = Event.query.filter(
        Event.start_datetime >= today,
        Event.start_datetime <= display_horizon,
        Event.condition.in_([CONDITION_SCHEDULED, CONDITION_SUBMITTED])
    ).count()

    # Get unscheduled events within 4 months - ONLY Unstaffed are truly unscheduled
    unscheduled_events_display = Event.query.filter(
        Event.condition == 'Unstaffed',
        Event.start_datetime >= today,
        Event.start_datetime <= display_horizon
    ).order_by(
        Event.start_datetime.asc(),
        Event.due_datetime.asc()
    ).all()

    # Calculate scheduling percentage
    scheduling_percentage = 0
    if total_events_display > 0:
        scheduling_percentage = round((scheduled_events_display / total_events_display) * 100, 1)

    # Get last scheduler run info
    last_run = db.session.query(SchedulerRunHistory).order_by(
        SchedulerRunHistory.started_at.desc()
    ).first()

    return render_template('auto_scheduler_main.html',
                         unscheduled_events_display=unscheduled_events_display,
                         total_events_display=total_events_display,
                         scheduled_events_display=scheduled_events_display,
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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']

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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']
    Employee = models['Employee']
    Schedule = models['Schedule']

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
                import re
                bumped_event = db.session.query(Event).filter_by(project_ref_num=ps.bumped_event_ref_num).first()
                ps_data['bumped_event_name'] = bumped_event.project_name if bumped_event else 'Unknown'
                ps_data['bumped_event_ref_num'] = ps.bumped_event_ref_num
                
                # Extract 6-digit event numbers from project names
                if bumped_event:
                    bumped_match = re.search(r'\d{6}', bumped_event.project_name)
                    ps_data['bumped_event_number'] = bumped_match.group(0) if bumped_match else str(ps.bumped_event_ref_num)
                else:
                    ps_data['bumped_event_number'] = str(ps.bumped_event_ref_num)
                
                if event:
                    replacing_match = re.search(r'\d{6}', event.project_name)
                    ps_data['replacing_event_number'] = replacing_match.group(0) if replacing_match else str(ps.event_ref_num)
                else:
                    ps_data['replacing_event_number'] = str(ps.event_ref_num)
                
                # Find where the bumped event is being rescheduled to
                # Check for ANY successful schedule (could be swap or non-swap)
                bumped_reschedule = db.session.query(PendingSchedule).filter(
                    PendingSchedule.scheduler_run_id == run.id,
                    PendingSchedule.event_ref_num == ps.bumped_event_ref_num,
                    PendingSchedule.status != 'superseded',
                    PendingSchedule.failure_reason.is_(None)
                ).first()
                
                if bumped_reschedule:
                    bumped_employee = db.session.query(Employee).get(bumped_reschedule.employee_id) if bumped_reschedule.employee_id else None
                    ps_data['bumped_rescheduled_to'] = {
                        'employee_name': bumped_employee.name if bumped_employee else 'Unassigned',
                        'schedule_datetime': bumped_reschedule.schedule_datetime.isoformat() if bumped_reschedule.schedule_datetime else None,
                        'schedule_date': bumped_reschedule.schedule_datetime.date().isoformat() if bumped_reschedule.schedule_datetime else None,
                        'schedule_time': bumped_reschedule.schedule_time.strftime('%H:%M') if bumped_reschedule.schedule_time else None
                    }
                else:
                    # Check if there's a failed rescheduling attempt
                    bumped_failed = db.session.query(PendingSchedule).filter(
                        PendingSchedule.scheduler_run_id == run.id,
                        PendingSchedule.event_ref_num == ps.bumped_event_ref_num,
                        PendingSchedule.failure_reason.isnot(None)
                    ).first()
                    
                    if bumped_failed:
                        ps_data['bumped_rescheduled_to'] = {
                            'failed': True,
                            'failure_reason': bumped_failed.failure_reason
                        }
                    else:
                        # This shouldn't happen - scheduler should always reschedule or fail
                        # But if it does, indicate an error
                        ps_data['bumped_rescheduled_to'] = {
                            'failed': True,
                            'failure_reason': 'Scheduler error: bumped event was not processed'
                        }
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
    models = get_models()
    PendingSchedule = models['PendingSchedule']
    Employee = models['Employee']

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
    models = get_models()
    PendingSchedule = models['PendingSchedule']

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
    from sqlalchemy import func

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

    # CHECK LOCKED DAYS: Before approving, check if any affected dates are locked
    # This includes both target schedule dates and dates of events being bumped
    LockedDay = current_app.config.get('LockedDay')
    if LockedDay:
        locked_date_conflicts = []
        checked_dates = set()

        for pending in pending_schedules:
            # Skip superseded schedules - they're not actually being scheduled
            if pending.status == 'superseded':
                continue

            # Check target schedule date
            if pending.schedule_datetime:
                schedule_date = pending.schedule_datetime.date()
                if schedule_date not in checked_dates:
                    checked_dates.add(schedule_date)
                    locked_info = LockedDay.get_locked_day(schedule_date)
                    if locked_info:
                        locked_date_conflicts.append({
                            'date': schedule_date.isoformat(),
                            'reason': locked_info.reason or 'No reason provided',
                            'locked_by': locked_info.locked_by,
                            'type': 'schedule_target',
                            'event_ref': pending.event_ref_num
                        })

            # Check if this approval involves bumping an event from a locked day
            if pending.is_swap and pending.bumped_event_ref_num:
                # Find the bumped event's current schedule date
                bumped_schedules = db.session.query(models['Schedule']).filter(
                    models['Schedule'].event_ref_num == pending.bumped_event_ref_num
                ).all()

                for bumped_sched in bumped_schedules:
                    bumped_date = bumped_sched.schedule_datetime.date()
                    if bumped_date not in checked_dates:
                        checked_dates.add(bumped_date)
                        locked_info = LockedDay.get_locked_day(bumped_date)
                        if locked_info:
                            locked_date_conflicts.append({
                                'date': bumped_date.isoformat(),
                                'reason': locked_info.reason or 'No reason provided',
                                'locked_by': locked_info.locked_by,
                                'type': 'bump_source',
                                'event_ref': pending.bumped_event_ref_num
                            })

        if locked_date_conflicts:
            # Sort by date for cleaner display
            locked_date_conflicts.sort(key=lambda x: x['date'])
            unique_dates = list(set(c['date'] for c in locked_date_conflicts))

            current_app.logger.warning(
                f"Cannot approve run {run_id} - {len(unique_dates)} locked date(s) would be affected: {unique_dates}"
            )

            return jsonify({
                'success': False,
                'error': f'Cannot approve: {len(unique_dates)} locked day(s) would be affected. Unlock these days first.',
                'locked_dates': locked_date_conflicts
            }), 409  # Conflict

    # FIRST: Handle bumped events BEFORE processing pending schedules
    # This ensures that bumped events are unscheduled before we try to schedule new events
    try:
        # Find all pending schedules that involve bumping another event
        swap_schedules = [ps for ps in pending_schedules if ps.is_swap and ps.bumped_event_ref_num]
        
        if swap_schedules:
            current_app.logger.info(f"Processing {len(swap_schedules)} schedules with bumps")
            
            # Track which events have been bumped to avoid duplicate processing
            bumped_event_refs = set()
            
            for swap_schedule in swap_schedules:
                bumped_ref = swap_schedule.bumped_event_ref_num
                
                if bumped_ref in bumped_event_refs:
                    continue  # Already processed this bumped event
                
                bumped_event_refs.add(bumped_ref)
                
                current_app.logger.info(f"Executing bump for event {bumped_ref}")
                
                # 1. Delete superseded PendingSchedule records for the bumped event
                superseded_pending = db.session.query(models['PendingSchedule']).filter(
                    models['PendingSchedule'].scheduler_run_id == run_id,
                    models['PendingSchedule'].event_ref_num == bumped_ref,
                    models['PendingSchedule'].status == 'superseded'
                ).all()
                
                for sup_pending in superseded_pending:
                    current_app.logger.info(
                        f"  Deleting superseded pending schedule for event {bumped_ref}"
                    )
                    db.session.delete(sup_pending)
                
                # 2. Delete any posted Schedule records for the bumped event
                # (These might exist from previous approved runs)
                posted_schedules = db.session.query(models['Schedule']).filter(
                    models['Schedule'].event_ref_num == bumped_ref
                ).all()
                
                scheduled_dates = set()  # Track dates for supervisor deletion
                for posted_schedule in posted_schedules:
                    current_app.logger.info(
                        f"  Deleting posted schedule for event {bumped_ref} "
                        f"(was scheduled to {posted_schedule.employee_id} at {posted_schedule.schedule_datetime})"
                    )
                    scheduled_dates.add(posted_schedule.schedule_datetime.date())
                    db.session.delete(posted_schedule)
                
                # 3. Delete matching Supervisor events (both pending and posted)
                bumped_event = db.session.query(models['Event']).filter_by(
                    project_ref_num=bumped_ref
                ).first()
                
                if bumped_event and bumped_event.event_type == 'Core':
                    # Extract event number to find matching Supervisor events
                    import re
                    match = re.search(r'\d{6}', bumped_event.project_name)
                    core_event_number = match.group(0) if match else None
                    
                    if core_event_number:
                        # Delete matching Supervisor pending schedules
                        supervisor_pending = db.session.query(models['PendingSchedule']).join(
                            models['Event'], models['PendingSchedule'].event_ref_num == models['Event'].project_ref_num
                        ).filter(
                            models['PendingSchedule'].scheduler_run_id == run_id,
                            models['Event'].event_type == 'Supervisor',
                            models['Event'].project_name.contains(core_event_number)
                        ).all()
                        
                        for sup_pending in supervisor_pending:
                            current_app.logger.info(
                                f"  Deleting matching Supervisor pending schedule {sup_pending.event_ref_num}"
                            )
                            db.session.delete(sup_pending)
                        
                        # Delete matching Supervisor posted schedules (for the dates that were scheduled)
                        for scheduled_date in scheduled_dates:
                            supervisor_posted = db.session.query(models['Schedule']).join(
                                models['Event'], models['Schedule'].event_ref_num == models['Event'].project_ref_num
                            ).filter(
                                models['Event'].event_type == 'Supervisor',
                                models['Event'].project_name.contains(core_event_number),
                                func.date(models['Schedule'].schedule_datetime) == scheduled_date
                            ).all()
                            
                            for sup_posted in supervisor_posted:
                                current_app.logger.info(
                                    f"  Deleting matching Supervisor posted schedule {sup_posted.event_ref_num}"
                                )
                                db.session.delete(sup_posted)
                
                # 4. Set the bumped event's is_scheduled flag to False
                if bumped_event:
                    bumped_event.is_scheduled = False
                    current_app.logger.info(f"  Set event {bumped_ref} is_scheduled=False")
            
            # Commit the bump deletions before proceeding with approvals
            db.session.flush()
            current_app.logger.info("Completed processing all bumps")
    
    except Exception as bump_error:
        db.session.rollback()
        current_app.logger.error(f"Failed to process bumps: {str(bump_error)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to process bumped events: {str(bump_error)}'
        }), 500

    api_submitted = 0
    api_failed = 0
    failed_details = []

    try:
        # Filter out superseded schedules - only process valid schedules
        for pending in pending_schedules:
            # Skip superseded schedules - they were bumped and should not be approved
            if pending.status == 'superseded':
                continue
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
                    models = get_models()
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
                models = get_models()
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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']

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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']

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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']

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
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']

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


@auto_scheduler_bp.route('/history')
@require_authentication()
def history():
    """Page showing all scheduler run history with scheduled events"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']

    # Get all scheduler runs, ordered by date descending
    runs = db.session.query(SchedulerRunHistory).order_by(
        SchedulerRunHistory.started_at.desc()
    ).limit(50).all()

    # Calculate event type counts for each run
    runs_data = []
    for run in runs:
        # Get event type counts for this run
        pending_schedules = db.session.query(PendingSchedule).filter_by(
            scheduler_run_id=run.id
        ).filter(PendingSchedule.failure_reason.is_(None)).all()

        type_counts = {}
        for ps in pending_schedules:
            event = db.session.query(Event).filter_by(
                project_ref_num=ps.event_ref_num
            ).first()
            if event:
                event_type = event.event_type or 'Other'
                type_counts[event_type] = type_counts.get(event_type, 0) + 1

        runs_data.append({
            'run': run,
            'type_counts': type_counts
        })

    return render_template('scheduler_history.html', runs_data=runs_data)


@auto_scheduler_bp.route('/api/history/<int:run_id>')
@require_authentication()
def get_run_history(run_id):
    """Get detailed event list for a specific scheduler run

    Query Parameters:
        status: Filter by status - 'all' (default), 'failed', 'scheduled'
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']
    Employee = models['Employee']

    # Get the run
    run = db.session.query(SchedulerRunHistory).get(run_id)
    if not run:
        return jsonify({'success': False, 'error': 'Run not found'}), 404

    # Get status filter parameter
    status_filter = request.args.get('status', 'all')

    # Build query for pending schedules
    query = db.session.query(PendingSchedule).filter_by(scheduler_run_id=run_id)

    # Apply status filter
    if status_filter == 'failed':
        query = query.filter(PendingSchedule.failure_reason.isnot(None))
    elif status_filter == 'scheduled':
        query = query.filter(PendingSchedule.failure_reason.is_(None))
    # 'all' applies no filter

    pending_schedules = query.all()

    events_data = []
    for ps in pending_schedules:
        event = db.session.query(Event).filter_by(
            project_ref_num=ps.event_ref_num
        ).first()
        employee = db.session.query(Employee).get(ps.employee_id) if ps.employee_id else None

        events_data.append({
            'event_ref_num': ps.event_ref_num,
            'event_name': event.project_name if event else 'Unknown',
            'event_type': event.event_type if event else 'Unknown',
            'employee_name': employee.name if employee else 'Unassigned',
            'scheduled_time': ps.schedule_datetime.strftime('%Y-%m-%d %I:%M %p') if ps.schedule_datetime else None,
            'start_date': event.start_datetime.strftime('%Y-%m-%d') if event and event.start_datetime else None,
            'due_date': event.due_datetime.strftime('%Y-%m-%d') if event and event.due_datetime else None,
            'status': 'failed' if ps.failure_reason else 'scheduled',
            'failure_reason': ps.failure_reason
        })

    # Get counts for all statuses (for filter buttons)
    all_count = db.session.query(PendingSchedule).filter_by(scheduler_run_id=run_id).count()
    failed_count = db.session.query(PendingSchedule).filter_by(
        scheduler_run_id=run_id
    ).filter(PendingSchedule.failure_reason.isnot(None)).count()
    scheduled_count = db.session.query(PendingSchedule).filter_by(
        scheduler_run_id=run_id
    ).filter(PendingSchedule.failure_reason.is_(None)).count()

    return jsonify({
        'success': True,
        'run': {
            'id': run.id,
            'run_type': run.run_type,
            'started_at': run.started_at.strftime('%Y-%m-%d %I:%M %p'),
            'completed_at': run.completed_at.strftime('%Y-%m-%d %I:%M %p') if run.completed_at else None,
            'status': run.status,
            'total_events_processed': run.total_events_processed,
            'events_scheduled': run.events_scheduled,
            'events_failed': run.events_failed,
            'approved_at': run.approved_at.strftime('%Y-%m-%d %I:%M %p') if run.approved_at else None
        },
        'events': events_data,
        'counts': {
            'all': all_count,
            'scheduled': scheduled_count,
            'failed': failed_count
        },
        'current_filter': status_filter
    })


@auto_scheduler_bp.route('/api/history/<int:run_id>/export')
@require_authentication()
def export_run_history(run_id):
    """Export scheduler run events to CSV

    Query Parameters:
        status: Filter by status - 'all' (default), 'failed', 'scheduled'
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']
    Employee = models['Employee']

    # Get the run
    run = db.session.query(SchedulerRunHistory).get(run_id)
    if not run:
        return jsonify({'success': False, 'error': 'Run not found'}), 404

    # Get status filter parameter
    status_filter = request.args.get('status', 'all')

    # Build query for pending schedules
    query = db.session.query(PendingSchedule).filter_by(scheduler_run_id=run_id)

    # Apply status filter
    if status_filter == 'failed':
        query = query.filter(PendingSchedule.failure_reason.isnot(None))
    elif status_filter == 'scheduled':
        query = query.filter(PendingSchedule.failure_reason.is_(None))

    pending_schedules = query.all()

    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)

    # Write header row
    writer.writerow([
        'Event Name',
        'Event Type',
        'Employee',
        'Scheduled Date',
        'Event Period',
        'Status',
        'Failure Reason'
    ])

    # Write data rows
    for ps in pending_schedules:
        event = db.session.query(Event).filter_by(
            project_ref_num=ps.event_ref_num
        ).first()
        employee = db.session.query(Employee).get(ps.employee_id) if ps.employee_id else None

        # Determine status
        status = 'Failed' if ps.failure_reason else 'Scheduled'

        # Format event period
        event_period = ''
        if event and event.start_datetime and event.due_datetime:
            event_period = f"{event.start_datetime.strftime('%Y-%m-%d')} to {event.due_datetime.strftime('%Y-%m-%d')}"

        writer.writerow([
            event.project_name if event else 'Unknown',
            event.event_type if event else 'Unknown',
            employee.name if employee else 'Unassigned',
            ps.schedule_datetime.strftime('%Y-%m-%d %I:%M %p') if ps.schedule_datetime else '',
            event_period,
            status,
            ps.failure_reason or ''
        ])

    # Prepare response
    output.seek(0)
    filename = f'scheduler_run_{run_id}_{status_filter}.csv'

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


@auto_scheduler_bp.route('/api/review/export')
@require_authentication()
def export_review_category():
    """Export auto-schedule review category to CSV

    Query Parameters:
        run_id: Scheduler run ID (optional, defaults to latest unapproved run)
        category: Category to export - 'newly_scheduled', 'swaps', 'failed', or 'all' (default)
    """
    import re
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    SchedulerRunHistory = models['SchedulerRunHistory']
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']
    Employee = models['Employee']

    run_id = request.args.get('run_id', type=int)
    category = request.args.get('category', 'all')

    # Get the run
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

    for ps in pending:
        event = db.session.query(Event).filter_by(project_ref_num=ps.event_ref_num).first()
        employee = db.session.query(Employee).get(ps.employee_id) if ps.employee_id else None

        ps_data = {
            'event_ref_num': ps.event_ref_num,
            'event_name': event.project_name if event else 'Unknown',
            'event_type': event.event_type if event else 'Unknown',
            'start_date': event.start_datetime.strftime('%m/%d/%Y') if event and event.start_datetime else '',
            'end_date': event.due_datetime.strftime('%m/%d/%Y') if event and event.due_datetime else '',
            'employee_name': employee.name if employee else 'Unassigned',
            'schedule_datetime': ps.schedule_datetime.strftime('%m/%d/%Y %I:%M %p') if ps.schedule_datetime else '',
            'is_swap': ps.is_swap,
            'swap_reason': ps.swap_reason or '',
            'failure_reason': ps.failure_reason or '',
            'bumped_event_name': '',
            'bumped_rescheduled_to': ''
        }

        if ps.failure_reason:
            failed.append(ps_data)
        elif ps.is_swap:
            # Get bumped event details
            if ps.bumped_event_ref_num:
                bumped_event = db.session.query(Event).filter_by(project_ref_num=ps.bumped_event_ref_num).first()
                ps_data['bumped_event_name'] = bumped_event.project_name if bumped_event else 'Unknown'

                # Find where the bumped event is being rescheduled to
                bumped_reschedule = db.session.query(PendingSchedule).filter(
                    PendingSchedule.scheduler_run_id == run.id,
                    PendingSchedule.event_ref_num == ps.bumped_event_ref_num,
                    PendingSchedule.status != 'superseded',
                    PendingSchedule.failure_reason.is_(None)
                ).first()

                if bumped_reschedule:
                    bumped_employee = db.session.query(Employee).get(bumped_reschedule.employee_id) if bumped_reschedule.employee_id else None
                    ps_data['bumped_rescheduled_to'] = f"{bumped_employee.name if bumped_employee else 'Unassigned'} on {bumped_reschedule.schedule_datetime.strftime('%m/%d/%Y %I:%M %p') if bumped_reschedule.schedule_datetime else 'N/A'}"
                else:
                    ps_data['bumped_rescheduled_to'] = 'Failed to reschedule'
            swaps.append(ps_data)
        else:
            newly_scheduled.append(ps_data)

    # Create CSV based on category
    output = StringIO()
    writer = csv.writer(output)

    if category == 'newly_scheduled':
        writer.writerow([
            'Event Number', 'Event Name', 'Event Type', 'Event Period',
            'Assigned To', 'Scheduled For'
        ])
        for ps in newly_scheduled:
            writer.writerow([
                ps['event_ref_num'],
                ps['event_name'],
                ps['event_type'],
                f"{ps['start_date']} - {ps['end_date']}",
                ps['employee_name'],
                ps['schedule_datetime']
            ])
        filename = f'review_newly_scheduled_run_{run.id}.csv'

    elif category == 'swaps':
        writer.writerow([
            'Event Number', 'Event Name', 'Event Type', 'Event Period',
            'Assigned To', 'Scheduled For', 'Bumping Event', 'Bumped Event Rescheduled To'
        ])
        for ps in swaps:
            writer.writerow([
                ps['event_ref_num'],
                ps['event_name'],
                ps['event_type'],
                f"{ps['start_date']} - {ps['end_date']}",
                ps['employee_name'],
                ps['schedule_datetime'],
                ps['bumped_event_name'],
                ps['bumped_rescheduled_to']
            ])
        filename = f'review_swaps_run_{run.id}.csv'

    elif category == 'failed':
        writer.writerow([
            'Event Number', 'Event Name', 'Event Type', 'Event Period', 'Failure Reason'
        ])
        for ps in failed:
            writer.writerow([
                ps['event_ref_num'],
                ps['event_name'],
                ps['event_type'],
                f"{ps['start_date']} - {ps['end_date']}",
                ps['failure_reason']
            ])
        filename = f'review_failed_run_{run.id}.csv'

    else:  # all
        writer.writerow([
            'Category', 'Event Number', 'Event Name', 'Event Type', 'Event Period',
            'Assigned To', 'Scheduled For', 'Bumped Event', 'Bumped Rescheduled To', 'Failure Reason'
        ])
        for ps in newly_scheduled:
            writer.writerow([
                'Newly Scheduled',
                ps['event_ref_num'],
                ps['event_name'],
                ps['event_type'],
                f"{ps['start_date']} - {ps['end_date']}",
                ps['employee_name'],
                ps['schedule_datetime'],
                '',
                '',
                ''
            ])
        for ps in swaps:
            writer.writerow([
                'Swap/Bump',
                ps['event_ref_num'],
                ps['event_name'],
                ps['event_type'],
                f"{ps['start_date']} - {ps['end_date']}",
                ps['employee_name'],
                ps['schedule_datetime'],
                ps['bumped_event_name'],
                ps['bumped_rescheduled_to'],
                ''
            ])
        for ps in failed:
            writer.writerow([
                'Failed',
                ps['event_ref_num'],
                ps['event_name'],
                ps['event_type'],
                f"{ps['start_date']} - {ps['end_date']}",
                '',
                '',
                '',
                '',
                ps['failure_reason']
            ])
        filename = f'review_all_run_{run.id}.csv'

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )

