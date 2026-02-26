"""
Daily Paperwork Generator Service
===================================

This service generates comprehensive daily paperwork packages including:
- Daily Schedule (Core and Juicer events)
- Daily Item Numbers table
- Per-event documentation (EDR, SalesTool, Activity Log, Checklist)
"""

import os
import tempfile
import logging
import requests
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Dict, Optional, Any

# Set up logging (avoid print() which can cause BrokenPipeError in WSGI servers)
logger = logging.getLogger(__name__)


class CancelledEventError(Exception):
    """
    Raised when one or more scheduled events have been cancelled in the EDR system.

    This exception is used to block paperwork generation when cancelled events are detected,
    requiring the user to unschedule the affected events first.
    """
    def __init__(self, cancelled_events: list):
        self.cancelled_events = cancelled_events
        event_names = [f"• {e['event_number']}: {e['event_name']} (Employee: {e['employee_name']})"
                       for e in cancelled_events]
        self.message = (
            f"Cannot generate paperwork: {len(cancelled_events)} event(s) have been CANCELLED "
            f"in the Walmart EDR system:\n\n" + "\n".join(event_names) + "\n\n"
            f"Please unschedule these events and either:\n"
            f"1. Leave the assigned employee unscheduled (notify them of the change), or\n"
            f"2. Reschedule them to a different event."
        )
        super().__init__(self.message)


# Status codes that indicate a cancelled event
CANCELLED_STATUS_CODES = {'5', 'CANC', 'cancelled', 'Cancelled', 'CANCELLED'}


def is_cancelled_status(status_code: str) -> bool:
    """Check if a status code indicates a cancelled event."""
    if not status_code or status_code == 'N/A':
        return False
    return str(status_code).upper() in {'5', 'CANC', 'CANCELLED'}


# Import EDR components
from app.integrations.edr import EDRReportGenerator

try:
    from PyPDF2 import PdfMerger, PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as ReportLabImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from xhtml2pdf import pisa
    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image as PILImage
    PDF_LIBRARIES_AVAILABLE = True
except ImportError:
    PDF_LIBRARIES_AVAILABLE = False


