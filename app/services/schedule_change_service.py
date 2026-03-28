"""
Schedule Change Notification Service

Central service for creating schedule change notifications and sending Web Push.
Called from schedule CRUD endpoints when a change affects an employee's schedule
within 7 days of today.
"""
import json
import logging
from datetime import date, datetime

from flask import current_app

logger = logging.getLogger(__name__)


class ScheduleChangeService:
    """Creates schedule change notification records and fires Web Push."""

    def __init__(self, db, models):
        self.db = db
        self.models = models

    def _is_within_7_days(self, event_date):
        """Check if event_date is within 7 days from today (inclusive)."""
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        today = date.today()
        days_until = (event_date - today).days
        return days_until <= 7

    def _should_notify_employee(self, employee_id):
        """Only notify specialist and lead roles, not supervisors."""
        Employee = self.models['Employee']
        emp = Employee.query.get(employee_id)
        if not emp:
            return False
        return emp.role in ('specialist', 'lead')

    def _format_time(self, dt):
        """Format datetime to '10:15 AM' style."""
        if isinstance(dt, datetime):
            return dt.strftime('%-I:%M %p')
        return str(dt)

    def _format_date(self, d):
        """Format date to 'Mon Mar 25' style."""
        if isinstance(d, datetime):
            d = d.date()
        return d.strftime('%a %b %-d')

    def _append_reason(self, description, reason):
        """Append optional reason to description text."""
        if reason:
            return f"{description} — {reason}"
        return description

    def notify_event_added(self, employee_id, event_type, schedule_datetime,
                           triggered_by=None, reason=None):
        """Notify employee that a new event was assigned to them."""
        event_date = schedule_datetime.date() if isinstance(schedule_datetime, datetime) else schedule_datetime
        if not self._is_within_7_days(event_date) or not self._should_notify_employee(employee_id):
            return None

        description = (
            f"You were assigned a {event_type} event on "
            f"{self._format_date(event_date)} at {self._format_time(schedule_datetime)}"
        )
        description = self._append_reason(description, reason)
        details = {'scheduled_time': schedule_datetime.isoformat()}
        if reason:
            details['reason'] = reason
        return self._create_and_push(
            employee_id=employee_id,
            change_type='event_added',
            event_type=event_type,
            event_date=event_date,
            description=description,
            change_details=json.dumps(details),
            triggered_by=triggered_by
        )

    def notify_event_removed(self, employee_id, event_type, event_date,
                             old_time, triggered_by=None, reason=None):
        """Notify employee that an event was removed from their schedule."""
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        if not self._is_within_7_days(event_date) or not self._should_notify_employee(employee_id):
            return None

        description = (
            f"Your {event_type} event on {self._format_date(event_date)} "
            f"at {self._format_time(old_time)} was removed from your schedule"
        )
        description = self._append_reason(description, reason)
        details = {
            'removed_time': old_time.isoformat() if isinstance(old_time, datetime) else str(old_time),
        }
        if reason:
            details['reason'] = reason
        return self._create_and_push(
            employee_id=employee_id,
            change_type='event_removed',
            event_type=event_type,
            event_date=event_date,
            description=description,
            change_details=json.dumps(details),
            triggered_by=triggered_by
        )

    def notify_time_changed(self, employee_id, event_type, event_date,
                            old_datetime, new_datetime, triggered_by=None,
                            reason=None):
        """Notify employee that their event time was changed."""
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        if not self._is_within_7_days(event_date) or not self._should_notify_employee(employee_id):
            return None

        description = (
            f"Your {event_type} event on {self._format_date(event_date)} "
            f"was moved from {self._format_time(old_datetime)} to {self._format_time(new_datetime)}"
        )
        description = self._append_reason(description, reason)
        details = {
            'old_time': old_datetime.isoformat() if isinstance(old_datetime, datetime) else str(old_datetime),
            'new_time': new_datetime.isoformat() if isinstance(new_datetime, datetime) else str(new_datetime),
        }
        if reason:
            details['reason'] = reason
        return self._create_and_push(
            employee_id=employee_id,
            change_type='time_changed',
            event_type=event_type,
            event_date=event_date,
            description=description,
            change_details=json.dumps(details),
            triggered_by=triggered_by
        )

    def notify_employee_swapped_in(self, new_employee_id, event_type,
                                   schedule_datetime, old_employee_name,
                                   triggered_by=None, reason=None):
        """Notify employee that they were assigned an event (replacing someone)."""
        event_date = schedule_datetime.date() if isinstance(schedule_datetime, datetime) else schedule_datetime
        if not self._is_within_7_days(event_date) or not self._should_notify_employee(new_employee_id):
            return None

        description = (
            f"You were assigned a {event_type} event on "
            f"{self._format_date(event_date)} at {self._format_time(schedule_datetime)} "
            f"(previously assigned to {old_employee_name})"
        )
        description = self._append_reason(description, reason)
        details = {
            'scheduled_time': schedule_datetime.isoformat(),
            'previous_employee': old_employee_name,
        }
        if reason:
            details['reason'] = reason
        return self._create_and_push(
            employee_id=new_employee_id,
            change_type='employee_swapped_in',
            event_type=event_type,
            event_date=event_date,
            description=description,
            change_details=json.dumps(details),
            triggered_by=triggered_by
        )

    def notify_employee_swapped_out(self, old_employee_id, event_type,
                                    event_date, old_time, new_employee_name,
                                    triggered_by=None, reason=None):
        """Notify employee that their event was reassigned to someone else."""
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        if not self._is_within_7_days(event_date) or not self._should_notify_employee(old_employee_id):
            return None

        description = (
            f"Your {event_type} event on {self._format_date(event_date)} "
            f"at {self._format_time(old_time)} was reassigned to {new_employee_name}"
        )
        description = self._append_reason(description, reason)
        details = {
            'removed_time': old_time.isoformat() if isinstance(old_time, datetime) else str(old_time),
            'replacement_employee': new_employee_name,
        }
        if reason:
            details['reason'] = reason
        return self._create_and_push(
            employee_id=old_employee_id,
            change_type='employee_swapped_out',
            event_type=event_type,
            event_date=event_date,
            description=description,
            change_details=json.dumps(details),
            triggered_by=triggered_by
        )

    def notify_event_traded(self, employee_id, old_event_type, old_event_date,
                            old_time, new_event_type, new_event_date, new_time,
                            trade_partner_name, triggered_by=None):
        """Notify employee that their event was traded with another employee."""
        if isinstance(old_event_date, datetime):
            old_event_date = old_event_date.date()
        if isinstance(new_event_date, datetime):
            new_event_date = new_event_date.date()
        if not self._is_within_7_days(old_event_date) or not self._should_notify_employee(employee_id):
            return None

        description = (
            f"Your {old_event_type} event on {self._format_date(old_event_date)} "
            f"at {self._format_time(old_time)} was traded with {trade_partner_name} "
            f"— you now have their {new_event_type} event on "
            f"{self._format_date(new_event_date)} at {self._format_time(new_time)}"
        )
        return self._create_and_push(
            employee_id=employee_id,
            change_type='event_traded',
            event_type=old_event_type,
            event_date=old_event_date,
            description=description,
            change_details=json.dumps({
                'old_time': old_time.isoformat() if isinstance(old_time, datetime) else str(old_time),
                'new_event_type': new_event_type,
                'new_event_date': new_event_date.isoformat(),
                'new_time': new_time.isoformat() if isinstance(new_time, datetime) else str(new_time),
                'trade_partner': trade_partner_name,
            }),
            triggered_by=triggered_by
        )

    def _create_and_push(self, employee_id, change_type, event_type, event_date,
                         description, change_details, triggered_by):
        """Create DB record and send web push notification."""
        SCN = self.models['ScheduleChangeNotification']
        notif = SCN(
            employee_id=employee_id,
            change_type=change_type,
            event_type=event_type,
            event_date=event_date,
            description=description,
            change_details=change_details,
            triggered_by=triggered_by,
        )
        self.db.session.add(notif)
        self.db.session.flush()  # Get ID before push attempt

        # Fire web push (non-blocking, swallow errors)
        try:
            self._send_push(notif)
        except Exception as e:
            logger.warning(f"Push delivery failed for notification {notif.id}: {e}")

        return notif

    def _send_push(self, notification):
        """Send web push to all active subscriptions for this employee."""
        PushSubscription = self.models['PushSubscription']
        subs = PushSubscription.query.filter_by(
            employee_id=notification.employee_id,
            is_active=True,
        ).all()

        if not subs:
            return

        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        if not vapid_private_key:
            logger.debug("VAPID_PRIVATE_KEY not configured, skipping push delivery")
            return

        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            logger.debug("pywebpush not installed, skipping push delivery")
            return

        vapid_claims = {
            'sub': current_app.config.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@pcevents.com')
        }

        payload = json.dumps({
            'title': 'Schedule Change',
            'body': notification.description,
            'url': '/my-notifications',
            'tag': f'schedule-change-{notification.id}',
        })

        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {
                            'p256dh': sub.p256dh_key,
                            'auth': sub.auth_key,
                        }
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                    timeout=5,
                )
                sub.last_used_at = datetime.utcnow()
                notification.push_sent = True
                notification.push_sent_at = datetime.utcnow()
            except WebPushException as e:
                if '410' in str(e) or '404' in str(e):
                    sub.is_active = False
                logger.warning(f"Push failed for subscription {sub.id}: {e}")
            except Exception as e:
                logger.warning(f"Push error for subscription {sub.id}: {e}")


def get_schedule_change_service():
    """Get service instance using model factory pattern."""
    from app.models import get_models, get_db
    models = get_models()
    db = get_db()
    return ScheduleChangeService(db, models)
