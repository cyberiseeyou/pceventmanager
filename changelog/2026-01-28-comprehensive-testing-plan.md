# Comprehensive Testing Plan - UI/UX Implementation

**Date:** 2026-01-28
**Type:** Testing & Verification
**Status:** 🔄 In Progress

---

## Overview

This document outlines the comprehensive testing plan for all UI/UX improvements implemented across Phases 1-5. The goal is to verify:
1. **Zero regressions** - All existing functionality preserved
2. **New features working** - Toast notifications, loading states, validation, etc.
3. **Accessibility compliance** - WCAG 2.1 AA standards met
4. **Cross-browser compatibility** - Works in all supported browsers
5. **Mobile responsiveness** - Touch targets, text sizes, layouts

---

## Critical Workflows to Test

### 1. Daily View - Primary Workflow

**Navigation & Date Selection:**
- [ ] Load daily view for today
- [ ] Navigate to previous day (← arrow)
- [ ] Navigate to next day (→ arrow)
- [ ] Verify loading overlay appears during navigation
- [ ] Verify data loads correctly for selected date
- [ ] Keyboard shortcut: Press ← for previous day
- [ ] Keyboard shortcut: Press → for next day
- [ ] Keyboard shortcut: Press 't' to go to today

**Event Display:**
- [ ] Events display in event cards (card view)
- [ ] Text is readable (14px minimum)
- [ ] Padding is comfortable (12px)
- [ ] Employee names are prominent (15px bold)
- [ ] Times display correctly with Core badges
- [ ] Status badges show correct colors
- [ ] Overdue badges appear when applicable
- [ ] Sales tool links work (if present)

**Toast Notifications:**
- [ ] No alert() dialogs appear anywhere
- [ ] Success toast shows green with checkmark
- [ ] Error toast shows red with X icon
- [ ] Warning toast shows orange
- [ ] Toasts auto-dismiss after timeout
- [ ] Multiple toasts stack correctly
- [ ] Screen reader announces toast messages

**Loading States:**
- [ ] Buttons show spinner during operations
- [ ] Button text changes to "Loading..." or similar
- [ ] Buttons disabled during operations
- [ ] Loading overlay shows for date changes
- [ ] Container loading spinners appear during data fetch
- [ ] aria-busy="true" set during operations

---

### 2. Event Reschedule Flow

**Opening Reschedule Modal:**
- [ ] Click "Reschedule" button on event card
- [ ] Modal opens with correct event information
- [ ] Modal title is "Reschedule Event"
- [ ] Close button (×) visible in header
- [ ] Focus trapped inside modal
- [ ] Escape key closes modal
- [ ] Background overlay prevents interaction

**Form Interaction:**
- [ ] Date field populated with current date
- [ ] Time field populated with current time
- [ ] Employee dropdown loads available employees
- [ ] Current employee pre-selected in dropdown
- [ ] Time dropdown appears if event has time restrictions
- [ ] Override constraints checkbox available
- [ ] All fields have proper labels with * for required

**Form Validation:**
- [ ] Date field shows error if empty and blurred
- [ ] Time field shows error if invalid format
- [ ] Employee field shows error if not selected
- [ ] Validation messages appear in red below fields
- [ ] Invalid fields have red border
- [ ] Valid fields have green border (after validation)
- [ ] Form cannot submit with validation errors

**Submitting Reschedule:**
- [ ] Click "Reschedule" button
- [ ] Button shows loading spinner
- [ ] Button text changes to "Rescheduling..."
- [ ] Button disabled during submission
- [ ] On success: Toast notification appears
- [ ] On success: Modal closes automatically
- [ ] On success: Daily view refreshes with new data
- [ ] On error: Error toast appears with message
- [ ] On error: Modal stays open
- [ ] On conflict (409): Conflict dialog appears with override option

**ApiClient Usage:**
- [ ] No raw fetch() calls executing
- [ ] CSRF token included automatically
- [ ] Request timeout handled (30s)
- [ ] Network errors show user-friendly message
- [ ] Retry logic works for failed requests

---

### 3. Event Reissue Flow

**Opening Reissue Modal:**
- [ ] Click "Reissue" button (orange) on overdue/past event
- [ ] Modal opens with "Reissue Event" title
- [ ] Event information displays correctly
- [ ] Form fields pre-populated