class DailyPaperworkGenerator:
    """Generates consolidated daily paperwork packages"""

    def __init__(self, db_session, models_dict, session_api_service=None, edr_generator=None):
        """
        Initialize the generator

        Args:
            db_session: SQLAlchemy database session
            models_dict: Dictionary containing model classes (Event, Schedule, Employee)
            session_api_service: Optional SessionAPIService for authenticated downloads
            edr_generator: Optional authenticated EDRReportGenerator instance (from Flask session)
        """
        self.db = db_session
        self.models = models_dict
        self.session_api_service = session_api_service
        self.edr_generator = edr_generator  # Injected authenticated instance
        self.temp_files = []  # Track temp files for cleanup

    def initialize_edr_generator(self):
        """
        Initialize the EDR generator for authentication

        DEPRECATED: EDR generator should be passed via constructor from Flask session.
        This method is kept for backward compatibility only.
        """
        if not self.edr_generator:
            self.edr_generator = EDRReportGenerator()
        return self.edr_generator

    def request_mfa_code(self) -> bool:
        """
        Request MFA code for authentication

        DEPRECATED: Use the admin route /api/admin/edr/request-code instead.
        Authentication should be managed at the Flask session level.
        """
        if not self.edr_generator:
            self.initialize_edr_generator()
        return self.edr_generator.request_mfa_code()

    def complete_authentication(self, mfa_code: str) -> bool:
        """
        Complete authentication with MFA code

        DEPRECATED: Use the admin route /api/admin/edr/authenticate instead.
        Authentication should be managed at the Flask session level.
        """
        if not self.edr_generator:
            return False
        return self.edr_generator.complete_authentication_with_mfa_code(mfa_code)

    def _get_edr_status_description(self, status_code: str) -> str:
        """
        Convert EDR status code to human-readable description.

        Args:
            status_code: The status code from EDR API (e.g., '5', 'CANC', 'ACTV')

        Returns:
            Human-readable status description
        """
        if not status_code or status_code == 'N/A':
            return 'Unknown'

        # Status code mappings (same as in pdf_generator_base.py)
        status_map = {
            '1': 'Pending',
            '2': 'Active/Scheduled',
            '3': 'In Progress',
            '4': 'Completed',
            '5': 'Cancelled',
            '6': 'On Hold',
            '7': 'Under Review',
            '8': 'Approved',
            '9': 'Rejected',
            '10': 'Suspended',
            'ACTV': 'Active',
            'COMP': 'Completed',
            'CANC': 'Cancelled',
            'PEND': 'Pending',
            'HOLD': 'On Hold',
            'PREP': 'In Preparation',
            'SCHED': 'Scheduled',
            'INPR': 'In Progress',
            'SUSP': 'Suspended',
            'CLOS': 'Closed',
            'APPR': 'Approved',
            'REJE': 'Rejected',
            'SUBM': 'Submitted',
            'REVI': 'Under Review'
        }

        code_str = str(status_code).upper()
        return status_map.get(code_str, f'Status {status_code}')

    def generate_barcode_image(self, item_number: str) -> Optional[str]:
        """
        Generate a barcode image for an item number

        UPC-A Logic:
        - If UPC is 11 digits, pass it directly to the library (library calculates check digit)
        - If UPC is NOT 11 digits, pad with leading zeros to make it 11 digits
        - Example: 333832507 (9 digits) -> 00333832507 (11 digits) -> library adds check digit

        Args:
            item_number: Item number to generate barcode for

        Returns:
            Path to generated barcode image or None if failed
        """
        try:
            # Clean the item number (remove any non-digits)
            clean_number = ''.join(filter(str.isdigit, str(item_number)))

            if not clean_number:
                return None

            # UPC-A barcode logic
            if len(clean_number) <= 12:
                # Pad to 11 digits with leading zeros
                # The library will automatically calculate the 12th digit (check digit)
                upc_base = clean_number.zfill(11)

                try:
                    barcode_class = barcode.get_barcode_class('upca')
                    clean_number = upc_base  # Use the 11-digit base
                except:
                    # Fallback to Code128 if UPC-A fails
                    barcode_class = barcode.get_barcode_class('code128')
                    clean_number = str(item_number)
            else:
                # For numbers longer than 12 digits, use Code128 which is more flexible
                barcode_class = barcode.get_barcode_class('code128')
                clean_number = str(item_number)

            # Generate barcode image
            output_path = os.path.join(tempfile.gettempdir(), f'barcode_{item_number}_{datetime.now().strftime("%Y%m%d%H%M%S%f")}.png')

            # Create barcode with custom options for smaller size
            barcode_instance = barcode_class(clean_number, writer=ImageWriter())

            # Save with custom options for better PDF integration
            options = {
                'module_width': 0.2,  # Width of bars
                'module_height': 8.0,  # Height of bars in mm
                'quiet_zone': 2.0,    # Quiet zone in mm
                'font_size': 8,       # Font size for text
                'text_distance': 2.0, # Distance between bars and text
                'write_text': True,   # Show the number below barcode
            }

            barcode_instance.save(output_path.replace('.png', ''), options=options)

            # The library adds .png automatically
            final_path = output_path.replace('.png', '') + '.png'

            if os.path.exists(final_path):
                self.temp_files.append(final_path)
                return final_path

            return None

        except Exception as e:
            logger.warning(f" Failed to generate barcode for {item_number}: {e}")
            return None

    def get_events_for_date(self, target_date: datetime.date) -> List[Any]:
        """
        Get all scheduled events for a specific date

        Returns Core, Freeosk, and Digitals events for paperwork generation
        """
        Event = self.models['Event']
        Schedule = self.models['Schedule']
        Employee = self.models['Employee']

        # Query for Core, Freeosk, and Digitals events (needed for paperwork)
        # Freeosk Setup manuals are included on Fridays
        # Digital Setup manuals are included on Saturdays
        schedules = self.db.query(
            Schedule, Event, Employee
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            Schedule.schedule_datetime >= target_date,
            Schedule.schedule_datetime < target_date + timedelta(days=1),
            Event.event_type.in_(['Core', 'Freeosk', 'Digitals'])
        ).order_by(
            Schedule.schedule_datetime
        ).all()

        core_count = sum(1 for s, e, emp in schedules if e.event_type == 'Core')
        freeosk_count = sum(1 for s, e, emp in schedules if e.event_type == 'Freeosk')
        digitals_count = sum(1 for s, e, emp in schedules if e.event_type == 'Digitals')
        logger.info(f" Found {len(schedules)} events for {target_date} (Core: {core_count}, Freeosk: {freeosk_count}, Digitals: {digitals_count})")

        return schedules

    def generate_daily_schedule_pdf(self, target_date: datetime.date, schedules: List) -> str:
        """
        Generate the daily schedule PDF (same format as Print Today's Schedule)

        Returns:
            Path to generated PDF file
        """
        if not PDF_LIBRARIES_AVAILABLE:
            raise ImportError("PDF libraries required. Install: pip install reportlab xhtml2pdf PyPDF2")

        # Filter for Core and Juicer Production events
        filtered_schedules = []
        for schedule, event, employee in schedules:
            if event.event_type == 'Core' or event.event_type == 'Juicer Production':
                filtered_schedules.append((schedule, event, employee))

        # Sort by time
        filtered_schedules.sort(key=lambda x: x[0].schedule_datetime)

        # Generate HTML
        date_str = target_date.strftime('%A, %B %d, %Y')

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Core Events Schedule - {date_str}</title>
            <style>
                @page {{ size: letter; margin: 0.5in; }}
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    background: white;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    border-bottom: 3px solid #2E4C73;
                    padding-bottom: 20px;
                }}
                .date-title {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2E4C73;
                    margin: 0;
                }}
                .subtitle {{
                    font-size: 16px;
                    color: #666;
                    margin: 5px 0 0 0;
                }}
                .schedule-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                .schedule-table th {{
                    background: #2E4C73;
                    color: white;
                    padding: 12px;
                    text-align: left;
                    font-weight: bold;
                    font-size: 14px;
                    border: 1px solid #ddd;
                }}
                .schedule-table td {{
                    padding: 10px 12px;
                    border: 1px solid #ddd;
                    font-size: 13px;
                }}
                .schedule-table tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .employee-name {{
                    font-weight: bold;
                    color: #2E4C73;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <p class="date-title">{date_str}</p>
                <p class="subtitle">CORE Events Schedule</p>
            </div>
            <table class="schedule-table">
                <thead>
                    <tr>
                        <th style="width: 15%;">Time</th>
                        <th style="width: 35%;">Employee</th>
                        <th style="width: 50%;">Event</th>
                    </tr>
                </thead>
                <tbody>
        """

        for schedule, event, employee in filtered_schedules:
            time_str = schedule.schedule_datetime.strftime('%I:%M %p')
            html += f"""
                    <tr>
                        <td>{time_str}</td>
                        <td class="employee-name">{employee.name}</td>
                        <td>{event.project_name}</td>
                    </tr>
            """

        html += """
                </tbody>
            </table>
        </body>
        </html>
        """

        # Generate PDF
        output_path = os.path.join(tempfile.gettempdir(), f'daily_schedule_{target_date.strftime("%Y%m%d")}.pdf')
        with open(output_path, 'wb') as pdf_file:
            pisa_status = pisa.CreatePDF(BytesIO(html.encode('utf-8')), dest=pdf_file)

        if pisa_status.err:
            raise Exception("Failed to generate daily schedule PDF")

        self.temp_files.append(output_path)
        return output_path

    def generate_item_numbers_pdf(self, edr_data_list: List, target_date: datetime.date) -> str:
        """
        Generate Daily Item Numbers table PDF from EDR data

        Args:
            edr_data_list: List of EDR data dictionaries
            target_date: Date for display

        Returns:
            Path to generated PDF file
        """
        if not PDF_LIBRARIES_AVAILABLE:
            raise ImportError("PDF libraries required")

        # Collect items grouped by event (no deduplication - items appear under each event)
        event_groups = []  # List of dicts: {event_id, event_name, items}
        total_items = 0

        for edr_data in edr_data_list:
            if not edr_data:
                continue

            event_id = str(edr_data.get('demoId', 'N/A'))
            event_name = str(edr_data.get('demoName', 'N/A'))
            item_details = edr_data.get('itemDetails', [])
            if item_details is None:
                continue

            event_items = []
            for item in item_details:
                item_nbr = str(item.get('itemNbr', ''))
                upc_nbr = str(item.get('gtin', ''))  # UPC number (gtin field) for barcode generation
                item_desc = str(item.get('itemDesc', ''))

                if item_nbr and item_nbr != 'N/A':
                    # Use gtin (UPC) if available, otherwise fall back to itemNbr
                    barcode_number = upc_nbr if upc_nbr and upc_nbr not in ['', 'N/A', 'None'] else item_nbr

                    # Debug logging for first few items per event
                    if len(event_items) < 3:
                        logger.debug(f" Item {item_nbr}: upcNbr='{upc_nbr}', using '{barcode_number}' for barcode")

                    event_items.append((item_nbr, barcode_number, item_desc))

            if event_items:
                event_groups.append({
                    'event_id': event_id,
                    'event_name': event_name,
                    'items': event_items
                })
                total_items += len(event_items)

        # Create PDF
        output_path = os.path.join(tempfile.gettempdir(), f'daily_item_numbers_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')
        doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)

        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2E4C73')
        )
        story.append(Paragraph("Daily Item Numbers", title_style))
        story.append(Spacer(1, 12))

        # Date
        date_str = target_date.strftime('%A, %B %d, %Y')
        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontSize=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        )
        story.append(Paragraph(date_str, date_style))
        story.append(Spacer(1, 12))

        # Help text
        help_text = "Use this list for getting the next day's product and printing price signs."
        help_style = ParagraphStyle(
            'HelpStyle',
            parent=styles['Normal'],
            fontSize=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        )
        story.append(Paragraph(help_text, help_style))
        story.append(Spacer(1, 20))

        # Event header style
        event_header_style = ParagraphStyle(
            'EventHeader',
            parent=styles['Heading2'],
            fontSize=13,
            spaceBefore=6,
            spaceAfter=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2E4C73'),
            borderWidth=0,
            borderColor=colors.HexColor('#2E4C73'),
            borderPadding=4,
        )

        # Table style template for each event's items
        item_table_style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E4C73')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            # Data rows
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            # Borders and alignment
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DDDDDD')),
            # Padding
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ])

        # Render each event group with header + items table
        if event_groups:
            for group in event_groups:
                # Event section header
                header_text = f"{group['event_id']} - {group['event_name']}"
                story.append(Paragraph(header_text, event_header_style))

                # Build table for this event's items
                table_data = [['UPC Number', 'Barcode', 'Description']]
                for item_num, barcode_num, desc in group['items']:
                    barcode_path = self.generate_barcode_image(barcode_num)
                    if barcode_path:
                        barcode_img = ReportLabImage(barcode_path, width=1.2*inch, height=0.5*inch)
                        table_data.append([str(barcode_num), barcode_img, str(desc)])
                    else:
                        table_data.append([str(barcode_num), 'N/A', str(desc)])

                item_table = Table(table_data, colWidths=[1.2*inch, 1.5*inch, 3.8*inch])
                item_table.setStyle(item_table_style)
                story.append(item_table)
                story.append(Spacer(1, 16))

            # Summary
            story.append(Spacer(1, 8))
            summary_style = ParagraphStyle(
                'SummaryStyle',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.HexColor('#2E4C73'),
                fontName='Helvetica-Bold'
            )
            summary_text = f"Total Items: {total_items}"
            story.append(Paragraph(summary_text, summary_style))
        else:
            story.append(Paragraph("No items found for today's events.", styles['Normal']))

        doc.build(story)
        self.temp_files.append(output_path)
        return output_path

    def get_event_edr_pdf(self, event_mplan_id: str, employee_name: str) -> Optional[str]:
        """
        Get EDR PDF for an event (fetches EDR data first)

        Returns:
            Path to EDR PDF file or None if failed
        """
        if not self.edr_generator or not self.edr_generator.auth_token:
            logger.error(" Not authenticated for EDR retrieval")
            return None

        try:
            # Import EDRPDFGenerator
            from app.integrations.edr import EDRPDFGenerator

            # Get EDR data
            edr_data = self.edr_generator.get_edr_report(event_mplan_id)
            if not edr_data:
                logger.warning(f" No EDR data for event {event_mplan_id}")
                return None

            # Use EDRPDFGenerator instead of xhtml2pdf (which has CSS compatibility issues)
            output_path = os.path.join(tempfile.gettempdir(), f'edr_{event_mplan_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')

            pdf_generator = EDRPDFGenerator()
            if pdf_generator.generate_pdf(edr_data, output_path, employee_name):
                self.temp_files.append(output_path)
                logger.info(f" EDR PDF generated for event {event_mplan_id}")
                return output_path
            else:
                logger.error(f" Failed to generate EDR PDF for {event_mplan_id}")
                return None

        except Exception as e:
            logger.error(f" Error getting EDR for {event_mplan_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_event_edr_pdf_from_data(self, edr_data: Dict, event_mplan_id: str, employee_name: str, schedule_info: Optional[Dict] = None) -> Optional[str]:
        """
        Generate EDR PDF from already-fetched EDR data (for efficiency in batch operations)

        Args:
            edr_data: Pre-fetched EDR data dictionary
            event_mplan_id: Event mPlan ID for filename
            employee_name: Employee name to include in PDF
            schedule_info: Optional dict with 'scheduled_date', 'start_date', 'due_date'

        Returns:
            Path to EDR PDF file or None if failed
        """
        try:
            # Import EDRPDFGenerator
            from app.integrations.edr import EDRPDFGenerator

            if not edr_data:
                logger.warning(f" No EDR data provided for event {event_mplan_id}")
                return None

            # Use EDRPDFGenerator to create PDF
            output_path = os.path.join(tempfile.gettempdir(), f'edr_{event_mplan_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')

            pdf_generator = EDRPDFGenerator()
            if pdf_generator.generate_pdf(edr_data, output_path, employee_name, schedule_info):
                self.temp_files.append(output_path)
                return output_path
            else:
                logger.error(f" Failed to generate EDR PDF for {event_mplan_id}")
                return None

        except Exception as e:
            logger.error(f" Error generating EDR PDF for {event_mplan_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_digital_setup_manual(self, mplan_id: str, store_id: str) -> Optional[str]:
        """
        Get Digital Setup instruction manual from MVRetail API

        Uses the same API endpoint as Freeosk manuals.
        The API returns a JSON response with a URL to the merged PDF, which we then download.

        Args:
            mplan_id: The mPlan ID from the Digital Setup event name (number in parentheses)
            store_id: The store number

        Returns:
            Path to downloaded PDF or None if failed
        """
        if not mplan_id or not store_id:
            logger.warning(f" Missing mplan_id ({mplan_id}) or store_id ({store_id}) for Digital Setup manual")
            return None

        try:
            import json
            import urllib.parse

            # Build the API request
            api_url = "https://crossmark.mvretail.com/planningextcontroller/bulkPrintMplanLocations"

            # Create the data payload
            mplan_locations = [{"mPlanID": mplan_id, "storeID": store_id}]
            data = {
                'mplanLocationIDs': json.dumps(mplan_locations),
                'includeAttachment': 'true'
            }

            logger.info(f" Fetching Digital Setup manual for mPlanID {mplan_id}, store {store_id}")
            logger.info(f" Request data: {data}")

            # Use authenticated session if available (for Crossmark URLs)
            if self.session_api_service and hasattr(self.session_api_service, 'session'):
                logger.info(f" Using authenticated session for Digital Setup manual")
                # When using authenticated session, just set minimal headers
                # The session already has cookies and authentication
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                }

                # Disable retries to see actual error response
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry

                # Create a session with no retries
                retry_strategy = Retry(total=0)
                adapter = HTTPAdapter(max_retries=retry_strategy)
                self.session_api_service.session.mount("https://", adapter)

                response = self.session_api_service.session.post(
                    api_url,
                    headers=headers,
                    data=data,
                    timeout=30
                )
            else:
                logger.warning(f" No authenticated session available for Digital Setup manual - request may fail")
                # Without authenticated session, include full browser headers
                headers = {
                    'accept': '*/*',
                    'accept-language': 'en-US,en;q=0.9',
                    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'origin': 'https://crossmark.mvretail.com',
                    'referer': 'https://crossmark.mvretail.com/planning/',
                    'x-requested-with': 'XMLHttpRequest'
                }
                response = requests.post(api_url, headers=headers, data=data, timeout=30)

            logger.info(f" Response status: {response.status_code}")
            logger.info(f" Response headers: {dict(response.headers)}")

            # Log response content before raising for status
            if response.status_code >= 400:
                logger.error(f" Error response body: {response.text[:2000]}")

            response.raise_for_status()

            # Parse JSON response
            try:
                json_response = response.json()
                logger.info(f" API response: {json_response}")
            except Exception as json_err:
                logger.error(f" Failed to parse JSON response: {json_err}")
                logger.error(f" Response text: {response.text[:500]}")
                return None

            # Extract PDF URL from response
            if not json_response.get('success'):
                logger.error(f" API returned success=false: {json_response.get('message', 'No message')}")
                return None

            pdf_url = json_response.get('mergedPdf')
            if not pdf_url:
                logger.error(f" No mergedPdf URL in response: {json_response}")
                return None

            logger.info(f" Downloading PDF from: {pdf_url}")

            # S3 URLs use pre-signed authentication, not cookies
            # Use plain request with exact browser headers from HAR analysis
            pdf_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'Referer': 'https://crossmark.mvretail.com/',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }

            logger.info(f" Downloading PDF from S3 with exact browser headers (no cookies)")
            pdf_response = requests.get(pdf_url, headers=pdf_headers, timeout=60)

            if pdf_response.status_code != 200:
                logger.error(f" PDF download failed with status {pdf_response.status_code}")
                logger.error(f" Response headers: {dict(pdf_response.headers)}")
                logger.error(f" Response body: {pdf_response.text[:500]}")

            pdf_response.raise_for_status()

            # Verify it's a PDF
            if len(pdf_response.content) > 4:
                pdf_magic = pdf_response.content[:4]
                if pdf_magic != b'%PDF':
                    logger.warning(f" Downloaded file does not start with PDF magic bytes: {pdf_magic}")
                    return None

            # Save the downloaded PDF temporarily
            temp_pdf_path = os.path.join(tempfile.gettempdir(), f'digital_original_{mplan_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')
            with open(temp_pdf_path, 'wb') as f:
                f.write(pdf_response.content)

            # Save as final output and return
            output_path = os.path.join(tempfile.gettempdir(), f'digital_setup_manual_{mplan_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')

            # Rename temp file to final output path
            import shutil
            shutil.move(temp_pdf_path, output_path)

            logger.info(f" ✓ Digital Setup manual saved successfully ({len(pdf_response.content):,} bytes)")

            self.temp_files.append(output_path)
            return output_path

        except Exception as e:
            logger.error(f" ✗ Failed to download Digital Setup manual for mPlanID {mplan_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_freeosk_setup_manual(self, mplan_id: str, store_id: str) -> Optional[str]:
        """
        Get Freeosk setup manual from MVRetail API

        The API returns a JSON response with a URL to the merged PDF, which we then download.

        Args:
            mplan_id: The mPlan ID from the Freeosk event name (number in parentheses)
            store_id: The store number

        Returns:
            Path to downloaded PDF or None if failed
        """
        if not mplan_id or not store_id:
            logger.warning(f" Missing mplan_id ({mplan_id}) or store_id ({store_id}) for Freeosk manual")
            return None

        try:
            import json
            import urllib.parse

            # Build the API request
            api_url = "https://crossmark.mvretail.com/planningextcontroller/bulkPrintMplanLocations"

            # Create the data payload
            mplan_locations = [{"mPlanID": mplan_id, "storeID": store_id}]
            data = {
                'mplanLocationIDs': json.dumps(mplan_locations),
                'includeAttachment': 'true'
            }

            logger.info(f" Fetching Freeosk setup manual for mPlanID {mplan_id}, store {store_id}")
            logger.info(f" Request data: {data}")

            # Use authenticated session if available (for Crossmark URLs)
            if self.session_api_service and hasattr(self.session_api_service, 'session'):
                logger.info(f" Using authenticated session for Freeosk manual")

                # Full headers matching working browser request
                headers = {
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Origin': 'https://crossmark.mvretail.com',
                    'Referer': 'https://crossmark.mvretail.com/planning/',
                    'X-Requested-With': 'XMLHttpRequest',
                    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
                }

                # Log cookies being sent for debugging
                cookies = self.session_api_service.session.cookies.get_dict()
                logger.info(f" Cookies in session: {list(cookies.keys())}")
                if 'PHPSESSID' in cookies:
                    logger.info(f" ✓ PHPSESSID cookie present: {cookies['PHPSESSID'][:10]}...")
                else:
                    logger.warning(f" ✗ PHPSESSID cookie missing!")

                # Disable retries to see actual error response
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry

                # Create a session with no retries
                retry_strategy = Retry(total=0)
                adapter = HTTPAdapter(max_retries=retry_strategy)
                self.session_api_service.session.mount("https://", adapter)

                logger.info(f" Making authenticated POST to {api_url}")

                response = self.session_api_service.session.post(
                    api_url,
                    headers=headers,
                    data=data,
                    timeout=90  # Increased timeout - MVRetail API can be slow
                )
            else:
                logger.warning(f" No authenticated session available for Freeosk manual - request may fail")
                # Without authenticated session, include full browser headers
                headers = {
                    'accept': '*/*',
                    'accept-language': 'en-US,en;q=0.9',
                    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'origin': 'https://crossmark.mvretail.com',
                    'referer': 'https://crossmark.mvretail.com/planning/',
                    'x-requested-with': 'XMLHttpRequest'
                }
                response = requests.post(api_url, headers=headers, data=data, timeout=90)

            logger.info(f" Response status: {response.status_code}")
            logger.info(f" Response headers: {dict(response.headers)}")

            # Log response content before raising for status
            if response.status_code >= 400:
                logger.error(f" Error response body: {response.text[:2000]}")

            response.raise_for_status()

            # Parse JSON response
            try:
                json_response = response.json()
                logger.info(f" API response: {json_response}")
            except Exception as json_err:
                logger.error(f" Failed to parse JSON response: {json_err}")
                logger.error(f" Response text: {response.text[:500]}")
                return None

            # Extract PDF URL from response
            if not json_response.get('success'):
                logger.error(f" API returned success=false: {json_response.get('message', 'No message')}")
                return None

            pdf_url = json_response.get('mergedPdf')
            if not pdf_url:
                logger.error(f" No mergedPdf URL in response: {json_response}")
                return None

            logger.info(f" Downloading PDF from: {pdf_url}")

            # CRITICAL: S3 pre-signed URLs contain authentication in query parameters
            # Any extra headers can break the signature and cause 403 Forbidden
            # Use absolutely NO headers - the URL signature is all we need
            logger.info(f" Downloading PDF from S3 (no headers - using pre-signed URL)")

            # Use completely fresh request with no session, no cookies, no headers
            pdf_response = requests.get(pdf_url, timeout=60)

            if pdf_response.status_code != 200:
                logger.error(f" PDF download failed with status {pdf_response.status_code}")
                logger.error(f" Response headers: {dict(pdf_response.headers)}")
                logger.error(f" Response body: {pdf_response.text[:500]}")

            pdf_response.raise_for_status()

            # Verify it's a PDF
            if len(pdf_response.content) > 4:
                pdf_magic = pdf_response.content[:4]
                if pdf_magic != b'%PDF':
                    logger.warning(f" Downloaded file does not start with PDF magic bytes: {pdf_magic}")
                    return None

            # Save the downloaded PDF temporarily
            temp_pdf_path = os.path.join(tempfile.gettempdir(), f'freeosk_original_{mplan_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')
            with open(temp_pdf_path, 'wb') as f:
                f.write(pdf_response.content)

            # Save as final output and return
            output_path = os.path.join(tempfile.gettempdir(), f'freeosk_manual_{mplan_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')

            # Rename temp file to final output path
            import shutil
            shutil.move(temp_pdf_path, output_path)

            logger.info(f" ✓ Freeosk manual saved successfully ({len(pdf_response.content):,} bytes)")

            self.temp_files.append(output_path)
            return output_path

        except Exception as e:
            logger.error(f" ✗ Failed to download Freeosk manual for mPlanID {mplan_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _fetch_sales_tool_url_from_api(self, event) -> Optional[str]:
        """
        Fetch salesToolUrl from external API (getPlanningMplans) for an event.

        Args:
            event: Event object with external_id (mPlanID)

        Returns:
            salesToolUrl string or None if not found
        """
        if not self.session_api_service:
            logger.warning(" No session API service available to fetch salesToolUrl")
            return None

        mplan_id = event.external_id or str(event.project_ref_num)
        if not mplan_id:
            logger.warning(f" No mPlanID for event: {event.project_name}")
            return None

        try:
            logger.info(f" Fetching mplan data from API for mPlanID: {mplan_id}")
            mplan_data = self.session_api_service.get_mplan_by_id(mplan_id)

            if mplan_data:
                # Extract salesToolUrl from salesTools array
                sales_tools = mplan_data.get('salesTools', [])
                if sales_tools and isinstance(sales_tools, list) and len(sales_tools) > 0:
                    if isinstance(sales_tools[0], dict):
                        sales_tool_url = sales_tools[0].get('salesToolURL')
                        if sales_tool_url:
                            logger.info(f" Found salesToolUrl: {sales_tool_url[:50]}...")
                            return sales_tool_url

                logger.warning(f" No salesTools found in API response for mPlanID: {mplan_id}")
                return None
            else:
                logger.warning(f" No mplan data returned from API for mPlanID: {mplan_id}")
                return None

        except Exception as e:
            logger.error(f" Error fetching salesToolUrl from API: {e}")
            return None

    def get_salestool_pdf(self, salestool_url: str, event_ref: str) -> Optional[str]:
        """
        Download SalesTool PDF from URL using authenticated session if available

        Returns:
            Path to downloaded PDF or None if failed
        """
        if not salestool_url:
            return None

        try:
            # Use authenticated session if available (for Crossmark URLs)
            if self.session_api_service and hasattr(self.session_api_service, 'session'):
                logger.info(f" Downloading SalesTool with authenticated session: {salestool_url}")
                response = self.session_api_service.session.get(salestool_url, timeout=30)
            else:
                logger.info(f" Downloading SalesTool (no auth): {salestool_url}")
                response = requests.get(salestool_url, timeout=30)

            response.raise_for_status()

            # Check if response is actually a PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and 'application/octet-stream' not in content_type.lower():
                logger.warning(f" URL {salestool_url} did not return PDF (Content-Type: {content_type})")
                logger.debug(f"Response size: {len(response.content)} bytes")
                if len(response.content) < 10000:  # Likely an error page
                    logger.debug(f"Response preview: {response.text[:500]}")
                return None

            # Verify content is actually PDF by checking magic bytes
            if len(response.content) > 4:
                pdf_magic = response.content[:4]
                if pdf_magic != b'%PDF':
                    logger.warning(f" Response does not start with PDF magic bytes: {pdf_magic}")
                    return None

            output_path = os.path.join(tempfile.gettempdir(), f'salestool_{event_ref}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')
            with open(output_path, 'wb') as f:
                f.write(response.content)

            file_size = len(response.content)
            logger.info(f" Downloaded SalesTool PDF ({file_size:,} bytes)")

            self.temp_files.append(output_path)
            return output_path

        except Exception as e:
            logger.warning(f" Failed to download SalesTool from {salestool_url}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def merge_pdfs(self, pdf_paths: List[str], output_path: str) -> bool:
        """
        Merge multiple PDFs into one

        Returns:
            True if successful
        """
        if not PDF_LIBRARIES_AVAILABLE:
            return False

        try:
            merger = PdfMerger()

            for pdf_path in pdf_paths:
                if pdf_path and os.path.exists(pdf_path):
                    merger.append(pdf_path)

            merger.write(output_path)
            merger.close()
            return True

        except Exception as e:
            logger.error(f" Failed to merge PDFs: {e}")
            return False

    def generate_complete_daily_paperwork(self, target_date: datetime.date) -> Optional[str]:
        """
        Generate complete daily paperwork package

        Returns:
            Path to final consolidated PDF
        """
        logger.info(f" Generating daily paperwork for {target_date.strftime('%Y-%m-%d')}...")

        # Get events for the date
        schedules = self.get_events_for_date(target_date)
        if not schedules:
            logger.warning(" No events found for this date")
            return None

        logger.info(f" Found {len(schedules)} scheduled events")

        # Get the Primary Lead for this date from rotation assignments
        # Primary Lead always gets shift block 1 (which has the first lunch time)
        primary_lead_id = None
        try:
            from app.services.rotation_manager import RotationManager
            from app.models.registry import get_models
            # Use registry to get full models dict (includes RotationAssignment, ScheduleException)
            full_models = get_models()
            rotation_manager = RotationManager(self.db, full_models)
            primary_lead = rotation_manager.get_rotation_employee(
                datetime.combine(target_date, datetime.min.time()), 
                'primary_lead'
            )
            if primary_lead:
                primary_lead_id = primary_lead.id
                logger.info(f" Primary Lead for {target_date}: {primary_lead.name} ({primary_lead_id}) - will get shift block 1")
        except Exception as e:
            logger.warning(f" Could not get Primary Lead: {e}")

        # Pre-assign shift blocks for ALL Core schedules using start-time grouping
        # This must happen before individual event processing to get correct block assignments
        core_schedules = [(s, e, emp) for s, e, emp in schedules if e.event_type == 'Core']
        if core_schedules:
            try:
                from app.services.shift_block_config import ShiftBlockConfig
                logger.info(f" Assigning shift blocks for {len(core_schedules)} Core events using start-time grouping...")
                block_assignments = ShiftBlockConfig.assign_blocks_for_date(
                    core_schedules, target_date, primary_lead_id=primary_lead_id
                )
                if block_assignments:
                    self.db.commit()
                    logger.info(f" Assigned {len(block_assignments)} shift blocks: {block_assignments}")
            except Exception as e:
                logger.warning(f" Could not assign shift blocks: {e}")

        # List to hold all PDF paths in order
        all_pdfs = []

        # 1. Generate Daily Schedule
        logger.info(" Generating daily schedule...")
        schedule_pdf = self.generate_daily_schedule_pdf(target_date, schedules)
        all_pdfs.append(schedule_pdf)

        # 2. First check for cancelled events from database (synced from Crossmark API)
        # This catches cancelled events BEFORE we try to fetch EDR data
        cancelled_events = []  # Track cancelled events to block generation
        from app.utils.event_helpers import get_walmart_event_id

        for schedule, event, employee in schedules:
            # Check if event is cancelled in the Crossmark system (condition field)
            if event.condition and event.condition.lower() == 'canceled':
                event_num = get_walmart_event_id(event)
                logger.warning(f" EVENT {event_num} is CANCELLED (from Crossmark API)! Cannot include in paperwork.")
                cancelled_events.append({
                    'event_number': event_num or str(event.project_ref_num),
                    'event_name': event.project_name,
                    'employee_name': employee.name if employee else 'Unassigned',
                    'edr_status': 'Canceled (Crossmark)'
                })

        # If cancelled events found from database, block immediately
        if cancelled_events:
            logger.error(f" BLOCKING PAPERWORK GENERATION: {len(cancelled_events)} cancelled event(s) found in database")
            raise CancelledEventError(cancelled_events)

        # 3. Fetch all EDR data using get_edr_report() for each event
        logger.info(" Fetching EDR data using direct API calls...")
        edr_data_cache = {}  # Cache: event_number -> edr_data
        edr_data_list = []

        if self.edr_generator:

            # Check if we need to authenticate
            if not self.edr_generator.auth_token:
                logger.error(" Not authenticated - cannot fetch EDR data")
                logger.info(" Please authenticate via the printing interface first")
            else:
                # Fetch EDR data for ALL scheduled events to check for cancelled status
                # This ensures we catch cancelled events regardless of event type
                for schedule, event, employee in schedules:
                    event_num = get_walmart_event_id(event)
                    if event_num:
                        logger.info(f" Fetching EDR for event {event_num} ({event.event_type}) via get_edr_report()...")

                        try:
                            # Call get_edr_report() directly for this event
                            edr_data = self.edr_generator.get_edr_report(event_num)

                            if edr_data:
                                # Check EDR status and update the Event model
                                edr_status_code = edr_data.get('demoStatusCode', 'N/A')
                                edr_status_desc = self._get_edr_status_description(edr_status_code)

                                # Update event's EDR status in database
                                try:
                                    event.edr_status = edr_status_desc
                                    event.edr_status_updated = datetime.now()
                                    self.db.commit()
                                    logger.info(f" Updated EDR status for event {event_num}: {edr_status_desc}")
                                except Exception as db_err:
                                    logger.warning(f" Could not update EDR status in database: {db_err}")

                                # Check if event is CANCELLED - block paperwork generation
                                if is_cancelled_status(edr_status_code):
                                    logger.warning(f" EVENT {event_num} IS CANCELLED! Cannot include in paperwork.")
                                    cancelled_events.append({
                                        'event_number': event_num,
                                        'event_name': event.project_name,
                                        'employee_name': employee.name if employee else 'Unassigned',
                                        'edr_status': edr_status_desc
                                    })
                                    continue  # Don't add to cache for PDF generation

                                # Only add Core events to the EDR cache for PDF generation
                                if event.event_type == 'Core':
                                    edr_data_cache[event_num] = edr_data
                                    edr_data_list.append(edr_data)

                                    # Verify gtin field is present
                                    item_details = edr_data.get('itemDetails', [])
                                    if item_details and len(item_details) > 0:
                                        first_item = item_details[0]
                                        gtin = first_item.get('gtin', 'N/A')
                                        logger.info(f" Event {event_num} fetched - {len(item_details)} items, first GTIN: {gtin}")
                                    else:
                                        logger.info(f" Event {event_num} fetched - no items")
                            else:
                                logger.warning(f" Event {event_num} returned no data")
                        except Exception as e:
                            logger.error(f" Failed to fetch event {event_num}: {e}")

        # CRITICAL: If any events are cancelled, stop generation and notify user
        if cancelled_events:
            logger.error(f" BLOCKING PAPERWORK GENERATION: {len(cancelled_events)} cancelled event(s) found")
            raise CancelledEventError(cancelled_events)

        # 3. Generate Daily Item Numbers from EDR data
        logger.info(" Generating daily item numbers...")
        items_pdf = self.generate_item_numbers_pdf(edr_data_list, target_date)
        all_pdfs.append(items_pdf)

        # 3b. Add Freeosk Setup manuals (Fridays) or Digital Setup manuals (Saturdays) after items list
        if target_date.weekday() == 4:  # Friday - add Freeosk Setup manuals
            logger.info(" Friday detected - looking for Freeosk Setup (LKD-FSK) manuals...")
            for schedule, event, employee in schedules:
                if event.event_type == 'Freeosk' and 'LKD-FSK' in (event.project_name or ''):
                    if hasattr(event, 'sales_tools_url') and event.sales_tools_url:
                        logger.info(f" Downloading Freeosk Setup manual for {event.project_name}...")
                        freeosk_pdf = self.get_salestool_pdf(event.sales_tools_url, event.project_ref_num)
                        if freeosk_pdf:
                            all_pdfs.append(freeosk_pdf)
                            logger.info(f" Freeosk Setup manual added after items list")
                        else:
                            logger.warning(f" Could not download Freeosk Setup manual for event {event.project_ref_num}")
                    else:
                        logger.warning(f" No sales_tools_url for Freeosk event: {event.project_name}")

        elif target_date.weekday() == 5:  # Saturday - add Digital Setup manuals
            logger.info(" Saturday detected - looking for Digital Setup manuals...")
            for schedule, event, employee in schedules:
                if event.event_type == 'Digitals' and 'Setup' in (event.project_name or ''):
                    if hasattr(event, 'sales_tools_url') and event.sales_tools_url:
                        logger.info(f" Downloading Digital Setup manual for {event.project_name}...")
                        digital_pdf = self.get_salestool_pdf(event.sales_tools_url, event.project_ref_num)
                        if digital_pdf:
                            all_pdfs.append(digital_pdf)
                            logger.info(f" Digital Setup manual added after items list")
                        else:
                            logger.warning(f" Could not download Digital Setup manual for event {event.project_ref_num}")
                    else:
                        logger.warning(f" No sales_tools_url for Digital Setup event: {event.project_name}")

        # 4. For each event, generate EDR, SalesTool, and dynamic templates from database
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs')

        # Load dynamic templates from database - separated by category
        logger.info(" Loading paperwork templates from database...")
        PaperworkTemplate = self.models.get('PaperworkTemplate')
        event_templates = []  # Templates to add for each event
        daily_templates = []  # Templates to add once at the end

        if PaperworkTemplate:
            try:
                templates = PaperworkTemplate.query.filter_by(is_active=True).order_by(PaperworkTemplate.display_order).all()
                for template in templates:
                    template_path = os.path.join(docs_dir, template.file_path)
                    if os.path.exists(template_path):
                        template_info = {
                            'name': template.name,
                            'path': template_path,
                            'order': template.display_order
                        }
                        # Separate by category: 'event' vs 'daily'
                        if template.category == 'daily':
                            daily_templates.append(template_info)
                            logger.info(f" Loaded daily template: {template.name}")
                        else:
                            event_templates.append(template_info)
                            logger.info(f" Loaded event template: {template.name}")
                    else:
                        logger.warning(f" Template file not found: {template.file_path}")
            except Exception as e:
                logger.warning(f" Could not load templates from database: {e}")
                logger.info(f" Falling back to legacy hardcoded templates")
                # Fallback to legacy behavior if database query fails
                activity_log_path = os.path.join(docs_dir, 'Event Table Activity Log.pdf')
                checklist_path = os.path.join(docs_dir, 'Daily Task Checkoff Sheet.pdf')
                if os.path.exists(activity_log_path):
                    event_templates.append({'name': 'Activity Log', 'path': activity_log_path, 'order': 1})
                if os.path.exists(checklist_path):
                    event_templates.append({'name': 'Checklist', 'path': checklist_path, 'order': 2})
        else:
            # Model not available, use legacy hardcoded paths
            logger.info(f" PaperworkTemplate model not available, using legacy templates")
            activity_log_path = os.path.join(docs_dir, 'Event Table Activity Log.pdf')
            checklist_path = os.path.join(docs_dir, 'Daily Task Checkoff Sheet.pdf')
            if os.path.exists(activity_log_path):
                event_templates.append({'name': 'Activity Log', 'path': activity_log_path, 'order': 1})
            if os.path.exists(checklist_path):
                event_templates.append({'name': 'Checklist', 'path': checklist_path, 'order': 2})

        for schedule, event, employee in schedules:
            logger.info(f" Processing event {event.project_ref_num} for {employee.name}...")

            # Only process documents for Core events
            if event.event_type == 'Core':
                event_num = get_walmart_event_id(event)

                # Get EDR PDF if we have cached data
                if event_num and event_num in edr_data_cache:
                    logger.info(f"Generating EDR PDF for event {event_num} (shift_block={schedule.shift_block})...")

                    # Prepare schedule info for PDF generation (includes shift_block for times)
                    # Block was already assigned upfront by assign_blocks_for_date()
                    schedule_info = {
                        'scheduled_date': schedule.schedule_datetime,
                        'scheduled_time': schedule.schedule_datetime.time() if schedule.schedule_datetime else None,
                        'event_type': event.event_type,
                        'shift_block': schedule.shift_block,  # IMPORTANT: Pass shift_block for lunch times
                        'start_date': event.start_date if hasattr(event, 'start_date') else None,
                        'due_date': event.due_date if hasattr(event, 'due_date') else None
                    }
                    edr_pdf = self.get_event_edr_pdf_from_data(edr_data_cache[event_num], event_num, employee.name, schedule_info)
                    if edr_pdf:
                        all_pdfs.append(edr_pdf)
                        logger.info(f" EDR PDF added for event {event_num}")

                # Get SalesTool if URL available
                if hasattr(event, 'sales_tools_url') and event.sales_tools_url:
                    logger.info(f"Downloading SalesTool for Core event...")
                    salestool_pdf = self.get_salestool_pdf(event.sales_tools_url, event.project_ref_num)
                    if salestool_pdf:
                        all_pdfs.append(salestool_pdf)
                        logger.info(f" SalesTool added")

                # Add event-level templates for this Core event (in order)
                for template in event_templates:
                    all_pdfs.append(template['path'])
                    logger.info(f" Added event template: {template['name']}")

            else:
                logger.info(f" Skipping documents - event type is '{event.event_type}' (not applicable for {target_date.strftime('%A')})")

        # 5. Add daily-level templates ONCE at the end (after all events)
        if daily_templates:
            logger.info(" Adding daily-level documentation at the end...")
            for template in daily_templates:
                all_pdfs.append(template['path'])
                logger.info(f" Added daily template: {template['name']}")

        # Merge all PDFs
        output_filename = f'Paperwork_{target_date.strftime("%Y%m%d")}.pdf'
        output_path = os.path.join(tempfile.gettempdir(), output_filename)

        logger.info(f" Merging {len(all_pdfs)} PDFs into final document...")
        if self.merge_pdfs(all_pdfs, output_path):
            logger.info(f" Daily paperwork generated: {output_path}")
            return output_path
        else:
            logger.error(" Failed to merge PDFs")
            return None

    def cleanup(self):
        """Clean up temporary files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        self.temp_files = []
