"""
Tests for the background sync daemon service.
Tests change detection, conflict classification, and SyncChangeLog creation.
"""
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


class TestSyncDaemonChangeDetection:
    """Test the SyncDaemon's ability to detect different types of changes."""

    def test_new_event_detected(self, app, db_session, models):
        """New upstream event not in local DB should be inserted and logged."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)

        upstream_record = {
            'mPlanID': '999999',
            'mPlanName': 'Test Core Event - Store 1234',
            'mPlanStartDate': '04/10/2026',
            'mPlanDueDate': '04/15/2026',
            'condition': 'Unstaffed',
            'LocationMVID': 'LOC123',
            'LocationName': 'Test Store',
        }

        change = daemon._handle_new_event(upstream_record, {})
        db_session.commit()

        # Verify event was created
        event = Event.query.filter_by(project_ref_num=999999).first()
        assert event is not None
        assert event.project_name == 'Test Core Event - Store 1234'
        assert event.sync_status == 'synced'

        # Verify change log entry
        assert change is not None
        assert change['change_type'] == 'new_event'
        assert change['entity_id'] == '999999'
        assert change['is_conflict'] is False

    def test_cancelled_event_without_schedule(self, app, db_session, models):
        """Event removed from upstream with no local schedule should be auto-cancelled."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        # Create a local event with no schedule
        event = Event(
            project_name='Test Event',
            project_ref_num=888888,
            external_id='888888',
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=5),
            condition='Unstaffed',
            event_type='Core',
        )
        db_session.add(event)
        db_session.commit()

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)
        change = daemon._handle_cancelled_event(event)
        db_session.commit()

        assert change is not None
        assert change['change_type'] == 'cancelled'
        assert change['is_conflict'] is False
        assert event.condition == 'Canceled'

    def test_cancelled_event_with_schedule_is_conflict(self, app, db_session, models):
        """Event removed from upstream with local schedule should be flagged as conflict."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        # Create employee for FK constraint
        Employee = models['Employee']
        emp = Employee(id='emp1', name='Test Employee', is_active=True, is_supervisor=False)
        db_session.add(emp)
        db_session.flush()

        # Create local event with schedule
        event = Event(
            project_name='Scheduled Event',
            project_ref_num=777777,
            external_id='777777',
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=5),
            condition='Scheduled',
            is_scheduled=True,
            event_type='Core',
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=777777,
            employee_id='emp1',
            schedule_datetime=datetime.now(),
        )
        db_session.add(schedule)
        db_session.commit()

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)
        change = daemon._handle_cancelled_event(event)

        assert change is not None
        assert change['change_type'] == 'conflict'
        assert change['is_conflict'] is True
        # Should NOT auto-cancel when there's a schedule
        assert event.condition == 'Scheduled'

    def test_safe_field_update_on_unscheduled_event(self, app, db_session, models):
        """Safe field changes on unscheduled events should be auto-applied."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        event = Event(
            project_name='Old Name',
            project_ref_num=666666,
            external_id='666666',
            start_datetime=datetime(2026, 4, 10),
            due_datetime=datetime(2026, 4, 15),
            condition='Unstaffed',
            is_scheduled=False,
            event_type='Core',
            store_name='Old Store',
        )
        db_session.add(event)
        db_session.commit()

        upstream_record = {
            'mPlanID': '666666',
            'mPlanName': 'New Name',
            'mPlanStartDate': '04/10/2026',
            'mPlanDueDate': '04/15/2026',
            'condition': 'Unstaffed',
            'LocationName': 'New Store',
        }

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)
        changes = daemon._compare_event(event, upstream_record, {})

        assert len(changes) >= 1
        modified = [c for c in changes if c['change_type'] == 'modified']
        assert len(modified) == 1
        assert modified[0]['is_conflict'] is False
        # Fields should have been updated
        assert event.project_name == 'New Name'
        assert event.store_name == 'New Store'

    def test_date_change_is_conflict(self, app, db_session, models):
        """Protected field (date) changes should be flagged as conflict."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        event = Event(
            project_name='Date Test Event',
            project_ref_num=555555,
            external_id='555555',
            start_datetime=datetime(2026, 4, 10),
            due_datetime=datetime(2026, 4, 15),
            condition='Unstaffed',
            is_scheduled=False,
            event_type='Core',
        )
        db_session.add(event)
        db_session.commit()

        upstream_record = {
            'mPlanID': '555555',
            'mPlanName': 'Date Test Event',
            'mPlanStartDate': '04/12/2026',  # Different date!
            'mPlanDueDate': '04/15/2026',
            'condition': 'Unstaffed',
        }

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)
        changes = daemon._compare_event(event, upstream_record, {})

        conflicts = [c for c in changes if c['is_conflict']]
        assert len(conflicts) == 1
        assert 'start_datetime' in conflicts[0]['summary']

    def test_schedule_mismatch_is_conflict(self, app, db_session, models):
        """Local shows scheduled but Crossmark shows unscheduled = conflict."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        # Create employee for FK constraint
        Employee = models['Employee']
        emp = Employee(id='emp1', name='Test Employee', is_active=True, is_supervisor=False)
        db_session.add(emp)
        db_session.flush()

        event = Event(
            project_name='Schedule Mismatch Event',
            project_ref_num=444444,
            external_id='444444',
            start_datetime=datetime(2026, 4, 10),
            due_datetime=datetime(2026, 4, 15),
            condition='Scheduled',
            is_scheduled=True,
            event_type='Core',
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=444444,
            employee_id='emp1',
            schedule_datetime=datetime.now(),
        )
        db_session.add(schedule)
        db_session.commit()

        upstream_record = {
            'mPlanID': '444444',
            'mPlanName': 'Schedule Mismatch Event',
            'mPlanStartDate': '04/10/2026',
            'mPlanDueDate': '04/15/2026',
            'condition': 'Unstaffed',  # Crossmark says unscheduled
        }

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)
        changes = daemon._compare_event(event, upstream_record, {})

        conflicts = [c for c in changes if c['is_conflict']]
        assert len(conflicts) >= 1
        has_schedule_conflict = any('is_scheduled' in c.get('summary', '') or
                                    'is_scheduled' in (c.get('field_changes') or '')
                                    for c in conflicts)
        assert has_schedule_conflict

    def test_no_change_returns_empty(self, app, db_session, models):
        """When upstream matches local, no changes should be returned."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        event = Event(
            project_name='No Change Event',
            project_ref_num=333333,
            external_id='333333',
            start_datetime=datetime(2026, 4, 10),
            due_datetime=datetime(2026, 4, 15),
            condition='Unstaffed',
            is_scheduled=False,
            event_type='Core',
        )
        db_session.add(event)
        db_session.commit()

        upstream_record = {
            'mPlanID': '333333',
            'mPlanName': 'No Change Event',
            'mPlanStartDate': '04/10/2026',
            'mPlanDueDate': '04/15/2026',
            'condition': 'Unstaffed',
        }

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)
        changes = daemon._compare_event(event, upstream_record, {})

        assert len(changes) == 0


class TestSyncDaemonHelpers:
    """Test helper methods of SyncDaemon."""

    def test_parse_upstream_record(self, app, db_session, models):
        """Upstream records should be correctly parsed into normalized dicts."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)

        record = {
            'mPlanID': '123456',
            'mPlanName': 'Test Event',
            'mPlanStartDate': '04/10/2026',
            'mPlanDueDate': '04/15/2026',
            'condition': 'Scheduled',
            'LocationMVID': 'LOC001',
            'LocationName': 'Store A',
            'storeNumber': '42',
            'scheduleDate': '04/12/2026 09:00:00 AM',
        }

        parsed = daemon._parse_upstream_record(record, {'123456': 120})

        assert parsed['project_name'] == 'Test Event'
        assert parsed['start_datetime'] == datetime(2026, 4, 10)
        assert parsed['due_datetime'] == datetime(2026, 4, 15)
        assert parsed['estimated_time'] == 120
        assert parsed['is_scheduled'] is True
        assert parsed['store_number'] == 42

    def test_map_event_type(self, app, db_session, models):
        """Event type mapping should handle common Crossmark types."""
        from app.services.sync_daemon import SyncDaemon

        Event = models['Event']
        Schedule = models['Schedule']
        SyncChangeLog = models['SyncChangeLog']
        SystemSetting = models['SystemSetting']

        daemon = SyncDaemon(db_session, Event, Schedule, SyncChangeLog, SystemSetting)

        assert daemon._map_event_type('CORE') == 'Core'
        assert daemon._map_event_type('SUPERVISOR') == 'Supervisor'
        assert daemon._map_event_type('JUICER PRODUCTION') == 'Juicer Production'
        assert daemon._map_event_type('JUICER DEEP CLEAN') == 'Juicer Deep Clean'
        assert daemon._map_event_type('DIGITAL SETUP') == 'Digitals'
        assert daemon._map_event_type('FREEOSK') == 'Freeosk'
        assert daemon._map_event_type(None) is None
        assert daemon._map_event_type('Unknown Type') is None


