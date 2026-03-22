# Spec 5: Lead Attendance View

## Overview

Create a new lead-specific attendance page that visually resembles the supervisor's attendance calendar but enforces the locking rules from Spec 4. Leads can submit new attendance records but cannot edit or delete existing ones. Every record shows who submitted it and whether it was modified.

## Dependencies

- **Spec 4 (Attendance Audit Trail + Locking)** must be implemented first — this spec depends on the `modified_by`/`modified_at` columns and API locking enforcement.

## Roles Affected

- **Lead** — gets new attendance page
- **Supervisor** — no changes (keeps existing attendance page)
- **Specialist** — no attendance access

## Requirements

### 1. Lead Attendance Page (`/lead/attendance`)

#### 1a. Route

- **Path**: `/lead/attendance` and `/lead/attendance/<date>`
- **Auth**: `@require_authentication()` + `@require_role('lead')`
- **Template**: `app/templates/lead/attendance.html` *(new)*

#### 1b. Layout — Monthly Calendar Grid

Similar visual structure to supervisor's attendance calendar (`attendance.html`):
- Monthly grid (7 columns, 5-6 rows)
- Month/year header with prev/next navigation
- Color-coded day cells by attendance status (same color scheme as supervisor view)
- Legend showing status colors
- "Today" button to jump to current month

#### 1c. Day Detail Panel

When clicking a date:
- Shows all employees scheduled for that date
- For each employee:

| Field | Display |
|-------|---------|
| Employee Name | Title case |
| Attendance Status | Color-coded badge (On-Time, Late, Called-In, No-Call-No-Show, Excused Absence) |
| Submitted By | "Recorded by {recorded_by}" — always shown |
| Modified | "Modified by {modified_by} on {modified_at}" — only shown if `is_modified` is true |
| Notes | If any |

#### 1d. Submitting New Records

- If an employee has **no attendance record** for that date:
  - Show a status dropdown (same options as supervisor: on_time, late, called_in, no_call_no_show, excused_absence)
  - Optional notes field
  - Submit button
  - Calls `POST /api/attendance` — API will accept because no existing record
  - After submit, cell updates to show the recorded status with "Recorded by {lead_username}"

#### 1e. Existing Records — Read Only

- If an employee already has an attendance record for that date:
  - Show the status badge, who submitted it, modification history
  - **No edit button, no delete button**
  - If lead tries to submit via API, the locking rules from Spec 4 return 403
  - Visual indicator: lock icon next to existing records

#### 1f. Employee Filter

- Dropdown to filter by specific employee or "All Employees" (default)
- Same pattern as supervisor's attendance page

### 2. Statistics Summary

- Show monthly stats (same as supervisor view):
  - Total records, on-time count, late count, called-in count, no-call-no-show count
  - On-time rate percentage
- These are read-only aggregate stats, no edit capability

### 3. Differences from Supervisor Attendance Page

| Feature | Supervisor | Lead |
|---------|-----------|------|
| View attendance records | Yes | Yes |
| Submit new records | Yes | Yes |
| Edit existing records | Yes | **No** |
| Delete records | Yes | **No** |
| See who submitted | Yes (recorded_by) | Yes (recorded_by) |
| See modifications | Yes (modified_by) | Yes (modified_by) |
| Employee filter | Yes | Yes |
| Monthly stats | Yes | Yes |
| Export/Print | Yes | **No** (optional, can add later) |

### 4. Scheduled Employees for Date

Use existing `GET /api/attendance/scheduled-employees/<date>` endpoint to get all employees scheduled for a date with their current attendance status. This already returns the data needed.

The response should now also include `recorded_by`, `modified_by`, `modified_at`, `is_modified` fields (from Spec 4 changes).

## Files Created

| File | Purpose |
|------|---------|
| `app/templates/lead/attendance.html` | Lead attendance page |
| `app/static/css/pages/lead-attendance.css` | Lead attendance styles |
| `app/static/js/pages/lead-attendance.js` | Lead attendance JS (calendar rendering, submit logic) |

## Files Modified

| File | Change |
|------|--------|
| `app/routes/main.py` | Add `/lead/attendance` route |
| `app/templates/base.html` | Lead sidebar already includes link (from Spec 3) |

## Acceptance Criteria

- [ ] Lead can access `/lead/attendance` — sees monthly calendar grid
- [ ] Calendar cells are color-coded by attendance status
- [ ] Clicking a date shows scheduled employees with attendance status
- [ ] Each record shows "Recorded by {name}"
- [ ] Modified records show "Modified by {name} on {date}"
- [ ] Lead can submit attendance for employees with no existing record
- [ ] Lead cannot edit or delete existing records (no buttons shown)
- [ ] If lead tries to submit for an employee+date that already has a record, they see an error
- [ ] Existing records show a lock icon
- [ ] Employee filter works
- [ ] Monthly stats display correctly
- [ ] Supervisor's attendance page is unchanged
- [ ] Specialist cannot access this page
