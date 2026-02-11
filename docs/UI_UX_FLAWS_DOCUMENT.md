# UI/UX Flaws Document
## Product Connections Scheduler

**Document Version:** 1.0
**Last Updated:** 2026-02-04
**Purpose:** Identify, document, and provide remediation plans for UI/UX design flaws

---

## Summary

| Priority | Count | Categories |
|----------|-------|------------|
| Critical | 3 | Accessibility, Consistency |
| High | 6 | Usability, Visual Design |
| Medium | 8 | Maintainability, Performance |
| Low | 4 | Polish, Minor Improvements |

---

## Critical Priority Flaws

### FLAW-001: Emoji Icons Used Instead of SVG Icons

**Location:** `app/templates/base.html` (lines 64-146, 194-214)

**Description:**
The navigation and dropdown menus use emoji characters (🏠, 📅, 👥, 🖨️, ❓, ⚙️, 🕐, 🔄, 🚪) as icons instead of proper SVG or icon font icons.

**Why This Is a Flaw:**
1. **Inconsistent rendering:** Emojis render differently across operating systems, browsers, and devices
2. **Unprofessional appearance:** Emojis carry a casual/playful connotation inappropriate for business software
3. **Accessibility issues:** Screen readers may announce emoji names unexpectedly
4. **Color inflexibility:** Emojis cannot be styled with CSS (color, size uniformity)
5. **Visual inconsistency:** Some buttons use proper SVGs (refresh, notifications) while nav uses emojis

**Current Implementation:**
```html
<span class="nav-icon">🏠</span>
<span class="nav-icon">📅</span>
<span class="dropdown-icon">⚙️</span>
```

**Recommended Fix:**
Replace all emoji icons with Material Symbols (already loaded in the project) or Heroicons/Lucide SVGs.

```html
<!-- Before -->
<span class="nav-icon">🏠</span>

<!-- After -->
<span class="nav-icon">
  <span class="material-symbols-outlined">home</span>
</span>
```

**Success Criteria:**
- [ ] All emoji icons replaced with Material Symbols or SVG icons
- [ ] Icons render consistently across Chrome, Firefox, Safari, Edge
- [ ] Icons respect `currentColor` for CSS color styling
- [ ] Screen readers announce icons appropriately (via aria-label or sr-only text)
- [ ] Visual appearance is consistent and professional

---

### FLAW-002: Duplicate/Conflicting Design Token Systems

**Location:**
- `app/static/css/design-tokens.css`
- `app/static/css/style.css` (lines 1-56)

**Description:**
Two separate design token systems exist with overlapping but inconsistent values:

| Token | design-tokens.css | style.css |
|-------|-------------------|-----------|
| Primary color | `--color-primary: #003366` | `--pc-navy: #2E4C73` |
| Spacing XS | `--spacing-xs: 0.25rem (4px)` | `--spacing-xs: 0.5rem (8px)` |
| Shadow SM | Different rgba values | Different rgba values |

**Why This Is a Flaw:**
1. **Maintenance nightmare:** Changes must be made in two places
2. **Inconsistency:** Different parts of the app use different token systems
3. **Confusion:** Developers don't know which tokens to use
4. **Navy color mismatch:** `#003366` vs `#2E4C73` creates subtle visual inconsistency

**Current Implementation:**
```css
/* design-tokens.css */
--color-primary: #003366;
--spacing-xs: var(--space-1); /* 4px */

/* style.css */
--pc-navy: #2E4C73;
--spacing-xs: 0.5rem; /* 8px - CONFLICT! */
```

**Recommended Fix:**
1. Audit both files and consolidate into a single source of truth
2. Choose the correct navy color (likely `#2E4C73` from brand guidelines)
3. Remove duplicate token definitions from `style.css`
4. Update all component references to use consolidated tokens

```css
/* design-tokens.css - SINGLE SOURCE OF TRUTH */
:root {
  /* Brand colors - use PC brand values */
  --color-primary: #2E4C73;        /* PC Navy from brand */
  --color-primary-light: #1B9BD8;  /* PC Blue */

  /* Spacing - consistent 4px base */
  --spacing-xs: 0.25rem;  /* 4px */
  --spacing-sm: 0.5rem;   /* 8px */
  /* ... */
}
```

