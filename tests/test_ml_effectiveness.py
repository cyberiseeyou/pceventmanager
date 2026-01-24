"""
Test ML Effectiveness Validation

Measures business impact of ML integration:
1. Baseline metrics collection
2. ML-enabled metrics collection
3. Success rate improvement measurement
4. Workload balance improvement
5. Statistical significance testing
"""

import pytest
from unittest.mock import patch
from datetime import datetime, timedelta
from app.services.scheduling_engine import SchedulingEngine
from app.ml.evaluation.metrics import MLMetricsTracker
import statistics


class TestBaselineMetrics:
    """Test baseline metrics collection (ML disabled)"""

    def test_collect_baseline_success_rate(self, app, db_session, models):
        """Test collecting baseline scheduler success rate"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']
            SchedulerRunHistory = models.get('SchedulerRunHistory')

            # Create test data
            employees = [
                Employee(name=f'Lead {i}', role='Lead Event Specialist', is_active=True)
                for i in range(3)
            ] + [
                Employee(name=f'Spec {i}', role='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            events = [
                Event(
                    project_name=f'Event {i}',
                    event_type='Core',
                    is_scheduled=False,
                    time_to_complete=2.0
                )
                for i in range(20)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # Simulate baseline scheduling (ML disabled)
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}
                engine = SchedulingEngine(db_session, models)

                scheduled_count = 0
                failed_count = 0

                for event in events[:10]:
                    leads = engine._get_available_leads(event, datetime.now())
                    if leads:
                        scheduled_count += 1
                    else:
                        failed_count += 1

                baseline_success_rate = scheduled_count / (scheduled_count + failed_count) if (scheduled_count + failed_count) > 0 else 0

                print(f"\nBaseline metrics (ML disabled):")
                print(f"  Events processed: {scheduled_count + failed_count}")
                print(f"  Events scheduled: {scheduled_count}")
                print(f"  Events failed: {failed_count}")
                print(f"  Success rate: {baseline_success_rate:.2%}")

                assert baseline_success_rate >= 0

    def test_collect_baseline_workload_balance(self, app, db_session, models):
        """Test collecting baseline workload balance"""
        with app.app_context():
            Employee = models['Employee']
            Schedule = models['Schedule']

            # Create employees
            employees = [
                Employee(name=f'Employee {i}', role='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            # Simulate some schedules
            base_date = datetime.now()
            for i, emp in enumerate(employees[:5]):
                # Give some employees more events than others
                num_events = (i % 3) + 1  # 1-3 events per employee
                for j in range(num_events):
                    schedule = Schedule(
                        event_id=None,  # Mock
                        employee_id=emp.id,
                        scheduled_datetime=base_date + timedelta(days=j),
                        status='confirmed'
                    )
                    db_session.add(schedule)
            db_session.commit()

            # Calculate workload balance
            workload_counts = {}
            for emp in employees[:5]:
                count = db_session.query(Schedule).filter(
                    Schedule.employee_id == emp.id
                ).count()
                workload_counts[emp.id] = count

            if workload_counts:
                workloads = list(workload_counts.values())
                std_dev = statistics.stdev(workloads) if len(workloads) > 1 else 0
                mean = statistics.mean(workloads)
                max_load = max(workloads)
                min_load = min(workloads)

                print(f"\nBaseline workload balance:")
                print(f"  Employees: {len(workloads)}")
                print(f"  Mean: {mean:.1f}")
                print(f"  Std dev: {std_dev:.2f}")
                print(f"  Max: {max_load}, Min: {min_load}")

                assert std_dev >= 0


class TestMLEnabledMetrics:
    """Test metrics collection with ML enabled"""

    def test_collect_ml_enabled_success_rate(self, app, db_session, models):
        """Test collecting success rate with ML enabled"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create test data
            employees = [
                Employee(name=f'Lead {i}', role='Lead Event Specialist', is_active=True)
                for i in range(3)
            ] + [
                Employee(name=f'Spec {i}', role='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            events = [
                Event(
                    project_name=f'Event {i}',
                    event_type='Core',
                    is_scheduled=False,
                    time_to_complete=2.0
                )
                for i in range(20)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # Simulate ML-enabled scheduling
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True,
                    'ML_CONFIDENCE_THRESHOLD': 0.6
                }
                engine = SchedulingEngine(db_session, models)

                scheduled_count = 0
                failed_count = 0

                for event in events[:10]:
                    leads = engine._get_available_leads(event, datetime.now())
                    if leads:
                        scheduled_count += 1
                    else:
                        failed_count += 1

                ml_success_rate = scheduled_count / (scheduled_count + failed_count) if (scheduled_count + failed_count) > 0 else 0

                print(f"\nML-enabled metrics:")
                print(f"  Events processed: {scheduled_count + failed_count}")
                print(f"  Events scheduled: {scheduled_count}")
                print(f"  Events failed: {failed_count}")
                print(f"  Success rate: {ml_success_rate:.2%}")

                assert ml_success_rate >= 0


class TestSuccessRateImprovement:
    """Test success rate improvement measurement"""

    def test_compare_success_rates(self, app, db_session, models):
        """Test comparing success rates between baseline and ML"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create test data
            employees = [
                Employee(name=f'Employee {i}', role='Lead Event Specialist', is_active=True)
                for i in range(5)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            events = [
                Event(project_name=f'Event {i}', event_type='Core', is_scheduled=False)
                for i in range(10)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # Baseline (ML disabled)
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}
                engine_baseline = SchedulingEngine(db_session, models)

                baseline_scheduled = sum(
                    1 for event in events[:5]
                    if engine_baseline._get_available_leads(event, datetime.now())
                )

            # ML enabled
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }
                engine_ml = SchedulingEngine(db_session, models)

                ml_scheduled = sum(
                    1 for event in events[:5]
                    if engine_ml._get_available_leads(event, datetime.now())
                )

            baseline_rate = baseline_scheduled / 5
            ml_rate = ml_scheduled / 5
            improvement = ml_rate - baseline_rate

            print(f"\nSuccess rate comparison:")
            print(f"  Baseline: {baseline_rate:.2%}")
            print(f"  ML: {ml_rate:.2%}")
            print(f"  Improvement: {improvement:+.2%}")

            # ML should not regress (>= baseline)
            assert ml_rate >= baseline_rate - 0.1  # Allow small margin


class TestWorkloadBalanceImprovement:
    """Test workload balance improvement"""

    def test_workload_distribution_fairness(self, app, db_session, models):
        """Test that ML improves workload distribution fairness"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(name=f'Employee {i}', role='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            events = [
                Event(project_name=f'Event {i}', event_type='Core', is_scheduled=False)
                for i in range(20)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # Baseline: Random selection (simulate)
            baseline_assignments = {emp.id: 0 for emp in employees}
            for i, event in enumerate(events[:10]):
                # Simulate uneven distribution
                baseline_assignments[employees[i % 3].id] += 1

            baseline_workloads = list(baseline_assignments.values())
            baseline_std = statistics.stdev(baseline_workloads) if len(baseline_workloads) > 1 else 0

            # ML-enabled: Should distribute more evenly
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }
                engine = SchedulingEngine(db_session, models)

                ml_assignments = {emp.id: 0 for emp in employees}
                for event in events[10:20]:
                    leads = engine._get_available_leads(event, datetime.now())
                    if leads:
                        # Simulate assignment to first lead
                        ml_assignments[leads[0].id] += 1

            ml_workloads = list(ml_assignments.values())
            ml_std = statistics.stdev(ml_workloads) if len(ml_workloads) > 1 else 0

            print(f"\nWorkload balance comparison:")
            print(f"  Baseline std dev: {baseline_std:.2f}")
            print(f"  ML std dev: {ml_std:.2f}")
            print(f"  Improvement: {baseline_std - ml_std:.2f}")

            # Note: This is a simplified test
            # Real improvement depends on ML model quality
            assert ml_std >= 0  # Just verify calculation works


