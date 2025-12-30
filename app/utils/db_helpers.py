"""
Database helper utilities for Flask Schedule Webapp
Provides optimized query patterns and database access helpers
"""
from datetime import datetime, date, time, timedelta
from typing import Tuple, Dict, Any
from flask import current_app
from functools import wraps


def get_models(app=None) -> Dict[str, Any]:
    """
    Helper to get all models at once from model registry.

    This function now uses the new model registry pattern instead of app.config.
    Provides backward compatibility by returning the same structure.

    Args:
        app: Flask app instance (optional, uses current_app if not provided)

    Returns:
        dict: Dictionary with db instance and all model classes

    Example:
        >>> m = get_models()
        >>> employee = m['db'].session.query(m['Employee']).first()
        >>> # Or use directly:
        >>> employee = m['Employee'].query.first()
    """
    if app is None:
        app = current_app

    # Get models from registry
    from app.models import get_models as registry_get_models
    models = registry_get_models()

    # Return with db instance for backward compatibility
    result = {'db': app.extensions['sqlalchemy']}
    result.update(models)

    return result


def with_models(f):
    """
    Decorator that injects models as first parameter after self/cls

    Reduces boilerplate in route handlers and service functions.

    Usage:
        @api_bp.route('/schedules')
        @with_models
        def get_schedules(models):
            schedules = models['Schedule'].query.all()
            return jsonify([...])

        # For class methods:
        class MyService:
            @with_models
            def process(self, models):
                employee = models['Employee'].query.first()

    Args:
        f: Function to decorate

    Returns:
        Decorated function with models injected
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        models = get_models()
        return f(models, *args, **kwargs)
    return decorated


def get_date_range(target_date: date) -> Tuple[datetime, datetime]:
    """
    Convert a date to a datetime range for efficient database queries.

    This is more efficient than using func.date() which prevents index usage.

    Args:
        target_date: Date to convert to range

    Returns:
        tuple: (start_datetime, end_datetime) covering the full day

    Example:
        >>> start, end = get_date_range(date(2025, 10, 15))
        >>> # Use in query: .filter(Schedule.schedule_datetime >= start,
        >>>                         Schedule.schedule_datetime < end)
    """
    date_start = datetime.combine(target_date, time.min)  # 00:00:00
    date_end = datetime.combine(target_date, time.max)    # 23:59:59.999999

    # Add 1 microsecond to handle exclusive upper bound
    date_end = date_end + timedelta(microseconds=1)

    return date_start, date_end


def get_schedules_with_relations(
    filters: Dict[str, Any] = None,
    include_employee: bool = True,
    include_event: bool = True,
    date_range: Tuple[datetime, datetime] = None
):
    """
    Optimized schedule query with eager loading to prevent N+1 queries

    This function uses SQLAlchemy's joinedload to fetch related entities
    in a single query, avoiding the N+1 query problem.

    Args:
        filters: Dictionary of filter conditions (e.g., {'employee_id': 'EMP001'})
        include_employee: Whether to eager-load employee data
        include_event: Whether to eager-load event data
        date_range: Optional tuple of (start_datetime, end_datetime) for filtering

    Returns:
        SQLAlchemy query object ready for execution

    Example:
        >>> # Instead of this (N+1 queries):
        >>> schedules = Schedule.query.filter_by(employee_id='EMP001').all()
        >>> for s in schedules:
        >>>     print(s.event.project_name)  # Each access = 1 query!

        >>> # Use this (1-2 queries total):
        >>> query = get_schedules_with_relations({'employee_id': 'EMP001'})
        >>> schedules = query.all()
        >>> for s in schedules:
        >>>     print(s.event.project_name)  # No extra queries!
    """
    from sqlalchemy.orm import joinedload
    models = get_models()
    Schedule = models['Schedule']

    query = Schedule.query

    # Apply eager loading based on parameters
    if include_employee:
        query = query.options(joinedload(Schedule.employee))
    if include_event:
        query = query.options(joinedload(Schedule.event))

    # Apply filters
    if filters:
        query = query.filter_by(**filters)

    # Apply date range filter if provided
    if date_range:
        start_dt, end_dt = date_range
        query = query.filter(
            Schedule.schedule_datetime >= start_dt,
            Schedule.schedule_datetime < end_dt
        )

    return query


def get_events_for_date_range(
    start_date: date,
    end_date: date,
    scheduled_only: bool = None,
    event_type: str = None
):
    """
    Optimized event query for date ranges with common filters

    Args:
        start_date: Start date for event range
        end_date: End date for event range
        scheduled_only: Filter by scheduled status (True/False/None for all)
        event_type: Filter by event type (e.g., 'Core', 'Supervisor')

    Returns:
        SQLAlchemy query object

    Example:
        >>> from datetime import date
        >>> events = get_events_for_date_range(
        ...     date(2025, 10, 1),
        ...     date(2025, 10, 31),
        ...     scheduled_only=False,
        ...     event_type='Core'
        ... ).all()
    """
    models = get_models()
    Event = models['Event']

    # Convert dates to datetime ranges for efficient querying
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max) + timedelta(microseconds=1)

    query = Event.query.filter(
        Event.start_datetime >= start_dt,
        Event.due_datetime < end_dt
    )

    if scheduled_only is not None:
        query = query.filter(Event.is_scheduled == scheduled_only)

    if event_type:
        query = query.filter(Event.event_type == event_type)

    return query


def bulk_get_employees_by_ids(employee_ids: list):
    """
    Efficiently fetch multiple employees by ID in a single query

    Args:
        employee_ids: List of employee IDs to fetch

    Returns:
        Dictionary mapping employee_id -> Employee object

    Example:
        >>> emp_ids = ['EMP001', 'EMP002', 'EMP003']
        >>> employees = bulk_get_employees_by_ids(emp_ids)
        >>> print(employees['EMP001'].name)
    """
    if not employee_ids:
        return {}

    models = get_models()
    Employee = models['Employee']

    employees = Employee.query.filter(Employee.id.in_(employee_ids)).all()

    return {emp.id: emp for emp in employees}
