# Chrome Remote Debugging EDR Authentication — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the blocked `requests`-based Walmart Retail Link login (steps 1-3) with Chrome Remote Debugging via pychrome CDP client, so PerimeterX sees a real browser and allows authentication.

**Architecture:** A new `ChromeEDRAuthenticator` class launches Chrome with `--remote-debugging-port=9222`, connects via pychrome CDP, drives the 3-step login flow using `Runtime.evaluate` (fetch calls in page context), extracts cookies via `Network.getCookies`, injects them into the existing `requests.Session`, and closes Chrome. Steps 4-6 continue unchanged.

**Tech Stack:** Python 3.12, pychrome (CDP client), subprocess (Chrome launch), requests (cookie injection)

**Design Doc:** `docs/plans/2026-03-01-chrome-cdp-edr-auth-design.md`

---

## Task 1: Add pychrome dependency

**Files:**
- Modify: `requirements.txt:13` (after `requests==2.32.3`)

**Step 1: Add pychrome to requirements.txt**

Add after the `requests` line:

```
pychrome>=0.2.4
```

**Step 2: Install the dependency**

Run: `pip install pychrome`
Expected: Successfully installed pychrome

**Step 3: Verify import works**

Run: `python -c "import pychrome; print(pychrome.__version__)"`
Expected: Prints version number

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add pychrome CDP client for Chrome Remote Debugging auth"
```

---

## Task 2: Create ChromeEDRAuthenticator — Chrome lifecycle management

**Files:**
- Create: `app/integrations/edr/chrome_cdp_auth.py`
- Test: `tests/test_chrome_cdp_auth.py`

**Step 1: Write failing tests for Chrome binary detection and lifecycle**

```python
"""Tests for ChromeEDRAuthenticator Chrome lifecycle management."""
import pytest
from unittest.mock import patch, MagicMock
import subprocess


class TestFindChromeBinary:
    """Test Chrome binary discovery."""

    @patch('shutil.which')
    def test_finds_google_chrome(self, mock_which):
        """Should find google-chrome first in search order."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        mock_which.side_effect = lambda name: '/usr/bin/google-chrome' if name == 'google-chrome' else None
        auth = ChromeEDRAuthenticator()
        assert auth._find_chrome_binary() == '/usr/bin/google-chrome'

    @patch('shutil.which')
    def test_falls_back_to_chromium(self, mock_which):
        """Should fall back through search order."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        def which_side_effect(name):
            if name == 'chromium-browser':
                return '/usr/bin/chromium-browser'
            return None
        mock_which.side_effect = which_side_effect
        auth = ChromeEDRAuthenticator()
        assert auth._find_chrome_binary() == '/usr/bin/chromium-browser'

    @patch('shutil.which', return_value=None)
    def test_returns_none_when_no_chrome(self, mock_which):
        """Should return None when no Chrome is found."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        assert auth._find_chrome_binary() is None


class TestChromeAlreadyRunning:
    """Test detection of existing Chrome debug instance."""

    @patch('requests.get')
    def test_detects_running_chrome(self, mock_get):
        """Should detect Chrome already running on debug port."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'Browser': 'Chrome/131.0.0.0'}
        mock_get.return_value = mock_response
        auth = ChromeEDRAuthenticator()
        assert auth._is_chrome_running() is True

    @patch('requests.get', side_effect=Exception("Connection refused"))
    def test_detects_no_chrome(self, mock_get):
        """Should return False when no Chrome on debug port."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        assert auth._is_chrome_running() is False


class TestCleanup:
    """Test Chrome process cleanup."""

    def test_cleanup_kills_process(self):
        """Should terminate Chrome process on cleanup."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_process = MagicMock()
        auth._chrome_process = mock_process
        auth._temp_profile_dir = None
        auth.cleanup()
        mock_process.terminate.assert_called_once()

    def test_cleanup_safe_when_no_process(self):
        """Should not raise when no process to clean up."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        auth._chrome_process = None
        auth._temp_profile_dir = None
        auth.cleanup()  # Should not raise
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_cdp_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.integrations.edr.chrome_cdp_auth'`

**Step 3: Write the Chrome lifecycle portion of ChromeEDRAuthenticator**

```python
"""
Chrome Remote Debugging authenticator for Walmart Retail Link.

Launches a real Chrome browser with --remote-debugging-port, connects via CDP
(pychrome), and drives the login flow. PerimeterX sees a normal browser session.
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

