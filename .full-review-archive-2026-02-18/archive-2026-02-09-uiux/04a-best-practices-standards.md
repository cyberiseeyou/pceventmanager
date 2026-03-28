# Phase 4: Best Practices & Standards Review

Review of 48 Jinja2 templates, 23 CSS files, and 37 JavaScript files against HTML/CSS/JS best practices, WCAG 2.1 AA accessibility standards, and modern frontend patterns.

---

## Critical Findings (5)

### BP-C1: Three Competing Modal Implementations With Inconsistent Accessibility

**Standard violated:** HTML best practices (single canonical component pattern), WCAG 2.1 SC 4.1.2 (Name, Role, Value)

**Evidence:**

The codebase contains three separate modal implementations with incompatible accessibility behaviors:

1. **Jinja2 macro** (`app/templates/components/modal_base.html`) -- Uses `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, BEM naming (`modal__container`), `data-modal-close` attribute pattern.

2. **JavaScript component** (`app/static/js/components/modal.js`) -- Uses `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, different BEM naming (`modal__overlay`), focus trap from `modules/focus-trap.js`, auto-manages body scroll.

3. **Inline HTML in dashboard templates** (`app/templates/dashboard/approved_events.html`, `app/templates/dashboard/weekly_validation.html`) -- Uses non-BEM class names (`modal-overlay`, `modal-content`), different show/hide mechanism (`style="display: none;"` toggled via JS), loads its own copy of `.btn-primary` and `.btn-secondary` with conflicting colors, no `role="dialog"`, no `aria-modal`, no `aria-labelledby`, no focus trap, no Escape key handling.

Additionally, `app/templates/base.html` contains two inline modals (Event Times Warning at line 258, Session Timeout at line 407) that use a fourth pattern: `modal-content` class with hardcoded inline styles, no ARIA dialog role on the Event Times modal, and no focus trap integration.

**Impact:** Screen reader users encounter different behavior depending on which page they are on. Keyboard users cannot dismiss some modals with Escape. Focus is not trapped in dashboard modals, allowing keyboard focus to wander behind the overlay.

---

### BP-C2: 225 Native alert()/confirm() Calls Block the Main Thread

**Standard violated:** JavaScript best practices (non-blocking UI patterns), WCAG 2.1 SC 4.1.3 (Status Messages)

**Evidence (quantified):**

| Source Type | Count | Files |
|-------------|-------|-------|
| Template inline scripts | 214 | 17 template files |
| External JS files | 11 | `main.js` (6), `dashboard.js` (2), `schedule-verification.js` (1), `workload-dashboard.js` (2) |
| `confirm()` calls | 37 | 20 files |
| **Total** | **262** | **21 unique files** |

Worst offenders: `printing.html` (53), `index.html` (28), `calendar.html` (26), `settings.html` (20), `weekly_validation.html` (18).

The application already ships two non-blocking notification systems: `ToastManager` (`app/static/js/modules/toast-notifications.js`) and `Modal` (`app/static/js/components/modal.js`), both with accessibility support. Neither is used by the pages with the highest `alert()` counts.

**Impact:** Native dialogs block the browser thread, preventing background operations. They are unstyled (ignoring the design system), inaccessible to screen readers as dynamic status messages, and impossible to customize. Users cannot interact with the page while a dialog is open.

---

### BP-C3: 161 Inline onclick Handlers Tightly Couple HTML and JavaScript

**Standard violated:** HTML best practices (separation of concerns), JavaScript best practices (event delegation), Content Security Policy compatibility

**Evidence (quantified by file):**

| Template | Count |
|----------|-------|
| `dashboard/approved_events.html` | 27 |
| `index.html` | 20 |
| `dashboard/weekly_validation.html` | 18 |
| `calendar.html` | 12 |
| `inventory/index.html` | 10 |
| `daily_view.html` | 8 |
| `components/quick_note_widget.html` | 8 |
| `sync_admin.html` | 7 |
| `unscheduled.html` | 7 |
| All other templates | 44 |
| **Total** | **161** |

Examples from `app/templates/employees.html` line 76:
```html
<button class="close-modal" onclick="closeAddEmployeeModal()">&times;</button>
```

