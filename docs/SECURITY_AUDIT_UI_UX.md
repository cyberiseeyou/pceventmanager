# UI/UX Security Audit Report

**Application:** Product Connections Scheduler (Crossmark Flask Scheduling Webapp)
**Audit Date:** 2026-02-09
**Scope:** 108 UI/UX files -- 48 Jinja2 templates, 23 CSS files, 37 JavaScript files
**Methodology:** Manual code review of templates, JavaScript, and configuration
**Auditor Classification:** Static Application Security Testing (SAST) -- UI/UX Layer

---

## Executive Summary

This audit identified **21 distinct security findings** across the UI/UX layer of the Flask scheduling application. The most severe issues center on **Cross-Site Scripting (XSS)** vulnerabilities arising from a systemic pattern of injecting Jinja2 template variables into inline JavaScript event handlers and using `innerHTML` without consistent sanitization. The CSRF protection implementation is functional but fragmented across four different retrieval methods, with one component (`ai-assistant.js`) retrieving tokens from a non-existent DOM attribute, resulting in **no CSRF protection for AI assistant API calls**. Security headers are defined in configuration but **never applied to responses** because the `after_request` hook that references `SECURITY_HEADERS` does not exist in `__init__.py`. Additionally, `.env.test` is checked into the repository (visible in untracked files) containing a **plaintext Redis password** and a **settings encryption key**.

**Risk Summary:**

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High | 6 |
| Medium | 8 |
| Low | 4 |

---

## Finding 1: Stored/Reflected XSS via Inline onclick Handlers with Template Variable Interpolation

**Severity:** Critical (CVSS 8.1)
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

**Description:**
161 inline `onclick` handlers across 23 templates inject Jinja2 template variables directly into JavaScript string contexts within HTML attributes. The escape strategy relies solely on `|replace("'", "\\'")`, which is insufficient. This replacement does not handle backslashes, double-quotes, HTML entities, newlines, or closing script/attribute sequences.

**Affected Files (representative samples):**

`/home/elliot/flask-schedule-webapp/app/templates/index.html`, line 201:
```html
<div class="core-event-item core-event-item--clickable" onclick="showEventDetails({{ schedule.id }}, '{{ event.project_ref_num }}', '{{ event.project_name|replace("'", "\\'") }}', '{{ employee.name|replace("'", "\\'") if employee else "Unassigned" }}', ...)">
```

`/home/elliot/flask-schedule-webapp/app/templates/unscheduled.html`, line 194:
```html
<button onclick="confirmUnscheduleEvent({{ event.id }}, '{{ event.project_name|replace("'", "\\'") }}')">
```

`/home/elliot/flask-schedule-webapp/app/templates/dashboard/weekly_validation.html`, line 593:
```html
<button class="action-btn warning" onclick="showEmployeeSchedules('{{ issue.details.employee_id }}', '{{ date_str }}', 'Core')">
```

**Attack Scenario:**
If an attacker can control the `project_name` field (e.g., via the external Crossmark API sync, or direct database manipulation), a payload such as:

```
Project'),alert(document.cookie);//
```

would break out of the string context and execute arbitrary JavaScript. The `|replace("'", "\\'")` filter would produce `Project\'),alert(document.cookie);//` but Jinja2 auto-escaping then HTML-encodes the backslash, producing `Project\&#39;),alert(...)` in the HTML attribute, which browsers may interpret variably. More critically, a payload containing HTML entities or double-quote characters (`"`) could close the `onclick` attribute entirely and inject new attributes:

```
" onmouseover="alert(1)" data-x="
```

**Remediation:**
1. Replace all inline `onclick` handlers with `addEventListener` bindings in JavaScript, passing data via `data-*` attributes that are safely auto-escaped by Jinja2.
2. Use `|tojson` for injecting values into JavaScript contexts:
   ```html
   <div class="core-event-item" data-schedule-id="{{ schedule.id }}" data-event-ref="{{ event.project_ref_num }}" data-event-name="{{ event.project_name }}">
   ```
   ```javascript
   document.querySelectorAll('.core-event-item').forEach(el => {
       el.addEventListener('click', () => {
           showEventDetails(el.dataset.scheduleId, el.dataset.eventRef, el.dataset.eventName);
       });
   });
   ```

---

## Finding 2: XSS via innerHTML Assignment of Server-Sourced Data Without Sanitization

**Severity:** Critical (CVSS 7.5)
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

**Description:**
195 `innerHTML` assignments were identified across 21 templates and 20 JavaScript files. While an `escapeHtml()` function exists in `daily_validation.html` (line 1724) and in 13 JavaScript files, its usage is inconsistent. Many innerHTML assignments inject server data or API response data directly without any escaping.

