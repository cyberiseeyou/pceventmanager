# Database Schema Discovery

**Date**: 2026-01-16
**Purpose**: Document actual database schema to fix ML feature extraction

## Summary of Findings

### Key Schema Differences

| Expected | Actual | Fix Required |
|----------|--------|--------------|
| Employee.role | Employee.job_title | Use job_title or derive from is_supervisor |
| Employee.years_experience | ❌ Not present | Use default or calculate from created_at |
| Schedule.event_type | ✅ Via relationship | Access via Schedule.event.event_type |
| EmployeeAttendance.schedule_datetime | attendance_date | Fixed - use attendance_date |
| Status: 'failed' | 'api_failed' | Fixed - use api_submitted, proposed, api_failed |

---

## Employee Model

**Table**: `employees`

### Columns
```
id                           VARCHAR(50)      PRIMARY KEY
name                         VARCHAR(100)     NOT NULL
email                        VARCHAR(120)     NULL
phone                        VARCHAR(20)      NULL
is_active                    BOOLEAN          NOT NULL
is_supervisor                BOOLEAN          NOT NULL
job_title                    VARCHAR(50)      NOT NULL
adult_beverage_trained       BOOLEAN          NOT NULL
created_at                   DATETIME         NOT NULL
termination_date             DATE             NULL
mv_retail_employee_number    VARCHAR(50)      NULL
crossmark_employee_id        VARCHAR(50)      NULL
external_id                  VARCHAR(100)     NULL
last_synced                  DATETIME         NULL
sync_status                  VARCHAR(20)      NULL
```

### Relationships
- `schedules` → Schedule (one-to-many)
- `rotation_assignments` → RotationAssignment (one-to-many)
- `pending_schedules` → PendingSchedule (one-to-many)
- `attendance_records` → EmployeeAttendance (one-to-many)

### Notes for ML Features
- **Role determination**: Use `job_title` field or `is_supervisor` flag
- **Experience**: Could calculate from `created_at` (days since hire)
- **Active status**: Use `is_active` boolean

---

## Event Model

**Table**: `events`

### Columns
```
id                           INTEGER          PRIMARY KEY
project_name                 TEXT             NOT NULL
project_ref_num              INTEGER          NOT NULL (used as ref_num)
location_mvid                TEXT             NULL
store_number                 INTEGER          NULL
store_name                   TEXT             NULL
start_datetime               DATETIME         NOT NULL
due_datetime                 DATETIME         NOT NULL
estimated_time               INTEGER          NULL
is_scheduled                 BOOLEAN          NOT NULL
event_type                   VARCHAR(20)      NOT NULL ✅
condition                    VARCHAR(20)      NULL
external_id                  VARCHAR(100)     NULL
last_synced                  DATETIME         NULL
sync_status                  VARCHAR(20)      NULL
sales_tools_url              TEXT             NULL
edr_status                   VARCHAR(50)      NULL
edr_status_updated           DATETIME         NULL
parent_event_ref_num         INTEGER          NULL (FOREIGN KEY)
```

### Relationships
- `schedules` → Schedule (one-to-many)
- `pending_schedules` → PendingSchedule (one-to-many)

### Event Types Found
Based on ML implementation plan, expected types:
- Juicer
- Digital Setup
- Digital Refresh
- Freeosk
- Digital Teardown
- Core
- Supervisor
- Digitals
- Other

---

## Schedule Model

**Table**: `schedules`

### Columns
```
id                           INTEGER          PRIMARY KEY
event_ref_num                INTEGER          NOT NULL (FOREIGN KEY → Event)
employee_id                  VARCHAR(50)      NOT NULL (FOREIGN KEY → Employee)
schedule_datetime            DATETIME         NOT NULL
external_id                  VARCHAR(100)     NULL
last_synced                  DATETIME         NULL
sync_status                  VARCHAR(20)      NULL
shift_block                  INTEGER          NULL
shift_block_assigned_at      DATETIME         NULL
```

### Relationships
- `employee` → Employee (many-to-one)
- `event` → Event (many-to-one) ✅

### Notes for ML Features
- ⚠️ **No direct event_type field**
- ✅ **Access via relationship**: `schedule.event.event_type`
- Example query: `db.query(Schedule).filter(...).join(Event).filter(Event.event_type == 'Core')`

---

## PendingSchedule Model

**Table**: `pending_schedules`

### Columns
```
id                           INTEGER          PRIMARY KEY
scheduler_run_id             INTEGER          NOT NULL (FOREIGN KEY)
event_ref_num                INTEGER          NOT NULL (FOREIGN KEY → Event)
employee_id                  VARCHAR          NULL (FOREIGN KEY → Employee)
schedule_datetime            DATETIME         NULL
schedule_time                TIME             NULL
status                       VARCHAR(20)      NULL ✅
is_swap                      BOOLEAN          NULL
bumped_event_ref_num         INTEGER          NULL (FOREIGN KEY → Event)
bumped_posted_schedule_id    INTEGER          NULL
swap_reason                  TEXT             NULL
failure_reason               TEXT             NULL
api_error_details            TEXT             NULL
api_submitted_at             DATETIME         NULL
created_at                   DATETIME         NULL
updated_at                   DATETIME         NULL
```

