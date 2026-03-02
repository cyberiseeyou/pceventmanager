"""
Chrome Remote Debugging authenticator for Walmart Retail Link.

Launches a real Chrome browser with --remote-debugging-port, connects via CDP
(pychrome), and drives the login flow. PerimeterX sees a normal browser session.
"""
import logging
import os
import shutil
import subprocess
import tempfile
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