**Affected Files (critical instances):**

`/home/elliot/flask-schedule-webapp/app/templates/index.html`, lines 567-569:
```javascript
document.getElementById('reschedule-event-info').innerHTML = `
    <strong>${eventName}</strong> (${eventType})<br>
    Current: ${currentDate} at ${currentTime} with ${employeeName}
`;
```
The variables `eventName`, `eventType`, and `employeeName` originate from textContent reads of DOM elements that were populated from Jinja2 template data. While secondary XSS risk, if the original template data contains HTML (which it does from server), this re-injection path bypasses sanitization.

`/home/elliot/flask-schedule-webapp/app/templates/index.html`, lines 1803-1815 (displayWidgetVerificationResults):
```javascript
statusBadge.innerHTML = `... ${criticalCount} Critical Issue${criticalCount !== 1 ? 's' : ''} Found`;
```
These values come from API responses at `/auto-schedule/api/verify-date`.

`/home/elliot/flask-schedule-webapp/app/templates/index.html`, lines 1824-1863 (formatVerificationIssue):
```javascript
function formatVerificationIssue(issue, severity) {
    return `
        <div class="verification-issue-item ${severity}">
            <div class="verification-issue-message">${issue.message}</div>
            ${issue.details ? `<div class="verification-issue-details">${issue.details}</div>` : ''}
            ${issue.action ? `<div class="verification-issue-action">${issue.action}</div>` : ''}
        </div>
    `;
}
```
`issue.message`, `issue.details`, and `issue.action` are server API response fields injected directly into HTML without escaping. If a schedule verification issue contains user-controlled data (e.g., employee names, event names in conflict messages), this is exploitable.

`/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html`, lines 1730-1742 (renderEventCard):
```javascript
return `
    <div class="event-card">
        <span class="event-id">${event.event_id}</span>
        <span class="event-name" title="${event.event_name}">${event.event_name}</span>
        ...
        ${event.assigned_employee_name ? `<span class="assigned-to">... ${event.assigned_employee_name}</span>` : ...}
    </div>
`;
```
`event.event_name` and `event.assigned_employee_name` come from the Walmart API response and are rendered without escaping.

`/home/elliot/flask-schedule-webapp/app/static/js/components/ai-assistant.js`, line 250-253:
```javascript
addMessage(role, text) {
    msgDiv.innerHTML = `
        <div class="ai-avatar">${role === 'user' ? '...' : '...'}</div>
        <div class="ai-bubble"><p>${this.formatText(text)}</p></div>
    `;
```

The `formatText` method at line 277-281:
```javascript
formatText(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}
```
This replaces bold markdown and newlines but **does NOT escape HTML first**. User messages AND AI responses are rendered with innerHTML without HTML entity escaping. Any `<script>` or `<img onerror>` tags in AI responses or reflected user input will execute.

**Remediation:**
1. Establish a mandatory `escapeHtml()` utility in a shared module and import it in every file that uses innerHTML.
2. For the AI assistant, escape HTML before applying markdown formatting:
   ```javascript
   formatText(text) {
       let safe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
       safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
       safe = safe.replace(/\n/g, '<br>');
       return safe;
   }
   ```
3. Consider using `textContent` where HTML formatting is not needed, or a DOM-based rendering approach instead of string concatenation into innerHTML.

---

## Finding 3: Credentials and Secrets Committed in `.env.test`

**Severity:** Critical (CVSS 7.5)
**CWE:** CWE-798 (Use of Hard-coded Credentials), CWE-312 (Cleartext Storage of Sensitive Information)

**Description:**
The file `/home/elliot/flask-schedule-webapp/.env.test` is present as an untracked file in the working directory and contains:

Line 44:
```
SETTINGS_ENCRYPTION_KEY=DY1iyKWPgYE3dhVwF-LyhJ5GAjmifUxT_srgSH0oKnU=
```

Line 47:
```
REDIS_PASSWORD=Redneck2013
```

Line 22:
```
WALMART_USER_ID=d2fr4w2
```

Even though this file is marked as a test configuration, the encryption key could be used to decrypt production settings if the same key was reused, and the Redis password grants access to the message broker. The file also appears in `git status` as untracked, meaning it could easily be committed accidentally.

**Remediation:**
1. Add `.env.test` to `.gitignore` immediately.
2. Rotate the `SETTINGS_ENCRYPTION_KEY` and `REDIS_PASSWORD` values.
3. Never store real credentials in files within the repository, even for test purposes. Use a secrets manager or at minimum a `.env.example` with placeholder values.

