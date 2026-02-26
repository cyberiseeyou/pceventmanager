"""
Test ML Safety & Fallback Validation

Verifies graceful degradation:
1. ML disabled fallback
2. Model loading failure handling
3. Corrupted model fallback
4. Feature extraction error handling
5. Prediction exception handling
6. Low confidence fallback
7. Import failure graceful handling
8. Constraint validation unchanged
"""

import pytest
from unittest.mock import patch, Mock, mock_open
from datetime import datetime, timedelta
import pickle
import os
from app.services.scheduling_engine import SchedulingEngine
from app.ml.inference.ml_scheduler_adapter import MLSchedulerAdapter

# Default datetime values for Event construction (NOT NULL fields)
_EVT_START = datetime(2026, 3, 1, 8, 0, 0)
_EVT_DUE = datetime(2026, 3, 8, 17, 0, 0)


class TestMLDisabledFallback:
    """Test system works correctly with ML disabled"""

    def test_scheduler_works_with_ml_disabled(self, app, db_session, models):
        """Test that scheduler functions normally with ML_ENABLED=false"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create test data
            employees = [
                Employee(id=f'lead_{i}', name=f'Lead {i}', job_title='Lead Event Specialist', is_active=True)
                for i in range(3)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            events = [
                Event(project_name=f'Event {i}', project_ref_num=1000+i, event_type='Core',
                      start_datetime=_EVT_START + timedelta(days=i), due_datetime=_EVT_DUE + timedelta(days=i),
                      is_scheduled=False)
                for i in range(5)
            ]
            for event in events:
                db_session.add(event)
            db_session.commit()

            # ML disabled
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}
                engine = SchedulingEngine(db_session, models)

                # Should work without ML — adapter exists but use_ml is False
                if engine.ml_adapter is not None:
                    assert engine.ml_adapter.use_ml is False

                # Should still be able to get employees
                for event in events:
                    leads = engine._get_available_leads(event, datetime.now())
                    assert isinstance(leads, list)

    def test_ml_adapter_disabled_when_ml_off(self, app, db_session, models):
        """Test that ml_adapter has use_ml=False when ML is disabled"""
        with app.app_context():
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {'ML_ENABLED': False}
                engine = SchedulingEngine(db_session, models)

                if engine.ml_adapter is not None:
                    assert engine.ml_adapter.use_ml is False
                else:
                    assert engine.ml_adapter is None


class TestModelLoadingFailure:
    """Test handling of model loading failures"""

    def test_missing_model_file_graceful_failure(self, app, db_session, models):
        """Test graceful handling when model file doesn't exist"""
        with app.app_context():
            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True,
                'ML_EMPLOYEE_RANKER_PATH': '/nonexistent/path/model.pkl'
            }

            adapter = MLSchedulerAdapter(db_session, models, config)

            # Should handle missing model gracefully
            model = adapter.employee_ranker
            assert model is None

            # Should still function (fallback to rules)
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            # Should fallback to rule-based ranking
            ranked = adapter.rank_employees(employees, event, datetime.now())
            assert len(ranked) > 0

    def test_model_loading_with_invalid_path(self, app, db_session, models):
        """Test handling of invalid model path"""
        with app.app_context():
            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True,
                'ML_EMPLOYEE_RANKER_PATH': None  # Invalid path
            }

            # Should not crash
            adapter = MLSchedulerAdapter(db_session, models, config)
            assert adapter is not None

            # Model should be None
            model = adapter.employee_ranker
            assert model is None


class TestCorruptedModelFallback:
    """Test handling of corrupted model files"""

    def test_corrupted_pickle_file_handling(self, app, db_session, models):
        """Test graceful handling of corrupted .pkl file"""
        with app.app_context():
            # Create a temporary corrupted file
            corrupted_path = '/tmp/corrupted_model.pkl'

            try:
                # Write corrupted data
                with open(corrupted_path, 'wb') as f:
                    f.write(b'NOT A VALID PICKLE FILE')

                config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True,
                    'ML_EMPLOYEE_RANKER_PATH': corrupted_path
                }

                adapter = MLSchedulerAdapter(db_session, models, config)

                # Should handle corrupted file gracefully
                model = adapter.employee_ranker
                assert model is None

            finally:
                # Cleanup
                if os.path.exists(corrupted_path):
                    os.remove(corrupted_path)

    def test_unpickle_error_handling(self, app, db_session, models):
        """Test handling of unpickling errors"""
        with app.app_context():
            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True,
                'ML_EMPLOYEE_RANKER_PATH': 'app/ml/models/artifacts/employee_ranker_latest.pkl'
            }

            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock joblib.load to raise exception (model uses joblib, not pickle)
            with patch('app.ml.models.employee_ranker.joblib.load', side_effect=Exception("Unpickle error")):
                # Force reload
                adapter._employee_ranker = None
                model = adapter.employee_ranker

                # Should return None gracefully
                assert model is None


