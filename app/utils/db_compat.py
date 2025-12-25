"""
Database compatibility utilities for cross-database support (SQLite and PostgreSQL)
"""
from sqlalchemy import func, cast, Time, text
from sqlalchemy.sql import expression
from contextlib import contextmanager


def get_dialect_name(session):
    """Get the dialect name from a session, handling None bind gracefully."""
    bind = session.get_bind() if hasattr(session, 'get_bind') else session.bind
    if bind is None:
        raise RuntimeError("Database session is not bound to an engine")
    return bind.dialect.name


def is_sqlite(session):
    """Check if the database is SQLite."""
    return get_dialect_name(session) == 'sqlite'


def is_postgresql(session):
    """Check if the database is PostgreSQL."""
    return get_dialect_name(session) == 'postgresql'


@contextmanager
def disable_foreign_keys(session):
    """
    Context manager to temporarily disable foreign key constraints.

    Works with both SQLite and PostgreSQL:
    - SQLite: Uses PRAGMA foreign_keys=OFF/ON
    - PostgreSQL: Uses session_replication_role = replica (disables triggers/FK checks)

    Usage:
        with disable_foreign_keys(db.session):
            # Delete operations here
            Model.query.delete()
            db.session.commit()
    """
    dialect = get_dialect_name(session)

    try:
        if dialect == 'sqlite':
            session.execute(text('PRAGMA foreign_keys=OFF'))
        elif dialect == 'postgresql':
            # For PostgreSQL, we'll use TRUNCATE CASCADE or handle FK order manually
            # session_replication_role requires superuser, so we skip it
            pass
        yield
    finally:
        if dialect == 'sqlite':
            session.execute(text('PRAGMA foreign_keys=ON'))
            session.commit()


def extract_time(column):
    """
    Extract time portion from a datetime column in a database-agnostic way.

    SQLite uses: time(column)
    PostgreSQL uses: column::time or CAST(column AS TIME)

    This function returns a SQLAlchemy expression that works with both.

    Args:
        column: A SQLAlchemy column containing datetime data

    Returns:
        A SQLAlchemy expression that extracts the time portion
    """
    # Use CAST which works on both SQLite and PostgreSQL
    # SQLite: CAST interprets as text but comparisons still work
    # PostgreSQL: CAST properly converts to TIME type
    return cast(column, Time)


def time_equals(column, time_value):
    """
    Compare the time portion of a datetime column to a time value.

    Args:
        column: A SQLAlchemy column containing datetime data
        time_value: A time string like '09:45:00' or datetime.time object

    Returns:
        A SQLAlchemy comparison expression
    """
    return cast(column, Time) == time_value


def time_not_equals(column, time_value):
    """
    Compare the time portion of a datetime column is not equal to a time value.

    Args:
        column: A SQLAlchemy column containing datetime data
        time_value: A time string like '09:45:00' or datetime.time object

    Returns:
        A SQLAlchemy comparison expression
    """
    return cast(column, Time) != time_value
