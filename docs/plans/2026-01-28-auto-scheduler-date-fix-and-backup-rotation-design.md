# Auto-Scheduler Date Fix and Backup Rotation Design

**Date:** 2026-01-28
**Type:** Enhancement + Bug Fix

## Problem Statement

### Problem 1: Past Date Scheduling Issue
The auto-scheduler attempts to schedule juicer events on their `start_date` even when that date has already passed. This results in failed schedules or attempts to schedule events in the past.

**Current Behavior:**
```python
target_date = event.start_datetime  # Line 1653 in scheduling_engine.py
```
If `start_datetime` is yesterday or earlier, the scheduler still tries to use that past date.

**Expected Behavior:**
- If `start_date` is in the past, use today (or next valid scheduling date) instead
- If `start_date` is past and `due_date` has also passed, fail the event appropriately
- Log when date adjustment occurs for transparency

### Problem 2: No Backup Rotation Configuration
Currently, `RotationAssignment` only supports a primary employee. When the primary is unavailable (time-off, conflicts, max hours), the event fails to schedule. There's no mechanism for automatic fallback to a backup employee.

**Current Limitation:**
- One employee per rotation slot (day + rotation_type)
- No automatic fallback when primary unavailable
- Manual intervention required for every absence

**Desired Behavior:**
- Configure a backup employee for each rotation slot
- Auto-scheduler tries backup when primary unavailable
- Maintain rotation exceptions (one-time overrides)

## Solution Overview

### Fix 1: Date Logic Correction
Modify `_schedule_juicer_event_wave2()` to detect past start dates and use today as the target date instead. Validate that the adjusted date doesn't exceed the due date.

### Fix 2: Backup Rotation System
Add `backup_employee_id` to `RotationAssignment` model. Enhance `RotationManager` to support fetching backup employees. Update scheduling engine to automatically try backup when primary is unavailable.

## Database Schema Changes

### RotationAssignment Model

**New Field:**
```python
backup_employee_id = db.Column(db.String, db.ForeignKey('employees.id'), nullable=True)
```

**Updated Relationships:**
```python
employee = db.relationship('Employee', foreign_keys=[employee_id], backref='rotation_assignments')
backup_employee = db.relationship('Employee', foreign_keys=[backup_employee_id], backref='backup_rotation_assignments')
```

**Migration Required:**
- Add `backup_employee_id` column (nullable)
- Add foreign key constraint to `employees` table
- No data migration needed (nullable allows gradual rollout)

**Design Decisions:**
- Nullable: Existing rotations continue working without backups
- Single backup: Covers most common use case, keeps configuration simple
- Per-day backup: Different days can have different backups

## Service Layer Changes

### RotationManager Enhancements

**Enhanced Method Signature:**
```python
def get_rotation_employee(
    self,
    target_date: datetime,
    rotation_type: str,
    try_backup: bool = False
) -> Optional[object]:
```

**Logic Flow:**
1. Check for `ScheduleException` first (one-time overrides take precedence)
2. If exception exists, return exception employee (ignores backup parameter)
3. Query `RotationAssignment` for day_of_week + rotation_type
4. If `try_backup=True` and `backup_employee_id` exists, return backup
5. Otherwise return primary employee

**New Helper Method:**
```python
def get_rotation_with_backup(
    self,
    target_date: datetime,
    rotation_type: str
) -> Tuple[Optional[object], Optional[object]]:
    """Returns (primary_employee, backup_employee)"""
```

## Scheduling Engine Changes

### Date Fix Implementation

**File:** `app/services/scheduling_engine.py`
**Method:** `_schedule_juicer_event_wave2()`