---

## Finding 4: Security Headers Defined but Never Applied to HTTP Responses

**Severity:** High (CVSS 7.1)
**CWE:** CWE-693 (Protection Mechanism Failure)

**Description:**
Security headers are defined in `/home/elliot/flask-schedule-webapp/app/config.py` at line 154:
```python
SECURITY_HEADERS = {
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
}
```

However, a grep for `SECURITY_HEADERS` in `/home/elliot/flask-schedule-webapp/app/__init__.py` returns **no matches**. The only `@app.after_request` handler in `__init__.py` is `add_csrf_token_cookie` (line 309). There is **no middleware or after_request hook** that applies these headers to responses.

This means:
- No HSTS header: no protection against protocol downgrade attacks.
- No X-Content-Type-Options: browsers may MIME-sniff responses.
- No X-Frame-Options: the application is vulnerable to clickjacking.
- No CSP header: inline scripts execute unrestricted.

**Remediation:**
Add an `after_request` handler in `__init__.py`:
```python
@app.after_request
def add_security_headers(response):
    for header, value in app.config.get('SECURITY_HEADERS', {}).items():
        response.headers[header] = value
    return response
```

---

## Finding 5: CSP Policy Allows 'unsafe-inline' and Omits External CDN Origins

**Severity:** High (CVSS 6.5)
**CWE:** CWE-1021 (Improper Restriction of Rendered UI Layers)

**Description:**
The defined (but unapplied -- see Finding 4) CSP at `/home/elliot/flask-schedule-webapp/app/config.py` line 159 is:
```
default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
```

Issues:
1. **`'unsafe-inline'` in script-src** renders CSP nearly useless against XSS. All 161 inline onclick handlers and all inline `<script>` blocks require this, but it means any injected inline script will also execute.
2. **Missing external CDN origins.** The application loads resources from:
   - `https://fonts.googleapis.com`, `https://fonts.gstatic.com` (base.html lines 17-21)
   - `https://cdnjs.cloudflare.com` (Font Awesome -- multiple templates)
   - `https://cdn.jsdelivr.net` (Bootstrap, Chart.js -- multiple templates)
   - `https://code.jquery.com` (jQuery -- daily_validation.html)
   - `https://corporate.walmart.com` (image -- approved_events.html)

   If CSP were enforced, all these resources would be blocked, breaking the application. This policy was clearly never tested.

3. **Missing directives:** No `img-src`, `font-src`, `connect-src`, `frame-ancestors`, or `form-action` directives.

**Remediation:**
1. Migrate all inline scripts to external files to remove the need for `'unsafe-inline'`. Use nonces or hashes for any remaining inline scripts.
2. Add all required external origins to the CSP.
3. Add `frame-ancestors 'self'` to replace X-Frame-Options.
4. Add `form-action 'self'` to prevent form hijacking.

---

## Finding 6: CSRF Token Retrieval Broken in AI Assistant Component

**Severity:** High (CVSS 7.3)
**CWE:** CWE-352 (Cross-Site Request Forgery)

**Description:**
The application has **four different CSRF token retrieval implementations**, and one of them is completely broken.

1. **`csrf_helper.js` (line 24-36):** Reads from cookie named `csrf_token`. This is the global interceptor applied to all fetch/XHR/jQuery calls.

2. **`api-client.js` (line 217-230):** Reads from meta tag `<meta name="csrf-token">`, falling back to `window.getCsrfToken()` function.

3. **`ai-chat.js` (line 303-311):** Reads from cookie or meta tag -- functional.

4. **`ai-assistant.js` (line 284-286):**
   ```javascript
   getCsrfToken() {
       return document.querySelector('script[src*="csrf_helper.js"]')?.getAttribute('data-csrf') || '';
   }
   ```
   This attempts to read a `data-csrf` attribute from the `<script>` tag that loads `csrf_helper.js`. However, in `base.html` line 302, the script tag is:
   ```html
   <script src="{{ url_for('static', filename='js/csrf_helper.js') }}"></script>
   ```
   There is **no `data-csrf` attribute**. The method always returns `''`.

Since `ai-assistant.js` makes POST requests to `/api/ai/query` (line 207) with this broken token, the CSRF header `X-CSRFToken` is always an empty string. If the server validates CSRF tokens (which it should via Flask-WTF), these requests would fail. If the server silently accepts empty tokens, the AI endpoint has no CSRF protection.

