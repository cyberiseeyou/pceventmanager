"""Conformance tests for plan 08 — CP-SAT retirement.

Verifies that CP-SAT has been fully removed from the production code
path: the config flag is gone, the production route instantiates only
the greedy SchedulingEngine, and the deprecated module still exists
but is not imported from production code.
"""
from unittest.mock import patch


def test_cpsat_enabled_flag_removed(app):
    """The CPSAT_ENABLED config flag must be absent after plan 08."""
    assert 'CPSAT_ENABLED' not in app.config, (
        "CPSAT_ENABLED flag must be removed after plan 08"
    )
    assert 'CPSAT_TIME_LIMIT' not in app.config, (
        "CPSAT_TIME_LIMIT flag must be removed after plan 08"
    )


def test_cpsat_engine_not_imported_in_production_route():
    """The auto_scheduler route module source must not reference
    CPSATSchedulingEngine after plan 08 — static import removed."""
    from pathlib import Path
    route_path = Path('app/routes/auto_scheduler.py').resolve()
    source = route_path.read_text()
    assert 'CPSATSchedulingEngine' not in source, (
        'CPSATSchedulingEngine must not be imported from the auto_scheduler '
        'route after plan 08'
    )
    assert 'CPSAT_ENABLED' not in source, (
        'CPSAT_ENABLED config lookup must not appear in the auto_scheduler '
        'route after plan 08'
    )


def test_cpsat_deprecation_notice_present():
    """The cpsat_scheduler module must carry a deprecation notice in its
    docstring pointing at plan 08."""
    import app.services.cpsat_scheduler as cpsat_mod
    doc = cpsat_mod.__doc__ or ''
    assert 'DEPRECATED' in doc, \
        'cpsat_scheduler.py must carry a DEPRECATED notice'
    assert '08-retire-cpsat' in doc, \
        'cpsat_scheduler.py must reference plan 08 in its docstring'
