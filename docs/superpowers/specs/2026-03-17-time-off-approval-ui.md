# Spec 1: Time-Off Approval UI

## Overview

Add a supervisor-only "Pending Approvals" tab to the existing Availability Management page (`/time-off`), surface pending request counts in the notification bell, and fix the CP-SAT scheduler to only honor approved time-off records.

## Roles Affected

- **Supervisor** — sees new tab, gets notification badge, can approve/deny
- **Lead** — no access to pending approvals (removed from endpoint)
- **Specialist** — no change (they submit requests from my-dashboard)

## Requirements

### 1. Pending Approvals Tab

- Add a third tab to `/time-off`: **"Time Off Requests" | "Pending Approvals" | "Availability Overrides"**
- Tab uses existing `.condition-tabs` / `.tab-btn` / `.tab-count` design system classes (from `unscheduled.css`)
- Pending Approvals tab uses `.tab-btn-warning` class (amber color) to draw attention
- Tab only renders for supervisors (`{% if is_supervisor %}`)
- Count badge on tab shows number of pending requests, hidden when zero

### 2. Approval Cards

Each pending request displays:
- Employee name (title case)
- Date range (formatted)
- Reason (if provided)
- Submitted date
- **Approve** button (green outline, fills on hover)
- **Deny** button (red outline, fills on hover)

### 3. Deny Workflow

- Clicking Deny opens a modal (follows existing modal pattern)
- Modal shows: employee name, date range, optional reason textarea
- Cancel and Confirm Deny buttons
- On confirm, calls `POST /api/time-off/<id>/review` with `{ action: "deny", reason: "..." }`

### 4. Approve Workflow

- Clicking Approve immediately calls `POST /api/time-off/<id>/review` with `{ action: "approve" }`
- No confirmation modal needed (single click)
- Flash message confirms action
- Card removed from list, count badge updates

### 5. Notification Panel Integration

- Add pending time-off count to `GET /api/notifications` — **supervisor-only check**
- Shows as warning: "X Pending Time Off Request(s)"
- Links to `/time-off?tab=pending`
- Page handles `?tab=pending` URL parameter to auto-switch tabs

### 6. CP-SAT Filter Fix

- `cpsat_scheduler.py` line 514: change `EmployeeTimeOff.query.all()` to `EmployeeTimeOff.query.filter_by(status='approved').all()`
- Remove stale TODO comment on lines 510-512
- Safe because `status` column has `server_default='approved'` — no NULL records exist

### 7. Endpoint Restriction

- `GET /api/time-off/pending`: change `@require_role('supervisor', 'lead')` to `@require_role('supervisor')`
- `POST /api/time-off/<id>/review`: already supervisor-only, no change needed

## Existing Endpoints Used (no new endpoints needed)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/time-off/pending` | GET | Fetch all pending requests |
| `/api/time-off/<id>/review` | POST | Approve or deny a request |
| `/api/notifications` | GET | Notification aggregator |

## Files Modified

| File | Change |
|------|--------|
| `app/templates/time_off_requests.html` | Add tab, panel, modal, JS, CSS |
| `app/routes/employees.py` | Pass `is_supervisor` to template; restrict pending endpoint |
| `app/routes/api_notifications.py` | Add Check 9 (supervisor-gated) |
| `app/services/cpsat_scheduler.py` | Filter by `status='approved'` |

## Acceptance Criteria

- [ ] Supervisor sees 3 tabs on `/time-off`; non-supervisors see 2 tabs
- [ ] Pending requests display with employee name, dates, reason, submitted date
- [ ] Approve removes card, updates badge, refreshes main list
- [ ] Deny opens modal, accepts optional reason, removes card after confirm
- [ ] Notification bell shows pending count for supervisors only
- [ ] Clicking notification links to `/time-off?tab=pending`
- [ ] CP-SAT only blocks scheduling for approved time-off
- [ ] All existing tests pass