**New Logic:**
```python
today = datetime.now().date()
event_start_date = event.start_datetime.date()

if event_start_date < today:
    # Start date has passed - use today instead
    target_date = datetime.combine(today, time(0, 0))
    logger.info(f"Event {event.project_ref_num} start date {event_start_date} is in the past. Using today {today}.")
else:
    # Start date is today or future - use it
    target_date = event.start_datetime

# Validate target date doesn't exceed due date
if target_date.date() > event.due_datetime.date():
    self._create_failed_pending_schedule(
        run, event,
        f"Start date {event_start_date} is in past and due date {event.due_datetime.date()} has also passed"
    )
    run.events_failed += 1
    return
```

**Edge Cases Handled:**
- Start date in past, due date in future → Use today
- Start date in past, due date also in past → Fail event
- Start date today → Use today (no change)
- Start date future → Use start date (no change)

### Backup Rotation Logic

**New Helper Method:**
```python
def _try_schedule_with_rotation_and_backup(
    self,
    run: object,
    event: object,
    target_date: datetime,
    schedule_time: time,
    rotation_type: str
) -> bool:
```

**Algorithm:**
1. Get primary rotation employee
2. If primary exists, validate assignment
3. If primary valid, schedule to primary (log "primary")
4. If primary invalid, get backup employee
5. If backup exists and different from primary, validate assignment
6. If backup valid, schedule to backup (log "BACKUP")
7. If both fail, create failed pending schedule with detailed reason

**Logging Strategy:**
- Log when primary is used: `"Scheduled to {name} (primary)"`
- Log when backup is used: `"Scheduled to {name} (BACKUP)"`
- Log when both fail: `"Primary unavailable and Backup also unavailable"`

**Integration Points:**
- Used by `_schedule_juicer_event_wave2()` for Juicer events
- Can be reused for primary lead rotation events
- Works with existing `ConstraintValidator` for availability checks

## API Changes

### Rotation Management Endpoints

**Assumed Existing Endpoints (to be updated):**

**POST /api/rotations**
- Add `backup_employee_id` to request body (optional)
- Validate backup is different from primary
- Return backup employee details in response

**PUT /api/rotations/<id>**
- Support updating `backup_employee_id`
- Allow setting to null (remove backup)

**GET /api/rotations**
- Include `backup_employee_id` in response
- Include backup employee details (name, id)

**Validation Rules:**
1. `backup_employee_id` must reference existing employee
2. `backup_employee_id` must differ from `employee_id`
3. Backup is optional (can be null)
4. Same employee can be backup for multiple rotations

## UI Changes

**Rotation Configuration Page:**
- Add "Backup Employee" dropdown next to primary employee selector
- Show badge/icon when backup is configured
- Allow clearing backup (set to null)
- Display backup name in rotation calendar views

**Auto-Scheduler Results Page:**
- Show "(BACKUP)" badge when backup employee was used
- Include explanation in event details/logs

**Schedule Views:**
- Optionally display backup employee in rotation tooltips/info panels

## Testing Strategy

### Unit Tests

**tests/test_rotation_manager.py:**
- `test_get_rotation_employee_primary()` - Returns primary when try_backup=False
- `test_get_rotation_employee_backup()` - Returns backup when try_backup=True
- `test_get_rotation_employee_no_backup()` - Returns None when backup not configured
- `test_get_rotation_with_backup()` - Returns correct tuple
- `test_schedule_exception_overrides_backup()` - Exception takes precedence

**tests/test_scheduling.py:**
- `test_juicer_past_start_date_uses_today()` - Date adjustment logic
- `test_juicer_past_start_past_due_fails()` - Both dates in past
- `test_juicer_future_start_date_unchanged()` - No adjustment needed
- `test_backup_used_when_primary_unavailable()` - Backup fallback
- `test_primary_preferred_when_both_available()` - Primary priority
- `test_both_unavailable_creates_failed_schedule()` - Failure handling
- `test_no_backup_configured_fails()` - Graceful fallback

**tests/test_migrations.py:**
- `test_migration_adds_backup_column()` - Migration applies
- `test_existing_rotations_unchanged()` - Backwards compatibility
- `test_downgrade_removes_backup_column()` - Rollback works

