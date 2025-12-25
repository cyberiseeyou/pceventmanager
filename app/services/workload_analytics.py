"""
Workload Analytics Service

Provides workload data aggregation for employee scheduling dashboard.
Calculates event counts, total hours, and workload status per employee.

Epic 2, Story 2.5: Create Workload Dashboard Backend API

Author: BMAD System
Created: 2025-10-14
"""

from sqlalchemy import func, and_
from datetime import datetime, date


class WorkloadAnalytics:
    """
    Service for analyzing employee workload across date ranges.

    This service aggregates scheduling data to provide insights into
    employee workload distribution, helping supervisors balance scheduling
    fairly across their team.
    """

    def __init__(self, db_session):
        """
        Initialize WorkloadAnalytics service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def get_workload_data(self, start_date, end_date):
        """
        Aggregate employee workload for given date range.

        Queries the database to calculate:
        - Number of scheduled events per employee
        - Total hours scheduled per employee
        - Workload status (normal/high/overloaded)

        Results are sorted by event count (highest workload first) and
        only include active employees.

        Args:
            start_date (date): Start of date range (inclusive)
            end_date (date): End of date range (inclusive)

        Returns:
            dict: Workload data with structure:
                {
                    "employees": [
                        {
                            "id": 123,
                            "name": "John Doe",
                            "event_count": 15,
                            "total_hours": 42.5,
                            "status": "normal"|"high"|"overloaded"
                        }
                    ],
                    "thresholds": {
                        "normal_max_events": 12,
                        "high_max_events": 18,
                        "overload_max_events": 20
                    }
                }
        """
        from models import Employee, Schedule, Event

        # Query: Group schedules by employee, count events, sum hours
        workload_query = self.db.session.query(
            Employee.id,
            Employee.name,
            func.count(Schedule.id).label('event_count'),
            func.sum(Event.estimated_time / 60.0).label('total_hours')  # Convert minutes to hours
        ).join(
            Schedule, Employee.id == Schedule.employee_id
        ).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            and_(
                Employee.is_active == True,
                func.date(Schedule.schedule_datetime) >= start_date,
                func.date(Schedule.schedule_datetime) <= end_date
            )
        ).group_by(
            Employee.id, Employee.name
        ).order_by(
            func.count(Schedule.id).desc()  # Sort by event count descending
        ).all()

        # Calculate status for each employee
        employees = []
        for emp_id, emp_name, event_count, total_hours in workload_query:
            status = self._calculate_status(event_count)
            employees.append({
                'id': emp_id,
                'name': emp_name,
                'event_count': event_count,
                'total_hours': round(total_hours or 0, 1),  # Handle null, round to 1 decimal
                'status': status
            })

        return {
            'employees': employees,
            'thresholds': {
                'normal_max_events': 12,
                'high_max_events': 18,
                'overload_max_events': 20
            }
        }

    def _calculate_status(self, event_count):
        """
        Calculate workload status based on event count.

        Thresholds:
        - normal: <= 12 events/week
        - high: 13-18 events/week
        - overloaded: >= 19 events/week

        Args:
            event_count (int): Number of events scheduled for employee

        Returns:
            str: Status code ('normal', 'high', or 'overloaded')
        """
        if event_count <= 12:
            return 'normal'
        elif event_count <= 18:
            return 'high'
        else:
            return 'overloaded'
