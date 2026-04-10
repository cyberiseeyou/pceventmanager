"""Conformance tests for spec 00-master-overview.md."""
from unittest.mock import patch

import pytest


def test_m0_default_scheduler_is_greedy(app):
    """Spec: the production scheduler is the greedy engine, not CP-SAT.

    Verified indirectly via the CPSAT_ENABLED config default.
    """
    assert app.config['CPSAT_ENABLED'] is False, (
        "CPSAT_ENABLED must default to False. Greedy is the "
        "production scheduler per the 2026-04-10 rewrite.")
