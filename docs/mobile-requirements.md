# Mobile Requirements - PCEventManager

## Target Users
- **Supervisor:** Club Supervisor - managing schedules on the floor (full access)
- **Lead Specialist:** Lead Event Specialist - viewing team schedules, managing own schedule (read-only team view)
- **Specialist:** Demo Event Specialists & Juice Baristas (10-20 people) - viewing own schedule and requesting time off

---

## Priority Pages for Mobile (Ranked)

### Tier 1 - Must Work Perfectly on Mobile
These are used multiple times daily, often while walking the floor.

1. **Daily Schedule View** (`/schedule/daily/<date>`)
   - See who's working what event today at a glance
   - Swipeable between days
   - Quick tap to see event details

2. **Command Center Dashboard** (`/dashboard/command-center`)
   - Morning check: what needs attention today
   - Urgent items, unscheduled events, deadline countdowns
   - Quick action buttons (approve, assign, dismiss)

3. **Daily Validation** (`/dashboard/daily-validation`)
   - Verify today's schedule is complete
   - See gaps and warnings
   - Quick-fix actions

4. **Scan-Out Checklist** (`/dashboard/scan-out-checklist`)
   - End-of-day LIA scan-out confirmation
   - Checkbox-style completion tracking

### Tier 2 - Should Work on Mobile
Used a few times per week, sometimes on the go.

5. **Unscheduled Events** (`/events`, `/unscheduled`)
   - Browse events needing assignment
   - Filter and search
   - Tap to schedule

6. **Schedule Event** (`/schedule/<event_id>`)
   - Assign employee to event
   - Select time, see conflicts
   - Submit to API

7. **Calendar View** (`/calendar`)
   - Monthly overview of event coverage
   - Tap day to drill into details

8. **Attendance** (`/attendance`)
   - Mark present/absent/late for today
   - View monthly calendar

9. **Employee List** (`/employees`)
   - Quick lookup of employee info
   - See availability status

### Tier 3 - Desktop Preferred, Mobile Acceptable
Used weekly or less, typically at a desk.

10. **Auto-Scheduler** (`/auto-schedule/`)
    - Run and review auto-assignments
    - Approve/reject proposals

11. **Reports** (`/reports/`)
    - View/export reports
    - Readable but not primary mobile use

12. **Printing** (`/printing/`)
    - Generate PDFs
    - Desktop-oriented workflow

13. **Inventory** (`/inventory/`)
    - Supply management
    - Order tracking

14. **Settings** (`/settings`)
    - Configuration changes
    - Rare use

15. **Help** (`/help/`)
    - Reference documentation
    - Readable on mobile

---

## Mobile-Specific Requirements

### Navigation
- Bottom tab bar on mobile with 4-5 primary tabs:
  - **Today** (daily schedule)
  - **Events** (unscheduled/all events)
  - **Dashboard** (command center)
  - **Team** (employees)
  - **More** (settings, reports, help, etc.)
- Standard top navbar on desktop (keep existing)
- Hamburger menu NOT preferred (bottom tabs are more thumb-friendly)

### Interactions
- All tap targets minimum 48x48px
- Swipe left/right for day navigation on schedule views
- Pull-to-refresh on data pages
- Long-press for context menus (edit, reassign, unschedule)

### Offline Capabilities (Nice-to-Have, Not Critical)
- Wi-Fi is reliable in-store, so offline is low priority
- Basic service worker caching for static assets (CSS, JS, images)
- Show "offline" indicator if connection drops
- Full offline schedule viewing deferred to later phase

### Notifications
- Push notification when schedule changes affect you (future phase)
- Badge count on "Events" tab for unscheduled events

### Performance
- Schedule views must load in under 2 seconds on 4G
- Lazy-load non-critical content (reports, history)

---

## Role-Based Views (3 Tiers)

### Supervisor (Club Supervisor)
Full access to everything:
- All scheduling controls (assign, reassign, approve, auto-schedule)
- Employee management (add/edit/terminate)
- Attendance marking for all employees
- Settings, credentials, sync administration
- Reports and exports
- Printing and paperwork generation
- Inventory management

### Lead Event Specialist
Read-only team view + own schedule management:
- View own schedule and assignments
- View **everyone else's** schedule (read-only, no changes)
- View daily schedule for the whole team
- Request time off
- View rotation assignments
- **Cannot** modify schedules, reassign events, or approve proposals

### Event Specialist / Juice Barista
Own schedule only:
- View own schedule and assignments
- See what events they are scheduled to (details, times, locations)
- Request time off
- View own rotation assignment
- **Cannot** see other employees' schedules

---

## Device Targets

- **Primary:** Budget Android phones (~360-400px wide, Chrome browser)
  - Test at: 360x640 (common budget Android), 375x667, 412x915
- **Secondary:** iPhones (Safari)
  - Test at: 375x667 (iPhone SE), 390x844 (iPhone 14)
- **Tablet:** Not a primary target, but should be usable
  - Test at: 768x1024 (iPad Mini)
- **Performance target:** Must be snappy on low-end devices — minimize JS, avoid heavy animations, lazy-load non-critical content

---

## Questions Confirmed

1. **Which page do you open first each morning?**
   - _Answer: Daily view or Command Center dashboard (both Tier 1)_

2. **Do your specialists need to see the app on their phones?**
   - _Answer: Yes. 3 role tiers: Supervisor (full access), Lead Specialist (read-only team view + own schedule), Specialist (own schedule only + time-off requests)_

3. **Do you use the app while walking the store floor?**
   - _Answer: Both. Mostly at desk/back office, but needs to make schedule changes and view times on the floor too. Mobile must support editing, not just viewing._

4. **Most common quick action on mobile?**
   - _Answer: All of these — check who's working an event, reassign someone last-minute, view event start/end times. Mobile must support quick lookups AND quick edits._

5. **Wi-Fi reliability in-store?**
   - _Answer: Reliable throughout the store. Offline support is nice-to-have, not critical. Focus on fast loading over offline caching._

6. **Devices?**
   - _Answer: Mostly budget Android phones. Test at 360px width as minimum._

7. **Bottom nav tabs (Today, Events, Dashboard, Team, More)?**
   - _Answer: Seems fine — will iterate based on real usage._

8. **How should specialist login/roles work?**
   - _Answer: Focus on mobile layout first. Design templates with role-awareness (CSS classes like `.supervisor-only`) but implement role-based auth as a separate phase after mobile conversion is done._