**Success Criteria:**
- [ ] Single design token file is the source of truth
- [ ] All duplicate definitions removed from style.css
- [ ] Brand colors match official Product Connections brand guide
- [ ] No conflicting token values exist
- [ ] Components consistently reference the same tokens

---

### FLAW-003: Inline Styles Throughout Templates

**Location:** Multiple templates including:
- `app/templates/index.html` (lines 482-495)
- `app/templates/base.html` (lines 254-278, 406-424)
- `app/templates/daily_view.html` (lines 275-286)
- `app/templates/employees.html` (throughout)

**Description:**
Extensive use of inline `style=""` attributes instead of CSS classes, particularly for layout, spacing, and colors.

**Why This Is a Flaw:**
1. **Unmaintainable:** Style changes require template edits, not CSS updates
2. **No caching:** Inline styles increase HTML size and can't be cached
3. **Inconsistency:** Same visual patterns have different implementations
4. **Violates separation of concerns:** Presentation mixed with structure
5. **Specificity issues:** Inline styles override CSS, making global changes impossible

**Current Implementation:**
```html
<!-- index.html line 482 -->
<div style="display: flex; gap: 2rem; justify-content: center; margin-top: 1.5rem; flex-wrap: wrap;">
  <div style="text-align: center; padding: 1rem 2rem; background: rgba(46, 76, 115, 0.1); border-radius: 8px; border-left: 4px solid var(--pc-navy);">
    <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: 500; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.5px;">Primary Lead</div>
```

**Recommended Fix:**
1. Extract inline styles into semantic CSS classes
2. Use design tokens for values
3. Create reusable component classes

```css
/* dashboard.css */
.role-display {
  display: flex;
  gap: var(--spacing-lg);
  justify-content: center;
  margin-top: var(--spacing-md);
  flex-wrap: wrap;
}

.role-card {
  text-align: center;
  padding: var(--spacing-sm) var(--spacing-lg);
  background: rgba(46, 76, 115, 0.1);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-primary);
}

.role-card--accent {
  border-left-color: var(--color-primary-light);
  background: rgba(27, 155, 216, 0.1);
}

.role-label {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  font-weight: var(--font-weight-medium);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--spacing-xs);
}
```

```html
<!-- After -->
<div class="role-display">
  <div class="role-card">
    <div class="role-label">Primary Lead</div>
    <div class="role-value">{{ primary_lead_today }}</div>
  </div>
</div>
```

**Success Criteria:**
- [ ] All inline styles converted to CSS classes
- [ ] Classes use design tokens for values
- [ ] No `style=""` attributes remain in templates (except dynamic values)
- [ ] Visual appearance unchanged after refactor
- [ ] CSS classes are reusable across pages

---

## High Priority Flaws

### FLAW-004: Hardcoded Color Values in Component CSS

**Location:**
- `app/templates/employees.html` (lines 45-88, embedded CSS)
- `app/templates/auto_schedule_review.html` (lines 21-292)
- Various page-specific embedded styles

**Description:**
Many colors are hardcoded as hex values instead of using design tokens:
- `#FF69B4`, `#00FFFF`, `#ff9800` for badges
- `#2c3e50`, `#7f8c8d`, `#95a5a6` for text
- `#dee2e6`, `#f8f9fa` for backgrounds

**Why This Is a Flaw:**
1. **No single source of truth:** Colors can't be changed globally
2. **Dark mode incompatible:** Hardcoded colors won't adapt to themes
3. **Inconsistent palette:** Random hex values not from design system
4. **Brand drift:** Colors may not match brand guidelines

**Current Implementation:**
```css
/* employees.html */
.badge-lead-event-specialist { background: #FF69B4; }
.badge-club-supervisor { background: #00FFFF; color: #000; }

/* auto_schedule_review.html */
.review-header h1 { color: #2c3e50; }
.stat-card h3 { color: #7f8c8d; }
```

**Recommended Fix:**
1. Create semantic token variables for all use cases
2. Replace hardcoded values with token references
3. Move embedded styles to external CSS files

```css
/* design-tokens.css additions */
:root {
  /* Role badge colors */
  --color-badge-lead: #FF69B4;
  --color-badge-supervisor: #00FFFF;
  --color-badge-juicer: var(--color-secondary);
  --color-badge-specialist: var(--color-success);

  /* Review page colors (map to existing tokens) */
  --color-heading-dark: var(--color-neutral-800);
  --color-text-muted: var(--color-neutral-500);
}
```

