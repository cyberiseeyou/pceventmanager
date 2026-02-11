# Workflow Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bugs and add features discovered during workflow testing: employee loading API error, weekly validation page crash, scheduler history filtering/export, and same-week notification system.

**Architecture:** Four independent fix areas that can be implemented in parallel. Bug fixes first (Tasks 1-2), then feature additions (Tasks 3-4). Each task is isolated to minimize risk.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Vanilla JavaScript, CSS

---

## Task 1: Fix Weekly Validation Page Error (CRITICAL)

**Priority:** P0 - Page is completely broken

**Root Cause:** In `dashboard.py`, the `weekly_validation()` function references `models` variable before it's defined.

**Files:**
- Fix: `app/routes/dashboard.py:603-615`
- Test: Manual verification at `/dashboard/weekly-validation`

**Step 1: Read the broken code**

```bash
# Verify the bug exists
grep -n "models\[" app/routes/dashboard.py | head -20
```

Expected: Line ~603 shows `models['Event']` being used

**Step 2: Fix the models initialization**

In `app/routes/dashboard.py`, find the `weekly_validation` function and add `get_models()` call:

```python
# BEFORE (broken):
@dashboard_bp.route('/weekly-validation')
def weekly_validation():
    """Weekly validation dashboard"""
    # ... some code ...
    models = {
        'Event': models['Event'],  # BUG: models not defined!
        'Schedule': models['Schedule'],
        # ...
    }

# AFTER (fixed):
@dashboard_bp.route('/weekly-validation')
def weekly_validation():
    """Weekly validation dashboard"""
    from app.models import get_models, get_db
    models = get_models()
    db = get_db()
    # ... rest of function uses models dict correctly ...
```

**Step 3: Verify the fix**

```bash
# Start the dev server
python wsgi.py &

# Test the page loads
curl -s http://localhost:5000/dashboard/weekly-validation | head -20
# Expected: HTML content, not error page

# Kill the server
pkill -f wsgi.py
```

**Step 4: Commit**

```bash
git add app/routes/dashboard.py
git commit -m "fix: initialize models in weekly_validation before use

The weekly_validation route was referencing the models dict before
calling get_models(), causing 'Unexpected Error' on page load."
```

---

## Task 2: Fix Employee Loading API Error

**Priority:** P1 - Blocks reassignment workflow

**Root Cause:** The JavaScript in `change-employee-modal.js` may not handle all API response formats correctly, and there could be missing error context.

**Files:**
- Investigate: `app/routes/api.py:850-996` (endpoint)
- Fix: `app/static/js/components/change-employee-modal.js:125-163`
- Fix: `app/static/js/components/reschedule-modal.js` (similar pattern)
- Test: Manual test via UI

**Step 1: Add better error logging to the API endpoint**

In `app/routes/api.py`, find the `get_available_employees_for_change` function and add debug logging:

```python
@api_bp.route('/available_employees_for_change/<date>/<event_type>', methods=['GET'])
def get_available_employees_for_change(date, event_type):
    """Get available employees for changing an event assignment"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Loading available employees for date={date}, event_type={event_type}")
        # ... existing code ...

        logger.info(f"Found {len(available_employees)} available employees")
        return jsonify(available_employees)

    except Exception as e:
        logger.error(f"Error loading available employees: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'employees': []}), 500
```

**Step 2: Fix JavaScript error handling in change-employee-modal.js**

In `app/static/js/components/change-employee-modal.js`, update `loadAvailableEmployees()`:

```javascript
async loadAvailableEmployees() {
    const select = this.modalElement.querySelector('#new-employee-select');

    try {
        const url = `/api/available_employees_for_change/${this.eventDate}/${this.eventType}`;
        console.log('Fetching employees from:', url);

        const response = await fetch(url);
        console.log('Response status:', response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        console.log('Received employees:', data);

        // Handle both array and object responses
        const employees = Array.isArray(data) ? data : (data.employees || []);

        if (employees.length === 0) {
            select.innerHTML = '<option value="">No available employees</option>';
            return;
        }

        select.innerHTML = '<option value="">Select an employee...</option>' +
            employees.map(emp =>
                `<option value="${emp.id}">${emp.name} (${emp.role || 'Staff'})</option>`
            ).join('');

    } catch (error) {
        console.error('Failed to load employees:', error);
        select.innerHTML = `<option value="">Error: ${error.message}</option>`;
        this.displayError(`Failed to load employees: ${error.message}`);
    }
}
```

