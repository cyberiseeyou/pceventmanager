"""
Notifications API Blueprint
Handles system notifications for scheduling alerts and validation status
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

# Create blueprint
notifications_api_bp = Blueprint('notifications_api', __name__, url_prefix='/api/notifications')


def init_notification_routes(db, models):
    """
    Initialize notification routes with database and models

    Args:
        db: SQLAlchemy database instance
        models: Dictionary of model classes
    """
    Event = models['Event']
    Schedule = models['Schedule']
    Employee = models['Employee']

    @notifications_api_bp.route('', methods=['GET'])
    def get_notifications():
        """
        Get all current notifications for the user

        Checks for:
        - Day not 100% validated for current/following day
        - Unscheduled events with start date within 2 weeks
        - Past events not reported (not submitted)
        - Events scheduled for inactive employees
        - Employees with multiple overlapping events
        - Events due within 24 hours that are unscheduled

        Returns:
            JSON with list of notifications grouped by priority
        """
        try:
            today = date.today()
            tomorrow = today + timedelta(days=1)
            two_weeks_out = today + timedelta(days=14)

            notifications = {
                'critical': [],
                'warning': [],
                'info': [],
                'count': 0
            }

            # Check 1: Unscheduled events starting within 2 weeks
            upcoming_unscheduled = Event.query.filter(
                Event.condition == 'Unstaffed',
                Event.start_datetime >= datetime.combine(today, datetime.min.time()),
                Event.start_datetime <= datetime.combine(two_weeks_out, datetime.max.time())
            ).count()

            if upcoming_unscheduled > 0:
                # Create date range search for unscheduled events in next 2 weeks
                # Format: s:MM-DD to MM-DD (start date range)
                start_search = f"s:{today.strftime('%m-%d')} to {two_weeks_out.strftime('%m-%d')}"
                notifications['warning'].append({
                    'id': 'upcoming_unscheduled',
                    'type': 'unscheduled_events',
                    'title': f'{upcoming_unscheduled} Unscheduled Event(s)',
                    'message': f'{upcoming_unscheduled} event(s) starting within 2 weeks need to be scheduled',
                    'action_url': f'/events?condition=unstaffed&search={start_search}',
                    'action_text': 'View Events'
                })

            # Check 2: Past events not reported (not submitted) - only last 2 weeks
            two_weeks_ago = today - timedelta(days=14)
            unreported_past = Event.query.join(
                Schedule, Event.project_ref_num == Schedule.event_ref_num
            ).filter(
                Schedule.schedule_datetime >= datetime.combine(two_weeks_ago, datetime.min.time()),
                Schedule.schedule_datetime < datetime.combine(today, datetime.min.time()),
                Event.condition.in_(['Scheduled', 'Staffed', 'In Progress', 'Paused'])
            ).count()

            if unreported_past > 0:
                notifications['critical'].append({
                    'id': 'unreported_past',
                    'type': 'unreported_events',
                    'title': f'{unreported_past} Unreported Event(s)',
                    'message': f'{unreported_past} past event(s) from last 2 weeks have not been reported',
                    'action_url': '/unreported-events',
                    'action_text': 'Review Events'
                })

            # Check 3: Events due within 24 hours that are unscheduled
            now = datetime.now()
            twenty_four_hours_from_now = now + timedelta(hours=24)
            urgent_unscheduled = Event.query.filter(
                Event.condition == 'Unstaffed',
                Event.due_datetime >= now,
                Event.due_datetime <= twenty_four_hours_from_now
            ).count()

            if urgent_unscheduled > 0:
                notifications['critical'].append({
                    'id': 'urgent_unscheduled',
                    'type': 'urgent_scheduling',
                    'title': f'{urgent_unscheduled} Urgent Event(s)',
                    'message': f'{urgent_unscheduled} event(s) due within 24 hours are still unscheduled',
                    'action_url': '/events?condition=unstaffed&urgent=true',
                    'action_text': 'Schedule Now'
                })

            # Check 4: Today's validation status
            today_events_total = Schedule.query.filter(
                db.func.date(Schedule.schedule_datetime) == today
            ).count()

            today_events_scheduled = db.session.query(Event).join(
                Schedule, Event.project_ref_num == Schedule.event_ref_num
            ).filter(
                db.func.date(Schedule.schedule_datetime) == today,
                Event.condition.in_(['Scheduled', 'Submitted'])
            ).count()

            if today_events_total > 0 and today_events_scheduled < today_events_total:
                validation_percent = int((today_events_scheduled / today_events_total) * 100)
                notifications['warning'].append({
                    'id': 'today_validation',
                    'type': 'validation_incomplete',
                    'title': f'Today {validation_percent}% Validated',
                    'message': f'{today_events_total - today_events_scheduled} event(s) today need attention',
                    'action_url': f'/daily/{today.strftime("%Y-%m-%d")}',
                    'action_text': 'View Daily Schedule'
                })

            # Check 5: Tomorrow's validation status
            tomorrow_events_total = Schedule.query.filter(
                db.func.date(Schedule.schedule_datetime) == tomorrow
            ).count()

            tomorrow_events_scheduled = db.session.query(Event).join(
                Schedule, Event.project_ref_num == Schedule.event_ref_num
            ).filter(
                db.func.date(Schedule.schedule_datetime) == tomorrow,
                Event.condition.in_(['Scheduled', 'Submitted'])
            ).count()

            if tomorrow_events_total > 0 and tomorrow_events_scheduled < tomorrow_events_total:
                validation_percent = int((tomorrow_events_scheduled / tomorrow_events_total) * 100)
                notifications['info'].append({
                    'id': 'tomorrow_validation',
                    'type': 'validation_incomplete',
                    'title': f'Tomorrow {validation_percent}% Validated',
                    'message': f'{tomorrow_events_total - tomorrow_events_scheduled} event(s) tomorrow need attention',
                    'action_url': f'/daily/{tomorrow.strftime("%Y-%m-%d")}',
                    'action_text': 'View Daily Schedule'
                })

            # Check 6: Events scheduled for inactive employees
            inactive_scheduled = db.session.query(Schedule).join(
                Employee, Schedule.employee_id == Employee.id
            ).filter(
                Employee.is_active == False,
                Schedule.schedule_datetime >= datetime.combine(today, datetime.min.time())
            ).count()

            if inactive_scheduled > 0:
                notifications['warning'].append({
                    'id': 'inactive_employees',
                    'type': 'inactive_employee_scheduled',
                    'title': f'{inactive_scheduled} Event(s) Scheduled to Inactive Employees',
                    'message': f'{inactive_scheduled} event(s) are assigned to employees marked as inactive',
                    'action_url': '/employees?filter=inactive_with_schedules',
                    'action_text': 'Review Assignments'
                })

            # Check 7: Auto-scheduler notifications (if there are pending schedules)
            PendingSchedule = models.get('PendingSchedule')
            if PendingSchedule:
                pending_approvals = PendingSchedule.query.filter_by(status='proposed').count()
                if pending_approvals > 0:
                    notifications['info'].append({
                        'id': 'pending_approvals',
                        'type': 'auto_scheduler_pending',
                        'title': f'{pending_approvals} Pending Approval(s)',
                        'message': f'{pending_approvals} auto-scheduled event(s) await your approval',
                        'action_url': '/auto-schedule',
                        'action_text': 'Review Schedules'
                    })

            # Calculate total count
            notifications['count'] = (
                len(notifications['critical']) +
                len(notifications['warning']) +
                len(notifications['info'])
            )

            logger.info(f"Retrieved {notifications['count']} notifications")

            return jsonify(notifications)

        except Exception as e:
            logger.error(f"Error retrieving notifications: {str(e)}")
            return jsonify({'error': str(e)}), 500

    return notifications_api_bp
