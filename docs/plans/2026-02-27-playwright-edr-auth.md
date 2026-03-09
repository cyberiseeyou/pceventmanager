# Playwright EDR Authentication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Python `requests`-based Walmart Retail Link login (Steps 1-3) with Playwright to bypass PerimeterX bot detection, while keeping the existing `requests.Session` for all post-auth API calls.

**Architecture:** Playwright launches a headless Chromium browser to handle the PerimeterX-protected login flow (password submission + MFA). After successful MFA validation, all cookies are extracted from the Playwright browser context and injected into the existing `requests.Session`. Steps 4-6 and all data-fetching APIs continue to use `requests` as before. The Playwright browser is closed immediately after cookie extraction to minimize resource usage.

**Tech Stack:** Playwright (Python async API), playwright-stealth, asyncio, existing requests.Session

---

## Background

Walmart's Retail Link login at `retaillink.login.wal-mart.com` is protected by PerimeterX (HUMAN Security). The current implementation uses Python `requests.Session()` to POST credentials, which gets blocked with HTTP 412 because:
1. TLS fingerprint doesn't match a real browser
2. PerimeterX JavaScript sensor (`px.js`) never executes
3. No `_px3` clearance cookie is generated

Playwright solves this by running real Chromium that executes PX JavaScript natively.

## Key Design Decisions

- **Only Steps 1-3 use Playwright** (login page → submit password → request MFA → validate MFA code). Steps 4-6 and all data APIs continue using `requests.Session` with the extracted cookies.
- **Playwright browser is short-lived** — launched at step1, closed after step3. ~500-700MB RAM for ~15-30 seconds only.
- **`playwright-stealth`** patches common automation fingerprints (`navigator.webdriver`, CDP artifacts, etc.).
- **The public interface of `EDRReportGenerator` does not change** — `step1_submit_password()`, `step2_request_mfa_code()`, `step3_validate_mfa_code()` keep the same signatures and return types. The printing route code needs zero changes.
- **Async bridging** — Playwright's Python API is async. We use `asyncio.run()` (or `asyncio.get_event_loop().run_until_complete()`) to call async Playwright code from the synchronous step methods.

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `requirements.txt` | Modify | Add `playwright` and `playwright-stealth` |
| `app/integrations/edr/playwright_auth.py` | **Create** | Async Playwright authentication module |
| `app/integrations/edr/report_generator.py` | Modify | Replace steps 1-3 to delegate to playwright_auth |
| `tests/test_playwright_auth.py` | **Create** | Unit tests for the new auth module |

---

### Task 1: Install Dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Add playwright and playwright-stealth to requirements.txt**

Add these lines after the existing `requests` entries (around line 14):

```
# Browser Automation (for Walmart PerimeterX bypass)
playwright==1.50.0
playwright-stealth==1.0.6
```

**Step 2: Install the packages**

Run:
```bash
pip install playwright playwright-stealth
```
Expected: Successful installation

**Step 3: Install Playwright browsers**

Run:
```bash
playwright install chromium
```
Expected: Downloads Chromium browser binary (~130MB). Output includes path to installed browser.

**Step 4: Verify installation**

Run:
```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
python -c "from playwright_stealth import stealth_async; print('Stealth OK')"
```
Expected: Both print OK without errors.

**Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: add playwright and playwright-stealth dependencies for EDR auth"
```

---

### Task 2: Create Playwright Authentication Module

**Files:**
- Create: `app/integrations/edr/playwright_auth.py`
- Test: `tests/test_playwright_auth.py`

**Step 1: Write the failing test**

Create `tests/test_playwright_auth.py`:

```python
"""Tests for Playwright-based Walmart authentication module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


class TestPlaywrightAuth:
    """Test the PlaywrightWalmartAuth class."""

    def test_import(self):
        """Module can be imported."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        assert PlaywrightWalmartAuth is not None

    def test_init(self):
        """Constructor stores credentials."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth(
            username="testuser",
            password="testpass",
            mfa_credential_id="cred123"
        )
        assert auth.username == "testuser"
        assert auth.password == "testpass"
        assert auth.mfa_credential_id == "cred123"
        assert auth.cookies == []
        assert auth.last_error is None

    def test_extract_cookies_returns_list(self):
        """extract_cookies_for_requests returns cookie dicts."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        auth.cookies = [
            {"name": "auth", "value": "tok123", "domain": ".wal-mart.com", "path": "/"},
            {"name": "sid", "value": "sess456", "domain": ".wal-mart.com", "path": "/"},
        ]
        result = auth.extract_cookies_for_requests()
        assert len(result) == 2
        assert result[0]["name"] == "auth"
        assert result[1]["value"] == "sess456"

    def test_inject_cookies_into_session(self):
        """inject_cookies_into_session populates a requests.Session cookie jar."""
        import requests
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        auth.cookies = [
            {"name": "token", "value": "abc", "domain": ".wal-mart.com", "path": "/", "secure": True, "httpOnly": True},
        ]
        session = requests.Session()
        auth.inject_cookies_into_session(session)
        assert session.cookies.get("token") == "abc"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_playwright_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.integrations.edr.playwright_auth'`

**Step 3: Write the playwright_auth module**

Create `app/integrations/edr/playwright_auth.py`:

