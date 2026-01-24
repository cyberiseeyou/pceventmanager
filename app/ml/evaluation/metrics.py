"""
Metrics tracking and evaluation for ML models.

Tracks model performance, business impact KPIs, and provides
monitoring dashboards.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class MLMetricsTracker:
    """Track ML model performance and business impact metrics."""

    def __init__(self, db_session, models):
        """
        Initialize metrics tracker.

        Args:
            db_session: SQLAlchemy database session
            models: Model registry from get_models()
        """
        self.db = db_session
        self.models = models

        # In-memory metrics for current session
        self.session_metrics = defaultdict(list)

    def track_employee_ranking_prediction(
        self,
        event_ref_num: str,
        employee_id: int,
        ml_confidence: float,
        ml_rank: int,
        rule_rank: int,
        actual_outcome: Optional[str] = None
    ):
        """
        Track an employee ranking prediction.

        Args:
            event_ref_num: Event reference number
            employee_id: Employee ID
            ml_confidence: ML confidence score
            ml_rank: ML ranking position
            rule_rank: Rule-based ranking position
            actual_outcome: Actual outcome ('success' or 'failure') when known
        """
        self.session_metrics['employee_rankings'].append({
            'timestamp': datetime.now(),
            'event_ref_num': event_ref_num,
            'employee_id': employee_id,
            'ml_confidence': ml_confidence,
            'ml_rank': ml_rank,
            'rule_rank': rule_rank,
            'actual_outcome': actual_outcome
        })

    def calculate_scheduler_success_rate(
        self,
        start_date: datetime,
        end_date: datetime,
        use_ml: Optional[bool] = None
    ) -> Dict[str, float]:
        """
        Calculate scheduler success rate metrics.

        Args:
            start_date: Start of measurement window
            end_date: End of measurement window
            use_ml: Filter by ML usage (None = all runs)

        Returns:
            Dictionary of metrics
        """
        SchedulerRunHistory = self.models['SchedulerRunHistory']

        query = self.db.query(SchedulerRunHistory).filter(
            SchedulerRunHistory.started_at >= start_date,
            SchedulerRunHistory.started_at < end_date
        )

        # Filter by ML usage if specified
        if use_ml is not None:
            # This would require adding a use_ml field to SchedulerRunHistory
            # For now, we'll skip this filter
            pass

        runs = query.all()

        if not runs:
            return {'success_rate': 0.0, 'total_runs': 0}

        total_runs = len(runs)
        successful_runs = sum(1 for run in runs if run.status == 'completed')

        # Calculate average events scheduled
        total_scheduled = sum(run.events_scheduled for run in runs if run.events_scheduled)
        total_failed = sum(run.events_failed for run in runs if run.events_failed)

        return {
            'success_rate': successful_runs / total_runs if total_runs > 0 else 0.0,
            'total_runs': total_runs,
            'successful_runs': successful_runs,
            'failed_runs': total_runs - successful_runs,
            'avg_events_scheduled': total_scheduled / total_runs if total_runs > 0 else 0.0,
            'avg_events_failed': total_failed / total_runs if total_runs > 0 else 0.0,
            'total_events_scheduled': total_scheduled,
            'total_events_failed': total_failed
        }

    def calculate_bumping_efficiency(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, float]:
        """
        Calculate bumping efficiency metrics.

        Args:
            start_date: Start of measurement window
            end_date: End of measurement window

        Returns:
            Dictionary of bumping metrics
        """
        PendingSchedule = self.models['PendingSchedule']

        # Find all bumped events
        bumped_events = self.db.query(PendingSchedule).filter(
            PendingSchedule.created_at >= start_date,
            PendingSchedule.created_at < end_date,
            PendingSchedule.is_swap == True,
            PendingSchedule.bumped_event_ref_num.isnot(None)
        ).all()

        if not bumped_events:
            return {
                'bump_reschedule_rate': 0.0,
                'total_bumps': 0,
                'rescheduled_count': 0,
                'avg_days_to_reschedule': 0.0
            }

        total_bumps = len(bumped_events)
        rescheduled_count = 0
        total_days_to_reschedule = 0

        for bump in bumped_events:
            # Check if the bumped event was rescheduled
            rescheduled = self.db.query(PendingSchedule).filter(
                PendingSchedule.event_ref_num == bump.bumped_event_ref_num,
                PendingSchedule.created_at > bump.created_at,
                PendingSchedule.status.in_(['pending_approval', 'approved', 'posted'])
            ).first()

            if rescheduled:
                rescheduled_count += 1
                days = (rescheduled.created_at - bump.created_at).days
                total_days_to_reschedule += days

        return {
            'bump_reschedule_rate': rescheduled_count / total_bumps if total_bumps > 0 else 0.0,
            'total_bumps': total_bumps,
            'rescheduled_count': rescheduled_count,
            'avg_days_to_reschedule': total_days_to_reschedule / rescheduled_count if rescheduled_count > 0 else 0.0
        }

    def calculate_workload_balance(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, float]:
        """
        Calculate workload balance metrics.

        Args:
            start_date: Start of measurement window
            end_date: End of measurement window

        Returns:
            Dictionary of workload metrics
        """
        Schedule = self.models['Schedule']
        Employee = self.models['Employee']

        # Get active employees
        active_employees = self.db.query(Employee).filter(
            Employee.is_active == True
        ).all()

        if not active_employees:
            return {
                'workload_std_dev': 0.0,
                'workload_balance_score': 1.0,
                'min_events': 0,
                'max_events': 0,
                'avg_events': 0.0
            }

        # Count events per employee
        events_per_employee = []

        for emp in active_employees:
            event_count = self.db.query(Schedule).filter(
                Schedule.employee_id == emp.id,
                Schedule.schedule_datetime >= start_date,
                Schedule.schedule_datetime < end_date
            ).count()
            events_per_employee.append(event_count)

        if not events_per_employee:
            return {
                'workload_std_dev': 0.0,
                'workload_balance_score': 1.0,
                'min_events': 0,
                'max_events': 0,
                'avg_events': 0.0
            }

        # Calculate statistics
        import numpy as np
        std_dev = np.std(events_per_employee)
        mean_events = np.mean(events_per_employee)

        # Balance score: 1.0 = perfect balance, lower = more imbalanced
        balance_score = 1.0 / (1.0 + std_dev / max(mean_events, 1))

        return {
            'workload_std_dev': float(std_dev),
            'workload_balance_score': float(balance_score),
            'min_events': int(np.min(events_per_employee)),
            'max_events': int(np.max(events_per_employee)),
            'avg_events': float(mean_events)
        }

    def compare_ml_vs_rules(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Dict[str, float]]:
        """
        Compare ML performance against rule-based baseline.

        Args:
            start_date: Start of comparison window
            end_date: End of comparison window

        Returns:
            Dictionary comparing ML vs rules metrics
        """
        # Get metrics for ML-enabled runs (would need ML flag in SchedulerRunHistory)
        # For now, return placeholder comparison

        return {
            'ml': {
                'success_rate': 0.0,
                'avg_events_scheduled': 0.0,
                'bump_efficiency': 0.0
            },
            'rules': {
                'success_rate': 0.0,
                'avg_events_scheduled': 0.0,
                'bump_efficiency': 0.0
            },
            'improvement': {
                'success_rate_delta': 0.0,
                'events_scheduled_delta': 0.0,
                'bump_efficiency_delta': 0.0
            }
        }

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get summary of metrics tracked in current session.

        Returns:
            Dictionary of session metrics
        """
        summary = {}

        # Employee ranking predictions
        rankings = self.session_metrics.get('employee_rankings', [])
        if rankings:
            summary['employee_rankings'] = {
                'total_predictions': len(rankings),
                'avg_ml_confidence': sum(r['ml_confidence'] for r in rankings) / len(rankings),
                'rank_changes': sum(1 for r in rankings if r['ml_rank'] != r['rule_rank']),
                'successful_outcomes': sum(1 for r in rankings if r.get('actual_outcome') == 'success')
            }

        return summary

    def generate_dashboard_data(
        self,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate data for ML monitoring dashboard.

        Args:
            lookback_days: Number of days to look back

        Returns:
            Dictionary of dashboard data
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        dashboard = {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': lookback_days
            },
            'scheduler_performance': self.calculate_scheduler_success_rate(start_date, end_date),
            'bumping_metrics': self.calculate_bumping_efficiency(start_date, end_date),
            'workload_balance': self.calculate_workload_balance(start_date, end_date),
            'ml_vs_rules': self.compare_ml_vs_rules(start_date, end_date),
            'session_metrics': self.get_session_summary()
        }

        return dashboard