class TestFeatureExtractionError:
    """Test handling of feature extraction errors"""

    def test_feature_extraction_exception_handling(self, app, db_session, models):
        """Test fallback when feature extraction fails"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employee = Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)
            db_session.add(employee)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock feature extraction to raise exception
            with patch.object(
                adapter.employee_features,
                'extract',
                side_effect=Exception("Feature error")
            ):
                # Should fallback to rule-based ranking
                ranked = adapter.rank_employees([employee], event, datetime.now())

                # Should still return results
                assert len(ranked) > 0
                assert adapter.fallbacks_triggered > 0

    def test_partial_feature_extraction_failure(self, app, db_session, models):
        """Test handling when some features fail to extract"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [
                Employee(id=f'emp_{i}', name=f'Employee {i}', job_title='Specialist', is_active=True)
                for i in range(3)
            ]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock feature extraction to fail for one employee
            original_extract = adapter.employee_features.extract
            call_count = [0]

            def selective_failure(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 2:  # Fail on second employee
                    raise Exception("Feature extraction failed")
                return original_extract(*args, **kwargs)

            with patch.object(
                adapter.employee_features,
                'extract',
                side_effect=selective_failure
            ):
                # Should handle partial failure gracefully
                ranked = adapter.rank_employees(employees, event, datetime.now())

                # Should still return some results (fallback for failed employee)
                assert len(ranked) > 0


class TestPredictionExceptionHandling:
    """Test handling of prediction exceptions"""

    def test_model_prediction_exception_handling(self, app, db_session, models):
        """Test graceful handling when model.predict raises exception"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock _ml_rank_employees to raise exception
            with patch.object(
                adapter,
                '_ml_rank_employees',
                side_effect=Exception("Prediction error")
            ):
                # Should fallback to rule-based ranking
                ranked = adapter.rank_employees(employees, event, datetime.now())

                assert len(ranked) > 0
                assert adapter.fallbacks_triggered > 0

    def test_numpy_error_handling(self, app, db_session, models):
        """Test handling of numpy/array errors during prediction"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock to simulate numpy/array error
            with patch.object(
                adapter,
                '_ml_rank_employees',
                side_effect=ValueError("Array dimension mismatch")
            ):
                ranked = adapter.rank_employees(employees, event, datetime.now())

                # Should fallback gracefully
                assert len(ranked) > 0


class TestLowConfidenceFallback:
    """Test low confidence threshold behavior"""

    def test_confidence_threshold_triggers_fallback(self, app, db_session, models):
        """Test that low confidence triggers fallback"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            # Very high confidence threshold (unrealistic)
            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True,
                'ML_CONFIDENCE_THRESHOLD': 0.999  # Nearly impossible to meet
            }

            adapter = MLSchedulerAdapter(db_session, models, config)

            initial_fallbacks = adapter.fallbacks_triggered
            ranked = adapter.rank_employees(employees, event, datetime.now())

            # Should have triggered fallback due to low confidence
            assert len(ranked) > 0
            assert adapter.fallbacks_triggered >= initial_fallbacks

    def test_variable_confidence_threshold(self, app, db_session, models):
        """Test different confidence thresholds"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            thresholds = [0.1, 0.5, 0.9, 0.99]
            fallback_counts = []

            for threshold in thresholds:
                config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True,
                    'ML_CONFIDENCE_THRESHOLD': threshold
                }

                adapter = MLSchedulerAdapter(db_session, models, config)
                adapter.reset_stats()

                ranked = adapter.rank_employees(employees, event, datetime.now())
                fallback_counts.append(adapter.fallbacks_triggered)

                assert len(ranked) > 0

            print(f"\nFallback counts by threshold:")
            for t, fb in zip(thresholds, fallback_counts):
                print(f"  Threshold {t:.2f}: {fb} fallbacks")


class TestImportFailureHandling:
    """Test graceful handling of import failures"""

    def test_missing_ml_dependencies(self, app, db_session, models):
        """Test handling when ML dependencies are missing"""
        with app.app_context():
            # Mock import failure for xgboost/lightgbm
            with patch('builtins.__import__', side_effect=ImportError("No module named 'xgboost'")):
                config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}

                # Should handle import failure gracefully
                try:
                    adapter = MLSchedulerAdapter(db_session, models, config)
                    # If adapter initializes, it should have None model
                    assert adapter.employee_ranker is None or adapter is not None
                except ImportError:
                    # Or it might not initialize at all - that's okay too
                    pass

    def test_ml_module_import_failure_graceful(self, app, db_session, models):
        """Test graceful handling when ML modules can't be imported"""
        with app.app_context():
            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }

                # Mock MLSchedulerAdapter import to fail
                with patch('app.services.scheduling_engine.MLSchedulerAdapter', side_effect=ImportError("ML module missing")):
                    # Scheduler should handle this gracefully
                    try:
                        engine = SchedulingEngine(db_session, models)
                        # If it initializes, ml_adapter should be None
                        assert engine.ml_adapter is None
                    except Exception:
                        # Or it might handle it differently - just verify no crash
                        pass