Additionally, the global `csrf_helper.js` fetch interceptor (line 75-94) should catch this because it wraps `window.fetch`. However, because `ai-assistant.js` also explicitly sets the `X-CSRFToken` header in its fetch options (line 211), and `csrf_helper.js` sets `options.headers['X-CSRF-Token']` (note different header name: `X-CSRF-Token` vs `X-CSRFToken`), the headers **do not collide** and **both are sent**. The server must check both header names, or one implementation's token will be ignored.

**Remediation:**
1. Standardize on a single CSRF token header name across the entire application (recommend `X-CSRFToken` to match Flask-WTF default).
2. Fix the `ai-assistant.js` `getCsrfToken()` method to use the meta tag or cookie approach.
3. Remove redundant CSRF retrieval implementations and use a shared utility.

---

## Finding 7: CSRF Cookie Set Without HttpOnly Flag by Design

**Severity:** High (CVSS 5.4)
**CWE:** CWE-1004 (Sensitive Cookie Without 'HttpOnly' Flag)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/__init__.py` at line 320-326:
```python
response.set_cookie(
    'csrf_token',
    csrf_token,
    secure=app.config.get('SESSION_COOKIE_SECURE', False),
    httponly=False,  # Intentionally False
    samesite='Lax'
)
```

The CSRF token cookie has `httponly=False` intentionally so that JavaScript can read it. This is a standard pattern for CSRF double-submit cookies. However, issues remain:

1. The `secure` flag defaults to `False` when `SESSION_COOKIE_SECURE` is not set, meaning the CSRF cookie can be transmitted over plain HTTP.
2. The CSRF token is exposed to any JavaScript on the page, including scripts from CDN origins (see Finding 8). If a CDN is compromised or a third-party script is injected, the CSRF token is available.

**Remediation:**
1. Ensure `SESSION_COOKIE_SECURE=True` in all production deployments.
2. Consider using the meta tag approach exclusively (which already exists at base.html line 7) and removing the cookie-based CSRF delivery. The meta tag is not accessible to third-party scripts in different origins (though inline scripts can read it).

---

## Finding 8: External CDN Resources Without Subresource Integrity (SRI)

**Severity:** High (CVSS 7.2)
**CWE:** CWE-829 (Inclusion of Functionality from Untrusted Control Sphere)

**Description:**
The application loads JavaScript and CSS from external CDNs. While `daily_validation.html` correctly includes `integrity` attributes on its 4 CDN resources, the majority of external resources across the application **do not have SRI hashes**:

**Resources WITHOUT integrity attributes:**

| File | Resource | Type |
|------|----------|------|
| `/home/elliot/flask-schedule-webapp/app/templates/base.html` line 19 | `fonts.googleapis.com/css2...Outfit` | CSS |
| `/home/elliot/flask-schedule-webapp/app/templates/base.html` line 21 | `fonts.googleapis.com/css2...Material+Symbols` | CSS |
| `/home/elliot/flask-schedule-webapp/app/templates/workload_dashboard.html` line 71 | `cdn.jsdelivr.net/npm/chart.js@4.4.0` | JS |
| `/home/elliot/flask-schedule-webapp/app/templates/inventory/orders.html` line 7 | `cdn.jsdelivr.net/npm/bootstrap@5.1.3/...css` | CSS |
| `/home/elliot/flask-schedule-webapp/app/templates/inventory/orders.html` line 9 | `cdnjs.cloudflare.com/...font-awesome/6.0.0` | CSS |
| `/home/elliot/flask-schedule-webapp/app/templates/inventory/orders.html` line 289 | `cdn.jsdelivr.net/npm/bootstrap@5.1.3/...js` | JS |
| `/home/elliot/flask-schedule-webapp/app/templates/inventory/index.html` lines 7, 9, 993 | Bootstrap CSS, Font Awesome CSS, Bootstrap JS | Multiple |
| `/home/elliot/flask-schedule-webapp/app/templates/inventory/order_detail.html` lines 7, 9, 444 | Bootstrap CSS, Font Awesome CSS, Bootstrap JS | Multiple |
| `/home/elliot/flask-schedule-webapp/app/templates/printing.html` lines 7, 9, 3510 | Bootstrap CSS, Font Awesome CSS, Bootstrap JS | Multiple |
| `/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html` line 6 | `cdnjs.cloudflare.com/...font-awesome/6.4.0` | CSS |
| `/home/elliot/flask-schedule-webapp/app/templates/dashboard/weekly_validation.html` line 6 | `cdnjs.cloudflare.com/...font-awesome/6.4.0` | CSS |
| `/home/elliot/flask-schedule-webapp/app/templates/dashboard/command_center.html` line 6 | `cdnjs.cloudflare.com/...font-awesome/6.4.0` | CSS |

A compromised CDN could serve malicious JavaScript that steals session cookies, CSRF tokens, or performs actions on behalf of authenticated users. The `chart.js` and `bootstrap.bundle.min.js` scripts are particularly high-risk since they are executable JavaScript from third-party CDNs.

**Remediation:**
1. Add `integrity` and `crossorigin="anonymous"` attributes to all external script and link tags.
2. Consider self-hosting critical dependencies (Bootstrap, Font Awesome, Chart.js) to eliminate CDN dependency entirely.

---

## Finding 9: AI Chat XSS via Unescaped User Input and AI Response Rendering

**Severity:** High (CVSS 6.8)
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

**Description:**
Two separate AI chat components handle user input differently:

**`ai-chat.js` (line 271-300):** The `formatMessage()` method DOES escape HTML before rendering:
```javascript
let formatted = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
```
This is correct.

**`ai-assistant.js` (line 277-281):** The `formatText()` method does NOT escape HTML:
```javascript
formatText(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}
```

Both user messages and AI responses pass through this method and are injected via innerHTML (line 252). If the AI model returns HTML tags in its response (which LLMs commonly do), or if a user types `<img src=x onerror=alert(1)>`, it will execute in the browser context. Since the AI assistant is available on every page via `base.html`, this is a persistent XSS vector across the entire application.

**Remediation:**
Add HTML escaping before markdown transformation in `ai-assistant.js`:
```javascript
formatText(text) {
    let safe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    safe = safe.replace(/\n/g, '<br>');
    return safe;
}
```

---

## Finding 10: document.write() Usage in Print Windows with Unsanitized Template Data

**Severity:** Medium (CVSS 5.3)
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

**Description:**
12 instances of `document.write()` exist across `index.html`, `calendar.html`, and `printing.html` for generating print-friendly pages. These inject server-side Jinja2 variables into JavaScript template literals, which are then written into new windows.

`/home/elliot/flask-schedule-webapp/app/templates/index.html`, lines 957-965:
```javascript
const printableEvents = [
    {% for schedule, event, employee in today_core_events %}
    {
        employee_name: "{{ employee.name }}",
        event_name: "{{ event.project_name }}",
        ...
    },
    {% endfor %}
];
```

These values are used in `generatePrintableSchedule()` (line 1193):
```javascript
${printableEvents.map(event => `
    <tr>
        <td class="employee-name">${event.employee_name}</td>
        <td class="event-name">${event.event_name}</td>
    </tr>
`).join('')}
```

Employee names or event names containing `"` would break the JavaScript string on initial assignment. Names containing HTML would be rendered as HTML in the print window.

