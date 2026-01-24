"""
Weekly Validation Service

Validates schedules across a full week for:
1. Daily validation rules (via ScheduleVerificationService)
2. Cross-day rules (weekly limits, randomization)
3. Additional rules not in daily verification

Implements rules from docs/scheduling_validation_rules.md
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from sqlalchemy import func, and_
from collections import Counter, defaultdict
import logging
import re

from .schedule_verification import ScheduleVerificationService, VerificationIssue, VerificationResult

logger = logging.getLogger(__name__)


@dataclass
class DayValidationSummary:
    """Summary of validation for a single day"""
    date: date
    status: str  # 'pass', 'warning', 'fail'
    critical_count: int
    warning_count: int
    info_count: int
    total_events: int


@dataclass
class WeeklyValidationResult:
    """Results of week-long validation"""
    week_start: date
    week_end: date
    overall_status: str  # 'pass', 'warning', 'fail'
    health_score: int  # 0-100
    daily_summaries: List[DayValidationSummary] = field(default_factory=list)
    daily_results: Dict[str, VerificationResult] = field(default_factory=dict)
    weekly_issues: List[VerificationIssue] = field(default_factory=list)

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'week_start': self.week_start.isoformat(),
            'week_end': self.week_end.isoformat(),
            'overall_status': self.overall_status,
            'health_score': self.health_score,
            'daily_summaries': [
                {
                    'date': s.date.isoformat(),
                    'status': s.status,
                    'critical_count': s.critical_count,
                    'warning_count': s.warning_count,
                    'info_count': s.info_count,
                    'total_events': s.total_events
                }
                for s in self.daily_summaries
            ],
            'daily_results': {
                d: r.to_dict() for d, r in self.daily_results.items()
            },
            'weekly_issues': [issue.to_dict() for issue in self.weekly_issues]
        }


class WeeklyValidationService:
    """
    Validates schedules across a full week

    Combines:
    - Daily validation (via ScheduleVerificationService) for each day
    - Cross-day rules that require week context
    - Health score calculation

    Usage:
        service = WeeklyValidationService(db.session, models)
        result = service.validate_week(start_date)
    """

    # Weekly limits from rules
    MAX_CORE_EVENTS_PER_WEEK = 6  # RULE-018
    MAX_JUICER_PRODUCTION_PER_WEEK = 5  # RULE-019

    def __init__(self, db_session, models: dict):
        """
        Initialize weekly validation service

        Args:
            db_session: SQLAlchemy session for database queries
            models: Dict of model classes (Event, Schedule, Employee, etc.)
        """
        self.db = db_session
        self.models = models
        self.Event = models['Event']
        self.Schedule = models['Schedule']
        self.Employee = models['Employee']
        self.IgnoredValidationIssue = models.get('IgnoredValidationIssue')

        # Use existing daily verification service
        self.daily_verifier = ScheduleVerificationService(db_session, models)

    def _filter_ignored_issues(self, issues: List[VerificationIssue]) -> List[VerificationIssue]:
        """
        Filter out issues that have been ignored by users.

        Args:
            issues: List of validation issues to filter

        Returns:
            List of issues that are not ignored
        """
        if not self.IgnoredValidationIssue:
            return issues

        filtered = []
        for issue in issues:
            # Generate hash for this issue
            issue_hash = self.IgnoredValidationIssue.generate_hash(
                issue.rule_name,
                issue.details
            )

            # Check if ignored (not expired)
            ignored = self.db.query(self.IgnoredValidationIssue).filter(
                self.IgnoredValidationIssue.issue_hash == issue_hash,
                (self.IgnoredValidationIssue.expires_at.is_(None)) |
                (self.IgnoredValidationIssue.expires_at > datetime.now())
            ).first()

            if not ignored:
                filtered.append(issue)

        return filtered

    def validate_week(self, start_date: date) -> WeeklyValidationResult:
        """
        Run comprehensive validation for a week starting from start_date

        Args:
            start_date: First day of the week to validate (inclusive)

        Returns:
            WeeklyValidationResult with all issues found
        """
        week_dates = [start_date + timedelta(days=i) for i in range(7)]
        week_end = week_dates[-1]

        daily_results = {}
        daily_summaries = []
        all_critical = 0
        all_warnings = 0

        # Run daily validation for each day
        for day in week_dates:
            result = self.daily_verifier.verify_schedule(day)

            # Add new daily rules not in existing service
            additional_issues = []
            additional_issues.extend(self._check_duplicate_products(day))
            additional_issues.extend(self._check_juicer_deep_clean_conflict(day))
            additional_issues.extend(self._check_primary_lead_block_1(day))
            additional_issues.extend(self._check_club_supervisor_on_core(day))
            additional_issues.extend(self._check_club_supervisor_on_digital(day))
            additional_issues.extend(self._check_time_slot_distribution(day))

            result.issues.extend(additional_issues)

            # Filter out ignored issues
            result.issues = self._filter_ignored_issues(result.issues)

            # Recompute counts
            critical = sum(1 for i in result.issues if i.severity == 'critical')
            warning = sum(1 for i in result.issues if i.severity == 'warning')
            info = sum(1 for i in result.issues if i.severity == 'info')

            all_critical += critical
            all_warnings += warning

            # Update status based on new counts
            if critical > 0:
                result.status = 'fail'
            elif warning > 0:
                result.status = 'warning'
            else:
                result.status = 'pass'

            daily_results[day.isoformat()] = result
            daily_summaries.append(DayValidationSummary(
                date=day,
                status=result.status,
                critical_count=critical,
                warning_count=warning,
                info_count=info,
                total_events=result.summary.get('total_events', 0)
            ))

        # Run cross-day (weekly) validation rules
        weekly_issues = []
        weekly_issues.extend(self._check_weekly_core_limit(week_dates))
        weekly_issues.extend(self._check_weekly_juicer_limit(week_dates))
        weekly_issues.extend(self._check_schedule_randomization(week_dates))

        # Filter out ignored weekly issues
        weekly_issues = self._filter_ignored_issues(weekly_issues)

        all_critical += sum(1 for i in weekly_issues if i.severity == 'critical')
        all_warnings += sum(1 for i in weekly_issues if i.severity == 'warning')

        # Determine overall status
        if all_critical > 0:
            overall_status = 'fail'
        elif all_warnings > 0:
            overall_status = 'warning'
        else:
            overall_status = 'pass'

        # Calculate health score (0-100)
        health_score = self._calculate_health_score(
            all_critical, all_warnings, daily_summaries
        )

        return WeeklyValidationResult(
            week_start=start_date,
            week_end=week_end,
            overall_status=overall_status,
            health_score=health_score,
            daily_summaries=daily_summaries,
            daily_results=daily_results,
            weekly_issues=weekly_issues
        )

    def _calculate_health_score(
        self,
        critical_count: int,
        warning_count: int,
        daily_summaries: List[DayValidationSummary]
    ) -> int:
        """
        Calculate a health score from 0-100

        Scoring:
        - Start at 100
        - Each critical issue: -10 points
        - Each warning: -3 points
        - Minimum score: 0
        """
        score = 100
        score -= critical_count * 10
        score -= warning_count * 3
        return max(0, min(100, score))

    # ============================================================================
    # ADDITIONAL DAILY RULES (not in existing ScheduleVerificationService)
    # ============================================================================

    def _check_duplicate_products(self, verify_date: date) -> List[VerificationIssue]:
        """
        RULE-020: No same-product events on same day

        Extracts product/brand name from project_name and checks for duplicates
        """
        issues = []

        # Get all Core events scheduled for this date
        schedules = self.db.query(
            self.Schedule, self.Event
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).all()

        # Extract product names and group by product
        product_events = defaultdict(list)
        for schedule, event in schedules:
            product_name = self._extract_product_name(event.project_name)
            if product_name:
                product_events[product_name.upper()].append({
                    'event_id': event.id,
                    'event_name': event.project_name,
                    'schedule_id': schedule.id
                })

        # Check for duplicates
        for product, events in product_events.items():
            if len(events) > 1:
                event_names = [e['event_name'] for e in events]
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Duplicate Product',
                    message=f"Product '{product}' is scheduled multiple times on {verify_date}: {len(events)} events",
                    details={
                        'product': product,
                        'date': verify_date.isoformat(),
                        'events': events,
                        'event_names': event_names
                    }
                ))

        return issues

    def _extract_product_name(self, project_name: str) -> Optional[str]:
        """
        Extract product/brand name from project name

        Examples:
        - "Core - Nurri - Store 123" -> "Nurri"
        - "Core Nurri" -> "Nurri"
        """
        if not project_name:
            return None

        # Common patterns:
        # "Core - PRODUCT - Location" or "Core PRODUCT"
        # Remove common prefixes and extract the product name

        name = project_name.strip()

        # Remove event type prefixes
        prefixes_to_remove = [
            'Core -', 'Core-', 'CORE -', 'CORE-',
            'Core', 'CORE',
            'Sams Club -', 'Sam\'s Club -',
            'SC -', 'SC-'
        ]

        for prefix in prefixes_to_remove:
            if name.upper().startswith(prefix.upper()):
                name = name[len(prefix):].strip()
                break

        # If there's a dash, take the first part (brand name)
        if ' - ' in name:
            name = name.split(' - ')[0].strip()
        elif '-' in name and not name.startswith('-'):
            parts = name.split('-')
            if len(parts[0].strip()) > 2:  # Avoid single letters
                name = parts[0].strip()

        # Clean up
        name = name.strip(' -')

        # Return None if too short or generic
        if len(name) < 2 or name.upper() in ['CORE', 'EVENT', 'DEMO']:
            return None

        return name

    def _check_juicer_deep_clean_conflict(self, verify_date: date) -> List[VerificationIssue]:
        """
        RULE-015: Juicer Deep Clean should not be on a day with Juicer Production
        """
        issues = []

        # Check if both Juicer Deep Clean and Juicer Production exist on same day
        deep_clean_count = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Juicer Deep Clean'
        ).count()

        production_count = self.db.query(self.Schedule).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Juicer Production'
        ).count()

        if deep_clean_count > 0 and production_count > 0:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Juicer Deep Clean Conflict',
                message=f"Juicer Deep Clean and Juicer Production are both scheduled on {verify_date}. Deep Clean should not occur on Production days.",
                details={
                    'date': verify_date.isoformat(),
                    'deep_clean_count': deep_clean_count,
                    'production_count': production_count
                }
            ))

        return issues

    def _check_primary_lead_block_1(self, verify_date: date) -> List[VerificationIssue]:
        """
        RULE-003: Primary Lead Event Specialist should be scheduled for Block 1 (10:15)
        when Core events exist
        """
        issues = []

        # Find Primary Lead Event Specialist
        # Note: MICHELLE MONTAGUE is the designated primary lead
        primary_lead = self.db.query(self.Employee).filter(
            self.Employee.name == 'MICHELLE MONTAGUE',
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).first()
        
        # Fallback to first active Lead Event Specialist if Michelle not found
        if not primary_lead:
            primary_lead = self.db.query(self.Employee).filter(
                self.Employee.job_title == 'Lead Event Specialist',
                self.Employee.is_active == True
            ).order_by(self.Employee.id).first()

        if not primary_lead:
            return issues

        # Check if there are any Core events scheduled for this date
        core_events_exist = self.db.query(
            self.Schedule, self.Event
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).first()

        if not core_events_exist:
            # No Core events this day, skip validation
            return issues

        # Check if Primary Lead is on time off or unavailable this day
        EmployeeTimeOff = self.models.get('EmployeeTimeOff')
        EmployeeAvailability = self.models.get('EmployeeAvailability')
        
        # Check time off
        on_time_off = False
        if EmployeeTimeOff:
            on_time_off = self.db.query(EmployeeTimeOff).filter(
                EmployeeTimeOff.employee_id == primary_lead.id,
                EmployeeTimeOff.start_date <= verify_date,
                EmployeeTimeOff.end_date >= verify_date
            ).first()
        
        # Check availability (is_available = False means day off)
        unavailable = False
        if EmployeeAvailability:
            availability = self.db.query(EmployeeAvailability).filter(
                EmployeeAvailability.employee_id == primary_lead.id,
                EmployeeAvailability.date == verify_date
            ).first()
            if availability and not availability.is_available:
                unavailable = True
        
        # If Primary Lead is on time off or unavailable, skip validation
        if on_time_off or unavailable:
            return issues

        # Check if Primary Lead is working this day (scheduled for ANY event)
        lead_any_schedule = self.db.query(self.Schedule).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Schedule.employee_id == primary_lead.id
        ).first()
        
        # If Primary Lead is not working at all this day, skip validation
        if not lead_any_schedule:
            return issues

        # Check if Primary Lead has a Core event scheduled
        lead_core_schedule = self.db.query(
            self.Schedule, self.Event
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Schedule.employee_id == primary_lead.id,
            self.Event.event_type == 'Core'
        ).first()

        if not lead_core_schedule:
            # Primary Lead is working but not scheduled for Core events
            # Get what they ARE scheduled for
            non_core_schedules = self.db.query(
                self.Schedule, self.Event
            ).join(
                self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
            ).filter(
                func.date(self.Schedule.schedule_datetime) == verify_date,
                self.Schedule.employee_id == primary_lead.id,
                self.Event.event_type != 'Core'
            ).all()
            
            non_core_types = [event.event_type for _, event in non_core_schedules]
            
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Primary Lead Not Scheduled',
                message=f"Primary Lead {primary_lead.name} is working on {verify_date} but not scheduled for Core events. Scheduled for: {', '.join(non_core_types)}. Core events exist and should be assigned to Primary Lead.",
                details={
                    'employee_id': primary_lead.id,
                    'employee_name': primary_lead.name,
                    'date': verify_date.isoformat(),
                    'expected_block': 1,
                    'actual_event_types': non_core_types
                }
            ))
            return issues
        
        # Primary Lead is scheduled for Core, continue to check if it's Block 1
        lead_schedule = lead_core_schedule

        schedule, event = lead_schedule

        # Check if it's Block 1 (10:15 AM)
        # Get Block 1 time from shift block config
        from app.services.shift_block_config import ShiftBlockConfig
        block_1 = ShiftBlockConfig.get_block(1)

        if not block_1:
            # Can't validate without block configuration
            return issues

        block_1_time = block_1['arrive']
        scheduled_time = schedule.schedule_datetime.time()

        # Check if scheduled time matches Block 1 arrive time
        is_block_1_time = (
            scheduled_time.hour == block_1_time.hour and
            scheduled_time.minute == block_1_time.minute
        )

        if not is_block_1_time:
            # Not scheduled for Block 1 time
            actual_time_str = scheduled_time.strftime('%I:%M %p')
            block_1_time_str = block_1_time.strftime('%I:%M %p')

            # Also check shift_block field if available
            actual_block = getattr(schedule, 'shift_block', None)

            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Primary Lead Block Assignment',
                message=f"Primary Lead {primary_lead.name} is scheduled for {actual_time_str} (Block {actual_block or '?'}) instead of Block 1 ({block_1_time_str}) on {verify_date}.",
                details={
                    'employee_id': primary_lead.id,
                    'employee_name': primary_lead.name,
                    'date': verify_date.isoformat(),
                    'actual_block': actual_block,
                    'actual_time': actual_time_str,
                    'expected_block': 1,
                    'expected_time': block_1_time_str
                }
            ))

        return issues

    def _check_club_supervisor_on_core(self, verify_date: date) -> List[VerificationIssue]:
        """
        RULE-022: Club Supervisors should not typically work Core events
        (unless manually approved/exception made)
        """
        issues = []

        # Get all Core events scheduled with Club Supervisors
        supervisor_cores = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core',
            self.Employee.job_title == 'Club Supervisor',
            self.Employee.is_active == True
        ).all()

        for schedule, event, employee in supervisor_cores:
            issues.append(VerificationIssue(
                severity='warning',
                rule_name='Club Supervisor on Core Event',
                message=f"Club Supervisor {employee.name} is scheduled for Core event on {verify_date}. Core events should typically go to Lead Event Specialists.",
                details={
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'job_title': employee.job_title,
                    'date': verify_date.isoformat(),
                    'event_id': event.id,
                    'event_name': event.project_name,
                    'schedule_id': schedule.id
                }
            ))

        return issues

    def _check_club_supervisor_on_digital(self, verify_date: date) -> List[VerificationIssue]:
        """
        RULE-023: Club Supervisors should not work Digital events if Lead Event Specialists
        are available (not scheduled or on time off)
        """
        issues = []

        # Get all Digital events (Digital Setup, Digital Refresh, Digital Teardown)
        digital_types = ['Digital Setup', 'Digital Refresh', 'Digital Teardown']

        # Get Digital events scheduled with Club Supervisors
        supervisor_digitals = self.db.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type.in_(digital_types),
            self.Employee.job_title == 'Club Supervisor',
            self.Employee.is_active == True
        ).all()

        if not supervisor_digitals:
            return issues

        # Check if Lead Event Specialists are available (not scheduled for Core or on time off)
        # Get all active Lead Event Specialists
        lead_specialists = self.db.query(self.Employee).filter(
            self.Employee.job_title == 'Lead Event Specialist',
            self.Employee.is_active == True
        ).all()

        # For each Club Supervisor on Digital, check if any Lead was available
        for schedule, event, supervisor in supervisor_digitals:
            # Check if any Lead Event Specialist was available at this time
            available_leads = []
            for lead in lead_specialists:
                # Check if lead has Core event this day
                has_core = self.db.query(self.Schedule).join(
                    self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
                ).filter(
                    func.date(self.Schedule.schedule_datetime) == verify_date,
                    self.Schedule.employee_id == lead.id,
                    self.Event.event_type == 'Core'
                ).first()

                # Check if lead is on time off
                EmployeeTimeOff = self.models.get('EmployeeTimeOff')
                on_time_off = False
                if EmployeeTimeOff:
                    on_time_off = self.db.query(EmployeeTimeOff).filter(
                        EmployeeTimeOff.employee_id == lead.id,
                        EmployeeTimeOff.start_date <= verify_date,
                        EmployeeTimeOff.end_date >= verify_date
                    ).first()

                if not has_core and not on_time_off:
                    available_leads.append(lead.name)

            # If there were available leads, this is a validation issue
            if available_leads:
                issues.append(VerificationIssue(
                    severity='warning',
                    rule_name='Club Supervisor on Digital Event',
                    message=f"Club Supervisor {supervisor.name} is scheduled for {event.event_type} event on {verify_date}, but Lead Event Specialists were available: {', '.join(available_leads)}",
                    details={
                        'employee_id': supervisor.id,
                        'employee_name': supervisor.name,
                        'job_title': supervisor.job_title,
                        'date': verify_date.isoformat(),
                        'event_id': event.id,
                        'event_name': event.project_name,
                        'event_type': event.event_type,
                        'schedule_id': schedule.id,
                        'available_leads': available_leads
                    }
                ))

        return issues

    def _check_time_slot_distribution(self, verify_date: date) -> List[VerificationIssue]:
        """
        RULE-021: Core events must be distributed correctly across time slots

        Pattern: 2 employees per time slot in order, then repeat
        - Events 1-2: First time slot
        - Events 3-4: Second time slot
        - Events 5-6: Third time slot
        - Events 7-8: Fourth time slot
        - Event 9+: Repeat pattern (add 1 more to each slot in order)

        Valid distributions:
        - 1 event: [1,0,0,0]
        - 2 events: [2,0,0,0]
        - 3 events: [2,1,0,0]
        - 4 events: [2,2,0,0]
        - 8 events: [2,2,2,2]
        - 9 events: [3,2,2,2]
        - 10 events: [3,3,2,2]
        """
        issues = []

        # Get all Core events scheduled for this date with their times
        schedules = self.db.query(
            self.Schedule, self.Event
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) == verify_date,
            self.Event.event_type == 'Core'
        ).order_by(self.Schedule.schedule_datetime).all()

        if len(schedules) == 0:
            return issues

        # Group schedules by time slot (hour:minute)
        from collections import defaultdict
        time_slot_counts = defaultdict(int)
        time_slots_ordered = []

        for schedule, event in schedules:
            time_key = schedule.schedule_datetime.strftime('%H:%M')
            if time_key not in time_slots_ordered:
                time_slots_ordered.append(time_key)
            time_slot_counts[time_key] += 1

        # Get counts in order
        counts = [time_slot_counts[ts] for ts in time_slots_ordered]
        total_events = len(schedules)

        # Validate the distribution pattern
        # Rule: counts should be non-increasing (each slot has >= count than next slot)
        # AND difference between adjacent slots should be at most 1
        # AND the pattern should match the 2-2-2-2 repeating cycle

        is_valid = True
        error_details = []

        for i in range(len(counts) - 1):
            current_count = counts[i]
            next_count = counts[i + 1]

            # Check that earlier slots have >= later slots
            if current_count < next_count:
                is_valid = False
                error_details.append(
                    f"Time slot {time_slots_ordered[i]} has {current_count} events but later slot "
                    f"{time_slots_ordered[i+1]} has {next_count} events"
                )

            # Check that difference is at most 1
            if current_count - next_count > 1:
                is_valid = False
                error_details.append(
                    f"Time slot {time_slots_ordered[i]} has {current_count} events but next slot "
                    f"{time_slots_ordered[i+1]} has only {next_count} events (gap too large)"
                )

        if not is_valid:
            # Build a helpful message
            distribution_str = ", ".join([f"{ts}: {time_slot_counts[ts]}" for ts in time_slots_ordered])

            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Time Slot Distribution',
                message=f"Core events on {verify_date} are not distributed correctly across time slots. "
                        f"Pattern should be 2 per slot in order before repeating. Current: {distribution_str}",
                details={
                    'date': verify_date.isoformat(),
                    'total_events': total_events,
                    'time_slots': time_slots_ordered,
                    'distribution': dict(time_slot_counts),
                    'errors': error_details
                }
            ))

        return issues

    # ============================================================================
    # CROSS-DAY (WEEKLY) VALIDATION RULES
    # ============================================================================

    def _check_weekly_core_limit(self, week_dates: List[date]) -> List[VerificationIssue]:
        """
        RULE-018: Employees cannot have more than 6 Core events per week
        """
        issues = []
        week_start = week_dates[0]
        week_end = week_dates[-1]

        # Get Core event counts per employee for the week
        core_counts = self.db.query(
            self.Employee.id,
            self.Employee.name,
            func.count(self.Schedule.id).label('core_count')
        ).join(
            self.Schedule, self.Employee.id == self.Schedule.employee_id
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) >= week_start,
            func.date(self.Schedule.schedule_datetime) <= week_end,
            self.Event.event_type == 'Core'
        ).group_by(
            self.Employee.id, self.Employee.name
        ).having(
            func.count(self.Schedule.id) > self.MAX_CORE_EVENTS_PER_WEEK
        ).all()

        for employee_id, employee_name, core_count in core_counts:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Weekly Core Event Limit',
                message=f"{employee_name} has {core_count} Core events scheduled for the week ({week_start} to {week_end}). Maximum is {self.MAX_CORE_EVENTS_PER_WEEK}.",
                details={
                    'employee_id': employee_id,
                    'employee_name': employee_name,
                    'core_count': core_count,
                    'max_allowed': self.MAX_CORE_EVENTS_PER_WEEK,
                    'week_start': week_start.isoformat(),
                    'week_end': week_end.isoformat()
                }
            ))

        return issues

    def _check_weekly_juicer_limit(self, week_dates: List[date]) -> List[VerificationIssue]:
        """
        RULE-019: Employees cannot have more than 5 Juicer Production events per week
        """
        issues = []
        week_start = week_dates[0]
        week_end = week_dates[-1]

        # Get Juicer Production counts per employee for the week
        juicer_counts = self.db.query(
            self.Employee.id,
            self.Employee.name,
            func.count(self.Schedule.id).label('juicer_count')
        ).join(
            self.Schedule, self.Employee.id == self.Schedule.employee_id
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) >= week_start,
            func.date(self.Schedule.schedule_datetime) <= week_end,
            self.Event.event_type == 'Juicer Production'
        ).group_by(
            self.Employee.id, self.Employee.name
        ).having(
            func.count(self.Schedule.id) > self.MAX_JUICER_PRODUCTION_PER_WEEK
        ).all()

        for employee_id, employee_name, juicer_count in juicer_counts:
            issues.append(VerificationIssue(
                severity='critical',
                rule_name='Weekly Juicer Production Limit',
                message=f"{employee_name} has {juicer_count} Juicer Production events for the week ({week_start} to {week_end}). Maximum is {self.MAX_JUICER_PRODUCTION_PER_WEEK}.",
                details={
                    'employee_id': employee_id,
                    'employee_name': employee_name,
                    'juicer_count': juicer_count,
                    'max_allowed': self.MAX_JUICER_PRODUCTION_PER_WEEK,
                    'week_start': week_start.isoformat(),
                    'week_end': week_end.isoformat()
                }
            ))

        return issues

    def _check_schedule_randomization(self, week_dates: List[date]) -> List[VerificationIssue]:
        """
        RULE-017: Employees should not consistently get the same scheduled time

        Checks if an employee has the same time slot on 4+ days in the week
        """
        issues = []
        week_start = week_dates[0]
        week_end = week_dates[-1]

        # Get all Core schedules for the week grouped by employee
        schedules = self.db.query(
            self.Schedule, self.Employee
        ).join(
            self.Employee, self.Schedule.employee_id == self.Employee.id
        ).join(
            self.Event, self.Schedule.event_ref_num == self.Event.project_ref_num
        ).filter(
            func.date(self.Schedule.schedule_datetime) >= week_start,
            func.date(self.Schedule.schedule_datetime) <= week_end,
            self.Event.event_type == 'Core'
        ).all()

        # Group by employee and count times
        employee_times = defaultdict(list)
        for schedule, employee in schedules:
            time_slot = schedule.schedule_datetime.strftime('%H:%M')
            employee_times[employee.id].append({
                'name': employee.name,
                'time': time_slot,
                'date': schedule.schedule_datetime.date()
            })

        # Check for repeated times
        for employee_id, times_list in employee_times.items():
            if len(times_list) < 4:
                continue  # Need at least 4 events to check pattern

            time_counts = Counter(t['time'] for t in times_list)
            employee_name = times_list[0]['name']

            for time_slot, count in time_counts.items():
                if count >= 4:  # Same time 4+ times in a week
                    issues.append(VerificationIssue(
                        severity='info',
                        rule_name='Schedule Randomization',
                        message=f"{employee_name} is scheduled at {time_slot} for {count} days this week. Consider varying start times.",
                        details={
                            'employee_id': employee_id,
                            'employee_name': employee_name,
                            'repeated_time': time_slot,
                            'occurrence_count': count,
                            'week_start': week_start.isoformat(),
                            'week_end': week_end.isoformat()
                        }
                    ))

        return issues
