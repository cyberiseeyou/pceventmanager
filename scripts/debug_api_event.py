#!/usr/bin/env python3
import sys
import os
import json
from datetime import datetime, date

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.integrations.external_api.session_api_service import SessionAPIService

def inspect_event():
    app = create_app()
    with app.app_context():
        print("Logging in to external API...")
        service = SessionAPIService(app)
        if not service.login():
            print("Failed to login")
            return

        print("Fetching events for 2026-01-20 to 2026-01-22...")
        # Get planning events
        data = service.get_all_planning_events(
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 22)
        )
        
        if not data or 'mplans' not in data:
            print("No mplans found")
            return
            
        records = data['mplans']
        print(f"Found {len(records)} events")
        
        # Look for the specific event from screenshot
        # Name contains "619062" or "LKD-CF"
        targets = [r for r in records if '619062' in r.get('name', '') or 'LKD-CF' in r.get('name', '')]
        
        print(f"\nFound {len(targets)} matching events:")
        for t in targets:
            print(f"\n--- Event {t.get('mPlanID')} ---")
            print(f"Name: {t.get('name')}")
            print(f"Start: {t.get('startDate')}")
            print(f"End: {t.get('endDate')}")
            print(f"EventType: '{t.get('eventType')}'")
            print(f"Event_Type: '{t.get('event_type')}'") # Check snake case too
            print(f"EstimatedTime: {t.get('estimatedTime')}")
            print(f"EstimatedMinutes: {t.get('estimatedMinutes')}")
            print(f"Duration: {t.get('duration')}")
            print(f"All Keys: {list(t.keys())}")

if __name__ == "__main__":
    inspect_event()
