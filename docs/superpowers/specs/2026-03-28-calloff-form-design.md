# Calloff Form — Design Spec

**Date**: 2026-03-28
**Status**: Approved
**Scope**: PWA calloff form for leads/specialists + supervisor management dashboard

## Context

Employees currently have no in-app way to report a same-day or next-day absence. They call or text their supervisor, which is inconsistent, hard to track, and leaves no audit trail. The existing time-off request system handles planned future absences but is the wrong tool for day-of emergencies.

This feature adds a mobile-first calloff form to the specialist/lead experience, a supervisor management dashboard for tracking and resolving calloffs, and pattern detection to surface attendance trends.

## Feature Overview

1. **Employee calloff form** — PWA mobile-first form for today/tomorrow calloffs
2. **Supervisor management dashboard** — review queue, excused/unexcused workflow, comments, file uploads
3. **Notifications** — push notification + SMS to supervisor on submission
4. **Attendance integration** — auto-creates `called_in` attendance record
5. **Schedule impact** — shows affected events, supervisor can unschedule/reassign
6. **Pattern tracking** — 30-day calloff count, day-of-week frequency, threshold alerts
7. **File management** — supervisor uploads doctor's notes, photos, etc.

---

## Data Model

### `EmployeeCalloff`

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| `id` | Integer | PK, auto-increment | |
| `employee_id` | String(50) | FK → employees.id, not null | Who called off |
| `calloff_date` | Date | not null | The date of absence |
| `reason` | String(50) | not null | `sick`, `family_emergency`, `personal`, `other` |
| `notes` | Text | nullable | Employee's additional context |
| `status` | String(20) | not null, default `pending` | `pending` → `excused` / `unexcused` |
| `reviewed_by` | String(100) | nullable | Supervisor name who reviewed |
| `reviewed_at` | DateTime | nullable | When reviewed |
| `supervisor_comments` | Text | nullable | Supervisor notes |
| `attendance_id` | Integer | FK → employee_attendance.id, nullable | Auto-created attendance link |
| `created_at` | DateTime | not null, default utcnow | Submission timestamp |
| `notified_at` | DateTime | nullable | When supervisor was push/SMS notified |

**Indexes:**
- `(employee_id, calloff_date)` — unique constraint, one calloff per employee per day
- `(status, created_at)` — pending calloff queries
- `(employee_id, created_at)` — employee history and pattern queries

### `CalloffAttachment`

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| `id` | Integer | PK, auto-increment | |
| `calloff_id` | Integer | FK → employee_calloffs.id, not null, cascade delete | Parent calloff |
| `filename` | String(255) | not null | Original filename |
| `file_path` | String(500) | not null | Server path (`uploads/calloffs/`) |
| `file_type` | String(100) | nullable | MIME type |
| `uploaded_by` | String(100) | not null | Employee ID or supervisor name |
| `created_at` | DateTime | not null, default utcnow | Upload timestamp |

**Index:** `(calloff_id)` — fetch attachments for a calloff

### File Storage

- Location: `uploads/calloffs/<YYYY-MM>/<calloff_id>/`
- Allowed types: PDF, JPEG, PNG, HEIC, WEBP
- Max file size: 10 MB per file
- Filenames: `secure_filename()` from werkzeug, prefixed with timestamp to avoid collisions
- Cleanup: files cascade-deleted when calloff is deleted (if ever needed)

---

## API Endpoints

### Employee-facing (specialist/lead)

```
POST   /api/calloffs                    — Submit a calloff
GET    /api/calloffs/my                 — My calloff history
GET    /api/calloffs/affected-events    — Preview affected events for a date
```

#### `POST /api/calloffs`

