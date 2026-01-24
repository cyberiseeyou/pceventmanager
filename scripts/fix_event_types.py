#!/usr/bin/env python3
"""
Database Refresh & Fix Script

This script can:
1. Perform a full database refresh from the Crossmark API
2. Fix truncated event types using pairing logic (--fix-truncated)

The truncated name fix uses Core/Supervisor pairing: events come in pairs with
adjacent project_ref_num values. If one is correctly typed, the other can be inferred.

Usage:
    cd /home/elliot/flask-schedule-webapp
    
    # Fix truncated event types without API refresh (safe, quick):
    python scripts/fix_event_types.py --fix-truncated
    
    # Full API refresh (overwrites local data):
    python scripts/fix_event_types.py --force
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.services.database_refresh_service import DatabaseRefreshService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def fix_truncated_events():
    """
    Fix event types for events with truncated names using pairing logic.
    
    Core and Supervisor events come in pairs with adjacent project_ref_num values.
    If one partner is correctly typed, we can infer the other's type.
    
    This is safe to run - it doesn't delete any data, just fixes event_type field.
    """
    app = create_app()
    
    with app.app_context():
        from flask import current_app
        from app.extensions import db
        
        Event = current_app.config['Event']
        
        print(f"\n{'='*60}")
        print("Fix Truncated Event Types")
        print(f"{'='*60}")
        
        # Find events with truncated names (100 chars) typed as "Other"
        truncated_other = Event.query.filter(
            Event.event_type == 'Other',
            db.func.length(Event.project_name) >= 99  # Allow for slight variations
        ).all()
        
        print(f"Found {len(truncated_other)} 'Other' type events with truncated names")
        
        if not truncated_other:
            print("✅ No truncated events need fixing!")
            return
        
        fixed_count = 0
        
        for event in truncated_other:
            new_type = None
            
            # Check adjacent ref_nums for paired events
            prev_event = Event.query.filter_by(
                project_ref_num=event.project_ref_num - 1
            ).first()
            next_event = Event.query.filter_by(
                project_ref_num=event.project_ref_num + 1
            ).first()
            
            # If partner is Core, this should be Supervisor (and vice versa)
            # Core events typically have higher ref_num than their Supervisor partner
            if prev_event and prev_event.event_type in ('Core', 'Supervisor'):
                # Check if they share similar base name (same event family)
                if _names_match(event.project_name, prev_event.project_name):
                    if prev_event.event_type == 'Core':
                        new_type = 'Supervisor'
                    else:
                        new_type = 'Core'
            
            if not new_type and next_event and next_event.event_type in ('Core', 'Supervisor'):
                if _names_match(event.project_name, next_event.project_name):
                    if next_event.event_type == 'Core':
                        new_type = 'Supervisor'
                    else:
                        new_type = 'Core'
            
            # Additional heuristics for unpaired events
            if not new_type:
                name_upper = (event.project_name or '').upper()
                # Check for patterns that indicate Core events
                # These prefixes typically indicate demo/core events
                if any(p in name_upper for p in ['-CF-', '-LKD-', '-AF-', '-MAP-', 'DEMO']):
                    # Without a partner, we can't be sure - check condition
                    # Events marked as "In Progress" are typically Core (being worked)
                    if event.condition == 'In Progress':
                        new_type = 'Core'
                    elif event.condition == 'Scheduled':
                        # Scheduled events without a partner - likely Supervisor
                        new_type = 'Supervisor'
            
            # Final fallback: if partner is also Other with same base name, use position
            # Pattern: lower ref_num = Supervisor, higher ref_num = Core
            if not new_type:
                if prev_event and prev_event.event_type == 'Other' and _names_match(event.project_name, prev_event.project_name):
                    # This event has higher ref_num than its partner -> Core
                    new_type = 'Core'
                elif next_event and next_event.event_type == 'Other' and _names_match(event.project_name, next_event.project_name):
                    # This event has lower ref_num than its partner -> Supervisor
                    new_type = 'Supervisor'
            
            if new_type:
                print(f"  Fixing {event.project_ref_num}: Other -> {new_type}")
                print(f"    Name: {event.project_name[:60]}...")
                event.event_type = new_type
                fixed_count += 1
        
        if fixed_count > 0:
            db.session.commit()
            print(f"\n✅ Fixed {fixed_count} events!")
        else:
            print("\n⚠️  Could not determine type for any events (no paired partners found)")


def _names_match(name1, name2):
    """
    Check if two event names appear to be from the same event "family".
    They should share the same base (project number and description).
    """
    if not name1 or not name2:
        return False
    
    # Extract project number (first segment before first dash or space)
    # e.g., "619062-LKD-CF-..." extracts "619062"
    base1 = name1.split('-')[0].strip() if '-' in name1 else name1[:6]
    base2 = name2.split('-')[0].strip() if '-' in name2 else name2[:6]
    
    return base1 == base2


def console_progress_callback(current_step, total_steps, step_label, processed=0, total=0, status='running', stats=None, error=None):
    """Print progress to console"""
    if status == 'error':
        print(f"❌ Error: {error}")
        return

    progress = ""
    if total > 0:
        percent = int((processed / total) * 100)
        progress = f"[{processed}/{total}] ({percent}%)"
    
    if status == 'completed':
        print(f"✅ {step_label}")
        if stats:
            print("\nStatistics:")
            print(f"  - Total Fetched: {stats.get('total_fetched', 0)}")
            print(f"  - Cleared: {stats.get('cleared', 0)}")
            print(f"  - Created Events: {stats.get('created', 0)}")
            print(f"  - Schedules Created: {stats.get('schedules', 0)}")
            print(f"  - Core Events Fixed: Check the daily view!")
    else:
        # Overwrite line for progress (simple version)
        print(f"Step {current_step}/{total_steps}: {step_label} {progress}")


def run_fix_refresh(force=False):
    app = create_app()
    
    with app.app_context():
        print(f"\n{'='*60}")
        print(f"Event Type Fix (Database Refresh)")
        print(f"{'='*60}")
        print("This will re-fetch all data from Crossmark API.")
        print("It will fix event types for events with truncated names by using API data.")
        print("⚠️  WARNING: Local unsynced changes will be overwritten.")
        
        if not force:
            confirm = input("\nAre you sure you want to continue? (y/N): ")
            if confirm.lower() != 'y':
                print("Aborted.")
                return

        print("\nStarting refresh...\n")
        
        service = DatabaseRefreshService(progress_callback=console_progress_callback)
        result = service.refresh()
        
        if result['success']:
            print(f"\n✨ {result['message']}")
            if result.get('warning'):
                print(f"⚠️  Warning: {result['warning']}")
        else:
            print(f"\n❌ Failed: {result['message']}")
            sys.exit(1)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix event types (truncated or via API refresh)')
    parser.add_argument('--force', action='store_true', help='Full API refresh (skip confirmation)')
    parser.add_argument('--fix-truncated', action='store_true', 
                        help='Fix truncated event types using pairing logic (safe, no API call)')
    
    args = parser.parse_args()
    
    if args.fix_truncated:
        fix_truncated_events()
    else:
        run_fix_refresh(force=args.force)

