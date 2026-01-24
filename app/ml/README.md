# ML-Based Predictive Scheduling

This module provides machine learning enhancements to the Flask Schedule Webapp's auto-scheduler, improving employee assignment decisions, bumping optimization, and schedule feasibility prediction.

## Overview

The ML module integrates seamlessly with the existing `SchedulingEngine` through the `MLSchedulerAdapter`, providing:

1. **Employee Ranking**: Predicts assignment success probability to rank employees
2. **Bumping Optimization** (Future): Predicts cost of bumping events
3. **Feasibility Prediction** (Future): Early warning for impossible schedules

**Key Principle**: ML suggests, constraints validate. The existing `ConstraintValidator` remains authoritative for all hard constraints.

## Architecture

```
app/ml/
├── models/              # Model definitions & trained artifacts
│   ├── employee_ranker.py
│   └── artifacts/       # .pkl files (gitignored)
├── features/            # Feature engineering
│   ├── employee_features.py
│   ├── event_features.py
│   └── historical_features.py
├── training/            # Training pipeline
│   ├── data_preparation.py
│   ├── train_employee_ranker.py
│   ├── train_bump_predictor.py (future)
│   └── train_feasibility.py (future)
├── inference/           # Production inference
│   └── ml_scheduler_adapter.py
└── evaluation/          # Metrics & monitoring
    └── metrics.py
```

## Quick Start

### 1. Install ML Dependencies

```bash
# Install ML packages
pip install -r requirements.txt

# Or install individually
pip install pandas numpy scikit-learn xgboost joblib
```

### 2. Train Initial Model

Requires at least 6 months of historical scheduling data:

```bash
# Train employee ranking model
python -m app.ml.training.train_employee_ranker

# With custom parameters
python -m app.ml.training.train_employee_ranker \
    --lookback-months 12 \
    --test-size 0.2 \
    --model-type xgboost
```

Expected output:
```
Training complete. AUC: 0.850, Precision@3: 0.890
Model saved: app/ml/models/artifacts/employee_ranker_v20260116_143022.pkl
```

### 3. Enable ML in Configuration

Add to `.env`:

```bash
# Enable ML (master switch)
ML_ENABLED=true

# Enable specific ML components
ML_EMPLOYEE_RANKING_ENABLED=true
ML_BUMP_PREDICTION_ENABLED=false  # Not yet implemented
ML_FEASIBILITY_ENABLED=false      # Not yet implemented

# Confidence threshold (0.0-1.0)
ML_CONFIDENCE_THRESHOLD=0.6

# Model path (defaults to latest)
ML_EMPLOYEE_RANKER_PATH=app/ml/models/artifacts/employee_ranker_latest.pkl

# Shadow mode: log predictions without using them (for testing)
ML_SHADOW_MODE=false
```

### 4. Verify Integration

```python
from app import create_app
from app.models import get_models, get_db
from app.ml.inference.ml_scheduler_adapter import MLSchedulerAdapter

app = create_app()
with app.app_context():
    db = get_db()
    models = get_models()

    # Create adapter
    adapter = MLSchedulerAdapter(db, models, app.config)

    # Check status
    print(adapter.get_stats())
    # Output: {'ml_enabled': True, 'employee_ranker_loaded': True, ...}
```

## Usage

### Integration with SchedulingEngine

The ML module is designed to integrate transparently with the existing `SchedulingEngine`. No changes to business logic are required.

**Before ML** (app/services/scheduling_engine.py):
```python
def _get_available_leads(self, event, schedule_datetime):
    leads = [...]  # Get all qualified leads
    available = [lead for lead in leads
                 if self.validator.validate_assignment(...).is_valid]
    return available  # Deterministic ordering (first come, first serve)
```

**After ML** (with MLSchedulerAdapter):
```python
def _get_available_leads(self, event, schedule_datetime):
    leads = [...]  # Get all qualified leads
    available = [lead for lead in leads
                 if self.validator.validate_assignment(...).is_valid]

    # NEW: ML ranking (with fallback to rules)
    if self.ml_adapter.use_ml:
        ranked_employees = self.ml_adapter.rank_employees(
            available, event, schedule_datetime
        )
        return [emp for emp, confidence in ranked_employees]

    return available  # Fallback to original ordering
```

