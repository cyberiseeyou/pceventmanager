# Spec 4: Attendance Audit Trail + Locking

## Overview

Add modification tracking to attendance records and enforce locking rules: once any user submits an attendance record for an employee+date, only the club supervisor can modify or delete that record. This is a data model + API change — no new UI pages (the lead attendance UI is Spec 5).

## Roles Affected

- **Supervisor** — can still create, edit, and delete any attendance record (no change to their experience)
- **Lead** — can create new records, cannot edit/delete existing records
- **Specialist** — no attendance access

## Requirements

### 1. Schema Changes

Add these columns to `EmployeeAttendance`:

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `modified_by` | String(100) | Yes | None | Username of last person who edited the record |
| `modified_at` | DateTime | Yes | None | Timestamp of last modification |

**Existing columns retained as-is:**
- `recorded_by` (String(100)) — who first created the record (already exists)
- `recorded_at` (DateTime) — when first created (already exists)
- `updated_at` (DateTime) — auto-updated on any change (already exists)

**Unique constraint** already exists: `(employee_id, attendance_date)` — one record per employee per day. This naturally enforces "first submitter wins."

### 2. Migration

- Create Alembic migration adding `modified_by` and `modified_at` columns
- Both nullable, no backfill needed
- Existing records will have `modified_by=NULL` and `modified_at=NULL` (never modified)

### 3. Locking Rules (API Enforcement)

#### POST `/api/attendance` (Create/Upsert)

Current behavior: upserts — creates if new, updates if exists.

**New behavior:**
- If no existing record for that `(employee_id, attendance_date)`: create normally, set `recorded_by` from session
- If existing record AND requester is **supervisor**: update allowed, set `modified_by` and `modified_at`
- If existing record AND requester is **NOT supervisor**: return `403 Forbidden` with message: `"This attendance record was already submitted by {recorded_by}. Only the club supervisor can modify it."`

#### PUT `/api/attendance/<id>` (Update)

**New behavior:**
- If requester is **supervisor**: update allowed, set `modified_by` and `modified_at`
- If requester is **NOT supervisor**: return `403 Forbidden` with same message

#### DELETE `/api/attendance/<id>` (Delete)

**New behavior:**
- If requester is **supervisor**: delete allowed
- If requester is **NOT supervisor**: return `403 Forbidden` with message: `"Only the club supervisor can delete attendance records."`

### 4. Modification Tracking

When a supervisor modifies an existing record:
- Set `modified_by = session.get('username', 'Unknown')`
- Set `modified_at = datetime.utcnow()`
- Do NOT overwrite `recorded_by` or `recorded_at` (preserve original submitter)

### 5. API Response Enhancement

All attendance endpoints that return record data should include:

```json
{
  "id": 1,
  "employee_id": "EMP001",
  "attendance_date": "2026-03-17",
  "status": "on_time",
  "notes": "...",
  "recorded_by": "robi",
  "recorded_at": "2026-03-17T08:00:00",
  "modified_by": "diane",
  "modified_at": "2026-03-17T10:30:00",
  "is_modified": true
}
```

`is_modified` is a computed field: `true` if `modified_by` is not null.

### 6. Role Detection

Use `get_current_user()` to determine role. The session stores `user_info.role` which is `'supervisor'`, `'lead'`, or `'specialist'`.

```python
user = get_current_user()
is_supervisor = user and user.get('role') == 'supervisor'
```

## Files Modified

| File | Change |
|------|--------|
| `app/models/employee_attendance.py` | Add `modified_by`, `modified_at` columns |
| `app/routes/api_attendance.py` | Add locking checks to POST/PUT/DELETE, set `modified_by`/`modified_at` on updates, add `is_modified` to responses |
| `migrations/versions/xxx_add_attendance_audit_fields.py` | New migration |

### 7. Update `to_dict()` Method

The `EmployeeAttendance.to_dict()` method must include the new fields:

```python
def to_dict(self):
    return {
        ...existing fields...,
        'modified_by': self.modified_by,
        'modified_at': self.modified_at.isoformat() if self.modified_at else None,
        'is_modified': self.modified_by is not None,
    }
```

This is required for Spec 5's lead attendance UI to display audit information.

## Files NOT Modified

- Supervisor attendance templates/JS — existing UI continues to work, just now shows `modified_by` info
- The supervisor's edit modal already calls PUT, which will now set `modified_by`

## Acceptance Criteria

- [ ] Migration adds `modified_by` and `modified_at` columns
- [ ] Creating a new attendance record sets `recorded_by` from session
- [ ] Supervisor can edit any record — `modified_by` and `modified_at` are set
- [ ] Non-supervisor cannot edit existing records — gets 403
- [ ] Non-supervisor cannot delete records — gets 403
- [ ] Non-supervisor CAN create new records (no existing record for that employee+date)
- [ ] `recorded_by` is never overwritten on edit
- [ ] API responses include `modified_by`, `modified_at`, `is_modified`
- [ ] All existing attendance tests pass
- [ ] If Robi submits for Lanie on 3/17, Diane gets 403 trying to submit for Lanie on 3/17
