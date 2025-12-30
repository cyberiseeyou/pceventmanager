"""
System Settings Model
Manages configuration settings stored in database with encryption support
"""
import logging
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.utils.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)


def create_system_setting_model(db):
    """
    Factory function to create SystemSetting model

    Args:
        db: SQLAlchemy database instance

    Returns:
        SystemSetting model class
    """

    class SystemSetting(db.Model):
        __tablename__ = 'system_settings'

        id = Column(Integer, primary_key=True)
        setting_key = Column(String(100), unique=True, nullable=False)
        setting_value = Column(Text)
        setting_type = Column(String(50))  # 'string', 'boolean', 'encrypted'
        description = Column(Text)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        updated_by = Column(String(100))

        @staticmethod
        def get_setting(key, default=None):
            """
            Get a setting value by key with type conversion

            Args:
                key (str): Setting key
                default: Default value if setting not found

            Returns:
                Setting value with appropriate type conversion
            """
            setting = SystemSetting.query.filter_by(setting_key=key).first()

            if not setting:
                return default

            # Type conversion based on setting_type
            if setting.setting_type == 'boolean':
                return setting.setting_value.lower() == 'true' if setting.setting_value else default

            elif setting.setting_type == 'encrypted':
                try:
                    return decrypt_value(setting.setting_value)
                except Exception as e:
                    logger.error(f"Error decrypting setting {key}: {str(e)}")
                    return default

            else:  # 'string' or default
                return setting.setting_value if setting.setting_value is not None else default

        @staticmethod
        def set_setting(key, value, setting_type='string', user='system', description=None):
            """
            Set a setting value (create or update)

            Args:
                key (str): Setting key
                value: Setting value
                setting_type (str): Type of setting ('string', 'boolean', 'encrypted')
                user (str): User making the change
                description (str): Setting description

            Returns:
                SystemSetting: The created or updated setting
            """
            setting = SystemSetting.query.filter_by(setting_key=key).first()

            # Convert value based on type
            if setting_type == 'boolean':
                value_str = 'true' if value else 'false'
            elif setting_type == 'encrypted':
                value_str = encrypt_value(str(value)) if value else None
            else:
                value_str = str(value) if value is not None else None

            if setting:
                # Update existing setting
                setting.setting_value = value_str
                setting.setting_type = setting_type
                setting.updated_by = user
                setting.updated_at = datetime.utcnow()
                if description:
                    setting.description = description
            else:
                # Create new setting
                setting = SystemSetting(
                    setting_key=key,
                    setting_value=value_str,
                    setting_type=setting_type,
                    description=description,
                    updated_by=user
                )
                db.session.add(setting)

            db.session.commit()
            return setting

    return SystemSetting
