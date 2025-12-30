"""
EDR PDF Generation Module
=========================

Provides PDF generation capabilities for EDR (Event Detail Report) data.
Includes automated printing functionality and enhanced formatting.

Classes:
- EDRPDFGenerator: Main PDF generation class
- AutomatedEDRPrinter: Automated batch PDF printing
- EnhancedEDRPrinter: Enhanced printing with additional features
"""

import sys
import datetime
import os
import tempfile
import subprocess
import platform
import logging
from typing import List, Optional, Dict, Any

# Import reportlab components
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfgen import canvas

# Import barcode components
try:
    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image as PILImage
    BARCODE_AVAILABLE = True
    logging.info("✓ Barcode libraries loaded successfully")
except ImportError as e:
    BARCODE_AVAILABLE = False
    logging.warning(f"⚠ Barcode libraries not available: {e}")
    logging.warning("Install with: pip install python-barcode Pillow")

# Import report generator and constants
from .report_generator import EDRReportGenerator

# Import event time settings service
try:
    from app.services.event_time_settings import EventTimeSettings
    EVENT_TIME_SETTINGS_AVAILABLE = True
except ImportError:
    EVENT_TIME_SETTINGS_AVAILABLE = False
    logging.warning("EventTimeSettings not available - shift times will not be displayed on PDFs")

# Import mapping data from constants module
try:
    from app.constants import DEMO_CLASS_CODES, EVENT_STATUS_CODES, DEPARTMENT_CODES
    logging.info("✓ Mapping constants loaded successfully")
except ImportError as e:
    logging.warning(f"Could not import mapping files: {e}")
    DEMO_CLASS_CODES = ([], )  # Tuple with empty list to match expected format
    EVENT_STATUS_CODES = []
    DEPARTMENT_CODES = []