**Reissue Form:**
- [ ] Date field editable
- [ ] Time field editable
- [ ] Employee dropdown loads correctly
- [ ] "Include Previous Responses" checkbox available
- [ ] Checkbox has help text below it

**Submitting Reissue:**
- [ ] Submit button shows loading state
- [ ] ApiClient used (no raw fetch)
- [ ] Success toast appears on completion
- [ ] Modal closes automatically
- [ ] Daily view refreshes
- [ ] Error handling works correctly

---

### 4. Employee Change Flow

**Opening Change Employee:**
- [ ] Click "More Actions" dropdown (⋮)
- [ ] Dropdown opens with menu items
- [ ] Click "Change Employee"
- [ ] Available employees load in dropdown
- [ ] Current employee shows in selection

**Conflict Detection:**
- [ ] Submit employee change
- [ ] If conflicts exist, conflict dialog appears
- [ ] Conflicts listed with severity icons
- [ ] Option to override conflicts shown
- [ ] Hard conflicts (✕) vs soft conflicts (⚠️)

**Successful Change:**
- [ ] Loading state shows on button
- [ ] Success toast appears
- [ ] Event card updates with new employee
- [ ] No page reload required

---

### 5. Event Type Change Flow

**Opening Change Event Type:**
- [ ] Click "More Actions" → "Change Event Type"
- [ ] Modal shows current event type
- [ ] Dropdown lists available event types
- [ ] Reason field available (optional)

**Submitting Change:**
- [ ] ApiClient used for request
- [ ] Loading state shows
- [ ] Success toast appears
- [ ] Daily view refreshes
- [ ] Event card shows new type

---

### 6. Trade Event Flow (Core Events Only)

**Opening Trade Modal:**
- [ ] Click "More Actions" → "Trade Event" (Core only)
- [ ] Modal shows source event details
- [ ] List of tradeable events loads
- [ ] Source event excluded from list
- [ ] Events displayed as cards

**Selecting Trade Target:**
- [ ] Click on target event card
- [ ] Card highlights with selection state
- [ ] "Execute Trade" button becomes enabled

**Executing Trade:**
- [ ] Click "Execute Trade"
- [ ] Button shows loading spinner
- [ ] ApiClient handles request
- [ ] Conflict detection works (409 response)
- [ ] Success: Both events swap employees
- [ ] Success toast appears
- [ ] Daily view refreshes

---

### 7. Unschedule Event Flow

**Opening Unschedule:**
- [ ] Click "More Actions" → "Unschedule"
- [ ] Confirmation dialog appears (browser confirm for now)

**Unscheduling:**
- [ ] Confirm unschedule
- [ ] ApiClient sends request
- [ ] Success toast appears
- [ ] Event card removed from view with animation
- [ ] If paired supervisor exists, notification mentions it
- [ ] If attendance exists, notification mentions removal

---

### 8. Attendance Recording

**Opening Attendance Dropdown:**
- [ ] Attendance list visible on daily view
- [ ] Each employee has status dropdown
- [ ] Click dropdown shows options:
  - On Time
  - Late
  - Called In
  - No Call No Show

**Recording Attendance:**
- [ ] Select status from dropdown
- [ ] Note modal appears (if applicable)
- [ ] Enter notes (optional)
- [ ] Submit attendance
- [ ] ApiClient used for POST request
- [ ] Success toast appears
- [ ] Attendance list refreshes
- [ ] Badge shows correct color for status

---

### 9. Lock/Unlock Day

**Lock Day:**
- [ ] Click "Lock Day" button (🔓 icon)
- [ ] Prompt appears for reason
- [ ] Enter reason
- [ ] ApiClient POST to /api/locked-days
- [ ] Success toast appears
- [ ] Button updates to "Unlock Day" (🔒 icon)
- [ ] Button text changes

**Unlock Day:**
- [ ] Click "Unlock Day" button
- [ ] Confirmation appears
- [ ] Confirm unlock
- [ ] ApiClient DELETE request
- [ ] Success toast appears
- [ ] Button returns to "Lock Day" state

**Locked Day Behavior:**
- [ ] Attempt to reschedule on locked day
- [ ] Error toast appears with unlock instructions
- [ ] Mentions "Lock Day" button location
- [ ] Operation blocked until unlocked

