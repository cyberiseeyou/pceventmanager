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

**Problem:** The quick note button in `quick_note_widget.html` uses Font Awesome classes, but `base.html` only loads Material Symbols. Font Awesome is not included anywhere, so the icons render as invisible.

**Scope:** All Font Awesome usages in both the static HTML and JavaScript-rendered content within `quick_note_widget.html`:

| Font Awesome (current) | Material Symbol (replacement) | Location |
|-------------------------|-------------------------------|----------|
| `fa-sticky-note` (x2) | `sticky_note_2` | Button, modal header |
| `fa-times` | `close` | Close button |
| `fa-plus` | `add` | Add tab |
| `fa-list` | `list` | Pending tab |
| `fa-check` | `check` | Done tab |
| `fa-save` | `save` | Save button |
| `fa-check-circle` | `check_circle` | JS: completed note icon |
| `fa-clipboard-list` | `assignment` | JS: pending note icon |
| `fa-trash` | `delete` | JS: delete button |

All `<i class="fas fa-...">` must become `<span class="material-symbols-outlined">icon_name</span>`.

**Additionally:** The `Note.type_icon` property in `app/models/notes.py` (lines 113-122) returns Font Awesome class names (`fa-user`, `fa-calendar`, etc.) which are consumed in JS via `note.type_icon`. This property must also be updated to return Material Symbol names, and the JS consumer updated to use `<span class="material-symbols-outlined">` instead of `<i class="...">`.

**Files:** `app/templates/components/quick_note_widget.html`, `app/models/notes.py`

---

## 3. Friday Bakery Prep Modal Fix

**Problem:** `friday-bakery-prep.js` expects a `#fridayBakeryPrepModal` element in the DOM and a set of child elements (`#bakeryPrepStepContent`, `#bakeryPrepMfaInput`, `#bakeryPrepMfaCode`, `#bakeryPrepProgress`, `#bakeryPrepProgressText`, `#bakeryPrepFooter`). Neither the modal HTML nor the script tag exist in `base.html`. The script silently exits at `if (!modal) return;` on line 302.

**Fix:**
1. Add the bakery prep modal HTML structure to `base.html` (or a new component template included from `base.html`)
2. Add `<script src="{{ url_for('static', filename='js/friday-bakery-prep.js') }}"></script>` to `base.html`

**Show/hide mechanism:** The JS uses inline `style.display` toggling (`display: 'flex'` to show, `display: 'none'` to hide). The modal outer div starts with `style="display:none;"`. No CSS class toggling is used.

**Modal HTML structure** (inferred from JS references):
```html
<div id="fridayBakeryPrepModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:9999; align-items:center; justify-content:center;">
  <div style="background:white; border-radius:16px; padding:0; max-width:480px; width:90%; box-shadow:0 25px 50px rgba(0,0,0,0.3); overflow:hidden;">
    <div style="background:linear-gradient(135deg,#78350f,#92400e); padding:20px 24px; color:white;">
      <h3 style="margin:0; font-size:18px;">Bakery Prep List</h3>
      <p style="margin:4px 0 0; opacity:0.8; font-size:13px;">Weekly Friday Task</p>
    </div>
    <div style="padding:24px;">
      <div id="bakeryPrepStepContent"></div>
      <div id="bakeryPrepMfaInput" style="display:none; margin-top:16px;">
        <label for="bakeryPrepMfaCode" style="display:block; font-weight:600; margin-bottom:6px;">MFA Code</label>
        <input id="bakeryPrepMfaCode" type="text" maxlength="6" placeholder="Enter 6-digit code" autocomplete="one-time-code"
               style="width:100%; padding:10px; font-size:18px; letter-spacing:4px; text-align:center; border:2px solid #d1d5db; border-radius:8px;">
      </div>
      <div id="bakeryPrepProgress" style="display:none; text-align:center; margin-top:16px;">
        <p id="bakeryPrepProgressText" style="color:#6b7280;">Working...</p>
      </div>
    </div>
    <div id="bakeryPrepFooter" style="padding:16px 24px; border-top:1px solid #e5e7eb; display:flex; gap:8px; justify-content:flex-end;"></div>
  </div>
</div>
```

**Files:** `app/templates/base.html`, `app/templates/components/bakery_prep_modal.html` (new)

---

## 4. Note Push Notification System

### 4.1 Behavior

