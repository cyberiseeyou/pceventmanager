# Notes Fixes & Push Notification System — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three bugs (notes banner duplication, missing icon on floating button, Friday bakery prep modal not loading) and add in-app push notification support for notes with snooze/dismiss.

**Architecture:** Bug fixes are isolated per-file changes. The notification system adds a `snoozed_until` column to the Note model, a new `/api/notes/<id>/snooze` endpoint, and a frontend poller + slide-in modal that shows due notes one at a time with dismiss/snooze actions.

**Tech Stack:** Flask/SQLAlchemy (backend), Alembic (migrations), vanilla JS (frontend), Material Symbols (icons), Jinja2 (templates)

**Spec:** `docs/superpowers/specs/2026-03-13-notes-fixes-and-notifications-design.md`

---

## Chunk 1: Bug Fixes

### Task 1: Fix notes banner duplication on reschedule

**Files:**
- Modify: `app/static/js/pages/daily-view.js:834-869`

- [ ] **Step 1: Add cleanup to renderNotesBanner()**

At the top of `renderNotesBanner()`, remove any existing banners before inserting a new one:

```javascript
renderNotesBanner(notes) {
    // Remove any existing banners (prevents duplication on re-init)
    document.querySelectorAll('.daily-notes-banner').forEach(el => el.remove());

    const banner = document.createElement('div');
```

In `app/static/js/pages/daily-view.js`, insert the cleanup line after line 834 (`renderNotesBanner(notes) {`) and before line 835 (`const banner = ...`).

- [ ] **Step 2: Also clear banners when no notes exist**

In `loadDailyNotes()`, if the response has 0 notes, also remove any stale banners. Modify the method at line 821:

```javascript
async loadDailyNotes() {
    try {
        const response = await fetch(`/api/daily-notes/${this.date}`);
        if (!response.ok) return;
        const data = await response.json();
        if (data.success && data.count > 0) {
            this.renderNotesBanner(data.notes);
        } else {
            // Clear any stale banners when no notes
            document.querySelectorAll('.daily-notes-banner').forEach(el => el.remove());
        }
    } catch (error) {
        console.error('Failed to load daily notes:', error);
    }
}
```

- [ ] **Step 3: Test manually**

Run: `python wsgi.py`
Open the daily view, verify only one note banner appears. Click Reschedule on an event, complete it, confirm only one banner remains.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/pages/daily-view.js
git commit -m "fix: prevent notes banner duplication on reschedule re-init"
```

---

### Task 2: Fix floating note button missing icon

**Files:**
- Modify: `app/templates/components/quick_note_widget.html:325-334,338-346,400-401,506-511,521,527-528`
- Modify: `app/models/notes.py:112-122`

- [ ] **Step 1: Replace Font Awesome icons in static HTML**

In `app/templates/components/quick_note_widget.html`, replace all `<i class="fas fa-...">` with Material Symbols `<span class="material-symbols-outlined">`:

Line 326: `<i class="fas fa-sticky-note"></i>` → `<span class="material-symbols-outlined" style="font-size:24px;">sticky_note_2</span>`

Line 333: `<i class="fas fa-sticky-note"></i>` → `<span class="material-symbols-outlined" style="font-size:18px;">sticky_note_2</span>`

Line 334: `<i class="fas fa-times"></i>` → `<span class="material-symbols-outlined">close</span>`

Line 339: `<i class="fas fa-plus"></i>` → `<span class="material-symbols-outlined" style="font-size:16px;">add</span>`

Line 342: `<i class="fas fa-list"></i>` → `<span class="material-symbols-outlined" style="font-size:16px;">list</span>`

Line 345: `<i class="fas fa-check"></i>` → `<span class="material-symbols-outlined" style="font-size:16px;">check</span>`

Line 401: `<i class="fas fa-save"></i>` → `<span class="material-symbols-outlined" style="font-size:16px;">save</span>`

- [ ] **Step 2: Replace Font Awesome icons in JavaScript-rendered content**

In the same file, update the JS template literals:

Line 508 (empty state icons): Replace:
```javascript
<i class="fas fa-${listType === 'pending' ? 'check-circle' : 'clipboard-list'}"></i>
```
With:
```javascript
<span class="material-symbols-outlined" style="font-size:32px;opacity:0.5;">${listType === 'pending' ? 'check_circle' : 'assignment'}</span>
```

Line 521 (type icon in notes list): Replace:
```javascript
<span><i class="${note.type_icon}"></i> ${note.display_type}</span>
```
With:
```javascript
<span><span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;">${note.type_icon}</span> ${note.display_type}</span>
```

Line 528 (delete button): Replace:
```javascript
<i class="fas fa-trash"></i>
```
With:
```javascript
<span class="material-symbols-outlined" style="font-size:16px;">delete</span>
```

- [ ] **Step 3: Update Note.type_icon property to return Material Symbol names**

In `app/models/notes.py`, lines 112-122, replace the `type_icon` property:

```python
@property
def type_icon(self):
    """Get Material Symbol icon name for note type"""
    icons = {
        'employee': 'person',
        'event': 'calendar_today',
        'task': 'check_box',
        'followup': 'notifications',
        'management': 'work'
    }
    return icons.get(self.note_type, 'sticky_note_2')
