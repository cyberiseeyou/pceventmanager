"""
Encryption utilities for sensitive settings storage
Uses Fernet symmetric encryption from cryptography library
"""
import os
import logging
from cryptography.fernet import Fernet
from flask import current_app

logger = logging.getLogger(__name__)


def get_encryption_key():
    """
    Get or generate encryption key for settings
    If not found in config, generates and persists to .env file

    Returns:
        bytes: Fernet encryption key
    """
    try:
        key = current_app.config.get('SETTINGS_ENCRYPTION_KEY')

        if not key:
            # Generate new key
            key = Fernet.generate_key()

            # Persist to .env file
            import os
            basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
            env_file = os.path.join(basedir, '.env')

            # Check if .env exists, create if not
            key_str = key.decode() if isinstance(key, bytes) else key

            # Read existing .env content if file exists
            env_content = ''
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    env_content = f.read()

            # Only add if not already present
            if 'SETTINGS_ENCRYPTION_KEY' not in env_content:
                with open(env_file, 'a') as f:
                    if env_content and not env_content.endswith('\n'):
                        f.write('\n')
                    f.write(f'SETTINGS_ENCRYPTION_KEY={key_str}\n')
                logger.warning(
                    f"Generated new encryption key and saved to {env_file}. "
                    "Keep this file secure and backed up!"
                )

            current_app.config['SETTINGS_ENCRYPTION_KEY'] = key

        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()

        return key
    except Exception as e:
        logger.error(f"Error getting encryption key: {str(e)}")
        raise


def encrypt_value(plain_text):
    """
    Encrypt a plain text value using Fernet

    Args:
        plain_text (str): Value to encrypt

    Returns:
        str: Encrypted value (base64 encoded)
    """
    if plain_text is None or plain_text == '':
        return None

    try:
        key = get_encryption_key()
        f = Fernet(key)

        # Ensure plain_text is bytes
        if isinstance(plain_text, str):
            plain_text = plain_text.encode()

        encrypted = f.encrypt(plain_text)
        return encrypted.decode()  # Return as string for database storage

    except Exception as e:
        logger.error(f"Error encrypting value: {str(e)}")
        raise


def decrypt_value(encrypted_text):
    """
    Decrypt an encrypted value using Fernet

    Args:
        encrypted_text (str): Encrypted value to decrypt

    Returns:
        str: Decrypted plain text value
    """
    if encrypted_text is None or encrypted_text == '':
        return None

    try:
        key = get_encryption_key()
        f = Fernet(key)

        # Ensure encrypted_text is bytes
        if isinstance(encrypted_text, str):
            encrypted_text = encrypted_text.encode()

        decrypted = f.decrypt(encrypted_text)
        return decrypted.decode()  # Return as string

    except Exception as e:
        logger.error(f"Error decrypting value: {str(e)}")
        raise
