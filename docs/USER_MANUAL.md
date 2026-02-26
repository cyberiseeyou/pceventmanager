# Product Connections Event Manager - User Manual

**Version 2.0** | **Last Updated: February 25, 2026**

This manual provides a complete guide to using the Product Connections Event Manager (PC Event Manager), a web-based employee scheduling system built for Crossmark retail demonstration teams operating in Walmart Sam's Club stores. Whether you are a manager scheduling your team, a lead checking tomorrow's assignments, or an administrator configuring the system, this manual will walk you through every feature step by step.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
   - [Logging In](#11-logging-in)
   - [The Loading Screen](#12-the-loading-screen)
   - [Session Management & Timeouts](#13-session-management--timeouts)
   - [Navigating the Application](#14-navigating-the-application)
2. [The Command Center (Dashboard)](#2-the-command-center-dashboard)
   - [Deadline Banner](#21-deadline-banner)
   - [Quick Stats Bar](#22-quick-stats-bar)
   - [Unscheduled Urgent Events](#23-unscheduled-urgent-events)
   - [Deadline Events (Left In Approved)](#24-deadline-events-left-in-approved)
   - [Rotation Assignments for Today](#25-rotation-assignments-for-today)
   - [Quick Notes & Tasks](#26-quick-notes--tasks)
3. [Schedule Management](#3-schedule-management)
   - [Daily View](#31-daily-view)
   - [Calendar View](#32-calendar-view)
   - [Scheduling a Single Event](#33-scheduling-a-single-event)
   - [Rescheduling an Event](#34-rescheduling-an-event)
   - [Reissuing a Submitted Event](#35-reissuing-a-submitted-event)
   - [Overriding Constraints](#36-overriding-constraints)
4. [All Events Page](#4-all-events-page)
   - [Condition Tabs](#41-condition-tabs)
   - [Smart Search](#42-smart-search)
   - [Filtering & Sorting](#43-filtering--sorting)
   - [Bulk Actions](#44-bulk-actions)
   - [Exporting Data](#45-exporting-data)
5. [Auto-Scheduler](#5-auto-scheduler)
   - [Understanding the Auto-Scheduler](#51-understanding-the-auto-scheduler)
   - [Running the Auto-Scheduler](#52-running-the-auto-scheduler)
   - [Reviewing Pending Schedules](#53-reviewing-pending-schedules)
   - [Approving & Rejecting Proposals](#54-approving--rejecting-proposals)
   - [Solver Options: Greedy vs CP-SAT](#55-solver-options-greedy-vs-cp-sat)
6. [Employee Management](#6-employee-management)
   - [Viewing Employees](#61-viewing-employees)
   - [Adding a New Employee](#62-adding-a-new-employee)
   - [Editing an Employee](#63-editing-an-employee)
   - [Importing Employees from Crossmark](#64-importing-employees-from-crossmark)
   - [Employee Roles & What They Can Do](#65-employee-roles--what-they-can-do)
7. [Availability & Time Off](#7-availability--time-off)
   - [Weekly Availability](#71-weekly-availability)
   - [Time-Off Requests](#72-time-off-requests)
   - [Availability Overrides](#73-availability-overrides)
   - [How the System Checks Availability](#74-how-the-system-checks-availability)
8. [Rotation Assignments](#8-rotation-assignments)
   - [What Are Rotations?](#81-what-are-rotations)
   - [Setting Weekly Rotations](#82-setting-weekly-rotations)
   - [Adding Rotation Exceptions](#83-adding-rotation-exceptions)
9. [Validation & Quality Checks](#9-validation--quality-checks)
   - [Weekly Validation Dashboard](#91-weekly-validation-dashboard)
   - [Daily Validation](#92-daily-validation)
   - [Health Score](#93-health-score)
   - [Fix Wizard](#94-fix-wizard)
10. [Printing & Paperwork](#10-printing--paperwork)
    - [Complete Daily Paperwork](#101-complete-daily-paperwork)
    - [Single Event Paperwork](#102-single-event-paperwork)
    - [Daily Schedule Print](#103-daily-schedule-print)
    - [Scan-Out Checklist](#104-scan-out-checklist)
    - [Walmart EDR Authentication](#105-walmart-edr-authentication)
11. [Attendance Tracking](#11-attendance-tracking)
    - [Recording Attendance](#111-recording-attendance)
    - [Viewing the Attendance Calendar](#112-viewing-the-attendance-calendar)
    - [Attendance Statistics](#113-attendance-statistics)
12. [AI Assistant](#12-ai-assistant)
    - [Opening the AI Assistant](#121-opening-the-ai-assistant)
    - [What You Can Ask](#122-what-you-can-ask)
    - [Scheduling Actions via AI](#123-scheduling-actions-via-ai)
13. [Inventory & Supplies](#13-inventory--supplies)
    - [Managing Supplies](#131-managing-supplies)
    - [Creating Purchase Orders](#132-creating-purchase-orders)
14. [Unreported Events & Left In Approved](#14-unreported-events--left-in-approved)
    - [Unreported Events](#141-unreported-events)
    - [Left In Approved](#142-left-in-approved)
15. [Administration](#15-administration)
    - [Settings Page](#151-settings-page)
    - [Event Time Configuration](#152-event-time-configuration)
    - [Shift Block Configuration](#153-shift-block-configuration)
    - [Company Holidays](#154-company-holidays)
    - [Locked Days](#155-locked-days)
    - [Database Refresh](#156-database-refresh)
16. [Understanding Scheduling Rules](#16-understanding-scheduling-rules)
    - [Event Types & Priority Order](#161-event-types--priority-order)
    - [The 8 Shift Block System](#162-the-8-shift-block-system)
    - [Daily Constraints](#163-daily-constraints)
    - [Weekly Constraints](#164-weekly-constraints)
    - [Conflict Resolution & Bumping](#165-conflict-resolution--bumping)
17. [Common Workflows](#17-common-workflows)
    - [Morning Routine](#171-morning-routine)
    - [Weekly Planning](#172-weekly-planning)
    - [Handling a Call-Out](#173-handling-a-call-out)
    - [End-of-Day Scan-Out](#174-end-of-day-scan-out)
18. [Troubleshooting](#18-troubleshooting)
19. [Keyboard Shortcuts](#19-keyboard-shortcuts)
20. [Glossary](#20-glossary)

---

## 1. Getting Started

### 1.1 Logging In

When you first open the application, you'll see the login page.

**To log in:**
1. Enter your **Crossmark username** in the Username field.
2. Enter your **Crossmark password** in the Password field.
3. Optionally check **Remember Me** to stay logged in longer.
4. Click **Log In**.

The system authenticates your credentials against the Crossmark API. If your credentials are valid, a session is created and you'll be taken to the loading screen.

**Important:** If this is the first time event times have been configured, a warning modal will appear after login directing you to the Settings page. Event times **must** be configured before you can schedule any events. See [Event Time Configuration](#152-event-time-configuration).

### 1.2 The Loading Screen

After a successful login, you'll see a loading page with a progress bar. This is the **database refresh** process:

1. **Initializing** - Preparing the connection to Crossmark
2. **Fetching Events** - Downloading events from the Crossmark API (1 month in the past through 1 month in the future)
3. **Processing** - Detecting event types, creating records
4. **Restoring Schedules** - Re-applying any locally approved schedules
5. **Syncing** - Matching Walmart event numbers for EDR lookups
6. **Complete** - Redirecting to the Command Center

The progress bar updates in real-time using Server-Sent Events (SSE). You'll see the current step name, a count of processed items, and an estimated percentage. When complete, you are automatically redirected to the Command Center.

**Note:** The loading process typically takes 15-60 seconds depending on how many events are in your 4-month horizon.

### 1.3 Session Management & Timeouts

Your session has a built-in inactivity timeout to protect security:

- **Inactivity timeout:** 10 minutes (configurable by your administrator)
- **Heartbeat:** As long as you're actively using the application (clicking, scrolling, typing), a heartbeat signal is sent every 2 minutes to keep your session alive.
- **Timeout warning:** A modal dialog appears **60 seconds** before your session expires. You can click **Stay Connected** to refresh your session.
- **After timeout:** You'll be automatically logged out and redirected to the login page.

**To manually log out:**
Click on your username in the top-right corner of the page, then select **Logout** from the dropdown menu.

### 1.4 Navigating the Application

The application uses a **sidebar navigation** on the left side of the screen. The sidebar is organized into groups:

| Group | Pages | What It's For |
|-------|-------|---------------|
| **Dashboard** | Command Center | Your home base - daily overview and urgent items |
| **Schedule** | Daily View, Calendar, Auto-Scheduler | Viewing and managing the schedule |
| **Events** | All Events, Unreported Events, Left in Approved | Finding and tracking events |
| **Team** | Employees, Attendance, Availability, Analytics | Managing your team |
| **Tools** | Printing, Weekly Validation, Scan-Out Checklist, Demo Supplies | Day-to-day operational tools |
| **Admin** | Settings, Event Times, Rotations, Database Refresh | System configuration |

At the top of every page you'll find:
- **Page title** showing where you are
- **AI Assistant button** (or press `Ctrl+K`) to open the AI chat panel
- **Notifications bell** with a badge showing unread count
- **User menu** (top-right) with Help and Logout options

On mobile devices, the sidebar collapses into a hamburger menu icon.

---

## 2. The Command Center (Dashboard)

The Command Center is your main landing page. Think of it as your "morning briefing" - it shows you everything important at a glance. You reach it by navigating to the **Dashboard** section in the sidebar, or it loads automatically after login.

### 2.1 Deadline Banner

At the very top of the Command Center, a colored banner shows your current deadline status:

- **Red (Urgent):** A major deadline is approaching within 24 hours (e.g., Friday end-of-week, Saturday reporting, end-of-month)
- **Yellow (Warning):** A deadline is approaching within 48 hours
- **Green (Normal):** No imminent deadlines

The banner includes a countdown timer and a brief description of what the deadline is (e.g., "Friday weekly reporting deadline in 4 hours").

### 2.2 Quick Stats Bar

Below the banner is a row of stat cards showing your scheduling health at a glance:

| Stat | What It Means |
|------|---------------|
| **Total Events** | All events within your 4-month scheduling horizon |
| **Scheduled** | Events that have been assigned to employees |
| **Unscheduled** | Events that still need to be assigned |
| **Scheduling %** | The percentage of total events that are scheduled (goal: as close to 100% as possible) |
| **Last Run** | When the auto-scheduler was last executed |

### 2.3 Unscheduled Urgent Events

This section highlights events that need scheduling **urgently** - specifically, events due within the next 7 days that don't have an employee assigned yet.

Events are color-coded by urgency:
- **Red:** Due within 1-2 days (critical)
- **Orange:** Due within 3-4 days (urgent)
- **Yellow:** Due within 5-7 days (attention needed)

Each event card shows the event name, type, due date, and a **Schedule Now** button that takes you directly to the scheduling form for that event.

### 2.4 Deadline Events (Left In Approved)

This section shows events that were marked as "Left in Approved" in Walmart's system - meaning they've been completed but their scan-out process hasn't been finalized. These need attention to avoid compliance issues.

Each item shows the event number, product name, and date. You can click through to view details or print the scan-out checklist.

### 2.5 Rotation Assignments for Today

A quick-reference card showing:
- **Today's Juicer:** Who is assigned to Juicer duties today (primary and backup)
- **Today's Primary Lead:** Who is the lead for today (primary and backup)
- **Quick Swap:** A button to quickly change today's rotation assignment if needed

### 2.6 Quick Notes & Tasks

A notes widget where you can jot down day-to-day notes, reminders, and tasks. Notes can have:
- **Priority levels:** Low, Normal, High, Urgent
- **Due dates:** For time-sensitive items
- **Linked items:** Optionally link a note to a specific employee or event

Click the **Refresh** button (top-right of the dashboard) to reload all dashboard data.

---

## 3. Schedule Management

### 3.1 Daily View

**Navigation:** Schedule > Daily View

The Daily View shows a full-screen breakdown of a single day's schedule. It is your primary tool for seeing "who is doing what today."

**What you'll see:**
- A **date selector** at the top with Previous Day / Next Day arrows
- **All events** for that day organized by time
- For each event:
  - Event name, type, and number
  - Assigned employee name
  - Start/end times
  - Status indicator (scheduled, submitted, etc.)
- **Rotation assignments** for the selected day (Juicer and Primary Lead)

**Actions you can take from Daily View:**

| Action | How | When to Use |
|--------|-----|-------------|
| **View event details** | Click on any event card | To see full event information |
| **Reschedule** | Click the reschedule icon on an event | To change the assigned employee or time |
| **Reassign** | Click the reassign icon | To move an employee to a different shift block |
| **Reissue** | Click reissue on a submitted event | To send a completed event back to "Scheduled" status |
| **Delete schedule** | Click the delete icon | To remove an assignment entirely |
| **Bulk select** | Check multiple event checkboxes | To perform batch operations |

### 3.2 Calendar View

**Navigation:** Schedule > Calendar

The Calendar View shows an entire month at a glance. Each day cell contains:
- Color-coded badges for event types (Core = mint, Juicer = red, Digital = teal, etc.)
- An event count
- A red dot indicator if there are unscheduled events on that day

**How to use it:**
1. Use the **Previous/Next** month buttons to navigate
2. Click on any **date cell** to expand a popup showing all events for that day
3. The expanded view shows employee names, times, event details, rotation assignments, and quick action buttons
4. Click an event in the popup to go to its scheduling page

### 3.3 Scheduling a Single Event

**How to schedule an unscheduled event:**

1. Find the event (from All Events, Daily View, Command Center, or Auto-Scheduler page)
2. Click **Schedule Now** or click the event card
3. You'll be taken to the scheduling form with these fields:

   | Field | Description |
   |-------|-------------|
   | **Scheduled Date** | Pick a date within the event's start-to-due date window |
   | **Available Employee** | Dropdown populated after you select a date - only shows employees who are available and qualified for this event type |
   | **Start Time** | Time picker or dropdown - validates against allowed times for this event type |

4. Click **Submit** to create the schedule

**What the system checks automatically when you pick an employee:**
- Is the employee on time-off that day?
- Is the employee available per their weekly pattern?
- Does the employee's role qualify for this event type?
- Does the employee already have the maximum events for the day/week?
- Are there any time conflicts?

If any issues are found, you'll see warning messages. The employee may be hidden from the dropdown entirely if they have a hard constraint violation (like being on time-off).

### 3.4 Rescheduling an Event

If an event is already scheduled but needs to be reassigned:

1. Find the event (Daily View, Calendar, or All Events)
2. Click the **Reschedule** button/icon
3. The form will show the current assignment and let you:
   - Pick a new employee
   - Pick a new date/time
4. Click **Submit** to apply the change

The old schedule is replaced with the new one.

### 3.5 Reissuing a Submitted Event

Events in "Submitted" status (already reported as complete) can be **reissued** to return them to "Scheduled" status. This is useful when:
- An event was accidentally reported as complete
- The work needs to be redone
- A different employee needs to redo the event

To reissue:
1. Find the submitted event
2. Click the **Reissue** button
3. Confirm the action in the dialog
4. The event returns to "Scheduled" status, ready to be worked again

### 3.6 Overriding Constraints

When scheduling manually, you have the option to **Override Scheduling Constraints** via a checkbox on the scheduling form. When enabled, the system bypasses:
- Role restrictions (lets any employee do any event type)
- The one-Core-per-day limit
- Availability constraints

**Use this sparingly and with caution.** It exists for emergency situations where the normal rules would prevent a necessary assignment. The override is logged for audit purposes.

---

## 4. All Events Page

**Navigation:** Events > All Events

This is your comprehensive event listing with powerful search and filtering. It's where you go when you need to find specific events or get an overview of your event landscape.

### 4.1 Condition Tabs

At the top of the page, you'll see tabs with event counts:

| Tab | What It Shows |
|-----|---------------|
| **All** | Every event regardless of status |
| **Scheduled** | Events assigned to employees |
| **Unscheduled** | Events needing assignment (truly unstaffed) |
| **Submitted** | Events reported as completed |
| **Paused** | Events temporarily on hold |
| **Reissued** | Events that were reissued and await new assignment |
| **Cannot Complete** | Events marked as unable to be done |

Click a tab to filter the list. The count badge on each tab updates in real-time.

### 4.2 Smart Search

The search box at the top supports several powerful search formats:

| What You Type | What It Finds |
|---------------|---------------|
| `123456` | Events with that 6-digit event number |
| `JOHN DOE` | Events assigned to that employee (use uppercase) |
| `10/28/25` | Events on that date |
| `10/28/25 to 11/2/25` | Events within a date range |
| `s:10/28/25` | Events **starting** on that date |
| `sc:10/28/25` | Events **scheduled** for that date |
| `e:10/28/25` or `d:10/28/25` | Events **due** on that date |

**Combining searches:** You can combine multiple criteria with commas. For example:
```
123456, JOHN DOE, s:10/28/25
```
This finds event #123456, OR events for John Doe, OR events starting on 10/28/25.

### 4.3 Filtering & Sorting

In addition to search, you have:

- **Date Range Filter:** From/To date pickers to narrow the time window
- **Event Type Filter:** Dropdown to show only Core, Juicer, Digital, etc.
- **Sort Options:**
  - By scheduled/start date (default)
  - By due date
  - By event type
- **Show Past Events:** Toggle switch (off by default) to include/exclude events with past due dates

### 4.4 Bulk Actions

To perform actions on multiple events at once:

1. Check the checkboxes on individual event cards (or use "Select All")
2. A **sticky toolbar** appears at the bottom showing:
   - How many events are selected
   - **Bulk Schedule** - Schedule all selected events
   - **Bulk Reassign** - Reassign selected events to a different employee
   - **Bulk Delete** - Remove schedules for selected events

### 4.5 Exporting Data

Two export options are available:

- **Export CSV:** Exports the currently filtered events to a spreadsheet file. Includes all event details, employee assignments, dates, and statuses.
- **Corporate Report:** Generates a formatted report for a specified date range, suitable for submitting to management.

---

## 5. Auto-Scheduler

The auto-scheduler is the heart of the system - it automatically assigns employees to events based on business rules, availability, and constraints.

### 5.1 Understanding the Auto-Scheduler

**Navigation:** Schedule > Auto-Scheduler

The Auto-Scheduler page shows:

1. **Scheduling Progress Circle:** A large visual showing your scheduling percentage (e.g., "73% Complete")
2. **Statistics:**
   - Total events in your 4-month horizon
   - Already scheduled count
   - Still unscheduled count
3. **Last Run Info:** When the scheduler last ran, what the results were
4. **Unscheduled Events List:** Scrollable list of events needing assignment, sorted by earliest due date first

### 5.2 Running the Auto-Scheduler

To run the auto-scheduler:

1. Click the **Run Auto-Scheduler** button
2. A confirmation dialog appears - click **Confirm**
3. The scheduler processes events (this typically takes 30 seconds to 2 minutes)
4. When complete, you'll see a results summary:
   - Total events processed
   - Events successfully scheduled
   - Events that required bumping (swapping with lower-priority events)
   - Events that failed (no qualified employees available)

**Important:** The auto-scheduler does NOT immediately apply changes. It creates **pending schedules** that you must review and approve. This gives you a chance to verify the proposals before they take effect.

### 5.3 Reviewing Pending Schedules

After the scheduler runs, click **Review Pending Schedules** (or navigate to `/auto-schedule/review`).

The review page shows:

| Column | Description |
|--------|-------------|
| **Event** | Event name and number |
| **Proposed Employee** | Who the scheduler wants to assign |
| **Proposed Date/Time** | When the event would be scheduled |
| **Current Workload** | How many events the employee already has that day |
| **Status** | Whether the proposal has any warnings |

If an event required bumping (displacing a lower-priority assignment), it will be highlighted with details about what was bumped and why.

### 5.4 Approving & Rejecting Proposals

You have several options:

| Action | What It Does |
|--------|--------------|
| **Approve All** | Accept every pending schedule in one click |
| **Approve Single** | Accept one individual schedule |
| **Reject All** | Discard all proposals (nothing changes) |
| **Reject Single** | Discard one individual proposal |

Once approved, schedules are immediately applied to the database. If sync is enabled, they are also queued for submission to the Crossmark API.

### 5.5 Solver Options: Greedy vs CP-SAT

The system offers two scheduling algorithms:

**Greedy Engine (Default):**
- Processes events one at a time in priority order
- Assigns the best available employee for each event
- Fast (seconds) but may miss globally optimal solutions
- Good for daily scheduling needs

**CP-SAT Constraint Solver:**
- Uses Google OR-Tools to find the mathematically optimal schedule
- Considers ALL events and employees simultaneously
- Slower (15-30 seconds) but produces better overall schedules
- Best for weekly planning or when you need maximum coverage

To select a solver, use the URL parameters when running the scheduler:
- Default (greedy): Just click "Run Auto-Scheduler"
- Force CP-SAT: Your administrator can enable this in Settings
- Emergency mode: Reduces scheduling buffers for last-minute situations

---

## 6. Employee Management

### 6.1 Viewing Employees

**Navigation:** Team > Employees

The Employees page shows your entire team in a grid layout. At the top you'll find:

**Summary Statistics Cards:**
- Total Employees
- Juicer Baristas count
- Event Specialists count
- Lead Event Specialists count
- Adult Beverage Trained count

**Search & Filters:**
- **Search by name:** Type to filter in real-time
- **Role filter:** All Roles, Lead Event Specialist, Event Specialist, Juicer Barista, Club Supervisor
- **Status filter:** Active Only (default), All, Inactive Only

**Each employee card shows:**
- Name with job title badge
- Email and phone number
- Training badges (AB Trained, Juicer Trained) if applicable
- Active/Inactive status indicator
- Weekly availability bar (Mon-Sun with checkmarks)
- Edit and Delete action buttons

### 6.2 Adding a New Employee

1. Click the **Add Employee** button
2. Fill in the form:

   | Field | Required? | Description |
   |-------|-----------|-------------|
   | Employee ID | No | Crossmark integration ID (auto-generated if blank) |
   | Name | **Yes** | Employee's full name |
   | Email | No | Email address |
   | Phone | No | Contact phone number |
   | Job Title | **Yes** | Select: Event Specialist, Lead Event Specialist, Club Supervisor, or Juicer Barista |
   | Active | - | Checked by default. Uncheck to create as inactive |
   | Adult Beverage Trained | - | Check if the employee has AB certification |
   | Juicer Trained | - | Check if the employee can operate the juice bar |
   | Supervisor | - | Check to mark as a supervisor |
   | Weekly Availability | - | 7 checkboxes (Mon-Sun). All checked by default. Uncheck days the employee is NOT available |

3. Click **Save Employee**

### 6.3 Editing an Employee

1. Click the **Edit** button on an employee card
2. The same form appears pre-filled with current data
3. Make your changes
4. Click **Save Employee**

**Common changes:**
- Updating job title (e.g., promoting from Event Specialist to Lead)
- Toggling training certifications
- Changing weekly availability
- Marking an employee as inactive (e.g., when they leave the company)

### 6.4 Importing Employees from Crossmark

Click the **Import Employees** button to bulk-import employee records from the Crossmark API. This syncs:
- Employee names
- Job titles
- External IDs
- Active/inactive status

Existing employees are updated; new ones are created. This does not overwrite locally-set fields like training certifications or weekly availability.

### 6.5 Employee Roles & What They Can Do

Understanding roles is critical because the system enforces role-based restrictions when scheduling:

| Role | Can Do These Event Types | Special Rules |
|------|--------------------------|---------------|
| **Club Supervisor** | Supervisor, Digital Setup/Refresh/Teardown, Freeosk, Juicer events, Core, Other | Exempt from the 1-Core-per-day limit. Preferred for Supervisor event assignments. |
| **Lead Event Specialist** | Freeosk, Digital Setup/Refresh/Teardown, Digitals, Core, Supervisor (backup), Other | When designated as Primary Lead, always assigned to Shift Block 1. Must handle Freeosk + Digital Refresh daily. |
| **Juicer Barista** | Juicer Production, Juicer Survey, Juicer Deep Clean | Specialized role. Rotation-based scheduling (one per shift). |
| **Event Specialist** | Core, Other | Standard role. Can also do Juicer events if `Juicer Trained` is checked. |

**Important:** An employee with **Juicer Trained** checked (regardless of job title) can also be assigned to Juicer Production, Juicer Survey, and Juicer Deep Clean events.

---

## 7. Availability & Time Off

### 7.1 Weekly Availability

Each employee has a **weekly availability pattern** - a set of 7 checkboxes (Monday through Sunday) indicating which days they are generally available to work. This is set on the employee profile and represents their "standard" schedule.

For example, an employee who works Monday through Friday would have Mon-Fri checked and Sat-Sun unchecked.

The auto-scheduler and manual scheduling both respect this pattern. If an employee is marked as unavailable on Wednesday, they won't appear in the employee dropdown when you try to schedule something on a Wednesday.

### 7.2 Time-Off Requests

**Navigation:** Team > Availability (or Team > Time Off)

Time-off requests represent date ranges when an employee will be absent (vacation, sick leave, personal days, etc.).

**To add a time-off request:**
1. Click **Add Time Off**
2. Select the **employee** from the dropdown
3. Choose a **start date** and **end date**
4. Optionally add a **reason** (e.g., "Family vacation")
5. Click **Save**

**What happens when time off is created:**
- The employee is automatically marked as unavailable for the entire date range (inclusive of both start and end dates)
- The auto-scheduler will not assign them during this period
- When manually scheduling, the employee will be flagged as unavailable
- If the employee was already scheduled for events during this period, you'll see conflict warnings

**Managing existing time-off:**
- View all requests filtered by employee and/or date range
- Edit a request to change dates
- Delete a request to cancel it

### 7.3 Availability Overrides

Availability overrides are **temporary changes** to an employee's weekly availability pattern for a specific date range. This is useful when an employee's schedule changes for a limited period.

**Example:** An employee normally works Monday through Friday, but for the next 3 weeks they can only work Tuesday and Thursday due to college classes.

To create an override:
1. Go to the employee's availability page
2. Add a date range (start and end)
3. For each day of the week, choose: Available, Unavailable, or No Change
4. Provide a reason (e.g., "College class schedule")

**Priority:** Overrides take the highest priority in the availability system. They override both the regular weekly pattern and any date-specific availability settings.

### 7.4 How the System Checks Availability

When the system needs to determine if an employee is available on a specific date, it checks these four levels in order (highest priority first):

1. **Availability Override** - Is there a temporary override for this week?
2. **Date-Specific Availability** - Is there a specific entry for this exact date?
3. **Time-Off Request** - Is the employee on time-off during this period?
4. **Weekly Availability** - What does their standard weekly pattern say?
5. **Company Holidays** - Is this a company holiday? (blocks ALL employees)

The first match wins. For example, if an employee has a time-off request for Monday but an override that says they ARE available on Monday, the override wins because it has higher priority.

---

## 8. Rotation Assignments

### 8.1 What Are Rotations?

Some roles need to be filled every day on a rotating basis:

- **Juicer Rotation:** One employee is assigned to Juicer duties each day. They handle Juicer Production (all-day), Juicer Survey (end of day), and Juicer Deep Clean events.
- **Primary Lead Rotation:** One Lead Event Specialist is designated as the "Primary Lead" each day. They get Shift Block 1 (first in), handle Freeosk events, Digital Refresh, and serve as the on-site lead.

Both rotations have a **primary** (preferred) and **backup** (fallback) employee for each day of the week.

### 8.2 Setting Weekly Rotations

**Navigation:** Admin > Rotations

The Rotations page has two sections:

**Juicer Rotations:**
A 7-day grid (Monday through Sunday). For each day:
- Select a **Primary** employee from the dropdown (filtered to show only Juicer-trained employees)
- Select a **Backup** employee

**Primary Lead Rotations:**
A 7-day grid (Monday through Sunday). For each day:
- Select a **Primary** Lead from the dropdown (filtered to Lead Event Specialists and Club Supervisors)
- Select a **Backup** Lead

Click **Save Rotations** to apply your changes. These take effect immediately - the next time the auto-scheduler runs, it will use these rotation assignments.

**Other actions:**
- **Clear All** - Reset all rotations to empty
- **Load Previous** - Copy assignments from the previous week
- **Verify** - Check for any conflicts (e.g., same person as both Juicer and Lead on the same day)

### 8.3 Adding Rotation Exceptions

Sometimes you need to override the regular rotation for a specific date without changing the weekly pattern. This is what **exceptions** are for.

**Example:** Monday's Juicer is normally Employee A, but Employee A is on vacation next Monday. Instead of changing the entire weekly rotation, add an exception:
- Date: Next Monday
- Type: Juicer
- Employee: Employee C
- Reason: "Employee A on vacation"

The exception only applies to that one date. The regular Monday rotation resumes the following week.

---

## 9. Validation & Quality Checks

### 9.1 Weekly Validation Dashboard

**Navigation:** Tools > Weekly Validation

The Weekly Validation dashboard gives you a bird's-eye view of scheduling quality for the upcoming week.

**What you'll see:**

1. **Header:** Week date range with Previous/Next navigation arrows
2. **Summary Cards:**
   - Total events for the week
   - Scheduled count
   - Unscheduled count
   - Warning count (issues found)
3. **Day Pills:** Seven clickable pills (Mon-Sun), color-coded:
   - **Green:** No issues
   - **Yellow:** Warnings present
   - **Red:** Critical issues found
4. **Day Detail Panel:** When you click a pill, shows:
   - Event counts broken down by type
   - Rotation assignments for that day
   - Any validation issues or missing coverage

### 9.2 Daily Validation

**Navigation:** Tools > Weekly Validation > Click a specific day

Daily validation checks a single day's schedule for issues:

**What it checks:**
- Missing rotation assignments (no Juicer or Lead assigned)
- Double-booked employees (same person scheduled for overlapping events)
- Role mismatches (employee assigned to an event type they're not qualified for)
- Time-off conflicts (employee scheduled but has approved time off)
- Missing Supervisor pairings (Core event without a paired Supervisor event)
- Weekly limit violations (employee exceeding 6 Core events or 5 Juicer events in the week)

Each issue is labeled with a severity:
- **Critical:** Must be fixed before the schedule can be considered valid
- **Warning:** Should be reviewed but may be acceptable
- **Info:** Informational note, no action required

### 9.3 Health Score

The health score is a number from 0 to 100 that summarizes your schedule's quality:

```
Health Score = 100 - (critical issues x 10) - (warning issues x 3)
```

| Score Range | Rating | Meaning |
|-------------|--------|---------|
| 90-100 | Excellent | Schedule is in great shape |
| 70-89 | Good | Minor issues, generally acceptable |
| 50-69 | Fair | Several issues need attention |
| Below 50 | Needs Attention | Significant problems to resolve |

**Target:** Aim for a health score above 85 for production schedules.

### 9.4 Fix Wizard

When validation finds issues, the **Fix Wizard** provides guided resolution:

1. It identifies each validation issue
2. For each issue, it generates multiple fix options:
   - **Reassign** to a different qualified employee
   - **Reschedule** to a different time slot
   - **Unschedule** the event (remove the assignment)
   - **Trade** with another employee's assignment
   - **Add missing pairing** (e.g., create a Supervisor event for an unpaired Core)
3. Each option has a **confidence score** (0-100%)
4. The highest-confidence option is marked as **Recommended**
5. You select the fix you want, and the wizard applies it directly

**Example:**
- **Issue:** "Employee John Doe is double-booked at 10:15 AM on Monday"
- **Fix Option 1 (Recommended, 92%):** Reassign Event B to Employee Jane Smith
- **Fix Option 2 (78%):** Reschedule Event B to 11:45 AM
- **Fix Option 3 (65%):** Unschedule Event B

---

## 10. Printing & Paperwork

**Navigation:** Tools > Printing

The Printing page is your central hub for generating all the paper documents you need for daily operations at the store.

### 10.1 Complete Daily Paperwork

This generates a full package of everything needed for a day's operations:

1. Click **Complete Daily Paperwork**
2. Select the **date**
3. Click **Generate**
4. The system creates a combined PDF containing:
   - **Daily Schedule** - Who is working what, and when
   - **Daily Item List** - Items to be demonstrated, with barcodes
   - **EDR (Event Detail Report)** for each Core event - Detailed event instructions from Walmart
   - **Sales Tool Manual** (Instructions) for each Core event

5. Download the combined PDF and print it

**Note:** This feature requires active Walmart EDR credentials. See [Walmart EDR Authentication](#105-walmart-edr-authentication).

### 10.2 Single Event Paperwork

To generate paperwork for just one specific event:

1. Enter the **6-digit event number**
2. Click **Generate**
3. Receive a PDF package containing:
   - EDR (Event Detail Report)
   - Instructions/Sales Tool Manual
   - Event Activity Log
   - Daily Task Checkoff Sheet

### 10.3 Daily Schedule Print

A simplified print of just the day's schedule:

1. Select the **date**
2. Choose: **View in Browser**, **Print to PDF**, or **Print Directly**
3. The schedule shows Core and Juicer Production events only, with employee names and times

### 10.4 Scan-Out Checklist

A compact checklist designed to be taken to the store floor for end-of-day scan-out:

1. Select the **date**
2. Generate the checklist
3. It shows:
   - Event numbers
   - Product names
   - Checkboxes to mark as scanned out

Print this and use it to verify every product has been scanned at the end of the day.

### 10.5 Walmart EDR Authentication

The first time you use printing features that require Walmart data, you'll need to authenticate:

1. The system detects no active Walmart session
2. You'll see an **Authenticate with Walmart RetailLink** prompt
3. Enter your **Walmart username**
4. The system initiates multi-factor authentication (MFA)
5. You'll receive an **SMS code** on your registered phone
6. Enter the **6-digit code**
7. Authentication completes - you can now generate EDR documents

**Session timeout:** The Walmart session expires after approximately 2 hours of inactivity. You'll need to re-authenticate when it expires.

**Credentials storage:** Your Walmart credentials can be saved in Settings to avoid re-entering them each time. See [Settings Page](#151-settings-page).

---

## 11. Attendance Tracking

### 11.1 Recording Attendance

**Navigation:** Team > Attendance

Attendance records track whether employees showed up for their scheduled shifts.

**Attendance statuses:**

| Status | Color | Meaning |
|--------|-------|---------|
| On Time | Green | Employee arrived as scheduled |
| Late | Yellow | Employee arrived but was tardy |
| Called In | Orange | Employee called to report absence |
| No Call / No Show | Red | Employee didn't show up and didn't call |
| Excused Absence | Gray | Legitimate absence (medical, emergency, etc.) |

To record attendance:
1. Navigate to the attendance page
2. Select the employee and date
3. Choose the appropriate status
4. Optionally add notes (e.g., "Called at 9:15 AM, car trouble")
5. Save

### 11.2 Viewing the Attendance Calendar

The attendance calendar shows a month-view grid:
- Use **Previous/Next** buttons to navigate months
- Select an **employee** from the dropdown (or "All" for a summary)
- Day cells are color-coded by attendance status
- Click any day cell to see details (events scheduled, check-in/out times, notes)

### 11.3 Attendance Statistics

At the bottom of the calendar, you'll see summary stats for the selected employee and month:
- Days worked
- Days off
- Total absences
- Attendance percentage
- Late arrivals count

---

## 12. AI Assistant

### 12.1 Opening the AI Assistant

The AI Assistant is available on every page. To open it:
- Click the **AI Assistant** button in the header, OR
- Press **Ctrl+K** (or **Cmd+K** on Mac)

A chat panel slides open on the right side of the screen.

### 12.2 What You Can Ask

The AI understands natural language questions about your scheduling operation:

| Question Type | Example | What It Does |
|---------------|---------|--------------|
| **Schedule queries** | "Who is working tomorrow?" | Fetches schedule data for the requested date |
| **Availability checks** | "Can John do a Core event Tuesday?" | Validates constraints and returns yes/no with reasons |
| **Conflict detection** | "Are there any double-bookings this week?" | Scans for scheduling conflicts |
| **Workload analysis** | "Show me the workload distribution for next week" | Analyzes per-employee event counts |
| **Employee suggestions** | "Who should work the Core event on Friday?" | Scores and ranks qualified employees |
| **Event lookup** | "Tell me about event #123456" | Fetches full event details |
| **Employee info** | "Show me Sarah's schedule this week" | Retrieves employee-specific data |

### 12.3 Scheduling Actions via AI

The AI can also **take actions** on your behalf:

- "Assign Sarah to Event #123456" - Creates a schedule assignment
- "Reschedule event #123456 to Wednesday" - Moves an assignment
- "Run the auto-scheduler" - Triggers a scheduler run
- "Fix the double booking on Monday" - Invokes the Fix Wizard

For actions that modify data, the AI will:
1. Show you what it plans to do
2. Ask for your confirmation
3. Only proceed after you approve

---

## 13. Inventory & Supplies

### 13.1 Managing Supplies

**Navigation:** Tools > Demo Supplies

The inventory system tracks demonstration supplies and materials:

**Supply Categories:** Organize supplies into categories (e.g., "Cups & Lids", "Napkins", "Cleaning Supplies")

**Supply List:** For each supply item:
- Name and category
- Current quantity on hand
- Minimum/maximum threshold levels
- Status indicator:
  - **Green (OK):** Quantity is within normal range
  - **Yellow (Low Stock):** Below minimum threshold
  - **Red (Out of Stock):** Zero quantity

**Actions:**
- **Add Supply** - Create a new supply item
- **Adjust Quantity** - Increase or decrease quantity with a reason (e.g., "Received shipment", "Used for demo")
- **Edit** - Change supply details
- **Delete** - Remove a supply item

### 13.2 Creating Purchase Orders

**Navigation:** Tools > Demo Supplies > Purchase Orders

Purchase orders track supply reorders:

1. Click **Create Order**
2. Add items to the order (select from your supply list)
3. Specify quantities and unit costs
4. Save as **Draft** or **Submit** for ordering

**Order statuses:**
- **Draft** - Not yet finalized
- **Pending** - Awaiting approval
- **Ordered** - Placed with vendor
- **Partial** - Some items received
- **Received** - All items received (inventory automatically updated)
- **Cancelled** - Order was cancelled

When items are received, the system automatically adjusts your inventory quantities.

---

## 14. Unreported Events & Left In Approved

### 14.1 Unreported Events

**Navigation:** Events > Unreported Events

This page shows events that were scheduled and the date has passed, but they haven't been reported as completed. These are "overdue" events that need attention.

**What you'll see:**
- Events from the past 2 weeks
- The scheduled date (in the past)
- The assigned employee
- How many days overdue
- Event type and store name

**Actions:**
- **Mark as Submitted** - If the work was done, mark it complete
- **Reschedule** - If it wasn't done, assign it to a new date/employee
- **Delete Schedule** - Remove the assignment entirely

### 14.2 Left In Approved

**Navigation:** Events > Left In Approved

These are events that Walmart shows as "Left in Approved" status - meaning they were completed but the scan-out process wasn't finalized at the store.

**Why this matters:** Events stuck in "Left in Approved" can cause compliance issues. They need to have their scan-out completed.

**Actions:**
- View event details
- Print the scan-out checklist for these events
- Mark as scan-out complete when done

---

## 15. Administration

### 15.1 Settings Page

**Navigation:** Admin > Settings

The Settings page has multiple sections:

**Walmart EDR Credentials:**
- Username for Walmart RetailLink system
- Password
- MFA Credential ID
- **Test Connection** button to verify credentials work

**Auto-Scheduler Settings:**
- Preferred solver type (Greedy or CP-SAT)
- Time limit for the solver (seconds)
- Emergency mode toggle

**Session & Security:**
- Inactivity timeout duration (in minutes)
- Remember Me duration

### 15.2 Event Time Configuration

**Navigation:** Admin > Event Times

**This is a required setup step.** Before any events can be scheduled, you must configure the allowed start times for each event type.

For each event type (Core, Juicer Production, Supervisor, Digital Setup, etc.):
1. View or edit the list of **allowed start times**
2. Add times using the time picker (e.g., 09:00, 09:15, 09:30, etc.)
3. Optionally set:
   - Minimum event duration
   - Maximum employees per day
   - Required role qualifications

Click **Save** after making changes.

**Why this matters:** When scheduling an event, the time dropdown only shows times that are configured here. If no times are configured for an event type, you won't be able to schedule events of that type.

### 15.3 Shift Block Configuration

The 8 shift blocks define the arrival/departure schedule for Core event employees:

| Block | Description | Default Arrive | Default Depart |
|-------|-------------|----------------|----------------|
| 1 | First shift (Primary Lead) | 10:15 AM | 5:00 PM |
| 2 | Second shift | 10:15 AM | 5:00 PM |
| 3 | Third shift | 10:45 AM | 5:00 PM |
| 4 | Fourth shift | 10:45 AM | 5:00 PM |
| 5 | Fifth shift | 11:15 AM | 5:00 PM |
| 6 | Sixth shift | 11:15 AM | 5:00 PM |
| 7 | Seventh shift | 11:45 AM | 5:00 PM |
| 8 | Eighth shift | 11:45 AM | 5:00 PM |

For each block, you can configure:
- Arrive time
- On-floor time
- Lunch begin/end times
- Off-floor time
- Depart time

These times appear on EDR reports and daily schedules.

### 15.4 Company Holidays

Company holidays are days when **no employees** can be scheduled, regardless of individual availability.

To add a holiday:
1. Enter the **holiday name** (e.g., "Christmas Day")
2. Select the **date**
3. Optionally mark as **recurring** (automatically repeats annually)
4. For recurring holidays, you can set rules like "4th Thursday of November" for Thanksgiving

### 15.5 Locked Days

Locked days are dates that **cannot be modified**. Once a day is locked:
- No new schedules can be created for that date
- No existing schedules can be changed
- The auto-scheduler will skip that date

**When to lock a day:** After you've printed all paperwork and finalized the schedule for a date. This prevents accidental changes.

To lock a day:
1. Navigate to the date in Daily View or via the admin page
2. Click **Lock Day**
3. Provide a reason (e.g., "Paperwork printed and distributed")

To unlock: An administrator can remove the lock from the admin page.

### 15.6 Database Refresh

**Navigation:** Admin > Refresh Database

A database refresh re-syncs all event and employee data from the Crossmark API. This is useful when:
- Events have been added or changed in the Crossmark system
- You need to ensure your data is up-to-date
- The automatic login refresh didn't capture recent changes

**Warning:** A database refresh clears existing events and re-fetches everything. However:
- Locally approved schedules are preserved and restored
- Event type overrides are preserved and reapplied
- Employee data is updated (not deleted)

**To refresh:**
1. Click **Refresh Database**
2. Confirm in the dialog
3. Watch the progress (same loading screen as login)
4. When complete, all data is refreshed

**Tip:** Always use the login refresh (which happens automatically) for routine syncing. Use manual refresh only when you specifically need to pull in changes.

---

## 16. Understanding Scheduling Rules

This section explains the business rules that govern how scheduling works. Understanding these rules helps you make better scheduling decisions and understand why the system may restrict certain assignments.

### 16.1 Event Types & Priority Order

The auto-scheduler processes events in this specific priority order (highest first):

| Priority | Event Type | Typical Duration | Who Can Do It |
|----------|------------|------------------|---------------|
| 1 (Highest) | **Juicer Production** | 9 hours | Juicer Barista, Club Supervisor, or anyone Juicer Trained |
| 2 | **Digital Setup** | 30 min | Lead Event Specialist or Club Supervisor |
| 3 | **Digital Refresh** | 30 min | Lead Event Specialist or Club Supervisor |
| 4 | **Freeosk** | 15 min | Lead Event Specialist or Club Supervisor |
| 5 | **Digital Teardown** | 15 min | Lead Event Specialist or Club Supervisor |
| 6 | **Core** | 6.5 hours | Any active employee |
| 7 | **Supervisor** | 5 min | Club Supervisor (preferred) or Primary Lead |
| 8 | **Digitals** | 15 min | Lead Event Specialist or Club Supervisor |
| 9 (Lowest) | **Other** | 15 min | Any active employee |

**Why priority matters:** When the auto-scheduler needs to bump (displace) a lower-priority event to make room for a higher-priority one, it follows this order. A Juicer event will bump a Core event, but never the reverse.

### 16.2 The 8 Shift Block System

Core events use an 8-block system to stagger employee arrival times throughout the morning:

| Block | Arrive | On Floor | Lunch | Depart |
|-------|--------|----------|-------|--------|
| 1 | 10:15 AM | 10:20 AM | 12:20 PM | 5:00 PM |
| 2 | 10:15 AM | 10:20 AM | 12:20 PM | 5:00 PM |
| 3 | 10:45 AM | 10:50 AM | 12:50 PM | 5:00 PM |
| 4 | 10:45 AM | 10:50 AM | 12:50 PM | 5:00 PM |
| 5 | 11:15 AM | 11:20 AM | 1:20 PM | 5:00 PM |
| 6 | 11:15 AM | 11:20 AM | 1:20 PM | 5:00 PM |
| 7 | 11:45 AM | 11:50 AM | 1:50 PM | 5:00 PM |
| 8 | 11:45 AM | 11:50 AM | 1:50 PM | 5:00 PM |

**Key rules:**
- The **Primary Lead always gets Block 1** (earliest arrival)
- Blocks are assigned sequentially: 1, 2, 3, 4, 5, 6, 7, 8
- If there are more than 8 Core events in a day, overflow uses priority order: 1, 3, 5, 7, 2, 4, 6, 8
- Each employee can only be in **one block per day**

### 16.3 Daily Constraints

These rules are checked every time an assignment is made:

| Rule | Description |
|------|-------------|
| **1 Core/day** | Each employee (except Club Supervisors) can only be assigned 1 Core event per day |
| **Juicer exclusivity** | An employee doing Juicer Production cannot also do a Core event that day |
| **Supervisor pairing** | Every Core event must have a paired Supervisor event on the same day |
| **Role qualifications** | Employees can only be assigned to event types their role allows |
| **Availability** | Employees must be available (not on time off, company holiday, or marked unavailable) |
| **No conflicts** | No overlapping assignments at the same time |

### 16.4 Weekly Constraints

These rules span the entire work week (Sunday through Saturday):

| Rule | Limit |
|------|-------|
| **Core events per week** | Maximum 6 per employee |
| **Juicer events per week** | Maximum 5 per employee |
| **Schedule randomization** | Warning if same time slot is used 4+ consecutive days (to ensure variety) |
| **Duplicate products** | Warning if same product is scheduled twice on the same day |

### 16.5 Conflict Resolution & Bumping

When the auto-scheduler cannot schedule an urgent event because all qualified employees are busy, it may **bump** (displace) a lower-priority assignment:

**How bumping works:**
1. The scheduler calculates a priority score for each event (based on days until due date - lower = more urgent)
2. It looks for lower-priority events that could be displaced
3. It will NOT bump:
   - Events due within 2 days (too risky to displace)
   - Supervisor events (they're paired with Core events)
4. Maximum 3 bumps per event to prevent cascading chain reactions
5. Bumped events are tracked - you'll see what was bumped and why in the review screen

**Your role:** All bumps appear as pending schedules requiring your approval. You decide whether each bump is acceptable.

---

## 17. Common Workflows

### 17.1 Morning Routine

A typical morning workflow:

1. **Log in** - Session refreshes database automatically
2. **Check the Command Center** - Scan the deadline banner, quick stats, and urgent items
3. **Review rotation assignments** - Verify today's Juicer and Primary Lead are correct
4. **Run validation** - Click through to Daily Validation for today to check for issues
5. **Fix any issues** - Use the Fix Wizard to resolve conflicts
6. **Run auto-scheduler** (if needed) - For any unscheduled events due soon
7. **Review & approve** - Check pending schedules and approve good assignments
8. **Print paperwork** - Generate the Complete Daily Paperwork package
9. **Lock the day** - Once paperwork is printed, lock the date to prevent changes

### 17.2 Weekly Planning

At the start of each week (or at the end of the prior week):

1. **Open Weekly Validation** - Check the health score for the upcoming week
2. **Review each day** - Click through the day pills to see coverage
3. **Set rotations** - Verify Juicer and Primary Lead rotations are set for the week
4. **Run auto-scheduler with CP-SAT** - For optimal weekly coverage
5. **Review proposals** - Approve the scheduler's weekly plan
6. **Check health score again** - Aim for 85+ after approvals
7. **Address remaining issues** - Use Fix Wizard for any leftover warnings

### 17.3 Handling a Call-Out

When an employee calls in sick or can't make it:

1. **Record the absence** in Attendance (Team > Attendance)
2. **Check Daily View** for the affected date to see what events they were assigned to
3. **Reschedule affected events** - Use the reschedule button on each event to assign a replacement
4. **If the employee is the rotation Juicer or Lead:**
   - Add a **rotation exception** for the day
   - Or use **Quick Swap** on the Command Center
5. **If they had EDR paperwork printed:**
   - Use **Bulk EDR Reissue** in the Printing page to regenerate PDFs with the new employee's name
6. **Reprint affected paperwork** if already distributed

### 17.4 End-of-Day Scan-Out

At the end of each work day:

1. **Print the Scan-Out Checklist** (Tools > Printing > Scan-Out Checklist)
2. **Go to the store floor** with the checklist
3. **Scan each product** - Check off items as you scan them out
4. **Verify all items** are accounted for
5. **Report any issues** (missing items, cancelled events)
6. **Lock the day** to finalize the schedule

---

## 18. Troubleshooting

### Common Issues and Solutions

**"The auto-scheduler isn't scheduling some events"**
- **Cause:** No qualified/available employees exist for those events
- **Check:** Employee roles match event type requirements, availability is set correctly, daily/weekly limits aren't exceeded
- **Fix:** Add availability overrides, create new employees, or manually schedule with constraint override

**"Supervisor events aren't pairing with Core events"**
- **Cause:** Core and Supervisor events need matching reference numbers (adjacent 6-digit prefixes)
- **Check:** Verify event ref numbers are in the expected pairing format
- **Fix:** The Supervisor event should be on the same day as the Core event. Manually create if auto-pairing fails

**"I can't schedule events more than 3 days out"**
- **Cause:** The auto-scheduler only looks 3 days ahead by design
- **Fix:** Use manual scheduling (select the event and assign directly) for dates further out

**"Database refresh deleted my schedules"**
- **Cause:** This is by design - refresh re-fetches everything from Crossmark
- **Note:** Locally-approved schedules ARE preserved and restored after refresh
- **Prevention:** Always back up before manual refresh (`./backup_now.sh`)

**"EDR paperwork generation fails"**
- **Cause:** Walmart session expired, or events are cancelled in Walmart
- **Fix:** Re-authenticate with Walmart (see [Section 10.5](#105-walmart-edr-authentication)). Check if events are cancelled - unschedule cancelled events first

**"An employee is showing as unavailable but shouldn't be"**
- **Check:** Time-off requests, weekly availability, availability overrides, and company holidays
- **Fix:** The system checks in priority order (override > date-specific > time-off > weekly > holiday). Remove or adjust the blocking entry

**"I accidentally locked a day and need to make changes"**
- **Fix:** Go to Admin and unlock the day. Only administrators can unlock dates

**"The health score is low"**
- **Cause:** Multiple scheduling issues accumulated
- **Fix:** Use the Fix Wizard to systematically resolve each issue. Focus on critical issues first (worth 10 points each) before warnings (worth 3 points each)

---

## 19. Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` (or `Cmd+K`) | Open AI Assistant panel |
| `Escape` | Close modals and dropdown menus |
| `Tab` | Navigate between form fields |
| `Enter` | Submit forms |
| `Arrow Keys` | Navigate date pickers |

---

## 20. Glossary

| Term | Definition |
|------|------------|
| **Bump / Swap** | When the auto-scheduler displaces a lower-priority assignment to make room for a higher-priority one |
| **Condition** | An event's workflow status: Unstaffed, Scheduled, Staffed, In Progress, Completed, Cancelled, Expired |
| **Core Event** | A standard product demonstration event, typically 6.5 hours. The most common event type |
| **CP-SAT** | Constraint Programming / Satisfiability solver - an advanced scheduling algorithm that finds mathematically optimal solutions |
| **EDR** | Event Detail Report - a Walmart document containing detailed event instructions, product information, and barcodes |
| **Event Horizon** | The 4-month window of events the system considers (current date minus 1 month to plus 3 months) |
| **Fix Wizard** | A guided tool that identifies scheduling issues and suggests fixes with confidence scores |
| **Freeosk** | A free-standing sample kiosk event at Walmart |
| **Greedy Scheduler** | The default scheduling algorithm that assigns events one at a time based on priority order |
| **Health Score** | A 0-100 rating of schedule quality, calculated from the number of critical and warning issues |
| **Juicer Production** | A full-day (9-hour) juice bar operation event |
| **Left In Approved** | An event that Walmart shows as completed but hasn't been fully scanned out |
| **Locked Day** | A date that cannot be modified - used after paperwork is printed |
| **MFA** | Multi-Factor Authentication - the SMS code verification required for Walmart RetailLink access |
| **MVRetail** | The backend API system used by Crossmark for managing retail operations |
| **Override** | Bypassing normal scheduling constraints for exceptional situations |
| **Pending Schedule** | A proposed assignment from the auto-scheduler that requires user approval before taking effect |
| **Primary Lead** | The designated Lead Event Specialist for a given day, always assigned to Shift Block 1 |
| **Rotation** | A weekly recurring assignment pattern for Juicer and Primary Lead roles |
| **Rotation Exception** | A one-time override to the regular rotation for a specific date |
| **Scan-Out** | The end-of-day process of scanning products at Walmart to confirm they've been accounted for |
| **Schedule Exception** | See Rotation Exception |
| **Shift Block** | One of 8 time slots (staggered arrival times) used for Core events |
| **Supervisor Event** | A brief (5-minute) supervisory check event, always paired with a Core event and scheduled 30 minutes after the Core start time |
| **Superseded** | A schedule that was bumped/displaced by a higher-priority assignment |
| **Sync** | The process of sending/receiving data between the local database and external systems (Crossmark, Walmart) |
| **Unreported Event** | A scheduled event whose date has passed but hasn't been marked as completed |

---

*This manual is for PC Event Manager v2.0. For technical documentation, see `docs/CODEBASE_MAP.md`. For business rule details, see `docs/scheduling_validation_rules.md`.*
