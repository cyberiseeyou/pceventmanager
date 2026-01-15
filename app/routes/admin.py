"""
Admin routes blueprint
Handles admin operations, sync management, testing, and utility endpoints
"""
from flask import Blueprint, render_template, request, jsonify, current_app, abort, make_response
from app.routes.auth import require_authentication
from app.utils.db_compat import disable_foreign_keys, is_sqlite
from datetime import datetime, timedelta, date, time
from io import BytesIO
from sqlalchemy import func
import requests
import re
import logging
import os
import pickle
import tempfile

admin_bp = Blueprint('admin', __name__)


def _get_edr_credentials():
    """
    Get EDR credentials from SystemSetting with config fallback
    Returns: tuple (username, password, mfa_credential_id)
    """
    SystemSetting = current_app.config.get('SystemSetting')

    if SystemSetting:
        username = SystemSetting.get_setting('edr_username') or current_app.config.get('WALMART_EDR_USERNAME')
        password = SystemSetting.get_setting('edr_password') or current_app.config.get('WALMART_EDR_PASSWORD')
        mfa_credential_id = SystemSetting.get_setting('edr_mfa_credential_id') or current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID')
    else:
        # Fallback to config if SystemSetting not available
        username = current_app.config.get('WALMART_EDR_USERNAME')
        password = current_app.config.get('WALMART_EDR_PASSWORD')
        mfa_credential_id = current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID')

    return username, password, mfa_credential_id


@admin_bp.route('/api/refresh/database', methods=['POST'])
@require_authentication()
def refresh_database():
    """
    Completely refresh database with latest planning events from Crossmark API
    Clears all existing events and replaces with fresh data
    Fetches events from 1 month before to 1 month after current date

    Note: This uses the shared DatabaseRefreshService for consistency with
    the post-login refresh that shows progress on the loading page.
    """
    try:
        from app.services.database_refresh_service import DatabaseRefreshService

        current_app.logger.info("Starting complete database refresh from Crossmark API (manual trigger)")

        # Use the shared service without progress tracking for manual refresh
        service = DatabaseRefreshService()
        result = service.refresh()

        if result['success']:
            stats = result.get('stats', {})
            warning_message = result.get('warning')

            if warning_message:
                current_app.logger.warning(f"WARNING: {warning_message}")

            return jsonify({
                'success': True,
                'message': 'Database completely refreshed with fresh data',
                'stats': {
                    'total_fetched': stats.get('total_fetched', 0),
                    'cleared': stats.get('cleared', 0),
                    'created': stats.get('created', 0)
                },
                'warning': warning_message
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', 'Database refresh failed')
            }), 500

    except Exception as e:
        current_app.logger.error(f"Database refresh failed: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Database refresh failed: {str(e)}'
        }), 500

@admin_bp.route('/api/refresh/status')
@require_authentication()
def refresh_status():
    """Get status of database refresh progress"""
    try:
        Event = current_app.config['Event']

        # Get total events count and last sync info
        total_events = Event.query.count()
        synced_events = Event.query.filter_by(sync_status='synced').count()
        last_sync = Event.query.filter(Event.last_synced.isnot(None)).order_by(Event.last_synced.desc()).first()

        return jsonify({
            'success': True,
            'stats': {
                'total_events': total_events,
                'synced_events': synced_events,
                'last_sync': last_sync.last_synced.isoformat() if last_sync and last_sync.last_synced else None
            }
        })
    except Exception as e:
        current_app.logger.error(f"Failed to get refresh status: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get refresh status'
        }), 500

@admin_bp.route('/delete_event/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    """Delete an event from the database"""
    try:
        db = current_app.extensions['sqlalchemy']
        Event = current_app.config['Event']
        Schedule = current_app.config['Schedule']

        # Find the event
        event = db.session.get(Event, event_id)
        if not event:
            return jsonify({'success': False, 'message': 'Event not found'}), 404

        # Check if event is scheduled - if so, also delete the schedule
        schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).all()
        for schedule in schedules:
            db.session.delete(schedule)

        # Delete the event
        event_name = event.project_name
        db.session.delete(event)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Event "{event_name}" has been removed successfully'
        })

    except Exception as e:
        db = current_app.extensions['sqlalchemy']
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error removing event: {str(e)}'
        }), 500