```python
"""
Playwright-based Walmart Retail Link Authentication
====================================================

Uses a real Chromium browser (via Playwright) to handle the PerimeterX-protected
login flow on retaillink.login.wal-mart.com. After successful authentication,
cookies are extracted and can be injected into a requests.Session for subsequent
API calls.

This module handles Steps 1-3 of the authentication flow:
  Step 1: Navigate to login page, submit username/password
  Step 2: Request MFA code via SMS
  Step 3: Validate the MFA code

Steps 4-6 (page registration, navigation, token extraction) remain in
report_generator.py using the cookie-injected requests.Session.
"""

import asyncio
import logging
from typing import List, Dict, Optional

from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import stealth_async

logger = logging.getLogger(__name__)

# Walmart auth URLs
LOGIN_PAGE_URL = "https://retaillink.login.wal-mart.com/login"
LOGIN_API_URL = "https://retaillink.login.wal-mart.com/api/login"
MFA_SEND_URL = "https://retaillink.login.wal-mart.com/api/mfa/sendCode"
MFA_VALIDATE_URL = "https://retaillink.login.wal-mart.com/api/mfa/validateCode"


class PlaywrightWalmartAuth:
    """Handles Walmart Retail Link authentication using Playwright.

    Launches a headless Chromium browser with stealth patches to bypass
    PerimeterX bot detection. The browser is only used for the login +
    MFA flow, then closed. Extracted cookies are transferred to a
    requests.Session for all subsequent API calls.
    """

    def __init__(self, username: str, password: str, mfa_credential_id: str):
        self.username = username
        self.password = password
        self.mfa_credential_id = mfa_credential_id
        self.cookies: List[Dict] = []
        self.last_error: Optional[str] = None

        # Internal state — kept alive between step1 and step3
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ------------------------------------------------------------------
    # Public synchronous interface (called from report_generator.py)
    # ------------------------------------------------------------------

    def step1_submit_password(self) -> bool:
        """Step 1: Launch browser, navigate to login, submit credentials.

        Returns True if password was accepted (MFA challenge expected next).
        """
        self.last_error = None
        try:
            return asyncio.run(self._async_step1())
        except Exception as e:
            self.last_error = f"Playwright step1 failed: {e}"
            logger.error(self.last_error)
            return False

    def step2_request_mfa_code(self) -> bool:
        """Step 2: Request MFA code to be sent via SMS.

        Must be called after step1_submit_password() succeeds.
        """
        self.last_error = None
        try:
            return asyncio.run(self._async_step2())
        except Exception as e:
            self.last_error = f"Playwright step2 failed: {e}"
            logger.error(self.last_error)
            return False

    def step3_validate_mfa_code(self, code: str) -> bool:
        """Step 3: Submit the user-provided MFA code, extract cookies, close browser.

        After this succeeds, self.cookies contains all browser cookies and
        the browser is closed.
        """
        self.last_error = None
        try:
            return asyncio.run(self._async_step3(code))
        except Exception as e:
            self.last_error = f"Playwright step3 failed: {e}"
            logger.error(self.last_error)
            return False

    def extract_cookies_for_requests(self) -> List[Dict]:
        """Return the stored cookies as a list of dicts."""
        return list(self.cookies)

    def inject_cookies_into_session(self, session) -> None:
        """Inject stored Playwright cookies into a requests.Session."""
        for cookie in self.cookies:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )

    def cleanup(self) -> None:
        """Force-close browser if still open. Safe to call multiple times."""
        try:
            if self._browser:
                asyncio.run(self._async_cleanup())
        except Exception:
            pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------
    # Async internals
    # ------------------------------------------------------------------

    async def _launch_browser(self) -> None:
        """Launch Playwright Chromium with stealth."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        self._page = await self._context.new_page()
        await stealth_async(self._page)

    async def _async_step1(self) -> bool:
        """Async implementation of step1."""
        logger.info("Playwright step1: launching browser and submitting password")
        await self._launch_browser()

        # Navigate to login page — this loads px.js and generates _px3 cookie
        logger.info("Navigating to login page...")
        await self._page.goto(LOGIN_PAGE_URL, wait_until="networkidle")
        # Small delay to let PX sensor complete fingerprinting
        await self._page.wait_for_timeout(2000)

        # Submit credentials via the page's fetch API (same as the login form does)
        logger.info("Submitting credentials via page context...")
        result = await self._page.evaluate(
            """async ({username, password}) => {
                try {
                    const resp = await fetch('/api/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({username, password, language: 'en'})
                    });
                    return {status: resp.status, body: await resp.text()};
                } catch (e) {
                    return {status: 0, body: e.message};
                }
            }""",
            {"username": self.username, "password": self.password},
        )

        status = result.get("status", 0)
        body = result.get("body", "")
        logger.info(f"Login response status: {status}")

        if status == 200:
            logger.info("Password accepted, MFA challenge expected")
            return True

        self.last_error = f"Walmart login returned HTTP {status}: {body[:300]}"
        logger.error(f"Step1 failed: {self.last_error}")
        await self._async_cleanup()
        return False

    async def _async_step2(self) -> bool:
        """Async implementation of step2."""
        if not self._page:
            self.last_error = "Browser not running — call step1 first"
            return False

        logger.info("Playwright step2: requesting MFA code")

        result = await self._page.evaluate(
            """async ({type, credid}) => {
                try {
                    const resp = await fetch('/api/mfa/sendCode', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({type, credid})
                    });
                    return {status: resp.status, body: await resp.text()};
                } catch (e) {
                    return {status: 0, body: e.message};
                }
            }""",
            {"type": "SMS_OTP", "credid": self.mfa_credential_id},
        )

        status = result.get("status", 0)
        body = result.get("body", "")
        logger.info(f"MFA sendCode response status: {status}")

        if status == 200:
            logger.info("MFA code sent successfully")
            return True

        self.last_error = f"MFA request returned HTTP {status}: {body[:300]}"
        logger.error(f"Step2 failed: {self.last_error}")
        return False

    async def _async_step3(self, code: str) -> bool:
        """Async implementation of step3."""
        if not self._page:
            self.last_error = "Browser not running — call step1 first"
            return False

        logger.info("Playwright step3: validating MFA code")

        result = await self._page.evaluate(
            """async ({type, credid, code}) => {
                try {
                    const resp = await fetch('/api/mfa/validateCode', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({type, credid, code, failureCount: 0})
                    });
                    return {status: resp.status, body: await resp.text()};
                } catch (e) {
                    return {status: 0, body: e.message};
                }
            }""",
            {"type": "SMS_OTP", "credid": self.mfa_credential_id, "code": code},
        )

        status = result.get("status", 0)
        body = result.get("body", "")
        logger.info(f"MFA validateCode response status: {status}")

        if status == 200:
            logger.info("MFA validation successful — extracting cookies")
            self.cookies = await self._context.cookies()
            logger.info(f"Extracted {len(self.cookies)} cookies from browser")
            await self._async_cleanup()
            return True

        self.last_error = f"MFA validation returned HTTP {status}: {body[:300]}"
        logger.error(f"Step3 failed: {self.last_error}")
        return False

    async def _async_cleanup(self) -> None:
        """Close browser and Playwright."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Cleanup error (non-fatal): {e}")
        self._browser = None
        self._playwright = None
        self._context = None
        self._page = None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_playwright_auth.py -v`
