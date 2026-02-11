# Component Patterns: Use This, Not That

Canonical component patterns for the Flask Schedule Webapp frontend. When building new features, use these shared components instead of rolling your own.

All canonical modules are loaded in `app/templates/base.html` and exposed as globals on `window`. You can use them from ES6 modules via `import` or from non-module scripts via `window.*`.

---

## Table of Contents

1. [CSRF Token Handling](#csrf-token-handling)
2. [API Client](#api-client)
3. [Modal](#modal)
4. [Toast Notifications](#toast-notifications)
5. [Focus Trap](#focus-trap)
6. [ARIA Announcer](#aria-announcer)
7. [Time Formatting](#time-formatting)
8. [HTML Escaping](#html-escaping)

---

## CSRF Token Handling

**Canonical source:** `app/static/js/csrf_helper.js`

Loaded as a regular (non-module) script in `base.html`. It automatically intercepts all state-changing requests (POST, PUT, DELETE, PATCH) across jQuery AJAX, `fetch`, and `XMLHttpRequest`, injecting the `X-CSRF-Token` header from the `csrf_token` cookie.

### How to use

In most cases, you do not need to do anything. CSRF protection is automatic for all AJAX requests. If you need the token value manually:

```javascript
// Global function exposed by csrf_helper.js
const token = window.getCsrfToken();
```

The canonical header name is `X-CSRF-Token` (with hyphen). Flask-WTF accepts both `X-CSRFToken` and `X-CSRF-Token`.

### Anti-patterns

```javascript
// WRONG: Manually reading the token and setting headers on every fetch call
fetch('/api/events', {
    method: 'POST',
    headers: { 'X-CSRF-Token': getTokenFromSomewhere() },
    body: JSON.stringify(data)
});

// WRONG: Reading from a meta tag when csrf_helper.js handles it automatically
const token = document.querySelector('meta[name="csrf-token"]').content;

// WRONG: Using the wrong header name
xhr.setRequestHeader('X-CSRFToken', token);  // Use X-CSRF-Token instead
```

### When to use

- **Always.** It is loaded globally on every page via `base.html`. You do not need to include it yourself.
- If you need the raw token value (e.g., for a hidden form field in a dynamically created form), use `window.getCsrfToken()`. The helper also auto-injects hidden `csrf_token` fields into forms via a MutationObserver.

---

## API Client

**Canonical source:** `app/static/js/utils/api-client.js`

Standardized HTTP client with built-in CSRF handling, 10-second timeout, automatic retry (1 retry on timeout/network error), and user-friendly error messages.

### How to use

```javascript
// ES6 module import
import { apiClient } from '../utils/api-client.js';

// Or use the global (set in base.html)
// window.apiClient

// GET request
const data = await apiClient.get('/api/events');

// POST request
const result = await apiClient.post('/api/schedules', {
    event_id: 42,
    employee_id: 7,
    scheduled_date: '2026-02-10'
});

// PUT request
await apiClient.put('/api/events/42', { name: 'Updated Event' });

// DELETE request
await apiClient.delete('/api/schedules/99');
```

Error handling:

```javascript
try {
    const data = await apiClient.post('/api/schedules', payload);
    toaster.success('Schedule saved');
} catch (error) {
    // error.message contains a user-friendly string
    // error.code is 'TIMEOUT' or 'NETWORK_ERROR' for those cases
    toaster.error(error.message);
}
```

### Anti-patterns

```javascript
// WRONG: Raw fetch without timeout, retry, or CSRF
const response = await fetch('/api/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
});

// WRONG: jQuery $.ajax for API calls
$.ajax({ url: '/api/events', type: 'POST', data: JSON.stringify(payload) });

// WRONG: Building your own retry/timeout logic
function fetchWithRetry(url, retries = 3) { /* ... */ }

// WRONG: Not handling errors, letting them silently fail
apiClient.post('/api/events', data);  // Missing await and try/catch
```

### When to use

- **All API calls** to backend endpoints. The client handles Content-Type, CSRF tokens, timeouts, retries, and error normalization.
- For custom timeout or retry values, instantiate a new `ApiClient`: `new ApiClient('', 30000, 3, 2000)`.

---

## Modal

**Canonical source:** `app/static/js/components/modal.js`

Reusable modal dialog with built-in focus trapping (via `FocusTrap`), Escape-to-close, overlay-click-to-close, body scroll lock, and ARIA attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`).

### How to use

```javascript
import { Modal, createModal } from '../components/modal.js';

// Option 1: Instance with lifecycle control
const modal = new Modal({ id: 'my-modal' });

modal.open('<p>Are you sure you want to delete this schedule?</p>', {
    title: 'Confirm Deletion',
    size: 'small',          // 'small' | 'medium' | 'large'
    closeButton: true,
    onClose: () => console.log('Modal closed')
});

// Later...
modal.close();

// Option 2: One-shot convenience function
const modal = createModal('<p>Quick message</p>', {
    title: 'Notice',
    size: 'medium'
});
```

Listening for modal events:

```javascript
document.addEventListener('modal-opened', (e) => {
    console.log('Modal opened:', e.detail.id);
});

document.addEventListener('modal-closed', (e) => {
    console.log('Modal closed:', e.detail.id);
});
```

### Anti-patterns

```javascript
// WRONG: Building modal HTML by hand without focus trapping
const overlay = document.createElement('div');
overlay.innerHTML = '<div class="my-modal">...</div>';
document.body.appendChild(overlay);

// WRONG: Using Bootstrap's $.modal() or any jQuery modal plugin
$('#myModal').modal('show');

// WRONG: Forgetting to close/destroy, causing memory leaks
const modal = new Modal();
modal.open(content);
// Never calling modal.close() or modal.destroy()

// WRONG: Not setting a title (breaks aria-labelledby)
modal.open(content, { closeButton: true }); // Add title for screen readers
```

### When to use

- **Any dialog, confirmation prompt, or overlay** that requires user attention.
- The Modal component automatically integrates `FocusTrap`, so you do not need to set up focus trapping separately when using it.

---

## Toast Notifications

**Canonical source:** `app/static/js/modules/toast-notifications.js`

Non-intrusive notification system with four severity levels, auto-dismiss with progress bar, pause-on-hover, screen reader announcements (via `AriaAnnouncer`), and max-toast limiting.

### How to use

```javascript
// ES6 module import (singleton)
import { toaster } from '../modules/toast-notifications.js';

// Or use the global (set in base.html)
// window.toaster

// Basic usage
toaster.success('Schedule saved successfully');
toaster.error('Failed to save schedule');
toaster.warning('Employee has conflicting availability');
toaster.info('5 new schedules pending approval');

// With options
toaster.show('Custom notification', {
    type: 'success',
    duration: 3000,        // ms, 0 = no auto-dismiss (default: 5000)
    dismissible: true,
    onClick: () => window.location.href = '/dashboard',
    onClose: () => console.log('Toast dismissed')
});

// Update an existing toast (e.g., saving -> saved)
const id = toaster.info('Saving...');
// After save completes:
toaster.update(id, { type: 'success', message: 'Saved successfully' });

// Dismiss programmatically
toaster.dismiss(id);
toaster.dismissAll();
```

### Anti-patterns

```javascript
// WRONG: alert() for user feedback
alert('Schedule saved!');

// WRONG: Custom notification divs with manual show/hide
const msg = document.createElement('div');
msg.textContent = 'Saved';
msg.className = 'success-msg';
document.body.appendChild(msg);
setTimeout(() => msg.remove(), 3000);

// WRONG: Creating a new ToastManager instead of using the singleton
const myToaster = new ToastManager();  // Use the exported `toaster` singleton

// WRONG: Using console.log for user-facing feedback
console.log('Operation completed');  // User cannot see this
```

### When to use

- **All user feedback** for operations: save/delete confirmations, error messages, warnings, and informational notices.
- The `toaster` singleton is the standard. Do not create additional `ToastManager` instances unless you need a separate container with different positioning.

---

## Focus Trap

**Canonical source:** `app/static/js/utils/focus-trap.js`

Traps keyboard focus within a container element (modals, dropdowns, side panels) for WCAG 2.1 AA compliance. Handles Tab/Shift+Tab cycling, Escape key callbacks, and focus restoration on deactivate.

### How to use

```javascript
import { FocusTrap, createFocusTrap } from '../utils/focus-trap.js';

// Or use the global (set in base.html)
// window.FocusTrap, window.createFocusTrap

const trap = new FocusTrap(panelElement, {
    onEscape: () => closePanel(),
    returnFocusOnDeactivate: true,   // default: true
    initialFocus: panelElement.querySelector('.first-input')
});

trap.activate();

// If panel content changes dynamically:
trap.updateFocusableElements();

// For nested overlays:
trap.pause();   // Temporarily stop trapping
trap.resume();  // Re-enable trapping

// When done:
trap.deactivate();  // Removes listeners, restores focus to previous element
```

### Anti-patterns

```javascript
// WRONG: Manual keydown listener for focus trapping
document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') { /* manual focus cycling */ }
});

// WRONG: Not trapping focus in modals/overlays at all
// (Keyboard users can tab behind the modal into page content)

// WRONG: Using FocusTrap inside a Modal component
// Modal already integrates FocusTrap internally - do not add another one

// WRONG: Forgetting to deactivate, causing "stuck" focus trapping
const trap = new FocusTrap(element);
trap.activate();
// Element removed from DOM but trap never deactivated
```

### When to use

- **Custom overlays, side panels, dropdowns** that are not using the `Modal` component.
- Do NOT use directly with `Modal` -- it is already built in.

---

## ARIA Announcer

**Canonical source:** `app/static/js/modules/aria-announcer.js`

Screen reader announcement system using ARIA live regions. Provides polite (non-urgent) and assertive (interrupt) announcements with debouncing to prevent overwhelming assistive technology.

### How to use

```javascript
// ES6 module import (singleton)
import { ariaAnnouncer } from '../modules/aria-announcer.js';

// Or use the global (set in base.html)
// window.ariaAnnouncer

// Basic announcements
ariaAnnouncer.announce('Schedule updated');                      // polite (default)
ariaAnnouncer.announce('Critical error occurred', 'assertive');  // interrupts

// Convenience methods
ariaAnnouncer.announceSuccess('Employee added');
ariaAnnouncer.announceError('Failed to load data');
ariaAnnouncer.announceWarning('Unsaved changes detected');
ariaAnnouncer.announceInfo('3 events loaded');

// Validation feedback
ariaAnnouncer.announceValidation(true, 'All schedules valid');
ariaAnnouncer.announceValidation(false, 'Missing required field');

// Loading states
ariaAnnouncer.announceLoading('Schedules');       // "Schedules, please wait..."
ariaAnnouncer.announceLoadingComplete('Schedules'); // "Schedules loaded successfully"

// Clear pending announcements
ariaAnnouncer.clear();
```

### Anti-patterns

```javascript
// WRONG: Creating your own aria-live region
const liveRegion = document.createElement('div');
liveRegion.setAttribute('aria-live', 'polite');
document.body.appendChild(liveRegion);
liveRegion.textContent = 'Updated';

// WRONG: Using alert role for non-critical messages
element.setAttribute('role', 'alert');  // Use ariaAnnouncer.announce() instead

// WRONG: Not announcing dynamic content changes to screen readers
// (Content appears visually but screen reader users are unaware)

// WRONG: Creating a new AriaAnnouncer instance
const myAnnouncer = new AriaAnnouncer();  // Use the exported singleton
```

### When to use

- **Every dynamic content update** that screen reader users need to know about: form validation results, data loading states, action confirmations, error messages.
- The `toaster` already calls `ariaAnnouncer.announce()` internally, so you do not need to announce separately when using toast notifications.
- Use `'assertive'` priority only for errors and urgent warnings. Use `'polite'` for everything else.

---

## Time Formatting

**Canonical source:** `app/static/js/utils/format-time.js`

Converts 24-hour time strings (from the database/API) to 12-hour display format.

### How to use

```javascript
// ES6 module import
import { formatTime } from '../utils/format-time.js';

// Or use the global (set in base.html)
// window.formatTime

formatTime('14:30');  // "2:30 PM"
formatTime('00:00');  // "12:00 AM"
formatTime('12:00');  // "12:00 PM"
formatTime('09:15');  // "9:15 AM"
```

### Anti-patterns

```javascript
// WRONG: Inline time formatting logic
const hour = parseInt(time.split(':')[0]);
const ampm = hour >= 12 ? 'PM' : 'AM';
const display = `${hour > 12 ? hour - 12 : hour}:${time.split(':')[1]} ${ampm}`;

// WRONG: Using Date object just to format a time string
const d = new Date(`2026-01-01T${time}`);
const formatted = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

// WRONG: Displaying raw 24-hour time to users
cell.textContent = schedule.scheduled_time;  // Shows "14:30" instead of "2:30 PM"
```

### When to use

- **Every time you display a time value** from the API/database to the user. The backend stores times in 24-hour format; the frontend should always display 12-hour format.

---

## HTML Escaping

**Canonical pattern:** `escapeHtml()` function (duplicated across many files -- no single canonical source yet)

Prevents XSS when inserting user-provided or API-provided text into HTML via `innerHTML` or template literals.

### The two implementations in use

**Regex-based** (used in `main.js`, `index-page.js`, `workload-dashboard.js`, and most standalone scripts):

```javascript
function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
```

**DOM-based** (used in `daily-validation.js`, `schedule-modal.js`, `notification-modal.js`, `change-employee-modal.js`, and some templates):

```javascript
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

Both are safe. The regex version is used more widely; the DOM version is used in newer component classes as a private method (`this._escapeHtml()`).

### How to use

When building HTML strings with dynamic data, always escape:

```javascript
// CORRECT: Escape before inserting into innerHTML
element.innerHTML = `<span>${escapeHtml(userName)}</span>`;

// CORRECT: In a class, use a private method
class MyComponent {
    _escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    render() {
        return `<div>${this._escapeHtml(this.data.name)}</div>`;
    }
}
```

When you do NOT need escaping:

```javascript
// textContent is inherently safe -- no escaping needed
element.textContent = userName;
```

### Anti-patterns

```javascript
// WRONG: Inserting unescaped user data into innerHTML (XSS vulnerability)
element.innerHTML = `<span>${userName}</span>`;
row.innerHTML = `<td>${event.name}</td><td>${event.location}</td>`;

// WRONG: Using .html() with unescaped data (jQuery XSS vulnerability)
$('#name').html(response.name);

// WRONG: Relying on the data being "safe" because it came from the API
// API data can contain <script> tags or HTML entities from user input
```

### When to use

- **Every time** you set `innerHTML`, build HTML template literals, or use jQuery `.html()` with any data that is not a hardcoded string literal.
- Prefer `textContent` over `innerHTML` when you do not need HTML markup. It is faster and inherently safe.
- Currently there is no shared importable module for `escapeHtml`. Each file defines its own copy. In ES6 module classes, use a private `_escapeHtml()` method. In non-module scripts, define a local `escapeHtml()` function using the regex pattern above.

---

## Quick Reference

| Need | Use This | Not That |
|------|----------|----------|
| API calls | `apiClient.get/post/put/delete()` | Raw `fetch()`, `$.ajax()` |
| CSRF tokens | Automatic via `csrf_helper.js` | Manual header setting |
| Dialogs/overlays | `Modal` component | Hand-built divs, Bootstrap modal |
| User feedback | `toaster.success/error/warning/info()` | `alert()`, custom notification divs |
| Focus management | `FocusTrap` (or `Modal` which includes it) | Manual keydown listeners |
| Screen reader updates | `ariaAnnouncer.announce()` | Custom `aria-live` regions |
| Time display | `formatTime('14:30')` | Inline parsing logic |
| HTML escaping | `escapeHtml(text)` | Unescaped `innerHTML` |