**Step 3: Apply same fix pattern to reschedule-modal.js**

In `app/static/js/components/reschedule-modal.js`, find the employee loading function and apply the same error handling pattern.

**Step 4: Test the fix**

1. Navigate to `/schedule/daily/2026-03-01`
2. Click "More" on an event card
3. Click "Change Employee"
4. Verify the employee dropdown loads (or shows meaningful error)
5. Check browser console for debug logs

**Step 5: Commit**

```bash
git add app/routes/api.py app/static/js/components/change-employee-modal.js app/static/js/components/reschedule-modal.js
git commit -m "fix: improve employee loading error handling in modals

- Add server-side logging for debugging
- Handle both array and object API responses
- Show meaningful error messages instead of generic failure
- Add console logging for troubleshooting"
```

---

## Task 3: Add Scheduler History Filtering and Export

**Priority:** P2 - Enables Tuesday reporting workflow

**Files:**
- Modify: `app/routes/auto_scheduler.py:1500-1593`
- Modify: `app/templates/scheduler_history.html:238-356`
- Create: `app/services/scheduler_export.py`
- Test: Manual verification

### Step 3.1: Add filter parameter to history API

In `app/routes/auto_scheduler.py`, modify the history API endpoint:

```python
@auto_scheduler_bp.route('/api/history/<int:run_id>')
def get_run_history(run_id):
    """Get detailed history for a scheduler run with optional filtering"""
    from app.models import get_models, get_db
    models = get_models()
    db = get_db()

    # Get filter parameter
    status_filter = request.args.get('status', 'all')  # 'all', 'failed', 'scheduled'

    PendingSchedule = models.get('PendingSchedule')
    SchedulerRunHistory = models.get('SchedulerRunHistory')

    # ... existing query setup ...

    query = db.session.query(PendingSchedule).filter(
        PendingSchedule.scheduler_run_id == run_id
    )

    # Apply status filter
    if status_filter == 'failed':
        query = query.filter(PendingSchedule.failure_reason.isnot(None))
    elif status_filter == 'scheduled':
        query = query.filter(PendingSchedule.failure_reason.is_(None))

    pending_schedules = query.all()

    # ... rest of existing code ...
```

### Step 3.2: Add export endpoint

In `app/routes/auto_scheduler.py`, add a new export endpoint:

```python
@auto_scheduler_bp.route('/api/history/<int:run_id>/export')
def export_run_history(run_id):
    """Export scheduler run history to CSV"""
    import csv
    import io
    from flask import Response
    from app.models import get_models, get_db

    models = get_models()
    db = get_db()

    status_filter = request.args.get('status', 'all')

    PendingSchedule = models.get('PendingSchedule')
    Event = models['Event']
    Employee = models['Employee']

    query = db.session.query(PendingSchedule).filter(
        PendingSchedule.scheduler_run_id == run_id
    )

    if status_filter == 'failed':
        query = query.filter(PendingSchedule.failure_reason.isnot(None))
    elif status_filter == 'scheduled':
        query = query.filter(PendingSchedule.failure_reason.is_(None))

    pending_schedules = query.all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(['Event Name', 'Event Type', 'Employee', 'Scheduled Date', 'Event Period', 'Status', 'Failure Reason'])

    for ps in pending_schedules:
        event = db.session.query(Event).filter_by(project_ref_num=ps.event_ref_num).first()
        employee = db.session.query(Employee).filter_by(id=ps.employee_id).first() if ps.employee_id else None

        writer.writerow([
            event.description if event else ps.event_ref_num,
            ps.event_type or 'Unknown',
            employee.name if employee else 'Unassigned',
            ps.proposed_datetime.strftime('%Y-%m-%d %H:%M') if ps.proposed_datetime else '',
            f"{event.start_datetime.strftime('%Y-%m-%d')} to {event.due_datetime.strftime('%Y-%m-%d')}" if event else '',
            'Failed' if ps.failure_reason else 'Scheduled',
            ps.failure_reason or ''
        ])

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=scheduler_run_{run_id}_{status_filter}.csv'}
    )
```

