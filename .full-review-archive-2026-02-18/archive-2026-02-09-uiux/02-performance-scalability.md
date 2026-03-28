# Frontend Performance & Scalability Analysis

**Application**: Crossmark Employee Scheduling Webapp
**Stack**: Flask/Jinja2, Vanilla JS (ES modules + global scripts), CSS Custom Properties
**Scope**: 48 Jinja2 templates, 23 CSS files, 37 JavaScript files
**Date**: 2026-02-09

---

## Executive Summary

The frontend suffers from **five systemic performance problems** that compound on every page load:

1. **Unminified, unbundled assets**: 633KB of JavaScript and 299KB of CSS delivered as 60+ individual HTTP requests with no build pipeline, no minification, and no cache busting.
2. **Massive inline code in templates**: Over 5,900 lines of inline JavaScript and 2,958 lines of inline CSS embedded directly in Jinja2 templates, making them uncacheable.
3. **Full-page reload anti-pattern**: 45 `location.reload()` calls across 20 files destroy user state after every CRUD operation instead of performing targeted DOM updates.
4. **Render-blocking resource chain**: The critical rendering path loads 2 CDN fonts, 8 local CSS files, and a synchronous CSRF script before any content paints.
5. **ES module/global script race condition**: Core infrastructure is loaded via `type="module"` (deferred by spec) then immediately consumed by synchronous `<script>` tags, creating a timing dependency that fails silently.

Estimated aggregate impact on a typical page load: **+2-4 seconds to Largest Contentful Paint (LCP)** and **+500ms-1s to Time to Interactive (TTI)** on 3G/throttled connections.

---

## Table of Contents

