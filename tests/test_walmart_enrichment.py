"""
Tests for WalmartEventEnrichmentService.

Tests cover:
- Deduplication and item collection from raw API rows
- Core/Supervisor prefix matching
- Name containment + date matching
- Billing-only event creation
- No false positive matches
"""

import json
import pytest
from datetime import datetime, timedelta


class TestDeduplicateAndCollectItems:
    """Test _deduplicate_and_collect_items merges rows and collects items."""

    def test_merges_duplicate_event_ids(self, app, db_session, models):
        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        raw = [
            {'eventId': '620001', 'eventName': 'Test Event', 'demoDate': '2026-03-01',
             'status': 'APPROVED', 'itemNbr': '100', 'itemDesc': 'Item A', 'vendorBilledNbr': '5001'},
            {'eventId': '620001', 'eventName': 'Test Event', 'demoDate': '2026-03-01',
             'status': 'APPROVED', 'itemNbr': '200', 'itemDesc': 'Item B', 'vendorBilledNbr': '5002'},
            {'eventId': '620002', 'eventName': 'Other Event', 'demoDate': '2026-03-01',
             'status': 'APPROVED', 'itemNbr': '300', 'itemDesc': 'Item C', 'vendorBilledNbr': '5003'},
        ]

        result = service._deduplicate_and_collect_items(raw)
        assert len(result) == 2
        assert '620001' in result
        assert '620002' in result

        # Event 620001 should have 2 items
        assert len(result['620001']['items']) == 2
        assert result['620001']['items'][0]['itemNumber'] == '100'
        assert result['620001']['items'][1]['itemNumber'] == '200'

        # Event 620002 should have 1 item
        assert len(result['620002']['items']) == 1

    def test_handles_missing_item_fields(self, app, db_session, models):
        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        raw = [
            {'eventId': '620010', 'eventName': 'No Items Event', 'demoDate': '2026-03-01',
             'status': 'APPROVED'},
        ]

        result = service._deduplicate_and_collect_items(raw)
        assert len(result['620010']['items']) == 0