From `app/templates/index.html`:
```html
<button class="btn-fix" onclick="fixScheduleError(${error.schedule_id}, '${error.project_name}', '${error.error}')">
```

The latter example interpolates JavaScript variables into an onclick attribute, creating a potential injection vector if any value contains a single quote.

**Impact:** Inline handlers require functions to exist in global scope, prevent Content Security Policy enforcement (`unsafe-inline`), cannot be unit-tested, and create tight coupling between markup and behavior. The codebase already demonstrates the correct pattern in `app/static/js/navigation.js`, which uses `addEventListener` throughout.

---

### BP-C4: 380 Inline Style Attributes Bypass the Design Token System

**Standard violated:** CSS best practices (separation of concerns, design token usage), maintainability

**Evidence (quantified by file):**

| Template | Inline `style=` Count |
|----------|----------------------|
| `dashboard/approved_events.html` | 42 |
| `printing.html` | 41 |
| `calendar.html` | 31 |
| `dashboard/daily_validation.html` | 28 |
| `daily_view.html` | 24 |
| `base.html` | 22 |
| `unscheduled.html` | 21 |
| `employees.html` | 19 |
| `auto_scheduler_main.html` | 18 |
| `settings.html` | 17 |
| All other templates | 117 |
| **Total** | **380** |

In `app/templates/base.html` (the master template), lines 260-284 contain a modal whose header, body, footer, and individual elements all use inline styles with hardcoded colors:
```html
<div class="modal-header" style="background: #dc3545; color: white;">
<div class="modal-body" style="padding: 25px;">
<ul style="margin-bottom: 20px; line-height: 1.8; padding-left: 25px;">
<button class="btn btn-primary" id="eventTimesGoToSettings"
    style="padding: 10px 20px; background: #dc3545;">
```

The design token `var(--color-danger)` maps to the same `#dc3545` value, making these inline styles entirely redundant yet unmaintainable.

**Impact:** Changes to the design system (e.g., rebranding, dark mode, accessibility themes) cannot propagate to 380 elements. The master template `base.html` sets a poor example for all developers extending it.

---

### BP-C5: Zero `<fieldset>` Elements Across All 48 Templates

**Standard violated:** WCAG 2.1 SC 1.3.1 (Info and Relationships), HTML form best practices

**Evidence:** A search for `<fieldset` across all templates returns zero results. The application contains numerous form groups that semantically represent related controls:

- `app/templates/employees.html` lines 117-130: A checkbox group for Active/AB Trained/Juicer Trained with no `<fieldset>` or `<legend>`.
- `app/templates/employees.html` lines 133-160: A weekly availability grid of 7 checkboxes (Mon-Sun) with an `<h4>` visual heading but no programmatic `<fieldset>`/`<legend>` grouping.
- `app/templates/settings.html`: Multiple configuration sections with groups of related controls.
- `app/templates/printing.html`: Print option groups with related checkboxes.

**Impact:** Screen reader users cannot determine which controls belong together. When navigating by form element, a user encountering the "Monday" checkbox has no programmatic context that it belongs to "Weekly Availability." WCAG 2.1 AA requires that related form controls be programmatically grouped.

---

## High Findings (8)

### BP-H1: Duplicate FocusTrap Implementations With Different Behavior

**Files:** `app/static/js/modules/focus-trap.js` (171 lines), `app/static/js/utils/focus-trap.js` (251 lines)

The `modules/` version dispatches a custom `escape` event on the container element. The `utils/` version calls an `options.onEscape` callback, filters hidden elements from the focusable list, supports `pause()`/`resume()` for nested modals, and includes a `handleFocusIn` guard.

Both are exported as `FocusTrap` and both are mounted on `window.FocusTrap`. The `utils/` version is loaded in `base.html` (line 314) and exposed globally, but `modal.js` imports from `modules/focus-trap.js` (line 25). Different modals therefore get different keyboard behavior: some filter hidden elements, some do not; some support nested modals, some do not.

---

### BP-H2: Duplicate Screen Reader Announcer Implementations

