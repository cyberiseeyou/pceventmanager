# EDR Bulk Data Caching System

## Overview

This caching system dramatically reduces the need for repeated MFA authentication by storing event data from bulk API calls in a local SQLite database. Instead of making individual API calls for each event report, the system:

1. **Fetches all events in one API call** using `browse_events()`
2. **Stores 100+ events** in local database automatically
3. **Generates reports from cache** without re-authenticating
4. **Manages cache freshness** with configurable expiry

## Key Benefits

- **Single MFA Authentication**: Authenticate once, generate multiple reports
- **Massive Efficiency**: 115 events fetched in 1 API call vs 115 individual calls
- **Offline Capable**: Generate reports from cache without network access
- **Auto-Expiry**: Configurable cache age management (default: 24 hours)

## Architecture

### Components

1. **db_manager.py**: Database operations and cache management
2. **report_generator.py**: Enhanced with caching methods
3. **SQLite Database**: Stores event data with metadata and timestamps

### Database Schema

```sql
events (
    event_id, event_type, event_date, bill_type, event_status,
    item_nbr, item_desc, upc_nbr, featured_item_ind,
    vendor_nbr, vendor_desc, dept_nbr, dept_desc,
    event_name, claim_nbr, fetched_at, store_number
)

cache_metadata (
    fetch_type, start_date, end_date, store_number,
    fetched_at, event_count, success
)
```

## Usage Guide

### Basic Usage - With Caching (Recommended)

```python
from edr.report_generator import EDRReportGenerator

# Initialize with caching enabled (default)
generator = EDRReportGenerator(
    enable_caching=True,          # Enable caching (default: True)
    cache_max_age_hours=24,       # Cache expires after 24 hours (default)
    db_path="edr_cache.db"        # Custom DB path (optional)
)

# Set credentials
generator.username = "your_username"
generator.password = "your_password"
generator.mfa_credential_id = "your_mfa_id"

# Authenticate ONCE (required for initial data fetch)
generator.authenticate()

# Fetch and cache all events for the month
events = generator.browse_events_with_cache()
# Result: Fetches from API and stores in cache

# Later: Generate reports without re-authenticating
html_report = generator.generate_html_report_from_cache(612730)

# Save or print the report
with open('report_612730.html', 'w') as f:
    f.write(html_report)
```

### Advanced Usage

#### Check Cache Status

```python
# Get cache statistics
stats = generator.get_cache_stats()
print(f"Total events cached: {stats['unique_events']}")
print(f"Cache age: {stats['cache_age_hours']:.2f} hours")
print(f"Date range: {stats['earliest_event_date']} to {stats['latest_event_date']}")
```

#### Force Refresh Cache

```python
# Force refresh even if cache is fresh
events = generator.browse_events_with_cache(force_refresh=True)
```

#### Get Specific Event from Cache

```python
# Retrieve event items without API call
event_items = generator.get_event_from_cache(612730)
# Returns list of all items for this event
```

#### Bulk Report Generation

```python
# Generate reports for all cached events
event_ids = generator.db.get_all_event_ids()

for event_id in event_ids:
    html = generator.generate_html_report_from_cache(event_id)
    if html:
        filename = f"report_{event_id}.html"
        with open(filename, 'w') as f:
            f.write(html)
        print(f"Generated: {filename}")
```

#### Cache Maintenance

```python
# Clear old cache data (30 days old)
events_deleted, metadata_deleted = generator.clear_old_cache(max_age_days=30)
print(f"Cleaned up {events_deleted} old records")
```

### Working Without Authentication

Once cache is populated, you can generate reports without authenticating:

```python
# Initialize generator (no authentication needed)
generator = EDRReportGenerator(enable_caching=True)

# Generate report from cache only
html_report = generator.generate_html_report_from_cache(612730)
```

## Workflow Examples

### Daily Morning Workflow

```python
# 1. Authenticate once in the morning
generator = EDRReportGenerator()
generator.username = "..."
generator.password = "..."
generator.mfa_credential_id = "..."
generator.authenticate()

# 2. Fetch and cache all month's events (one MFA required)
events = generator.browse_events_with_cache()
print(f"Cached {len(events)} events")

# 3. Generate multiple reports throughout the day (no MFA)
for event_id in [612730, 595831, 600036]:
    html = generator.generate_html_report_from_cache(event_id)
    with open(f'daily_report_{event_id}.html', 'w') as f:
        f.write(html)
```

### Scheduled Cache Refresh

```python
import schedule
import time

def refresh_cache():
    generator = EDRReportGenerator()
    generator.username = os.getenv('USERNAME')
    generator.password = os.getenv('PASSWORD')
    generator.mfa_credential_id = os.getenv('MFA_ID')

    if generator.authenticate():
        generator.refresh_cache()
        print("✅ Cache refreshed successfully")

# Refresh cache every 12 hours
schedule.every(12).hours.do(refresh_cache)

while True:
    schedule.run_pending()
    time.sleep(1)
```

