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

    STEP_FETCHING = 1        # Fetching events from API (parallel chunks)
    STEP_FETCHING_TIMES = 2  # Fetching estimated times from scheduling API
    STEP_CLEARING = 3
    STEP_PROCESSING = 4
    STEP_SCHEDULES = 5
    STEP_FINALIZING = 6
    TOTAL_STEPS = 6

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
            from app.models import get_models

            db = current_app.extensions['sqlalchemy']
            models = get_models()
            Event = models['Event']
            Schedule = models['Schedule']
            Employee = models['Employee']

            # Step 1: Fetching events from API
            self._update_progress(
                self.STEP_FETCHING,
                'Pulling events',
                processed=0,
                total=100
            )

            current_app.logger.info("Starting database refresh from Crossmark API")

            # Create progress callback for API fetch
            def api_progress_callback(percent, status):
                """Report API fetch progress as part of STEP_FETCHING"""
                self._update_progress(
                    self.STEP_FETCHING,
                    'Pulling events',
                    processed=percent,
                    total=100
                )

            # Use PARALLEL fetching for 4.5x speed improvement (~41s vs ~185s)
            events_data = external_api.get_all_planning_events_parallel(progress_callback=api_progress_callback)

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

            # Handle different API response structures:
            # - 'mplans' key from planning controller
            # - 'events' key from scheduled events endpoint
            # - 'records' key from some endpoints
            records = (events_data.get('mplans') or
                       events_data.get('events') or
                       events_data.get('records') or [])
            total_fetched = len(records)

            # Step 2: Fetch EstimatedTime from scheduling endpoints (planning API doesn't include it)
            # Build a lookup map: mPlanID -> EstimatedTime
            self._update_progress(
                self.STEP_FETCHING_TIMES,
                'Fetching event times from scheduling API',
                processed=0,
                total=100
            )
            estimated_time_map = self._fetch_estimated_times(external_api)
            current_app.logger.info(f"Fetched EstimatedTime for {len(estimated_time_map)} events from scheduling API")
            self._update_progress(
                self.STEP_FETCHING_TIMES,
                'Fetching event times from scheduling API',
                processed=100,
                total=100
            )


            # Step 3: Clearing existing data
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

            # Step 4: Processing events
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
                        event_record, db, Event, Schedule, Employee, estimated_time_map
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

                # Update progress every 10 events for smoother visual feedback
                if (i + 1) % 10 == 0 or i == len(records) - 1:
                    self._update_progress(
                        self.STEP_PROCESSING,
                        'Processing events',
                        processed=i + 1,
                        total=total_fetched
                    )

            # Step 5: Creating schedules (already done in step 4, but keeping for progress display)
            self._update_progress(
                self.STEP_SCHEDULES,
                'Creating schedules',
                processed=schedule_count,
                total=schedule_count
            )

            # Step 6: Finalizing
            self._update_progress(
                self.STEP_FINALIZING,
                'Finalizing'
            )

            db.session.commit()
            
            # Post-import fix: Correct truncated event types using pairing logic
            # Events with 100-char names have their type suffix cut off
            truncated_fixed = self._fix_truncated_event_types(db, Event)
            if truncated_fixed > 0:
                current_app.logger.info(f"Fixed {truncated_fixed} truncated event types using pairing logic")

            # Reapply event type overrides after import
            overrides_applied = self._reapply_event_type_overrides(db, Event)
            if overrides_applied > 0:
                current_app.logger.info(f"Reapplied {overrides_applied} event type overrides")

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

    def _fetch_estimated_times(self, external_api):
        """
        Fetch EstimatedTime values from scheduling endpoints.
        
        The planning API doesn't return EstimatedTime, but the scheduling
        endpoints do. We fetch both scheduled and non-scheduled visits
        and build a lookup map.
        
        Returns:
            dict: Mapping of mPlanID -> EstimatedTime (in minutes)
        """
        from datetime import timedelta
        
        estimated_time_map = {}
        
        try:
            # Fetch from scheduled events (4 month window)
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now() + timedelta(days=120)
            
            # Get scheduled events with EstimatedTime
            scheduled = external_api.get_scheduled_events(start_date, end_date)
            if scheduled:
                events = scheduled if isinstance(scheduled, list) else scheduled.get('events', [])
                for event in events:
                    mplan_id = event.get('mPlanID') or event.get('mplanID') or event.get('id')
                    est_time = event.get('EstimatedTime') or event.get('estimatedTime')
                    if mplan_id and est_time:
                        try:
                            estimated_time_map[str(mplan_id)] = int(float(est_time))
                        except (ValueError, TypeError):
                            pass
            
            # Get non-scheduled visits with EstimatedTime
            non_scheduled = external_api.get_non_scheduled_visits_with_details(start_date, end_date)
            if non_scheduled:
                visits = non_scheduled if isinstance(non_scheduled, list) else non_scheduled.get('visits', [])
                for visit in visits:
                    mplan_id = visit.get('mPlanID') or visit.get('mplanID') or visit.get('id')
                    est_time = visit.get('EstimatedTime') or visit.get('estimatedTime')
                    if mplan_id and est_time:
                        try:
                            estimated_time_map[str(mplan_id)] = int(float(est_time))
                        except (ValueError, TypeError):
                            pass
            
            current_app.logger.info(f"Built EstimatedTime lookup map with {len(estimated_time_map)} entries")
            
        except Exception as e:
            current_app.logger.warning(f"Failed to fetch EstimatedTime from scheduling API: {e}")
        
        return estimated_time_map

    def _process_event(self, event_record, db, Event, Schedule, Employee, estimated_time_map=None):
        """
        Process a single event record from the API

        Args:
            estimated_time_map: Dict mapping mPlanID -> EstimatedTime from scheduling API

        Returns:
            tuple: (event_created, schedule_created) booleans
        """
        mplan_id = event_record.get('mPlanID')
        if not mplan_id:
            return None, False

        # Parse dates - API uses multiple field naming conventions
        # Check mPlanStartDate/mPlanDueDate first (raw API), then startDate/endDate (transformed)
        start_date = (self._parse_date(event_record.get('mPlanStartDate'), '%m/%d/%Y') or
                      self._parse_date(event_record.get('startDate'), '%m/%d/%Y'))
        end_date = (self._parse_date(event_record.get('mPlanDueDate'), '%m/%d/%Y') or
                    self._parse_date(event_record.get('mPlanEndDate'), '%m/%d/%Y') or
                    self._parse_date(event_record.get('endDate'), '%m/%d/%Y'))
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

        # Extract estimated time (duration in minutes)
        # First try to get from scheduling API map (most reliable)
        # Then fall back to planning API fields
        mplan_id = event_record.get('mPlanID')
        estimated_time = None
        
        # Try estimated_time_map first (from scheduling API)
        if estimated_time_map and mplan_id:
            estimated_time = estimated_time_map.get(str(mplan_id))
        
        # Fallback to direct API fields if not in map
        if estimated_time is None:
            raw_et = (event_record.get('EstimatedTime') or
                      event_record.get('estimatedTime') or
                      event_record.get('estimatedMinutes') or
                      event_record.get('duration'))
            try:
                estimated_time = int(float(raw_et)) if raw_et is not None else None
            except (ValueError, TypeError):
                estimated_time = None

        # Extract event type from API if available
        api_event_type = event_record.get('eventType') or event_record.get('event_type')

        # Extract project name - API uses 'mPlanName', some transformations use 'name'
        project_name = event_record.get('mPlanName') or event_record.get('name', '')

        # Extract location info - API uses various field names
        location_mvid = (event_record.get('LocationMVID') or
                         event_record.get('locationMVID') or
                         event_record.get('storeID', ''))
        store_name = (event_record.get('LocationName') or
                      event_record.get('storeName', ''))

        # Extract store number
        store_number = None
        raw_store_num = event_record.get('storeNumber')
        if raw_store_num:
            try:
                store_number = int(raw_store_num)
            except (ValueError, TypeError):
                store_number = None

        # Create event
        new_event = Event(
            external_id=str(mplan_id),
            project_name=project_name,
            project_ref_num=int(mplan_id) if str(mplan_id).isdigit() else 0,
            location_mvid=location_mvid,
            store_name=store_name,
            store_number=store_number,
            start_datetime=start_date,
            due_datetime=end_date,
            is_scheduled=is_event_scheduled,
            estimated_time=estimated_time,
            condition=condition,
            sales_tools_url=sales_tools_url,
            last_synced=datetime.utcnow(),
            sync_status='synced'
        )
        
        # Determine event type:
        # 1. Use API provided type if valid
        # 2. Fallback to detection logic (name/duration based)
        extracted_type = None
        if api_event_type:
            # Map API type to our internal types if needed
            if 'CORE' in api_event_type.upper():
                extracted_type = 'Core'
            elif 'SUPER' in api_event_type.upper():
                extracted_type = 'Supervisor'
            elif 'JUICER' in api_event_type.upper():
                if 'DEEP' in api_event_type.upper():
                    extracted_type = 'Juicer Deep Clean'
                elif 'PROD' in api_event_type.upper():
                    extracted_type = 'Juicer Production'
                elif 'SURVEY' in api_event_type.upper():
                    extracted_type = 'Juicer Survey'
                else:
                    extracted_type = api_event_type # Use as is
            elif 'DIGITAL' in api_event_type.upper():
                extracted_type = 'Digitals' 
            elif 'FREEOSK' in api_event_type.upper():
                extracted_type = 'Freeosk'
                
        if extracted_type:
             new_event.event_type = extracted_type
        else:
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

    def _fix_truncated_event_types(self, db, Event):
        """
        Fix event types for events with truncated names using pairing logic.
        
        Core and Supervisor events come in pairs with adjacent project_ref_num values.
        When one is correctly typed, we can infer the other's type.
        
        Returns:
            int: Number of events fixed
        """
        from sqlalchemy import func as sqla_func
        
        # Find events with truncated names (>=99 chars) typed as "Other"
        truncated_other = Event.query.filter(
            Event.event_type == 'Other',
            sqla_func.length(Event.project_name) >= 99
        ).all()
        
        if not truncated_other:
            return 0
        
        fixed_count = 0
        
        for event in truncated_other:
            new_type = None
            
            # Check adjacent ref_nums for paired events
            prev_event = Event.query.filter_by(
                project_ref_num=event.project_ref_num - 1
            ).first()
            next_event = Event.query.filter_by(
                project_ref_num=event.project_ref_num + 1
            ).first()
            
            # If partner is Core, this should be Supervisor (and vice versa)
            if prev_event and prev_event.event_type in ('Core', 'Supervisor'):
                if self._names_match_base(event.project_name, prev_event.project_name):
                    new_type = 'Supervisor' if prev_event.event_type == 'Core' else 'Core'
            
            if not new_type and next_event and next_event.event_type in ('Core', 'Supervisor'):
                if self._names_match_base(event.project_name, next_event.project_name):
                    new_type = 'Supervisor' if next_event.event_type == 'Core' else 'Core'
            
            # Fallback: if partner is also Other with same base name, use position
            if not new_type:
                if prev_event and prev_event.event_type == 'Other' and self._names_match_base(event.project_name, prev_event.project_name):
                    new_type = 'Core'  # Higher ref_num -> Core
                elif next_event and next_event.event_type == 'Other' and self._names_match_base(event.project_name, next_event.project_name):
                    new_type = 'Supervisor'  # Lower ref_num -> Supervisor
            
            # Additional heuristics based on condition
            if not new_type:
                name_upper = (event.project_name or '').upper()
                if any(p in name_upper for p in ['-CF-', '-LKD-', '-AF-', '-MAP-', 'DEMO']):
                    if event.condition == 'In Progress':
                        new_type = 'Core'
                    elif event.condition == 'Scheduled':
                        new_type = 'Supervisor'
            
            if new_type:
                event.event_type = new_type
                fixed_count += 1
        
        if fixed_count > 0:
            db.session.commit()
        
        return fixed_count

    def _names_match_base(self, name1, name2):
        """Check if two event names share the same project number base."""
        if not name1 or not name2:
            return False
        base1 = name1.split('-')[0].strip() if '-' in name1 else name1[:6]
        base2 = name2.split('-')[0].strip() if '-' in name2 else name2[:6]
        return base1 == base2

    def _reapply_event_type_overrides(self, db, Event):
        """
        Reapply event type overrides after database refresh.
        Ensures manual changes persist through refreshes.

        Returns:
            int: Number of overrides successfully reapplied
        """
        try:
            from app.models import get_models
            models = get_models()
            EventTypeOverride = models['EventTypeOverride']
            overrides = EventTypeOverride.query.all()

            if not overrides:
                return 0

            applied_count = 0
            for override in overrides:
                event = Event.query.filter_by(
                    project_ref_num=override.project_ref_num
                ).first()

                if event:
                    event.event_type = override.override_event_type
                    applied_count += 1
                else:
                    # Event no longer in API - keep override for audit trail
                    current_app.logger.warning(
                        f"Stale override: Event {override.project_ref_num} not in API"
                    )

            if applied_count > 0:
                db.session.commit()

            return applied_count

        except Exception as e:
            current_app.logger.error(f"Error reapplying overrides: {e}")
            return 0

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