Expected: All 4 tests PASS (import, init, extract_cookies, inject_cookies)

**Step 5: Commit**

```bash
git add app/integrations/edr/playwright_auth.py tests/test_playwright_auth.py
git commit -m "feat: add Playwright-based Walmart auth module for PerimeterX bypass"
```

---

### Task 3: Integrate Playwright Auth into EDRReportGenerator

**Files:**
- Modify: `app/integrations/edr/report_generator.py` (lines 49-59, 74-91, 118-239, 241-273)

This is the critical integration task. We modify `EDRReportGenerator` to delegate Steps 1-3 to `PlaywrightWalmartAuth`, then transfer cookies into `self.session` for Steps 4-6.

**Step 1: Write the integration test**

Add to `tests/test_playwright_auth.py`:

```python
class TestEDRReportGeneratorIntegration:
    """Test that EDRReportGenerator delegates to PlaywrightWalmartAuth."""

    def test_report_generator_has_playwright_auth(self):
        """EDRReportGenerator creates a PlaywrightWalmartAuth internally."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        gen = EDRReportGenerator()
        gen.username = "testuser"
        gen.password = "testpass"
        gen.mfa_credential_id = "cred123"
        # _pw_auth is created lazily in step1, so it should be None initially
        assert gen._pw_auth is None

    def test_step1_creates_pw_auth(self):
        """step1_submit_password creates PlaywrightWalmartAuth and delegates."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        from unittest.mock import patch, MagicMock

        gen = EDRReportGenerator()
        gen.username = "testuser"
        gen.password = "testpass"
        gen.mfa_credential_id = "cred123"

        with patch('app.integrations.edr.report_generator.PlaywrightWalmartAuth') as MockPWAuth:
            mock_instance = MagicMock()
            mock_instance.step1_submit_password.return_value = True
            MockPWAuth.return_value = mock_instance

            result = gen.step1_submit_password()

            assert result is True
            MockPWAuth.assert_called_once_with("testuser", "testpass", "cred123")
            mock_instance.step1_submit_password.assert_called_once()

    def test_step3_transfers_cookies(self):
        """step3 extracts cookies from Playwright and injects into requests.Session."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        from unittest.mock import patch, MagicMock

        gen = EDRReportGenerator()
        gen.username = "u"
        gen.password = "p"
        gen.mfa_credential_id = "c"

        mock_pw = MagicMock()
        mock_pw.step3_validate_mfa_code.return_value = True
        mock_pw.cookies = [
            {"name": "auth-token", "value": "tok", "domain": ".wal-mart.com", "path": "/"},
        ]
        mock_pw.inject_cookies_into_session = MagicMock()
        gen._pw_auth = mock_pw

        result = gen.step3_validate_mfa_code("123456")

        assert result is True
        mock_pw.step3_validate_mfa_code.assert_called_once_with("123456")
        mock_pw.inject_cookies_into_session.assert_called_once_with(gen.session)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_playwright_auth.py::TestEDRReportGeneratorIntegration -v`