```

- [ ] **Step 4: Also fix .notes-empty CSS selector**

In `quick_note_widget.html`, line 302-306, update the CSS from targeting `i` to targeting `span`:

```css
.notes-empty span {
    font-size: 32px;
    margin-bottom: 8px;
    opacity: 0.5;
}
```

(The original was `.notes-empty i` which no longer matches the Material Symbols `<span>` element.)

- [ ] **Step 5: Test manually**

Run: `python wsgi.py`
Verify: floating button shows a sticky note icon, modal header shows icon, tab icons (Add/Pending/Done) visible, note type icons visible in lists, delete button icon visible.

- [ ] **Step 6: Commit**

```bash
git add app/templates/components/quick_note_widget.html app/models/notes.py
git commit -m "fix: replace Font Awesome icons with Material Symbols in note widget"
```

---

### Task 3: Fix Friday bakery prep modal not appearing

**Files:**
- Create: `app/templates/components/bakery_prep_modal.html`
- Modify: `app/templates/base.html:768-770`

- [ ] **Step 1: Create bakery prep modal component**

Create `app/templates/components/bakery_prep_modal.html`:

```html
<!-- Friday Bakery Prep Modal - Required by friday-bakery-prep.js -->
<div id="fridayBakeryPrepModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:9999; align-items:center; justify-content:center;">
    <div style="background:white; border-radius:16px; max-width:480px; width:90%; box-shadow:0 25px 50px rgba(0,0,0,0.3); overflow:hidden; margin:auto;">
        <div style="background:linear-gradient(135deg,#78350f,#92400e); padding:20px 24px; color:white;">
            <h3 style="margin:0; font-size:18px; display:flex; align-items:center; gap:8px;">
                <span class="material-symbols-outlined">bakery_dining</span>
                Bakery Prep List
            </h3>
            <p style="margin:4px 0 0; opacity:0.8; font-size:13px;">Weekly Friday Task</p>
        </div>
        <div style="padding:24px;">
            <div id="bakeryPrepStepContent"></div>
            <div id="bakeryPrepMfaInput" style="display:none; margin-top:16px;">
                <label for="bakeryPrepMfaCode" style="display:block; font-weight:600; margin-bottom:6px; font-size:14px;">MFA Code</label>
                <input id="bakeryPrepMfaCode" type="text" maxlength="6" placeholder="Enter 6-digit code" autocomplete="one-time-code"
                       style="width:100%; padding:12px; font-size:20px; letter-spacing:6px; text-align:center; border:2px solid #d1d5db; border-radius:8px; box-sizing:border-box;">
            </div>
            <div id="bakeryPrepProgress" style="display:none; text-align:center; margin-top:16px;">
                <div style="width:32px; height:32px; border:3px solid #e5e7eb; border-top-color:#0071ce; border-radius:50%; animation:spin 0.8s linear infinite; margin:0 auto 8px;"></div>
                <p id="bakeryPrepProgressText" style="color:#6b7280; margin:0;">Working...</p>
            </div>
        </div>
        <div id="bakeryPrepFooter" style="padding:16px 24px; border-top:1px solid #e5e7eb; display:flex; gap:8px; justify-content:flex-end;"></div>
    </div>