@admin_bp.route('/api/sync/health')
def sync_health():
    """Check sync system health and API connectivity"""
    try:
        from app.integrations.external_api.session_api_service import session_api as external_api

        health_status = external_api.health_check()
        return jsonify({
            'sync_enabled': current_app.config.get('SYNC_ENABLED', False),
            'external_api': health_status,
            'database': {'status': 'healthy', 'message': 'Database accessible'},
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'sync_enabled': current_app.config.get('SYNC_ENABLED', False),
            'external_api': {'status': 'unhealthy', 'message': str(e)},
            'database': {'status': 'healthy', 'message': 'Database accessible'},
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@admin_bp.route('/api/sync/trigger', methods=['POST'])
def trigger_sync():
    """Manually trigger a complete synchronization"""
    from error_handlers import requires_sync_enabled, api_error_handler, sync_logger
    from sync_engine import sync_engine

    # Apply decorators programmatically
    requires_sync_enabled_check = requires_sync_enabled(lambda: None)
    if hasattr(requires_sync_enabled_check, '__wrapped__'):
        # Decorator returned an error response
        return requires_sync_enabled_check

    sync_logger.sync_started('manual_full_sync', 'Triggered by user')
    result = sync_engine.sync_all()

    if result['status'] == 'success':
        sync_logger.sync_completed('manual_full_sync', result)
    else:
        sync_logger.sync_warning('manual_full_sync', f"Sync completed with status: {result['status']}")

    status_code = 200 if result['status'] == 'success' else 207 if result['status'] == 'partial' else 500
    return jsonify(result), status_code

@admin_bp.route('/api/sync/status')
def sync_status():
    """Get synchronization status overview"""
    try:
        db = current_app.extensions['sqlalchemy']
        Employee = current_app.config['Employee']
        Event = current_app.config['Event']
        Schedule = current_app.config['Schedule']

        # Get sync statistics
        pending_employees = Employee.query.filter_by(sync_status='pending').count()
        failed_employees = Employee.query.filter_by(sync_status='failed').count()
        synced_employees = Employee.query.filter_by(sync_status='synced').count()

        pending_events = Event.query.filter_by(sync_status='pending').count()
        failed_events = Event.query.filter_by(sync_status='failed').count()
        synced_events = Event.query.filter_by(sync_status='synced').count()

        pending_schedules = Schedule.query.filter_by(sync_status='pending').count()
        failed_schedules = Schedule.query.filter_by(sync_status='failed').count()
        synced_schedules = Schedule.query.filter_by(sync_status='synced').count()

        # Get last sync timestamps
        last_employee_sync = db.session.query(Employee.last_synced).filter(
            Employee.last_synced.isnot(None)).order_by(Employee.last_synced.desc()).first()
        last_event_sync = db.session.query(Event.last_synced).filter(
            Event.last_synced.isnot(None)).order_by(Event.last_synced.desc()).first()
        last_schedule_sync = db.session.query(Schedule.last_synced).filter(
            Schedule.last_synced.isnot(None)).order_by(Schedule.last_synced.desc()).first()

        return jsonify({
            'sync_enabled': current_app.config.get('SYNC_ENABLED', False),
            'employees': {
                'pending': pending_employees,
                'failed': failed_employees,
                'synced': synced_employees,
                'last_sync': last_employee_sync[0].isoformat() if last_employee_sync and last_employee_sync[0] else None
            },
            'events': {
                'pending': pending_events,
                'failed': failed_events,
                'synced': synced_events,
                'last_sync': last_event_sync[0].isoformat() if last_event_sync and last_event_sync[0] else None
            },
            'schedules': {
                'pending': pending_schedules,
                'failed': failed_schedules,
                'synced': synced_schedules,
                'last_sync': last_schedule_sync[0].isoformat() if last_schedule_sync and last_schedule_sync[0] else None
            },
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting sync status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/webhook/schedule_update', methods=['POST'])
# Note: CSRF exemption applied in app.py - external webhook cannot include CSRF token
def webhook_schedule_update():
    """
    Receive webhook notifications from external API.

    Security: This route is CSRF-exempt because it's called by external systems.
    TODO: Implement HMAC signature validation to verify webhook authenticity.
    """
    try:
        db = current_app.extensions['sqlalchemy']
        Schedule = current_app.config['Schedule']
        from sync_engine import sync_engine

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        webhook_type = data.get('type', '')
        payload = data.get('data', {})

        logging.info(f"Received webhook: {webhook_type}")

        if webhook_type == 'schedule.created':
            # Handle new schedule from external system
            result = sync_engine._create_local_schedule_from_external(payload)
        elif webhook_type == 'schedule.updated':
            # Handle schedule update from external system
            schedule = Schedule.query.filter_by(external_id=payload.get('id')).first()
            if schedule:
                result = sync_engine._update_local_schedule(schedule, payload)
        elif webhook_type == 'schedule.deleted':
            # Handle schedule deletion from external system
            schedule = Schedule.query.filter_by(external_id=payload.get('id')).first()
            if schedule:
                db.session.delete(schedule)
                db.session.commit()
                result = True
        else:
            logging.warning(f"Unknown webhook type: {webhook_type}")
            return jsonify({'message': f'Unknown webhook type: {webhook_type}'}), 400

        return jsonify({
            'status': 'processed' if result else 'failed',
            'webhook_type': webhook_type,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logging.error(f"Webhook processing failed: {str(e)}")
        return jsonify({
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@admin_bp.route('/sync/admin')
def sync_admin():
    """Sync administration interface"""
    return render_template('sync_admin.html', config=current_app.config)

@admin_bp.route('/api/universal_search')
def universal_search():
    """Universal search endpoint for events, employees, and schedules"""
    db = current_app.extensions['sqlalchemy']
    Event = current_app.config['Event']
    Employee = current_app.config['Employee']
    Schedule = current_app.config['Schedule']

    query = request.args.get('q', '').strip()
    context = request.args.get('context', 'all')  # all, scheduling, tracking, reporting
    filters = request.args.getlist('filters')  # Additional filters

    if not query:
        return jsonify({
            'results': [],
            'total': 0,
            'query': query,
            'context': context
        })

    results = {
        'events': [],
        'employees': [],
        'schedules': [],
        'total': 0
    }

    # Search Events
    if context in ['all', 'scheduling', 'tracking']:
        # Search by event name, project ref number, store name, or location
        event_query = Event.query.filter(
            db.or_(
                Event.project_name.ilike(f'%{query}%'),
                Event.project_ref_num == query if query.isdigit() else False,
                Event.store_name.ilike(f'%{query}%') if Event.store_name else False,
                Event.location_mvid.ilike(f'%{query}%') if Event.location_mvid else False
            )
        )

        # Apply context-specific filters
        if context == 'scheduling':
            event_query = event_query.filter_by(is_scheduled=False)

        # Apply additional filters
        if 'event_type' in [f.split(':')[0] for f in filters]:
            event_type = next(f.split(':')[1] for f in filters if f.startswith('event_type:'))
            event_query = event_query.filter_by(event_type=event_type)

        if 'status' in [f.split(':')[0] for f in filters]:
            status = next(f.split(':')[1] for f in filters if f.startswith('status:'))
            if status == 'scheduled':
                event_query = event_query.filter_by(is_scheduled=True)
            elif status == 'unscheduled':
                event_query = event_query.filter_by(is_scheduled=False)

        events = event_query.order_by(Event.start_datetime.asc()).limit(20).all()

        for event in events:
            # Calculate priority (days until deadline)
            days_remaining = (event.due_datetime.date() - datetime.now().date()).days
            if days_remaining <= 1:
                priority = 'critical'
                priority_color = 'red'
            elif days_remaining <= 7:
                priority = 'urgent'
                priority_color = 'yellow'
            else:
                priority = 'normal'
                priority_color = 'green'

            results['events'].append({
                'id': event.id,
                'project_ref_num': event.project_ref_num,
                'project_name': event.project_name,
                'store_name': event.store_name,
                'location_mvid': event.location_mvid,
                'start_datetime': event.start_datetime.isoformat(),
                'due_datetime': event.due_datetime.isoformat(),
                'event_type': event.event_type,
                'is_scheduled': event.is_scheduled,
                'priority': priority,
                'priority_color': priority_color,
                'days_remaining': days_remaining
            })

    # Search Employees
    if context in ['all', 'scheduling']:
        employee_query = Employee.query.filter(
            db.and_(
                Employee.is_active == True,
                db.or_(
                    Employee.name.ilike(f'%{query}%'),
                    Employee.id.ilike(f'%{query}%'),
                    Employee.email.ilike(f'%{query}%') if Employee.email else False
                )
            )
        )

        employees = employee_query.limit(20).all()

        for emp in employees:
            results['employees'].append({
                'id': emp.id,
                'name': emp.name,
                'email': emp.email,
                'job_title': emp.job_title,
                'is_supervisor': emp.is_supervisor
            })

    # Search Schedules (when tracking specific assignments)
    if context in ['all', 'tracking']:
        try:
            # Try searching by project ref number or employee ID
            schedule_query = db.session.query(Schedule, Event, Employee).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).join(
                Employee, Schedule.employee_id == Employee.id
            ).filter(
                db.or_(
                    Event.project_name.ilike(f'%{query}%'),
                    Event.project_ref_num == query if query.isdigit() else False,
                    Employee.name.ilike(f'%{query}%'),
                    Employee.id.ilike(f'%{query}%')
                )
            )

            schedules = schedule_query.limit(20).all()

            for schedule, event, employee in schedules:
                results['schedules'].append({
                    'id': schedule.id,
                    'event_ref_num': event.project_ref_num,
                    'event_name': event.project_name,
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'schedule_datetime': schedule.schedule_datetime.isoformat(),
                    'event_type': event.event_type
                })
        except Exception as e:
            current_app.logger.warning(f"Error searching schedules: {e}")

    results['total'] = len(results['events']) + len(results['employees']) + len(results['schedules'])
    results['query'] = query
    results['context'] = context

    return jsonify(results)

@admin_bp.route('/api/test')
def api_tester():
    """API testing and request capture tool"""
    return render_template('api_tester.html')

@admin_bp.route('/api/test/login', methods=['POST'])
def test_login():
    """Test login endpoint for capturing session data"""
    try:
        data = request.get_json()
        login_url = data.get('login_url')
        username = data.get('username')
        password = data.get('password')

        if not all([login_url, username, password]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        # Create a test session
        test_session = requests.Session()

        # First get the login page
        login_page = test_session.get(login_url, timeout=30)

        # Prepare login data
        login_data = {
            'username': username,
            'password': password
        }

        # Attempt login
        login_response = test_session.post(login_url, data=login_data, timeout=30, allow_redirects=True)

        # Extract session information
        session_id = test_session.cookies.get('PHPSESSID')

        return jsonify({
            'success': True,
            'status_code': login_response.status_code,
            'session_id': session_id,
            'cookies': dict(test_session.cookies),
            'final_url': login_response.url,
            'headers': dict(login_response.headers),
            'response_preview': login_response.text[:500] if len(login_response.text) > 500 else login_response.text
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/test/request', methods=['POST'])
def test_request():
    """Test generic API requests with session"""
    try:
        data = request.get_json()
        method = data.get('method', 'GET')
        url = data.get('endpoint_url')
        headers = data.get('headers', {})
        request_data = data.get('data')
        session_id = data.get('session_id')

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'})

        # Create test session
        test_session = requests.Session()

        # Set session cookie if provided
        if session_id:
            test_session.cookies.set('PHPSESSID', session_id)

        # Set headers
        if headers:
            test_session.headers.update(headers)

        # Prepare request data
        request_kwargs = {'timeout': 30}
        if request_data:
            if headers.get('Content-Type') == 'application/json':
                request_kwargs['json'] = request_data
            else:
                request_kwargs['data'] = request_data

        # Make request
        response = test_session.request(method, url, **request_kwargs)

        return jsonify({
            'success': True,
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'cookies': dict(test_session.cookies),
            'response_preview': response.text[:1000] if len(response.text) > 1000 else response.text,
            'content_type': response.headers.get('Content-Type', 'unknown')
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# DEPRECATED: Use extract_event_number from app.utils.event_helpers instead
# Kept for backward compatibility
def extract_event_number(project_name):
    """
    Extract the first 6 digits from a Core event's project name

    DEPRECATED: Import from app.utils.event_helpers instead
    """
    from app.utils.event_helpers import extract_event_number as _extract_event_number
    return _extract_event_number(project_name)

def _extract_event_number_legacy(project_name):
    """Legacy implementation - DO NOT USE"""
    if not project_name:
        return None

    # Look for 6-digit numbers at the start of the project name
    match = re.match(r'^(\d{6})', project_name)
    if match:
        return match.group(1)

    # If no match at start, look for any 6-digit sequence
    match = re.search(r'\d{6}', project_name)
    if match:
        return match.group(0)

    return None


def _generate_daily_schedule_pdf(events, target_date, output_path, Schedule, Employee):
    """Generate daily schedule PDF section"""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas

    c = pdf_canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width/2, height - 50, f"Daily Schedule - {target_date.strftime('%B %d, %Y')}")

    # Table headers
    y = height - 100
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Time")
    c.drawString(150, y, "Employee")
    c.drawString(300, y, "Event")

    # Draw header line
    c.line(50, y-5, width-50, y-5)

    y -= 25
    c.setFont("Helvetica", 11)

    for event in events:
        schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).all()
        for schedule in schedules:
            employee = Employee.query.get(schedule.employee_id)
            if employee:
                time_str = schedule.schedule_datetime.strftime('%I:%M %p')
                c.drawString(50, y, time_str)
                c.drawString(150, y, employee.name)

                # Truncate long event names
                event_name = event.project_name[:40] + '...' if len(event.project_name) > 40 else event.project_name
                c.drawString(300, y, event_name)

                y -= 20

                # Start new page if needed
                if y < 100:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - 50

    c.save()


def _generate_item_numbers_layout_pdf(all_items, output_path):
    """Generate item numbers layout PDF from EDR data with instructional text"""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT

    doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    story = []
    styles = getSampleStyleSheet()

    # Title
    title = Paragraph("<b>Master Item Numbers List - All Core Events</b>", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 15))

    # Instructional Text Box
    instruction_style = ParagraphStyle(
        'InstructionBox',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        leftIndent=10,
        rightIndent=10,
        spaceBefore=10,
        spaceAfter=10,
        borderColor=colors.HexColor('#2E4C73'),
        borderWidth=2,
        borderPadding=10,
        backColor=colors.HexColor('#F0F4F8')
    )

    instruction_text = """
    <b>INSTRUCTIONS:</b><br/>
    <br/>
    <b>Use this list to:</b><br/>
    • Collect all needed items from the warehouse/stockroom before events begin<br/>
    • Print item signs/labels for each product using the GTIN or Item Number<br/>
    • Verify all items are available and in stock<br/>
    • Cross-reference with EDR reports for each individual event<br/>
    <br/>
    <b>Note:</b> Each event's specific items are listed with their event number. Gather all items for the day's events to ensure smooth execution.
    """

    instruction_para = Paragraph(instruction_text, instruction_style)
    story.append(instruction_para)
    story.append(Spacer(1, 20))

    # Create table data
    table_data = [['Event #', 'Item Number', 'GTIN', 'Description', 'Vendor']]

    for event_num, items in sorted(all_items.items()):
        for item in items:
            table_data.append([
                str(event_num),
                str(item.get('itemNbr', '')),
                str(item.get('gtin', '')),
                str(item.get('itemDesc', ''))[:35],  # Truncate description
                str(item.get('vendorNbr', ''))
            ])

    # Create table
    table = Table(table_data, colWidths=[0.8*inch, 1*inch, 1.3*inch, 2.4*inch, 0.8*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E4C73')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
    ]))

    story.append(table)
    doc.build(story)


def _generate_edr_pdf_from_html(edr_gen, edr_data, assigned_employee, output_path):
    """Generate EDR PDF from HTML using xhtml2pdf"""
    from xhtml2pdf import pisa

    # Generate HTML using EDRReportGenerator
    html_content = edr_gen.generate_html_report(edr_data)

    # Convert HTML to PDF
    with open(output_path, 'wb') as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)

    if pisa_status.err:
        raise Exception(f"Failed to generate EDR PDF: {pisa_status.err}")


def _download_pdf_from_url(url, output_path):
    """Download PDF from URL"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Check if response is actually a PDF
        content_type = response.headers.get('Content-Type', '')
        if 'pdf' not in content_type.lower():
            current_app.logger.warning(f"URL {url} did not return PDF (Content-Type: {content_type})")
            return False

        with open(output_path, 'wb') as f:
            f.write(response.content)

        return True
    except Exception as e:
        current_app.logger.error(f"Failed to download PDF from {url}: {str(e)}")
        return False


def get_sales_tool_doc(salestool_url, output_path):
    """
    Download sales tool document from URL

    Args:
        salestool_url: URL to the sales tool PDF
        output_path: Where to save the downloaded PDF

    Returns:
        True if successful, False otherwise
    """
    return _download_pdf_from_url(salestool_url, output_path)

def generate_edr_documents(event_numbers, credentials=None):
    """Generate EDR documents using the product-connections-implementation"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    # Import EDR reporting functionality
    try:
        from app.integrations.edr import EDRReportGenerator
        edr_available = True
    except ImportError:
        edr_available = False
        EDRReportGenerator = None

    if not event_numbers:
        return None

    if not edr_available:
        current_app.logger.error("EDR report generator is not available - product-connections-implementation not installed")
        return None

    try:
        event_numbers_str = ', '.join(event_numbers)
        current_app.logger.info(f"Generating EDR reports for event numbers: {event_numbers_str}")

        # Initialize the EDR report generator
        generator = EDRReportGenerator()

        # Set credentials if provided, otherwise it will prompt interactively
        if credentials and credentials.get('username') and credentials.get('password'):
            generator.set_credentials(credentials['username'], credentials['password'])

        # Authenticate with Retail Link
        if not generator.authenticate():
            current_app.logger.error("Failed to authenticate with Retail Link for EDR generation")
            return None

        pdf_files = []

        # Generate EDR report for each event number
        for event_id in event_numbers:
            try:
                current_app.logger.info(f"Generating EDR report for event ID: {event_id}")

                # Get EDR data for this event
                edr_data = generator.get_edr_report(event_id)

                if not edr_data:
                    current_app.logger.warning(f"No EDR data found for event ID: {event_id}")
                    continue

                # Generate HTML report
                html_content = generator.generate_html_report(edr_data)

                if html_content:
                    # Convert HTML to PDF (you might want to use a library like WeasyPrint for this)
                    # For now, we'll create a simple PDF with the event ID as placeholder
                    pdf_buffer = BytesIO()
                    pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=letter)
                    pdf_canvas.setFont("Helvetica-Bold", 16)
                    pdf_canvas.drawString(50, 750, f"EDR Report - Event {event_id}")
                    pdf_canvas.setFont("Helvetica", 12)
                    pdf_canvas.drawString(50, 720, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    # Add some basic EDR data if available
                    y_position = 680
                    if isinstance(edr_data, dict):
                        for key, value in list(edr_data.items())[:10]:  # Show first 10 items
                            pdf_canvas.drawString(50, y_position, f"{key}: {str(value)[:60]}")
                            y_position -= 20

                    pdf_canvas.save()
                    pdf_buffer.seek(0)

                    pdf_files.append({
                        'name': f"EDR_Event_{event_id}.pdf",
                        'content': pdf_buffer.getvalue()
                    })

                    current_app.logger.info(f"Successfully generated EDR report for event ID: {event_id}")
                else:
                    current_app.logger.warning(f"Failed to generate HTML report for event ID: {event_id}")

            except Exception as e:
                current_app.logger.error(f"Error generating EDR report for event ID {event_id}: {str(e)}")
                continue

        if pdf_files:
            current_app.logger.info(f"Successfully generated {len(pdf_files)} EDR PDF(s)")
            return pdf_files
        else:
            current_app.logger.error("No EDR PDF files were generated")
            return None

    except Exception as e:
        current_app.logger.error(f"Error in EDR document generation: {str(e)}")
        return None

@admin_bp.route('/api/edr/request_code', methods=['POST'])
@require_authentication()
def edr_request_code():
    """
    Request MFA code to be sent to phone
    This must be called BEFORE showing the MFA popup
    """
    try:
        from app.integrations.edr import EDRReportGenerator
        from flask import session as flask_session

        # Clear any existing EDR session data
        if 'edr_temp_cookies' in flask_session:
            del flask_session['edr_temp_cookies']
        if 'edr_session_cookies' in flask_session:
            del flask_session['edr_session_cookies']
        if 'edr_auth_token' in flask_session:
            del flask_session['edr_auth_token']

        # Create EDR generator with credentials from settings (with config fallback)
        username, password, mfa_credential_id = _get_edr_credentials()
        edr_gen = EDRReportGenerator(
            username=username,
            password=password,
            mfa_credential_id=mfa_credential_id
        )

        # Request MFA code (steps 1 & 2: submit password, request code)
        if edr_gen.request_mfa_code():
            # Store ALL session cookies in a server-side cache file (avoid 4KB session limit)
            # Use user's session ID as the cache key
            import pickle
            import tempfile

            session_id = flask_session.get('user_id') or 'default'
            cache_file = os.path.join(tempfile.gettempdir(), f'edr_session_{session_id}.pkl')

            # Serialize all cookies
            session_data = {}
            for cookie in edr_gen.session.cookies:
                session_data[cookie.name] = cookie.value

            # Save to file
            with open(cache_file, 'wb') as f:
                pickle.dump(session_data, f)

            # Store only a small marker in Flask session
            flask_session['edr_mfa_requested'] = True
            flask_session['edr_mfa_timestamp'] = datetime.utcnow().isoformat()
            flask_session['edr_cache_file'] = cache_file

            current_app.logger.info(f"MFA code requested successfully. Cached {len(session_data)} cookies to {cache_file}")
            return jsonify({'success': True, 'message': 'MFA code sent to your phone'})
        else:
            current_app.logger.error("Failed to request MFA code - check credentials")
            return jsonify({'success': False, 'message': 'Failed to request MFA code. Please check your credentials in Settings.'}), 500

    except Exception as e:
        error_msg = str(e).encode('ascii', errors='ignore').decode('ascii')
        current_app.logger.error(f"MFA code request error: {error_msg}")
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/api/edr/authenticate', methods=['POST'])
@require_authentication()
def edr_authenticate():
    """
    Authenticate with Walmart Retail Link using MFA code
    Does a complete authentication flow from scratch with the MFA code
    """
    try:
        from app.integrations.edr import EDRReportGenerator
        from flask import session as flask_session

        data = request.get_json()
        mfa_code = data.get('mfa_code')

        if not mfa_code:
            return jsonify({'success': False, 'message': 'MFA code is required'}), 400

        # Check that MFA was requested
        if not flask_session.get('edr_mfa_requested'):
            return jsonify({'success': False, 'message': 'Please request MFA code first'}), 400

        # Load session cookies from cache file
        cache_file = flask_session.get('edr_cache_file')
        if not cache_file or not os.path.exists(cache_file):
            return jsonify({'success': False, 'message': 'Session expired. Please request MFA code again.'}), 400

        try:
            with open(cache_file, 'rb') as f:
                session_cookies = pickle.load(f)
            current_app.logger.info(f"Loaded {len(session_cookies)} cookies from cache file")
        except Exception as e:
            current_app.logger.error(f"Failed to load session cache: {str(e)}")
            return jsonify({'success': False, 'message': 'Session expired. Please request MFA code again.'}), 400

        # Create EDR generator with credentials
        username, password, mfa_credential_id = _get_edr_credentials()
        edr_gen = EDRReportGenerator(
            username=username,
            password=password,
            mfa_credential_id=mfa_credential_id
        )

        # Restore the EXACT session state from request_code
        # Do NOT clear or reset - just restore the saved cookies
        edr_gen.session.cookies.clear()
        for name, value in session_cookies.items():
            edr_gen.session.cookies.set(name, value)

        current_app.logger.info(f"Restored {len(session_cookies)} cookies from request_code session")

        # Step 3: Validate MFA code (steps 1 & 2 were already done in request_code)
        if not edr_gen.step3_validate_mfa_code(mfa_code):
            current_app.logger.error("MFA code validation failed")
            return jsonify({'success': False, 'message': 'Invalid MFA code. Please try again.'}), 401

        current_app.logger.info("MFA code validated successfully")

        # Steps 4-6: Complete authentication (following exact pattern from edr_report_generator.py)
        current_app.logger.info("Step 4: Registering page access...")
        edr_gen.step4_register_page_access()

        current_app.logger.info("Step 5: Navigating to Event Management...")
        edr_gen.step5_navigate_to_event_management()

        current_app.logger.info("Step 6: Authenticating with Event Management API...")

        # Use the edr_printer's step6 method
        if not edr_gen.step6_authenticate_event_management():
            current_app.logger.error("Step 6 failed - could not extract auth token")

            # Log cookies for debugging
            cookie_names = [c.name for c in edr_gen.session.cookies]
            current_app.logger.error(f"Available cookies: {cookie_names}")

            return jsonify({'success': False, 'message': 'Failed to extract auth token from Event Management API. Session may have expired.'}), 500

        current_app.logger.info(f"Authentication complete! Auth token: {edr_gen.auth_token[:50]}...")

        # Store auth token in session for reuse
        flask_session['edr_auth_token'] = edr_gen.auth_token

        # Store only essential cookies (avoid session size limit)
        essential_cookies = {}
        for cookie in edr_gen.session.cookies:
            # Only store auth-related cookies, skip tracking cookies
            if cookie.name in ['_auth', '_refreshAuth', 'RLSESSION', 'RETAILLINKSESSION',
                              'auth-token', 'fcnRealm', 'TS01b1e5a6', 'TS0111a950']:
                essential_cookies[cookie.name] = cookie.value

        flask_session['edr_session_cookies'] = essential_cookies

        # Clean up cache file
        try:
            if cache_file and os.path.exists(cache_file):
                os.remove(cache_file)
                current_app.logger.info(f"Cleaned up cache file: {cache_file}")
        except Exception as e:
            current_app.logger.warning(f"Failed to clean up cache file: {str(e)}")

        # Clear MFA request flag and cache reference
        if 'edr_mfa_requested' in flask_session:
            del flask_session['edr_mfa_requested']
        if 'edr_mfa_timestamp' in flask_session:
            del flask_session['edr_mfa_timestamp']
        if 'edr_cache_file' in flask_session:
            del flask_session['edr_cache_file']

        current_app.logger.info(f"EDR authentication successful. Stored {len(essential_cookies)} essential cookies")
        return jsonify({'success': True, 'message': 'EDR authentication successful'})

    except Exception as e:
        current_app.logger.error(f"EDR authentication error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/edr/sync-cache', methods=['POST'])
@require_authentication()
def edr_sync_cache():
    """
    Sync EDR cache using browse_events() API
    This fetches bulk data for ±30 days and caches it locally
    Requires prior authentication via /api/edr/authenticate
    """
    try:
        from flask import session as flask_session
        from app.integrations.edr import EDRReportGenerator

        # Check if authenticated
        if not flask_session.get('edr_auth_token'):
            return jsonify({
                'success': False,
                'message': 'Not authenticated. Please authenticate first.'
            }), 401

        # Get EDR settings from database
        username_setting = SystemSetting.query.filter_by(setting_key='retaillink_username').first()
        password_setting = SystemSetting.query.filter_by(setting_key='retaillink_password').first()
        mfa_setting = SystemSetting.query.filter_by(setting_key='retaillink_mfa_credential_id').first()

        if not all([username_setting, password_setting, mfa_setting]):
            return jsonify({
                'success': False,
                'message': 'EDR credentials not configured. Please configure in Settings.'
            }), 400

        # Create EDR generator with caching enabled
        edr_gen = EDRReportGenerator(
            username=username_setting.setting_value,
            password=password_setting.setting_value,
            mfa_credential_id=mfa_setting.setting_value,
            enable_caching=True
        )

        # Restore auth token from session
        edr_gen.auth_token = flask_session.get('edr_auth_token')

        # Restore session cookies
        session_cookies = flask_session.get('edr_session_cookies', {})
        edr_gen.session.cookies.clear()
        for name, value in session_cookies.items():
            edr_gen.session.cookies.set(name, value)

        current_app.logger.info("Starting EDR cache sync using browse_events()...")

        # Call browse_events() to sync cache (±30 days by default)
        events = edr_gen.browse_events()

        if not events:
            return jsonify({
                'success': False,
                'message': 'No events returned from browse_events(). Authentication may have expired.'
            }), 500

        # Get cache stats
        stats = edr_gen.get_cache_stats()

        current_app.logger.info(f"EDR cache sync complete: {len(events)} events cached")

        return jsonify({
            'success': True,
            'message': f'Successfully cached {len(events)} event items',
            'events_cached': len(events),
            'unique_events': stats.get('unique_events', 0),
            'date_range': f"{stats.get('earliest_event_date', 'N/A')} to {stats.get('latest_event_date', 'N/A')}"
        })

    except Exception as e:
        current_app.logger.error(f"EDR cache sync error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/edr/cache-status', methods=['GET'])
@require_authentication()
def edr_cache_status():
    """
    Get current EDR cache status
    Returns cache age, event count, date range, etc.
    """
    try:
        from app.integrations.edr import EDRReportGenerator

        # Create EDR generator to check cache
        edr_gen = EDRReportGenerator(enable_caching=True)

        # Get cache stats
        stats = edr_gen.get_cache_stats()

        # Determine if sync is recommended
        cache_age_hours = stats.get('cache_age_hours')
        is_fresh = cache_age_hours is not None and cache_age_hours < 24
        sync_recommended = not is_fresh or stats.get('unique_events', 0) == 0

        # Create user-friendly message
        if cache_age_hours is None:
            message = "Cache is empty. Sync required."
        elif cache_age_hours < 12:
            message = f"Cache is fresh ({cache_age_hours:.1f} hours old)"
        elif cache_age_hours < 24:
            message = f"Cache is acceptable ({cache_age_hours:.1f} hours old)"
        elif cache_age_hours < 48:
            message = f"Cache is stale ({cache_age_hours:.1f} hours old). Sync recommended."
        else:
            days = cache_age_hours / 24
            message = f"Cache is very stale ({days:.1f} days old). Sync required."

        return jsonify({
            'success': True,
            'is_fresh': is_fresh,
            'sync_recommended': sync_recommended,
            'message': message,
            'cache_age_hours': cache_age_hours,
            'unique_events': stats.get('unique_events', 0),
            'total_event_items': stats.get('total_event_items', 0),
            'earliest_event_date': stats.get('earliest_event_date'),
            'latest_event_date': stats.get('latest_event_date'),
            'last_fetch_time': stats.get('last_fetch_time')
        })

    except Exception as e:
        current_app.logger.error(f"EDR cache status error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/print_paperwork/<paperwork_type>')
def print_paperwork(paperwork_type):
    """
    Print paperwork for Core events (today or tomorrow)
    Structure: Sales Tool PDF -> EDR -> Activity Log -> Checklist (for each event)
    paperwork_type: 'today' or 'tomorrow'
    """
    # Calculate target date from paperwork_type
    if paperwork_type == 'today':
        target_date = date.today()
    elif paperwork_type == 'tomorrow':
        target_date = date.today() + timedelta(days=1)
    else:
        return jsonify({'error': 'Invalid paperwork type. Use "today" or "tomorrow"'}), 400

    # Call refactored internal function with calculated date
    return print_paperwork_internal(paperwork_type, target_date)
def print_paperwork_internal(paperwork_type, target_date_override=None):
    """
    Internal function to generate comprehensive paperwork PDF with:
    - Daily schedule
    - Item numbers layout from EDR data
    - EDR reports for all Core events
    - Sales Tools URL documents
    - Daily Task Checkoff Sheet
    - Event Table Activity Log
    """
    try:
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from app.integrations.edr import EDRReportGenerator
        from flask import session as flask_session

        db = current_app.extensions['sqlalchemy']
        Event = current_app.config['Event']
        Employee = current_app.config['Employee']
        Schedule = current_app.config['Schedule']

        # Determine target date
        if target_date_override:
            target_date = target_date_override
        elif paperwork_type == 'today':
            target_date = date.today()
        elif paperwork_type == 'tomorrow':
            target_date = date.today() + timedelta(days=1)
        else:
            target_date = date.today()

        # Query Core events for target date
        events = Event.query.filter(
            func.date(Event.start_datetime) == target_date,
            Event.event_type == 'Core'
        ).order_by(Event.start_datetime).all()

        if not events:
            return jsonify({'message': f'No Core events found for {target_date}'}), 404

        # Create temporary directory for PDF components
        temp_dir = tempfile.mkdtemp()
        pdf_components = []

        try:
            # ===== 1. Generate Daily Schedule PDF =====
            current_app.logger.info("Generating daily schedule section...")
            schedule_pdf_path = os.path.join(temp_dir, "01_daily_schedule.pdf")
            _generate_daily_schedule_pdf(events, target_date, schedule_pdf_path, Schedule, Employee)
            pdf_components.append(schedule_pdf_path)

            # ===== 2. Prepare EDR data and item numbers =====
            current_app.logger.info("Fetching EDR data for all events...")

            edr_gen = None
            events_with_edr = []  # List of (event, event_num, edr_data)
            all_items = {}  # event_number -> list of items

            # Check if we have EDR authentication
            if flask_session.get('edr_auth_token'):
                # Get EDR credentials
                username, password, mfa_credential_id = _get_edr_credentials()
                edr_gen = EDRReportGenerator(username, password, mfa_credential_id)

                # Restore session from flask session
                if flask_session.get('edr_session_cookies'):
                    current_app.logger.info(f"Restoring {len(flask_session['edr_session_cookies'])} cookies to EDR session")
                    for name, value in flask_session['edr_session_cookies'].items():
                        edr_gen.session.cookies.set(name, value)
                        current_app.logger.debug(f"  Restored cookie: {name}")

                edr_gen.auth_token = flask_session['edr_auth_token']
                current_app.logger.info(f"Restored auth token: {edr_gen.auth_token[:50]}...")

                # Fetch EDR data for all events
                for event in events:
                    event_num = extract_event_number(event.project_name)
                    if event_num:
                        try:
                            current_app.logger.info(f"Fetching EDR data for event {event_num}")
                            edr_data = edr_gen.get_edr_report(event_num)
                            if edr_data:
                                events_with_edr.append((event, event_num, edr_data))
                                # Extract items
                                items = edr_data.get('itemDetails', [])
                                if items:
                                    all_items[event_num] = items
                        except Exception as e:
                            current_app.logger.error(f"Failed to fetch EDR for event {event_num}: {str(e)}")
            else:
                current_app.logger.warning("No EDR authentication - skipping EDR reports and item layout")

            # ===== 3. Generate Item Numbers Layout (Master List) =====
            if all_items:
                current_app.logger.info("Generating master item numbers list...")
                item_layout_pdf_path = os.path.join(temp_dir, "02_item_numbers_master.pdf")
                _generate_item_numbers_layout_pdf(all_items, item_layout_pdf_path)
                pdf_components.append(item_layout_pdf_path)

            # ===== 4. Generate Event Packets (EDR + Sales Tool + Activity Log + Checklist per event) =====
            current_app.logger.info("Generating event packets...")

            # Get static PDF paths
            checkoff_path = os.path.join(current_app.root_path, 'docs', 'Daily Task Checkoff Sheet.pdf')
            activity_log_path = os.path.join(current_app.root_path, 'docs', 'Event Table Activity Log.pdf')

            for event, event_num, edr_data in events_with_edr:
                current_app.logger.info(f"Creating packet for event {event_num}...")

                # Find assigned employee for this event
                assigned_employee = "N/A"
                schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).all()
                if schedules:
                    emp = Employee.query.get(schedules[0].employee_id)
                    if emp:
                        assigned_employee = emp.name

                # 4a. EDR Report
                edr_pdf_path = os.path.join(temp_dir, f"event_{event_num}_1_edr.pdf")
                _generate_edr_pdf_from_html(edr_gen, edr_data, assigned_employee, edr_pdf_path)
                pdf_components.append(edr_pdf_path)

                # 4b. Sales Tool Document
                if event.sales_tools_url:
                    try:
                        sales_tool_pdf_path = os.path.join(temp_dir, f"event_{event_num}_2_salestool.pdf")
                        if _download_pdf_from_url(event.sales_tools_url, sales_tool_pdf_path):
                            pdf_components.append(sales_tool_pdf_path)
                        else:
                            current_app.logger.warning(f"Failed to download Sales Tool for event {event_num}")
                    except Exception as e:
                        current_app.logger.error(f"Error downloading Sales Tool for event {event_num}: {str(e)}")

                # 4c. Event Table Activity Log
                if os.path.exists(activity_log_path):
                    pdf_components.append(activity_log_path)

                # 4d. Daily Task Checkoff Sheet
                if os.path.exists(checkoff_path):
                    pdf_components.append(checkoff_path)

            # ===== 5. Merge all PDFs =====
            current_app.logger.info(f"Merging {len(pdf_components)} PDF components...")
            final_pdf_buffer = BytesIO()
            pdf_writer = PdfWriter()

            for pdf_path in pdf_components:
                try:
                    with open(pdf_path, 'rb') as pdf_file:
                        pdf_reader = PdfReader(pdf_file)
                        for page in pdf_reader.pages:
                            pdf_writer.add_page(page)
                except Exception as e:
                    current_app.logger.error(f"Failed to add PDF component {pdf_path}: {str(e)}")

            pdf_writer.write(final_pdf_buffer)
            final_pdf_buffer.seek(0)

            # Clean up temp directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

            # Return the merged PDF
            response = make_response(final_pdf_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="Sales_Tools_{paperwork_type}_{target_date.strftime("%Y-%m-%d")}.pdf"'

            return response

        except Exception as e:
            # Clean up on error
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    except Exception as e:
        current_app.logger.error(f"Error generating paperwork: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to generate paperwork: {str(e)}'}), 500


@admin_bp.route('/api/print_paperwork_by_date/<date_str>')
@require_authentication()
def print_paperwork_by_date(date_str):
    """
    Print paperwork for Core events on a specific date
    date_str: Date in YYYY-MM-DD format
    """
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    return print_paperwork_internal('custom', target_date)


@admin_bp.route('/api/print_salestools_by_date/<date_str>')
@require_authentication()
def print_salestools_by_date(date_str):
    """
    Download and merge sales tool PDFs for all Core events on a specific date
    date_str: Date in YYYY-MM-DD format
    """
    try:
        from PyPDF2 import PdfWriter, PdfReader

        db = current_app.extensions['sqlalchemy']
        Event = current_app.config['Event']
        Schedule = current_app.config['Schedule']

        # Parse date
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Get all CORE events scheduled for this date
        core_events = db.session.query(Event).join(
            Schedule, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) == target_date,
            Event.event_type == 'Core',
            Event.sales_tools_url.isnot(None),
            Event.sales_tools_url != ''
        ).distinct().all()

        if not core_events:
            return jsonify({'error': f'No Core events with SalesTools found for {target_date}'}), 404

        current_app.logger.info(f"Found {len(core_events)} Core events with SalesTools URLs for {target_date}")

        # Create temp directory for downloaded PDFs
        temp_dir = tempfile.mkdtemp()
        downloaded_pdfs = []

        try:
            # Download each sales tool PDF
            for i, event in enumerate(core_events):
                salestool_url = event.sales_tools_url
                current_app.logger.info(f"Downloading SalesTool {i+1}/{len(core_events)}: {salestool_url}")

                output_path = os.path.join(temp_dir, f'salestool_{i}_{event.project_ref_num}.pdf')

                if get_sales_tool_doc(salestool_url, output_path):
                    downloaded_pdfs.append(output_path)
                    current_app.logger.info(f"✓ Downloaded SalesTool for event {event.project_ref_num}")
                else:
                    current_app.logger.warning(f"✗ Failed to download SalesTool for event {event.project_ref_num}")

            if not downloaded_pdfs:
                return jsonify({'error': 'Failed to download any SalesTools PDFs'}), 500

            current_app.logger.info(f"Successfully downloaded {len(downloaded_pdfs)} SalesTools PDFs, merging...")

            # Merge all PDFs
            pdf_writer = PdfWriter()

            for pdf_path in downloaded_pdfs:
                try:
                    with open(pdf_path, 'rb') as pdf_file:
                        pdf_reader = PdfReader(pdf_file)
                        for page in pdf_reader.pages:
                            pdf_writer.add_page(page)
                except Exception as e:
                    current_app.logger.error(f"Failed to add PDF {pdf_path}: {str(e)}")

            # Write merged PDF to buffer
            output_buffer = BytesIO()
            pdf_writer.write(output_buffer)
            output_buffer.seek(0)

            # Clean up temp directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

            # Return merged PDF
            response = make_response(output_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="SalesTools_{target_date.strftime("%Y-%m-%d")}.pdf"'

            return response

        except Exception as e:
            # Clean up on error
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    except Exception as e:
        current_app.logger.error(f"Error generating SalesTools PDF: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to generate SalesTools PDF: {str(e)}'}), 500


@admin_bp.route('/api/print_event_paperwork/<int:event_id>')
@require_authentication()
def print_event_paperwork(event_id):
    """Print paperwork for a single event"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from io import BytesIO

        db = current_app.extensions['sqlalchemy']
        Event = current_app.config['Event']
        Employee = current_app.config['Employee']
        Schedule = current_app.config['Schedule']

        # Get event details
        event = Event.query.get(event_id)
        if not event:
            return jsonify({'error': f'Event {event_id} not found'}), 404

        # Get schedules for this event
        schedules = Schedule.query.filter_by(event_ref_num=event.project_ref_num).all()
        if not schedules:
            return jsonify({'error': f'Event {event_id} is not scheduled'}), 404

        # Generate simple PDF for single event
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)

        # Title
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 750, f"Event Paperwork - {event.project_name}")
        p.setFont("Helvetica", 12)
        p.drawString(100, 730, f"Event ID: {event.id}")
        p.drawString(100, 710, f"Date: {event.start_datetime.strftime('%Y-%m-%d %I:%M %p')}")
        p.drawString(100, 690, f"Type: {event.event_type}")
        
        # Employees assigned
        y = 650
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, y, "Assigned Employees:")
        y -= 20
        
        p.setFont("Helvetica", 11)
        for schedule in schedules:
            employee = Employee.query.get(schedule.employee_id)
            if employee:
                time_str = schedule.schedule_datetime.strftime('%I:%M %p') if schedule.schedule_datetime else 'TBD'
                p.drawString(120, y, f"• {employee.name} - {time_str}")
                y -= 18
        
        p.save()
        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="Event_{event_id}_Paperwork.pdf"'
        
        return response

    except Exception as e:
        current_app.logger.error(f"Error generating event paperwork: {str(e)}")
        return jsonify({'error': f'Failed to generate paperwork: {str(e)}'}), 500


@admin_bp.route('/api/auto_schedule_event/<int:event_id>', methods=['POST'])
@require_authentication()
def auto_schedule_event(event_id):
    """Auto-schedule a single event using SchedulingEngine"""
    try:
        db = current_app.extensions['sqlalchemy']
        Event = current_app.config['Event']
        SchedulerRunHistory = current_app.config['SchedulerRunHistory']

        # Get event
        event = Event.query.get(event_id)
        if not event:
            return jsonify({'error': f'Event {event_id} not found'}), 404

        # Check if already scheduled
        if event.condition in ['Scheduled', 'Submitted']:
            return jsonify({'error': f'Event {event_id} is already scheduled'}), 400

        # Initialize SchedulingEngine
        from app.services.scheduling_engine import SchedulingEngine
        models = {k: current_app.config[k] for k in [
            'Employee', 'Event', 'Schedule', 'SchedulerRunHistory',
            'PendingSchedule', 'RotationAssignment', 'ScheduleException',
            'EmployeeTimeOff', 'EmployeeAvailability', 'EmployeeWeeklyAvailability'
        ]}
        engine = SchedulingEngine(db.session, models)

        # Create run history
        run = SchedulerRunHistory(
            run_type='manual',
            total_events_processed=1,
            events_scheduled=0,
            events_requiring_swaps=0,
            events_failed=0
        )
        db.session.add(run)
        db.session.commit()

        # Try to schedule the event
        result = engine.schedule_single_event(event)

        if not result:
            run.events_failed = 1
            db.session.commit()
            return jsonify({'error': 'Failed to find available employee for this event'}), 500

        # Single-event auto-scheduling always creates the schedule immediately (no approval needed)
        Schedule = current_app.config['Schedule']

        # Create the schedule
        schedule = Schedule(
            event_ref_num=event.project_ref_num,
            employee_id=result['employee_id'],
            schedule_datetime=result['schedule_datetime']
        )
        db.session.add(schedule)

        # Update event status
        event.is_scheduled = True
        event.condition = 'Scheduled'

        run.events_scheduled = 1
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Scheduled for {result["employee_name"]} on {result["schedule_datetime"].strftime("%m/%d at %I:%M %p")}',
            'employee_name': result['employee_name'],
            'schedule_datetime': result['schedule_datetime'].isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error auto-scheduling event {event_id}: {str(e)}")
        return jsonify({'error': f'Scheduling failed: {str(e)}'}), 500


@admin_bp.route('/employees/analytics', methods=['GET'])
@require_authentication()
def employee_analytics():
    """Display employee scheduling analytics for the selected week"""
    from datetime import datetime, timedelta
    
    db = current_app.extensions['sqlalchemy']
    Employee = current_app.config['Employee']
    Schedule = current_app.config['Schedule']
    
    # Get week_start parameter or default to current week's Sunday
    week_start_str = request.args.get('week_start')
    if week_start_str:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
    else:
        today = date.today()
        # Calculate Sunday: go back (weekday + 1) days (Monday=0, Sunday=6)
        week_start = today - timedelta(days=(today.weekday() + 1) % 7)
    
    week_end = week_start + timedelta(days=6)  # Saturday
    
    # Query employee statistics
    from sqlalchemy import func
    stats = db.session.query(
        Employee.id,
        Employee.name,
        func.count(func.distinct(func.date(Schedule.schedule_datetime))).label('days_scheduled'),
        func.count(Schedule.id).label('total_events')
    ).join(
        Schedule, Employee.id == Schedule.employee_id
    ).filter(
        func.date(Schedule.schedule_datetime) >= week_start,
        func.date(Schedule.schedule_datetime) <= week_end
    ).group_by(
        Employee.id, Employee.name
    ).order_by(
        func.count(func.distinct(func.date(Schedule.schedule_datetime))).desc()
    ).all()
    
    # Convert to list of dicts
    employee_stats = []
    for stat in stats:
        employee_stats.append({
            'employee_id': stat[0],
            'employee_name': stat[1],
            'days_scheduled': stat[2],
            'total_events': stat[3]
        })
    
    return render_template('employee_analytics.html',
                         employee_stats=employee_stats,
                         week_start=week_start.strftime('%Y-%m-%d'),
                         week_end=week_end.strftime('%Y-%m-%d'))


@admin_bp.route('/api/print_weekly_summary/<week_start_str>')
@require_authentication()
def print_weekly_summary(week_start_str):
    """Print weekly schedule summary for all employees (Core events with Juicer days highlighted in orange)"""
    try:
        from collections import defaultdict
        from xhtml2pdf import pisa
        from io import BytesIO

        db = current_app.extensions['sqlalchemy']
        Employee = current_app.config['Employee']
        Schedule = current_app.config['Schedule']
        Event = current_app.config['Event']

        # Parse week start
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        week_end = week_start + timedelta(days=6)

        # Query CORE schedules for the week
        core_schedules = db.session.query(
            Employee.name,
            Schedule.schedule_datetime,
            Event.event_type
        ).join(
            Schedule, Employee.id == Schedule.employee_id
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) >= week_start,
            func.date(Schedule.schedule_datetime) <= week_end,
            Event.event_type == 'Core'
        ).order_by(
            Employee.name, Schedule.schedule_datetime
        ).all()

        # Query JUICER schedules for the week (to determine which days to highlight)
        juicer_schedules = db.session.query(
            Employee.name,
            Schedule.schedule_datetime,
            Event.event_type
        ).join(
            Schedule, Employee.id == Schedule.employee_id
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) >= week_start,
            func.date(Schedule.schedule_datetime) <= week_end,
            Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean', 'Juicer'])
        ).order_by(
            Employee.name, Schedule.schedule_datetime
        ).all()

        # Group CORE schedules by employee and day
        core_employee_schedules = defaultdict(lambda: defaultdict(list))
        for name, schedule_dt, event_type in core_schedules:
            day_name = schedule_dt.strftime('%a')  # Mon, Tue, Wed
            time_str = schedule_dt.strftime('%I:%M %p')
            core_employee_schedules[name][day_name].append(time_str)

        # Track Juicer events by employee/day with times and types
        # Structure: juicer_employee_schedules[name][day] = {'Production': [times], 'Survey': [times]}
        juicer_employee_schedules = defaultdict(lambda: defaultdict(lambda: {'Production': [], 'Survey': []}))
        for name, schedule_dt, event_type in juicer_schedules:
            day_name = schedule_dt.strftime('%a')
            time_str = schedule_dt.strftime('%I:%M %p')
            if 'Production' in event_type:
                juicer_employee_schedules[name][day_name]['Production'].append(time_str)
            elif 'Survey' in event_type:
                juicer_employee_schedules[name][day_name]['Survey'].append(time_str)
            # Also add employee to core_employee_schedules if not already present
            if name not in core_employee_schedules:
                core_employee_schedules[name] = defaultdict(list)

        # Calculate dates for each day of the week
        day_dates = []
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            day_dates.append(day_date)

        # Build list of day abbreviations from actual dates
        day_abbrevs = [d.strftime('%a') for d in day_dates]

        # Generate HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Weekly Schedule Summary</title>
            <style>
                @page {{ size: A4 landscape; margin: 0.5in; }}
                body {{ font-family: Arial, sans-serif; font-size: 10pt; }}
                .header {{ text-align: center; margin-bottom: 20px; border-bottom: 2px solid #2E4C73; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                th {{ background: #2E4C73; color: white; padding: 8px; text-align: left; font-size: 9pt; }}
                .day-header {{ font-weight: bold; }}
                .date-header {{ font-size: 8pt; font-weight: normal; }}
                td {{ padding: 6px 8px; border: 1px solid #ddd; font-size: 9pt; }}
                tr:nth-child(even) {{ background: #f9f9f9; }}
                .juicer-day {{ background: #FFE0B2 !important; }}
                .juicer-time {{ color: #E65100; font-size: 8pt; }}
                .juicer-label {{ font-weight: bold; color: #E65100; }}
                .legend {{ margin-top: 10px; font-size: 9pt; color: #666; }}
                .legend-box {{ display: inline-block; width: 15px; height: 15px; background: #FFE0B2; border: 1px solid #FF9800; vertical-align: middle; margin-right: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Weekly Schedule Summary - {week_start.strftime('%B %d')} to {week_end.strftime('%B %d, %Y')}</h2>
                <p>(CORE + Juicer Events)</p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 20%;">Employee</th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[0].strftime('%a')}</div><div class="date-header">{day_dates[0].strftime('%b %d')}</div></th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[1].strftime('%a')}</div><div class="date-header">{day_dates[1].strftime('%b %d')}</div></th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[2].strftime('%a')}</div><div class="date-header">{day_dates[2].strftime('%b %d')}</div></th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[3].strftime('%a')}</div><div class="date-header">{day_dates[3].strftime('%b %d')}</div></th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[4].strftime('%a')}</div><div class="date-header">{day_dates[4].strftime('%b %d')}</div></th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[5].strftime('%a')}</div><div class="date-header">{day_dates[5].strftime('%b %d')}</div></th>
                        <th style="width: 11.4%;"><div class="day-header">{day_dates[6].strftime('%a')}</div><div class="date-header">{day_dates[6].strftime('%b %d')}</div></th>
                    </tr>
                </thead>
                <tbody>
        """

        # Add employee rows - highlight cells orange if employee has Juicer event that day
        for employee_name in sorted(core_employee_schedules.keys()):
            html += f"<tr><td><strong>{employee_name}</strong></td>"
            for day in day_abbrevs:
                core_times = core_employee_schedules[employee_name].get(day, [])
                juicer_data = juicer_employee_schedules.get(employee_name, {}).get(day, {'Production': [], 'Survey': []})
                has_juicer = juicer_data['Production'] or juicer_data['Survey']
                cell_class = 'class="juicer-day"' if has_juicer else ''

                # Build cell content
                cell_parts = []
                if core_times:
                    cell_parts.append('<br>'.join(core_times))
                if juicer_data['Production']:
                    cell_parts.append(f'<span class="juicer-time"><span class="juicer-label">P:</span> {", ".join(juicer_data["Production"])}</span>')
                if juicer_data['Survey']:
                    cell_parts.append(f'<span class="juicer-time"><span class="juicer-label">S:</span> {", ".join(juicer_data["Survey"])}</span>')

                cell_content = '<br>'.join(cell_parts) if cell_parts else '-'
                html += f"<td {cell_class}>{cell_content}</td>"
            html += "</tr>"

        if not core_employee_schedules:
            html += f'<tr><td colspan="8" style="text-align: center; color: #666;">No events scheduled for this week</td></tr>'

        html += """
                </tbody>
            </table>
            <div class="legend">
                <span class="legend-box"></span> Orange cell = Juicer day | <strong style="color: #E65100;">P:</strong> Production time | <strong style="color: #E65100;">S:</strong> Survey time
            </div>
        </body>
        </html>
        """

        # Generate PDF
        output = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=output)

        if pisa_status.err:
            return jsonify({'error': 'PDF generation failed'}), 500

        output.seek(0)

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename="Weekly_Summary_{week_start_str}.pdf"'

        return response

    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        current_app.logger.error(f"Error generating weekly summary: {str(e)}")
        return jsonify({'error': f'Failed to generate summary: {str(e)}'}), 500


@admin_bp.route('/api/print_employee_schedule/<int:employee_id>/<week_start_str>')
@require_authentication()
def print_employee_schedule(employee_id, week_start_str):
    """Print detailed weekly schedule for a single employee (all event types)"""
    try:
        from collections import defaultdict
        from xhtml2pdf import pisa
        from io import BytesIO

        db = current_app.extensions['sqlalchemy']
        Employee = current_app.config['Employee']
        Schedule = current_app.config['Schedule']
        Event = current_app.config['Event']

        # Get employee
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'error': f'Employee {employee_id} not found'}), 404

        # Parse week start
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        week_end = week_start + timedelta(days=6)

        # Query schedules for the employee
        schedules = db.session.query(
            Schedule.schedule_datetime,
            Event.project_name,
            Event.event_type
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee_id,
            func.date(Schedule.schedule_datetime) >= week_start,
            func.date(Schedule.schedule_datetime) <= week_end
        ).order_by(
            Schedule.schedule_datetime
        ).all()

        # Group by date
        daily_schedules = defaultdict(list)
        for schedule_dt, project_name, event_type in schedules:
            day_key = schedule_dt.date()
            daily_schedules[day_key].append({
                'time': schedule_dt.strftime('%I:%M %p'),
                'name': project_name,
                'type': event_type
            })

        # Generate HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{employee.name} - Weekly Schedule</title>
            <style>
                @page {{ size: A4 landscape; margin: 0.75in; }}
                body {{ font-family: Arial, sans-serif; }}
                .header {{ text-align: center; margin-bottom: 30px; border-bottom: 3px solid #2E4C73; padding-bottom: 15px; }}
                h1 {{ color: #2E4C73; margin: 0; font-size: 24pt; }}
                .week-range {{ color: #666; font-size: 14pt; margin-top: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #2E4C73; color: white; padding: 12px; text-align: left; font-size: 12pt; }}
                td {{ padding: 10px 12px; border: 1px solid #ddd; font-size: 11pt; vertical-align: top; }}
                tr:nth-child(even) {{ background: #f9f9f9; }}
                .day-header {{ font-weight: bold; color: #2E4C73; font-size: 12pt; }}
                .event-time {{ color: #1B9BD8; font-weight: bold; }}
                .no-events {{ color: #999; font-style: italic; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{employee.name}</h1>
                <p class="week-range">Week of {week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}</p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 15%;">Day</th>
                        <th style="width: 15%;">Time</th>
                        <th style="width: 70%;">Event</th>
                    </tr>
                </thead>
                <tbody>
        """

        # Add rows for each day
        current_date = week_start
        while current_date <= week_end:
            day_name = current_date.strftime('%A, %B %d')
            events = daily_schedules.get(current_date, [])

            if events:
                for idx, event in enumerate(events):
                    if idx == 0:
                        html += f"""
                        <tr>
                            <td class="day-header" rowspan="{len(events)}">{day_name}</td>
                            <td class="event-time">{event['time']}</td>
                            <td>{event['name']} <em>({event['type']})</em></td>
                        </tr>
                        """
                    else:
                        html += f"""
                        <tr>
                            <td class="event-time">{event['time']}</td>
                            <td>{event['name']} <em>({event['type']})</em></td>
                        </tr>
                        """
            else:
                html += f"""
                <tr>
                    <td class="day-header">{day_name}</td>
                    <td class="no-events" colspan="2">No events scheduled</td>
                </tr>
                """

            current_date += timedelta(days=1)

        html += """
                </tbody>
            </table>
        </body>
        </html>
        """

        # Generate PDF
        output = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=output)

        if pisa_status.err:
            return jsonify({'error': 'PDF generation failed'}), 500

        output.seek(0)

        filename = employee.name.replace(' ', '_') + f'_Schedule_{week_start_str}.pdf'
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        current_app.logger.error(f"Error generating employee schedule: {str(e)}")
        return jsonify({'error': f'Failed to generate schedule: {str(e)}'}), 500


@admin_bp.route('/settings')
@require_authentication()
def settings_page():
    """Display settings page for Retail Link credentials and other configuration"""
    SystemSetting = current_app.config.get('SystemSetting')

    # Get current settings
    settings = {}
    if SystemSetting:
        settings['edr_username'] = SystemSetting.get_setting('edr_username') or ''
        settings['edr_password'] = '***' if SystemSetting.get_setting('edr_password') else ''
        settings['edr_mfa_credential_id'] = SystemSetting.get_setting('edr_mfa_credential_id') or ''
        settings['ai_provider'] = SystemSetting.get_setting('ai_provider') or 'openai'
        settings['ai_api_key'] = '***' if SystemSetting.get_setting('ai_api_key') else ''
        settings['auto_scheduler_enabled'] = SystemSetting.get_setting('auto_scheduler_enabled', True)
        settings['auto_scheduler_require_approval'] = SystemSetting.get_setting('auto_scheduler_require_approval', True)
    else:
        settings['edr_username'] = current_app.config.get('WALMART_EDR_USERNAME', '')
        settings['edr_password'] = '***' if current_app.config.get('WALMART_EDR_PASSWORD') else ''
        settings['edr_mfa_credential_id'] = current_app.config.get('WALMART_EDR_MFA_CREDENTIAL_ID', '')
        settings['ai_provider'] = current_app.config.get('AI_PROVIDER', 'openai')
        settings['ai_api_key'] = '***' if current_app.config.get('AI_API_KEY') else ''
        settings['auto_scheduler_enabled'] = current_app.config.get('AUTO_SCHEDULER_ENABLED', True)
        settings['auto_scheduler_require_approval'] = current_app.config.get('AUTO_SCHEDULER_REQUIRE_APPROVAL', True)

    # Load event time settings
    event_times = {}
    if SystemSetting:
        # Load single event times
        for event_type in ['freeosk', 'supervisor', 'other']:
            event_times[f'{event_type}_start_time'] = SystemSetting.get_setting(f'{event_type}_start_time', '')
            event_times[f'{event_type}_end_time'] = SystemSetting.get_setting(f'{event_type}_end_time', '')

        # Load multi-slot event times
        for slot in range(1, 5):
            for event_type in ['digital_setup', 'digital_teardown']:
                event_times[f'{event_type}_{slot}_start_time'] = SystemSetting.get_setting(f'{event_type}_{slot}_start_time', '')
                event_times[f'{event_type}_{slot}_end_time'] = SystemSetting.get_setting(f'{event_type}_{slot}_end_time', '')

            # Note: Core event times are now managed via Shift Blocks (/admin/shift-blocks)

    return render_template('settings.html', settings=settings, event_times=event_times)


@admin_bp.route('/event-times')
@require_authentication()
def event_times_page():
    """Display consolidated event time settings page"""
    return render_template('event_times.html')


# Keep old route for backwards compatibility
@admin_bp.route('/shift-blocks')
@require_authentication()
def shift_blocks_page():
    """Redirect to new event times page"""
    from flask import redirect, url_for
    return redirect(url_for('admin.event_times_page'))


@admin_bp.route('/api/settings/edr', methods=['POST'])
@require_authentication()
def save_edr_settings():
    """Save Retail Link EDR credentials to database"""
    try:
        from flask import session as flask_session
        SystemSetting = current_app.config.get('SystemSetting')

        if not SystemSetting:
            return jsonify({'success': False, 'message': 'SystemSetting model not available'}), 500

        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip() if data.get('password') else None
        mfa_credential_id = data.get('mfa_credential_id', '').strip()

        # Validate required fields (username and MFA credential always required)
        if not username or not mfa_credential_id:
            return jsonify({'success': False, 'message': 'Username and MFA Credential ID are required'}), 400

        # Check if password is required (only if no existing password)
        existing_password = SystemSetting.get_setting('edr_password')
        if not password and not existing_password:
            return jsonify({'success': False, 'message': 'Password is required for initial setup'}), 400

        # Save to database
        SystemSetting.set_setting('edr_username', username)

        # Only update password if a new one was provided
        if password:
            SystemSetting.set_setting('edr_password', password, setting_type='encrypted')

        SystemSetting.set_setting('edr_mfa_credential_id', mfa_credential_id)

        # Clear any existing EDR session
        if 'edr_auth_token' in flask_session:
            del flask_session['edr_auth_token']
        if 'edr_session_cookies' in flask_session:
            del flask_session['edr_session_cookies']

        current_app.logger.info("Retail Link EDR credentials updated successfully")
        return jsonify({'success': True, 'message': 'Credentials saved successfully'})

    except Exception as e:
        current_app.logger.error(f"Failed to save EDR settings: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/settings/ai', methods=['POST'])
@require_authentication()
def save_ai_settings():
    """Save AI Assistant provider and API key to database"""
    try:
        SystemSetting = current_app.config.get('SystemSetting')

        if not SystemSetting:
            return jsonify({'success': False, 'message': 'SystemSetting model not available'}), 500

        data = request.get_json()
        provider = data.get('provider', '').strip()
        api_key = data.get('api_key', '').strip()

        # Validate provider
        valid_providers = ['openai', 'anthropic', 'gemini']
        if provider and provider not in valid_providers:
            return jsonify({
                'success': False,
                'message': f'Invalid provider. Must be one of: {", ".join(valid_providers)}'
            }), 400

        # Save provider if provided
        if provider:
            SystemSetting.set_setting('ai_provider', provider, setting_type='string')
            current_app.logger.info(f"AI provider updated to: {provider}")

        # Save API key if provided (encrypted)
        if api_key:
            SystemSetting.set_setting('ai_api_key', api_key, setting_type='encrypted')
            current_app.logger.info("AI API key updated successfully")

        if not provider and not api_key:
            return jsonify({'success': False, 'message': 'No settings to update'}), 400

        return jsonify({'success': True, 'message': 'AI settings saved successfully'})

    except Exception as e:
        current_app.logger.error(f"Failed to save AI settings: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/settings/auto-scheduler', methods=['POST'])
@require_authentication()
def save_auto_scheduler_settings():
    """Save Auto-Scheduler configuration settings to database"""
    try:
        SystemSetting = current_app.config.get('SystemSetting')

        if not SystemSetting:
            return jsonify({'success': False, 'message': 'SystemSetting model not available'}), 500

        data = request.get_json()
        enabled = data.get('enabled')
        require_approval = data.get('require_approval')

        # Save enabled setting if provided
        if enabled is not None:
            SystemSetting.set_setting('auto_scheduler_enabled', enabled, setting_type='boolean')
            current_app.logger.info(f"Auto-scheduler enabled updated to: {enabled}")

        # Save require_approval setting if provided
        if require_approval is not None:
            SystemSetting.set_setting('auto_scheduler_require_approval', require_approval, setting_type='boolean')
            current_app.logger.info(f"Auto-scheduler require_approval updated to: {require_approval}")

        if enabled is None and require_approval is None:
            return jsonify({'success': False, 'message': 'No settings to update'}), 400

        return jsonify({'success': True, 'message': 'Auto-scheduler settings saved successfully'})

    except Exception as e:
        current_app.logger.error(f"Failed to save auto-scheduler settings: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/settings/event-times', methods=['POST'])
@require_authentication()
def save_event_time_settings():
    """Save event time configuration settings to database"""
    try:
        SystemSetting = current_app.config.get('SystemSetting')

        if not SystemSetting:
            return jsonify({'success': False, 'message': 'SystemSetting model not available'}), 500

        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        # Validate and save event time settings
        saved_count = 0

        # Define expected settings
        expected_settings = [
            'freeosk_start_time', 'freeosk_end_time',
            'supervisor_start_time', 'supervisor_end_time',
            'other_start_time', 'other_end_time'
        ]

        # Add multi-slot settings for Digital Setup/Teardown
        for slot in range(1, 5):
            for event_type in ['digital_setup', 'digital_teardown']:
                expected_settings.append(f'{event_type}_{slot}_start_time')
                expected_settings.append(f'{event_type}_{slot}_end_time')
            # Note: Core event times are now managed via Shift Blocks (/admin/shift-blocks)

        # Save each setting
        for key, value in data.items():
            if key in expected_settings:
                # Validate time format (HH:MM)
                if not value or not isinstance(value, str):
                    continue

                # Simple time format validation
                parts = value.split(':')
                if len(parts) != 2:
                    return jsonify({
                        'success': False,
                        'message': f'Invalid time format for {key}. Expected HH:MM'
                    }), 400

                try:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                        return jsonify({
                            'success': False,
                            'message': f'Invalid time value for {key}. Hour must be 0-23, minute must be 0-59'
                        }), 400
                except ValueError:
                    return jsonify({
                        'success': False,
                        'message': f'Invalid time format for {key}. Expected HH:MM'
                    }), 400

                # Save setting
                SystemSetting.set_setting(key, value, setting_type='string')
                saved_count += 1

        if saved_count == 0:
            return jsonify({'success': False, 'message': 'No valid settings to save'}), 400

        # Clear the event time settings cache
        from app.services.event_time_settings import clear_event_time_cache
        clear_event_time_cache()

        current_app.logger.info(f"Saved {saved_count} event time settings")
        return jsonify({
            'success': True,
            'message': f'Event time settings saved successfully ({saved_count} settings updated)'
        })

    except Exception as e:
        current_app.logger.error(f"Failed to save event time settings: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/event-times', methods=['GET'])
@require_authentication()
def get_event_times():
    """Get all event time settings"""
    try:
        SystemSetting = current_app.config.get('SystemSetting')

        if not SystemSetting:
            return jsonify({'success': False, 'error': 'SystemSetting not available'}), 500

        times = {}

        # Load simple event times
        for event_type in ['freeosk', 'supervisor', 'other']:
            times[f'{event_type}_start_time'] = SystemSetting.get_setting(f'{event_type}_start_time', '')
            times[f'{event_type}_end_time'] = SystemSetting.get_setting(f'{event_type}_end_time', '')

        # Load multi-slot event times
        for slot in range(1, 5):
            for event_type in ['digital_setup', 'digital_teardown']:
                times[f'{event_type}_{slot}_start_time'] = SystemSetting.get_setting(f'{event_type}_{slot}_start_time', '')
                times[f'{event_type}_{slot}_end_time'] = SystemSetting.get_setting(f'{event_type}_{slot}_end_time', '')

        return jsonify({'success': True, 'times': times})

    except Exception as e:
        current_app.logger.error(f"Failed to get event times: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/sync/employees', methods=['POST'])
@require_authentication()
def sync_employees_from_api():
    """
    Sync employee data from Crossmark API
    Uses getQualifiedRepsForScheduling to fetch current employee RepIDs and info
    """
    try:
        db = current_app.extensions['sqlalchemy']
        Employee = current_app.config['Employee']
        Event = current_app.config['Event']
        from app.integrations.external_api.session_api_service import session_api as external_api

        # Ensure authenticated
        if not external_api.ensure_authenticated():
            return jsonify({'success': False, 'error': 'Failed to authenticate with Crossmark API'}), 401

        # Get a sample event to fetch qualified reps
        sample_event = Event.query.filter(Event.location_mvid.isnot(None)).first()
        if not sample_event:
            return jsonify({'success': False, 'error': 'No events found to fetch qualified reps'}), 404

        current_app.logger.info(f"Fetching qualified reps using event {sample_event.external_id} at location {sample_event.location_mvid}")

        # Fetch qualified reps from API
        reps_data = external_api.get_qualified_reps_for_scheduling(
            mplan_id=sample_event.external_id,
            store_id=sample_event.location_mvid
        )

        if not reps_data or 'data' not in reps_data:
            return jsonify({'success': False, 'error': 'No qualified reps data returned from API'}), 500

        current_app.logger.info(f"Fetched {len(reps_data.get('data', []))} qualified reps from API")

        # Update employees with correct RepIDs
        updated_count = 0
        not_found = []

        for rep in reps_data.get('data', []):
            rep_id = rep.get('ID') or rep.get('RepID')
            first_name = rep.get('FirstName', '').strip()
            last_name = rep.get('LastName', '').strip()
            full_name = f"{first_name} {last_name}".upper()

            if not rep_id:
                continue

            # Try to find employee by name
            employee = Employee.query.filter(
                db.func.upper(Employee.name) == full_name
            ).first()

            if employee:
                # Update external_id with correct RepID
                old_rep_id = employee.external_id
                employee.external_id = str(rep_id)
                employee.last_synced = datetime.utcnow()
                updated_count += 1
                current_app.logger.info(f"Updated {employee.name}: RepID {old_rep_id} -> {rep_id}")
            else:
                not_found.append(full_name)
                current_app.logger.warning(f"Employee not found in database: {full_name} (RepID: {rep_id})")

        # Commit changes
        db.session.commit()

        return jsonify({
            'success': True,
            'updated': updated_count,
            'not_found': not_found,
            'total_reps_fetched': len(reps_data.get('data', []))
        })

    except Exception as e:
        current_app.logger.error(f"Error syncing employees: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/daily_paperwork/request_mfa', methods=['POST'])
@require_authentication()
def request_daily_paperwork_mfa():
    """
    Request MFA code for daily paperwork generation

    DEPRECATED: Use /api/admin/edr/request-code instead.
    This route redirects to the unified EDR authentication endpoint.
    """
    # Redirect to unified EDR authentication
    return edr_request_code()


@admin_bp.route('/api/edr_reports/request_mfa', methods=['POST'])
@require_authentication()
def request_edr_reports_mfa():
    """
    Request MFA code for EDR reports generation
    Uses the unified EDR authentication endpoint
    """
    return edr_request_code()


@admin_bp.route('/api/edr_reports/generate_by_date', methods=['POST'])
@require_authentication()
def generate_edr_reports_by_date():
    """
    Generate EDR reports for all CORE events on a specific date
    Extracts event numbers from CORE events and generates individual EDR reports
    Returns a consolidated PDF
    """
    try:
        from flask import session as flask_session
        from app.integrations.edr import EDRReportGenerator
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, PageBreak
        from reportlab.lib.units import inch
        import pickle
        import re
        from io import BytesIO

        data = request.get_json()
        date_str = data.get('date')  # Format: YYYY-MM-DD
        mfa_code = data.get('mfa_code')

        if not date_str:
            return jsonify({'error': 'Date required'}), 400

        # Parse date
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Authenticate with MFA code if provided and not already authenticated
        if mfa_code and not flask_session.get('edr_auth_token'):
            current_app.logger.info("Completing EDR authentication with provided MFA code...")

            # Check if MFA was requested
            if not flask_session.get('edr_mfa_requested'):
                return jsonify({'error': 'No MFA request found. Please request MFA code first.'}), 400

            cache_file = flask_session.get('edr_cache_file')
            if not cache_file or not os.path.exists(cache_file):
                return jsonify({'error': 'Session expired. Please request MFA code again.'}), 400

            # Load cached cookies
            with open(cache_file, 'rb') as f:
                cached_cookies = pickle.load(f)

            # Get credentials and create EDR generator
            username, password, mfa_credential_id = _get_edr_credentials()
            edr_gen = EDRReportGenerator(username, password, mfa_credential_id)

            # Restore cookies
            edr_gen.session.cookies.clear()
            for name, value in cached_cookies.items():
                edr_gen.session.cookies.set(name, value)

            # Validate MFA code (step 3)
            if not edr_gen.step3_validate_mfa_code(mfa_code):
                return jsonify({'error': 'Invalid MFA code'}), 401

            # Complete authentication (steps 4-6)
            edr_gen.step4_register_page_access()
            edr_gen.step5_navigate_to_event_management()

            if not edr_gen.step6_authenticate_event_management():
                return jsonify({'error': 'Authentication failed at step 6'}), 500

            # Store auth token and cookies in Flask session
            flask_session['edr_auth_token'] = edr_gen.auth_token

            essential_cookies = {}
            for cookie in edr_gen.session.cookies:
                if cookie.name in ['_auth', '_refreshAuth', 'RLSESSION', 'RETAILLINKSESSION',
                                   'TS0111a950', 'TS01b1e5a6', 'TS04fe286f027']:
                    essential_cookies[cookie.name] = cookie.value

            flask_session['edr_session_cookies'] = essential_cookies

            # Cleanup temp files
            if cache_file and os.path.exists(cache_file):
                os.remove(cache_file)

            current_app.logger.info(f"[OK] Authentication complete! Auth token: {edr_gen.auth_token[:50]}...")

        # Get database and models
        db = current_app.extensions['sqlalchemy']
        Event = current_app.config['Event']
        Schedule = current_app.config['Schedule']

        # Get all CORE events scheduled for the target date
        core_events = db.session.query(Event, Schedule).join(
            Schedule, Event.project_ref_num == Schedule.event_ref_num
        ).filter(
            db.func.date(Schedule.schedule_datetime) == target_date,
            Event.event_type == 'Core'
        ).all()

        if not core_events:
            return jsonify({'error': f'No CORE events found for {date_str}'}), 404

        current_app.logger.info(f"Found {len(core_events)} CORE events for {date_str}")

        # Extract event numbers (first 6 digits from project_name)
        event_numbers = []
        for event, schedule in core_events:
            # Extract first 6 digits from project_name
            match = re.match(r'^(\d{6})', event.project_name)
            if match:
                event_number = match.group(1)
                event_numbers.append(event_number)
                current_app.logger.info(f"Extracted event number {event_number} from {event.project_name}")
            else:
                current_app.logger.warning(f"Could not extract event number from {event.project_name}")

        if not event_numbers:
            return jsonify({'error': 'No valid event numbers found in CORE events'}), 404

        current_app.logger.info(f"Processing {len(event_numbers)} event numbers: {event_numbers}")

        # Restore EDR generator from Flask session if authenticated
        if not flask_session.get('edr_auth_token'):
            return jsonify({'error': 'EDR authentication required'}), 401

        username, password, mfa_credential_id = _get_edr_credentials()
        edr_gen = EDRReportGenerator(username, password, mfa_credential_id)

        # Restore session cookies
        if flask_session.get('edr_session_cookies'):
            for name, value in flask_session['edr_session_cookies'].items():
                edr_gen.session.cookies.set(name, value)

        # Restore auth token
        edr_gen.auth_token = flask_session['edr_auth_token']

        # Generate EDR reports for each event number
        html_reports = []
        for event_number in event_numbers:
            try:
                current_app.logger.info(f"Generating EDR report for event {event_number}")
                edr_data = edr_gen.get_edr_report(event_number)
                if edr_data:
                    html_report = edr_gen.generate_html_report(edr_data)
                    html_reports.append((event_number, html_report))
                else:
                    current_app.logger.warning(f"No EDR data returned for event {event_number}")
            except Exception as e:
                current_app.logger.error(f"Error generating EDR for event {event_number}: {str(e)}")

        if not html_reports:
            return jsonify({'error': 'Failed to generate any EDR reports'}), 500

        # Create consolidated PDF using weasyprint or return HTML files
        try:
            from weasyprint import HTML

            # Create a temporary PDF for each report and merge them
            pdf_buffer = BytesIO()

            # For the first HTML report, write to buffer
            HTML(string=html_reports[0][1]).write_pdf(pdf_buffer)

            # For subsequent reports, we need to merge PDFs
            if len(html_reports) > 1:
                from PyPDF2 import PdfMerger
                merger = PdfMerger()

                # Add first PDF
                pdf_buffer.seek(0)
                merger.append(pdf_buffer)

                # Add remaining PDFs
                for event_num, html in html_reports[1:]:
                    temp_buffer = BytesIO()
                    HTML(string=html).write_pdf(temp_buffer)
                    temp_buffer.seek(0)
                    merger.append(temp_buffer)

                # Write merged PDF to final buffer
                final_buffer = BytesIO()
                merger.write(final_buffer)
                merger.close()
                pdf_data = final_buffer.getvalue()
            else:
                pdf_data = pdf_buffer.getvalue()

        except ImportError:
            # Fallback: Return first HTML report as attachment
            current_app.logger.warning("WeasyPrint not available, returning HTML instead of PDF")
            response = make_response(html_reports[0][1])
            response.headers['Content-Type'] = 'text/html'
            response.headers['Content-Disposition'] = f'attachment; filename="EDR_Report_{date_str}.html"'
            return response

        # Return PDF
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="EDR_Reports_{date_str}.pdf"'

        return response

    except Exception as e:
        current_app.logger.error(f"Error generating EDR reports: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/daily_paperwork/generate', methods=['POST'])
@require_authentication()
def generate_daily_paperwork():
    """
    Generate daily paperwork using authenticated EDR session

    Supports two authentication flows:
    1. NEW: Uses unified EDR authentication from Flask session (preferred)
    2. LEGACY: Accepts mfa_code in request body for backward compatibility
    """
    try:
        from flask import session as flask_session
        from app.services.daily_paperwork_generator import DailyPaperworkGenerator
        from app.integrations.edr import EDRReportGenerator
        import pickle

        data = request.get_json()
        date_str = data.get('date')  # Format: YYYY-MM-DD
        mfa_code = data.get('mfa_code')  # Legacy parameter

        if not date_str:
            return jsonify({'error': 'Date required'}), 400

        # Parse date
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # LEGACY FLOW: If mfa_code provided and not already authenticated
        if mfa_code and not flask_session.get('edr_auth_token'):
            current_app.logger.info("Completing EDR authentication with provided MFA code...")

            # Check if MFA was requested
            if not flask_session.get('edr_mfa_requested'):
                return jsonify({'error': 'No MFA request found. Please request MFA code first.'}), 400

            cache_file = flask_session.get('edr_cache_file')
            if not cache_file or not os.path.exists(cache_file):
                return jsonify({'error': 'Session expired. Please request MFA code again.'}), 400

            # Load cached cookies
            with open(cache_file, 'rb') as f:
                cached_cookies = pickle.load(f)

            # Get credentials and create EDR generator
            username, password, mfa_credential_id = _get_edr_credentials()
            edr_gen = EDRReportGenerator(username, password, mfa_credential_id)

            # Restore cookies
            edr_gen.session.cookies.clear()
            for name, value in cached_cookies.items():
                edr_gen.session.cookies.set(name, value)

            # Validate MFA code (step 3)
            if not edr_gen.step3_validate_mfa_code(mfa_code):
                return jsonify({'error': 'Invalid MFA code'}), 401

            # Complete authentication (steps 4-6)
            edr_gen.step4_register_page_access()
            edr_gen.step5_navigate_to_event_management()

            if not edr_gen.step6_authenticate_event_management():
                return jsonify({'error': 'Authentication failed at step 6'}), 500

            # Store auth token and cookies in Flask session
            flask_session['edr_auth_token'] = edr_gen.auth_token

            essential_cookies = {}
            for cookie in edr_gen.session.cookies:
                if cookie.name in ['_auth', '_refreshAuth', 'RLSESSION', 'RETAILLINKSESSION',
                                   'TS0111a950', 'TS01b1e5a6', 'TS04fe286f027']:
                    essential_cookies[cookie.name] = cookie.value

            flask_session['edr_session_cookies'] = essential_cookies

            # Cleanup temp files
            if cache_file and os.path.exists(cache_file):
                os.remove(cache_file)

            current_app.logger.info(f"[OK] Authentication complete! Auth token: {edr_gen.auth_token[:50]}...")
            current_app.logger.info(f"Stored {len(essential_cookies)} essential cookies in session")

        # Get database and models
        db = current_app.extensions['sqlalchemy']
        models_dict = {
            'Event': current_app.config['Event'],
            'Schedule': current_app.config['Schedule'],
            'Employee': current_app.config['Employee'],
            'PaperworkTemplate': current_app.config['PaperworkTemplate']
        }

        # Get authenticated SessionAPIService for downloading SalesTools
        session_api_service = current_app.config.get('SESSION_API_SERVICE')

        # Restore EDR generator from Flask session if authenticated
        edr_gen = None
        if flask_session.get('edr_auth_token'):
            current_app.logger.info("Restoring EDR authentication from Flask session...")

            # Get EDR credentials
            username, password, mfa_credential_id = _get_edr_credentials()
            edr_gen = EDRReportGenerator(username, password, mfa_credential_id)

            # Restore session cookies
            if flask_session.get('edr_session_cookies'):
                current_app.logger.info(f"Restoring {len(flask_session['edr_session_cookies'])} cookies to EDR session")
                for name, value in flask_session['edr_session_cookies'].items():
                    edr_gen.session.cookies.set(name, value)

            # Restore auth token
            edr_gen.auth_token = flask_session['edr_auth_token']
            current_app.logger.info(f"Restored EDR auth token: {edr_gen.auth_token[:50]}...")
        else:
            current_app.logger.warning("No EDR authentication found - paperwork will be generated without EDRs")

        # Create generator with authenticated EDR instance
        generator = DailyPaperworkGenerator(
            db.session,
            models_dict,
            session_api_service,
            edr_generator=edr_gen  # Inject authenticated instance
        )

        # Generate paperwork
        pdf_path = generator.generate_complete_daily_paperwork(target_date)

        if not pdf_path:
            return jsonify({'error': 'Failed to generate daily paperwork'}), 500

        # Read PDF and return as response
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()

        # Cleanup
        generator.cleanup()

        # Return PDF
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="Paperwork_{date_str}.pdf"'

        return response

    except Exception as e:
        current_app.logger.error(f"Error generating daily paperwork: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/schedule-verification')
@require_authentication()
def schedule_verification():
    """
    Schedule Verification page

    Allows managers to verify schedules for any date and identify potential issues.
    Runs 8 validation rules to catch scheduling problems proactively.
    """
    from datetime import date, timedelta

    # Default to tomorrow
    tomorrow = date.today() + timedelta(days=1)

    return render_template(
        'schedule_verification.html',
        default_date=tomorrow.isoformat()
    )