- A JavaScript poller runs every 60 seconds on authenticated pages (loaded from `base.html`)
- It calls `GET /api/notes/notifications/pending` (already exists)
- When due notes are returned, they are added to a queue
- A full-screen blocking modal (slide-in panel from right) appears showing one note at a time
- User must interact: **Dismiss** or **Snooze** (5m, 15m, 30m, 1hr)
- After interaction, the next queued note appears; when empty, modal closes
- Snoozed notes are excluded from pending query until their snooze time expires
- Dismissed notes have `reminder_sent` set to `True` (existing mechanism)

**Authentication guard:** The poller checks for the CSRF meta tag before starting. If not present (login page, unauthenticated), polling does not start. If a poll returns 401/403, polling stops to avoid console errors on every page.

**Multi-tab behavior:** The server-side `reminder_sent = True` (on dismiss) and `snoozed_until` (on snooze) are the source of truth. There is a brief race window (up to 60s) where a second tab may show a notification that was already dismissed in another tab. This is acceptable — the user simply dismisses it again. No cross-tab coordination mechanism is needed.

### 4.2 Model Change

Add `snoozed_until` column to `Note` model:

```python
snoozed_until = db.Column(db.DateTime, nullable=True, default=None)
```

**Migration required.** Nullable column, no backfill needed.

Also update `Note.to_dict()` to include `snoozed_until` in the serialized output:
```python
'snoozed_until': self.snoozed_until.isoformat() if self.snoozed_until else None,
```

### 4.3 New Endpoint

```
POST /api/notes/<id>/snooze
Body: { "duration": 5 | 15 | 30 | 60 }  (minutes)
Response: { "success": true, "snoozed_until": "2026-03-13T15:30:00" }
```

Sets `snoozed_until = datetime.now() + timedelta(minutes=duration)` on the note. Uses `datetime.now()` (local time) to match the existing pending query convention. Resets `reminder_sent` to `False` so the note will re-trigger after snooze expires.

**CSRF:** The endpoint requires `X-CSRFToken` header, consistent with other POST endpoints. The notification JS must read the CSRF token from the `<meta name="csrf-token">` tag.

**Overdue note behavior:** Dismissed overdue notes are silenced permanently (`reminder_sent = True`). Snoozed overdue notes re-trigger after the snooze period. This is intentional — dismiss means "I'm done with this", snooze means "remind me again."

### 4.4 Pending Notifications Query Change

The existing `GET /api/notes/notifications/pending` endpoint must add an additional filter:

```python
from sqlalchemy import or_  # Add to imports

# Exclude snoozed notes
.filter(or_(Note.snoozed_until.is_(None), Note.snoozed_until <= datetime.now()))
```

**Timezone note:** Uses `datetime.now()` (local time) consistent with the existing pending query logic. The codebase has a pre-existing inconsistency where model defaults use `datetime.utcnow()` but queries use `datetime.now()`. This spec follows the existing query convention. A future cleanup may normalize to UTC throughout.

### 4.5 Frontend Components

**New file: `app/static/js/components/note-notifications.js`**

Responsibilities:
- Check for CSRF meta tag before starting (authentication guard)
- Poll `GET /api/notes/notifications/pending` every 60 seconds
- Stop polling on 401/403 response
- Maintain an internal queue of due notes (deduplicated by note ID)
- Show/hide the notification modal
- Handle dismiss (calls `POST /api/notes/<id>/notification-sent` with `X-CSRFToken` header)
- Handle snooze (calls `POST /api/notes/<id>/snooze` with `X-CSRFToken` header)
- Advance to next queued note or close modal when queue is empty

**New file: `app/templates/components/note_notification_modal.html`**

Slide-in panel HTML + scoped CSS:
- Full-screen overlay (`position: fixed; inset: 0; background: rgba(0,0,0,0.5)`)
- Panel docked to right side, 380px wide, white background, rounded left corners
- Header with amber icon, "Reminder" title, due time display
- Due time display: shows time if `due_time` is set, otherwise "Due today" or "Overdue" based on `due_date` vs today
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
| Update `to_dict()` serialization | `app/models/notes.py` |
| Update `type_icon` property to Material Symbols | `app/models/notes.py` |
| Create migration | `migrations/versions/xxxx_add_snoozed_until_to_notes.py` |
| Add snooze endpoint | `app/routes/api_notes.py` |
| Update pending query filter + add `or_` import | `app/routes/api_notes.py` |
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
- UTC/local timezone normalization (pre-existing inconsistency, separate effort)
