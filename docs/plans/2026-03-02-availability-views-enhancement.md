# Availability Views Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the existing Employee Availability and Available Schedule Blocks dashboard views discoverable (sidebar links), printable (print button + print CSS), and accessible from the /printing hub.

**Architecture:** The two views and their backing service (`WeeklyPlanningService`) already exist. We add `@media print` CSS and a print button to each template, add sidebar navigation links in `base.html`, and add two new card sections to `printing.html` that link out to the existing views (same pattern as the Scan-Out Checklist section).

**Tech Stack:** Flask/Jinja2 templates, CSS `@media print`, existing `WeeklyPlanningService`

---

### Task 1: Add print support to Employee Availability template

**Files:**
- Modify: `app/templates/dashboard/employee_availability.html`

**Step 1: Add print button and `@media print` CSS**

Add a print button next to the nav buttons in the header, and add print-friendly CSS that hides the sidebar, nav, header chrome, and optimizes the grid for paper.

In `employee_availability.html`, add after the existing `</style>` tag (line 87), before `{% endblock %}`:

```html
<style>
@media print {
    .sidebar, .sidebar-overlay, .top-bar, .nav-btns, .stats-row, .print-btn { display: none !important; }
    .planning-header { border-radius: 0; margin-bottom: 12px; padding: 12px 16px; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
    .week-grid { gap: 4px; }
    .day-column { box-shadow: none; border: 1px solid #ddd; break-inside: avoid; }
    .day-body { min-height: auto; }
    .employee-row { padding: 3px 6px; font-size: 11px; }
    .day-header .day-name { font-size: 10px; }
    .day-header .day-date { font-size: 14px; }
    .container-fluid { padding: 0 !important; }
    body { padding: 0; margin: 0; }
}
</style>
```

Then add a print button inside the `.nav-btns` div, after the "Next" link (line 103):

```html
<button class="print-btn" onclick="window.print()" style="background: rgba(255,255,255,0.2); color: white; padding: 8px 16px; border-radius: 6px; border: none; font-weight: 500; cursor: pointer;">
    <i class="fas fa-print"></i> Print
</button>
```

**Step 2: Verify visually**

Run: `python wsgi.py` and navigate to `/dashboard/employee-availability`. Confirm the Print button appears. Click it and confirm the print preview shows a clean grid without sidebar/nav.

**Step 3: Commit**

```bash
git add app/templates/dashboard/employee_availability.html
git commit -m "feat: add print support to Employee Availability view"
```

---

### Task 2: Add print support to Available Schedule Blocks template

**Files:**
- Modify: `app/templates/dashboard/available_blocks.html`

**Step 1: Add print button and `@media print` CSS**

Same pattern as Task 1. Add after the existing `</style>` tag (line 87):

```html
<style>
@media print {
    .sidebar, .sidebar-overlay, .top-bar, .nav-btns, .stats-row, .print-btn { display: none !important; }
    .planning-header { border-radius: 0; margin-bottom: 12px; padding: 12px 16px; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
    .week-grid { gap: 4px; }
    .day-column { box-shadow: none; border: 1px solid #ddd; break-inside: avoid; }
    .day-body { min-height: auto; }
    .employee-row { padding: 3px 6px; font-size: 11px; }
    .day-header .day-name { font-size: 10px; }
    .day-header .day-date { font-size: 14px; }
    .container-fluid { padding: 0 !important; }
    body { padding: 0; margin: 0; }
}
</style>
```

Add print button inside `.nav-btns` div, after the "Next" link (line 103):

```html
<button class="print-btn" onclick="window.print()" style="background: rgba(255,255,255,0.2); color: white; padding: 8px 16px; border-radius: 6px; border: none; font-weight: 500; cursor: pointer;">
    <i class="fas fa-print"></i> Print
</button>
```

**Step 2: Verify visually**

Navigate to `/dashboard/available-blocks`. Confirm print button and print preview look correct.

**Step 3: Commit**

```bash
git add app/templates/dashboard/available_blocks.html
git commit -m "feat: add print support to Available Schedule Blocks view"
```

---

### Task 3: Add sidebar navigation links

**Files:**
- Modify: `app/templates/base.html` (around line 254, in the Tools group)

**Step 1: Add two sidebar links**

In `base.html`, find the Tools group section (line 248). After the "Weekly Validation" link (line 258) and before the "Scan-Out Checklist" link (line 259), insert:

