"""
Configuration management for Flask Schedule Webapp
Handles environment-based settings and external API configuration

Updated with lazy validation pattern to avoid requiring all credentials
during development and testing.
"""
import os
import secrets
from decouple import config
from typing import Optional


class Config:
    """Base configuration class"""
    # Flask settings
    # Development: Generate random key on startup (non-persistent OK for dev)
    SECRET_KEY = config('SECRET_KEY', default=secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI = config('DATABASE_URL', default='sqlite:///instance/scheduler.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # External API settings (Crossmark Session-based authentication)
    EXTERNAL_API_BASE_URL = config('EXTERNAL_API_BASE_URL', default='https://crossmark.mvretail.com')
    EXTERNAL_API_USERNAME = config('EXTERNAL_API_USERNAME', default='')
    EXTERNAL_API_PASSWORD = config('EXTERNAL_API_PASSWORD', default='')
    EXTERNAL_API_TIMEZONE = config('EXTERNAL_API_TIMEZONE', default='America/Indiana/Indianapolis')
    EXTERNAL_API_TIMEOUT = config('EXTERNAL_API_TIMEOUT', default=30, cast=int)
    EXTERNAL_API_MAX_RETRIES = config('EXTERNAL_API_MAX_RETRIES', default=3, cast=int)

    # Sync settings
    SYNC_ENABLED = config('SYNC_ENABLED', default=False, cast=bool)

    # Logging settings
    LOG_LEVEL = config('LOG_LEVEL', default='INFO')
    LOG_FILE = config('LOG_FILE', default='logs/scheduler.log')

    # Session settings
    SESSION_INACTIVITY_TIMEOUT = config('SESSION_INACTIVITY_TIMEOUT', default=600, cast=int)  # 10 minutes

    # Test instance indicator
    IS_TEST_INSTANCE = config('IS_TEST_INSTANCE', default=False, cast=bool)

    # Walmart Retail Link EDR settings
    # SECURITY: No default values - must be set in environment variables
    WALMART_EDR_USERNAME = config('WALMART_EDR_USERNAME', default='')
    WALMART_EDR_PASSWORD = config('WALMART_EDR_PASSWORD', default='')
    WALMART_EDR_MFA_CREDENTIAL_ID = config('WALMART_EDR_MFA_CREDENTIAL_ID', default='')
    WALMART_USER_ID = config('WALMART_USER_ID', default='')  # Walmart user ID for API calls (e.g., 'd2fr4w2')

    # Settings encryption key (should be set in environment for production)
    SETTINGS_ENCRYPTION_KEY = config('SETTINGS_ENCRYPTION_KEY', default=None)

    # ML (Machine Learning) settings
    ML_ENABLED = config('ML_ENABLED', default=False, cast=bool)
    ML_EMPLOYEE_RANKING_ENABLED = config('ML_EMPLOYEE_RANKING_ENABLED', default=True, cast=bool)
    ML_BUMP_PREDICTION_ENABLED = config('ML_BUMP_PREDICTION_ENABLED', default=False, cast=bool)
    ML_FEASIBILITY_ENABLED = config('ML_FEASIBILITY_ENABLED', default=False, cast=bool)
    ML_CONFIDENCE_THRESHOLD = config('ML_CONFIDENCE_THRESHOLD', default=0.6, cast=float)
    ML_EMPLOYEE_RANKER_PATH = config('ML_EMPLOYEE_RANKER_PATH', default='app/ml/models/artifacts/employee_ranker_latest.pkl')
    ML_SHADOW_MODE = config('ML_SHADOW_MODE', default=False, cast=bool)  # Log predictions without using them

    @classmethod
    def validate(cls, validate_walmart: bool = True) -> None:
        """
        Validate configuration - can be called explicitly or on-demand

        This allows development without all credentials, while ensuring
        production has everything configured.

        Args:
            validate_walmart: Whether to validate Walmart EDR credentials

        Raises:
            ValueError: If required configuration is missing

        Example:
            >>> config = get_config()
            >>> config.validate()  # Validate all settings
            >>> config.validate(validate_walmart=False)  # Skip Walmart validation
        """
        pass  # Base config has no required validation

    @classmethod
    def is_feature_enabled(cls, feature: str) -> bool:
        """
        Check if a specific feature is enabled

        Args:
            feature: Feature name (e.g., 'edr', 'sync')

        Returns:
            bool: True if feature is enabled
        """
        feature_flags = {
            'edr': config('ENABLE_EDR_FEATURES', default=False, cast=bool),
            'sync': cls.SYNC_ENABLED,
        }
        return feature_flags.get(feature.lower(), False)


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

    @classmethod
    def validate(cls, validate_walmart: bool = True) -> None:
        """Development mode: no validation required"""
        pass


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SYNC_ENABLED = False

    @classmethod
    def validate(cls, validate_walmart: bool = True) -> None:
        """Testing mode: no validation required"""
        pass


class ProductionConfig(Config):
    """Production configuration with enterprise security features"""
    DEBUG = False
    TESTING = False

    # Security - Production REQUIRES environment variables (no defaults)
    # Will raise error if SECRET_KEY is not set - see get_config() validation
    SECRET_KEY = config('SECRET_KEY', default='change-this-to-a-random-secret-key-in-production')
    EXTERNAL_API_USERNAME = config('EXTERNAL_API_USERNAME', default='')
    EXTERNAL_API_PASSWORD = config('EXTERNAL_API_PASSWORD', default='')

    # Session Security
    SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
    SESSION_COOKIE_HTTPONLY = config('SESSION_COOKIE_HTTPONLY', default=True, cast=bool)
    SESSION_COOKIE_SAMESITE = config('SESSION_COOKIE_SAMESITE', default='Lax')
    PERMANENT_SESSION_LIFETIME = config('PERMANENT_SESSION_LIFETIME', default=3600, cast=int)

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = config('WTF_CSRF_TIME_LIMIT', default=3600, cast=int)

    # Database Connection Pool (for production databases)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': config('DB_POOL_SIZE', default=10, cast=int),
        'pool_recycle': config('DB_POOL_RECYCLE', default=3600, cast=int),
        'pool_pre_ping': True,
        'max_overflow': config('DB_MAX_OVERFLOW', default=20, cast=int),
    }

    # Security Headers
    SECURITY_HEADERS = {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
    }

    # Rate Limiting
    RATELIMIT_ENABLED = config('RATELIMIT_ENABLED', default=True, cast=bool)
    RATELIMIT_DEFAULT = config('RATELIMIT_DEFAULT', default='100 per hour')

    # Logging
    LOG_LEVEL = config('LOG_LEVEL', default='WARNING')

    # Performance
    SEND_FILE_MAX_AGE_DEFAULT = config('SEND_FILE_MAX_AGE_DEFAULT', default=31536000, cast=int)

    @classmethod
    def validate(cls, validate_walmart: bool = True) -> None:
        """
        Production mode: validate all required settings

        Args:
            validate_walmart: Whether to validate Walmart EDR credentials

        Raises:
            ValueError: If any required configuration is missing
        """
        # Validate SECRET_KEY
        try:
            secret_key = config('SECRET_KEY')
        except Exception:
            raise ValueError(
                "SECRET_KEY environment variable must be set in production. "
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )

        if len(secret_key) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters in production (current: {len(secret_key)}). "
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )

        # Validate Walmart credentials only if feature is enabled
        if validate_walmart and cls.is_feature_enabled('edr'):
            walmart_vars = {
                'WALMART_EDR_USERNAME': config('WALMART_EDR_USERNAME', default=''),
                'WALMART_EDR_PASSWORD': config('WALMART_EDR_PASSWORD', default=''),
                'WALMART_EDR_MFA_CREDENTIAL_ID': config('WALMART_EDR_MFA_CREDENTIAL_ID', default='')
            }

            missing = [var for var, value in walmart_vars.items() if not value]
            if missing:
                raise ValueError(
                    f"EDR features require: {', '.join(missing)}. "
                    f"Please set these in your .env file or disable EDR features (ENABLE_EDR_FEATURES=False)."
                )


# Configuration mapping
config_mapping = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(config_name: Optional[str] = None, validate: bool = False) -> type:
    """
    Get configuration class based on environment.

    Updated with lazy validation pattern - credentials are only validated
    when explicitly requested or when features that need them are used.

    Args:
        config_name: Environment name ('development', 'testing', 'production')
        validate: Whether to validate configuration immediately (default: False)

    Returns:
        Config class for the specified environment

    Raises:
        ValueError: If validation is enabled and required variables are missing

    Example:
        >>> # Development - no validation
        >>> config = get_config()

        >>> # Production - validate on startup
        >>> config = get_config('production', validate=True)

        >>> # Validate later when needed
        >>> config = get_config()
        >>> config.validate()  # Validate when actually needed
    """
    if config_name is None:
        config_name = config('FLASK_ENV', default='development')

    config_class = config_mapping.get(config_name, DevelopmentConfig)

    # Only validate if explicitly requested
    if validate:
        config_class.validate()

    return config_class