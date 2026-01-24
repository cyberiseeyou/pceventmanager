#!/usr/bin/env python3
"""
Collect ML Effectiveness Metrics

Collects comprehensive metrics to measure business impact of ML integration.

Usage:
    python scripts/collect_ml_metrics.py [--lookback-days 30] [--output metrics.json]
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import get_models, get_db
from app.ml.evaluation.metrics import MLMetricsTracker


def calculate_improvement(current, baseline, lower_is_better=False):
    """
    Calculate improvement percentage.

    Args:
        current: Current metric value
        baseline: Baseline metric value
        lower_is_better: If True, lower values are better (e.g., std dev)

    Returns:
        float: Improvement percentage
    """
    if baseline == 0:
        return 0

    if lower_is_better:
        improvement = ((baseline - current) / baseline) * 100
    else:
        improvement = ((current - baseline) / baseline) * 100

    return improvement


def collect_ml_metrics(lookback_days=30):
    """
    Collect comprehensive ML effectiveness metrics.

    Args:
        lookback_days (int): Number of days to analyze

    Returns:
        dict: Comprehensive metrics report
    """
    print("="*80)
    print("ML EFFECTIVENESS METRICS COLLECTION")
    print("="*80)

    app = create_app()

    with app.app_context():
        db = get_db()
        models = get_models()

        print(f"\nCollecting metrics from last {lookback_days} days...")

        # Initialize metrics tracker
        tracker = MLMetricsTracker(db.session, models)

        # Generate comprehensive dashboard data
        print("\n1. Generating dashboard data...")
        try:
            dashboard = tracker.generate_dashboard_data(lookback_days=lookback_days)

            scheduler_perf = dashboard.get('scheduler_performance', {})
            workload_balance = dashboard.get('workload_balance', {})
            bumping_metrics = dashboard.get('bumping_metrics', {})
            ml_comparison = dashboard.get('ml_vs_rules_comparison', {})

            print("   ✅ Dashboard data collected")

        except Exception as e:
            print(f"   ❌ Error collecting dashboard data: {e}")
            dashboard = {
                'scheduler_performance': {},
                'workload_balance': {},
                'bumping_metrics': {},
                'ml_vs_rules_comparison': {}
            }

        # Display scheduler performance
        print("\n2. Scheduler Performance:")
        scheduler_perf = dashboard.get('scheduler_performance', {})
        print(f"   Total runs: {scheduler_perf.get('total_runs', 0)}")
        print(f"   Success rate: {scheduler_perf.get('success_rate', 0):.2%}")
        print(f"   Events processed: {scheduler_perf.get('total_events_processed', 0)}")
        print(f"   Events scheduled: {scheduler_perf.get('total_events_scheduled', 0)}")
        print(f"   Events failed: {scheduler_perf.get('total_events_failed', 0)}")

        # Display workload balance
        print("\n3. Workload Balance:")
        workload_balance = dashboard.get('workload_balance', {})
        print(f"   Active employees: {workload_balance.get('active_employees', 0)}")
        print(f"   Mean workload: {workload_balance.get('mean_workload', 0):.1f}")
        print(f"   Std deviation: {workload_balance.get('workload_std_dev', 0):.2f}")
        print(f"   Max load: {workload_balance.get('max_workload', 0)}")
        print(f"   Min load: {workload_balance.get('min_workload', 0)}")

        # Display bumping metrics
        print("\n4. Bumping Efficiency:")
        bumping_metrics = dashboard.get('bumping_metrics', {})
        print(f"   Events requiring swaps: {bumping_metrics.get('total_bumps', 0)}")
        print(f"   Successfully rescheduled: {bumping_metrics.get('successful_reschedules', 0)}")
        print(f"   Reschedule rate: {bumping_metrics.get('bump_reschedule_rate', 0):.2%}")

        # Display ML comparison
        print("\n5. ML vs Rules Comparison:")
        ml_comparison = dashboard.get('ml_vs_rules_comparison', {})
        print(f"   ML success rate: {ml_comparison.get('ml_success_rate', 0):.2%}")
        print(f"   Rule success rate: {ml_comparison.get('rule_success_rate', 0):.2%}")
        print(f"   Difference: {(ml_comparison.get('ml_success_rate', 0) - ml_comparison.get('rule_success_rate', 0)):.2%}")

        # Calculate improvements (requires baseline metrics)
        print("\n6. Calculating Improvements:")

        # Baseline metrics (these would typically be loaded from a previous collection)
        # For now, we use estimated baselines
        baseline_metrics = {
            'success_rate': 0.85,
            'workload_std_dev': 2.5,
            'bump_efficiency': 0.70
        }

        improvements = {
            'success_rate': calculate_improvement(
                scheduler_perf.get('success_rate', 0),
                baseline_metrics['success_rate']
            ),
            'workload_balance': calculate_improvement(
                workload_balance.get('workload_std_dev', 0),
                baseline_metrics['workload_std_dev'],
                lower_is_better=True
            ),
            'bump_efficiency': calculate_improvement(
                bumping_metrics.get('bump_reschedule_rate', 0),
                baseline_metrics['bump_efficiency']
            )
        }

        print(f"   Success rate: {improvements['success_rate']:+.1f}%")
        print(f"   Workload balance: {improvements['workload_balance']:+.1f}%")
        print(f"   Bump efficiency: {improvements['bump_efficiency']:+.1f}%")

        # Generate summary
        print("\n7. Summary:")

        significant_improvements = sum(1 for imp in improvements.values() if imp >= 3.0)
        any_regression = any(imp < -2.0 for imp in improvements.values())

        if any_regression:
            status = "⚠️  REGRESSION DETECTED"
        elif significant_improvements >= 1:
            status = "✅ SIGNIFICANT IMPROVEMENT"
        else:
            status = "🔵 MINOR IMPROVEMENT"

        print(f"   Status: {status}")
        print(f"   Significant improvements: {significant_improvements}/3 metrics")

        # Build final report
        report = {
            'collection_date': datetime.now().isoformat(),
            'lookback_days': lookback_days,
            'scheduler_performance': scheduler_perf,
            'workload_balance': workload_balance,
            'bumping_metrics': bumping_metrics,
            'ml_vs_rules_comparison': ml_comparison,
            'baseline_metrics': baseline_metrics,
            'improvements': improvements,
            'summary': {
                'status': status,
                'significant_improvements': significant_improvements,
                'any_regression': any_regression
            }
        }

        return report


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Collect ML effectiveness metrics')
    parser.add_argument(
        '--lookback-days',
        type=int,
        default=30,
        help='Number of days to analyze (default: 30)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='ml_metrics.json',
        help='Output file path (default: ml_metrics.json)'
    )

    args = parser.parse_args()

    try:
        report = collect_ml_metrics(lookback_days=args.lookback_days)

        # Save report
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n{'='*80}")
        print(f"Metrics saved to: {args.output}")
        print(f"{'='*80}")

        # Exit with appropriate code
        if report['summary']['any_regression']:
            print("\n⚠️  WARNING: Regression detected in some metrics")
            sys.exit(1)
        else:
            print("\n✅ Metrics collection complete")
            sys.exit(0)

    except Exception as e:
        print(f"\n❌ Metrics collection failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
