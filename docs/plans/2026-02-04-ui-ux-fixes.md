# UI/UX Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 21 identified UI/UX flaws across 5 phases, improving consistency, accessibility, and maintainability of the Product Connections Scheduler frontend.

**Architecture:** Consolidate design tokens into single source of truth, replace emoji icons with Material Symbols, extract inline/embedded CSS to external files, standardize modal implementations, and improve accessibility compliance (WCAG 2.1 AA).

**Tech Stack:** Jinja2 templates, CSS custom properties, Material Symbols icons, Flask/Python for dynamic values

---

## Phase 1: Quick Wins

### Task 1: Fix Copyright Year (FLAW-008)

**Files:**
- Modify: `app/templates/base.html:292`

**Step 1: Locate the footer copyright line**

Search for the hardcoded year in base.html footer section.

**Step 2: Update to dynamic year**

```html
<!-- Before -->
<p>&copy; 2024 Product Connections. All rights reserved.</p>

<!-- After -->
<p>&copy; {{ now().year if now is defined else 2026 }} Product Connections. All rights reserved.</p>
```

**Step 3: Add context processor for `now()` function**

Modify: `app/__init__.py` (in create_app function, after app configuration)

```python
@app.context_processor
def inject_now():
    from datetime import datetime
    return {'now': datetime.now}
```

**Step 4: Verify the fix**

Run: `python wsgi.py` and check footer displays "2026"

**Step 5: Commit**

```bash
git add app/templates/base.html app/__init__.py
git commit -m "fix: make footer copyright year dynamic

FLAW-008: Footer now displays current year automatically.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Add Cursor Pointer to Interactive Elements (FLAW-006)

**Files:**
- Modify: `app/static/css/style.css` (add at end of file)

**Step 1: Add global cursor pointer rule**

```css
/* ==========================================================================
   Interactive Element Cursor Styles (FLAW-006)
   ========================================================================== */

/* Elements with click handlers or interactive roles */
[onclick],
[role="button"],
[tabindex]:not([tabindex="-1"]) {
  cursor: pointer;
}

/* Interactive cards and list items */
.stat-card,
.event-card,
.unscheduled-item,
.core-event-item,
.employee-card,
.day-card,
.notification-item,
.clickable {
  cursor: pointer;
}

/* Ensure buttons always have pointer cursor */
button:not(:disabled),
.btn:not(.btn-disabled) {
  cursor: pointer;
}
```

**Step 2: Verify cursor changes on hover**

Open browser, hover over stat cards on dashboard - cursor should change to pointer.

**Step 3: Commit**

```bash
git add app/static/css/style.css
git commit -m "fix: add cursor pointer to interactive elements

FLAW-006: Cards, buttons, and clickable elements now show pointer cursor.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Use Z-Index Tokens Consistently (FLAW-012)

**Files:**
- Modify: `app/static/css/style.css`
- Modify: `app/static/css/responsive.css`
- Modify: `app/static/css/modals.css`

**Step 1: Search for hardcoded z-index values**

Run: `grep -r "z-index:" app/static/css/ --include="*.css" | grep -v "var(--z-"`

**Step 2: Replace hardcoded values in style.css**

Find and replace:
- `z-index: 1000` → `z-index: var(--z-dropdown)`
- `z-index: 1001` → `z-index: var(--z-modal)`
- `z-index: 999` → `z-index: var(--z-fixed)`

**Step 3: Replace hardcoded values in responsive.css**

Find `.nav-links { z-index: 999; }` and replace with:
```css
.nav-links {
  z-index: var(--z-fixed);
}
```

**Step 4: Replace hardcoded values in modals.css**

Find modal z-index rules and replace:
```css
.modal {
  z-index: var(--z-modal);
}

.modal-overlay {
  z-index: var(--z-modal-backdrop);
}
```

**Step 5: Verify modal layering works correctly**

Open app, trigger a modal, verify it appears above other content.

**Step 6: Commit**

```bash
git add app/static/css/style.css app/static/css/responsive.css app/static/css/modals.css
git commit -m "fix: use z-index design tokens consistently

FLAW-012: All z-index values now reference design tokens.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Remove Deprecated Touch Scrolling CSS (FLAW-017)

**Files:**
- Modify: `app/static/css/responsive.css:113-120`

**Step 1: Find the deprecated property**

Locate `-webkit-overflow-scrolling: touch` in responsive.css.

**Step 2: Replace with modern alternative**

```css
/* Before */
.notifications-content,
.nav-links,
.modal-body,
table {
  -webkit-overflow-scrolling: touch;
  scroll-behavior: smooth;
}

