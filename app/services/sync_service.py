"""
Background sync service for Crossmark API integration
Handles asynchronous synchronization of schedules, employees, and events
"""
import logging
from datetime import datetime, timedelta
from celery import Celery, Task
from flask import Flask

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    'scheduler_sync',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minute soft limit
    broker_connection_retry_on_startup=True,
)


class FlaskTask(Task):
    """Custom Celery task that runs within Flask app context"""
    _app = None

    def __call__(self, *args, **kwargs):
        if self._app is None:
            from app import app as flask_app
            self._app = flask_app

        with self._app.app_context():
            return super().__call__(*args, **kwargs)


celery_app.Task = FlaskTask


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def sync_schedule_to_crossmark(self, schedule_id):
    """
    Background task to sync a schedule to Crossmark API
    Automatically retries on failure with exponential backoff

    Args:
        schedule_id: ID of the schedule to sync

    Returns:
        dict: Result of the sync operation
    """
    try:
        from app import db, Schedule, Event, Employee
        from app.integrations.external_api.session_api_service import session_api as external_api

        logger.info(f"Starting background sync for schedule {schedule_id}")

        # Get the schedule
        schedule = db.session.get(Schedule, schedule_id)
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return {'success': False, 'message': 'Schedule not found'}

        # Get related event and employee
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        employee = Employee.query.filter_by(id=schedule.employee_id).first()

        if not event or not employee:
            logger.error(f"Missing related data for schedule {schedule_id}")
            return {'success': False, 'message': 'Missing event or employee data'}

        # Map employee name to Crossmark RepID
        employee_to_repid = {
            'MAT CONDER': '152052',
            'DIANE CARR': '19461',
            'BRANDY CREASEY': '157632',
            'NANCY DINKINS': '141359',
            'MELISSA MCINTOSH': '141359',
            'KRISSY TAYLOR': '184862',
            'BETH DAVIS': '188743'
        }

        employee_name = employee.name.upper()
        rep_id = employee_to_repid.get(employee_name)

        if not rep_id:
            logger.error(f"No Crossmark RepID found for employee: {employee_name}")
            return {'success': False, 'message': f'No Crossmark RepID mapping found for {employee_name}'}

        logger.info(f"Using Crossmark RepID {rep_id} for employee {employee_name}")

        # Call Crossmark API to schedule the event
        # Calculate end datetime based on event's estimated time or event type default
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = schedule.schedule_datetime + timedelta(minutes=estimated_minutes)

        api_result = external_api.schedule_mplan_event(
            rep_id=rep_id,
            mplan_id=event.external_id,
            location_id=event.location_mvid or '157384',
            start_datetime=schedule.schedule_datetime,
            end_datetime=end_datetime
        )

        if api_result.get('success'):
            # Update schedule sync status
            schedule.sync_status = 'synced'
            schedule.last_synced = datetime.utcnow()
            db.session.commit()

            logger.info(f"Successfully synced schedule {schedule_id} to Crossmark")
            return {'success': True, 'message': 'Schedule synced successfully'}
        else:
            # API call failed, mark as failed and retry
            schedule.sync_status = 'failed'
            db.session.commit()

            error_msg = api_result.get('message', 'Unknown error')
            logger.warning(f"Failed to sync schedule {schedule_id}: {error_msg}")

            # Retry with exponential backoff
            raise self.retry(exc=Exception(error_msg), countdown=60 * (2 ** self.request.retries))

    except Exception as exc:
        logger.error(f"Exception during schedule sync {schedule_id}: {str(exc)}")

        # Mark as failed in database
        try:
            from app import db, Schedule
            schedule = db.session.get(Schedule, schedule_id)
            if schedule:
                schedule.sync_status = 'failed'
                db.session.commit()
        except:
            pass

        # Retry if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        else:
            return {'success': False, 'message': f'Failed after {self.max_retries} retries: {str(exc)}'}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def sync_schedule_update_to_crossmark(self, schedule_id, new_employee_id=None, new_datetime=None):
    """
    Background task to sync schedule updates (employee change, reschedule) to Crossmark API

    Args:
        schedule_id: ID of the schedule to update
        new_employee_id: New employee ID (if changing employee)
        new_datetime: New datetime (if rescheduling)

    Returns:
        dict: Result of the sync operation
    """
    try:
        from app import db, Schedule, Event, Employee
        from app.integrations.external_api.session_api_service import session_api as external_api

        logger.info(f"Starting background sync update for schedule {schedule_id}")

        # Get the schedule
        schedule = db.session.get(Schedule, schedule_id)
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return {'success': False, 'message': 'Schedule not found'}

        # Get related event
        event = Event.query.filter_by(project_ref_num=schedule.event_ref_num).first()
        if not event:
            logger.error(f"Event not found for schedule {schedule_id}")
            return {'success': False, 'message': 'Event not found'}

        # Determine which employee to use
        employee_id = new_employee_id if new_employee_id else schedule.employee_id
        employee = Employee.query.filter_by(id=employee_id).first()

        if not employee:
            logger.error(f"Employee {employee_id} not found")
            return {'success': False, 'message': 'Employee not found'}

        # Determine which datetime to use
        schedule_datetime = new_datetime if new_datetime else schedule.schedule_datetime

        # Map employee name to Crossmark RepID
        employee_to_repid = {
            'MAT CONDER': '152052',
            'DIANE CARR': '19461',
            'BRANDY CREASEY': '157632',
            'NANCY DINKINS': '141359',
            'MELISSA MCINTOSH': '141359',
            'KRISSY TAYLOR': '184862',
            'BETH DAVIS': '188743'
        }

        employee_name = employee.name.upper()
        rep_id = employee_to_repid.get(employee_name)

        if not rep_id:
            logger.error(f"No Crossmark RepID found for employee: {employee_name}")
            return {'success': False, 'message': f'No Crossmark RepID mapping found for {employee_name}'}

        logger.info(f"Updating schedule in Crossmark: RepID {rep_id}, mPlanID {event.external_id}")

        # Call Crossmark API to update the scheduled event
        # Calculate end datetime based on event's estimated time or event type default
        estimated_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = schedule_datetime + timedelta(minutes=estimated_minutes)

        api_result = external_api.schedule_mplan_event(
            rep_id=rep_id,
            mplan_id=event.external_id,
            location_id=event.location_mvid or '157384',
            start_datetime=schedule_datetime,
            end_datetime=end_datetime
        )

        if api_result.get('success'):
            # Update schedule sync status
            schedule.sync_status = 'synced'
            schedule.last_synced = datetime.utcnow()
            db.session.commit()

            logger.info(f"Successfully synced schedule update {schedule_id} to Crossmark")
            return {'success': True, 'message': 'Schedule update synced successfully'}
        else:
            error_msg = api_result.get('message', 'Unknown error')
            logger.warning(f"Failed to sync schedule update {schedule_id}: {error_msg}")
            raise self.retry(exc=Exception(error_msg), countdown=60 * (2 ** self.request.retries))

    except Exception as exc:
        logger.error(f"Exception during schedule update sync {schedule_id}: {str(exc)}")

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        else:
            return {'success': False, 'message': f'Failed after {self.max_retries} retries: {str(exc)}'}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def sync_schedule_deletion_to_crossmark(self, external_id):
    """
    Background task to sync schedule deletion to Crossmark API

    Args:
        external_id: External ID (mPlanID) of the schedule to delete

    Returns:
        dict: Result of the sync operation
    """
    try:
        from app.integrations.external_api.session_api_service import session_api as external_api

        logger.info(f"Starting background sync deletion for external_id {external_id}")

        # Call Crossmark API to delete/unschedule the event
        api_result = external_api.delete_schedule(external_id)

        if api_result.get('success'):
            logger.info(f"Successfully unscheduled event {external_id} from Crossmark")
            return {'success': True, 'message': 'Schedule deletion synced successfully'}
        else:
            error_msg = api_result.get('message', 'Unknown error')
            logger.warning(f"Failed to unschedule event {external_id}: {error_msg}")
            raise self.retry(exc=Exception(error_msg), countdown=60 * (2 ** self.request.retries))

    except Exception as exc:
        logger.error(f"Exception during schedule deletion sync {external_id}: {str(exc)}")

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        else:
            return {'success': False, 'message': f'Failed after {self.max_retries} retries: {str(exc)}'}


