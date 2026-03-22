# Spec 3: Lead Dashboard + Lead Daily View

## Overview

Create lead-specific pages that are entirely separate from supervisor views. Leads get everything specialists get (personal dashboard with weekly grid, monthly schedule, time-off requests) plus a team daily view and an approved time-off widget. All lead pages are new — they do not share templates or routes with the supervisor.

## Roles Affected

- **Lead** — new dashboard, new daily view, new sidebar
- **Specialist / Supervisor** — no changes

## Requirements

### 1. Lead Sidebar

The lead sidebar shows ONLY these items:

| Item | Icon | Route |
|------|------|-------|
| My Dashboard | `home` | `/my-dashboard` |
| Team Daily View | `today` | `/lead/daily/<date>` *(new)* |
| Lead Attendance | `how_to_reg` | `/lead/attendance` *(new, Spec 5)* |
| My Events | `list_alt` | `/events` |
| Monthly Schedule | `calendar_month` | `/my-schedule/monthly` |
| Request Time Off | `event_busy` | `/time-off` |

**Remove for leads:** Supervisor Dashboard, Calendar, Auto-Scheduler, Notifications, Unreported Events, Left in Approved, Lost Demos, Employees list, Supervisor Attendance, Analytics, all Tools group items.

### 2. Lead Dashboard (`/my-dashboard`)

The lead dashboard is the **same page** as the specialist dashboard (Spec 2) with one addition:

#### 2a. Approved Time-Off Widget

- Placed after the weekly calendar grid, before the time-off request form
- **Title**: "Team Time Off" with `event_busy` icon
- **Shows**: upcoming approved time-off for OTHER employees (not the lead's own)
- **Each entry displays**:
  - Employee name (title case)
  - Date range (e.g., "Mar 20 – Mar 24, 2026")
  - **No reason shown** (privacy)
- **Query**: `EmployeeTimeOff` where `status='approved'`, `end_date >= today`, `employee_id != current_employee_id`
- **Sorted**: by `start_date` ascending (soonest first)
- **Limit**: show up to 10, with "View all" link if more
- **Empty state**: "No upcoming team time off"

#### 2b. Role Detection

The `/my-dashboard` route already receives the user's role. Pass `is_lead` boolean to the template. The widget renders inside `{% if is_lead %}`.

### 3. Lead Daily View (`/lead/daily/<date>`) — New Page

#### 3a. Purpose

Simple read-only view of all employees' schedules for a given date. No editing, no reassigning, no condition tracking.

#### 3b. Display

- **Header**: Date with day-of-week (e.g., "Monday, March 17, 2026")
- **Navigation**: Previous/Next day arrows, "Today" button
- **Schedule table/list** showing ALL scheduled employees for that date:

| Column | Source |
|--------|--------|
| Employee | `Employee.name` (title case) |
| Event | `Event.project_name` |
| Time | `Schedule.schedule_datetime` formatted as "8:00 AM" |

- **Sorted by**: scheduled time ascending
- **No other data**: no condition, no store, no reporting status, no edit buttons, no reassign, no EDR status
- **Empty state**: "No events scheduled for this date"

#### 3c. Route

- **Path**: `/lead/daily/<date>` (date format: YYYY-MM-DD)
- **Blueprint**: main blueprint or a new `lead_bp` blueprint
- **Auth**: `@require_authentication()` + `@require_role('lead', 'supervisor')`
- **Template**: `app/templates/lead/daily_view.html` *(new)*

#### 3d. API Endpoint

`GET /api/lead/daily-schedule/<date>`

- **Auth**: `@require_authentication()` + `@require_role('lead', 'supervisor')`
- **Returns**:

```json
{
  "date": "2026-03-17",
  "day_label": "Monday, March 17, 2026",
  "schedules": [
    {
      "employee_name": "John Doe",
      "event_name": "Core - Walmart #1234",
      "time": "08:00 AM"
    }
  ]
}
```

Or render server-side (simpler). Decision left to implementation plan.

### 4. Lead Role Routing

- When a lead logs in, they should be routed to `/my-dashboard` (same as specialist)
- Currently leads go to command center — change routing in `main.py` line 57-59:

```python
# Before:
if user and user.get('role') == 'specialist':
    return redirect(url_for('main.my_dashboard'))
return redirect(url_for('dashboard.command_center'))

# After:
if user and user.get('role') in ('specialist', 'lead'):
    return redirect(url_for('main.my_dashboard'))
return redirect(url_for('dashboard.command_center'))
```

## Files Created

| File | Purpose |
|------|---------|
| `app/templates/lead/daily_view.html` | Lead daily view template |
| `app/static/css/pages/lead-daily-view.css` | Lead daily view styles |

## Files Modified

| File | Change |
|------|--------|
| `app/templates/my_dashboard.html` | Add team time-off widget (inside `{% if is_lead %}`) |
| `app/routes/main.py` | Add lead daily view route, add `is_lead` to dashboard context, update index routing |
| `app/templates/base.html` | Update lead sidebar (new section between specialist and supervisor) |
| `app/static/css/pages/my-dashboard.css` | Styles for team time-off widget |

### 5. Mobile Bottom Nav Update

Update the lead mobile bottom nav (`base.html` lines 389-419) to match the lead sidebar:

| Item | Icon | Route |
|------|------|-------|
| Home | `home` | `/my-dashboard` |
| Team Daily | `today` | `/lead/daily/<today>` |
| Attendance | `how_to_reg` | `/lead/attendance` |
| My Events | `list_alt` | `/events` |
| More | `more_horiz` | (expand menu) |

Fixes the pre-existing bug where lead bottom nav links to `main.attendance` (nonexistent endpoint).

## Acceptance Criteria

- [ ] Lead login redirects to `/my-dashboard` (not command center)
- [ ] Lead sidebar shows only: My Dashboard, Team Daily View, Lead Attendance, My Events, Monthly Schedule, Request Time Off
- [ ] Lead mobile bottom nav updated to match sidebar
- [ ] Lead dashboard shows personal stats, weekly grid, time-off (same as specialist)
- [ ] Lead dashboard additionally shows "Team Time Off" widget with approved time-off (no reason)
- [ ] Specialist dashboard does NOT show the team time-off widget
- [ ] Lead daily view shows: employee name, event name, scheduled time — nothing else
- [ ] Lead daily view has prev/next day navigation
- [ ] Lead daily view is read-only (no edit/reassign/delete actions)
- [ ] Supervisor views are unchanged

## Cross-Spec Dependencies

- **Depends on Spec 2** — sidebar three-way branch and dashboard redesign must be in place first
- Independent of Specs 1, 4, 5 (though Spec 5 creates the lead attendance page linked from sidebar)