/* After */
.notifications-content,
.nav-links,
.modal-body,
table {
  overflow-y: auto;
  overscroll-behavior: contain;
  scroll-behavior: smooth;
}
```

**Step 3: Test scrolling on mobile simulator**

Open DevTools, enable device mode, test scrolling in modals and nav.

**Step 4: Commit**

```bash
git add app/static/css/responsive.css
git commit -m "fix: remove deprecated webkit-overflow-scrolling

FLAW-017: Replaced with modern overscroll-behavior property.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5: Standardize Border Radius Values (FLAW-018)

**Files:**
- Modify: Various CSS files with hardcoded border-radius

**Step 1: Search for hardcoded border-radius values**

Run: `grep -r "border-radius:" app/static/css/ --include="*.css" | grep -v "var(--radius"`

**Step 2: Create mapping reference**

```
4px  → var(--radius-sm)
6px  → var(--radius-md)
8px  → var(--radius-lg)
12px → var(--radius-xl)
```

**Step 3: Replace in style.css**

Find and replace all hardcoded `border-radius` values with appropriate tokens.

Example replacements:
```css
/* Before */
border-radius: 4px;
border-radius: 8px;
border-radius: 12px;

/* After */
border-radius: var(--radius-sm);
border-radius: var(--radius-lg);
border-radius: var(--radius-xl);
```

**Step 4: Verify visual appearance unchanged**

Compare before/after screenshots of buttons, cards, modals.

**Step 5: Commit**

```bash
git add app/static/css/style.css
git commit -m "fix: use border-radius design tokens consistently

FLAW-018: All border-radius values now reference design tokens.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Improve Hover Animations (FLAW-007)

**Files:**
- Modify: `app/templates/index.html` (embedded styles)
- Modify: `app/static/css/style.css`

**Step 1: Reduce transform distances**

In index.html embedded styles, find hover transforms and reduce:

```css
/* Before */
.stat-card:hover {
  transform: translateY(-4px);
}

.dashboard-section:hover {
  transform: translateY(-2px);
}

/* After */
.stat-card:hover {
  box-shadow: var(--shadow-lg);
  border-color: var(--pc-light-blue);
  transform: translateY(-2px);
}

.dashboard-section:hover {
  box-shadow: var(--shadow-md);
  /* Remove transform entirely for sections */
}
```

**Step 2: Add touch device media query**

```css
/* Disable transforms on touch devices */
@media (hover: none) {
  .stat-card:hover,
  .dashboard-section:hover,
  .event-card:hover,
  .core-event-item:hover {
    transform: none;
  }
}
```

**Step 3: Add will-change for performance**

```css
.stat-card,
.event-card {
  will-change: box-shadow, border-color;
}
```

**Step 4: Test hover behavior**

Verify cards respond smoothly on desktop, no movement on mobile emulator.

**Step 5: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "fix: improve hover animations and disable on touch

FLAW-007: Reduced transform distances, disabled on touch devices.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Design Token Cleanup

### Task 7: Consolidate Design Token Systems (FLAW-002)

**Files:**
- Modify: `app/static/css/design-tokens.css`
- Modify: `app/static/css/style.css`

**Step 1: Document the conflicts**

| Token | design-tokens.css | style.css | Resolution |
|-------|-------------------|-----------|------------|
| Primary color | `#003366` | `#2E4C73` | Use `#2E4C73` (brand) |
| spacing-xs | `0.25rem` | `0.5rem` | Use `0.25rem` (4px grid) |

**Step 2: Update design-tokens.css with correct brand colors**

```css
/* PRIMARY BRAND COLORS - Updated to match brand guidelines */
--color-primary: #2E4C73;        /* PC Navy - from brand logo */
--color-primary-light: #1B9BD8;  /* PC Blue - from brand logo */
--color-primary-dark: #1E3A5F;   /* Darker navy for pressed states */
```

**Step 3: Add PC-prefixed aliases for backward compatibility**

```css
/* Brand Color Aliases (for backward compatibility) */
--pc-navy: var(--color-primary);
--pc-blue: var(--color-primary-light);
--pc-light-blue: #E8F4F9;
```

**Step 4: Remove duplicate token definitions from style.css**

Delete lines 1-56 from style.css (the duplicate :root block with conflicting tokens).

Keep only the component styles, starting from `/* Base Styles */`.

**Step 5: Update any references to old token names**

Search and replace:
- `--primary-color` → `var(--color-primary)` or keep as alias
- Ensure `--spacing-xs` consistently refers to 4px

**Step 6: Test the application**

Run: `python wsgi.py`
Verify: Colors look correct, spacing is consistent.

**Step 7: Commit**

```bash
git add app/static/css/design-tokens.css app/static/css/style.css
git commit -m "fix: consolidate design token systems

FLAW-002: Single source of truth in design-tokens.css.
- Updated primary color to brand value #2E4C73
- Removed duplicate definitions from style.css
- Added backward-compatible aliases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 8: Add Badge Color Tokens (FLAW-004 Part 1)

**Files:**
- Modify: `app/static/css/design-tokens.css`

**Step 1: Add role badge color tokens**

Add after Event Type Colors section:

```css
/* ===========================
 * ROLE BADGE COLORS
 * =========================== */

