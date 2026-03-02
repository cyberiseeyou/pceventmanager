# Chrome Remote Debugging EDR Authentication — Design Document

**Date:** 2026-03-01
**Status:** Approved
**Replaces:** `docs/plans/2026-02-27-playwright-edr-auth.md` (reverted approach)

## Problem

Walmart's Retail Link login at `retaillink.login.wal-mart.com` is protected by PerimeterX (HUMAN Security). The current `requests`-based authentication gets HTTP 412 because:

1. `requests` has no JS engine — PerimeterX's `px.js` sensor never executes
2. No `_px3` clearance cookie is generated
3. TLS fingerprint doesn't match a real browser

A previous Playwright + stealth approach also got 412 — PX detects CDP artifacts and/or datacenter IPs even with stealth patches.

## Solution

Use **Chrome Remote Debugging** (CDP) to drive a real Chrome browser for the PX-protected login steps (1-3). After MFA validation, extract all cookies from Chrome and inject them into the existing `requests.Session`. Steps 4-6 on `retaillink2.wal-mart.com` continue unchanged.

**Why this works:** Chrome is a real, unmodified browser with a real fingerprint. Unlike Playwright/Selenium, connecting via `--remote-debugging-port` does not inject detectable automation artifacts (`navigator.webdriver`, ChromeDriver fingerprints). PerimeterX sees a normal user session.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Flask App (printing.py)                                    │
│                                                             │
│  User clicks "Authenticate EDR"                             │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────┐                                │
│  │ ChromeEDRAuthenticator  │──── launches ────┐             │
│  │ (chrome_cdp_auth.py)    │                  │             │
│  └────────┬────────────────┘                  ▼             │
│           │                          ┌──────────────┐       │
│           │◄──── CDP (port 9222) ───►│ Real Chrome  │       │
│           │                          │ (visible)    │       │
│           │                          └──────────────┘       │
│           │                                                 │
│           │  1. Navigate to login page (PX loads normally)  │
│           │  2. Execute JS: submit credentials              │
│           │  3. Execute JS: request MFA                     │
│           │  4. Execute JS: validate MFA code               │
│           │  5. Extract ALL cookies via Network.getCookies  │
│           │  6. Close Chrome                                │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────────┐                                    │
│  │ EDRReportGenerator  │                                    │
│  │ (existing)          │                                    │
│  │  .session.cookies ◄─── injected from Chrome cookies      │
│  │  .step4_register()  │  ◄── continues with requests       │
│  │  .step5_navigate()  │                                    │
│  │  .step6_auth()      │  ◄── extracts auth-token           │
│  └─────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

## Chrome Lifecycle

### Launch

The app spawns Chrome as a subprocess:

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/edr-chrome-profile \
  --no-first-run \
  --disable-default-apps
```

- `--user-data-dir` — dedicated temp profile, avoids conflicts with normal Chrome
- `--no-first-run` — skips welcome screen
- App polls `http://localhost:9222/json/version` until Chrome is ready (max 10s)

### Reuse

If Chrome is already running on port 9222, the app reuses the existing instance instead of launching a new one.

### Teardown

After cookies are extracted, the Chrome process is terminated and the temp profile is cleaned up.

### Chrome Binary Detection

Search order: `google-chrome` → `google-chrome-stable` → `chromium-browser` → `chromium`. Error with clear message if none found.

## Login Flow via CDP

All login steps use `Runtime.evaluate` to execute `fetch()` calls in the page context — the same way Retail Link's SPA works natively.

### Step 1 — Navigate & Submit Credentials

```python
tab.Page.navigate(url="https://retaillink.login.wal-mart.com/login")
# Wait for Page.loadEventFired
# Human delay: 2-3s

tab.Runtime.evaluate(expression="""
    fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: '...', password: '...', language: 'en'})
    }).then(r => r.json()).then(d => JSON.stringify({status: 'ok', data: d}))
      .catch(e => JSON.stringify({status: 'error', message: e.message}))
""")
```

### Step 2 — Request MFA Code

```python
tab.Runtime.evaluate(expression="""
    fetch('/api/mfa/sendCode', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type: 'SMS_OTP', credid: '...'})
    }).then(r => r.json()).then(d => JSON.stringify({status: 'ok', data: d}))
      .catch(e => JSON.stringify({status: 'error', message: e.message}))
""")
```

