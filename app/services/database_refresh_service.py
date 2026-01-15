"""
Database Refresh Service with Progress Tracking
Handles fetching events from Crossmark API and updating the local database
"""
from datetime import datetime
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class DatabaseRefreshService:
    """Service to refresh database with progress callbacks"""

    STEP_FETCHING = 1
    STEP_CLEARING = 2
    STEP_PROCESSING = 3
    STEP_SCHEDULES = 4
    STEP_FINALIZING = 5
    TOTAL_STEPS = 5

    def __init__(self, progress_callback=None):
        """
        Initialize the service with optional progress callback

        Args:
            progress_callback: Function to call with progress updates.
                              Signature: callback(step, step_label, processed=0, total=0, status='running')
        """
        self.progress_callback = progress_callback

    def _update_progress(self, step, step_label, processed=0, total=0, status='running', stats=None, error=None):
        """Send progress update if callback is set"""
        if self.progress_callback:
            self.progress_callback(
                current_step=step,
                total_steps=self.TOTAL_STEPS,
                step_label=step_label,
                processed=processed,
                total=total,
                status=status,
                stats=stats,
                error=error
            )

    def refresh(self):
        """
        Perform full database refresh with progress tracking

        Returns:
            dict: Result with success status, message, and stats
        """
        try:
            from app.integrations.external_api.session_api_service import session_api as external_api
            from app.utils.db_compat import disable_foreign_keys

            db = current_app.extensions['sqlalchemy']
            Event = current_app.config['Event']
            Schedule = current_app.config['Schedule']
            Employee = current_app.config['Employee']

            # Step 1: Fetching events from API
            self._update_progress(
                self.STEP_FETCHING,
                'Fetching events from Crossmark API'
            )

            current_app.logger.info("Starting database refresh from Crossmark API")
            events_data = external_api.get_all_planning_events()

            if not events_data:
                self._update_progress(
                    self.STEP_FETCHING,
                    'Failed to fetch events',
                    status='error',
                    error='Failed to fetch events from Crossmark API'
                )
                return {
                    'success': False,
                    'message': 'Failed to fetch events from Crossmark API'
                }

            records = events_data.get('mplans', [])
            total_fetched = len(records)

            self._update_progress(
                self.STEP_FETCHING,
                'Fetching events from Crossmark API',
                processed=total_fetched,
                total=total_fetched
            )

            # Step 2: Clearing existing data
            self._update_progress(
                self.STEP_CLEARING,
                'Clearing existing data',
                total=total_fetched
            )

            current_app.logger.info("Clearing all existing events from database")
            existing_count = Event.query.count()

            with disable_foreign_keys(db.session):
                # Clear auto scheduler results if table exists
                try:
                    from models.auto_scheduler import AutoSchedulerResult
                    AutoSchedulerResult.query.delete()
                except (ImportError, AttributeError):
                    pass

                Schedule.query.delete()
                Event.query.delete()
                db.session.commit()

            current_app.logger.info(f"Cleared {existing_count} existing events")

            # Step 3: Processing events
            self._update_progress(
                self.STEP_PROCESSING,
                'Processing events',
                processed=0,
                total=total_fetched
            )

            created_count = 0
            schedule_count = 0

            for i, event_record in enumerate(records):
                try:
                    event, schedule_created = self._process_event(
                        event_record, db, Event, Schedule, Employee
                    )
                    if event:
                        created_count += 1
                    if schedule_created:
                        schedule_count += 1

                except Exception as e:
                    current_app.logger.error(
                        f"Error processing event {event_record.get('mPlanID', 'unknown')}: {e}"
                    )
                    continue

                # Update progress every 50 events
                if (i + 1) % 50 == 0 or i == len(records) - 1:
                    self._update_progress(
                        self.STEP_PROCESSING,
                        'Processing events',
                        processed=i + 1,
                        total=total_fetched
                    )

            # Step 4: Creating schedules (already done in step 3, but keeping for progress display)
            self._update_progress(
                self.STEP_SCHEDULES,
                'Creating schedules',
                processed=schedule_count,
                total=schedule_count
            )

            # Step 5: Finalizing
            self._update_progress(
                self.STEP_FINALIZING,
                'Finalizing'
            )

            db.session.commit()

            # Check for staffed events without schedules
            from sqlalchemy import select
            staffed_without_schedule = Event.query.filter(
                Event.condition == 'Staffed',
                ~Event.project_ref_num.in_(select(Schedule.event_ref_num))
            ).count()

            warning_message = None
            if staffed_without_schedule:
                warning_message = f"{staffed_without_schedule} events are marked as 'Staffed' but have no schedule records."

            stats = {
                'total_fetched': total_fetched,
                'cleared': existing_count,
                'created': created_count,
                'schedules': schedule_count
            }

            current_app.logger.info(
                f"Database refresh completed: Cleared {existing_count}, created {created_count} events, {schedule_count} schedules"
            )

            self._update_progress(
                self.STEP_FINALIZING,
                'Complete',
                processed=total_fetched,
                total=total_fetched,
                status='completed',
                stats=stats
            )

            return {
                'success': True,
                'message': 'Database refreshed successfully',
                'stats': stats,
                'warning': warning_message
            }

        except Exception as e:
            import traceback
            error_msg = str(e)
            current_app.logger.error(f"Database refresh failed: {error_msg}")
            current_app.logger.error(traceback.format_exc())

            try:
                db = current_app.extensions['sqlalchemy']
                db.session.rollback()
            except:
                pass

            self._update_progress(
                self.STEP_PROCESSING,
                'Error occurred',
                status='error',
                error=error_msg
            )

            return {
                'success': False,
                'message': f'Database refresh failed: {error_msg}'
            }

    def _process_event(self, event_record, db, Event, Schedule, Employee):
        """
        Process a single event record from the API

        Returns:
            tuple: (event_created, schedule_created) booleans
        """
        mplan_id = event_record.get('mPlanID')
        if not mplan_id:
            return None, False

        # Parse dates
        start_date = self._parse_date(event_record.get('startDate'), '%m/%d/%Y')
        end_date = self._parse_date(event_record.get('endDate'), '%m/%d/%Y')
        schedule_date = self._parse_date(
            event_record.get('scheduleDate'),
            '%m/%d/%Y %I:%M:%S %p'
        )

        if not start_date:
            start_date = datetime.utcnow()
        if not end_date:
            end_date = datetime.utcnow()

        condition = event_record.get('condition', 'Unstaffed')
        is_event_scheduled = (condition != 'Unstaffed') or (schedule_date is not None)

        # Extract SalesToolURL
        sales_tools_url = None
        sales_tools = event_record.get('salesTools', [])
        if sales_tools and isinstance(sales_tools, list) and len(sales_tools) > 0:
            if isinstance(sales_tools[0], dict):
                sales_tools_url = sales_tools[0].get('salesToolURL')

        # Create event
        new_event = Event(
            external_id=str(mplan_id),
            project_name=event_record.get('name', ''),
            project_ref_num=int(mplan_id) if str(mplan_id).isdigit() else 0,
            location_mvid=event_record.get('storeID', ''),
            store_name=event_record.get('storeName', ''),
            start_datetime=start_date,
            due_datetime=end_date,
            is_scheduled=is_event_scheduled,
            condition=condition,
            sales_tools_url=sales_tools_url,
            last_synced=datetime.utcnow(),
            sync_status='synced'
        )
        new_event.event_type = new_event.detect_event_type()
        db.session.add(new_event)

        # Create schedule if applicable
        schedule_created = False
        if schedule_date and is_event_scheduled:
            employee = self._find_employee(event_record, Employee)
            if employee:
                scheduled_event_id = event_record.get('scheduleEventID')
                schedule = Schedule(
                    event_ref_num=int(mplan_id) if str(mplan_id).isdigit() else 0,
                    employee_id=employee.id,
                    schedule_datetime=schedule_date,
                    external_id=str(scheduled_event_id) if scheduled_event_id else None,
                    last_synced=datetime.utcnow(),
                    sync_status='synced'
                )
                db.session.add(schedule)
                schedule_created = True

        return new_event, schedule_created

    def _parse_date(self, date_str, format_str):
        """Parse date string, return None on failure"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, format_str)
        except ValueError:
            return None

    def _find_employee(self, event_record, Employee):
        """Find employee by name or RepID"""
        staffed_reps = event_record.get('staffedReps', '')
        schedule_rep_id = event_record.get('scheduleRepID', '')

        if staffed_reps:
            first_rep_name = staffed_reps.split(',')[0].strip()
            employee = Employee.query.filter_by(name=first_rep_name).first()
            if employee:
                return employee

        if schedule_rep_id:
            employee = Employee.query.filter_by(external_id=str(schedule_rep_id)).first()
            if employee:
                return employee

        return None


def refresh_database_with_progress(task_id):
    """
    Convenience function to refresh database with Redis progress tracking

    Args:
        task_id: Redis task ID for progress storage

    Returns:
        dict: Refresh result
    """
    from app.routes.auth import update_refresh_progress

    def progress_callback(**kwargs):
        update_refresh_progress(task_id, **kwargs)

    service = DatabaseRefreshService(progress_callback=progress_callback)
    return service.refresh()
