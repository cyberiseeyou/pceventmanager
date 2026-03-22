# Spec 2: Specialist Views (Dashboard + Monthly Schedule + Sidebar)

## Overview

Redesign the specialist (non-lead employee) experience so they only see pages and data relevant to them. Specialists get a personal dashboard with a weekly calendar grid, a monthly schedule page, and a locked-down sidebar with only their pages.

## Roles Affected

- **Specialist** — full redesign of their views
- **Lead / Supervisor** — no changes to their existing views

## Requirements

### 1. Specialist Sidebar (Locked Down)

The specialist sidebar shows ONLY these items:

| Item | Icon | Route |
|------|------|-------|
| My Dashboard | `home` | `/my-dashboard` |
| My Events | `list_alt` | `/events` (already filtered to their events) |
| Monthly Schedule | `calendar_month` | `/my-schedule/monthly` *(new)* |
| Request Time Off | `event_busy` | `/time-off` |

**Remove for specialists:** Daily View, Calendar, Auto-Scheduler, Notifications, Unreported Events, Left in Approved, Lost Demos, Employees, Attendance, Analytics, all Tools group items.

### 2. Specialist Dashboard (`/my-dashboard`) — Redesigned

#### 2a. Greeting + Today/Next Event

- Keep existing greeting (Good morning/afternoon/evening + first name + date)
- **Today's events** section: if events today, show event name, type, and time for each
- **Next scheduled event**: if no events today, prominently show the next upcoming event with date, time, event name, and type

#### 2b. Stats Card — "This Week"

| Stat | Source | Display |
|------|--------|---------|
| Scheduled Hours | Sum of `Event.estimated_time` (minutes) for all schedules this week, converted to hours | e.g., "12.5 hrs" |
| Days Scheduled | Count of distinct dates with schedules this week | e.g., "4 days" |
| Events | Count of schedules this week | e.g., "6 events" |

`estimated_time` is in minutes on the Event model. If null, use `Event.get_default_duration(event_type)` as fallback.

#### 2c. Time-Off Request Form

- Keep existing form: start date, end date, reason (optional), submit button
- Posts to `POST /api/my-time-off` (existing endpoint)
- No changes to behavior

#### 2d. Time-Off Request Status List

- Keep existing list showing all future/current time-off requests
- Status badges: pending (yellow), approved (green), denied (red)
- Denial reason shown if denied
- No changes to behavior

#### 2e. Weekly Calendar Grid (Sun–Sat)

- **Grid layout**: 7 columns (Sunday through Saturday) for the current week
- **Header row**: Day abbreviations (Sun, Mon, Tue, Wed, Thu, Fri, Sat) with date numbers
- **Current day** highlighted with distinct background/border
- **Events displayed** in each day cell:
  - Event name (truncated if long)
  - Scheduled time (e.g., "8:00 AM")
  - Event type color accent (reuse existing `event_accent()` mapping: core=blue, juicer=purple, digital=teal, etc.)
- **Empty days**: show subtle "No events" or leave empty
- **Week navigation**: Previous/Next week arrows to browse other weeks
- **Data source**: `GET /api/my-schedule/weekly?week_start=YYYY-MM-DD` *(new endpoint)*
- **Only shows the logged-in employee's schedule**

#### 2f. Section Ordering on Dashboard

1. Greeting + Today/Next Event
2. Stats Card (This Week)
3. Weekly Calendar Grid
4. Time-Off Request Form + Status List
5. Remove: Quick Actions buttons, Notes section, "Upcoming Schedule" list (replaced by weekly grid)

### 3. Monthly Schedule Page (`/my-schedule/monthly`) — New Page

- **Route**: `/my-schedule/monthly` (on main blueprint)
- **Auth**: `@require_authentication()` — any authenticated employee
- **Layout**: Full calendar month grid (standard 7-column, 5-6 row layout)
- **Data**: only the logged-in employee's scheduled events
- **Day cells show**:
  - Event count badge if events exist
  - Color dot per event type
  - Clicking a day expands to show event details (name, time, type, store) — inline expansion or modal
- **Navigation**: Previous/Next month arrows, "Today" button to jump to current month
- **Header**: Month name + year (e.g., "March 2026")
- **No supervisor features**: No validation status, no lock indicators, no unscheduled counts, no employee filters
- **Responsive**: Collapses gracefully on mobile (list view fallback at 480px)

### 4. New API Endpoint

#### `GET /api/my-schedule/weekly`