### Relationships
- `event` → Event (many-to-one) ✅
- `employee` → Employee (many-to-one) ✅
- `bumped_event` → Event (many-to-one)
- `scheduler_run` → SchedulerRunHistory (many-to-one)

### Status Values (Confirmed)
Based on production data:
- `api_submitted` - Successfully submitted to API
- `proposed` - Proposed schedule awaiting approval
- `api_failed` - Failed to submit to API

### Notes for ML Features
- ✅ Training labels: Success = ['api_submitted', 'proposed'], Failure = ['api_failed']
- ✅ Access event type via: `pending_schedule.event.event_type`
- ✅ Access employee info via: `pending_schedule.employee.job_title`

---

## EmployeeAttendance Model

**Table**: `employee_attendance`

### Columns
```
id                           INTEGER          PRIMARY KEY
employee_id                  VARCHAR(50)      NOT NULL (FOREIGN KEY → Employee)
attendance_date              DATE             NOT NULL ✅
status                       VARCHAR(20)      NOT NULL
notes                        TEXT             NULL
recorded_by                  VARCHAR(100)     NULL
recorded_at                  DATETIME         NOT NULL
updated_at                   DATETIME         NULL
```

### Relationships
- `employee` → Employee (many-to-one)

### Status Values
From model constants:
- `on_time`
- `late`
- `called_in`
- `no_call_no_show`
- `excused_absence`

### Notes for ML Features
- ✅ Use `attendance_date` (not schedule_datetime)
- ✅ Filter by date: `EmployeeAttendance.attendance_date >= thirty_days_ago.date()`

---

## Recommendations for ML Feature Extraction

### 1. Employee Role Handling
```python
# Option A: Use job_title directly
role = employee.job_title  # e.g., "Lead", "Specialist"

# Option B: Derive from is_supervisor
if employee.is_supervisor:
    role = "Lead"
else:
    role = "Specialist"  # Or parse from job_title

# Option C: Use job_title with mapping
role_mapping = {
    'Lead': 'Lead',
    'Specialist': 'Specialist',
    'Juicer': 'Juicer',
    # ... other mappings
}
role = role_mapping.get(employee.job_title, 'Specialist')
```

### 2. Event Type from Schedule
```python
# When querying Schedule model
# Option A: Eager load the relationship
schedules = db.query(Schedule).options(
    joinedload(Schedule.event)
).filter(...)

for schedule in schedules:
    event_type = schedule.event.event_type  # Access via relationship

# Option B: Join in query
schedules = db.query(Schedule).join(Event).filter(
    Event.event_type == 'Core',
    Schedule.employee_id == employee_id
).all()
```

### 3. Years of Experience
```python
from datetime import datetime

if employee.created_at:
    days_employed = (datetime.now() - employee.created_at).days
    years_experience = days_employed / 365.25
else:
    years_experience = 1.0  # Default assumption
```

---

## Updated Feature Extraction Strategy

Based on schema discovery, features should be extracted as:

### Employee Features
```python
# Role (from job_title or is_supervisor)
features['is_supervisor'] = 1.0 if employee.is_supervisor else 0.0
features['job_title_encoded'] = encode_job_title(employee.job_title)

# Experience (derived from created_at)
features['days_employed'] = (datetime.now() - employee.created_at).days if employee.created_at else 365

# Active status
features['is_active'] = 1.0 if employee.is_active else 0.0
```

### Schedule Queries
```python
# Count events by type (via relationship)
from sqlalchemy.orm import joinedload

recent_schedules = db.query(Schedule).options(
    joinedload(Schedule.event)
).filter(
    Schedule.employee_id == employee.id,
    Schedule.schedule_datetime >= thirty_days_ago
).all()

# Access event type
for schedule in recent_schedules:
    event_type = schedule.event.event_type
```

### PendingSchedule Labels
```python
# Training labels
success_statuses = ['api_submitted', 'proposed']
failure_statuses = ['api_failed']

label = 1 if pending_schedule.status in success_statuses else 0
```

---

## Action Items

1. ✅ Update `SimpleEmployeeFeatureExtractor` to use:
   - `job_title` or `is_supervisor` instead of `role`
   - Derived experience from `created_at`
   - Relationship access for event types

2. ✅ Update data preparation to:
   - Use correct status values
   - Eager load relationships to avoid N+1 queries
   - Handle missing fields gracefully

3. ✅ Test feature extraction on single record before full training

4. ✅ Re-run training with corrected schema

---

**Schema Discovery Complete**: All necessary fields documented and mapped