@celery_app.task
def sync_employee_to_crossmark(employee_id):
    """
    Background task to sync employee changes to Crossmark API

    Args:
        employee_id: ID of the employee to sync

    Returns:
        dict: Result of the sync operation
    """
    try:
        from app import db, Employee
        from sync_engine import sync_engine

        logger.info(f"Starting background employee sync for {employee_id}")

        employee = db.session.get(Employee, employee_id)
        if not employee:
            logger.error(f"Employee {employee_id} not found")
            return {'success': False, 'message': 'Employee not found'}

        # Use existing sync engine method
        if sync_engine._sync_employee_to_external(employee):
            logger.info(f"Successfully synced employee {employee_id} to Crossmark")
            return {'success': True, 'message': 'Employee synced successfully'}
        else:
            return {'success': False, 'message': 'Employee sync failed'}

    except Exception as exc:
        logger.error(f"Exception during employee sync {employee_id}: {str(exc)}")
        return {'success': False, 'message': str(exc)}


@celery_app.task
def refresh_events_from_crossmark():
    """
    Periodic task to refresh events from Crossmark API
    This should be run periodically (e.g., every hour) to keep data fresh

    Returns:
        dict: Result of the refresh operation
    """
    try:
        from app import app, db, Event
        from app.integrations.external_api.session_api_service import session_api as external_api

        logger.info("Starting periodic event refresh from Crossmark")

        # Get all planning events
        events_data = external_api.get_all_planning_events()

        if not events_data:
            logger.warning("No events data received from Crossmark API")
            return {'success': False, 'message': 'No events data received'}

        # Process events
        records = events_data.get('mplans', [])
        created_count = 0
        updated_count = 0

        for record in records:
            try:
                external_id = str(record.get('mPlanID', ''))

                # Check if event already exists
                existing_event = Event.query.filter_by(external_id=external_id).first()

                if existing_event:
                    # Update existing event if needed
                    # (Add update logic here if needed)
                    updated_count += 1
                else:
                    # Create new event
                    # (Add creation logic here using sync_engine methods)
                    created_count += 1

            except Exception as e:
                logger.error(f"Error processing event: {str(e)}")
                continue

        logger.info(f"Event refresh completed: {created_count} created, {updated_count} updated")
        return {
            'success': True,
            'message': f'Refreshed events: {created_count} created, {updated_count} updated'
        }

    except Exception as exc:
        logger.error(f"Exception during event refresh: {str(exc)}")
        return {'success': False, 'message': str(exc)}


# Periodic task schedule configuration
celery_app.conf.beat_schedule = {
    'refresh-events-every-hour': {
        'task': 'services.sync_service.refresh_events_from_crossmark',
        'schedule': 3600.0,  # Run every hour
    },
}