### Integration Tests

1. Full auto-scheduler run with backups configured
2. Backup receives event when primary has time-off
3. Backup receives event when primary at max hours
4. Logging shows correct "(BACKUP)" indicators
5. Past date juicer events reschedule to today

### Manual Testing Checklist

- [ ] Apply migration to test database
- [ ] Configure backup for Monday Juicer rotation
- [ ] Create Juicer event with past start date
- [ ] Mark primary Juicer unavailable (add time-off)
- [ ] Run auto-scheduler
- [ ] Verify event scheduled to backup with today's date
- [ ] Check logs show date adjustment and backup usage
- [ ] Test UI shows backup configuration correctly
- [ ] Test API CRUD operations with backup field

## Implementation Order

### Phase 1: Database Migration (Low Risk)
1. Create migration file with `backup_employee_id` column
2. Test migration on test instance (`./start_test_instance.sh`)
3. Verify migration up and down work correctly
4. Apply to development database

### Phase 2: RotationManager Updates (Low Risk)
1. Update `get_rotation_employee()` method signature
2. Add `try_backup` parameter logic
3. Add `get_rotation_with_backup()` helper
4. Write and run unit tests

### Phase 3: Scheduling Engine - Date Fix (Medium Risk)
1. Modify `_schedule_juicer_event_wave2()` date logic
2. Add date comparison and adjustment
3. Add logging for date adjustments
4. Test with various date scenarios
5. Verify no regression in normal date cases

### Phase 4: Scheduling Engine - Backup Logic (Medium Risk)
1. Create `_try_schedule_with_rotation_and_backup()` method
2. Integrate with `_schedule_juicer_event_wave2()`
3. Add comprehensive logging
4. Run unit and integration tests
5. Verify existing schedules unaffected

### Phase 5: API & UI Updates (Low Risk)
1. Update rotation CRUD endpoints
2. Add backup field to API request/response schemas
3. Update UI forms and displays
4. Test end-to-end workflow
5. Document API changes

### Phase 6: Integration Testing (Critical)
1. Full auto-scheduler run with mixed scenarios
2. Verify all logging output
3. Test edge cases and failure modes
4. Performance testing (backup lookup overhead)

## Risk Assessment

### Low Risk Changes
- Database migration (reversible, nullable column)
- RotationManager updates (backwards compatible)
- API changes (additive, optional field)

### Medium Risk Changes
- Date fix logic (affects core scheduling behavior)
- Backup rotation logic (changes scheduling flow)

### Mitigation Strategies
- **Comprehensive testing** at each phase
- **Rollback plan** documented for migration
- **Backwards compatibility** maintained (backup is optional)
- **Extensive logging** for troubleshooting
- **Test instance validation** before production

### Rollback Plan
1. Database migration is reversible (`flask db downgrade`)
2. Code changes can be reverted via git
3. Backup column nullable ensures existing rotations work
4. No breaking changes to existing API contracts

## Pre-Production Checklist

- [ ] Backup production database (`./backup_now.sh`)
- [ ] Test migration on staging/test instance
- [ ] Verify all unit tests pass
- [ ] Run full integration test suite
- [ ] Review and approve changelog
- [ ] Document new backup configuration in user guide
- [ ] Plan rollout communication to users

## Success Metrics

**Date Fix:**
- Zero events scheduled to past dates
- Appropriate failure messages when due date passed
- Clear logging of date adjustments

**Backup Rotation:**
- Reduced failed schedules when primary unavailable
- Successful automatic fallback to backup
- Clear indication of backup usage in logs and UI
- No performance degradation

## Future Enhancements (Out of Scope)

- Multiple backups with priority ordering
- Auto-suggest backups based on availability patterns
- Rotation swap requests (employee-initiated)
- Backup notification system (alert backup when they'll be needed)
