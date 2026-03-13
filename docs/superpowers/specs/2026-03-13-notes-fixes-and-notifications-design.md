# Notes Fixes & Push Notification System

**Date:** 2026-03-13
**Status:** Approved

## Overview

Four related changes to the notes system: fix the duplicating daily notes banner, fix the missing icon on the floating note button, fix the Friday bakery prep modal not appearing, and add in-app push notification support for notes with due dates.

---

## 1. Notes Banner Duplication Fix

**Problem:** Every time a reschedule completes, `window.dailyView.init()` is called, which re-invokes `loadDailyNotes()` → `renderNotesBanner()`. The function always creates and inserts a new banner via `insertBefore` without removing existing ones, causing "1 note for today" to appear multiple times.

**Fix:** At the top of `renderNotesBanner()` in `app/static/js/pages/daily-view.js`, remove all existing `.daily-notes-banner` elements before inserting the new one.

**File:** `app/static/js/pages/daily-view.js` (line ~834)

---

## 2. Floating Note Button Icon Fix

**Problem:** The quick note button in `quick_note_widget.html` uses Font Awesome classes (`fas fa-sticky-note`, `fas fa-times`), but `base.html` only loads Material Symbols. Font Awesome is not included anywhere, so the icons render as invisible.

**Fix:** Replace all Font Awesome `<i class="fas fa-...">` references in `quick_note_widget.html` with Material Symbols `<span class="material-symbols-outlined">` equivalents:
- `fa-sticky-note` → `sticky_note_2`
- `fa-times` → `close`
- Any other FA icons in the widget → appropriate Material Symbols

**File:** `app/templates/components/quick_note_widget.html`

---

## 3. Friday Bakery Prep Modal Fix

**Problem:** `friday-bakery-prep.js` expects a `#fridayBakeryPrepModal` element in the DOM and a set of child elements (`#bakeryPrepStepContent`, `#bakeryPrepMfaInput`, `#bakeryPrepMfaCode`, `#bakeryPrepProgress`, `#bakeryPrepProgressText`, `#bakeryPrepFooter`). Neither the modal HTML nor the script tag exist in `base.html`. The script silently exits at `if (!modal) return;` on line 302.

**Fix:**
1. Add the bakery prep modal HTML structure to `base.html` (or a new component template included from `base.html`)
2. Add `<script src="{{ url_for('static', filename='js/friday-bakery-prep.js') }}"></script>` to `base.html`

**Modal HTML structure** (inferred from JS references):
```html
<div id="fridayBakeryPrepModal" class="modal-overlay" style="display:none;">
  <div class="modal-container">
    <div class="modal-header">
      <h3>Bakery Prep List</h3>
    </div>
    <div class="modal-body">
      <div id="bakeryPrepStepContent"></div>
      <div id="bakeryPrepMfaInput" style="display:none;">
        <label for="bakeryPrepMfaCode">MFA Code</label>
        <input id="bakeryPrepMfaCode" type="text" maxlength="6" placeholder="Enter 6-digit code" autocomplete="one-time-code">
      </div>
      <div id="bakeryPrepProgress" style="display:none;">
        <p id="bakeryPrepProgressText">Working...</p>
      </div>
    </div>
    <div id="bakeryPrepFooter" class="modal-footer"></div>
  </div>
</div>
```

**Files:** `app/templates/base.html`, potentially `app/templates/components/bakery_prep_modal.html` (new)

---

## 4. Note Push Notification System

### 4.1 Behavior

- A JavaScript poller runs every 60 seconds on every page (loaded from `base.html`)
- It calls `GET /api/notes/notifications/pending` (already exists)
- When due notes are returned, they are added to a queue
- A full-screen blocking modal (slide-in panel from right) appears showing one note at a time
- User must interact: **Dismiss** or **Snooze** (5m, 15m, 30m, 1hr)
- After interaction, the next queued note appears; when empty, modal closes
- Snoozed notes are excluded from pending query until their snooze time expires
- Dismissed notes have `reminder_sent` set to `True` (existing mechanism)

### 4.2 Model Change

Add `snoozed_until` column to `Note` model:

```python
snoozed_until = db.Column(db.DateTime, nullable=True, default=None)
```

**Migration required.** Nullable column, no backfill needed.

### 4.3 New Endpoint

```
POST /api/notes/<id>/snooze
Body: { "duration": 5 | 15 | 30 | 60 }  (minutes)
Response: { "success": true, "snoozed_until": "2026-03-13T15:30:00" }
```

Sets `snoozed_until = now() + duration minutes` on the note. Resets `reminder_sent` to `False` so the note will re-trigger after snooze expires.

### 4.4 Pending Notifications Query Change

The existing `GET /api/notes/notifications/pending` endpoint must add an additional filter:

```python
# Exclude snoozed notes
.filter(or_(Note.snoozed_until.is_(None), Note.snoozed_until <= datetime.now()))
```

### 4.5 Frontend Components

**New file: `app/static/js/components/note-notifications.js`**

Responsibilities:
- Poll `GET /api/notes/notifications/pending` every 60 seconds
- Maintain an internal queue of due notes (deduplicated by note ID)
- Show/hide the notification modal
- Handle dismiss (calls `POST /api/notes/<id>/notification-sent`)
- Handle snooze (calls `POST /api/notes/<id>/snooze`)
- Advance to next queued note or close modal when queue is empty
- Track shown note IDs in `sessionStorage` to avoid re-showing dismissed notes within the same session

**New file: `app/templates/components/note_notification_modal.html`**

Slide-in panel HTML + scoped CSS:
- Full-screen overlay (`position: fixed; inset: 0; background: rgba(0,0,0,0.5)`)
- Panel docked to right side, 380px wide, white background, rounded left corners
- Header with amber icon, "Reminder" title, due time
- Note content area with title, description, priority badge, linked entity
- Dismiss button (primary, full width)
- 4 snooze buttons in a grid row (5m, 15m, 30m, 1h)
- Queue indicator: "1 of 3" when multiple notes are queued

**Modified: `app/templates/base.html`**

- Include `note_notification_modal.html` component
- Add script tag for `note-notifications.js`

### 4.6 Design Details (Option B: Slide-in Panel)

- Panel slides in from right with CSS transition (`transform: translateX(100%)` → `translateX(0)`)
- Overlay fades in (`opacity: 0` → `opacity: 1`)
- Dismiss button: Walmart blue (`#0071CE`), full width
- Snooze buttons: Light gray grid, 4 columns
- Priority badge colors: urgent=red, high=orange, normal=blue, low=gray
- Queue counter shown below header when multiple notes queued

### 4.7 Files Summary

| Action | File |
|--------|------|
| Add `snoozed_until` column | `app/models/notes.py` |
| Create migration | `migrations/versions/xxxx_add_snoozed_until_to_notes.py` |
| Add snooze endpoint | `app/routes/api_notes.py` |
| Update pending query filter | `app/routes/api_notes.py` |
| New notification poller/controller | `app/static/js/components/note-notifications.js` |
| New modal template + CSS | `app/templates/components/note_notification_modal.html` |
| Include modal + script | `app/templates/base.html` |

---

## Out of Scope

- Browser Push API / service worker push notifications
- Sound effects or audio alerts
- Per-user notification preferences UI
- Notification history / log
- Desktop notifications via Notification API
