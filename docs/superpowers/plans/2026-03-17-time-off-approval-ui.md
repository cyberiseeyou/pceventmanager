# Time Off Approval UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Pending Approvals" tab to the existing Time Off Requests page so supervisors can approve/deny employee-submitted time-off requests, surface pending requests in the notification bell, and fix the CP-SAT scheduler to only honor approved time-off.

**Architecture:** Three small, independent changes: (1) new tab + JS on existing template using existing API endpoints, (2) one new notification check in the existing notification aggregator (supervisor-only), (3) one-line filter fix in CP-SAT. All changes use existing patterns — no new files, models, or endpoints needed.

**Tech Stack:** Flask/Jinja2, vanilla JS, existing CSS design system (`.condition-tabs`, `.tab-btn`, `.tab-count` from `unscheduled.css`)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/templates/time_off_requests.html` | Modify | Add "Pending Approvals" tab (supervisor-only), approval cards, review modal, JS handlers |
| `app/routes/employees.py:24-27` | Modify | Pass `is_supervisor` flag to template |
| `app/routes/employees.py:791` | Modify | Restrict `GET /api/time-off/pending` to supervisor only (remove lead) |
| `app/routes/api_notifications.py:238` | Modify | Add Check 9: count pending time-off requests (supervisor-only) |
| `app/services/cpsat_scheduler.py:510-514` | Modify | Filter `EmployeeTimeOff` by `status='approved'` |

---

### Task 1: Fix CP-SAT to only honor approved time-off

**Files:**
- Modify: `app/services/cpsat_scheduler.py:510-514`

- [ ] **Step 1: Fix the filter**

In `app/services/cpsat_scheduler.py`, replace lines 510-514:

```python
# Before:
        # TODO Fix #3: When EmployeeTimeOff gains an 'approved' or 'status'
        # column, filter here: .filter_by(status='approved') or
        # .filter(EmployeeTimeOff.approved == True)
        if self.EmployeeTimeOff:
            for to in self.EmployeeTimeOff.query.all():

# After:
        if self.EmployeeTimeOff:
            for to in self.EmployeeTimeOff.query.filter_by(status='approved').all():
```

Note: The `status` column has `server_default='approved'`, so all pre-existing records already have `'approved'` — no NULL safety net needed.

- [ ] **Step 2: Verify no regressions**

Run: `pytest tests/test_cpsat_stress.py -v --timeout=120`
Expected: All 38 stress tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/services/cpsat_scheduler.py
git commit -m "fix: CP-SAT solver only honors approved time-off requests"
```

---

### Task 2: Restrict pending time-off endpoint and pass role to template

**Files:**
- Modify: `app/routes/employees.py:24-27, 791`

- [ ] **Step 1: Change role restriction on pending endpoint**

At line 791 of `app/routes/employees.py`, change:

```python
# Before:
@require_role('supervisor', 'lead')

# After:
@require_role('supervisor')
```

- [ ] **Step 2: Pass `is_supervisor` to the template**

Update the `time_off_requests` route (lines 24-27) to pass the user's role:

```python
@employees_bp.route('/time-off')
@require_authentication()
def time_off_requests():
    """Display time off requests management page"""
    user = get_current_user()
    is_supervisor = user.get('role') == 'supervisor' if user else False
    return render_template('time_off_requests.html', is_supervisor=is_supervisor)
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/employees.py
git commit -m "fix: restrict pending time-off to supervisor, pass role to template"
```

---

### Task 3: Add "Pending Approvals" tab to Time Off Requests page

**Files:**
- Modify: `app/templates/time_off_requests.html`

This is the main UI work. We add a third tab (supervisor-only) using the existing `.condition-tabs` / `.tab-btn` pattern from `unscheduled.css`, a new tab panel with approval cards, and a deny-reason modal.

- [ ] **Step 1: Add the tab CSS from the design system**

The tab styles (`.condition-tabs`, `.tab-btn`, `.tab-count`) live in `app/static/css/pages/unscheduled.css`. Copy the tab-related rules (lines 493-567) into the `<style>` block of `time_off_requests.html` to avoid importing the entire 800+ line file and risking style collisions. Add these at the top of the `<style>` block:

```css
/* Tab styles (from design system - unscheduled.css) */
.condition-tabs {
    display: flex;
    gap: var(--spacing-xs);
    margin-bottom: var(--spacing-lg);
    border-bottom: 2px solid var(--pc-light-blue);
    padding-bottom: 0;
}

.tab-btn {
    padding: var(--spacing-sm) var(--spacing-md);
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    color: var(--text-secondary);
    text-decoration: none;
    font-weight: var(--font-weight-bold);
    transition: all 0.2s ease;
    margin-bottom: -2px;
    cursor: pointer;
}

.tab-btn:hover {
    color: var(--pc-blue);
    background: rgba(27, 155, 216, 0.05);
}

.tab-btn.active {
    color: var(--pc-navy);
    border-bottom-color: var(--pc-navy);
    background: rgba(46, 76, 115, 0.05);
}

.tab-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
    background: #e5e7eb;
    color: #6b7280;
    margin-left: 4px;
}

.tab-btn.active .tab-count {
    background: var(--pc-navy);
    color: white;
}

.tab-btn-warning {
    color: #b45309;
}

.tab-btn-warning:hover {
    color: #92400e;
    background: rgba(245, 158, 11, 0.08);
}

.tab-btn-warning.active {
    color: #92400e;
    border-bottom-color: #d97706;
    background: rgba(245, 158, 11, 0.08);
}

.tab-btn-warning .tab-count {
    background: rgba(245, 158, 11, 0.15);
    color: #b45309;
}

.tab-btn-warning.active .tab-count {
    background: #d97706;
    color: white;
}
```

Note: The template already has mobile `.condition-tabs` / `.tab-btn` overrides at lines 233-235 in the `@media (max-width: 480px)` block — keep those as-is, they complement the base styles above.

- [ ] **Step 2: Add "Pending Approvals" tab button (supervisor-only) with count badge**

Replace the tab navigation (lines 264-267) with:

```html
<!-- Tab Navigation -->
<div class="condition-tabs" style="margin-bottom: var(--spacing-lg);">
    <button class="tab-btn active" data-action="show-tab" data-tab="time-off">Time Off Requests</button>
    {% if is_supervisor %}
    <button class="tab-btn tab-btn-warning" data-action="show-tab" data-tab="pending">
        Pending Approvals <span id="pending-count" class="tab-count" style="display:none;">0</span>
    </button>
    {% endif %}
    <button class="tab-btn" data-action="show-tab" data-tab="overrides">Availability Overrides</button>
</div>
```

The `tab-btn-warning` class gives the pending tab an amber/orange color to draw supervisor attention — consistent with the warning tab pattern in `unscheduled.css`.

- [ ] **Step 3: Add the Pending Approvals tab panel**

After the `<!-- ===== TIME OFF TAB ===== -->` section (after line 293, before the overrides tab), insert:

```html
{% if is_supervisor %}
<!-- ===== PENDING APPROVALS TAB ===== -->
<div id="tab-pending" style="display: none;">
    <div class="time-off-list">
        <div id="pending-container">
            <div class="empty-state">Loading pending requests...</div>
        </div>
    </div>
</div>
{% endif %}
```

- [ ] **Step 4: Add approval card CSS**

Add these styles to the `<style>` block inside `extra_head`:

