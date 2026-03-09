# Lost Demos Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Lost Demos tracking — a new category on the approved events page for unassigned past-due events, a weekly confirmation list, and a lost demo rate metric in reports.

**Architecture:** New `LostDemo` model (factory pattern), new `lost_demos` blueprint for the weekly list page and API endpoints, modifications to the approved events JS for the 4th category, and a new metric in the event statistics report.

**Tech Stack:** Flask, SQLAlchemy, Alembic, vanilla JS (matching existing patterns), Jinja2 templates, CSS

---

### Task 1: Create LostDemo Model

**Files:**
- Create: `app/models/lost_demo.py`
- Modify: `app/models/__init__.py:5-19` (add import) and `app/models/__init__.py:22-80` (add to init_models and return dict)

**Step 1: Create the model factory file**

Create `app/models/lost_demo.py`:

```python
"""
LostDemo model — tracks events confirmed as lost demos.
"""
from datetime import datetime


def create_lost_demo_model(db):
    """Factory function to create LostDemo model with db instance."""

    class LostDemo(db.Model):
        """
        Tracks events confirmed as lost (unassigned + past due).
        Each record represents one event that was confirmed lost,
        filed under the week (Sun-Sat) of the event's due date.
        """
        __tablename__ = 'lost_demos'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        event_ref_num = db.Column(
            db.Integer,
            db.ForeignKey('events.project_ref_num'),
            nullable=False,
            unique=True
        )
        week_start_date = db.Column(db.Date, nullable=False)
        confirmed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        notes = db.Column(db.Text, nullable=True)

        __table_args__ = (
            db.Index('idx_lost_demos_week', 'week_start_date'),
        )

        def __repr__(self):
            return f'<LostDemo event_ref={self.event_ref_num} week={self.week_start_date}>'

    return LostDemo
```

**Step 2: Register the model in `app/models/__init__.py`**

Add import at line 20 (after the existing imports):
```python
from .lost_demo import create_lost_demo_model
```

Inside `init_models()`, after line 46 (`inventory_models = ...`), add:
```python
LostDemo = create_lost_demo_model(db)
```

Add to the return dict (after `'InventoryReminder'` entry):
```python
'LostDemo': LostDemo,
```

**Step 3: Create the migration**

Run:
```bash
flask db migrate -m "add lost_demos table"
```

Review the generated migration file, then:
```bash
flask db upgrade
```

**Step 4: Commit**

```bash
git add app/models/lost_demo.py app/models/__init__.py migrations/versions/
git commit -m "feat: add LostDemo model for tracking confirmed lost demos"
```

---

### Task 2: Create Lost Demos API Endpoints

**Files:**
- Create: `app/routes/lost_demos.py`
- Modify: `app/__init__.py:254-255` (register blueprint)

**Step 1: Write the failing test**

Create `tests/test_lost_demos.py`:

```python
"""Tests for Lost Demos feature."""
import pytest
from datetime import datetime, date, timedelta


def _sunday_of(d):
    """Return the Sunday starting the week containing date d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


class TestConfirmLostDemo:
    """Test POST /api/lost-demos/<ref_num>/confirm"""

    def test_confirm_lost_creates_record(self, client, db_session, models):
        Event = models['Event']
        LostDemo = models['LostDemo']

        event = Event(
            project_name='Test Event',
            project_ref_num=99901,
            start_datetime=datetime(2026, 2, 1),
            due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        resp = client.post('/api/lost-demos/99901/confirm',
                          json={},
                          content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'

        record = LostDemo.query.filter_by(event_ref_num=99901).first()
        assert record is not None
        assert record.week_start_date == _sunday_of(date(2026, 2, 15))

    def test_confirm_duplicate_returns_409(self, client, db_session, models):
        Event = models['Event']
        LostDemo = models['LostDemo']

        event = Event(
            project_name='Test Event',
            project_ref_num=99902,
            start_datetime=datetime(2026, 2, 1),
            due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        client.post('/api/lost-demos/99902/confirm',
                    json={}, content_type='application/json')
        resp = client.post('/api/lost-demos/99902/confirm',
                          json={}, content_type='application/json')
        assert resp.status_code == 409

    def test_confirm_nonexistent_event_returns_404(self, client, db_session, models):
        resp = client.post('/api/lost-demos/00000/confirm',
                          json={}, content_type='application/json')
        assert resp.status_code == 404


class TestUndoLostDemo:
    """Test DELETE /api/lost-demos/<ref_num>/confirm"""

    def test_undo_deletes_record(self, client, db_session, models):
        Event = models['Event']
        LostDemo = models['LostDemo']

        event = Event(
            project_name='Test Event',
            project_ref_num=99903,
            start_datetime=datetime(2026, 2, 1),
            due_datetime=datetime(2026, 2, 15),
            event_type='Core'
        )
        db_session.add(event)
        db_session.commit()

        client.post('/api/lost-demos/99903/confirm',
                    json={}, content_type='application/json')
        resp = client.delete('/api/lost-demos/99903/confirm')
        assert resp.status_code == 200

        record = LostDemo.query.filter_by(event_ref_num=99903).first()
        assert record is None


class TestListLostDemos:
    """Test GET /api/lost-demos"""

    def test_list_by_week(self, client, db_session, models):
        Event = models['Event']

        # Create 2 events in same week
        for i, ref in enumerate([99904, 99905]):
            event = Event(
                project_name=f'Lost Event {i}',
                project_ref_num=ref,
                start_datetime=datetime(2026, 2, 1),
                due_datetime=datetime(2026, 2, 11 + i),  # Wed/Thu of same week
                event_type='Core'
            )
            db_session.add(event)
        db_session.commit()

        for ref in [99904, 99905]:
            client.post(f'/api/lost-demos/{ref}/confirm',
                       json={}, content_type='application/json')

        week_start = _sunday_of(date(2026, 2, 11)).isoformat()
        resp = client.get(f'/api/lost-demos?week_start={week_start}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['data']) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lost_demos.py -v`
