#!/usr/bin/env python3
"""
Generate ML Effectiveness Report

Generates a comprehensive report (JSON/HTML) documenting the effectiveness
of ML integration.

Usage:
    python scripts/generate_ml_report.py [--input metrics.json] [--format html]
"""

import sys
import os
import json
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_text_report(metrics):
    """
    Generate a text-based report.

    Args:
        metrics (dict): Metrics data

    Returns:
        str: Formatted text report
    """
    report_lines = [
        "="*80,
        "ML EFFECTIVENESS REPORT",
        "="*80,
        "",
        f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Analysis Period: {metrics.get('lookback_days', 'N/A')} days",
        "",
        "EXECUTIVE SUMMARY",
        "-"*80,
        ""
    ]

    # Summary status
    summary = metrics.get('summary', {})
    report_lines.append(f"Status: {summary.get('status', 'Unknown')}")
    report_lines.append(f"Significant Improvements: {summary.get('significant_improvements', 0)}/3 metrics")
    report_lines.append(f"Regression Detected: {'Yes' if summary.get('any_regression') else 'No'}")
    report_lines.append("")

    # Scheduler Performance
    report_lines.extend([
        "SCHEDULER PERFORMANCE",
        "-"*80,
        ""
    ])

    scheduler_perf = metrics.get('scheduler_performance', {})
    report_lines.append(f"Total Runs: {scheduler_perf.get('total_runs', 0)}")
    report_lines.append(f"Success Rate: {scheduler_perf.get('success_rate', 0):.2%}")
    report_lines.append(f"Events Processed: {scheduler_perf.get('total_events_processed', 0)}")
    report_lines.append(f"Events Scheduled: {scheduler_perf.get('total_events_scheduled', 0)}")
    report_lines.append(f"Events Failed: {scheduler_perf.get('total_events_failed', 0)}")
    report_lines.append("")

    # Workload Balance
    report_lines.extend([
        "WORKLOAD BALANCE",
        "-"*80,
        ""
    ])

    workload = metrics.get('workload_balance', {})
    report_lines.append(f"Active Employees: {workload.get('active_employees', 0)}")
    report_lines.append(f"Mean Workload: {workload.get('mean_workload', 0):.1f} events/employee")
    report_lines.append(f"Standard Deviation: {workload.get('workload_std_dev', 0):.2f}")
    report_lines.append(f"Max Workload: {workload.get('max_workload', 0)}")
    report_lines.append(f"Min Workload: {workload.get('min_workload', 0)}")
    report_lines.append("")

    # Bumping Efficiency
    report_lines.extend([
        "BUMPING EFFICIENCY",
        "-"*80,
        ""
    ])

    bumping = metrics.get('bumping_metrics', {})
    report_lines.append(f"Events Requiring Swaps: {bumping.get('total_bumps', 0)}")
    report_lines.append(f"Successfully Rescheduled: {bumping.get('successful_reschedules', 0)}")
    report_lines.append(f"Reschedule Rate: {bumping.get('bump_reschedule_rate', 0):.2%}")
    report_lines.append("")

    # ML vs Rules
    report_lines.extend([
        "ML vs RULE-BASED COMPARISON",
        "-"*80,
        ""
    ])

    ml_comparison = metrics.get('ml_vs_rules_comparison', {})
    report_lines.append(f"ML Success Rate: {ml_comparison.get('ml_success_rate', 0):.2%}")
    report_lines.append(f"Rule Success Rate: {ml_comparison.get('rule_success_rate', 0):.2%}")
    diff = ml_comparison.get('ml_success_rate', 0) - ml_comparison.get('rule_success_rate', 0)
    report_lines.append(f"Difference: {diff:+.2%}")
    report_lines.append("")

    # Improvements
    report_lines.extend([
        "IMPROVEMENTS OVER BASELINE",
        "-"*80,
        ""
    ])

    improvements = metrics.get('improvements', {})
    report_lines.append(f"Success Rate: {improvements.get('success_rate', 0):+.1f}%")
    report_lines.append(f"Workload Balance: {improvements.get('workload_balance', 0):+.1f}%")
    report_lines.append(f"Bump Efficiency: {improvements.get('bump_efficiency', 0):+.1f}%")
    report_lines.append("")

    # Recommendations
    report_lines.extend([
        "RECOMMENDATIONS",
        "-"*80,
        ""
    ])

    if summary.get('any_regression'):
        report_lines.extend([
            "⚠️  Regression detected in some metrics.",
            "   → Review model configuration and feature engineering",
            "   → Consider retraining with more recent data",
            "   → Check for data quality issues"
        ])
    elif summary.get('significant_improvements', 0) >= 2:
        report_lines.extend([
            "✅ Significant improvements detected across multiple metrics.",
            "   → Continue monitoring performance",
            "   → Consider expanding ML features (bump prediction, feasibility)",
            "   → Document lessons learned for future improvements"
        ])
    else:
        report_lines.extend([
            "🔵 Minor improvements detected.",
            "   → Continue collecting data for statistical significance",
            "   → Consider A/B testing different model configurations",
            "   → Monitor for edge cases and failure modes"
        ])

    report_lines.append("")
    report_lines.append("="*80)
    report_lines.append("END OF REPORT")
    report_lines.append("="*80)

    return "\n".join(report_lines)