**Files:** `app/static/js/modules/aria-announcer.js` (`AriaAnnouncer`), `app/static/js/utils/sr-announcer.js` (`ScreenReaderAnnouncer`)

Both create two ARIA live regions (polite + assertive) appended to `document.body`. When both are loaded on the same page, the DOM contains four live regions. The `AriaAnnouncer` uses inline `style` properties for visual hiding; the `ScreenReaderAnnouncer` uses the `sr-only` CSS class. Both are exposed as globals (`window.ariaAnnouncer` and `window.srAnnouncer`). The `ToastManager` imports `ariaAnnouncer` specifically, so code using `window.srAnnouncer` produces announcements in a different live region that the toast system does not manage.

---

### BP-H3: 846 Hardcoded Color Values in CSS Files Despite Design Token System

**Files:** All 20 CSS files (excluding `design-tokens.css`)

Despite `app/static/css/design-tokens.css` defining a comprehensive color palette with 60+ tokens, CSS files contain 846 hardcoded hex color values. The worst offenders:

| File | Hardcoded Colors | `var()` References |
|------|------------------|--------------------|
| `pages/daily-view.css` | 223 | 275 |
| `pages/attendance-calendar.css` | 144 | 106 |
| `modals.css` | 78 | 8 |
| `pages/unscheduled.css` | 36 | 124 |
| `validation.css` | 55 | 50 |
| `style.css` | 44 | 270 |
| `components/schedule-modal.css` | 32 | 17 |
| `components/notification-modal.css` | 50 | 0 |
| `components/ai-chat.css` | 26 | 0 |

Notably, `modals.css` (930 lines) uses almost exclusively hardcoded values (`#3B82F6`, `#E5E7EB`, `#374151`, `#111827`, `#6B7280`, etc.) with only 8 `var()` references -- all for z-index tokens. The design token `--color-info: #3B82F6` exists but is not referenced.

---

### BP-H4: Duplicate CSS Rule Declarations in style.css Create Conflicting Renders

**File:** `app/static/css/style.css`

Several CSS classes are defined twice with conflicting property values:

- `.event-type-badge` -- First definition (line ~865) uses `var()` tokens; second definition (line ~1254) uses hardcoded values with different sizing.
- `.event-type-core` -- First definition uses `background: linear-gradient(135deg, #28a745, #20c997)` (green); second uses `background-color: #dc3545` (red). These are opposite colors for the same event type.
- `.alert` and `.alert-success` -- Defined at lines ~920 and ~1166 with different padding, borders, and colors.
- `.btn` -- Defined with conflicting heights and padding at lines ~692 and ~780.

Due to CSS cascade rules, the second definition always wins, making the first definition dead code that misleads developers.

---

### BP-H5: Dashboard Templates Load External CSS Frameworks

**Files:** `app/templates/dashboard/approved_events.html` (line 6), `app/templates/dashboard/daily_validation.html`

The `approved_events.html` template loads Font Awesome 6.4 from a CDN:
```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
    crossorigin="anonymous" />
```

The `daily_validation.html` template previously loaded Bootstrap 4.6. Both templates also contain massive `<style>` blocks (the `approved_events.html` block starts at line 8 and contains hundreds of lines of inline CSS) that redefine core component classes (`.btn-primary`, `.btn-secondary`, `.modal-content`) with completely different values than the design system.

Meanwhile, the rest of the application uses Material Symbols icons loaded in `base.html`. This means the same semantic concept ("icon for a close button") uses three different icon systems across the app.

---

### BP-H6: No Semantic HTML Landmarks on Most Pages

**Standard violated:** WCAG 2.1 SC 1.3.1, SC 2.4.1 (Bypass Blocks)

Out of 48 templates, semantic landmark elements (`<main>`, `<section>`, `<article>`, `<nav>`, `<aside>`, `<header>`, `<footer>`) appear in only 17 files with a total of 64 occurrences, concentrated heavily in `base.html` (3), `daily_view.html` (13), and the 11 help templates (3 each, from their shared layout).

Critically, `base.html` wraps page content in `<div class="main-content" id="main-content">` instead of a `<main>` element. The skip-to-content link at line 35 targets `#main-content`, but a `<div>` is not a landmark region, so screen reader landmark navigation will not identify it as the main content area.

