# Reissue Logic for Daily View

**Date:** 2026-01-26
**Type:** Feature Addition

Implemented dynamic "Reissue" vs "Reschedule" button logic for events in the daily schedule view.

**Business Logic:**
- Events show "Reissue" button (orange) when:
  - Event condition is 'Submitted', OR
  - Current date is on or after the event's due date
- Events show "Reschedule" button (blue) otherwise

**Files Modified:**

1. **`app/routes/api.py`** (lines 395-396)
   - Added `condition` and `due_datetime` fields to event dictionary in `get_daily_events` API endpoint
   - Enables frontend to determine button type based on event state

2. **`app/routes/main.py`** (line 694)
   - Added `today = datetime.now().date()` to capture current date
   - Passed `today` to template context for date comparison
   - Fixed: Used `datetime.now().date()` instead of `date.today()` to avoid naming conflict with route parameter

3. **`app/templates/daily_view.html`**
   - Added `data-today` attribute to `.daily-view-container` (lines 77-78)
   - Created complete "Reissue Event" modal with:
     - Event info display
     - Date and time inputs
     - Employee selector
     - "Include Previous Responses" checkbox
     - Submit and cancel buttons
   - Added CSS styling for reissue button:
     - Orange color (#f97316) to differentiate from blue Reschedule button
     - Forced `width: 100%` for both buttons to match sizing
   - Updated CSS cache buster to timestamp: `?v=1769471990`

4. **`app/static/js/pages/daily-view.js`**
   - **Constructor** (lines 10-26): Added `this.today` to store today's date from DOM

   - **`shouldShowReissue()` method** (lines 1092-1135):
     - Helper function to determine if event should show Reissue vs Reschedule
     - Checks if `event.condition === 'Submitted'`
     - Compares today's date with event's due date using string comparison (avoiding timezone issues)
     - **Bug Fix**: Changed from Date object comparison to string comparison to avoid timezone issues
       - Old: `new Date("2026-01-26")` interpreted as UTC midnight → Jan 25 7PM EST
       - New: Direct string comparison of YYYY-MM-DD format dates

   - **`createEventCard()` method** (lines 869-963):
     - Added `isReissue`, `buttonLabel`, `buttonClass` variables
     - Dynamically sets button class (`btn-reissue` or `btn-reschedule`)
     - Dynamically sets button label and emoji
     - Added `data-event-condition` and `data-due-datetime` attributes to event cards

   - **`attachEventCardListeners()` method** (lines 988-1007):
     - Added event listener for `.btn-reissue` buttons

   - **`handleReissue()` method** (lines 1278-1302):
     - Extracts event data from card
     - Opens reissue modal with pre-populated data

   - **`openReissueModal()` method** (lines 1304-1328):
     - Populates modal fields
     - Loads available employees
     - Displays modal

   - **`closeReissueModal()` method** (lines 1330-1335):
     - Hides reissue modal

   - **Reissue form submission handler** (lines 3319-3371):
     - Handles form submit event
     - Calls `/api/reissue-event` endpoint
     - Handles success/error responses
     - Reloads daily view on success

   - **`createEventListRow()` method** (lines 821-847):
     - Updated list view to use same reissue logic
     - Added `data-event-condition` and `data-due-datetime` attributes
     - Dynamically sets button class for list view

   - **`attachEventListListeners()` method** (lines 849-870):
     - Added event listener for `.btn-reissue-list` buttons in list view

5. **`app/static/css/pages/daily-view.css`** (lines 1171-1175)
   - Added `.btn-reissue` to responsive CSS rule alongside `.btn-reschedule`
   - Ensures both buttons have `width: 100%` in mobile/responsive layouts

**Bug Fixes:**
- Fixed timezone issue in `shouldShowReissue()`: Changed from Date object comparison to string comparison
- Fixed naming conflict in `main.py`: Used `datetime.now().date()` instead of `date.today()`
- Fixed button sizing: Both Reissue and Reschedule buttons now have consistent width across all screen sizes

**Color Scheme:**
- Reschedule button: Blue (primary color)
- Reissue button: Orange (#f97316) with darker orange hover (#ea580c)

**Testing:**
- Event with `condition='Submitted'` → Shows "Reissue" (orange)
- Event with `due_datetime` = today or past → Shows "Reissue" (orange)
- Event with `due_datetime` in future and `condition='Scheduled'` → Shows "Reschedule" (blue)
- Works in both card view and list view

**API Integration:**
- Reissue action calls `/api/reissue-event` endpoint
- Accepts: `schedule_id`, `employee_id`, `schedule_date`, `schedule_time`, `include_responses`
- Reschedule action continues to call `/api/event/{id}/reschedule` endpoint
