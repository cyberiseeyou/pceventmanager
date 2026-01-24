"""
Machine Learning module for predictive scheduling.

This module provides ML-enhanced decision making for the auto-scheduler:
- Employee ranking based on predicted assignment success
- Bumping decision optimization
- Schedule feasibility prediction

The ML module integrates with the existing SchedulingEngine via MLSchedulerAdapter,
with graceful fallback to rule-based logic on any failure.
"""

__version__ = "0.1.0"