After this step, the Flask UI prompts the user for their MFA code. Chrome stays open and idle.

### Step 3 — Validate MFA Code

```python
tab.Runtime.evaluate(expression="""
    fetch('/api/mfa/validateCode', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type: 'SMS_OTP', credid: '...', code: '...', failureCount: 0})
    }).then(r => r.json()).then(d => JSON.stringify({status: 'ok', data: d}))
      .catch(e => JSON.stringify({status: 'error', message: e.message}))
""")
```

### Cookie Extraction

```python
result = tab.Network.getCookies()
cookies = result['cookies']
# Filter to *.wal-mart.com domains only
```

## Cookie Injection

Extracted cookies are injected into `EDRReportGenerator.session`:

```python
for cookie in chrome_cookies:
    if '.wal-mart.com' in cookie.get('domain', ''):
        self.session.cookies.set(
            cookie['name'],
            cookie['value'],
            domain=cookie.get('domain', ''),
            path=cookie.get('path', '/'),
            secure=cookie.get('secure', False),
        )
```

After injection, existing steps 4-6 run unchanged via `requests`.

## File Changes

### New File: `app/integrations/edr/chrome_cdp_auth.py`

Contains `ChromeEDRAuthenticator` class with:
- `launch_chrome()` — finds and spawns Chrome with debug port
- `connect()` — connects via pychrome to CDP
- `step1_submit_credentials(username, password)` — navigates and submits login
- `step2_request_mfa(mfa_credential_id)` — triggers SMS MFA
- `step3_validate_mfa(mfa_credential_id, code)` — validates MFA code
- `extract_cookies()` — gets all cookies via `Network.getCookies`
- `cleanup()` — kills Chrome, removes temp profile
- `inject_cookies_into_session(session)` — transfers cookies to `requests.Session`

### Modified: `app/integrations/edr/report_generator.py`

- New method `chrome_step1_submit_password()` — delegates to `ChromeEDRAuthenticator`
- New method `chrome_step2_request_mfa_code()` — delegates to `ChromeEDRAuthenticator`
- New method `chrome_step3_validate_mfa_code(code)` — delegates, extracts cookies, injects
- Chrome instance stored as `self._chrome_auth` (created on first chrome step, cleaned up after step 3)

### Modified: `app/routes/printing.py`

- `edr_request_mfa()` calls chrome-based steps 1+2 instead of `requests`-based
- `edr_authenticate()` calls chrome-based step 3, then existing steps 4-6
- Fallback: if `pychrome` not installed or Chrome not available, uses existing `requests` flow

### New Dependency

- `pychrome` added to `requirements.txt`

## UX Flow

The user experience is nearly identical to today:

1. User clicks "Authenticate EDR" in the printing page
2. **New:** A Chrome window opens briefly, showing the Retail Link login page
3. Credentials submitted automatically via CDP → PX passes (real browser)
4. MFA triggered → user enters code in Flask UI (same as today)
5. MFA validated via CDP → cookies extracted → Chrome closes
6. Steps 4-6 run via `requests` with injected cookies
7. "Authentication successful" — same as today

The only visible difference is Chrome briefly appearing during auth.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Chrome binary not found | Clear error message with install instructions |
| Port 9222 already in use (non-Chrome) | Try alternative port 9223, then error |
| CDP connection timeout (10s) | Error with suggestion to check Chrome |
| Step 1 returns non-200 | Report status + body, suggest checking credentials |
| Step 2 fails | Report error, suggest checking MFA credential ID |
| Step 3 fails (wrong code) | Report error, allow retry |
| Chrome crashes mid-auth | Detect process exit, report which step failed |
| `pychrome` not installed | Fall back to `requests`-based flow with warning |

## Fallback Strategy

If Chrome Remote Debugging is unavailable (no Chrome installed, `pychrome` missing, etc.), the system falls back to the existing `requests`-based steps 1-3. This ensures the app doesn't break in environments where Chrome isn't available, even though PX will likely block the `requests` approach.

## Security Considerations

- Credentials are passed via `Runtime.evaluate` JS execution in the browser context — they exist only in the page's JS scope, not logged or persisted
- The temp Chrome profile (`/tmp/edr-chrome-profile`) is deleted after each auth session
- Cookies are filtered to `*.wal-mart.com` domains before injection
- The CDP port (9222) is bound to localhost only — not accessible from other machines