### Shadow Mode (A/B Testing)

Use shadow mode to validate ML predictions without affecting scheduling:

```bash
ML_ENABLED=true
ML_SHADOW_MODE=true  # Log predictions but use rule-based logic
```

This logs ML predictions to metrics for comparison with rule-based outcomes.

## Training

### Data Requirements

**Minimum Data**:
- 6 months of historical scheduling data
- 1,000+ assignment records (PendingSchedule)
- 500+ bumping events (for bump predictor)
- 2,000+ events (for feasibility predictor)

### Training Process

1. **Data Extraction**: Query historical data from `PendingSchedule`, `Schedule`, `EmployeeAttendance`
2. **Feature Engineering**: Extract 35 features per employee-event pair
3. **Model Training**: XGBoost/LightGBM with 80/20 temporal split
4. **Evaluation**: AUC, Precision@K, business KPIs
5. **Deployment**: Save model to `artifacts/` directory

### Retraining

Recommended schedule: **Weekly on Sunday nights**

```bash
# Manual retraining
python -m app.ml.training.train_employee_ranker

# Automated with Celery (future)
# celery -A celery_worker beat  # Scheduler
# @weekly task: retrain_employee_ranker()
```

### Model Versioning

Models are versioned by timestamp:
- `employee_ranker_v20260116_143022.pkl` (versioned)
- `employee_ranker_latest.pkl` (symlink to latest)

## Features

### Employee Ranking Features (35 total)

**Historical Performance (10 features)**:
- `success_rate_last_30_days`, `success_rate_last_90_days`
- `attendance_on_time_rate`, `total_events_completed`
- `consecutive_success_streak`, etc.

**Current Workload (8 features)**:
- `events_scheduled_this_week`, `hours_scheduled`
- `workload_status`, `events_next_7_days`
- `days_since_last_assignment`, etc.

**Role & Experience (5 features)**:
- `is_lead`, `is_specialist`, `is_juicer`
- `years_experience`, `event_type_specialization_score`

**Event Context (7 features)**:
- `event_priority_level`, `days_until_due`
- `is_rotation_event`, `time_slot_preference_match`
- `has_worked_event_type`, etc.

**Temporal (5 features)**:
- `day_of_week`, `week_of_year`, `is_weekend`
- `season`, `is_holiday_week`

## Monitoring

### Metrics Dashboard

View ML performance metrics:

```python
from app.ml.evaluation.metrics import MLMetricsTracker

tracker = MLMetricsTracker(db, models)

# Generate dashboard data
dashboard = tracker.generate_dashboard_data(lookback_days=30)

print(dashboard['scheduler_performance'])
# {'success_rate': 0.92, 'total_runs': 50, ...}

print(dashboard['bumping_metrics'])
# {'bump_reschedule_rate': 0.85, 'avg_days_to_reschedule': 2.3, ...}

print(dashboard['workload_balance'])
# {'workload_std_dev': 1.2, 'balance_score': 0.89, ...}
```

### Key Metrics

**Model Performance**:
- **AUC-ROC**: Overall discrimination ability (target: > 0.80)
- **Precision@Top-3**: Accuracy of top 3 ranked employees (target: > 0.85)

**Business Impact KPIs**:
1. **Scheduler Success Rate**: % of events successfully scheduled (+5% target)
2. **Bumping Efficiency**: % of bumped events rescheduled (+15% target)
3. **Workload Balance**: Std deviation of events per employee (-20% target)
4. **User Intervention Rate**: % of runs requiring manual fixes (-30% target)

## Fallback & Safety

### Multi-Layer Safety

**Layer 1: Model Loading Failure**
```python
try:
    model = EmployeeRanker.load(model_path)
except Exception:
    self.use_ml = False  # Disable ML globally
    # Continue with rule-based logic
```

**Layer 2: Prediction Failure**
```python
try:
    predictions = model.predict(features)
except Exception:
    return self._fallback_rank_employees(employees)
```