**Success Criteria:**
- [ ] All hardcoded colors replaced with design tokens
- [ ] Token names are semantic (describe purpose, not color)
- [ ] Visual appearance unchanged
- [ ] Easy to implement dark mode in future

---

### FLAW-005: Inconsistent Modal Implementations

**Location:**
- `app/templates/base.html` (multiple modals)
- `app/templates/daily_view.html` (reschedule, reissue, bulk-reassign modals)
- `app/templates/employees.html` (employee modals)
- `app/static/css/modals.css`
- `app/static/css/components/modal.css`

**Description:**
Multiple modal implementation patterns exist:
1. BEM-style `.modal__overlay`, `.modal__container` (components/modal.css)
2. Legacy `.modal`, `.modal-content` (employees.html)
3. `.modal-backdrop`, `.action-modal` (daily_view.html)
4. Inline modal styles in templates

**Why This Is a Flaw:**
1. **Inconsistent behavior:** Focus trapping, escape handling varies
2. **Maintenance burden:** Multiple patterns to maintain
3. **Visual inconsistency:** Different animations, padding, styling
4. **Developer confusion:** Which pattern to use?

**Current Implementation:**
```html
<!-- Pattern 1: base.html -->
<div class="modal">
  <div class="modal-overlay"></div>
  <div class="modal-container">...</div>
</div>

<!-- Pattern 2: employees.html -->
<div class="modal">
  <div class="modal-content">...</div>
</div>

<!-- Pattern 3: daily_view.html -->
<div class="modal-backdrop">
  <div class="action-modal">...</div>
</div>
```

**Recommended Fix:**
1. Choose one modal pattern (BEM pattern from components/modal.css)
2. Create a reusable modal component
3. Migrate all modals to consistent structure
4. Remove duplicate CSS

```html
<!-- Standardized modal structure -->
<div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <div class="modal__overlay"></div>
  <div class="modal__container modal__container--medium">
    <header class="modal__header">
      <h2 class="modal__title" id="modal-title">Title</h2>
      <button class="modal__close" aria-label="Close">×</button>
    </header>
    <div class="modal__body">Content</div>
    <footer class="modal__footer">
      <button class="btn btn-secondary">Cancel</button>
      <button class="btn btn-primary">Confirm</button>
    </footer>
  </div>
</div>
```

**Success Criteria:**
- [ ] Single modal CSS file used across all pages
- [ ] All modals use consistent HTML structure
- [ ] Focus trapping works consistently
- [ ] Escape key closes all modals
- [ ] Animations are consistent

---

### FLAW-006: Missing Cursor Pointer on Interactive Elements

**Location:** Various templates and CSS files

**Description:**
Many interactive elements (cards, clickable divs, custom buttons) are missing `cursor: pointer`, making it unclear they are interactive.

**Why This Is a Flaw:**
1. **Poor affordance:** Users can't tell elements are clickable
2. **Reduced usability:** Hesitation before clicking
3. **Accessibility concern:** Visual indicator of interactivity missing

**Current Implementation:**
```css
/* Cards with hover effects but no cursor change */
.stat-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-4px);
  /* Missing: cursor: pointer; */
}

.unscheduled-item:hover {
  box-shadow: var(--shadow-sm);
  transform: translateY(-2px);
  /* Missing: cursor: pointer; */
}
```

**Recommended Fix:**
Add `cursor: pointer` to all interactive elements:

```css
/* Global interactive element rule */
[onclick],
[role="button"],
.stat-card,
.event-card,
.unscheduled-item,
.core-event-item,
.clickable {
  cursor: pointer;
}
```

**Success Criteria:**
- [ ] All clickable elements show pointer cursor on hover
- [ ] Interactive cards clearly indicate clickability
- [ ] Consistent cursor behavior across the application

---

### FLAW-007: Hover Animations Cause Layout Shift

**Location:**
- `app/templates/index.html` (stat-card, dashboard-section hover)
- Various card components throughout

**Description:**
Hover effects using `transform: translateY(-4px)` create visual shift that can be jarring and may cause layout reflow.

