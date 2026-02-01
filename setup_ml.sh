#!/bin/bash
# Quick setup script for ML-based predictive scheduling
# Run: bash setup_ml.sh

set -e  # Exit on error

echo "=========================================="
echo "ML Predictive Scheduling Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "ERROR: Python 3.8+ required"
    exit 1
fi

# Install ML dependencies
echo ""
echo "Installing ML dependencies..."
pip install pandas numpy scikit-learn xgboost joblib --quiet

echo "✓ Dependencies installed"

# Verify historical data
echo ""
echo "Checking historical data availability..."
python3 << 'PYEOF'
from datetime import datetime, timedelta
from app import create_app

app = create_app()
with app.app_context():
    from app.models import get_models, get_db
    db = get_db()
    models = get_models()

    # Check PendingSchedule records
    total_records = db.query(models['PendingSchedule']).count()

    # Check records in last 6 months
    six_months_ago = datetime.now() - timedelta(days=180)
    recent_records = db.query(models['PendingSchedule']).filter(
        models['PendingSchedule'].created_at >= six_months_ago
    ).count()

    print(f"Total PendingSchedule records: {total_records}")
    print(f"Last 6 months: {recent_records}")

    if total_records < 100:
        print("\n⚠️  WARNING: Insufficient data for training (need 1000+)")
        print("   The system will work but model performance may be poor.")
        print("   Recommendation: Collect more data before training.")
        exit(1)
    elif recent_records < 500:
        print("\n⚠️  WARNING: Limited recent data (< 500 records)")
        print("   Model may not capture current patterns well.")
    else:
        print("\n✓ Sufficient historical data available")
PYEOF

data_check=$?

if [ $data_check -ne 0 ]; then
    echo ""
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 1
    fi
fi

# Create artifacts directory
echo ""
echo "Creating model artifacts directory..."
mkdir -p app/ml/models/artifacts
echo "✓ Directory created"

# Configure ML settings
echo ""
echo "Configuring ML settings..."

if [ ! -f .env ]; then
    echo "Creating .env file..."
    touch .env
fi

# Check if ML_ENABLED already exists
if grep -q "ML_ENABLED" .env; then
    echo "✓ ML configuration already exists in .env"
else
    echo "Adding ML configuration to .env..."
    cat >> .env << 'EOF'

# ML Predictive Scheduling Configuration
ML_ENABLED=false  # Set to true after training model
ML_EMPLOYEE_RANKING_ENABLED=true
ML_BUMP_PREDICTION_ENABLED=false  # Not yet implemented
ML_FEASIBILITY_ENABLED=false      # Not yet implemented
ML_CONFIDENCE_THRESHOLD=0.6
ML_EMPLOYEE_RANKER_PATH=app/ml/models/artifacts/employee_ranker_latest.pkl
ML_SHADOW_MODE=true  # Start in shadow mode (log predictions, use rules)
EOF
    echo "✓ Configuration added to .env"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Train the initial model:"
echo "   $ python -m app.ml.training.train_employee_ranker"
echo ""
echo "2. Enable ML (after successful training):"
echo "   Edit .env: Set ML_ENABLED=true"
echo ""
echo "3. Test in shadow mode first:"
echo "   ML_SHADOW_MODE=true logs predictions without using them"
echo ""
echo "4. Monitor performance:"
echo "   Check logs/scheduler.log for ML activity"
echo ""
echo "For detailed documentation, see:"
echo "  - app/ml/README.md"
echo "  - ML_IMPLEMENTATION_STATUS.md"
echo ""
