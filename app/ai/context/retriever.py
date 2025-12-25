"""Retrieve relevant context from database based on query analysis"""

from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
import logging

from sqlalchemy import and_, or_

from ..config import ai_config
from .classifier import QueryAnalysis, QueryType
from app.models.registry import get_models

logger = logging.getLogger(__name__)


@dataclass
class SchedulingContext:
    """Container for all retrieved scheduling context"""
    employees: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    schedules: List[Dict[str, Any]]
    availability: Dict[str, List[Dict[str, Any]]]
    time_off: List[Dict[str, Any]]
    rotations: List[Dict[str, Any]]
    holidays: List[Dict[str, Any]]

    # Metadata
    date_range: tuple
    query_type: str
    retrieved_at: datetime

    def to_prompt_context(self) -> str:
        """Format context for inclusion in LLM prompt"""
        sections = []

        # Date context
        sections.append(f"**Date Range:** {self.date_range[0]} to {self.date_range[1]}")
        sections.append(f"**Current Date:** {datetime.now().strftime('%Y-%m-%d %A')}")

        # Employees
        if self.employees:
            emp_lines = ["**Employees:**"]
            for emp in self.employees[:ai_config.max_employees_in_context]:
                job_title = emp.get('job_title', 'Event Specialist')
                emp_lines.append(
                    f"- {emp['name']} (ID: {emp['id']}) - {job_title}"
                )
            sections.append("\n".join(emp_lines))

        # Events
        if self.events:
            event_lines = ["**Events:**"]
            for evt in self.events[:ai_config.max_events_in_context]:
                event_lines.append(
                    f"- {evt['project_name']} (Ref: {evt['project_ref_num']}) on {evt['date']} - {evt['event_type']} ({evt['condition']})"
                )
            sections.append("\n".join(event_lines))

        # Current Schedules
        if self.schedules:
            sched_lines = ["**Current Schedules:**"]
            for sched in self.schedules[:ai_config.max_schedules_in_context]:
                sched_lines.append(
                    f"- {sched['employee_name']} -> {sched['event_name']} on {sched['date']}"
                )
            sections.append("\n".join(sched_lines))

        # Time Off
        if self.time_off:
            to_lines = ["**Scheduled Time Off:**"]
            for to in self.time_off:
                reason = to.get('reason', 'Time off')
                to_lines.append(
                    f"- {to['employee_name']}: {to['start_date']} to {to['end_date']} ({reason})"
                )
            sections.append("\n".join(to_lines))

        # Holidays
        if self.holidays:
            hol_lines = ["**Company Holidays:**"]
            for hol in self.holidays:
                hol_lines.append(f"- {hol['date']}: {hol['name']}")
            sections.append("\n".join(hol_lines))

        return "\n\n".join(sections)


