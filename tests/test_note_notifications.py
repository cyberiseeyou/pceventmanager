"""Tests for note notification system: snooze, dismiss, pending query"""
import pytest
from datetime import datetime, date, time, timedelta
from unittest.mock import patch
from app.models import get_models

AUTH_PATCH = 'app.routes.auth.is_authenticated'


class TestNoteSnoozedUntil:
    """Test the snoozed_until column on the Note model"""

    def test_note_has_snoozed_until_field(self, db_session, models):
        """snoozed_until should be nullable DateTime, default None"""
        Note = models['Note']
        note = Note(title='Test note', note_type='task')
        db_session.add(note)
        db_session.commit()

        assert note.snoozed_until is None

    def test_note_snoozed_until_can_be_set(self, db_session, models):
        """snoozed_until can be set to a datetime"""
        Note = models['Note']
        snooze_time = datetime.now() + timedelta(minutes=15)
        note = Note(title='Snoozed note', note_type='task', snoozed_until=snooze_time)
        db_session.add(note)
        db_session.commit()

        fetched = db_session.query(Note).get(note.id)
        assert fetched.snoozed_until is not None

    def test_note_to_dict_includes_snoozed_until(self, db_session, models):
        """to_dict() should include snoozed_until"""
        Note = models['Note']
        note = Note(title='Dict test', note_type='task')
        db_session.add(note)
        db_session.commit()

        d = note.to_dict()
        assert 'snoozed_until' in d
        assert d['snoozed_until'] is None

    def test_note_to_dict_snoozed_until_format(self, db_session, models):
        """to_dict() snoozed_until should be ISO format string when set"""
        Note = models['Note']
        snooze_time = datetime(2026, 3, 13, 15, 30, 0)
        note = Note(title='Format test', note_type='task', snoozed_until=snooze_time)
        db_session.add(note)
        db_session.commit()

        d = note.to_dict()
        assert d['snoozed_until'] == '2026-03-13T15:30:00'


class TestSnoozeEndpoint:
    """Test POST /api/notes/<id>/snooze"""

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_sets_snoozed_until(self, mock_auth, client, db_session, models):
        """Snoozing a note should set snoozed_until to now + duration"""
        Note = models['Note']
        note = Note(title='Snooze me', note_type='task', due_date=date.today(), reminder_sent=False)
        db_session.add(note)
        db_session.commit()

        response = client.post(f'/api/notes/{note.id}/snooze',
                               json={'duration': 15},
                               content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'snoozed_until' in data

        # Verify DB was updated
        db_session.refresh(note)
        assert note.snoozed_until is not None
        assert note.reminder_sent is False  # Reset to False for re-trigger

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_resets_reminder_sent(self, mock_auth, client, db_session, models):
        """Snoozing should reset reminder_sent to False"""
        Note = models['Note']
        note = Note(title='Already sent', note_type='task', due_date=date.today(), reminder_sent=True)
        db_session.add(note)
        db_session.commit()

        response = client.post(f'/api/notes/{note.id}/snooze',
                               json={'duration': 30},
                               content_type='application/json')
        assert response.status_code == 200

        db_session.refresh(note)
        assert note.reminder_sent is False

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_invalid_duration(self, mock_auth, client, db_session, models):
        """Invalid duration should return 400"""
        Note = models['Note']
        note = Note(title='Bad duration', note_type='task')
        db_session.add(note)
        db_session.commit()

        response = client.post(f'/api/notes/{note.id}/snooze',
                               json={'duration': 999},
                               content_type='application/json')
        assert response.status_code == 400

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_nonexistent_note(self, mock_auth, client, db_session):
        """Snoozing nonexistent note should return 404"""
        response = client.post('/api/notes/99999/snooze',
                               json={'duration': 15},
                               content_type='application/json')
        assert response.status_code == 404


class TestPendingNotificationsWithSnooze:
    """Test that snoozed notes are excluded from pending notifications"""

    @patch(AUTH_PATCH, return_value=True)
    def test_snoozed_note_excluded_from_pending(self, mock_auth, client, db_session, models):
        """A note snoozed until the future should NOT appear in pending"""
        Note = models['Note']
        note = Note(
            title='Snoozed note',
            note_type='task',
            due_date=date.today(),
            is_completed=False,
            reminder_sent=False,
            snoozed_until=datetime.now() + timedelta(hours=1)
        )
        db_session.add(note)
        db_session.commit()

        response = client.get('/api/notes/notifications/pending')
        assert response.status_code == 200
        data = response.get_json()
        note_ids = [n['id'] for n in data['notifications']]
        assert note.id not in note_ids

    @patch(AUTH_PATCH, return_value=True)
    def test_expired_snooze_appears_in_pending(self, mock_auth, client, db_session, models):
        """A note whose snooze has expired SHOULD appear in pending"""
        Note = models['Note']
        note = Note(
            title='Expired snooze',
            note_type='task',
            due_date=date.today(),
            is_completed=False,
            reminder_sent=False,
            snoozed_until=datetime.now() - timedelta(minutes=5)
        )
        db_session.add(note)
        db_session.commit()

        response = client.get('/api/notes/notifications/pending')
        assert response.status_code == 200
        data = response.get_json()
        note_ids = [n['id'] for n in data['notifications']]
        assert note.id in note_ids

    @patch(AUTH_PATCH, return_value=True)
    def test_null_snoozed_until_appears_in_pending(self, mock_auth, client, db_session, models):
        """A note with no snooze (NULL) should appear in pending normally"""
        Note = models['Note']
        note = Note(
            title='No snooze',
            note_type='task',
            due_date=date.today(),
            is_completed=False,
            reminder_sent=False,
            snoozed_until=None
        )
        db_session.add(note)
        db_session.commit()

        response = client.get('/api/notes/notifications/pending')
        assert response.status_code == 200
        data = response.get_json()
        note_ids = [n['id'] for n in data['notifications']]
        assert note.id in note_ids