1. [Asset Loading & Critical Rendering Path](#1-asset-loading--critical-rendering-path)
2. [CSS Performance](#2-css-performance)
3. [JavaScript Performance](#3-javascript-performance)
4. [Image & Font Loading](#4-image--font-loading)
5. [Caching Strategy](#5-caching-strategy)
6. [Network Requests & API Patterns](#6-network-requests--api-patterns)
7. [DOM Complexity & Template Size](#7-dom-complexity--template-size)
8. [Summary Table](#8-summary-table)

---

## 1. Asset Loading & Critical Rendering Path

### PERF-01: Render-Blocking CSS Chain (8 files, no bundling) -- Critical

**Severity**: Critical
**Estimated Impact**: +400-800ms to First Contentful Paint (FCP)

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/base.html`, lines 23-31):

Every page load triggers 8 synchronous CSS requests before the browser can render anything:

```html
<link rel="stylesheet" href="...css/design-tokens.css">      <!-- 9.4KB -->
<link rel="stylesheet" href="...css/style.css">               <!-- 41.7KB -->
<link rel="stylesheet" href="...css/modals.css">              <!-- 18.0KB -->
<link rel="stylesheet" href="...css/loading-states.css">      <!-- 2.5KB -->
<link rel="stylesheet" href="...css/keyboard-shortcuts.css">  <!-- 2.0KB -->
<link rel="stylesheet" href="...css/form-validation.css">     <!-- 6.3KB -->
<link rel="stylesheet" href="...css/responsive.css">          <!-- 24.8KB -->
<link rel="stylesheet" href="...css/components/notification-modal.css"> <!-- 9.7KB -->
```

**Total**: 114.4KB unminified across 8 HTTP requests. Each request adds latency (DNS, TCP, TLS for each resource on HTTP/1.1). CSS is render-blocking by default -- the browser cannot paint until all stylesheets are downloaded and parsed.

Page-specific CSS adds further requests. For example, `index.html` adds 4 more files (index.css, dashboard.css, schedule-modal.css, modal.css) bringing the total to 12 render-blocking CSS requests and ~172KB before content appears.

**Recommendation**: Introduce a build step (e.g., esbuild, PostCSS CLI, or a simple concatenation script) to produce a single minified CSS bundle. Expected reduction: ~40% file size via minification, and 7 fewer HTTP roundtrips.

```bash
# Example: concatenate and minify with esbuild
esbuild --bundle app/static/css/style.css --minify --outfile=app/static/dist/bundle.css
```

---

### PERF-02: ES Module / Global Script Race Condition -- Critical

**Severity**: Critical
**Estimated Impact**: Intermittent runtime errors, undefined `window.apiClient` on slow connections

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/base.html`, lines 302-333):

```html
<!-- Synchronous script (executes immediately) -->
<script src="...js/csrf_helper.js"></script>

<!-- ES Module (deferred by specification) -->
<script type="module">
    import { apiClient } from '...js/utils/api-client.js';
    window.apiClient = apiClient;  // Sets global
</script>

<!-- Synchronous scripts (execute before module completes) -->
<script src="...js/navigation.js"></script>
<script src="...js/user_dropdown.js"></script>
<script src="...js/database-refresh.js"></script>
```

Per the HTML specification, `type="module"` scripts are **always deferred** -- they execute after the document is parsed but their execution order relative to non-module scripts is not guaranteed until DOMContentLoaded. The synchronous scripts that follow may attempt to access `window.apiClient`, `window.toaster`, etc. before the module block has executed.

The downstream scripts (navigation.js, database-refresh.js) use `document.readyState === 'loading'` checks, which partially mitigate the race. However, any code that accesses the globals at parse time or in inline script blocks will fail silently.

**Evidence of consumption** (`/home/elliot/flask-schedule-webapp/app/static/js/pages/daily-view.js`): Over 20 references to `window.toaster`, `window.loadingState`, etc. that depend on the module having executed first.

**Recommendation**: Convert the global scripts to modules, or use a module-aware loader pattern:

```html
<!-- Option A: Make everything a module -->
<script type="module" src="...js/navigation.js"></script>

<!-- Option B: Use a ready check pattern -->
<script>
  window._coreReady = new Promise(resolve => {
    window._resolveCoreReady = resolve;
  });
</script>
<script type="module">
  import { apiClient } from '...js/utils/api-client.js';
  window.apiClient = apiClient;
  window._resolveCoreReady();
</script>
```

---

### PERF-03: No JavaScript Bundling (37 individual files, 633KB total) -- High

**Severity**: High
**Estimated Impact**: +1-3 seconds to TTI on slow connections (HTTP/1.1 connection limits)

**Evidence** (file size analysis):

| File | Size |
|------|------|
| `daily-view.js` | 160KB |
| `main.js` | 39KB |
| `attendance-calendar.js` | 35KB |
| `employees.js` | 31KB |
| `schedule-form.js` | 24KB |
| `schedule-modal.js` | 23KB |
| `validation-engine.js` | 22KB |
| `trade-modal.js` | 22KB |
| `toast-notifications.js` | 21KB |
| 28 more files... | ~256KB |
| **Total** | **633KB** |

None of these files are minified. No tree-shaking is applied. Every page loads the base.html scripts (csrf_helper, api-client, state-manager, aria-announcer, toast-notifications, loading-state, validation-engine, focus-trap, navigation, user_dropdown, database-refresh, notifications, ai-assistant, notification-modal) = **14 script requests** minimum before any page-specific JavaScript loads.

**Recommendation**: Implement a simple build pipeline:

```bash
# Minification alone saves ~40%
esbuild app/static/js/main.js --minify --outfile=app/static/dist/main.min.js
# Bundle common modules into a single file
esbuild app/static/js/base-bundle.js --bundle --minify --outfile=app/static/dist/base.min.js
```

---

## 2. CSS Performance

### PERF-04: Wildcard Transition Rule on daily_validation.html -- Critical

**Severity**: Critical
**Estimated Impact**: Continuous layout thrashing; can cause 100ms+ jank on every DOM change

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`, lines 12-14):

```css
* {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

This rule applies a 300ms CSS transition to **every property** of **every element** on the page. When the browser changes any computed style (background, width, height, margin, padding, transform, opacity, border, color, etc.) on any element, it must run the transition engine. On a dashboard page with hundreds of DOM elements, this creates:

- Forced reflows when elements resize (e.g., tabbed content switching)
- Animation jank on scroll (any position-dependent computed styles trigger transitions)
- Compositing layer explosion (the browser may promote elements to GPU layers to satisfy transition requirements)
- Interference with the auto-refresh timer (line 1553) that does `location.reload()` every 5 minutes

The page also has a secondary auto-refresh `setInterval` that ticks every second (line 1553-1570), combining with the wildcard transition to create continuous visual noise.

**Recommendation**: Remove the wildcard rule entirely. Apply transitions only to specific interactive elements:

```css
/* Instead of * { transition: all 0.3s } */
.metric-card,
.issue-card,
.rotation-card,
.quick-action-btn {
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
```

---

### PERF-05: Bootstrap 4.6 + Font Awesome CDN Loads on Dashboard Pages -- High

**Severity**: High
**Estimated Impact**: +80-120KB extra CSS, icon font conflict with Material Symbols

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`, lines 7-9):

```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" ...>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css" ...>
```

The rest of the application uses Material Symbols (loaded in base.html) and a custom design token system. These dashboard pages add:
- Bootstrap 4.6 CSS: ~160KB (minified) -- most of which is unused
- Font Awesome 6.4 CSS: ~75KB (minified) + ~400KB WOFF2 font files

Both CDN loads are on different origins (cdnjs.cloudflare.com, cdn.jsdelivr.net), requiring additional DNS lookups and TLS handshakes.

**Affected pages**:
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html`

The Bootstrap grid classes (`col-md-4`, `row`, `mb-5`, `container-fluid`, etc.) are used alongside the custom design system, creating conflicting spacing, typography, and color systems.

**Recommendation**: Replace Bootstrap grid usage with CSS Grid (already native to the design system). Replace Font Awesome icons with the already-loaded Material Symbols. This eliminates ~235KB of CSS and 400KB of font downloads.

---

### PERF-06: Massive Inline CSS in Templates (uncacheable) -- High

**Severity**: High
**Estimated Impact**: +15-35KB of uncacheable CSS per page view

**Evidence** (inline `<style>` line counts):

| Template | Inline CSS Lines | Estimated Size |
|----------|-----------------|----------------|
| `daily_validation.html` | 1,051 | ~35KB |
| `approved_events.html` | 902 | ~30KB |
| `calendar.html` | 574 | ~19KB |
| `weekly_validation.html` | 431 | ~14KB |
| **Total** | **2,958** | **~98KB** |

This CSS is embedded in the HTML response body. Unlike external CSS files, inline styles:
- Cannot be cached by the browser
- Are re-downloaded on every page visit
- Cannot be shared across pages
- Increase the HTML document size (impacts TTFB)
- Cannot be minified or processed by build tools

**Recommendation**: Extract each page's inline CSS into corresponding files under `app/static/css/pages/`. Some pages already have this (e.g., `daily-view.css`, `index.css`, `employees.css`). The dashboard pages do not.

---

### PERF-07: Duplicate CSS Rule Definitions -- Medium

**Severity**: Medium
**Estimated Impact**: ~3KB wasted per page, minor parse overhead

**Evidence** (`/home/elliot/flask-schedule-webapp/app/static/css/style.css`):

Multiple CSS rules are defined twice in the same file. For example:
- `.event-type-badge` is defined at line 865 and again at line 1254 with different values
- `.event-type-core` is defined at line 876 (gradient) and line 1266 (flat color)
- `.alert` is defined at line 921 and again at line 1166
- `.flash-messages` is defined at line 917 and again at line 1162

The later definitions override the earlier ones, making the first set dead code. This is a maintenance hazard and wastes parse time.

**Recommendation**: Audit `style.css` for duplicate selectors and consolidate. Use a CSS linting tool:

```bash
npx stylelint "app/static/css/**/*.css" --config '{"rules":{"no-duplicate-selectors":true}}'
```

---

### PERF-08: `will-change` Applied Permanently (GPU Memory) -- Low

**Severity**: Low
**Estimated Impact**: Elevated GPU memory usage

**Evidence** (`/home/elliot/flask-schedule-webapp/app/static/css/style.css`, lines 1881-1883):

```css
.stat-card,
.event-card {
  will-change: box-shadow, border-color;
}
```

`will-change` is intended as a temporary hint before an animation. Applying it permanently forces the browser to maintain compositing layers, consuming GPU memory for every `.stat-card` and `.event-card` on the page, even when idle.

**Recommendation**: Apply `will-change` only on hover/before animation:

```css
.stat-card:hover,
.event-card:hover {
  will-change: box-shadow, border-color;
}
```

---

## 3. JavaScript Performance

### PERF-09: 45 `location.reload()` Calls as Primary State Update -- Critical

**Severity**: Critical
**Estimated Impact**: +2-5 seconds of delay per user action; loss of scroll position, form state, and selected filters

**Evidence** (grep across all JS and template files):

| Location | Count |
|----------|-------|
| Template inline scripts | 26 |
| External JS files | 19 |
| **Total** | **45** |

**Files with the most reload calls**:
- `weekly_validation.html`: 7 reloads
- `calendar.html`: 4 reloads
- `index.html`: 3 reloads
- `daily-view.js`: 2 reloads
- `inventory/order_detail.html`: 5 reloads

After every CRUD operation (reschedule, unschedule, change employee, approve, reject), the application does `location.reload()`. This:
1. Discards the entire DOM and re-parses the HTML
2. Re-downloads and re-parses all CSS (114KB base + page CSS)
3. Re-downloads and re-parses all JavaScript (633KB total)
4. Re-executes all initialization code
5. Re-makes all API calls (4+ for daily-view)
6. Loses scroll position, filter selections, modal state, and input values
7. Shows a blank white screen during reload (Flash of Unstyled Content)

The application already has a state manager (`state-manager.js`, 16KB) and toast notification system, but they are not being used for CRUD result handling.

**Recommendation**: Replace `location.reload()` with targeted DOM updates:

```javascript
// Instead of: location.reload()
// After successful API call:
async function onRescheduleSuccess(data) {
    closeModal('reschedule-modal');
    window.toaster.success(data.message);
    await dailyView.loadDailyEvents();    // Refresh just the events
    await dailyView.loadDailySummary();   // Refresh just the summary
}
```

---

### PERF-10: 1,420 Lines of Uncacheable Inline JS on index.html -- High

**Severity**: High
**Estimated Impact**: ~50KB of uncacheable JavaScript per dashboard visit

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/index.html`):

The main dashboard page contains 1,420 lines of inline JavaScript in its `{% block scripts %}`. This includes:
- Event detail modal management (showEventDetails, closeEventDetails)
- Reschedule workflow (openRescheduleModal, setupTimeRestrictions)
- Change employee workflow (openChangeEmployeeModal, loadAvailableEmployeesForChange)
- Print functions (printEDR, printInstructions, printBoth, printScheduleByDate, printPaperworkByDate)
- Form submission handlers
- Verification widget logic
- Schedule Now modal logic

**Inline script counts across major templates**:

| Template | Inline JS Lines | Estimated Size |
|----------|----------------|----------------|
| `index.html` | 1,420 | ~50KB |
| `calendar.html` | 1,112 | ~38KB |
| `approved_events.html` | 986 | ~34KB |
| `auto_schedule_review.html` | 946 | ~32KB |
| `weekly_validation.html` | 750 | ~25KB |
| `daily_validation.html` | 266 | ~9KB |
| **Total** | **5,480** | **~188KB** |

This code is re-downloaded with every page view and cannot be cached by the browser.

**Recommendation**: Extract inline scripts to external files. Most of this code has no Jinja2 template dependencies and can be moved directly:

```
app/static/js/pages/index-dashboard.js     <- from index.html
app/static/js/pages/calendar-page.js       <- from calendar.html
app/static/js/pages/approved-events.js     <- from approved_events.html
```

For the small amount of Jinja2-dependent data, use data attributes:

```html
<div id="dashboard-config"
     data-today="{{ today.strftime('%Y-%m-%d') }}"
     data-csrf-token="{{ csrf_token() }}">
</div>
```

---

### PERF-11: daily-view.js Monolith (160KB, 3,950+ lines) -- High

**Severity**: High
**Estimated Impact**: +500ms parse time on mobile devices; high memory baseline

**Evidence** (`/home/elliot/flask-schedule-webapp/app/static/js/pages/daily-view.js`): 160KB, containing:

- `DailyView` class with 40+ methods
- 37 `innerHTML` assignments (full DOM replacement)
- 20 `fetch()` calls to different API endpoints
- 60 `addEventListener` calls with only 4 `removeEventListener` calls
- Template literal HTML generation with string concatenation

The `innerHTML` pattern is especially concerning:

```javascript
this.timeslotContainer.innerHTML = html;  // Replaces entire container
this.summaryContainer.innerHTML = html;    // Replaces entire container
this.eventsContainer.innerHTML = html;     // Replaces entire container
this.attendanceContainer.innerHTML = html; // Replaces entire container
```

Each `innerHTML` assignment destroys and recreates all child elements, their event listeners, and browser-maintained state. With 37 such assignments, the page frequently discards and rebuilds large DOM subtrees.

**Memory leak risk**: 60 `addEventListener` calls vs 4 `removeEventListener` calls. Event handlers added to dynamically-created elements (via innerHTML) will be orphaned when the elements are replaced, though the garbage collector can reclaim them if there are no external references. However, handlers attached to persistent elements (document, window) without cleanup are a clear leak vector.

**Recommendation**: Split into focused modules:

```
daily-view-summary.js      (renderEventTypeSummary, renderTimeslotCoverage)
daily-view-events.js        (loadDailyEvents, renderEventCards, filterAndRenderEvents)
daily-view-attendance.js    (loadAttendance, renderAttendanceList)
daily-view-modals.js        (reschedule, change-employee, trade, reissue)
daily-view-lock.js          (checkLockStatus, toggleLock)
```

Use event delegation instead of per-element handlers:

```javascript
// Instead of: adding click handlers to each card after innerHTML
this.eventsContainer.addEventListener('click', (e) => {
    const card = e.target.closest('.event-card');
    if (card) this.handleCardClick(card);
});
```

---

### PERF-12: Aggressive Keyboard Shortcut Hijacking on daily_validation.html -- Medium

**Severity**: Medium
**Estimated Impact**: Usability issue; interferes with browser shortcuts and accessibility tools

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`, lines 1582-1601):

```javascript
document.addEventListener('keydown', function(e) {
    if (e.key === 'r' || e.key === 'R') {
        if (!e.ctrlKey && !e.metaKey) {
            location.reload();
        }
    }
    if (e.key === '1') {
        window.location.href = '/calendar?date=...';
    }
    if (e.key === '2') {
        window.location.href = '/schedule/daily/...';
    }
});
```

Pressing any of these keys -- even while typing in a form field, search box, or the date picker on the same page -- will trigger navigation or a full reload. The handler does not check if the target is an input field.

**Recommendation**: Add target checks:

```javascript
document.addEventListener('keydown', function(e) {
    if (e.target.matches('input, textarea, select, [contenteditable]')) return;
    // ...shortcut logic
});
```

---

### PERF-13: Auto-Refresh Timer Ticking Every Second -- Medium

**Severity**: Medium
**Estimated Impact**: ~12,000 unnecessary function calls over 5 minutes; wastes CPU on mobile

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`, lines 1550-1570):

```javascript
let refreshCountdown = 5 * 60;  // 300 seconds
const refreshTimer = setInterval(() => {
    refreshCountdown--;
    if (refreshCountdown === 30) {
        // Update button text
    }
    if (refreshCountdown <= 0) {
        clearInterval(refreshTimer);
        location.reload();
    }
}, 1000);  // Every 1 second
```

This interval fires every second for 5 minutes (300 invocations), but only takes action at two points: t=270s (show warning) and t=300s (reload). The remaining 298 invocations are wasted.

Additionally, `base.html` already has its own session activity tracker with heartbeats every 2 minutes and status checks every 30 seconds (lines 434-589). These two independent polling systems compound network and CPU overhead.

**Recommendation**: Use `setTimeout` instead of `setInterval`:

```javascript
setTimeout(() => {
    // Show warning
    refreshBtn.textContent = 'Refreshing in 30s...';
    setTimeout(() => location.reload(), 30000);
}, 270000);  // 4.5 minutes
```

---

### PERF-14: Session Activity Tracker Registers 6 Event Listeners on Document -- Low

**Severity**: Low
**Estimated Impact**: Minor; passive listeners are efficient but add up

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/base.html`, lines 447-457):

```javascript
const activityEvents = ['mousemove', 'mousedown', 'keypress', 'scroll', 'touchstart', 'click'];
activityEvents.forEach(event => {
    document.addEventListener(event, () => {
        lastActivity = Date.now();
        if (warningShown) {
            hideTimeoutWarning();
            sendHeartbeat();
        }
    }, { passive: true });
});
```

Six event listeners on the document, firing on every mouse move, scroll, and click. Although marked `{ passive: true }`, the `mousemove` listener in particular fires at very high frequency (60+ times/second during mouse movement). Each invocation calls `Date.now()` and checks `warningShown`.

**Recommendation**: Throttle the activity handler:

```javascript
let lastTracked = 0;
function trackActivity() {
    const now = Date.now();
    if (now - lastTracked < 5000) return;  // At most once per 5 seconds
    lastTracked = now;
    lastActivity = now;
}
```

---

## 4. Image & Font Loading

### PERF-15: Render-Blocking Font Loading (2 CDN requests, no preload for icons) -- High

**Severity**: High
**Estimated Impact**: +200-500ms to FCP; Flash of Invisible Text (FOIT)

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/base.html`, lines 17-21):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
```

Two separate Google Fonts requests, each requiring:
1. DNS lookup for fonts.googleapis.com
2. Download CSS file (contains @font-face declarations)
3. Download actual font files from fonts.gstatic.com

The Outfit font uses `display=swap` (good -- shows fallback text immediately). However, the Material Symbols font does **not** have `display=swap`, meaning icons will be invisible until the font loads (FOIT).

The Material Symbols request also uses a very wide axis range (`opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200`), which can result in a larger font file than necessary.

**Recommendation**:
1. Add `display=swap` to Material Symbols
2. Self-host both fonts to eliminate 2 DNS lookups and 2 origin roundtrips
3. Narrow the Material Symbols axis range to only what's used

```html
<!-- Add display=swap -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL@24,400,0&display=swap" />
```

---

### PERF-16: Large Logo Image Without Optimization -- Low

**Severity**: Low
**Estimated Impact**: +29KB on every page load

**Evidence** (`/home/elliot/flask-schedule-webapp/app/static/img/PC-Logo_Primary_Full-Color-1024x251.png`): 29KB PNG displayed at `height: 50px`.

The image is 1024x251 pixels but displayed at approximately 205x50 pixels (4x oversampled). While this provides crisp rendering on 2x displays, a 512x126 PNG would suffice and be ~8KB.

**Recommendation**: Create optimized variants:

```html
<img src="...img/PC-Logo-512.webp"
     srcset="...img/PC-Logo-512.webp 1x, ...img/PC-Logo-1024.webp 2x"
     alt="Product Connections"
     width="205" height="50"
     loading="eager">
```

---

## 5. Caching Strategy

### PERF-17: No Cache Busting on Static Assets -- High

**Severity**: High
**Estimated Impact**: Users may see stale CSS/JS after deployments; or cache is effectively disabled

**Evidence**: All asset URLs use Flask's `url_for('static', ...)` which generates paths like `/static/css/style.css` with no query string or hash-based versioning.

Without cache-busting:
- If `Cache-Control` is set to long TTL: Users get stale assets after deployment
- If `Cache-Control` is short/none: Assets are re-downloaded on every visit (633KB JS + 299KB CSS)

There is no evidence of a static asset build pipeline, no content hashing, and no Flask extension like `Flask-Assets` or `Whitenoise` configured.

**Recommendation**: Implement cache busting via query string versioning:

```python
# In Flask config or template context
import hashlib, os

def versioned_static(filename):
    filepath = os.path.join(app.static_folder, filename)
    mtime = os.path.getmtime(filepath)
    return url_for('static', filename=filename, v=int(mtime))
```

Or use `Flask-Assets` / `webassets` for automatic bundling and hashing.

---

### PERF-18: CacheManager Exists But Is Not Used by API Calls -- Medium

**Severity**: Medium
**Estimated Impact**: Duplicate API calls for identical data

**Evidence** (`/home/elliot/flask-schedule-webapp/app/static/js/utils/cache-manager.js`):

A well-designed `CacheManager` class exists with TTL support, but it is never imported or used by any page script. The `api-client.js` makes no mention of caching. Every `fetch()` call hits the server fresh.

For example, the daily-view page makes 4 parallel API calls on load (`/api/daily-summary`, `/api/attendance/scheduled-employees`, `/api/daily-events`, `/api/locked-days`). If the user navigates away and returns, all 4 calls are repeated.

**Recommendation**: Integrate the cache manager with the API client:

```javascript
class ApiClient {
    constructor() {
        this.cache = new CacheManager(60000);  // 1-minute TTL
    }

    async get(url, options = {}) {
        if (!options.skipCache) {
            const cached = this.cache.get(url);
            if (cached) return cached;
        }
        const data = await this.request(url, { method: 'GET' });
        this.cache.set(url, data);
        return data;
    }
}
```

---

## 6. Network Requests & API Patterns

### PERF-19: Waterfall API Calls on index.html (Server-Rendered + Client Fetch) -- Medium

**Severity**: Medium
**Estimated Impact**: Redundant data fetching; server renders data that JS re-fetches

The main dashboard (`index.html`) is an interesting hybrid: the server pre-renders core events, scheduling progress, and statistics into the HTML via Jinja2, but then the `{% block scripts %}` section also contains verification widget logic that makes additional API calls.

The daily-view page (`daily-view.js`) takes the better approach: parallel `Promise.all()` for its 4 initial API calls (line 40-45). This is a good pattern to replicate elsewhere.

**Recommendation**: For server-rendered pages, embed initial data as JSON in a `<script>` tag to avoid redundant API calls:

```html
<script>
    window.__INITIAL_DATA__ = {{ initial_data | tojson }};
</script>
```

---

### PERF-20: 20 Different API Endpoints Called From daily-view.js -- Medium

**Severity**: Medium
**Estimated Impact**: High network overhead on complex interactions

**Evidence**: `daily-view.js` contains `fetch()` calls to 20 distinct API endpoints. While not all are called at once, user interactions like rescheduling trigger sequential calls:

1. Fetch schedule details
2. Fetch active employees
3. Post reschedule
4. Reload daily events
5. Reload daily summary

Each call is a separate HTTP roundtrip. On mobile networks with 200ms+ latency, a 5-call sequence takes >1 second of network time alone.

**Recommendation**: Create a batch API endpoint for common multi-resource operations:

```python
@api_bp.route('/api/batch', methods=['POST'])
def batch_request():
    # Accept multiple API calls in a single request
    requests = request.json.get('requests', [])
    results = {}
    for req in requests:
        results[req['id']] = dispatch_internal(req['method'], req['url'], req.get('body'))
    return jsonify(results)
```

---

### PERF-21: Session Heartbeat + Auth Check Double-Polling -- Low

**Severity**: Low
**Estimated Impact**: 1 extra API call every 30 seconds (unnecessary network traffic)

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/base.html`, lines 573-582):

```javascript
// Heartbeat every 2 minutes
setInterval(() => {
    if (timeSinceActivity < HEARTBEAT_INTERVAL) {
        sendHeartbeat();  // POST /api/session/heartbeat
    }
}, HEARTBEAT_INTERVAL);

// Status check every 30 seconds
setInterval(checkSessionStatus, CHECK_INTERVAL);  // GET /api/auth/status
```

Two independent polling loops: one POST every 2 minutes, one GET every 30 seconds. These could be consolidated into a single check.

**Recommendation**: Combine into one polling mechanism:

```javascript
setInterval(async () => {
    if (Date.now() - lastActivity < 120000) {
        const data = await fetch('/api/session/heartbeat', { method: 'POST' }).then(r => r.json());
        // heartbeat response includes session status
        handleSessionStatus(data);
    }
}, 60000);  // Once per minute
```

---

## 7. DOM Complexity & Template Size

### PERF-22: Extremely Large Template Files with Mixed Concerns -- High

**Severity**: High
**Estimated Impact**: Slow server-side rendering; large HTML documents; difficult maintenance

**Evidence** (template sizes):

| Template | Lines | Size | Inline CSS Lines | Inline JS Lines |
|----------|-------|------|------------------|-----------------|
| `approved_events.html` | 2,155 | 73KB | 902 | 986 |
| `index.html` | 1,870 | ~65KB | 0* | 1,420 |
| `calendar.html` | 1,858 | 73KB | 574 | 1,112 |
| `weekly_validation.html` | 1,733 | 68KB | 431 | 750 |
| `daily_validation.html` | 1,731 | ~60KB | 1,051 | 266 |
| `auto_schedule_review.html` | 1,212 | ~45KB | 0** | 946 |

*index.html CSS was already extracted to `css/pages/index.css`
**auto_schedule_review.html CSS was already extracted

These templates generate HTML documents of 60-73KB each. With base.html overhead (header, footer, nav, modals = ~11KB), the total HTML payload for a dashboard page is approximately 70-85KB before any CSS/JS.

For comparison, a typical well-optimized web application targets <30KB HTML for the initial document.

**Recommendation**: Decompose large templates into Jinja2 includes:

```jinja2
{# Instead of 2,155 lines in one file #}
{% block content %}
    {% include 'dashboard/partials/_header.html' %}
    {% include 'dashboard/partials/_metrics.html' %}
    {% include 'dashboard/partials/_event_list.html' %}
    {% include 'dashboard/partials/_modals.html' %}
{% endblock %}
```

---

### PERF-23: Modal HTML Pre-Rendered on Every Page -- Medium

**Severity**: Medium
**Estimated Impact**: +5-10KB of DOM nodes rendered but hidden on every page

**Evidence** (`/home/elliot/flask-schedule-webapp/app/templates/base.html`, lines 228-431):

Every page load includes:
- Database Refresh Modal (lines 228-255)
- Event Times Warning Modal (lines 258-285)
- Session Timeout Warning Modal (lines 407-431)
- AI Assistant Panel (line 402, included via `{% include %}`)
- Floating Verification Widget (line 405, included via `{% include %}`)
- Quick Note Widget (line 598, included via `{% include %}`)

These modals are hidden by default but are parsed and added to the DOM on every page, increasing DOM node count and memory usage. On pages like the print view or help pages, they serve no purpose.

**Recommendation**: Lazy-load modal HTML only when needed:

```javascript
async function showRefreshModal() {
    if (!document.getElementById('refreshDatabaseModal')) {
        const html = await fetch('/partials/refresh-modal').then(r => r.text());
        document.body.insertAdjacentHTML('beforeend', html);
    }
    document.getElementById('refreshDatabaseModal').classList.add('modal-open');
}
```

---

## 8. Summary Table

| ID | Finding | Severity | Category | Est. Impact |
|----|---------|----------|----------|-------------|
| PERF-01 | 8+ render-blocking CSS files, no bundling | Critical | Asset Loading | +400-800ms FCP |
| PERF-02 | ES module/global script race condition | Critical | Asset Loading | Silent failures |
| PERF-03 | 37 unminified JS files, 633KB total | High | Asset Loading | +1-3s TTI |
| PERF-04 | `* { transition: all 0.3s }` wildcard rule | Critical | CSS | 100ms+ jank per DOM change |
| PERF-05 | Bootstrap + Font Awesome CDN on dashboards | High | CSS | +235KB CSS, +400KB fonts |
| PERF-06 | 2,958 lines inline CSS (uncacheable) | High | CSS | +98KB uncacheable |
| PERF-07 | Duplicate CSS rule definitions in style.css | Medium | CSS | ~3KB waste |
| PERF-08 | Permanent `will-change` on cards | Low | CSS | Elevated GPU memory |
| PERF-09 | 45 `location.reload()` calls | Critical | JavaScript | +2-5s per action |
| PERF-10 | 5,480 lines inline JS (uncacheable) | High | JavaScript | +188KB uncacheable |
| PERF-11 | daily-view.js monolith (160KB) | High | JavaScript | +500ms parse on mobile |
| PERF-12 | Keyboard shortcuts hijack input fields | Medium | JavaScript | Usability issue |
| PERF-13 | Auto-refresh setInterval every 1 second | Medium | JavaScript | 300 wasted calls/5min |
| PERF-14 | Session tracker 6 document listeners | Low | JavaScript | Minor overhead |
| PERF-15 | Render-blocking fonts, no `display=swap` on icons | High | Fonts | +200-500ms FCP |
| PERF-16 | Oversized logo PNG (29KB at 4x) | Low | Images | +20KB saveable |
| PERF-17 | No cache busting on static assets | High | Caching | Stale assets or no cache |
| PERF-18 | CacheManager built but unused | Medium | Caching | Duplicate API calls |
| PERF-19 | Server-render + client-fetch redundancy | Medium | Network | Extra roundtrips |
| PERF-20 | 20 API endpoints from one page | Medium | Network | High interaction latency |
| PERF-21 | Session heartbeat + auth status double-poll | Low | Network | 1 extra call/30s |
| PERF-22 | Templates exceeding 2,000 lines | High | DOM | Large HTML payloads |
| PERF-23 | Hidden modals pre-rendered on every page | Medium | DOM | +5-10KB DOM waste |

---

## Priority Optimization Roadmap

### Phase 1: Quick Wins (1-2 days, highest ROI)

1. **Remove `* { transition: all 0.3s }` from daily_validation.html** (PERF-04)
   - 5-minute fix, eliminates continuous layout thrashing
2. **Add `display=swap` to Material Symbols** (PERF-15)
   - 1-minute fix in base.html line 21
3. **Remove Bootstrap/Font Awesome from dashboard pages** (PERF-05)
   - Replace ~20 Bootstrap classes with native CSS Grid
   - Replace ~15 Font Awesome icons with Material Symbols (already loaded)
4. **Fix keyboard shortcut input-field interference** (PERF-12)
   - Add `if (e.target.matches('input, textarea, select')) return;`

### Phase 2: Extract Inline Code (3-5 days)

5. **Extract inline CSS from 4 dashboard templates** (PERF-06)
   - Create `daily-validation.css`, `approved-events.css`, `weekly-validation.css`, `calendar-page.css`
6. **Extract inline JS from 6 templates** (PERF-10)
   - Create corresponding page JS files
   - Use `data-*` attributes for Jinja2 template values

### Phase 3: Build Pipeline (3-5 days)

7. **Implement CSS/JS bundling and minification** (PERF-01, PERF-03)
   - Use esbuild or a simple shell script
   - Expected savings: ~40% file size reduction
8. **Add cache busting** (PERF-17)
   - Content-hash query parameters on asset URLs
9. **Self-host fonts** (PERF-15)
   - Download Outfit and Material Symbols WOFF2 files

### Phase 4: Architecture Improvements (1-2 weeks)

10. **Replace `location.reload()` with targeted DOM updates** (PERF-09)
    - Start with highest-traffic pages (daily-view, index)
    - Wire up existing state manager and toast notifications
11. **Split daily-view.js into focused modules** (PERF-11)
12. **Fix ES module/global script race condition** (PERF-02)
    - Convert all base.html scripts to modules, or implement promise-based readiness
13. **Integrate CacheManager with API client** (PERF-18)
14. **Consolidate session polling** (PERF-21)