Templates like `employees.html`, `calendar.html`, `unscheduled.html`, `printing.html`, `settings.html`, and all dashboard templates use only `<div>` elements for structural grouping, with no semantic landmarks.

---

### BP-H7: ES Module and Global Script Race Condition in base.html

**File:** `app/templates/base.html` (lines 302-331)

The base template loads ES modules and global scripts in this order:

1. Line 302: `csrf_helper.js` loaded as regular `<script>` (synchronous)
2. Lines 306-327: ES module block that imports `apiClient`, `stateManager`, `ariaAnnouncer`, `toaster`, `loadingState`, `ValidationEngine`, `FocusTrap` and assigns them to `window.*`
3. Line 330: `navigation.js` loaded as regular `<script>` (synchronous)
4. Line 333: `user_dropdown.js` loaded as regular `<script>` (synchronous)
5. Line 336: `database-refresh.js` loaded as regular `<script>` (synchronous)

ES module scripts are deferred by specification -- they execute after the document is parsed. However, the global scripts at lines 330-336 execute synchronously and earlier. If any of these scripts reference `window.apiClient` or `window.toaster`, they will find `undefined` because the module has not yet executed.

Currently `navigation.js` and `database-refresh.js` do not reference these globals, but the pattern is fragile -- any future developer adding `window.toaster.success()` to a global script will encounter an intermittent runtime error.

---

### BP-H8: 150 innerHTML Assignments in JavaScript Without Sanitization

**Files:** 20 JavaScript files

| File | innerHTML Count |
|------|----------------|
| `pages/daily-view.js` | 36 |
| `employees.js` | 15 |
| `main.js` | 14 |
| `pages/schedule-form.js` | 12 |
| `components/schedule-modal.js` | 11 |
| `search.js` | 9 |
| `utils/loading-state.js` | 7 |

Template literal strings containing server-provided data are assigned via `innerHTML`:
```javascript
// app/static/js/employees.js, createEmployeeCard()
return `<div class="employee-card" data-employee-id="${employee.id}">
    <h3 class="employee-name">${employee.name}</h3>`;
```

If `employee.name` contains `<script>` or event handlers, it will execute. The safer alternative `textContent` or DOM API (`createElement`/`appendChild`) is used in newer modules like `toast-notifications.js` but not in older files.

---

## Medium Findings (10)

### BP-M1: No `<main>` Element in base.html Layout

**File:** `app/templates/base.html` line 289

The page content wrapper uses:
```html
<div class="main-content" id="main-content">
    {% block content %}{% endblock %}
</div>
```

Per WCAG 2.1 SC 2.4.1 and HTML5 semantics, this should be a `<main>` element. The skip-to-content link at line 35 targets this ID, but assistive technology landmark navigation cannot identify a `<div>` as the main content region.

---

### BP-M2: 279 DOM Style Manipulations via JavaScript `.style` Property

**Files:** 27 JavaScript files, most heavily `pages/daily-view.js` (64), `main.js` (33), `login.js` (29)

DOM elements are shown/hidden and styled by directly setting `.style` properties:
```javascript
// app/static/js/main.js, displayConflictWarnings()
warningsContainer.style.cssText = `
    margin: var(--spacing-md) 0;
    padding: var(--spacing-md);
    border-radius: var(--border-radius-md);
    background: ${conflictData.has_conflicts ? 'rgba(220, 53, 69, 0.1)' : 'rgba(255, 193, 7, 0.1)'};
`;
```

The CSS-in-JS approach makes styles impossible to override via CSS specificity, invisible to the browser's style debugging tools, and uncacheable. The preferred pattern is to toggle CSS classes.

---

### BP-M3: Inconsistent BEM Naming Convention

**CSS Files:** Mixed conventions across the codebase

Newer components use BEM consistently:
- `modal_base.html`: `modal__container`, `modal__header`, `modal__title`, `modal__close`, `modal__body`, `modal__footer`
- `toast-notifications.js`: `toast__icon`, `toast__content`, `toast__message`, `toast__close`, `toast__progress`
- `style.css` notifications: `notifications-empty__icon`, `notifications-empty__message`, `notification-item__header`

