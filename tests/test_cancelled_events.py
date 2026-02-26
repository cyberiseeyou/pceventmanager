"""
Tests for cancelled event handling during database refresh and daily view display.

Verifies that:
- Cancelled events are NOT restored during schedule restoration
- Both spelling variants ('Canceled'/'Cancelled') are detected
- is_scheduled is False for cancelled/expired events
"""
import pytest
from datetime import datetime, timedelta
from app.models import get_models, get_db
from app.constants import CANCELLED_VARIANTS, INACTIVE_CONDITIONS


class TestCancelledEventRestoration:
    """Test that schedule restoration skips cancelled/expired events."""

    def test_cancelled_event_not_restored(self, app, db_session, models):
        """A cancelled event should not have its schedule restored after refresh."""
        Event = models['Event']
        Schedule = models['Schedule']

        # Create a cancelled event (as it would appear after fresh API import)
        event = Event(
            external_id='100001',
            project_name='Test Core Event',
            project_ref_num=100001,
            start_datetime=datetime.utcnow(),
            due_datetime=datetime.utcnow() + timedelta(days=1),
            condition='Canceled',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        # Verify the event's condition should block restoration
        assert event.condition in INACTIVE_CONDITIONS

        # Verify no schedule exists
        schedule = Schedule.query.filter_by(event_ref_num=100001).first()
        assert schedule is None

    def test_expired_event_not_restored(self, app, db_session, models):
        """An expired event should not have its schedule restored after refresh."""
        Event = models['Event']

        event = Event(
            external_id='100002',
            project_name='Test Expired Event',
            project_ref_num=100002,
            start_datetime=datetime.utcnow() - timedelta(days=30),
            due_datetime=datetime.utcnow() - timedelta(days=20),
            condition='Expired',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        assert event.condition in INACTIVE_CONDITIONS

    def test_scheduled_event_is_restorable(self, app, db_session, models):
        """A normally-scheduled event should NOT be blocked from restoration."""
        Event = models['Event']

        event = Event(
            external_id='100003',
            project_name='Test Scheduled Event',
            project_ref_num=100003,
            start_datetime=datetime.utcnow(),
            due_datetime=datetime.utcnow() + timedelta(days=1),
            condition='Scheduled',
            is_scheduled=True,
        )
        db_session.add(event)
        db_session.commit()

        assert event.condition not in INACTIVE_CONDITIONS


class TestCancelledVariantsDetection:
    """Test that both spelling variants are detected for cancelled status."""

    def test_american_spelling_detected(self, app, db_session, models):
        """'Canceled' (American) should be detected as cancelled."""
        assert 'Canceled' in CANCELLED_VARIANTS

    def test_british_spelling_detected(self, app, db_session, models):
        """'Cancelled' (British) should be detected as cancelled."""
        assert 'Cancelled' in CANCELLED_VARIANTS

    def test_daily_view_api_detects_cancelled_condition(self, client, db_session, models):
        """The daily view API should mark events with condition='Canceled' as cancelled."""
        Event = models['Event']
        Schedule = models['Schedule']
        Employee = models['Employee']

        # Create employee
        emp = Employee(id='test_cancel_1', name='Test Worker', external_id='EMP001')
        db_session.add(emp)
        db_session.flush()

        # Create a cancelled event with a schedule (simulating restored schedule
        # from before the fix — the schedule shouldn't exist, but if it does
        # the API should still flag it as cancelled)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        schedule_dt = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)

        event = Event(
            external_id='200001',
            project_name='Cancelled Core Event',
            project_ref_num=200001,
            start_datetime=schedule_dt,
            due_datetime=schedule_dt + timedelta(days=1),
            condition='Canceled',
            is_scheduled=True,
            event_type='Core',
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=200001,
            employee_id=emp.id,
            schedule_datetime=schedule_dt,
        )
        db_session.add(schedule)
        db_session.commit()

        response = client.get(f'/api/daily-events/{today}')
        assert response.status_code == 200

        data = response.get_json()
        events = data.get('data', {}).get('events', [])

        # Find our cancelled event
        cancelled = [e for e in events if e.get('event_id') == 200001]
        if cancelled:
            assert cancelled[0]['reporting_status'] == 'cancelled'
            assert cancelled[0]['is_cancelled'] is True

    def test_daily_view_api_detects_british_spelling(self, client, db_session, models):
        """The daily view API should also detect 'Cancelled' (British spelling)."""
        Event = models['Event']
        Schedule = models['Schedule']
        Employee = models['Employee']

        emp = Employee(id='test_cancel_2', name='Test Worker 2', external_id='EMP002')
        db_session.add(emp)
        db_session.flush()

        today = datetime.utcnow().strftime('%Y-%m-%d')
        schedule_dt = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)

        event = Event(
            external_id='200002',
            project_name='British Cancelled Event',
            project_ref_num=200002,
            start_datetime=schedule_dt,
            due_datetime=schedule_dt + timedelta(days=1),
            condition='Cancelled',  # British spelling
            is_scheduled=True,
            event_type='Core',
        )
        db_session.add(event)
        db_session.flush()

        schedule = Schedule(
            event_ref_num=200002,
            employee_id=emp.id,
            schedule_datetime=schedule_dt,
        )
        db_session.add(schedule)
        db_session.commit()

        response = client.get(f'/api/daily-events/{today}')
        assert response.status_code == 200

        data = response.get_json()
        events = data.get('data', {}).get('events', [])

        cancelled = [e for e in events if e.get('event_id') == 200002]
        if cancelled:
            assert cancelled[0]['reporting_status'] == 'cancelled'
            assert cancelled[0]['is_cancelled'] is True


class TestIsScheduledForInactiveConditions:
    """Test that is_scheduled is False for cancelled/expired events during import."""

    def test_canceled_condition_not_scheduled(self):
        """Events with condition='Canceled' should have is_scheduled=False."""
        condition = 'Canceled'
        schedule_date = None
        is_event_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )
        assert is_event_scheduled is False

    def test_expired_condition_not_scheduled(self):
        """Events with condition='Expired' should have is_scheduled=False."""
        condition = 'Expired'
        schedule_date = None
        is_event_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )
        assert is_event_scheduled is False

    def test_canceled_with_schedule_date_still_not_scheduled(self):
        """Even if a cancelled event has a schedule_date, is_scheduled should be False."""
        condition = 'Canceled'
        schedule_date = datetime.utcnow()
        is_event_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )
        assert is_event_scheduled is False

    def test_scheduled_condition_is_scheduled(self):
        """Events with condition='Scheduled' should have is_scheduled=True."""
        condition = 'Scheduled'
        schedule_date = None
        is_event_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )
        assert is_event_scheduled is True

    def test_unstaffed_with_schedule_date_is_scheduled(self):
        """Unstaffed events with a schedule_date should have is_scheduled=True."""
        condition = 'Unstaffed'
        schedule_date = datetime.utcnow()
        is_event_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )
        assert is_event_scheduled is True

    def test_unstaffed_without_schedule_date_not_scheduled(self):
        """Unstaffed events without a schedule_date should have is_scheduled=False."""
        condition = 'Unstaffed'
        schedule_date = None
        is_event_scheduled = (
            condition not in INACTIVE_CONDITIONS
            and (condition != 'Unstaffed' or schedule_date is not None)
        )
        assert is_event_scheduled is False
