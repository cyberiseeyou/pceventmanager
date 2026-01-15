"""
EDR Authentication Module
Handles Walmart Retail Link authentication and session management
"""
import requests
import json
import urllib.parse
import logging
from typing import Dict, Optional, Any


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

    def _get_initial_cookies(self) -> Dict[str, str]:
        """Return initial cookies required for authentication"""
        return {
            'vtc': 'Q0JqQVX0STHy6sao9qdhNw',
            '_pxvid': '3c803a96-548a-11f0-84bf-e045250e632c',
            '_ga': 'GA1.2.103605184.1751648140',
            'QuantumMetricUserID': '23bc666aa80d92de6f4ffa5b79ff9fdc',
            'pxcts': 'd0d1b4d9-65f2-11f0-a59e-62912b00fffc',
            'rl_access_attempt': '0',
            'rlLoginInfo': '',
            'bstc': 'ZpNiPcM5OgU516Fy1nOhHw',
            'rl_show_login_form': 'N',
        }

    def _get_standard_headers(self, content_type: Optional[str] = None, referer: Optional[str] = None) -> Dict[str, str]:
        """Return standard headers for API requests"""
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        }

        if content_type:
            headers['content-type'] = content_type

        if referer:
            headers['referer'] = referer

        if self.auth_token:
            headers['authorization'] = f'Bearer {self.auth_token}'

        return headers

    def step1_submit_password(self) -> bool:
        """Submit username and password"""
        login_url = "https://retaillink.login.wal-mart.com/api/login"
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'priority': 'u=1, i',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }

        # Clear all existing cookies and set initial cookies
        self.session.cookies.clear()
        for name, value in self._get_initial_cookies().items():
            self.session.cookies.set(name, value)

        payload = {"username": self.username, "password": self.password, "language": "en"}

        try:
            response = self.session.post(login_url, headers=headers, json=payload)
            response.raise_for_status()
            self.logger.info("Password accepted")
            return True
        except Exception as e:
            self.logger.error(f"Password submission failed: {str(e)}")
            return False

    def step2_request_mfa_code(self) -> bool:
        """Request MFA code"""
        send_code_url = "https://retaillink.login.wal-mart.com/api/mfa/sendCode"
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }
        payload = {"type": "SMS_OTP", "credid": self.mfa_credential_id}

        try:
            response = self.session.post(send_code_url, headers=headers, json=payload)
            response.raise_for_status()
            self.logger.info("MFA code sent successfully")
            return True
        except Exception as e:
            self.logger.error(f"MFA code request failed: {str(e)}")
            return False

    def step3_validate_mfa_code(self, code: str) -> bool:
        """Validate MFA code"""
        validate_url = "https://retaillink.login.wal-mart.com/api/mfa/validateCode"
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }
        payload = {
            "type": "SMS_OTP",
            "credid": self.mfa_credential_id,
            "code": code,
            "failureCount": 0
        }

        try:
            response = self.session.post(validate_url, headers=headers, json=payload)
            response.raise_for_status()
            self.logger.info("MFA code validated successfully")
            return True
        except Exception as e:
            self.logger.error(f"MFA validation failed: {str(e)}")
            return False

    def step4_register_page_access(self):
        """Register page access"""
        url = "https://retaillink2.wal-mart.com/rl_portal_services/api/Site/InsertRlPageDetails"
        params = {'pageId': '6', 'pageSubId': 'w6040', 'pageSubDesc': 'Event Management System'}
        try:
            self.session.get(url, params=params, timeout=10)
        except:
            pass

    def step5_navigate_to_event_management(self):
        """Navigate to Event Management"""
        try:
            self.session.get("https://retaillink2.wal-mart.com/rl_portal/", timeout=10)
            self.session.get(f"{self.base_url}/", timeout=10)
        except:
            pass

    def step6_authenticate_event_management(self) -> bool:
        """Get auth token from Event Management API"""
        auth_url = f"{self.base_url}/api/authenticate"

        try:
            response = self.session.get(auth_url, timeout=10)
            if response.status_code == 200:
                # Extract auth token from cookies
                for cookie in self.session.cookies:
                    if cookie.name == 'auth-token' and cookie.value:
                        cookie_data = urllib.parse.unquote(cookie.value)
                        try:
                            token_data = json.loads(cookie_data)
                            self.auth_token = token_data.get('token')
                            if self.auth_token:
                                self.logger.info("Authentication successful")
                                return True
                        except:
                            pass
            return False
        except Exception as e:
            self.logger.error(f"Event Management auth failed: {str(e)}")
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
            response.raise_for_status()

            result = response.json() if response.text else {}
            self.logger.info(f"Successfully rolled event {event_id} to {scheduled_date}")
            return {'success': True, 'result': result}

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Failed to roll event {event_id}: {error_msg}")
            return {'success': False, 'error': error_msg}