</div>
<style>
    @keyframes spin { to { transform: rotate(360deg); } }
    #fridayBakeryPrepModal .btn { padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; }
    #fridayBakeryPrepModal .btn-primary { background: #0071ce; color: white; }
    #fridayBakeryPrepModal .btn-primary:hover { background: #005ea6; }
    #fridayBakeryPrepModal .btn-secondary { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
    #fridayBakeryPrepModal .btn-secondary:hover { background: #e5e7eb; }
</style>
```

- [ ] **Step 2: Include modal and script in base.html**

In `app/templates/base.html`, after line 768 (`{% include 'components/quick_note_widget.html' %}`), add:

```html
    <!-- Friday Bakery Prep Modal -->
    {% include 'components/bakery_prep_modal.html' %}
```

Then before the closing `</body>` tag (after the PWA script block, around line 803), add the script:

```html
    <script src="{{ url_for('static', filename='js/friday-bakery-prep.js') }}"></script>
```

- [ ] **Step 3: Test manually**

Run: `python wsgi.py`
Open browser console, run `window.triggerBakeryPrepSend()` — verify the bakery prep modal appears with the correct layout. (The actual Friday auto-trigger only fires on Fridays when enabled + not completed.)

- [ ] **Step 4: Commit**

```bash
git add app/templates/components/bakery_prep_modal.html app/templates/base.html
git commit -m "fix: add bakery prep modal HTML and script to base template"
```

---

## Chunk 2: Note Notification Backend

### Task 4: Add snoozed_until column to Note model

**Files:**
- Modify: `app/models/notes.py:57-58,145-166`
- Create: `migrations/versions/xxxx_add_snoozed_until_to_notes.py` (via flask db migrate)

- [ ] **Step 1: Write failing test for snoozed_until field**

Create `tests/test_note_notifications.py`:

```python
"""Tests for note notification system: snooze, dismiss, pending query"""
import pytest
from datetime import datetime, date, time, timedelta
from unittest.mock import patch
from app.models import get_models

AUTH_PATCH = 'app.routes.auth.is_authenticated'


class TestNoteSnoozedUntil:
    """Test the snoozed_until column on the Note model"""

    def test_note_has_snoozed_until_field(self, db_session, models):
        """snoozed_until should be nullable DateTime, default None"""
        Note = models['Note']
        note = Note(title='Test note', note_type='task')
        db_session.add(note)
        db_session.commit()

        assert note.snoozed_until is None

    def test_note_snoozed_until_can_be_set(self, db_session, models):
        """snoozed_until can be set to a datetime"""
        Note = models['Note']
        snooze_time = datetime.now() + timedelta(minutes=15)
        note = Note(title='Snoozed note', note_type='task', snoozed_until=snooze_time)
        db_session.add(note)
        db_session.commit()

        fetched = db_session.query(Note).get(note.id)
        assert fetched.snoozed_until is not None

    def test_note_to_dict_includes_snoozed_until(self, db_session, models):
        """to_dict() should include snoozed_until"""
        Note = models['Note']
        note = Note(title='Dict test', note_type='task')
        db_session.add(note)
        db_session.commit()

        d = note.to_dict()
        assert 'snoozed_until' in d
        assert d['snoozed_until'] is None

    def test_note_to_dict_snoozed_until_format(self, db_session, models):
        """to_dict() snoozed_until should be ISO format string when set"""
        Note = models['Note']
        snooze_time = datetime(2026, 3, 13, 15, 30, 0)
        note = Note(title='Format test', note_type='task', snoozed_until=snooze_time)
        db_session.add(note)
        db_session.commit()

        d = note.to_dict()
        assert d['snoozed_until'] == '2026-03-13T15:30:00'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_note_notifications.py::TestNoteSnoozedUntil -v`
Expected: FAIL — `snoozed_until` column doesn't exist yet.

- [ ] **Step 3: Add snoozed_until column to Note model**

In `app/models/notes.py`, after line 58 (`reminder_sent = ...`), add:

```python
        # Snooze tracking for push notifications
        snoozed_until = db.Column(db.DateTime, nullable=True, default=None)