```html
<a href="{{ url_for('dashboard.employee_availability') }}"
    class="sidebar-item {% if request.endpoint == 'dashboard.employee_availability' %}active{% endif %}">
    <span class="material-symbols-outlined">groups</span>
    <span>Employee Availability</span>
</a>
<a href="{{ url_for('dashboard.available_blocks') }}"
    class="sidebar-item {% if request.endpoint == 'dashboard.available_blocks' %}active{% endif %}">
    <span class="material-symbols-outlined">event_available</span>
    <span>Available Blocks</span>
</a>
```

**Step 2: Verify**

Navigate to any page and confirm both links appear in the sidebar under "Tools". Click each and confirm they navigate correctly and show as "active" when on that page.

**Step 3: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add Employee Availability and Available Blocks to sidebar nav"
```

---

### Task 4: Add availability sections to the Printing hub

**Files:**
- Modify: `app/templates/printing.html` (insert before the Freeosk Manual Test section, around line 423)

**Step 1: Add two card sections**

These follow the same pattern as the Scan-Out Checklist section — a date picker and a link that opens the view in a new tab. Insert before the Freeosk section:

```html
<!-- Employee Availability Section -->
<div class="row mb-4">
    <div class="col-md-6 mb-3">
        <div class="card shadow-sm h-100">
            <div class="card-header text-white" style="background-color: #667eea;">
                <h5 class="mb-0">
                    <i class="fas fa-users"></i> Employee Availability
                </h5>
            </div>
            <div class="card-body">
                <p class="text-muted">Weekly view of who is available each day (checks weekly schedule, time off, holidays)</p>
                <div class="row">
                    <div class="col-12">
                        <label for="availability-start-date" class="form-label">Week Starting</label>
                        <input type="date" class="form-control" id="availability-start-date">
                    </div>
                </div>
                <div class="mt-3">
                    <a id="availability-link" href="/dashboard/employee-availability" class="btn text-white" style="background-color: #667eea;" target="_blank">
                        <i class="fas fa-external-link-alt"></i> Open &amp; Print
                    </a>
                    <small class="text-muted ms-2">Opens in new tab with print button</small>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-6 mb-3">
        <div class="card shadow-sm h-100">
            <div class="card-header text-white" style="background-color: #059669;">
                <h5 class="mb-0">
                    <i class="fas fa-calendar-check"></i> Available Schedule Blocks
                </h5>
            </div>
            <div class="card-body">
                <p class="text-muted">Who can still be scheduled (available, no time off, no main event yet)</p>
                <div class="row">
                    <div class="col-12">
                        <label for="blocks-start-date" class="form-label">Week Starting</label>
                        <input type="date" class="form-control" id="blocks-start-date">
                    </div>
                </div>
                <div class="mt-3">
                    <a id="blocks-link" href="/dashboard/available-blocks" class="btn text-white" style="background-color: #059669;" target="_blank">
                        <i class="fas fa-external-link-alt"></i> Open &amp; Print
                    </a>
                    <small class="text-muted ms-2">Opens in new tab with print button</small>
                </div>
            </div>
        </div>
    </div>
</div>
```

**Step 2: Add JavaScript to update links when date changes**

In the `<script>` section's `DOMContentLoaded` handler, add after the existing default date setters (around line 744):

```javascript
// Set default dates for availability sections
document.getElementById('availability-start-date').value = today;
document.getElementById('blocks-start-date').value = today;

// Update availability links when dates change
document.getElementById('availability-start-date').addEventListener('change', function() {
    document.getElementById('availability-link').href = '/dashboard/employee-availability?start_date=' + this.value;
});
document.getElementById('blocks-start-date').addEventListener('change', function() {
    document.getElementById('blocks-link').href = '/dashboard/available-blocks?start_date=' + this.value;
});
```

**Step 3: Verify**

Navigate to `/printing`. Confirm both new cards appear. Change the dates and confirm the links update. Click each link and confirm they open in new tabs at the correct URLs.

**Step 4: Commit**

```bash
git add app/templates/printing.html
git commit -m "feat: add Employee Availability and Available Blocks to printing hub"
```

---

### Task 5: Run tests and final verification

**Step 1: Run the test suite**

Run: `pytest -v`
Expected: All existing tests pass (no new tests needed — this is pure template/UI work)

**Step 2: Manual smoke test**

1. Start server: `python wsgi.py`
2. Open sidebar — confirm both new links appear under "Tools"
3. Click "Employee Availability" — view loads with weekly grid
4. Click Print button — print preview shows clean layout
5. Click "Available Blocks" — view loads with weekly grid
6. Click Print button — print preview shows clean layout
7. Go to `/printing` — confirm both new cards appear
8. Change dates in cards — confirm links update
9. Click "Open & Print" links — confirm they open correct views in new tabs

**Step 3: Commit any fixes if needed, then done**
