"""
Walmart Event Enrichment Service

Stores Walmart 6-digit event numbers on local events by matching Walmart API
data to local event records. Also auto-imports billing-only events that exist
in Walmart but not in the local database (e.g., Non-Billable Supply Scan Out).

Matching strategies (tried in order):
1. Already matched: Event.walmart_event_id == eventId
2. Core/Supervisor prefix: project_name starts with 6-digit eventId
3. Name containment + date: project_name contains Walmart eventName + same date
"""

import json
import logging
import re
from datetime import datetime

from app.models import get_models, get_db

logger = logging.getLogger(__name__)


class WalmartEventEnrichmentService:
    """Enriches local events with Walmart event IDs and item data."""

    # Large offset for billing-only event project_ref_num to avoid collision
    BILLING_REF_NUM_OFFSET = 900000000

    def __init__(self):
        models = get_models()
        self.db = get_db()
        self.Event = models['Event']

    def enrich_events_from_walmart_data(self, walmart_events):
        """
        Main entry point. Match Walmart API rows to local events and store
        walmart_event_id + walmart_items.

        Args:
            walmart_events: Raw list from Walmart daily-schedule-report API.
                Multiple rows may exist per eventId (one per item).

        Returns:
            dict: {matched: int, items_stored: int, errors: int}
        """
        if not walmart_events:
            return {'matched': 0, 'items_stored': 0, 'errors': 0}

        events_by_id = self._deduplicate_and_collect_items(walmart_events)
        matched = 0
        items_stored = 0
        errors = 0

        for event_id, event_data in events_by_id.items():
            try:
                result = self._match_and_enrich_single(event_id, event_data)
                if result:
                    matched += 1
                    if event_data.get('items'):
                        items_stored += 1
            except Exception as e:
                logger.error(f"Error enriching event {event_id}: {e}")
                errors += 1

        if matched > 0:
            try:
                self.db.session.commit()
                logger.info(f"Enrichment complete: {matched} matched, {items_stored} items stored, {errors} errors")
            except Exception as e:
                self.db.session.rollback()
                logger.error(f"Failed to commit enrichment: {e}")
                return {'matched': 0, 'items_stored': 0, 'errors': errors + 1}

        return {'matched': matched, 'items_stored': items_stored, 'errors': errors}

    def _deduplicate_and_collect_items(self, walmart_events):
        """
        Group raw API rows by eventId and collect item details per event.

        The Walmart daily-schedule-report API returns one row per item per event.
        This groups them into one entry per eventId with an items array.

        Args:
            walmart_events: Raw list from API

        Returns:
            dict: {eventId: {event_data..., items: [{itemNumber, itemDesc, vendorNbr}]}}
        """
        events_by_id = {}

        for row in walmart_events:
            event_id = row.get('eventId') or row.get('event_id')
            if not event_id:
                continue

            event_id_str = str(event_id)

            if event_id_str not in events_by_id:
                events_by_id[event_id_str] = {
                    'eventName': row.get('eventName') or row.get('event_name', ''),
                    'eventDate': row.get('demoDate') or row.get('eventDate') or row.get('demo_date', ''),
                    'status': (row.get('status') or row.get('eventStatus') or '').strip().upper(),
                    'items': []
                }

            # Collect item info if present
            item_number = row.get('itemNbr') or row.get('item_nbr')
            item_desc = row.get('itemDesc') or row.get('item_desc')
            vendor_nbr = row.get('vendorBilledNbr') or row.get('vendor_billed_nbr')

            if item_number or item_desc:
                events_by_id[event_id_str]['items'].append({
                    'itemNumber': str(item_number) if item_number else None,
                    'itemDesc': str(item_desc) if item_desc else None,
                    'vendorNbr': str(vendor_nbr) if vendor_nbr else None,
                })

        logger.info(f"Deduplicated {len(walmart_events)} rows into {len(events_by_id)} unique events")
        return events_by_id

    def _match_and_enrich_single(self, event_id, event_data):
        """
        Try to match a single Walmart event to a local event using three strategies.

        Args:
            event_id: Walmart event ID (string)
            event_data: Dict with eventName, eventDate, items

        Returns:
            Event instance if matched, None otherwise
        """
        items_json = json.dumps(event_data['items']) if event_data.get('items') else None

        # Strategy 1: Already matched by walmart_event_id
        existing = self.Event.query.filter_by(walmart_event_id=event_id).first()
        if existing:
            # Update items if we have new data
            if items_json and existing.walmart_items != items_json:
                existing.walmart_items = items_json
            return existing

        # Strategy 2: Core/Supervisor prefix match (project_name starts with "XXXXXX-")
        if re.match(r'^\d{6}$', event_id):
            prefix_match = self.Event.query.filter(
                self.Event.project_name.like(f'{event_id}-%'),
                self.Event.event_type.in_(['Core', 'Supervisor']),
                self.Event.walmart_event_id.is_(None)
            ).all()

            if prefix_match:
                for event in prefix_match:
                    event.walmart_event_id = event_id
                    if items_json:
                        event.walmart_items = items_json
                logger.info(f"Prefix matched event {event_id} to {len(prefix_match)} Core/Supervisor event(s)")
                return prefix_match[0]

        # Strategy 3: Name containment + date match
        walmart_name = (event_data.get('eventName') or '').strip()
        walmart_date_str = event_data.get('eventDate', '')

        if walmart_name and walmart_date_str:
            try:
                walmart_date = datetime.strptime(walmart_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                logger.warning(f"Could not parse date '{walmart_date_str}' for event {event_id}")
                return None

            # Search for events whose project_name contains the Walmart event name
            # and have a matching date
            candidates = self.Event.query.filter(
                self.Event.project_name.contains(walmart_name),
                self.Event.walmart_event_id.is_(None)
            ).all()

            # Filter by date match (start_datetime or due_datetime)
            for candidate in candidates:
                if candidate.start_datetime and candidate.start_datetime.date() == walmart_date:
                    candidate.walmart_event_id = event_id
                    if items_json:
                        candidate.walmart_items = items_json
                    logger.info(f"Name+date matched event {event_id} ('{walmart_name}') to event {candidate.id}")
                    return candidate
                elif candidate.due_datetime and candidate.due_datetime.date() == walmart_date:
                    candidate.walmart_event_id = event_id
                    if items_json:
                        candidate.walmart_items = items_json
                    logger.info(f"Name+date matched event {event_id} ('{walmart_name}') to event {candidate.id} (by due_date)")
                    return candidate

        logger.debug(f"No match found for Walmart event {event_id} ('{walmart_name}')")
        return None

    def create_billing_only_events(self, events_by_id=None, walmart_events=None):
        """
        Create local Event records for unmatched Walmart events (billing-only).

        These are events like "Non-Billable Supply Scan Out" or "AID Contingency"
        that exist in Walmart but not in the local database.

        Args:
            events_by_id: Pre-deduplicated dict from _deduplicate_and_collect_items.
                If None, will deduplicate from walmart_events.
            walmart_events: Raw Walmart API data (used if events_by_id is None)

        Returns:
            dict: {billing_created: int, errors: int}
        """
        if events_by_id is None:
            if walmart_events is None:
                return {'billing_created': 0, 'errors': 0}
            events_by_id = self._deduplicate_and_collect_items(walmart_events)

        created = 0
        errors = 0

        for event_id, event_data in events_by_id.items():
            try:
                # Skip if already matched to a local event
                existing = self.Event.query.filter(
                    (self.Event.walmart_event_id == event_id) |
                    self.Event.project_name.contains(event_id)
                ).first()
                if existing:
                    continue

                # Parse date
                event_date_str = event_data.get('eventDate', '')
                try:
                    event_date = datetime.strptime(event_date_str, '%Y-%m-%d')
                except (ValueError, TypeError):
                    logger.warning(f"Cannot create billing event {event_id}: invalid date '{event_date_str}'")
                    errors += 1
                    continue

                walmart_name = (event_data.get('eventName') or '').strip()

                # Dedup: check if billing event with same name+date already exists
                existing_billing = self.Event.query.filter_by(
                    walmart_event_id=event_id,
                    billing_only=True
                ).first()
                if existing_billing:
                    continue

                # Generate project_ref_num using offset to avoid collision
                try:
                    ref_num = self.BILLING_REF_NUM_OFFSET + int(event_id)
                except (ValueError, TypeError):
                    ref_num = self.BILLING_REF_NUM_OFFSET + hash(event_id) % 1000000

                # Check ref_num uniqueness
                if self.Event.query.filter_by(project_ref_num=ref_num).first():
                    logger.warning(f"Billing event {event_id}: ref_num {ref_num} already exists, skipping")
                    errors += 1
                    continue

                items_json = json.dumps(event_data['items']) if event_data.get('items') else None

                new_event = self.Event(
                    project_name=f"[BILLING] {walmart_name}",
                    project_ref_num=ref_num,
                    start_datetime=event_date,
                    due_datetime=event_date,
                    estimated_time=5,
                    is_scheduled=False,
                    event_type='Other',
                    condition='Unstaffed',
                    walmart_event_id=event_id,
                    billing_only=True,
                    walmart_items=items_json,
                )
                self.db.session.add(new_event)
                created += 1
                logger.info(f"Created billing-only event: {event_id} '{walmart_name}'")

            except Exception as e:
                logger.error(f"Error creating billing event {event_id}: {e}")
                errors += 1

        if created > 0:
            try:
                self.db.session.commit()
                logger.info(f"Created {created} billing-only events")
            except Exception as e:
                self.db.session.rollback()
                logger.error(f"Failed to commit billing events: {e}")
                return {'billing_created': 0, 'errors': errors + 1}

        return {'billing_created': created, 'errors': errors}
