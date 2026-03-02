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


class TestLoginFlow:
    def _make_auth_with_mock_tab(self):
        from app.integrations.edr.chrome_cdp_auth import ChromeEDRAuthenticator
        auth = ChromeEDRAuthenticator()
        mock_tab = MagicMock()
        auth._tab = mock_tab
        return auth, mock_tab

    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step1_navigates_and_submits_credentials(self, mock_sleep):
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Page.navigate.return_value = None
        mock_tab.wait.return_value = None
        mock_tab.Runtime.evaluate.return_value = {
            'result': {'type': 'string', 'value': '{"status":"ok","data":{}}'}
        }
        result = auth.step1_submit_credentials('testuser', 'testpass')
        assert result is True
        mock_tab.Page.navigate.assert_called_once()
        mock_tab.Runtime.evaluate.assert_called_once()

    @patch('app.integrations.edr.chrome_cdp_auth.time.sleep')
    def test_step1_fails_on_error_response(self, mock_sleep):
        auth, mock_tab = self._make_auth_with_mock_tab()
        mock_tab.Page.navigate.return_value = None
        mock_tab.wait.return_value = None
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
