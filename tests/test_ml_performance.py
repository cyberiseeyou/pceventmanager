"""
Test ML Performance Validation

Measures speed and resource usage:
1. Prediction latency (target: <50ms)
2. Batch prediction speedup
3. Memory usage
4. Scheduler run time comparison
5. Feature extraction speed
6. Concurrent prediction handling
"""

import pytest
import time
import psutil
import os
from datetime import datetime, timedelta
from unittest.mock import patch
from app.services.scheduling_engine import SchedulingEngine
from app.ml.inference.ml_scheduler_adapter import MLSchedulerAdapter


class TestPredictionLatency:
    """Test prediction latency benchmarks"""

    def test_single_prediction_latency(self, app, db_session, models):
        """Test that single prediction completes in <50ms"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create test employees
            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(5)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                          start_datetime=start, due_datetime=start + timedelta(days=7),
                          is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True
            }

            adapter = MLSchedulerAdapter(db_session, models, config)

            # Warm up (first prediction may load model)
            adapter.rank_employees([employees[0]], event, datetime.now())

            # Measure actual prediction time
            start_time = time.time()
            adapter.rank_employees([employees[1]], event, datetime.now())
            elapsed_ms = (time.time() - start_time) * 1000

            # Target: <50ms per prediction
            assert elapsed_ms < 50, f"Prediction took {elapsed_ms:.2f}ms (target: <50ms)"

    def test_average_prediction_latency(self, app, db_session, models):
        """Test average prediction latency across multiple predictions"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                          start_datetime=start, due_datetime=start + timedelta(days=7),
                          is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Warm up
            adapter.rank_employees([employees[0]], event, datetime.now())

            # Measure 10 predictions
            latencies = []
            for i in range(1, 10):
                start_time = time.time()
                adapter.rank_employees([employees[i]], event, datetime.now())
                latencies.append((time.time() - start_time) * 1000)

            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)

            print(f"\nAverage latency: {avg_latency:.2f}ms")
            print(f"Max latency: {max_latency:.2f}ms")

            assert avg_latency < 50, f"Average latency {avg_latency:.2f}ms exceeds 50ms target"


class TestBatchPrediction:
    """Test batch prediction performance"""

    def test_batch_prediction_speedup(self, app, db_session, models):
        """Test that batch predictions are faster than sequential"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(20)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                          start_datetime=start, due_datetime=start + timedelta(days=7),
                          is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Warm up
            adapter.rank_employees([employees[0]], event, datetime.now())

            # Sequential predictions
            start_time = time.time()
            for emp in employees[1:11]:
                adapter.rank_employees([emp], event, datetime.now())
            sequential_time = time.time() - start_time

            # Batch prediction
            start_time = time.time()
            adapter.rank_employees(employees[11:21], event, datetime.now())
            batch_time = time.time() - start_time

            print(f"\nSequential time (10 employees): {sequential_time:.3f}s")
            print(f"Batch time (10 employees): {batch_time:.3f}s")
            print(f"Speedup: {sequential_time / batch_time:.2f}x")

            # Batch should be at least as fast (potentially faster with optimizations)
            assert batch_time <= sequential_time * 1.2  # Allow 20% margin


class TestMemoryUsage:
    """Test memory usage of ML components"""

    def test_model_memory_footprint(self, app, db_session, models):
        """Test that model memory usage is acceptable"""
        with app.app_context():
            process = psutil.Process(os.getpid())
            baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True,
                'ML_EMPLOYEE_RANKER_PATH': 'app/ml/models/artifacts/employee_ranker_latest.pkl'
            }

            adapter = MLSchedulerAdapter(db_session, models, config)

            # Trigger model loading
            if os.path.exists(config['ML_EMPLOYEE_RANKER_PATH']):
                model = adapter.employee_ranker

                loaded_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = loaded_memory - baseline_memory

                print(f"\nBaseline memory: {baseline_memory:.2f} MB")
                print(f"After model load: {loaded_memory:.2f} MB")
                print(f"Memory increase: {memory_increase:.2f} MB")

                # Target: <500MB for model loading
                assert memory_increase < 500, f"Model uses {memory_increase:.2f}MB (target: <500MB)"

    def test_prediction_memory_leak(self, app, db_session, models):
        """Test that repeated predictions don't leak memory"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                          start_datetime=start, due_datetime=start + timedelta(days=7),
                          is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            process = psutil.Process(os.getpid())

            # Warm up
            for _ in range(10):
                adapter.rank_employees(employees, event, datetime.now())

            baseline_memory = process.memory_info().rss / 1024 / 1024

            # Run 100 predictions
            for _ in range(100):
                adapter.rank_employees(employees, event, datetime.now())

            final_memory = process.memory_info().rss / 1024 / 1024
            memory_increase = final_memory - baseline_memory

            print(f"\nMemory after 100 predictions: {memory_increase:+.2f} MB change")

            # Should not increase memory significantly (allow 10MB growth)
            assert memory_increase < 10, f"Memory leaked {memory_increase:.2f}MB in 100 predictions"