**Why This Is a Flaw:**
1. **Visual instability:** Elements jump on hover
2. **Potential performance:** Transform without will-change can cause repaints
3. **Accessibility:** Users with motor impairments may accidentally trigger
4. **Mobile issues:** Hover states don't work well on touch

**Current Implementation:**
```css
.stat-card:hover {
  transform: translateY(-4px);
}

.dashboard-section:hover {
  transform: translateY(-2px);
}

.core-event-item:hover {
  transform: translateX(4px);
}
```

**Recommended Fix:**
1. Use subtler hover effects (color, shadow only)
2. Or reduce transform distance significantly
3. Add `will-change` for performance
4. Consider removing transforms on touch devices

```css
/* Subtler, more professional approach */
.stat-card {
  transition: box-shadow var(--transition-base), border-color var(--transition-base);
}

.stat-card:hover {
  box-shadow: var(--shadow-lg);
  border-color: var(--color-primary-light);
  /* Remove transform or reduce to 1-2px */
}

/* Or with will-change for performance */
.stat-card {
  will-change: transform, box-shadow;
}

.stat-card:hover {
  transform: translateY(-2px); /* Reduced from -4px */
}

/* Disable on touch devices */
@media (hover: none) {
  .stat-card:hover {
    transform: none;
  }
}
```

**Success Criteria:**
- [ ] Hover effects are subtle and professional
- [ ] No jarring visual jumps
- [ ] Transforms disabled on touch devices
- [ ] Performance optimized with will-change where needed

---

### FLAW-008: Footer Shows Outdated Copyright Year

**Location:** `app/templates/base.html` (line 292)

**Description:**
Footer displays "© 2024" but current year is 2026.

**Why This Is a Flaw:**
1. **Outdated appearance:** Makes app seem unmaintained
2. **Legal concerns:** Copyright year should be current
3. **Easy fix:** Should be dynamic

**Current Implementation:**
```html
<p>&copy; 2024 Product Connections. All rights reserved.</p>
```

**Recommended Fix:**
Use Jinja2 to dynamically set the year:

```html
<p>&copy; {{ now().year }} Product Connections. All rights reserved.</p>
```

Or in the Flask route:
```python
from datetime import datetime
return render_template('base.html', current_year=datetime.now().year)
```

**Success Criteria:**
- [ ] Footer displays current year dynamically
- [ ] Year updates automatically each January

---

### FLAW-009: Table Accessibility Missing

**Location:**
- `app/templates/auto_schedule_review.html` (event-table)
- Various data tables throughout

**Description:**
Tables lack proper accessibility attributes like `scope`, `caption`, and `aria-describedby`.

**Why This Is a Flaw:**
1. **Screen reader incompatibility:** Table relationships not conveyed
2. **WCAG violation:** Tables need proper markup for accessibility
3. **No table description:** Purpose of table unclear to assistive tech

**Current Implementation:**
```html
<table class="event-table">
  <thead>
    <tr><th>Event</th><th>Date</th><th>Status</th></tr>
  </thead>
  <tbody>
    <tr><td>...</td></tr>
  </tbody>
</table>
```

**Recommended Fix:**
```html
<table class="event-table" aria-describedby="table-description">
  <caption class="sr-only" id="table-description">
    List of proposed schedule changes awaiting approval
  </caption>
  <thead>
    <tr>
      <th scope="col">Event</th>
      <th scope="col">Date</th>
      <th scope="col">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">Event Name</th>
      <td>Jan 15</td>
      <td>Pending</td>
    </tr>
  </tbody>
</table>
```

**Success Criteria:**
- [ ] All data tables have `caption` or `aria-describedby`
- [ ] Column headers have `scope="col"`
- [ ] Row headers (if applicable) have `scope="row"`
- [ ] Screen readers can navigate table structure

---

## Medium Priority Flaws

### FLAW-010: Embedded CSS in Templates Instead of External Files

**Location:**
- `app/templates/index.html` (lines 7-457 - 450+ lines of CSS!)
- `app/templates/employees.html` (lines 6-500+)
- `app/templates/auto_schedule_review.html` (lines 6-450+)
- `app/templates/unscheduled.html` (lines 7-240+)
- `app/templates/daily_view.html` (lines 8-92)