--color-badge-lead: #FF69B4;           /* Lead Event Specialist - Hot Pink */
--color-badge-supervisor: #00CED1;     /* Club Supervisor - Dark Cyan */
--color-badge-juicer: var(--color-secondary); /* Juicer Barista - Orange */
--color-badge-specialist: var(--color-success); /* Event Specialist - Green */
--color-badge-ab-trained: #007bff;     /* A&B Trained - Blue */
--color-badge-juicer-trained: #17a2b8; /* Juicer Trained - Teal */
--color-badge-inactive: var(--color-danger); /* Inactive - Red */
```

**Step 2: Commit**

```bash
git add app/static/css/design-tokens.css
git commit -m "feat: add role badge color tokens

FLAW-004: Added semantic color tokens for employee role badges.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 9: Replace Hardcoded Colors in employees.html (FLAW-004 Part 2)

**Files:**
- Modify: `app/templates/employees.html`

**Step 1: Find the embedded badge styles**

Locate the `.badge-*` classes in the `<style>` block.

**Step 2: Replace with token references**

```css
/* Before */
.badge-lead-event-specialist { background: #FF69B4; }
.badge-club-supervisor { background: #00FFFF; color: #000; }
.badge-juicer-barista { background: #ff9800; }
.badge-event-specialist { background: #28a745; }
.badge-ab-trained { background: #007bff; }
.badge-juicer-trained { background: #17a2b8; }
.badge-inactive { background: #dc3545; }

/* After */
.badge-lead-event-specialist { background: var(--color-badge-lead); }
.badge-club-supervisor { background: var(--color-badge-supervisor); color: #000; }
.badge-juicer-barista { background: var(--color-badge-juicer); }
.badge-event-specialist { background: var(--color-badge-specialist); }
.badge-ab-trained { background: var(--color-badge-ab-trained); }
.badge-juicer-trained { background: var(--color-badge-juicer-trained); }
.badge-inactive { background: var(--color-badge-inactive); }
```

**Step 3: Replace other hardcoded colors**

Search for `#` in the style block and replace with appropriate tokens:
- `#6c757d` → `var(--color-neutral-500)`
- `#ddd` → `var(--color-neutral-300)`
- `#fff` → `var(--color-neutral-50)`

**Step 4: Verify badge colors look correct**

Navigate to `/employees` page, verify badges display correctly.

**Step 5: Commit**

