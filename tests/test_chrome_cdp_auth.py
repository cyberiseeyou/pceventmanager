"""Tests for ChromeEDRAuthenticator Chrome lifecycle management."""
import pytest
from unittest.mock import patch, MagicMock
import subprocess


class TestFindChromeBinary:
    @patch('shutil.which')
    def test_finds_google_chrome(self, mock_which):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        mock_which.side_effect = lambda name: '/usr/bin/google-chrome' if name == 'google-chrome' else None
        auth = ChromeEDRAuthenticator()
        assert auth._find_chrome_binary() == '/usr/bin/google-chrome'

    @patch('shutil.which')
    def test_falls_back_to_chromium(self, mock_which):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        def which_side_effect(name):
            if name == 'chromium-browser':
                return '/usr/bin/chromium-browser'
            return None
        mock_which.side_effect = which_side_effect
        auth = ChromeEDRAuthenticator()
        assert auth._find_chrome_binary() == '/usr/bin/chromium-browser'

    @patch('shutil.which', return_value=None)
    def test_returns_none_when_no_chrome(self, mock_which):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        assert auth._find_chrome_binary() is None


class TestChromeAlreadyRunning:
    @patch('app.integrations.edr.chrome_cdp_auth.http_requests.get')
    def test_detects_running_chrome(self, mock_get):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'Browser': 'Chrome/131.0.0.0'}
        mock_get.return_value = mock_response
        auth = ChromeEDRAuthenticator()
        assert auth._is_chrome_running() is True

    @patch('app.integrations.edr.chrome_cdp_auth.http_requests.get', side_effect=Exception("Connection refused"))
    def test_detects_no_chrome(self, mock_get):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        assert auth._is_chrome_running() is False