### Step 3.3: Add filter and export UI to template

In `app/templates/scheduler_history.html`, add filter buttons and export link after the run header:

```html
<!-- Add after line ~270, inside the run card header area -->
<div class="run-filters" style="margin-top: 10px;">
    <div class="btn-group btn-group-sm" role="group" aria-label="Filter events">
        <button type="button" class="btn btn-outline-secondary filter-btn active" data-filter="all" onclick="filterEvents(this, {{ run.id }}, 'all')">
            All ({{ run.scheduled_count + run.failed_count }})
        </button>
        <button type="button" class="btn btn-outline-success filter-btn" data-filter="scheduled" onclick="filterEvents(this, {{ run.id }}, 'scheduled')">
            ✓ Scheduled ({{ run.scheduled_count }})
        </button>
        <button type="button" class="btn btn-outline-danger filter-btn" data-filter="failed" onclick="filterEvents(this, {{ run.id }}, 'failed')">
            ✗ Failed ({{ run.failed_count }})
        </button>
    </div>
    <a href="/auto-schedule/api/history/{{ run.id }}/export?status=failed" class="btn btn-sm btn-outline-primary ms-2" download>
        📥 Export Failed to CSV
    </a>
</div>
```

### Step 3.4: Add JavaScript filter function

In `app/templates/scheduler_history.html`, add the filter JavaScript:

```javascript
// Add to the script section
async function filterEvents(button, runId, status) {
    // Update active button state
    const btnGroup = button.closest('.btn-group');
    btnGroup.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');

    // Update export link
    const exportLink = button.closest('.run-filters').querySelector('a[download]');
    exportLink.href = `/auto-schedule/api/history/${runId}/export?status=${status}`;
    exportLink.textContent = status === 'all' ? '📥 Export All to CSV' :
                             status === 'failed' ? '📥 Export Failed to CSV' :
                             '📥 Export Scheduled to CSV';

    // Reload events with filter
    await loadRunEvents(runId, status);
}

// Modify existing loadRunEvents to accept status parameter
async function loadRunEvents(runId, status = 'all') {
    const container = document.getElementById(`events-${runId}`);
    container.innerHTML = '<div class="loading">Loading events...</div>';

    try {
        const response = await fetch(`/auto-schedule/api/history/${runId}?status=${status}`);
        const data = await response.json();
        // ... rest of existing rendering code ...
    } catch (error) {
        container.innerHTML = `<div class="error">Failed to load events: ${error.message}</div>`;
    }
}
```

### Step 3.5: Test the changes

1. Navigate to `/auto-schedule/history`
2. Expand a run with failed events
3. Click "Failed" filter button - should show only failed events
4. Click "Export Failed to CSV" - should download CSV file
5. Open CSV and verify content

### Step 3.6: Commit

```bash
git add app/routes/auto_scheduler.py app/templates/scheduler_history.html
git commit -m "feat: add filtering and CSV export to scheduler history

- Add status filter parameter to history API (all/failed/scheduled)
- Add CSV export endpoint for scheduler runs
- Add filter toggle buttons in UI
- Add export button that updates based on current filter

Enables Tuesday evening 'lost events' reporting workflow."
```

---

## Task 4: Add Same-Week Schedule Notification System

**Priority:** P2 - Prevents missed employee notifications

**Files:**
- Modify: `app/routes/api.py` (schedule-event endpoint)
- Create: `app/static/js/components/notification-modal.js`
- Modify: `app/static/js/components/change-employee-modal.js`
- Modify: `app/static/js/components/reschedule-modal.js`
- Create: `app/static/css/components/notification-modal.css`
- Modify: `app/templates/base.html` (include new JS/CSS)