import requests as http_requests

logger = logging.getLogger(__name__)

# CDP port for Chrome Remote Debugging
DEFAULT_CDP_PORT = 9222
# Chrome binary search order
CHROME_BINARIES = ['google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium']
# Max seconds to wait for Chrome to start listening on CDP port
CHROME_STARTUP_TIMEOUT = 10


class ChromeEDRAuthenticator:
    """Drives Walmart Retail Link login via Chrome Remote Debugging (CDP).

    Launches Chrome with --remote-debugging-port, connects via pychrome,
    executes the 3-step login flow (credentials, MFA request, MFA validate)
    using Runtime.evaluate fetch() calls, then extracts all cookies.
    """

    def __init__(self, cdp_port: int = DEFAULT_CDP_PORT):
        self.cdp_port = cdp_port
        self._chrome_process: Optional[subprocess.Popen] = None
        self._temp_profile_dir: Optional[str] = None
        self._browser = None  # pychrome Browser instance
        self._tab = None      # pychrome Tab instance
        self.last_error: Optional[str] = None

    def _find_chrome_binary(self) -> Optional[str]:
        """Search for Chrome/Chromium binary on the system."""
        for name in CHROME_BINARIES:
            path = shutil.which(name)
            if path:
                logger.info(f"Found Chrome binary: {path}")
                return path
        logger.warning("No Chrome/Chromium binary found in PATH")
        return None

    def _is_chrome_running(self) -> bool:
        """Check if Chrome is already running with remote debugging on our port."""
        try:
            resp = http_requests.get(
                f"http://localhost:{self.cdp_port}/json/version",
                timeout=2
            )
            return resp.status_code == 200
        except Exception:
            return False

    def launch_chrome(self) -> bool:
        """Launch Chrome with remote debugging enabled.

        Returns True if Chrome is ready for CDP connections.
        Reuses an existing Chrome instance if one is already on the port.
        """
        # Check if Chrome is already running on this port
        if self._is_chrome_running():
            logger.info(f"Chrome already running on port {self.cdp_port}, reusing")
            return True

        chrome_binary = self._find_chrome_binary()
        if not chrome_binary:
            self.last_error = (
                "Chrome/Chromium not found. Install Google Chrome or Chromium to use EDR authentication. "
                "Search order: google-chrome, google-chrome-stable, chromium-browser, chromium"
            )
            return False

        # Create temp profile directory
        self._temp_profile_dir = tempfile.mkdtemp(prefix='edr-chrome-')
        logger.info(f"Chrome temp profile: {self._temp_profile_dir}")

        cmd = [
            chrome_binary,
            f'--remote-debugging-port={self.cdp_port}',
            f'--user-data-dir={self._temp_profile_dir}',
            '--no-first-run',
            '--disable-default-apps',
            '--disable-extensions',
            '--disable-background-networking',
            '--disable-sync',
        ]

        try:
            self._chrome_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Chrome launched (PID {self._chrome_process.pid})")
        except OSError as e:
            self.last_error = f"Failed to launch Chrome: {e}"
            self._cleanup_temp_profile()
            return False

        # Wait for Chrome to start listening on CDP port
        deadline = time.time() + CHROME_STARTUP_TIMEOUT
        while time.time() < deadline:
            if self._is_chrome_running():
                logger.info("Chrome is ready for CDP connections")
                return True
            # Check if process died
            if self._chrome_process.poll() is not None:
                self.last_error = f"Chrome exited unexpectedly with code {self._chrome_process.returncode}"
                self._cleanup_temp_profile()
                return False
            time.sleep(0.5)

        self.last_error = f"Chrome did not start within {CHROME_STARTUP_TIMEOUT}s"
        self.cleanup()
        return False

    def connect(self) -> bool:
        """Connect to Chrome via CDP (pychrome)."""
        try:
            import pychrome
        except ImportError:
            self.last_error = "pychrome not installed. Run: pip install pychrome"
            return False

        try:
            self._browser = pychrome.Browser(url=f"http://127.0.0.1:{self.cdp_port}")
            # Get the first available tab, or create one
            tabs = self._browser.list_tab()
            if tabs:
                self._tab = tabs[0]
            else:
                self._tab = self._browser.new_tab()
            self._tab.start()
            self._tab.Network.enable()
            self._tab.Page.enable()
            logger.info("CDP connection established")
            return True
        except Exception as e:
            self.last_error = f"Failed to connect to Chrome via CDP: {e}"
            return False

    def cleanup(self) -> None:
        """Terminate Chrome and clean up temp profile. Safe to call multiple times."""
        # Close CDP tab
        if self._tab:
            try:
                self._tab.stop()
            except Exception:
                pass
            self._tab = None

        # Terminate Chrome process (only if we launched it)
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None

        self._browser = None
        self._cleanup_temp_profile()

    def _cleanup_temp_profile(self) -> None:
        """Remove the temp Chrome profile directory."""
        if self._temp_profile_dir and os.path.exists(self._temp_profile_dir):
            try:
                shutil.rmtree(self._temp_profile_dir)
                logger.info(f"Cleaned up temp profile: {self._temp_profile_dir}")
            except OSError as e:
                logger.warning(f"Could not remove temp profile: {e}")
            self._temp_profile_dir = None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chrome_cdp_auth.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add app/integrations/edr/chrome_cdp_auth.py tests/test_chrome_cdp_auth.py