```bash
git add app/templates/employees.html
git commit -m "fix: use design tokens for employee badge colors

FLAW-004: Replaced hardcoded hex colors with design token references.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 10: Replace Hardcoded Colors in auto_schedule_review.html (FLAW-004 Part 3)

**Files:**
- Modify: `app/templates/auto_schedule_review.html`

**Step 1: Find and replace hardcoded colors**

```css
/* Before */
.review-header h1 { color: #2c3e50; }
.stat-card h3 { color: #7f8c8d; }
.stat-card .value { color: #2c3e50; }
.stat-card .stat-description { color: #95a5a6; }

/* After */
.review-header h1 { color: var(--text-primary); }
.stat-card h3 { color: var(--text-muted); }
.stat-card .value { color: var(--text-primary); }
.stat-card .stat-description { color: var(--text-muted); }
```

**Step 2: Replace status colors**

```css
/* Before */
.stat-card.success { border-left-color: #27ae60; }
.stat-card.warning { border-left-color: #f39c12; }
.stat-card.error { border-left-color: #e74c3c; }

/* After */
.stat-card.success { border-left-color: var(--color-success); }
.stat-card.warning { border-left-color: var(--color-warning); }
.stat-card.error { border-left-color: var(--color-danger); }
```

**Step 3: Replace background colors**

```css
/* Before */
background: #f8f9fa;
background: #dee2e6;

/* After */
background: var(--color-neutral-100);
border-color: var(--color-neutral-200);
```

**Step 4: Commit**

```bash
git add app/templates/auto_schedule_review.html
git commit -m "fix: use design tokens in auto_schedule_review

FLAW-004: Replaced hardcoded colors with semantic design tokens.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 11: Standardize Button Classes (FLAW-011)

**Files:**
- Modify: `app/static/css/style.css`
- Modify: `app/templates/employees.html`

**Step 1: Add button size variants to style.css**

```css
/* ==========================================================================
   Button Size Variants (FLAW-011)
   ========================================================================== */

.btn-sm {
  height: 2rem;           /* 32px */
  padding: 0.25rem 0.75rem;
  font-size: var(--font-size-sm);
}

.btn {
  height: var(--btn-height);  /* 40px */
  padding: var(--btn-padding-y) var(--btn-padding-x);
  font-size: var(--btn-font-size);
}

.btn-lg {
  height: 3rem;           /* 48px */
  padding: 0.75rem 1.5rem;
  font-size: var(--font-size-md);
}
```

**Step 2: Replace .btn-small with .btn-sm in templates**

In employees.html, find and replace:
```html
<!-- Before -->
<button class="btn-small">

<!-- After -->
<button class="btn btn-sm">
```

**Step 3: Remove the old .btn-small class definition**

Delete from employees.html:
```css
.btn-small {
    padding: 6px 12px;
    font-size: 12px;
}
```

**Step 4: Verify buttons render correctly**

Check employee page, verify button sizes are appropriate.

**Step 5: Commit**

```bash
git add app/static/css/style.css app/templates/employees.html
git commit -m "fix: standardize button size classes

FLAW-011: Added btn-sm, btn, btn-lg variants. Replaced btn-small.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Component Standardization

### Task 12: Replace Emoji Icons with Material Symbols (FLAW-001)

**Files:**
- Modify: `app/templates/base.html`

**Step 1: Create icon mapping reference**

| Emoji | Material Symbol | Usage |
|-------|-----------------|-------|
| 🏠 | `home` | Home nav link |
| 📅 | `calendar_month` | Scheduling dropdown |
| 👥 | `group` | Team dropdown |
| 🖨️ | `print` | Printing link |
| ✨ | `auto_awesome` | AI Assistant |
| ❓ | `help` | Help menu item |
| ⚙️ | `settings` | Settings menu item |
| 🕐 | `schedule` | Event Times menu item |
| 🔄 | `sync` | Rotation Management |
| 🚪 | `logout` | Logout menu item |

**Step 2: Replace navigation icons (lines 64-147)**

```html
<!-- Home Link -->
<a href="{{ url_for('main.index') }}" class="nav-link ..." aria-label="Go to home page">
    <span class="nav-icon"><span class="material-symbols-outlined">home</span></span>
    <span class="nav-text">Home</span>
</a>

<!-- Scheduling Dropdown -->
<button class="nav-link nav-dropdown-toggle" ...>
    <span class="nav-icon"><span class="material-symbols-outlined">calendar_month</span></span>
    <span class="nav-text">Scheduling</span>
    <span class="nav-arrow">▼</span>
</button>

<!-- Team Dropdown -->
<button class="nav-link nav-dropdown-toggle" ...>
    <span class="nav-icon"><span class="material-symbols-outlined">group</span></span>
    <span class="nav-text">Team</span>
    <span class="nav-arrow">▼</span>
</button>

<!-- Printing Link -->
<a href="{{ url_for('printing.printing_home') }}" class="nav-link ..." aria-label="Go to printing page">
    <span class="nav-icon"><span class="material-symbols-outlined">print</span></span>
    <span class="nav-text">Printing</span>
</a>
```

**Step 3: Replace AI Assistant icon (line 163)**

```html
<button id="aiPanelToggle" class="notifications-btn" title="AI Assistant (Ctrl+K)" aria-label="AI Assistant">
    <span class="nav-icon"><span class="material-symbols-outlined">auto_awesome</span></span>
</button>
```

**Step 4: Replace user dropdown icons (lines 193-214)**

```html
<a href="{{ url_for('help.help_home') }}" class="dropdown-item">
    <span class="dropdown-icon"><span class="material-symbols-outlined">help</span></span>
    Help
</a>
<a href="{{ url_for('admin.settings_page') }}" class="dropdown-item">
    <span class="dropdown-icon"><span class="material-symbols-outlined">settings</span></span>
    Settings
</a>
<a href="{{ url_for('admin.event_times_page') }}" class="dropdown-item">
    <span class="dropdown-icon"><span class="material-symbols-outlined">schedule</span></span>
    Event Time Settings
</a>
<a href="{{ url_for('rotations.index') }}" class="dropdown-item ...">
    <span class="dropdown-icon"><span class="material-symbols-outlined">sync</span></span>
    Rotation Management
</a>
<a href="{{ url_for('auth.logout') }}" class="dropdown-item">
    <span class="dropdown-icon"><span class="material-symbols-outlined">logout</span></span>
    Logout
</a>
```

**Step 5: Update CSS for Material Symbols sizing**

Add to style.css:

```css
/* Material Symbols Icon Styling */
.nav-icon .material-symbols-outlined,
.dropdown-icon .material-symbols-outlined {
  font-size: 1.25rem;
  vertical-align: middle;
}

.dropdown-icon .material-symbols-outlined {
  font-size: 1.125rem;
}
```

**Step 6: Verify icons render correctly**

Open app in browser, check navigation and dropdown icons display properly.

**Step 7: Commit**

```bash
git add app/templates/base.html app/static/css/style.css
git commit -m "fix: replace emoji icons with Material Symbols

FLAW-001: All navigation icons now use Material Symbols for
consistent, professional appearance across browsers.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 13: Add Mobile Menu Close Button (FLAW-014)

**Files:**
- Modify: `app/templates/base.html`
- Modify: `app/static/css/responsive.css`
- Modify: `app/static/js/navigation.js`

**Step 1: Add close button HTML after nav-links opening div**

In base.html, after `<div class="nav-links" id="navLinks">`:

```html
<div class="nav-links" id="navLinks">
    <!-- Mobile Close Button -->
    <button class="nav-close" id="navCloseBtn" aria-label="Close navigation menu">
        <span class="material-symbols-outlined">close</span>
    </button>

    <!-- Home Link ... -->
```

**Step 2: Add CSS for close button**

In responsive.css, in the mobile section:

```css
/* Mobile Close Button (FLAW-014) */
.nav-close {
  display: none;
}

@media (max-width: 768px) {
  .nav-close {
    display: flex;
    align-items: center;
    justify-content: center;
    position: absolute;
    top: var(--safe-area-top, 16px);
    right: 16px;
    width: 44px;
    height: 44px;
    background: rgba(255, 255, 255, 0.1);
    border: none;
    border-radius: var(--radius-md);
    color: white;
    cursor: pointer;
    z-index: 1;
  }

  .nav-close:hover {
    background: rgba(255, 255, 255, 0.2);
  }

  .nav-close .material-symbols-outlined {
    font-size: 24px;
  }
}
```

**Step 3: Add JavaScript handler**

In navigation.js, add close button handler:

```javascript
// Mobile nav close button
const navCloseBtn = document.getElementById('navCloseBtn');
if (navCloseBtn) {
  navCloseBtn.addEventListener('click', function() {
    navLinks.classList.remove('nav-links--open');
    hamburgerBtn.classList.remove('hamburger-menu--open');
    hamburgerBtn.setAttribute('aria-expanded', 'false');
  });
}
```

**Step 4: Test mobile menu close**

Open DevTools, enable mobile view, open nav menu, verify close button works.

**Step 5: Commit**

```bash
git add app/templates/base.html app/static/css/responsive.css app/static/js/navigation.js
git commit -m "feat: add close button to mobile navigation menu

FLAW-014: Mobile menu now has explicit close button for better UX.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 14: Create Consistent Loading Component (FLAW-015)

**Files:**
- Modify: `app/static/css/loading-states.css`
- Modify: `app/templates/daily_view.html`

**Step 1: Verify spinner CSS exists in loading-states.css**

Ensure the spinner component is defined:

```css
/* Loading Spinner */
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--color-neutral-200);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Loading State Container */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg);
  color: var(--text-muted);
}

.loading-state .spinner {
  margin-bottom: var(--spacing-sm);
}
```

**Step 2: Update loading states in daily_view.html**

Find all instances of "Loading..." text and replace:

```html
<!-- Before -->
<div class="loading-spinner" role="status" aria-live="polite">
  <span class="sr-only">Loading summary...</span>
  Loading...
</div>

<!-- After -->
<div class="loading-state" role="status" aria-live="polite">
  <div class="spinner"></div>
  <span class="sr-only">Loading summary...</span>
</div>
```

**Step 3: Apply to all loading states in the file**

Repeat for:
- `#daily-summary` section
- `#timeslot-blocks` section
- `#attendance-list-container` section
- `#event-cards-container` section

**Step 4: Verify spinners display correctly**

Refresh daily view page, observe loading spinners appear before content loads.

**Step 5: Commit**

```bash
git add app/static/css/loading-states.css app/templates/daily_view.html
git commit -m "fix: use consistent spinner loading component

FLAW-015: Replaced plain 'Loading...' text with animated spinner.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 15: Standardize Modal Structure (FLAW-005)

**Files:**
- Create: `app/templates/components/modal_base.html`
- Modify: `app/static/css/components/modal.css`

**Step 1: Create reusable modal macro**

Create `app/templates/components/modal_base.html`:

```html
{# Reusable Modal Component Macro #}
{% macro modal(id, title, size='medium', extra_classes='') %}
<div class="modal" id="{{ id }}" role="dialog" aria-modal="true" aria-labelledby="{{ id }}-title" style="display: none;">
  <div class="modal__overlay" data-modal-close></div>
  <div class="modal__container modal__container--{{ size }} {{ extra_classes }}">
    <header class="modal__header">
      <h2 class="modal__title" id="{{ id }}-title">{{ title }}</h2>
      <button class="modal__close" aria-label="Close {{ title }}" data-modal-close>
        <span class="material-symbols-outlined">close</span>
      </button>
    </header>
    <div class="modal__body">
      {{ caller() }}
    </div>
    {% if varargs %}
    <footer class="modal__footer">
      {{ varargs[0] if varargs else '' }}
    </footer>
    {% endif %}
  </div>
</div>
{% endmacro %}
```

**Step 2: Ensure modal.css uses BEM naming**

Verify `app/static/css/components/modal.css` has:

```css
.modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: none;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal.modal-open {
  display: flex;
}

.modal__overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: var(--modal-backdrop);
  z-index: var(--z-modal-backdrop);
}

.modal__container {
  position: relative;
  background: var(--color-neutral-50);
  border-radius: var(--modal-border-radius);
  box-shadow: var(--shadow-xl);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  z-index: var(--z-modal);
}

.modal__container--small { max-width: 400px; width: 90%; }
.modal__container--medium { max-width: 600px; width: 90%; }
.modal__container--large { max-width: 800px; width: 95%; }

.modal__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--modal-padding);
  border-bottom: 1px solid var(--color-neutral-200);
}

.modal__title {
  margin: 0;
  font-size: var(--font-size-xl);
  color: var(--text-primary);
}

.modal__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-muted);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.modal__close:hover {
  background: var(--color-neutral-100);
  color: var(--text-primary);
}

.modal__body {
  padding: var(--modal-padding);
  overflow-y: auto;
  flex: 1;
}

.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--modal-padding);
  border-top: 1px solid var(--color-neutral-200);
}
```

**Step 3: Commit**

```bash
git add app/templates/components/modal_base.html app/static/css/components/modal.css
git commit -m "feat: create standardized modal component structure

