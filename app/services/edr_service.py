"""
EDR Service Module
==================

Provides business logic for EDR (Event Detail Report) operations including:
- Walmart RetailLink authentication
- EDR data retrieval
- PDF generation for single and batch events

This service integrates the standalone EDR downloader functionality into the
main Flask application's Printing page.
"""

import os
import tempfile
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from flask import session

# Import database models
from app import db
from app.models import Event, Schedule, Employee

# Import EDR components
from app.integrations.edr import EDRReportGenerator, EDRPDFGenerator, AutomatedEDRPrinter, EnhancedEDRPrinter

# Import utility functions
from app.utils.event_helpers import extract_event_number

logger = logging.getLogger(__name__)


class EDRService:
    """
    Service class for EDR operations

    Handles authentication, data retrieval, and PDF generation for
    Walmart RetailLink Event Detail Reports.
    """

    def __init__(self):
        """Initialize EDR service"""
        self.logger = logging.getLogger(__name__)

    def initialize_edr_authenticator(self) -> EDRReportGenerator:
        """
        Initialize EDR authenticator with credentials from environment

        Returns:
            EDRReportGenerator instance

        Raises:
            ValueError: If credentials are not configured
        """
        # Get credentials from environment or Flask config
        username = os.environ.get('WALMART_USERNAME')
        password = os.environ.get('WALMART_PASSWORD')
        mfa_credential_id = os.environ.get('WALMART_MFA_PHONE')

        if not all([username, password, mfa_credential_id]):
            raise ValueError(
                "Walmart credentials not configured. Please set WALMART_USERNAME, "
                "WALMART_PASSWORD, and WALMART_MFA_PHONE environment variables."
            )

        # Create authenticator instance
        auth = EDRReportGenerator()
        auth.username = username
        auth.password = password
        auth.mfa_credential_id = mfa_credential_id

        return auth

    def request_mfa_code(self) -> bool:
        """
        Request MFA code to be sent to user's phone

        Returns:
            True if MFA code was requested successfully, False otherwise
        """
        try:
            self.logger.info("Requesting MFA code for EDR authentication")

            # Initialize authenticator
            auth = self.initialize_edr_authenticator()

            # Step 1: Submit password
            if not auth.step1_submit_password():
                self.logger.error("Failed to submit password")
                return False

            # Step 2: Request MFA code
            if not auth.step2_request_mfa_code():
                self.logger.error("Failed to request MFA code")
                return False

            # Store authenticator in session for next step
            session['edr_auth_pending'] = True
            session['edr_auth_session'] = {
                'cookies': dict(auth.session.cookies),
                'username': auth.username,
                'password': auth.password,
                'mfa_credential_id': auth.mfa_credential_id
            }

            self.logger.info("MFA code requested successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error requesting MFA code: {e}", exc_info=True)
            return False

    def complete_authentication(self, mfa_code: str) -> bool:
        """
        Complete authentication with MFA code

        Args:
            mfa_code: 6-digit MFA code from user's phone

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            self.logger.info("Completing EDR authentication with MFA code")

            # Check if we have pending auth
            if not session.get('edr_auth_pending'):
                self.logger.error("No pending authentication found")
                return False

            # Recreate authenticator from session
            auth = self.initialize_edr_authenticator()
            auth_session_data = session.get('edr_auth_session', {})

            # Restore session cookies
            for name, value in auth_session_data.get('cookies', {}).items():
                auth.session.cookies.set(name, value)

            # Step 3: Validate MFA code
            if not auth.step3_validate_mfa_code(mfa_code):
                self.logger.error("MFA code validation failed")
                return False

            # Step 4: Register page access
            if not auth.step4_register_page_access():
                self.logger.warning("Failed to register page access (non-critical)")

            # Step 5: Navigate to event management
            if not auth.step5_navigate_to_event_management():
                self.logger.warning("Failed to navigate to event management (non-critical)")

            # Step 6: Authenticate with Event Management API
            if not auth.step6_authenticate_event_management():
                self.logger.error("Failed to authenticate with Event Management API")
                return False

            # Store authenticated state in session
            session['edr_authenticated'] = True
            session['edr_auth_token'] = auth.auth_token
            session['edr_auth_session'] = {
                'cookies': dict(auth.session.cookies),
                'auth_token': auth.auth_token,
                'username': auth.username,
                'password': auth.password,
                'mfa_credential_id': auth.mfa_credential_id
            }
            session.pop('edr_auth_pending', None)

            self.logger.info("EDR authentication completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error completing authentication: {e}", exc_info=True)
            return False

    def get_authenticated_client(self) -> Optional[EDRReportGenerator]:
        """
        Get authenticated EDR client from session

        Returns:
            Authenticated EDRReportGenerator instance or None if not authenticated
        """
        if not session.get('edr_authenticated'):
            self.logger.warning("Attempted to get EDR client without authentication")
            return None

        try:
            # Recreate authenticator with session data
            auth = self.initialize_edr_authenticator()
            auth_session_data = session.get('edr_auth_session', {})

            # Restore auth token
            auth.auth_token = auth_session_data.get('auth_token')

            # Restore session cookies
            for name, value in auth_session_data.get('cookies', {}).items():
                auth.session.cookies.set(name, value)

            return auth

        except Exception as e:
            self.logger.error(f"Error getting authenticated client: {e}", exc_info=True)
            return None

    def get_events_for_date(self, target_date: str) -> List[Tuple[Schedule, Event, Employee]]:
        """
        Get all scheduled Core events for a specific date

        Args:
            target_date: Date string in YYYY-MM-DD format

        Returns:
            List of tuples (Schedule, Event, Employee)
        """
        try:
            # Parse date string
            date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()

            # Query scheduled Core events for the date
            schedules = db.session.query(
                Schedule, Event, Employee
            ).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).join(
                Employee, Schedule.employee_id == Employee.id
            ).filter(
                Schedule.schedule_datetime >= date_obj,
                Schedule.schedule_datetime < date_obj + timedelta(days=1),
                Event.event_type == 'Core'  # Only Core events have EDRs
            ).order_by(
                Schedule.schedule_datetime
            ).all()

            self.logger.info(f"Found {len(schedules)} Core events for date {target_date}")
            
            # NEW: Auto-assign shift blocks for Core events that don't have one
            # This is a fallback for events scheduled before the shift block system
            for schedule, event, employee in schedules:
                if schedule.shift_block is None:
                    try:
                        from app.services.shift_block_config import ShiftBlockConfig
                        block_num = ShiftBlockConfig.assign_next_available_block(
                            schedule, 
                            date_obj
                        )
                        if block_num:
                            self.logger.info(
                                f"Auto-assigned shift block {block_num} to schedule {schedule.id} "
                                f"(fallback for EDR generation)"
                            )
                    except Exception as e:
                        self.logger.warning(f"Could not auto-assign shift block: {e}")
            
            # Commit any shift block assignments
            try:
                db.session.commit()
            except Exception as e:
                self.logger.warning(f"Could not commit shift block assignments: {e}")
                db.session.rollback()
            
            return schedules

        except Exception as e:
            self.logger.error(f"Error querying events for date {target_date}: {e}", exc_info=True)
            return []

    def fetch_edr_data(self, event_number: str, auth_client: EDRReportGenerator) -> Optional[Dict[str, Any]]:
        """
        Fetch EDR data for a specific event number

        Args:
            event_number: 6-digit event number
            auth_client: Authenticated EDRReportGenerator instance

        Returns:
            EDR data dictionary or None if fetch failed
        """
        try:
            self.logger.info(f"Fetching EDR data for event {event_number}")
            edr_data = auth_client.get_edr_report(event_number)

            if edr_data:
                self.logger.info(f"Successfully fetched EDR for event {event_number}")
                return edr_data
            else:
                self.logger.warning(f"No EDR data found for event {event_number}")
                return None

        except Exception as e:
            self.logger.error(f"Error fetching EDR for event {event_number}: {e}", exc_info=True)
            return None

    def generate_single_edr_pdf(self, event_number: str, employee_name: str = 'N/A') -> Optional[bytes]:
        """
        Generate PDF for a single EDR

        Args:
            event_number: 6-digit event number
            employee_name: Name of assigned employee

        Returns:
            PDF bytes or None if generation failed
        """
        try:
            self.logger.info(f"Generating PDF for single EDR {event_number}")

            # Get authenticated client
            auth = self.get_authenticated_client()
            if not auth:
                self.logger.error("Not authenticated")
                return None

            # Fetch EDR data
            edr_data = self.fetch_edr_data(event_number, auth)
            if not edr_data:
                return None

            # Generate PDF
            pdf_generator = EDRPDFGenerator()

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                output_path = tmp.name

            try:
                # Generate PDF
                success = pdf_generator.generate_pdf(edr_data, output_path, employee_name)

                if not success:
                    self.logger.error(f"PDF generation failed for event {event_number}")
                    return None

                # Read PDF bytes
                with open(output_path, 'rb') as f:
                    pdf_bytes = f.read()

                self.logger.info(f"Successfully generated PDF for event {event_number} ({len(pdf_bytes)} bytes)")
                return pdf_bytes

            finally:
                # Clean up temporary file
                try:
                    os.remove(output_path)
                except:
                    pass

        except Exception as e:
            self.logger.error(f"Error generating single EDR PDF: {e}", exc_info=True)
            return None

    def generate_batch_edr_pdf(self, target_date: str) -> Optional[bytes]:
        """
        Generate consolidated PDF for all EDRs on a specific date

        Args:
            target_date: Date string in YYYY-MM-DD format

        Returns:
            PDF bytes or None if generation failed
        """
        try:
            self.logger.info(f"Generating batch EDR PDF for date {target_date}")

            # Get authenticated client
            auth = self.get_authenticated_client()
            if not auth:
                self.logger.error("Not authenticated")
                return None

            # Get scheduled events for the date
            schedules = self.get_events_for_date(target_date)

            if not schedules:
                self.logger.warning(f"No Core events found for date {target_date}")
                return None

            # Collect EDR data and employee mappings
            edr_data_list = []
            employee_mapping = {}

            for schedule, event, employee in schedules:
                # Extract event number from project name
                event_number = extract_event_number(event.project_name)

                if not event_number:
                    self.logger.warning(f"Could not extract event number from: {event.project_name}")
                    continue

                # Fetch EDR data
                edr_data = self.fetch_edr_data(event_number, auth)

                if edr_data:
                    edr_data_list.append(edr_data)
                    employee_mapping[str(edr_data.get('demoId'))] = employee.name

            if not edr_data_list:
                self.logger.warning(f"No EDR data retrieved for date {target_date}")
                return None

            self.logger.info(f"Retrieved {len(edr_data_list)} EDRs for date {target_date}")

            # Generate individual PDFs
            pdf_generator = EDRPDFGenerator()
            pdf_paths = []

            for edr_data in edr_data_list:
                event_id = str(edr_data.get('demoId'))
                employee_name = employee_mapping.get(event_id, 'N/A')

                # Create temporary file for individual PDF
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    pdf_path = tmp.name

                # Generate PDF
                success = pdf_generator.generate_pdf(edr_data, pdf_path, employee_name)

                if success:
                    pdf_paths.append(pdf_path)
                    self.logger.info(f"Generated PDF for event {event_id}")
                else:
                    self.logger.warning(f"Failed to generate PDF for event {event_id}")

            if not pdf_paths:
                self.logger.error("No PDFs were generated successfully")
                return None

            # Merge PDFs
            try:
                from PyPDF2 import PdfMerger

                # Create temporary file for merged PDF
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    output_path = tmp.name

                merger = PdfMerger()
                for pdf_path in pdf_paths:
                    merger.append(pdf_path)

                merger.write(output_path)
                merger.close()

                # Read merged PDF
                with open(output_path, 'rb') as f:
                    pdf_bytes = f.read()

                self.logger.info(
                    f"Successfully merged {len(pdf_paths)} PDFs into final document "
                    f"({len(pdf_bytes)} bytes)"
                )

                # Clean up merged PDF
                try:
                    os.remove(output_path)
                except:
                    pass

                return pdf_bytes

            finally:
                # Clean up individual PDFs
                for pdf_path in pdf_paths:
                    try:
                        os.remove(pdf_path)
                    except:
                        pass

        except Exception as e:
            self.logger.error(f"Error generating batch EDR PDF: {e}", exc_info=True)
            return None

    def is_authenticated(self) -> bool:
        """
        Check if user is authenticated for EDR operations

        Returns:
            True if authenticated, False otherwise
        """
        return session.get('edr_authenticated', False)

    def clear_authentication(self):
        """Clear EDR authentication from session"""
        session.pop('edr_authenticated', None)
        session.pop('edr_auth_token', None)
        session.pop('edr_auth_session', None)
        session.pop('edr_auth_pending', None)
        self.logger.info("EDR authentication cleared from session")


# Convenience functions for route handlers
_service_instance = None


def get_edr_service() -> EDRService:
    """
    Get singleton instance of EDRService

    Returns:
        EDRService instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = EDRService()
    return _service_instance


