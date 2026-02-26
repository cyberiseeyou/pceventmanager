"""
Validation types and data classes for auto-scheduler constraint checking
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class ConstraintType(str, Enum):
    """Types of scheduling constraints"""
    AVAILABILITY = "availability"
    TIME_OFF = "time_off"
    ROLE = "role"
    DAILY_LIMIT = "daily_limit"
    ALREADY_SCHEDULED = "already_scheduled"
    EVENT_TYPE = "event_type"
    DUE_DATE = "due_date"
    PAST_DATE = "past_date"
    ROTATION = "rotation"


class ConstraintSeverity(str, Enum):
    """Severity levels for constraint violations"""
    HARD = "hard"  # Cannot be violated
    SOFT = "soft"  # Prefer not to violate but can with approval


@dataclass
class ConstraintViolation:
    """Represents a single constraint violation"""
    constraint_type: ConstraintType
    message: str
    severity: ConstraintSeverity
    details: dict = field(default_factory=dict)

    def __str__(self):
        return f"[{self.severity.upper()}] {self.constraint_type.value}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validating a proposed schedule assignment"""
    is_valid: bool
    violations: List[ConstraintViolation] = field(default_factory=list)

    @property
    def hard_violations(self) -> List[ConstraintViolation]:
        """Get only hard constraint violations"""
        return [v for v in self.violations if v.severity == ConstraintSeverity.HARD]

    @property
    def soft_violations(self) -> List[ConstraintViolation]:
        """Get only soft constraint violations"""
        return [v for v in self.violations if v.severity == ConstraintSeverity.SOFT]

    @property
    def has_hard_violations(self) -> bool:
        """Check if there are any hard violations"""
        return len(self.hard_violations) > 0

    def add_violation(self, violation: ConstraintViolation):
        """Add a violation to the result"""
        self.violations.append(violation)
        if violation.severity == ConstraintSeverity.HARD:
            self.is_valid = False


@dataclass
class SwapProposal:
    """Proposal to swap/bump an event to make room for higher priority event"""
    high_priority_event_ref: int
    low_priority_event_ref: int
    reason: str
    employee_id: str
    proposed_date: str  # ISO format date string

    def __str__(self):
        return f"Swap Event {self.low_priority_event_ref} → Event {self.high_priority_event_ref} (Reason: {self.reason})"


@dataclass
class SchedulingDecision:
    """Decision result from scheduling algorithm"""
    event_ref_num: int
    employee_id: Optional[str]
    schedule_datetime: Optional[str]  # ISO format datetime string
    schedule_time: Optional[str]  # HH:MM format
    success: bool
    is_swap: bool = False
    swap_proposal: Optional[SwapProposal] = None
    failure_reason: Optional[str] = None
    validation_result: Optional[ValidationResult] = None