FLAW-005: Added reusable modal macro with BEM CSS naming.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 4: Accessibility Improvements

### Task 16: Add Table Accessibility (FLAW-009)

**Files:**
- Modify: `app/templates/auto_schedule_review.html`

**Step 1: Find table elements**

Locate `<table class="event-table">` elements.

**Step 2: Add accessibility attributes**

```html
<!-- Before -->
<table class="event-table">
  <thead>
    <tr><th>Event</th><th>Date</th><th>Employee</th><th>Status</th></tr>
  </thead>

<!-- After -->
<table class="event-table" aria-describedby="proposed-schedules-desc">
  <caption id="proposed-schedules-desc" class="sr-only">
    List of proposed schedule assignments awaiting review
  </caption>
  <thead>
    <tr>
      <th scope="col">Event</th>
      <th scope="col">Date</th>
      <th scope="col">Employee</th>
      <th scope="col">Status</th>
    </tr>
  </thead>
```

**Step 3: Add scope to all table headers**

For any tables with row headers, add `scope="row"`:

```html
<tbody>
  <tr>
    <th scope="row">{{ event.name }}</th>
    <td>{{ event.date }}</td>
    <td>{{ event.employee }}</td>
    <td>{{ event.status }}</td>
  </tr>
</tbody>
```