**Auth**: `@require_authentication()` — specialist or lead only
**Body**:
```json
{
  "calloff_date": "2026-03-28",      // required, today or tomorrow only
  "reason": "sick",                   // required, one of: sick, family_emergency, personal, other
  "notes": "Woke up with a fever..." // optional
}
```
**Response** (201):
```json
{
  "status": "success",
  "calloff": {
    "id": 1,
    "calloff_date": "2026-03-28",
    "reason": "sick",
    "status": "pending",
    "affected_events": [
      {"event_name": "Core Event", "event_type": "Core", "time": "9:00 AM"}
    ]
  }
}
```
**Side effects**:
1. Creates `EmployeeAttendance` record with `status='called_in'`
2. Sends push notification to all supervisors
3. Sends SMS to configured supervisor number (if `SMS_NOTIFICATIONS_ENABLED`)
4. Flags affected scheduled events (does NOT unschedule)

**Validation**:
- `calloff_date` must be today or tomorrow (reject past dates and dates > tomorrow)
- Duplicate check: one calloff per employee per day
- Employee must have role `specialist` or `lead`

#### `GET /api/calloffs/my`

**Auth**: specialist or lead
**Query params**: `?limit=20&offset=0`
**Returns**: Employee's own calloff history, newest first

#### `GET /api/calloffs/affected-events?date=2026-03-28`

**Auth**: specialist or lead
**Returns**: List of scheduled events for the authenticated employee on the given date. Used by the form to show the "Affected Events" preview before submission.

### Supervisor-facing

```
GET    /api/calloffs                         — List all calloffs (filterable)
GET    /api/calloffs/<id>                    — Single calloff detail with attachments
PUT    /api/calloffs/<id>/review             — Mark excused/unexcused + comment
POST   /api/calloffs/<id>/attachments        — Upload file
DELETE /api/calloffs/<id>/attachments/<aid>   — Remove attachment
GET    /api/calloffs/<id>/attachments/<aid>/download — Download file
GET    /api/calloffs/patterns                — Employee patterns & alerts
POST   /api/calloffs/<id>/resolve            — Unschedule affected events
```

#### `PUT /api/calloffs/<id>/review`

**Auth**: `@require_role('supervisor')`
**Body**:
```json
{
  "status": "excused",                    // required: "excused" or "unexcused"
  "supervisor_comments": "Dr note received" // optional
}
```
**Side effects**:
- If `excused`: updates linked `EmployeeAttendance` to `excused_absence`
- Sets `reviewed_by` to supervisor name, `reviewed_at` to now

#### `POST /api/calloffs/<id>/attachments`

**Auth**: `@require_role('supervisor')`
**Body**: multipart/form-data with `file` field
**Validation**: Allowed extensions (pdf, jpg, jpeg, png, heic, webp), max 10 MB
**Returns**: Attachment metadata (id, filename, file_type, created_at)

#### `POST /api/calloffs/<id>/resolve`

**Auth**: `@require_role('supervisor')`
**Body**:
```json
{
  "action": "unschedule_all"  // or "unschedule" with "schedule_ids": [1, 2]
}
```
**Behavior**: Reuses the same pattern as `resolve_time_off_conflicts` — unschedules events via Crossmark API, sends schedule change notifications to the employee.

#### `GET /api/calloffs/patterns`

**Auth**: `@require_role('supervisor')`
**Query params**: `?days=30` (default 30, supports 30/60/90)
**Returns**:
```json
{
  "employees": [
    {
      "employee_id": "US123",
      "name": "Jane Smith",
      "total_calloffs": 3,
      "by_reason": {"sick": 2, "personal": 1},
      "by_day_of_week": {"Monday": 2, "Friday": 1},
      "last_calloff": "2026-03-28",
      "alert": true,
      "alert_reason": "3 calloffs in 30 days"
    }
  ],
  "threshold": 3,
  "window_days": 30
}
```

#### `POST /api/calloffs/<id>/notify-sms` (behind feature flag)

**Auth**: `@require_role('supervisor')`
**Behavior**: Resends SMS notification to supervisor. Useful if the original SMS failed or a different supervisor needs to be notified.

---

## Pages & Templates

