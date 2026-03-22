# Attendance Audit Trail Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add modification tracking (`modified_by`, `modified_at`) to attendance records and enforce locking rules so that once any user submits an attendance record, only the club supervisor can modify or delete it.

**Architecture:** Two columns added to `EmployeeAttendance`, role-based guards added to the three write endpoints (POST/PUT/DELETE) in `api_attendance.py`, and `to_dict()` updated with computed `is_modified` field. No new UI pages — existing supervisor attendance UI continues to work unchanged.

**Tech Stack:** Flask/SQLAlchemy, Alembic migration, existing Redis-based auth (`get_current_user()`)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/models/employee_attendance.py` | Modify | Add `modified_by`, `modified_at` columns; update `to_dict()` |
| `app/routes/api_attendance.py` | Modify | Add role-based locking to POST/PUT/DELETE; set audit fields on update |
| `migrations/versions/xxxx_add_attendance_audit_fields.py` | Create | Alembic migration for new columns |

---

### Task 1: Add schema columns + migration

**Files:**
- Modify: `app/models/employee_attendance.py:60-63`
- Create: `migrations/versions/xxxx_add_attendance_audit_fields.py`

- [ ] **Step 1: Add `modified_by` and `modified_at` columns to model**

In `app/models/employee_attendance.py`, after the existing audit fields (lines 60-63), add the two new columns:

```python
# Before (lines 60-63):
        # Audit fields
        recorded_by = db.Column(db.String(100), nullable=True)
        recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

# After:
        # Audit fields
        recorded_by = db.Column(db.String(100), nullable=True)
        recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)
        modified_by = db.Column(db.String(100), nullable=True)
        modified_at = db.Column(db.DateTime, nullable=True)
