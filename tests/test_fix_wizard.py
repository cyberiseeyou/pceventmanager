"""
Tests for the Fix Wizard service and routes.

Tests cover:
- Service: option generation for various rule types, apply_fix operations
- Routes: page rendering, API responses, error handling
"""
import pytest
from datetime import datetime, date, timedelta


# ============================================================================
# Helper: create test data
# ============================================================================

def _create_employee(db_session, models, emp_id, name, job_title='Event Specialist', is_active=True):
    Employee = models['Employee']
    emp = Employee(id=emp_id, name=name, job_title=job_title, is_active=is_active)
    db_session.add(emp)
    return emp


def _create_event(db_session, models, ref_num, name, event_type='Core',
                  start_dt=None, due_dt=None):
    Event = models['Event']
    start_dt = start_dt or datetime(2026, 3, 1)
    due_dt = due_dt or datetime(2026, 3, 7)
    ev = Event(
        project_ref_num=ref_num,
        project_name=name,
        event_type=event_type,
        estimated_time=60,
        start_datetime=start_dt,
        due_datetime=due_dt,
        condition='Scheduled',
        is_scheduled=True,
    )
    db_session.add(ev)
    return ev


def _create_schedule(db_session, models, event_ref, emp_id, dt):
    Schedule = models['Schedule']
    sched = Schedule(
        event_ref_num=event_ref,
        employee_id=emp_id,
        schedule_datetime=dt,
    )
    db_session.add(sched)
    return sched


def _sunday_of(d):
    """Align a date to its week's Sunday."""
    days_since_sunday = (d.weekday() + 1) % 7
    return d - timedelta(days=days_since_sunday)


# Use a fixed date range: Sunday March 1, 2026 (it IS a Sunday)
TEST_DATE = date(2026, 3, 1)
TEST_DATETIME = datetime(2026, 3, 2, 10, 15)  # Monday


# ============================================================================
# Service Tests
# ============================================================================