class TestCoreSupervisorPrefixMatching:
    """Test matching by 6-digit prefix in project_name for Core/Supervisor events."""

    def test_matches_core_event_by_prefix(self, app, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='620458-JJSF-Super Pretzel King Size',
            project_ref_num=999001,
            start_datetime=datetime(2026, 3, 1),
            due_datetime=datetime(2026, 3, 3),
            event_type='Core',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        walmart_events = [
            {'eventId': '620458', 'eventName': 'JJSF-Super Pretzel', 'demoDate': '2026-03-01',
             'status': 'APPROVED', 'itemNbr': '100', 'itemDesc': 'Pretzel', 'vendorBilledNbr': '7001'},
        ]

        result = service.enrich_events_from_walmart_data(walmart_events)
        assert result['matched'] == 1

        db_session.refresh(event)
        assert event.walmart_event_id == '620458'
        assert event.walmart_items is not None
        items = json.loads(event.walmart_items)
        assert len(items) == 1
        assert items[0]['itemDesc'] == 'Pretzel'

    def test_matches_supervisor_event_by_prefix(self, app, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='620458-Supervisor-Super Pretzel',
            project_ref_num=999002,
            start_datetime=datetime(2026, 3, 1),
            due_datetime=datetime(2026, 3, 3),
            event_type='Supervisor',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        walmart_events = [
            {'eventId': '620458', 'eventName': 'Supervisor-Super Pretzel', 'demoDate': '2026-03-01',
             'status': 'APPROVED'},
        ]

        result = service.enrich_events_from_walmart_data(walmart_events)
        assert result['matched'] == 1
        db_session.refresh(event)
        assert event.walmart_event_id == '620458'


class TestNameContainmentMatching:
    """Test matching by project_name containing Walmart eventName + date."""

    def test_matches_juicer_by_name_and_date(self, app, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='02-14 8HR-ES1-Juicer Production-SPCLTY (260205543343) - ES1',
            project_ref_num=999003,
            start_datetime=datetime(2026, 2, 14),
            due_datetime=datetime(2026, 2, 14),
            event_type='Juicer Production',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        walmart_events = [
            {'eventId': '620999', 'eventName': '02-14 8HR-ES1-Juicer Production-SPCLTY',
             'demoDate': '2026-02-14', 'status': 'APPROVED'},
        ]

        result = service.enrich_events_from_walmart_data(walmart_events)
        assert result['matched'] == 1
        db_session.refresh(event)
        assert event.walmart_event_id == '620999'

    def test_no_match_on_wrong_date(self, app, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='02-14 8HR-ES1-Juicer Production-SPCLTY (260205543343) - ES1',
            project_ref_num=999004,
            start_datetime=datetime(2026, 2, 14),
            due_datetime=datetime(2026, 2, 14),
            event_type='Juicer Production',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        # Different date
        walmart_events = [
            {'eventId': '620999', 'eventName': '02-14 8HR-ES1-Juicer Production-SPCLTY',
             'demoDate': '2026-03-01', 'status': 'APPROVED'},
        ]

        result = service.enrich_events_from_walmart_data(walmart_events)
        assert result['matched'] == 0
        db_session.refresh(event)
        assert event.walmart_event_id is None

    def test_no_false_positive_similar_names(self, app, db_session, models):
        """Events with similar but non-matching names should not match."""
        Event = models['Event']
        event = Event(
            project_name='Juicer Deep Clean Special',
            project_ref_num=999005,
            start_datetime=datetime(2026, 3, 1),
            due_datetime=datetime(2026, 3, 1),
            event_type='Juicer Deep Clean',
            is_scheduled=False,
        )
        db_session.add(event)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        # Name does NOT match (different event)
        walmart_events = [
            {'eventId': '621000', 'eventName': 'Juicer Production-SPCLTY',
             'demoDate': '2026-03-01', 'status': 'APPROVED'},
        ]

        result = service.enrich_events_from_walmart_data(walmart_events)
        assert result['matched'] == 0
        db_session.refresh(event)
        assert event.walmart_event_id is None


class TestBillingOnlyEventCreation:
    """Test auto-creation of billing-only events for unmatched Walmart events."""

    def test_creates_billing_event(self, app, db_session, models):
        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        events_by_id = {
            '621500': {
                'eventName': 'Non-Billable Supply Scan Out',
                'eventDate': '2026-03-01',
                'status': 'APPROVED',
                'items': [{'itemNumber': '555', 'itemDesc': 'Supplies', 'vendorNbr': '9001'}]
            }
        }

        result = service.create_billing_only_events(events_by_id=events_by_id)
        assert result['billing_created'] == 1

        Event = models['Event']
        billing_event = Event.query.filter_by(walmart_event_id='621500').first()
        assert billing_event is not None
        assert billing_event.billing_only is True
        assert billing_event.project_name == '[BILLING] Non-Billable Supply Scan Out'
        assert billing_event.project_ref_num == 900000000 + 621500

    def test_skips_already_matched_events(self, app, db_session, models):
        """Events already in local DB should not create billing duplicates."""
        Event = models['Event']
        existing = Event(
            project_name='620458-JJSF-Super Pretzel',
            project_ref_num=999006,
            start_datetime=datetime(2026, 3, 1),
            due_datetime=datetime(2026, 3, 3),
            event_type='Core',
            is_scheduled=False,
            walmart_event_id='620458',
        )
        db_session.add(existing)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        events_by_id = {
            '620458': {
                'eventName': 'JJSF-Super Pretzel',
                'eventDate': '2026-03-01',
                'status': 'APPROVED',
                'items': []
            }
        }

        result = service.create_billing_only_events(events_by_id=events_by_id)
        assert result['billing_created'] == 0

    def test_deduplicates_billing_events(self, app, db_session, models):
        """Should not create duplicate billing events on repeated calls."""
        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        events_by_id = {
            '621600': {
                'eventName': 'AID Contingency',
                'eventDate': '2026-03-01',
                'status': 'APPROVED',
                'items': []
            }
        }

        result1 = service.create_billing_only_events(events_by_id=events_by_id)
        assert result1['billing_created'] == 1

        result2 = service.create_billing_only_events(events_by_id=events_by_id)
        assert result2['billing_created'] == 0


class TestAlreadyMatchedUpdate:
    """Test that already-matched events get their items updated."""

    def test_updates_items_on_already_matched(self, app, db_session, models):
        Event = models['Event']
        event = Event(
            project_name='620458-JJSF-Super Pretzel',
            project_ref_num=999007,
            start_datetime=datetime(2026, 3, 1),
            due_datetime=datetime(2026, 3, 3),
            event_type='Core',
            is_scheduled=False,
            walmart_event_id='620458',
        )
        db_session.add(event)
        db_session.commit()

        from app.services.walmart_event_enrichment import WalmartEventEnrichmentService
        service = WalmartEventEnrichmentService()

        walmart_events = [
            {'eventId': '620458', 'eventName': 'JJSF-Super Pretzel', 'demoDate': '2026-03-01',
             'status': 'APPROVED', 'itemNbr': '999', 'itemDesc': 'Updated Item', 'vendorBilledNbr': '8001'},
        ]

        result = service.enrich_events_from_walmart_data(walmart_events)
        assert result['matched'] == 1

        db_session.refresh(event)
        items = json.loads(event.walmart_items)
        assert len(items) == 1
        assert items[0]['itemDesc'] == 'Updated Item'
