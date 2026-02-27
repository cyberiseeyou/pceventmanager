"""
Playwright-based Walmart Retail Link Authentication
====================================================

Replaces the requests-based auth flow with Playwright Chromium + stealth patches
to bypass PerimeterX (PX) bot detection that blocks direct HTTP requests (HTTP 412).

Flow:
  1. step1_submit_password() - Launch browser, navigate to login page, POST credentials
     via in-page fetch() so PX sensor cookies (_px3, _pxvid) are sent naturally.
  2. step2_request_mfa_code() - Request SMS OTP from the same browser context.
  3. step3_validate_mfa_code(code) - Validate the OTP, extract all cookies, close browser.

After step3, cookies can be injected into a requests.Session for subsequent API calls.

All public methods are synchronous (Flask routes are sync). Async internals are
delegated through _run_async() which handles both "no loop" and "loop already running"
scenarios.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Async helper — runs a coroutine from synchronous code
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine from synchronous code.

    - If no event loop is running, uses asyncio.run().
    - If a loop IS already running (e.g. inside Flask/gevent/Jupyter),
      dispatches asyncio.run(coro) into a background thread so we don't
      block the existing loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop running — safe to use asyncio.run directly
        return asyncio.run(coro)

    # A loop is already running — run in a separate thread
    logger.debug("Existing event loop detected; running async code in thread pool")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class PlaywrightWalmartAuth:
    """Handles Walmart Retail Link authentication using Playwright.

    Uses a headless Chromium browser with stealth patches so that PerimeterX
    sensor scripts run naturally and the _px3 cookie is valid for subsequent
    fetch() calls made from the page context.
    """

    LOGIN_URL = "https://retaillink.login.wal-mart.com/login"
    LOGIN_API = "/api/login"
    MFA_SEND_API = "/api/mfa/sendCode"
    MFA_VALIDATE_API = "/api/mfa/validateCode"

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    )

    def __init__(self, username: str, password: str, mfa_credential_id: str):
        self.username = username
        self.password = password
        self.mfa_credential_id = mfa_credential_id

        self.cookies: List[Dict] = []
        self.last_error: Optional[str] = None

        # Internal Playwright state — populated by _launch_browser()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------
    # Public synchronous API
    # ------------------------------------------------------------------

    def step1_submit_password(self) -> bool:
        """Step 1: Launch browser, navigate to login, POST credentials.

        Returns True if the server responded HTTP 200, False otherwise.
        The browser is kept alive for step2/step3.
        """
        return _run_async(self._async_step1())

    def step2_request_mfa_code(self) -> bool:
        """Step 2: Request MFA SMS OTP code.

        Returns True if the server responded HTTP 200, False otherwise.
        """
        return _run_async(self._async_step2())

    def step3_validate_mfa_code(self, code: str) -> bool:
        """Step 3: Validate the MFA OTP code.

        On success, extracts all browser cookies and closes the browser.
        Returns True if the server responded HTTP 200, False otherwise.
        """
        return _run_async(self._async_step3(code))

    def extract_cookies_for_requests(self) -> List[Dict]:
        """Return a copy of the extracted browser cookies as a list of dicts."""
        return list(self.cookies)

    def inject_cookies_into_session(self, session) -> None:
        """Populate a ``requests.Session`` cookie jar with extracted cookies.

        Args:
            session: A ``requests.Session`` instance.
        """
        for cookie in self.cookies:
            session.cookies.set(
                cookie.get("name", ""),
                cookie.get("value", ""),
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )

    def cleanup(self) -> None:
        """Force-close the browser if still open. Safe to call multiple times."""
        _run_async(self._async_cleanup())

    # ------------------------------------------------------------------
    # Async internals
    # ------------------------------------------------------------------

    async def _launch_browser(self) -> None:
        """Start Playwright, launch Chromium with stealth, create page."""
        logger.info("Launching Playwright Chromium (headless, stealth)")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        self._page = await self._context.new_page()
        await stealth_async(self._page)
        logger.debug("Stealth patches applied to page")

    async def _async_step1(self) -> bool:
        """Async implementation of step1_submit_password."""
        self.last_error = None
        try:
            await self._launch_browser()

            logger.info("Navigating to Walmart login page")
            await self._page.goto(self.LOGIN_URL, wait_until="networkidle")

            # Give PX sensor time to fingerprint the browser
            logger.debug("Waiting 2s for PX sensor fingerprinting")
            await self._page.wait_for_timeout(2000)

            # Execute the login fetch from the page's JS context so that
            # all cookies (including _px3) are sent automatically.
            js_code = """
            async ({username, password}) => {
                const resp = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password, language: 'en'})
                });
                return {status: resp.status, body: await resp.text()};
            }
            """
            result = await self._page.evaluate(
                js_code,
                {"username": self.username, "password": self.password},
            )

            status = result.get("status", 0)
            body = result.get("body", "")

            if status == 200:
                logger.info("Step 1 succeeded — password accepted, MFA required")
                return True
            else:
                self.last_error = (
                    f"Login API returned HTTP {status}: {body[:300]}"
                )
                logger.warning("Step 1 failed: %s", self.last_error)
                await self._async_cleanup()
                return False

        except Exception as exc:
            self.last_error = f"Step 1 error: {exc}"
            logger.error("Step 1 exception: %s", exc, exc_info=True)
            await self._async_cleanup()
            return False

    async def _async_step2(self) -> bool:
        """Async implementation of step2_request_mfa_code."""
        self.last_error = None
        try:
            if not self._page:
                self.last_error = "Browser not running — call step1 first"
                logger.error(self.last_error)
                return False

            js_code = """
            async ({credid}) => {
                const resp = await fetch('/api/mfa/sendCode', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: 'SMS_OTP', credid})
                });
                return {status: resp.status, body: await resp.text()};
            }
            """
            result = await self._page.evaluate(
                js_code,
                {"credid": self.mfa_credential_id},
            )

            status = result.get("status", 0)
            body = result.get("body", "")

            if status == 200:
                logger.info("Step 2 succeeded — MFA code sent")
                return True
            else:
                self.last_error = (
                    f"MFA sendCode returned HTTP {status}: {body[:300]}"
                )
                logger.warning("Step 2 failed: %s", self.last_error)
                return False

        except Exception as exc:
            self.last_error = f"Step 2 error: {exc}"
            logger.error("Step 2 exception: %s", exc, exc_info=True)
            return False

    async def _async_step3(self, code: str) -> bool:
        """Async implementation of step3_validate_mfa_code."""
        self.last_error = None
        try:
            if not self._page:
                self.last_error = "Browser not running — call step1 first"
                logger.error(self.last_error)
                return False

            js_code = """
            async ({credid, code}) => {
                const resp = await fetch('/api/mfa/validateCode', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        type: 'SMS_OTP',
                        credid,
                        code,
                        failureCount: 0
                    })
                });
                return {status: resp.status, body: await resp.text()};
            }
            """
            result = await self._page.evaluate(
                js_code,
                {"credid": self.mfa_credential_id, "code": code},
            )

            status = result.get("status", 0)
            body = result.get("body", "")

            if status == 200:
                logger.info("Step 3 succeeded — MFA validated, extracting cookies")
                self.cookies = await self._context.cookies()
                logger.info("Extracted %d cookies from browser", len(self.cookies))
                await self._async_cleanup()
                return True
            else:
                self.last_error = (
                    f"MFA validateCode returned HTTP {status}: {body[:300]}"
                )
                logger.warning("Step 3 failed: %s", self.last_error)
                return False

        except Exception as exc:
            self.last_error = f"Step 3 error: {exc}"
            logger.error("Step 3 exception: %s", exc, exc_info=True)
            return False

    async def _async_cleanup(self) -> None:
        """Close browser and stop Playwright. Safe to call multiple times."""
        if self._browser:
            try:
                await self._browser.close()
                logger.debug("Browser closed")
            except Exception as exc:
                logger.warning("Error closing browser: %s", exc)
            self._browser = None
            self._context = None
            self._page = None

        if self._playwright:
            try:
                await self._playwright.stop()
                logger.debug("Playwright stopped")
            except Exception as exc:
                logger.warning("Error stopping Playwright: %s", exc)
            self._playwright = None
