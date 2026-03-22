# PC Events — User Guide

**Version 3.0** | **Updated: March 21, 2026**

This guide covers how to use the PC Events app for all three roles: **Specialist**, **Lead**, and **Supervisor**. If you're looking for system administration or developer documentation, see `USER_MANUAL.md` or `CODEBASE_MAP.md`.

---

## Table of Contents

1. [Installing the App](#1-installing-the-app)
2. [Logging In](#2-logging-in)
3. [Specialist Guide](#3-specialist-guide)
4. [Lead Guide](#4-lead-guide)
5. [Supervisor Guide](#5-supervisor-guide)
6. [Common Features](#6-common-features)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Installing the App

PC Events is a Progressive Web App (PWA). You can add it to your home screen for quick access — it works like a native app.

### iPhone (Safari)

1. Open Safari and go to the PC Events URL
2. Tap the **Share** button (square with arrow pointing up)
3. Scroll down and tap **"Add to Home Screen"**
4. Tap **Add**

### Android (Chrome)

1. Open Chrome and go to the PC Events URL
2. You should see an **"Install PC Events"** banner at the bottom
3. Tap **Install**
4. If no banner appears, tap the **⋮ menu** → **"Install app"** or **"Add to Home Screen"**

Once installed, the app appears on your home screen with the PC Events icon. It opens in full-screen mode without browser navigation bars.

### Offline Support

If you lose internet connection, the app shows an **"Offline"** banner at the top and displays cached data when available. When the connection returns, the banner disappears automatically.

---

## 2. Logging In

### Employee Login (Specialists & Leads)

1. Go to the **Team Login** page
2. Enter your **Employee ID** (just the numbers — no "US" prefix needed)
3. Enter the **4-digit PIN** your supervisor gave you
4. Tap **Sign In**

You'll land on your **My Dashboard** page.

> **Don't have a PIN?** Ask your supervisor to set one up for you. You cannot create your own account.

### Supervisor Login

1. Go to the supervisor login page (link at bottom of Team Login: **"Supervisor? Use Crossmark login"**)
2. Enter your **Crossmark username and password**
3. Click **Log In**
4. Wait for the loading screen to sync data from Crossmark

You'll land on the **Daily View** for today.

### Session Timeout

- Your session stays active as long as you're using the app
- After **10 minutes of inactivity**, you'll be logged out automatically
- Sessions expire after **24 hours** regardless

### Logging Out

- **Mobile**: Open the sidebar (hamburger menu ☰) → tap **Logout** at the bottom
- **Desktop**: Click your name in the top right → click **Logout**

---

## 3. Specialist Guide

As a specialist, you have four pages available:

### 3.1 My Dashboard

Your home screen after logging in. Shows everything at a glance.

**Today's Schedule Banner**
- If you're working today: lists your events with times and types
- If you're off today: shows your **next upcoming event** with its date
- If nothing is scheduled: shows a "No events — enjoy your day off" message

**This Week Stats**
Three numbers for the current week (Sunday–Saturday):
- **Scheduled Hours** — total estimated hours
- **Days Scheduled** — how many days you're working
- **Events** — total number of events

**Weekly Calendar**
A 7-day grid showing your schedule for the week. Each event appears as a color-coded pill:

| Color | Event Type |
|-------|-----------|
| Blue | Core |
| Purple | Juicer |
| Teal | Digital |
| Amber | Freeosk |
| Pink | Supervisor |
| Gray | Other |

Use the **← →** arrows to navigate between weeks. Today is highlighted.

### 3.2 My Events

A simple weekly list of your schedule. Each day shows:
- **Time** — when the event starts
- **Event Name** — the project/event name
- **Type Badge** — color-coded event type

Today's section is highlighted and labeled "(Today)". Days with no events show "No events." Use **← →** arrows to change weeks.

### 3.3 Monthly Schedule

A full-month calendar view of your schedule.

**On desktop**: A standard 7-column grid. Each day cell shows:
- A count badge (number of events)
- Up to 4 colored dots showing event types
- Click a day to expand a **detail panel** showing each event's time, name, type, and estimated hours

**On mobile**: Automatically switches to a scrollable list showing only days with events.

Use **← →** to change months. Tap **Today** to jump back.

### 3.4 My Time Off

**Requesting Time Off**
1. Select a **From** date and **To** date (both default to today)
2. Tap **Submit Request**
3. A green success message appears — the page reloads automatically

> You cannot request dates in the past. The end date automatically adjusts if you change the start date.

**Viewing Your Requests**

Below the form, all your time-off requests are listed (newest first). Each shows:
- **Date range** or single date
- **Status badge**: Pending (amber), Approved (green), or Denied (red)
- **Denial reason** (if denied) shown in red text

---

## 4. Lead Guide

As a lead, you have everything specialists have **plus** the Team Daily View page and an extra dashboard section.

### 4.1 My Dashboard — Lead Extras

Your dashboard is the same as the specialist version, plus:

**Upcoming Approved Time Off** — A panel at the bottom showing all team members with approved time off in the next 30 days. Each entry shows the employee name and date range.

### 4.2 Team Daily View

A read-only view of the **entire team's** schedule for a specific day. Has three tabs:

**Schedule Tab**
A table showing every scheduled employee for the day:
- **Time** — event start time
- **Employee** — who's assigned
- **Event** — the event name and type

**Attendance Tab**
Shows attendance for each scheduled employee:
- **Existing records** appear locked with a status badge (On Time, Late, Called In, etc.) and who recorded it
- **Unrecorded employees** show a dropdown to record their status:
  - On Time
  - Late
  - Called In
  - No Call/No Show
  - Excused Absence

> Once you record attendance, it locks — you cannot change it. Contact your supervisor if a correction is needed.

**Notes Tab**
- View notes attached to this day
- Add a new note using the text area (max 500 characters)
- Delete notes you created

**Navigation**: Use **← →** buttons to move between days. Tap **Today** to jump to the current date.

### 4.3 Lead Attendance Calendar

Access via sidebar: a monthly calendar view where you can:
- See team attendance status for each day (color-coded cells)
- Filter by specific employee using the dropdown
- Click any day to view and record attendance details

---

## 5. Supervisor Guide

Supervisors have full access to all features. Here's a summary of the key tools organized by sidebar section.

### 5.1 Schedule Management

| Page | What You Can Do |
|------|----------------|
| **Daily View** | View/edit the day's schedule, assign employees to events, reschedule, swap assignments |
| **Calendar** | Month-view of all events with click-to-schedule |
| **Auto-Scheduler** | Run the automated scheduler (CP-SAT or Greedy engine), review proposed assignments, approve/reject |
| **Notifications** | View short-notice assignment alerts, mark employees as notified |

### 5.2 Events Management

| Page | What You Can Do |
|------|----------------|
| **All Events** | Search, filter, and manage all events. Tabs: Unstaffed, Scheduled, Submitted, Past Due, Cancelled |
| **Unreported Events** | Events that haven't been reported to Walmart |
| **Left in Approved** | Events still in Approved status (need action) |
| **Lost Demos** | Confirm events as lost demos, export CSV |

### 5.3 Team Management

| Page | What You Can Do |
|------|----------------|
| **Employees** | Add/edit employees, set PINs for login access, manage availability |
| **Attendance** | Monthly attendance calendar, record/edit attendance |
| **Availability** | View/manage time-off requests (approve, deny with reason), set availability overrides |
| **Analytics** | Employee performance and workload analytics |

### 5.4 Setting Up Employee Login

To give a specialist or lead access to the app:

1. Go to **Employees** page
2. Find the employee
3. Click **Set PIN** (or the key icon)
4. Enter a 4-digit PIN
5. Share the PIN with the employee

To revoke access, click **Revoke Access** on the same page.

### 5.5 Managing Time-Off Requests

Go to **Availability** page → **Pending Approvals** tab:

1. Review each request (employee name, dates, submitted date)
2. Click **Approve** or **Deny**
3. If denying, enter an optional reason

All requests (pending, approved, denied) remain visible in the **Time Off Requests** tab. Use the **Status Filter** dropdown to filter by status.

### 5.6 Auto-Scheduler

1. Go to **Auto-Scheduler** page
2. Choose solver: **CP-SAT** (optimal, recommended) or **Greedy** (faster fallback)
3. Click **Run Auto-Schedule**
4. Review the proposed assignments on the **Review** page
5. Edit individual assignments if needed
6. Click **Approve All** to finalize

> **Emergency Mode**: Check "Emergency mode" before running to allow scheduling within the 3-day buffer for urgent events.

### 5.7 Tools

| Tool | Purpose |
|------|---------|
| **Printing** | Generate daily paperwork PDFs (schedules, item numbers, EDR reports) |
| **Weekly Validation** | Check the week's schedule against business rules, get health score |
| **Employee Availability** | Grid showing who's available each day |
| **Available Blocks** | Open scheduling slots by day and shift block |
| **Reports** | 7 report types: Event Stats, Employee Schedules, Event Breakdown, Workload, Attendance, Coverage, Time Off |
| **Scan-Out Checklist** | End-of-day verification checklist |
| **Demo Supplies** | Inventory management for demonstration supplies |

### 5.8 Admin

| Setting | Purpose |
|---------|---------|
| **Settings** | System configuration, API credentials |
| **Event Time Settings** | Set default start/end times per event type and shift block |
| **Rotations** | Configure weekly rotation assignments (Juicer, Digital, etc.) |
| **Refresh Database** | Pull latest event data from Crossmark API |

---

## 6. Common Features

### Schedule Change Notifications

If your schedule changes, you may receive a **browser notification** saying "Schedule Updated." This works when:
- You've installed the app or allowed notifications in your browser
- You're on the My Dashboard page (specialists/leads)

### AI Assistant (Supervisors Only)

Click the **✨** button or press **Ctrl+K** to open the AI assistant. You can ask questions about schedules, employees, and events in plain language.

### PWA Features

- **Works offline**: Cached pages still load when you lose connection
- **Push notifications**: Schedule changes can trigger browser notifications
- **Full-screen mode**: When installed, the app runs without browser UI

---

## 7. Troubleshooting

| Problem | Solution |
|---------|----------|
| **Can't log in** | Check your Employee ID (numbers only, no "US") and PIN. If you forgot your PIN, ask your supervisor. |
| **"Session expired" message** | Your session timed out after 10 minutes of inactivity. Log in again. |
| **Page won't load** | Check your internet connection. If offline, the app shows cached data. |
| **Schedule not showing** | Make sure you're looking at the correct week/month. Use the Today button to reset. |
| **Time-off request denied** | Check the red status badge for the denial reason. Submit a new request with different dates if needed. |
| **Can't find a page** | On mobile, check the **sidebar** (☰ menu) — some pages are only there, not in the bottom nav. |
| **"Install PC Events" banner not showing** | On iPhone, use Safari. On Android, use Chrome. Other browsers may not support PWA install. |
| **Attendance record locked** | Once attendance is recorded, it can't be changed by leads. Contact your supervisor. |

---

**Need more help?** Contact your Club Supervisor.
