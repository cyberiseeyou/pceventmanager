"""
Database Manager for EDR Events Caching
========================================

This module provides database operations for caching event data from the
browse_events API call. It uses SQLite for simplicity and portability.

Features:
- Store bulk event data from single API call
- Track data freshness with timestamps
- Query events by ID, date range, status, etc.
- Automatic cache expiry management
"""

import sqlite3
import json
import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path


class EDRDatabaseManager:
    """
    Manages SQLite database for caching EDR event data.

    This reduces the need for repeated MFA authentication by storing
    event data fetched from the browse_events API call.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Defaults to 'edr_cache.db' in current directory.
        """
        if db_path is None:
            # Store in edr directory by default
            db_path = Path(__file__).parent / "edr_cache.db"

        self.db_path = str(db_path)
        self.conn = None
        self._init_database()

    def _init_database(self):
        """Initialize database connection and create tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        cursor = self.conn.cursor()

        # Create events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                event_type TEXT,
                event_date TEXT,
                bill_type TEXT,
                event_status TEXT,
                lock_date TEXT,
                event_fee TEXT,
                item_nbr INTEGER,
                featured_item_ind TEXT,
                item_desc TEXT,
                upc_nbr INTEGER,
                dept_nbr INTEGER,
                dept_desc TEXT,
                vendor_nbr INTEGER,
                vendor_desc TEXT,
                vendor_billed_nbr INTEGER,
                vendor_billed_desc TEXT,
                target_club_cnt INTEGER,
                sub_cat_nbr INTEGER,
                sub_cat_desc TEXT,
                event_name TEXT,
                country TEXT,
                last_change_user TEXT,
                claim_nbr TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                store_number TEXT,
                UNIQUE(event_id, item_nbr, fetched_at)
            )
        ''')

        # Create indexes for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_event_id ON events(event_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_event_date ON events(event_date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_event_status ON events(event_status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetched_at ON events(fetched_at)
        ''')

        # Create cache metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_type TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                store_number TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_count INTEGER,
                success BOOLEAN
            )
        ''')

        self.conn.commit()

    def store_events(self, events_data: List[Dict[str, Any]], store_number: str,
                    start_date: Optional[str] = None, end_date: Optional[str] = None) -> int:
        """
        Store bulk events data from browse_events API call.

        Args:
            events_data: List of event dictionaries from browse_events()
            store_number: Store number these events belong to
            start_date: Start date of the query (optional)
            end_date: End date of the query (optional)

        Returns:
            Number of events stored
        """
        cursor = self.conn.cursor()
        stored_count = 0
        fetched_at = datetime.datetime.now().isoformat()

        for event in events_data:
            try:
                # Convert claim_nbr list to JSON string for storage
                claim_nbr_json = json.dumps(event.get('claimNbr', []))

                cursor.execute('''
                    INSERT OR REPLACE INTO events (
                        event_id, event_type, event_date, bill_type, event_status,
                        lock_date, event_fee, item_nbr, featured_item_ind, item_desc,
                        upc_nbr, dept_nbr, dept_desc, vendor_nbr, vendor_desc,
                        vendor_billed_nbr, vendor_billed_desc, target_club_cnt,
                        sub_cat_nbr, sub_cat_desc, event_name, country,
                        last_change_user, claim_nbr, fetched_at, store_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event.get('eventId'),
                    event.get('eventType'),
                    event.get('eventDate'),
                    event.get('billType'),
                    event.get('eventStatus'),
                    event.get('lockDate'),
                    event.get('eventFee'),
                    event.get('itemNbr'),
                    event.get('featuredItemInd'),
                    event.get('itemDesc'),
                    event.get('upcNbr'),
                    event.get('deptNbr'),
                    event.get('deptDesc'),
                    event.get('vendorNbr'),
                    event.get('vendorDesc'),
                    event.get('vendorBilledNbr'),
                    event.get('vendorBilledDesc'),
                    event.get('targetClubCnt'),
                    event.get('subCatNbr'),
                    event.get('subCatDesc'),
                    event.get('eventName'),
                    event.get('country'),
                    event.get('lastChangeUser'),
                    claim_nbr_json,
                    fetched_at,
                    store_number
                ))
                stored_count += 1
            except sqlite3.IntegrityError:
                # Duplicate entry, skip
                continue

        # Record cache metadata
        cursor.execute('''
            INSERT INTO cache_metadata (
                fetch_type, start_date, end_date, store_number,
                fetched_at, event_count, success
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('browse_events', start_date, end_date, store_number, fetched_at, stored_count, True))

        self.conn.commit()
        return stored_count

    def get_event_by_id(self, event_id: int, max_age_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all items for a specific event ID from cache.

        Args:
            event_id: The event ID to retrieve
            max_age_hours: Maximum age of cached data in hours (None = no limit)

        Returns:
            List of event item dictionaries (one event can have multiple items)
        """
        cursor = self.conn.cursor()

        query = 'SELECT * FROM events WHERE event_id = ?'
        params = [event_id]

        if max_age_hours is not None:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=max_age_hours)
            query += ' AND fetched_at >= ?'
            params.append(cutoff_time.isoformat())

        query += ' ORDER BY featured_item_ind DESC, item_nbr'

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    def get_events_by_date_range(self, start_date: str, end_date: str,
                                 store_number: Optional[str] = None,
                                 max_age_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get events within a date range from cache.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            store_number: Filter by store number (optional)
            max_age_hours: Maximum age of cached data in hours (None = no limit)

        Returns:
            List of event dictionaries
        """
        cursor = self.conn.cursor()

        query = '''
            SELECT * FROM events
            WHERE event_date BETWEEN ? AND ?
        '''
        params = [start_date, end_date]

        if store_number:
            query += ' AND store_number = ?'
            params.append(store_number)

        if max_age_hours is not None:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=max_age_hours)
            query += ' AND fetched_at >= ?'
            params.append(cutoff_time.isoformat())

        query += ' ORDER BY event_date DESC, event_id, featured_item_ind DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    def get_all_event_ids(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                         max_age_hours: Optional[int] = None) -> List[int]:
        """
        Get list of unique event IDs in cache.

        Args:
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)
            max_age_hours: Maximum age of cached data in hours (None = no limit)

        Returns:
            List of unique event IDs
        """
        cursor = self.conn.cursor()

        query = 'SELECT DISTINCT event_id FROM events WHERE 1=1'
        params = []

        if start_date and end_date:
            query += ' AND event_date BETWEEN ? AND ?'
            params.extend([start_date, end_date])

        if max_age_hours is not None:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=max_age_hours)
            query += ' AND fetched_at >= ?'
            params.append(cutoff_time.isoformat())

        query += ' ORDER BY event_id'

        cursor.execute(query, params)
        return [row[0] for row in cursor.fetchall()]

    def is_cache_fresh(self, store_number: str, start_date: str, end_date: str,
                      max_age_hours: int = 24) -> bool:
        """
        Check if cache data exists and is fresh for given parameters.

        Args:
            store_number: Store number to check
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            max_age_hours: Maximum acceptable age in hours (default: 24)

        Returns:
            True if fresh cache data exists, False otherwise
        """
        cursor = self.conn.cursor()
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=max_age_hours)

        cursor.execute('''
            SELECT COUNT(*) FROM cache_metadata
            WHERE fetch_type = 'browse_events'
            AND store_number = ?
            AND start_date = ?
            AND end_date = ?
            AND fetched_at >= ?
            AND success = 1
        ''', (store_number, start_date, end_date, cutoff_time.isoformat()))

        count = cursor.fetchone()[0]
        return count > 0

    def clear_old_cache(self, max_age_days: int = 30) -> Tuple[int, int]:
        """
        Clear cache data older than specified days.

        Args:
            max_age_days: Maximum age to keep in days (default: 30)

        Returns:
            Tuple of (events_deleted, metadata_records_deleted)
        """
        cursor = self.conn.cursor()
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=max_age_days)

        # Delete old events
        cursor.execute('''
            DELETE FROM events WHERE fetched_at < ?
        ''', (cutoff_time.isoformat(),))
        events_deleted = cursor.rowcount

        # Delete old metadata
        cursor.execute('''
            DELETE FROM cache_metadata WHERE fetched_at < ?
        ''', (cutoff_time.isoformat(),))
        metadata_deleted = cursor.rowcount

        self.conn.commit()
        return (events_deleted, metadata_deleted)

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cached data.

        Returns:
            Dictionary with cache statistics
        """
        cursor = self.conn.cursor()

        # Total events
        cursor.execute('SELECT COUNT(*) FROM events')
        total_events = cursor.fetchone()[0]

        # Unique event IDs
        cursor.execute('SELECT COUNT(DISTINCT event_id) FROM events')
        unique_events = cursor.fetchone()[0]

        # Date range
        cursor.execute('SELECT MIN(event_date), MAX(event_date) FROM events')
        date_range = cursor.fetchone()

        # Last fetch time
        cursor.execute('SELECT MAX(fetched_at) FROM cache_metadata WHERE success = 1')
        last_fetch = cursor.fetchone()[0]

        # Cache age
        cache_age_hours = None
        if last_fetch:
            last_fetch_dt = datetime.datetime.fromisoformat(last_fetch)
            cache_age = datetime.datetime.now() - last_fetch_dt
            cache_age_hours = cache_age.total_seconds() / 3600

        return {
            'total_event_items': total_events,
            'unique_events': unique_events,
            'earliest_event_date': date_range[0],
            'latest_event_date': date_range[1],
            'last_fetch_time': last_fetch,
            'cache_age_hours': cache_age_hours,
            'database_path': self.db_path
        }

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Convert SQLite row to dictionary matching API response format.

        Args:
            row: SQLite row object

        Returns:
            Dictionary in API response format
        """
        # Parse claim_nbr JSON back to list
        claim_nbr = json.loads(row['claim_nbr']) if row['claim_nbr'] else []

        return {
            'eventId': row['event_id'],
            'eventType': row['event_type'],
            'eventDate': row['event_date'],
            'billType': row['bill_type'],
            'eventStatus': row['event_status'],
            'lockDate': row['lock_date'],
            'eventFee': row['event_fee'],
            'itemNbr': row['item_nbr'],
            'featuredItemInd': row['featured_item_ind'],
            'itemDesc': row['item_desc'],
            'upcNbr': row['upc_nbr'],
            'deptNbr': row['dept_nbr'],
            'deptDesc': row['dept_desc'],
            'vendorNbr': row['vendor_nbr'],
            'vendorDesc': row['vendor_desc'],
            'vendorBilledNbr': row['vendor_billed_nbr'],
            'vendorBilledDesc': row['vendor_billed_desc'],
            'targetClubCnt': row['target_club_cnt'],
            'subCatNbr': row['sub_cat_nbr'],
            'subCatDesc': row['sub_cat_desc'],
            'eventName': row['event_name'],
            'country': row['country'],
            'lastChangeUser': row['last_change_user'],
            'claimNbr': claim_nbr,
            '_cached_at': row['fetched_at']  # Add metadata about when it was cached
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Example usage and testing
if __name__ == "__main__":
    # Create database manager
    db = EDRDatabaseManager()

    # Get cache stats
    stats = db.get_cache_stats()
    print("Cache Statistics:")
    print(f"  Total event items: {stats['total_event_items']}")
    print(f"  Unique events: {stats['unique_events']}")
    print(f"  Date range: {stats['earliest_event_date']} to {stats['latest_event_date']}")
    print(f"  Last fetch: {stats['last_fetch_time']}")
    print(f"  Cache age: {stats['cache_age_hours']:.2f} hours" if stats['cache_age_hours'] else "  Cache age: N/A")
    print(f"  Database: {stats['database_path']}")

    db.close()
