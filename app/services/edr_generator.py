"""
Simplified EDR (Event Detail Report) Generator for Flask integration
Extracts event numbers from sales tool PDFs and generates EDR HTML reports
"""
import requests
import json
import logging
from typing import Dict, List, Optional, Any
import urllib.parse
from datetime import datetime


class EDRGenerator:
    """Simplified EDR generator for integration with Flask app"""

    def __init__(self, username: str, password: str, mfa_credential_id: str):
        self.session = requests.Session()
        self.base_url = "https://retaillink2.wal-mart.com/EventManagement"
        self.auth_token = None
        self.user_data = None
        self.logger = logging.getLogger(__name__)

        # Store credentials
        self.username = username
        self.password = password
        self.mfa_credential_id = mfa_credential_id

    def request_mfa_code(self) -> bool:
        """
        Request MFA code to be sent (steps 1 & 2)
        Call this BEFORE showing the MFA popup
        Returns True if code was requested successfully
        """
        try:
            # Step 1: Submit password
            if not self._step1_submit_password():
                return False

            # Step 2: Request MFA code
            if not self._step2_request_mfa_code():
                return False

            self.logger.info("MFA code requested successfully")
            return True

        except Exception as e:
            self.logger.error(f"MFA code request failed: {str(e)}")
            return False

    def authenticate_with_mfa_code(self, mfa_code: str) -> bool:
        """
        Complete authentication flow with provided MFA code
        NOTE: request_mfa_code() must be called first!
        Returns True if successful
        """
        try:
            # Step 3: Validate MFA code
            if not self._step3_validate_mfa_code(mfa_code):
                return False

            # Step 4-6: Navigate and get auth token
            self._step4_register_page_access()
            self._step5_navigate_to_event_management()

            if not self._step6_authenticate_event_management():
                return False

            self.logger.info("EDR authentication successful")
            return True

        except Exception as e:
            self.logger.error(f"EDR authentication failed: {str(e)}")
            return False

    def _get_initial_cookies(self) -> dict:
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

    def _step1_submit_password(self) -> bool:
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
            self.logger.info("Password accepted. MFA required.")
            return True
        except Exception as e:
            self.logger.error(f"Password submission failed: {str(e)}")
            return False

    def _step2_request_mfa_code(self) -> bool:
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

    def _step3_validate_mfa_code(self, code: str) -> bool:
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

    def _step4_register_page_access(self):
        """Register page access"""
        url = "https://retaillink2.wal-mart.com/rl_portal_services/api/Site/InsertRlPageDetails"
        params = {'pageId': '6', 'pageSubId': 'w6040', 'pageSubDesc': 'Event Management System'}
        try:
            self.session.get(url, params=params, timeout=10)
        except:
            pass

    def _step5_navigate_to_event_management(self):
        """Navigate to Event Management"""
        try:
            self.session.get("https://retaillink2.wal-mart.com/rl_portal/", timeout=10)
            self.session.get(f"{self.base_url}/", timeout=10)
        except:
            pass

    def _step6_authenticate_event_management(self) -> bool:
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
                                return True
                        except:
                            pass
            return False
        except Exception as e:
            self.logger.error(f"Event Management auth failed: {str(e)}")
            return False

    def get_edr_report(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get EDR report data for a specific event ID
        Matches the exact implementation from edr_printer/edr_report_generator.py
        """
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
        except requests.exceptions.RequestException as e:
            self.logger.error(f"EDR report retrieval failed for event {event_id}: {str(e)}")
            return {}
        except Exception as e:
            self.logger.error(f"Failed to get EDR report for event {event_id}: {str(e)}")
            return {}

    def generate_html_report(self, edr_data: Dict[str, Any], assigned_employee: str = "N/A") -> str:
        """Generate HTML report from EDR data - matches edr-printer terminal format exactly"""
        if not edr_data:
            return ""

        # Get current date and time for the report header
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")
        report_time = now.strftime("%H:%M:%S")

        # Extract event information
        event_number = edr_data.get('demoId', 'N/A')
        event_type = edr_data.get('demoClassCode', 'N/A')
        event_status = edr_data.get('demoStatusCode', 'N/A')
        event_date = edr_data.get('demoDate', 'N/A')
        event_name = edr_data.get('demoName', 'N/A')
        event_locked = edr_data.get('demoLockInd', 'N/A')

        # Instructions
        instructions = edr_data.get('demoInstructions', {})
        event_prep = instructions.get('demoPrepnTxt', 'N/A') if instructions else 'N/A'
        event_portion = instructions.get('demoPortnTxt', 'N/A') if instructions else 'N/A'

        # Item details
        item_details = edr_data.get('itemDetails', [])

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

        # Map event type and status codes to descriptions (from enhanced_edr_printer.py)
        event_type_codes = {
            '44': 'Event Type 44',  # This is what we see in your data
            '45': 'Food Demo/Sampling',
            '46': 'Beverage Demo',
            '47': 'Product Demonstration',
            '48': 'Special Event',
            '49': 'Promotional Event',
            '50': 'Tasting Event',
        }

        event_status_codes = {
            '2': 'Active/Scheduled',  # This is what we see in your data
            '1': 'Pending',
            '3': 'In Progress',
            '4': 'Completed',
            '5': 'Cancelled',
        }

        # Convert codes to descriptions
        event_type_display = event_type_codes.get(str(event_type), f"Event Type {event_type}")
        event_status_display = event_status_codes.get(str(event_status), f"Status {event_status}")

        # Complete HTML template - matches ReportLab enhanced_edr_printer format exactly
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Event Detail Report</title>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 40px 50px;
            font-size: 9pt;
            line-height: 1.3;
        }}

        .report-title {{
            text-align: center;
            font-size: 16pt;
            font-weight: bold;
            margin-bottom: 20px;
        }}

        .important-notice {{
            font-size: 8pt;
            line-height: 1.4;
            margin-bottom: 12px;
            text-align: justify;
        }}

        .important-notice b {{
            font-size: 8pt;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 2px;
        }}

        table.items {{
            margin-top: 10px;
            margin-bottom: 20px;
        }}

        th {{
            background-color: #d3d3d3;
            border: 1px solid black;
            padding: 5px 6px;
            text-align: left;
            font-weight: bold;
            font-size: 9pt;
        }}

        td {{
            border: 1px solid black;
            padding: 5px 6px;
            font-size: 9pt;
        }}

        table.items th,
        table.items td {{
            text-align: center;
            font-size: 8pt;
            padding: 4px 5px;
        }}

        .signature-header {{
            text-align: center;
            font-size: 11pt;
            font-weight: bold;
            margin-top: 25px;
            margin-bottom: 20px;
        }}

        .signature-row {{
            margin: 12px 0;
            font-size: 9pt;
            line-height: 1.8;
        }}

        @page {{
            size: letter;
            margin: 0.5in;
        }}

        @media print {{
            body {{
                margin: 0;
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="report-title">EVENT DETAIL REPORT</div>

    <div class="important-notice">
        <b>IMPORTANT!!!</b> This report should be printed each morning prior to completing each event.<br>
        1. The Event Details Report should be kept in the event prep area for each demonstrator to review instructions and item status.<br>
        2. The Event Co-ordinator should use this sheet when visiting the event area. Comments should be written to enter into the system at a later time.<br>
        3. Remember to scan items for product charge using the Club Use function on the handheld device.<br>
        Retention: This report should be kept in a monthly folder with the most recent being put in the front. The previous 6 months need to be kept accessible in the event prep area. Reports older than 6 months should be boxed and stored. Discard any report over 18 months old.
    </div>

    <table>
        <tr>
            <th style="width: 20%;">Event Number</th>
            <th style="width: 40%;">Event Type</th>
            <th style="width: 40%;">Event Locked</th>
        </tr>
        <tr>
            <td>{event_number}</td>
            <td>{event_type_display}</td>
            <td>{event_locked}</td>
        </tr>
    </table>

    <table>
        <tr>
            <th style="width: 20%;">Event Status</th>
            <th style="width: 20%;">Event Date</th>
            <th style="width: 60%;">Event Name</th>
        </tr>
        <tr>
            <td>{event_status_display}</td>
            <td>{event_date}</td>
            <td>{event_name}</td>
        </tr>
    </table>

    <table class="items">
        <thead>
            <tr>
                <th style="width: 15%;">Item Number</th>
                <th style="width: 22%;">Primary Item Number</th>
                <th style="width: 38%;">Description</th>
                <th style="width: 12%;">Vendor</th>
                <th style="width: 13%;">Category</th>
            </tr>
        </thead>
        <tbody>
            {item_rows}
        </tbody>
    </table>

    <div class="signature-header">MUST BE SIGNED AND DATED</div>

    <div class="signature-row">
        Event Specialist Assigned: <b>{assigned_employee}</b>
    </div>

    <div class="signature-row" style="margin-top: 20px;">
        Event Specialist Signature: ________________________________
    </div>

    <div class="signature-row">
        Date Event Performed: ________________________________
    </div>

    <div class="signature-row">
        Supervisor Signature: ________________________________
    </div>
</body>
</html>
        """

        return html_content.strip()