| Route | Template | Role | Purpose |
|-------|----------|------|---------|
| `/calloff` | `calloff_form.html` | specialist, lead | PWA calloff submission form |
| `/calloffs` | `calloff_management.html` | supervisor | Management dashboard |

### Employee Calloff Form (`/calloff`)

Single-page mobile-first form:
- **Date toggle**: Today / Tomorrow buttons (defaults to today, highlighted)
- **Reason dropdown**: Sick/Illness, Family Emergency, Personal, Other
- **Doctor's note warning**: Yellow banner shown only when "Sick/Illness" selected — "A doctor's note will be required to turn in to your Club Supervisor upon return to work in order to be excused."
- **Additional details**: Optional textarea for context
- **Affected events preview**: Shows scheduled events for the selected date with "Will be affected" badges. Loaded via `/api/calloffs/affected-events?date=...` when date changes.
- **Submit button**: Full-width, primary color

**Access point**: Prominent "Call Off" button on the `my_dashboard` page, above the fold.

### Supervisor Management Dashboard (`/calloffs`)

Three-tab layout:

**Tab 1 — Pending Review** (default, badge count):
- Calloff cards sorted newest first
- Each card shows: employee name/avatar, date, reason (with emoji), 30-day count (green/red), employee notes, affected events, doctor's note reminder (if sick)
- Action buttons: Mark Excused, Mark Unexcused, Upload File, Comment
- NEW badge on calloffs submitted within the last hour

**Tab 2 — All Calloffs**:
- Filterable table/list of all calloffs
- Filters: employee, date range, status (pending/excused/unexcused), reason
- Each row shows: date, employee, reason, status badge, attachment count, comment indicator
- Click to expand/view detail

**Tab 3 — Patterns & Alerts**:
- Per-employee summary cards with calloff count, most common reason, day-of-week frequency
- Visual indicators: green (normal), yellow (approaching threshold), red (threshold exceeded)
- Alert banner when any employee hits the threshold

**Access point**: "Calloffs" link in supervisor sidebar. Badge count for pending calloffs.

---

## Notification Flow

### On Calloff Submission

1. **Push notification** to all supervisors (reuses existing push infrastructure):
   - Title: "Calloff: {employee_name}"
   - Body: "{reason} — {date}. {N} events affected."
   - Click URL: `/calloffs` (supervisor management page)

2. **SMS notification** to configured supervisor number (behind `SMS_NOTIFICATIONS_ENABLED` flag):
   - Message: "{employee_name} called off for {date} ({reason}). {N} events affected. View: {app_url}/calloffs"
   - Uses Twilio API
   - Config: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `SUPERVISOR_SMS_NUMBER`

3. **In-app notification**: Pending count badge on supervisor sidebar

### On Supervisor Review

- No notification back to employee (they know they called off)
- Attendance record updated if excused

---

## Attendance Integration

When a calloff is submitted:
1. Query `EmployeeAttendance` for `(employee_id, calloff_date)`
2. If exists: update status to `called_in`, append to notes
3. If not exists: create new record with `status='called_in'`, `recorded_by='system:calloff'`
4. Store the `attendance_id` on the calloff record for linkage

When supervisor marks excused:
1. Load linked `EmployeeAttendance` via `attendance_id`
2. Update status to `excused_absence`
3. Update `modified_by` to supervisor name

---

## Schedule Impact

When calloff is submitted:
- Query employee's schedules for `calloff_date`
- Return affected events in the API response and store count on the calloff
- Events are NOT automatically unscheduled

When supervisor clicks "Resolve" on a calloff:
- Reuse the `resolve_time_off_conflicts` pattern from `employees.py`
- Unschedule via Crossmark API, send schedule change notifications
- Supervisor can choose to unschedule all or select specific events

---

## Pattern Detection

Runs synchronously on each calloff submission (lightweight query):