```css
/* Pending Approval Cards */
.approval-card {
    background: var(--bg-secondary);
    border-left: 4px solid #f59e0b;
    border-radius: var(--border-radius-md);
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
    transition: all 0.2s ease;
}

.approval-card:hover {
    box-shadow: var(--shadow-sm);
    transform: translateX(4px);
}

.approval-card:last-child {
    margin-bottom: 0;
}

.approval-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: var(--spacing-sm);
}

.approval-card-employee {
    font-size: var(--font-size-body);
    font-weight: var(--font-weight-bold);
    color: var(--pc-navy);
}

.approval-card-submitted {
    font-size: var(--font-size-small);
    color: var(--text-muted);
}

.approval-card-dates {
    font-size: var(--font-size-small);
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: var(--spacing-xs);
}

.approval-card-reason {
    font-size: var(--font-size-small);
    color: var(--text-muted);
    font-style: italic;
    margin-bottom: var(--spacing-sm);
}

.approval-card-actions {
    display: flex;
    gap: var(--spacing-sm);
}

.btn-approve {
    background: #fff;
    border: 1px solid #16a34a;
    color: #16a34a;
    padding: 6px 16px;
    border-radius: var(--border-radius-sm);
    cursor: pointer;
    font-size: var(--font-size-small);
    font-weight: 500;
    transition: all 0.2s ease;
}

.btn-approve:hover {
    background: #16a34a;
    color: white;
}

.btn-deny {
    background: #fff;
    border: 1px solid #dc3545;
    color: #dc3545;
    padding: 6px 16px;
    border-radius: var(--border-radius-sm);
    cursor: pointer;
    font-size: var(--font-size-small);
    font-weight: 500;
    transition: all 0.2s ease;
}

.btn-deny:hover {
    background: #dc3545;
    color: white;
}

/* Deny Reason Modal (reuses existing modal pattern) */
#deny-reason-modal .modal-body {
    padding: var(--spacing-lg);
}

#deny-reason-modal .modal-title {
    color: var(--pc-navy);
}

#deny-reason-modal .modal-header {
    border-bottom: 2px solid #dc3545;
}

.deny-employee-name {
    font-weight: var(--font-weight-bold);
    color: var(--pc-navy);
    margin-bottom: var(--spacing-sm);
}

.deny-date-range {
    font-size: var(--font-size-small);
    color: var(--text-secondary);
    margin-bottom: var(--spacing-md);
}

@media (max-width: 480px) {
    .approval-card { padding: 14px; }
    .approval-card-header { flex-direction: column; gap: 4px; }
    .approval-card-actions { width: 100%; }
    .approval-card-actions button { flex: 1; min-height: 44px; text-align: center; }
}
```

- [ ] **Step 5: Add the Deny Reason modal (supervisor-only)**

Add this modal after the existing `add-override-modal` (after line 431), before `{% endblock %}`:

```html
{% if is_supervisor %}
<!-- Deny Time Off Modal -->
<div id="deny-reason-modal" class="modal">
    <div class="modal-overlay" data-action="close-deny-modal"></div>
    <div class="modal-container">
        <div class="modal-header">
            <h2 class="modal-title">Deny Time Off Request</h2>
            <button class="modal-close" data-action="close-deny-modal" aria-label="Close">&times;</button>
        </div>
        <div class="modal-body">
            <div class="deny-employee-name" id="deny-employee-name"></div>
            <div class="deny-date-range" id="deny-date-range"></div>
            <div class="form-group">
                <label for="deny-reason-input">Reason for Denial (optional)</label>
                <textarea id="deny-reason-input" rows="3"
                    placeholder="e.g., Too many employees off that week"></textarea>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-action="close-deny-modal">Cancel</button>
                <button type="button" class="btn btn-primary" id="confirm-deny-btn"
                    style="background: #dc3545; border-color: #dc3545;">Deny Request</button>
            </div>
        </div>
    </div>
</div>
{% endif %}
```

- [ ] **Step 6: Add JS for pending approvals tab (supervisor-only)**

Wrap the pending-approvals JS in a Jinja conditional. Add the following inside the `<script>` block, before the delegated click handler:

```javascript
{% if is_supervisor %}
// ===== PENDING APPROVALS TAB =====
let pendingRequests = [];
let denyingRequestId = null;

async function loadPendingRequests() {
    const container = document.getElementById('pending-container');
    container.innerHTML = '<div class="empty-state">Loading pending requests...</div>';

    try {
        const response = await fetch('/api/time-off/pending');
        if (!response.ok) throw new Error('Failed to load pending requests');

        pendingRequests = await response.json();
        updatePendingCount(pendingRequests.length);
        displayPendingRequests();
    } catch (error) {
        console.error('Error loading pending requests:', error);
        container.innerHTML = '<div class="alert alert-error">Error loading pending requests</div>';
    }
}

function updatePendingCount(count) {
    const badge = document.getElementById('pending-count');
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = '';
    } else {
        badge.style.display = 'none';
    }
}

function displayPendingRequests() {
    const container = document.getElementById('pending-container');

    if (pendingRequests.length === 0) {
        container.innerHTML = '<div class="empty-state">No pending time off requests</div>';
        return;
    }

    container.innerHTML = pendingRequests.map(req => createApprovalCard(req)).join('');
}

function createApprovalCard(req) {
    const formatDate = (dateStr) => {
        const [year, month, day] = dateStr.split('-');
        return new Date(year, month - 1, day).toLocaleDateString();
    };

    const dateDisplay = req.start_date === req.end_date
        ? formatDate(req.start_date)
        : `${formatDate(req.start_date)} - ${formatDate(req.end_date)}`;

    const submittedDate = new Date(req.created_at).toLocaleDateString();

    return `
        <div class="approval-card" data-request-id="${req.id}">
            <div class="approval-card-header">
                <div class="approval-card-employee">${toTitleCase(req.employee_name)}</div>
                <div class="approval-card-submitted">Submitted ${submittedDate}</div>
            </div>
            <div class="approval-card-dates">${escapeHtml(dateDisplay)}</div>
            ${req.reason ? `<div class="approval-card-reason">Reason: ${escapeHtml(req.reason)}</div>` : ''}
            <div class="approval-card-actions">
                <button class="btn-approve" data-action="approve-request" data-request-id="${req.id}">Approve</button>
                <button class="btn-deny" data-action="deny-request" data-request-id="${req.id}"
                    data-employee-name="${escapeHtml(req.employee_name)}"
                    data-date-range="${escapeHtml(dateDisplay)}">Deny</button>
            </div>
        </div>
    `;
}

async function approveRequest(requestId) {
    try {
        const response = await fetch(`/api/time-off/${requestId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'approve' })
        });

        const data = await response.json();
        if (!response.ok) {
            showFlashMessage(`Error: ${data.error}`, 'error');
            return;
        }

        showFlashMessage(data.message, 'success');
        await loadPendingRequests();
        // Also refresh main time-off list since status changed
        await loadAllTimeOffRequests();
        filterRequests();
    } catch (error) {
        console.error('Error approving request:', error);
        showFlashMessage('Error approving request. Please try again.', 'error');
    }
}

function openDenyModal(requestId, employeeName, dateRange) {
    denyingRequestId = requestId;
    document.getElementById('deny-employee-name').textContent = toTitleCase(employeeName);
    document.getElementById('deny-date-range').textContent = dateRange;
    document.getElementById('deny-reason-input').value = '';

    const modal = document.getElementById('deny-reason-modal');
    if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }
    modal.classList.add('modal-open');
}

function closeDenyModal() {
    denyingRequestId = null;
    document.getElementById('deny-reason-modal').classList.remove('modal-open');
}

