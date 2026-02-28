"""
EDR Authentication Module
Handles Walmart Retail Link authentication and session management

Bot Detection Mitigations:
- No stale hardcoded cookies - visits login page fresh to get real ones
- Consistent Chrome version across all requests
- Human-like delays between authentication steps
- Detailed response logging to diagnose bot blocks
"""
import requests
import json
import time
import urllib.parse
import logging
from typing import Dict, Optional, Any

# Consistent browser version used across ALL requests
# Keep this in sync with routes.py _fetch_approved_events_with_session headers
CHROME_VERSION = '131'
USER_AGENT = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36'
SEC_CH_UA = f'"Google Chrome";v="{CHROME_VERSION}", "Chromium";v="{CHROME_VERSION}", "Not_A Brand";v="24"'


class EDRAuthenticator:
    """Handles authentication with Walmart Retail Link Event Management System"""

    def __init__(self, username: str, password: str, mfa_credential_id: str):
        self.session = requests.Session()
        self.base_url = "https://retaillink2.wal-mart.com/EventManagement"
        self.auth_token = None
        self.username = username
        self.password = password
        self.mfa_credential_id = mfa_credential_id
        self.logger = logging.getLogger(__name__)

    def _get_login_headers(self) -> Dict[str, str]:
        """Return headers for login domain requests (retaillink.login.wal-mart.com)"""
        return {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': USER_AGENT,
        }

    def _get_standard_headers(self, content_type: Optional[str] = None, referer: Optional[str] = None) -> Dict[str, str]:
        """Return standard headers for API requests on retaillink2 domain"""
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': USER_AGENT,
        }

        if content_type:
            headers['content-type'] = content_type

        if referer:
            headers['referer'] = referer

        if self.auth_token:
            headers['authorization'] = f'Bearer {self.auth_token}'

        return headers

    def _log_response_diagnostic(self, step_name: str, response: requests.Response):
        """Log detailed response info for diagnosing bot detection blocks"""
        self.logger.info(
            f"[{step_name}] status={response.status_code}, "
            f"url={response.url}, "
            f"content-type={response.headers.get('content-type', 'N/A')}, "
            f"body_preview={response.text[:300] if response.text else 'empty'}"
        )

        # Check for common bot detection indicators
        body_lower = response.text.lower() if response.text else ''
        ct = response.headers.get('content-type', '').lower()

        if response.status_code == 403:
            self.logger.warning(f"[{step_name}] GOT 403 FORBIDDEN - likely bot detection block")

        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 'not set')
            self.logger.warning(f"[{step_name}] GOT 429 RATE LIMITED - Retry-After: {retry_after}")

        if 'captcha' in body_lower or 'challenge' in body_lower or 'perimeterx' in body_lower:
            self.logger.warning(f"[{step_name}] BOT DETECTION: Response contains captcha/challenge content")

        if 'text/html' in ct and response.status_code == 200 and 'json' in (response.request.headers.get('accept', '')):
            self.logger.warning(f"[{step_name}] SUSPICIOUS: Expected JSON but got HTML - possible redirect to captcha page")

        # Log cookies received
        new_cookies = [c.name for c in response.cookies]
        if new_cookies:
            self.logger.info(f"[{step_name}] New cookies set: {new_cookies}")

        # Log if redirected
        if response.history:
            chain = ' -> '.join(str(r.status_code) + ' ' + r.url for r in response.history)
            self.logger.info(f"[{step_name}] Redirect chain: {chain} -> {response.status_code} {response.url}")

    def _human_delay(self, min_seconds: float = 1.0, max_seconds: float = 2.5):
        """Add a human-like delay between requests"""
        import random
        delay = random.uniform(min_seconds, max_seconds)
        self.logger.debug(f"Waiting {delay:.1f}s between requests")
        time.sleep(delay)

    def step1_submit_password(self) -> bool:
        """Submit username and password.

        First visits the login page to acquire fresh cookies (PerimeterX, etc.)
        instead of using stale hardcoded ones that trigger bot detection.
        """
        # Step 1a: Visit login page to get fresh cookies from Walmart's bot detection system
        self.session.cookies.clear()
        self.logger.info("[Step 1a] Visiting login page to acquire fresh cookies...")
        try:
            page_response = self.session.get(
                'https://retaillink.login.wal-mart.com/login',
                headers={
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'accept-language': 'en-US,en;q=0.9',
                    'sec-ch-ua': SEC_CH_UA,
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'none',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                    'user-agent': USER_AGENT,
                },
                timeout=15,
            )
            self._log_response_diagnostic("Step 1a - Login Page", page_response)
            cookie_names = [c.name for c in self.session.cookies]
            self.logger.info(f"[Step 1a] Acquired {len(cookie_names)} cookies: {cookie_names}")
        except Exception as e:
            self.logger.warning(f"[Step 1a] Could not pre-fetch login page: {e} - continuing anyway")

        self._human_delay(1.5, 3.0)

        # Step 1b: Submit credentials
        login_url = "https://retaillink.login.wal-mart.com/api/login"
        headers = self._get_login_headers()
        payload = {"username": self.username, "password": self.password, "language": "en"}

        self.logger.info("[Step 1b] Submitting password...")
        try:
            response = self.session.post(login_url, headers=headers, json=payload, timeout=15)
            self._log_response_diagnostic("Step 1b - Password", response)
            response.raise_for_status()
            self.logger.info("[Step 1b] Password accepted")
            return True
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"[Step 1b] Password submission failed: HTTP {e.response.status_code if e.response else 'N/A'}")
            if e.response is not None:
                self._log_response_diagnostic("Step 1b - FAILED", e.response)
            return False
        except Exception as e:
            self.logger.error(f"[Step 1b] Password submission failed: {str(e)}")
            return False

    def step2_request_mfa_code(self) -> bool:
        """Request MFA code"""
        self._human_delay(1.0, 2.0)

        send_code_url = "https://retaillink.login.wal-mart.com/api/mfa/sendCode"
        headers = self._get_login_headers()
        payload = {"type": "SMS_OTP", "credid": self.mfa_credential_id}

        self.logger.info("[Step 2] Requesting MFA code...")
        try:
            response = self.session.post(send_code_url, headers=headers, json=payload, timeout=15)
            self._log_response_diagnostic("Step 2 - MFA Request", response)
            response.raise_for_status()
            self.logger.info("[Step 2] MFA code sent successfully")
            return True
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"[Step 2] MFA code request failed: HTTP {e.response.status_code if e.response else 'N/A'}")
            if e.response is not None:
                self._log_response_diagnostic("Step 2 - FAILED", e.response)
            return False
        except Exception as e:
            self.logger.error(f"[Step 2] MFA code request failed: {str(e)}")
            return False

    def step3_validate_mfa_code(self, code: str) -> bool:
        """Validate MFA code"""
        self._human_delay(0.5, 1.5)

        validate_url = "https://retaillink.login.wal-mart.com/api/mfa/validateCode"
        headers = self._get_login_headers()
        payload = {
            "type": "SMS_OTP",
            "credid": self.mfa_credential_id,
            "code": code,
            "failureCount": 0
        }

        self.logger.info("[Step 3] Validating MFA code...")
        try:
            response = self.session.post(validate_url, headers=headers, json=payload, timeout=15)
            self._log_response_diagnostic("Step 3 - MFA Validate", response)
            response.raise_for_status()
            self.logger.info("[Step 3] MFA code validated successfully")
            return True
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"[Step 3] MFA validation failed: HTTP {e.response.status_code if e.response else 'N/A'}")
            if e.response is not None:
                self._log_response_diagnostic("Step 3 - FAILED", e.response)
            return False
        except Exception as e:
            self.logger.error(f"[Step 3] MFA validation failed: {str(e)}")
            return False

    def step4_register_page_access(self):
        """Register page access"""
        self._human_delay(1.0, 2.0)

        url = "https://retaillink2.wal-mart.com/rl_portal_services/api/Site/InsertRlPageDetails"
        params = {'pageId': '6', 'pageSubId': 'w6040', 'pageSubDesc': 'Event Management System'}
        headers = self._get_standard_headers(referer='https://retaillink2.wal-mart.com/rl_portal/')

        self.logger.info("[Step 4] Registering page access...")
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=10)
            self._log_response_diagnostic("Step 4 - Page Register", response)
        except Exception as e:
            self.logger.warning(f"[Step 4] Page registration failed (non-critical): {e}")

    def step5_navigate_to_event_management(self):
        """Navigate to Event Management"""
        self._human_delay(1.0, 2.0)

        nav_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-site',
            'upgrade-insecure-requests': '1',
            'user-agent': USER_AGENT,
        }

        self.logger.info("[Step 5] Navigating to Event Management...")
        try:
            response = self.session.get("https://retaillink2.wal-mart.com/rl_portal/", headers=nav_headers, timeout=10)
            self._log_response_diagnostic("Step 5a - Portal", response)
        except Exception as e:
            self.logger.warning(f"[Step 5a] Portal navigation failed (non-critical): {e}")

        self._human_delay(1.0, 2.0)

        try:
            response = self.session.get(f"{self.base_url}/", headers=nav_headers, timeout=10)
            self._log_response_diagnostic("Step 5b - Event Management", response)
        except Exception as e:
            self.logger.warning(f"[Step 5b] Event Management navigation failed (non-critical): {e}")

    def step6_authenticate_event_management(self) -> bool:
        """Get auth token from Event Management API"""
        self._human_delay(1.0, 2.0)

        auth_url = f"{self.base_url}/api/authenticate"
        headers = self._get_standard_headers(referer=f"{self.base_url}/")

        self.logger.info("[Step 6] Authenticating with Event Management API...")
        try:
            response = self.session.get(auth_url, headers=headers, timeout=10)
            self._log_response_diagnostic("Step 6 - Auth Token", response)

            if response.status_code == 200:
                # Extract auth token from cookies
                for cookie in self.session.cookies:
                    if cookie.name == 'auth-token' and cookie.value:
                        cookie_data = urllib.parse.unquote(cookie.value)
                        try:
                            token_data = json.loads(cookie_data)
                            self.auth_token = token_data.get('token')
                            if self.auth_token:
                                self.logger.info("[Step 6] Auth token extracted successfully")
                                return True
                        except json.JSONDecodeError as e:
                            self.logger.error(f"[Step 6] Failed to parse auth-token cookie as JSON: {e}")
                            self.logger.error(f"[Step 6] Cookie value: {cookie_data[:200]}")

                self.logger.error("[Step 6] No auth-token cookie found. Available cookies: "
                                  f"{[c.name for c in self.session.cookies]}")
            else:
                self.logger.error(f"[Step 6] Authentication failed with status {response.status_code}")
            return False
        except Exception as e:
            self.logger.error(f"[Step 6] Event Management auth failed: {str(e)}")
            return False

    def authenticate(self, mfa_code: str) -> bool:
        """Complete authentication flow with MFA code"""
        try:
            if not self.step1_submit_password():
                return False

            if not self.step2_request_mfa_code():
                return False

            if not self.step3_validate_mfa_code(mfa_code):
                return False

            self.step4_register_page_access()
            self.step5_navigate_to_event_management()

            if not self.step6_authenticate_event_management():
                return False

            return True
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            return False

    def get_edr_report(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get EDR report data for a specific event ID"""
        if not self.auth_token:
            self.logger.error("Not authenticated - cannot get EDR report")
            return None

        url = f"{self.base_url}/api/edrReport?id={event_id}"
        headers = self._get_standard_headers(referer=f"{self.base_url}/browse-event")

        self.logger.info(f"Retrieving EDR report for event {event_id}...")
        try:
            response = self.session.get(url, headers=headers, timeout=30)
            self._log_response_diagnostic(f"EDR Report {event_id}", response)
            response.raise_for_status()

            report_data = response.json()
            self.logger.info(f"EDR report retrieved successfully for event {event_id}")
            return report_data
        except Exception as e:
            self.logger.error(f"Failed to get EDR report for event {event_id}: {str(e)}")
            return None

    def get_approved_events(self, club_numbers: list, start_date: str, end_date: str,
                           event_types: Optional[list] = None) -> Optional[list]:
        """
        Get events with APPROVED status from Daily Scheduled Report.

        Args:
            club_numbers: List of club/store numbers (e.g., ['8135'])
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            event_types: Optional list of event type IDs (defaults to all types)

        Returns:
            List of approved events with details, or None if request fails
        """
        if not self.auth_token:
            self.logger.error("Not authenticated - cannot get approved events")
            return None

        url = f"{self.base_url}/api/store-event/daily-schedule-report"
        headers = self._get_standard_headers(
            content_type='application/json',
            referer=f"{self.base_url}/daily-scheduled-report"
        )

        # Default to all event types if not specified
        if event_types is None:
            event_types = list(range(1, 58))  # Event types 1-57

        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "eventType": event_types,
            "clubList": club_numbers,
            "walmartWeekYear": ""
        }

        self.logger.info(f"Fetching approved events for clubs {club_numbers} from {start_date} to {end_date}")

        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=60)
            self._log_response_diagnostic("Approved Events", response)
            response.raise_for_status()

            all_events = response.json()

            # Filter for APPROVED status only
            approved_events = [
                event for event in all_events
                if event.get('status', '').upper() == 'APPROVED'
            ]

            self.logger.info(f"Found {len(approved_events)} approved events out of {len(all_events)} total")
            return approved_events

        except Exception as e:
            self.logger.error(f"Failed to get approved events: {str(e)}")
            return None

    def roll_event(self, event_id: str, scheduled_date: str, club_id: str, walmart_user_id: str) -> Dict[str, Any]:
        """
        Roll an event to a new scheduled date in Walmart.

        Args:
            event_id: The Walmart event ID (e.g., '619688')
            scheduled_date: Target date in YYYY-MM-DD format (e.g., '2026-01-11')
            club_id: Club/store number (e.g., '8135')
            walmart_user_id: Walmart user ID from session (e.g., 'd2fr4w2')

        Returns:
            Dict with 'success' (bool) and optional 'message' or 'error'
        """
        if not self.auth_token:
            self.logger.error("Not authenticated - cannot roll event")
            return {'success': False, 'error': 'Not authenticated'}

        url = f"{self.base_url}/api/club-details"
        headers = self._get_standard_headers(
            content_type='application/json',
            referer=f"{self.base_url}/club-details"
        )

        payload = {
            "action": "update",
            "eventId": int(event_id),
            "eventStatusCode": 2,  # APPROVED status
            "userId": walmart_user_id,
            "clubId": int(club_id),
            "scheduledDate": scheduled_date
        }

        self.logger.info(f"Rolling event {event_id} to {scheduled_date} for club {club_id}")

        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=30)
            self._log_response_diagnostic(f"Roll Event {event_id}", response)
            response.raise_for_status()

            result = response.json() if response.text else {}
            self.logger.info(f"Successfully rolled event {event_id} to {scheduled_date}")
            return {'success': True, 'result': result}

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Failed to roll event {event_id}: {error_msg}")
            return {'success': False, 'error': error_msg}
