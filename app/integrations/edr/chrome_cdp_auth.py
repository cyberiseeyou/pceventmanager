"""
Chrome Remote Debugging authenticator for Walmart Retail Link.

Launches a real Chrome browser with --remote-debugging-port, connects via CDP
(pychrome), and drives the login flow. PerimeterX sees a normal browser session.
"""
import json
import logging
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Dict, List, Optional

import requests as http_requests

logger = logging.getLogger(__name__)

DEFAULT_CDP_PORT = 9222
CHROME_BINARIES = ['google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium']
CHROME_STARTUP_TIMEOUT = 10


class ChromeEDRAuthenticator:
    """Drives Walmart Retail Link login via Chrome Remote Debugging (CDP)."""

    def __init__(self, cdp_port: int = DEFAULT_CDP_PORT):
        self.cdp_port = cdp_port
        self._chrome_process: Optional[subprocess.Popen] = None
        self._temp_profile_dir: Optional[str] = None
        self._browser = None
        self._tab = None
        self._cookies: List[Dict] = []
        self.last_error: Optional[str] = None

    def __del__(self):
        """Safety net: clean up Chrome if instance is garbage-collected."""
        if self._chrome_process is not None:
            self.cleanup()

    def _find_chrome_binary(self) -> Optional[str]:
        """Search for Chrome/Chromium binary in PATH.

        Checks in priority order: google-chrome, google-chrome-stable,
        chromium-browser, chromium. Returns the first found path or None.
        """
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

        If Chrome is already running on the configured port, reuses that instance.
        Otherwise, launches a new Chrome process with a temporary profile directory.

        Returns:
            True if Chrome is ready for CDP connections, False on failure.
            On failure, self.last_error contains a description of what went wrong.
        """
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
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info(f"Chrome launched (PID {self._chrome_process.pid})")
        except OSError as e:
            self.last_error = f"Failed to launch Chrome: {e}"
            self._cleanup_temp_profile()
            return False

        # Wait for Chrome to become ready for CDP connections
        deadline = time.time() + CHROME_STARTUP_TIMEOUT
        while time.time() < deadline:
            if self._is_chrome_running():
                logger.info("Chrome is ready for CDP connections")
                return True
            if self._chrome_process.poll() is not None:
                self.last_error = f"Chrome exited unexpectedly with code {self._chrome_process.returncode}"
                self._cleanup_temp_profile()
                return False
            time.sleep(0.5)

        self.last_error = f"Chrome did not start within {CHROME_STARTUP_TIMEOUT}s"
        self.cleanup()
        return False

    def connect(self) -> bool:
        """Connect to Chrome via CDP (Chrome DevTools Protocol).

        Requires pychrome to be installed. Connects to the browser, selects
        or creates a tab, and enables Network and Page domains.

        Returns:
            True if CDP connection is established, False on failure.
            On failure, self.last_error contains a description of what went wrong.
        """
        try:
            import pychrome
        except ImportError:
            self.last_error = "pychrome not installed. Run: pip install pychrome"
            return False

        try:
            self._browser = pychrome.Browser(url=f"http://127.0.0.1:{self.cdp_port}")
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
        """Clean up Chrome process and temporary profile directory.

        Stops the CDP tab, terminates (or kills) the Chrome process,
        and removes the temporary profile directory. Safe to call
        multiple times or when no process is running.
        """
        if self._tab:
            try:
                self._tab.stop()
            except Exception:
                pass
            self._tab = None

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
        """Remove the temporary Chrome profile directory if it exists."""
        if self._temp_profile_dir and os.path.exists(self._temp_profile_dir):
            try:
                shutil.rmtree(self._temp_profile_dir)
                logger.info(f"Cleaned up temp profile: {self._temp_profile_dir}")
            except OSError as e:
                logger.warning(f"Could not remove temp profile: {e}")
            self._temp_profile_dir = None

    # ── Login flow helpers ────────────────────────────────────────────

    def _evaluate_fetch(self, js_expression: str) -> dict:
        """Execute a JS fetch expression via CDP and return parsed JSON result.

        Calls Runtime.evaluate on the given expression, extracts the string
        value from the CDP result, and parses it as JSON.

        Args:
            js_expression: JavaScript expression that resolves to a JSON string.

        Returns:
            Parsed dict from the JSON string, or an error dict on failure.
        """
        try:
            cdp_result = self._tab.Runtime.evaluate(
                expression=js_expression,
                awaitPromise=True,
                returnByValue=True,
            )
            result_obj = cdp_result.get('result', {})
            value = result_obj.get('value')
            if value is None:
                return {'status': 'error', 'message': 'No value in CDP result'}
            return json.loads(value)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            return {'status': 'error', 'message': f'Failed to parse CDP result: {e}'}
        except Exception as e:
            return {'status': 'error', 'message': f'CDP evaluate failed: {e}'}

    def _human_delay(self, min_seconds: float, max_seconds: float) -> None:
        """Sleep for a random duration between min and max seconds."""
        time.sleep(random.uniform(min_seconds, max_seconds))

    # ── Cookie extraction and injection ─────────────────────────────────

    def extract_cookies(self) -> List[Dict]:
        """Extract Walmart-related cookies from Chrome via CDP.

        Calls Network.getCookies to get all cookies from the browser,
        filters to only those with 'wal-mart.com' in the domain, and
        stores them in self._cookies.

        Returns:
            List of cookie dicts filtered to Walmart domains.
            Returns empty list if no tab is connected or on error.
        """
        if not self._tab:
            logger.warning("Cannot extract cookies: no CDP tab connected")
            return []

        try:
            result = self._tab.Network.getCookies()
            all_cookies = result.get('cookies', [])
            filtered = [c for c in all_cookies if 'wal-mart.com' in c.get('domain', '')]
            self._cookies = filtered

            cookie_names = [c['name'] for c in filtered]
            logger.info(
                f"Extracted {len(filtered)} Walmart cookies from {len(all_cookies)} total: {cookie_names}"
            )
            return self._cookies
        except Exception as e:
            logger.error(f"Failed to extract cookies: {e}")
            return []

    def inject_cookies_into_session(self, session) -> int:
        """Inject stored Walmart cookies into a requests.Session.

        Args:
            session: A requests.Session instance to inject cookies into.

        Returns:
            Number of cookies injected. Returns 0 if no cookies are stored.
        """
        if not self._cookies:
            logger.warning("No cookies to inject (call extract_cookies first)")
            return 0

        count = 0
        for cookie in self._cookies:
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain', ''),
                path=cookie.get('path', '/'),
                secure=cookie.get('secure', False),
            )
            count += 1

        logger.info(f"Injected {count} cookies into requests session")
        return count

    # ── 3-step login flow ─────────────────────────────────────────────

    def step1_submit_credentials(self, username: str, password: str) -> bool:
        """Step 1: Navigate to login page and submit credentials.

        Args:
            username: Walmart Retail Link username.
            password: Walmart Retail Link password.

        Returns:
            True if login API returned status 'ok', False otherwise.
        """
        self.last_error = None
        try:
            # Wait for page load via event, not tab.wait() which blocks on tab stop
            load_event = threading.Event()
            self._tab.Page.loadEventFired = lambda **kwargs: load_event.set()
            self._tab.Page.navigate(url='https://retaillink.login.wal-mart.com/login')
            if not load_event.wait(timeout=15):
                self.last_error = "Login page load timed out after 15 seconds"
                logger.error(self.last_error)
                return False
            self._human_delay(2, 4)

            js = (
                "fetch('/api/login', {"
                "method: 'POST', "
                "headers: {'Content-Type': 'application/json'}, "
                f"body: JSON.stringify({{username: {json.dumps(username)}, password: {json.dumps(password)}, language: 'en'}})"
                "})"
                ".then(r => r.ok ? r.json().then(d => JSON.stringify({status: 'ok', data: d})) "
                "                : r.text().then(t => JSON.stringify({status: 'error', message: 'HTTP ' + r.status + ': ' + t.substring(0, 200)})))"
                ".catch(e => JSON.stringify({status: 'error', message: e.message}))"
            )

            result = self._evaluate_fetch(js)
            if result.get('status') == 'ok':
                logger.info("Step 1: Credentials submitted successfully")
                return True
            else:
                self.last_error = f"Step 1 failed: {result.get('message', 'Unknown error')}"
                logger.warning(self.last_error)
                return False
        except Exception as e:
            self.last_error = f"Step 1 exception: {e}"
            logger.error(self.last_error)
            return False

    def step2_request_mfa(self, mfa_credential_id: str) -> bool:
        """Step 2: Request an MFA code via SMS.

        Args:
            mfa_credential_id: The credential ID for MFA (from step 1 response).

        Returns:
            True if MFA send-code API returned status 'ok', False otherwise.
        """
        self.last_error = None
        try:
            self._human_delay(1, 2)

            js = (
                "fetch('/api/mfa/sendCode', {"
                "method: 'POST', "
                "headers: {'Content-Type': 'application/json'}, "
                f"body: JSON.stringify({{type: 'SMS_OTP', credid: {json.dumps(mfa_credential_id)}}})"
                "})"
                ".then(r => r.ok ? r.json().then(d => JSON.stringify({status: 'ok', data: d})) "
                "                : r.text().then(t => JSON.stringify({status: 'error', message: 'HTTP ' + r.status + ': ' + t.substring(0, 200)})))"
                ".catch(e => JSON.stringify({status: 'error', message: e.message}))"
            )

            result = self._evaluate_fetch(js)
            if result.get('status') == 'ok':
                logger.info("Step 2: MFA code requested successfully")
                return True
            else:
                self.last_error = f"Step 2 failed: {result.get('message', 'Unknown error')}"
                logger.warning(self.last_error)
                return False
        except Exception as e:
            self.last_error = f"Step 2 exception: {e}"
            logger.error(self.last_error)
            return False

    def step3_validate_mfa(self, mfa_credential_id: str, code: str) -> bool:
        """Step 3: Validate the MFA code.

        Args:
            mfa_credential_id: The credential ID for MFA.
            code: The MFA code received via SMS.

        Returns:
            True if MFA validation API returned status 'ok', False otherwise.
        """
        self.last_error = None
        try:
            self._human_delay(0.5, 1.5)

            js = (
                "fetch('/api/mfa/validateCode', {"
                "method: 'POST', "
                "headers: {'Content-Type': 'application/json'}, "
                f"body: JSON.stringify({{type: 'SMS_OTP', credid: {json.dumps(mfa_credential_id)}, code: {json.dumps(code)}, failureCount: 0}})"
                "})"
                ".then(r => r.ok ? r.json().then(d => JSON.stringify({status: 'ok', data: d})) "
                "                : r.text().then(t => JSON.stringify({status: 'error', message: 'HTTP ' + r.status + ': ' + t.substring(0, 200)})))"
                ".catch(e => JSON.stringify({status: 'error', message: e.message}))"
            )

            result = self._evaluate_fetch(js)
            if result.get('status') == 'ok':
                logger.info("Step 3: MFA validated successfully")
                return True
            else:
                self.last_error = f"Step 3 failed: {result.get('message', 'Unknown error')}"
                logger.warning(self.last_error)
                return False
        except Exception as e:
            self.last_error = f"Step 3 exception: {e}"
            logger.error(self.last_error)
            return False
