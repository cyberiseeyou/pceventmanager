"""
Training script for employee ranking model.

This script:
1. Extracts historical training data from the database
2. Prepares features and labels
3. Trains an XGBoost/LightGBM model
4. Evaluates performance
5. Saves the trained model
"""

import os
import sys
from datetime import datetime, timedelta
import logging
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import get_models, get_db
from app.ml.training.data_preparation import TrainingDataPreparation
from app.ml.models.employee_ranker import EmployeeRanker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train_employee_ranker(
    lookback_months: int = 6,
    test_size: float = 0.2,
    model_type: str = 'auto',
    output_dir: str = None
):
    """
    Train employee ranking model.

    Args:
        lookback_months: How many months of history to use
        test_size: Proportion of data for testing
        model_type: 'xgboost', 'lightgbm', or 'auto'
        output_dir: Where to save the model (defaults to app/ml/models/artifacts/)

    Returns:
        Tuple of (model, metrics)
    """
    # Initialize Flask app context
    app = create_app()
    with app.app_context():
        db = get_db()
        models = get_models()
        db_session = db.session

        logger.info("=" * 60)
        logger.info("EMPLOYEE RANKER TRAINING")
        logger.info("=" * 60)

        # Determine date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_months * 30)
        min_lookback = 30  # Need at least 30 days history for features

        logger.info(f"Training data window: {start_date.date()} to {end_date.date()}")
        logger.info(f"Minimum lookback: {min_lookback} days")

        # Step 1: Prepare training data
        logger.info("\n--- Step 1: Data Preparation ---")
        data_prep = TrainingDataPreparation(db_session, models)

        df = data_prep.prepare_employee_ranking_data(
            start_date=start_date,
            end_date=end_date,
            min_lookback_days=min_lookback
        )

        if len(df) == 0:
            logger.error("No training data available. Ensure historical PendingSchedule records exist.")
            return None, {}

        # Step 2: Validate data quality
        logger.info("\n--- Step 2: Data Quality Validation ---")
        is_valid, message = data_prep.validate_data_quality(df, min_samples=100)

        if not is_valid:
            logger.error(f"Data quality check failed: {message}")
            logger.info("Attempting to proceed with available data...")

        # Step 3: Split data temporally
        logger.info("\n--- Step 3: Temporal Train/Test Split ---")
        train_df, test_df = data_prep.split_temporal(df, test_size=test_size)

        # Separate features and labels
        metadata_cols = ['employee_id', 'event_ref_num', 'schedule_datetime', 'created_at', 'label']
        feature_cols = [col for col in df.columns if col not in metadata_cols]

        X_train = train_df[feature_cols]
        y_train = train_df['label']
        X_test = test_df[feature_cols]
        y_test = test_df['label']

        logger.info(f"Features: {len(feature_cols)} columns")
        logger.info(f"Training set: {len(X_train)} samples ({y_train.sum()} successes, {len(y_train)-y_train.sum()} failures)")
        logger.info(f"Test set: {len(X_test)} samples ({y_test.sum()} successes, {len(y_test)-y_test.sum()} failures)")

        # Handle missing values (simple imputation)
        X_train = X_train.fillna(X_train.median())
        X_test = X_test.fillna(X_train.median())  # Use train median for test

        # Step 4: Train model
        logger.info(f"\n--- Step 4: Model Training ({model_type}) ---")
        ranker = EmployeeRanker(model_type=model_type)

        # Use 80/20 split of training data for train/validation
        val_split_idx = int(len(X_train) * 0.8)
        X_train_fit = X_train.iloc[:val_split_idx]
        y_train_fit = y_train.iloc[:val_split_idx]
        X_val = X_train.iloc[val_split_idx:]
        y_val = y_train.iloc[val_split_idx:]

        metrics = ranker.train(
            X_train=X_train_fit,
            y_train=y_train_fit,
            X_val=X_val,
            y_val=y_val
        )

        # Step 5: Evaluate on test set
        logger.info("\n--- Step 5: Test Set Evaluation ---")
        y_test_pred_proba = ranker.predict_proba(X_test)
        y_test_pred = (y_test_pred_proba >= 0.5).astype(int)

        from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score

        test_metrics = {
            'test_auc': roc_auc_score(y_test, y_test_pred_proba),
            'test_accuracy': accuracy_score(y_test, y_test_pred),
            'test_precision': precision_score(y_test, y_test_pred, zero_division=0),
            'test_recall': recall_score(y_test, y_test_pred, zero_division=0),
            'test_precision_at_top3': ranker._precision_at_k(y_test, y_test_pred_proba, k=3)
        }

        metrics.update(test_metrics)

        logger.info(f"Test AUC: {test_metrics['test_auc']:.3f}")
        logger.info(f"Test Accuracy: {test_metrics['test_accuracy']:.3f}")
        logger.info(f"Test Precision@3: {test_metrics['test_precision_at_top3']:.3f}")

        # Step 6: Feature importance
        logger.info("\n--- Step 6: Feature Importance ---")
        feature_importance = ranker.get_feature_importance(top_k=10)
        logger.info("Top 10 features:")
        for feature, importance in feature_importance.items():
            logger.info(f"  {feature}: {importance:.4f}")

        # Step 7: Save model
        logger.info("\n--- Step 7: Saving Model ---")
        if output_dir is None:
            output_dir = os.path.join(project_root, 'app', 'ml', 'models', 'artifacts')

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"employee_ranker_v{timestamp}.pkl"
        model_path = os.path.join(output_dir, model_filename)

        ranker.save(model_path)

        # Save a "latest" symlink for easy loading
        latest_path = os.path.join(output_dir, "employee_ranker_latest.pkl")
        if os.path.exists(latest_path):
            os.remove(latest_path)

        # Copy instead of symlink for Windows compatibility
        import shutil
        shutil.copy2(model_path, latest_path)

        logger.info(f"Model saved: {model_path}")
        logger.info(f"Latest model: {latest_path}")

        # Step 8: Summary
        logger.info("\n" + "=" * 60)
        logger.info("TRAINING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Model Type: {model_type}")
        logger.info(f"Training Samples: {len(X_train)}")
        logger.info(f"Test Samples: {len(X_test)}")
        logger.info(f"Features: {len(feature_cols)}")
        logger.info(f"Validation AUC: {metrics['auc']:.3f}")
        logger.info(f"Test AUC: {test_metrics['test_auc']:.3f}")
        logger.info(f"Test Precision@3: {test_metrics['test_precision_at_top3']:.3f}")
        logger.info("=" * 60)

        return ranker, metrics


def main():
    """Command-line interface for training."""
    parser = argparse.ArgumentParser(description='Train employee ranking model')

    parser.add_argument(
        '--lookback-months',
        type=int,
        default=6,
        help='How many months of history to use (default: 6)'
    )

    parser.add_argument(
        '--test-size',
        type=float,
        default=0.2,
        help='Proportion of data for testing (default: 0.2)'
    )

    parser.add_argument(
        '--model-type',
        choices=['auto', 'xgboost', 'lightgbm'],
        default='auto',
        help='Model type to use (default: auto)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for model (default: app/ml/models/artifacts/)'
    )

    args = parser.parse_args()

    try:
        train_employee_ranker(
            lookback_months=args.lookback_months,
            test_size=args.test_size,
            model_type=args.model_type,
            output_dir=args.output_dir
        )
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