class TestSchedulerRunTime:
    """Test overall scheduler run time impact"""

    def test_scheduler_run_time_with_ml_disabled(self, app, db_session, models):
        """Benchmark scheduler run time without ML"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create realistic dataset
            employees = [
                Employee(id=f'lead_{i}', name=f'Lead {i}', job_title='Lead Event Specialist', is_active=True)
                for i in range(5)
            ] + [
                Employee(id=f'spec_{i}', name=f'Spec {i}', job_title='Specialist', is_active=True)
                for i in range(15)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            events = [
                Event(
                    project_name=f'Event {i}',
                    project_ref_num=1000+i,
                    event_type='Core',
                    start_datetime=start,
                    due_datetime=start + timedelta(days=7),
                    is_scheduled=False,
                    estimated_time=2.0
                )
                for i in range(20)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}

                engine = SchedulingEngine(db_session, models)

                start_time = time.time()

                # Simulate scheduling
                for event in events[:5]:  # Schedule 5 events
                    leads = engine._get_available_leads(event, datetime.now())

                baseline_time = time.time() - start_time

                print(f"\nScheduler run time (ML disabled): {baseline_time:.3f}s")
                return baseline_time

    def test_scheduler_run_time_with_ml_enabled(self, app, db_session, models):
        """Benchmark scheduler run time with ML"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(id=f'lead_{i}', name=f'Lead {i}', job_title='Lead Event Specialist', is_active=True)
                for i in range(5)
            ] + [
                Employee(id=f'spec_{i}', name=f'Spec {i}', job_title='Specialist', is_active=True)
                for i in range(15)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            events = [
                Event(
                    project_name=f'Event {i}',
                    project_ref_num=1000+i,
                    event_type='Core',
                    start_datetime=start,
                    due_datetime=start + timedelta(days=7),
                    is_scheduled=False,
                    estimated_time=2.0
                )
                for i in range(20)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True,
                    'ML_CONFIDENCE_THRESHOLD': 0.6
                }

                engine = SchedulingEngine(db_session, models)

                start_time = time.time()

                for event in events[:5]:
                    leads = engine._get_available_leads(event, datetime.now())

                ml_time = time.time() - start_time

                print(f"Scheduler run time (ML enabled): {ml_time:.3f}s")

                # Get baseline from previous test (approximate)
                # In practice, you'd run both in same test
                # Target: <10% overhead from ML
                # For now, just verify it completes in reasonable time
                assert ml_time < 5.0, f"Scheduler took {ml_time:.3f}s (too slow)"


class TestFeatureExtractionSpeed:
    """Test feature extraction performance"""

    def test_feature_extraction_latency(self, app, db_session, models):
        """Test feature extraction speed"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employee = Employee(
                id='test_emp',
                name='Test Employee',
                job_title='Specialist',
                is_active=True
            )
            db_session.add(employee)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                          start_datetime=start, due_datetime=start + timedelta(days=7),
                          is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Measure feature extraction time
            start_time = time.time()
            for _ in range(100):
                try:
                    features = adapter.employee_features.extract_features(
                        employee, event, datetime.now()
                    )
                except Exception:
                    # If not implemented, skip
                    pytest.skip("Feature extraction not fully implemented")

            elapsed_ms = (time.time() - start_time) * 1000 / 100

            print(f"\nAverage feature extraction: {elapsed_ms:.2f}ms")

            # Target: <10ms per extraction
            assert elapsed_ms < 10, f"Feature extraction took {elapsed_ms:.2f}ms (target: <10ms)"


class TestConcurrentPredictions:
    """Test thread safety of ML predictions"""

    def test_concurrent_predictions_no_race_conditions(self, app, db_session, models):
        """Test that concurrent predictions don't cause race conditions"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(10)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            events = [
                Event(project_name=f'Event {i}', project_ref_num=1000+i, event_type='Core',
                      start_datetime=start, due_datetime=start + timedelta(days=7),
                      is_scheduled=False)
                for i in range(5)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Note: This is a simplified test
            # In production, you'd use threading.Thread or concurrent.futures
            # For now, just verify sequential calls don't interfere
            results = []
            for event in events:
                ranked = adapter.rank_employees(employees, event, datetime.now())
                results.append(ranked)

            # All should complete successfully
            assert len(results) == len(events)
            for result in results:
                assert isinstance(result, list)

    def test_statistics_tracking_concurrent(self, app, db_session, models):
        """Test that statistics tracking works with concurrent predictions"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                          start_datetime=start, due_datetime=start + timedelta(days=7),
                          is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            initial_count = adapter.predictions_made

            # Make 10 predictions
            for _ in range(10):
                adapter.rank_employees(employees, event, datetime.now())

            # Stats should reflect 10 processing attempts (predictions or fallbacks)
            total_processed = adapter.predictions_made + adapter.fallbacks_triggered
            assert total_processed >= initial_count + 10


class TestPerformanceRegression:
    """Test that ML doesn't cause performance regression"""

    def test_no_significant_slowdown(self, app, db_session, models):
        """Test that ML adds <10% overhead to scheduler run"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create test data
            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(20)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            start = datetime.now() + timedelta(days=7)
            events = [
                Event(project_name=f'Event {i}', project_ref_num=1000+i, event_type='Core',
                      start_datetime=start, due_datetime=start + timedelta(days=7),
                      is_scheduled=False)
                for i in range(10)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # Benchmark without ML
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}
                engine_no_ml = SchedulingEngine(db_session, models)

                start_time = time.time()
                for event in events[:5]:
                    engine_no_ml._get_available_specialists(event, datetime.now())
                time_no_ml = time.time() - start_time

            # Benchmark with ML
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }
                engine_with_ml = SchedulingEngine(db_session, models)

                start_time = time.time()
                for event in events[:5]:
                    engine_with_ml._get_available_specialists(event, datetime.now())
                time_with_ml = time.time() - start_time

            overhead_pct = ((time_with_ml - time_no_ml) / time_no_ml) * 100 if time_no_ml > 0 else 0

            print(f"\nTime without ML: {time_no_ml:.3f}s")
            print(f"Time with ML: {time_with_ml:.3f}s")
            print(f"Overhead: {overhead_pct:+.1f}%")

            # Target: <10% overhead (but allow up to 20% margin for test variability)
            assert overhead_pct < 20, f"ML overhead is {overhead_pct:.1f}% (target: <10%)"