```

- [ ] **Step 4: Add snoozed_until to to_dict()**

In `app/models/notes.py`, in the `to_dict()` method, after the `'reminder_sent'` line (line 165), add:

```python
                'snoozed_until': self.snoozed_until.isoformat() if self.snoozed_until else None
```

(Don't forget to add a comma after the `'reminder_sent': self.reminder_sent` line.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_note_notifications.py::TestNoteSnoozedUntil -v`
Expected: All 4 PASS.

- [ ] **Step 6: Create migration**

```bash
./backup_now.sh
flask db migrate -m "add snoozed_until column to notes table"
```

Review the generated migration file to ensure it only adds the `snoozed_until` column.

- [ ] **Step 7: Apply migration to test DB first, then main**

```bash
DATABASE_URL=sqlite:///instance/scheduler_test.db flask db upgrade
flask db upgrade
```

- [ ] **Step 8: Commit**

```bash
git add app/models/notes.py tests/test_note_notifications.py migrations/versions/
git commit -m "feat: add snoozed_until column to Note model for snooze support"
```

---

### Task 5: Add snooze endpoint and update pending query

**Files:**
- Modify: `app/routes/api_notes.py:1-9,454-501`
- Test: `tests/test_note_notifications.py`

- [ ] **Step 1: Write failing tests for snooze endpoint**

Add to `tests/test_note_notifications.py`:

```python
class TestSnoozeEndpoint:
    """Test POST /api/notes/<id>/snooze"""

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_sets_snoozed_until(self, mock_auth, client, db_session, models):
        """Snoozing a note should set snoozed_until to now + duration"""
        Note = models['Note']
        note = Note(title='Snooze me', note_type='task', due_date=date.today(), reminder_sent=False)
        db_session.add(note)
        db_session.commit()

        response = client.post(f'/api/notes/{note.id}/snooze',
                               json={'duration': 15},
                               content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'snoozed_until' in data

        # Verify DB was updated
        db_session.refresh(note)
        assert note.snoozed_until is not None
        assert note.reminder_sent is False  # Reset to False for re-trigger

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_resets_reminder_sent(self, mock_auth, client, db_session, models):
        """Snoozing should reset reminder_sent to False"""
        Note = models['Note']
        note = Note(title='Already sent', note_type='task', due_date=date.today(), reminder_sent=True)
        db_session.add(note)
        db_session.commit()

        response = client.post(f'/api/notes/{note.id}/snooze',
                               json={'duration': 30},
                               content_type='application/json')
        assert response.status_code == 200

        db_session.refresh(note)
        assert note.reminder_sent is False

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_invalid_duration(self, mock_auth, client, db_session, models):
        """Invalid duration should return 400"""
        Note = models['Note']
        note = Note(title='Bad duration', note_type='task')
        db_session.add(note)
        db_session.commit()

        response = client.post(f'/api/notes/{note.id}/snooze',
                               json={'duration': 999},
                               content_type='application/json')
        assert response.status_code == 400

    @patch(AUTH_PATCH, return_value=True)
    def test_snooze_nonexistent_note(self, mock_auth, client, db_session):
        """Snoozing nonexistent note should return 404"""
        response = client.post('/api/notes/99999/snooze',
                               json={'duration': 15},
                               content_type='application/json')
        assert response.status_code == 404


class TestPendingNotificationsWithSnooze:
    """Test that snoozed notes are excluded from pending notifications"""

    @patch(AUTH_PATCH, return_value=True)
    def test_snoozed_note_excluded_from_pending(self, mock_auth, client, db_session, models):
        """A note snoozed until the future should NOT appear in pending"""
        Note = models['Note']
        note = Note(
            title='Snoozed note',
            note_type='task',
            due_date=date.today(),
            is_completed=False,
            reminder_sent=False,
            snoozed_until=datetime.now() + timedelta(hours=1)
        )
        db_session.add(note)
        db_session.commit()

        response = client.get('/api/notes/notifications/pending')
        assert response.status_code == 200
        data = response.get_json()
        note_ids = [n['id'] for n in data['notifications']]
        assert note.id not in note_ids

    @patch(AUTH_PATCH, return_value=True)
    def test_expired_snooze_appears_in_pending(self, mock_auth, client, db_session, models):
        """A note whose snooze has expired SHOULD appear in pending"""
        Note = models['Note']
        note = Note(
            title='Expired snooze',
            note_type='task',
            due_date=date.today(),
            is_completed=False,
            reminder_sent=False,
            snoozed_until=datetime.now() - timedelta(minutes=5)
        )
        db_session.add(note)
        db_session.commit()

        response = client.get('/api/notes/notifications/pending')
        assert response.status_code == 200
        data = response.get_json()
        note_ids = [n['id'] for n in data['notifications']]
        assert note.id in note_ids

    @patch(AUTH_PATCH, return_value=True)
    def test_null_snoozed_until_appears_in_pending(self, mock_auth, client, db_session, models):
        """A note with no snooze (NULL) should appear in pending normally"""
        Note = models['Note']
        note = Note(
            title='No snooze',
            note_type='task',
            due_date=date.today(),
            is_completed=False,
            reminder_sent=False,
            snoozed_until=None
        )
        db_session.add(note)
        db_session.commit()

        response = client.get('/api/notes/notifications/pending')
        assert response.status_code == 200
        data = response.get_json()
        note_ids = [n['id'] for n in data['notifications']]
        assert note.id in note_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_note_notifications.py::TestSnoozeEndpoint tests/test_note_notifications.py::TestPendingNotificationsWithSnooze -v`
