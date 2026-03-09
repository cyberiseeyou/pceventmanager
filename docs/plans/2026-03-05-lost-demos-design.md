# Lost Demos Feature Design

**Date**: 2026-03-05
**Status**: Approved

## Overview

Add a "Lost Demos" category to the approved events page for unassigned events with past due dates, a weekly Lost Demo tracking list, and a lost demo rate metric in reports.

## Requirements

1. On the approved events page, events that are **unassigned AND past due** appear in a new "Lost Demos" category instead of "Schedule First, Then Roll"
2. Each Lost Demo has a "Confirm Lost" button that records it on a weekly lost demo list
3. Confirmed events are removed from the approved events page (undo-able)
4. Weekly Lost Demo list page under Events nav group — view by week (Sun–Sat), export CSV, print
5. No duplicate events on the lost demo list (DB unique constraint)
6. Reports page shows lost demo rate (lost / total events) for selected week

## Data Model

New `LostDemo` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer PK | Auto-increment |
| `event_ref_num` | String FK → Event.project_ref_num | The lost event (UNIQUE) |
| `week_start_date` | Date | Sunday of the week the due date falls in |
| `confirmed_at` | DateTime | When user confirmed |
| `notes` | Text (nullable) | Optional note from user |

- Unique constraint on `event_ref_num` prevents duplicates
- `week_start_date` computed from `Event.due_datetime` (Sunday of that week)

## Approved Events Page Changes

### Categorization Logic (approved-events.js)

Current 3 categories become 4:

1. **Scan-Out** — scheduled + assigned + date ≤ today (unchanged)
2. **Roll Scheduled** — scheduled + needs_rolling + future date (unchanged)
3. **Lost Demos** — NOT assigned + due_datetime < today + NOT in LostDemo table (NEW)
4. **Schedule First, Then Roll** — everything else (reduced scope)

### API Changes

The `/dashboard/api/approved-events` endpoint adds a `confirmed_lost_event_refs` list to the response so JS can filter out already-confirmed events.

### UI

- Lost Demos panel between Roll Scheduled and Schedule First
- Red/orange warning styling
- Each card: Event ID, Name, Due Date, "Confirm Lost" button
- Summary card count updates

## New API Endpoints

```
POST /api/events/<ref_num>/confirm-lost    → Create LostDemo record
DELETE /api/events/<ref_num>/confirm-lost   → Undo (delete LostDemo record)
GET /api/lost-demos?week_start=YYYY-MM-DD  → List for a week
GET /api/lost-demos/export?week_start=YYYY-MM-DD → CSV export
```

## Weekly Lost Demo List Page

- Route: `/events/lost-demos`
- Week selector with prev/next navigation, defaults to current week
- Table: Event ID, Event Name, Event Type, Due Date, Confirmed Date, Notes
- "Undo" button per row (DELETE endpoint)
- Export CSV button
- Print button with print-friendly CSS

## Navigation

Add under **Events** group in sidebar (`base.html`):
- After "Left in Approved"
- Icon: `event_busy` (Material Symbols)
- Label: "Lost Demos"

## Reports Integration

Add "Lost Demo Rate" to Event Statistics report:
- Lost % = (LostDemo count for week / Total Event count for week) × 100
- Displayed as a metric card in the report
- Uses same Sun–Sat week boundary

## Key Decisions

- **Both conditions required**: Event must be unassigned AND past due to be Lost Demo
- **Week assignment**: Based on event's due date, not confirmation date
- **Undo supported**: Deleting LostDemo record returns event to approved page
- **Confirmed events removed**: From approved page on next refresh
- **Approach**: Dedicated LostDemo table (not Event model modification)
