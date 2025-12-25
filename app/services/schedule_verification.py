"""
Schedule Verification Service

Comprehensive schedule validation supporting both:
1. Daily verification (single date) - 8 validation rules for daily checks
2. Date range verification (multi-day) - Pre/post-approval validation

Daily Mode: Verifies daily schedules for issues before the day starts
Range Mode: Validates completeness and correctness for date ranges

This service performs comprehensive validation of schedules to catch:
- Critical data integrity issues (blocks approval)
- Warning conditions (allows approval with confirmation)
- Informational messages (FYI only)
"""
from datetime import datetime, date, timedelta, time
from sqlalchemy import func, and_, or_
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import Counter
from app.utils.db_compat import extract_time
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class VerificationIssue:
    """Represents a single verification issue found in the schedule"""
    severity: str  # 'critical', 'warning', 'info'
    rule_name: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'severity': self.severity,
            'rule_name': self.rule_name,
            'message': self.message,
            'details': self.details
        }


@dataclass
class VerificationResult:
    """Results of schedule verification"""
    status: str  # 'pass', 'warning', 'fail'
    issues: List[VerificationIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'status': self.status,
            'issues': [issue.to_dict() for issue in self.issues],
            'summary': self.summary
        }


class ScheduleVerificationService:
    """
    Comprehensive schedule verification for both daily and date range validation

    Daily Mode (verify_schedule):
        - Implements 8 validation rules for a single date
        - Used for proactive daily schedule checks
        - Verifies committed schedules only

    Range Mode (verify_date_range):
        - Validates schedules across multiple days
        - Supports pre-approval (includes pending) and post-approval modes
        - Checks data integrity, conflicts, and coverage

    Both modes provide critical/warning/info categorization for issues.
    """

    MAX_WORK_DAYS_PER_WEEK = 6

    @classmethod
    def _get_core_timeslots(cls):
        """Get Core event time slots from database settings"""
        from app.services.event_time_settings import get_core_slots

        try:
            slots = get_core_slots()
            # Convert to HH:MM:SS format for comparison
            return [f"{slot['start'].hour:02d}:{slot['start'].minute:02d}:00" for slot in slots]
        except Exception:
            # Fallback to hard-coded defaults
            return ['09:45:00', '10:30:00', '11:00:00', '11:30:00']

    @classmethod
    def _get_supervisor_time(cls):
        """Get Supervisor event time from database settings"""
        from app.services.event_time_settings import get_supervisor_times

        try:
            times = get_supervisor_times()
            # Convert to HH:MM:SS format for comparison
            return f"{times['start'].hour:02d}:{times['start'].minute:02d}:00"
        except Exception:
            # Fallback to hard-coded default
            return '12:00:00'

    def __init__(self, db_session, models: dict):
        """
        Initialize verification service

        Args:
            db_session: SQLAlchemy session for database queries
            models: Dict of model classes (Event, Schedule, PendingSchedule, etc.)
        """
        self.db = db_session
        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.PendingSchedule = models.get('PendingSchedule')
        self.Employee = models['Employee']
        self.EmployeeTimeOff = models['EmployeeTimeOff']
        self.EmployeeAvailability = models.get('EmployeeAvailability')
        self.EmployeeWeeklyAvailability = models.get('EmployeeWeeklyAvailability')
        self.EmployeeAttendance = models.get('EmployeeAttendance')
        self.RotationAssignment = models.get('RotationAssignment')
        self.ScheduleException = models.get('ScheduleException')

        # Load time settings from database
        self.CORE_TIMESLOTS = self._get_core_timeslots()
        self.SUPERVISOR_TIME = self._get_supervisor_time()

    # ============================================================================
    # DAILY VERIFICATION (Single Date) - 8 Validation Rules
    # ============================================================================

    def verify_schedule(self, verify_date: date) -> VerificationResult:
        """
        Run all verification rules for a specific date (Daily Mode)

        Validation rules:
        1. One Core per employee max
        2. Employee availability check (weekly pattern)
        3. Employee time-off check
        4. Core event times are correct and balanced
        5. Each Core has supervisor event paired correctly
        6. Freeosk scheduled to correct person at correct time
        7. Digitals scheduled to correct person at correct time
        8. Events due tomorrow are scheduled
        9. Juicer scheduled to rotation Juicer for the day
        10. Juicer employee not also scheduled for Core

        Args:
            verify_date: Date to verify (datetime.date object)

        Returns:
            VerificationResult with all issues found
        """
        issues = []

        # Run all verification rules
        issues.extend(self._check_core_event_limit(verify_date))  # Rule 1
        issues.extend(self._check_employee_availability_only(verify_date))  # Rules 2 & 3
        issues.extend(self._check_core_times_and_balance(verify_date))  # Rule 4
        issues.extend(self._check_core_supervisor_pairing(verify_date))  # Rule 5
        issues.extend(self._check_freeosk_scheduling(verify_date))  # Rule 6
        issues.extend(self._check_digitals_scheduling(verify_date))  # Rule 7
        issues.extend(self._check_events_due_tomorrow(verify_date))  # Rule 8
        issues.extend(self._check_juicer_rotation(verify_date))  # Rules 9 & 10

        # Determine overall status
        critical_count = sum(1 for issue in issues if issue.severity == 'critical')
        warning_count = sum(1 for issue in issues if issue.severity == 'warning')

        if critical_count > 0:
            status = 'fail'
        elif warning_count > 0:
            status = 'warning'
        else:
            status = 'pass'

        # Build summary
        summary = {
            'date': verify_date.isoformat(),
            'total_issues': len(issues),
            'critical_issues': critical_count,
            'warnings': warning_count,
            'total_events': self._count_events(verify_date),
            'total_employees': self._count_employees(verify_date)
        }

        return VerificationResult(status=status, issues=issues, summary=summary)

    def _check_juicer_events(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 1: Verify Juicer events are assigned to qualified employees

        Juicer events (Production, Survey, Deep Clean) require Club Supervisor or Juicer Barista
        """
        issues = []

        # Get all Juicer events scheduled for this date (all 3 types)
        juicer_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
        ).all()

        for schedule, event, employee in juicer_schedules:
            # Check if employee can work Juicer events
            if employee.job_title not in ['Club Supervisor', 'Juicer Barista']:
                issues.append(VerificationIssue(
                    severity='critical',
                    rule_name='Juicer Event Assignment',
                    message=f"Juicer event '{event.project_name}' is assigned to {employee.name} ({employee.job_title}), who is not qualified for Juicer events.",
                    details={
                        'employee_id': employee.id,
                        'employee_name': employee.name,
                        'employee_job_title': employee.job_title,
                        'event_id': event.id,
                        'event_name': event.project_name,
                        'event_type': event.event_type,
                        'schedule_id': schedule.id,
                        'required_titles': ['Club Supervisor', 'Juicer Barista']
                    }
                ))

        return issues

    def _check_core_event_limit(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 2: Verify each employee has maximum 1 Core event per day
        """
        issues = []

        # Get Core event counts per employee for this date
        core_counts = self.db.query(
            self.Employee.id,
            self.Employee.name,
            func.count(self.Schedule.id).label('core_count')
        ).join(
            self.Schedule, self.Employee.id == self.Schedule.employee_id
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).group_by(
            self.Employee.id, self.Employee.name
        ).having(
            func.count(self.Schedule.id) > 1
        ).all()

        for employee_id, employee_name, core_count in core_counts:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Core Event Limit',
                message=f"{employee_name} has {core_count} Core events scheduled. Employees can only work 1 Core event per day.",
                details={
                    'employee_id': employee_id,
                    'employee_name': employee_name,
                    'core_event_count': core_count
                }
            ))

        return issues

    def _check_supervisor_assignments(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 3: Verify Supervisor events are assigned to Club Supervisor or Lead Event Specialist
        """
        issues = []

        # Get all Supervisor events for this date
        supervisor_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Supervisor'
        ).all()

        for schedule, event, employee in supervisor_schedules:
            # Check if employee is Club Supervisor or Lead Event Specialist
            if employee.job_title not in ['Club Supervisor', 'Lead Event Specialist']:
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Supervisor Event Assignment',
                    message=f"Supervisor event '{event.project_name}' is assigned to {employee.name} ({employee.job_title}). Should be assigned to Club Supervisor or Lead Event Specialist.",
                    details={
                        'employee_id': employee.id,
                        'employee_name': employee.name,
                        'employee_job_title': employee.job_title,
                        'event_id': event.id,
                        'event_name': event.project_name,
                        'schedule_id': schedule.id,
                        'required_titles': ['Club Supervisor', 'Lead Event Specialist']
                    }
                ))

        return issues

    def _check_supervisor_times(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 4: Verify all Supervisor events are scheduled at 12:00 noon
        """
        issues = []

        # Get all Supervisor events for this date
        supervisor_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Supervisor'
        ).all()

        for schedule, event, employee in supervisor_schedules:
            scheduled_time = schedule.schedule_datetime.time()
            # Parse expected time from settings (format: "HH:MM:SS")
            try:
                h, m, s = map(int, self.SUPERVISOR_TIME.split(':'))
                expected_time = time(h, m)
            except (ValueError, AttributeError):
                expected_time = time(12, 0)  # Fallback to 12:00 PM

            if scheduled_time != expected_time:
                expected_time_str = expected_time.strftime('%I:%M %p').lstrip('0')
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Supervisor Event Time',
                    message=f"Supervisor event '{event.project_name}' for {employee.name} is scheduled at {scheduled_time.strftime('%I:%M %p')}. Should be at {expected_time_str}.",
                    details={
                        'employee_id': employee.id,
                        'employee_name': employee.name,
                        'event_id': event.id,
                        'event_name': event.project_name,
                        'schedule_id': schedule.id,
                        'scheduled_time': scheduled_time.strftime('%H:%M:%S'),
                        'expected_time': expected_time.strftime('%H:%M:%S')
                    }
                ))

        return issues

    def _check_shift_balance(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 5: Verify Core events are balanced across 4 shifts

        Rule: No shift should have 3+ events while another shift has 0 events
        """
        issues = []

        # Get Core event counts per timeslot
        shift_counts = {}
        for timeslot in self.CORE_TIMESLOTS:
            count = self.db.query(self.Schedule).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                func.date(self.Schedule.schedule_datetime) == verify_date,
                extract_time(self.Schedule.schedule_datetime) == timeslot,
                self.Event.event_type == 'Core'
            ).count()
            shift_counts[timeslot] = count

        # Check for imbalance: any shift with 3+ events while another has 0
        max_count = max(shift_counts.values())
        min_count = min(shift_counts.values())

        if max_count >= 3 and min_count == 0:
            # Find shifts with max and min
            max_shifts = [slot for slot, count in shift_counts.items() if count == max_count]
            min_shifts = [slot for slot, count in shift_counts.items() if count == min_count]

            issues.append(VerificationIssue(
                severity='warning',
                rule_name='Shift Balance',
                message=f"Core events are imbalanced across shifts. {self._format_time(max_shifts[0])} has {max_count} events while {self._format_time(min_shifts[0])} has 0 events.",
                details={
                    'shift_counts': {self._format_time(k): v for k, v in shift_counts.items()},
                    'overloaded_shifts': [self._format_time(s) for s in max_shifts],
                    'empty_shifts': [self._format_time(s) for s in min_shifts]
                }
            ))

        return issues

    def _check_lead_coverage(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 6: Verify opening and closing Lead Event Specialist coverage

        If more than 1 Lead Event Specialist scheduled:
        - Check if there's an opening Lead (earliest Core time)
        - Check if there's a closing Lead (latest Core time)
        - Suggest shift swaps with Event Specialists if needed
        """
        issues = []

        # Get all Lead Event Specialists with Core events on this date
        lead_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core',
            self.Employee.job_title == 'Lead Event Specialist'
        ).order_by(
            self.Schedule.schedule_datetime
        ).all()

        # Only check if there are 2+ Leads scheduled
        if len(lead_schedules) < 2:
            return issues

        # Get all Core event times for the day
        all_core_times = self.db.query(
            self.Schedule.schedule_datetime
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).order_by(
            self.Schedule.schedule_datetime
        ).all()

        if not all_core_times:
            return issues

        earliest_time = all_core_times[0][0].time()
        latest_time = all_core_times[-1][0].time()

        # Get Lead times
        lead_times = [schedule.schedule_datetime.time() for schedule, _, _ in lead_schedules]

        # Check opening Lead
        has_opening_lead = earliest_time in lead_times

        # Check closing Lead
        has_closing_lead = latest_time in lead_times

        if not has_opening_lead:
            # Find Event Specialists at opening time to suggest swap
            opening_specialists = self._find_shift_swap_candidates(
                verify_date, earliest_time, 'Lead Event Specialist'
            )

            issues.append(VerificationIssue(
                severity='warning',
                rule_name='Lead Coverage - Opening',
                message=f"No Lead Event Specialist at opening shift ({self._format_time_obj(earliest_time)}). Consider swapping a Lead's shift with an Event Specialist.",
                details={
                    'missing_shift': self._format_time_obj(earliest_time),
                    'coverage_type': 'opening',
                    'swap_suggestions': opening_specialists
                }
            ))

        if not has_closing_lead:
            # Find Event Specialists at closing time to suggest swap
            closing_specialists = self._find_shift_swap_candidates(
                verify_date, latest_time, 'Lead Event Specialist'
            )

            issues.append(VerificationIssue(
                severity='warning',
                rule_name='Lead Coverage - Closing',
                message=f"No Lead Event Specialist at closing shift ({self._format_time_obj(latest_time)}). Consider swapping a Lead's shift with an Event Specialist.",
                details={
                    'missing_shift': self._format_time_obj(latest_time),
                    'coverage_type': 'closing',
                    'swap_suggestions': closing_specialists
                }
            ))

        return issues

    def _find_shift_swap_candidates(
        self,
        verify_date: date,
        target_time: time,
        target_job_title: str
    ) -> List[Dict[str, Any]]:
        """
        Find potential shift swap candidates

        Looks for:
        1. Event Specialists at target_time (who could swap with a Lead at different time)
        2. Leads at different times (who could swap to target_time)
        """
        candidates = []

        # Get Event Specialists at target time
        specialists_at_target = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            extract_time(self.Schedule.schedule_datetime) == target_time,
            self.Event.event_type == 'Core',
            self.Employee.job_title == 'Event Specialist'
        ).all()

        # Get Leads at different times
        leads_at_other_times = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            extract_time(self.Schedule.schedule_datetime) != target_time,
            self.Event.event_type == 'Core',
            self.Employee.job_title == target_job_title
        ).all()

        # Build swap suggestions
        for spec_sched, spec_event, specialist in specialists_at_target:
            for lead_sched, lead_event, lead in leads_at_other_times:
                candidates.append({
                    'swap_type': 'shift_time',
                    'suggestion': f"Swap {lead.name}'s shift time ({self._format_time_obj(lead_sched.schedule_datetime.time())}) with {specialist.name}'s shift time ({self._format_time_obj(spec_sched.schedule_datetime.time())})",
                    'lead_employee': {
                        'id': lead.id,
                        'name': lead.name,
                        'current_time': self._format_time_obj(lead_sched.schedule_datetime.time()),
                        'schedule_id': lead_sched.id
                    },
                    'specialist_employee': {
                        'id': specialist.id,
                        'name': specialist.name,
                        'current_time': self._format_time_obj(spec_sched.schedule_datetime.time()),
                        'schedule_id': spec_sched.id
                    }
                })

        return candidates

    def _check_employee_work_limits(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 7: Check employee work limits

        - Verify availability
        - Check time-off requests
        - Ensure max 6 days worked per week (Sunday-Saturday)
        """
        issues = []

        # Get all employees scheduled for this date
        scheduled_employees = self.db.query(
            self.Employee
        ).join(
            self.Schedule, self.Employee.id == self.Schedule.employee_id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date
        ).distinct().all()

        for employee in scheduled_employees:
            # Check 1: Availability
            availability_issue = self._check_employee_availability(employee, verify_date)
            if availability_issue:
                issues.append(availability_issue)

            # Check 2: Time-off
            time_off_issue = self._check_employee_time_off(employee, verify_date)
            if time_off_issue:
                issues.append(time_off_issue)

            # Check 3: Max work days (6 per week, Sunday-Saturday)
            work_days_issue = self._check_employee_work_days(employee, verify_date)
            if work_days_issue:
                issues.append(work_days_issue)

        return issues

    def _check_employee_availability(
        self,
        employee,
        verify_date: date
    ) -> Optional[VerificationIssue]:
        """Check if employee is available on this date"""

        # Check specific date availability
        if self.EmployeeAvailability:
            specific_avail = self.db.query(self.EmployeeAvailability).filter(
                self.EmployeeAvailability.employee_id == employee.id,
                self.EmployeeAvailability.date == verify_date
            ).first()

            if specific_avail and not specific_avail.is_available:
                return VerificationIssue(
                    severity='warning',
                    rule_name='Employee Availability',
                    message=f"{employee.name} is marked as unavailable on {verify_date}. Reason: {specific_avail.reason or 'Not specified'}",
                    details={
                        'employee_id': employee.id,
                        'employee_name': employee.name,
                        'date': verify_date.isoformat(),
                        'reason': specific_avail.reason
                    }
                )

        # Check weekly availability
        if self.EmployeeWeeklyAvailability:
            day_of_week = verify_date.weekday()  # 0=Monday, 6=Sunday
            day_columns = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_column = day_columns[day_of_week]

            weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter(
                self.EmployeeWeeklyAvailability.employee_id == employee.id
            ).first()

            if weekly_avail:
                is_available = getattr(weekly_avail, day_column)
                if not is_available:
                    return VerificationIssue(
                        severity='warning',
                        rule_name='Employee Weekly Availability',
                        message=f"{employee.name} is not available on {day_column.capitalize()}s according to their weekly availability pattern.",
                        details={
                            'employee_id': employee.id,
                            'employee_name': employee.name,
                            'day_of_week': day_column,
                            'date': verify_date.isoformat()
                        }
                    )

        return None

    def _check_employee_time_off(
        self,
        employee,
        verify_date: date
    ) -> Optional[VerificationIssue]:
        """Check if employee has time-off on this date"""

        time_off = self.db.query(self.EmployeeTimeOff).filter(
            self.EmployeeTimeOff.employee_id == employee.id,
            self.EmployeeTimeOff.start_date <= verify_date,
            self.EmployeeTimeOff.end_date >= verify_date
        ).first()

        if time_off:
            return VerificationIssue(
                severity='warning',
                rule_name='Employee Time Off',
                message=f"{employee.name} has time-off scheduled from {time_off.start_date} to {time_off.end_date}. Reason: {time_off.reason or 'Not specified'}",
                details={
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'time_off_start': time_off.start_date.isoformat(),
                    'time_off_end': time_off.end_date.isoformat(),
                    'reason': time_off.reason
                }
            )

        return None

    def _check_employee_work_days(
        self,
        employee,
        verify_date: date
    ) -> Optional[VerificationIssue]:
        """
        Check if employee is working more than 6 days in the week

        Week definition: Sunday through Saturday containing verify_date
        """
        # Find the Sunday of the week containing verify_date
        days_since_sunday = (verify_date.weekday() + 1) % 7  # Monday=0, Sunday=6 -> 1,2,3,4,5,6,0
        week_start = verify_date - timedelta(days=days_since_sunday)
        week_end = week_start + timedelta(days=6)

        # Count distinct days worked in this week
        days_worked = self.db.query(
            func.date(self.Schedule.schedule_datetime)
        ).filter(
            self.Schedule.employee_id == employee.id,
            func.date(self.Schedule.schedule_datetime) >= week_start,
            func.date(self.Schedule.schedule_datetime) <= week_end
        ).distinct().count()

        if days_worked > self.MAX_WORK_DAYS_PER_WEEK:
            return VerificationIssue(
                severity='warning',
                rule_name='Employee Work Days Limit',
                message=f"{employee.name} is scheduled for {days_worked} days in the week of {week_start} to {week_end}. Maximum is {self.MAX_WORK_DAYS_PER_WEEK} days per week.",
                details={
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'days_worked': days_worked,
                    'max_days': self.MAX_WORK_DAYS_PER_WEEK,
                    'week_start': week_start.isoformat(),
                    'week_end': week_end.isoformat()
                }
            )

        return None

    def _check_event_date_ranges(self, verify_date: date) -> List[VerificationIssue]:
        """
        Rule 8: Verify event date ranges

        - Check if scheduled events are within their start_datetime and due_datetime
        - Check for unscheduled events that should be done on this date
        """
        issues = []

        # Check 1: Scheduled events outside their date range
        out_of_range = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            or_(
                func.date(self.Schedule.schedule_datetime) < func.date(self.Event.start_datetime),
                func.date(self.Schedule.schedule_datetime) > func.date(self.Event.due_datetime)
            )
        ).all()

        for schedule, event, employee in out_of_range:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Event Date Range',
                message=f"Event '{event.project_name}' is scheduled on {verify_date} but must be done between {event.start_datetime.date()} and {event.due_datetime.date()}.",
                details={
                    'event_id': event.id,
                    'event_name': event.project_name,
                    'schedule_id': schedule.id,
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'scheduled_date': verify_date.isoformat(),
                    'event_start_date': event.start_datetime.date().isoformat(),
                    'event_due_date': event.due_datetime.date().isoformat()
                }
            ))

        # Check 2: Unscheduled events that should be done today
        unscheduled_today = self.db.query(self.Event).filter(
            self.Event.is_scheduled == False,
            func.date(self.Event.start_datetime) <= verify_date,
            func.date(self.Event.due_datetime) >= verify_date
        ).all()

        for event in unscheduled_today:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Unscheduled Required Event',
                message=f"Event '{event.project_name}' (Type: {event.event_type}) is not scheduled but must be completed between {event.start_datetime.date()} and {event.due_datetime.date()}.",
                details={
                    'event_id': event.id,
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'event_start_date': event.start_datetime.date().isoformat(),
                    'event_due_date': event.due_datetime.date().isoformat(),
                    'verify_date': verify_date.isoformat()
                }
            ))

        return issues

    # ============================================================================
    # NEW FOCUSED VERIFICATION RULES
    # ============================================================================

    def _check_employee_availability_only(self, verify_date: date) -> List[VerificationIssue]:
        """
        Check employee availability AND time-off for all scheduled employees

        Combines:
        - Weekly availability pattern check
        - Specific date availability check
        - Time-off request check
        """
        issues = []

        # Get all employees scheduled for this date
        scheduled_employees = self.db.query(
            self.Employee
        ).join(
            self.Schedule, self.Employee.id == self.Schedule.employee_id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date
        ).distinct().all()

        for employee in scheduled_employees:
            # Check time-off first (highest priority)
            time_off = self.db.query(self.EmployeeTimeOff).filter(
                self.EmployeeTimeOff.employee_id == employee.id,
                self.EmployeeTimeOff.start_date <= verify_date,
                self.EmployeeTimeOff.end_date >= verify_date
            ).first()

            if time_off:
                issues.append(VerificationIssue(
                    severity='critical',
                    rule_name='Employee Time Off',
                    message=f"{employee.name} has time-off from {time_off.start_date} to {time_off.end_date}. Reason: {time_off.reason or 'Not specified'}",
                    details={
                        'employee_id': employee.id,
                        'employee_name': employee.name,
                        'time_off_start': time_off.start_date.isoformat(),
                        'time_off_end': time_off.end_date.isoformat(),
                        'reason': time_off.reason
                    }
                ))
                continue  # Skip availability check if on time-off

            # Check weekly availability pattern
            if self.EmployeeWeeklyAvailability:
                day_of_week = verify_date.weekday()
                day_columns = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                day_column = day_columns[day_of_week]

                weekly_avail = self.db.query(self.EmployeeWeeklyAvailability).filter(
                    self.EmployeeWeeklyAvailability.employee_id == employee.id
                ).first()

                if weekly_avail:
                    is_available = getattr(weekly_avail, day_column)
                    if not is_available:
                        issues.append(VerificationIssue(
                            severity='critical',
                            rule_name='Employee Availability',
                            message=f"{employee.name} is not available on {day_column.capitalize()}s but is scheduled.",
                            details={
                                'employee_id': employee.id,
                                'employee_name': employee.name,
                                'day_of_week': day_column,
                                'date': verify_date.isoformat()
                            }
                        ))

        return issues

    def _check_core_times_and_balance(self, verify_date: date) -> List[VerificationIssue]:
        """
        Verify Core events are at valid times and balanced across shifts
        """
        issues = []

        # Get all Core events for this date
        core_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).all()

        # Check each Core event is at a valid time slot
        for schedule, event, employee in core_schedules:
            scheduled_time = schedule.schedule_datetime.time().strftime('%H:%M:%S')
            if scheduled_time not in self.CORE_TIMESLOTS:
                valid_times = [self._format_time(t) for t in self.CORE_TIMESLOTS]
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Core Event Time',
                    message=f"Core event for {employee.name} is scheduled at {self._format_time(scheduled_time)} which is not a standard time slot. Valid times: {', '.join(valid_times)}",
                    details={
                        'employee_id': employee.id,
                        'employee_name': employee.name,
                        'event_name': event.project_name,
                        'scheduled_time': scheduled_time,
                        'valid_times': self.CORE_TIMESLOTS
                    }
                ))

        # Check shift balance
        shift_counts = {}
        for timeslot in self.CORE_TIMESLOTS:
            count = sum(1 for s, e, emp in core_schedules
                       if s.schedule_datetime.time().strftime('%H:%M:%S') == timeslot)
            shift_counts[timeslot] = count

        if shift_counts:
            max_count = max(shift_counts.values())
            min_count = min(shift_counts.values())

            if max_count >= 3 and min_count == 0:
                max_shifts = [self._format_time(s) for s, c in shift_counts.items() if c == max_count]
                min_shifts = [self._format_time(s) for s, c in shift_counts.items() if c == min_count]

                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Shift Balance',
                    message=f"Core events are imbalanced. {max_shifts[0]} has {max_count} events while {min_shifts[0]} has 0.",
                    details={
                        'shift_counts': {self._format_time(k): v for k, v in shift_counts.items()},
                        'overloaded': max_shifts,
                        'empty': min_shifts
                    }
                ))

        return issues

    def _check_core_supervisor_pairing(self, verify_date: date) -> List[VerificationIssue]:
        """
        Verify each Core event has a paired Supervisor event scheduled to a supervisor
        """
        issues = []

        # Get all Core events for this date
        core_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).all()

        # Get all Supervisor events for this date
        supervisor_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Supervisor'
        ).all()

        # Build map of Supervisor events by project_ref_num
        supervisor_map = {}
        for sched, event, emp in supervisor_schedules:
            supervisor_map[event.project_ref_num] = {
                'schedule': sched,
                'event': event,
                'employee': emp
            }

        for core_sched, core_event, core_emp in core_schedules:
            # Check if there's a corresponding Supervisor event (by parent_event_ref_num)
            # Supervisor events should have parent_event_ref_num pointing to Core
            paired_sup = None
            for sup_ref, sup_data in supervisor_map.items():
                if sup_data['event'].parent_event_ref_num == core_event.project_ref_num:
                    paired_sup = sup_data
                    break

            if not paired_sup:
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Core-Supervisor Pairing',
                    message=f"Core event '{core_event.project_name}' for {core_emp.name} has no paired Supervisor event.",
                    details={
                        'core_event_ref': core_event.project_ref_num,
                        'core_event_name': core_event.project_name,
                        'core_employee': core_emp.name
                    }
                ))
            else:
                # Check Supervisor is assigned to correct person (Club Supervisor or Lead)
                sup_emp = paired_sup['employee']
                if sup_emp.job_title not in ['Club Supervisor', 'Lead Event Specialist']:
                    issues.append(VerificationIssue(
                        severity='warning',
                        rule_name='Supervisor Assignment',
                        message=f"Supervisor event for '{core_event.project_name}' is assigned to {sup_emp.name} ({sup_emp.job_title}). Should be Club Supervisor or Lead.",
                        details={
                            'supervisor_employee': sup_emp.name,
                            'supervisor_title': sup_emp.job_title,
                            'core_event': core_event.project_name
                        }
                    ))

        return issues

    def _check_freeosk_scheduling(self, verify_date: date) -> List[VerificationIssue]:
        """
        Verify Freeosk events are scheduled to correct person (Lead/Supervisor) at correct time
        """
        issues = []

        # Get expected Freeosk times from settings
        try:
            from app.services.event_time_settings import get_freeosk_times
            freeosk_times = get_freeosk_times()
            expected_time = freeosk_times.get('start', time(10, 0))
            if hasattr(expected_time, 'strftime'):
                expected_time_str = expected_time.strftime('%H:%M:%S')
            else:
                expected_time_str = '10:00:00'
        except Exception:
            expected_time_str = '10:00:00'

        # Get all Freeosk events for this date
        freeosk_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Freeosk'
        ).all()

        for schedule, event, employee in freeosk_schedules:
            # Check person is qualified (Lead or Supervisor)
            if employee.job_title not in ['Club Supervisor', 'Lead Event Specialist']:
                issues.append(VerificationIssue(
                    severity='critical',
                    rule_name='Freeosk Assignment',
                    message=f"Freeosk event '{event.project_name}' is assigned to {employee.name} ({employee.job_title}). Must be Club Supervisor or Lead Event Specialist.",
                    details={
                        'event_name': event.project_name,
                        'employee': employee.name,
                        'job_title': employee.job_title
                    }
                ))

        return issues

    def _check_digitals_scheduling(self, verify_date: date) -> List[VerificationIssue]:
        """
        Verify Digital events are scheduled to correct person (Lead/Supervisor) at correct time
        """
        issues = []

        # Get all Digital events for this date (includes Digital Setup, Digital Refresh, Digital Teardown, Digitals)
        digital_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type.in_(['Digitals', 'Digital Setup', 'Digital Refresh', 'Digital Teardown'])
        ).all()

        for schedule, event, employee in digital_schedules:
            # Check person is qualified (Lead or Supervisor)
            if employee.job_title not in ['Club Supervisor', 'Lead Event Specialist']:
                issues.append(VerificationIssue(
                    severity='critical',
                    rule_name='Digital Event Assignment',
                    message=f"Digital event '{event.project_name}' is assigned to {employee.name} ({employee.job_title}). Must be Club Supervisor or Lead Event Specialist.",
                    details={
                        'event_name': event.project_name,
                        'event_type': event.event_type,
                        'employee': employee.name,
                        'job_title': employee.job_title
                    }
                ))

        return issues

    def _check_events_due_tomorrow(self, verify_date: date) -> List[VerificationIssue]:
        """
        Check that all events due tomorrow (next day) are scheduled
        """
        issues = []

        tomorrow = verify_date + timedelta(days=1)

        # Find events with due_datetime = tomorrow that are not scheduled
        unscheduled_due_tomorrow = self.db.query(self.Event).filter(
            self.Event.is_scheduled == False,
            func.date(self.Event.due_datetime) == tomorrow,
            self.Event.condition != 'Canceled'
        ).all()

        for event in unscheduled_due_tomorrow:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Event Due Tomorrow',
                message=f"Event '{event.project_name}' ({event.event_type}) is due tomorrow ({tomorrow}) but is not scheduled.",
                details={
                    'event_id': event.id,
                    'event_ref_num': event.project_ref_num,
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'due_date': tomorrow.isoformat()
                }
            ))

        return issues

    def _check_juicer_rotation(self, verify_date: date) -> List[VerificationIssue]:
        """
        Verify Juicer events:
        1. Juicer is scheduled to the correct rotation person for that day
        2. If Juicer employee is on Juicer Production, they should NOT have a Core event
        """
        issues = []

        # Get the expected Juicer for this day from rotation
        expected_juicer_id = None
        if self.RotationAssignment:
            day_of_week = (verify_date.weekday() + 1) % 7  # Convert to 0=Sunday format
            rotation = self.db.query(self.RotationAssignment).filter(
                self.RotationAssignment.day_of_week == day_of_week,
                self.RotationAssignment.rotation_type == 'juicer'
            ).first()

            if rotation:
                expected_juicer_id = rotation.employee_id

        # Get all Juicer events scheduled for this date
        juicer_schedules = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type.in_(['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'])
        ).all()

        juicer_employee_ids = set()

        for schedule, event, employee in juicer_schedules:
            juicer_employee_ids.add(employee.id)

            # Check if employee is qualified
            if employee.job_title not in ['Club Supervisor', 'Juicer Barista']:
                issues.append(VerificationIssue(
                    severity='critical',
                    rule_name='Juicer Qualification',
                    message=f"Juicer event assigned to {employee.name} ({employee.job_title}) who is not qualified for Juicer events.",
                    details={
                        'employee': employee.name,
                        'job_title': employee.job_title,
                        'event_name': event.project_name
                    }
                ))

            # Check if this is the rotation Juicer
            if expected_juicer_id and employee.id != expected_juicer_id:
                expected_emp = self.db.query(self.Employee).get(expected_juicer_id)
                expected_name = expected_emp.name if expected_emp else 'Unknown'
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Juicer Rotation',
                    message=f"Juicer event assigned to {employee.name} but {expected_name} is on Juicer rotation for this day.",
                    details={
                        'assigned_employee': employee.name,
                        'rotation_employee': expected_name,
                        'day_of_week': verify_date.strftime('%A')
                    }
                ))

        # Check if Juicer employees also have Core events (not allowed)
        for juicer_emp_id in juicer_employee_ids:
            core_event = self.db.query(self.Schedule).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                func.date(self.Schedule.schedule_datetime) == verify_date,
                self.Schedule.employee_id == juicer_emp_id,
                self.Event.event_type == 'Core'
            ).first()

            if core_event:
                employee = self.db.query(self.Employee).get(juicer_emp_id)
                issues.append(VerificationIssue(
                    severity='critical',
                    rule_name='Juicer-Core Conflict',
                    message=f"{employee.name} is scheduled for both Juicer and Core events on the same day. Juicer employees cannot work Core events.",
                    details={
                        'employee_id': juicer_emp_id,
                        'employee_name': employee.name,
                        'date': verify_date.isoformat()
                    }
                ))

        return issues

    # ============================================================================
    # DATE RANGE VERIFICATION (Multi-Day) - Pre/Post-Approval Support
    # ============================================================================

    def verify_date_range(
        self,
        start_date: date,
        end_date: date,
        include_pending: bool = False,
        run_id: Optional[int] = None
    ) -> Dict:
        """
        Verify schedules for a date range (Range Mode)

        Performs comprehensive validation of all schedules within the specified
        date range. Can operate in two modes:

        Pre-approval mode (include_pending=True):
            - Includes PendingSchedule records for the specified run_id
            - Validates proposed schedules before API submission
            - Checks for conflicts with existing schedules
            - Verifies employee availability and constraints
            - WARNING: Cannot verify supervisor pairing (created during approval)

        Post-approval mode (include_pending=False):
            - Only checks committed Schedule records
            - Used for audit and retrospective verification
            - Can validate supervisor pairing with Core events

        Args:
            start_date: datetime.date - Start of verification range
            end_date: datetime.date - End of verification range (inclusive)
            include_pending: bool - Include PendingSchedule records (for pre-approval)
            run_id: int - Scheduler run ID (required if include_pending=True)

        Returns:
            {
                'critical_issues': [],  # Block approval - must fix
                'warnings': [],         # Allow with confirmation
                'info': [],             # FYI only
                'stats': {              # Summary statistics
                    'total_schedules': int,
                    'pending_schedules': int,
                    'committed_schedules': int,
                    'unique_employees': int,
                    'unique_events': int,
                    'date_range_days': int
                }
            }

        Raises:
            ValueError: If include_pending=True but run_id is not provided
        """
        if include_pending and run_id is None:
            raise ValueError("run_id is required when include_pending=True")

        logger.info(
            f"Starting schedule verification for {start_date} to {end_date} "
            f"(include_pending={include_pending}, run_id={run_id})"
        )

        # Initialize results
        critical_issues = []
        warnings = []
        info = []

        # Check event data freshness first
        freshness_result = self._get_event_data_freshness()
        if freshness_result['is_stale']:
            warnings.append({
                'severity': 'warning',
                'type': 'stale_data',
                'category': 'Data Quality',
                'message': f"Event data is stale ({freshness_result['staleness_hours']:.1f} hours old)",
                'details': {
                    'last_sync': freshness_result['last_sync'].isoformat() if freshness_result['last_sync'] else 'Never',
                    'staleness_hours': freshness_result['staleness_hours']
                },
                'action': 'Consider syncing event data before scheduling to ensure accuracy'
            })

        # Run all verification checks
        critical_issues.extend(
            self._check_employee_conflicts(start_date, end_date, include_pending, run_id)
        )

        warnings.extend(
            self._check_event_coverage(start_date, end_date, include_pending, run_id)
        )

        warnings.extend(
            self._check_rotation_coverage(start_date, end_date, include_pending, run_id)
        )

        # Supervisor pairing check: Only works post-approval
        if include_pending:
            info.append({
                'severity': 'info',
                'type': 'supervisor_pairing_skipped',
                'category': 'Verification Scope',
                'message': 'Supervisor pairing verification skipped (pre-approval mode)',
                'details': 'Supervisor events are created during approval, not before',
                'action': None
            })
        else:
            warnings.extend(
                self._check_supervisor_pairing(start_date, end_date)
            )

        # Calculate statistics
        stats = self._calculate_stats(start_date, end_date, include_pending, run_id)

        # Log summary
        logger.info(
            f"Verification complete: {len(critical_issues)} critical, "
            f"{len(warnings)} warnings, {len(info)} info items"
        )

        return {
            'critical_issues': critical_issues,
            'warnings': warnings,
            'info': info,
            'stats': stats
        }

    def _get_event_data_freshness(self) -> Dict:
        """
        Check how fresh event data is from last sync

        Stale event data (>24 hours) may mean schedules are being created
        against outdated information (canceled events, changed dates, etc.)

        Returns:
            {
                'last_sync': datetime or None,
                'is_stale': bool,
                'staleness_hours': float
            }
        """
        # Find most recently synced event
        most_recent = self.db.query(self.Event).filter(
            self.Event.last_synced.isnot(None)
        ).order_by(self.Event.last_synced.desc()).first()

        if not most_recent or not most_recent.last_synced:
            return {
                'last_sync': None,
                'is_stale': True,
                'staleness_hours': float('inf')
            }

        last_sync = most_recent.last_synced
        staleness_hours = (datetime.utcnow() - last_sync).total_seconds() / 3600
        is_stale = staleness_hours > 24

        return {
            'last_sync': last_sync,
            'is_stale': is_stale,
            'staleness_hours': staleness_hours
        }

    def _check_employee_conflicts(
        self,
        start_date: date,
        end_date: date,
        include_pending: bool = False,
        run_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Check for employee scheduling conflicts (CRITICAL)

        Validates:
        - Double-booking: Same employee, overlapping times
        - Time-off violations: Employee scheduled during approved time-off
        - Schedule outside event period: Schedule datetime not in event's date range

        These are CRITICAL issues that block approval because they represent
        true data integrity problems or business rule violations.

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_pending: Include pending schedules
            run_id: Scheduler run ID (if checking pending)

        Returns:
            List of critical issue dicts
        """
        critical_issues = []

        # Get all schedules in date range (committed + pending if requested)
        all_schedules = self._get_combined_schedules(
            start_date, end_date, include_pending, run_id
        )

        if not all_schedules:
            return critical_issues

        # Check 1: Time-off violations
        time_off_conflicts = self._check_time_off_conflicts(all_schedules, start_date, end_date)
        if time_off_conflicts:
            critical_issues.append({
                'severity': 'critical',
                'type': 'time_off_conflict',
                'category': 'Employee Availability',
                'message': f'{len(time_off_conflicts)} employee(s) scheduled during approved time-off',
                'details': time_off_conflicts,
                'action': 'Remove or reassign these schedules - employees are not available'
            })

        # Check 2: Double-booking (same employee, overlapping times)
        double_bookings = self._check_double_bookings(all_schedules)
        if double_bookings:
            critical_issues.append({
                'severity': 'critical',
                'type': 'double_booking',
                'category': 'Schedule Conflicts',
                'message': f'{len(double_bookings)} employee(s) double-booked at same time',
                'details': double_bookings,
                'action': 'Resolve conflicts by rescheduling one of the overlapping events'
            })

        # Check 3: Schedule datetime outside event period
        out_of_range = self._check_schedule_date_validity(all_schedules)
        if out_of_range:
            critical_issues.append({
                'severity': 'critical',
                'type': 'schedule_out_of_range',
                'category': 'Data Integrity',
                'message': f'{len(out_of_range)} schedule(s) outside event date range',
                'details': out_of_range,
                'action': 'Reschedule within event period or verify event dates are correct'
            })

        return critical_issues

    def _get_combined_schedules(
        self,
        start_date: date,
        end_date: date,
        include_pending: bool = False,
        run_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get all schedules (committed + pending) for date range

        Returns unified schedule data from both Schedule and PendingSchedule tables,
        normalized to a common format for conflict checking.

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_pending: Whether to include pending schedules
            run_id: Scheduler run ID (required if include_pending)

        Returns:
            List of schedule dicts with keys:
                - employee_id
                - schedule_datetime
                - event_ref_num
                - event (Event object)
                - employee (Employee object)
                - source ('committed' or 'pending')
                - duration_minutes
        """
        schedules = []

        # Get committed schedules
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)

        committed = self.db.query(self.Schedule, self.Event, self.Employee).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            self.Schedule.schedule_datetime >= start_datetime,
            self.Schedule.schedule_datetime <= end_datetime,
            self.Schedule.sync_status.in_(['synced', 'pending'])
        ).all()

        for sched, event, employee in committed:
            schedules.append({
                'employee_id': sched.employee_id,
                'schedule_datetime': sched.schedule_datetime,
                'event_ref_num': sched.event_ref_num,
                'event': event,
                'employee': employee,
                'source': 'committed',
                'duration_minutes': event.estimated_time or event.get_default_duration(event.event_type)
            })

        # Get pending schedules if requested
        if include_pending and run_id and self.PendingSchedule:
            pending = self.db.query(self.PendingSchedule, self.Event, self.Employee).join(
                self.Event, self.PendingSchedule.event_ref_num == self.Event.project_ref_num
            ).outerjoin(
                self.Employee, self.PendingSchedule.employee_id == self.Employee.id
            ).filter(
                self.PendingSchedule.scheduler_run_id == run_id,
                self.PendingSchedule.schedule_datetime >= start_datetime,
                self.PendingSchedule.schedule_datetime <= end_datetime,
                self.PendingSchedule.status.in_(['proposed', 'user_edited']),
                self.PendingSchedule.failure_reason.is_(None),
                self.PendingSchedule.employee_id.isnot(None),
                self.PendingSchedule.schedule_datetime.isnot(None)
            ).all()

            for pend, event, employee in pending:
                if employee:  # Only add if employee assigned
                    schedules.append({
                        'employee_id': pend.employee_id,
                        'schedule_datetime': pend.schedule_datetime,
                        'event_ref_num': pend.event_ref_num,
                        'event': event,
                        'employee': employee,
                        'source': 'pending',
                        'duration_minutes': event.estimated_time or event.get_default_duration(event.event_type)
                    })

        return schedules

    def _check_time_off_conflicts(
        self,
        all_schedules: List[Dict],
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """
        Check for schedules during approved time-off

        Args:
            all_schedules: Combined schedule list
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of conflict dicts
        """
        conflicts = []

        # Get all time-off records overlapping with date range
        time_off_records = self.db.query(self.EmployeeTimeOff).filter(
            self.EmployeeTimeOff.start_date <= end_date,
            self.EmployeeTimeOff.end_date >= start_date
        ).all()

        # Build lookup: employee_id -> list of time-off date ranges
        time_off_map = {}
        for to in time_off_records:
            if to.employee_id not in time_off_map:
                time_off_map[to.employee_id] = []
            time_off_map[to.employee_id].append({
                'start': to.start_date,
                'end': to.end_date,
                'reason': to.reason
            })

        # Check each schedule against time-off
        for sched in all_schedules:
            employee_id = sched['employee_id']
            sched_date = sched['schedule_datetime'].date()

            if employee_id in time_off_map:
                for to_range in time_off_map[employee_id]:
                    if to_range['start'] <= sched_date <= to_range['end']:
                        conflicts.append({
                            'employee_id': employee_id,
                            'employee_name': sched['employee'].name,
                            'schedule_date': sched_date.isoformat(),
                            'schedule_time': sched['schedule_datetime'].strftime('%H:%M'),
                            'event_ref_num': sched['event_ref_num'],
                            'event_name': sched['event'].project_name,
                            'event_type': sched['event'].event_type,
                            'time_off_reason': to_range['reason'],
                            'time_off_range': f"{to_range['start']} to {to_range['end']}",
                            'source': sched['source']
                        })
                        break  # One conflict per schedule is enough

        return conflicts

    def _check_double_bookings(self, all_schedules: List[Dict]) -> List[Dict]:
        """
        Check for employee double-booking (overlapping times)

        Exception: Club Supervisor can have multiple Supervisor events at same time
        (they oversee multiple Core events simultaneously)

        Args:
            all_schedules: Combined schedule list

        Returns:
            List of double-booking dicts
        """
        # Group schedules by employee and time
        employee_time_map = {}

        for sched in all_schedules:
            employee_id = sched['employee_id']
            start_time = sched['schedule_datetime']
            duration_minutes = sched['duration_minutes']
            end_time = start_time + timedelta(minutes=duration_minutes)

            if employee_id not in employee_time_map:
                employee_time_map[employee_id] = []

            employee_time_map[employee_id].append({
                'start': start_time,
                'end': end_time,
                'event_ref_num': sched['event_ref_num'],
                'event_name': sched['event'].project_name,
                'event_type': sched['event'].event_type,
                'employee': sched['employee'],
                'source': sched['source']
            })

        # Check for overlaps
        double_bookings = []

        for employee_id, time_slots in employee_time_map.items():
            if len(time_slots) < 2:
                continue  # No possibility of conflict

            # Sort by start time
            time_slots.sort(key=lambda x: x['start'])

            # Check each pair for overlap
            for i in range(len(time_slots)):
                for j in range(i + 1, len(time_slots)):
                    slot1 = time_slots[i]
                    slot2 = time_slots[j]

                    # Check if times overlap
                    if slot1['start'] < slot2['end'] and slot2['start'] < slot1['end']:
                        # Exception: Club Supervisor can have multiple Supervisor events
                        employee = slot1['employee']
                        if (employee.job_title == 'Club Supervisor' and
                            slot1['event_type'] == 'Supervisor' and
                            slot2['event_type'] == 'Supervisor'):
                            continue  # Allowed

                        double_bookings.append({
                            'employee_id': employee_id,
                            'employee_name': employee.name,
                            'event1_ref': slot1['event_ref_num'],
                            'event1_name': slot1['event_name'],
                            'event1_type': slot1['event_type'],
                            'event1_time': f"{slot1['start'].strftime('%Y-%m-%d %H:%M')} - {slot1['end'].strftime('%H:%M')}",
                            'event1_source': slot1['source'],
                            'event2_ref': slot2['event_ref_num'],
                            'event2_name': slot2['event_name'],
                            'event2_type': slot2['event_type'],
                            'event2_time': f"{slot2['start'].strftime('%Y-%m-%d %H:%M')} - {slot2['end'].strftime('%H:%M')}",
                            'event2_source': slot2['source']
                        })

        return double_bookings

    def _check_schedule_date_validity(self, all_schedules: List[Dict]) -> List[Dict]:
        """
        Check if schedule datetime is within event's valid period

        Events have a start_datetime and due_datetime that define when
        the work can be performed. Schedules outside this range are invalid.

        Args:
            all_schedules: Combined schedule list

        Returns:
            List of out-of-range schedule dicts
        """
        out_of_range = []

        for sched in all_schedules:
            event = sched['event']
            sched_datetime = sched['schedule_datetime']

            # Check if schedule is outside event period
            if not (event.start_datetime <= sched_datetime <= event.due_datetime):
                out_of_range.append({
                    'employee_id': sched['employee_id'],
                    'employee_name': sched['employee'].name,
                    'event_ref_num': sched['event_ref_num'],
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'schedule_datetime': sched_datetime.isoformat(),
                    'event_start': event.start_datetime.isoformat(),
                    'event_due': event.due_datetime.isoformat(),
                    'source': sched['source']
                })

        return out_of_range

    def _check_event_coverage(
        self,
        start_date: date,
        end_date: date,
        include_pending: bool = False,
        run_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Check if required events are scheduled (WARNING level)

        Validates that expected event types have schedules:
        - Freeosk events: Typically should be scheduled
        - Digital events (Setup/Refresh/Teardown): Typically should be scheduled

        This is WARNING level (not critical) because:
        1. Events might not exist in the system yet
        2. Events might be intentionally unscheduled (canceled, delayed)
        3. Not all events require immediate scheduling

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_pending: Include pending schedules
            run_id: Scheduler run ID (if checking pending)

        Returns:
            List of warning dicts
        """
        warnings = []

        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)

        # Find Freeosk and Digital events in date range that aren't canceled
        required_events = self.db.query(self.Event).filter(
            self.Event.start_datetime >= start_datetime,
            self.Event.start_datetime <= end_datetime,
            self.Event.event_type.in_(['Freeosk', 'Digitals']),
            self.Event.condition != 'Canceled'
        ).all()

        if not required_events:
            return warnings  # No events to check

        # Get scheduled event refs (committed + pending)
        scheduled_refs = set()

        # Committed schedules
        committed = self.db.query(self.Schedule.event_ref_num).filter(
            self.Schedule.schedule_datetime >= start_datetime,
            self.Schedule.schedule_datetime <= end_datetime
        ).all()
        scheduled_refs.update([ref for (ref,) in committed])

        # Pending schedules
        if include_pending and run_id and self.PendingSchedule:
            pending = self.db.query(self.PendingSchedule.event_ref_num).filter(
                self.PendingSchedule.scheduler_run_id == run_id,
                self.PendingSchedule.status.in_(['proposed', 'user_edited']),
                self.PendingSchedule.failure_reason.is_(None)
            ).all()
            scheduled_refs.update([ref for (ref,) in pending])

        # Find unscheduled required events
        unscheduled = []
        for event in required_events:
            if event.project_ref_num not in scheduled_refs:
                unscheduled.append({
                    'event_ref_num': event.project_ref_num,
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'start_date': event.start_datetime.strftime('%Y-%m-%d'),
                    'due_date': event.due_datetime.strftime('%Y-%m-%d'),
                    'condition': event.condition
                })

        if unscheduled:
            warnings.append({
                'severity': 'warning',
                'type': 'unscheduled_required_events',
                'category': 'Event Coverage',
                'message': f'{len(unscheduled)} Freeosk/Digital event(s) are unscheduled',
                'details': unscheduled,
                'action': 'Review if these events should be scheduled (may be intentionally unscheduled)'
            })

        return warnings

    def _check_rotation_coverage(
        self,
        start_date: date,
        end_date: date,
        include_pending: bool = False,
        run_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Check if primary leads have Core events scheduled (WARNING level)

        Validates that employees assigned to primary_lead rotation have
        corresponding Core events scheduled for their rotation days.

        This is WARNING level because:
        1. Rotation assignment might be intentionally empty (no events that day)
        2. Schedule exceptions might override rotation
        3. Not all rotation days require Core events

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_pending: Include pending schedules
            run_id: Scheduler run ID (if checking pending)

        Returns:
            List of warning dicts
        """
        warnings = []

        if not self.RotationAssignment:
            return warnings

        # Get all rotation assignments
        rotations = self.db.query(self.RotationAssignment).filter(
            self.RotationAssignment.rotation_type == 'primary_lead'
        ).all()

        if not rotations:
            return warnings  # No rotations configured

        # Build map: day_of_week -> employee_id
        rotation_map = {rot.day_of_week: rot.employee_id for rot in rotations}

        # Get combined schedules for date range
        all_schedules = self._get_combined_schedules(
            start_date, end_date, include_pending, run_id
        )

        # Group Core event schedules by (employee_id, date)
        core_schedules = {}
        for sched in all_schedules:
            if sched['event'].event_type == 'Core':
                sched_date = sched['schedule_datetime'].date()
                key = (sched['employee_id'], sched_date)
                if key not in core_schedules:
                    core_schedules[key] = []
                core_schedules[key].append(sched)

        # Check each date in range
        gaps = []
        current_date = start_date
        while current_date <= end_date:
            day_of_week = current_date.weekday()

            # Check for schedule exception first
            exception_employee = None
            if self.ScheduleException:
                exception = self.db.query(self.ScheduleException).filter_by(
                    exception_date=current_date,
                    rotation_type='primary_lead'
                ).first()
                if exception:
                    exception_employee = exception.employee_id

            # Determine who should have Core event
            expected_employee = exception_employee or rotation_map.get(day_of_week)

            if expected_employee:
                # Check if this employee has Core event scheduled
                if (expected_employee, current_date) not in core_schedules:
                    employee = self.db.query(self.Employee).get(expected_employee)
                    gaps.append({
                        'date': current_date.isoformat(),
                        'day_of_week': current_date.strftime('%A'),
                        'employee_id': expected_employee,
                        'employee_name': employee.name if employee else 'Unknown',
                        'rotation_type': 'primary_lead',
                        'is_exception': exception_employee is not None
                    })

            current_date += timedelta(days=1)

        if gaps:
            warnings.append({
                'severity': 'warning',
                'type': 'rotation_coverage_gaps',
                'category': 'Rotation Coverage',
                'message': f'{len(gaps)} day(s) where primary lead has no Core event scheduled',
                'details': gaps,
                'action': 'Review if Core events should be scheduled for these rotation days'
            })

        return warnings

    def _check_supervisor_pairing(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """
        Check Supervisor event pairing with Core events (WARNING level)

        NOTE: Only works post-approval mode (include_pending=False)
        Supervisor events are created during the approval process, not before.

        Validates:
        - Supervisor events have matching Core events
        - Supervisor events scheduled on same date as Core events
        - Core events have corresponding Supervisor events (if needed)

        This is WARNING level because:
        1. Supervisor events are auto-created during approval
        2. Pairing logic may have legitimate reasons for mismatches
        3. Some Core events might not require Supervisor events

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of warning dicts
        """
        warnings = []

        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)

        # Get all Supervisor events in date range
        supervisor_events = self.db.query(self.Event).filter(
            self.Event.event_type == 'Supervisor',
            self.Event.start_datetime >= start_datetime,
            self.Event.start_datetime <= end_datetime
        ).all()

        unpaired_supervisor = []
        mismatched_dates = []

        for sup_event in supervisor_events:
            # Extract event number from Supervisor event name
            match = re.search(r'\d{6}', sup_event.project_name)
            if not match:
                unpaired_supervisor.append({
                    'supervisor_ref': sup_event.project_ref_num,
                    'supervisor_name': sup_event.project_name,
                    'reason': 'Cannot extract event number from name'
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
                            'supervisor_name': sup_event.project_name,
                            'supervisor_date': sup_schedule.schedule_datetime.date().isoformat(),
                            'core_ref': core_event.project_ref_num,
                            'core_name': core_event.project_name,
                            'core_date': core_schedule.schedule_datetime.date().isoformat()
                        })

        if unpaired_supervisor:
            warnings.append({
                'severity': 'warning',
                'type': 'unpaired_supervisor',
                'category': 'Event Pairing',
                'message': f'{len(unpaired_supervisor)} Supervisor event(s) without matching Core events',
                'details': unpaired_supervisor,
                'action': 'Verify Core events exist or adjust Supervisor events'
            })

        if mismatched_dates:
            warnings.append({
                'severity': 'warning',
                'type': 'supervisor_date_mismatch',
                'category': 'Event Pairing',
                'message': f'{len(mismatched_dates)} Supervisor event(s) scheduled on different date than Core',
                'details': mismatched_dates,
                'action': 'Consider rescheduling Supervisor events to match Core event dates'
            })

        return warnings

    def _calculate_stats(
        self,
        start_date: date,
        end_date: date,
        include_pending: bool = False,
        run_id: Optional[int] = None
    ) -> Dict:
        """
        Calculate summary statistics for verification report

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_pending: Include pending schedules
            run_id: Scheduler run ID (if checking pending)

        Returns:
            Statistics dict
        """
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)

        # Count committed schedules
        committed_count = self.db.query(func.count(self.Schedule.id)).filter(
            self.Schedule.schedule_datetime >= start_datetime,
            self.Schedule.schedule_datetime <= end_datetime
        ).scalar()

        # Count pending schedules
        pending_count = 0
        if include_pending and run_id and self.PendingSchedule:
            pending_count = self.db.query(func.count(self.PendingSchedule.id)).filter(
                self.PendingSchedule.scheduler_run_id == run_id,
                self.PendingSchedule.status.in_(['proposed', 'user_edited']),
                self.PendingSchedule.failure_reason.is_(None)
            ).scalar()

        # Get unique employees and events
        all_schedules = self._get_combined_schedules(
            start_date, end_date, include_pending, run_id
        )

        unique_employees = len(set(s['employee_id'] for s in all_schedules))
        unique_events = len(set(s['event_ref_num'] for s in all_schedules))

        # Calculate date range span
        date_range_days = (end_date - start_date).days + 1

        return {
            'total_schedules': committed_count + pending_count,
            'committed_schedules': committed_count,
            'pending_schedules': pending_count,
            'unique_employees': unique_employees,
            'unique_events': unique_events,
            'date_range_days': date_range_days,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }

    def quick_conflict_check(
        self,
        employee_id: str,
        schedule_datetime: datetime,
        event_ref_num: int
    ) -> Dict:
        """
        Fast conflict check for single schedule (used during approval)

        Performs a quick check for scheduling conflicts immediately before
        API submission to catch race conditions where schedules were approved
        concurrently.

        Checks:
        - Double-booking with recently approved schedules
        - Time-off conflicts

        Args:
            employee_id: Employee to check
            schedule_datetime: Proposed schedule datetime
            event_ref_num: Event being scheduled

        Returns:
            {
                'has_conflict': bool,
                'conflict_type': str or None ('double_booking', 'time_off'),
                'conflict_details': dict or None
            }
        """
        # Get event duration
        event = self.db.query(self.Event).filter_by(
            project_ref_num=event_ref_num
        ).first()

        if not event:
            return {
                'has_conflict': False,
                'conflict_type': None,
                'conflict_details': None
            }

        duration_minutes = event.estimated_time or event.get_default_duration(event.event_type)
        end_datetime = schedule_datetime + timedelta(minutes=duration_minutes)

        # Check 1: Double-booking with existing schedules
        # Find overlapping schedules for this employee
        existing_schedules = self.db.query(self.Schedule, self.Event).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            self.Schedule.employee_id == employee_id
        ).all()

        for existing_sched, existing_event in existing_schedules:
            existing_start = existing_sched.schedule_datetime
            existing_duration = existing_event.estimated_time or existing_event.get_default_duration(existing_event.event_type)
            existing_end = existing_start + timedelta(minutes=existing_duration)

            # Check for overlap
            if schedule_datetime < existing_end and end_datetime > existing_start:
                # Exception: Club Supervisor can have multiple Supervisor events
                employee = self.db.query(self.Employee).get(employee_id)
                if (employee and employee.job_title == 'Club Supervisor' and
                    event.event_type == 'Supervisor' and
                    existing_event.event_type == 'Supervisor'):
                    continue  # Allowed

                return {
                    'has_conflict': True,
                    'conflict_type': 'double_booking',
                    'conflict_details': {
                        'existing_event_ref': existing_sched.event_ref_num,
                        'existing_event_name': existing_event.project_name,
                        'existing_time': f"{existing_start.strftime('%Y-%m-%d %H:%M')} - {existing_end.strftime('%H:%M')}"
                    }
                }

        # Check 2: Time-off conflict
        schedule_date = schedule_datetime.date()
        time_off = self.db.query(self.EmployeeTimeOff).filter(
            self.EmployeeTimeOff.employee_id == employee_id,
            self.EmployeeTimeOff.start_date <= schedule_date,
            self.EmployeeTimeOff.end_date >= schedule_date
        ).first()

        if time_off:
            return {
                'has_conflict': True,
                'conflict_type': 'time_off',
                'conflict_details': {
                    'time_off_reason': time_off.reason,
                    'time_off_range': f"{time_off.start_date} to {time_off.end_date}"
                }
            }

        # No conflicts found
        return {
            'has_conflict': False,
            'conflict_type': None,
            'conflict_details': None
        }

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    def _count_events(self, verify_date: date) -> int:
        """Count total events scheduled for the date"""
        return self.db.query(self.Schedule).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date
        ).count()

    def _count_employees(self, verify_date: date) -> int:
        """Count total employees scheduled for the date"""
        return self.db.query(self.Schedule.employee_id).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date
        ).distinct().count()

    def _format_time(self, time_str: str) -> str:
        """Format time string (HH:MM:SS) to readable format (HH:MM AM/PM)"""
        try:
            t = datetime.strptime(time_str, '%H:%M:%S').time()
            return self._format_time_obj(t)
        except:
            return time_str

    def _format_time_obj(self, time_obj: time) -> str:
        """Format time object to readable format (HH:MM AM/PM)"""
        hour = time_obj.hour
        minute = time_obj.minute
        ampm = 'AM' if hour < 12 else 'PM'
        display_hour = hour if hour <= 12 else hour - 12
        display_hour = 12 if display_hour == 0 else display_hour
        return f"{display_hour}:{minute:02d} {ampm}"
