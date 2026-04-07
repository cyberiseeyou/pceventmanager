"""
Background Sync Daemon Service
Polls Crossmark MVRetail API every 5 minutes, incrementally upserts changes,
and detects conflicts between local and upstream data.
"""
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from app.constants import INACTIVE_CONDITIONS

logger = logging.getLogger(__name__)

# Fields that are safe to auto-update from upstream without flagging a conflict
SAFE_FIELDS = {
    'project_name', 'store_name', 'location_mvid', 'store_number',
    'estimated_time', 'sales_tools_url', 'event_type',
}

# Fields where a mismatch between local and upstream is a red flag
PROTECTED_FIELDS = {
    'start_datetime', 'due_datetime',
}

# Verify safe/protected sets don't overlap (catches future mistakes)
assert SAFE_FIELDS.isdisjoint(PROTECTED_FIELDS), \
    f"SAFE_FIELDS and PROTECTED_FIELDS overlap: {SAFE_FIELDS & PROTECTED_FIELDS}"


def run_sync_cycle():
    """
    Main sync cycle — called by APScheduler every 5 minutes.
    Runs inside Flask app context provided by the scheduler wrapper.
    """
    # Feature flag guard — CLAUDE.md mandates checking before external API calls
    if not current_app.config.get('SYNC_ENABLED'):
        logger.debug("Sync disabled, skipping cycle")
        return {'status': 'disabled'}

    from app.models import get_models, get_db

    try:
        models = get_models()
        db = get_db()
        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        daemon = SyncDaemon(db, Event, Schedule, SyncChangeLog, SystemSetting)
        result = daemon.sync()

        logger.info(
            "Sync cycle complete: %d new, %d modified, %d cancelled, %d conflicts (%.1fs)",
            result['new'], result['modified'], result['cancelled'],
            result['conflicts'], result['duration']
        )

        return result

    except Exception as e:
        logger.error("Sync cycle failed: %s", e, exc_info=True)
        # Track failure in SystemSetting so health check can surface the error
        try:
            from app.models import get_models, get_db
            models = get_models()
            SystemSetting = models['SystemSetting']
            SystemSetting.set_setting(
                'last_sync_error',
                str(e),
                setting_type='string',
                user='sync_daemon',
            )
            get_db().session.commit()
        except Exception:
            logger.error("Failed to persist sync error to SystemSetting", exc_info=True)
        return {'status': 'error', 'error': str(e)}