---

### 10. Bulk Reassign Supervisor Events

**Opening Bulk Reassign:**
- [ ] Click "Reassign Supervisor Events" button
- [ ] Modal opens with supervisor events list
- [ ] Employee dropdown loads supervisors
- [ ] Date field shows current date

**Submitting Bulk Reassign:**
- [ ] Select new supervisor
- [ ] Click "Reassign"
- [ ] Button shows loading state
- [ ] ApiClient POST request
- [ ] Success toast with count of events reassigned
- [ ] Modal closes
- [ ] Daily view refreshes
- [ ] All supervisor events show new employee

---

### 11. View Toggle (Card vs List)

**Card View (Default):**
- [ ] Events display as cards
- [ ] 2-column grid layout (on desktop)
- [ ] Card view button active (pressed state)

**List View:**
- [ ] Click "List" toggle button
- [ ] Events display in list format
- [ ] Single column layout
- [ ] List view button active

**Switching Between Views:**
- [ ] Toggle preserves filter selection
- [ ] Toggle maintains scroll position (if possible)
- [ ] All event data displays correctly in both views

---

### 12. Event Type Filter

**Filter Dropdown:**
- [ ] Filter dropdown shows all event types
- [ ] "All Types" selected by default
- [ ] Options: Core, Demo, Setup, Juicer, Supervisor, Freeosk, Digitals, Other

**Applying Filter:**
- [ ] Select "Core"
- [ ] Only Core events display
- [ ] Event count updates if shown
- [ ] Select "All Types"
- [ ] All events display again

---

### 13. Keyboard Navigation

**Keyboard Shortcuts (from Phase 4):**
- [ ] Press `←` - Navigate to previous day
- [ ] Press `→` - Navigate to next day
- [ ] Press `t` - Go to today
- [ ] Press `?` - Show keyboard shortcuts help modal
- [ ] Shortcuts don't trigger when typing in input fields
- [ ] Help modal lists all available shortcuts
- [ ] ESC closes help modal

**Tab Navigation:**
- [ ] Tab through all interactive elements
- [ ] Focus indicators visible (2px outline)
- [ ] Logical tab order
- [ ] No keyboard traps
- [ ] Skip-to-content link works

---

### 14. Semantic HTML & Accessibility

**Page Structure:**
- [ ] Page uses `<main>` landmark
- [ ] Header uses `<header>` landmark
- [ ] Navigation uses `<nav>` landmarks
- [ ] Sections use `<section>` with headings
- [ ] Proper heading hierarchy (h1 → h2 → h3)

**Event Cards:**
- [ ] Cards use `<article>` element
- [ ] Header uses `<header>` element
- [ ] Footer uses `<footer>` element
- [ ] Employee name is `<h3>` element
- [ ] Times use `<time datetime>` elements
- [ ] ARIA labels present on buttons
- [ ] Screen reader only text (`.sr-only`) provides context
- [ ] Decorative icons have `aria-hidden="true"`

**Modals:**
- [ ] Modal uses `role="dialog"`
- [ ] Modal has `aria-modal="true"`
- [ ] Modal labeled with `aria-labelledby`
- [ ] Modal header uses `<header>` element
- [ ] Modal footer uses `<footer>` element
- [ ] Required fields marked with `aria-required="true"`
- [ ] Help text associated with `aria-describedby`

**ARIA Live Regions:**
- [ ] Toast notifications announced by screen readers
- [ ] Status updates use `aria-live="polite"`
- [ ] Loading states announce via aria-busy
- [ ] Dynamic content changes announced

---

## Accessibility Testing

### Screen Reader Testing (NVDA/VoiceOver)

**Page Navigation:**
- [ ] Landmarks announced correctly
- [ ] Heading hierarchy makes sense
- [ ] Skip-to-content link works

**Event Cards:**
- [ ] Card announces as "Article"
- [ ] Employee name announced as "Heading level 3"
- [ ] Time announced with "Time:" prefix
- [ ] Event name announced with "Event:" prefix
- [ ] Status announced with "Status:" prefix
- [ ] Buttons have descriptive labels