```

- [ ] **Step 2: Create Alembic migration**

Run:
```bash
flask db migrate -m "add attendance audit fields modified_by and modified_at"
```

Verify the generated migration file looks like this (adjust revision IDs to match):

```python
"""add attendance audit fields modified_by and modified_at

Revision ID: <generated>
Revises: d83af02d5196
Create Date: <generated>

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '<generated>'
down_revision = 'd83af02d5196'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('employee_attendance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modified_by', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('modified_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('employee_attendance', schema=None) as batch_op:
        batch_op.drop_column('modified_at')
        batch_op.drop_column('modified_by')
```

Both columns are nullable with no default — existing records will have `NULL` (never modified).

- [ ] **Step 3: Test migration on test database**

```bash
DATABASE_URL=sqlite:///instance/scheduler_test.db flask db upgrade
```

- [ ] **Step 4: Commit**

```bash
git add app/models/employee_attendance.py migrations/versions/*attendance_audit*
git commit -m "schema: add modified_by and modified_at columns to employee_attendance"
```

---

### Task 2: Update `to_dict()` method to include new fields

**Files:**
- Modify: `app/models/employee_attendance.py:90-108`

- [ ] **Step 1: Add `modified_by`, `modified_at`, and `is_modified` to `to_dict()`**

In `app/models/employee_attendance.py`, replace the `to_dict()` method (lines 90-108):

```python
# Before (lines 90-108):
        def to_dict(self):
            """
            Convert attendance record to dictionary for JSON serialization

            Returns:
                dict: Attendance record as dictionary
            """
            return {
                'id': self.id,
                'employee_id': self.employee_id,
                'employee_name': self.employee.name if self.employee else None,
                'attendance_date': self.attendance_date.isoformat() if self.attendance_date else None,
                'status': self.status,
                'status_label': self.STATUS_LABELS.get(self.status, self.status),
                'notes': self.notes,
                'recorded_by': self.recorded_by,
                'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }

# After:
        def to_dict(self):
            """
            Convert attendance record to dictionary for JSON serialization

            Returns:
                dict: Attendance record as dictionary
            """
            return {
                'id': self.id,
                'employee_id': self.employee_id,
                'employee_name': self.employee.name if self.employee else None,
                'attendance_date': self.attendance_date.isoformat() if self.attendance_date else None,
                'status': self.status,
                'status_label': self.STATUS_LABELS.get(self.status, self.status),
                'notes': self.notes,
                'recorded_by': self.recorded_by,
                'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'modified_by': self.modified_by,
                'modified_at': self.modified_at.isoformat() if self.modified_at else None,
                'is_modified': self.modified_by is not None,
            }
```

`is_modified` is a computed field: `true` when `modified_by` is not null. This is used by Spec 5's lead attendance UI to display audit information.

- [ ] **Step 2: Commit**

```bash
git add app/models/employee_attendance.py
git commit -m "feat: include modified_by, modified_at, is_modified in attendance to_dict()"
```

---

### Task 3: Add locking enforcement to POST endpoint (create vs upsert logic)

**Files:**
- Modify: `app/routes/api_attendance.py:1-5,29-113`

- [ ] **Step 1: Add `get_current_user` import**

In `app/routes/api_attendance.py`, add the import at the top of the file. Replace lines 1-5:

```python
# Before (lines 1-5):
"""
Attendance API Blueprint
Handles all attendance-related API endpoints for tracking employee attendance
"""
from flask import Blueprint, request, jsonify, session

# After:
"""
Attendance API Blueprint
Handles all attendance-related API endpoints for tracking employee attendance
"""
from flask import Blueprint, request, jsonify, session
from app.routes.auth import get_current_user
```

- [ ] **Step 2: Add locking logic to `create_or_update_attendance` (POST endpoint)**

In `app/routes/api_attendance.py`, replace the upsert block (lines 74-98) inside `create_or_update_attendance()`:

```python
# Before (lines 74-98):
            # Check if attendance record already exists (UPSERT behavior)
            attendance = EmployeeAttendance.query.filter_by(
                employee_id=employee_id,
                attendance_date=attendance_date
            ).first()

            if attendance:
                # Update existing record
                attendance.status = status
                attendance.notes = notes
                attendance.updated_at = datetime.utcnow()
                action = 'updated'
                status_code = 200
            else:
                # Create new record
                attendance = EmployeeAttendance(
                    employee_id=employee_id,
                    attendance_date=attendance_date,
                    status=status,
                    notes=notes,
                    recorded_by=session.get('username', 'Unknown')
                )
                db.session.add(attendance)
                action = 'created'
                status_code = 201

# After:
            # Check if attendance record already exists (UPSERT behavior)
            attendance = EmployeeAttendance.query.filter_by(
                employee_id=employee_id,
                attendance_date=attendance_date
            ).first()

            if attendance:
                # Existing record — only supervisor can modify
                user = get_current_user()
                is_supervisor = user and user.get('role') == 'supervisor'

                if not is_supervisor:
                    return jsonify({
                        'error': f'This attendance record was already submitted by {attendance.recorded_by}. Only the club supervisor can modify it.'
                    }), 403

                # Supervisor update: set audit trail fields
                attendance.status = status
                attendance.notes = notes
                attendance.modified_by = session.get('username', 'Unknown')
                attendance.modified_at = datetime.utcnow()
                action = 'updated'
                status_code = 200
            else:
                # Create new record — any authenticated user can create
                attendance = EmployeeAttendance(
                    employee_id=employee_id,
                    attendance_date=attendance_date,
                    status=status,
                    notes=notes,
                    recorded_by=session.get('username', 'Unknown')
                )
                db.session.add(attendance)
                action = 'created'
                status_code = 201
```

Key changes:
- When an existing record is found, check `get_current_user()` for supervisor role
- Non-supervisors get `403` with a message naming the original submitter
- Supervisor updates set `modified_by` and `modified_at` (NOT overwriting `recorded_by`)
- The explicit `attendance.updated_at = datetime.utcnow()` line is removed because the column has `onupdate=datetime.utcnow` which handles this automatically on commit

- [ ] **Step 3: Commit**

```bash
git add app/routes/api_attendance.py
git commit -m "feat: enforce attendance locking on POST — only supervisor can modify existing records"
```

---

### Task 4: Add locking enforcement to PUT endpoint

**Files:**
- Modify: `app/routes/api_attendance.py:195-241`

- [ ] **Step 1: Add supervisor-only guard and audit trail to `update_attendance` (PUT endpoint)**

In `app/routes/api_attendance.py`, replace the `update_attendance` function (lines 195-241):

```python
# Before (lines 195-241):
    @attendance_api_bp.route('/<int:record_id>', methods=['PUT'])
    def update_attendance(record_id):
        """
        Update existing attendance record

        Request JSON:
        {
            "status": "late",
            "notes": "Updated notes"
        }

        Returns:
            JSON with updated attendance record
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)

            data = request.get_json()
            status = data.get('status')
            notes = data.get('notes')

            # Update status if provided
            if status:
                if status not in EmployeeAttendance.VALID_STATUSES:
                    return jsonify({
                        'error': f'Invalid status. Must be one of: {", ".join(EmployeeAttendance.VALID_STATUSES)}'
                    }), 400
                attendance.status = status

            # Update notes if provided (allow empty string to clear notes)
            if notes is not None:
                attendance.notes = notes

            attendance.updated_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Updated attendance record {record_id}")

            return jsonify({
                'success': True,
                'attendance': attendance.to_dict()
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating attendance {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500

# After:
    @attendance_api_bp.route('/<int:record_id>', methods=['PUT'])
    def update_attendance(record_id):
        """
        Update existing attendance record

        Only the club supervisor can update existing records.

        Request JSON:
        {
            "status": "late",
            "notes": "Updated notes"
        }

        Returns:
            JSON with updated attendance record
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)

            # Only supervisor can modify existing records
            user = get_current_user()
            is_supervisor = user and user.get('role') == 'supervisor'

            if not is_supervisor:
                return jsonify({
                    'error': f'This attendance record was already submitted by {attendance.recorded_by}. Only the club supervisor can modify it.'
                }), 403

            data = request.get_json()
            status = data.get('status')
            notes = data.get('notes')

            # Update status if provided
            if status:
                if status not in EmployeeAttendance.VALID_STATUSES:
                    return jsonify({
                        'error': f'Invalid status. Must be one of: {", ".join(EmployeeAttendance.VALID_STATUSES)}'
                    }), 400
                attendance.status = status

            # Update notes if provided (allow empty string to clear notes)
            if notes is not None:
                attendance.notes = notes

            # Set audit trail fields
            attendance.modified_by = session.get('username', 'Unknown')
            attendance.modified_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Updated attendance record {record_id} by {attendance.modified_by}")

            return jsonify({
                'success': True,
                'attendance': attendance.to_dict()
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating attendance {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500
```

Key changes:
- Added `get_current_user()` role check at the top of the function
- Non-supervisors get `403` with a message naming the original submitter
- Supervisor updates set `modified_by` and `modified_at`
- Removed explicit `attendance.updated_at = datetime.utcnow()` (handled by column `onupdate`)

- [ ] **Step 2: Commit**

```bash
git add app/routes/api_attendance.py
git commit -m "feat: enforce attendance locking on PUT — only supervisor can update records"
```

---

### Task 5: Add locking enforcement to DELETE endpoint

**Files:**
- Modify: `app/routes/api_attendance.py:243-267`

- [ ] **Step 1: Add supervisor-only guard to `delete_attendance` (DELETE endpoint)**

In `app/routes/api_attendance.py`, replace the `delete_attendance` function (lines 243-267):

```python
# Before (lines 243-267):
    @attendance_api_bp.route('/<int:record_id>', methods=['DELETE'])
    def delete_attendance(record_id):
        """
        Delete attendance record

        Returns:
            JSON with success message
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)

            db.session.delete(attendance)
            db.session.commit()

            logger.info(f"Deleted attendance record {record_id}")

            return jsonify({
                'success': True,
                'message': 'Attendance record deleted successfully'
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting attendance {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500

# After:
    @attendance_api_bp.route('/<int:record_id>', methods=['DELETE'])
    def delete_attendance(record_id):
        """
        Delete attendance record

        Only the club supervisor can delete attendance records.

        Returns:
            JSON with success message
        """
        try:
            attendance = EmployeeAttendance.query.get_or_404(record_id)

            # Only supervisor can delete records
            user = get_current_user()
            is_supervisor = user and user.get('role') == 'supervisor'

            if not is_supervisor:
                return jsonify({
                    'error': 'Only the club supervisor can delete attendance records.'
                }), 403

            db.session.delete(attendance)
            db.session.commit()

            logger.info(f"Deleted attendance record {record_id}")

            return jsonify({
                'success': True,
                'message': 'Attendance record deleted successfully'
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting attendance {record_id}: {str(e)}")
            return jsonify({'error': str(e)}), 500
```

Key change: Added `get_current_user()` role check — non-supervisors get `403` with a distinct message (no `recorded_by` reference since the action is deletion, not modification).

- [ ] **Step 2: Commit**

```bash
git add app/routes/api_attendance.py
git commit -m "feat: enforce attendance locking on DELETE — only supervisor can delete records"
```

---

### Task 6: Verification (tests + manual)

**Files:**
- No files modified — verification only

- [ ] **Step 1: Run existing test suite**

Run: `pytest -v --timeout=120`

Expected: All existing tests pass (308+). The existing attendance tests in `tests/test_reports.py` should still pass since those are GET requests (report pages) which are unaffected by the locking changes.

- [ ] **Step 2: Manual smoke test checklist**

1. Start dev server: `python wsgi.py`
2. **Supervisor creates record**: Log in as supervisor. Go to attendance page. Create a new attendance record for an employee. Verify `recorded_by` is set, `modified_by` is null, `is_modified` is `false` in the JSON response.
3. **Supervisor updates record**: Edit the same record (change status or notes). Verify `recorded_by` is preserved (original submitter), `modified_by` is set to current supervisor username, `modified_at` is set, `is_modified` is `true`.
4. **Lead creates new record**: Log in as lead. Create a new attendance record for a different employee+date combination. Verify it succeeds (201).
5. **Lead tries to update existing record (POST upsert)**: As lead, POST for the same employee+date that already has a record. Verify 403 response with message: `"This attendance record was already submitted by {recorded_by}. Only the club supervisor can modify it."`
6. **Lead tries to PUT existing record**: As lead, PUT to `/api/attendance/<id>`. Verify 403 response.
7. **Lead tries to DELETE existing record**: As lead, DELETE to `/api/attendance/<id>`. Verify 403 response with message: `"Only the club supervisor can delete attendance records."`
8. **Supervisor can still delete**: As supervisor, DELETE to `/api/attendance/<id>`. Verify success.
9. **API response shape**: Verify all attendance API responses include `modified_by`, `modified_at`, and `is_modified` fields.

- [ ] **Step 3: Verify migration is clean**

```bash
flask db check
```

Expected: No migration drift detected.

- [ ] **Step 4: Verify the "first submitter wins" scenario from spec**

> If Robi submits for Lanie on 3/17, Diane gets 403 trying to submit for Lanie on 3/17

1. Log in as Robi (lead). POST attendance for Lanie on 2026-03-17. Verify 201.
2. Log in as Diane (lead). POST attendance for Lanie on 2026-03-17. Verify 403 with message mentioning Robi.
3. Log in as supervisor. POST attendance for Lanie on 2026-03-17. Verify 200 (update allowed), `modified_by` set to supervisor username, `recorded_by` still says Robi.
