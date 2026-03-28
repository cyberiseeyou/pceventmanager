"""
SMS Service

Sends SMS notifications via Twilio. Behind SMS_NOTIFICATIONS_ENABLED feature flag.
Fails silently — SMS failure should never block application logic.
"""
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def send_calloff_sms(employee_name, calloff_date, reason, affected_count):
    """
    Send an SMS to the configured supervisor number about an employee calloff.

    Args:
        employee_name: Name of the employee who called off
        calloff_date: Date of the calloff
        reason: Human-readable reason label
        affected_count: Number of affected scheduled events
    """
    if not current_app.config.get('SMS_NOTIFICATIONS_ENABLED', False):
        return

    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_number = current_app.config.get('TWILIO_FROM_NUMBER')
    to_number = current_app.config.get('SUPERVISOR_SMS_NUMBER')

    if not all([account_sid, auth_token, from_number, to_number]):
        logger.warning("SMS enabled but Twilio credentials incomplete, skipping")
        return

    date_str = calloff_date.strftime('%a %b %-d') if hasattr(calloff_date, 'strftime') else str(calloff_date)
    body = f"{employee_name} called off for {date_str} ({reason})."
    if affected_count:
        body += f" {affected_count} event{'s' if affected_count != 1 else ''} affected."

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(
            body=body,
            from_=from_number,
            to=to_number,
        )
        logger.info(f"SMS sent to {to_number}: calloff for {employee_name}")
    except ImportError:
        logger.warning("twilio package not installed, skipping SMS")
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