**Forms:**
- [ ] Field labels announced correctly
- [ ] Required fields announced as "required"
- [ ] Help text read when field focused
- [ ] Validation errors announced
- [ ] Success states announced

**Interactive Elements:**
- [ ] All buttons have descriptive labels
- [ ] Links announce purpose
- [ ] Dropdowns announce current selection
- [ ] Checkboxes announce state (checked/unchecked)

### Keyboard-Only Testing

**Without Mouse:**
- [ ] Can navigate entire page with Tab
- [ ] Can activate all buttons with Enter/Space
- [ ] Can open/close dropdowns with keyboard
- [ ] Can select dropdown items with arrow keys
- [ ] Can close modals with Escape
- [ ] Can use keyboard shortcuts
- [ ] Focus always visible

### Color Contrast Testing

**Text Colors:**
- [ ] All body text meets 4.5:1 minimum
- [ ] Headings meet 4.5:1 minimum (or 3:1 if 18pt+)
- [ ] Badge text meets 4.5:1 minimum
- [ ] Button text meets 4.5:1 minimum
- [ ] Link text meets 4.5:1 minimum

**Using Browser DevTools:**
- [ ] Inspect elements in Chrome DevTools
- [ ] Check computed contrast ratios
- [ ] Verify all pass WCAG AA

---

## Mobile Responsiveness Testing

### Touch Targets

**Minimum 40px Touch Targets:**
- [ ] All buttons at least 40px height
- [ ] Date navigation arrows tappable
- [ ] Event card buttons tappable
- [ ] Dropdown toggles tappable
- [ ] Modal close buttons tappable

**Spacing:**
- [ ] Adequate space between interactive elements
- [ ] No accidental taps when scrolling
- [ ] Comfortable padding in cards

### Text Readability

**Font Sizes:**
- [ ] Body text at least 14px
- [ ] Readable without zooming
- [ ] Heading hierarchy clear
- [ ] Badge text legible (12px acceptable for labels)

**Layout:**
- [ ] Cards stack on mobile (single column)
- [ ] Buttons don't overlap
- [ ] Modals fit on screen
- [ ] No horizontal scrolling

### Device Testing

**Screen Sizes:**
- [ ] iPhone SE (375px) - Smallest common
- [ ] iPhone 12/13 (390px) - Standard
- [ ] iPad (768px) - Tablet
- [ ] Desktop (1280px+) - Desktop

**Orientation:**
- [ ] Portrait mode works correctly
- [ ] Landscape mode works correctly
- [ ] Orientation changes don't break layout

---

## Browser Compatibility Testing

### Modern Browsers

**Chrome (Desktop & Mobile):**
- [ ] CSS variables work
- [ ] Design tokens applied correctly
- [ ] Toast notifications display
- [ ] Loading states work
- [ ] ApiClient functions correctly
- [ ] Keyboard shortcuts work

**Firefox (Desktop):**
- [ ] All features work identically to Chrome
- [ ] No console errors
- [ ] CSS renders correctly

**Safari (Desktop & iOS):**
- [ ] CSS variables work
- [ ] Touch events work on iOS
- [ ] Date/time inputs work
- [ ] No webkit-specific issues

**Edge (Chromium):**
- [ ] Works identically to Chrome

### Fallback Testing

**CSS Variable Fallbacks:**
- [ ] Inspect computed styles
- [ ] Verify fallback values present
- [ ] Colors match whether token or fallback used

---

## Performance Testing

### Load Time:**
- [ ] Daily view loads in < 2 seconds
- [ ] CSS loads quickly (design tokens ~4KB)
- [ ] JavaScript loads quickly
- [ ] No blocking resources

### Interaction Performance:**
- [ ] Button clicks responsive (< 100ms feedback)
- [ ] Toast animations smooth (60fps)
- [ ] Loading spinners smooth
- [ ] Dropdown opens instantly
- [ ] Modal opens/closes smoothly

### Network Performance:**
- [ ] ApiClient timeouts work (30s)
- [ ] Retry logic doesn't cause excessive requests
- [ ] Failed requests handled gracefully
- [ ] Loading states show during network delay

---

## Regression Testing

### Existing Functionality Preserved

**Data Operations:**
- [ ] Events load correctly from database
- [ ] Filters work as before
- [ ] Sorting works as before
- [ ] Search works as before (if applicable)