**Remediation:**
1. Use `|tojson` filter for JavaScript variable assignment: `employee_name: {{ employee.name|tojson }}`.
2. Escape HTML when building print content, or use DOM manipulation instead of document.write.

---

## Finding 11: Raw fetch() Calls Without Timeout on Multiple Pages

**Severity:** Medium (CVSS 4.3)
**CWE:** CWE-400 (Uncontrolled Resource Consumption)

**Description:**
While the `api-client.js` module implements a 10-second timeout with AbortController, many pages make direct `fetch()` calls that bypass this client entirely, resulting in no timeout protection:

- `/home/elliot/flask-schedule-webapp/app/templates/index.html`: 15+ raw fetch() calls (unschedule, reschedule, change employee, print EDR, MFA requests, verification, etc.)
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html`: 8+ raw fetch() calls (auth, session, events, rolling)
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`: fetch to `/api/daily-employees/`
- `/home/elliot/flask-schedule-webapp/app/templates/base.html`: fetch to `/api/session-info`, `/api/session/heartbeat`, `/api/auth/status`

A slow or unresponsive server can cause the browser tab to appear frozen indefinitely with no user feedback or cancellation mechanism.

**Remediation:**
Wrap all fetch calls with AbortController timeouts, or migrate to the existing `apiClient` module:
```javascript
// Instead of: fetch('/api/endpoint')
// Use: window.apiClient.get('/api/endpoint')
```

---

## Finding 12: ES Module / Global Script Race Condition

**Severity:** Medium (CVSS 4.0)
**CWE:** CWE-362 (Race Condition)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/base.html` at lines 306-327, core infrastructure modules are loaded as ES modules (`type="module"`) and exposed to the global `window` object:
```javascript
<script type="module">
    import { apiClient } from '...api-client.js';
    window.apiClient = apiClient;
    window.ValidationEngine = ValidationEngine;
    // ...