Older code uses flat naming:
- `style.css`: `.nav-link`, `.nav-dropdown`, `.schedule-btn`, `.form-group`, `.loading-spinner`
- `modals.css`: `.modal-header`, `.modal-body`, `.modal-footer`, `.modal-close` (non-BEM)
- `pages/daily-view.css`: `.daily-view-header`, `.btn-back`, `.date-navigation` (kebab-case, no BEM)

The result is that two naming conventions coexist: BEM with double underscores for element separators and single or double hyphens for modifier separators, alongside flat kebab-case without BEM structure. There is no documented convention in the codebase to guide which pattern to use.

---

### BP-M4: CSS Specificity Conflicts from Multiple `.btn` Redefinitions

**Files:** `app/static/css/style.css`, `app/static/css/modals.css`

The `.btn` class is defined in `style.css` at two locations (lines ~692 and ~780) and again in `modals.css` (line ~650). Each definition sets different `padding`, `font-size`, `font-weight`, `border-radius`, and `border` values. Since `modals.css` is loaded after `style.css` in `base.html`, the modals version wins globally, not just within modals.

Similarly, `.btn-primary` and `.btn-secondary` are defined in `style.css` using `var(--primary-color)` but redefined in `modals.css` with hardcoded `#3B82F6` -- a different shade of blue than the design token value of `#2E4C73`.

---

### BP-M5: Form Labels Not Programmatically Associated in Some Templates

**Standard violated:** WCAG 2.1 SC 1.3.1, SC 3.3.2 (Labels or Instructions)

While most form inputs have associated `<label>` elements (212 `<label>` tags found), several patterns break the association:

In `app/templates/employees.html` lines 117-130, checkbox inputs are nested inside `<label>` elements (implicit association, which is valid) but use `<span>` for label text without clear visual separation. However, the "Weekly Availability" section uses `<label for="avail-monday">Mon</label>` with matching `id` attributes, which is correctly associated.

The `app/templates/employees.html` line 84 shows:
```html
<label for="employee-id">Employee ID</label>
<input type="text" id="employee-id" placeholder="e.g., US814117">
```
This is correctly associated. However, the `placeholder` is used as supplementary instruction, which disappears on input, violating the pattern of persistent visible labels.

The larger concern is form groups without `<fieldset>`/`<legend>` (see BP-C5), where individual labels exist but the group relationship is not communicated.

---

### BP-M6: login.html Does Not Extend base.html

**File:** `app/templates/login.html`

The login page is a standalone HTML document that does not use `{% extends "base.html" %}`. While this is an intentional design choice (login has a unique layout), it means:

- The design token CSS is loaded independently (line 11), but `responsive.css` is not loaded.
- The login page has no skip-to-content link.
- The login page does not load the CSRF helper script (`csrf_helper.js`), relying on standard form submission with action attribute instead.
- There is no `<main>` landmark element; the content is in `<div class="login-container">`.

The login form itself is well-implemented: proper `for`/`id` associations, `autocomplete` attributes, `aria-describedby`, required indicators, and password visibility toggle.

---

### BP-M7: ToastManager Injects CSS via JavaScript Instead of External Stylesheet

**File:** `app/static/js/modules/toast-notifications.js` lines 544-728

The `ToastManager._injectStyles()` method creates a `<style>` element with 170+ lines of CSS and appends it to `<head>`. This CSS is:
- Not cacheable independently (embedded in JS)
- Not visible in CSS debugging tools until JS executes
- Not subject to the design token system (uses hardcoded colors `#10b981`, `#ef4444`, `#f59e0b`, `#3b82f6`)
- Duplicates the BEM pattern but with different token values than `design-tokens.css`

---

### BP-M8: Inconsistent Loading State Patterns

The application displays loading states in at least four different ways:

1. **Text replacement:** `grid.innerHTML = '<div class="loading">Loading employees</div>';` (employees.js line 14)
2. **CSS class:** `loading-states.css` provides `.skeleton-loader` and `.loading-overlay` classes
3. **JavaScript utility:** `app/static/js/utils/loading-state.js` provides a `LoadingState` class
4. **Inline HTML:** `<div class="notifications-loading">Loading...</div>` in `base.html` line 186

