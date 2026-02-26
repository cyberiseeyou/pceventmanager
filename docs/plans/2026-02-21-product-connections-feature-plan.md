# Product Connections Scheduler — Feature Plan for Implementation

This document is a comprehensive feature plan for improving pceventmanager.site. Each item includes what to change, why, and implementation guidance. Items are grouped by area and ordered by priority within each group.

---

## 1. DASHBOARD & HOME PAGE

### 1.1 — Create a Real Dashboard Homepage
**Current behavior:** The Home link (`/`) redirects to today's daily schedule. There is no overview page.

**Why change:** A manager logging in each morning has no single screen that shows the state of the operation. They must visit multiple pages (daily schedule, notifications, weekly validation, unscheduled events, inventory) to piece together what needs attention. Every other workflow starts with "figure out what's urgent," and the app doesn't help with that first step.

**Implementation:**
Build a new `/dashboard` route that becomes the default Home page. It should surface:
- Today's quick stats: total events, staffed vs. unstaffed count, attendance completion percentage
- Critical alerts pulled from the notification system: urgent unscheduled events, overdue events, low-stock supply alerts
- A "Today's Priorities" action list: unrecorded attendance, events due today that are unscheduled, unreported events
- Quick-link cards to the most common daily actions: "Print Today's Paperwork," "Record Attendance," "Verify Schedule," "View Unscheduled Events"
- A mini weekly outlook showing staffing coverage for the next 7 days (similar to the weekly validation summary)

The existing daily schedule page stays at `/schedule/daily/:date` — the dashboard links into it rather than replacing it.

---

## 2. NAVIGATION

### 2.1 — Restructure Navigation with Sidebar
**Current behavior:** The top nav has two dropdown menus (Scheduling with 7 items, Team with 4 items), direct links (Home, Printing), utility buttons (Refresh Database, AI, Notifications), and a user dropdown hiding 5 more links (Help, Settings, Event Times, Rotations, Logout). That's 20+ navigation targets spread across dropdowns, direct links, icon buttons, and a user menu.

**Why change:** The navigation cognitive load is high. The Scheduling dropdown mixes daily operations (Calendar, Events) with admin tasks (Schedule Verification, Auto-Scheduler). Important items like "Left in Approved" and "Weekly Validation" are buried inside a dropdown alongside unrelated pages. Users can't see all options without clicking through menus.

**Implementation:**
Replace the top dropdown navigation with a collapsible sidebar for desktop. Group items into clear categories:
- **Schedule:** Calendar, Daily View, Auto-Scheduler
- **Events:** All Events, Unreported Events, Left in Approved
- **Team:** Employees, Attendance, Time Off, Analytics
- **Admin/Settings:** System Settings, Event Time Settings, Rotation Management, Inventory
- **Tools:** Printing, Schedule Verification, Weekly Validation

Move "Refresh Database" into the Settings/Admin section — it's a rare, potentially destructive action that shouldn't sit in the primary nav next to daily-use items. Keep Notifications and User menu in the top bar since they're global utilities.

On mobile, the sidebar becomes a slide-out hamburger menu (the toggle already exists in the DOM as `ref_6`/`ref_7`).

### 2.2 — Move Refresh Database to Admin Section
**Current behavior:** "Refresh Database" sits in the top nav bar as a prominent button alongside daily navigation items.

**Why change:** This action clears all existing events and re-fetches from CrossMark. It's destructive, rarely needed, and should not be one accidental click away from daily-use navigation. Its current placement gives it equal visual weight to "Scheduling" and "Team."

**Implementation:**
Remove the Refresh Database button from the top nav bar. Place it in the Settings page or a new Admin section. Add a confirmation step (which already exists as a dialog, so just move the entry point).

---

## 3. DAILY SCHEDULE PAGE

### 3.1 — Add Employee Filter to Scheduled Events Section
**Current behavior:** The Scheduled Events section shows all events for the day grouped by type (Juicer, Core & Supervisor, Freeosk, Digital, Other). You can filter by event type but not by employee.

