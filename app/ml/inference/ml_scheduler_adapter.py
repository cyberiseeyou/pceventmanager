"""
ML Scheduler Adapter - Integration layer between ML models and SchedulingEngine.

This adapter provides ML-enhanced decision making for employee ranking,
bumping decisions, and feasibility prediction, with graceful fallback
to rule-based logic on any failure.
"""

import os
import logging
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

from app.ml.models.employee_ranker import EmployeeRanker
from app.ml.features.simple_employee_features import SimpleEmployeeFeatureExtractor
from app.ml.features.event_features import EventFeatureExtractor

logger = logging.getLogger(__name__)


class MLSchedulerAdapter:
    """
    Adapter between SchedulingEngine and ML models.

    Provides:
    - Employee ranking by predicted success probability
    - Bumping cost prediction (future)
    - Schedule feasibility prediction (future)

    All methods have fallback to rule-based logic.
    """

    def __init__(self, db_session, models, config=None):
        """
        Initialize ML adapter.

        Args:
            db_session: SQLAlchemy database session
            models: Model registry from get_models()
            config: Optional configuration dict
        """
        self.db = db_session
        self.models = models
        self.config = config or {}

        # ML feature flags
        self.use_ml = self.config.get('ML_ENABLED', False)
        self.use_employee_ranking = self.config.get('ML_EMPLOYEE_RANKING_ENABLED', True)
        self.use_bump_prediction = self.config.get('ML_BUMP_PREDICTION_ENABLED', False)
        self.use_feasibility = self.config.get('ML_FEASIBILITY_ENABLED', False)

        # Confidence thresholds
        self.confidence_threshold = self.config.get('ML_CONFIDENCE_THRESHOLD', 0.6)

        # Feature extractors (using simple extractor aligned with actual schema)
        self.employee_features = SimpleEmployeeFeatureExtractor(db_session, models)
        self.event_features = EventFeatureExtractor(db_session, models)

        # ML models (lazy-loaded)
        self._employee_ranker = None
        self._bump_predictor = None
        self._feasibility_predictor = None

        # Stats tracking (for shadow mode)
        self.predictions_made = 0
        self.fallbacks_triggered = 0

        logger.info(f"MLSchedulerAdapter initialized (ML enabled: {self.use_ml})")

    @property
    def employee_ranker(self) -> Optional[EmployeeRanker]:
        """Lazy-load employee ranker model."""
        if not self.use_ml or not self.use_employee_ranking:
            return None

        if self._employee_ranker is None:
            try:
                model_path = self.config.get(
                    'ML_EMPLOYEE_RANKER_PATH',
                    'app/ml/models/artifacts/employee_ranker_latest.pkl'
                )

                if not os.path.exists(model_path):
                    logger.warning(f"Employee ranker model not found: {model_path}")
                    return None

                self._employee_ranker = EmployeeRanker.load(model_path)
                logger.info(f"Employee ranker loaded from {model_path}")

            except Exception as e:
                logger.error(f"Failed to load employee ranker: {e}", exc_info=True)
                self._employee_ranker = None

        return self._employee_ranker

    def rank_employees(
        self,
        employees: List,
        event,
        schedule_datetime: datetime
    ) -> List[Tuple[Any, float]]:
        """
        Rank employees by predicted assignment success probability.

        Args:
            employees: List of Employee model instances
            event: Event model instance
            schedule_datetime: Proposed schedule datetime

        Returns:
            List of (employee, confidence_score) tuples, sorted DESC by score.
            If ML fails, returns employees with neutral scores (0.5).
        """
        if not employees:
            return []

        # Attempt ML ranking
        if self.employee_ranker is not None:
            try:
                return self._ml_rank_employees(employees, event, schedule_datetime)
            except Exception as e:
                logger.error(f"ML ranking failed: {e}", exc_info=True)
                self.fallbacks_triggered += 1

        # Fallback: rule-based ranking
        return self._fallback_rank_employees(employees, event, schedule_datetime)

    def _ml_rank_employees(
        self,
        employees: List,
        event,
        schedule_datetime: datetime
    ) -> List[Tuple[Any, float]]:
        """ML-based employee ranking."""
        feature_dicts = []

        # Extract features for each employee
        for employee in employees:
            try:
                features = self.employee_features.extract(
                    employee,
                    event,
                    schedule_datetime
                )
                feature_dicts.append(features)
            except Exception as e:
                logger.warning(f"Feature extraction failed for employee {employee.id}: {e}")
                # Use fallback for this employee
                feature_dicts.append(None)

        # Filter out failed extractions
        valid_indices = [i for i, f in enumerate(feature_dicts) if f is not None]
        valid_features = [feature_dicts[i] for i in valid_indices]
        valid_employees = [employees[i] for i in valid_indices]

        if not valid_features:
            logger.warning("No valid features extracted, falling back")
            return self._fallback_rank_employees(employees, event, schedule_datetime)

        # Get ML rankings
        rankings = self.employee_ranker.rank_employees(valid_features)

        # Map back to employee objects
        ranked_employees = [
            (valid_employees[idx], confidence)
            for idx, confidence in rankings
            if confidence >= self.confidence_threshold
        ]

        # Add employees with failed feature extraction at the end with low confidence
        failed_employees = [employees[i] for i in range(len(employees)) if i not in valid_indices]
        ranked_employees.extend([(emp, 0.3) for emp in failed_employees])

        self.predictions_made += 1

        logger.debug(f"ML ranked {len(ranked_employees)} employees, top confidence: {ranked_employees[0][1]:.3f}")

        return ranked_employees

    def _fallback_rank_employees(
        self,
        employees: List,
        event,
        schedule_datetime: datetime
    ) -> List[Tuple[Any, float]]:
        """
        Rule-based fallback ranking.

        Uses existing SchedulingEngine logic:
        - Leads first
        - Then Specialists
        - Then Juicers (for Specialist work)

        Returns employees with neutral confidence scores.
        """
        # Separate by role
        leads = [emp for emp in employees if emp.role == 'Lead']
        specialists = [emp for emp in employees if emp.role == 'Specialist']
        juicers = [emp for emp in employees if emp.role == 'Juicer']

        # Combine in priority order
        ranked = []

        # Leads get 0.7 confidence
        for emp in leads:
            ranked.append((emp, 0.7))

        # Specialists get 0.6 confidence
        for emp in specialists:
            ranked.append((emp, 0.6))

        # Juicers get 0.5 confidence (only for non-Juicer events)
        if event.event_type != 'Juicer':
            for emp in juicers:
                ranked.append((emp, 0.5))

        return ranked

    def predict_bump_cost(self, event, current_datetime: datetime) -> float:
        """
        Predict cost of bumping an event (higher = more expensive to bump).

        Args:
            event: Event model instance (candidate to be bumped)
            current_datetime: Current datetime

        Returns:
            Bump cost score [0-100]. Higher = avoid bumping.
            Fallback: uses days_until_due as proxy.
        """
        # Placeholder for future implementation
        # Currently uses fallback logic
        if event.due_datetime:
            days_until_due = (event.due_datetime - current_datetime).days
            # Lower days = higher cost (more urgent)
            return max(100 - (days_until_due * 5), 0)
        else:
            return 50  # Neutral cost

    def predict_feasibility(self, event, current_datetime: datetime) -> float:
        """
        Predict probability that event will fail to schedule [0.0-1.0].

        Args:
            event: Event model instance
            current_datetime: Current datetime

        Returns:
            Failure probability [0.0-1.0]. 1.0 = certain failure.
            Fallback: returns 0.1 (optimistic).
        """
        # Placeholder for future implementation
        return 0.1  # Optimistic default

    def get_stats(self) -> Dict[str, Any]:
        """
        Get adapter statistics (for monitoring).

        Returns:
            Dictionary of stats
        """
        return {
            'ml_enabled': self.use_ml,
            'employee_ranking_enabled': self.use_employee_ranking,
            'bump_prediction_enabled': self.use_bump_prediction,
            'feasibility_enabled': self.use_feasibility,
            'employee_ranker_loaded': self._employee_ranker is not None,
            'predictions_made': self.predictions_made,
            'fallbacks_triggered': self.fallbacks_triggered,
            'fallback_rate': self.fallbacks_triggered / max(self.predictions_made, 1)
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self.predictions_made = 0
        self.fallbacks_triggered = 0