- **Auth**: `@require_authentication()`
- **Query params**: `week_start` (YYYY-MM-DD, defaults to current week's Sunday)
- **Returns**: Events for the logged-in employee for that Sun–Sat week

```json
{
  "week_start": "2026-03-15",
  "week_end": "2026-03-21",
  "days": {
    "2026-03-15": [],
    "2026-03-16": [
      {
        "schedule_id": 123,
        "time": "08:00 AM",
        "event_name": "Core - Walmart #1234",
        "event_type": "Core",
        "store_name": "Walmart #1234",
        "estimated_time": 390
      }
    ],
    ...
  },
  "stats": {
    "total_hours": 12.5,
    "days_scheduled": 4,
    "event_count": 6
  }
}
```

#### `GET /api/my-schedule/monthly`

- **Auth**: `@require_authentication()`
- **Query params**: `month` (YYYY-MM, defaults to current month)
- **Returns**: Events for the logged-in employee for that month, grouped by date

```json
{
  "month": "2026-03",
  "days": {
    "2026-03-02": [
      {
        "time": "08:00 AM",
        "event_name": "Core - Walmart #1234",
        "event_type": "Core",
        "store_name": "Walmart #1234",
        "estimated_time": 390
      }
    ],
    ...
  }
}
```

## Files Created

| File | Purpose |
|------|---------|
| `app/templates/my_schedule_monthly.html` | Monthly calendar page |
| `app/static/css/pages/my-schedule-monthly.css` | Monthly page styles |

### 5. Mobile Bottom Nav Update

Update the specialist mobile bottom nav (`base.html` lines 363-388) to match the sidebar:

| Item | Icon | Route |
|------|------|-------|
| Home | `home` | `/my-dashboard` |
| My Events | `list_alt` | `/events` |
| Monthly | `calendar_month` | `/my-schedule/monthly` |
| Time Off | `event_busy` | `/time-off` |

Replace the current Calendar link (which shows all employees) with Monthly Schedule.

### 6. Sidebar Structure (three-way branch)

The `base.html` sidebar must be restructured from the current `if specialist / else` pattern to a three-way `if specialist / elif lead / else (supervisor)` pattern. This spec handles the specialist block; Spec 3 handles the lead block. The supervisor `else` block remains unchanged.

### 7. Route Cleanup

When redesigning the dashboard, remove dead code from `my_dashboard()` route in `main.py`:
- Remove `upcoming_by_day` computation (lines 137-167) — replaced by weekly API
- Remove `employee_notes` query (lines 192-195) — Notes section removed from dashboard
- Remove corresponding template variables from `render_template()` call

### 8. API Blueprint

Place new `/api/my-schedule/*` endpoints on `api_bp` (prefix `/api`) for consistency with codebase convention, not on `main_bp`.

## Files Created

| File | Purpose |
|------|---------|
| `app/templates/my_schedule_monthly.html` | Monthly calendar page |
| `app/static/css/pages/my-schedule-monthly.css` | Monthly page styles |

## Files Modified

| File | Change |
|------|--------|
| `app/templates/my_dashboard.html` | Redesign: add weekly grid, update stats, remove notes/quick-actions/upcoming list |
| `app/static/css/pages/my-dashboard.css` | Add weekly grid styles, update layout |
| `app/routes/main.py` | Add monthly route, update dashboard data, remove dead code |
| `app/routes/api.py` | Add `GET /api/my-schedule/weekly` and `GET /api/my-schedule/monthly` endpoints |
| `app/templates/base.html` | Restructure sidebar to three-way branch; update specialist sidebar + mobile bottom nav |

## Acceptance Criteria

- [ ] Specialist sidebar shows only: My Dashboard, My Events, Monthly Schedule, Request Time Off
- [ ] Specialist mobile bottom nav shows only: Home, My Events, Monthly, Time Off
- [ ] Dashboard shows scheduled hours (from `estimated_time`), days scheduled, event count
- [ ] Weekly grid displays Sun–Sat with events in correct day cells
- [ ] Week navigation (prev/next) works
- [ ] Current day is visually highlighted
- [ ] Monthly page shows month grid with employee's events only
- [ ] Month navigation works
- [ ] No supervisor data visible (no validation, no locks, no other employees)
- [ ] Time-off form and status list work unchanged
- [ ] Mobile responsive at 480px breakpoint
- [ ] Dead code removed from `my_dashboard()` route

## Cross-Spec Dependencies

- **Spec 3 depends on this spec** — the lead sidebar block and dashboard widget build on the restructured `base.html` and redesigned `my_dashboard.html`
- This spec is independent of Specs 1, 4, 5
