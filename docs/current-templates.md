# PCEventManager - Complete Page & Route Reference

> Auto-generated reference of every page/route in the application.
> Last updated: 2026-03-09

---

## Table of Contents

- [User-Facing Pages (HTML Templates)](#user-facing-pages-html-templates)
- [Dashboard Pages](#dashboard-pages)
- [Scheduling Pages](#scheduling-pages)
- [Auto-Scheduler Pages](#auto-scheduler-pages)
- [Employee Pages](#employee-pages)
- [Reports Pages](#reports-pages)
- [Printing Pages](#printing-pages)
- [Inventory Pages](#inventory-pages)
- [Help Pages](#help-pages)
- [Authentication Pages](#authentication-pages)
- [Admin / Settings Pages](#admin--settings-pages)
- [API Endpoints (JSON)](#api-endpoints-json)

---

## User-Facing Pages (HTML Templates)

### Main Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/` | *(redirect)* | Redirects to `/dashboard/command-center` |
| `/dashboard` | *(redirect)* | Redirects to `/dashboard/command-center` |
| `/events`, `/unscheduled` | `unscheduled.html` | Events list view with filtering by condition, type, date range, and smart search. Shows all unscheduled events that need employee assignments. |
| `/unreported-events` | `unreported_events.html` | Displays events from the last 2 weeks that are past their date but have no completion report filed. |
| `/calendar` | `calendar.html` | Monthly calendar view of scheduled events. Shows event counts per day with color-coded status. |
| `/schedule/daily/<date>` | `daily_view.html` | Full-screen daily schedule view showing all events for a specific date, organized by time blocks with role rotation assignments. |
| `/attendance`, `/attendance/<employee_id>` | `attendance.html` | Employee attendance calendar. Monthly grid view showing attendance status (present, absent, late, excused) for each employee. |
| `/employees/workload` | `workload_dashboard.html` | Employee workload analytics dashboard. Shows hours distribution, event counts, and workload balance across the team. |
| `/rotations/` | `rotations.html` | Role rotation assignments page. Configure which employees handle Juice Bar, Freezer, etc. on which days. |
| `/events/lost-demos` | `lost_demos.html` | Weekly lost demos tracker. Lists events that were scheduled but couldn't be completed, with confirmation workflow. |

---

### Dashboard Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/dashboard/command-center` | `dashboard/command_center.html` | **Main landing page.** Morning command center showing: deadline countdowns, quick stats bar, urgent unscheduled events, pending tasks/notes, employee issues, today's rotation assignments. |
| `/dashboard/daily-validation` | `dashboard/daily_validation.html` | Daily validation dashboard. Shows event counts by type, rotation assignments, unscheduled events, validation warnings/errors, and quick-action buttons for a selected date. |
| `/dashboard/weekly-validation` | `dashboard/weekly_validation.html` | Weekly validation overview. Summarizes scheduling coverage and issues across an entire week. |
| `/dashboard/fix-wizard` | `dashboard/fix_wizard.html` | Guided fix wizard for resolving scheduling issues. Walks through each problem one-by-one with suggested fixes. |
| `/dashboard/approved-events` | `dashboard/approved_events.html` | View of all approved/submitted schedule assignments. Shows events that have been confirmed with Crossmark API. |
| `/dashboard/employee-availability` | `dashboard/employee_availability.html` | Employee availability grid. Shows which employees are available on which days, accounting for time-off and weekly schedules. |
| `/dashboard/available-blocks` | `dashboard/available_blocks.html` | Available time blocks view. Shows open scheduling slots by day and time block. |
| `/dashboard/scan-out-checklist` | `dashboard/scan_out_checklist.html` | End-of-day scan-out checklist. Lists LIA (Limited In-store Assistance) events that need scan-out confirmation before the deadline. |

---

### Scheduling Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/schedule/<int:event_id>` | `schedule.html` | Individual event scheduling form. Shows event details, available employees, conflict warnings, and time selection for assigning an employee to an event. |

---

### Auto-Scheduler Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/auto-schedule/` | `auto_scheduler_main.html` | Main auto-scheduler page. Shows scheduling progress, run statistics, and a button to trigger the OR-Tools CP-SAT solver for automatic event-to-employee assignment. |
| `/auto-schedule/review` | `auto_schedule_review.html` | Proposal review page. Displays auto-scheduler results for human review before approval. Shows proposed assignments with conflict warnings and allows editing, approving, or rejecting individual or bulk proposals. |
| `/auto-schedule/history` | `scheduler_history.html` | Scheduler run history page. Lists all past auto-scheduler runs with timestamps, event counts, success rates, and links to view/export details. |

---

### Employee Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/employees` | `employees.html` | Employee management page. List of all employees (active/inactive) with ability to add, edit, delete, set weekly availability, and manage roles (Core, Juice Bar, Freezer). |
| `/employees/add` | `employees/add.html` | Add new employee form. |
| `/employees/import` | `employees/import_selection.html` | Import employees from MVRetail/Crossmark API. Shows available reps not yet in local database. |
| `/time-off` | `time_off_requests.html` | Time off request management. Calendar-style view for creating, viewing, and managing employee time-off requests. |
| `/employees/analytics` | `employee_analytics.html` | Employee scheduling analytics. Shows detailed per-employee metrics for a selected week: hours worked, event types, utilization rate. |

---

### Reports Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/reports/` | `reports/index.html` | Reports hub. Navigation page linking to all available reports. |
| `/reports/event-statistics` | `reports/event_statistics.html` | Event statistics report with date filtering. Counts, types, and status breakdown of events. |
| `/reports/employee-schedules` | `reports/employee_schedules.html` | Employee schedule details report. Per-employee breakdown of assigned events and hours. |
| `/reports/event-type-breakdown` | `reports/event_type_breakdown.html` | Event type breakdown report. Distribution of Core, Juice Bar, Freezer, and other event types. |
| `/reports/employee-workload` | `reports/employee_workload.html` | Employee workload report. Hours and event count analysis per employee over a date range. |
| `/reports/attendance` | `reports/attendance.html` | Attendance report. Monthly attendance records with present/absent/late statistics. |
| `/reports/scheduling-coverage` | `reports/scheduling_coverage.html` | Scheduling coverage report. Shows how well events are covered by date with gap analysis. |
| `/reports/time-off` | `reports/time_off.html` | Time off summary report. Monthly view of all time-off requests and their impact on scheduling. |

---

### Printing Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/printing/` | `printing.html` | Main printing hub. Provides options to generate and print: daily schedules, weekly schedules, employee schedules, event instructions (sales tools), EDR paperwork, bakery prep lists, and consolidated daily paperwork packets. |

---

### Inventory Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/inventory/` | `inventory/index.html` | Main inventory page. Shows supply categories, current stock levels, low-stock alerts, and quick-adjust controls. |
| `/inventory/orders` | `inventory/orders.html` | Purchase orders page. Lists orders grouped by status (draft, submitted, received, cancelled). |
| `/inventory/order/<order_id>` | `inventory/order_detail.html` | Single order detail page. Shows order items, quantities, and receiving workflow. |

---

### Help Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/help/` | `help/index.html` | Help home page with navigation to all guides. |
| `/help/getting-started` | `help/getting_started.html` | Getting started guide for new users. |
| `/help/walmart-credentials` | `help/walmart_credentials.html` | Guide for setting up Walmart Retail Link credentials. |
| `/help/employee-management` | `help/employee_management.html` | Employee management guide. |
| `/help/auto-scheduler` | `help/auto_scheduler.html` | Auto-scheduler explanation and usage guide. |
| `/help/review-approve` | `help/review_approve.html` | Review and approval workflow guide. |
| `/help/daily-validation` | `help/daily_validation.html` | Daily validation dashboard guide. |
| `/help/printing-reports` | `help/printing_reports.html` | Printing and reports guide. |
| `/help/edr-sync` | `help/edr_sync.html` | EDR sync and paperwork generation guide. |
| `/help/attendance` | `help/attendance.html` | Attendance tracking and time-off management guide. |
| `/help/workload-analytics` | `help/workload_analytics.html` | Workload analytics and performance dashboard guide. |

---

### Authentication Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/login` | `login.html` | Login page. Authenticates against Crossmark API. Redirects to daily view if already authenticated. |
| `/loading` | `auth/loading.html` | Database refresh loading page. Shows progress bar while syncing events from Crossmark API. |
| `/logout` | *(redirect)* | Clears Redis session and redirects to login. |

---

### Admin / Settings Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/settings` | `settings.html` | Settings page for credentials and configuration. Manage EDR credentials, AI assistant settings, auto-scheduler config. |
| `/event-times` | `event_times.html` | Consolidated event time settings. Configure default start/end times and allowed time ranges for each event type. |
| `/shift-blocks` | *(redirect)* | Redirects to `/event-times` (legacy URL). |
| `/sync/admin` | `sync_admin.html` | Sync administration interface. Manual sync triggers, API health checks, sync status monitoring. |
| `/api/test` | `api_tester.html` | API testing and request capture tool. For debugging API calls to Crossmark/MVRetail. |
| `/schedule-verification` | `schedule_verification.html` | Schedule verification page. Validates submitted schedules against business rules. |

---

### Shared Components (Included via Jinja2)

| Template | Used In | Description |
|----------|---------|-------------|
| `base.html` | All pages | Base layout template with nav, sidebar, footer, and common JS/CSS. |
| `components/ai_chat_bubble.html` | Multiple pages | Floating AI chat bubble for natural language commands. |
| `components/ai_panel.html` | Multiple pages | Expandable AI assistant panel with conversation history. |
| `components/floating_verification_widget.html` | Schedule pages | Floating widget showing real-time schedule validation status. |
| `components/modal_base.html` | Multiple pages | Reusable modal dialog base template. |
| `components/quick_note_widget.html` | Multiple pages | Quick note creation widget for adding tasks/reminders inline. |

---

## API Endpoints (JSON)

### Core Scheduling API (`/api/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/daily-summary/<date>` | GET | Event type counts and timeslot coverage for a date |
| `/api/daily-events/<date>` | GET | All events scheduled for a date |
| `/api/daily-employees/<date>` | GET | All employees scheduled for a date |
| `/api/daily-notes/<date>` | GET | Notes for a specific date |
| `/api/event-by-ref/<ref_num>` | GET | Get event by reference number |
| `/api/schedule/<int:schedule_id>` | GET | Schedule assignment details |
| `/api/schedule-event` | POST | Schedule a new event assignment |
| `/api/reschedule` | POST | Reschedule an event |
| `/api/event/<int:schedule_id>/reschedule` | POST | Reschedule with validation |
| `/api/event/<int:schedule_id>/change-employee` | POST | Change employee assignment |
| `/api/event/<int:schedule_id>/unschedule` | POST | Quick unschedule |
| `/api/unschedule/<int:schedule_id>` | DELETE | Unschedule an event |
| `/api/bulk-unschedule` | POST | Bulk unschedule multiple events |
| `/api/trade-events` | POST | Trade events between employees |
| `/api/bulk-reassign-supervisor-events` | POST | Bulk reassign supervisor events |
| `/api/rebalance-week` | POST | Rebalance schedule for a week |
| `/api/available_employees/<date>` | GET | Available employees for a date |
| `/api/available-employees` | GET | Available employees for scheduling |
| `/api/suggest-employees` | GET | AI-ranked employee suggestions for an event |
| `/api/validate-schedule` | POST | Real-time schedule validation |
| `/api/check_conflicts` | POST | Check scheduling conflicts |
| `/api/verify-schedule` | POST | Verify a schedule |
| `/api/validate_schedule_for_export` | GET | Validate schedule before export |
| `/api/event-default-time/<event_type>` | GET | Default time for event type |
| `/api/event-allowed-times/<event_type>` | GET | Allowed times for event type |
| `/api/event-time-settings` | GET | All event time settings |
| `/api/events/<int:event_id>/cannot-complete` | POST | Mark event as cannot complete |
| `/api/reissue-event` | POST | Reissue an event |
| `/api/event/<int:event_ref>/change-type` | POST | Change event type |
| `/api/event/<int:event_ref>/remove-type-override` | DELETE | Remove type override |
| `/api/universal_search` | GET | Universal search (events, employees, schedules) |
| `/api/workload` | GET | Employee workload data |
| `/api/employee-schedule-details` | GET | Detailed employee schedule info |
| `/api/schedule/print/<date>` | GET | Schedule data formatted for printing |
| `/api/calendar/day/<date>` | GET | Events for a specific calendar day |

### Export/Import API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/export/schedule` | GET | Export schedule to CSV/Excel |
| `/api/export/events` | GET | Export events to CSV/Excel |
| `/api/export/corporate-report` | GET | Export corporate report |
| `/api/import/events` | POST | Import events from file |
| `/api/import/scheduled` | POST | Import scheduled events from file |

### Employee API (`/api/employees/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/employees` | GET, POST | List or add employees |
| `/api/employees/<id>` | GET, POST, DELETE | Get, update, or delete employee |
| `/api/employees/active` | GET | Active employees for dropdowns |
| `/api/employees/<id>/availability` | GET, POST | Manage date-specific availability |
| `/api/employees/<id>/time_off` | GET, POST | Manage time off requests |
| `/api/employees/<id>/future-events` | GET | Future scheduled events for an employee |
| `/api/employees/terminate` | POST | Terminate employee and handle future events |
| `/api/time_off/<int:id>` | DELETE | Delete a time off request |
| `/api/populate_employees` | POST | Populate from JSON data |
| `/api/get_available_reps` | GET | Available reps from MVRetail API |
| `/api/lookup_employee_id` | POST | Lookup external employee ID |
| `/api/import_employees` | POST | Import employees from MVRetail |

### Attendance API (`/api/attendance/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/attendance` | POST | Create or update attendance record |
| `/api/attendance/<employee_id>` | GET | Get attendance records for employee |
| `/api/attendance/<int:record_id>` | GET, PUT, DELETE | Get, update, or delete specific record |
| `/api/attendance/date/<date>` | GET | All attendance for a date |
| `/api/attendance/month/<date>` | GET | Monthly attendance with statistics |
| `/api/attendance/scheduled-employees/<date>` | GET | Scheduled employees with attendance status |

### Auto-Scheduler API (`/auto-schedule/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/auto-schedule/run` | POST | Trigger auto-scheduler run |
| `/auto-schedule/status/<int:run_id>` | GET | Get run status |
| `/auto-schedule/approve` | POST | Approve all proposals |
| `/auto-schedule/approve-single/<int:id>` | POST | Approve single proposal |
| `/auto-schedule/reject` | POST | Reject all proposals |
| `/auto-schedule/mark-approved/<int:run_id>` | POST | Mark run as approved |
| `/auto-schedule/api/pending` | GET | Get pending schedule proposals |
| `/auto-schedule/api/pending/<int:id>` | PUT | Edit pending proposal |
| `/auto-schedule/api/pending/by-ref/<ref>` | DELETE | Delete pending by event ref |
| `/auto-schedule/api/dashboard-status` | GET | Pending run notification check |
| `/auto-schedule/api/verify/<int:run_id>` | GET | Verify pending run |
| `/auto-schedule/api/verify-date` | GET | Verify schedules for a date |
| `/auto-schedule/api/verify-date-range` | GET | Verify schedules for date range |
| `/auto-schedule/api/history/<int:run_id>` | GET | Run history data |
| `/auto-schedule/api/history/<int:run_id>/export` | GET | Export run history as CSV |
| `/auto-schedule/api/review/export` | GET | Export review proposals as CSV |

### Auto-Scheduler Settings API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/auto-scheduler/settings` | GET, PUT | Get or update auto-scheduler config |
| `/api/events/<int:id>/scheduling-override` | GET, DELETE | Get or delete event scheduling override |
| `/api/events/scheduling-override` | POST | Set event scheduling override |

### Availability Overrides API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/availability-overrides` | POST | Create temporary availability override |
| `/api/availability-overrides/<employee_id>` | GET | Get overrides for employee |
| `/api/availability-overrides/<int:id>` | PUT, DELETE | Update or delete override |

### Notes & Tasks API (`/api/notes/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/notes/` | GET, POST | List or create notes/tasks |
| `/api/notes/<int:id>` | GET, PUT, DELETE | Get, update, or delete note |
| `/api/notes/<int:id>/complete` | POST | Mark note as complete |
| `/api/notes/<int:id>/reopen` | POST | Reopen a completed note |
| `/api/notes/summary` | GET | Note counts by status/type |
| `/api/notes/employee/<id>` | GET | Notes for an employee |
| `/api/notes/event/<int:ref>` | GET | Notes for an event |
| `/api/notes/notifications/pending` | GET | Notes needing browser notifications |
| `/api/notes/<int:id>/notification-sent` | POST | Mark notification as sent |
| `/api/notes/reminders` | GET, POST | List or create recurring reminders |
| `/api/notes/reminders/<int:id>` | PUT, DELETE | Update or delete reminder |
| `/api/notes/reminders/trigger` | POST | Trigger due reminders |

### Notifications API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/notifications` | GET | Get all current notifications (unscheduled events, unreported events, overdue notes, etc.) |

### Company Holidays API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/company-holidays/` | GET, POST | List or create holidays |
| `/api/company-holidays/<int:id>` | GET, PUT, DELETE | Get, update, or delete holiday |
| `/api/company-holidays/check` | GET | Check if date is a holiday |
| `/api/company-holidays/upcoming` | GET | Upcoming holidays |
| `/api/company-holidays/range` | GET | Holidays in date range |

### Locked Days API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/locked-days` | GET, POST | List locked days or lock a date |
| `/api/locked-days/<date>` | GET, DELETE | Check or unlock a date |
| `/api/locked-days/check-range` | POST | Check which days in range are locked |

### Shift Blocks / Event Times API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/shift-blocks/` | GET, PUT | Get or update all 8 shift blocks |
| `/api/shift-blocks/<int:n>` | GET, PUT | Get or update specific shift block |
| `/api/shift-blocks/initialize` | POST | Initialize from environment variables |
| `/api/event-times` | GET | Get all event time settings |

### Paperwork Templates API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/paperwork-templates/` | GET, POST | List or create templates |
| `/api/paperwork-templates/<int:id>` | PUT, DELETE | Update or delete template |
| `/api/paperwork-templates/reorder` | POST | Reorder templates |
| `/api/paperwork-templates/upload` | POST | Upload template PDF file |

### Lost Demos API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/lost-demos` | GET | List lost demos for a week |
| `/api/lost-demos/<ref>/confirm` | POST, DELETE | Confirm or undo lost demo |
| `/api/lost-demos/confirmed-refs` | GET | List confirmed lost event refs |
| `/api/lost-demos/export` | GET | Export lost demos as CSV |

### Rotation API (`/rotations/api/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/rotations/api/rotations` | GET, POST | Get or save rotation assignments |
| `/rotations/api/exceptions` | GET, POST | Get or add rotation exceptions |
| `/rotations/api/exceptions/<id>` | DELETE | Delete rotation exception |

### Dashboard Validation API

| Route | Methods | Description |
|-------|---------|-------------|
| `/dashboard/api/command-center` | GET | Command center data (AJAX refresh) |
| `/dashboard/api/validation-summary` | GET | Validation summary data |
| `/dashboard/api/weekly-validation` | GET | Weekly validation data |
| `/dashboard/api/validation/ignore` | POST | Ignore a validation warning |
| `/dashboard/api/validation/unignore` | POST | Un-ignore a validation warning |
| `/dashboard/api/validation/ignored` | GET | Get list of ignored validations |
| `/dashboard/api/validation/assign-supervisor` | POST | Auto-assign supervisor to Core event |
| `/dashboard/api/fix-wizard/issues` | GET | Get fix wizard issues list |
| `/dashboard/api/fix-wizard/apply` | POST | Apply a fix wizard suggestion |
| `/dashboard/api/fix-wizard/skip` | POST | Skip a fix wizard issue |

### Printing API (`/printing/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/printing/employees` | GET | Employee list for dropdowns |
| `/printing/daily-schedule` | GET | Daily schedule data |
| `/printing/weekly-schedule` | GET | Weekly schedule (Sun-Sat) |
| `/printing/employee-schedule` | GET | Employee bi-weekly schedule |
| `/printing/event-instructions` | GET | Event instructions / sales tool URLs |
| `/printing/event-instructions/merge` | POST | Merge instruction PDFs |
| `/printing/daily-item-list` | GET | Daily item list |
| `/printing/core-events-count` | GET | Core events count for a date |
| `/printing/complete-paperwork` | POST | Generate consolidated daily PDF |
| `/printing/event-paperwork` | POST | Generate single event paperwork |
| `/printing/bakery-prep-list` | GET | Bakery prep items |
| `/printing/freeosk-manual-test` | POST | Test FreeOSK barcode scanner |
| `/printing/edr/request-mfa` | POST | Request Walmart EDR MFA code |
| `/printing/edr/auth-status` | GET | Check EDR auth status |
| `/printing/edr/authenticate` | POST | Authenticate with EDR |
| `/printing/edr/batch-download` | POST | Download/merge EDR PDFs |
| `/printing/edr/daily-items-list` | POST | Generate daily items list from EDRs |

### Inventory API (`/inventory/api/...`)

| Route | Methods | Description |
|-------|---------|-------------|
| `/inventory/api/categories` | GET, POST | List or create categories |
| `/inventory/api/categories/<id>` | PUT, DELETE | Update or delete category |
| `/inventory/api/supplies` | GET, POST | List or create supplies |
| `/inventory/api/supplies/<id>` | GET, PUT, DELETE | Get, update, or soft-delete supply |
| `/inventory/api/supplies/<id>/adjust` | POST | Adjust supply quantity |
| `/inventory/api/supplies/<id>/set-quantity` | POST | Set exact quantity |
| `/inventory/api/supplies/<id>/history` | GET | Supply adjustment history |
| `/inventory/api/summary` | GET | Inventory summary |
| `/inventory/api/low-stock` | GET | Low stock items |
| `/inventory/api/notifications` | GET | Inventory notifications |
| `/inventory/api/orders` | GET, POST | List or create orders |
| `/inventory/api/orders/<id>` | GET, DELETE | Get or delete order |
| `/inventory/api/orders/<id>/items` | POST | Add item to order |
| `/inventory/api/orders/<id>/items/<item_id>` | DELETE | Remove item from order |
| `/inventory/api/orders/<id>/items/<item_id>/quantity` | PUT | Update item quantity |
| `/inventory/api/orders/<id>/submit` | POST | Submit draft order |
| `/inventory/api/orders/<id>/receive-item/<item_id>` | POST | Receive single item |
| `/inventory/api/orders/<id>/receive-all` | POST | Receive all items |
| `/inventory/api/orders/<id>/cancel` | POST | Cancel order |
| `/inventory/api/orders/create-reorder` | POST | Create order from low-stock |
| `/inventory/api/reminders` | GET, POST | List or create reminders |
| `/inventory/api/reminders/due` | GET | Get due/overdue reminders |
| `/inventory/api/reminders/<id>/complete` | POST | Mark reminder complete |
| `/inventory/api/reminders/<id>` | DELETE | Delete reminder |

### Sync / EDR API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/refresh/database` | POST | Full database refresh from Crossmark API |
| `/api/refresh/status` | GET | Database refresh progress |
| `/api/sync/health` | GET | Sync system health check |
| `/api/sync/trigger` | POST | Trigger full sync |
| `/api/sync/status` | GET | Sync status overview |
| `/api/sync/employees` | POST | Sync employees from API |
| `/api/sync/retaillink` | POST | Sync EDR data from Walmart Retail Link |
| `/api/sync/mvretail` | POST | Sync from MVRetail |
| `/api/sync/status/retaillink` | GET | Retail Link cache status |
| `/api/webhook/schedule_update` | POST | Webhook for external schedule updates |
| `/api/edr/request_code` | POST | Request EDR MFA code |
| `/api/edr/authenticate` | POST | EDR MFA authenticate |
| `/api/edr/sync-cache` | POST | Sync EDR cache |
| `/api/edr/cache-status` | GET | EDR cache status |

### Print Paperwork API (Admin)

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/print_paperwork/<type>` | GET | Print paperwork by type (daily, sales tools, EDR) |
| `/api/print_paperwork_by_date/<date>` | GET | Print daily paperwork for date |
| `/api/print_salestools_by_date/<date>` | GET | Print sales tools for date |
| `/api/print_event_paperwork/<int:event_id>` | GET | Print single event paperwork |
| `/api/print_weekly_summary/<week_start>` | GET | Print weekly schedule summary PDF |
| `/api/print_employee_schedule/<int:id>/<week>` | GET | Print employee weekly schedule PDF |
| `/api/daily_paperwork/request_mfa` | POST | Request MFA for paperwork generation |
| `/api/daily_paperwork/generate` | POST | Generate daily paperwork |
| `/api/edr_reports/request_mfa` | POST | Request MFA for EDR reports |
| `/api/edr_reports/generate_by_date` | POST | Generate EDR reports by date |

### Settings API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/settings/edr` | POST | Save Retail Link EDR credentials |
| `/api/settings/ai` | POST | Save AI assistant settings |
| `/api/settings/auto-scheduler` | POST | Save auto-scheduler config |
| `/api/settings/event-times` | POST | Save event time settings |

### Auth API

| Route | Methods | Description |
|-------|---------|-------------|
| `/login` | POST | Handle login (rate limited: 5/min) |
| `/api/session-info` | GET | Session info including event times config status |
| `/api/auth/diag` | GET | Redis connection diagnostic |
| `/api/auth/status` | GET | Auth status and timeout info |
| `/api/session/heartbeat` | POST | Keep session alive |
| `/loading/progress/<task_id>` | GET | SSE stream for DB refresh progress |
| `/loading/start/<task_id>` | POST | Start DB refresh process |

### AI Assistant API

| Route | Methods | Description |
|-------|---------|-------------|
| `/api/ai/query` | POST | Process natural language query |
| `/api/ai/confirm` | POST | Confirm pending AI action |
| `/api/ai/suggestions` | GET | Get suggested queries |
| `/api/ai/health` | GET | AI assistant health check |
| `/api/ai/current-model` | GET | Currently configured AI model |

### Health Check API

| Route | Methods | Description |
|-------|---------|-------------|
| `/health/ping` | GET | Basic connectivity check |
| `/health/live` | GET | Container liveness probe |
| `/health/ready` | GET | Readiness probe (checks dependencies) |
| `/health/status` | GET | Detailed app status and metrics |
| `/health/metrics` | GET | Prometheus-compatible metrics |

### Reports Export API

| Route | Methods | Description |
|-------|---------|-------------|
| `/reports/event-statistics/export` | GET | Export event statistics CSV |
| `/reports/employee-schedules/export` | GET | Export employee schedules CSV |
| `/reports/event-type-breakdown/export` | GET | Export event type breakdown CSV |
| `/reports/employee-workload/export` | GET | Export employee workload CSV |
| `/reports/attendance/export` | GET | Export attendance CSV |
| `/reports/scheduling-coverage/export` | GET | Export scheduling coverage CSV |
| `/reports/time-off/export` | GET | Export time off summary CSV |

---

## Summary

| Category | Count |
|----------|-------|
| **User-facing pages (HTML)** | ~45 |
| **Shared components** | 5 |
| **JSON API endpoints** | ~190 |
| **PDF generation endpoints** | ~12 |
| **CSV export endpoints** | ~12 |
| **SSE streaming endpoints** | 1 |
| **Health check endpoints** | 5 |
| **Total routes** | **~270** |