**Description:**
Most page templates contain hundreds of lines of embedded CSS in `<style>` tags rather than external stylesheets.

**Why This Is a Flaw:**
1. **No caching:** Styles re-downloaded with every page load
2. **Duplication:** Similar styles repeated across templates
3. **Harder to maintain:** CSS scattered across many files
4. **Larger HTML payloads:** Increases page size
5. **No CSS minification:** External files can be optimized

**Current Implementation:**
```html
{% block extra_head %}
<style>
    /* 400+ lines of CSS embedded in template */
    .page-header { ... }
    .welcome-section { ... }
    .stats-grid { ... }
    /* etc. */
</style>
{% endblock %}
```

**Recommended Fix:**
1. Extract embedded styles to external page-specific CSS files
2. Reference via `<link>` tag
3. Share common styles via component CSS

```html
{% block extra_head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/index.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/stat-card.css') }}">
{% endblock %}
```

**Success Criteria:**
- [ ] All embedded `<style>` blocks moved to external CSS
- [ ] Page-specific styles in `css/pages/` directory
- [ ] Common components in `css/components/`
- [ ] Templates only contain structural HTML
- [ ] CSS files can be cached by browser

---

### FLAW-011: Inconsistent Button Styling Patterns

**Location:** Throughout templates and CSS

**Description:**
Multiple button class patterns in use:
- `.btn .btn-primary` (standard)
- `.btn-small` (employees.html)
- `.btn-sm` (elsewhere)
- `.btn-lock` (custom)
- Various inline button styles

**Why This Is a Flaw:**
1. **Inconsistent naming:** `-small` vs `-sm`
2. **Visual inconsistency:** Different buttons look different
3. **Harder to maintain:** Multiple patterns to support

**Recommended Fix:**
Standardize on a single button system:

```css
/* Button sizes */
.btn-sm { /* Small */ }
.btn    { /* Default */ }
.btn-lg { /* Large */ }

/* Button variants */
.btn-primary { }
.btn-secondary { }
.btn-outline { }
.btn-danger { }
.btn-ghost { }
```

**Success Criteria:**
- [ ] Single button naming convention
- [ ] Consistent visual appearance
- [ ] Documented button system

---

### FLAW-012: Z-Index Management Not Consistently Used

**Location:** Various CSS files

**Description:**
Z-index tokens are defined in design-tokens.css but not consistently used. Hardcoded z-index values appear throughout:
- `z-index: 1000` (modals)
- `z-index: 1001` (modal content)
- `z-index: 999` (mobile nav)

**Why This Is a Flaw:**
1. **Z-index wars:** Conflicting layering
2. **Hard to debug:** Random values scattered
3. **Design tokens ignored:** System exists but unused

**Current Implementation:**
```css
/* design-tokens.css defines */
--z-modal: 1050;
--z-modal-backdrop: 1040;

/* But templates use */
z-index: 1000;
z-index: 1001;
```

**Recommended Fix:**
Replace all hardcoded z-index values with tokens:

```css
.modal { z-index: var(--z-modal); }
.modal-overlay { z-index: var(--z-modal-backdrop); }
.nav-links { z-index: var(--z-fixed); }
```

**Success Criteria:**
- [ ] All z-index values use design tokens
- [ ] No hardcoded z-index values in CSS
- [ ] Clear layering hierarchy documented

---

### FLAW-013: Form Labels Not Associated with Inputs

**Location:** Some modal forms, particularly older templates

**Description:**
Some form labels use visual association only without proper `for` attribute linkage.

**Why This Is a Flaw:**
1. **Accessibility violation:** Screen readers can't associate labels
2. **Usability issue:** Clicking label doesn't focus input
3. **WCAG failure:** Level A requirement

**Current Implementation (problematic):**
```html
<div class="form-group">
  <label>Event:</label>  <!-- Missing for attribute -->
  <div id="reschedule-event-info"></div>
</div>
```

**Recommended Fix:**
```html
<div class="form-group">
  <label for="reschedule-event-info">Event:</label>
  <div id="reschedule-event-info" aria-labelledby="event-label"></div>
</div>
```

**Success Criteria:**
- [ ] All form labels have `for` attribute
- [ ] All inputs have matching `id`
- [ ] Clicking label focuses input

---

### FLAW-014: Mobile Menu Lacks Close Button

