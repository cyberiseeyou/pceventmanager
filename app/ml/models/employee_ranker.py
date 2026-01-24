"""
Employee ranking model for predicting assignment success.

Uses gradient boosting (XGBoost/LightGBM) to predict the probability
that an employee will successfully complete an event assignment.
"""

import os
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

from sklearn.metrics import roc_auc_score, precision_score, recall_score, accuracy_score
import joblib

logger = logging.getLogger(__name__)


class EmployeeRanker:
    """
    ML model for ranking employees by predicted assignment success probability.

    Uses gradient boosting to predict assignment success based on:
    - Historical performance
    - Current workload
    - Role & experience
    - Event context
    - Temporal features
    """

    def __init__(self, model_type: str = 'auto'):
        """
        Initialize employee ranker.

        Args:
            model_type: 'xgboost', 'lightgbm', or 'auto' (selects based on availability)
        """
        self.model_type = self._select_model_type(model_type)
        self.model = None
        self.feature_columns = None
        self.metadata = {}

    def _select_model_type(self, requested: str) -> str:
        """Select appropriate model type based on availability."""
        if requested == 'auto':
            if HAS_XGBOOST:
                return 'xgboost'
            elif HAS_LIGHTGBM:
                return 'lightgbm'
            else:
                raise RuntimeError("No gradient boosting library available. Install xgboost or lightgbm.")

        if requested == 'xgboost' and not HAS_XGBOOST:
            raise RuntimeError("XGBoost not installed. Run: pip install xgboost")

        if requested == 'lightgbm' and not HAS_LIGHTGBM:
            raise RuntimeError("LightGBM not installed. Run: pip install lightgbm")

        return requested

    def train(self, X_train: pd.DataFrame, y_train: pd.Series,
              X_val: pd.DataFrame, y_val: pd.Series,
              hyperparams: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Train the employee ranking model.

        Args:
            X_train: Training features
            y_train: Training labels (1=success, 0=failure)
            X_val: Validation features
            y_val: Validation labels
            hyperparams: Optional hyperparameter overrides

        Returns:
            Dictionary of training metrics
        """
        logger.info(f"Training {self.model_type} employee ranker on {len(X_train)} samples")

        # Store feature columns
        self.feature_columns = X_train.columns.tolist()

        # Default hyperparameters
        if self.model_type == 'xgboost':
            default_params = {
                'max_depth': 6,
                'learning_rate': 0.1,
                'n_estimators': 100,
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'random_state': 42,
                'use_label_encoder': False
            }
            default_params.update(hyperparams or {})

            self.model = xgb.XGBClassifier(**default_params)
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )

        elif self.model_type == 'lightgbm':
            default_params = {
                'max_depth': 6,
                'learning_rate': 0.1,
                'n_estimators': 100,
                'objective': 'binary',
                'metric': 'auc',
                'random_state': 42,
                'verbosity': -1
            }
            default_params.update(hyperparams or {})

            self.model = lgb.LGBMClassifier(**default_params)
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )

        # Evaluate on validation set
        y_pred_proba = self.model.predict_proba(X_val)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        metrics = {
            'auc': roc_auc_score(y_val, y_pred_proba),
            'accuracy': accuracy_score(y_val, y_pred),
            'precision': precision_score(y_val, y_pred, zero_division=0),
            'recall': recall_score(y_val, y_pred, zero_division=0),
            'samples_train': len(X_train),
            'samples_val': len(X_val),
            'model_type': self.model_type,
            'trained_at': datetime.now().isoformat()
        }

        # Precision @ Top-3 (what matters for ranking)
        metrics['precision_at_top3'] = self._precision_at_k(y_val, y_pred_proba, k=3)

        self.metadata = metrics
        logger.info(f"Training complete. AUC: {metrics['auc']:.3f}, Precision@3: {metrics['precision_at_top3']:.3f}")

        return metrics

    def _precision_at_k(self, y_true: pd.Series, y_pred_proba: np.ndarray, k: int = 3) -> float:
        """
        Calculate precision @ K (relevant for ranking use case).

        Args:
            y_true: True labels
            y_pred_proba: Predicted probabilities
            k: Number of top predictions to consider

        Returns:
            Precision at K score
        """
        # Sort by predicted probability (descending)
        sorted_indices = np.argsort(-y_pred_proba)
        top_k_indices = sorted_indices[:k]

        # Calculate precision
        if len(top_k_indices) == 0:
            return 0.0

        relevant = y_true.iloc[top_k_indices].sum()
        return relevant / k

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict assignment success probability.

        Args:
            X: Feature DataFrame

        Returns:
            Array of probabilities [0.0-1.0]
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")

        # Ensure features match training
        X_aligned = X[self.feature_columns]

        probas = self.model.predict_proba(X_aligned)[:, 1]
        return probas

    def rank_employees(self, feature_dicts: List[Dict[str, Any]]) -> List[Tuple[int, float]]:
        """
        Rank employees by predicted success probability.

        Args:
            feature_dicts: List of feature dictionaries (one per employee)

        Returns:
            List of (index, probability) tuples sorted DESC by probability
        """
        if not feature_dicts:
            return []

        # Convert to DataFrame
        X = pd.DataFrame(feature_dicts)

        # Predict probabilities
        probas = self.predict_proba(X)

        # Create ranked list
        rankings = [(i, prob) for i, prob in enumerate(probas)]
        rankings.sort(key=lambda x: x[1], reverse=True)

        return rankings

    def get_feature_importance(self, top_k: int = 10) -> Dict[str, float]:
        """
        Get feature importance scores.

        Args:
            top_k: Number of top features to return

        Returns:
            Dictionary of {feature_name: importance_score}
        """
        if self.model is None:
            return {}

        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            feature_importance = dict(zip(self.feature_columns, importances))

            # Sort and return top K
            sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
            return dict(sorted_features[:top_k])

        return {}

    def save(self, filepath: str):
        """
        Save model to disk.

        Args:
            filepath: Path to save model (.pkl file)
        """
        if self.model is None:
            raise ValueError("No model to save. Train first.")

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        model_data = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'model_type': self.model_type,
            'metadata': self.metadata
        }

        joblib.dump(model_data, filepath)
        logger.info(f"Model saved to {filepath}")

    @classmethod
    def load(cls, filepath: str) -> 'EmployeeRanker':
        """
        Load model from disk.

        Args:
            filepath: Path to model file

        Returns:
            Loaded EmployeeRanker instance
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Model file not found: {filepath}")

        model_data = joblib.load(filepath)

        ranker = cls(model_type=model_data['model_type'])
        ranker.model = model_data['model']
        ranker.feature_columns = model_data['feature_columns']
        ranker.metadata = model_data.get('metadata', {})

        logger.info(f"Model loaded from {filepath}")
        logger.info(f"Metadata: {ranker.metadata}")

        return ranker