### Step 4.1: Add same-week detection to API

In `app/routes/api.py`, modify the `schedule_event` endpoint to detect same-week assignments:

```python
@api_bp.route('/schedule-event', methods=['POST'])
def schedule_event():
    """Schedule an employee for an event"""
    from datetime import datetime, timedelta
    from app.models import get_models, get_db

    models = get_models()
    db = get_db()
    Employee = models['Employee']

    data = request.get_json()
    employee_id = data.get('employee_id')
    event_date_str = data.get('date')
    override_notification = data.get('override_notification', False)

    # Parse the event date
    event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
    today = datetime.now().date()

    # Check if this is a same-week assignment (within 7 days)
    days_until_event = (event_date - today).days
    is_same_week = 0 <= days_until_event <= 7

    # If same-week and not overridden, return notification required response
    if is_same_week and not override_notification:
        employee = db.session.query(Employee).filter_by(id=employee_id).first()
        if employee:
            return jsonify({
                'status': 'notification_required',
                'message': 'This is a same-week schedule change. The employee should be notified.',
                'employee': {
                    'id': employee.id,
                    'name': employee.name,
                    'phone': employee.phone,
                    'email': getattr(employee, 'email', None)
                },
                'event_date': event_date_str,
                'days_until': days_until_event
            }), 202  # 202 Accepted - needs further action

    # ... rest of existing scheduling logic ...
```

### Step 4.2: Create notification modal component

Create `app/static/js/components/notification-modal.js`:

```javascript
/**
 * Notification Modal Component
 * Shows a blocking modal when same-week schedule changes require employee notification
 */
class NotificationModal {
    constructor(data, onConfirm, onCancel) {
        this.data = data;
        this.onConfirm = onConfirm;
        this.onCancel = onCancel;
        this.modalElement = null;
    }

    open() {
        this.render();
        this.attachEventListeners();
        document.body.style.overflow = 'hidden';
    }

    render() {
        const { employee, event_date, days_until } = this.data;

        const urgencyText = days_until === 0 ? 'TODAY' :
                           days_until === 1 ? 'TOMORROW' :
                           `in ${days_until} days`;

        const modalHTML = `
            <div class="modal notification-modal" id="notification-modal">
                <div class="modal-overlay"></div>
                <div class="modal-container">
                    <div class="modal-header notification-header">
                        <h2>📱 Same-Week Schedule Change</h2>
                    </div>

                    <div class="modal-body">
                        <div class="notification-alert">
                            <div class="alert-icon">⚠️</div>
                            <div class="alert-text">
                                <strong>${employee.name}</strong> is being added to a shift
                                <strong>${urgencyText}</strong> (${event_date}).
                                <br>They should be notified of this change.
                            </div>
                        </div>

                        <div class="contact-info">
                            <h4>Contact Information:</h4>
                            <div class="contact-row">
                                <span class="contact-label">📞 Phone:</span>
                                <span class="contact-value">${employee.phone || 'Not available'}</span>
                                ${employee.phone ? `<button type="button" class="btn-copy" onclick="navigator.clipboard.writeText('${employee.phone}')">Copy</button>` : ''}
                            </div>
                            ${employee.email ? `
                            <div class="contact-row">
                                <span class="contact-label">📧 Email:</span>
                                <span class="contact-value">${employee.email}</span>
                                <button type="button" class="btn-copy" onclick="navigator.clipboard.writeText('${employee.email}')">Copy</button>
                            </div>
                            ` : ''}
                        </div>

                        <div class="message-template">
                            <h4>Suggested Message:</h4>
                            <textarea id="notification-message" rows="3" readonly>Hi ${employee.name.split(' ')[0]}, this is your supervisor from Product Connections. You've been added to the schedule for ${event_date}. Please confirm you can make it. Thanks!</textarea>
                            <button type="button" class="btn btn-secondary btn-sm" onclick="navigator.clipboard.writeText(document.getElementById('notification-message').value)">
                                📋 Copy Message
                            </button>
                        </div>

                        <div class="notification-options">
                            <h4>How will you notify them?</h4>
                            <div class="option-buttons">
                                <label class="option-btn">
                                    <input type="radio" name="notify-method" value="text" required>
                                    <span>📱 I'll text them</span>
                                </label>
                                <label class="option-btn">
                                    <input type="radio" name="notify-method" value="call">
                                    <span>📞 I'll call them</span>
                                </label>
                                <label class="option-btn">
                                    <input type="radio" name="notify-method" value="already">
                                    <span>✅ Already notified</span>
                                </label>
                                <label class="option-btn">
                                    <input type="radio" name="notify-method" value="not-needed">
                                    <span>⏭️ Not needed</span>
                                </label>
                            </div>
                        </div>
                    </div>

                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" id="btn-cancel-notification">Cancel Assignment</button>
                        <button type="button" class="btn btn-primary" id="btn-confirm-notification" disabled>
                            Confirm & Continue
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('notification-modal');
        if (existingModal) existingModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.modalElement = document.getElementById('notification-modal');
        this.modalElement.classList.add('modal-open');
    }

    attachEventListeners() {
        const cancelBtn = this.modalElement.querySelector('#btn-cancel-notification');
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-notification');
        const radios = this.modalElement.querySelectorAll('input[name="notify-method"]');

        cancelBtn.addEventListener('click', () => {
            this.close();
            if (this.onCancel) this.onCancel();
        });

        confirmBtn.addEventListener('click', () => {
            const selected = this.modalElement.querySelector('input[name="notify-method"]:checked');
            this.close();
            if (this.onConfirm) this.onConfirm(selected.value);
        });

        // Enable confirm button when an option is selected
        radios.forEach(radio => {
            radio.addEventListener('change', () => {
                confirmBtn.disabled = false;
            });
        });

        // Escape key handler
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                this.close();
                if (this.onCancel) this.onCancel();
            }
        };
        document.addEventListener('keydown', handleEscape);
        this.modalElement._escapeHandler = handleEscape;
    }

    close() {
        if (!this.modalElement) return;

        if (this.modalElement._escapeHandler) {
            document.removeEventListener('keydown', this.modalElement._escapeHandler);
        }

        this.modalElement.classList.remove('modal-open');
        document.body.style.overflow = '';

        setTimeout(() => {
            this.modalElement.remove();
            this.modalElement = null;
        }, 200);
    }
}