**Step 4: Test with screen reader simulation**

Use browser accessibility tools to verify table structure is announced.

**Step 5: Commit**

```bash
git add app/templates/auto_schedule_review.html
git commit -m "fix: add accessibility attributes to data tables

FLAW-009: Tables now have caption, scope attributes for screen readers.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 17: Associate Form Labels with Inputs (FLAW-013)

**Files:**
- Modify: `app/templates/daily_view.html`
- Modify: `app/templates/employees.html`

**Step 1: Find labels without for attributes**

Search for `<label>` tags missing `for=` attribute.

**Step 2: Add for attributes to labels in daily_view.html**

```html
<!-- Before -->
<div class="form-group">
  <label>Event:</label>
  <div id="reschedule-event-info"></div>
</div>

<!-- After -->
<div class="form-group">
  <label id="reschedule-event-label">Event:</label>
  <div id="reschedule-event-info" aria-labelledby="reschedule-event-label"></div>
</div>

<!-- For actual inputs -->
<div class="form-group">
  <label for="reschedule-date">New Date: <span class="required-indicator">*</span></label>
  <input type="date" id="reschedule-date" required aria-required="true">
</div>
```

**Step 3: Verify all form inputs have associated labels**

Check each modal form:
- Reschedule modal
- Reissue modal
- Bulk reassign modal
- Change event type modal

**Step 4: Test by clicking labels**

Click on label text, verify the input receives focus.

**Step 5: Commit**

```bash
git add app/templates/daily_view.html app/templates/employees.html
git commit -m "fix: associate form labels with inputs

FLAW-013: All form labels now properly linked to their inputs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 18: Add Focus Styles to Custom Elements (FLAW-019)

**Files:**
- Modify: `app/static/css/style.css`

**Step 1: Add focus-visible styles for interactive elements**

