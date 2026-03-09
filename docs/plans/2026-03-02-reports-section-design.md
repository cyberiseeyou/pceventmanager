# Reports Section Design

**Date**: 2026-03-02
**Status**: Approved

## Overview

New Reports section with 7 reports, each on its own page. Accessible from a "Reports" hub page linked in the sidebar. Each report has a date range picker, Chart.js visualizations, data tables, and Print/Export CSV buttons.

Also: remove the Corporate Report button from the unscheduled events page.

## Architecture

- **Blueprint**: `reports_bp` at `/reports`
- **Service**: `app/services/report_service.py` — all report query methods
- **Templates**: `app/templates/reports/` — hub + 7 individual report pages
- **Charts**: Chart.js 4.4.0 (already in use on workload dashboard)
- **Sidebar**: "Reports" link under Tools group in `base.html`
- **Pattern**: Server-rendered pages. Each report page has a date range form that submits GET params. Server computes data, passes to template. Chart.js renders charts from data embedded in the template.

## Reports

### 1. Event Statistics (`/reports/event-statistics`)
Replaces the Corporate Report export from the events page.

**Summary cards**: Total Events, Completion Rate %, Scheduled %, Unscheduled %
**Pie chart**: Events by condition (Submitted, Scheduled, Unstaffed, Canceled, etc.)
**Table**: Events grouped by week — Event #, Name, Type, Status, Start Date, Due Date, Employee, Schedule Date, Days Available
**Default date range**: Current week (Sun-Sat)

### 2. Employee Schedule Details (`/reports/employee-schedules`)
**Per employee**: Section with name, table of assigned events sorted by schedule date
**Table columns**: Event Name, Event Type, Start Date, End Date, Schedule Date
**Per-employee totals**: X events, Y days scheduled
**Bar chart**: Events per employee (horizontal bars)
**Default date range**: Current week

### 3. Event Type Breakdown (`/reports/event-type-breakdown`)
**Donut chart**: Each event type's share of total
**Table**: Event Type, Count, Percentage — sorted by count descending
**Summary card**: Total events in range
**Default date range**: Current week

### 4. Employee Workload (`/reports/employee-workload`)
**Horizontal bar chart**: Estimated hours per employee
**Table**: Employee, Event Count, Total Hours, Avg Hours/Event, Status (Normal/High/Overloaded)
**Color-coded status**: Normal (green), High (yellow), Overloaded (red)
**Thresholds**: Normal <=12 events, High <=18, Overloaded >=19
**Default date range**: Current week

### 5. Attendance Report (`/reports/attendance`)
**Stacked bar chart**: Per employee — on-time vs late vs absent
**Table**: Employee, Days Tracked, On-Time, Late, Called-In, No-Call-No-Show, Excused, Attendance Rate %
**Default date range**: Current month

### 6. Scheduling Coverage (`/reports/scheduling-coverage`)
**Line chart**: Daily coverage % (scheduled / total events) over the date range
**Table**: Date, Total Events, Scheduled, Unscheduled, Coverage %
**Summary cards**: Overall coverage %, best day, worst day
**Default date range**: Current week

### 7. Time Off Summary (`/reports/time-off`)
**Horizontal timeline**: Bars showing each employee's time-off blocks across the date range
**Table**: Employee, Start Date, End Date, Days Off, Reason
**Summary**: Total time-off days across team
**Default date range**: Current month

## Shared Features

Every report page has:
- Date range picker (from/to) with "Generate" button
- Print button (triggers `window.print()` via `data-action`)
- Export CSV button (downloads server-generated CSV)
- `@media print` CSS hiding nav/sidebar/buttons
- Consistent header styling matching existing dashboard pages

## Files to Create

| File | Purpose |
|------|---------|
| `app/routes/reports.py` | Blueprint with routes |
| `app/services/report_service.py` | Query/computation methods |
| `app/templates/reports/index.html` | Hub page with report cards |
| `app/templates/reports/event_statistics.html` | Report 1 |
| `app/templates/reports/employee_schedules.html` | Report 2 |
| `app/templates/reports/event_type_breakdown.html` | Report 3 |
| `app/templates/reports/employee_workload.html` | Report 4 |
| `app/templates/reports/attendance.html` | Report 5 |
| `app/templates/reports/scheduling_coverage.html` | Report 6 |
| `app/templates/reports/time_off.html` | Report 7 |
| `app/static/css/pages/reports.css` | Shared report styles |

## Files to Modify

| File | Change |
|------|--------|
| `app/templates/base.html` | Add "Reports" sidebar link |
| `app/templates/unscheduled.html` | Remove Corporate Report button |
| `app/__init__.py` | Register `reports_bp` |

## Data Models Used

- Event, Employee, Schedule (reports 1-4, 6)
- EmployeeAttendance (report 5)
- EmployeeTimeOff (report 7)
- All accessed via `get_models()` factory pattern