The `loading-state.js` utility creates overlay elements with inline styles, the CSS file provides skeleton screen patterns, and most actual pages use simple text replacement. There is no documented standard for which approach to use.

---

### BP-M9: window.* Global Namespace Pollution

**Files:** 28 JavaScript files, 182 `window.*` assignments

The application exposes 15+ objects on the global `window` namespace:
- `window.apiClient`, `window.stateManager`, `window.ariaAnnouncer`, `window.toaster`, `window.loadingState`, `window.ValidationEngine`, `window.FocusTrap`, `window.createFocusTrap` (from base.html module block)
- `window.navigationManager` (navigation.js)
- `window.srAnnouncer` (sr-announcer.js)
- `window.getCsrfToken` (csrf_helper.js)
- `window.currentEventType`, `window.currentEmployeeId`, `window.currentScheduleDate`, `window.currentStartDate`, `window.currentDueDate`, `window.currentEventName` (main.js, for cross-function state)

`main.js` uses 38 `window.*` references for inter-function state passing, creating implicit coupling between functions that should use parameters or a state object.

---

### BP-M10: 45 Full-Page Reloads After CRUD Operations

**Files:** 9 JS files, 12 templates

After successful create/update/delete operations, the application calls `window.location.reload()` instead of updating the DOM. Examples:

- `app/static/js/main.js` line 80: After import, `setTimeout(() => { window.location.reload(); }, 2000);`
- `app/static/js/main.js` line 936: After reschedule, `window.location.reload();`

This loses scroll position, triggers a full server round-trip, causes a flash of unstyled content, and negates the benefit of having a JSON API. The toast notification system supports inline feedback, but most operations do not use it.

---

## Low Findings (6)

### BP-L1: Mixed CSS Architecture -- Token Aliases Create Triple Indirection

**File:** `app/static/css/style.css` lines 13-50

The file defines a second `:root` block with semantic aliases that reference design tokens:
```css
--secondary-color: var(--color-primary-light);
--success-color: var(--color-success);
--error-color: var(--color-danger);
--bg-primary: var(--color-neutral-50);
--text-primary: var(--color-primary);
```

This creates a three-layer system: `--color-primary` (token) -> `--primary-color` (legacy alias in tokens) -> `--text-primary` (semantic alias in style.css). A developer changing the primary color must understand all three layers. While indirection can be useful for theming, this particular triple layer is undocumented and confusing.

---

### BP-L2: Inconsistent CSRF Token Header Names

**Files:** `app/static/js/csrf_helper.js` (line 57, 84, 116), `app/static/js/utils/api-client.js` (line 51)

The CSRF helper sends `X-CSRF-Token` header. The API client also sends `X-CSRFToken` (no hyphen between CSRF and Token). If the backend only checks one header name, requests from the other source may fail CSRF validation silently.

---

### BP-L3: Console.log Statements in Production Code

**Files:** Throughout all JS modules

Every module includes `console.log` statements for initialization and operation tracking:
- `[Base] Core infrastructure modules loaded` (base.html line 326)
- `[ToastManager] Initialized at position:` (toast-notifications.js line 57)
- `[FocusTrap] Activated` / `Deactivated` (both focus-trap files)
- `[AriaAnnouncer] Announced (polite):` (aria-announcer.js line 86)
- `[Session] Activity tracker initialized` (base.html line 587)
- `[CSRF] Protection initialized successfully` (csrf_helper.js line 182)
- `Override toggled:` debug log (main.js line 957)

These add noise to the browser console and may expose implementation details. A logging utility with configurable log levels would allow disabling verbose output in production.

---

### BP-L4: CSS `!important` Usage

**Files:** `app/static/css/responsive.css`, `app/static/css/style.css`, `app/static/css/design-tokens.css`