```css
/* ==========================================================================
   Focus Styles for Custom Interactive Elements (FLAW-019)
   ========================================================================== */

/* Cards and clickable items */
.stat-card:focus-visible,
.event-card:focus-visible,
.employee-card:focus-visible,
.unscheduled-item:focus-visible,
.day-card:focus-visible {
  outline: 2px solid var(--color-primary-light);
  outline-offset: 2px;
}

/* Make cards focusable */
.stat-card[onclick],
.event-card[onclick],
.employee-card[onclick] {
  tabindex: 0;
}

/* Dropdown items */
.nav-dropdown-item:focus-visible,
.dropdown-item:focus-visible {
  outline: 2px solid var(--color-primary-light);
  outline-offset: -2px;
  background: var(--bg-secondary);
}

/* Custom buttons */
.notifications-btn:focus-visible,
.refresh-database-btn:focus-visible,
.hamburger-menu:focus-visible {
  outline: 2px solid white;
  outline-offset: 2px;
}
```

**Step 2: Add tabindex to clickable cards in templates**

In index.html, add tabindex to stat cards:
```html
<div class="stat-card" onclick="..." tabindex="0" role="button">
```

**Step 3: Test keyboard navigation**

Tab through the page, verify all interactive elements have visible focus.

**Step 4: Commit**

```bash
git add app/static/css/style.css
git commit -m "fix: add focus styles for custom interactive elements

FLAW-019: Keyboard users now see visible focus on cards and buttons.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 19: Implement Sticky Footer (FLAW-020)

**Files:**
- Modify: `app/static/css/style.css`

**Step 1: Add flexbox layout to body**

Update body styles:

```css
body {
  font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: var(--font-size-body);
  font-weight: var(--font-weight-body);
  color: var(--text-secondary);
  background-color: var(--bg-tertiary);
  line-height: 1.6;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
```

**Step 2: Make main content flex-grow**

```css
.container {
  max-width: 100%;
  width: 100%;
  margin: 0 auto;
  padding: 0 var(--spacing-lg);
  flex: 1;
}
```

**Step 3: Ensure footer stays at bottom**

```css
.footer {
  background: var(--pc-navy);
  color: var(--text-white);
  text-align: center;
  padding: var(--spacing-lg) 0;
  margin-top: auto;
}
```

**Step 4: Test on short content pages**

Navigate to a page with minimal content, verify footer is at viewport bottom.

**Step 5: Commit**

```bash
git add app/static/css/style.css
git commit -m "fix: implement sticky footer pattern

FLAW-020: Footer now stays at viewport bottom on short pages.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 20: Enhance Print Styles (FLAW-021)

**Files:**
- Modify: `app/static/css/responsive.css`

**Step 1: Expand print media query**

Find the `@media print` section and replace:

```css
/* ==========================================================================
   Print Styles (FLAW-021)
   ========================================================================== */

@media print {
  /* Hide interactive and navigation elements */
  .header,
  .footer,
  .nav-link,
  .hamburger-menu,
  .nav-user-section,
  .btn:not(.btn-print),
  button:not(.btn-print),
  .ai-panel,
  .floating-widget,
  .modal {
    display: none !important;
  }

  /* Reset container widths */
  .container,
  .main-content {
    max-width: 100%;
    padding: 0;
    margin: 0;
  }

  body {
    background: white;
    color: black;
    font-size: 12pt;
  }

  /* Links - show URL */
  a[href]:after {
    content: " (" attr(href) ")";
    font-size: 0.8em;
    color: #666;
  }

  a[href^="#"]:after,
  a[href^="javascript"]:after {
    content: "";
  }

  /* Tables */
  table {
    border-collapse: collapse;
    width: 100%;
    page-break-inside: avoid;
  }

  th, td {
    border: 1px solid #000;
    padding: 8px;
  }

  thead {
    display: table-header-group;
  }

  tr {
    page-break-inside: avoid;
  }

  /* Cards */
  .stat-card,
  .event-card,
  .card {
    border: 1px solid #000;
    box-shadow: none;
    break-inside: avoid;
  }

  /* Ensure page breaks work */
  h1, h2, h3, h4 {
    page-break-after: avoid;
  }

  img {
    max-width: 100%;
    page-break-inside: avoid;
  }

  /* Remove backgrounds for ink savings */
  * {
    background: transparent !important;
  }

  .stat-card,
  .event-card {
    background: white !important;
  }
}
```

**Step 2: Test print preview**

Press Ctrl+P to open print preview, verify:
- Navigation hidden
- Tables have borders
- Content is readable

**Step 3: Commit**

```bash
git add app/static/css/responsive.css
git commit -m "fix: enhance print stylesheet

FLAW-021: Improved print output with proper tables, hidden nav, page breaks.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 5: Major Refactoring (Optional - High Effort)

### Task 21: Extract Inline Styles from index.html (FLAW-003)

**Files:**
- Create: `app/static/css/pages/index.css`
- Modify: `app/templates/index.html`

**Step 1: Create external CSS file**

Create `app/static/css/pages/index.css` with extracted styles from index.html's `<style>` block:

```css
/**
 * Dashboard/Index Page Styles
 * Extracted from inline styles per FLAW-003
 */

/* Page Header */
.page-header {
  text-align: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 2px solid var(--pc-light-blue);
}

.page-title {
  font-size: var(--font-size-h1);
  font-weight: var(--font-weight-heading);
  color: var(--pc-navy);
  margin: 0;
  letter-spacing: -0.02em;
}

/* Welcome Section */
.welcome-section {
  background: var(--bg-primary);
  border: 2px solid var(--pc-light-blue);
  padding: var(--spacing-xl);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
  position: relative;
  overflow: hidden;
}

.welcome-section::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 6px;
  background: linear-gradient(90deg, var(--pc-navy) 0%, var(--pc-blue) 100%);
}

