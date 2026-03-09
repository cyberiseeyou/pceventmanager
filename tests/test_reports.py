"""Tests for the Reports section routes and CSV exports."""
import pytest
from datetime import date, timedelta


class TestReportRoutes:
    """Test that all report pages load successfully."""

    def test_reports_hub(self, client):
        resp = client.get('/reports/')
        assert resp.status_code == 200
        assert b'Reports' in resp.data

    def test_event_statistics(self, client, db_session):
        resp = client.get('/reports/event-statistics')
        assert resp.status_code == 200
        assert b'Event Statistics' in resp.data

    def test_event_statistics_with_dates(self, client, db_session):
        resp = client.get('/reports/event-statistics?start_date=2026-03-01&end_date=2026-03-07')
        assert resp.status_code == 200

    def test_employee_schedules(self, client, db_session):
        resp = client.get('/reports/employee-schedules')
        assert resp.status_code == 200
        assert b'Employee Schedule Details' in resp.data

    def test_event_type_breakdown(self, client, db_session):
        resp = client.get('/reports/event-type-breakdown')
        assert resp.status_code == 200
        assert b'Event Type Breakdown' in resp.data

    def test_employee_workload(self, client, db_session):
        resp = client.get('/reports/employee-workload')
        assert resp.status_code == 200
        assert b'Employee Workload' in resp.data

    def test_attendance(self, client, db_session):
        resp = client.get('/reports/attendance')
        assert resp.status_code == 200
        assert b'Attendance Report' in resp.data

    def test_scheduling_coverage(self, client, db_session):
        resp = client.get('/reports/scheduling-coverage')
        assert resp.status_code == 200
        assert b'Scheduling Coverage' in resp.data

    def test_time_off(self, client, db_session):
        resp = client.get('/reports/time-off')
        assert resp.status_code == 200
        assert b'Time Off Summary' in resp.data

    def test_invalid_dates_fallback_to_defaults(self, client, db_session):
        resp = client.get('/reports/event-statistics?start_date=bad&end_date=bad')
        assert resp.status_code == 200


class TestReportExports:
    """Test CSV exports return downloadable files."""

    def test_event_statistics_export(self, client, db_session):
        resp = client.get('/reports/event-statistics/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'
        assert 'attachment' in resp.headers.get('Content-Disposition', '')

    def test_employee_schedules_export(self, client, db_session):
        resp = client.get('/reports/employee-schedules/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_event_type_breakdown_export(self, client, db_session):
        resp = client.get('/reports/event-type-breakdown/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_employee_workload_export(self, client, db_session):
        resp = client.get('/reports/employee-workload/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_attendance_export(self, client, db_session):
        resp = client.get('/reports/attendance/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_scheduling_coverage_export(self, client, db_session):
        resp = client.get('/reports/scheduling-coverage/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_time_off_export(self, client, db_session):
        resp = client.get('/reports/time-off/export')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_export_with_date_params(self, client, db_session):
        resp = client.get('/reports/event-statistics/export?start_date=2026-03-01&end_date=2026-03-07')
        assert resp.status_code == 200
        assert 'event_statistics_2026-03-01_2026-03-07.csv' in resp.headers.get('Content-Disposition', '')