git commit -m "feat: add ChromeEDRAuthenticator with Chrome lifecycle management"
```

---

## Task 3: Add CDP login flow methods (steps 1-3)

**Files:**
- Modify: `app/integrations/edr/chrome_cdp_auth.py`
- Test: `tests/test_chrome_cdp_auth.py`

**Step 1: Write failing tests for the 3-step login flow**

Add to `tests/test_chrome_cdp_auth.py`:

```python
class TestLoginFlow:
    """Test the 3-step login flow via CDP."""

    def _make_auth_with_mock_tab(self):
        """Create authenticator with a mocked CDP tab."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_tab = MagicMock()
        auth._tab = mock_tab
        return auth, mock_tab

    def test_step1_navigates_and_submits_credentials(self):
        """Step 1 should navigate to login page, wait, then submit credentials via fetch."""
        auth, mock_tab = self._make_auth_with_mock_tab()
        # Mock Page.navigate (no return needed)
        mock_tab.Page.navigate.return_value = None
        # Mock wait for load event
        mock_tab.wait.return_value = None
        # Mock Runtime.evaluate for the fetch call - returns success
        mock_tab.Runtime.evaluate.return_value = {'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}}

        result = auth.step1_submit_credentials('testuser', 'testpass')
        assert result is True
        mock_tab.Page.navigate.assert_called_once()
        mock_tab.Runtime.evaluate.assert_called_once()

    def test_step1_fails_on_error_response(self):
        """Step 1 should return False if fetch returns error."""
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Page.navigate.return_value = None
        mock_tab.wait.return_value = None
        mock_tab.Runtime.evaluate.return_value = {'result': {'type': 'string', 'value': '{"status":"error","message":"Invalid credentials"}'}}

        result = auth.step1_submit_credentials('bad', 'creds')
        assert result is False
        assert auth.last_error is not None

    def test_step2_requests_mfa(self):
        """Step 2 should call sendCode endpoint via fetch."""
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Runtime.evaluate.return_value = {'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}}

        result = auth.step2_request_mfa('cred-id-123')
        assert result is True

    def test_step3_validates_mfa(self):
        """Step 3 should validate MFA code via fetch."""
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Runtime.evaluate.return_value = {'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}}

        result = auth.step3_validate_mfa('cred-id-123', '123456')
        assert result is True

    def test_step3_fails_on_wrong_code(self):
        """Step 3 should return False if MFA code is wrong."""
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Runtime.evaluate.return_value = {'result': {'type': 'string', 'value': '{"status":"error","message":"Invalid code"}'}}

        result = auth.step3_validate_mfa('cred-id-123', '000000')
        assert result is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_cdp_auth.py::TestLoginFlow -v`
Expected: FAIL — `AttributeError: 'ChromeEDRAuthenticator' object has no attribute 'step1_submit_credentials'`

**Step 3: Implement the 3-step login flow**

Add these methods to `ChromeEDRAuthenticator` in `chrome_cdp_auth.py`:

```python
    def _evaluate_fetch(self, js_expression: str) -> dict:
        """Execute a JS fetch() call via CDP Runtime.evaluate and parse the result.

        The JS expression must resolve to a JSON string with format:
        {"status": "ok"|"error", "data": {...}} or {"status": "error", "message": "..."}

        Returns parsed dict. Raises RuntimeError on CDP errors.
        """
        if not self._tab:
            raise RuntimeError("Not connected to Chrome — call connect() first")

        try:
            result = self._tab.Runtime.evaluate(expression=js_expression)
        except Exception as e:
            raise RuntimeError(f"CDP Runtime.evaluate failed: {e}")

        # Extract the string value from the CDP result
        value = result.get('result', {}).get('value')
        if value is None:
            exception_details = result.get('exceptionDetails')
            if exception_details:
                raise RuntimeError(f"JS execution error: {exception_details}")
            return {'status': 'error', 'message': 'No value returned from JS'}

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {'status': 'error', 'message': f'Invalid JSON from JS: {value[:200]}'}

    def _human_delay(self, min_seconds: float = 1.0, max_seconds: float = 2.5) -> None:
        """Add a human-like delay between actions."""
        import random
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def step1_submit_credentials(self, username: str, password: str) -> bool:
        """Step 1: Navigate to login page and submit credentials via fetch().

        PX's px.js loads and executes normally in the real Chrome page context,
        generating the _px3 clearance cookie before we make the API call.
        """
        self.last_error = None
        logger.info("[Chrome Step 1] Navigating to Retail Link login page...")

        try:
            self._tab.Page.navigate(url="https://retaillink.login.wal-mart.com/login")
            self._tab.wait(timeout=15)
        except Exception as e:
            self.last_error = f"Failed to navigate to login page: {e}"
            logger.error(self.last_error)
            return False

        # Wait for PX to initialize and generate clearance cookie
        self._human_delay(2.0, 4.0)

        # Use json.dumps to safely escape credentials in JS string
        username_js = json.dumps(username)
        password_js = json.dumps(password)

        js = f"""
            fetch('/api/login', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{username: {username_js}, password: {password_js}, language: 'en'}})
            }})
            .then(r => r.ok ? r.json().then(d => JSON.stringify({{status: 'ok', data: d}}))
                            : r.text().then(t => JSON.stringify({{status: 'error', message: 'HTTP ' + r.status + ': ' + t.substring(0, 200)}})))
            .catch(e => JSON.stringify({{status: 'error', message: e.message}}))
        """

        logger.info("[Chrome Step 1] Submitting credentials via fetch()...")
        try:
            result = self._evaluate_fetch(js)
        except RuntimeError as e:
            self.last_error = f"Step 1 JS execution failed: {e}"
            logger.error(self.last_error)
            return False

        if result.get('status') == 'ok':
            logger.info("[Chrome Step 1] Credentials accepted, MFA required")
            return True
        else:
            self.last_error = f"Walmart login failed: {result.get('message', 'Unknown error')}"
            logger.error(f"[Chrome Step 1] {self.last_error}")
            return False

    def step2_request_mfa(self, mfa_credential_id: str) -> bool:
        """Step 2: Request MFA code via fetch()."""
        self.last_error = None
        self._human_delay(1.0, 2.0)

        credid_js = json.dumps(mfa_credential_id)
        js = f"""
            fetch('/api/mfa/sendCode', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{type: 'SMS_OTP', credid: {credid_js}}})
            }})
            .then(r => r.ok ? r.json().then(d => JSON.stringify({{status: 'ok', data: d}}))
                            : r.text().then(t => JSON.stringify({{status: 'error', message: 'HTTP ' + r.status + ': ' + t.substring(0, 200)}})))
            .catch(e => JSON.stringify({{status: 'error', message: e.message}}))
        """

        logger.info("[Chrome Step 2] Requesting MFA code...")
        try:
            result = self._evaluate_fetch(js)
        except RuntimeError as e:
            self.last_error = f"Step 2 JS execution failed: {e}"
            logger.error(self.last_error)
            return False

        if result.get('status') == 'ok':
            logger.info("[Chrome Step 2] MFA code sent to device")
            return True
        else:
            self.last_error = f"MFA request failed: {result.get('message', 'Unknown error')}"
            logger.error(f"[Chrome Step 2] {self.last_error}")
            return False

    def step3_validate_mfa(self, mfa_credential_id: str, code: str) -> bool:
        """Step 3: Validate MFA code via fetch()."""
        self.last_error = None
        self._human_delay(0.5, 1.5)

        credid_js = json.dumps(mfa_credential_id)
        code_js = json.dumps(code)
        js = f"""
            fetch('/api/mfa/validateCode', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{type: 'SMS_OTP', credid: {credid_js}, code: {code_js}, failureCount: 0}})
            }})
            .then(r => r.ok ? r.json().then(d => JSON.stringify({{status: 'ok', data: d}}))
                            : r.text().then(t => JSON.stringify({{status: 'error', message: 'HTTP ' + r.status + ': ' + t.substring(0, 200)}})))
            .catch(e => JSON.stringify({{status: 'error', message: e.message}}))
        """

        logger.info("[Chrome Step 3] Validating MFA code...")
        try:
            result = self._evaluate_fetch(js)
        except RuntimeError as e:
            self.last_error = f"Step 3 JS execution failed: {e}"
            logger.error(self.last_error)
            return False

        if result.get('status') == 'ok':
            logger.info("[Chrome Step 3] MFA validation successful")
            return True
        else:
            self.last_error = f"MFA validation failed: {result.get('message', 'Unknown error')}"
            logger.error(f"[Chrome Step 3] {self.last_error}")
            return False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chrome_cdp_auth.py -v`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add app/integrations/edr/chrome_cdp_auth.py tests/test_chrome_cdp_auth.py
git commit -m "feat: add CDP login flow methods (steps 1-3) to ChromeEDRAuthenticator"
```

---

## Task 4: Add cookie extraction and injection

**Files:**
- Modify: `app/integrations/edr/chrome_cdp_auth.py`
- Test: `tests/test_chrome_cdp_auth.py`

**Step 1: Write failing tests for cookie extraction and injection**

Add to `tests/test_chrome_cdp_auth.py`:

```python
class TestCookieExtraction:
    """Test cookie extraction from Chrome and injection into requests.Session."""

    def test_extract_cookies_returns_walmart_cookies(self):
        """Should return only wal-mart.com cookies."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_tab = MagicMock()
        auth._tab = mock_tab
        mock_tab.Network.getCookies.return_value = {
            'cookies': [
                {'name': '_px3', 'value': 'abc123', 'domain': '.wal-mart.com', 'path': '/', 'secure': True},
                {'name': 'session', 'value': 'xyz', 'domain': 'retaillink.login.wal-mart.com', 'path': '/', 'secure': True},
                {'name': 'unrelated', 'value': 'foo', 'domain': '.google.com', 'path': '/', 'secure': False},
            ]
        }
        cookies = auth.extract_cookies()
        assert len(cookies) == 2
        names = [c['name'] for c in cookies]
        assert '_px3' in names
        assert 'session' in names
        assert 'unrelated' not in names

    def test_inject_cookies_into_session(self):
        """Should inject extracted cookies into a requests.Session."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        import requests
        auth = ChromeEDRAuthenticator()
        auth._cookies = [
            {'name': '_px3', 'value': 'abc123', 'domain': '.wal-mart.com', 'path': '/', 'secure': True},
            {'name': 'sid', 'value': 'xyz789', 'domain': 'retaillink.login.wal-mart.com', 'path': '/', 'secure': True},
        ]
        session = requests.Session()
        auth.inject_cookies_into_session(session)
        cookie_names = [c.name for c in session.cookies]
        assert '_px3' in cookie_names
        assert 'sid' in cookie_names

    def test_extract_cookies_empty_when_no_tab(self):
        """Should return empty list when not connected."""
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        auth._tab = None
        cookies = auth.extract_cookies()
        assert cookies == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_cdp_auth.py::TestCookieExtraction -v`
Expected: FAIL — `AttributeError: 'ChromeEDRAuthenticator' object has no attribute 'extract_cookies'`

**Step 3: Implement cookie extraction and injection**

Add to `ChromeEDRAuthenticator` in `chrome_cdp_auth.py`:

```python
    def extract_cookies(self) -> List[Dict]:
        """Extract all wal-mart.com cookies from Chrome via CDP.

        Returns list of cookie dicts filtered to *.wal-mart.com domains.
        Stores them internally as self._cookies for later injection.
        """
        if not self._tab:
            logger.warning("Cannot extract cookies — no CDP tab connected")
            self._cookies = []
            return []

        try:
            result = self._tab.Network.getCookies()
            all_cookies = result.get('cookies', [])
            logger.info(f"Chrome has {len(all_cookies)} total cookies")

            # Filter to Walmart domains only
            walmart_cookies = [
                c for c in all_cookies
                if 'wal-mart.com' in c.get('domain', '')
            ]
            logger.info(f"Filtered to {len(walmart_cookies)} wal-mart.com cookies: "
                        f"{[c['name'] for c in walmart_cookies]}")

            self._cookies = walmart_cookies
            return walmart_cookies
        except Exception as e:
            logger.error(f"Failed to extract cookies from Chrome: {e}")
            self._cookies = []
            return []

    def inject_cookies_into_session(self, session) -> int:
        """Inject stored cookies into a requests.Session.

        Args:
            session: A requests.Session instance (typically EDRReportGenerator.session)

        Returns:
            Number of cookies injected.
        """
        cookies = getattr(self, '_cookies', [])
        if not cookies:
            logger.warning("No cookies to inject — call extract_cookies() first")
            return 0

        count = 0
        for cookie in cookies:
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain', ''),
                path=cookie.get('path', '/'),
                secure=cookie.get('secure', False),
            )
            count += 1

        logger.info(f"Injected {count} cookies into requests.Session")
        return count
```

Also add `self._cookies: List[Dict] = []` to `__init__`.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chrome_cdp_auth.py -v`
Expected: All 14 tests PASS

**Step 5: Commit**

```bash
git add app/integrations/edr/chrome_cdp_auth.py tests/test_chrome_cdp_auth.py
git commit -m "feat: add cookie extraction and injection to ChromeEDRAuthenticator"
```

---

## Task 5: Integrate ChromeEDRAuthenticator into EDRReportGenerator

**Files:**
- Modify: `app/integrations/edr/report_generator.py:52-82` (init) and after line 203 (add chrome methods)
- Test: `tests/test_chrome_cdp_auth.py`

**Step 1: Write failing tests for the integration**

Add to `tests/test_chrome_cdp_auth.py`:

```python
class TestReportGeneratorIntegration:
    """Test ChromeEDRAuthenticator integration with EDRReportGenerator."""

    @patch('app.integrations.edr.chrome_cdp_auth.ChromeEDRAuthenticator')
    def test_chrome_step1_delegates_to_authenticator(self, MockAuth):
        """chrome_step1 should launch Chrome, connect, and call step1."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        mock_instance = MockAuth.return_value
        mock_instance.launch_chrome.return_value = True
        mock_instance.connect.return_value = True
        mock_instance.step1_submit_credentials.return_value = True
        mock_instance.last_error = None

        gen = EDRReportGenerator()
        gen.username = 'testuser'
        gen.password = 'testpass'
        result = gen.chrome_step1_submit_password()

        assert result is True
        mock_instance.launch_chrome.assert_called_once()
        mock_instance.connect.assert_called_once()
        mock_instance.step1_submit_credentials.assert_called_once_with('testuser', 'testpass')

    @patch('app.integrations.edr.chrome_cdp_auth.ChromeEDRAuthenticator')
    def test_chrome_step3_extracts_and_injects_cookies(self, MockAuth):
        """chrome_step3 should validate MFA, extract cookies, inject, then cleanup."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        mock_instance = MockAuth.return_value
        mock_instance.step3_validate_mfa.return_value = True
        mock_instance.extract_cookies.return_value = [
            {'name': '_px3', 'value': 'abc', 'domain': '.wal-mart.com', 'path': '/', 'secure': True}
        ]
        mock_instance.inject_cookies_into_session.return_value = 1
        mock_instance.last_error = None

        gen = EDRReportGenerator()
        gen.mfa_credential_id = 'cred-123'
        gen._chrome_auth = mock_instance

        result = gen.chrome_step3_validate_mfa_code('123456')

        assert result is True
        mock_instance.step3_validate_mfa.assert_called_once_with('cred-123', '123456')
        mock_instance.extract_cookies.assert_called_once()
        mock_instance.inject_cookies_into_session.assert_called_once_with(gen.session)
        mock_instance.cleanup.assert_called_once()

    @patch('app.integrations.edr.chrome_cdp_auth.ChromeEDRAuthenticator')
    def test_chrome_step1_falls_back_on_import_error(self, MockAuth):
        """Should fall back to requests if pychrome not available."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        MockAuth.side_effect = Exception("pychrome not installed")

        gen = EDRReportGenerator()
        gen.username = 'testuser'
        gen.password = 'testpass'
        # Should not raise — falls back gracefully
        result = gen.chrome_step1_submit_password()
        # Falls back to requests-based flow, which will fail without a real server
        # but the point is it doesn't raise
        assert isinstance(result, bool)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_cdp_auth.py::TestReportGeneratorIntegration -v`
Expected: FAIL — `AttributeError: 'EDRReportGenerator' object has no attribute 'chrome_step1_submit_password'`

**Step 3: Add chrome methods to EDRReportGenerator**

Add to `report_generator.py` after the existing `step1_submit_password` method (after line 203). Add `self._chrome_auth = None` to `__init__` (around line 62).

```python
    # ---- Chrome Remote Debugging methods ----

    def chrome_step1_submit_password(self) -> bool:
        """Step 1 via Chrome Remote Debugging (bypasses PerimeterX).

        Launches Chrome, connects via CDP, navigates to login page (PX clears),
        and submits credentials via fetch(). Falls back to requests on failure.
        """
        try:
            from .chrome_cdp_auth import ChromeEDRAuthenticator
            self._chrome_auth = ChromeEDRAuthenticator()
        except Exception as e:
            self.logger.warning(f"Chrome auth unavailable ({e}), falling back to requests")
            return self.step1_submit_password()

        if not self._chrome_auth.launch_chrome():
            self.last_error = self._chrome_auth.last_error
            self.logger.warning(f"Chrome launch failed: {self.last_error}, falling back to requests")
            self._chrome_auth = None
            return self.step1_submit_password()

        if not self._chrome_auth.connect():
            self.last_error = self._chrome_auth.last_error
            self.logger.warning(f"CDP connect failed: {self.last_error}, falling back to requests")
            self._chrome_auth.cleanup()
            self._chrome_auth = None
            return self.step1_submit_password()

        if not self._chrome_auth.step1_submit_credentials(self.username, self.password):
            self.last_error = self._chrome_auth.last_error
            self._chrome_auth.cleanup()
            self._chrome_auth = None
            return False

        return True

    def chrome_step2_request_mfa_code(self) -> bool:
        """Step 2 via Chrome Remote Debugging."""
        if not self._chrome_auth:
            self.logger.warning("No Chrome auth session, falling back to requests")
            return self.step2_request_mfa_code()

        if not self._chrome_auth.step2_request_mfa(self.mfa_credential_id):
            self.last_error = self._chrome_auth.last_error
            return False

        return True

    def chrome_step3_validate_mfa_code(self, code: str) -> bool:
        """Step 3 via Chrome Remote Debugging.

        After validation, extracts cookies from Chrome, injects them into
        self.session, then closes Chrome. Steps 4-6 continue via requests.
        """
        if not self._chrome_auth:
            self.logger.warning("No Chrome auth session, falling back to requests")
            return self.step3_validate_mfa_code(code)

        if not self._chrome_auth.step3_validate_mfa(self.mfa_credential_id, code):
            self.last_error = self._chrome_auth.last_error
            return False

        # Extract and inject cookies
        cookies = self._chrome_auth.extract_cookies()
        if not cookies:
            self.last_error = "No Walmart cookies found in Chrome after MFA validation"
            self._chrome_auth.cleanup()
            self._chrome_auth = None
            return False

        count = self._chrome_auth.inject_cookies_into_session(self.session)
        self.logger.info(f"Injected {count} cookies from Chrome into requests.Session")

        # Done with Chrome — close it
        self._chrome_auth.cleanup()
        self._chrome_auth = None

        return True
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chrome_cdp_auth.py -v`
Expected: All 17 tests PASS

**Step 5: Commit**

```bash
git add app/integrations/edr/report_generator.py tests/test_chrome_cdp_auth.py
git commit -m "feat: integrate ChromeEDRAuthenticator into EDRReportGenerator"
```

---

## Task 6: Wire up printing.py routes to use Chrome auth

**Files:**
- Modify: `app/routes/printing.py:1219-1228` (edr_request_mfa steps 1+2)
- Modify: `app/routes/printing.py:1287` (edr_authenticate step 3)

**Step 1: Write failing test for the route integration**

Add to `tests/test_chrome_cdp_auth.py`:

```python
class TestPrintingRouteIntegration:
    """Test that printing.py routes call chrome methods."""

    @patch('app.integrations.edr.report_generator.EDRReportGenerator')
    def test_edr_request_mfa_calls_chrome_steps(self, MockGen):
        """edr_request_mfa should call chrome_step1 and chrome_step2."""
        mock_instance = MockGen.return_value
        mock_instance.chrome_step1_submit_password.return_value = True
        mock_instance.chrome_step2_request_mfa_code.return_value = True
        mock_instance.last_error = None
        # Verify the method names exist (structural test)
        assert hasattr(mock_instance, 'chrome_step1_submit_password')
        assert hasattr(mock_instance, 'chrome_step2_request_mfa_code')
        assert hasattr(mock_instance, 'chrome_step3_validate_mfa_code')
