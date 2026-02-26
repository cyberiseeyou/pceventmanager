"""Timezone conversion utilities for displaying UTC datetimes in local time."""

import re
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=8)
def _get_tz(tz_name):
    return ZoneInfo(tz_name)


def to_local_time(dt, fmt='%m/%d/%Y %I:%M %p', tz_name=None):
    """Convert a naive UTC datetime to local time and format it.

    Args:
        dt: A naive datetime assumed to be UTC, or None.
        fmt: strftime format string.
        tz_name: IANA timezone name. Falls back to app config or Indianapolis.

    Returns:
        Formatted local time string, or '' if dt is None.
    """
    if dt is None:
        return ''
    if tz_name is None:
        from flask import current_app
        tz_name = current_app.config.get(
            'EXTERNAL_API_TIMEZONE', 'America/Indiana/Indianapolis'
        )
    local_tz = _get_tz(tz_name)
    utc_dt = dt.replace(tzinfo=timezone.utc)
    local_dt = utc_dt.astimezone(local_tz)
    formatted = local_dt.strftime(fmt)
    # Strip leading zeros from month, day, and hour only (not minutes or year)
    formatted = re.sub(r'(?<![:\d])0(\d)', r'\1', formatted)
    return formatted
