"""Tests for Lost Demos feature."""
import pytest
from datetime import datetime, date, timedelta


def _sunday_of(d):
    """Return the Sunday starting the week containing date d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


class TestConfirmLostDemo:
    def test_confirm_lost_creates_record(self, client, db_session, models):
        Event = models['Event']
        LostDemo = models['LostDemo']
        event = Event(
            project_name='Test Event', project_ref_num=99901,
            start_datetime=datetime(2026, 2, 1), due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()
        resp = client.post('/api/lost-demos/99901/confirm', json={}, content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        record = LostDemo.query.filter_by(event_ref_num=99901).first()
        assert record is not None
        assert record.week_start_date == _sunday_of(date(2026, 2, 15))

    def test_confirm_duplicate_returns_409(self, client, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='Test Event', project_ref_num=99902,
            start_datetime=datetime(2026, 2, 1), due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()
        client.post('/api/lost-demos/99902/confirm', json={}, content_type='application/json')
        resp = client.post('/api/lost-demos/99902/confirm', json={}, content_type='application/json')
        assert resp.status_code == 409

    def test_confirm_nonexistent_event_returns_404(self, client, db_session, models):
        resp = client.post('/api/lost-demos/00000/confirm', json={}, content_type='application/json')
        assert resp.status_code == 404


class TestUndoLostDemo:
    def test_undo_deletes_record(self, client, db_session, models):
        Event = models['Event']
        LostDemo = models['LostDemo']
        event = Event(
            project_name='Test Event', project_ref_num=99903,
            start_datetime=datetime(2026, 2, 1), due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()
        client.post('/api/lost-demos/99903/confirm', json={}, content_type='application/json')
        resp = client.delete('/api/lost-demos/99903/confirm')
        assert resp.status_code == 200
        record = LostDemo.query.filter_by(event_ref_num=99903).first()
        assert record is None


class TestListLostDemos:
    def test_list_by_week(self, client, db_session, models):
        Event = models['Event']
        for i, ref in enumerate([99904, 99905]):
            event = Event(
                project_name=f'Lost Event {i}', project_ref_num=ref,
                start_datetime=datetime(2026, 2, 1), due_datetime=datetime(2026, 2, 11 + i),
                event_type='Core'
            )
            db_session.add(event)
        db_session.commit()
        for ref in [99904, 99905]:
            client.post(f'/api/lost-demos/{ref}/confirm', json={}, content_type='application/json')
        week_start = _sunday_of(date(2026, 2, 11)).isoformat()
        resp = client.get(f'/api/lost-demos?week_start={week_start}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['data']) == 2


class TestConfirmedRefs:
    def test_confirmed_refs_returns_list(self, client, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='Test', project_ref_num=99906,
            start_datetime=datetime(2026, 2, 1), due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()
        client.post('/api/lost-demos/99906/confirm', json={}, content_type='application/json')
        resp = client.get('/api/lost-demos/confirmed-refs')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 99906 in data['data']
