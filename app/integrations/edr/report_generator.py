"""
EDR (Event Detail Report) Generator
==================================

This module provides functionality to generate Event Detail Reports from Walmart's Retail Link
Event Management System. It combines the authentication flow from testing_api_clean.py with
the EDR report generation capabilities derived from the provided cURL commands and frontend code.

Dependencies:
- requests: HTTP client library
- json: JSON handling
- datetime: Date/time utilities
- typing: Type hints

Usage:
    from edr_report_generator import EDRReportGenerator
    
    generator = EDRReportGenerator()
    generator.authenticate()  # Interactive authentication
    report_data = generator.get_edr_report(event_id="606034")
    html_report = generator.generate_html_report(report_data)
"""

import requests
import json
import datetime
import time
import random
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
import urllib.parse
import tempfile
import os
import subprocess
import platform

# Import database manager for caching
from .db_manager import EDRDatabaseManager


class EDRReportGenerator:
    """
    Event Detail Report Generator for Walmart Retail Link Event Management System.
    
    This class handles:
    1. Multi-factor authentication with Retail Link
    2. Event browsing and filtering
    3. EDR report data retrieval
    4. HTML report generation with print styling
    """
    
    def __init__(self, enable_caching: bool = True, cache_max_age_hours: int = 24, db_path: Optional[str] = None):
        self.session = requests.Session()
        self.base_url = "https://retaillink2.wal-mart.com/EventManagement"
        self.auth_token = None
        self.user_data = None

        # Store credentials (in production, use environment variables)
        self.username = ""
        self.password = ""
        self.mfa_credential_id = ""

        # Event report table headers from the JavaScript component
        self.report_headers = [
            "Item Number", "Primary Item Number", "Description", "Vendor", "Category"
        ]

        # Default store number for filtering (from cURL command)
        self.default_store_number = "8135"

        # Caching configuration
        self.enable_caching = enable_caching
        self.cache_max_age_hours = cache_max_age_hours
        self.db = EDRDatabaseManager(db_path) if enable_caching else None

    # Consistent browser version - keep in sync with authenticator.py
    CHROME_VERSION = '131'
    USER_AGENT = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36'
    SEC_CH_UA = f'"Google Chrome";v="{CHROME_VERSION}", "Chromium";v="{CHROME_VERSION}", "Not_A Brand";v="24"'

    logger = logging.getLogger(__name__)

    def _human_delay(self, min_seconds: float = 1.0, max_seconds: float = 2.5):
        """Add a human-like delay between requests"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def _get_standard_headers(self, content_type: Optional[str] = None, referer: Optional[str] = None) -> Dict[str, str]:
        """Return standard headers for API requests."""
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': self.SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.USER_AGENT,
        }
        
        if content_type:
            headers['content-type'] = content_type
            
        if referer:
            headers['referer'] = referer
            
        if self.auth_token:
            headers['authorization'] = f'Bearer {self.auth_token}'
            
        return headers

    def step1_submit_password(self) -> bool:
        """Step 1: Submit username and password.

        Visits login page first to acquire fresh cookies from PerimeterX/HUMAN
        bot detection. Stale hardcoded cookies were triggering bot blocks.
        """
        login_url = "https://retaillink.login.wal-mart.com/api/login"

        # Clear stale cookies and visit login page to get fresh ones
        self.session.cookies.clear()
        self.logger.info("[Step 1a] Visiting login page to acquire fresh cookies...")
        print("➡️ Step 1a: Visiting login page to obtain fresh cookies...")
        try:
            login_page_response = self.session.get(
                'https://retaillink.login.wal-mart.com/login',
                headers={
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'accept-language': 'en-US,en;q=0.9',
                    'sec-ch-ua': self.SEC_CH_UA,
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'none',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                    'user-agent': self.USER_AGENT,
                },
                timeout=15,
            )
            cookie_names = [c.name for c in self.session.cookies]
            print(f"   Login page status: {login_page_response.status_code}")
            print(f"   Cookies received: {len(cookie_names)} cookies: {cookie_names}")
            self.logger.info(f"[Step 1a] Login page status={login_page_response.status_code}, cookies={cookie_names}")
        except Exception as e:
            print(f"⚠️ Could not pre-fetch login page: {e}")
            self.logger.warning(f"[Step 1a] Could not pre-fetch login page: {e}")
            print("   Continuing anyway...")

        self._human_delay(1.5, 3.0)

        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'priority': 'u=1, i',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': self.SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.USER_AGENT,
        }

        payload = {"username": self.username, "password": self.password, "language": "en"}

        print("➡️ Step 1b: Submitting username and password...")
        try:
            response = self.session.post(login_url, headers=headers, json=payload)
            print(f"   Response status: {response.status_code}")
            print(f"   Response body preview: {response.text[:200] if response.text else 'empty'}")
            response.raise_for_status()
            print("✅ Password accepted. MFA required.")
            return True
        except requests.exceptions.HTTPError as e:
            print(f"❌ Step 1 failed with HTTP error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Status code: {e.response.status_code}")
                print(f"   Response body: {e.response.text[:500] if e.response.text else 'empty'}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Step 1 failed: {e}")
            return False

    def step2_request_mfa_code(self) -> bool:
        """Step 2: Request MFA code to be sent to user's device."""
        self._human_delay(1.0, 2.0)
        send_code_url = "https://retaillink.login.wal-mart.com/api/mfa/sendCode"
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': self.SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.USER_AGENT,
        }
        payload = {"type": "SMS_OTP", "credid": self.mfa_credential_id}

        print("➡️ Step 2: Requesting MFA code...")
        print(f"🔍 DEBUG: MFA Credential ID = {self.mfa_credential_id}")
        print(f"🔍 DEBUG: Payload = {payload}")
        try:
            response = self.session.post(send_code_url, headers=headers, json=payload)
            print(f"🔍 DEBUG: Response status = {response.status_code}")
            print(f"🔍 DEBUG: Response body = {response.text[:500] if response.text else 'empty'}")
            response.raise_for_status()
            print("✅ MFA code sent successfully. Check your device.")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Step 2 failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"🔍 DEBUG: Error response body = {e.response.text[:500] if e.response.text else 'empty'}")
            return False

    def step3_validate_mfa_code(self, code: str) -> bool:
        """Step 3: Validate the MFA code entered by user."""
        self._human_delay(0.5, 1.5)
        validate_url = "https://retaillink.login.wal-mart.com/api/mfa/validateCode"
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://retaillink.login.wal-mart.com',
            'referer': 'https://retaillink.login.wal-mart.com/login',
            'sec-ch-ua': self.SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.USER_AGENT,
        }
        payload = {
            "type": "SMS_OTP",
            "credid": self.mfa_credential_id,
            "code": code,
            "failureCount": 0
        }

        print("➡️ Step 3: Validating MFA code...")
        try:
            response = self.session.post(validate_url, headers=headers, json=payload)
            response.raise_for_status()
            print("✅ MFA authentication complete!")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Step 3 failed. The code may have been incorrect.")
            return False

    def step4_register_page_access(self) -> bool:
        """Step 4: Register page access to Event Management System."""
        self._human_delay(1.0, 2.0)
        url = "https://retaillink2.wal-mart.com/rl_portal_services/api/Site/InsertRlPageDetails"
        params = {
            'pageId': '6',
            'pageSubId': 'w6040',
            'pageSubDesc': 'Event Management System'
        }
        
        headers = self._get_standard_headers(referer='https://retaillink2.wal-mart.com/rl_portal/')
        headers['priority'] = 'u=1, i'
        
        print("➡️ Step 4: Registering page access...")
        try:
            response = self.session.get(url, headers=headers, params=params)
            if response.status_code == 200:
                print("✅ Page access registered")
                return True
            else:
                print(f"⚠️ Page registration status: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Page registration failed: {e}")
            return False

    def step5_navigate_to_event_management(self) -> bool:
        """Step 5: Navigate to Event Management system."""
        self._human_delay(1.0, 2.0)
        # Navigate to portal first
        portal_url = "https://retaillink2.wal-mart.com/rl_portal/"
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': self.SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-site',
            'upgrade-insecure-requests': '1',
            'user-agent': self.USER_AGENT,
        }
        
        print("➡️ Step 5: Navigating to Event Management...")
        try:
            # First portal
            response = self.session.get(portal_url, headers=headers)
            if response.status_code != 200:
                print(f"❌ Portal access failed: {response.status_code}")
                return False
                
            # Then Event Management
            self._human_delay(1.0, 2.0)
            event_mgmt_url = f"{self.base_url}/"
            response = self.session.get(event_mgmt_url, headers=headers)
            if response.status_code == 200:
                print("✅ Event Management navigation successful")
                return True
            else:
                print(f"❌ Event Management access failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Navigation failed: {e}")
            return False

    def step6_authenticate_event_management(self) -> bool:
        """Step 6: Authenticate with Event Management API and extract auth token."""
        self._human_delay(1.0, 2.0)
        auth_url = f"{self.base_url}/api/authenticate"
        headers = self._get_standard_headers(referer=f"{self.base_url}/")

        print("➡️ Step 6: Authenticating with Event Management API...")
        try:
            response = self.session.get(auth_url, headers=headers)
            print(f"   Response status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Event Management authentication successful!")

                # Debug: Log all cookies to see what's available
                print(f"   Available cookies ({len(self.session.cookies)} total):")
                for cookie in self.session.cookies:
                    # Show first 30 chars of value for debugging
                    value_preview = cookie.value[:30] + "..." if len(cookie.value) > 30 else cookie.value
                    print(f"      - {cookie.name}: {value_preview}")

                # Try multiple possible cookie names for auth token
                token_cookie_names = ['auth-token', 'authToken', 'token', 'auth_token', 'Authorization', 'jwt']
                
                for cookie in self.session.cookies:
                    if cookie.name in token_cookie_names and cookie.value:
                        print(f"   Found token cookie: {cookie.name}")
                        # Parse the URL-encoded cookie value
                        cookie_data = urllib.parse.unquote(cookie.value)
                        
                        # Try parsing as JSON first
                        try:
                            token_obj = json.loads(cookie_data)
                            if isinstance(token_obj, dict):
                                # Look for token in various fields
                                self.auth_token = (token_obj.get('token') or 
                                                   token_obj.get('access_token') or
                                                   token_obj.get('accessToken') or
                                                   token_obj.get('jwt'))
                            elif isinstance(token_obj, str):
                                self.auth_token = token_obj
                                
                            if self.auth_token:
                                print(f"🔑 Auth token extracted from cookie: {self.auth_token[:50]}...")
                                return True
                        except json.JSONDecodeError:
                            # Cookie value might be the token itself
                            if len(cookie_data) > 20:  # Tokens are typically long
                                self.auth_token = cookie_data
                                print(f"🔑 Auth token extracted (raw cookie value): {self.auth_token[:50]}...")
                                return True

                # If no token cookie found, try to extract from response body
                print("   Checking response body for token...")
                try:
                    response_text = response.text[:500]
                    print(f"   Response preview: {response_text}")
                    
                    auth_data = response.json()
                    print(f"   Response JSON keys: {list(auth_data.keys()) if isinstance(auth_data, dict) else 'not a dict'}")
                    
                    # Look for token in various response fields
                    if isinstance(auth_data, dict):
                        self.auth_token = (auth_data.get('token') or 
                                           auth_data.get('access_token') or
                                           auth_data.get('accessToken') or
                                           auth_data.get('jwt') or
                                           auth_data.get('data', {}).get('token') if isinstance(auth_data.get('data'), dict) else None)
                        
                        if self.auth_token:
                            print(f"🔑 Auth token extracted from response: {self.auth_token[:50]}...")
                            return True
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"   Could not parse response as JSON: {e}")
                    pass

                print("⚠️ auth-token not found in cookies or response")
                print("   This may indicate Walmart changed their authentication flow")
                return False
            else:
                print(f"❌ Authentication failed: {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Authentication API call failed: {e}")
            return False
            return False

    def authenticate(self, mfa_code: Optional[str] = None) -> bool:
        """
        Complete authentication flow.

        Args:
            mfa_code: Optional MFA code. If not provided, will prompt for input.

        Returns True if successful, False otherwise.
        """
        print("🔐 Starting Retail Link authentication...")

        # Step 1: Submit password
        if not self.step1_submit_password():
            return False

        # Step 2: Request MFA code
        if not self.step2_request_mfa_code():
            return False

        # Step 3: Get MFA code from user or parameter
        if mfa_code is None:
            mfa_code = input("📱 Please enter the MFA code you received: ").strip()
        else:
            print(f"📱 Using provided MFA code: {mfa_code[:2]}****")
            mfa_code = mfa_code.strip()

        if not self.step3_validate_mfa_code(mfa_code):
            return False
        
        # Step 4: Register page access
        if not self.step4_register_page_access():
            print("⚠️ Page registration failed, continuing...")
        
        # Step 5: Navigate to Event Management
        if not self.step5_navigate_to_event_management():
            print("⚠️ Navigation failed, continuing...")
        
        # Step 6: Authenticate and get token
        if not self.step6_authenticate_event_management():
            print("❌ Could not obtain auth token")
            return False
        
        print("✅ Full authentication completed successfully!")
        return True

    def browse_events(self, start_date: Optional[str] = None, end_date: Optional[str] = None, 
                     store_number: Optional[str] = None, event_types: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Browse events using the API endpoint from cURL command 3.
        
        Args:
            start_date: Start date in YYYY-MM-DD format (defaults to current month)
            end_date: End date in YYYY-MM-DD format (defaults to current month)
            store_number: Store number (defaults to 8135)
            event_types: List of event type IDs (defaults to all types)
            
        Returns:
            Dictionary containing event browse results
        """
        if not self.auth_token:
            raise ValueError("Must authenticate first before browsing events")
        
        # Set defaults: 1 month before today to 1 month after today
        if not start_date or not end_date:
            now = datetime.datetime.now()
            # Calculate 1 month before
            one_month_ago = now - datetime.timedelta(days=30)
            # Calculate 1 month ahead
            one_month_ahead = now + datetime.timedelta(days=30)

            start_date = one_month_ago.strftime("%Y-%m-%d")
            end_date = one_month_ahead.strftime("%Y-%m-%d")
        
        if not store_number:
            store_number = self.default_store_number
        
        if not event_types:
            # All event types from cURL command
            event_types = [1,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45]
        
        url = f"{self.base_url}/api/browse-event/browse-data"
        headers = self._get_standard_headers(
            content_type='application/json',
            referer=f"{self.base_url}/browse-event"
        )
        headers['origin'] = 'https://retaillink2.wal-mart.com'
        headers['priority'] = 'u=1, i'
        
        payload = {
            "itemNbr": None,
            "vendorNbr": None,
            "startDate": start_date,
            "endDate": end_date,
            "billType": None,
            "eventType": event_types,
            "userId": None,
            "primItem": None,
            "storeNbr": store_number,
            "deptNbr": None
        }
        
        print(f"🔍 Browsing events from {start_date} to {end_date} for store {store_number}...")
        try:
            response = self.session.post(url, headers=headers, json=payload)
            response.raise_for_status()

            events_data = response.json()
            print(f"✅ Found {len(events_data)} event items")

            # Cache the data if caching is enabled
            if self.enable_caching and self.db and events_data:
                stored_count = self.db.store_events(events_data, store_number, start_date, end_date)
                print(f"💾 Cached {stored_count} event items to database")

            return events_data
        except requests.exceptions.RequestException as e:
            print(f"❌ Event browsing failed: {e}")
            return []

    def browse_events_with_cache(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                                  store_number: Optional[str] = None, event_types: Optional[List[int]] = None,
                                  force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Browse events with caching support - checks cache first, falls back to API.

        Args:
            start_date: Start date in YYYY-MM-DD format (defaults to current month)
            end_date: End date in YYYY-MM-DD format (defaults to current month)
            store_number: Store number (defaults to 8135)
            event_types: List of event type IDs (not used for cache lookup)
            force_refresh: Force refresh from API even if cache is fresh

        Returns:
            List of event dictionaries
        """
        # Set defaults: 1 month before today to 1 month after today
        if not start_date or not end_date:
            now = datetime.datetime.now()
            # Calculate 1 month before
            one_month_ago = now - datetime.timedelta(days=30)
            # Calculate 1 month ahead
            one_month_ahead = now + datetime.timedelta(days=30)

            start_date = one_month_ago.strftime("%Y-%m-%d")
            end_date = one_month_ahead.strftime("%Y-%m-%d")

        if not store_number:
            store_number = self.default_store_number

        # Check cache first if caching is enabled and not forcing refresh
        if self.enable_caching and self.db and not force_refresh:
            is_fresh = self.db.is_cache_fresh(store_number, start_date, end_date, self.cache_max_age_hours)

            if is_fresh:
                print(f"📦 Using cached data (less than {self.cache_max_age_hours} hours old)")
                cached_events = self.db.get_events_by_date_range(start_date, end_date, store_number, self.cache_max_age_hours)
                if cached_events:
                    print(f"✅ Retrieved {len(cached_events)} event items from cache")
                    return cached_events

        # Cache miss or force refresh - fetch from API
        if force_refresh:
            print("🔄 Force refresh requested - fetching from API")
        else:
            print("⚠️ Cache miss or stale - fetching from API")

        # Ensure authentication
        if not self.auth_token:
            print("❌ Not authenticated - cannot fetch from API")
            return []

        return self.browse_events(start_date, end_date, store_number, event_types)

    def get_event_from_cache(self, event_id: int) -> List[Dict[str, Any]]:
        """
        Get event data from cache by event ID.

        Args:
            event_id: The event ID to retrieve

        Returns:
            List of event item dictionaries (one event can have multiple items)
        """
        if not self.enable_caching or not self.db:
            print("⚠️ Caching is disabled")
            return []

        event_items = self.db.get_event_by_id(event_id, self.cache_max_age_hours)

        if event_items:
            print(f"✅ Found {len(event_items)} items for event {event_id} in cache")
        else:
            print(f"⚠️ Event {event_id} not found in cache or cache is stale")

        return event_items

    def get_event_data_smart(self, event_id: int, mfa_code: Optional[str] = None,
                              auto_authenticate: bool = True) -> List[Dict[str, Any]]:
        """
        Smart cache-first method: Get event data from cache, or fetch from API if missing.

        This is the PRIMARY method that printing operations should use.

        Workflow:
        1. Check cache for event data
        2. If found with items, return immediately
        3. If not found or no items:
           - Authenticate if needed (requires MFA code)
           - Fetch bulk data using browse_events()
           - Update database cache
           - Return event data from cache

        Args:
            event_id: The event ID to retrieve
            mfa_code: Optional MFA code for authentication if needed
            auto_authenticate: If True, will attempt to authenticate if not already authenticated

        Returns:
            List of event item dictionaries, or empty list if failed
        """
        if not self.enable_caching or not self.db:
            print("❌ Caching is not enabled - cannot use smart fetch")
            return []

        print(f"🔍 Smart fetch for event {event_id}...")

        # Step 1: Try cache first
        event_items = self.get_event_from_cache(event_id)

        if event_items:
            print(f"✅ Using cached data for event {event_id}")
            return event_items

        # Step 2: Cache miss - need to fetch from API
        print(f"⚠️ Event {event_id} not in cache - will fetch from API")

        # Check if we need authentication
        if not self.auth_token:
            if not auto_authenticate:
                print("❌ Not authenticated and auto_authenticate=False")
                return []

            if not mfa_code:
                print("❌ Not authenticated and no MFA code provided")
                print("💡 Provide mfa_code parameter to enable automatic authentication")
                return []

            print("🔐 Authenticating to fetch missing data...")
            auth_success = self.authenticate(mfa_code=mfa_code)

            if not auth_success:
                print("❌ Authentication failed - cannot fetch data")
                return []

        # Step 3: Fetch bulk data using browse_events()
        print("📥 Fetching bulk event data from API...")
        events_data = self.browse_events()  # Uses default date range (±30 days)

        if not events_data:
            print("❌ No events data returned from API")
            return []

        print(f"✅ Fetched and cached {len(events_data)} event items")

        # Step 4: Get the specific event from cache (now it should be there)
        event_items = self.get_event_from_cache(event_id)

        if event_items:
            print(f"✅ Event {event_id} now available in cache with {len(event_items)} items")
            return event_items
        else:
            print(f"⚠️ Event {event_id} still not in cache after fetch - may be outside date range")
            return []

    def refresh_cache(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                     store_number: Optional[str] = None) -> bool:
        """
        Force refresh cache data from API.

        Args:
            start_date: Start date in YYYY-MM-DD format (defaults to current month)
            end_date: End date in YYYY-MM-DD format (defaults to current month)
            store_number: Store number (defaults to 8135)

        Returns:
            True if refresh was successful, False otherwise
        """
        print("🔄 Refreshing cache from API...")

        if not self.auth_token:
            print("❌ Not authenticated - cannot refresh cache")
            return False

        events_data = self.browse_events(start_date, end_date, store_number)
        return len(events_data) > 0 if isinstance(events_data, list) else False

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cached data.

        Returns:
            Dictionary with cache statistics or empty dict if caching is disabled
        """
        if not self.enable_caching or not self.db:
            return {'caching_enabled': False}

        stats = self.db.get_cache_stats()
        stats['caching_enabled'] = True
        stats['max_age_hours'] = self.cache_max_age_hours
        return stats

    def clear_old_cache(self, max_age_days: int = 30) -> Tuple[int, int]:
        """
        Clear cache data older than specified days.

        Args:
            max_age_days: Maximum age to keep in days (default: 30)

        Returns:
            Tuple of (events_deleted, metadata_records_deleted)
        """
        if not self.enable_caching or not self.db:
            print("⚠️ Caching is disabled")
            return (0, 0)

        events_deleted, metadata_deleted = self.db.clear_old_cache(max_age_days)
        print(f"🗑️ Cleared {events_deleted} old event records and {metadata_deleted} metadata records")
        return (events_deleted, metadata_deleted)

    def convert_cached_items_to_edr_format(self, cached_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert browse_events cached format to get_edr_report format
        for compatibility with existing code.

        Args:
            cached_items: List of item dictionaries from cache (one event can have multiple items)

        Returns:
            EDR data dictionary in get_edr_report format
        """
        if not cached_items:
            return {}

        first_item = cached_items[0]

        # Clean up event type and status - the cache stores full descriptive text
        # like "Event Type Supplier" or "Status APPROVED", but we need just the value
        event_type = first_item.get('eventType', '')
        event_status = first_item.get('eventStatus', '')

        # Remove "Event Type " prefix if present
        if event_type and event_type.startswith('Event Type '):
            event_type = event_type.replace('Event Type ', '', 1)

        # Remove "Status " prefix if present
        if event_status and event_status.startswith('Status '):
            event_status = event_status.replace('Status ', '', 1)

        return {
            'demoId': first_item.get('eventId'),
            'demoName': first_item.get('eventName'),
            'demoDate': first_item.get('eventDate'),
            'demoClassCode': event_type,  # Cleaned value
            'demoStatusCode': event_status,  # Cleaned value
            'demoLockInd': first_item.get('lockDate', 'false'),
            'itemDetails': [
                {
                    'itemNbr': item.get('itemNbr'),
                    'gtin': item.get('upcNbr'),  # UPC number
                    'itemDesc': item.get('itemDesc'),
                    'vendorNbr': item.get('vendorBilledNbr'),
                    'vendorDesc': item.get('vendorBilledDesc'),
                    'deptNbr': item.get('deptNbr'),
                    'deptDesc': item.get('deptDesc'),
                    'featuredItemInd': item.get('featuredItemInd', 'N')
                }
                for item in cached_items
            ]
        }

    def generate_html_report_from_cache(self, event_id: int) -> str:
        """
        Generate HTML report from cached event data (bypasses get_edr_report API call).

        Args:
            event_id: The event ID to generate report for

        Returns:
            Complete HTML report ready for printing, or empty string if event not found
        """
        # Get event items from cache
        event_items = self.get_event_from_cache(event_id)

        if not event_items:
            print(f"❌ Cannot generate report - event {event_id} not found in cache")
            return ""

        # Get current date and time for the report header
        now = datetime.datetime.now()
        report_date = now.strftime("%Y-%m-%d")
        report_time = now.strftime("%H:%M:%S")

        # Extract event information from first item (all items share same event metadata)
        first_item = event_items[0]
        event_number = first_item.get('eventId', 'N/A')
        event_type = first_item.get('eventType', 'N/A')
        event_status = first_item.get('eventStatus', 'N/A')
        event_date = first_item.get('eventDate', 'N/A')
        event_name = first_item.get('eventName', 'N/A')
        event_locked = first_item.get('lockDate', 'false')

        # Generate table rows for items (3 columns only: Item Number, Description, Category)
        item_rows = ""
        for item in event_items:
            # Mark featured items with a star
            featured = "⭐ " if item.get('featuredItemInd') == 'Y' else ""

            item_rows += f"""
                <tr class="edr-wrapper">
                    <td class="report-table-content">{item.get('itemNbr', '')}</td>
                    <td class="report-table-content">{featured}{item.get('itemDesc', '')}</td>
                    <td class="report-table-content">{item.get('deptDesc', '')}</td>
                </tr>
            """

        # Complete HTML template (no instructions section)
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Event Management System - EDR Report</title>
    <style>
        /* CSS from the provided files combined with print optimization */
        body {{
            font-family: Arial, sans-serif;
            padding: 20px;
            margin: 0;
        }}

        .detail-header {{
            display: flex;
            justify-content: center;
            align-items: center;
            font-weight: 700;
            font-size: 24px;
            margin-bottom: 20px;
        }}

        .elememnt-padding {{
            padding: 10px 0;
        }}

        .font-weight-bold {{
            font-size: 18px;
            margin-top: 10px;
            margin-bottom: 10px;
            font-weight: bold;
        }}

        .space-underlined {{
            display: inline-block;
            width: calc(80% - 230px);
            border-bottom: 1px solid black;
            margin-left: 10px;
        }}

        .report-footer div {{
            padding: 2px 0;
        }}

        .report-first {{
            margin-left: 20%;
        }}

        .help-text {{
            font-size: 14px;
            line-height: 1.2;
        }}

        .demo-text {{
            margin-left: 12px;
            font-weight: 700;
        }}

        .col-40 {{
            flex: 0 0 40%;
            max-width: 40%;
        }}

        .report-table-content {{
            text-align: center;
        }}

        .row {{
            display: flex;
            padding: 5px;
            width: 100%;
        }}

        .col {{
            flex: 1;
            display: block;
            padding: 5px;
            width: 100%;
        }}

        .col-25 {{
            flex: 0 0 25%;
            max-width: 25%;
        }}

        .input-label {{
            font-weight: normal;
        }}

        td {{
            padding: 8px;
            border-top: solid 1px #ccc;
            font-family: arial;
            font-size: 12px;
            text-align: left;
            font-weight: 400;
            color: grey;
            line-height: 18px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: center;
            font-size: 94%;
            outline: #ccc solid 1px;
            table-layout: fixed;
            margin-bottom: 10px;
        }}

        th {{
            padding: 5px;
            background: #e2e1e1;
            font-size: 14px;
            font-weight: 400;
            color: grey;
        }}

        .demo-table-header {{
            background: #e2e1e1;
        }}

        hr {{
            border: 1px solid #ccc;
            margin: 10px 0;
        }}

        @media print {{
            body {{
                padding: 10px;
            }}
            .print-button {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div id="reportDdr_pdf">
        <div class="detail-header">EVENT DETAIL REPORT</div>

        <div class="elememnt-padding font-weight-bold">
            <span>RUN ON </span>
            <span>{report_date}</span>
            <span> AT </span>
            <span>{report_time}</span>
        </div>

        <hr>

        <div class="elememnt-padding help-text">
            <div>
                <span class="report-first">IMPORTANT!!!</span>
                This report should be printed each morning prior to completing each event.<br>
                1. The Event Details Report should be kept in the event prep area for each demonstrator to review instructions and item status.<br>
                2. The Event Co-ordinator should use this sheet when visiting the event area. Comments should be written to enter into the system at a later time.<br>
                3. Remember to scan items for product charge using the Club Use function on the handheld device.<br>
                Retention: This report should be kept in a monthly folder with the most recent being put in the front. The previous 6 months need to be kept accessible in the event prep area. Reports older than 6 months should be boxed and stored. Discard any report over 18 months old.
            </div>
        </div>

        <hr>

        <div id="demo_div">
            <div class="row responsive-md">
                <div class="col col-25">
                    <span class="input-label" title="Event Number">
                        Event Number <span class="demo-text">{event_number}</span>
                    </span>
                </div>
                <div class="col col-25">
                    <span class="input-label" title="Event Type">
                        Event Type <span class="demo-text">{event_type}</span>
                    </span>
                </div>
                <div class="col col-40">
                    <span class="input-label" title="Event Locked">
                        Event Locked <span class="demo-text">{event_locked}</span>
                    </span>
                </div>
            </div>

            <div class="row responsive-md">
                <div class="col col-25">
                    <span class="input-label" title="Event Status">
                        Event Status <span class="demo-text">{event_status}</span>
                    </span>
                </div>
                <div class="col col-25">
                    <span class="input-label" title="Event Date">
                        Event Date <span class="demo-text">{event_date}</span>
                    </span>
                </div>
                <div class="col col-40">
                    <span class="input-label" title="Event Name">
                        Event Name <span class="demo-text" title="{event_name}">{event_name}</span>
                    </span>
                </div>
            </div>
        </div>

        <div id="demo_pdf">
            <table id="new_event">
                <thead>
                    <tr class="demo-table-header">
                        <th>Item Number</th>
                        <th>Description</th>
                        <th>Category</th>
                    </tr>
                </thead>
                <tbody>
                    {item_rows}
                </tbody>
            </table>
        </div>

        <div class="report-footer">
            <div>
                <span>Club Associate Printed Name:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Club Associate Signature:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Club Associate Title:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Date:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Tastes & Tips Rep Signature:</span>
                <span class="space-underlined"></span>
            </div>
        </div>

        <div class="print-button" style="margin-top: 20px; text-align: right;">
            <button onclick="window.print()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 4px; cursor: pointer;">
                🖨️ Print Report
            </button>
        </div>
    </div>
</body>
</html>
        """

        return html_content.strip()

    def get_edr_report(self, event_id: str) -> Dict[str, Any]:
        """
        Get EDR report data for a specific event ID.
        
        Args:
            event_id: The event ID to retrieve the report for
            
        Returns:
            Dictionary containing EDR report data
        """
        if not self.auth_token:
            raise ValueError("Must authenticate first before getting EDR report")
        
        url = f"{self.base_url}/api/edrReport?id={event_id}"
        headers = self._get_standard_headers(referer=f"{self.base_url}/browse-event")
        
        print(f"📄 Retrieving EDR report for event {event_id}...")
        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            report_data = response.json()
            print(f"✅ EDR report retrieved successfully")
            return report_data
        except requests.exceptions.RequestException as e:
            print(f"❌ EDR report retrieval failed: {e}")
            return {}

    def get_event_detail_report_page(self) -> str:
        """
        Get the event detail report page HTML (from cURL command 1).
        
        Returns:
            HTML content of the event detail report page
        """
        url = f"{self.base_url}/event-detail-report?_rsc=h0aj8"
        headers = {
            'User-Agent': self.USER_AGENT,
            'Referer': f"{self.base_url}/create-event"
        }
        
        print("📋 Retrieving event detail report page...")
        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            print("✅ Event detail report page retrieved")
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"❌ Event detail report page retrieval failed: {e}")
            return ""

    def generate_html_report(self, edr_data: Dict[str, Any]) -> str:
        """
        Generate HTML report based on the React component structure and CSS styling.
        
        Args:
            edr_data: EDR report data from get_edr_report()
            
        Returns:
            Complete HTML report ready for printing
        """
        # Get current date and time for the report header
        now = datetime.datetime.now()
        report_date = now.strftime("%Y-%m-%d")
        report_time = now.strftime("%H:%M:%S")
        
        # Extract event information (adjust based on actual API response structure)
        event_number = edr_data.get('demoId', 'N/A') if edr_data else 'N/A'
        event_type = edr_data.get('demoClassCode', 'N/A') if edr_data else 'N/A'
        event_status = edr_data.get('demoStatusCode', 'N/A') if edr_data else 'N/A'
        event_date = edr_data.get('demoDate', 'N/A') if edr_data else 'N/A'
        event_name = edr_data.get('demoName', 'N/A') if edr_data else 'N/A'
        event_locked = edr_data.get('demoLockInd', 'N/A') if edr_data else 'N/A'
        
        # Instructions
        instructions = edr_data.get('demoInstructions', {}) if edr_data else {}
        event_prep = instructions.get('demoPrepnTxt', 'N/A') if instructions else 'N/A'
        event_portion = instructions.get('demoPortnTxt', 'N/A') if instructions else 'N/A'
        
        # Item details
        item_details = edr_data.get('itemDetails', []) if edr_data else []
        
        # Generate table rows for items
        item_rows = ""
        for item in item_details:
            item_rows += f"""
                <tr class="edr-wrapper">
                    <td class="report-table-content">{item.get('itemNbr', '')}</td>
                    <td class="report-table-content">{item.get('gtin', '')}</td>
                    <td class="report-table-content">{item.get('itemDesc', '')}</td>
                    <td class="report-table-content">{item.get('vendorNbr', '')}</td>
                    <td class="report-table-content">{item.get('deptNbr', '')}</td>
                </tr>
            """

        # Complete HTML template based on the React component and CSS
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Event Management System - EDR Report</title>
    <style>
        /* CSS from the provided files combined with print optimization */
        body {{ 
            font-family: Arial, sans-serif; 
            padding: 20px; 
            margin: 0;
        }}
        
        .detail-header {{ 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            font-weight: 700;
            font-size: 24px;
            margin-bottom: 20px;
        }}
        
        .elememnt-padding {{ 
            padding: 10px 0; 
        }}
        
        .font-weight-bold {{ 
            font-size: 18px; 
            margin-top: 10px; 
            margin-bottom: 10px; 
            font-weight: bold;
        }}
        
        .space-underlined {{ 
            display: inline-block; 
            width: calc(80% - 230px); 
            border-bottom: 1px solid black;
            margin-left: 10px;
        }}
        
        .instruction-heading {{ 
            margin-top: 10px; 
            margin-bottom: 10px; 
            font-size: 18px; 
            font-weight: 500; 
        }}
        
        .report-footer div {{ 
            padding: 2px 0; 
        }}
        
        .report-first {{ 
            margin-left: 20%; 
        }}
        
        .help-text {{ 
            font-size: 14px; 
            line-height: 1.2; 
        }}
        
        .demo-text {{ 
            margin-left: 12px; 
            font-weight: 700; 
        }}
        
        .col-40 {{ 
            flex: 0 0 40%; 
            max-width: 40%; 
        }}
        
        .report-table-content {{ 
            text-align: center; 
        }}
        
        .row {{ 
            display: flex; 
            padding: 5px; 
            width: 100%; 
        }}
        
        .col {{ 
            flex: 1; 
            display: block; 
            padding: 5px; 
            width: 100%; 
        }}
        
        .col-25 {{ 
            flex: 0 0 25%; 
            max-width: 25%; 
        }}
        
        .input-label {{ 
            font-weight: normal; 
        }}
        
        td {{ 
            padding: 8px; 
            border-top: solid 1px #ccc; 
            font-family: arial; 
            font-size: 12px; 
            text-align: left; 
            font-weight: 400; 
            color: grey; 
            line-height: 18px; 
        }}
        
        table {{ 
            width: 100%; 
            border-collapse: collapse; 
            text-align: center; 
            font-size: 94%; 
            outline: #ccc solid 1px; 
            table-layout: fixed; 
            margin-bottom: 10px; 
        }}
        
        th {{ 
            padding: 5px; 
            background: #e2e1e1; 
            font-size: 14px; 
            font-weight: 400; 
            color: grey; 
        }}
        
        .demo-table-header {{ 
            background: #e2e1e1; 
        }}
        
        hr {{ 
            border: 1px solid #ccc; 
            margin: 10px 0; 
        }}
        
        @media print {{
            body {{ 
                padding: 10px; 
            }}
            .print-button {{ 
                display: none; 
            }}
        }}
    </style>
</head>
<body>
    <div id="reportDdr_pdf">
        <div class="detail-header">EVENT DETAIL REPORT</div>
        
        <div class="elememnt-padding font-weight-bold">
            <span>RUN ON </span>
            <span>{report_date}</span>
            <span> AT </span>
            <span>{report_time}</span>
        </div>
        
        <hr>
        
        <div class="elememnt-padding help-text">
            <div>
                <span class="report-first">IMPORTANT!!!</span> 
                This report should be printed each morning prior to completing each event.<br>
                1. The Event Details Report should be kept in the event prep area for each demonstrator to review instructions and item status.<br>
                2. The Event Co-ordinator should use this sheet when visiting the event area. Comments should be written to enter into the system at a later time.<br>
                3. Remember to scan items for product charge using the Club Use function on the handheld device.<br>
                Retention: This report should be kept in a monthly folder with the most recent being put in the front. The previous 6 months need to be kept accessible in the event prep area. Reports older than 6 months should be boxed and stored. Discard any report over 18 months old.
            </div>
        </div>
        
        <hr>
        
        <div id="demo_div">
            <div class="row responsive-md">
                <div class="col col-25">
                    <span class="input-label" title="Event Number">
                        Event Number <span class="demo-text">{event_number}</span>
                    </span>
                </div>
                <div class="col col-25">
                    <span class="input-label" title="Event Type">
                        Event Type <span class="demo-text">{event_type}</span>
                    </span>
                </div>
                <div class="col col-40">
                    <span class="input-label" title="Event Locked">
                        Event Locked <span class="demo-text">{event_locked}</span>
                    </span>
                </div>
            </div>
            
            <div class="row responsive-md">
                <div class="col col-25">
                    <span class="input-label" title="Event Status">
                        Event Status <span class="demo-text">{event_status}</span>
                    </span>
                </div>
                <div class="col col-25">
                    <span class="input-label" title="Event Date">
                        Event Date <span class="demo-text">{event_date}</span>
                    </span>
                </div>
                <div class="col col-40">
                    <span class="input-label" title="Event Name">
                        Event Name <span class="demo-text" title="{event_name}">{event_name}</span>
                    </span>
                </div>
            </div>
        </div>
        
        <div id="demo_pdf">
            <table id="new_event">
                <thead>
                    <tr class="demo-table-header">
                        <th>Item Number</th>
                        <th>Primary Item Number</th>
                        <th>Description</th>
                        <th>Vendor</th>
                        <th>Category</th>
                    </tr>
                </thead>
                <tbody>
                    {item_rows}
                </tbody>
            </table>
        </div>
        
        <h4 class="instruction-heading">Instructions:</h4>
        
        <div>
            <span class="input-label" title="Event Preparation">
                Event Preparation: <span class="demo-text">{event_prep}</span>
            </span>
            <div>
                <span class="input-label" title="Event Portion">
                    Event Portion: <span class="demo-text">{event_portion}</span>
                </span>
            </div>
        </div>
        
        <div class="report-footer">
            <div>
                <span>Club Associate Printed Name:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Club Associate Signature:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Club Associate Title:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Date:</span>
                <span class="space-underlined"></span>
            </div>
            <div>
                <span>Tastes & Tips Rep Signature:</span>
                <span class="space-underlined"></span>
            </div>
        </div>
        
        <div class="print-button" style="margin-top: 20px; text-align: right;">
            <button onclick="window.print()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 4px; cursor: pointer;">
                🖨️ Print Report
            </button>
        </div>
    </div>
</body>
</html>
        """
        
        return html_content.strip()

    def save_html_report(self, html_content: str, filename: Optional[str] = None) -> str:
        """
        Save HTML report to file.
        
        Args:
            html_content: HTML content to save
            filename: Optional filename (defaults to timestamp-based name)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"edr_report_{timestamp}.html"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"💾 Report saved to: {filename}")
        return filename

    def print_html_report(self, html_content: str, temp_filename: Optional[str] = None) -> bool:
        """
        Print HTML report directly to the default printer without user interaction.
        
        Args:
            html_content: HTML content to print
            temp_filename: Optional temporary filename (auto-generated if not provided)
            
        Returns:
            True if print job was sent successfully, False otherwise
        """
        try:
            # Create temporary file if needed
            if not temp_filename:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_filename = f"temp_edr_report_{timestamp}.html"
            
            # Save HTML to temporary file
            temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"🖨️ Printing report to default printer...")
            print(f"📁 Temporary file: {temp_path}")
            
            # Platform-specific printing
            system = platform.system().lower()
            
            if system == "windows":
                # Try multiple Windows printing methods
                result = (self._print_on_windows_simple(temp_path) or 
                         self._print_on_windows_advanced(temp_path) or
                         self._print_on_windows_fallback(temp_path))
            elif system == "darwin":  # macOS
                result = self._print_on_macos(temp_path)
            elif system == "linux":
                result = self._print_on_linux(temp_path)
            else:
                print(f"❌ Unsupported operating system: {system}")
                return False
            
            if result:
                print("✅ Print job sent successfully to default printer")
                
                # Clean up temporary file after a longer delay to ensure printing completes
                try:
                    import time
                    print("⏳ Waiting for print job to complete...")
                    time.sleep(5)  # Give printer more time to read the file
                    os.remove(temp_path)
                    print("🗑️ Temporary file cleaned up")
                except OSError as e:
                    print(f"⚠️ Could not remove temporary file: {temp_path} - {e}")
                
                return True
            else:
                print("❌ Failed to send print job")
                print(f"📁 Report file remains at: {temp_path}")
                print("🗑️ Cleaning up temporary file...")
                try:
                    os.remove(temp_path)
                    print("✅ Temporary file cleaned up")
                except OSError:
                    pass
                return False
                
        except Exception as e:
            print(f"❌ Print operation failed: {e}")
            return False

    def _print_on_windows_simple(self, file_path: str) -> bool:
        """Simple Windows printing using start command with /wait to prevent popups."""
        try:
            print("🖨️ Method 1: Using Windows start command with print verb...")
            abs_path = os.path.abspath(file_path)
            
            # Use /wait to prevent browser from staying open, /min to minimize
            result = subprocess.run([
                "cmd", "/c", "start", "/wait", "/min", "", "/print", abs_path
            ], capture_output=True, text=True, timeout=15)
            
            success = result.returncode == 0
            if success:
                print("✅ Print command successful")
            else:
                print(f"⚠️ Print command failed with code: {result.returncode}")
                
            return success
            
        except subprocess.TimeoutExpired:
            print("⚠️ Print command timed out")
            return False
        except Exception as e:
            print(f"⚠️ Simple print method failed: {e}")
            return False

    def _print_on_windows_advanced(self, file_path: str) -> bool:
        """Advanced Windows printing using PowerShell with better control."""
        try:
            print("🖨️ Method 2: Using PowerShell with hidden window...")
            abs_path = os.path.abspath(file_path)
            
            # Use PowerShell with WindowStyle Hidden to prevent popup
            ps_cmd = f'Start-Process -FilePath "{abs_path}" -Verb Print -WindowStyle Hidden -Wait'
            
            result = subprocess.run([
                "powershell.exe", "-WindowStyle", "Hidden", "-Command", ps_cmd
            ], capture_output=True, text=True, timeout=15)
            
            success = result.returncode == 0
            if success:
                print("✅ PowerShell print command successful")
            else:
                print(f"⚠️ PowerShell print failed with code: {result.returncode}")
                
            return success
            
        except subprocess.TimeoutExpired:
            print("⚠️ PowerShell print command timed out")
            return False
        except Exception as e:
            print(f"⚠️ Advanced print method failed: {e}")
            return False

    def _print_on_windows_fallback(self, file_path: str) -> bool:
        """Fallback Windows printing - use print command directly."""
        try:
            print("🖨️ Method 3: Using Windows print command...")
            abs_path = os.path.abspath(file_path)
            
            # Try using the print command directly
            result = subprocess.run([
                "print", abs_path
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print("✅ Direct print command successful")
                return True
            else:
                print(f"⚠️ Direct print failed with code: {result.returncode}")
                print("❌ All automatic printing methods failed")
                print(f"📁 Report saved at: {abs_path}")
                print("💡 You can manually print this file if needed")
                return False
                
        except Exception as e:
            print(f"⚠️ Fallback print method failed: {e}")
            print("❌ All automatic printing methods failed")
            print(f"📁 Report saved at: {file_path}")
            return False

    def _print_on_macos(self, file_path: str) -> bool:
        """Print HTML file on macOS using lp or open command."""
        try:
            # Method 1: Try using lp with HTML file directly
            result = subprocess.run([
                "lp", "-d", "default", file_path
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True
            
            # Method 2: Use open command to print via default browser
            result = subprocess.run([
                "open", "-a", "Safari", file_path
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                # Send print command via AppleScript
                applescript = '''
                tell application "Safari"
                    delay 2
                    tell application "System Events"
                        keystroke "p" using command down
                        delay 1
                        keystroke return
                    end tell
                end tell
                '''
                
                subprocess.run([
                    "osascript", "-e", applescript
                ], timeout=10)
                return True
            
            return False
            
        except subprocess.TimeoutExpired:
            print("⚠️ Print operation timed out")
            return False
        except Exception as e:
            print(f"⚠️ macOS print method failed: {e}")
            return False

    def _print_on_linux(self, file_path: str) -> bool:
        """Print HTML file on Linux using lp command."""
        try:
            # Method 1: Try using lp command with default printer
            result = subprocess.run([
                "lp", file_path
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True
            
            # Method 2: Try using lpr command
            result = subprocess.run([
                "lpr", file_path
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True
            
            # Method 3: Use xdg-open and attempt to print via default browser
            result = subprocess.run([
                "xdg-open", file_path
            ], capture_output=True, text=True, timeout=10)
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("⚠️ Print operation timed out")
            return False
        except Exception as e:
            print(f"⚠️ Linux print method failed: {e}")
            return False

    def generate_and_print_edr_report(self, event_id: str, save_copy: bool = True) -> bool:
        """
        Complete workflow: Get EDR data, generate HTML report, and print automatically.
        
        Args:
            event_id: The event ID to generate and print report for
            save_copy: Whether to save a permanent copy of the report (default: True)
            
        Returns:
            True if the entire process was successful, False otherwise
        """
        if not self.auth_token:
            print("❌ Must authenticate first before generating reports")
            return False
        
        print(f"📋 Starting EDR report generation and printing for event {event_id}...")
        
        # Step 1: Get EDR data
        print("📄 Retrieving EDR data...")
        edr_data = self.get_edr_report(event_id)
        if not edr_data:
            print("❌ Failed to retrieve EDR data")
            return False
        
        # Step 2: Generate HTML report
        print("🔧 Generating HTML report...")
        html_report = self.generate_html_report(edr_data)
        if not html_report:
            print("❌ Failed to generate HTML report")
            return False
        
        # Step 3: Save permanent copy if requested
        saved_file = None
        if save_copy:
            print("💾 Saving permanent copy...")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_file = self.save_html_report(
                html_report, 
                f"edr_report_{event_id}_{timestamp}.html"
            )
        
        # Step 4: Print the report
        print("🖨️ Sending to printer...")
        print_success = self.print_html_report(html_report)
        
        if print_success:
            print("✅ EDR report generated and printed successfully!")
            if saved_file:
                print(f"📁 Permanent copy saved as: {saved_file}")
            return True
        else:
            print("❌ Report generated but printing failed")
            if saved_file:
                print(f"📁 Report still saved as: {saved_file}")
            return False


# Example usage and testing
if __name__ == "__main__":
    # Automated usage - no user interaction
    generator = EDRReportGenerator()
    
    print("🤖 Running in automated mode - no user interaction")
    print("⚠️ Note: MFA authentication will fail in automated mode")
    print("📋 This script is designed for use after manual authentication")
    
    # For automated usage, assume authentication is already handled
    # or use this for testing the report generation parts only
    
    # Example of automated report generation (would need pre-authenticated session)
    # event_id = "606034"  # Default event ID for testing
    # 
    # if generator.auth_token:  # Only if already authenticated
    #     print(f"🖨️ Generating and printing EDR report for event {event_id}...")
    #     success = generator.generate_and_print_edr_report(event_id, save_copy=True)
    #     if success:
    #         print("✅ EDR report generated, saved, and sent to printer!")
    #     else:
    #         print("❌ Failed to complete the automated process")
    # else:
    #     print("❌ No authentication token available for automated operation")
    
    print("� For automated usage, integrate this class into your workflow after authentication")
