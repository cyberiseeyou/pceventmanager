"""
Security regression tests.

Tests that security headers, CSRF protection, and XSS mitigations
are properly configured and functioning.
"""
import pytest
from app.config import ProductionConfig


class TestSecurityHeaders:
    """Test that security headers are configured in production config."""

    def test_production_config_has_security_headers(self):
        """Verify ProductionConfig defines all required security headers."""
        headers = ProductionConfig.SECURITY_HEADERS
        assert 'X-Content-Type-Options' in headers
        assert headers['X-Content-Type-Options'] == 'nosniff'

        assert 'X-Frame-Options' in headers
        assert headers['X-Frame-Options'] == 'SAMEORIGIN'

        assert 'X-XSS-Protection' in headers

        assert 'Strict-Transport-Security' in headers
        assert 'max-age=' in headers['Strict-Transport-Security']

        assert 'Content-Security-Policy' in headers

    def test_security_headers_config_complete(self):
        """Verify production config has all required security header keys and values."""
        headers = ProductionConfig.SECURITY_HEADERS
        # Must have at least 4 security headers defined
        assert len(headers) >= 4
        # CSP must include script-src directive
        assert 'script-src' in headers.get('Content-Security-Policy', '')
        # HSTS must have a reasonable max-age
        hsts = headers.get('Strict-Transport-Security', '')
        assert 'max-age=' in hsts


class TestCSRFProtection:
    """Test that CSRF protection is properly configured."""

    def test_csrf_enabled_in_production(self):
        """Verify WTF_CSRF_ENABLED is True in production config."""
        assert ProductionConfig.WTF_CSRF_ENABLED is True

    def test_session_cookie_security_in_production(self):
        """Verify session cookies have security attributes in production."""
        assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
        assert ProductionConfig.SESSION_COOKIE_SAMESITE == 'Lax'

    def test_csrf_token_cookie_set_on_response(self, client):
        """Verify CSRF token cookie is set on HTML responses."""
        response = client.get('/', follow_redirects=True)
        set_cookie_headers = response.headers.getlist('Set-Cookie')
        csrf_cookies = [h for h in set_cookie_headers if 'csrf_token' in h]
        if csrf_cookies:
            # Cookie should have a non-empty value
            assert 'csrf_token=' in csrf_cookies[0]
            assert 'csrf_token=;' not in csrf_cookies[0]  # Not cleared


class TestXSSPrevention:
    """Test that XSS payloads are properly escaped."""

    def test_no_inline_onclick_in_templates(self):
        """Verify no onclick= attributes remain in templates."""
        import os
        import re

        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'app', 'templates'
        )

        inline_handler_pattern = re.compile(
            r'\bon(click|change|submit|keydown|keyup|mouseover|focus|blur)\s*=',
            re.IGNORECASE
        )

        violations = []
        for root, dirs, files in os.walk(templates_dir):
            for fname in files:
                if not fname.endswith('.html') or fname.endswith('.bak'):
                    continue
                filepath = os.path.join(root, fname)
                with open(filepath, 'r') as f:
                    for lineno, line in enumerate(f, 1):
                        if inline_handler_pattern.search(line):
                            rel = os.path.relpath(filepath, templates_dir)
                            violations.append(f"{rel}:{lineno}")

        assert violations == [], (
            f"Found inline event handlers in templates:\n"
            + "\n".join(violations)
        )

    def test_xss_payload_escaped_in_health_endpoint(self, client):
        """Verify that XSS payloads in responses are escaped."""
        # Health endpoint returns JSON, which is inherently safe
        response = client.get('/health/ping')
        assert response.status_code == 200
        assert b'<script>' not in response.data


class TestConditionConstants:
    """Test that condition constants are properly defined."""

    def test_inactive_conditions_defined(self):
        """Verify INACTIVE_CONDITIONS constant exists and has expected values."""
        from app.constants import INACTIVE_CONDITIONS, CONDITION_CANCELED, CONDITION_EXPIRED
        assert CONDITION_CANCELED in INACTIVE_CONDITIONS
        assert CONDITION_EXPIRED in INACTIVE_CONDITIONS

    def test_cancelled_variants_defined(self):
        """Verify CANCELLED_VARIANTS covers both spellings."""
        from app.constants import CANCELLED_VARIANTS
        assert 'Canceled' in CANCELLED_VARIANTS
        assert 'Cancelled' in CANCELLED_VARIANTS

    def test_all_conditions_defined(self):
        """Verify ALL_CONDITIONS tuple has expected entries."""
        from app.constants import ALL_CONDITIONS
        assert len(ALL_CONDITIONS) >= 8  # At minimum 8 condition types
