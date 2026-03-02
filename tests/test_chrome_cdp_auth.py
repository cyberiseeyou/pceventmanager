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