</script>
```

Module scripts are deferred by specification and execute after all synchronous scripts. However, the inline `<script>` blocks in child templates (e.g., `index.html` line 449, which defines functions using `window.getCsrfToken`) execute synchronously during parsing. If any inline script attempts to use `window.apiClient` or `window.ValidationEngine` before the module script completes, it will encounter `undefined`.

The current code mitigates this partially through DOMContentLoaded listeners, but some functions like `runVerification()` (index.html line 1744) are called directly from inline onclick handlers and use raw `fetch()` instead of `apiClient`, suggesting developers encountered this race condition and worked around it by not using the module system.

**Remediation:**
1. Convert all inline scripts to deferred external module scripts.
2. Use a module loader pattern or event-driven initialization to guarantee execution order.

---

## Finding 13: Keyboard Shortcuts Conflict with User Input

**Severity:** Medium (CVSS 3.1)
**CWE:** CWE-20 (Improper Input Validation)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html` at lines 1582-1601:
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

These shortcuts trigger on **any keypress** without checking if the user is typing in an input field, textarea, or contenteditable element. Typing the letter "r" in the date picker, MFA input, or search field will reload the page. Typing "1", "2", or "3" will navigate away, potentially losing unsaved work.

**Remediation:**
Add a guard to ignore shortcuts when focus is in an input element:
```javascript
document.addEventListener('keydown', function(e) {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) {
        return;
    }
    // ... shortcut logic
});
```

---

## Finding 14: Clickjacking Vulnerability (X-Frame-Options Not Enforced)

**Severity:** Medium (CVSS 4.7)
**CWE:** CWE-1021 (Improper Restriction of Rendered UI Layers or Frames)

**Description:**
As described in Finding 4, the X-Frame-Options header is defined but never applied. Without this header, the application can be embedded in an `<iframe>` on a malicious site. An attacker could overlay invisible UI elements to trick users into clicking buttons (e.g., "Approve All" in the auto-scheduler, "Unschedule" event actions, or "Refresh Database" which clears all events).

This is particularly dangerous because:
- The "Refresh Database" button (base.html line 156) clears all existing events and refetches from API.
- The auto-scheduler approve-all endpoint bulk-approves pending schedules.
- Unschedule actions remove employee assignments.

**Remediation:**
Apply the X-Frame-Options header as described in Finding 4's remediation.

---

## Finding 15: Open Redirect via Unvalidated window.location.href Assignments

**Severity:** Medium (CVSS 4.3)
**CWE:** CWE-601 (URL Redirection to Untrusted Site)

**Description:**
Multiple pages construct redirect URLs from user-controlled or DOM-sourced data:

`/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`, line 1473:
```javascript
function navigateToDate(dateValue) {
    if (dateValue) {
        window.location.href = `/dashboard/daily-validation?date=${dateValue}`;
    }
}
```
The `dateValue` comes from an `<input type="date">` element, which browsers constrain to date format. However, programmatic manipulation of the input value via browser DevTools could inject arbitrary path characters.

`/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html`, lines 1689, 1699:
```javascript
onclick="window.location.href='/events?search=${event.event_id}'"
```
`event.event_id` comes from the Walmart API. A malicious event ID containing `javascript:` or path traversal could potentially redirect.

While exploitation is limited (same-origin redirects only in most cases), it's a defense-in-depth concern.

**Remediation:**
Validate and sanitize URL parameters before assignment. Use URL object parsing to ensure paths stay within the application.

---

## Finding 16: External Image Load from Walmart Corporate Domain

**Severity:** Medium (CVSS 3.1)
**CWE:** CWE-829 (Inclusion of Functionality from Untrusted Control Sphere)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html` line 917:
```html
<img src="https://corporate.walmart.com/content/dam/corporate/images/global/social-share-og/Walmart_Spark.png"
    alt="Walmart" style="height: 32px; filter: brightness(0) invert(1);">
```

This loads an image from an external domain on every page load of the "Left in Approved" dashboard. This:
1. Leaks the user's IP address and page visit timing to Walmart's servers.
2. Could be used for tracking if the image URL contains identifiers.
3. If the image CDN is compromised, a malicious SVG or specially crafted image could exploit browser vulnerabilities.

**Remediation:**
Download the image, host it locally as a static asset, and reference it via `url_for('static', ...)`.

---

## Finding 17: Weak Default SECRET_KEY in Configuration

**Severity:** Medium (CVSS 5.9)
**CWE:** CWE-1188 (Insecure Default Initialization of Resource)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/config.py` line 131:
```python
SECRET_KEY = config('SECRET_KEY', default='change-this-to-a-random-secret-key-in-production')
```