```python
def check_calloff_patterns(employee_id, window_days=30):
    cutoff = date.today() - timedelta(days=window_days)
    recent = EmployeeCalloff.query.filter(
        EmployeeCalloff.employee_id == employee_id,
        EmployeeCalloff.calloff_date >= cutoff
    ).all()

    count = len(recent)
    alert = count >= CALLOFF_ALERT_THRESHOLD  # default: 3

    # Day-of-week frequency
    day_counts = Counter(c.calloff_date.strftime('%A') for c in recent)

    return {
        'count': count,
        'alert': alert,
        'by_day_of_week': dict(day_counts),
        'by_reason': dict(Counter(c.reason for c in recent))
    }
```

**Alert threshold**: Configurable via `SystemSetting` (key: `calloff_alert_threshold`, default: 3). Stored in the database so supervisors can adjust without redeployment.

---

## SMS Integration (Twilio)

Behind `SMS_NOTIFICATIONS_ENABLED` feature flag (default: false).

**Config** (in `.env`):
```
SMS_NOTIFICATIONS_ENABLED=false
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
SUPERVISOR_SMS_NUMBER=
```

**Service** (`app/services/sms_service.py`):
```python
def send_calloff_sms(employee_name, calloff_date, reason, affected_count):
    if not config.SMS_NOTIFICATIONS_ENABLED:
        return
    # Twilio REST API call
```

Fails silently with logging — SMS failure should never block the calloff submission.

---

## New Files

| File | Purpose |
|------|---------|
| `app/models/calloff.py` | EmployeeCalloff + CalloffAttachment models |
| `app/services/calloff_service.py` | Submission, review, pattern detection, attendance integration |
| `app/services/sms_service.py` | Twilio SMS delivery |
| `app/routes/api_calloffs.py` | All calloff API endpoints |
| `app/templates/calloff_form.html` | Employee PWA form |
| `app/templates/calloff_management.html` | Supervisor dashboard |
| `app/static/css/pages/calloff-form.css` | Form styling |
| `app/static/css/pages/calloff-management.css` | Dashboard styling |
| `app/static/js/pages/calloff-form.js` | Form logic (date toggle, affected events fetch, submit) |
| `app/static/js/pages/calloff-management.js` | Dashboard logic (tabs, filters, review actions, uploads) |
| `migrations/versions/xxxx_add_calloff_tables.py` | DB migration |

## Modified Files

| File | Change |
|------|--------|
| `app/models/__init__.py` | Register EmployeeCalloff + CalloffAttachment in model factory |
| `app/__init__.py` | Register api_calloffs blueprint, add upload folder config |
| `app/config.py` | Add SMS/Twilio config vars, calloff upload path |
| `app/templates/base.html` | Add "Calloffs" to supervisor sidebar with badge |
| `app/templates/my_dashboard.html` | Add "Call Off" button for specialist/lead |
| `app/routes/main.py` | Add `/calloff` and `/calloffs` page routes |
| `requirements.txt` | Add `twilio` package |
| `CLAUDE.md` | Add api_calloffs_bp to blueprint table |

---

## Verification

1. **Employee flow**: Log in as specialist → dashboard shows "Call Off" button → tap → fill form → select Sick/Illness → verify doctor's note warning appears → submit → verify attendance record created → verify push notification sent to supervisor
2. **Supervisor flow**: Log in as supervisor → sidebar shows "Calloffs" with badge → click → see pending calloff → mark excused → verify attendance updated to `excused_absence` → upload a doctor's note file → verify file saves and displays
3. **Schedule impact**: Submit calloff for a day with scheduled events → verify affected events shown → supervisor clicks resolve → verify events unscheduled via API
4. **Pattern detection**: Submit 3+ calloffs for same employee in 30 days → verify alert appears on Patterns tab → verify 30-day count shows red on calloff card
5. **Date restriction**: Try to submit calloff for 2 days from now → verify rejection
6. **Duplicate prevention**: Submit calloff for today → try again for same day → verify rejection
7. **SMS**: Configure Twilio creds → submit calloff → verify SMS received (or logs show attempt)
8. **File upload**: Upload PDF + JPEG → verify both display → download each → verify content matches → delete one → verify removed
