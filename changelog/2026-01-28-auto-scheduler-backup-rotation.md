# Auto-Scheduler: Date Fix and Backup Rotation

**Date:** 2026-01-28
**Type:** Enhancement + Bug Fix

## Summary
Fixed auto-scheduler attempting to schedule juicer events on past dates, and added backup rotation configuration for automatic failover when primary employees are unavailable.

## Changes Made

### Files Modified
- `app/models/auto_scheduler.py` (lines 58-87)
  - Added `backup_employee_id` field to RotationAssignment model
  - Added `backup_employee` relationship
  - Updated `__repr__` to show backup info

- `app/services/rotation_manager.py` (lines 32-180)
  - Added `try_backup` parameter to `get_rotation_employee()`
  - Added `get_rotation_with_backup()` helper method
  - Returns backup employee when requested
  - Updated `get_all_rotations()` to return both primary and backup
  - Updated `set_all_rotations()` to accept backup employees

- `app/services/scheduling_engine.py` (lines 1617-1760)
  - Fixed past date logic in `_schedule_juicer_event_wave2()`
  - Added `_try_schedule_with_rotation_and_backup()` helper
  - Automatic failover to backup when primary unavailable
  - Enhanced logging for date adjustments and backup usage

- `app/routes/rotations.py` (lines 42-95)
  - Updated GET endpoint to include backup employee details
  - Updated POST endpoint to accept backup_employee_id
  - Validation to ensure backup differs from primary
  - Backward compatible with old API format

### Database Changes
- Migration: Add `backup_employee_id` column to `rotation_assignments` table
- Foreign key constraint to `employees` table
- Nullable column (backward compatible)

### Business Logic Changes

**Past Date Handling:**
- If event `start_date` is in the past, use today as target date
- Fail only if both `start_date` and `due_date` are in the past
- Log when date adjustment occurs

**Backup Rotation:**
- Try primary rotation employee first
- Automatically fall back to backup if primary unavailable
- Fail only if both primary and backup unavailable
- Clear logging shows whether primary or backup was used

## Bug Fixes
- **Issue:** Auto-scheduler attempted to schedule events on past dates
- **Root Cause:** `_schedule_juicer_event_wave2` used `event.start_datetime` directly without checking if it was in the past
- **Resolution:** Added date comparison logic to use today if start date has passed

## Testing
- Added `tests/test_rotation_manager_backup.py` - Backup employee lookup tests (3 tests)
- Added `tests/test_scheduling_past_dates.py` - Past date handling tests (3 tests)
- Added `tests/test_scheduling_backup_rotation.py` - Backup failover tests (3 tests)
- All existing tests continue to pass

## API Changes

**GET /rotations/api/rotations:**
Response now includes backup employee information:
```json
{
  "juicer": {
    "0": {
      "primary": "emp1",
      "primary_name": "John Doe",
      "backup": "emp2",
      "backup_name": "Jane Smith"
    }
  }
}
```

**POST /rotations/api/rotations:**
Now accepts backup employee in request:
```json
{
  "juicer": {
    "0": {
      "primary": "emp1",
      "backup": "emp2"
    }
  }
}
```

Old format (string employee_id) still supported for backward compatibility.

## Related Files
- Design document: `docs/plans/2026-01-28-auto-scheduler-date-fix-and-backup-rotation-design.md`
- Implementation plan: `docs/plans/2026-01-28-auto-scheduler-backup-rotation-implementation.md`