**Location:** `app/templates/base.html`, `app/static/css/responsive.css`

**Description:**
Mobile navigation slide-out menu can only be closed by clicking outside or the hamburger button. No explicit close button within the menu.

**Why This Is a Flaw:**
1. **Discoverability:** Users may not know to tap outside
2. **Accessibility:** Touch target for closing is the whole overlay
3. **Consistency:** Most mobile menus have an X button

**Recommended Fix:**
Add a close button at the top of mobile nav:

```html
<div class="nav-links">
  <button class="nav-close" aria-label="Close menu">
    <span class="material-symbols-outlined">close</span>
  </button>
  <!-- Nav items -->
</div>
```

**Success Criteria:**
- [ ] Mobile menu has visible close button
- [ ] Close button is 44x44px touch target
- [ ] Close button has aria-label

---

### FLAW-015: Loading States Show "Loading..." Text

**Location:** `app/templates/daily_view.html` and other templates

**Description:**
Loading states show plain "Loading..." text instead of branded spinners or skeleton screens.

**Why This Is a Flaw:**
1. **Unprofessional:** Plain text looks unfinished
2. **No visual progress indication:** User doesn't know app is working
3. **Inconsistent:** Some places have spinners, others have text

**Current Implementation:**
```html
<div class="loading-spinner" role="status">
  <span class="sr-only">Loading summary...</span>
  Loading...  <!-- Plain text visible to users -->
</div>
```

**Recommended Fix:**
Use consistent loading component:

```html
<div class="loading-state" role="status" aria-live="polite">
  <div class="spinner"></div>
  <span class="sr-only">Loading summary...</span>
</div>
```

**Success Criteria:**
- [ ] All loading states use spinner component
- [ ] Screen reader text describes what's loading
- [ ] Visual spinner animation present

---

### FLAW-016: No Dark Mode Support

**Location:** Application-wide

**Description:**
Application has no dark mode option despite having a design token system that could support it.

**Why This Is a Flaw:**
1. **User preference ignored:** Many users prefer dark mode
2. **Eye strain:** Bright screens in low light environments
3. **Modern expectation:** Dark mode is standard in 2026
4. **Accessibility:** Some users need dark mode for visual reasons

**Recommended Fix:**
1. Add dark mode color tokens
2. Implement media query for system preference
3. Add manual toggle option

```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #1F2937;
    --bg-secondary: #111827;
    --text-primary: #F9FAFB;
    /* etc. */
  }
}
```

**Success Criteria:**
- [ ] Dark mode tokens defined
- [ ] `prefers-color-scheme: dark` respected
- [ ] Manual toggle available in settings
- [ ] All pages render correctly in dark mode

---

### FLAW-017: Touch Scrolling Performance

**Location:** `app/static/css/responsive.css`

**Description:**
`-webkit-overflow-scrolling: touch` is deprecated and may cause performance issues on modern browsers.

**Why This Is a Flaw:**
1. **Deprecated property:** No longer needed in modern iOS
2. **Potential issues:** Can cause rendering bugs
3. **Unnecessary code:** Modern browsers handle this natively

**Current Implementation:**
```css
.notifications-content,
.modal-body,
table {
  -webkit-overflow-scrolling: touch;
}
```

**Recommended Fix:**
Remove deprecated property, use modern alternatives:

```css
.notifications-content,
.modal-body {
  overflow-y: auto;
  overscroll-behavior: contain;
}
```

**Success Criteria:**
- [ ] `-webkit-overflow-scrolling` removed
- [ ] `overscroll-behavior` used where appropriate
- [ ] Scrolling feels smooth on iOS

---

## Low Priority Flaws

### FLAW-018: Inconsistent Border Radius Values

**Location:** Throughout CSS files

**Description:**
Border radius values vary inconsistently: 4px, 6px, 8px, 12px used somewhat randomly.

**Recommended Fix:**
Consistently use design tokens:
- `--radius-sm: 4px` - Small elements
- `--radius-md: 6px` - Buttons, inputs
- `--radius-lg: 8px` - Cards
- `--radius-xl: 12px` - Modals

**Success Criteria:**
- [ ] All border-radius values use tokens

---

### FLAW-019: Missing Focus Styles on Some Custom Elements