## API Reference

### EDRReportGenerator Methods

#### Caching Methods

- `browse_events_with_cache()` - Fetch events with cache-first strategy
- `get_event_from_cache(event_id)` - Get event data from cache
- `refresh_cache()` - Force refresh cache from API
- `get_cache_stats()` - Get cache statistics
- `clear_old_cache(max_age_days)` - Clean up old cache data
- `generate_html_report_from_cache(event_id)` - Generate report from cached data

### EDRDatabaseManager Methods

#### Database Operations

- `store_events(events_data, store_number, start_date, end_date)` - Store bulk events
- `get_event_by_id(event_id, max_age_hours)` - Get event items by ID
- `get_events_by_date_range(start_date, end_date, store_number, max_age_hours)` - Query by date
- `get_all_event_ids(start_date, end_date, max_age_hours)` - Get unique event IDs
- `is_cache_fresh(store_number, start_date, end_date, max_age_hours)` - Check cache freshness
- `get_cache_stats()` - Get database statistics
- `clear_old_cache(max_age_days)` - Remove old records

## Testing

Run the test suite to verify caching functionality:

```bash
python test_caching.py
```

Tests include:
1. Database operations (store, retrieve, query)
2. Cache integration with EDRReportGenerator
3. Report generation from cached data
4. Complete workflow simulation

## Cache Data Structure

Cached events include all fields from the `browse_events` API:

```python
{
    'eventId': 612730,
    'eventType': 'Club Choice Company',
    'eventDate': '2025-10-01',
    'billType': '6 Hour',
    'eventStatus': 'APPROVED',
    'lockDate': 'true',
    'eventFee': '0.00',
    'itemNbr': 980055288,
    'featuredItemInd': 'Y',
    'itemDesc': 'ORANGE JUICE',
    'upcNbr': 25540600000,
    'deptNbr': 56,
    'deptDesc': 'Produce and Floral',
    'vendorNbr': 456104,
    'vendorBilledNbr': 456104,
    'vendorBilledDesc': 'SAMS PRODUCE DCS',
    'eventName': '10.01-LKD-CF-Orange/Lemonade/Limeade',
    'claimNbr': ['000015000234189'],
    '_cached_at': '2025-10-09T07:26:56.719367'  # Metadata
}
```

## Configuration

### Cache Expiry

Control cache freshness:

```python
# Cache expires after 6 hours
generator = EDRReportGenerator(cache_max_age_hours=6)

# Cache never expires (use with caution)
generator = EDRReportGenerator(cache_max_age_hours=999999)
```

### Database Location

```python
# Default: edr/edr_cache.db
generator = EDRReportGenerator()

# Custom location
generator = EDRReportGenerator(db_path="/path/to/custom_cache.db")

# In-memory database (for testing)
generator = EDRReportGenerator(db_path=":memory:")
```

### Disable Caching

```python
# Use traditional API-only mode
generator = EDRReportGenerator(enable_caching=False)
```

## Performance Comparison

### Without Caching (Old Method)
- 1 authentication session per day
- 1 API call per report
- 50 reports = 50 API calls + potential rate limiting

### With Caching (New Method)
- 1 authentication session per day
- 1 bulk API call (fetches 100+ events)
- 50 reports = 0 additional API calls
- No rate limiting concerns

## Limitations

1. **Cached Data Doesn't Include Instructions**: The bulk API doesn't return event preparation/portion instructions. Reports generated from cache show "N/A" for these fields.

2. **Cache Staleness**: Cached data may be outdated. The system uses timestamps and max_age_hours to manage this.

3. **Single Store Focus**: Currently optimized for single store (8135). Multi-store requires separate caching.

## Troubleshooting

### Cache Not Working

```python
# Check if caching is enabled
if generator.enable_caching:
    print("✅ Caching enabled")
else:
    print("❌ Caching disabled")

# Check database connection
if generator.db:
    print("✅ Database connected")
    print(generator.get_cache_stats())
```

### Stale Cache

```python
# Force refresh
events = generator.browse_events_with_cache(force_refresh=True)

# Or clear and rebuild
generator.clear_old_cache(max_age_days=0)  # Clear all
generator.refresh_cache()  # Rebuild
```

### Database Errors

```python
# Reset database
import os
if os.path.exists('edr_cache.db'):
    os.remove('edr_cache.db')

# Reinitialize
generator = EDRReportGenerator()
```

## Future Enhancements

- [ ] Multi-store support
- [ ] Background cache refresh scheduling
- [ ] Cache statistics dashboard
- [ ] Export cache to JSON/CSV
- [ ] Compressed database storage
- [ ] Event change detection and notifications

## Contributing

When adding new features:
1. Update database schema in `db_manager.py`
2. Add corresponding methods to `EDRReportGenerator`
3. Update tests in `test_caching.py`
4. Document changes in this README

## License

Part of the Scheduler App project.
