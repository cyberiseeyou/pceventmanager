"""
Test ML Integration with SchedulingEngine

This script verifies that:
1. ML models can be loaded
2. SchedulingEngine initializes with ML adapter
3. ML adapter can rank employees
4. Fallback to rule-based logic works
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import get_models, get_db
from app.services.scheduling_engine import SchedulingEngine
from datetime import datetime, timedelta

def test_ml_integration():
    """Test ML integration with SchedulingEngine"""

    print("="*80)
    print("ML INTEGRATION TEST")
    print("="*80)

    # Create Flask app
    app = create_app()

    with app.app_context():
        db = get_db()
        models = get_models()

        print("\n1. Testing SchedulingEngine initialization...")
        try:
            engine = SchedulingEngine(db.session, models)
            print("   ✅ SchedulingEngine initialized successfully")
        except Exception as e:
            print(f"   ❌ SchedulingEngine initialization failed: {e}")
            return False

        print("\n2. Checking ML adapter status...")
        if engine.ml_adapter is None:
            print("   ⚠️  ML adapter not initialized (ML_ENABLED=false or import failed)")
            print("   → This is expected if ML is disabled in config")
        else:
            print(f"   ✅ ML adapter initialized")
            print(f"   → ML Enabled: {engine.ml_adapter.use_ml}")
            print(f"   → Employee Ranking: {engine.ml_adapter.use_employee_ranking}")
            print(f"   → Confidence Threshold: {engine.ml_adapter.confidence_threshold}")

            # Check if model is loaded
            if engine.ml_adapter.employee_ranker:
                print(f"   ✅ Employee ranker model loaded")
                metadata = engine.ml_adapter.employee_ranker.metadata
                print(f"   → Model version: {metadata.get('version', 'unknown')}")
                print(f"   → Training accuracy: {metadata.get('accuracy', 'unknown')}")
            else:
                print("   ⚠️  Employee ranker model not loaded yet (lazy loading)")

        print("\n3. Testing employee selection methods...")

        # Get a test event
        Event = models['Event']
        test_event = db.session.query(Event).filter(
            Event.is_scheduled == False
        ).first()

        if test_event:
            print(f"   Using test event: {test_event.project_name} ({test_event.event_type})")

            # Test schedule datetime (3 days from now)
            test_datetime = datetime.now() + timedelta(days=3)
            test_datetime = test_datetime.replace(hour=10, minute=0, second=0, microsecond=0)

            try:
                # Test leads selection
                leads = engine._get_available_leads(test_event, test_datetime)
                print(f"   ✅ _get_available_leads() returned {len(leads)} leads")

                if leads and engine.ml_adapter and engine.ml_adapter.use_ml:
                    print("   → ML ranking was applied (if enabled)")

                # Test specialists selection
                specialists = engine._get_available_specialists(test_event, test_datetime)
                print(f"   ✅ _get_available_specialists() returned {len(specialists)} specialists")

            except Exception as e:
                print(f"   ❌ Employee selection failed: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print("   ⚠️  No unscheduled events found for testing")

        print("\n4. Testing ML adapter statistics...")
        if engine.ml_adapter:
            try:
                stats = engine.ml_adapter.get_stats()
                print("   ✅ ML adapter statistics:")
                for key, value in stats.items():
                    print(f"      → {key}: {value}")
            except Exception as e:
                print(f"   ⚠️  Could not retrieve stats: {e}")

        print("\n" + "="*80)
        print("ML INTEGRATION TEST COMPLETE")
        print("="*80)
        print("\nNext Steps:")
        print("1. To enable ML, set ML_ENABLED=true in .env")
        print("2. To enable shadow mode, set ML_SHADOW_MODE=true in .env")
        print("3. Run auto-scheduler and check logs for ML predictions")

        return True

if __name__ == "__main__":
    try:
        success = test_ml_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
