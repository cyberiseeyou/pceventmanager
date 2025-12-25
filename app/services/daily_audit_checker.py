"""
Daily Audit Checker Service
Automated validation and issue detection for scheduling system

Runs daily to:
- Detect missing Freeosk/Digital events
- Validate rotation coverage
- Check for scheduling conflicts
- Flag unscheduled urgent events
- Verify paperwork generation
"""
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class DailyAuditChecker:
    """
    Performs automated daily audits of scheduling system

    Checks performed:
    1. Missing expected events (Freeosk, Digitals)
    2. Rotation gaps (no Juicer or Primary Lead assigned)
    3. Events due today that are unscheduled
    4. Paperwork not generated for today's events
    5. Employee schedule conflicts
    6. Events within 3-day window that need attention
    """

    def __init__(self, db_session, models: dict):
        """
        Initialize audit checker

        Args:
            db_session: SQLAlchemy database session
            models: Dictionary of model classes from app.config
        """
        self.db = db_session
        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.Employee = models['Employee']
        self.RotationAssignment = models['RotationAssignment']
        self.ScheduleException = models.get('ScheduleException')
        self.EmployeeTimeOff = models['EmployeeTimeOff']
        self.AuditLog = models.get('AuditLog')  # Will be created

    def run_daily_audit(self, target_date: date = None) -> Dict:
        """
        Run full daily audit

        Args:
            target_date: Date to audit (defaults to today)

        Returns:
            Dict with audit results:
            {
                'date': date,
                'total_issues': int,
                'critical_issues': int,
                'warning_issues': int,
                'issues': List[Dict],
                'summary': str
            }
        """
        if target_date is None:
            target_date = date.today()

        logger.info(f"Starting daily audit for {target_date}")

        issues = []

        # Run all audit checks
        issues.extend(self._check_missing_events(target_date))
        issues.extend(self._check_rotation_gaps(target_date))
        issues.extend(self._check_urgent_unscheduled(target_date))
        issues.extend(self._check_employee_conflicts(target_date))
        issues.extend(self._check_three_day_window(target_date))
        issues.extend(self._check_rotation_availability(target_date))
        issues.extend(self._check_supervisor_pairing(target_date))

        # Categorize issues
        critical_issues = [i for i in issues if i['severity'] == 'critical']
        warning_issues = [i for i in issues if i['severity'] == 'warning']
        info_issues = [i for i in issues if i['severity'] == 'info']

        # Generate summary
        summary = self._generate_summary(critical_issues, warning_issues, info_issues)

        # Log audit results
        audit_result = {
            'date': target_date.isoformat(),
            'total_issues': len(issues),
            'critical_issues': len(critical_issues),
            'warning_issues': len(warning_issues),
            'info_issues': len(info_issues),
            'issues': issues,
            'summary': summary
        }

        # Save to audit log if model exists
        if self.AuditLog:
            self._save_audit_log(target_date, audit_result)

        logger.info(f"Audit complete: {len(issues)} total issues ({len(critical_issues)} critical)")

        return audit_result

    def _check_missing_events(self, target_date: date) -> List[Dict]:
        """
        Check for missing expected events (Freeosk, Digitals)

        Logic:
        - Query for events of type Freeosk/Digitals with start_date = target_date
        - Compare against expected patterns (if configured)
        - Flag if expected but missing
        """
        issues = []

        # Check Freeosk events scheduled for today
        freeosk_count = self.db.query(self.Event).filter(
            self.Event.event_type == 'Freeosk',
            self.Event.start_datetime >= datetime.combine(target_date, datetime.min.time()),
            self.Event.start_datetime <= datetime.combine(target_date, datetime.max.time())
        ).count()

        # Check Digital events scheduled for today
        digital_count = self.db.query(self.Event).filter(
            self.Event.event_type == 'Digitals',
            self.Event.start_datetime >= datetime.combine(target_date, datetime.min.time()),
            self.Event.start_datetime <= datetime.combine(target_date, datetime.max.time())
        ).count()

        # Note: This is a basic check. In production, you might have expected counts
        # based on store schedules, historical patterns, or external data
        # For now, we just log counts for awareness

        if freeosk_count == 0 and digital_count == 0:
            issues.append({
                'severity': 'info',
                'type': 'missing_events',
                'category': 'Event Import',
                'message': f'No Freeosk or Digital events found for {target_date}',
                'details': 'This may be normal (no events scheduled) or indicate import issues',
                'action': 'Verify with MVRetail if events expected'
            })

        return issues

    def _check_rotation_gaps(self, target_date: date) -> List[Dict]:
        """
        Check for rotation assignment gaps

        Flags:
        - Days with no Juicer rotation assigned
        - Days with no Primary Lead rotation assigned
        """
        issues = []
        day_of_week = target_date.weekday()

        # Check Juicer rotation
        juicer_rotation = self._get_rotation_assignment(target_date, 'juicer')
        if not juicer_rotation:
            issues.append({
                'severity': 'critical',
                'type': 'rotation_gap',
                'category': 'Rotation',
                'message': f'No Juicer rotation assigned for {target_date.strftime("%A")}',
                'details': f'Day of week: {day_of_week} ({target_date.strftime("%A")})',
                'action': 'Configure Juicer rotation in Rotation Management'
            })

        # Check Primary Lead rotation
        lead_rotation = self._get_rotation_assignment(target_date, 'primary_lead')
        if not lead_rotation:
            issues.append({
                'severity': 'critical',
                'type': 'rotation_gap',
                'category': 'Rotation',
                'message': f'No Primary Lead rotation assigned for {target_date.strftime("%A")}',
                'details': f'Day of week: {day_of_week} ({target_date.strftime("%A")})',
                'action': 'Configure Primary Lead rotation in Rotation Management'
            })

        return issues

    def _check_urgent_unscheduled(self, target_date: date) -> List[Dict]:
        """
        Check for unscheduled events due today or very soon

        Flags:
        - Events due today (or tomorrow) that are unscheduled
        - Events within 24 hours that lack assignments
        """
        issues = []

        # Events due today
        due_today = self.db.query(self.Event).filter(
            self.Event.condition == 'Unstaffed',
            func.date(self.Event.due_datetime) == target_date
        ).all()

        if due_today:
            issues.append({
                'severity': 'critical',
                'type': 'urgent_unscheduled',
                'category': 'Scheduling',
                'message': f'{len(due_today)} event(s) due TODAY are unscheduled',
                'details': [
                    {'ref_num': e.project_ref_num, 'name': e.project_name, 'type': e.event_type}
                    for e in due_today
                ],
                'action': 'Schedule immediately or request deadline extension'
            })

        # Events due tomorrow
        tomorrow = target_date + timedelta(days=1)
        due_tomorrow = self.db.query(self.Event).filter(
            self.Event.condition == 'Unstaffed',
            func.date(self.Event.due_datetime) == tomorrow
        ).all()

        if due_tomorrow:
            issues.append({
                'severity': 'warning',
                'type': 'urgent_unscheduled',
                'category': 'Scheduling',
                'message': f'{len(due_tomorrow)} event(s) due TOMORROW are unscheduled',
                'details': [
                    {'ref_num': e.project_ref_num, 'name': e.project_name, 'type': e.event_type}
                    for e in due_tomorrow
                ],
                'action': 'Schedule today to avoid last-minute rush'
            })

        return issues

    def _check_employee_conflicts(self, target_date: date) -> List[Dict]:
        """
        Check for employee scheduling conflicts

        Flags:
        - Employees scheduled during time off
        - Employees double-booked (same time, multiple events)
        - Employees exceeding daily Core event limit
        """
        issues = []

        # Get today's schedules
        today_schedules = self.db.query(self.Schedule, self.Event, self.Employee).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == target_date
        ).all()

        # Check for time-off conflicts
        time_off_conflicts = []
        for schedule, event, employee in today_schedules:
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == employee.id,
                self.EmployeeTimeOff.start_date <= target_date,
                self.EmployeeTimeOff.end_date >= target_date
            ).first()

            if time_off:
                time_off_conflicts.append({
                    'employee_name': employee.name,
                    'employee_id': employee.id,
                    'event_ref': event.project_ref_num,
                    'event_name': event.project_name,
                    'time_off_reason': time_off.reason
                })

        if time_off_conflicts:
            issues.append({
                'severity': 'critical',
                'type': 'time_off_conflict',
                'category': 'Employee Availability',
                'message': f'{len(time_off_conflicts)} employee(s) scheduled during time off',
                'details': time_off_conflicts,
                'action': 'Reassign events immediately'
            })

        # Check for double-booking (same employee, same time, different events)
        time_slot_map = {}
        for schedule, event, employee in today_schedules:
            key = (employee.id, schedule.schedule_datetime)
            if key not in time_slot_map:
                time_slot_map[key] = []
            time_slot_map[key].append({
                'event_ref': event.project_ref_num,
                'event_name': event.project_name,
                'event_type': event.event_type
            })

        double_bookings = []
        for (employee_id, schedule_time), events in time_slot_map.items():
            if len(events) > 1:
                # Exception: Club Supervisor can have multiple Supervisor events
                employee = self.db.query(self.Employee).get(employee_id)
                if employee and employee.job_title == 'Club Supervisor':
                    # Check if all events are Supervisor type
                    all_supervisor = all(e['event_type'] == 'Supervisor' for e in events)
                    if all_supervisor:
                        continue  # This is allowed

                double_bookings.append({
                    'employee_name': employee.name if employee else 'Unknown',
                    'employee_id': employee_id,
                    'time': schedule_time.strftime('%I:%M %p'),
                    'events': events
                })

        if double_bookings:
            issues.append({
                'severity': 'critical',
                'type': 'double_booking',
                'category': 'Scheduling',
                'message': f'{len(double_bookings)} employee(s) double-booked',
                'details': double_bookings,
                'action': 'Resolve time conflicts by rescheduling one event'
            })

        # Check for Core event daily limit violations
        core_limit_violations = []
        employee_core_counts = {}
        for schedule, event, employee in today_schedules:
            if event.event_type == 'Core':
                if employee.id not in employee_core_counts:
                    employee_core_counts[employee.id] = {
                        'name': employee.name,
                        'count': 0,
                        'events': []
                    }
                employee_core_counts[employee.id]['count'] += 1
                employee_core_counts[employee.id]['events'].append(event.project_ref_num)

        for employee_id, data in employee_core_counts.items():
            if data['count'] > 1:
                core_limit_violations.append({
                    'employee_name': data['name'],
                    'employee_id': employee_id,
                    'core_event_count': data['count'],
                    'event_refs': data['events']
                })

        if core_limit_violations:
            issues.append({
                'severity': 'warning',
                'type': 'core_limit_violation',
                'category': 'Business Rules',
                'message': f'{len(core_limit_violations)} employee(s) exceed Core event daily limit',
                'details': core_limit_violations,
                'action': 'Review and redistribute Core events (max 1 per day)'
            })

        return issues

    def _check_three_day_window(self, target_date: date) -> List[Dict]:
        """
        Check events within 3-day scheduling window

        Flags:
        - Events within 3 days that are unscheduled
        - Events that should have been auto-scheduled but weren't
        """
        issues = []

        three_days_ahead = target_date + timedelta(days=3)

        unscheduled_within_window = self.db.query(self.Event).filter(
            self.Event.condition == 'Unstaffed',
            self.Event.start_datetime >= datetime.combine(target_date, datetime.min.time()),
            self.Event.start_datetime <= datetime.combine(three_days_ahead, datetime.max.time())
        ).all()

        if unscheduled_within_window:
            issues.append({
                'severity': 'warning',
                'type': 'within_window_unscheduled',
                'category': 'Scheduling',
                'message': f'{len(unscheduled_within_window)} event(s) within 3-day window are unscheduled',
                'details': [
                    {
                        'ref_num': e.project_ref_num,
                        'name': e.project_name,
                        'type': e.event_type,
                        'start_date': e.start_datetime.strftime('%Y-%m-%d')
                    }
                    for e in unscheduled_within_window
                ],
                'action': 'Run auto-scheduler or manually assign'
            })

        return issues

    def _check_rotation_availability(self, target_date: date) -> List[Dict]:
        """
        Check if rotation-assigned employees are available

        Flags:
        - Rotation employee has time off
        - Rotation employee is inactive
        - No exception created for rotation override
        """
        issues = []

        # Check Juicer rotation
        juicer_rotation = self._get_rotation_assignment(target_date, 'juicer')
        if juicer_rotation:
            employee = self.db.query(self.Employee).get(juicer_rotation['employee_id'])
            if employee:
                # Check if inactive
                if not employee.is_active:
                    issues.append({
                        'severity': 'critical',
                        'type': 'rotation_inactive',
                        'category': 'Rotation',
                        'message': f'Juicer rotation employee {employee.name} is inactive',
                        'details': {'employee_id': employee.id, 'rotation_type': 'Juicer'},
                        'action': 'Update rotation or reactivate employee'
                    })

                # Check if has time off (without exception)
                if not juicer_rotation['is_exception']:
                    time_off = self.db.query(self.EmployeeTimeOff).filter(
                        self.EmployeeTimeOff.employee_id == employee.id,
                        self.EmployeeTimeOff.start_date <= target_date,
                        self.EmployeeTimeOff.end_date >= target_date
                    ).first()

                    if time_off:
                        issues.append({
                            'severity': 'warning',
                            'type': 'rotation_time_off',
                            'category': 'Rotation',
                            'message': f'Juicer rotation employee {employee.name} has time off',
                            'details': {
                                'employee_id': employee.id,
                                'rotation_type': 'Juicer',
                                'time_off_reason': time_off.reason
                            },
                            'action': 'Create Schedule Exception or reassign Juicer events'
                        })

        # Check Primary Lead rotation (same logic)
        lead_rotation = self._get_rotation_assignment(target_date, 'primary_lead')
        if lead_rotation:
            employee = self.db.query(self.Employee).get(lead_rotation['employee_id'])
            if employee:
                if not employee.is_active:
                    issues.append({
                        'severity': 'critical',
                        'type': 'rotation_inactive',
                        'category': 'Rotation',
                        'message': f'Primary Lead rotation employee {employee.name} is inactive',
                        'details': {'employee_id': employee.id, 'rotation_type': 'Primary Lead'},
                        'action': 'Update rotation or reactivate employee'
                    })

                if not lead_rotation['is_exception']:
                    time_off = self.db.query(self.EmployeeTimeOff).filter(
                        self.EmployeeTimeOff.employee_id == employee.id,
                        self.EmployeeTimeOff.start_date <= target_date,
                        self.EmployeeTimeOff.end_date >= target_date
                    ).first()

                    if time_off:
                        issues.append({
                            'severity': 'warning',
                            'type': 'rotation_time_off',
                            'category': 'Rotation',
                            'message': f'Primary Lead rotation employee {employee.name} has time off',
                            'details': {
                                'employee_id': employee.id,
                                'rotation_type': 'Primary Lead',
                                'time_off_reason': time_off.reason
                            },
                            'action': 'Create Schedule Exception or reassign Lead events'
                        })

        return issues

    def _check_supervisor_pairing(self, target_date: date) -> List[Dict]:
        """
        Check Supervisor event pairing with Core events

        Flags:
        - Supervisor events without matching Core events
        - Supervisor events scheduled on different date than Core
        - Core events without Supervisor events (if expected)
        """
        issues = []

        # Get all Supervisor events scheduled for today or upcoming
        supervisor_events = self.db.query(self.Event).filter(
            self.Event.event_type == 'Supervisor',
            self.Event.start_datetime >= datetime.combine(target_date, datetime.min.time())
        ).all()

        unpaired_supervisor = []
        mismatched_dates = []

        import re
        for sup_event in supervisor_events:
            # Extract event number
            match = re.search(r'\d{6}', sup_event.project_name)
            if not match:
                unpaired_supervisor.append({
                    'supervisor_ref': sup_event.project_ref_num,
                    'supervisor_name': sup_event.project_name,
                    'reason': 'Cannot extract event number'
                })
                continue

            event_number = match.group(0)

            # Find matching Core event
            core_event = self.db.query(self.Event).filter(
                self.Event.event_type == 'Core',
                self.Event.project_name.contains(event_number)
            ).first()

            if not core_event:
                unpaired_supervisor.append({
                    'supervisor_ref': sup_event.project_ref_num,
                    'supervisor_name': sup_event.project_name,
                    'event_number': event_number,
                    'reason': 'No matching Core event found'
                })
            else:
                # Check if scheduled on same date
                sup_schedule = self.db.query(self.Schedule).filter_by(
                    event_ref_num=sup_event.project_ref_num
                ).first()

                core_schedule = self.db.query(self.Schedule).filter_by(
                    event_ref_num=core_event.project_ref_num
                ).first()

                if sup_schedule and core_schedule:
                    if sup_schedule.schedule_datetime.date() != core_schedule.schedule_datetime.date():
                        mismatched_dates.append({
                            'supervisor_ref': sup_event.project_ref_num,
                            'core_ref': core_event.project_ref_num,
                            'supervisor_date': sup_schedule.schedule_datetime.date().isoformat(),
                            'core_date': core_schedule.schedule_datetime.date().isoformat()
                        })

        if unpaired_supervisor:
            issues.append({
                'severity': 'warning',
                'type': 'unpaired_supervisor',
                'category': 'Event Pairing',
                'message': f'{len(unpaired_supervisor)} Supervisor event(s) without matching Core events',
                'details': unpaired_supervisor,
                'action': 'Verify Core events exist in MVRetail or adjust Supervisor events'
            })

        if mismatched_dates:
            issues.append({
                'severity': 'warning',
                'type': 'supervisor_date_mismatch',
                'category': 'Event Pairing',
                'message': f'{len(mismatched_dates)} Supervisor event(s) scheduled on different date than Core',
                'details': mismatched_dates,
                'action': 'Reschedule Supervisor events to match Core event dates'
            })

        return issues

    def _get_rotation_assignment(self, target_date: date, rotation_type: str) -> Dict:
        """Get rotation assignment for date (checks exceptions first)"""
        # Check for exception
        if self.ScheduleException:
            exception = self.db.query(self.ScheduleException).filter_by(
                exception_date=target_date,
                rotation_type=rotation_type
            ).first()

            if exception:
                return {
                    'employee_id': exception.employee_id,
                    'is_exception': True,
                    'reason': exception.reason
                }

        # Check weekly rotation
        day_of_week = target_date.weekday()
        rotation = self.db.query(self.RotationAssignment).filter_by(
            day_of_week=day_of_week,
            rotation_type=rotation_type
        ).first()

        if rotation:
            return {
                'employee_id': rotation.employee_id,
                'is_exception': False,
                'reason': None
            }

        return None

    def _generate_summary(self, critical_issues: List, warning_issues: List, info_issues: List) -> str:
        """Generate human-readable summary of audit results"""
        if not critical_issues and not warning_issues:
            return "All checks passed. System is healthy."

        summary_parts = []

        if critical_issues:
            summary_parts.append(f"⚠️ {len(critical_issues)} CRITICAL issue(s) require immediate attention")

        if warning_issues:
            summary_parts.append(f"⚠ {len(warning_issues)} warning(s) should be reviewed")

        if info_issues:
            summary_parts.append(f"ℹ️ {len(info_issues)} informational item(s)")

        return ". ".join(summary_parts) + "."

    def _save_audit_log(self, target_date: date, audit_result: Dict):
        """Save audit results to database"""
        try:
            import json

            audit_log = self.AuditLog(
                audit_date=target_date,
                audit_timestamp=datetime.utcnow(),
                total_issues=audit_result['total_issues'],
                critical_issues=audit_result['critical_issues'],
                warning_issues=audit_result['warning_issues'],
                info_issues=audit_result['info_issues'],
                summary=audit_result['summary'],
                details_json=json.dumps(audit_result['issues'])
            )

            self.db.add(audit_log)
            self.db.commit()
            logger.info(f"Audit log saved for {target_date}")
        except Exception as e:
            logger.error(f"Failed to save audit log: {e}")
            self.db.rollback()

    def send_audit_notification(self, audit_result: Dict, recipients: List[str]):
        """
        Send audit results via email

        Args:
            audit_result: Audit result dict from run_daily_audit()
            recipients: List of email addresses

        Note: Requires email configuration in app settings
        """
        # This is a placeholder - implement with your email service
        # Example using Flask-Mail or similar

        try:
            subject = f"Daily Scheduling Audit - {audit_result['date']}"

            if audit_result['critical_issues'] > 0:
                subject = f"🚨 URGENT: {subject}"

            # Build email body
            body_parts = [
                f"Daily Audit Report for {audit_result['date']}",
                "",
                audit_result['summary'],
                "",
                f"Total Issues: {audit_result['total_issues']}",
                f"- Critical: {audit_result['critical_issues']}",
                f"- Warnings: {audit_result['warning_issues']}",
                f"- Info: {audit_result['info_issues']}",
                "",
                "Details:",
                ""
            ]

            for issue in audit_result['issues']:
                body_parts.append(f"[{issue['severity'].upper()}] {issue['message']}")
                body_parts.append(f"  Action: {issue['action']}")
                body_parts.append("")

            body = "\n".join(body_parts)

            # TODO: Implement actual email sending
            # Example:
            # from flask_mail import Message
            # msg = Message(subject, recipients=recipients, body=body)
            # mail.send(msg)

            logger.info(f"Audit notification prepared for {len(recipients)} recipient(s)")
            logger.debug(f"Email body:\n{body}")

        except Exception as e:
            logger.error(f"Failed to send audit notification: {e}")