Expected: FAIL — `EDRReportGenerator` doesn't have `_pw_auth` attribute yet

**Step 3: Modify report_generator.py**

Make these specific changes to `app/integrations/edr/report_generator.py`:

**3a. Add import at top of file (after line 32, before the db_manager import):**

```python
# Import Playwright-based auth (graceful fallback if not installed)
try:
    from .playwright_auth import PlaywrightWalmartAuth
    _playwright_available = True
except ImportError:
    _playwright_available = False
    PlaywrightWalmartAuth = None
```

**3b. Add `_pw_auth` attribute in `__init__` (after line 59 `self.last_error = None`):**

```python
        # Playwright auth delegate (created lazily in step1)
        self._pw_auth = None
```

**3c. Remove `_get_initial_cookies` method entirely (lines 74-91).**

This method contains hardcoded stale PerimeterX cookies that are no longer used.

**3d. Replace `step1_submit_password` method (lines 118-187) with:**

```python
    def step1_submit_password(self) -> bool:
        """Step 1: Submit username and password.

        Delegates to Playwright for PerimeterX-protected login.
        Falls back to raw requests if Playwright is not installed.
        """
        self.last_error = None

        if _playwright_available:
            logger.info("Using Playwright for Walmart login (PerimeterX bypass)")
            self._pw_auth = PlaywrightWalmartAuth(
                self.username, self.password, self.mfa_credential_id
            )
            result = self._pw_auth.step1_submit_password()
            if not result:
                self.last_error = self._pw_auth.last_error
            return result

        # Fallback: raw requests (may fail with PerimeterX 412)
        logger.warning("Playwright not available — falling back to raw requests (may be blocked by PerimeterX)")
        return self._step1_requests_fallback()

    def _step1_requests_fallback(self) -> bool:
        """Legacy step1 using requests.Session (blocked by PerimeterX)."""
        login_url = "https://retaillink.login.wal-mart.com/api/login"
        self.last_error = None

        try:
            login_page_response = self.session.get(
                'https://retaillink.login.wal-mart.com/login',
                headers={
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
                timeout=15
            )
        except Exception as e:
            logger.warning(f"Could not pre-fetch login page: {e}")

        headers = self._get_standard_headers(content_type='application/json')
        headers['origin'] = 'https://retaillink.login.wal-mart.com'
        headers['referer'] = 'https://retaillink.login.wal-mart.com/login'

        payload = {"username": self.username, "password": self.password, "language": "en"}

        try:
            response = self.session.post(login_url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if hasattr(e, 'response') and e.response is not None else 'unknown'
            body = ''
            if hasattr(e, 'response') and e.response is not None:
                body = e.response.text[:300] if e.response.text else ''
            self.last_error = f"Walmart login returned HTTP {status}: {body}" if body else f"Walmart login returned HTTP {status}"
            return False
        except requests.exceptions.RequestException as e:
            self.last_error = f"Walmart login request failed: {e}"
            return False
```

Note: `logger` is used instead of `print()`. Add `import logging` at top and `logger = logging.getLogger(__name__)` after imports if not already present.

**3e. Replace `step2_request_mfa_code` method (lines 189-239) with:**