While the `ProductionConfig.validate()` method checks for proper key length, the `BaseConfig` class used by all environments defaults to a predictable string. If a developer runs the app without setting `SECRET_KEY`, all sessions, CSRF tokens, and signed cookies use this known value.

The `DevelopmentConfig` and `TestingConfig` classes inherit this default. Only `ProductionConfig` validates it.

**Remediation:**
1. Remove the default value entirely: `SECRET_KEY = config('SECRET_KEY')` -- this forces explicit configuration.
2. Alternatively, generate a random key per-process for development: `SECRET_KEY = config('SECRET_KEY', default=secrets.token_hex(32))`.

---

## Finding 18: Session Heartbeat and Auth Status Endpoints Without Rate Limiting

**Severity:** Low (CVSS 3.1)
**CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/base.html`, the session activity tracker sends:
- Heartbeat every 120 seconds (line 438, `HEARTBEAT_INTERVAL = 120000`)
- Auth status check every 30 seconds (line 439, `CHECK_INTERVAL = 30000`)

These endpoints (`/api/session/heartbeat` and `/api/auth/status`) are called continuously on every page. While rate limiting is configured at the application level (`RATELIMIT_DEFAULT = '100 per hour'`), these automated requests could consume rate limit budget, causing legitimate user actions to be rate-limited.

Additionally, the heartbeat does not include CSRF protection (it uses the global fetch interceptor from csrf_helper.js, but the method is `POST` without explicit CSRF token -- it relies on the cookie being set).

**Remediation:**
1. Exempt session management endpoints from general rate limits.
2. Ensure heartbeat POST includes CSRF protection.

---

## Finding 19: jQuery 3.6.0 with Known Vulnerabilities

**Severity:** Low (CVSS 3.7)
**CWE:** CWE-1395 (Dependency on Vulnerable Third-Party Component)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html` line 1464:
```html
<script src="https://code.jquery.com/jquery-3.6.0.min.js" ...></script>
```

jQuery 3.6.0 has known prototype pollution vulnerabilities. While the integrity hash protects against CDN tampering, the library itself contains the vulnerability. Note: the SRI hash specified (`sha384-vtXRMe3mGCbOeY7l30aIg8H9p3GdeSe4IFlP6G8JMa7o7lXvnz3GFKzPxzJdPfGK`) appears to be incorrect for jQuery 3.6.0 (the official hash is different), which means the browser may reject the script entirely or accept it without verification depending on the crossorigin attribute behavior.

**Remediation:**
1. Upgrade jQuery to the latest 3.x release (3.7.1+).
2. Verify the SRI hash matches the actual file.
3. Consider removing jQuery entirely since it's only used on this one page for Bootstrap tab functionality. Bootstrap 5.x does not require jQuery.

---

## Finding 20: Auto-Refresh Without User Consent