def generate_html_report(metrics):
    """
    Generate an HTML report.

    Args:
        metrics (dict): Metrics data

    Returns:
        str: HTML report
    """
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ML Effectiveness Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
        }}
        .card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            margin-top: 0;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .metric:last-child {{
            border-bottom: none;
        }}
        .metric-label {{
            color: #666;
        }}
        .metric-value {{
            font-weight: bold;
            color: #333;
        }}
        .improvement {{
            color: #10b981;
        }}
        .regression {{
            color: #ef4444;
        }}
        .status-success {{
            background: #10b981;
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            display: inline-block;
        }}
        .status-warning {{
            background: #f59e0b;
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            display: inline-block;
        }}
        .status-info {{
            background: #3b82f6;
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            display: inline-block;
        }}
        .recommendations {{
            background: #fef3c7;
            padding: 15px;
            border-left: 4px solid #f59e0b;
            border-radius: 4px;
        }}
        .recommendations ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ML Effectiveness Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Analysis Period: {metrics.get('lookback_days', 'N/A')} days</p>
    </div>

    <div class="card">
        <h2>Executive Summary</h2>
        <div class="status-{_get_status_class(metrics.get('summary', {}).get('status', ''))}">
            {metrics.get('summary', {}).get('status', 'Unknown')}
        </div>
        <div style="margin-top: 15px;">
            <div class="metric">
                <span class="metric-label">Significant Improvements</span>
                <span class="metric-value">{metrics.get('summary', {}).get('significant_improvements', 0)}/3 metrics</span>
            </div>
            <div class="metric">
                <span class="metric-label">Regression Detected</span>
                <span class="metric-value">{'Yes' if metrics.get('summary', {}).get('any_regression') else 'No'}</span>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>Scheduler Performance</h2>
        <div class="metric">
            <span class="metric-label">Total Runs</span>
            <span class="metric-value">{metrics.get('scheduler_performance', {}).get('total_runs', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Success Rate</span>
            <span class="metric-value">{metrics.get('scheduler_performance', {}).get('success_rate', 0):.2%}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Events Processed</span>
            <span class="metric-value">{metrics.get('scheduler_performance', {}).get('total_events_processed', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Events Scheduled</span>
            <span class="metric-value">{metrics.get('scheduler_performance', {}).get('total_events_scheduled', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Events Failed</span>
            <span class="metric-value">{metrics.get('scheduler_performance', {}).get('total_events_failed', 0)}</span>
        </div>
    </div>

    <div class="card">
        <h2>Workload Balance</h2>
        <div class="metric">
            <span class="metric-label">Active Employees</span>
            <span class="metric-value">{metrics.get('workload_balance', {}).get('active_employees', 0)}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Mean Workload</span>
            <span class="metric-value">{metrics.get('workload_balance', {}).get('mean_workload', 0):.1f} events/employee</span>
        </div>
        <div class="metric">
            <span class="metric-label">Standard Deviation</span>
            <span class="metric-value">{metrics.get('workload_balance', {}).get('workload_std_dev', 0):.2f}</span>
        </div>
    </div>

    <div class="card">
        <h2>Improvements Over Baseline</h2>
        <div class="metric">
            <span class="metric-label">Success Rate</span>
            <span class="metric-value {_get_improvement_class(metrics.get('improvements', {}).get('success_rate', 0))}">{metrics.get('improvements', {}).get('success_rate', 0):+.1f}%</span>
        </div>
        <div class="metric">
            <span class="metric-label">Workload Balance</span>
            <span class="metric-value {_get_improvement_class(metrics.get('improvements', {}).get('workload_balance', 0))}">{metrics.get('improvements', {}).get('workload_balance', 0):+.1f}%</span>
        </div>
        <div class="metric">
            <span class="metric-label">Bump Efficiency</span>
            <span class="metric-value {_get_improvement_class(metrics.get('improvements', {}).get('bump_efficiency', 0))}">{metrics.get('improvements', {}).get('bump_efficiency', 0):+.1f}%</span>
        </div>
    </div>

    <div class="card recommendations">
        <h2>Recommendations</h2>
        {_generate_recommendations_html(metrics.get('summary', {}))}
    </div>

</body>
</html>
"""
    return html


def _get_status_class(status):
    """Get CSS class for status"""
    if '✅' in status or 'IMPROVEMENT' in status:
        return 'success'
    elif '⚠️' in status or 'REGRESSION' in status:
        return 'warning'
    else:
        return 'info'


def _get_improvement_class(value):
    """Get CSS class for improvement value"""
    if value >= 3.0:
        return 'improvement'
    elif value < -2.0:
        return 'regression'
    else:
        return ''


def _generate_recommendations_html(summary):
    """Generate recommendations HTML"""
    if summary.get('any_regression'):
        return """
        <p><strong>⚠️ Regression detected in some metrics.</strong></p>
        <ul>
            <li>Review model configuration and feature engineering</li>
            <li>Consider retraining with more recent data</li>
            <li>Check for data quality issues</li>
        </ul>
        """
    elif summary.get('significant_improvements', 0) >= 2:
        return """
        <p><strong>✅ Significant improvements detected across multiple metrics.</strong></p>
        <ul>
            <li>Continue monitoring performance</li>
            <li>Consider expanding ML features (bump prediction, feasibility)</li>
            <li>Document lessons learned for future improvements</li>
        </ul>
        """
    else:
        return """
        <p><strong>🔵 Minor improvements detected.</strong></p>
        <ul>
            <li>Continue collecting data for statistical significance</li>
            <li>Consider A/B testing different model configurations</li>
            <li>Monitor for edge cases and failure modes</li>
        </ul>
        """


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Generate ML effectiveness report')
    parser.add_argument(
        '--input',
        type=str,
        default='ml_metrics.json',
        help='Input metrics file (default: ml_metrics.json)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['text', 'html', 'both'],
        default='both',
        help='Report format (default: both)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='ml_report',
        help='Output file basename (default: ml_report)'
    )

    args = parser.parse_args()

    try:
        # Load metrics
        print(f"Loading metrics from {args.input}...")
        with open(args.input, 'r') as f:
            metrics = json.load(f)

        # Generate reports
        if args.format in ['text', 'both']:
            print("Generating text report...")
            text_report = generate_text_report(metrics)
            text_file = f"{args.output}.txt"
            with open(text_file, 'w') as f:
                f.write(text_report)
            print(f"✅ Text report saved to: {text_file}")

        if args.format in ['html', 'both']:
            print("Generating HTML report...")
            html_report = generate_html_report(metrics)
            html_file = f"{args.output}.html"
            with open(html_file, 'w') as f:
                f.write(html_report)
            print(f"✅ HTML report saved to: {html_file}")

        print("\n" + "="*80)
        print("Report generation complete!")
        print("="*80)

    except FileNotFoundError:
        print(f"❌ Error: Metrics file '{args.input}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid JSON in '{args.input}'")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Report generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