class ContextRetriever:
    """Retrieve scheduling context from database"""

    def __init__(self, db_session):
        self.db = db_session
        self._models = None

    @property
    def models(self):
        """Lazy load models"""
        if self._models is None:
            self._models = get_models()
        return self._models

    def retrieve(self, analysis: QueryAnalysis) -> SchedulingContext:
        """Retrieve context based on query analysis"""
        start_date, end_date = analysis.date_range

        # Always get basic context
        employees = self._get_employees(analysis.mentioned_employees)
        holidays = self._get_holidays(start_date, end_date)

        # Get context based on query type
        events = []
        schedules = []
        availability = {}
        time_off = []
        rotations = []

        if analysis.query_type in [
            QueryType.AVAILABILITY,
            QueryType.EMPLOYEE_SUGGEST,
            QueryType.SCHEDULE_VIEW
        ]:
            events = self._get_events(start_date, end_date, analysis.mentioned_events)
            schedules = self._get_schedules(start_date, end_date)
            availability = self._get_availability(start_date, end_date)
            time_off = self._get_time_off(start_date, end_date)

        elif analysis.query_type == QueryType.CONFLICT_CHECK:
            schedules = self._get_schedules(start_date, end_date)
            events = self._get_events(start_date, end_date)
            time_off = self._get_time_off(start_date, end_date)

        elif analysis.query_type == QueryType.WORKLOAD_ANALYSIS:
            # Extend date range for workload analysis
            extended_start = start_date - timedelta(days=30)
            schedules = self._get_schedules(extended_start, end_date)

        elif analysis.query_type == QueryType.TIME_OFF_IMPACT:
            schedules = self._get_schedules(start_date, end_date)
            events = self._get_events(start_date, end_date)
            time_off = self._get_time_off(start_date, end_date)

        else:  # GENERAL or unknown
            events = self._get_events(start_date, end_date)
            schedules = self._get_schedules(start_date, end_date)

        return SchedulingContext(
            employees=employees,
            events=events,
            schedules=schedules,
            availability=availability,
            time_off=time_off,
            rotations=rotations,
            holidays=holidays,
            date_range=(start_date, end_date),
            query_type=analysis.query_type.value,
            retrieved_at=datetime.now(),
        )

    def _get_employees(
        self,
        specific_names: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Get employee information"""
        Employee = self.models['Employee']
        query = self.db.query(Employee).filter(Employee.is_active == True)

        if specific_names:
            query = query.filter(Employee.name.in_(specific_names))

        employees = query.all()

        return [
            {
                "id": emp.id,
                "name": emp.name,
                "email": emp.email,
                "job_title": emp.job_title,
                "is_supervisor": emp.is_supervisor,
                "adult_beverage_trained": emp.adult_beverage_trained,
            }
            for emp in employees
        ]

    def _get_events(
        self,
        start_date: date,
        end_date: date,
        specific_events: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Get events in date range"""
        Event = self.models['Event']
        query = self.db.query(Event).filter(
            and_(
                Event.start_datetime >= datetime.combine(start_date, datetime.min.time()),
                Event.start_datetime <= datetime.combine(end_date, datetime.max.time())
            )
        )

        if specific_events:
            query = query.filter(Event.project_name.in_(specific_events))

        events = query.order_by(Event.start_datetime).all()

        return [
            {
                "id": evt.id,
                "project_name": evt.project_name,
                "project_ref_num": evt.project_ref_num,
                "date": evt.start_datetime.date().isoformat(),
                "start_datetime": evt.start_datetime.isoformat(),
                "due_datetime": evt.due_datetime.isoformat(),
                "event_type": evt.event_type,
                "condition": evt.condition,
                "is_scheduled": evt.is_scheduled,
                "store_name": evt.store_name,
                "store_number": evt.store_number,
            }
            for evt in events
        ]

    def _get_schedules(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get schedules in date range"""
        Schedule = self.models['Schedule']
        Event = self.models['Event']

        schedules = self.db.query(Schedule).join(
            Event,
            Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            and_(
                Schedule.schedule_datetime >= datetime.combine(start_date, datetime.min.time()),
                Schedule.schedule_datetime <= datetime.combine(end_date, datetime.max.time())
            )
        ).all()

        return [
            {
                "id": sched.id,
                "employee_id": sched.employee_id,
                "employee_name": sched.employee.name if sched.employee else "Unknown",
                "event_ref_num": sched.event_ref_num,
                "event_name": sched.event.project_name if sched.event else "Unknown",
                "date": sched.schedule_datetime.date().isoformat(),
                "datetime": sched.schedule_datetime.isoformat(),
            }
            for sched in schedules
        ]

    def _get_availability(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get employee availability"""
        EmployeeAvailability = self.models['EmployeeAvailability']
        Employee = self.models['Employee']

        # Get daily availability
        avail_records = self.db.query(EmployeeAvailability).join(
            Employee,
            EmployeeAvailability.employee_id == Employee.id
        ).filter(
            and_(
                EmployeeAvailability.date >= start_date,
                EmployeeAvailability.date <= end_date
            )
        ).all()

        availability = {}
        for record in avail_records:
            emp_name = record.employee.name if hasattr(record, 'employee') and record.employee else str(record.employee_id)
            if emp_name not in availability:
                availability[emp_name] = []
            availability[emp_name].append({
                "date": record.date.isoformat(),
                "available": record.is_available,
                "reason": record.reason if hasattr(record, 'reason') else None,
            })

        return availability

    def _get_time_off(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get time off requests"""
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        Employee = self.models['Employee']

        time_off = self.db.query(EmployeeTimeOff).join(
            Employee,
            EmployeeTimeOff.employee_id == Employee.id
        ).filter(
            or_(
                and_(
                    EmployeeTimeOff.start_date >= start_date,
                    EmployeeTimeOff.start_date <= end_date
                ),
                and_(
                    EmployeeTimeOff.end_date >= start_date,
                    EmployeeTimeOff.end_date <= end_date
                )
            )
        ).all()

        return [
            {
                "employee_id": to.employee_id,
                "employee_name": to.employee.name if hasattr(to, 'employee') and to.employee else str(to.employee_id),
                "start_date": to.start_date.isoformat(),
                "end_date": to.end_date.isoformat(),
                "reason": to.reason if hasattr(to, 'reason') else "Time off",
            }
            for to in time_off
        ]

    def _get_holidays(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get company holidays"""
        CompanyHoliday = self.models['CompanyHoliday']

        holidays = self.db.query(CompanyHoliday).filter(
            and_(
                CompanyHoliday.date >= start_date,
                CompanyHoliday.date <= end_date
            )
        ).all()

        return [
            {
                "date": hol.date.isoformat(),
                "name": hol.name,
            }
            for hol in holidays
        ]