class TestSyncDaemonHealthCheck:
    """Test daemon health check functions."""

    def test_is_daemon_healthy_with_recent_sync(self, app, db_session, models):
        """Daemon should report healthy when last sync was recent."""
        SystemSetting = models['SystemSetting']
        SystemSetting.set_setting(
            'last_successful_sync',
            datetime.utcnow().isoformat(),
            setting_type='string',
            user='test',
        )
        db_session.commit()

        from app.services.sync_daemon import is_daemon_healthy
        assert is_daemon_healthy(max_age_seconds=300) is True

    def test_is_daemon_healthy_with_stale_sync(self, app, db_session, models):
        """Daemon should report unhealthy when last sync is too old."""
        SystemSetting = models['SystemSetting']
        stale_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        SystemSetting.set_setting(
            'last_successful_sync',
            stale_time,
            setting_type='string',
            user='test',
        )
        db_session.commit()

        from app.services.sync_daemon import is_daemon_healthy
        assert is_daemon_healthy(max_age_seconds=300) is False

    def test_is_daemon_healthy_with_no_sync(self, app, db_session, models):
        """Daemon should report unhealthy when no sync has ever run."""
        from app.services.sync_daemon import is_daemon_healthy
        # No last_successful_sync setting exists
        assert is_daemon_healthy() is False