Expected: FAIL — snooze endpoint doesn't exist, pending query doesn't filter snoozed.

- [ ] **Step 3: Add or_ import to api_notes.py**

In `app/routes/api_notes.py`, add a new import line after line 5 (`from flask import Blueprint, request, jsonify, current_app`):

```python
from sqlalchemy import or_
```

- [ ] **Step 4: Add snooze endpoint**

In `app/routes/api_notes.py`, after the `mark_notification_sent` function (after line 529), add:

```python
@api_notes_bp.route('/<int:note_id>/snooze', methods=['POST'])
@require_authentication()
def snooze_note(note_id):
    """Snooze a note notification for a specified duration"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    VALID_DURATIONS = [5, 15, 30, 60]

    try:
        data = request.get_json() or {}
        duration = data.get('duration')

        if duration not in VALID_DURATIONS:
            return jsonify({
                'success': False,
                'error': f'Invalid duration. Must be one of: {VALID_DURATIONS}'
            }), 400

        note = db.session.query(Note).get(note_id)
        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        note.snoozed_until = datetime.now() + timedelta(minutes=duration)
        note.reminder_sent = False
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Note snoozed for {duration} minutes',
            'snoozed_until': note.snoozed_until.isoformat()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error snoozing note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
```

- [ ] **Step 5: Update pending notifications query to exclude snoozed notes**

In `app/routes/api_notes.py`, in the `get_pending_notifications` function (around line 468), update the query to add a snoozed filter. Change:

```python
        pending_notes = db.session.query(Note).filter(
            Note.due_date <= today,
            Note.is_completed == False,
            Note.reminder_sent == False
        ).all()
```

To:

```python
        pending_notes = db.session.query(Note).filter(
            Note.due_date <= today,
            Note.is_completed == False,
            Note.reminder_sent == False,
            or_(Note.snoozed_until.is_(None), Note.snoozed_until <= datetime.now())
        ).all()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_note_notifications.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `pytest -v`
Expected: All existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add app/routes/api_notes.py tests/test_note_notifications.py
git commit -m "feat: add snooze endpoint and exclude snoozed notes from pending"
```

---

## Chunk 3: Note Notification Frontend

### Task 6: Create notification modal template

**Files:**
- Create: `app/templates/components/note_notification_modal.html`

- [ ] **Step 1: Create the slide-in panel modal template**

Create `app/templates/components/note_notification_modal.html`:

```html
<!-- Note Notification Modal - Slide-in panel for due note reminders -->
<div id="noteNotificationOverlay" style="display:none;">
    <div id="noteNotificationPanel">
        <!-- Header -->
        <div id="noteNotifHeader">
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="width:48px; height:48px; background:linear-gradient(135deg,#F59E0B,#D97706); border-radius:12px; display:flex; align-items:center; justify-content:center;">
                    <span class="material-symbols-outlined" style="color:white; font-size:24px;">notifications_active</span>
                </div>
                <div>
                    <div style="font-weight:700; font-size:18px; color:#1F2937;">Reminder</div>
                    <div id="noteNotifDueTime" style="color:#6B7280; font-size:12px;"></div>
                </div>
            </div>
            <div id="noteNotifQueue" style="display:none; font-size:12px; color:#6B7280; margin-top:8px;"></div>
        </div>

        <!-- Note Content -->
        <div id="noteNotifBody">
            <div id="noteNotifContent">
                <div id="noteNotifTitle" style="font-weight:700; color:#92400E; font-size:15px;"></div>
                <div id="noteNotifDesc" style="color:#78716C; font-size:13px; margin-top:4px;"></div>
            </div>
            <div id="noteNotifMeta" style="display:flex; gap:6px; margin-top:12px; flex-wrap:wrap;"></div>
        </div>

        <!-- Actions -->
        <div id="noteNotifActions">
            <button id="noteNotifDismissBtn" type="button">
                <span class="material-symbols-outlined" style="font-size:18px; vertical-align:middle;">check</span>
                Got it — Dismiss
            </button>
            <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px;">
                <button type="button" class="snooze-btn" data-duration="5">5m</button>
                <button type="button" class="snooze-btn" data-duration="15">15m</button>
                <button type="button" class="snooze-btn" data-duration="30">30m</button>
                <button type="button" class="snooze-btn" data-duration="60">1h</button>
            </div>
            <div style="text-align:center; color:#9CA3AF; font-size:11px; margin-top:4px;">Snooze for...</div>
        </div>
    </div>
</div>

<style>
    #noteNotificationOverlay {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.5);
        z-index: 10000;
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    #noteNotificationOverlay.visible {
        opacity: 1;
    }
    #noteNotificationPanel {
        position: absolute;
        top: 0;
        right: 0;
        bottom: 0;
        width: 380px;
        max-width: 90vw;
        background: white;
        border-radius: 16px 0 0 16px;
        box-shadow: -8px 0 30px rgba(0,0,0,0.2);
        display: flex;
        flex-direction: column;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    }
    #noteNotificationOverlay.visible #noteNotificationPanel {
        transform: translateX(0);
    }
    #noteNotifHeader {
        padding: 24px 24px 16px;
        border-bottom: 2px solid #FDE68A;
    }
    #noteNotifBody {
        flex: 1;
        padding: 20px 24px;
    }
    #noteNotifContent {
        background: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 16px;
        border-radius: 0 8px 8px 0;
    }
    #noteNotifActions {
        padding: 20px 24px;
        border-top: 1px solid #E5E7EB;
    }
    #noteNotifDismissBtn {
        width: 100%;
        padding: 12px;
        background: #0071CE;
        color: white;
        border: none;
        border-radius: 8px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        margin-bottom: 10px;
    }
    #noteNotifDismissBtn:hover {
        background: #005ea6;
    }
    .snooze-btn {
        padding: 8px 4px;
        background: #F9FAFB;
        color: #374151;
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
    }
    .snooze-btn:hover {
        background: #F3F4F6;
        border-color: #D1D5DB;
    }
    @media (max-width: 480px) {
        #noteNotificationPanel {
            width: 100vw;
            max-width: 100vw;
            border-radius: 0;
        }
    }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/components/note_notification_modal.html
git commit -m "feat: add note notification slide-in panel modal template"
```

---

### Task 7: Create notification poller JavaScript

**Files:**
- Create: `app/static/js/components/note-notifications.js`

- [ ] **Step 1: Create the notification poller and modal controller**

Create `app/static/js/components/note-notifications.js`:

```javascript
/**
 * Note Notification System
 *
 * Polls for due notes every 60 seconds and shows a blocking slide-in
 * modal for each. User must dismiss or snooze each note.
 *
 * Depends on: #noteNotificationOverlay (from note_notification_modal.html)
 * API: GET /api/notes/notifications/pending
 *       POST /api/notes/<id>/notification-sent
 *       POST /api/notes/<id>/snooze
 */
(function () {
    'use strict';

    const POLL_INTERVAL_MS = 60000; // 1 minute
    const PRIORITY_LABELS = {
        urgent: { text: 'Urgent', bg: '#FEE2E2', color: '#DC2626' },
        high:   { text: 'High',   bg: '#FEF3C7', color: '#D97706' },
        normal: { text: 'Normal', bg: '#DBEAFE', color: '#1E40AF' },
        low:    { text: 'Low',    bg: '#F3F4F6', color: '#6B7280' }
    };

    let overlay, panel, titleEl, descEl, dueTimeEl, metaEl, queueEl, dismissBtn;
    let queue = [];
    let currentNote = null;
    let pollTimer = null;
    let dismissedThisSession = new Set();

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function isAuthenticated() {
        // If no CSRF meta tag, we're on an unauthenticated page
        return !!document.querySelector('meta[name="csrf-token"]');
    }

    // ---- Polling ----

    function startPolling() {
        if (!isAuthenticated()) return;
        poll(); // immediate first check
        pollTimer = setInterval(poll, POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    async function poll() {
        try {
            const response = await fetch('/api/notes/notifications/pending');

            if (response.status === 401 || response.status === 403) {
                stopPolling();
                return;
            }

            if (!response.ok) return;

            const data = await response.json();
            if (!data.success || !data.notifications || data.notifications.length === 0) return;

            // Add new notes to queue (dedup by ID and skip dismissed this session)
            const currentIds = new Set(queue.map(n => n.id));
            if (currentNote) currentIds.add(currentNote.id);

            data.notifications.forEach(function (note) {
                if (!currentIds.has(note.id) && !dismissedThisSession.has(note.id)) {
                    queue.push(note);
                }
            });

            // Show modal if not already showing
            if (!currentNote && queue.length > 0) {
                showNext();
            } else if (currentNote) {
                updateQueueIndicator();
            }
        } catch (err) {
            console.error('[NoteNotif] Poll error:', err);
        }
    }

    // ---- Modal display ----

    function showNext() {
        if (queue.length === 0) {
            hideModal();
            currentNote = null;
            return;
        }

        currentNote = queue.shift();
        renderNote(currentNote);
        showModal();
    }

    function renderNote(note) {
        if (!titleEl) return;

        titleEl.textContent = note.title || 'Note Reminder';
        descEl.textContent = note.content || '';
        descEl.style.display = note.content ? '' : 'none';

        // Due time display
        if (note.is_overdue) {
            dueTimeEl.textContent = 'Overdue — ' + (note.due_date || '');
            dueTimeEl.style.color = '#DC2626';
        } else if (note.due_time) {
            dueTimeEl.textContent = 'Due now — ' + formatTime(note.due_time);
            dueTimeEl.style.color = '#6B7280';
        } else {
            dueTimeEl.textContent = 'Due today';
            dueTimeEl.style.color = '#6B7280';
        }

        // Meta badges
        var metaHtml = '';
        var p = PRIORITY_LABELS[note.priority] || PRIORITY_LABELS.normal;
        metaHtml += '<span style="background:' + p.bg + '; color:' + p.color +
            '; font-size:11px; padding:2px 8px; border-radius:4px; font-weight:600;">' +
            p.text + '</span>';

        if (note.linked_event_ref_num) {
            metaHtml += '<span style="background:#DBEAFE; color:#1E40AF; font-size:11px; padding:2px 8px; border-radius:4px;">' +
                '📋 Event #' + note.linked_event_ref_num + '</span>';
        }
        if (note.linked_employee_id) {
            metaHtml += '<span style="background:#D1FAE5; color:#065F46; font-size:11px; padding:2px 8px; border-radius:4px;">' +
                '👤 ' + note.linked_employee_id + '</span>';
        }
        if (note.display_type) {
            metaHtml += '<span style="color:#9CA3AF; font-size:11px; padding:2px 0;">' +
                note.display_type + '</span>';
        }
        metaEl.innerHTML = metaHtml;

        updateQueueIndicator();
    }

    function updateQueueIndicator() {
        if (!queueEl) return;
        if (queue.length > 0) {
            queueEl.textContent = (queue.length + 1) + ' reminders — showing 1 of ' + (queue.length + 1);
            queueEl.style.display = '';
        } else {
            queueEl.style.display = 'none';
        }
    }

    function formatTime(timeStr) {
        if (!timeStr) return '';
        var parts = timeStr.split(':');
        var h = parseInt(parts[0], 10);
        var m = parts[1];
        var ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        return h + ':' + m + ' ' + ampm;
    }

    function showModal() {
        if (!overlay) return;
        overlay.style.display = '';
        // Force reflow before adding class for transition
        overlay.offsetHeight;
        overlay.classList.add('visible');
    }

    function hideModal() {
        if (!overlay) return;
        overlay.classList.remove('visible');
        setTimeout(function () {
            overlay.style.display = 'none';
        }, 300);
    }

    // ---- Actions ----

    async function dismiss() {
        if (!currentNote) return;
        var noteId = currentNote.id;
        dismissedThisSession.add(noteId);

        try {
            await fetch('/api/notes/' + noteId + '/notification-sent', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
        } catch (err) {
            console.error('[NoteNotif] Dismiss error:', err);
        }

        showNext();
    }

    async function snooze(duration) {
        if (!currentNote) return;
        var noteId = currentNote.id;
        dismissedThisSession.add(noteId); // Don't re-show this session

        try {
            await fetch('/api/notes/' + noteId + '/snooze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ duration: duration })
            });
        } catch (err) {
            console.error('[NoteNotif] Snooze error:', err);
        }

        showNext();
    }

    // ---- Init ----

    document.addEventListener('DOMContentLoaded', function () {
        overlay = document.getElementById('noteNotificationOverlay');
        if (!overlay) return;

        panel = document.getElementById('noteNotificationPanel');
        titleEl = document.getElementById('noteNotifTitle');
        descEl = document.getElementById('noteNotifDesc');
        dueTimeEl = document.getElementById('noteNotifDueTime');
        metaEl = document.getElementById('noteNotifMeta');
        queueEl = document.getElementById('noteNotifQueue');
        dismissBtn = document.getElementById('noteNotifDismissBtn');

        // Dismiss button
        if (dismissBtn) {
            dismissBtn.addEventListener('click', dismiss);
        }

        // Snooze buttons
        document.querySelectorAll('.snooze-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var duration = parseInt(this.getAttribute('data-duration'), 10);
                snooze(duration);
            });
        });

        startPolling();
    });
})();
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/components/note-notifications.js
git commit -m "feat: add note notification poller and modal controller JS"
```