/* ... continue with all styles ... */
```

**Step 2: Remove embedded styles from template**

Delete the entire `<style>` block from index.html's `{% block extra_head %}`.

**Step 3: Link to external CSS**

```html
{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/index.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/schedule-modal.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/modal.css') }}">
{% endblock %}
```

**Step 4: Replace inline styles in HTML**

Find inline `style=""` attributes and replace with classes:

```html
<!-- Before -->
<div style="display: flex; gap: 2rem; justify-content: center; margin-top: 1.5rem;">

<!-- After -->
<div class="role-display">
```

**Step 5: Verify visual appearance unchanged**

Compare screenshots before/after extraction.

**Step 6: Commit**

```bash
git add app/static/css/pages/index.css app/templates/index.html
git commit -m "refactor: extract inline styles from index.html

FLAW-003: Moved 450+ lines of embedded CSS to external stylesheet.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 22: Extract Embedded CSS from employees.html (FLAW-010)

**Files:**
- Create: `app/static/css/pages/employees.css`
- Modify: `app/templates/employees.html`

**Step 1: Create external CSS file**

Extract the embedded `<style>` block to `app/static/css/pages/employees.css`.

**Step 2: Remove embedded styles from template**

**Step 3: Link to external CSS**

```html
{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/employees.css') }}">
{% endblock %}
```

**Step 4: Commit**

```bash
git add app/static/css/pages/employees.css app/templates/employees.html
git commit -m "refactor: extract embedded CSS from employees.html

FLAW-010: Moved 500+ lines of embedded CSS to external stylesheet.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 23: Extract Embedded CSS from auto_schedule_review.html (FLAW-010)

**Files:**
- Create: `app/static/css/pages/auto-schedule-review.css`
- Modify: `app/templates/auto_schedule_review.html`

Follow same pattern as Task 22.

---

### Task 24: Extract Embedded CSS from unscheduled.html (FLAW-010)

**Files:**
- Create: `app/static/css/pages/unscheduled.css`
- Modify: `app/templates/unscheduled.html`

Follow same pattern as Task 22.

---

## Success Metrics

After completing all tasks, verify:

### Phase 1 Metrics
- [ ] Footer shows "2026" (dynamic year)
- [ ] Pointer cursor on all clickable cards
- [ ] No hardcoded z-index values in CSS
- [ ] No `-webkit-overflow-scrolling` in CSS
- [ ] All border-radius use tokens
- [ ] Hover transforms reduced/disabled on touch

### Phase 2 Metrics
- [ ] Single design token file is authoritative
- [ ] `--color-primary` is `#2E4C73`
- [ ] All badge colors use tokens
- [ ] Button sizes use `.btn-sm`, `.btn`, `.btn-lg`

### Phase 3 Metrics
- [ ] No emoji icons in navigation
- [ ] Material Symbols render correctly
- [ ] Mobile menu has close button
- [ ] Loading spinners replace text

### Phase 4 Metrics
- [ ] Tables pass accessibility audit
- [ ] All form labels associated
- [ ] Focus visible on all interactive elements
- [ ] Footer sticky on short pages
- [ ] Print preview looks professional

### Phase 5 Metrics
- [ ] No embedded `<style>` blocks over 50 lines
- [ ] Page CSS in `/css/pages/` directory
- [ ] CSS files cached by browser

---

## Testing Commands

```bash
# Run tests
pytest -v

# Check CSS for issues
# (manual browser inspection)

# Accessibility audit
# Use browser DevTools Lighthouse or axe extension

# Print preview
# Ctrl+P in browser
```

---

Plan complete and saved to `docs/plans/2026-02-04-ui-ux-fixes.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