The `!important` flag is used in:
- `responsive.css`: `.hidden-mobile { display: none !important; }` and similar utility classes (justified for utility overrides)
- `responsive.css`: `.nav-close { display: none !important; }` (used to hide mobile-only elements on desktop)
- `responsive.css`: `.nav-dropdown-menu { position: absolute !important; }` at lines 133-138 (workaround for specificity conflict)
- `style.css`: `.nav-dropdown-menu[hidden] { display: none !important; }` (overriding the `hidden` attribute behavior)
- `design-tokens.css`: `@media (prefers-reduced-motion)` uses `!important` on all animations (justified for accessibility)

Most uses are justified (utility classes, accessibility), but the `.nav-dropdown-menu` `!important` at line 133 is a specificity workaround that indicates a deeper cascade issue.

---

### BP-L5: Heading Hierarchy Skips in Some Templates

**Standard:** WCAG 2.1 SC 1.3.1 (Info and Relationships)

In `app/templates/employees.html`, the heading hierarchy is: `<h1>` (from base page title style) -> `<h2>` (section title) -> `<h3>` (employee name in card) -> `<h4>` (inline, at line 132 for "Weekly Availability"). This is a valid sequence.

However, `app/templates/index.html` uses `<h1>` for the page title, then `<h3>` for section titles (skipping `<h2>`), which breaks the heading hierarchy for screen reader navigation.

---

### BP-L6: Redundant `.sr-only` Definitions

**Files:** `app/static/css/design-tokens.css` (line 253), `app/static/css/responsive.css` (line 1097), `app/static/css/modals.css` (line 513)

The `.sr-only` class (screen-reader-only visually hidden pattern) is defined three times with identical properties. While this does not cause functional issues due to CSS cascade, it creates maintenance overhead if the pattern needs to be updated.

---

## Positive Findings

### PF-1: Comprehensive Design Token System

`app/static/css/design-tokens.css` (246 lines) defines a thorough, well-documented token system covering:
- Color palette with semantic naming (primary, secondary, success, warning, danger, info)
- Event-type-specific colors (juicer, digital, core, supervisor, freeosk)
- Role badge colors for employee types
- Typography scale with accessibility minimum (14px body text)
- 4px grid spacing system with semantic aliases
- Component-specific tokens (event cards, buttons, inputs, modals, navigation)
- Shadow scale (xs through xl)
- Border tokens with radius scale
- Transition timing tokens
- Z-index layering system (10 defined layers)
- Breakpoint reference documentation

When files use it consistently (e.g., `pages/index.css` with 171 `var()` references), the design system works well.

### PF-2: Skip-to-Content Link and Keyboard Navigation Infrastructure

`app/templates/base.html` line 35 includes a skip-to-content link:
```html
<a href="#main-content" class="skip-to-content">Skip to main content</a>
```

The CSS in `design-tokens.css` properly hides it off-screen and reveals it on `:focus`. The `responsive.css` file provides comprehensive `:focus-visible` styles for all interactive elements, distinguishing keyboard and mouse focus.

### PF-3: Reduced Motion and High Contrast Support

Three files (`design-tokens.css`, `style.css`, `responsive.css`) include `@media (prefers-reduced-motion: reduce)` rules that disable animations and transitions. Two files include `@media (prefers-contrast: high)` rules that increase border widths and outline widths. This demonstrates awareness of WCAG 2.1 SC 2.3.3 (Animation from Interactions).

### PF-4: Well-Implemented Touch Target Sizing

`app/static/css/responsive.css` enforces 44x44px minimum touch targets on touch devices via `@media (hover: none) and (pointer: coarse)`, sets 16px font size on inputs to prevent iOS zoom, and includes safe area inset support for notched devices.

### PF-5: Proper ARIA Attributes on Navigation

`app/templates/base.html` navigation uses `aria-haspopup="true"`, `aria-expanded="false"`, `aria-label` on buttons, and the `hidden` attribute on dropdown menus. The `NavigationManager` in `navigation.js` correctly toggles `aria-expanded` when opening/closing dropdowns. Dropdown menus use the `hidden` attribute (semantically correct) rather than just CSS `display: none`.

### PF-6: Modal Macro Component (modal_base.html) Is Well-Designed