class TestSyncChangeLogModel:
    """Test the SyncChangeLog model."""

    def test_create_change_log_entry(self, app, db_session, models):
        """SyncChangeLog entries should be creatable with all fields."""
        SyncChangeLog = models['SyncChangeLog']

        log = SyncChangeLog(
            change_type='new_event',
            entity_type='event',
            entity_id='12345',
            summary='New event: Test at Store 42',
            is_conflict=False,
            detected_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        saved = SyncChangeLog.query.first()
        assert saved is not None
        assert saved.change_type == 'new_event'
        assert saved.entity_id == '12345'
        assert saved.is_conflict is False
        assert saved.resolved is False

    def test_conflict_entry_with_field_changes(self, app, db_session, models):
        """Conflict entries should store field change diffs as JSON."""
        SyncChangeLog = models['SyncChangeLog']

        field_changes = json.dumps({
            'start_datetime': {
                'local': '2026-04-10T00:00:00',
                'upstream': '2026-04-12T00:00:00',
            }
        })

        log = SyncChangeLog(
            change_type='conflict',
            entity_type='event',
            entity_id='99999',
            summary='Conflict: date mismatch',
            field_changes=field_changes,
            is_conflict=True,
            detected_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        saved = SyncChangeLog.query.first()
        assert saved.is_conflict is True
        parsed = json.loads(saved.field_changes)
        assert 'start_datetime' in parsed

    def test_to_dict_serialization(self, app, db_session, models):
        """to_dict should produce a serializable dict."""
        SyncChangeLog = models['SyncChangeLog']

        log = SyncChangeLog(
            change_type='modified',
            entity_type='event',
            entity_id='55555',
            summary='Event updated',
            is_conflict=False,
            detected_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        d = log.to_dict()
        assert d['change_type'] == 'modified'
        assert d['entity_id'] == '55555'
        assert d['is_conflict'] is False
        assert 'detected_at' in d
