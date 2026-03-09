"""
Tests for LostDemo model.
"""
from datetime import date, datetime
import pytest
from app.models import get_models


class TestLostDemoModel:
    """Tests for LostDemo model creation and attributes."""

    def test_model_registered_in_factory(self, models):
        """LostDemo should be accessible via get_models()."""
        assert 'LostDemo' in models

    def test_create_lost_demo(self, db_session, models):
        """Should create a LostDemo record with required fields."""
        Event = models['Event']
        LostDemo = models['LostDemo']

        # Create a prerequisite event
        event = Event(
            project_name='Test Core Event',
            project_ref_num=99001,
            start_datetime=datetime(2026, 3, 3),
            due_datetime=datetime(2026, 3, 7),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        lost = LostDemo(
            event_ref_num=99001,
            week_start_date=date(2026, 3, 2),
            notes='Store refused entry'
        )
        db_session.add(lost)
        db_session.commit()

        result = LostDemo.query.filter_by(event_ref_num=99001).first()
        assert result is not None
        assert result.week_start_date == date(2026, 3, 2)
        assert result.notes == 'Store refused entry'
        assert result.confirmed_at is not None

    def test_confirmed_at_defaults_to_now(self, db_session, models):
        """confirmed_at should default to current UTC time."""
        Event = models['Event']
        LostDemo = models['LostDemo']

        event = Event(
            project_name='Test Event',
            project_ref_num=99002,
            start_datetime=datetime(2026, 3, 3),
            due_datetime=datetime(2026, 3, 7),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        before = datetime.utcnow()
        lost = LostDemo(
            event_ref_num=99002,
            week_start_date=date(2026, 3, 2)
        )
        db_session.add(lost)
        db_session.commit()

        assert lost.confirmed_at >= before

    def test_event_ref_num_unique(self, db_session, models):
        """event_ref_num should be unique - no duplicate lost demos per event."""
        Event = models['Event']
        LostDemo = models['LostDemo']

        event = Event(
            project_name='Test Event',
            project_ref_num=99003,
            start_datetime=datetime(2026, 3, 3),
            due_datetime=datetime(2026, 3, 7),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        lost1 = LostDemo(
            event_ref_num=99003,
            week_start_date=date(2026, 3, 2)
        )
        db_session.add(lost1)
        db_session.commit()

        lost2 = LostDemo(
            event_ref_num=99003,
            week_start_date=date(2026, 3, 9)
        )
        db_session.add(lost2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_notes_nullable(self, db_session, models):
        """notes field should be optional."""
        Event = models['Event']
        LostDemo = models['LostDemo']

        event = Event(
            project_name='Test Event',
            project_ref_num=99004,
            start_datetime=datetime(2026, 3, 3),
            due_datetime=datetime(2026, 3, 7),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        lost = LostDemo(
            event_ref_num=99004,
            week_start_date=date(2026, 3, 2)
        )
        db_session.add(lost)
        db_session.commit()

        assert lost.notes is None

    def test_repr(self, db_session, models):
        """__repr__ should include event_ref_num and week_start_date."""
        LostDemo = models['LostDemo']
        lost = LostDemo(
            event_ref_num=99999,
            week_start_date=date(2026, 3, 2)
        )
        repr_str = repr(lost)
        assert '99999' in repr_str
        assert '2026-03-02' in repr_str

    def test_week_start_date_index_exists(self, db_session, models):
        """The week_start_date index should exist on the table."""
        LostDemo = models['LostDemo']
        indexes = {idx.name for idx in LostDemo.__table__.indexes}
        assert 'idx_lost_demos_week' in indexes
