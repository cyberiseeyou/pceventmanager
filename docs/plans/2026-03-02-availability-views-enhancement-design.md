# Availability Views Enhancement Design

**Date**: 2026-03-02
**Status**: Approved

## Problem

Two useful weekly planning views exist at `/dashboard/employee-availability` and `/dashboard/available-blocks` but are undiscoverable (no sidebar links), lack print support, and aren't integrated into the /printing hub.

## Existing Views

### Employee Availability (`/dashboard/employee-availability`)
- Weekly Sun-Sat grid showing employees available each day
- Checks: weekly availability pattern, overrides, time off, company holidays
- Has daily counts and a weekly total stat
- Powered by `WeeklyPlanningService.get_available_employees()`

### Available Schedule Blocks (`/dashboard/available-blocks`)
- Same as above, but additionally filters out employees already scheduled for main events (Core, Juicer Production, Juicer Deep Clean, or 4hr+ events)
- Shows who can still be assigned to a main event
- Powered by `WeeklyPlanningService.get_available_for_main_events()`

## Changes

### 1. Print Support on Both Views
- Add a Print button in the header of both templates
- Add `@media print` CSS to both templates: hide sidebar, nav, print button; optimize layout for paper

### 2. Sidebar Navigation
- Add two links under the "Tools" group in `base.html` sidebar
- "Employee Availability" → `/dashboard/employee-availability`
- "Available Blocks" → `/dashboard/available-blocks`

### 3. Printing Hub Integration
- Add two new sections to `/printing` page
- Each section fetches data from a new API endpoint and renders a printable weekly grid
- New API endpoints: `GET /printing/employee-availability` and `GET /printing/available-blocks`

## Files to Modify

| File | Change |
|------|--------|
| `app/templates/dashboard/employee_availability.html` | Add print button + `@media print` CSS |
| `app/templates/dashboard/available_blocks.html` | Add print button + `@media print` CSS |
| `app/templates/base.html` | Add sidebar links under Tools group |
| `app/routes/printing.py` | Add two API endpoints |
| `app/templates/printing.html` | Add two new print sections |

## No Changes Needed

- `WeeklyPlanningService` — already has the right logic
- `app/routes/dashboard.py` — existing routes are correct
- Database models — no schema changes
