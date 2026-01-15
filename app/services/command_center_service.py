"""
Command Center Service

Aggregates data from multiple sources to provide a unified "morning briefing" view:
- Deadline events (Fri/Sat/EOM approved LIA)
- Unscheduled urgent events
- Pending tasks and notes
- Employee issues (time-off, special notes)
- Quick stats
"""
from datetime import datetime, date, timedelta
from calendar import monthrange
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CommandCenterService:
    """
    Service to aggregate data for the command center dashboard.
    Provides a single view of everything that needs attention.
    """

    def __init__(self, db, models: Dict):
        """
        Initialize with database and models.

        Args:
            db: SQLAlchemy database instance
            models: Dictionary of model classes
        """
        self.db = db
        self.Event = models.get('Event')
        self.Schedule = models.get('Schedule')
        self.Employee = models.get('Employee')
        self.EmployeeTimeOff = models.get('EmployeeTimeOff')
        self.Note = models.get('Note')
        self.RotationAssignment = models.get('RotationAssignment')
        self.Supply = models.get('Supply')

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get all data needed for the command center dashboard.

        Returns:
            Dictionary containing all dashboard sections
        """
        today = date.today()
        now = datetime.now()

        return {
            'generated_at': now.isoformat(),
            'today': today.isoformat(),
            'day_of_week': today.strftime('%A'),
            'is_deadline_day': self._is_deadline_day(today),
            'deadline_info': self._get_deadline_info(today, now),
            'quick_stats': self._get_quick_stats(today),
            'deadline_events': self._get_deadline_events(today),
            'unscheduled_urgent': self._get_unscheduled_urgent(today),
            'pending_tasks': self._get_pending_tasks(today),
            'employee_issues': self._get_employee_issues(today),
            'rotation_info': self._get_rotation_info(today),
            'inventory_alerts': self._get_inventory_alerts(),
        }

    def _is_deadline_day(self, check_date: date) -> bool:
        """Check if date is a deadline day (Fri/Sat/EOM)"""
        is_friday = check_date.weekday() == 4
        is_saturday = check_date.weekday() == 5
        _, last_day = monthrange(check_date.year, check_date.month)
        is_last_day = check_date.day == last_day
        return is_friday or is_saturday or is_last_day

    def _get_deadline_info(self, today: date, now: datetime) -> Dict[str, Any]:
        """Get deadline day information"""
        is_friday = today.weekday() == 4
        is_saturday = today.weekday() == 5
        _, last_day = monthrange(today.year, today.month)
        is_last_day = today.day == last_day

        is_deadline_day = is_friday or is_saturday or is_last_day

        if not is_deadline_day:
            # Find next deadline day
            next_deadline = self._find_next_deadline_day(today)
            return {
                'is_deadline_day': False,
                'next_deadline': next_deadline.isoformat() if next_deadline else None,
                'days_until_deadline': (next_deadline - today).days if next_deadline else None
            }

        # Calculate time until 6 PM
        deadline_time = datetime(now.year, now.month, now.day, 18, 0, 0)
        time_remaining = deadline_time - now

        reasons = []
        if is_friday:
            reasons.append('Friday')
        if is_saturday:
            reasons.append('Saturday')
        if is_last_day:
            reasons.append('End of Month')

        # Determine urgency
        hours_remaining = time_remaining.total_seconds() / 3600
        if hours_remaining <= 0:
            urgency = 'past_deadline'
        elif hours_remaining <= 1:
            urgency = 'urgent'
        elif hours_remaining <= 3:
            urgency = 'warning'
        else:
            urgency = 'normal'

        return {
            'is_deadline_day': True,
            'reason': ' & '.join(reasons),
            'deadline_time': '6:00 PM',
            'hours_remaining': max(0, hours_remaining),
            'urgency': urgency,
            'time_remaining_seconds': max(0, int(time_remaining.total_seconds()))
        }

    def _find_next_deadline_day(self, from_date: date) -> Optional[date]:
        """Find the next deadline day from a given date"""
        check_date = from_date + timedelta(days=1)
        for _ in range(31):  # Check up to a month ahead
            if self._is_deadline_day(check_date):
                return check_date
            check_date += timedelta(days=1)
        return None

    def _get_quick_stats(self, today: date) -> Dict[str, int]:
        """Get quick statistics for the dashboard"""
        stats = {
            'events_today': 0,
            'events_scheduled_today': 0,
            'unscheduled_total': 0,
            'unscheduled_urgent': 0,
            'pending_tasks': 0,
            'overdue_tasks': 0,
            'employees_active': 0,
            'employees_out_today': 0
        }

        if self.Event and self.Schedule:
            # Events scheduled for today
            schedules_today = self.db.session.query(self.Schedule).filter(
                self.db.func.date(self.Schedule.schedule_datetime) == today
            ).count()
            stats['events_scheduled_today'] = schedules_today

            # Events that start today
            events_today = self.db.session.query(self.Event).filter(
                self.db.func.date(self.Event.start_datetime) == today
            ).count()
            stats['events_today'] = events_today

            # Unscheduled events
            unscheduled = self.db.session.query(self.Event).filter(
                self.Event.is_scheduled == False,
                self.Event.condition == 'Unstaffed'
            ).count()
            stats['unscheduled_total'] = unscheduled

            # Urgent unscheduled (due within 3 days)
            urgent_deadline = today + timedelta(days=3)
            urgent = self.db.session.query(self.Event).filter(
                self.Event.is_scheduled == False,
                self.Event.condition == 'Unstaffed',
                self.Event.due_datetime <= datetime.combine(urgent_deadline, datetime.max.time())
            ).count()
            stats['unscheduled_urgent'] = urgent

        if self.Note:
            # Pending tasks
            pending = self.db.session.query(self.Note).filter(
                self.Note.is_completed == False
            ).count()
            stats['pending_tasks'] = pending

            # Overdue tasks
            overdue = self.db.session.query(self.Note).filter(
                self.Note.is_completed == False,
                self.Note.due_date < today
            ).count()
            stats['overdue_tasks'] = overdue

        if self.Employee:
            # Active employees
            active = self.db.session.query(self.Employee).filter(
                self.Employee.is_active == True
            ).count()
            stats['employees_active'] = active

        if self.EmployeeTimeOff:
            # Employees out today
            out_today = self.db.session.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.start_date <= today,
                self.EmployeeTimeOff.end_date >= today
            ).count()
            stats['employees_out_today'] = out_today

        return stats

    def _get_deadline_events(self, today: date) -> List[Dict]:
        """
        Get events that must be handled by today's deadline.
        This queries the approved events service for LIA events needing action.
        """
        # For now, return placeholder - this would integrate with ApprovedEventsService
        # when Walmart session is active
        return []

    def _get_unscheduled_urgent(self, today: date) -> List[Dict]:
        """Get unscheduled events due within 3 days"""
        if not self.Event:
            return []

        urgent_deadline = today + timedelta(days=3)

        events = self.db.session.query(self.Event).filter(
            self.Event.is_scheduled == False,
            self.Event.condition == 'Unstaffed',
            self.Event.due_datetime <= datetime.combine(urgent_deadline, datetime.max.time())
        ).order_by(
            self.Event.due_datetime.asc()
        ).limit(10).all()

        result = []
        for event in events:
            days_until_due = (event.due_datetime.date() - today).days if event.due_datetime else None
            result.append({
                'event_id': event.project_ref_num,
                'name': event.project_name,
                'event_type': event.event_type,
                'due_date': event.due_datetime.date().isoformat() if event.due_datetime else None,
                'days_until_due': days_until_due,
                'urgency': 'urgent' if days_until_due and days_until_due <= 1 else 'warning'
            })

        return result

    def _get_pending_tasks(self, today: date) -> List[Dict]:
        """Get pending tasks, prioritizing due today and overdue"""
        if not self.Note:
            return []

        # Get overdue and due today first, then other pending
        notes = self.db.session.query(self.Note).filter(
            self.Note.is_completed == False
        ).order_by(
            # Overdue first, then due today, then by due date
            self.db.case(
                (self.Note.due_date < today, 0),
                (self.Note.due_date == today, 1),
                else_=2
            ),
            self.Note.due_date.asc().nullslast(),
            self.db.case(
                (self.Note.priority == 'urgent', 0),
                (self.Note.priority == 'high', 1),
                (self.Note.priority == 'normal', 2),
                else_=3
            )
        ).limit(10).all()

        return [n.to_dict() for n in notes]

    def _get_employee_issues(self, today: date) -> Dict[str, List]:
        """Get employee-related issues: time-off, notes"""
        issues = {
            'out_today': [],
            'out_this_week': [],
            'active_notes': []
        }

        if self.EmployeeTimeOff and self.Employee:
            # Employees out today
            out_today = self.db.session.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.start_date <= today,
                self.EmployeeTimeOff.end_date >= today
            ).all()

            for time_off in out_today:
                employee = self.db.session.query(self.Employee).get(time_off.employee_id)
                if employee:
                    issues['out_today'].append({
                        'employee_id': employee.id,
                        'name': employee.name,
                        'start_date': time_off.start_date.isoformat(),
                        'end_date': time_off.end_date.isoformat(),
                        'reason': time_off.reason if hasattr(time_off, 'reason') else None
                    })

            # Employees out this week
            week_end = today + timedelta(days=(6 - today.weekday()))
            out_week = self.db.session.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.start_date <= week_end,
                self.EmployeeTimeOff.end_date >= today,
                ~((self.EmployeeTimeOff.start_date <= today) & (self.EmployeeTimeOff.end_date >= today))
            ).all()

            for time_off in out_week:
                employee = self.db.session.query(self.Employee).get(time_off.employee_id)
                if employee:
                    issues['out_this_week'].append({
                        'employee_id': employee.id,
                        'name': employee.name,
                        'start_date': time_off.start_date.isoformat(),
                        'end_date': time_off.end_date.isoformat()
                    })

        if self.Note:
            # Active employee notes
            employee_notes = self.db.session.query(self.Note).filter(
                self.Note.note_type == 'employee',
                self.Note.is_completed == False
            ).order_by(
                self.Note.due_date.asc().nullslast()
            ).limit(5).all()

            issues['active_notes'] = [n.to_dict() for n in employee_notes]

        return issues

    def _get_rotation_info(self, today: date) -> Dict[str, Any]:
        """Get today's rotation assignments"""
        info = {
            'juicer': None,
            'primary_lead': None
        }

        if not self.RotationAssignment or not self.Employee:
            return info

        # Get Juicer rotation for today
        day_of_week = today.weekday()  # 0=Monday, 6=Sunday

        juicer = self.db.session.query(self.RotationAssignment).filter(
            self.RotationAssignment.rotation_type == 'juicer',
            self.RotationAssignment.day_of_week == day_of_week
        ).first()

        if juicer and juicer.employee_id:
            employee = self.db.session.query(self.Employee).get(juicer.employee_id)
            if employee:
                info['juicer'] = {
                    'employee_id': employee.id,
                    'name': employee.name
                }

        # Get Primary Lead rotation for today
        lead = self.db.session.query(self.RotationAssignment).filter(
            self.RotationAssignment.rotation_type == 'primary_lead',
            self.RotationAssignment.day_of_week == day_of_week
        ).first()

        if lead and lead.employee_id:
            employee = self.db.session.query(self.Employee).get(lead.employee_id)
            if employee:
                info['primary_lead'] = {
                    'employee_id': employee.id,
                    'name': employee.name
                }

        return info

    def _get_inventory_alerts(self) -> Dict[str, Any]:
        """Get inventory alerts for low stock and out of stock items"""
        alerts = {
            'out_of_stock': [],
            'low_stock': [],
            'total_low': 0,
            'total_out': 0
        }

        if not self.Supply:
            return alerts

        # Get out of stock items
        out_of_stock = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.current_quantity <= 0
        ).order_by(self.Supply.name).limit(5).all()

        alerts['out_of_stock'] = [
            {'id': s.id, 'name': s.name, 'unit': s.unit}
            for s in out_of_stock
        ]
        alerts['total_out'] = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.current_quantity <= 0
        ).count()

        # Get low stock items (below reorder threshold but not out)
        low_stock = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.reorder_threshold.isnot(None),
            self.Supply.current_quantity > 0,
            self.Supply.current_quantity <= self.Supply.reorder_threshold
        ).order_by(self.Supply.current_quantity.asc()).limit(5).all()

        alerts['low_stock'] = [
            {
                'id': s.id,
                'name': s.name,
                'current_quantity': s.current_quantity,
                'reorder_threshold': s.reorder_threshold,
                'unit': s.unit
            }
            for s in low_stock
        ]
        alerts['total_low'] = self.db.session.query(self.Supply).filter(
            self.Supply.is_active == True,
            self.Supply.reorder_threshold.isnot(None),
            self.Supply.current_quantity > 0,
            self.Supply.current_quantity <= self.Supply.reorder_threshold
        ).count()

        return alerts
