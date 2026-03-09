# Auto-Balance Weekly Schedule

**Date**: 2026-03-06
**Status**: Approved

## Overview

A one-click rebalance feature for a selected week that redistributes Core events to achieve:
1. **Employee workload balance** — Even out Core event counts across eligible employees
2. **Time slot balance** — Distribute Core events evenly across the 4 daily time slots (7:00, 9:00, 11:00, 13:00)

Changes are applied immediately to posted schedules. All existing scheduling constraints are respected (availability, time-off, rotations, max hours, locked days).

## Scope

- **Event types**: Core only
- **Time range**: Single week (Monday-Sunday)
- **Constraints**: All existing constraints enforced (same as auto-scheduler)
- **Approval flow**: Fully automatic (no preview/approve step)

## Trigger Points

- **Weekly validation page**: Always-visible "Rebalance Week" button
- Button is visually promoted (badge/highlight) when RULE-024 workload imbalance or shift balance warnings are detected
- Rebalances the currently viewed week

## Algorithm

### Phase 1: Time Slot Rebalancing (per day)

For each day in the week:
1. Count Core events per time slot
2. Identify overloaded slots (above average) and underloaded slots (below average)
3. Move Core events from overloaded to underloaded slots
4. Validate each move against constraints (employee availability at new time, no conflicts)

### Phase 2: Employee Workload Rebalancing (across week)

1. Count Core events per eligible employee for the week
2. Calculate target = total Core events / eligible employee count
3. Identify overloaded employees (above target) and underloaded employees (below target)
4. For each overloaded employee, find a Core event that can be reassigned to an underloaded employee who passes all constraint checks
5. Execute swaps until spread (max - min) <= 1 or no valid swaps remain

### Constraints Checked Per Move

- Employee availability on the target date/time
- No time-off conflicts
- Rotation assignment compatibility
- Max daily/weekly hours not exceeded
- Locked day check (skip locked days entirely)
- No double-booking (employee not already scheduled at that time)

## Backend

### New Service: `app/services/schedule_rebalancer.py`

- `rebalance_week(week_start_date)` -> returns:
  ```python
  {
      'moves_made': int,
      'time_slot_moves': int,
      'employee_swaps': int,
      'skipped_reasons': list,
      'details': list  # individual move descriptions
  }
  ```
- Uses `ConstraintValidator` for all move validation
- Operates on posted `Schedule` records (not `PendingSchedule`)

### New Route

`POST /api/rebalance-week` with body `{ "week_start": "YYYY-MM-DD" }`

Returns summary of changes made.

## Frontend

### Weekly Validation Page

- "Rebalance Week" button in the page header/toolbar area
- Default state: standard button
- When imbalance issues detected: highlighted with warning icon/badge
- On click: loading spinner, call API, toast notification with summary, reload validation results

## Dependencies

- `app/services/constraint_validator.py` — validate each proposed move
- `app/services/weekly_validation.py` — RULE-024 detection drives button highlighting
- `app/models/schedule.py` — Schedule model for reading/updating posted schedules
- `app/routes/api.py` — new endpoint
- `app/templates/dashboard/weekly_validation.html` — button UI
- `app/static/js/pages/weekly-validation.js` — button handler