async function confirmDeny() {
    if (!denyingRequestId) return;

    const reason = document.getElementById('deny-reason-input').value.trim();

    try {
        const response = await fetch(`/api/time-off/${denyingRequestId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'deny', reason: reason })
        });

        const data = await response.json();
        if (!response.ok) {
            showFlashMessage(`Error: ${data.error}`, 'error');
            return;
        }

        closeDenyModal();
        showFlashMessage(data.message, 'success');
        await loadPendingRequests();
        await loadAllTimeOffRequests();
        filterRequests();
    } catch (error) {
        console.error('Error denying request:', error);
        showFlashMessage('Error denying request. Please try again.', 'error');
    }
}
{% endif %}
```

- [ ] **Step 7: Wire up the new actions in the delegated click handler**

In the existing delegated `document.addEventListener('click', ...)` handler (around line 993), add these cases to the switch statement (inside `{% if is_supervisor %}` or unconditionally since the buttons won't exist for non-supervisors):

```javascript
case 'approve-request':
    approveRequest(parseInt(target.dataset.requestId));
    break;
case 'deny-request':
    openDenyModal(
        parseInt(target.dataset.requestId),
        target.dataset.employeeName,
        target.dataset.dateRange
    );
    break;
case 'close-deny-modal':
    closeDenyModal();
    break;
```

- [ ] **Step 8: Update tab switching and page init**

Update the `showTab()` function to handle the new tab:

```javascript
function showTab(tabName) {
    document.getElementById('tab-time-off').style.display = tabName === 'time-off' ? '' : 'none';
    var pendingTab = document.getElementById('tab-pending');
    if (pendingTab) pendingTab.style.display = tabName === 'pending' ? '' : 'none';
    document.getElementById('tab-overrides').style.display = tabName === 'overrides' ? '' : 'none';
    document.querySelectorAll('[data-action="show-tab"]').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    if (tabName === 'overrides') loadOverrides();
    if (tabName === 'pending' && typeof loadPendingRequests === 'function') loadPendingRequests();
}
```

Update `initializePage()` to load pending count and handle `?tab=pending` URL param:

```javascript
async function initializePage() {
    await loadEmployees();
    await loadAllTimeOffRequests();
    setupEventListeners();
    setupDateInputs();

    // Supervisor-only: load pending count and wire deny button
    if (typeof loadPendingRequests === 'function') {
        await loadPendingRequests();
        var confirmDenyBtn = document.getElementById('confirm-deny-btn');
        if (confirmDenyBtn) {
            confirmDenyBtn.addEventListener('click', confirmDeny);
        }
    }

    // Check for tab parameter in URL (e.g., ?tab=pending from notification link)
    var urlParams = new URLSearchParams(window.location.search);
    var tabParam = urlParams.get('tab');
    if (tabParam) {
        showTab(tabParam);
    }
}
```

Note: `loadPendingRequests()` runs once on init (for the badge count), and `showTab('pending')` also calls it — but only when `?tab=pending` is in the URL. Since `showTab` is called after init finishes, this at most results in one redundant fetch that ensures fresh data is displayed. Acceptable tradeoff for simplicity.

- [ ] **Step 9: Commit**

```bash
git add app/templates/time_off_requests.html
git commit -m "feat: add Pending Approvals tab with approve/deny workflow"
```

---

### Task 4: Add pending time-off to notification panel (supervisor-only)

**Files:**
- Modify: `app/routes/api_notifications.py:238` (before the count calculation)

- [ ] **Step 1: Import get_current_user**

At the top of `api_notifications.py`, add the import:

```python
from app.routes.auth import get_current_user
```

- [ ] **Step 2: Add Check 9 for pending time-off requests (supervisor-gated)**

After the existing Check 8 (notes due today, around line 238) and before the `# Calculate total count` line, add:

```python
            # Check 9: Pending time off requests awaiting supervisor review
            user = get_current_user()
            if user and user.get('role') == 'supervisor':
                EmployeeTimeOff = models.get('EmployeeTimeOff')
                if EmployeeTimeOff:
                    pending_time_off = EmployeeTimeOff.query.filter_by(
                        status='pending'
                    ).count()

                    if pending_time_off > 0:
                        notifications['warning'].append({
                            'id': 'pending_time_off',
                            'type': 'pending_time_off',
                            'title': f'{pending_time_off} Pending Time Off Request(s)',
                            'message': f'{pending_time_off} employee time off request(s) awaiting your review',
                            'action_url': '/time-off?tab=pending',
                            'action_text': 'Review Requests'
                        })
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/api_notifications.py
git commit -m "feat: show pending time-off requests in supervisor notification panel"
```

---

### Task 5: Verify everything works together

- [ ] **Step 1: Run full test suite**

Run: `pytest -v --timeout=120`
Expected: All tests pass (308+).

- [ ] **Step 2: Manual smoke test checklist**

1. Start dev server: `python wsgi.py`
2. Log in as supervisor
3. Navigate to `/time-off` — verify 3 tabs visible with proper styling (Pending Approvals in amber)
4. Click "Pending Approvals" tab — verify it loads (may be empty)
5. Log in as employee on separate browser, submit a time-off request from my-dashboard
6. Return to supervisor — refresh pending tab, verify request appears with employee name, dates, reason
7. Click Approve on one — verify flash message, card disappears, count badge updates
8. Submit another request, click Deny — verify modal opens, enter reason, confirm
9. Check notification bell — verify "X Pending Time Off Request(s)" appears with link
10. Click notification link — verify it navigates to `/time-off?tab=pending`
11. Log in as employee — verify denied request shows denial reason on my-dashboard
12. Log in as lead — verify Pending Approvals tab is NOT visible on `/time-off`