def request_edr_mfa_code() -> bool:
    """
    Request MFA code for EDR authentication

    Returns:
        True if successful, False otherwise
    """
    service = get_edr_service()
    return service.request_mfa_code()


def complete_edr_authentication(mfa_code: str) -> bool:
    """
    Complete EDR authentication with MFA code

    Args:
        mfa_code: 6-digit MFA code

    Returns:
        True if successful, False otherwise
    """
    service = get_edr_service()
    return service.complete_authentication(mfa_code)


def generate_single_edr_pdf(event_number: str, employee_name: str = 'N/A') -> Optional[bytes]:
    """
    Generate PDF for single EDR

    Args:
        event_number: 6-digit event number
        employee_name: Name of assigned employee

    Returns:
        PDF bytes or None if failed
    """
    service = get_edr_service()
    return service.generate_single_edr_pdf(event_number, employee_name)


def generate_daily_edrs_pdf(date_str: str) -> Optional[bytes]:
    """
    Generate consolidated PDF for all EDRs on a date

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        PDF bytes or None if failed
    """
    service = get_edr_service()
    return service.generate_batch_edr_pdf(date_str)


def is_edr_authenticated() -> bool:
    """
    Check if user is authenticated for EDR operations

    Returns:
        True if authenticated, False otherwise
    """
    service = get_edr_service()
    return service.is_authenticated()


def clear_edr_authentication():
    """Clear EDR authentication from session"""
    service = get_edr_service()
    service.clear_authentication()