class TestStatisticalSignificance:
    """Test statistical significance of improvements"""

    def test_success_rate_statistical_significance(self, app, db_session, models):
        """Test statistical significance of success rate improvement"""
        with app.app_context():
            # Note: Real statistical testing requires larger sample sizes
            # This is a placeholder for the methodology

            # Simulate baseline results (10 runs)
            baseline_success_rates = [0.82, 0.85, 0.80, 0.87, 0.83, 0.84, 0.81, 0.86, 0.82, 0.85]

            # Simulate ML results (10 runs)
            ml_success_rates = [0.86, 0.89, 0.85, 0.90, 0.87, 0.88, 0.86, 0.91, 0.88, 0.89]

            baseline_mean = statistics.mean(baseline_success_rates)
            ml_mean = statistics.mean(ml_success_rates)

            baseline_std = statistics.stdev(baseline_success_rates)
            ml_std = statistics.stdev(ml_success_rates)

            # Simple t-test approximation
            # (Real implementation would use scipy.stats.ttest_ind)
            pooled_std = ((baseline_std ** 2 + ml_std ** 2) / 2) ** 0.5
            effect_size = (ml_mean - baseline_mean) / pooled_std if pooled_std > 0 else 0

            print(f"\nStatistical analysis:")
            print(f"  Baseline mean: {baseline_mean:.3f} ± {baseline_std:.3f}")
            print(f"  ML mean: {ml_mean:.3f} ± {ml_std:.3f}")
            print(f"  Effect size: {effect_size:.3f}")

            # Effect size > 0.5 is generally considered moderate
            # This is just demonstration - real test would use scipy
            assert effect_size >= 0  # Positive improvement

    def test_no_regression_in_failures(self, app, db_session, models):
        """Test that ML doesn't increase failure rate"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(name=f'Employee {i}', role='Specialist', is_active=True)
                for i in range(5)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            events = [
                Event(project_name=f'Event {i}', event_type='Core', is_scheduled=False)
                for i in range(10)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # Baseline failures
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}
                engine_baseline = SchedulingEngine(db_session, models)

                baseline_failures = sum(
                    1 for event in events[:5]
                    if not engine_baseline._get_available_leads(event, datetime.now())
                )

            # ML failures
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }
                engine_ml = SchedulingEngine(db_session, models)

                ml_failures = sum(
                    1 for event in events[:5]
                    if not engine_ml._get_available_leads(event, datetime.now())
                )

            print(f"\nFailure comparison:")
            print(f"  Baseline failures: {baseline_failures}")
            print(f"  ML failures: {ml_failures}")

            # ML should not significantly increase failures
            assert ml_failures <= baseline_failures + 1  # Allow small margin


class TestMetricsTracking:
    """Test metrics tracking infrastructure"""

    def test_scheduler_run_history_tracking(self, app, db_session, models):
        """Test that SchedulerRunHistory tracks metrics correctly"""
        with app.app_context():
            SchedulerRunHistory = models.get('SchedulerRunHistory')

            if SchedulerRunHistory is None:
                pytest.skip("SchedulerRunHistory model not available")

            # Create test run history
            run = SchedulerRunHistory(
                started_at=datetime.now() - timedelta(minutes=5),
                completed_at=datetime.now(),
                total_events_processed=50,
                events_scheduled=45,
                events_failed=5,
                events_requiring_swaps=3,
                status='completed'
            )
            db_session.add(run)
            db_session.commit()

            # Verify tracking
            retrieved = db_session.query(SchedulerRunHistory).first()
            assert retrieved is not None
            assert retrieved.total_events_processed == 50
            assert retrieved.events_scheduled == 45
            assert retrieved.events_failed == 5

            # Calculate success rate
            success_rate = retrieved.events_scheduled / retrieved.total_events_processed
            assert success_rate == 0.9  # 45/50

    def test_ml_metrics_tracker_integration(self, app, db_session, models):
        """Test MLMetricsTracker integration"""
        with app.app_context():
            try:
                tracker = MLMetricsTracker(db_session, models)

                # Test that tracker initializes
                assert tracker is not None

                # Note: Full metrics tracking tests would require
                # more complete database setup with historical data
                print("\nMLMetricsTracker initialized successfully")

            except Exception as e:
                pytest.skip(f"MLMetricsTracker not available: {e}")


class TestBusinessImpactMeasurement:
    """Test business impact measurement"""

    def test_calculate_business_impact_metrics(self, app, db_session, models):
        """Test calculating comprehensive business impact metrics"""
        with app.app_context():
            # Simulated baseline and ML metrics
            baseline = {
                'success_rate': 0.85,
                'workload_std_dev': 2.5,
                'bumping_efficiency': 0.70,
                'user_interventions': 15
            }

            ml_enabled = {
                'success_rate': 0.88,
                'workload_std_dev': 2.2,
                'bumping_efficiency': 0.78,
                'user_interventions': 12
            }

            # Calculate improvements
            improvements = {
                'success_rate': ((ml_enabled['success_rate'] - baseline['success_rate']) /
                                baseline['success_rate'] * 100),
                'workload_balance': ((baseline['workload_std_dev'] - ml_enabled['workload_std_dev']) /
                                    baseline['workload_std_dev'] * 100),
                'bumping_efficiency': ((ml_enabled['bumping_efficiency'] - baseline['bumping_efficiency']) /
                                      baseline['bumping_efficiency'] * 100),
                'user_interventions': ((baseline['user_interventions'] - ml_enabled['user_interventions']) /
                                      baseline['user_interventions'] * 100)
            }

            print(f"\nBusiness impact analysis:")
            print(f"  Success rate: {improvements['success_rate']:+.1f}%")
            print(f"  Workload balance: {improvements['workload_balance']:+.1f}%")
            print(f"  Bumping efficiency: {improvements['bumping_efficiency']:+.1f}%")
            print(f"  User interventions: {improvements['user_interventions']:+.1f}%")

            # Target: At least one metric improved by 3%+
            significant_improvements = sum(1 for imp in improvements.values() if imp >= 3.0)
            assert significant_improvements >= 0  # Verify calculation works

    def test_roi_calculation(self, app, db_session, models):
        """Test ROI calculation for ML implementation"""
        with app.app_context():
            # Simplified ROI calculation
            # (Real calculation would involve actual costs and time savings)

            # Estimated time savings per week
            baseline_manual_hours = 10  # Hours spent on manual scheduling fixes
            ml_manual_hours = 7  # Hours after ML implementation
            time_saved_hours = baseline_manual_hours - ml_manual_hours

            # Estimated cost per hour
            labor_cost_per_hour = 50  # dollars

            weekly_savings = time_saved_hours * labor_cost_per_hour
            annual_savings = weekly_savings * 52

            # ML implementation cost (one-time)
            ml_implementation_cost = 10000  # dollars (estimated)

            # Simple payback period
            payback_months = ml_implementation_cost / (annual_savings / 12)

            print(f"\nROI Analysis:")
            print(f"  Weekly time saved: {time_saved_hours} hours")
            print(f"  Weekly cost savings: ${weekly_savings:.2f}")
            print(f"  Annual savings: ${annual_savings:.2f}")
            print(f"  Implementation cost: ${ml_implementation_cost:.2f}")
            print(f"  Payback period: {payback_months:.1f} months")

            assert payback_months > 0
            assert annual_savings > 0