**Location:** Custom interactive elements (stat cards, event cards)

**Description:**
Some custom interactive elements lack visible focus styles for keyboard users.

**Recommended Fix:**
```css
.stat-card:focus-visible,
.event-card:focus-visible {
  outline: 2px solid var(--color-primary-light);
  outline-offset: 2px;
}
```

**Success Criteria:**
- [ ] All interactive elements have visible focus states

---

### FLAW-020: Footer Could Be Sticky/Fixed

**Location:** `app/templates/base.html`

**Description:**
Footer is positioned normally and can appear mid-page on short content pages.

**Recommended Fix:**
Implement sticky footer pattern:

```css
body {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
}

.footer {
  margin-top: auto;
}
```

**Success Criteria:**
- [ ] Footer always at bottom of viewport or content

---

### FLAW-021: Print Styles Could Be Enhanced

**Location:** `app/static/css/responsive.css` (lines 765-781)

**Description:**
Print styles are minimal - only hiding navigation. Tables, colors, and layout could be optimized.

**Recommended Fix:**
Enhance print stylesheet:

```css
@media print {
  .header, .footer, .nav-link, button { display: none; }
  .container { max-width: 100%; padding: 0; }
  a { color: black; text-decoration: none; }
  table { page-break-inside: avoid; border: 1px solid #000; }
  .stat-card { border: 1px solid #000; box-shadow: none; }
}
```

**Success Criteria:**
- [ ] Pages print cleanly without interactive elements
- [ ] Tables print with visible borders
- [ ] Colors optimized for black/white printing

---

## Implementation Priority Matrix

| Flaw | Impact | Effort | Priority Score |
|------|--------|--------|----------------|
| FLAW-001 (Emoji icons) | High | Medium | **Critical** |
| FLAW-002 (Duplicate tokens) | High | Medium | **Critical** |
| FLAW-003 (Inline styles) | High | High | **Critical** |
| FLAW-004 (Hardcoded colors) | Medium | Low | High |
| FLAW-005 (Modal inconsistency) | Medium | Medium | High |
| FLAW-006 (Cursor pointer) | Medium | Low | High |
| FLAW-007 (Hover layout shift) | Low | Low | High |
| FLAW-008 (Copyright year) | Low | Low | High |
| FLAW-009 (Table accessibility) | Medium | Low | High |
| FLAW-010 (Embedded CSS) | Medium | High | Medium |
| FLAW-011 (Button naming) | Low | Low | Medium |
| FLAW-012 (Z-index) | Low | Low | Medium |
| FLAW-013 (Form labels) | Medium | Low | Medium |
| FLAW-014 (Mobile close) | Low | Low | Medium |
| FLAW-015 (Loading states) | Low | Low | Medium |
| FLAW-016 (Dark mode) | Medium | High | Medium |
| FLAW-017 (Touch scrolling) | Low | Low | Medium |
| FLAW-018 (Border radius) | Low | Low | Low |
| FLAW-019 (Focus styles) | Medium | Low | Low |
| FLAW-020 (Sticky footer) | Low | Low | Low |
| FLAW-021 (Print styles) | Low | Low | Low |

---

## Recommended Implementation Order

### Phase 1: Quick Wins (1-2 days)
- FLAW-006: Add cursor pointer (15 min)
- FLAW-008: Fix copyright year (5 min)
- FLAW-012: Use z-index tokens (30 min)
- FLAW-017: Remove deprecated CSS (15 min)
- FLAW-018: Standardize border radius (30 min)

### Phase 2: Design Token Cleanup (3-5 days)
- FLAW-002: Consolidate design tokens
- FLAW-004: Replace hardcoded colors
- FLAW-011: Standardize button classes

### Phase 3: Component Standardization (1-2 weeks)
- FLAW-001: Replace emoji icons
- FLAW-005: Unify modal implementations
- FLAW-015: Create loading component

### Phase 4: Major Refactoring (2-4 weeks)
- FLAW-003: Extract inline styles
- FLAW-010: Move embedded CSS to files
- FLAW-016: Implement dark mode

### Phase 5: Accessibility Improvements (1 week)
- FLAW-009: Table accessibility
- FLAW-013: Form label associations
- FLAW-019: Focus styles
- FLAW-014: Mobile menu close button

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | Claude | Initial documentation |