---

### Task 8: Wire notification components into base.html

**Files:**
- Modify: `app/templates/base.html:768`

- [ ] **Step 1: Add notification modal include and script**

In `app/templates/base.html`, after the quick note widget include (line 768) and bakery prep modal include (added in Task 3), add:

```html
    <!-- Note Notification Modal -->
    {% include 'components/note_notification_modal.html' %}
```

Then before the closing `</body>` tag (after the friday-bakery-prep.js script added in Task 3), add:

```html
    <script src="{{ url_for('static', filename='js/components/note-notifications.js') }}"></script>
```

- [ ] **Step 2: Test the full flow manually**

Run: `python wsgi.py`

1. Create a note with a due date of today and a due time in the past via the Quick Note widget
2. Wait up to 60 seconds — the slide-in notification panel should appear
3. Test snooze (5m) — modal should close, note should reappear after 5 minutes
4. Test dismiss — modal should close, note should NOT reappear

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests pass including new notification tests.

- [ ] **Step 4: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: wire note notification modal and poller into base template"
```

---

## Chunk 4: Final Verification

### Task 9: End-to-end verification and regression check

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Manual verification checklist**

Run: `python wsgi.py`

1. **Notes banner**: Open daily view → verify exactly 1 note banner. Reschedule an event → verify still exactly 1 banner.
2. **Floating button**: Verify note icon (sticky_note_2) visible in the blue circle. Click it → verify modal icons (header, tabs, save, etc.) all display correctly.
3. **Bakery prep modal**: Open browser console → run `window.triggerBakeryPrepSend()` → verify modal appears with proper layout.
4. **Note notifications**: Create a note due today with past time → wait ~60s → verify slide-in panel appears. Test dismiss. Test snooze. Test multiple notes queuing.

- [ ] **Step 3: Final commit if any fixes needed**

Only if manual testing reveals issues that need small fixes.
