"""Tests for Playwright-based Walmart authentication module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPlaywrightAuth:
    """Test the PlaywrightWalmartAuth class."""

    def test_import(self):
        """Module can be imported."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        assert PlaywrightWalmartAuth is not None

    def test_init(self):
        """Constructor stores credentials."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth(
            username="testuser",
            password="testpass",
            mfa_credential_id="cred123"
        )
        assert auth.username == "testuser"
        assert auth.password == "testpass"
        assert auth.mfa_credential_id == "cred123"
        assert auth.cookies == []
        assert auth.last_error is None

    def test_init_internal_state_is_none(self):
        """Constructor initializes internal Playwright state to None."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        assert auth._playwright is None
        assert auth._browser is None
        assert auth._context is None
        assert auth._page is None

    def test_extract_cookies_returns_list(self):
        """extract_cookies_for_requests returns cookie dicts."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        auth.cookies = [
            {"name": "auth", "value": "tok123", "domain": ".wal-mart.com", "path": "/"},
            {"name": "sid", "value": "sess456", "domain": ".wal-mart.com", "path": "/"},
        ]
        result = auth.extract_cookies_for_requests()
        assert len(result) == 2
        assert result[0]["name"] == "auth"
        assert result[1]["value"] == "sess456"

    def test_extract_cookies_returns_copy(self):
        """extract_cookies_for_requests returns a new list, not a reference."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        auth.cookies = [{"name": "a", "value": "1"}]
        result = auth.extract_cookies_for_requests()
        assert result is not auth.cookies
        assert result == auth.cookies

    def test_extract_cookies_empty(self):
        """extract_cookies_for_requests returns empty list before auth."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        result = auth.extract_cookies_for_requests()
        assert result == []

    def test_inject_cookies_into_session(self):
        """inject_cookies_into_session populates a requests.Session cookie jar."""
        import requests
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        auth.cookies = [
            {"name": "token", "value": "abc", "domain": ".wal-mart.com", "path": "/", "secure": True, "httpOnly": True},
        ]
        session = requests.Session()
        auth.inject_cookies_into_session(session)
        assert session.cookies.get("token") == "abc"

    def test_inject_multiple_cookies(self):
        """inject_cookies_into_session handles multiple cookies."""
        import requests
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        auth.cookies = [
            {"name": "a", "value": "1", "domain": ".wal-mart.com", "path": "/"},
            {"name": "b", "value": "2", "domain": ".wal-mart.com", "path": "/"},
            {"name": "c", "value": "3", "domain": ".wal-mart.com", "path": "/api"},
        ]
        session = requests.Session()
        auth.inject_cookies_into_session(session)
        assert session.cookies.get("a") == "1"
        assert session.cookies.get("b") == "2"
        assert session.cookies.get("c") == "3"

    def test_run_async_helper(self):
        """_run_async creates a new event loop when none is running."""
        from app.integrations.edr.playwright_auth import _run_async
        import asyncio

        async def coro():
            return 42

        result = _run_async(coro())
        assert result == 42

    def test_run_async_with_complex_return(self):
        """_run_async properly returns complex objects."""
        from app.integrations.edr.playwright_auth import _run_async

        async def coro():
            return {"status": 200, "body": "ok"}

        result = _run_async(coro())
        assert result == {"status": 200, "body": "ok"}

    def test_class_constants(self):
        """Class-level URL constants are correct."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        assert "retaillink.login.wal-mart.com" in PlaywrightWalmartAuth.LOGIN_URL
        assert PlaywrightWalmartAuth.LOGIN_API == "/api/login"
        assert PlaywrightWalmartAuth.MFA_SEND_API == "/api/mfa/sendCode"
        assert PlaywrightWalmartAuth.MFA_VALIDATE_API == "/api/mfa/validateCode"

    def test_cleanup_safe_when_not_started(self):
        """cleanup() does not raise when browser was never started."""
        from app.integrations.edr.playwright_auth import PlaywrightWalmartAuth
        auth = PlaywrightWalmartAuth("u", "p", "c")
        # Should not raise
        auth.cleanup()
        assert auth._browser is None
        assert auth._playwright is None


class TestEDRReportGeneratorIntegration:
    """Test that EDRReportGenerator delegates to PlaywrightWalmartAuth."""

    def test_report_generator_has_pw_auth_attr(self):
        """EDRReportGenerator has _pw_auth attribute initialized to None."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        gen = EDRReportGenerator()
        assert gen._pw_auth is None

    def test_step1_creates_pw_auth_and_delegates(self):
        """step1_submit_password creates PlaywrightWalmartAuth and delegates."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        from unittest.mock import patch, MagicMock

        gen = EDRReportGenerator()
        gen.username = "testuser"
        gen.password = "testpass"
        gen.mfa_credential_id = "cred123"

        with patch('app.integrations.edr.report_generator.PlaywrightWalmartAuth') as MockPWAuth:
            mock_instance = MagicMock()
            mock_instance.step1_submit_password.return_value = True
            MockPWAuth.return_value = mock_instance

            result = gen.step1_submit_password()

            assert result is True
            MockPWAuth.assert_called_once_with("testuser", "testpass", "cred123")
            mock_instance.step1_submit_password.assert_called_once()

    def test_step1_propagates_last_error(self):
        """step1 propagates last_error from PlaywrightWalmartAuth on failure."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        from unittest.mock import patch, MagicMock

        gen = EDRReportGenerator()
        gen.username = "u"
        gen.password = "p"
        gen.mfa_credential_id = "c"

        with patch('app.integrations.edr.report_generator.PlaywrightWalmartAuth') as MockPWAuth:
            mock_instance = MagicMock()
            mock_instance.step1_submit_password.return_value = False
            mock_instance.last_error = "HTTP 412: PerimeterX blocked"
            MockPWAuth.return_value = mock_instance

            result = gen.step1_submit_password()

            assert result is False
            assert gen.last_error == "HTTP 412: PerimeterX blocked"

    def test_step2_delegates_to_pw_auth(self):
        """step2_request_mfa_code delegates to PlaywrightWalmartAuth when active."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        from unittest.mock import MagicMock

        gen = EDRReportGenerator()
        mock_pw = MagicMock()
        mock_pw.step2_request_mfa_code.return_value = True
        gen._pw_auth = mock_pw

        result = gen.step2_request_mfa_code()

        assert result is True
        mock_pw.step2_request_mfa_code.assert_called_once()

    def test_step3_transfers_cookies_to_session(self):
        """step3 extracts cookies from Playwright and injects into requests.Session."""
        from app.integrations.edr.report_generator import EDRReportGenerator
        from unittest.mock import MagicMock

        gen = EDRReportGenerator()
        gen.username = "u"
        gen.password = "p"
        gen.mfa_credential_id = "c"

        mock_pw = MagicMock()
        mock_pw.step3_validate_mfa_code.return_value = True
        mock_pw.cookies = [
            {"name": "auth-token", "value": "tok", "domain": ".wal-mart.com", "path": "/"},
        ]
        gen._pw_auth = mock_pw

        result = gen.step3_validate_mfa_code("123456")

        assert result is True
        mock_pw.step3_validate_mfa_code.assert_called_once_with("123456")
        mock_pw.inject_cookies_into_session.assert_called_once_with(gen.session)
        # _pw_auth should be cleared after successful step3
        assert gen._pw_auth is None