**Layer 3: Low Confidence Threshold**
```python
if confidence < 0.6:  # Tunable threshold
    return self._fallback_rank_employees(employees)
```

### Fallback Behavior

When ML fails or is disabled, the system falls back to rule-based ranking:
1. Leads first (confidence 0.7)
2. Specialists second (confidence 0.6)
3. Juicers third (confidence 0.5, for non-Juicer events)

**No user-facing errors, no scheduling failures.**

## Troubleshooting

### Model Not Loading

**Problem**: `WARNING: Employee ranker model not found`

**Solution**:
```bash
# Check model path
ls app/ml/models/artifacts/

# Train new model
python -m app.ml.training.train_employee_ranker

# Verify path in config
ML_EMPLOYEE_RANKER_PATH=app/ml/models/artifacts/employee_ranker_latest.pkl
```

### Insufficient Training Data

**Problem**: `ERROR: No training data available`

**Solution**:
- Ensure at least 6 months of historical `PendingSchedule` records exist
- Check database: `SELECT COUNT(*) FROM pending_schedule;`
- If new deployment, collect data for 1-2 months before enabling ML

### Low Model Performance

**Problem**: AUC < 0.70 or Precision@3 < 0.75

**Solution**:
1. Increase lookback period: `--lookback-months 12`
2. Check data quality: `validate_data_quality()`
3. Review feature importance: `ranker.get_feature_importance()`
4. Retrain with more data

### ML Predictions Ignored

**Problem**: ML enabled but predictions not used

**Solution**:
```bash
# Check configuration
ML_ENABLED=true
ML_EMPLOYEE_RANKING_ENABLED=true
ML_SHADOW_MODE=false  # Must be false to use predictions

# Check adapter stats
adapter.get_stats()
# Look for: 'predictions_made': 0 (indicates no calls)
```

## Future Enhancements

### Phase 2: Bumping Predictor (Week 7-8)
- Predict cost of bumping events
- Optimize bump decisions to maximize reschedule probability

### Phase 3: Feasibility Predictor (Week 9-10)
- Pre-processing step before scheduling
- Early warning for impossible assignments
- Reduce user intervention rate

### Phase 4+: Advanced Features
- Multi-objective optimization (ranking + workload + travel)
- Reinforcement learning for bumping
- Deep learning (LSTM for temporal patterns)
- Automated constraint learning from user overrides

## API Reference

### MLSchedulerAdapter

```python
adapter = MLSchedulerAdapter(db_session, models, config)

# Rank employees by predicted success
ranked = adapter.rank_employees(employees, event, schedule_datetime)
# Returns: [(employee, confidence), ...] sorted DESC

# Get adapter statistics
stats = adapter.get_stats()
# Returns: {'ml_enabled': bool, 'predictions_made': int, ...}

# Reset statistics
adapter.reset_stats()
```

### EmployeeRanker

```python
ranker = EmployeeRanker(model_type='xgboost')

# Train model
metrics = ranker.train(X_train, y_train, X_val, y_val)

# Predict probabilities
probas = ranker.predict_proba(X_test)

# Rank candidates
rankings = ranker.rank_employees(feature_dicts)

# Get feature importance
importance = ranker.get_feature_importance(top_k=10)

# Save/load model
ranker.save('model.pkl')
ranker = EmployeeRanker.load('model.pkl')
```

## Contributing

When adding new ML features:

1. **Add feature extractor** in `app/ml/features/`
2. **Update data preparation** in `app/ml/training/data_preparation.py`
3. **Create model class** in `app/ml/models/`
4. **Add training script** in `app/ml/training/`
5. **Update MLSchedulerAdapter** to use new model
6. **Add configuration flags** in `app/config.py`
7. **Update documentation**

## Support

For issues or questions:
- Check logs: `logs/scheduler.log`
- Review metrics: `MLMetricsTracker.generate_dashboard_data()`
- Open GitHub issue with:
  - Configuration (`.env` settings)
  - Model version and training date
  - Adapter stats (`get_stats()`)
  - Relevant log excerpts

---

**Status**: Phase 1 Complete (Employee Ranking)
**Last Updated**: 2026-01-16
**Version**: 0.1.0
