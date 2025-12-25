"""
Services package for business logic and background tasks
"""

from .validation_types import (
    ValidationResult,
    ConstraintViolation,
    ConstraintType,
    ConstraintSeverity,
    SwapProposal,
    SchedulingDecision
)

from .rotation_manager import RotationManager
from .constraint_validator import ConstraintValidator
from .conflict_resolver import ConflictResolver
from .scheduling_engine import SchedulingEngine

__all__ = [
    # Validation types
    'ValidationResult',
    'ConstraintViolation',
    'ConstraintType',
    'ConstraintSeverity',
    'SwapProposal',
    'SchedulingDecision',
    # Services
    'RotationManager',
    'ConstraintValidator',
    'ConflictResolver',
    'SchedulingEngine',
]
