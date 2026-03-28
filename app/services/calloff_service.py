"""
Calloff Service

Handles calloff submission, supervisor review, attendance integration,
schedule impact detection, pattern analysis, and push/SMS notifications.
"""
import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta

from flask import current_app

from app.models import get_models, get_db

logger = logging.getLogger(__name__)


class CalloffService:
    """Central service for employee calloff operations."""

    def __init__(self):
        self.models = get_models()
        self.db = get_db()

    # ── Submission ──────────────────────────────────────────────

    def submit_calloff(self, employee_id, calloff_date, reason, notes=None):
        """
        Submit a new calloff. Validates inputs, creates the calloff record,
        auto-creates an attendance record, and returns affected events.

        Returns:
            dict with 'calloff' and 'affected_events' on success
        Raises:
            ValueError for validation failures
        """
        EmployeeCalloff = self.models['EmployeeCalloff']
        Employee = self.models['Employee']

        # Validate employee exists and has correct role
        employee = Employee.query.get(employee_id)
        if not employee:
            raise ValueError('Employee not found')
        if employee.role not in ('specialist', 'lead'):
            raise ValueError('Only specialists and leads can submit calloffs')

        # Validate date (today or tomorrow only)
        today = date.today()
        tomorrow = today + timedelta(days=1)
        if isinstance(calloff_date, str):
            calloff_date = date.fromisoformat(calloff_date)
        if calloff_date not in (today, tomorrow):
            raise ValueError('Calloff date must be today or tomorrow')

        # Validate reason
        if reason not in EmployeeCalloff.VALID_REASONS:
            raise ValueError(f'Invalid reason. Must be one of: {", ".join(EmployeeCalloff.VALID_REASONS)}')

        # Check for duplicate
        existing = EmployeeCalloff.query.filter_by(
            employee_id=employee_id,
            calloff_date=calloff_date,
        ).first()
        if existing:
            raise ValueError('A calloff already exists for this date')

        # Create attendance record
        attendance = self._create_attendance_record(employee_id, calloff_date)

        # Create calloff
        calloff = EmployeeCalloff(
            employee_id=employee_id,
            calloff_date=calloff_date,
            reason=reason,
            notes=notes,
            attendance_id=attendance.id if attendance else None,
        )
        self.db.session.add(calloff)
        self.db.session.flush()

        # Get affected events
        affected = self.get_affected_events(employee_id, calloff_date)

        # Send notifications (non-blocking)
        try:
            self._notify_supervisors(calloff, employee, affected)
        except Exception as e:
            logger.warning(f"Supervisor notification failed for calloff {calloff.id}: {e}")

        try:
            self._send_sms(calloff, employee, affected)
        except Exception as e:
            logger.warning(f"SMS notification failed for calloff {calloff.id}: {e}")

        self.db.session.commit()

        return {
            'calloff': calloff.to_dict(),
            'affected_events': affected,
        }

    def _create_attendance_record(self, employee_id, calloff_date):
        """Create or update an EmployeeAttendance record for this calloff."""
        EmployeeAttendance = self.models['EmployeeAttendance']

        existing = EmployeeAttendance.query.filter_by(
            employee_id=employee_id,
            attendance_date=calloff_date,
        ).first()

        if existing:
            existing.status = EmployeeAttendance.STATUS_CALLED_IN
            existing.notes = (existing.notes or '') + ' [Updated by calloff submission]'
            existing.modified_by = 'system:calloff'
            existing.modified_at = datetime.utcnow()
            return existing

        attendance = EmployeeAttendance(
            employee_id=employee_id,
            attendance_date=calloff_date,
            status=EmployeeAttendance.STATUS_CALLED_IN,
            recorded_by='system:calloff',
        )
        self.db.session.add(attendance)
        self.db.session.flush()
        return attendance

    # ── Review ──────────────────────────────────────────────────

    def review_calloff(self, calloff_id, status, supervisor_name, comments=None):
        """
        Mark a calloff as excused or unexcused.
        If excused, updates linked attendance to excused_absence.
        """
        EmployeeCalloff = self.models['EmployeeCalloff']
        EmployeeAttendance = self.models['EmployeeAttendance']

        calloff = EmployeeCalloff.query.get(calloff_id)
        if not calloff:
            raise ValueError('Calloff not found')

        if status not in ('excused', 'unexcused', 'pending'):
            raise ValueError('Status must be "excused", "unexcused", or "pending"')

        if status != 'pending':
            calloff.status = status
        calloff.reviewed_by = supervisor_name
        calloff.reviewed_at = datetime.utcnow()
        if comments:
            calloff.supervisor_comments = comments

        # Update attendance if excused
        if status == 'excused' and calloff.attendance_id:
            attendance = EmployeeAttendance.query.get(calloff.attendance_id)
            if attendance:
                attendance.status = EmployeeAttendance.STATUS_EXCUSED_ABSENCE
                attendance.modified_by = supervisor_name
                attendance.modified_at = datetime.utcnow()

        self.db.session.commit()
        return calloff.to_dict(include_attachments=True)

    # ── Affected Events ─────────────────────────────────────────

    def get_affected_events(self, employee_id, calloff_date):
        """Get scheduled events for an employee on a given date."""
        Schedule = self.models['Schedule']
        Event = self.models['Event']

        if isinstance(calloff_date, str):
            calloff_date = date.fromisoformat(calloff_date)

        day_start = datetime.combine(calloff_date, datetime.min.time())
        day_end = datetime.combine(calloff_date, datetime.max.time())

        schedules = self.db.session.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee_id,
            Schedule.schedule_datetime >= day_start,
            Schedule.schedule_datetime <= day_end,
        ).order_by(Schedule.schedule_datetime).all()

        return [
            {
                'schedule_id': sched.id,
                'event_name': event.project_name,
                'event_type': event.event_type,
                'time': sched.schedule_datetime.strftime('%-I:%M %p'),
                'event_ref_num': event.project_ref_num,
            }
            for sched, event in schedules
        ]

    # ── Pattern Detection ───────────────────────────────────────

    def get_alert_threshold(self):
        """Get calloff alert threshold from SystemSetting, default 3."""
        SystemSetting = self.models.get('SystemSetting')
        if SystemSetting:
            val = SystemSetting.get_setting('calloff_alert_threshold', '3')
            try:
                return int(val)
            except (ValueError, TypeError):
                return 3
        return 3

    def check_patterns(self, employee_id, window_days=30):
        """Check calloff patterns for a single employee within a rolling window."""
        EmployeeCalloff = self.models['EmployeeCalloff']
        cutoff = date.today() - timedelta(days=window_days)

        recent = EmployeeCalloff.query.filter(
            EmployeeCalloff.employee_id == employee_id,
            EmployeeCalloff.calloff_date >= cutoff,
        ).all()

        count = len(recent)
        threshold = self.get_alert_threshold()

        return {
            'count': count,
            'alert': count >= threshold,
            'threshold': threshold,
            'by_day_of_week': dict(Counter(c.calloff_date.strftime('%A') for c in recent)),
            'by_reason': dict(Counter(c.reason for c in recent)),
            'last_calloff': max((c.calloff_date for c in recent), default=None),
        }

    def get_all_patterns(self, window_days=30):
        """Get calloff patterns for all employees who have calloffs in the window."""
        EmployeeCalloff = self.models['EmployeeCalloff']
        Employee = self.models['Employee']
        cutoff = date.today() - timedelta(days=window_days)

        recent = EmployeeCalloff.query.filter(
            EmployeeCalloff.calloff_date >= cutoff,
        ).all()

        # Group by employee
        by_employee = {}
        for c in recent:
            by_employee.setdefault(c.employee_id, []).append(c)

        threshold = self.get_alert_threshold()
        results = []

        for emp_id, calloffs in by_employee.items():
            emp = Employee.query.get(emp_id)
            count = len(calloffs)
            results.append({
                'employee_id': emp_id,
                'name': emp.name if emp else 'Unknown',
                'total_calloffs': count,
                'by_reason': dict(Counter(c.reason for c in calloffs)),
                'by_day_of_week': dict(Counter(c.calloff_date.strftime('%A') for c in calloffs)),
                'last_calloff': max(c.calloff_date for c in calloffs).isoformat(),
                'alert': count >= threshold,
                'alert_reason': f'{count} calloffs in {window_days} days' if count >= threshold else None,
            })

        results.sort(key=lambda r: r['total_calloffs'], reverse=True)

        return {
            'employees': results,
            'threshold': threshold,
            'window_days': window_days,
        }

    # ── Resolve (unschedule affected events) ────────────────────

    def resolve_calloff_events(self, calloff_id, action='unschedule_all', schedule_ids=None):
        """Unschedule events affected by a calloff. Mirrors resolve_time_off_conflicts."""
        EmployeeCalloff = self.models['EmployeeCalloff']
        Schedule = self.models['Schedule']
        Event = self.models['Event']

        calloff = EmployeeCalloff.query.get(calloff_id)
        if not calloff:
            raise ValueError('Calloff not found')

        day_start = datetime.combine(calloff.calloff_date, datetime.min.time())
        day_end = datetime.combine(calloff.calloff_date, datetime.max.time())

        if action == 'unschedule_all':
            conflicting = Schedule.query.filter(
                Schedule.employee_id == calloff.employee_id,
                Schedule.schedule_datetime >= day_start,
                Schedule.schedule_datetime <= day_end,
            ).all()
        elif action == 'unschedule':
            if not schedule_ids:
                raise ValueError('No schedule_ids provided')
            conflicting = Schedule.query.filter(
                Schedule.id.in_(schedule_ids),
                Schedule.employee_id == calloff.employee_id,
            ).all()
        else:
            raise ValueError('action must be "unschedule_all" or "unschedule"')

        if not conflicting:
            return {'unscheduled_count': 0, 'unscheduled_events': []}

        from app.integrations.external_api.session_api_service import session_api as external_api
        from app.services.schedule_change_service import get_schedule_change_service

        unscheduled = []
        svc = get_schedule_change_service()

        for sched in conflicting:
            event = Event.query.filter_by(project_ref_num=sched.event_ref_num).first()

            # Unschedule via Crossmark API
            if sched.external_id:
                try:
                    if external_api.ensure_authenticated():
                        api_result = external_api.unschedule_mplan_event(str(sched.external_id))
                        if not api_result.get('success'):
                            logger.warning(f"Crossmark unschedule failed: {api_result.get('message')}")
                except Exception as e:
                    logger.error(f"Crossmark API error: {e}")

            # Send schedule change notification
            if event and event.event_type != 'Supervisor':
                try:
                    svc.notify_event_removed(
                        employee_id=sched.employee_id,
                        event_type=event.event_type,
                        event_date=sched.schedule_datetime,
                        old_time=sched.schedule_datetime,
                        triggered_by='Supervisor',
                        reason='employee calloff',
                    )
                except Exception as e:
                    logger.warning(f"Schedule change notification failed: {e}")

            # Update event status
            if event:
                event.is_scheduled = False
                event.condition = 'Unstaffed'
                unscheduled.append(event.project_name)

            self.db.session.delete(sched)

        self.db.session.commit()

        return {
            'unscheduled_count': len(unscheduled),
            'unscheduled_events': unscheduled,
        }

    # ── Notifications ───────────────────────────────────────────

    def _notify_supervisors(self, calloff, employee, affected_events):
        """Send push notification to all supervisors about a new calloff."""
        PushSubscription = self.models['PushSubscription']
        Employee = self.models['Employee']

        # Find all supervisors
        supervisors = Employee.query.filter(
            Employee.is_active == True,
            (Employee.is_supervisor == True) | (Employee.job_title == 'Club Supervisor'),
        ).all()

        if not supervisors:
            return

        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        if not vapid_private_key:
            return

        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            return

        vapid_claims = {
            'sub': current_app.config.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@pcevents.com')
        }

        reason_label = calloff.REASON_LABELS.get(calloff.reason, calloff.reason)
        affected_count = len(affected_events)
        body = f"{reason_label} — {calloff.calloff_date.strftime('%a %b %-d')}."
        if affected_count:
            body += f" {affected_count} event{'s' if affected_count != 1 else ''} affected."

        payload = json.dumps({
            'title': f'Calloff: {employee.name}',
            'body': body,
            'url': '/calloffs',
            'tag': f'calloff-{calloff.id}',
        })

        for sup in supervisors:
            subs = PushSubscription.query.filter_by(
                employee_id=sup.id,
                is_active=True,
            ).all()

            for sub in subs:
                try:
                    webpush(
                        subscription_info={
                            'endpoint': sub.endpoint,
                            'keys': {'p256dh': sub.p256dh_key, 'auth': sub.auth_key},
                        },
                        data=payload,
                        vapid_private_key=vapid_private_key,
                        vapid_claims=vapid_claims,
                        timeout=5,
                    )
                    sub.last_used_at = datetime.utcnow()
                except Exception as e:
                    if '410' in str(e) or '404' in str(e):
                        sub.is_active = False
                    logger.warning(f"Push to supervisor {sup.name} failed: {e}")

        calloff.notified_at = datetime.utcnow()

    def _send_sms(self, calloff, employee, affected_events):
        """Send SMS notification to supervisor via Twilio (behind feature flag)."""
        from app.services.sms_service import send_calloff_sms
        send_calloff_sms(
            employee_name=employee.name,
            calloff_date=calloff.calloff_date,
            reason=calloff.REASON_LABELS.get(calloff.reason, calloff.reason),
            affected_count=len(affected_events),
        )


def get_calloff_service():
    """Get a CalloffService instance (for use in request context)."""
    return CalloffService()
