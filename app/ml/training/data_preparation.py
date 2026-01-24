"""
Data preparation for ML model training.

Extracts training data from historical scheduling records,
ensuring proper temporal splitting to avoid data leakage.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import logging
import pandas as pd
from sqlalchemy import and_, or_

from app.models import get_models, get_db
from app.ml.features.simple_employee_features import SimpleEmployeeFeatureExtractor
from app.ml.features.event_features import EventFeatureExtractor
from app.ml.features.historical_features import HistoricalFeatureExtractor

logger = logging.getLogger(__name__)


class TrainingDataPreparation:
    """Prepare training data from historical scheduling records."""

    def __init__(self, db_session=None, models=None):
        """
        Initialize data preparation.

        Args:
            db_session: Optional database session (will create if not provided)
            models: Optional model registry (will get if not provided)
        """
        if db_session is None:
            db = get_db()
            self.db = db.session
        else:
            self.db = db_session
        self.models = models or get_models()

        self.employee_features = SimpleEmployeeFeatureExtractor(self.db, self.models)
        self.event_features = EventFeatureExtractor(self.db, self.models)
        self.historical_features = HistoricalFeatureExtractor(self.db, self.models)

    def prepare_employee_ranking_data(self, start_date: datetime, end_date: datetime,
                                     min_lookback_days: int = 30) -> pd.DataFrame:
        """
        Prepare training data for employee ranking model.

        Extracts features for each (employee, event, datetime) combination
        from historical PendingSchedule records, with label = success/failure.

        Args:
            start_date: Start of training data window
            end_date: End of training data window
            min_lookback_days: Minimum days of history required before start_date

        Returns:
            DataFrame with features and labels
        """
        logger.info(f"Preparing employee ranking data from {start_date} to {end_date}")

        PendingSchedule = self.models['PendingSchedule']
        Event = self.models['Event']
        Employee = self.models['Employee']

        # Query all pending schedules in date range
        # Success = status in ('api_submitted', 'proposed')
        # Failure = status == 'api_failed'
        pending_schedules = self.db.query(PendingSchedule).filter(
            and_(
                PendingSchedule.created_at >= start_date,
                PendingSchedule.created_at < end_date,
                PendingSchedule.status.in_(['api_submitted', 'proposed', 'api_failed'])
            )
        ).all()

        logger.info(f"Found {len(pending_schedules)} pending schedule records")

        training_records = []

        for ps in pending_schedules:
            try:
                # Skip if missing required data
                if not ps.event or not ps.employee or not ps.schedule_datetime:
                    continue

                # Extract features "as of" the scheduling decision time
                as_of_date = ps.created_at if ps.created_at else ps.schedule_datetime

                # Skip if insufficient lookback history
                if (as_of_date - start_date).days < min_lookback_days:
                    continue

                # Extract features
                features = self.employee_features.extract(
                    ps.employee,
                    ps.event,
                    ps.schedule_datetime
                )

                # Add label (1 = success, 0 = failure)
                features['label'] = 1 if ps.status in ['api_submitted', 'proposed'] else 0

                # Add metadata for analysis
                features['employee_id'] = ps.employee_id
                features['event_ref_num'] = ps.event_ref_num
                features['schedule_datetime'] = ps.schedule_datetime
                features['created_at'] = as_of_date

                training_records.append(features)

            except Exception as e:
                logger.warning(f"Error extracting features for PendingSchedule {ps.id}: {e}")
                continue

        df = pd.DataFrame(training_records)
        logger.info(f"Prepared {len(df)} training records with {df['label'].sum()} successes")

        return df

    def prepare_bumping_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Prepare training data for bumping cost prediction.

        Extracts features for events that were bumped, with label = days to reschedule.

        Args:
            start_date: Start of training data window
            end_date: End of training data window

        Returns:
            DataFrame with features and bump cost labels
        """
        logger.info(f"Preparing bumping data from {start_date} to {end_date}")

        PendingSchedule = self.models['PendingSchedule']
        Event = self.models['Event']

        # Find all bumped events (is_swap = True)
        bumped_schedules = self.db.query(PendingSchedule).filter(
            and_(
                PendingSchedule.created_at >= start_date,
                PendingSchedule.created_at < end_date,
                PendingSchedule.is_swap == True,
                PendingSchedule.bumped_event_ref_num.isnot(None)
            )
        ).all()

        logger.info(f"Found {len(bumped_schedules)} bumped event records")

        training_records = []

        for ps in bumped_schedules:
            try:
                # Get the event that was bumped
                bumped_event = ps.bumped_event
                if not bumped_event:
                    continue

                # Extract features for the bumped event at time of bump
                as_of_date = ps.created_at if ps.created_at else ps.schedule_datetime

                features = self.event_features.extract_for_bumping(
                    bumped_event,
                    as_of_date
                )

                # Calculate bump cost: days until rescheduled
                # Look for when this event was rescheduled
                rescheduled = self.db.query(PendingSchedule).filter(
                    and_(
                        PendingSchedule.event_ref_num == bumped_event.ref_num,
                        PendingSchedule.created_at > as_of_date,
                        PendingSchedule.status.in_(['api_submitted', 'proposed'])
                    )
                ).order_by(PendingSchedule.created_at).first()

                if rescheduled:
                    days_to_reschedule = (rescheduled.created_at - as_of_date).days
                    features['bump_cost_days'] = min(max(days_to_reschedule, 0), 30)  # Cap at 30 days
                    features['was_rescheduled'] = 1
                else:
                    # Not rescheduled within window - high cost
                    features['bump_cost_days'] = 30
                    features['was_rescheduled'] = 0

                # Add metadata
                features['event_ref_num'] = bumped_event.ref_num
                features['bumped_at'] = as_of_date

                training_records.append(features)

            except Exception as e:
                logger.warning(f"Error extracting bumping features for PendingSchedule {ps.id}: {e}")
                continue

        df = pd.DataFrame(training_records)
        logger.info(f"Prepared {len(df)} bumping records")

        return df

    def prepare_feasibility_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Prepare training data for schedule feasibility prediction.

        Extracts features for all events, with label = successfully scheduled or not.

        Args:
            start_date: Start of training data window
            end_date: End of training data window

        Returns:
            DataFrame with features and feasibility labels
        """
        logger.info(f"Preparing feasibility data from {start_date} to {end_date}")

        Event = self.models['Event']
        Schedule = self.models['Schedule']

        # Query all events created in date range
        events = self.db.query(Event).filter(
            and_(
                Event.start_datetime >= start_date,
                Event.start_datetime < end_date,
                Event.is_cancelled == False
            )
        ).all()

        logger.info(f"Found {len(events)} events")

        training_records = []

        for event in events:
            try:
                # Determine if event was successfully scheduled
                scheduled = self.db.query(Schedule).filter(
                    Schedule.event_ref_num == event.ref_num
                ).first()

                # Extract features at event creation time
                as_of_date = event.start_datetime

                features = self.event_features.extract_for_feasibility(
                    event,
                    as_of_date
                )

                # Label: 1 = successfully scheduled, 0 = failed
                features['feasibility_label'] = 1 if scheduled else 0

                # Add metadata
                features['event_ref_num'] = event.ref_num
                features['event_type'] = event.event_type
                features['created_at'] = as_of_date

                training_records.append(features)

            except Exception as e:
                logger.warning(f"Error extracting feasibility features for Event {event.ref_num}: {e}")
                continue

        df = pd.DataFrame(training_records)
        logger.info(f"Prepared {len(df)} feasibility records with {df['feasibility_label'].sum()} successes")

        return df

    def validate_data_quality(self, df: pd.DataFrame, min_samples: int = 100) -> Tuple[bool, str]:
        """
        Validate training data quality.

        Args:
            df: Training DataFrame
            min_samples: Minimum required samples

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(df) < min_samples:
            return False, f"Insufficient samples: {len(df)} < {min_samples}"

        # Check for missing values
        missing_pct = df.isnull().sum() / len(df)
        if (missing_pct > 0.3).any():
            high_missing_cols = missing_pct[missing_pct > 0.3].index.tolist()
            return False, f"High missing values in columns: {high_missing_cols}"

        # Check label distribution (for classification)
        if 'label' in df.columns:
            label_dist = df['label'].value_counts(normalize=True)
            if label_dist.min() < 0.05:
                return False, f"Imbalanced labels: {label_dist.to_dict()}"

        # Check for variance
        numeric_cols = df.select_dtypes(include=['number']).columns
        zero_variance = [col for col in numeric_cols if df[col].std() == 0]
        if zero_variance:
            logger.warning(f"Zero variance columns (will be dropped): {zero_variance}")

        return True, "Data quality OK"

    def split_temporal(self, df: pd.DataFrame, test_size: float = 0.2,
                      date_column: str = 'created_at') -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data temporally to avoid data leakage.

        Args:
            df: Training DataFrame
            test_size: Proportion for test set
            date_column: Column to use for temporal sorting

        Returns:
            Tuple of (train_df, test_df)
        """
        df_sorted = df.sort_values(date_column)
        split_idx = int(len(df_sorted) * (1 - test_size))

        train_df = df_sorted.iloc[:split_idx].copy()
        test_df = df_sorted.iloc[split_idx:].copy()

        logger.info(f"Temporal split: {len(train_df)} train, {len(test_df)} test")
        logger.info(f"Train date range: {train_df[date_column].min()} to {train_df[date_column].max()}")
        logger.info(f"Test date range: {test_df[date_column].min()} to {test_df[date_column].max()}")

        return train_df, test_df