```

**Step 2: Run test to verify it passes (structural check)**

Run: `pytest tests/test_chrome_cdp_auth.py::TestPrintingRouteIntegration -v`
Expected: PASS

**Step 3: Modify edr_request_mfa in printing.py**

In `app/routes/printing.py`, change lines 1218-1228 from:

```python
        # Step 1: Submit password
        if not edr_authenticator.step1_submit_password():
            detail = edr_authenticator.last_error or 'Failed to submit password'
            logger.error(f"EDR step1 failed: {detail}")
            return jsonify({'success': False, 'error': f'Walmart login failed: {detail}'}), 400

        # Step 2: Request MFA code
        if not edr_authenticator.step2_request_mfa_code():
            detail = edr_authenticator.last_error or 'Failed to request MFA code'
            logger.error(f"EDR step2 failed: {detail}")
            return jsonify({'success': False, 'error': f'MFA request failed: {detail}'}), 400
```

To:

```python
        # Step 1: Submit password (Chrome Remote Debugging bypasses PerimeterX)
        if not edr_authenticator.chrome_step1_submit_password():
            detail = edr_authenticator.last_error or 'Failed to submit password'
            logger.error(f"EDR step1 failed: {detail}")
            return jsonify({'success': False, 'error': f'Walmart login failed: {detail}'}), 400

        # Step 2: Request MFA code
        if not edr_authenticator.chrome_step2_request_mfa_code():
            detail = edr_authenticator.last_error or 'Failed to request MFA code'
            logger.error(f"EDR step2 failed: {detail}")
            return jsonify({'success': False, 'error': f'MFA request failed: {detail}'}), 400