**Why change (Scenario #1):** When an employee calls off, the manager needs to quickly find all of that employee's events. Currently they must visually scan through 15+ event cards to find the right ones. This is the most time-critical workflow in the app — a call-off happens in real-time and decisions must be made fast.

**Implementation:**
Add an employee dropdown filter alongside the existing Type filter in the Scheduled Events toolbar. When an employee is selected, show only their event cards. This filter should also work in combination with the type filter. The employee list should be populated from the day's scheduled employees.

### 3.2 — Add Event Urgency Indicators (Days Remaining)
**Current behavior:** Event cards show a date range (e.g., "02/21/2026 - 02/22/2026") but there's no computed indicator showing urgency.

**Why change (Scenario #1):** When deciding which events to prioritize during a call-off, the manager must mentally calculate how many days remain for each event. The date range tells you when the event window closes, but under pressure, a badge like "DUE TODAY" vs. "5 days left" is far faster to process. This is the core decision point in the call-off workflow and it's currently entirely manual.

**Implementation:**
Calculate `days_remaining = event_end_date - today` and display a badge on each event card:
- 0 days remaining (expires today): red badge "DUE TODAY"
- 1 day remaining: orange badge "1 DAY LEFT"
- 2-3 days: yellow badge with count
- 4+ days: green/neutral badge with count

Place this badge prominently in the card header, near the employee name.

### 3.3 — Add Call-Off Wizard
**Current behavior:** When marking an employee as "Called-In" in the attendance section, nothing else happens. The manager must then manually scroll down, find the employee's events, and handle each one individually.

**Why change (Scenario #1):** The call-off flow is the most common emergency workflow, and it currently requires the manager to mentally track which steps they've completed across a long scrolling page. A structured flow reduces errors and saves time when the manager is likely also dealing with the physical store disruption.

**Implementation:**
When a "Called-In" or "No-Call-No-Show" attendance status is recorded, show a prompt: "Would you like to manage [Employee]'s events for today?" If yes, open a focused modal or side panel that:
1. Lists only that employee's events for the day
2. Shows the urgency badge (days remaining) for each
3. For each event, provides action buttons: "Reassign to..." (with employee dropdown), "Reschedule to..." (date picker), or "Unschedule"
4. Shows which other employees are available and what their current load is
5. Highlights trade candidates — employees whose events have more days remaining

### 3.4 — Use Tabbed or Collapsible Layout for Daily Sections
**Current behavior:** The daily schedule page stacks four sections vertically: Events Summary, Core Timeslot Coverage, Employee Attendance, and Scheduled Events. On a day with 15 events, this page requires extensive scrolling. You lose context of the summary while scrolling through event cards.

**Why change:** The most common daily tasks involve either the attendance section or the events section, rarely both at the same time. Stacking them forces unnecessary scrolling. The Events Summary at the top is useful context but disappears from view immediately.

**Implementation:**
Keep the page header (date, navigation arrows, role assignments, Lock Day, Reassign Supervisor Events) pinned. Make the Events Summary a compact horizontal stat bar rather than a full section. Below that, use tabs: "Events" (showing Scheduled Events with card/list toggle and filters), "Attendance" (showing attendance list), and "Coverage" (showing Core Timeslot Coverage). Alternatively, on wide screens (>1200px), use a two-column layout: attendance on the left, events on the right.

### 3.5 — Make List View the Default for Event Cards
**Current behavior:** Card view is the default. A Card/List toggle exists but defaults to cards.

**Why change:** Card view is visually rich but takes up significant space — each card is ~150px tall. On a day with 15 events, that's 2250px of scrolling in the events section alone. List view is more scannable for day-of operations where you need to quickly check status and assignment across many events. Card view is useful for focusing on a single event's details.

**Implementation:**
Switch the default to List view. Persist the user's preference in localStorage so it remembers across sessions.

### 3.6 — Display 6-Digit Event Numbers on All Event Cards
**Current behavior:** Core event names include a 6-digit event number at the start (e.g., "620662-LKD-MMCL-CF-..."). Juicer, Freeosk, Digital, and Other events do NOT — their names start with date formats like "02-21 8HR-ES1-..." with no 6-digit number.

**Why change (Scenario #6):** At end of day, every event needs its 6-digit number for scan-out. Core events have it visible in the name, but Juicers and others don't. This forces the manager into the Walmart authentication flow on the Left in Approved page just to get Juicer event numbers. If the session times out (which happens frequently since scan-out coincides with store closing duties), the numbers are lost.

**Implementation:**
Add a dedicated, prominently displayed "Event #" field to every event card, separate from the event name string. For events where the number is embedded in the name, parse it out. For events where the number comes from Walmart's Left in Approved system, store it in the local database when synced (see 3.7). Display it as a bold, easily copyable field on the card.

### 3.7 — Persist Synced Event Numbers Across Sessions
**Current behavior:** Event numbers fetched via "Sync Event Numbers" on the Left in Approved page are only available during the active Walmart authentication session. If the session expires, the numbers are gone.

**Why change (Scenario #6):** This is a critical end-of-day workflow that fails when the manager gets interrupted (which is common at closing time). The numbers don't change — once an event has a 6-digit number, it's permanent. There's no reason for them to be ephemeral.

**Implementation:**
When the "Sync Event Numbers" action fetches event numbers from Walmart, persist them into the local events database. Store them as a field on the event record. Once stored, they should display on event cards everywhere in the app (daily schedule, All Events page, etc.) without requiring re-authentication. Only re-sync when explicitly requested or during database refresh.

### 3.8 — Add Scan-Out Checklist View
**Current behavior:** There is no dedicated scan-out view. Managers scroll through the daily schedule copying event numbers by hand.

**Why change (Scenario #6):** Scan-out is a repetitive end-of-day task with a strict 6 PM deadline (shown on the Left in Approved page). The current daily schedule view has much more information than needed for scan-out, creating noise. A purpose-built view would make this faster and less error-prone.

**Implementation:**
Add a "Scan-Out Checklist" view accessible from the daily schedule page (a button or tab). It should show a minimal table: event number, product name, assigned employee, and a checkbox. As each event is scanned out, the checkbox marks it done. Persist checkbox state so interruptions don't lose progress. This view should be printable.

---

## 4. CALENDAR

### 4.1 — Fix "undefined" Juicer Count Labels
**Current behavior:** Across nearly every day on the calendar, the Juicer badge shows "J|1 undefined" instead of a clean count.

**Why change:** This looks like a data or rendering bug. It appears on almost every day cell and undermines trust in the application's reliability. If users can't trust the calendar overview, they won't use it.

**Implementation:**
Debug the Juicer event count rendering in the calendar. The issue is likely a missing label/category mapping for Juicer event subtypes. The badge should show "J|1" or "J|2" cleanly like Core shows "C|5."

### 4.2 — Add Hover Tooltips to Calendar Day Cells
**Current behavior:** Calendar days show small colored badges (C|5, S|4, J|1, F|1, D|3, O|1) and a warning icon for unscheduled events. You must click into the day to see details.

**Why change:** The badges are dense and hard to read at a glance. A tooltip on hover would let managers quickly scan the week without clicking into each day.

**Implementation:**
Add a hover tooltip to each day cell showing: total events, breakdown by type, how many are unscheduled, how many are past due, and which employees are scheduled. This is a lightweight enhancement that dramatically improves the calendar's utility for weekly planning.

### 4.3 — Add Week View Mode
**Current behavior:** The calendar only has a month view. The daily schedule shows one day at a time.

**Why change (Scenario #4):** When dealing with cancellations or rescheduling across a whole week, the month view is too zoomed out (you can't see event details) and the daily view is too zoomed in (you can only see one day). A week view would show 7 days of event assignments side by side, making cross-day rescheduling decisions much easier.

**Implementation:**
Add a Week view toggle to the calendar page. Display 7 columns (one per day) with a condensed list of events per day. Each event row shows: employee, event type badge, time, and urgency badge. Support drag-and-drop between days for quick rescheduling.

---

## 5. ALL EVENTS PAGE

### 5.1 — Add Date Range Picker UI
**Current behavior:** Date filtering requires typing search syntax like `s:02/21/2026 to 02/28/2026`. The syntax guide is shown in small text below the search bar.

**Why change (Scenario #3):** The search syntax is powerful but not discoverable. New users won't know about `s:`, `sc:`, `d:` prefixes. Even experienced users make typos in date format. A visual date picker is faster and less error-prone for the most common filtering task.

**Implementation:**
Add two date input fields ("From" and "To") next to the search bar. These populate the search with the correct syntax under the hood. Keep the text search for advanced queries but make date filtering accessible without memorizing syntax. Also add a "Due Date" filter (using the `d:` prefix) as a separate date range picker, since "events starting this week" and "events due this week" are different questions.

### 5.2 — Add Counts to Status Tabs
**Current behavior:** The tabs (All, Scheduled, Unscheduled, Submitted, Paused, Reissued) show labels but no counts.

**Why change:** Knowing there are 32 unscheduled events vs. 3 matters for prioritization. Currently you must click into each tab to see how many items are there.

**Implementation:**
Show a count badge on each tab: "Unscheduled (32)", "Paused (0)", etc. Update counts dynamically when filters are applied.

### 5.3 — Default to Current/Upcoming Events
**Current behavior:** The All Events tab shows events starting from the oldest (January 2026).

**Why change:** Past events are rarely the focus. Managers almost always want to see current and upcoming events. Starting from the oldest requires scrolling past weeks of history.

**Implementation:**
Default the event list to showing events from today onward, sorted by start date ascending. Add a "Show Past Events" toggle or a "Past" tab for historical access.

### 5.4 — Add Sort Controls
**Current behavior:** Events appear in a fixed order with no visible sort options.

**Why change:** Different tasks require different orderings. When triaging call-offs, you want to sort by urgency (due date). When reviewing an employee's workload, you want to sort by employee. When checking status, you want to sort by status.

**Implementation:**
Add a "Sort by" dropdown with options: Date (default), Due Date, Employee, Event Type, Status. Support ascending/descending toggle.

### 5.5 — Add Bulk Actions (Multi-Select)
**Current behavior:** Each event can only be acted on individually — one Unschedule, one Reschedule, one Change Employee at a time.

**Why change (Scenario #4):** When many events are cancelled across a week, unscheduling 20 events one-by-one across multiple daily pages is extremely tedious. There is no multi-select or bulk action capability anywhere in the app. This is the most time-consuming workflow gap in the entire application.

**Implementation:**
Add checkboxes to each event row (on the All Events page and on the daily schedule's event cards). When one or more events are selected, show a floating bulk action toolbar with: "Bulk Unschedule," "Bulk Change Employee," "Bulk Reschedule." For Bulk Unschedule, confirm once and unschedule all selected. For Bulk Change Employee, show an employee picker that applies to all selected. Add a "Select All" checkbox in the header. This should work across filtered results — e.g., filter to a date range, select all, bulk unschedule.

### 5.6 — Add "Cannot Complete" / "Skip" Status
**Current behavior:** Events have statuses: Scheduled, Unscheduled, Submitted, Paused, Reissued. There is no way to explicitly mark an event as "will not be completed."

**Why change (Scenario #3):** "Unscheduled" means "hasn't been assigned yet," which is different from "we've decided we can't do this." When generating a report for corporate about events that won't get done, the manager needs to make a deliberate decision and mark each event. Currently, unscheduled events and deliberately-skipped events look identical.

**Implementation:**
Add a new status: "Cannot Complete" or "Skipped." Add it as an action option on event cards ("Mark as Cannot Complete"). Require a reason selection (Insufficient Staff, Cancelled, Product Unavailable, Other). Add a "Cannot Complete" tab to the Events page. The Export CSV should include this status and reason for corporate reporting.

### 5.7 — Add Corporate Report Export
**Current behavior:** Export CSV exports the raw event list based on the current filter.

**Why change (Scenario #3):** Corporate needs a clean, formatted report of events that won't be completed, grouped by week. The raw CSV export requires manual formatting and doesn't include context like reason codes or staffing notes.

**Implementation:**
Add a "Generate Corporate Report" action that produces a formatted export (PDF and/or CSV) for a selected date range. Group events by week. Include: event name, event number, date, status, assigned employee (if any), reason for non-completion, days the event was available. Include a summary header with total events, completion rate, and breakdown by reason.

---

## 6. EMPLOYEE MANAGEMENT

### 6.1 — Add Date-Specific Availability Overrides
**Current behavior:** Employee availability is a static weekly grid (Mon-Sun checkboxes). The only date-specific feature is Time Off Requests (which marks someone as unavailable).

**Why change (Scenario #2):** Employees frequently have one-off availability that differs from their regular pattern. Diane is normally off Tuesdays but can work this Tuesday. Currently there's no way to represent this without temporarily changing her permanent weekly availability (and remembering to change it back). The auto-scheduler ignores her for Tuesdays, and the Weekly Validation flags her as a critical error if manually scheduled.

**Why this is already partially done:** The `EmployeeAvailabilityOverride` model already exists (see `app/models/availability.py`). The `WeeklyPlanningService` and `ConstraintValidator` already check overrides. What's missing is a **UI** to create/view/delete overrides — the model exists but there's no way for a user to use it.

**Implementation:**
Add an "Availability Overrides" section to the employee management system. This could live as a second section on the Time Off Requests page (rename the page to "Availability Management") or as a tab within each employee's edit modal. The UI for adding an override: select employee, select date range, toggle weekday availability, add optional reason.

### 6.2 — Add Search/Filter to Employee List
**Current behavior:** The Employee Management page shows all employees as large cards with no search or filter capability.

**Why change:** With 11 employees, it's manageable but still requires scrolling. As teams grow, finding a specific employee becomes tedious. There's also no way to filter by role (Event Specialist, Lead, Juicer Barista).

**Implementation:**
Add a search bar at the top of the Employees page that filters by name or ID. Add a role filter dropdown. Consider adding a compact table/list view toggle alongside the existing card view.

### 6.3 — Move Delete Button to Overflow Menu
**Current behavior:** Edit, Deactivate, and Delete buttons sit side by side on each employee card.

**Why change:** Delete is a destructive, irreversible action positioned with the same visual weight as Edit. Accidental clicks are a real risk, especially on mobile. Deactivate exists as the safe alternative and should be the prominent option.

**Implementation:**
Remove the Delete button from the visible card layout. Move it into an overflow/more menu or place it at the bottom of the Edit modal with a confirmation step. Keep Edit and Deactivate as the visible primary actions.

---

## 7. NOTES & COMMUNICATION

### 7.1 — Link Notes to Specific Events and Employees
**Current behavior:** Quick Notes are free-text with a type category (Task, Employee Note, Event Note, Follow-up, Management) but no actual linkage to specific event or employee records.

**Why change (Scenario #5):** When a manager sees crucial information about a future event, they can create a note, but it floats disconnected from the event it's about. A week later when that event comes up, the note doesn't surface on the event card or the daily schedule. The manager has to remember to check the Quick Notes panel, which is a floating widget with no contextual awareness.

**Implementation:**
Add optional "Link to Employee" and "Link to Event" dropdowns in the Quick Notes creation form. When an employee is linked, show a note indicator (badge/icon) on that employee's card in the Employee Management page and on the daily schedule's attendance row. When an event is linked, show a note indicator on the event card wherever it appears (daily schedule, All Events page). Clicking the indicator expands to show the note text. Also add an "Add Note" option to the event card's "More" menu and to the attendance row's dropdown — this pre-fills the link automatically.

### 7.2 — Surface Contextual Notes on Daily Schedule
**Current behavior:** Notes are only visible in the Quick Notes floating panel. They don't appear anywhere else.

**Why change (Scenario #5):** The whole point of leaving a note about an event is so that the right person sees it at the right time. If the note about Shannon's event next Tuesday only lives in a floating panel, it will almost certainly be missed.

**Implementation:**
On the daily schedule page, scan for notes linked to any event or employee on that day. If notes exist, show a small banner or badge: "3 notes for today's events" with an expandable section. On individual event cards, if a linked note exists, show a note icon in the card header. On attendance rows, if an employee note exists, show the icon next to their name.

### 7.3 — Add Reminders/Notifications for Notes
**Current behavior:** Notes are passive — they sit in the "Pending" tab until manually checked.

**Why change (Scenario #5):** A note about a future event is useless if nobody sees it on the day it matters. The Due Date field exists on notes but doesn't trigger any notification.

**Implementation:**
When a note has a due date, trigger it as a notification in the Notifications bell on that date. Include it in the dashboard's daily priorities section. Optionally, if the note is linked to an event on a specific day, auto-set the reminder to that event's scheduled date.

---

## 8. VERIFICATION & VALIDATION

### 8.1 — Consolidate Duplicate Verification Features
**Current behavior:** Three separate verification features exist: "Schedule Verification" page (`/schedule-verification`), "Weekly Validation" page (`/dashboard/weekly-validation`), and a "Schedule Verification" panel embedded in the AI Assistant floating widget. They serve overlapping purposes and live in different locations.

**Why change:** Having three verification tools creates confusion about which one to use. The Weekly Validation page is the most actionable — it shows issues by day with Reassign/Unschedule/Ignore buttons. The standalone Schedule Verification page is minimal (just a date picker and a verify button). The AI widget version is a duplicate.

**Implementation:**
Make Weekly Validation the primary verification tool. Enhance it to also handle single-day verification (currently it only does week-at-a-time). Remove or redirect the standalone Schedule Verification page to Weekly Validation. Remove the verification panel from the AI Assistant widget. Keep the Weekly Validation link in the main nav and add a "Verify Today" shortcut button on the daily schedule page that jumps to the current week's validation view filtered to today.

---

## 9. AUTO-SCHEDULER

### 9.1 — Add Emergency Mode (Short Buffer)
**Current behavior:** The auto-scheduler has a hard 3-day buffer and will not schedule anything within the next 3 days.

**Why change (Scenario #4):** When mass cancellations happen, the most urgent events to fill are within the next 1-3 days. The auto-scheduler explicitly refuses to help with these, forcing all urgent rescheduling to be done manually. The buffer makes sense as a default safety measure but should be overridable for emergencies.

**Implementation:**
Add an "Emergency Mode" toggle on the Auto-Scheduler page. When enabled, allow scheduling events within 0-3 days. Show a warning: "Emergency mode will schedule events within the next 3 days. These assignments should be reviewed manually." Log when emergency mode is used. Consider requiring a confirmation step.

---

## 10. FLOATING WIDGETS

### 10.1 — Consolidate Floating Tools
**Current behavior:** Up to four floating elements compete for the bottom-right corner: AI Assistant bubble, Claude extension bubble (with notification badge), Schedule Verification button, and Quick Notes button. They overlap and create visual clutter.

**Why change:** The bottom-right corner is congested. On smaller screens or when scrolled to certain positions, these widgets overlap content or each other. The user has to manage multiple floating panels.

**Implementation:**
Combine the AI Assistant and Quick Notes into a single floating panel with tabs. Remove the Schedule Verification floating button (moved to the main nav per 8.1). The single floating button opens a panel with tabs: "Chat" (AI Assistant), "Notes" (Quick Notes), and optionally "Verify" (quick verification). This reduces the floating buttons to one (plus the Claude extension which is external).

---

## 11. DATA CONSISTENCY

### 11.1 — Standardize Employee Name Casing
**Current behavior:** Some employee names appear in ALL CAPS (DIANE CARR, SHANNON FIELDS), while others are in mixed case (Mat Conder, Maxine SPALLONE). This inconsistency appears throughout the app.

**Why change:** Inconsistent casing looks unprofessional and can cause confusion. It likely stems from different data sources (some imported from CrossMark in uppercase, some entered manually in mixed case).

**Implementation:**
Normalize all employee names to Title Case (Diane Carr, Mat Conder) on display. Store original case in the database if needed for integration matching, but render consistently everywhere. Apply a `toTitleCase()` display formatter globally.

### 11.2 — Fix AI Assistant Context Detection
**Current behavior:** The AI Assistant's context awareness panel shows stale/wrong information — referencing "Daily Schedule for Oct 24" and "Sunday" when the actual page shows February 2026 Saturday.

**Why change:** The AI Assistant's context badge is meant to show situational awareness ("I see you're viewing..."), but displaying wrong dates undermines the user's trust in the AI's suggestions.

**Implementation:**
Fix the context detection logic to read the current page's actual date from the DOM or route parameters. Update the suggested quick actions to match the actual day of the week and date.

---

## 12. LEFT IN APPROVED

### 12.1 — Auto-Sync Event Numbers During Database Refresh
**Current behavior:** Event numbers are only fetched when the user manually goes to Left in Approved, authenticates with Walmart, and clicks "Sync Event Numbers."

**Why change (Scenario #6):** If the database refresh already connects to CrossMark/Walmart systems, it should also fetch event numbers at that time. This means event numbers are available all day long, not just during a fragile end-of-day authentication window.

**Implementation:**
During the "Refresh Database" flow, if Walmart credentials are configured in Settings, also fetch and store event numbers for all current events. If authentication fails during refresh, log a warning but don't block the rest of the refresh. Show a status indicator on the dashboard: "Event numbers last synced: [timestamp]" so the manager knows if they need to manually re-sync.

---

## 13. ROTATIONS PAGE

### 13.1 — Fix Broken Rotations Page
**Current behavior:** The `/rotations/` page returns "Unexpected Error (ID: 20260221_164127_933035)" — a raw error with no navigation, no context, and no recovery path.

**Why change:** This is a feature listed in the navigation menu that is completely non-functional. Users who click it see a blank page with an error ID. It undermines confidence in the application.

**Implementation:**
Diagnose and fix the error. If the feature is still under development, either hide the nav link or display a proper "Coming Soon" placeholder page with navigation intact so users can get back to the rest of the app.

---

## 14. PRINTING / REPORTS

### 14.1 — Add Scan-Out Checklist to Printing Center
**Current behavior:** The Printing Center generates daily paperwork (schedule, item list, EDR instructions) but has no scan-out specific output.

**Why change (Scenario #6):** Scan-out is a daily task that needs a simple reference sheet: event numbers, product names, checkboxes. The current daily schedule printout contains far more information than needed for scan-out.

**Implementation:**
Add a "Scan-Out Checklist" option to the Printing Center. It generates a compact, printable list of: event number (6-digit), product name, event type, assigned employee, and a checkbox column. Sorted by event type (Juicer first, then Core, etc.) to match the typical scan-out order.

---

## 15. FIRST-RUN / ONBOARDING

### 15.1 — Create Setup Wizard for First-Time Configuration
**Current behavior:** An "Event Times Not Configured" modal warning blocks the page on load. It links to a generic "Go to Settings" button. A new user has to figure out the configuration order themselves across multiple settings pages (Walmart credentials, Event Times, Employees, Rotations).

**Why change:** The current experience for a new user is: dismissive modal -> confusion about what to configure first -> visiting multiple settings pages in an unknown order. A guided wizard would ensure proper setup and reduce support requests.

**Implementation:**
Create a setup wizard that triggers on first login (or when critical settings are missing). Steps:
1. Walmart Retail-Link credentials (Settings page fields)
2. Event Time Settings (time slots for each event type)
3. Employee setup (import or add employees)
4. Rotation configuration (weekly rotation patterns)

Each step validates before allowing the user to proceed. The wizard can be re-accessed from Settings. The blocking modal should be replaced with a persistent banner that links to the specific unconfigured setting, not a generic settings page.

---

## Implementation Priority Guide

**Phase 1 — Critical Fixes (bugs and broken features):**
13.1 (Fix Rotations page), 4.1 (Fix calendar "undefined" bug), 11.2 (Fix AI context detection), 11.1 (Standardize name casing)

**Phase 2 — High-Impact Daily Workflow (Scenarios #1, #6):**
3.1 (Employee filter on daily events), 3.2 (Urgency badges), 3.6 (Event numbers on all cards), 3.7 (Persist synced event numbers), 3.3 (Call-Off Wizard), 3.8 (Scan-Out Checklist)

**Phase 3 — Bulk Operations & Reporting (Scenarios #3, #4):**
5.5 (Bulk actions/multi-select), 5.6 (Cannot Complete status), 5.7 (Corporate report export), 5.1 (Date range picker), 9.1 (Auto-scheduler emergency mode)

**Phase 4 — Availability & Communication (Scenarios #2, #5):**
6.1 (Availability overrides), 7.1 (Link notes to events/employees), 7.2 (Surface contextual notes), 7.3 (Note reminders)

**Phase 5 — Layout & Navigation Improvements:**
1.1 (Dashboard homepage), 2.1 (Sidebar navigation), 3.4 (Tabbed daily schedule), 10.1 (Consolidate floating widgets), 8.1 (Consolidate verification)

**Phase 6 — Polish & Enhancements:**
2.2 (Move Refresh Database), 3.5 (Default list view), 4.2 (Calendar tooltips), 4.3 (Week view), 5.2 (Tab counts), 5.3 (Default to current events), 5.4 (Sort controls), 6.2 (Employee search), 6.3 (Move Delete button), 12.1 (Auto-sync during refresh), 14.1 (Scan-Out in Printing Center), 15.1 (Setup wizard)