Expected: FAIL (routes don't exist yet)

**Step 3: Create the blueprint**

Create `app/routes/lost_demos.py`:

```python
"""
Lost Demos Blueprint
API endpoints for confirming, undoing, and listing lost demos.
Also serves the weekly lost demos list page.
"""
from flask import Blueprint, jsonify, request, render_template, current_app, make_response
from datetime import datetime, date, timedelta
from app.models import get_models, get_db
import csv
import io

lost_demos_bp = Blueprint('lost_demos', __name__)


def _sunday_of(d):
    """Return the Sunday starting the week containing date d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


@lost_demos_bp.route('/api/lost-demos/<int:ref_num>/confirm', methods=['POST'])
def confirm_lost(ref_num):
    """Confirm an event as a lost demo."""
    models = get_models()
    db = get_db()
    Event = models['Event']
    LostDemo = models['LostDemo']

    event = Event.query.filter_by(project_ref_num=ref_num).first()
    if not event:
        return jsonify({'status': 'error', 'error': 'Event not found'}), 404

    existing = LostDemo.query.filter_by(event_ref_num=ref_num).first()
    if existing:
        return jsonify({'status': 'error', 'error': 'Already confirmed as lost'}), 409

    data = request.get_json(silent=True) or {}
    week_start = _sunday_of(event.due_datetime.date())

    record = LostDemo(
        event_ref_num=ref_num,
        week_start_date=week_start,
        confirmed_at=datetime.utcnow(),
        notes=data.get('notes', ''),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({'status': 'success', 'data': {
        'event_ref_num': ref_num,
        'week_start_date': week_start.isoformat(),
    }})


@lost_demos_bp.route('/api/lost-demos/<int:ref_num>/confirm', methods=['DELETE'])
def undo_lost(ref_num):
    """Undo a lost demo confirmation."""
    models = get_models()
    db = get_db()
    LostDemo = models['LostDemo']

    record = LostDemo.query.filter_by(event_ref_num=ref_num).first()
    if not record:
        return jsonify({'status': 'error', 'error': 'Not found'}), 404

    db.session.delete(record)
    db.session.commit()

    return jsonify({'status': 'success'})


@lost_demos_bp.route('/api/lost-demos')
def list_lost_demos():
    """List lost demos for a given week."""
    models = get_models()
    Event = models['Event']
    LostDemo = models['LostDemo']

    week_str = request.args.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'status': 'error', 'error': 'Invalid date format'}), 400
    else:
        today = date.today()
        week_start = _sunday_of(today)

    week_end = week_start + timedelta(days=6)

    records = LostDemo.query.filter(
        LostDemo.week_start_date >= week_start,
        LostDemo.week_start_date <= week_end,
    ).all()

    results = []
    for rec in records:
        event = Event.query.filter_by(project_ref_num=rec.event_ref_num).first()
        results.append({
            'event_ref_num': rec.event_ref_num,
            'event_name': event.project_name if event else 'Unknown',
            'event_type': event.event_type if event else 'Unknown',
            'due_date': event.due_datetime.strftime('%m/%d/%Y') if event and event.due_datetime else '',
            'confirmed_at': rec.confirmed_at.strftime('%m/%d/%Y %I:%M %p') if rec.confirmed_at else '',
            'notes': rec.notes or '',
            'week_start_date': rec.week_start_date.isoformat(),
        })

    return jsonify({
        'status': 'success',
        'data': results,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
    })


@lost_demos_bp.route('/api/lost-demos/confirmed-refs')
def confirmed_refs():
    """Return list of event_ref_nums that are confirmed lost. Used by approved events JS."""
    models = get_models()
    LostDemo = models['LostDemo']

    refs = [r.event_ref_num for r in LostDemo.query.all()]
    return jsonify({'status': 'success', 'data': refs})


@lost_demos_bp.route('/api/lost-demos/export')
def export_lost_demos():
    """Export lost demos for a week as CSV."""
    models = get_models()
    Event = models['Event']
    LostDemo = models['LostDemo']

    week_str = request.args.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            week_start = _sunday_of(date.today())
    else:
        week_start = _sunday_of(date.today())

    week_end = week_start + timedelta(days=6)

    records = LostDemo.query.filter(
        LostDemo.week_start_date >= week_start,
        LostDemo.week_start_date <= week_end,
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Lost Demos', f'{week_start} to {week_end}'])
    writer.writerow(['Event #', 'Event Name', 'Event Type', 'Due Date', 'Confirmed At', 'Notes'])

    for rec in records:
        event = Event.query.filter_by(project_ref_num=rec.event_ref_num).first()
        writer.writerow([
            rec.event_ref_num,
            event.project_name if event else 'Unknown',
            event.event_type if event else 'Unknown',
            event.due_datetime.strftime('%m/%d/%Y') if event and event.due_datetime else '',
            rec.confirmed_at.strftime('%m/%d/%Y %I:%M %p') if rec.confirmed_at else '',
            rec.notes or '',
        ])

    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=lost_demos_{week_start}_{week_end}.csv'
    return resp


@lost_demos_bp.route('/events/lost-demos')
def lost_demos_page():
    """Weekly Lost Demos list page."""
    return render_template('lost_demos.html')
```

**Step 4: Register the blueprint in `app/__init__.py`**

After line 255 (`app.register_blueprint(reports_bp)`), add:

```python
from app.routes.lost_demos import lost_demos_bp
app.register_blueprint(lost_demos_bp)
```

**Step 5: Run tests**

Run: `pytest tests/test_lost_demos.py -v`
Expected: PASS for all tests

**Step 6: Commit**

```bash
git add app/routes/lost_demos.py app/__init__.py tests/test_lost_demos.py
git commit -m "feat: add Lost Demos API endpoints with tests"
```

---

### Task 3: Add Lost Demos Category to Approved Events JS

**Files:**
- Modify: `app/static/js/pages/approved-events.js`

**Step 1: Add confirmed refs fetching**

At the top of `fetchApprovedEvents()` (around line 299, after `var club = ...`), fetch confirmed refs in parallel. Replace the function to fetch confirmed refs before categorizing:

After `currentEvents = data.events || [];` (line 342), add:

```javascript
// Fetch confirmed lost demo refs to exclude from Lost Demos category
var confirmedRefs = [];
try {
    var lostResp = await fetch('/api/lost-demos/confirmed-refs');
    var lostData = await lostResp.json();
    if (lostData.status === 'success') {
        confirmedRefs = lostData.data || [];
    }
} catch (err) {
    console.error('Failed to fetch confirmed lost demo refs:', err);
}
currentConfirmedLostRefs = confirmedRefs;
```

At the top of the file (after `var currentFilter = 'all';` on line 20), add:
```javascript
var currentConfirmedLostRefs = [];
```

**Step 2: Update `updateStats()` to include Lost Demos count**

Replace `updateStats` function (lines 410-437) with:

```javascript
function updateStats(summary, events) {
    var scanOutCount = events.filter(function (e) {
        if (!e.is_scheduled || !e.assigned_employee_name) return false;
        var dateToCheck = e.schedule_datetime || e.scheduled_date;
        return isOnOrBeforeToday(dateToCheck);
    }).length;

    var rollScheduledCount = events.filter(function (e) {
        if (!e.is_scheduled || !e.needs_rolling) return false;
        var dateToCheck = e.schedule_datetime || e.scheduled_date;
        return !isOnOrBeforeToday(dateToCheck);
    }).length;

    // Lost demos: unassigned + past due + not already confirmed
    var lostDemoCount = events.filter(function (e) {
        if (e.assigned_employee_name) return false;
        if (currentConfirmedLostRefs.indexOf(e.local_ref_num) !== -1) return false;
        return e.due_datetime && isOnOrBeforeToday(e.due_datetime);
    }).length;

    var rollUnscheduledCount = events.length - scanOutCount - rollScheduledCount - lostDemoCount;

    var totalLIAs = scanOutCount + rollScheduledCount + lostDemoCount + rollUnscheduledCount;

    document.getElementById('statScanOut').textContent = scanOutCount;
    document.getElementById('statRollScheduled').textContent = rollScheduledCount;
    document.getElementById('statLostDemos').textContent = lostDemoCount;
    document.getElementById('statRollUnscheduled').textContent = rollUnscheduledCount;
    document.getElementById('statTotal').textContent = totalLIAs;

    return totalLIAs;
}
```

**Step 3: Update `renderPanelView()` to include Lost Demos panel**

In `renderPanelView` (line 440), after computing `rollScheduledEvents` and before the catch-all, add Lost Demos filtering:

```javascript
// Lost Demos: unassigned + past due + not already confirmed lost
var lostDemoEvents = events.filter(function (e) {
    if (e.assigned_employee_name) return false;
    if (currentConfirmedLostRefs.indexOf(e.local_ref_num) !== -1) return false;
    return e.due_datetime && isOnOrBeforeToday(e.due_datetime);
});
```

Update the catch-all to exclude lost demos:
```javascript
var lostDemoIds = new Set(lostDemoEvents.map(function (e) { return e.event_id; }));
var rollUnscheduledEvents = events.filter(function (e) {
    return !scanOutIds.has(e.event_id) && !rollScheduledIds.has(e.event_id) && !lostDemoIds.has(e.event_id);
});
```

Add filter visibility for lost demos:
```javascript
var showLostDemos = currentFilter === 'all' || currentFilter === 'lost_demos';
```

Add rendering for the Lost Demos panel (after roll scheduled panel rendering, before roll unscheduled):

```javascript
// Render Lost Demos Panel
var lostDemosPanel = document.getElementById('lostDemosPanel');
if (lostDemoEvents.length > 0 && showLostDemos) {
    lostDemosPanel.style.display = 'block';
    document.getElementById('lostDemosPanelCount').textContent = lostDemoEvents.length;
    document.getElementById('lostDemosEvents').innerHTML = lostDemoEvents.map(function (e) {
        return renderLostDemoCard(e);
    }).join('');
} else {
    lostDemosPanel.style.display = 'none';
}
```

**Step 4: Add `renderLostDemoCard()` function**

After `renderEventCard` function, add:

```javascript
function renderLostDemoCard(event) {
    var dueDate = event.due_datetime ? formatDate(event.due_datetime) : formatDate(event.scheduled_date);
    return '<div class="event-card lost-demo-card">' +
        '<span class="event-id">' + escapeHtml(event.event_id) + '</span>' +
        '<span class="event-name" title="' + escapeHtml(event.event_name) + '">' + escapeHtml(event.event_name) + '</span>' +
        '<span class="event-date" style="color: #dc2626;"><i class="fas fa-calendar-times"></i> Due: ' + dueDate + '</span>' +
        '<span class="assigned-to" style="color: #dc2626;"><i class="fas fa-user-slash"></i> Unassigned</span>' +
        '<button class="action-btn danger" data-action="confirm-lost" data-ref-num="' + (event.local_ref_num || event.event_id) + '">' +
        '<i class="fas fa-exclamation-triangle"></i> Confirm Lost</button>' +
        '</div>';
}
```

**Step 5: Add `confirmLostDemo()` function and click handler**

Add the function:

```javascript
async function confirmLostDemo(refNum) {
    if (!confirm('Confirm this event as a Lost Demo?')) return;

    try {
        var response = await fetch('/api/lost-demos/' + refNum + '/confirm', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({})
        });
        var data = await response.json();

        if (response.ok && data.status === 'success') {
            fetchApprovedEvents();  // Refresh
        } else {
            alert('Failed to confirm: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Confirm lost demo error:', error);
        alert('Failed to confirm: ' + error.message);
    }
}
```

Add to the delegated click handler (inside the `switch` statement, around line 997):

```javascript
case 'confirm-lost': confirmLostDemo(target.dataset.refNum); break;
```

**Step 6: Commit**

```bash
git add app/static/js/pages/approved-events.js
git commit -m "feat: add Lost Demos category to approved events page JS"
```

---

### Task 4: Add Lost Demos Panel to Approved Events Template

**Files:**
- Modify: `app/templates/dashboard/approved_events.html`

**Step 1: Add Lost Demos stat card**

After the "Needs Scheduling" stat card (around line 1037-1042) and before the "Total LIAs" card, add:

```html
<div class="stat-card action-card lost-demos" data-action="filter-action" data-filter="lost_demos">
    <div class="action-icon"><i class="fas fa-exclamation-triangle"></i></div>
    <div class="count" id="statLostDemos">0</div>
    <div class="label">Lost Demos</div>
    <div class="action-hint">Unassigned & past due</div>
</div>
```

**Step 2: Add Lost Demos panel**

After the Roll Scheduled panel (line 1101) and before the Roll Unscheduled panel (line 1103), add:

```html
<!-- Lost Demos Panel -->
<div id="lostDemosPanel" class="action-panel" style="display: none;">
    <div class="panel-header lost-demos-header">
        <h3><i class="fas fa-exclamation-triangle"></i> Lost Demos</h3>
        <div style="display: flex; gap: 10px; align-items: center;">
            <span class="panel-count" id="lostDemosPanelCount">0</span>
            <button class="print-btn" data-action="print-category" data-category="lost-demos" title="Print this category">
                <i class="fas fa-print"></i> Print
            </button>
        </div>
    </div>
    <div class="panel-instruction">
        These events are unassigned and past their due date. Confirm them as lost to add to the weekly Lost Demo list.
    </div>
    <div class="panel-events" id="lostDemosEvents"></div>
</div>
```

**Step 3: Add CSS for Lost Demos panel and card styling**

In the `<style>` block, add:

```css
.lost-demos-header {
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
    color: white;
}

.stat-card.lost-demos {
    border-left: 4px solid #dc2626;
}

.lost-demo-card {
    border-left: 3px solid #dc2626;
}

.action-btn.danger {
    background: #dc2626;
    color: white;
    border: none;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
}

.action-btn.danger:hover {
    background: #b91c1c;
}
```

**Step 4: Update print CSS rules**

In the print media query, update the panel hiding rules to include lost-demos:

```css
body.printing-scan-out #rollScheduledPanel,
body.printing-scan-out #rollUnscheduledPanel,
body.printing-scan-out #lostDemosPanel,
body.printing-roll-scheduled #scanOutPanel,
body.printing-roll-scheduled #rollUnscheduledPanel,
body.printing-roll-scheduled #lostDemosPanel,
body.printing-roll-unscheduled #scanOutPanel,
body.printing-roll-unscheduled #rollScheduledPanel,
body.printing-roll-unscheduled #lostDemosPanel,
body.printing-lost-demos #scanOutPanel,
body.printing-lost-demos #rollScheduledPanel,
body.printing-lost-demos #rollUnscheduledPanel {
    display: none !important;
}
```

**Step 5: Commit**

```bash
git add app/templates/dashboard/approved_events.html
git commit -m "feat: add Lost Demos panel and stat card to approved events template"
```

---

### Task 5: Create Weekly Lost Demos List Page

**Files:**
- Create: `app/templates/lost_demos.html`

**Step 1: Create the template**

Create `app/templates/lost_demos.html`:

```html
{% extends "base.html" %}

{% block title %}Lost Demos{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/reports.css') }}">
<style>
    .week-nav {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 24px;
    }
    .week-nav button {
        background: var(--primary);
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 14px;
    }
    .week-nav button:hover { opacity: 0.9; }
    .week-label {
        font-size: 18px;
        font-weight: 600;
    }
    .lost-demos-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 16px;
    }
    .lost-demos-table th,
    .lost-demos-table td {
        padding: 10px 14px;
        text-align: left;
        border-bottom: 1px solid #e5e7eb;
    }
    .lost-demos-table th {
        background: #f9fafb;
        font-weight: 600;
        font-size: 13px;
        text-transform: uppercase;
        color: #6b7280;
    }
    .lost-demos-table tr:hover { background: #f9fafb; }
    .undo-btn {
        background: #f59e0b;
        color: white;
        border: none;
        padding: 4px 12px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
    }
    .undo-btn:hover { background: #d97706; }
    .empty-state {
        text-align: center;
        padding: 60px 20px;
        color: #9ca3af;
    }
    .empty-state i { font-size: 48px; margin-bottom: 16px; }
    .summary-stat {
        font-size: 14px;
        color: #6b7280;
        margin-bottom: 8px;
    }
    @media print {
        .week-nav button, .undo-btn, .report-actions { display: none !important; }
    }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <div class="report-header">
        <div>
            <h1>Lost Demos</h1>
            <div class="subtitle">Weekly list of confirmed lost demo events</div>
        </div>
        <div class="report-actions">
            <a id="exportBtn" href="#" class="btn">Export CSV</a>
            <button class="btn" data-action="print">Print</button>
        </div>
    </div>

    <div class="week-nav">
        <button id="prevWeek"><i class="fas fa-chevron-left"></i> Prev</button>
        <span class="week-label" id="weekLabel">Loading...</span>
        <button id="nextWeek">Next <i class="fas fa-chevron-right"></i></button>
    </div>

    <div class="summary-stat" id="summaryCount"></div>

    <div id="tableContainer">
        <table class="lost-demos-table">
            <thead>
                <tr>
                    <th>Event #</th>
                    <th>Event Name</th>
                    <th>Type</th>
                    <th>Due Date</th>
                    <th>Confirmed</th>
                    <th>Notes</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="demosBody"></tbody>
        </table>
    </div>

    <div id="emptyState" class="empty-state" style="display: none;">
        <i class="fas fa-check-circle"></i>
        <h3>No Lost Demos</h3>
        <p>No confirmed lost demos for this week.</p>
    </div>
</div>

<script>
(function() {
    var currentWeekStart = getSundayOfCurrentWeek();

    function getSundayOfCurrentWeek() {
        var d = new Date();
        var day = d.getDay();
        d.setDate(d.getDate() - day);
        d.setHours(0, 0, 0, 0);
        return d;
    }

    function formatISODate(d) {
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    function formatDisplayDate(d) {
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    function updateUI() {
        var end = new Date(currentWeekStart);
        end.setDate(end.getDate() + 6);
        document.getElementById('weekLabel').textContent =
            formatDisplayDate(currentWeekStart) + ' — ' + formatDisplayDate(end);

        var ws = formatISODate(currentWeekStart);
        document.getElementById('exportBtn').href = '/api/lost-demos/export?week_start=' + ws;

        fetchDemos(ws);
    }

    async function fetchDemos(weekStart) {
        try {
            var resp = await fetch('/api/lost-demos?week_start=' + weekStart);
            var result = await resp.json();

            if (result.status !== 'success') {
                document.getElementById('demosBody').innerHTML = '';
                document.getElementById('emptyState').style.display = 'block';
                document.getElementById('tableContainer').style.display = 'none';
                document.getElementById('summaryCount').textContent = '';
                return;
            }

            var demos = result.data;
            if (demos.length === 0) {
                document.getElementById('demosBody').innerHTML = '';
                document.getElementById('emptyState').style.display = 'block';
                document.getElementById('tableContainer').style.display = 'none';
                document.getElementById('summaryCount').textContent = '0 lost demos this week';
                return;
            }

            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('tableContainer').style.display = 'block';
            document.getElementById('summaryCount').textContent = demos.length + ' lost demo' + (demos.length !== 1 ? 's' : '') + ' this week';

            document.getElementById('demosBody').innerHTML = demos.map(function(d) {
                return '<tr>' +
                    '<td>' + escapeHtml(String(d.event_ref_num)) + '</td>' +
                    '<td>' + escapeHtml(d.event_name) + '</td>' +
                    '<td>' + escapeHtml(d.event_type) + '</td>' +
                    '<td>' + escapeHtml(d.due_date) + '</td>' +
                    '<td>' + escapeHtml(d.confirmed_at) + '</td>' +
                    '<td>' + escapeHtml(d.notes) + '</td>' +
                    '<td><button class="undo-btn" data-action="undo-lost" data-ref="' + d.event_ref_num + '">Undo</button></td>' +
                    '</tr>';
            }).join('');

        } catch (err) {
            console.error('Failed to fetch lost demos:', err);
        }
    }

    function escapeHtml(text) {
        if (text == null) return '';
        return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    document.getElementById('prevWeek').addEventListener('click', function() {
        currentWeekStart.setDate(currentWeekStart.getDate() - 7);
        updateUI();
    });

    document.getElementById('nextWeek').addEventListener('click', function() {
        currentWeekStart.setDate(currentWeekStart.getDate() + 7);
        updateUI();
    });

    document.addEventListener('click', function(e) {
        var target = e.target.closest('[data-action]');
        if (!target) return;

        if (target.dataset.action === 'undo-lost') {
            undoLost(target.dataset.ref);
        } else if (target.dataset.action === 'print') {
            window.print();
        }
    });

    async function undoLost(refNum) {
        if (!confirm('Undo this lost demo confirmation? The event will return to the approved events page.')) return;

        try {
            var resp = await fetch('/api/lost-demos/' + refNum + '/confirm', {
                method: 'DELETE',
                headers: {
                    'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''
                }
            });
            var data = await resp.json();
            if (resp.ok && data.status === 'success') {
                updateUI();
            } else {
                alert('Failed to undo: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            alert('Failed to undo: ' + err.message);
        }
    }

    updateUI();
})();
</script>
{% endblock %}
```

**Step 2: Commit**

```bash
git add app/templates/lost_demos.html
git commit -m "feat: add weekly Lost Demos list page template"
```

---

### Task 6: Add Navigation Link

**Files:**
- Modify: `app/templates/base.html:218-222`

**Step 1: Add Lost Demos nav item**

After the "Left in Approved" sidebar item (line 222), add:

```html
<a href="{{ url_for('lost_demos.lost_demos_page') }}"
    class="sidebar-item {% if request.endpoint == 'lost_demos.lost_demos_page' %}active{% endif %}">
    <span class="material-symbols-outlined">event_busy</span>
    <span>Lost Demos</span>
</a>
```

**Step 2: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add Lost Demos link to sidebar navigation"
```

---

### Task 7: Add Lost Demo Rate to Reports

**Files:**
- Modify: `app/services/report_service.py:10-19` (constructor) and `app/services/report_service.py:21-91` (get_event_statistics method)
- Modify: `app/templates/reports/event_statistics.html:31-48` (stat cards)

**Step 1: Update ReportService constructor**

In `app/services/report_service.py`, add `LostDemo` to the constructor (line 19):

```python
self.LostDemo = models.get('LostDemo')
```

**Step 2: Add lost demo rate to `get_event_statistics`**

At the end of `get_event_statistics`, before the return statement (line 84), add:

```python
# Lost demo rate for the date range
lost_count = 0
if self.LostDemo:
    lost_count = self.LostDemo.query.filter(
        self.LostDemo.week_start_date >= start_date,
        self.LostDemo.week_start_date <= end_date,
    ).count()
lost_rate = round((lost_count / total * 100), 1) if total > 0 else 0
```

Add to the return dict:
```python
'lost_count': lost_count,
'lost_rate': lost_rate,
```

**Step 3: Add Lost Demo Rate stat card to template**

In `app/templates/reports/event_statistics.html`, after the "Unstaffed" stat card (line 47), add:

```html
<div class="stat-card" style="border-left: 4px solid #dc2626;">
    <div class="value">{{ data.lost_rate }}%</div>
    <div class="label">Lost Demo Rate</div>
    <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">{{ data.lost_count }} lost of {{ data.total }} total</div>
</div>
```

**Step 4: Update CSV export to include lost demo rate**

In `app/routes/reports.py`, in `export_event_statistics()` (line 140), update the summary row:

```python
writer.writerow([f'Total: {data["total"]}', f'Completion Rate: {data["completion_rate"]}%',
                 f'Scheduled: {data["scheduled_pct"]}%', f'Unstaffed: {data["unstaffed_pct"]}%',
                 f'Lost Demo Rate: {data["lost_rate"]}%'])
```

**Step 5: Add Lost Demos card to reports index**

In `app/templates/reports/index.html`, add a card in the reports grid (after the last card):

Note: This is NOT a separate report page — it links to Event Statistics which already shows the metric. No new card needed; the metric is embedded in Event Statistics.

**Step 6: Commit**

```bash
git add app/services/report_service.py app/templates/reports/event_statistics.html app/routes/reports.py
git commit -m "feat: add lost demo rate metric to Event Statistics report"
```

---

### Task 8: Handle `local_ref_num` in Approved Events Data

**Files:**
- Modify: `app/static/js/pages/approved-events.js` (if `local_ref_num` is not already in the event data from the API)

The approved events API returns Walmart event data merged with local DB data. The `event_id` is the Walmart event ID, but `confirm-lost` needs the `project_ref_num` (our internal ref). Check what the approved events API returns.

**Step 1: Verify the API response includes `local_ref_num` or `project_ref_num`**

Read the Walmart approved events API route to check what fields are returned. If `local_ref_num` or `project_ref_num` is not included, the API response needs to be modified to include it.

Look at the Walmart API route (`app/integrations/walmart_api/routes.py`) for the `/api/walmart/events/approved` endpoint and check the response shape. The `renderLostDemoCard` function uses `event.local_ref_num || event.event_id` — ensure this field exists.

If the field doesn't exist, update the Walmart API route to include `local_ref_num: event.project_ref_num` in each event dict. If it does exist, no changes needed.

**Step 2: Commit if changes were needed**

```bash
git add app/integrations/walmart_api/routes.py
git commit -m "feat: include local_ref_num in approved events API response"
```

---

### Task 9: Run Full Test Suite

**Step 1: Run all tests**

```bash
pytest -v
```

Expected: All tests pass (178 existing + new lost demos tests).

**Step 2: Manual smoke test**

1. Start dev server: `python wsgi.py`
2. Navigate to Left in Approved page → verify Lost Demos category appears for qualifying events
3. Click "Confirm Lost" → verify event disappears and appears on weekly list
4. Navigate to Events → Lost Demos in sidebar → verify weekly list shows confirmed demos
5. Click "Undo" → verify event returns to approved page
6. Check Export CSV and Print buttons work
7. Navigate to Reports → Event Statistics → verify Lost Demo Rate card appears
8. Done

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Lost Demos feature — tracking, weekly list, reports integration"
```