**Business Logic:**
- [ ] Event priorities unchanged
- [ ] Scheduling constraints enforced
- [ ] Conflict detection works
- [ ] Validation rules unchanged

**Integration Points:**
- [ ] Walmart EDR integration works
- [ ] MVRetail sync works (if enabled)
- [ ] PDF generation works
- [ ] Email notifications work (if applicable)

---

## Security Testing

### CSRF Protection:**
- [ ] All POST requests include CSRF token
- [ ] ApiClient includes CSRF automatically
- [ ] Requests without token rejected

### Input Validation:**
- [ ] Date fields validate format
- [ ] Time fields validate format
- [ ] Employee IDs validated
- [ ] SQL injection prevented (server-side, but verify)
- [ ] XSS prevented (escaped output)

---

## Test Execution Checklist

### Pre-Testing Setup
- [ ] Deploy all changes to test environment
- [ ] Verify database backup exists
- [ ] Clear browser cache
- [ ] Test in incognito/private mode

### During Testing
- [ ] Document all findings
- [ ] Screenshot any issues
- [ ] Note steps to reproduce bugs
- [ ] Check browser console for errors

### Post-Testing
- [ ] Compile test results
- [ ] Categorize issues by severity
- [ ] Create bug tickets for issues found
- [ ] Document workarounds if needed

---

## Test Results Template

### Workflow: [Name]
**Status:** ✅ Pass / ⚠️ Pass with issues / ❌ Fail

**Tested On:**
- Browser: [Chrome/Firefox/Safari]
- Device: [Desktop/Mobile/Tablet]
- Screen Size: [Width x Height]

**Results:**
- Expected: [What should happen]
- Actual: [What actually happened]
- Issues Found: [List any issues]
- Screenshots: [Attach if applicable]

---

## Success Criteria

### Must Pass (P0):
- ✅ All critical workflows function correctly
- ✅ No console errors during normal use
- ✅ No alert() dialogs anywhere
- ✅ Toast notifications work
- ✅ Loading states show appropriately
- ✅ ApiClient handles all requests
- ✅ Validation works in forms
- ✅ WCAG 2.1 AA compliance for text/contrast
- ✅ Touch targets meet 40px minimum
- ✅ Keyboard navigation works
- ✅ Screen readers can navigate

### Should Pass (P1):
- ✅ All browsers tested (Chrome, Firefox, Safari, Edge)
- ✅ All device sizes tested (mobile, tablet, desktop)
- ✅ Performance acceptable (< 2s load, smooth animations)
- ✅ No regressions in existing features

### Nice to Have (P2):
- ✅ Perfect score in Lighthouse accessibility audit
- ✅ Zero WAVE accessibility errors
- ✅ Sub-1-second load time

---

## Testing Timeline

**Phase 1: Core Functionality (Today)**
- Daily view navigation
- Event operations (reschedule, reissue, change)
- Toast notifications
- Loading states

**Phase 2: Accessibility (Today)**
- Screen reader testing
- Keyboard navigation
- Color contrast
- Semantic HTML verification

**Phase 3: Cross-Browser/Device (Today/Next)**
- Chrome, Firefox, Safari, Edge
- Mobile, tablet, desktop
- Touch interaction testing

**Phase 4: Regression & Performance (Next)**
- Existing features verification
- Performance benchmarks
- Security verification

---

## Issue Tracking

### Critical Issues (Block Release):
- [ ] Core workflow broken
- [ ] Data loss possible
- [ ] Security vulnerability
- [ ] Accessibility blocker (WCAG violation)

### High Priority Issues (Fix Before Release):
- [ ] Feature not working as expected
- [ ] Poor user experience
- [ ] Inconsistent behavior
- [ ] Console errors

### Medium Priority Issues (Fix Soon):
- [ ] Visual inconsistencies
- [ ] Minor UX issues
- [ ] Performance concerns
- [ ] Browser-specific quirks

### Low Priority Issues (Fix When Possible):
- [ ] Cosmetic issues
- [ ] Nice-to-have features
- [ ] Edge case bugs
- [ ] Documentation improvements

---

**Testing Lead:** Claude Code
**Testing Date:** 2026-01-28
**Target Completion:** 2026-01-28
**Status:** 🔄 In Progress