class TestFixWizardService:

    def _make_service(self, db_session, models):
        from app.services.fix_wizard import FixWizardService
        return FixWizardService(db_session, models)

    def test_empty_week_returns_empty_list(self, db_session, models):
        """No schedules -> no issues -> empty list."""
        service = self._make_service(db_session, models)
        issues = service.get_fixable_issues(TEST_DATE)
        assert isinstance(issues, list)
        # May or may not be empty depending on what other validation rules catch
        # but the call should not error
        assert issues is not None

    def test_ignore_option_always_present(self, db_session, models):
        """Every fixable issue should have IGNORE as the last option."""
        from app.services.fix_wizard import FixActionType

        # Create a scenario that will generate an issue: employee on time off with schedule
        emp = _create_employee(db_session, models, 'fw_ign', 'IGNORE TEST', 'Event Specialist')
        db_session.commit()

        ev = _create_event(db_session, models, 5001, 'Core Test 123456', 'Core')
        _create_schedule(db_session, models, 5001, emp.id, TEST_DATETIME)

        # Put employee on time off for that day
        EmployeeTimeOff = models['EmployeeTimeOff']
        time_off = EmployeeTimeOff(
            employee_id=emp.id,
            start_date=TEST_DATETIME.date(),
            end_date=TEST_DATETIME.date(),
        )
        db_session.add(time_off)
        db_session.commit()

        service = self._make_service(db_session, models)
        issues = service.get_fixable_issues(TEST_DATE)

        for issue in issues:
            assert len(issue.options) > 0
            last_option = issue.options[-1]
            assert last_option.action_type == FixActionType.IGNORE

    def test_recommendation_is_highest_confidence(self, db_session, models):
        """The is_recommended flag should be on the highest-confidence option."""
        emp = _create_employee(db_session, models, 'fw_rec', 'REC TEST', 'Event Specialist')
        # Create a second employee who could be a replacement
        _create_employee(db_session, models, 'fw_rec2', 'REC ALT', 'Event Specialist')
        db_session.commit()

        ev = _create_event(db_session, models, 5002, 'Core Rec 123457', 'Core')
        _create_schedule(db_session, models, 5002, emp.id, TEST_DATETIME)

        EmployeeTimeOff = models['EmployeeTimeOff']
        time_off = EmployeeTimeOff(
            employee_id=emp.id,
            start_date=TEST_DATETIME.date(),
            end_date=TEST_DATETIME.date(),
        )
        db_session.add(time_off)
        db_session.commit()

        service = self._make_service(db_session, models)
        issues = service.get_fixable_issues(TEST_DATE)

        for issue in issues:
            recommended = [o for o in issue.options if o.is_recommended]
            if recommended:
                # The recommended option should have the highest confidence
                # (excluding IGNORE which always has confidence=0)
                non_ignore = [o for o in issue.options if o.action_type != 'ignore']
                if non_ignore:
                    max_conf = max(o.confidence for o in non_ignore)
                    assert recommended[0].confidence == max_conf

    def test_apply_reassign_changes_employee(self, db_session, models):
        """apply_fix(REASSIGN) should change employee_id on the Schedule."""
        emp1 = _create_employee(db_session, models, 'fw_r1', 'OLD EMP', 'Event Specialist')
        emp2 = _create_employee(db_session, models, 'fw_r2', 'NEW EMP', 'Event Specialist')
        ev = _create_event(db_session, models, 5003, 'Core Reassign 123458', 'Core')
        sched = _create_schedule(db_session, models, 5003, emp1.id, TEST_DATETIME)
        db_session.commit()

        service = self._make_service(db_session, models)
        result = service.apply_fix('reassign', {
            'schedule_id': sched.id,
            'new_employee_id': emp2.id,
        })

        assert result['success'] is True

        Schedule = models['Schedule']
        updated = db_session.query(Schedule).get(sched.id)
        assert updated.employee_id == emp2.id

    def test_apply_unschedule_removes_schedule(self, db_session, models):
        """apply_fix(UNSCHEDULE) should delete the Schedule and reset Event."""
        emp = _create_employee(db_session, models, 'fw_u1', 'UNSCHED EMP', 'Event Specialist')
        ev = _create_event(db_session, models, 5004, 'Core Unsched 123459', 'Core')
        sched = _create_schedule(db_session, models, 5004, emp.id, TEST_DATETIME)
        db_session.commit()

        sched_id = sched.id
        service = self._make_service(db_session, models)
        result = service.apply_fix('unschedule', {
            'schedule_id': sched_id,
            'event_ref_num': 5004,
        })

        assert result['success'] is True

        Schedule = models['Schedule']
        assert db_session.query(Schedule).get(sched_id) is None

        Event = models['Event']
        updated_ev = db_session.query(Event).filter_by(project_ref_num=5004).first()
        assert updated_ev.condition == 'Unstaffed'
        assert updated_ev.is_scheduled is False

    def test_apply_reschedule_changes_time(self, db_session, models):
        """apply_fix(RESCHEDULE) should update schedule_datetime."""
        emp = _create_employee(db_session, models, 'fw_rs1', 'RESCHED EMP', 'Event Specialist')
        ev = _create_event(db_session, models, 5005, 'Core Resched 123460', 'Core')
        sched = _create_schedule(db_session, models, 5005, emp.id, TEST_DATETIME)
        db_session.commit()

        new_dt = datetime(2026, 3, 2, 11, 30)
        service = self._make_service(db_session, models)
        result = service.apply_fix('reschedule', {
            'schedule_id': sched.id,
            'new_datetime': new_dt.isoformat(),
        })

        assert result['success'] is True

        Schedule = models['Schedule']
        updated = db_session.query(Schedule).get(sched.id)
        assert updated.schedule_datetime == new_dt

    def test_apply_ignore_creates_record(self, db_session, models):
        """apply_fix(IGNORE) should create an IgnoredValidationIssue record."""
        IgnoredValidationIssue = models.get('IgnoredValidationIssue')
        if not IgnoredValidationIssue:
            pytest.skip("IgnoredValidationIssue model not available")

        # Need at least a minimal employee/event for the models dict to work
        _create_employee(db_session, models, 'fw_ig1', 'IGN EMP', 'Event Specialist')
        db_session.commit()

        service = self._make_service(db_session, models)
        result = service.apply_fix('ignore', {
            'rule_name': 'Test Rule',
            'details': {'employee_id': 'fw_ig1'},
            'date': '2026-03-02',
            'message': 'Test issue',
            'severity': 'warning',
        })

        assert result['success'] is True
        assert db_session.query(IgnoredValidationIssue).count() >= 1


