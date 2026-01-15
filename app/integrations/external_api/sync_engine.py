"""
Bidirectional sync engine for external API integration
Handles synchronization between local database and external scheduling system
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from app.integrations.external_api.session_api_service import session_api as external_api, SessionError as APIError


class SyncEngine:
    """Main synchronization engine"""

    def __init__(self, app=None, db=None):
        self.app = app
        self.db = db
        self.logger = logging.getLogger(__name__)
        self.api = external_api

    def init_app(self, app, db):
        """Initialize with Flask app and database"""
        self.app = app
        self.db = db

    def sync_all(self) -> Dict:
        """Perform complete bidirectional synchronization"""
        if not self.app:
            return {'status': 'failed', 'message': 'SyncEngine not initialized with Flask app'}

        with self.app.app_context():
            if not self.app.config.get('SYNC_ENABLED'):
                return {'status': 'disabled', 'message': 'Synchronization is disabled'}

            results = {
                'employees': {'synced': 0, 'errors': 0, 'details': []},
                'events': {'synced': 0, 'errors': 0, 'details': []},
                'schedules': {'synced': 0, 'errors': 0, 'details': []},
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat()
            }

            try:
                # Check API health first
                health = self.api.health_check()
                if health['status'] != 'healthy':
                    return {
                        'status': 'failed',
                        'message': f"API health check failed: {health['message']}"
                    }

                # Sync employees
                employee_result = self.sync_employees()
                results['employees'] = employee_result

                # Sync events
                event_result = self.sync_events()
                results['events'] = event_result

                # Sync schedules
                schedule_result = self.sync_schedules()
                results['schedules'] = schedule_result

                # Update overall status
                total_errors = (employee_result['errors'] +
                              event_result['errors'] +
                              schedule_result['errors'])

                if total_errors > 0:
                    results['status'] = 'partial'
                    results['message'] = f"Completed with {total_errors} errors"

                self.logger.info(f"Sync completed: {results['status']}")
                return results

            except Exception as e:
                self.logger.error(f"Sync failed: {str(e)}")
                return {
                    'status': 'failed',
                    'message': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }

    def sync_employees(self) -> Dict:
        """Sync employees bidirectionally"""
        # This method is called within the app context from sync_all()
        from app import Employee  # Import here to avoid circular imports

        result = {'synced': 0, 'errors': 0, 'details': []}

        try:
            # Get external employees
            external_employees = self.api.get_employees()

            for ext_emp in external_employees:
                try:
                    local_emp = Employee.query.filter_by(
                        external_id=ext_emp.get('id')
                    ).first()

                    if local_emp:
                        # Update existing employee
                        if self._update_local_employee(local_emp, ext_emp):
                            result['synced'] += 1
                    else:
                        # Create new employee from external data
                        new_emp = self._create_local_employee_from_external(ext_emp)
                        if new_emp:
                            result['synced'] += 1

                except Exception as e:
                    result['errors'] += 1
                    result['details'].append(f"Employee sync error: {str(e)}")
                    self.logger.error(f"Employee sync error: {str(e)}")

            # Sync local employees to external system
            pending_employees = Employee.query.filter(
                Employee.sync_status.in_(['pending', 'failed'])
            ).all()

            for local_emp in pending_employees:
                try:
                    if self._sync_employee_to_external(local_emp):
                        result['synced'] += 1
                except Exception as e:
                    result['errors'] += 1
                    result['details'].append(f"Employee upload error: {str(e)}")

        except APIError as e:
            result['errors'] += 1
            result['details'].append(f"API error during employee sync: {e.message}")

        return result

    def sync_events(self) -> Dict:
        """Sync events from external system"""
        from app import Event  # Import here to avoid circular imports

        result = {'synced': 0, 'errors': 0, 'details': []}

        try:
            # Get events from last month to 4 months ahead (matches database refresh)
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now() + timedelta(days=120)

            # Sync both scheduled and unscheduled events
            all_external_events = []

            # Get scheduled events
            try:
                scheduled_events = self.api.get_scheduled_events(start_date, end_date)
                if scheduled_events:
                    # Handle the response format from Crossmark API
                    if isinstance(scheduled_events, dict) and 'events' in scheduled_events:
                        all_external_events.extend(scheduled_events['events'])
                    elif isinstance(scheduled_events, list):
                        all_external_events.extend(scheduled_events)
                    else:
                        all_external_events.append(scheduled_events)

                result['details'].append(f"Retrieved {len(scheduled_events)} scheduled events")
            except Exception as e:
                result['details'].append(f"Error getting scheduled events: {str(e)}")

            # Get unscheduled events from planning API
            try:
                unscheduled_response = self.api.get_unscheduled_events(start_date, end_date)
                if unscheduled_response:
                    # Handle the planning API response format
                    if isinstance(unscheduled_response, dict) and 'records' in unscheduled_response:
                        unscheduled_events = unscheduled_response['records']
                        all_external_events.extend(unscheduled_events)
                        result['details'].append(f"Retrieved {len(unscheduled_events)} unscheduled events from planning API")
                    elif isinstance(unscheduled_response, list):
                        all_external_events.extend(unscheduled_response)
                        result['details'].append(f"Retrieved {len(unscheduled_response)} unscheduled events")
                    else:
                        all_external_events.append(unscheduled_response)
                        result['details'].append("Retrieved 1 unscheduled event")
                else:
                    result['details'].append("No unscheduled events found")
            except Exception as e:
                result['details'].append(f"Error getting unscheduled events: {str(e)}")

            # Separate events that need mplan data lookup (scheduled events with mPlanID but no salesTools)
            events_needing_mplan_lookup = []
            mplan_location_pairs = []

            for ext_event in all_external_events:
                # Check if this event needs mplan data lookup
                mplan_id = ext_event.get('mPlanID')
                location_id = ext_event.get('storeID') or ext_event.get('locationID') or ext_event.get('LocationID')

                if mplan_id and location_id and not ext_event.get('salesTools'):
                    events_needing_mplan_lookup.append(ext_event)
                    mplan_location_pairs.append({
                        'mPlanID': str(mplan_id),
                        'storeID': str(location_id)
                    })

            # Bulk fetch mplan data if needed
            mplan_data_map = {}
            if mplan_location_pairs:
                self.logger.info(f"Bulk fetching mplan data for {len(mplan_location_pairs)} events")
                try:
                    bulk_mplan_data = self.api.get_mplan_bulk_print(mplan_location_pairs)
                    if bulk_mplan_data and 'mplans' in bulk_mplan_data:
                        for mplan in bulk_mplan_data['mplans']:
                            mplan_id = str(mplan.get('mPlanID', ''))
                            if mplan_id:
                                mplan_data_map[mplan_id] = mplan
                        self.logger.info(f"Retrieved {len(mplan_data_map)} mplan records with bulk fetch")
                    elif bulk_mplan_data:
                        # Handle different response structure
                        for mplan in bulk_mplan_data if isinstance(bulk_mplan_data, list) else [bulk_mplan_data]:
                            mplan_id = str(mplan.get('mPlanID', ''))
                            if mplan_id:
                                mplan_data_map[mplan_id] = mplan
                except Exception as e:
                    self.logger.error(f"Error in bulk mplan fetch: {str(e)}")

            # Merge mplan data into events that needed it
            for ext_event in events_needing_mplan_lookup:
                mplan_id = str(ext_event.get('mPlanID', ''))
                if mplan_id in mplan_data_map:
                    mplan_data = mplan_data_map[mplan_id]
                    # Copy salesTools from mplan data to event
                    if 'salesTools' in mplan_data:
                        ext_event['salesTools'] = mplan_data['salesTools']

            # Process all events
            for ext_event in all_external_events:
                try:
                    local_event = Event.query.filter_by(
                        external_id=ext_event.get('id', ext_event.get('Id'))
                    ).first()

                    if local_event:
                        # Update existing event
                        if self._update_local_event(local_event, ext_event):
                            result['synced'] += 1
                    else:
                        # Create new event from external data
                        new_event = self._create_local_event_from_external(ext_event)
                        if new_event:
                            result['synced'] += 1

                except Exception as e:
                    result['errors'] += 1
                    result['details'].append(f"Event sync error: {str(e)}")
                    self.logger.error(f"Event sync error: {str(e)}")

        except APIError as e:
            result['errors'] += 1
            result['details'].append(f"API error during event sync: {e.message}")

        return result

    def sync_schedules(self) -> Dict:
        """Sync schedules bidirectionally"""
        from app import Schedule, Event, Employee  # Import here to avoid circular imports

        result = {'synced': 0, 'errors': 0, 'details': []}

        try:
            # Sync local schedules to external system
            pending_schedules = Schedule.query.filter(
                Schedule.sync_status.in_(['pending', 'failed'])
            ).all()

            for local_schedule in pending_schedules:
                try:
                    if self._sync_schedule_to_external(local_schedule):
                        result['synced'] += 1
                except Exception as e:
                    result['errors'] += 1
                    result['details'].append(f"Schedule upload error: {str(e)}")

            # Also check for schedules marked for deletion
            deleted_schedules = Schedule.query.filter(
                Schedule.sync_status == 'delete_pending'
            ).all()

            for local_schedule in deleted_schedules:
                try:
                    if self._delete_schedule_from_external(local_schedule):
                        result['synced'] += 1
                        result['details'].append(f"Successfully unscheduled event {local_schedule.external_id}")
                except Exception as e:
                    result['errors'] += 1
                    result['details'].append(f"Schedule deletion error: {str(e)}")

        except Exception as e:
            result['errors'] += 1
            result['details'].append(f"Error during schedule sync: {str(e)}")

        return result

    def _update_local_employee(self, local_emp, external_data) -> bool:
        """Update local employee with external data"""
        from app import db  # Import db directly from app module
        try:
            # Get the transform method directly from API - simplified for now
            # transformed_data = self.api.transform_external_to_local(external_data)
            transformed_data = external_data  # Use external data directly for now

            # Update fields if they've changed
            updated = False
            if local_emp.name != transformed_data.get('name'):
                local_emp.name = transformed_data.get('name')
                updated = True

            if local_emp.email != transformed_data.get('email'):
                local_emp.email = transformed_data.get('email')
                updated = True

            if updated:
                local_emp.last_synced = datetime.utcnow()
                local_emp.sync_status = 'synced'
                db.session.commit()

            return updated
        except Exception as e:
            db.session.rollback()
            raise e

    def _create_local_employee_from_external(self, external_data) -> bool:
        """Create new local employee from external data"""
        from app import Employee, db  # Import here to avoid circular imports

        try:
            # Simplified transformation for now
            transformed_data = external_data

            new_employee = Employee(
                id=external_data.get('id', str(hash(external_data.get('name', '')))),
                name=transformed_data.get('name', ''),
                email=transformed_data.get('email'),
                external_id=external_data.get('id'),
                last_synced=datetime.utcnow(),
                sync_status='synced'
            )

            db.session.add(new_employee)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e

    def _update_local_event(self, local_event, external_data) -> bool:
        """Update local event with external data"""
        from app import db
        try:
            # Transform Crossmark data to local format
            transformed_data = self._transform_crossmark_event_to_local(external_data)

            # Update fields if they've changed
            updated = False

            # Check project name
            if local_event.project_name != transformed_data.get('project_name'):
                local_event.project_name = transformed_data.get('project_name')
                updated = True

            # Check store information
            if local_event.store_name != transformed_data.get('store_name'):
                local_event.store_name = transformed_data.get('store_name')
                updated = True

            if local_event.store_number != transformed_data.get('store_number'):
                local_event.store_number = transformed_data.get('store_number')
                updated = True

            # Check scheduled dates - THIS IS CRITICAL FOR DATE MISMATCHES
            new_start_date = transformed_data.get('start_datetime')
            new_due_date = transformed_data.get('due_datetime')

            if new_start_date and local_event.start_datetime != new_start_date:
                self.logger.info(f"Event {local_event.external_id}: Start date changed from {local_event.start_datetime} to {new_start_date}")
                local_event.start_datetime = new_start_date
                updated = True

            if new_due_date and local_event.due_datetime != new_due_date:
                self.logger.info(f"Event {local_event.external_id}: Due date changed from {local_event.due_datetime} to {new_due_date}")
                local_event.due_datetime = new_due_date
                updated = True

            # Check estimated time
            if local_event.estimated_time != transformed_data.get('estimated_time'):
                local_event.estimated_time = transformed_data.get('estimated_time')
                updated = True

            # Check location details
            if local_event.location_mvid != transformed_data.get('location_mvid'):
                local_event.location_mvid = transformed_data.get('location_mvid')
                updated = True

            if local_event.project_ref_num != transformed_data.get('project_ref_num'):
                local_event.project_ref_num = transformed_data.get('project_ref_num')
                updated = True

            # Check sales tools URL
            if local_event.sales_tools_url != transformed_data.get('sales_tools_url'):
                local_event.sales_tools_url = transformed_data.get('sales_tools_url')
                updated = True

            if updated:
                local_event.last_synced = datetime.utcnow()
                local_event.sync_status = 'synced'
                db.session.commit()
                self.logger.info(f"Updated event {local_event.external_id} with changes from Crossmark")

            return updated
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error updating local event: {str(e)}")
            raise e

    def _create_local_event_from_external(self, external_data) -> bool:
        """Create new local event from Crossmark data"""
        from app import Event, db  # Import here to avoid circular imports

        try:
            # Transform Crossmark data to our local format
            transformed_data = self._transform_crossmark_event_to_local(external_data)

            new_event = Event(
                project_name=transformed_data.get('project_name', ''),
                project_ref_num=transformed_data.get('project_ref_num'),
                store_name=transformed_data.get('store_name'),
                location_mvid=transformed_data.get('location_mvid'),
                store_number=transformed_data.get('store_number'),
                start_datetime=transformed_data.get('start_datetime'),
                due_datetime=transformed_data.get('due_datetime'),
                estimated_time=transformed_data.get('estimated_time'),
                sales_tools_url=transformed_data.get('sales_tools_url'),
                external_id=str(external_data.get('Id', external_data.get('id', ''))),
                last_synced=datetime.utcnow(),
                sync_status='synced'
            )

            # Auto-detect event type
            new_event.event_type = new_event.detect_event_type()

            # Set default duration if estimated_time is not set
            new_event.set_default_duration()

            db.session.add(new_event)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e

    def _sync_employee_to_external(self, local_employee) -> bool:
        """Sync local employee to external system"""
        from app import db
        try:
            employee_data = {
                'id': local_employee.id,
                'name': local_employee.name,
                'email': local_employee.email,
                'phone': local_employee.phone,
                'is_active': local_employee.is_active,
                'job_title': local_employee.job_title
            }

            if local_employee.external_id:
                # Update existing employee
                response = self.api.update_employee(local_employee.external_id, employee_data)
            else:
                # Create new employee
                response = self.api.create_employee(employee_data)
                local_employee.external_id = response.get('id')

            local_employee.last_synced = datetime.utcnow()
            local_employee.sync_status = 'synced'
            db.session.commit()
            return True

        except APIError as e:
            local_employee.sync_status = 'failed'
            db.session.commit()
            raise e

    def _sync_schedule_to_external(self, local_schedule) -> bool:
        """Sync local schedule to external Crossmark system"""
        from app import db
        try:
            # Get related event and employee data
            from app import Event, Employee

            event = Event.query.filter_by(project_ref_num=local_schedule.event_ref_num).first()
            employee = Employee.query.filter_by(id=local_schedule.employee_id).first()

            if not event or not employee:
                raise Exception(f"Missing related data for schedule {local_schedule.id}")

            # Calculate end datetime using event's default duration if not set
            start_datetime = local_schedule.schedule_datetime
            end_datetime = event.calculate_end_datetime(start_datetime)

            # Prepare Crossmark scheduling data
            schedule_data = {
                'rep_id': employee.external_id or employee.id,  # RepID in Crossmark
                'mplan_id': event.external_id,  # mPlanID in Crossmark (from unscheduled events)
                'location_id': event.location_mvid,  # LocationID in Crossmark
                'start_datetime': start_datetime,
                'end_datetime': end_datetime,
                'planning_override': True  # Allow override of planning constraints
            }

            self.logger.info(f"Scheduling event {event.project_name} for {employee.name} at {local_schedule.schedule_datetime}")

            if local_schedule.external_id:
                # For existing schedules, delete old and create new (Crossmark doesn't support updates)
                self.logger.info(f"Deleting existing schedule {local_schedule.external_id} before creating new one")
                delete_response = self.api.delete_schedule(local_schedule.external_id)

                if delete_response.get('success'):
                    # Create new schedule with updated data
                    response = self.api.create_schedule(schedule_data)
                    if response.get('success'):
                        # Keep the same external_id (mPlan ID) since it's the same event
                        self.logger.info(f"Successfully recreated schedule with new employee")
                    else:
                        raise Exception(f"Failed to recreate schedule after deletion: {response.get('message', 'Unknown error')}")
                else:
                    # If delete failed, try update anyway as fallback
                    self.logger.warning(f"Delete failed, attempting update: {delete_response.get('message')}")
                    response = self.api.update_schedule(local_schedule.external_id, schedule_data)
            else:
                # Create new schedule using Crossmark API
                response = self.api.create_schedule(schedule_data)
                if response.get('success'):
                    # Store the mPlan ID as external_id for future reference
                    local_schedule.external_id = schedule_data['mplan_id']

            if response.get('success'):
                local_schedule.last_synced = datetime.utcnow()
                local_schedule.sync_status = 'synced'
                db.session.commit()
                self.logger.info(f"Successfully synced schedule {local_schedule.id} to Crossmark")
                return True
            else:
                local_schedule.sync_status = 'failed'
                db.session.commit()
                raise Exception(f"Crossmark scheduling failed: {response.get('message', 'Unknown error')}")

        except Exception as e:
            local_schedule.sync_status = 'failed'
            db.session.commit()
            self.logger.error(f"Failed to sync schedule to Crossmark: {str(e)}")
            raise e

    def _delete_schedule_from_external(self, local_schedule) -> bool:
        """Delete/unschedule an event from Crossmark system"""
        from app import db
        try:
            if not local_schedule.external_id:
                self.logger.warning(f"Schedule {local_schedule.id} has no external_id, cannot delete from Crossmark")
                # Just delete locally since it wasn't synced to Crossmark
                db.session.delete(local_schedule)
                db.session.commit()
                return True

            self.logger.info(f"Unscheduling event {local_schedule.external_id} from Crossmark")

            # Call Crossmark delete endpoint
            response = self.api.delete_schedule(local_schedule.external_id)

            if response.get('success'):
                # Successfully unscheduled from Crossmark, now delete locally
                db.session.delete(local_schedule)
                db.session.commit()
                self.logger.info(f"Successfully unscheduled and deleted schedule {local_schedule.id}")
                return True
            else:
                # Failed to unschedule from Crossmark
                local_schedule.sync_status = 'delete_failed'
                db.session.commit()
                raise Exception(f"Failed to unschedule from Crossmark: {response.get('message', 'Unknown error')}")

        except Exception as e:
            local_schedule.sync_status = 'delete_failed'
            db.session.commit()
            self.logger.error(f"Failed to delete schedule from Crossmark: {str(e)}")
            raise e

    def _transform_crossmark_event_to_local(self, crossmark_data: Dict) -> Dict:
        """Transform Crossmark event data to local format"""
        try:
            # Parse Crossmark datetime format (assuming it comes in a specific format)
            start_datetime = self._parse_crossmark_datetime(crossmark_data.get('StartDateTime', crossmark_data.get('StartDate')))
            due_datetime = self._parse_crossmark_datetime(crossmark_data.get('EndDateTime', crossmark_data.get('EndDate')))

            return {
                'project_name': crossmark_data.get('ProjectName', crossmark_data.get('Name', '')),
                'project_ref_num': self._extract_project_ref_num(crossmark_data),
                'store_name': crossmark_data.get('StoreName', crossmark_data.get('Location', '')),
                'location_mvid': crossmark_data.get('LocationId', crossmark_data.get('StoreId', '')),
                'store_number': self._extract_store_number(crossmark_data),
                'start_datetime': start_datetime,
                'due_datetime': due_datetime,
                'estimated_time': self._extract_estimated_time(crossmark_data),
                'sales_tools_url': self._extract_sales_tools_url(crossmark_data)
            }
        except Exception as e:
            logging.error(f"Error transforming Crossmark data: {str(e)}")
            # Return basic transformation
            return {
                'project_name': str(crossmark_data.get('ProjectName', crossmark_data.get('Name', 'Unknown'))),
                'project_ref_num': hash(str(crossmark_data)) % 1000000,  # Generate a ref num
                'store_name': str(crossmark_data.get('StoreName', crossmark_data.get('Location', ''))),
                'location_mvid': str(crossmark_data.get('LocationId', crossmark_data.get('StoreId', ''))),
                'store_number': 0,
                'start_datetime': datetime.now(),
                'due_datetime': datetime.now() + timedelta(days=7),
                'estimated_time': 60,  # Default 1 hour
                'sales_tools_url': self._extract_sales_tools_url(crossmark_data)
            }

    def _parse_crossmark_datetime(self, date_string) -> datetime:
        """Parse Crossmark datetime string to datetime object"""
        if not date_string:
            return datetime.now()

        try:
            # Try common datetime formats that Crossmark might use
            formats = [
                "%Y-%m-%dT%H:%M:%S",  # ISO format
                "%Y-%m-%d %H:%M:%S",  # Standard format
                "%m/%d/%Y %H:%M:%S",  # US format
                "%Y-%m-%d",           # Date only
                "%m/%d/%Y"            # US date only
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(str(date_string).split('.')[0], fmt)  # Remove microseconds if present
                except ValueError:
                    continue

            # If none work, try parsing as ISO with timezone info
            from dateutil import parser
            return parser.parse(str(date_string))

        except Exception as e:
            logging.warning(f"Could not parse date '{date_string}': {str(e)}")
            return datetime.now()

    def _extract_project_ref_num(self, crossmark_data: Dict) -> int:
        """Extract or generate project reference number from Crossmark data"""
        # Try to get ID or other unique identifier
        ref_candidates = [
            crossmark_data.get('Id'),
            crossmark_data.get('ProjectId'),
            crossmark_data.get('VisitId'),
            crossmark_data.get('WorkOrderId')
        ]

        for candidate in ref_candidates:
            if candidate is not None:
                try:
                    return int(candidate)
                except (ValueError, TypeError):
                    # If it's not an integer, hash it
                    return hash(str(candidate)) % 1000000

        # Fallback: hash the entire record
        return hash(str(crossmark_data)) % 1000000

    def _extract_store_number(self, crossmark_data: Dict) -> int:
        """Extract store number from Crossmark data"""
        store_candidates = [
            crossmark_data.get('StoreNumber'),
            crossmark_data.get('StoreId'),
            crossmark_data.get('LocationNumber')
        ]

        for candidate in store_candidates:
            if candidate is not None:
                try:
                    return int(str(candidate).replace('#', '').replace('-', ''))
                except (ValueError, TypeError):
                    continue

        return 0  # Default store number

    def _extract_estimated_time(self, crossmark_data: Dict) -> int:
        """Extract estimated time in minutes from Crossmark data"""
        time_candidates = [
            crossmark_data.get('EstimatedTime'),
            crossmark_data.get('Duration'),
            crossmark_data.get('ExpectedDuration')
        ]

        for candidate in time_candidates:
            if candidate is not None:
                try:
                    return int(candidate)
                except (ValueError, TypeError):
                    continue

        return 60  # Default 1 hour

    def _extract_sales_tools_url(self, crossmark_data: Dict) -> str:
        """Extract sales tools URL from Crossmark data"""
        # Check if this data has salesTools (should be populated by bulk fetch)
        sales_tools = crossmark_data.get('salesTools', [])

        if isinstance(sales_tools, list) and len(sales_tools) > 0:
            # Return the first sales tool URL if available
            first_tool = sales_tools[0]
            if isinstance(first_tool, dict):
                url = first_tool.get('salesToolURL', '')
                if url:
                    self.logger.info(f"Extracted salesToolURL: {url}")
                    return url

        # Check for direct salesToolURL field
        direct_url = crossmark_data.get('salesToolURL', '')
        if direct_url:
            self.logger.info(f"Found direct salesToolURL: {direct_url}")
            return direct_url

        # Log if no sales tools URL found
        mplan_id = crossmark_data.get('mPlanID')
        if mplan_id:
            self.logger.info(f"No salesTools URL found for mPlanID {mplan_id}")

        return ''

    def _transform_local_to_crossmark(self, local_data: Dict) -> Dict:
        """Transform local event data to Crossmark format (for future scheduling API)"""
        return {
            'ProjectName': local_data.get('project_name', ''),
            'LocationId': local_data.get('location_mvid', ''),
            'StoreName': local_data.get('store_name', ''),
            'StartDateTime': local_data.get('schedule_datetime', '').isoformat() if local_data.get('schedule_datetime') else '',
            'EmployeeId': local_data.get('employee_id', ''),
            'Duration': local_data.get('estimated_time', 60)
        }


# Global instance
sync_engine = SyncEngine()