// Export for use in other modules
window.NotificationModal = NotificationModal;
```

### Step 4.3: Create notification modal CSS

Create `app/static/css/components/notification-modal.css`:

```css
.notification-modal .modal-container {
    max-width: 500px;
}

.notification-modal .notification-header {
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: white;
}

.notification-modal .notification-header h2 {
    margin: 0;
    font-size: 1.25rem;
}

.notification-alert {
    display: flex;
    gap: 12px;
    padding: 16px;
    background: #fef3c7;
    border: 1px solid #f59e0b;
    border-radius: 8px;
    margin-bottom: 20px;
}

.notification-alert .alert-icon {
    font-size: 2rem;
}

.notification-alert .alert-text {
    flex: 1;
    line-height: 1.5;
}

.contact-info, .message-template, .notification-options {
    margin-bottom: 20px;
}

.contact-info h4, .message-template h4, .notification-options h4 {
    font-size: 0.9rem;
    color: #6b7280;
    margin-bottom: 8px;
}

.contact-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
    border-bottom: 1px solid #e5e7eb;
}

.contact-label {
    font-weight: 500;
    min-width: 80px;
}

.contact-value {
    flex: 1;
    font-family: monospace;
    font-size: 1.1rem;
}

.btn-copy {
    padding: 4px 8px;
    font-size: 0.75rem;
    background: #e5e7eb;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

.btn-copy:hover {
    background: #d1d5db;
}

.message-template textarea {
    width: 100%;
    padding: 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.9rem;
    resize: none;
    background: #f9fafb;
    margin-bottom: 8px;
}

.option-buttons {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}

.option-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
}

.option-btn:hover {
    border-color: #3b82f6;
    background: #eff6ff;
}

.option-btn input {
    margin: 0;
}