The Jinja2 macro at `app/templates/components/modal_base.html` implements:
- `role="dialog"` and `aria-modal="true"`
- `aria-labelledby` linking title to modal container
- Close button with `aria-label="Close {{ title }}"` (contextual)
- Size variants (small, medium, large)
- BEM naming convention (`modal__container`, `modal__header`, etc.)
- `data-modal-close` attribute for declarative close behavior
- Footer slot support via a second macro variant

### PF-7: API Client With Timeout and Retry

`app/static/js/utils/api-client.js` implements:
- Configurable request timeout (default 10s) via `AbortController`
- Retry logic with configurable delay (default 1 retry, 1s delay)
- User-friendly error messages for all HTTP status codes
- Automatic CSRF token attachment
- Network offline detection
- Clean separation of GET/POST/PUT/DELETE methods

### PF-8: Comprehensive Responsive Breakpoint Coverage

The `responsive.css` file covers:
- Desktop (default)
- Tablet (1024px)
- Mobile (768px)
- Small mobile (480px)
- Extra small (374px)
- Landscape orientation with height constraints (600px, 500px, 400px)
- Print styles
- Dynamic viewport height (`100dvh`) for mobile browser compatibility

### PF-9: Toast Notification System With Accessibility

`app/static/js/modules/toast-notifications.js` provides:
- `aria-live="polite"` for non-error toasts, `aria-live="assertive"` for errors
- Integration with `AriaAnnouncer` for screen reader announcements
- Progress bar with pause-on-hover
- Auto-dismiss with configurable duration
- Close button with `aria-label="Close notification"`
- Maximum toast limit to prevent UI overflow
- Mobile-responsive layout

### PF-10: Login Form Accessibility

`app/templates/login.html` demonstrates strong form accessibility:
- `<label>` elements with `for` attributes matching input `id` values
- `aria-describedby` linking inputs to help text
- `autocomplete` attributes (`username`, `current-password`)
- Required field indicators with `required` attribute
- `maxlength` and `minlength` validation attributes
- Password visibility toggle with `aria-label`
- Loading state with visual spinner and text

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Critical findings | 5 |
| High findings | 8 |
| Medium findings | 10 |
| Low findings | 6 |
| Positive findings | 10 |

### Key Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| Inline `style` attributes | 380 across 35 templates | Poor -- design system bypassed |
| Inline `onclick` handlers | 161 across 23 templates | Poor -- tight coupling, CSP incompatible |
| `alert()`/`confirm()` calls | 262 across 21 files | Poor -- blocking, inaccessible |
| `innerHTML` assignments in JS | 150 across 20 files | Moderate risk -- unsanitized |
| Hardcoded hex colors in CSS | 846 across 20 files | Poor -- tokens not adopted uniformly |
| `var()` token references in CSS | 1,783 across 21 files | Good -- tokens used where adopted |
| ARIA attributes in templates | 120 across 14 templates | Moderate -- concentrated in newer pages |
| Semantic landmarks in templates | 64 across 17 templates | Low -- most pages use only `<div>` |
| `<fieldset>` elements | 0 | Poor -- no form grouping |
| ES module exports | 26 across 15 files | Good -- newer code is modular |
| Global `window.*` assignments | 182 across 28 files | High -- significant namespace pollution |
| Modal implementations | 3 (macro + JS + inline) | Poor -- no single canonical pattern |
| FocusTrap implementations | 2 (modules/ + utils/) | Poor -- should be unified |
| Screen reader announcer implementations | 2 (modules/ + utils/) | Poor -- should be unified |

### Architecture Gap Assessment

The codebase exhibits a clear generational split: newer code (modules/, utils/, components/, modal_base.html) follows modern best practices with ES modules, BEM naming, design tokens, ARIA attributes, and accessibility features. Older code (index.html, dashboard templates, calendar.html, main.js) uses inline styles, inline handlers, global functions, native dialogs, and hardcoded colors.

The infrastructure for best-practice compliance exists (design tokens, toast notifications, modal components, focus traps, ARIA announcers, API client). The primary gap is adoption: the majority of user-facing pages still use the older patterns, and the newer infrastructure has not been retrofitted onto existing pages.