```python
    def step2_request_mfa_code(self) -> bool:
        """Step 2: Request MFA code. Delegates to Playwright if active."""
        self.last_error = None

        if self._pw_auth:
            result = self._pw_auth.step2_request_mfa_code()
            if not result:
                self.last_error = self._pw_auth.last_error
            return result

        # Fallback: raw requests
        return self._step2_requests_fallback()

    def _step2_requests_fallback(self) -> bool:
        """Legacy step2 using requests.Session."""
        send_code_url = "https://retaillink.login.wal-mart.com/api/mfa/sendCode"
        self.last_error = None
        headers = self._get_standard_headers(content_type='application/json')
        headers['origin'] = 'https://retaillink.login.wal-mart.com'
        headers['referer'] = 'https://retaillink.login.wal-mart.com/login'

        payload = {"type": "SMS_OTP", "credid": self.mfa_credential_id}

        try:
            response = self.session.post(send_code_url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if hasattr(e, 'response') and e.response is not None else 'unknown'
            body = ''
            if hasattr(e, 'response') and e.response is not None:
                body = e.response.text[:300] if e.response.text else ''
            self.last_error = f"MFA request returned HTTP {status}: {body}" if body else f"MFA request returned HTTP {status}"
            return False
        except requests.exceptions.RequestException as e:
            self.last_error = f"MFA request failed: {e}"
            return False
```

**3f. Replace `step3_validate_mfa_code` method (lines 241-273) with:**

```python
    def step3_validate_mfa_code(self, code: str) -> bool:
        """Step 3: Validate MFA code. If using Playwright, transfers cookies to session."""
        self.last_error = None

        if self._pw_auth:
            result = self._pw_auth.step3_validate_mfa_code(code)
            if not result:
                self.last_error = self._pw_auth.last_error
                return False

            # Transfer cookies from Playwright browser to requests.Session
            logger.info("Transferring Playwright cookies to requests.Session")
            self._pw_auth.inject_cookies_into_session(self.session)
            logger.info(f"Transferred {len(self._pw_auth.cookies)} cookies to session")

            # Clear Playwright reference (browser already closed by step3)
            self._pw_auth = None
            return True

        # Fallback: raw requests
        return self._step3_requests_fallback(code)

    def _step3_requests_fallback(self, code: str) -> bool:
        """Legacy step3 using requests.Session."""
        validate_url = "https://retaillink.login.wal-mart.com/api/mfa/validateCode"
        headers = self._get_standard_headers(content_type='application/json')
        headers['origin'] = 'https://retaillink.login.wal-mart.com'
        headers['referer'] = 'https://retaillink.login.wal-mart.com/login'

        payload = {
            "type": "SMS_OTP",
            "credid": self.mfa_credential_id,
            "code": code,
            "failureCount": 0
        }

        try:
            response = self.session.post(validate_url, headers=headers, json=payload)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException:
            self.last_error = "MFA validation failed. The code may have been incorrect."
            return False
```

**Step 4: Run all tests**

Run: `pytest tests/test_playwright_auth.py -v`
Expected: All 7 tests PASS

Run: `pytest -v`
Expected: All existing tests still pass (no regressions)

**Step 5: Commit**

```bash
git add app/integrations/edr/report_generator.py tests/test_playwright_auth.py
git commit -m "feat: integrate Playwright auth into EDRReportGenerator for PerimeterX bypass"
```

---

### Task 4: Handle Async Event Loop Edge Cases

**Files:**
- Modify: `app/integrations/edr/playwright_auth.py` (step methods)

Flask/Gunicorn may already have a running event loop (especially with gevent). `asyncio.run()` will fail if called inside an existing loop. We need to handle this.

**Step 1: Write the test**

Add to `tests/test_playwright_auth.py`:

```python
class TestAsyncBridging:
    """Test that sync wrappers handle existing event loops."""

    def test_run_async_helper_creates_loop_when_none_exists(self):
        """_run_async creates a new event loop when none is running."""
        from app.integrations.edr.playwright_auth import _run_async
        import asyncio

        async def coro():
            return 42

        result = _run_async(coro())
        assert result == 42
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_playwright_auth.py::TestAsyncBridging -v`
Expected: FAIL — `_run_async` not found

**Step 3: Add `_run_async` helper to playwright_auth.py**

Add this function before the class definition:

```python
def _run_async(coro):
    """Run an async coroutine from sync code, handling existing event loops.

    Uses asyncio.run() when no loop is running. If an event loop is already
    running (e.g. under gevent/gunicorn), creates a new thread to run the
    coroutine.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    # An event loop is already running — run in a new thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=120)
```

Then replace all `asyncio.run(self._async_stepX())` calls in the class with `_run_async(self._async_stepX())`.

**Step 4: Run tests**

Run: `pytest tests/test_playwright_auth.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app/integrations/edr/playwright_auth.py tests/test_playwright_auth.py
git commit -m "fix: handle existing event loops in Playwright async bridging"
```

---

### Task 5: Add Logging and Error Surfacing

**Files:**
- Modify: `app/integrations/edr/report_generator.py` (remove print statements)

The old step methods used `print()` for debug output. Replace any remaining `print()` calls in the report_generator with `logger.info/error/warning`. This task also ensures the `last_error` from Playwright is properly surfaced to the user through the printing route's error responses.

**Step 1: Search and replace print statements**

In `report_generator.py`, find all remaining `print("➡️` / `print("✅` / `print("❌` / `print("⚠️` / `print("🔍` / `print("🔑` / `print("📄` / `print(f"` patterns in steps 4-6 and data methods. Replace with `logger.info()` / `logger.error()` / `logger.warning()`.

There's no functional test for this — it's a cleanup. Verify with:

Run: `grep -n "^        print(" app/integrations/edr/report_generator.py | head -20`

Replace each `print(...)` with the appropriate `logger.info(...)`, `logger.error(...)`, or `logger.warning(...)`.

**Step 2: Run existing tests**

Run: `pytest -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add app/integrations/edr/report_generator.py
git commit -m "refactor: replace print statements with logger in report_generator"
```

---

### Task 6: Manual End-to-End Verification

**Files:** None (testing only)

**Step 1: Start the dev server**

Run: `FLASK_ENV=development python wsgi.py`

**Step 2: Navigate to the printing page**

Open `https://pceventmanager.site/printing` in Chrome.

**Step 3: Trigger EDR authentication**

Click "Generate Event Paperwork" with an event number. The MFA flow should:
1. Show "Requesting MFA code..." loading message
2. You receive an SMS with the MFA code (Playwright is running in background)
3. Enter the MFA code in the prompt
4. Authentication succeeds, paperwork generates

**Step 4: Check server logs**

Look for these log lines:
```
Using Playwright for Walmart login (PerimeterX bypass)
Playwright step1: launching browser and submitting password
Navigating to login page...
Login response status: 200
Password accepted, MFA challenge expected
Playwright step2: requesting MFA code
MFA sendCode response status: 200
MFA code sent successfully
Playwright step3: validating MFA code
MFA validation successful — extracting cookies
Extracted N cookies from browser
Transferring Playwright cookies to requests.Session
```

**Step 5: Verify no PerimeterX 412 errors**

Check that the console no longer shows `400 (Bad Request)` for `/printing/edr/request-mfa`.

**Step 6: Test fallback behavior**

Temporarily rename `playwright_auth.py` to `playwright_auth.py.bak`, restart server, and verify the old requests-based path still runs (will still get PX 412, but shouldn't crash).

Rename it back when done.

---

## Rollback Plan

If Playwright doesn't work (PerimeterX still blocks):

1. The `_playwright_available` flag means the code gracefully falls back to the old `requests` path
2. No changes were made to `printing.py` routes — the public API is unchanged
3. To fully rollback: revert the report_generator.py changes and delete playwright_auth.py

## Future Improvements

- **Cookie persistence**: Cache authenticated cookies in Redis/SQLite with TTL to avoid re-authenticating for every session
- **Headed mode fallback**: If headless is detected, try with `headless=False` + Xvfb virtual display
- **curl_cffi for API calls**: Replace `requests.Session` with `curl_cffi` to match browser TLS fingerprint for post-auth API calls (if PerimeterX validates on every request)