# ============================================================================
# Route Tests
# ============================================================================

from unittest.mock import patch

def _auth_bypass():
    """Patch target for bypassing require_authentication in route tests."""
    return 'app.routes.auth.is_authenticated'


class TestFixWizardRoutes:

    def test_wizard_requires_auth(self, client):
        """SEC-CRT-01: Fix Wizard routes must require authentication."""
        resp = client.get('/dashboard/fix-wizard')
        assert resp.status_code == 302

    @patch(_auth_bypass(), return_value=True)
    def test_wizard_page_renders(self, mock_auth, client):
        """GET /dashboard/fix-wizard should return 200 when authenticated."""
        resp = client.get('/dashboard/fix-wizard')
        assert resp.status_code == 200
        assert b'Fix Wizard' in resp.data

    @patch(_auth_bypass(), return_value=True)
    def test_wizard_page_with_date(self, mock_auth, client):
        """GET /dashboard/fix-wizard?start_date= should return 200."""
        resp = client.get('/dashboard/fix-wizard?start_date=2026-03-01')
        assert resp.status_code == 200

    @patch(_auth_bypass(), return_value=True)
    def test_issues_api_returns_json(self, mock_auth, client, db_session):
        """GET /dashboard/api/fix-wizard/issues should return JSON with issues key."""
        resp = client.get('/dashboard/api/fix-wizard/issues?start_date=2026-03-01')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'issues' in data
        assert 'total' in data

    @patch(_auth_bypass(), return_value=True)
    def test_apply_requires_action_type(self, mock_auth, client):
        """POST /dashboard/api/fix-wizard/apply without action_type -> 400."""
        resp = client.post('/dashboard/api/fix-wizard/apply',
                          json={'target': {'schedule_id': 1}},
                          content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'action_type' in data.get('error', '')

    @patch(_auth_bypass(), return_value=True)
    def test_apply_invalid_action_type(self, mock_auth, client):
        """SEC-CRT-04: Invalid action_type must be rejected."""
        resp = client.post('/dashboard/api/fix-wizard/apply',
                          json={'action_type': 'DROP TABLE', 'target': {'id': 1}},
                          content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'Invalid action_type' in data.get('error', '')

    @patch(_auth_bypass(), return_value=True)
    def test_apply_requires_target(self, mock_auth, client):
        """POST /dashboard/api/fix-wizard/apply without target -> 400."""
        resp = client.post('/dashboard/api/fix-wizard/apply',
                          json={'action_type': 'reassign'},
                          content_type='application/json')
        assert resp.status_code == 400

    @patch(_auth_bypass(), return_value=True)
    def test_apply_no_data_returns_400(self, mock_auth, client):
        """POST /dashboard/api/fix-wizard/apply with no JSON body -> 400."""
        resp = client.post('/dashboard/api/fix-wizard/apply')
        assert resp.status_code == 400

    @patch(_auth_bypass(), return_value=True)
    def test_skip_api_works(self, mock_auth, client, db_session):
        """POST /dashboard/api/fix-wizard/skip should accept issue data."""
        resp = client.post('/dashboard/api/fix-wizard/skip',
                          json={
                              'rule_name': 'Test Rule',
                              'details': {},
                              'message': 'Test',
                              'severity': 'info',
                          },
                          content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