class TestCleanup:
    def test_cleanup_kills_process(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_process = MagicMock()
        auth._chrome_process = mock_process
        auth._temp_profile_dir = None
        auth.cleanup()
        mock_process.terminate.assert_called_once()

    def test_cleanup_safe_when_no_process(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        auth._chrome_process = None
        auth._temp_profile_dir = None
        auth.cleanup()  # Should not raise

    def test_cleanup_terminates_xvfb(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_xvfb = MagicMock()
        auth._xvfb_process = mock_xvfb
        auth._chrome_process = None
        auth._temp_profile_dir = None
        auth.cleanup()
        mock_xvfb.terminate.assert_called_once()
        assert auth._xvfb_process is None


class TestEnsureDisplay:
    @patch.dict('os.environ', {'DISPLAY': ':0'})
    def test_uses_existing_display(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        result = auth._ensure_display()
        assert result == ':0'
        assert auth._xvfb_process is None

    @patch.dict('os.environ', {}, clear=True)
    @patch('shutil.which', return_value=None)
    def test_returns_none_when_no_xvfb(self, mock_which):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        result = auth._ensure_display()
        assert result is None
        assert auth._xvfb_process is None

    @patch.dict('os.environ', {}, clear=True)
    @patch('os.path.exists', return_value=True)
    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    @patch('subprocess.Popen')
    @patch('shutil.which', return_value='/usr/bin/Xvfb')
    def test_launches_xvfb_when_no_display(self, mock_which, mock_popen, mock_sleep, mock_exists):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc
        auth = ChromeEDRAuthenticator()
        result = auth._ensure_display()
        assert result == ':99'
        assert auth._xvfb_process is mock_proc
        mock_popen.assert_called_once()

    @patch.dict('os.environ', {}, clear=True)
    @patch('subprocess.Popen', side_effect=OSError("not found"))
    @patch('shutil.which', return_value='/usr/bin/Xvfb')
    def test_falls_back_when_xvfb_fails_to_start(self, mock_which, mock_popen):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        result = auth._ensure_display()
        assert result is None


class TestLoginFlow:
    def _make_auth_with_mock_tab(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_tab = MagicMock()
        auth._tab = mock_tab
        return auth, mock_tab

    @patch('app.integrations.edr.chrome_cdp_auth.threading.Event')
    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step1_navigates_and_submits_credentials(self, mock_sleep, MockEvent):
        mock_event = MockEvent.return_value
        mock_event.wait.return_value = True  # Simulate page load completed
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Page.navigate.return_value = None
        mock_tab.Runtime.evaluate.return_value = {
            'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}
        }
        result = auth.step1_submit_credentials('testuser', 'testpass')
        assert result is True
        mock_tab.Page.navigate.assert_called_once()
        mock_tab.Runtime.evaluate.assert_called_once()

    @patch('app.integrations.edr.chrome_cdp_auth.threading.Event')
    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step1_fails_on_error_response(self, mock_sleep, MockEvent):
        mock_event = MockEvent.return_value
        mock_event.wait.return_value = True  # Simulate page load completed
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Page.navigate.return_value = None
        mock_tab.Runtime.evaluate.return_value = {
            'result': {'type': 'string', 'value': '{"status":"error","message":"Invalid credentials"}'}
        }
        result = auth.step1_submit_credentials('bad', 'creds')
        assert result is False
        assert auth.last_error is not None

    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step2_requests_mfa(self, mock_sleep):
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Runtime.evaluate.return_value = {
            'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}
        }
        result = auth.step2_request_mfa('cred-id-123')
        assert result is True

    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step3_validates_mfa(self, mock_sleep):
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Runtime.evaluate.return_value = {
            'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}
        }
        result = auth.step3_validate_mfa('cred-id-123', '123456')
        assert result is True

    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step3_fails_on_wrong_code(self, mock_sleep):
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Runtime.evaluate.return_value = {
            'result': {'type': 'string', 'value': '{"status":"error","message":"Invalid code"}'}
        }
        result = auth.step3_validate_mfa('cred-id-123', '000000')
        assert result is False


class TestCookieExtraction:
    def test_extract_cookies_returns_walmart_cookies(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_tab = MagicMock()
        auth._tab = mock_tab
        mock_tab.Network.getCookies.return_value = {
            'cookies': [
                {'name': '_px3', 'value': 'abc123', 'domain': '.wal-mart.com', 'path': '/', 'secure': True},
                {'name': 'session', 'value': 'xyz', 'domain': 'retaillink.login.wal-mart.com', 'path': '/', 'secure': True},
                {'name': 'unrelated', 'value': 'foo', 'domain': '.google.com', 'path': '/', 'secure': False},
            ]
        }
        cookies = auth.extract_cookies()
        assert len(cookies) == 2
        names = [c['name'] for c in cookies]
        assert '_px3' in names
        assert 'session' in names
        assert 'unrelated' not in names

    def test_inject_cookies_into_session(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        import requests
        auth = ChromeEDRAuthenticator()
        auth._cookies = [
            {'name': '_px3', 'value': 'abc123', 'domain': '.wal-mart.com', 'path': '/', 'secure': True},
            {'name': 'sid', 'value': 'xyz789', 'domain': 'retaillink.login.wal-mart.com', 'path': '/', 'secure': True},
        ]
        session = requests.Session()
        count = auth.inject_cookies_into_session(session)
        assert count == 2
        cookie_names = [c.name for c in session.cookies]
        assert '_px3' in cookie_names
        assert 'sid' in cookie_names

    def test_extract_cookies_empty_when_no_tab(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        auth._tab = None
        cookies = auth.extract_cookies()
        assert cookies == []


class TestReportGeneratorIntegration:
    @patch('app.integrations.edr.report_generator.EDRReportGenerator.step1_submit_password')
    @patch('app.integrations.edr.chrome_cdp_auth.ChromeEDRAuthenticator')
    def test_chrome_step1_delegates_to_authenticator(self, MockAuth, mock_fallback):
        from app.integrations.edr.report_generator import EDRReportGenerator
        mock_instance = MockAuth.return_value
        mock_instance.launch_chrome.return_value = True
        mock_instance.connect.return_value = True
        mock_instance.step1_submit_credentials.return_value = True
        mock_instance.last_error = None

        gen = EDRReportGenerator()
        gen.username = 'testuser'
        gen.password = 'testpass'
        result = gen.chrome_step1_submit_password()

        assert result is True
        mock_instance.launch_chrome.assert_called_once()
        mock_instance.connect.assert_called_once()
        mock_instance.step1_submit_credentials.assert_called_once_with('testuser', 'testpass')
        mock_fallback.assert_not_called()

    @patch('app.integrations.edr.report_generator.EDRReportGenerator.step1_submit_password')
    @patch('app.integrations.edr.chrome_cdp_auth.ChromeEDRAuthenticator')
    def test_chrome_step1_falls_back_on_launch_failure(self, MockAuth, mock_fallback):
        from app.integrations.edr.report_generator import EDRReportGenerator
        mock_instance = MockAuth.return_value
        mock_instance.launch_chrome.return_value = False
        mock_instance.last_error = "Chrome not found"
        mock_fallback.return_value = True

        gen = EDRReportGenerator()
        gen.username = 'testuser'
        gen.password = 'testpass'
        result = gen.chrome_step1_submit_password()

        assert result is True
        mock_fallback.assert_called_once()

    @patch('app.integrations.edr.chrome_cdp_auth.ChromeEDRAuthenticator')
    def test_chrome_step3_extracts_and_injects_cookies(self, MockAuth):
        from app.integrations.edr.report_generator import EDRReportGenerator
        mock_instance = MockAuth.return_value
        mock_instance.step3_validate_mfa.return_value = True
        mock_instance.extract_cookies.return_value = [
            {'name': '_px3', 'value': 'abc', 'domain': '.wal-mart.com', 'path': '/', 'secure': True}
        ]
        mock_instance.inject_cookies_into_session.return_value = 1
        mock_instance.last_error = None

        gen = EDRReportGenerator()
        gen.mfa_credential_id = 'cred-123'
        gen._chrome_auth = mock_instance

        result = gen.chrome_step3_validate_mfa_code('123456')

        assert result is True
        mock_instance.step3_validate_mfa.assert_called_once_with('cred-123', '123456')
        mock_instance.extract_cookies.assert_called_once()
        mock_instance.inject_cookies_into_session.assert_called_once_with(gen.session)
        mock_instance.cleanup.assert_called_once()