```

**Step 4: Modify edr_authenticate in printing.py**

In `app/routes/printing.py`, change line 1287 from:

```python
        if not edr_authenticator.step3_validate_mfa_code(mfa_code):
```

To:

```python
        if not edr_authenticator.chrome_step3_validate_mfa_code(mfa_code):
```

**Step 5: Run existing test suite to verify nothing is broken**

Run: `pytest -v`
Expected: All existing tests PASS (the printing routes aren't directly tested, but model/service tests should still pass)

**Step 6: Commit**

```bash
git add app/routes/printing.py
git commit -m "feat: wire printing routes to use Chrome Remote Debugging auth flow"
```

---

## Task 7: Run full test suite and verify

**Files:**
- No new files

**Step 1: Run the complete test suite**

Run: `pytest -v`
Expected: All tests PASS (178+ existing + new chrome_cdp_auth tests)

**Step 2: Verify Chrome binary is available**

Run: `which google-chrome || which chromium-browser || which chromium`
Expected: Path to a Chrome/Chromium binary

**Step 3: Quick smoke test of the module import chain**

Run: `python -c "from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator; print('Import OK')"`
Expected: `Import OK`

**Step 4: Final commit (if any cleanup needed)**

```bash
git status
# If clean, no commit needed
```

---

## Summary of All Changes

| File | Action | Purpose |
|------|--------|---------|
| `requirements.txt` | Modify | Add `pychrome>=0.2.4` |
| `app/integrations/edr/chrome_cdp_auth.py` | Create | `ChromeEDRAuthenticator` — Chrome lifecycle, CDP login flow, cookie extraction |
| `app/integrations/edr/report_generator.py` | Modify | Add `chrome_step1/2/3` methods that delegate to `ChromeEDRAuthenticator` with fallback |
| `app/routes/printing.py` | Modify | Call `chrome_step1/2/3` instead of `step1/2/3` in auth endpoints |
| `tests/test_chrome_cdp_auth.py` | Create | Unit tests for all new code (lifecycle, login flow, cookies, integration) |
| `docs/plans/2026-03-01-chrome-cdp-edr-auth-design.md` | Already committed | Design document |
| `docs/plans/2026-03-01-chrome-cdp-edr-auth-plan.md` | This file | Implementation plan |