class EDRPDFGenerator:
    """Generates PDF files from EDR report data with Product Connections formatting"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Product Connections color scheme
        self.pc_blue = colors.HexColor('#2E4C73')  # Dark blue
        self.pc_light_blue = colors.HexColor('#1B9BD8')  # Light blue

    def get_event_type_description(self, code: str) -> str:
        """Convert event type code to human readable description"""
        if not code or code == 'N/A':
            return 'N/A'

        # DEMO_CLASS_CODES is a tuple containing a list
        codes_list = DEMO_CLASS_CODES[0] if isinstance(DEMO_CLASS_CODES, tuple) else DEMO_CLASS_CODES

        for item in codes_list:
            if str(item.get('DEMO_CLASS_CODE')) == str(code):
                return item.get('DEMO_CLASS_DESC', f"Event Type {code}")

        return f"Event Type {code}"

    def get_event_status_description(self, code: str) -> str:
        """Convert event status code to human readable description"""
        if not code or code == 'N/A':
            return 'N/A'

        for item in EVENT_STATUS_CODES:
            if str(item.get('DEMO_STATUS_CODE')) == str(code):
                return item.get('DEMO_STATUS_DESC', f"Status {code}")

        return f"Status {code}"

    def get_department_description(self, code: str) -> str:
        """Convert department code to human readable description"""
        if not code or code == 'N/A':
            return 'N/A'

        for item in DEPARTMENT_CODES:
            if str(item.get('DEPT_NO')) == str(code):
                return item.get('DESCRIPTION', f"Department {code}")

        return 'N/A'

    def wrap_category_text(self, text: str, max_length: int = 18) -> str:
        """
        Wrap category text to fit within max_length per line.
        Breaks on word boundaries to avoid splitting words.
        Wraps if adding the next word would make the line exceed max_length.

        Args:
            text: Text to wrap
            max_length: Maximum characters per line (default 18)

        Returns:
            Text with newlines inserted at appropriate positions
        """
        if len(text) <= max_length:
            return text

        words = text.split()
        if not words:
            return text

        lines = []
        current_line = []
        current_length = 0

        for word in words:
            # Check if adding this word would exceed the limit
            word_length = len(word)
            space_length = 1 if current_line else 0  # Space before word (if not first word)

            # Wrap if adding this word would make line > max_length (more than 18 chars)
            # This allows lines to be exactly 18 characters, but not more
            if current_line and current_length + space_length + word_length > max_length:
                # Start new line
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length
            else:
                # Word fits on current line
                current_line.append(word)
                current_length += space_length + word_length

        # Add remaining words
        if current_line:
            lines.append(' '.join(current_line))

        return '\n'.join(lines)

    def format_date(self, date_str: str) -> str:
        """Format date from YYYY-MM-DD to MM-DD-YYYY"""
        if not date_str or date_str == 'N/A':
            return 'N/A'
        try:
            parts = date_str.split('-')
            if len(parts) == 3:
                return f"{parts[1]}-{parts[2]}-{parts[0]}"
        except:
            pass
        return date_str

    def get_shift_times_for_schedule(self, schedule_info: Optional[Dict]) -> Optional[Dict]:
        """
        Get the shift times (start, lunch, end) based on the scheduled time and event type.

        Args:
            schedule_info: Dict with 'scheduled_time' (time object), 'event_type' (str),
                          and optionally 'shift_block' (int 1-8)

        Returns:
            Dict with 'start', 'lunch_begin', 'lunch_end', 'end' times as formatted strings,
            or None if shift times cannot be determined
        """
        if not EVENT_TIME_SETTINGS_AVAILABLE or not schedule_info:
            return None

        scheduled_time = schedule_info.get('scheduled_time')
        event_type = schedule_info.get('event_type', '')
        shift_block = schedule_info.get('shift_block')  # New: assigned shift block (1-8)

        if not event_type:
            return None

        try:
            # Only Core events have full shift times with lunch
            if 'core' in event_type.lower():
                # Try new 8-block shift system first
                try:
                    from app.services.shift_block_config import ShiftBlockConfig
                    
                    # CASE 1: Event has a shift_block assigned (new system)
                    if shift_block:
                        block = ShiftBlockConfig.get_block(shift_block)
                        if block:
                            return {
                                'block': shift_block,
                                'start': f"{block['arrive'].hour:02d}:{block['arrive'].minute:02d}",
                                'on_floor': f"{block['on_floor'].hour:02d}:{block['on_floor'].minute:02d}",
                                'lunch_begin': f"{block['lunch_begin'].hour:02d}:{block['lunch_begin'].minute:02d}",
                                'lunch_end': f"{block['lunch_end'].hour:02d}:{block['lunch_end'].minute:02d}",
                                'off_floor': f"{block['off_floor'].hour:02d}:{block['off_floor'].minute:02d}",
                                'end': f"{block['depart'].hour:02d}:{block['depart'].minute:02d}"
                            }
                    
                    # CASE 2: No shift_block assigned yet - try to match by arrive time (scheduling time)
                    if scheduled_time:
                        # Try to match to an active shift block by arrive time
                        block = ShiftBlockConfig.find_block_by_arrive_time(scheduled_time)
                        if block:
                            return {
                                'block': block['block'],
                                'start': f"{block['arrive'].hour:02d}:{block['arrive'].minute:02d}",
                                'on_floor': f"{block['on_floor'].hour:02d}:{block['on_floor'].minute:02d}",
                                'lunch_begin': f"{block['lunch_begin'].hour:02d}:{block['lunch_begin'].minute:02d}",
                                'lunch_end': f"{block['lunch_end'].hour:02d}:{block['lunch_end'].minute:02d}",
                                'off_floor': f"{block['off_floor'].hour:02d}:{block['off_floor'].minute:02d}",
                                'end': f"{block['depart'].hour:02d}:{block['depart'].minute:02d}"
                            }
                        
                        # CASE 3: Legacy event - try to match scheduled time to legacy slots
                        legacy_slot = ShiftBlockConfig.find_legacy_slot_by_time(scheduled_time)
                        if legacy_slot:
                            return {
                                'legacy': True,
                                'slot': legacy_slot['slot'],
                                'start': f"{legacy_slot['start'].hour:02d}:{legacy_slot['start'].minute:02d}",
                                'lunch_begin': f"{legacy_slot['lunch_begin'].hour:02d}:{legacy_slot['lunch_begin'].minute:02d}",
                                'lunch_end': f"{legacy_slot['lunch_end'].hour:02d}:{legacy_slot['lunch_end'].minute:02d}",
                                'end': f"{legacy_slot['end'].hour:02d}:{legacy_slot['end'].minute:02d}"
                            }
                    
                except ImportError:
                    pass  # Fall through to old system
                
                # Fallback to old EventTimeSettings system if new system not available
                core_slots = EventTimeSettings.get_core_slots()

                # Find the matching slot based on scheduled time
                for slot in core_slots:
                    slot_start = slot['start']
                    # Match if scheduled time equals slot start time
                    if scheduled_time and scheduled_time.hour == slot_start.hour and scheduled_time.minute == slot_start.minute:
                        return {
                            'slot': slot['slot'],
                            'start': f"{slot['start'].hour:02d}:{slot['start'].minute:02d}",
                            'lunch_begin': f"{slot['lunch_begin'].hour:02d}:{slot['lunch_begin'].minute:02d}",
                            'lunch_end': f"{slot['lunch_end'].hour:02d}:{slot['lunch_end'].minute:02d}",
                            'end': f"{slot['end'].hour:02d}:{slot['end'].minute:02d}"
                        }

            # For non-Core events, just return start and end times (no lunch)
            elif 'digital setup' in event_type.lower() or 'digital refresh' in event_type.lower():
                slots = EventTimeSettings.get_digital_setup_slots()
                for slot in slots:
                    if scheduled_time and scheduled_time.hour == slot['start'].hour and scheduled_time.minute == slot['start'].minute:
                        return {
                            'slot': slot['slot'],
                            'start': f"{slot['start'].hour:02d}:{slot['start'].minute:02d}",
                            'end': f"{slot['end'].hour:02d}:{slot['end'].minute:02d}"
                        }

            elif 'digital teardown' in event_type.lower():
                slots = EventTimeSettings.get_digital_teardown_slots()
                for slot in slots:
                    if scheduled_time and scheduled_time.hour == slot['start'].hour and scheduled_time.minute == slot['start'].minute:
                        return {
                            'slot': slot['slot'],
                            'start': f"{slot['start'].hour:02d}:{slot['start'].minute:02d}",
                            'end': f"{slot['end'].hour:02d}:{slot['end'].minute:02d}"
                        }

            elif 'freeosk' in event_type.lower():
                times = EventTimeSettings.get_freeosk_times()
                return {
                    'start': f"{times['start'].hour:02d}:{times['start'].minute:02d}",
                    'end': f"{times['end'].hour:02d}:{times['end'].minute:02d}"
                }

            elif 'supervisor' in event_type.lower():
                times = EventTimeSettings.get_supervisor_times()
                return {
                    'start': f"{times['start'].hour:02d}:{times['start'].minute:02d}",
                    'end': f"{times['end'].hour:02d}:{times['end'].minute:02d}"
                }

        except Exception as e:
            self.logger.warning(f"Error getting shift times: {e}")

        return None

    def format_time_12h(self, time_str: str) -> str:
        """Convert 24h time string (HH:MM) to 12h format (H:MM AM/PM)"""
        try:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1])

            if hour == 0:
                return f"12:{minute:02d} AM"
            elif hour < 12:
                return f"{hour}:{minute:02d} AM"
            elif hour == 12:
                return f"12:{minute:02d} PM"
            else:
                return f"{hour - 12}:{minute:02d} PM"
        except:
            return time_str

    # REMOVED: draw_horizontal_line method - no longer used
    # The horizontal line and "Staple Price Signs Here" text have been removed per user request
    # def draw_horizontal_line(self, canvas, doc):
    #     """Draw horizontal line at 2/3 page height and 'Staple Price Signs Here' text"""
    #     page_height = letter[1]  # 792pt
    #     page_width = letter[0]   # 612pt
    #     two_thirds_height = page_height * (2/3)  # 528pt
    #
    #     canvas.saveState()
    #
    #     # Draw horizontal line at 2/3 page height
    #     canvas.setStrokeColor(colors.black)
    #     canvas.setLineWidth(2)
    #     canvas.line(72, two_thirds_height, page_width - 72, two_thirds_height)
    #
    #     # Calculate center position between 2/3 line and bottom of page
    #     # Center Y position is halfway between two_thirds_height (528pt) and page bottom (0pt)
    #     center_y = two_thirds_height / 2  # 264pt from bottom
    #
    #     # Draw "Staple Price Signs Here" text centered horizontally and vertically
    #     canvas.setFillColor(self.pc_blue)
    #     canvas.setFont('Helvetica-Bold', 16)
    #     text = "Staple Price Signs Here"
    #     text_width = canvas.stringWidth(text, 'Helvetica-Bold', 16)
    #     center_x = page_width / 2
    #     canvas.drawString(center_x - (text_width / 2), center_y, text)
    #
    #     canvas.restoreState()

    def generate_pdf(self, edr_data: Dict[str, Any], filename: str, employee_name: str = 'N/A', schedule_info: Optional[Dict] = None) -> bool:
        """
        Generate a PDF file from EDR data

        Args:
            edr_data: EDR report data dictionary
            filename: Output PDF filename
            employee_name: Employee name for signature section
            schedule_info: Optional dict with 'scheduled_date', 'start_date', 'due_date'
        """
        try:
            # Create PDF with custom page template for 2/3 line
            doc = SimpleDocTemplate(
                filename,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            story = []
            styles = getSampleStyleSheet()

            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=20,
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                textColor=self.pc_blue
            )

            header_style = ParagraphStyle(
                'CustomHeader',
                parent=styles['Heading2'],
                fontSize=14,
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )

            # Extract event data
            event_number = edr_data.get('demoId', 'N/A')
            event_name = edr_data.get('demoName', 'N/A')
            event_type_code = edr_data.get('demoClassCode', 'N/A')
            event_status_code = edr_data.get('demoStatusCode', 'N/A')
            event_date_raw = edr_data.get('demoDate', 'N/A')
            event_locked = edr_data.get('demoLockInd', 'N/A')

            # Format the data
            event_type = self.get_event_type_description(event_type_code)
            event_status = self.get_event_status_description(event_status_code)
            event_date = self.format_date(event_date_raw)
            locked_display = 'YES' if str(event_locked).upper() in ['Y', 'YES', 'TRUE', '1'] else 'NO'

            item_details = edr_data.get('itemDetails', [])

            # Handle case where itemDetails is None
            if item_details is None:
                item_details = []
                self.logger.warning(f"Event {event_number} has no item details (None)")

            # Calculate available width for tables (letter width - margins)
            page_width = letter[0] - 144  # 72 left + 72 right margins

            # Title
            story.append(Paragraph("EVENT DETAIL REPORT", title_style))

            # Scheduled date under the heading (if provided in schedule_info)
            if schedule_info and schedule_info.get('scheduled_date'):
                scheduled_date = schedule_info.get('scheduled_date')
                scheduled_date_str = scheduled_date.strftime('%m-%d-%Y')

                date_under_heading_style = ParagraphStyle(
                    'DateUnderHeading',
                    parent=styles['Normal'],
                    fontSize=12,
                    spaceAfter=12,
                    alignment=TA_CENTER,
                    fontName='Helvetica-Bold',
                    textColor=colors.black
                )
                story.append(Paragraph(f"Event Scheduled On {scheduled_date_str}", date_under_heading_style))
            else:
                story.append(Spacer(1, 12))

            # Row 1: Event Number and Event Name (2 columns, Event Name takes 75% width)
            row1_data = [
                ['Event Number', 'Event Name'],
                [str(event_number), str(event_name)]
            ]
            row1_table = Table(row1_data, colWidths=[page_width * 0.25, page_width * 0.75])
            row1_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.pc_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, 1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))

            # Row 2: Event Date, Event Type, Status, Locked (4 equal columns)
            row2_data = [
                ['Event Date', 'Event Type', 'Status', 'Locked'],
                [event_date, event_type, event_status, locked_display]
            ]
            col_width = page_width / 4
            row2_table = Table(row2_data, colWidths=[col_width, col_width, col_width, col_width])
            row2_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.pc_blue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, 1), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),  # Headers centered
                ('ALIGN', (0, 1), (-1, 1), 'LEFT'),    # Values left aligned
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
                ('FONTNAME', (3, 1), (3, 1), 'Helvetica-Bold'),  # Bold for Locked value
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))

            story.append(row1_table)
            story.append(Spacer(1, 3))
            story.append(row2_table)
            story.append(Spacer(1, 20))

            # Items table with department description
            if item_details:
                items_data = [['Item Number', 'Description', 'Category']]
                for item in item_details:
                    dept_no = str(item.get('deptNbr', ''))
                    category = self.get_department_description(dept_no)
                    # Wrap category text to prevent overflow (18 char max per line)
                    wrapped_category = self.wrap_category_text(category, max_length=18)
                    items_data.append([
                        str(item.get('itemNbr', '')),
                        str(item.get('itemDesc', '')),
                        wrapped_category
                    ])

                # Increased Category column width from 1.5 to 2.2 inches to fit longer category names
                # like "EXTREME VALUE GIFT CARDS" and "PLANNING SOLUTIONS"
                items_table = Table(items_data, colWidths=[1.2*inch, 3.1*inch, 2.2*inch])
                items_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), self.pc_light_blue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Item Number column - CENTER
                    ('ALIGN', (1, 0), (1, 0), 'CENTER'),   # Description header - CENTER
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Category column - CENTER
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Description data - LEFT (must be last)
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(items_table)
                story.append(Spacer(1, 20))

            # Shift Times Section (before signature)
            shift_times = self.get_shift_times_for_schedule(schedule_info)
            if shift_times:
                # Create style for shift times section
                shift_times_style = ParagraphStyle(
                    'ShiftTimes',
                    parent=styles['Normal'],
                    fontSize=10,
                    spaceAfter=3,
                    alignment=TA_CENTER,
                    fontName='Helvetica-Bold',
                    textColor=self.pc_blue
                )

                # Build shift times display with all 5 time fields for Core events
                shift_times_parts = []
                shift_times_parts.append(f"START: {self.format_time_12h(shift_times['start'])}")
                
                # Add ON FLOOR time if present (new 8-block system)
                if 'on_floor' in shift_times:
                    shift_times_parts.append(f"ON FLOOR: {self.format_time_12h(shift_times['on_floor'])}")

                # Only Core events have lunch times
                if 'lunch_begin' in shift_times and 'lunch_end' in shift_times:
                    shift_times_parts.append(f"LUNCH: {self.format_time_12h(shift_times['lunch_begin'])} - {self.format_time_12h(shift_times['lunch_end'])}")
                
                # Add OFF FLOOR time if present (new 8-block system)
                if 'off_floor' in shift_times:
                    shift_times_parts.append(f"OFF FLOOR: {self.format_time_12h(shift_times['off_floor'])}")

                shift_times_parts.append(f"LEAVE: {self.format_time_12h(shift_times['end'])}")

                shift_times_text = "   |   ".join(shift_times_parts)
                story.append(Paragraph(shift_times_text, shift_times_style))
                story.append(Spacer(1, 15))
            else:
                # For non-Core events, show at least the scheduled time
                scheduled_time = schedule_info.get('scheduled_time') if schedule_info else None
                if scheduled_time:
                    time_style = ParagraphStyle(
                        'ScheduledTime',
                        parent=styles['Normal'],
                        fontSize=10,
                        spaceAfter=3,
                        alignment=TA_CENTER,
                        fontName='Helvetica-Bold',
                        textColor=self.pc_blue
                    )
                    time_text = f"SCHEDULED TIME: {self.format_time_12h(scheduled_time)}"
                    story.append(Paragraph(time_text, time_style))
                    story.append(Spacer(1, 15))

            # Signature section
            story.append(Paragraph("<b>MUST BE SIGNED AND DATED</b>", header_style))
            story.append(Spacer(1, 20))

            # Create signature table with horizontal lines
            signature_data = [
                ['Scheduled Employee:', employee_name],
                ['Employee Signature:', ''],
                ['Date Performed:', ''],
                ['Supervisor Signature:', '']
            ]

            # Signature table with proper column alignment
            # Labels in left column (2.0"), signature lines in right column (4.0")
            signature_table = Table(signature_data, colWidths=[2.0*inch, 4.0*inch], rowHeights=[0.35*inch, 0.35*inch, 0.35*inch, 0.35*inch])
            signature_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Labels left aligned
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # Values left aligned
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),  # Bottom align for better line alignment
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),  # All labels bold
                ('LINEBELOW', (1, 1), (1, 1), 1, colors.black),  # Line under Employee Signature
                ('LINEBELOW', (1, 2), (1, 2), 1, colors.black),  # Line under Date Performed
                ('LINEBELOW', (1, 3), (1, 3), 1, colors.black),  # Line under Supervisor Signature
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (1, 1), (1, -1), 0),  # Remove left padding for signature lines
            ]))
            story.append(signature_table)

            # Create a custom page template to add "Printed" timestamp in bottom right
            def add_printed_timestamp(canvas, doc):
                """Add 'Printed: mm-dd-yyyy at HH:MM AM/PM' in bottom right corner"""
                canvas.saveState()

                # Get current timestamp
                now = datetime.datetime.now()
                timestamp_str = now.strftime('Printed: %m-%d-%Y at %I:%M %p')

                # Position in bottom right corner (72pt = 1 inch from edges)
                page_width = letter[0]  # 612pt
                x_position = page_width - 72 - 150  # 150pt width for text, 72pt right margin
                y_position = 50  # 50pt from bottom

                canvas.setFont('Helvetica', 9)
                canvas.setFillColor(colors.grey)
                canvas.drawRightString(page_width - 72, y_position, timestamp_str)

                canvas.restoreState()

            # Build PDF with custom page template
            doc.build(story, onFirstPage=add_printed_timestamp, onLaterPages=add_printed_timestamp)
            self.logger.info(f"PDF generated successfully: {filename}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to generate PDF: {str(e)}", exc_info=True)
            return False


class AutomatedEDRPrinter:
    """
    Fully automated EDR report printer with no user interaction.
    """

    def __init__(self):
        self.generator = EDRReportGenerator()

        # Default event IDs to process (edit these as needed)
        self.DEFAULT_EVENT_IDS = [
            "606034",  # Example event ID
            # Add more event IDs here as needed
        ]

    def authenticate_once(self) -> bool:
        """
        Perform authentication once for the entire session.

        Returns:
            True if authentication successful, False otherwise
        """
        print("🔐 Performing one-time authentication...")
        success = self.generator.authenticate()
        if success:
            print("✅ Authentication successful - token will be reused for all reports")
            return True
        else:
            print("❌ Authentication failed")
            return False


class EnhancedEDRPrinter(AutomatedEDRPrinter):
    """
    Enhanced EDR printer with additional features and improved output.
    """

    def __init__(self):
        super().__init__()
        self.pdf_generator = EDRPDFGenerator()

    def process_events_to_pdf(self, event_ids: List[str], output_dir: str = None) -> Dict[str, Any]:
        """
        Process multiple events and generate individual PDF files.

        Args:
            event_ids: List of event IDs to process
            output_dir: Directory to save PDFs (default: current directory)

        Returns:
            Dictionary with processing results
        """
        if output_dir is None:
            output_dir = os.getcwd()

        os.makedirs(output_dir, exist_ok=True)

        results = {
            'successful': [],
            'failed': [],
            'total': len(event_ids)
        }

        for event_id in event_ids:
            try:
                print(f"📄 Processing event {event_id}...")
                edr_data = self.generator.get_edr_report(event_id)

                if edr_data:
                    pdf_filename = os.path.join(output_dir, f"EDR_{event_id}.pdf")
                    if self.pdf_generator.generate_pdf(edr_data, pdf_filename):
                        results['successful'].append(event_id)
                        print(f"✅ Generated: {pdf_filename}")
                    else:
                        results['failed'].append(event_id)
                        print(f"❌ Failed to generate PDF for event {event_id}")
                else:
                    results['failed'].append(event_id)
                    print(f"❌ Failed to fetch data for event {event_id}")

            except Exception as e:
                results['failed'].append(event_id)
                print(f"❌ Error processing event {event_id}: {str(e)}")

        return results


class DailyItemsListPDFGenerator:
    """Generates a consolidated daily items list PDF from multiple EDR reports"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Product Connections color scheme
        self.pc_blue = colors.HexColor('#2E4C73')  # Dark blue
        self.pc_light_blue = colors.HexColor('#1B9BD8')  # Light blue

        # Build department code mappings
        self.department_codes = {}
        for item in DEPARTMENT_CODES:
            dept_no = str(item.get('DEPT_NO', ''))
            desc = item.get('DESCRIPTION', '').strip()
            if dept_no and desc:
                self.department_codes[dept_no] = desc

    def get_department_description(self, dept_no: str) -> str:
        """Convert department number to description"""
        if not dept_no or dept_no == 'N/A' or dept_no == '':
            return 'N/A'
        return self.department_codes.get(str(dept_no), 'N/A')

    def wrap_category_text(self, text: str, max_length: int = 18) -> str:
        """
        Wrap category text to fit within max_length per line.
        Breaks on word boundaries to avoid splitting words.
        Wraps if adding the next word would make the line exceed max_length.

        Args:
            text: Text to wrap
            max_length: Maximum characters per line (default 18)

        Returns:
            Text with newlines inserted at appropriate positions
        """
        if len(text) < max_length:
            return text

        words = text.split()
        if not words:
            return text

        lines = []
        current_line = []
        current_length = 0

        for word in words:
            # Check if adding this word would exceed the limit
            word_length = len(word)
            space_length = 1 if current_line else 0  # Space before word (if not first word)

            # Wrap if adding this word would make line > max_length (more than 18 chars)
            # This allows lines to be exactly 18 characters, but not more
            if current_line and current_length + space_length + word_length > max_length:
                # Start new line
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length
            else:
                # Word fits on current line
                current_line.append(word)
                current_length += space_length + word_length

        # Add remaining words
        if current_line:
            lines.append(' '.join(current_line))

        return '\n'.join(lines)

    def generate_barcode_image(self, item_number: str) -> Optional[str]:
        """
        Generate a barcode image for an item number

        Args:
            item_number: Item number to generate barcode for

        Returns:
            Path to generated barcode image or None if failed
        """
        if not BARCODE_AVAILABLE:
            self.logger.debug(f"Barcode libraries not available, skipping barcode for {item_number}")
            return None

        try:
            # Clean the item number (remove any non-digits)
            clean_number = ''.join(filter(str.isdigit, str(item_number)))

            if not clean_number:
                return None

            # Pad to 12 digits for UPC-A if needed
            if len(clean_number) < 12:
                clean_number = clean_number.zfill(12)

            # For UPC-A, we need exactly 11 digits (12th is check digit)
            if len(clean_number) == 12:
                try:
                    barcode_class = barcode.get_barcode_class('upca')
                    # UPC-A needs 11 digits, check digit is auto-calculated
                    clean_number = clean_number[:11]
                except:
                    barcode_class = barcode.get_barcode_class('code128')
                    clean_number = str(item_number)
            else:
                barcode_class = barcode.get_barcode_class('code128')
                clean_number = str(item_number)

            # Generate barcode image
            output_path = os.path.join(tempfile.gettempdir(), f'barcode_{item_number}_{datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")}.png')

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
                return final_path

            return None

        except Exception as e:
            self.logger.warning(f"Failed to generate barcode for {item_number}: {e}")
            return None

    def generate_daily_items_pdf(self, edr_data_list: List[Dict[str, Any]], filename: str, date_str: str = '') -> bool:
        """
        Generate a daily items list PDF from multiple EDR reports.

        Args:
            edr_data_list: List of EDR data dictionaries from multiple events
            filename: Output PDF filename
            date_str: Date string for display (e.g., "October 5, 2025")

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                filename,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            story = []
            styles = getSampleStyleSheet()

            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                textColor=self.pc_blue
            )

            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=12,
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Helvetica',
                textColor=colors.black
            )

            # Title
            story.append(Paragraph("DAILY ITEMS LIST", title_style))

            # Add date if provided
            if date_str:
                date_para = Paragraph(f"<b>{date_str}</b>", subtitle_style)
                story.append(date_para)

            # Subtitle text
            story.append(Paragraph("Use this list for getting the next day's product and printing price signs.", subtitle_style))
            story.append(Spacer(1, 20))

            # Collect all unique items from all EDR reports
            all_items = {}  # Use dict to avoid duplicates by item number

            for edr_data in edr_data_list:
                event_id = edr_data.get('demoId', 'N/A')
                event_name = edr_data.get('demoName', 'N/A')
                item_details = edr_data.get('itemDetails', [])

                # Handle case where itemDetails is None
                if item_details is None:
                    self.logger.warning(f"Event {event_id} has no item details (None)")
                    continue

                for item in item_details:
                    item_nbr = str(item.get('itemNbr', ''))
                    upc_nbr = str(item.get('upcNbr', ''))  # UPC number for barcode generation

                    if item_nbr and item_nbr != 'N/A':
                        # Store item with all its details
                        if item_nbr not in all_items:
                            dept_no = str(item.get('deptNbr', ''))
                            # Use UPC for barcode, fallback to item number if UPC is empty/None/N/A
                            final_upc = upc_nbr if upc_nbr and upc_nbr not in ['', 'N/A', 'None'] else item_nbr

                            # Debug logging for first few items
                            if len(all_items) < 3:
                                self.logger.info(f"Item {item_nbr}: upcNbr='{upc_nbr}', using '{final_upc}' for barcode")

                            all_items[item_nbr] = {
                                'itemNbr': item_nbr,
                                'upcNbr': final_upc,
                                'itemDesc': str(item.get('itemDesc', '')),
                                'deptNbr': dept_no,
                                'category': self.get_department_description(dept_no),
                                'events': [event_name]
                            }
                        else:
                            # Add event to list if item appears in multiple events
                            if event_name not in all_items[item_nbr]['events']:
                                all_items[item_nbr]['events'].append(event_name)

            if not all_items:
                self.logger.warning("No items found in EDR data")
                # Still create PDF with message
                story.append(Paragraph("No items found for this date.", styles['Normal']))
            else:
                # Sort items by item number
                sorted_items = sorted(all_items.values(), key=lambda x: x['itemNbr'])

                # Create items table with barcode column
                table_data = [['Item Number', 'Barcode', 'Description', 'Category']]

                # Log barcode availability once
                if not BARCODE_AVAILABLE:
                    self.logger.warning(f"⚠ Barcode generation disabled - libraries not available. Install with: pip install python-barcode Pillow")

                for item in sorted_items:
                    # Generate barcode image based on the UPC number (primary item number)
                    barcode_path = None
                    if BARCODE_AVAILABLE:
                        try:
                            # Use upcNbr for barcode generation (this is the primary/UPC item number)
                            barcode_path = self.generate_barcode_image(item['upcNbr'])
                        except Exception as e:
                            self.logger.error(f"Failed to generate barcode for item {item['itemNbr']} (UPC: {item['upcNbr']}): {e}")

                    # Wrap category text if needed (18 char max per line)
                    wrapped_category = self.wrap_category_text(item['category'], max_length=18)

                    if barcode_path:
                        # Create ReportLab Image object for the barcode
                        barcode_img = ReportLabImage(barcode_path, width=1.2*inch, height=0.5*inch)
                        # Keep item number visible in first column, barcode generated from item number in second column
                        table_data.append([
                            item['itemNbr'],
                            barcode_img,
                            item['itemDesc'],
                            wrapped_category
                        ])
                    else:
                        # If barcode generation fails, just show the item number
                        table_data.append([
                            item['itemNbr'],
                            'N/A',
                            item['itemDesc'],
                            wrapped_category
                        ])

                # Calculate available width
                page_width = letter[0] - 144  # 72 left + 72 right margins

                # Create table with appropriate column widths - adjusted for barcode column
                items_table = Table(table_data, colWidths=[1.0*inch, 1.5*inch, 2.3*inch, 1.7*inch])
                items_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), self.pc_blue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    # Column alignment
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Item Number column - CENTER
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),  # Barcode column - CENTER
                    ('ALIGN', (2, 0), (2, 0), 'CENTER'),   # Description header - CENTER
                    ('ALIGN', (2, 1), (2, -1), 'LEFT'),    # Description data - LEFT
                    ('ALIGN', (3, 0), (3, -1), 'CENTER'),  # Category column - CENTER
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))

                story.append(items_table)

                # Add summary at bottom
                story.append(Spacer(1, 20))
                summary_text = f"<b>Total Items: {len(sorted_items)}</b>"
                story.append(Paragraph(summary_text, styles['Normal']))

            # Build PDF
            doc.build(story)
            self.logger.info(f"Daily items list PDF generated successfully: {filename}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to generate daily items list PDF: {str(e)}", exc_info=True)
            return False