.option-btn input:checked + span {
    font-weight: 600;
}

.option-btn:has(input:checked) {
    border-color: #3b82f6;
    background: #eff6ff;
}
```

### Step 4.4: Integrate into change-employee-modal.js

In `app/static/js/components/change-employee-modal.js`, modify `executeChange()`:

```javascript
async executeChange() {
    // ... existing validation code ...

    try {
        const response = await fetch('/api/schedule-event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify({
                employee_id: newEmployeeId,
                event_ref_num: this.eventRefNum,
                date: this.eventDate,
                time: this.eventTime,
                override_notification: false
            })
        });

        const result = await response.json();

        // Handle notification required response
        if (response.status === 202 && result.status === 'notification_required') {
            const notificationModal = new NotificationModal(
                result,
                // On confirm - retry with override
                async (notifyMethod) => {
                    console.log('Notification method selected:', notifyMethod);
                    await this.executeChangeWithOverride(newEmployeeId);
                },
                // On cancel - do nothing
                () => {
                    console.log('Assignment cancelled');
                }
            );
            notificationModal.open();
            return;
        }

        // ... rest of existing success/error handling ...

    } catch (error) {
        // ... existing error handling ...
    }
}

async executeChangeWithOverride(newEmployeeId) {
    try {
        const response = await fetch('/api/schedule-event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify({
                employee_id: newEmployeeId,
                event_ref_num: this.eventRefNum,
                date: this.eventDate,
                time: this.eventTime,
                override_notification: true
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to change employee');
        }

        this.showNotification('Employee changed successfully', 'success');
        this.close();
        setTimeout(() => location.reload(), 1000);

    } catch (error) {
        this.displayError(error.message);
    }
}
```

### Step 4.5: Include new files in base template

In `app/templates/base.html`, add the new CSS and JS:

```html
<!-- In the <head> section, after other CSS -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/notification-modal.css') }}">

<!-- Before closing </body> tag, after other scripts -->
<script src="{{ url_for('static', filename='js/components/notification-modal.js') }}"></script>
```

### Step 4.6: Test the feature

1. Navigate to `/schedule/daily/2026-02-02` (within 7 days of today)
2. Click "More" on an event > "Change Employee"
3. Select a different employee
4. Click "Change Employee" button
5. Verify notification modal appears with:
   - Employee name and phone
   - Suggested message with copy button
   - Radio options for notification method
   - Confirm button disabled until option selected
6. Select an option and confirm
7. Verify assignment completes

### Step 4.7: Commit

```bash
git add app/routes/api.py app/static/js/components/notification-modal.js app/static/css/components/notification-modal.css app/static/js/components/change-employee-modal.js app/templates/base.html
git commit -m "feat: add same-week schedule notification system

- API returns 202 status when same-week assignment detected
- New NotificationModal component shows employee contact info
- Pre-written message template with copy button
- Requires selecting notification method before proceeding
- Override flag allows continuing after acknowledgment

Prevents forgetting to notify employees about last-minute schedule changes."
```

---

## Summary

| Task | Priority | Complexity | Files Changed |
|------|----------|------------|---------------|
| 1. Fix Weekly Validation | P0 | Low | 1 |
| 2. Fix Employee Loading | P1 | Medium | 3 |
| 3. Add History Filter/Export | P2 | Medium | 2 |
| 4. Add Notification System | P2 | High | 6 |

**Recommended Order:** 1 → 2 → 3 → 4 (dependencies and risk-based)

**Total Estimated Files:** 12 files modified/created

---

## Testing Checklist

After all tasks complete:

- [ ] `/dashboard/weekly-validation` loads without error
- [ ] Change Employee modal loads employees or shows meaningful error
- [ ] Reschedule modal loads employees or shows meaningful error
- [ ] `/auto-schedule/history` shows filter buttons
- [ ] Failed events filter shows only failed
- [ ] CSV export downloads correctly
- [ ] Same-week assignment shows notification modal
- [ ] Notification modal displays employee phone
- [ ] Copy message button works
- [ ] Assignment completes after notification acknowledged
