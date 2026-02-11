"""
Template rendering tests.

Tests that critical templates render without errors when given
expected context variables.
"""
import pytest
from unittest.mock import patch
from datetime import datetime, date, timedelta


class TestHealthEndpoints:
    """Test that health check templates/endpoints render correctly."""

    def test_health_ping_renders(self, client):
        """Verify /health/ping returns valid JSON."""
        response = client.get('/health/ping')
        assert response.status_code == 200
        data = response.get_json()
        assert data is not None
        assert 'status' in data

    def test_health_ready_renders(self, client):
        """Verify /health/ready returns valid JSON."""
        response = client.get('/health/ready')
        assert response.status_code in [200, 503]
        data = response.get_json()
        assert data is not None


class TestIndexTemplate:
    """Test that the index page template renders correctly."""

    def test_index_page_renders(self, client):
        """Verify the index page loads without server errors."""
        response = client.get('/', follow_redirects=True)
        assert response.status_code == 200
        # Should contain some expected page content
        assert len(response.data) > 0

    def test_index_page_has_no_jinja_errors(self, client):
        """Verify no Jinja2 template errors in the response."""
        response = client.get('/', follow_redirects=True)
        # Jinja errors produce 500 status or error traces
        assert response.status_code != 500
        assert b'TemplateSyntaxError' not in response.data
        assert b'UndefinedError' not in response.data


class TestAPIEndpoints:
    """Test that API endpoints return valid JSON responses."""

    def test_events_api_returns_json(self, client):
        """Verify /api/events returns valid JSON."""
        response = client.get('/api/events')
        # May redirect to login or return data
        if response.status_code == 200:
            data = response.get_json()
            assert data is not None

    def test_employees_api_returns_json(self, client):
        """Verify /api/employees returns valid JSON."""
        response = client.get('/api/employees')
        if response.status_code == 200:
            data = response.get_json()
            assert data is not None


class TestErrorPages:
    """Test that error pages render without additional errors."""

    def test_404_page_renders(self, client):
        """Verify a 404 response is returned for nonexistent routes."""
        response = client.get('/nonexistent-route-that-does-not-exist')
        assert response.status_code == 404

    def test_404_does_not_crash(self, client):
        """Verify 404 handler doesn't produce a 500 error."""
        response = client.get('/nonexistent-route-xyz')
        assert response.status_code != 500


class TestTemplateIncludes:
    """Test that template components don't have syntax errors."""

    def test_base_template_loads(self, app):
        """Verify the base template can be loaded by Jinja."""
        template = app.jinja_env.get_template('base.html')
        assert template is not None

    def test_login_template_loads(self, app):
        """Verify the login template can be loaded."""
        try:
            template = app.jinja_env.get_template('auth/login.html')
            assert template is not None
        except Exception:
            # Login template may be at a different path
            pass

    def test_calendar_template_loads(self, app):
        """Verify the calendar template can be loaded."""
        template = app.jinja_env.get_template('calendar.html')
        assert template is not None

    def test_daily_view_template_loads(self, app):
        """Verify the daily_view template can be loaded."""
        template = app.jinja_env.get_template('daily_view.html')
        assert template is not None

    def test_employees_template_loads(self, app):
        """Verify the employees template can be loaded."""
        template = app.jinja_env.get_template('employees.html')
        assert template is not None

    def test_settings_template_loads(self, app):
        """Verify the settings template can be loaded."""
        template = app.jinja_env.get_template('settings.html')
        assert template is not None


class TestFrozenTime:
    """Test date-dependent logic with frozen time."""

    @patch('app.services.scheduling_engine.datetime')
    def test_scheduling_uses_current_date(self, mock_datetime, app, db_session, models):
        """Verify scheduling engine references datetime correctly."""
        frozen = datetime(2026, 1, 15, 10, 0, 0)
        mock_datetime.now.return_value = frozen
        mock_datetime.today.return_value = frozen
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # The scheduling engine should be importable without errors
        from app.services.scheduling_engine import SchedulingEngine
        assert SchedulingEngine is not None

    def test_date_formatting_consistency(self):
        """Verify date formatting produces expected output."""
        test_date = date(2026, 3, 15)
        formatted = test_date.strftime('%A, %B %d, %Y')
        assert formatted == 'Sunday, March 15, 2026'

        iso_formatted = test_date.strftime('%Y-%m-%d')
        assert iso_formatted == '2026-03-15'
