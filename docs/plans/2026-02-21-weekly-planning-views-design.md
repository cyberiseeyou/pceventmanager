# Weekly Planning Views Design

**Date**: 2026-02-21
**Status**: Approved

## Overview

Two new weekly dashboard views for capacity planning and scheduling action:

1. **Employee Availability** (`/dashboard/employee-availability`) - Shows all available employees per day for capacity forecasting.
2. **Available Schedule Blocks** (`/dashboard/available-blocks`) - Shows employees still open for main event assignment.

## View 1: Employee Availability

**Purpose**: Capacity planning. See how many people are available each day to forecast staffing shortfalls.

**Route**: `/dashboard/employee-availability?start_date=YYYY-MM-DD`

**Layout**:
- Purple gradient header with week navigation (prev/next/today), matching existing weekly validation style.
- 7-column grid (Sun-Sat), one column per day.
- Each column lists employee names who are available that day.
- Column headers show day name, date, and count of available employees.
- Store closure days show "Store Closed" instead of employee names.

**Availability logic** (employee shows if ALL are true):
1. `EmployeeWeeklyAvailability` for that weekday is `True` (or no record, default=True)
2. No `EmployeeAvailabilityOverride` marking that weekday `False` for a range covering that date
3. No `EmployeeTimeOff` where `start_date <= date <= end_date`
4. No `CompanyHoliday` on that date
5. Employee `is_active = True`

## View 2: Available Schedule Blocks

**Purpose**: Scheduling action. See who can still take a main event each day for manual scheduling.

**Route**: `/dashboard/available-blocks?start_date=YYYY-MM-DD`

**Layout**: Same 7-column weekly grid as View 1 but further filtered.

**"Main event" definition** - an employee already has a main event if scheduled to:
- Event type in explicit list: `Core`, `Juicer Production`, `Juicer Deep Clean`
- OR any event with `estimated_time >= 240` minutes (>= 4 hours)

**Employee shows if ALL are true**:
1. Passes all availability checks from View 1
2. NOT already scheduled to a "main event" on that day

**Non-blocking events**: Digital Setup, Digital Refresh, Digital Teardown, Freeosk, Supervisor, Juicer Survey, Digitals, Other - these do NOT exclude an employee from this view.

## Technical Approach

### Backend
- **Service**: `app/services/weekly_planning_service.py` with shared availability logic
  - `get_available_employees(start_date, end_date)` - returns dict of date -> list of available employees
  - `get_available_for_main_events(start_date, end_date)` - same but filtered by main event scheduling
- **Routes**: Added to `app/routes/dashboard.py`
  - `employee_availability()` - View 1
  - `available_blocks()` - View 2
- Week alignment: Sunday start, same pattern as weekly validation

### Frontend
- **Templates**: `app/templates/dashboard/employee_availability.html`, `app/templates/dashboard/available_blocks.html`
- Reuse existing dashboard CSS patterns (gradient header, cards, responsive grid)
- No separate JS files needed - these are read-only display views

### Navigation
- Added to the scheduling dropdown in `base.html` between "Weekly Validation" and "Left in Approved"

### Data queries
- Uses `get_models()` factory pattern
- Batch-loads availability, time off, holidays, and schedules for the full week in single queries (not per-day)