class SyncDaemon:
    """Incremental sync engine that compares upstream Crossmark data to local state."""

    def __init__(self, db, Event, Schedule, SyncChangeLog, SystemSetting):
        self._db = db
        self.Event = Event
        self.Schedule = Schedule
        self.SyncChangeLog = SyncChangeLog
        self.SystemSetting = SystemSetting

    @property
    def session(self):
        """Get the SQLAlchemy session, supporting both Flask-SQLAlchemy and scoped_session."""
        if hasattr(self._db, 'session'):
            return self._db.session
        return self._db

    def sync(self):
        """
        Perform one incremental sync cycle.

        Returns:
            dict with counts of new, modified, cancelled, conflicts, and duration
        """
        from app.integrations.external_api.session_api_service import session_api as external_api

        start_time = datetime.utcnow()
        counts = {'new': 0, 'modified': 0, 'cancelled': 0, 'conflicts': 0}
        change_logs = []

        # 1. Clear singleton state and authenticate (CLAUDE.md: always clear before login)
        external_api.authenticated = False
        external_api.phpsessid = None
        if external_api.session:
            external_api.session.cookies.clear()

        if not external_api.ensure_authenticated():
            logger.error("Sync daemon: authentication failed")
            return {**counts, 'status': 'auth_failed', 'duration': 0}

        # 2. Fetch upstream events (full 150-day window, parallel)
        upstream_events = self._fetch_upstream_events(external_api)
        if upstream_events is None:
            logger.error("Sync daemon: failed to fetch upstream events")
            return {**counts, 'status': 'fetch_failed', 'duration': 0}

        # 3. Build lookup of upstream events by mPlanID
        upstream_map = {}
        for record in upstream_events:
            mplan_id = record.get('mPlanID')
            if mplan_id:
                upstream_map[str(mplan_id)] = record

        # 4. Fetch estimated times from scheduling API
        estimated_time_map = self._fetch_estimated_times(external_api)

        # 5. Build set of local events for comparison
        local_events = self.Event.query.all()
        local_map = {str(e.project_ref_num): e for e in local_events if e.project_ref_num}

        # 6. Compare: upstream vs local
        for mplan_id, upstream_record in upstream_map.items():
            local_event = local_map.get(mplan_id)

            if local_event is None:
                # New event — insert it
                change = self._handle_new_event(upstream_record, estimated_time_map)
                if change:
                    change_logs.append(change)
                    counts['new'] += 1
            else:
                # Existing event — check for changes
                changes = self._compare_event(local_event, upstream_record, estimated_time_map)
                if changes:
                    change_logs.extend(changes)
                    for c in changes:
                        if c['is_conflict']:
                            counts['conflicts'] += 1
                        else:
                            counts['modified'] += 1

        # 7. Check for events removed from upstream (cancelled)
        upstream_ids = set(upstream_map.keys())
        for ref_num, local_event in local_map.items():
            if ref_num not in upstream_ids:
                # Only flag active events — don't re-flag already cancelled ones
                if local_event.condition not in INACTIVE_CONDITIONS:
                    change = self._handle_cancelled_event(local_event)
                    if change:
                        change_logs.append(change)
                        counts['cancelled'] += 1

        # 8. Send push notifications FIRST (mutates push_sent flag on dicts)
        if change_logs:
            self._send_push_notifications(change_logs, counts)

        # 8b. Write change logs to database (reads push_sent from dicts)
        if change_logs:
            self._write_change_logs(change_logs)

        # 9. Commit all changes
        try:
            self.session.commit()
        except SQLAlchemyError:
            logger.error("Sync daemon: commit failed", exc_info=True)
            self.session.rollback()
            # Return zeroed counts — the work was rolled back
            return {'new': 0, 'modified': 0, 'cancelled': 0, 'conflicts': 0,
                    'status': 'commit_failed', 'duration': 0}

        # 10. Update sync metadata
        duration = (datetime.utcnow() - start_time).total_seconds()
        self._update_sync_metadata(duration, counts)

        return {
            **counts,
            'status': 'success',
            'duration': duration,
            'total_upstream': len(upstream_map),
            'total_local': len(local_map),
        }

    def _fetch_upstream_events(self, api):
        """Fetch all events from Crossmark API using parallel fetching."""
        try:
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now() + timedelta(days=120)

            result = api.get_all_planning_events_parallel(
                start_date=start_date,
                end_date=end_date
            )
            if not result:
                return None

            records = (result.get('mplans') or
                       result.get('events') or
                       result.get('records') or [])
            return records

        except requests.exceptions.RequestException as e:
            logger.warning("Transient API failure fetching upstream events: %s", e)
            return None
        except Exception as e:
            logger.error("Unexpected error fetching upstream events: %s", e, exc_info=True)
            return None

    def _fetch_estimated_times(self, api):
        """Fetch EstimatedTime lookup map from scheduling endpoints."""
        estimated_time_map = {}
        try:
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now() + timedelta(days=120)

            scheduled = api.get_scheduled_events(start_date, end_date)
            if scheduled:
                events = scheduled if isinstance(scheduled, list) else scheduled.get('events', [])
                for event in events:
                    mplan_id = event.get('mPlanID') or event.get('mplanID') or event.get('id')
                    est_time = event.get('EstimatedTime') or event.get('estimatedTime')
                    if mplan_id and est_time:
                        try:
                            estimated_time_map[str(mplan_id)] = int(float(est_time))
                        except (ValueError, TypeError):
                            logger.debug("Unparseable estimated time for mPlan %s: %s", mplan_id, est_time)
        except Exception as e:
            logger.error("Failed to fetch estimated times: %s", e, exc_info=True)

        return estimated_time_map

    def _handle_new_event(self, upstream_record, estimated_time_map):
        """Insert a new event from upstream and return a change log entry."""
        mplan_id = upstream_record.get('mPlanID')
        if not mplan_id:
            return None

        parsed = self._parse_upstream_record(upstream_record, estimated_time_map)

        new_event = self.Event(
            external_id=str(mplan_id),
            project_name=parsed['project_name'],
            project_ref_num=int(mplan_id) if str(mplan_id).isdigit() else 0,
            location_mvid=parsed['location_mvid'],
            store_name=parsed['store_name'],
            store_number=parsed['store_number'],
            start_datetime=parsed['start_datetime'],
            due_datetime=parsed['due_datetime'],
            estimated_time=parsed['estimated_time'],
            is_scheduled=parsed['is_scheduled'],
            condition=parsed['condition'],
            sales_tools_url=parsed['sales_tools_url'],
            last_synced=datetime.utcnow(),
            sync_status='synced',
        )
        new_event.event_type = parsed.get('event_type') or new_event.detect_event_type()
        self.session.add(new_event)

        store_info = f" at {parsed['store_name']}" if parsed['store_name'] else ''
        date_info = parsed['start_datetime'].strftime('%b %d') if parsed['start_datetime'] else ''

        return {
            'change_type': 'new_event',
            'entity_type': 'event',
            'entity_id': str(mplan_id),
            'summary': f"New event: {parsed['project_name']}{store_info} on {date_info}",
            'field_changes': None,
            'is_conflict': False,
        }

    def _handle_cancelled_event(self, local_event):
        """Mark a local event as cancelled (no longer in upstream)."""
        has_schedule = self.Schedule.query.filter_by(
            event_ref_num=local_event.project_ref_num
        ).first() is not None

        if has_schedule:
            # Event with a schedule was removed from Crossmark — flag as conflict
            return {
                'change_type': 'conflict',
                'entity_type': 'event',
                'entity_id': str(local_event.project_ref_num),
                'summary': (
                    f"Event {local_event.project_name} removed from Crossmark "
                    f"but has a local schedule — investigate"
                ),
                'field_changes': json.dumps({
                    'condition': {
                        'local': local_event.condition,
                        'upstream': 'Removed from API'
                    }
                }),
                'is_conflict': True,
            }
        else:
            # No schedule — safe to auto-cancel
            local_event.condition = 'Canceled'
            local_event.last_synced = datetime.utcnow()

            return {
                'change_type': 'cancelled',
                'entity_type': 'event',
                'entity_id': str(local_event.project_ref_num),
                'summary': f"Event cancelled: {local_event.project_name}",
                'field_changes': None,
                'is_conflict': False,
            }

    def _compare_event(self, local_event, upstream_record, estimated_time_map):
        """
        Compare a local event against upstream data.
        Returns a list of change log entries (may be empty if nothing changed).
        """
        parsed = self._parse_upstream_record(upstream_record, estimated_time_map)
        changes = []
        safe_diffs = {}
        protected_diffs = {}

        # Check if event has a local schedule (makes all field changes conflicts)
        has_schedule = self.Schedule.query.filter_by(
            event_ref_num=local_event.project_ref_num
        ).first() is not None

        # Compare safe fields
        for field in SAFE_FIELDS:
            local_val = getattr(local_event, field, None)
            upstream_val = parsed.get(field)

            # Normalize for comparison (treat None and empty string as equivalent)
            local_norm = (local_val.strip() if isinstance(local_val, str) else local_val) or None
            upstream_norm = (upstream_val.strip() if isinstance(upstream_val, str) else upstream_val) or None
            if local_norm == upstream_norm:
                continue
            # Skip if upstream is None/empty (missing data is not a change)
            if upstream_norm is None:
                continue

            if has_schedule:
                # Any field change on a scheduled event is a conflict
                protected_diffs[field] = {
                    'local': str(local_val) if local_val is not None else None,
                    'upstream': str(upstream_val) if upstream_val is not None else None,
                }
            else:
                safe_diffs[field] = {
                    'local': str(local_val) if local_val is not None else None,
                    'upstream': str(upstream_val) if upstream_val is not None else None,
                }

        # Compare protected fields (always conflict if different)
        for field in PROTECTED_FIELDS:
            local_val = getattr(local_event, field, None)
            upstream_val = parsed.get(field)
            if upstream_val is None:
                continue

            # Compare datetimes by date only (time precision varies)
            if isinstance(local_val, datetime) and isinstance(upstream_val, datetime):
                if local_val.date() == upstream_val.date():
                    continue
            elif local_val == upstream_val:
                continue

            protected_diffs[field] = {
                'local': local_val.isoformat() if isinstance(local_val, datetime) else str(local_val),
                'upstream': upstream_val.isoformat() if isinstance(upstream_val, datetime) else str(upstream_val),
            }

        # Check schedule status mismatch
        upstream_is_scheduled = parsed.get('is_scheduled', False)
        if local_event.is_scheduled and not upstream_is_scheduled:
            protected_diffs['is_scheduled'] = {
                'local': 'True (scheduled)',
                'upstream': 'False (unscheduled in Crossmark)',
            }
        elif not local_event.is_scheduled and upstream_is_scheduled and has_schedule:
            protected_diffs['is_scheduled'] = {
                'local': 'False (unscheduled locally)',
                'upstream': 'True (scheduled in Crossmark)',
            }

        # Check condition change to cancelled
        upstream_condition = parsed.get('condition', 'Unstaffed')
        if upstream_condition in INACTIVE_CONDITIONS and local_event.condition not in INACTIVE_CONDITIONS:
            if has_schedule:
                protected_diffs['condition'] = {
                    'local': local_event.condition,
                    'upstream': upstream_condition,
                }
            else:
                # Auto-apply cancellation
                local_event.condition = upstream_condition
                local_event.last_synced = datetime.utcnow()
                changes.append({
                    'change_type': 'cancelled',
                    'entity_type': 'event',
                    'entity_id': str(local_event.project_ref_num),
                    'summary': f"Event cancelled: {local_event.project_name}",
                    'field_changes': None,
                    'is_conflict': False,
                })

        # Apply safe changes
        if safe_diffs and not has_schedule:
            for field, diff in safe_diffs.items():
                upstream_val = parsed.get(field)
                setattr(local_event, field, upstream_val)
            local_event.last_synced = datetime.utcnow()

            changes.append({
                'change_type': 'modified',
                'entity_type': 'event',
                'entity_id': str(local_event.project_ref_num),
                'summary': f"Event updated: {local_event.project_name} ({', '.join(safe_diffs.keys())})",
                'field_changes': json.dumps(safe_diffs),
                'is_conflict': False,
            })

        # Record conflicts (never auto-apply)
        if protected_diffs:
            changes.append({
                'change_type': 'conflict',
                'entity_type': 'event',
                'entity_id': str(local_event.project_ref_num),
                'summary': (
                    f"Conflict: {local_event.project_name} — "
                    f"{', '.join(protected_diffs.keys())} differ from Crossmark"
                ),
                'field_changes': json.dumps(protected_diffs),
                'is_conflict': True,
            })

        return changes

    def _parse_upstream_record(self, record, estimated_time_map):
        """Parse an upstream API record into a normalized dict of event fields."""
        mplan_id = record.get('mPlanID')

        # Parse dates
        start_date = (self._parse_date(record.get('mPlanStartDate'), '%m/%d/%Y') or
                      self._parse_date(record.get('startDate'), '%m/%d/%Y'))
        end_date = (self._parse_date(record.get('mPlanDueDate'), '%m/%d/%Y') or
                    self._parse_date(record.get('mPlanEndDate'), '%m/%d/%Y') or
                    self._parse_date(record.get('endDate'), '%m/%d/%Y'))
        schedule_date = self._parse_date(record.get('scheduleDate'), '%m/%d/%Y %I:%M:%S %p')

        if not start_date:
            logger.warning("Missing start date for mPlan %s, defaulting to now", mplan_id)
            start_date = datetime.utcnow()
        if not end_date:
            logger.warning("Missing end date for mPlan %s, defaulting to now", mplan_id)
            end_date = datetime.utcnow()

        condition = record.get('condition', 'Unstaffed')
        is_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )

        # Sales tools URL
        sales_tools_url = None
        sales_tools = record.get('salesTools', [])
        if sales_tools and isinstance(sales_tools, list) and len(sales_tools) > 0:
            if isinstance(sales_tools[0], dict):
                sales_tools_url = sales_tools[0].get('salesToolURL')

        # Estimated time
        estimated_time = None
        if estimated_time_map and mplan_id:
            estimated_time = estimated_time_map.get(str(mplan_id))
        if estimated_time is None:
            raw_et = (record.get('EstimatedTime') or record.get('estimatedTime') or
                      record.get('estimatedMinutes') or record.get('duration'))
            try:
                estimated_time = int(float(raw_et)) if raw_et is not None else None
            except (ValueError, TypeError):
                estimated_time = None

        # Event type
        api_event_type = record.get('eventType') or record.get('event_type')
        event_type = self._map_event_type(api_event_type)

        # Location
        location_mvid = (record.get('LocationMVID') or record.get('locationMVID') or
                         record.get('storeID', ''))
        store_name = record.get('LocationName') or record.get('storeName', '')
        store_number = None
        raw_store_num = record.get('storeNumber')
        if raw_store_num:
            try:
                store_number = int(raw_store_num)
            except (ValueError, TypeError):
                pass

        return {
            'project_name': record.get('mPlanName') or record.get('name', ''),
            'location_mvid': str(location_mvid) if location_mvid else '',
            'store_name': store_name,
            'store_number': store_number,
            'start_datetime': start_date,
            'due_datetime': end_date,
            'estimated_time': estimated_time,
            'is_scheduled': is_scheduled,
            'condition': condition,
            'sales_tools_url': sales_tools_url,
            'event_type': event_type,
        }

    def _map_event_type(self, api_type):
        """Map API event type string to internal type, or return None for detection fallback."""
        if not api_type:
            return None
        upper = api_type.upper()
        if 'CORE' in upper:
            return 'Core'
        if 'SUPER' in upper:
            return 'Supervisor'
        if 'JUICER' in upper:
            if 'DEEP' in upper:
                return 'Juicer Deep Clean'
            if 'PROD' in upper:
                return 'Juicer Production'
            if 'SURVEY' in upper:
                return 'Juicer Survey'
            return api_type
        if 'DIGITAL' in upper:
            return 'Digitals'
        if 'FREEOSK' in upper:
            return 'Freeosk'
        return None

    def _parse_date(self, date_str, format_str):
        """Parse date string, return None on failure."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, format_str)
        except ValueError:
            logger.debug("Unparseable date '%s' (expected format: %s)", date_str, format_str)
            return None

    def _write_change_logs(self, change_entries):
        """Write change log entries to the SyncChangeLog table."""
        for entry in change_entries:
            log = self.SyncChangeLog(
                change_type=entry['change_type'],
                entity_type=entry['entity_type'],
                entity_id=entry['entity_id'],
                summary=entry['summary'],
                field_changes=entry.get('field_changes'),
                is_conflict=entry['is_conflict'],
                detected_at=datetime.utcnow(),
                push_sent=entry.get('push_sent', False),
                push_sent_at=datetime.utcnow() if entry.get('push_sent') else None,
            )
            self.session.add(log)

    def _send_push_notifications(self, change_logs, counts):
        """Send push notifications to supervisors about sync changes."""
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            logger.debug("pywebpush not installed, skipping push notifications")
            return

        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        if not vapid_private_key:
            return

        from app.models import get_models
        models = get_models()
        PushSubscription = models['PushSubscription']
        Employee = models['Employee']

        # Find supervisor employees with active push subscriptions
        supervisors = Employee.query.filter_by(is_supervisor=True, is_active=True).all()
        sup_ids = [s.id for s in supervisors]
        if not sup_ids:
            return

        subs = PushSubscription.query.filter(
            PushSubscription.employee_id.in_(sup_ids),
            PushSubscription.is_active.is_(True),
        ).all()
        if not subs:
            return

        # Build notification payload
        has_conflicts = counts.get('conflicts', 0) > 0
        parts = []
        if counts.get('new', 0):
            parts.append(f"{counts['new']} new")
        if counts.get('cancelled', 0):
            parts.append(f"{counts['cancelled']} cancelled")
        if counts.get('modified', 0):
            parts.append(f"{counts['modified']} updated")
        if counts.get('conflicts', 0):
            parts.append(f"{counts['conflicts']} conflicts")

        body = ', '.join(parts) if parts else 'Changes detected'

        if has_conflicts:
            title = 'Schedule Conflict Detected'
            tag = 'sync-conflict'
            url = '/sync/conflicts'
        else:
            title = 'Crossmark Sync Update'
            tag = 'sync-update'
            url = '/sync/changes'

        vapid_claims = {
            'sub': current_app.config.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@pcevents.com')
        }
        payload = json.dumps({
            'title': title,
            'body': body,
            'url': url,
            'tag': tag,
        })

        any_sent = False
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {
                            'p256dh': sub.p256dh_key,
                            'auth': sub.auth_key,
                        }
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                    timeout=5,
                )
                sub.last_used_at = datetime.utcnow()
                any_sent = True
            except WebPushException as e:
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code in (404, 410):
                        sub.is_active = False
                elif '410' in str(e) or '404' in str(e):
                    sub.is_active = False
                logger.warning("Push failed for sub %s: %s", sub.id, e)
            except Exception as e:
                logger.warning("Push error for sub %s: %s", sub.id, e)

        # Only mark as push-sent if at least one push succeeded
        if any_sent:
            for entry in change_logs:
                entry['push_sent'] = True

    def _update_sync_metadata(self, duration, counts):
        """Store sync metadata in SystemSetting for health checks."""
        try:
            self.SystemSetting.set_setting(
                'last_successful_sync',
                datetime.utcnow().isoformat(),
                setting_type='string',
                user='sync_daemon',
                description='Timestamp of last successful background sync'
            )
            self.SystemSetting.set_setting(
                'last_sync_duration',
                str(round(duration, 1)),
                setting_type='string',
                user='sync_daemon',
                description='Duration of last sync cycle in seconds'
            )
            self.SystemSetting.set_setting(
                'last_sync_changes',
                json.dumps(counts),
                setting_type='string',
                user='sync_daemon',
                description='Change counts from last sync cycle'
            )
            self.session.commit()
        except Exception as e:
            logger.error("Failed to update sync metadata: %s", e, exc_info=True)
            try:
                self.session.rollback()
            except Exception:
                pass


def get_last_sync_time():
    """
    Get the timestamp of the last successful sync.
    Returns datetime or None if never synced.
    """
    from app.models import get_models
    models = get_models()
    SystemSetting = models['SystemSetting']
    value = SystemSetting.get_setting('last_successful_sync')
    if value:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return None


def is_daemon_healthy(max_age_seconds=300):
    """
    Check if the daemon has synced recently enough to skip the loading page.

    Args:
        max_age_seconds: Maximum seconds since last sync (default 300 = 5 min)

    Returns:
        bool: True if daemon synced within max_age_seconds
    """
    last_sync = get_last_sync_time()
    if last_sync is None:
        return False
    age = (datetime.utcnow() - last_sync).total_seconds()
    return age <= max_age_seconds