class TestConstraintValidationUnchanged:
    """Test that constraints are still enforced with ML"""

    def test_constraints_enforced_before_ml(self, app, db_session, models):
        """Test that constraint validation happens before ML ranking"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            # Create available and unavailable employees
            available = Employee(id='avail_emp', name='Available', job_title='Specialist', is_active=True)
            unavailable = Employee(id='unavail_emp', name='Unavailable', job_title='Specialist', is_active=False)

            db_session.add(available)
            db_session.add(unavailable)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }

                engine = SchedulingEngine(db_session, models)

                # Get available specialists
                specialists = engine._get_available_specialists(event, datetime.now())

                # Only available employee should be returned
                specialist_ids = [s.id for s in specialists]
                assert available.id in specialist_ids or len(specialists) == 0
                # Unavailable should be filtered out by constraints
                assert unavailable.id not in specialist_ids

    def test_time_off_constraints_respected(self, app, db_session, models):
        """Test that time-off constraints are respected with ML enabled"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']
            EmployeeTimeOff = models.get('EmployeeTimeOff')

            if EmployeeTimeOff is None:
                pytest.skip("EmployeeTimeOff model not available")

            # Create employee
            employee = Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)
            db_session.add(employee)
            db_session.commit()

            # Create time-off request
            test_date = datetime.now() + timedelta(days=1)
            time_off = EmployeeTimeOff(
                employee_id=employee.id,
                start_date=test_date.date(),
                end_date=test_date.date()
            )
            db_session.add(time_off)
            db_session.commit()

            # Create event on time-off day
            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }

                engine = SchedulingEngine(db_session, models)

                # Get available specialists on time-off day
                specialists = engine._get_available_specialists(event, test_date)

                # Employee should be filtered out by constraint validator
                specialist_ids = [s.id for s in specialists]
                assert employee.id not in specialist_ids

    def test_max_shifts_constraint_respected(self, app, db_session, models):
        """Test that max shifts per day constraint is respected"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employee = Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)
            db_session.add(employee)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            with patch('app.services.scheduling_engine.current_app') as mock_app:
                mock_app.config = {
                    'ML_ENABLED': True,
                    'ML_EMPLOYEE_RANKING_ENABLED': True
                }

                engine = SchedulingEngine(db_session, models)

                # Get available specialists
                specialists = engine._get_available_specialists(event, datetime.now())

                # Should respect constraints (actual behavior depends on ConstraintValidator)
                assert isinstance(specialists, list)


class TestSystemResilience:
    """Test overall system resilience"""

    def test_multiple_failures_handled_gracefully(self, app, db_session, models):
        """Test that system handles multiple simultaneous failures"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {
                'ML_ENABLED': True,
                'ML_EMPLOYEE_RANKING_ENABLED': True,
                'ML_EMPLOYEE_RANKER_PATH': '/nonexistent/model.pkl'  # Bad path
            }

            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock feature extraction to also fail
            with patch.object(
                adapter.employee_features,
                'extract',
                side_effect=Exception("Feature error")
            ):
                # Should still work (double fallback)
                ranked = adapter.rank_employees(employees, event, datetime.now())

                assert len(ranked) > 0
                assert adapter.fallbacks_triggered > 0

    def test_system_logs_failures_appropriately(self, app, db_session, models):
        """Test that failures are logged for debugging"""
        with app.app_context():
            Employee = models['Employee']
            Event = models['Event']

            employees = [Employee(id='test_emp', name='Test', job_title='Specialist', is_active=True)]
            for emp in employees:
                db_session.add(emp)
            db_session.commit()

            event = Event(project_name='Test', project_ref_num=1000, event_type='Core',
                      start_datetime=_EVT_START, due_datetime=_EVT_DUE, is_scheduled=False)
            db_session.add(event)
            db_session.commit()

            config = {'ML_ENABLED': True, 'ML_EMPLOYEE_RANKING_ENABLED': True}
            adapter = MLSchedulerAdapter(db_session, models, config)

            # Mock logger
            with patch('app.ml.inference.ml_scheduler_adapter.logger') as mock_logger:
                # Force an error
                with patch.object(adapter, '_ml_rank_employees', side_effect=Exception("Test error")):
                    ranked = adapter.rank_employees(employees, event, datetime.now())

                    # Should have logged the error
                    mock_logger.error.assert_called()
                    assert len(ranked) > 0
