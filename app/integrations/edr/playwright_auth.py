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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stealth init script — injected before any page JS runs.
# Replaces the broken playwright_stealth package with targeted patches for
# PerimeterX detection vectors.
# ---------------------------------------------------------------------------

_STEALTH_JS = """
// 1. navigator.webdriver → false (not undefined)
Object.defineProperty(navigator, 'webdriver', {get: () => false});

// 2. navigator.languages — the playwright_stealth override was broken
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

// 3. navigator.platform — must match the User-Agent (Windows)
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});

// 4. navigator.plugins — headless has 0, real Chrome has several
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const makePlugin = (name, desc, filename, mimeType) => {
            const mt = {type: mimeType, suffixes: '', description: desc, enabledPlugin: null};
            const p = {name, description: desc, filename, length: 1, 0: mt, item: i => mt, namedItem: n => mt};
            mt.enabledPlugin = p;
            return p;
        };
        const plugins = [
            makePlugin('PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'),
            makePlugin('Chrome PDF Plugin', 'Portable Document Format', 'internal-pdf-viewer', 'application/x-google-chrome-pdf'),
            makePlugin('Chrome PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'),
            makePlugin('Native Client', '', 'internal-nacl-plugin', 'application/x-nacl'),
        ];
        plugins.item = i => plugins[i];
        plugins.namedItem = n => plugins.find(p => p.name === n);
        plugins.refresh = () => {};
        return plugins;
    }
});

// 5. navigator.mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const mimes = [
            {type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
            {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format'},
        ];
        mimes.item = i => mimes[i];
        mimes.namedItem = n => mimes.find(m => m.type === n);
        return mimes;
    }
});

// 6. window.chrome — give it a realistic shape
if (!window.chrome) { window.chrome = {}; }
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        connect: () => {},
        sendMessage: () => {},
        onMessage: {addListener: () => {}, removeListener: () => {}},
        id: undefined,
    };
}

// 7. Permissions.query — real Chrome returns 'denied' for notifications by default
const origQuery = window.Permissions?.prototype?.query;
if (origQuery) {
    window.Permissions.prototype.query = function(params) {
        if (params?.name === 'notifications') {
            return Promise.resolve({state: Notification.permission});
        }
        return origQuery.call(this, params);
    };
}

// 8. WebGL vendor/renderer — mask SwiftShader (headless giveaway)
const getParamOrig = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    // UNMASKED_VENDOR_WEBGL
    if (param === 0x9245) return 'Google Inc. (NVIDIA)';
    // UNMASKED_RENDERER_WEBGL
    if (param === 0x9246) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    return getParamOrig.call(this, param);
};

// 9. Remove Playwright/CDP artifacts
delete window.__playwright;
delete window.__pw_manual;
"""

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
        return future.result(timeout=120)


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
        if not self._browser and not self._playwright:
            return
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
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1920,1080",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        # Inject stealth patches before any page JS runs
        await self._context.add_init_script(_STEALTH_JS)
        self._page = await self._context.new_page()
        logger.debug("Stealth patches applied via init script")

    async def _async_step1(self) -> bool:
        """Async implementation of step1_submit_password."""
        self.last_error = None
        try:
            await self._launch_browser()

            logger.info("Navigating to Walmart login page")
            await self._page.goto(self.LOGIN_URL, wait_until="networkidle")

            # Give PX sensor time to fingerprint the browser — 5s allows the
            # sensor script to complete its full fingerprint collection cycle.
            logger.debug("Waiting for PX sensor fingerprinting")
            await self._page.wait_for_timeout(3000)

            # Simulate minimal human-like interaction so PX behavioral analysis
            # sees mouse movement before the login request.
            await self._page.mouse.move(960, 400)
            await self._page.wait_for_timeout(500)
            await self._page.mouse.move(800, 350)
            await self._page.wait_for_timeout(1500)

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