**Severity:** Low (CVSS 2.3)
**CWE:** CWE-799 (Improper Control of Interaction Frequency)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html` lines 1551-1570:
```javascript
let refreshCountdown = 5 * 60;
const refreshTimer = setInterval(() => {
    refreshCountdown--;
    if (refreshCountdown <= 0) {
        clearInterval(refreshTimer);
        location.reload();
    }
}, 1000);
```

The page automatically reloads every 5 minutes without user consent. This:
1. Discards any unsaved user state.
2. Makes the page unsuitable for long reading sessions.
3. Could interfere with accessibility tools.
4. Creates predictable network patterns that simplify timing attacks.

**Remediation:**
Replace auto-refresh with a notification-based approach: show a "New data available - click to refresh" banner instead of forcing a reload.

---

## Finding 21: |safe Filter Usage in Template Component

**Severity:** Low (CVSS 3.7)
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

**Description:**
In `/home/elliot/flask-schedule-webapp/app/templates/components/modal_base.html` line 46:
```jinja2
{{ footer_content|safe if footer_content else '' }}
```

The `|safe` filter disables Jinja2's auto-escaping. If `footer_content` is ever passed user-controlled or database-sourced HTML, it will be rendered without sanitization. This is the only `|safe` usage found across all 48 templates, so the risk is contained to this single component.

**Remediation:**
Audit all callers of `modal_base.html` to ensure `footer_content` only receives developer-controlled HTML strings. Add a comment documenting this requirement. Consider using Jinja2's `Markup()` class on the server side instead of `|safe` in templates.

---

## Summary of Remediation Priorities

### Immediate (Week 1)
1. **Finding 3**: Add `.env.test` to `.gitignore` and rotate exposed credentials.
2. **Finding 4**: Implement the security headers `after_request` hook in `__init__.py`.
3. **Finding 6**: Fix the broken CSRF token retrieval in `ai-assistant.js`.

### Short-Term (Weeks 2-3)
4. **Finding 1**: Begin migrating inline onclick handlers to data-attribute + addEventListener pattern, starting with highest-traffic pages (`index.html`, `daily_view.html`, `unscheduled.html`).
5. **Finding 2 / Finding 9**: Standardize `escapeHtml()` as a shared module, audit all innerHTML assignments.
6. **Finding 8**: Add SRI hashes to all external CDN resources, or self-host them.

### Medium-Term (Weeks 4-6)
7. **Finding 5**: Develop a proper CSP with nonces for any remaining inline scripts.
8. **Finding 7**: Ensure Secure flag on all cookies in production.
9. **Finding 10**: Apply `|tojson` to all template variables used in JavaScript contexts.
10. **Finding 11**: Migrate raw fetch() calls to the apiClient module.

### Long-Term (Month 2+)
11. **Finding 12**: Resolve the ES module/global script race condition by converting all inline scripts to modules.
12. **Finding 14**: Implement clickjacking protections via CSP `frame-ancestors`.
13. **Finding 19**: Upgrade or remove jQuery dependency.

---

## Appendix A: Methodology

Files examined in detail:
- `/home/elliot/flask-schedule-webapp/app/templates/base.html`
- `/home/elliot/flask-schedule-webapp/app/templates/index.html`
- `/home/elliot/flask-schedule-webapp/app/templates/daily_view.html`
- `/home/elliot/flask-schedule-webapp/app/templates/unscheduled.html`
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/daily_validation.html`
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/approved_events.html`
- `/home/elliot/flask-schedule-webapp/app/templates/dashboard/weekly_validation.html`
- `/home/elliot/flask-schedule-webapp/app/templates/components/ai_panel.html`
- `/home/elliot/flask-schedule-webapp/app/templates/components/modal_base.html`
- `/home/elliot/flask-schedule-webapp/app/static/js/csrf_helper.js`
- `/home/elliot/flask-schedule-webapp/app/static/js/utils/api-client.js`
- `/home/elliot/flask-schedule-webapp/app/static/js/modules/validation-engine.js`
- `/home/elliot/flask-schedule-webapp/app/static/js/components/ai-chat.js`
- `/home/elliot/flask-schedule-webapp/app/static/js/components/ai-assistant.js`
- `/home/elliot/flask-schedule-webapp/app/config.py`
- `/home/elliot/flask-schedule-webapp/app/__init__.py`
- `/home/elliot/flask-schedule-webapp/.env.test`

Pattern searches performed across all 108 UI/UX files:
- `|safe` filter usage (1 hit)
- `{% autoescape false %}` (0 hits)
- `innerHTML =` (195 hits across 41 files)
- `onclick=` with `{{ }}` interpolation (161 hits across 23 files)
- `escapeHtml` usage (13 files)
- `document.write` (12 hits)
- `eval()`, `Function()`, `setTimeout(string)` (0 hits)
- `postMessage` / message event listeners (0 hits)
- `__proto__`, `prototype[]`, `constructor[]` (0 hits)
- External CDN URLs without integrity attributes (20+ hits)
- Credential/secret patterns in static JS files (0 hits)

## Appendix B: Positive Security Observations

1. **CSRF token auto-injection via fetch interceptor** (`csrf_helper.js`) is a sound pattern that covers jQuery, fetch, and XHR.
2. **Jinja2 auto-escaping is enabled by default** (no `{% autoescape false %}` found anywhere).
3. **No `eval()` or string-based `setTimeout()` / `setInterval()` calls** found in any JavaScript or template file.
4. **No `postMessage` handlers** that could be exploited for cross-origin attacks.
5. **No prototype pollution patterns** found in application JavaScript.
6. **The `ai-chat.js` component** correctly implements HTML escaping before markdown rendering.
7. **`validation-engine.js`** is well-structured with proper field-level validation, accessibility support, and no innerHTML usage.
8. **Session management** includes activity tracking, heartbeat, and timeout with countdown warning.
9. **The `apiClient` module** implements proper timeout (10s), retry logic, and CSRF token handling.
10. **SRI hashes are present** on the daily_validation.html CDN resources (jQuery, Bootstrap CSS/JS, Font Awesome).
