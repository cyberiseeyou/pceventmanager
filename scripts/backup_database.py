#!/usr/bin/env python3
"""
Flask Schedule Webapp - Database Backup Script
Backs up SQLite or PostgreSQL databases with compression and retention management
"""

import os
import sys
import gzip
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Optional
import logging

class DatabaseBackup:
    """Handles database backups with compression and retention"""

    def __init__(self, backup_dir: str, retention_days: int = 7):
        """
        Initialize backup handler

        Args:
            backup_dir: Directory to store backups
            retention_days: Number of days to retain backups
        """
        self.backup_dir = Path(backup_dir)
        self.retention_days = retention_days
        self.project_root = Path(__file__).parent.parent

        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Setup logging
        log_dir = self.project_root / 'logs'
        log_file = log_dir / 'backup.log'

        # Try to create log directory and file, fall back to stdout only
        handlers = [logging.StreamHandler()]
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file))
        except (PermissionError, OSError) as e:
            print(f"Warning: Cannot write to {log_file}, logging to stdout only")

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
        self.logger = logging.getLogger(__name__)

    def detect_database_type(self) -> Tuple[str, str]:
        """
        Detect database type from .env configuration

        Returns:
            Tuple of (database_type, database_path_or_url)
            database_type: 'sqlite' or 'postgresql'
        """
        env_file = self.project_root / '.env'

        if not env_file.exists():
            raise FileNotFoundError(f".env file not found at {env_file}")

        # Read .env file
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    database_url = line.split('=', 1)[1].strip()

                    if database_url.startswith('sqlite'):
                        # Extract path from sqlite:///path/to/db
                        db_path = database_url.replace('sqlite:///', '')
                        full_path = self.project_root / db_path
                        return ('sqlite', str(full_path))
                    elif database_url.startswith('postgresql'):
                        return ('postgresql', database_url)
                    else:
                        raise ValueError(f"Unsupported database type: {database_url}")

        raise ValueError("DATABASE_URL not found in .env file")

    def backup_sqlite(self, db_path: str) -> Path:
        """
        Backup SQLite database with gzip compression

        Args:
            db_path: Path to SQLite database file

        Returns:
            Path to compressed backup file
        """
        db_file = Path(db_path)

        if not db_file.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        backup_name = f"scheduler_{timestamp}.db.gz"
        backup_path = self.backup_dir / backup_name

        self.logger.info(f"Backing up SQLite database: {db_path}")
        self.logger.info(f"Backup destination: {backup_path}")

        # Copy and compress database
        with open(db_file, 'rb') as f_in:
            with gzip.open(backup_path, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Get file sizes
        original_size = db_file.stat().st_size / (1024 * 1024)  # MB
        compressed_size = backup_path.stat().st_size / (1024 * 1024)  # MB
        compression_ratio = (1 - compressed_size / original_size) * 100

        self.logger.info(f"Backup created: {backup_path}")
        self.logger.info(f"Original size: {original_size:.2f} MB")
        self.logger.info(f"Compressed size: {compressed_size:.2f} MB")
        self.logger.info(f"Compression ratio: {compression_ratio:.1f}%")

        return backup_path

    def backup_postgresql(self, db_url: str) -> Path:
        """
        Backup PostgreSQL database using pg_dump

        Args:
            db_url: PostgreSQL connection URL

        Returns:
            Path to compressed backup file
        """
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        backup_name = f"scheduler_{timestamp}.sql.gz"
        backup_path = self.backup_dir / backup_name

        self.logger.info(f"Backing up PostgreSQL database")
        self.logger.info(f"Backup destination: {backup_path}")

        try:
            # Use pg_dump with gzip compression
            cmd = f"pg_dump {db_url} | gzip -9 > {backup_path}"
            result = subprocess.run(
                cmd,
                shell=True,
                check=True,
                capture_output=True,
                text=True
            )

            compressed_size = backup_path.stat().st_size / (1024 * 1024)  # MB

            self.logger.info(f"Backup created: {backup_path}")
            self.logger.info(f"Compressed size: {compressed_size:.2f} MB")

            return backup_path

        except subprocess.CalledProcessError as e:
            self.logger.error(f"pg_dump failed: {e.stderr}")
            raise
        except FileNotFoundError:
            self.logger.error("pg_dump not found. Install PostgreSQL client tools.")
            raise

    def backup_config_files(self) -> Path:
        """
        Backup configuration files and migrations

        Returns:
            Path to compressed tar archive
        """
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        backup_name = f"config_{timestamp}.tar.gz"
        backup_path = self.backup_dir / backup_name

        self.logger.info("Backing up configuration files")

        # Files and directories to backup
        items_to_backup = [
            '.env',
            'gunicorn_config.py',
            'wsgi.py',
            'celery_worker.py',
            'requirements.txt',
            'migrations/versions'
        ]

        # Filter to only existing items
        existing_items = []
        for item in items_to_backup:
            item_path = self.project_root / item
            if item_path.exists():
                existing_items.append(item)

        if not existing_items:
            self.logger.warning("No configuration files found to backup")
            return None

        # Create tar.gz archive
        import tarfile
        with tarfile.open(backup_path, 'w:gz') as tar:
            for item in existing_items:
                item_path = self.project_root / item
                tar.add(item_path, arcname=item)
                self.logger.info(f"  Added: {item}")

        compressed_size = backup_path.stat().st_size / 1024  # KB
        self.logger.info(f"Config backup created: {backup_path}")
        self.logger.info(f"Size: {compressed_size:.1f} KB")

        return backup_path

    def verify_backup(self, backup_path: Path) -> bool:
        """
        Verify backup file integrity

        Args:
            backup_path: Path to backup file

        Returns:
            True if backup is valid, False otherwise
        """
        self.logger.info(f"Verifying backup: {backup_path}")

        try:
            # Test gzip integrity
            if backup_path.suffix == '.gz':
                with gzip.open(backup_path, 'rb') as f:
                    # Read first chunk to verify
                    f.read(1024)

            # Check file is not empty
            if backup_path.stat().st_size == 0:
                self.logger.error("Backup file is empty")
                return False

            self.logger.info("Backup verification passed")
            return True

        except Exception as e:
            self.logger.error(f"Backup verification failed: {e}")
            return False

    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        self.logger.info(f"Cleaning up backups older than {self.retention_days} days")

        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        removed_count = 0

        for backup_file in self.backup_dir.glob('*'):
            if not backup_file.is_file():
                continue

            # Get file modification time
            file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)

            if file_time < cutoff_date:
                self.logger.info(f"Removing old backup: {backup_file.name}")
                backup_file.unlink()
                removed_count += 1

        if removed_count > 0:
            self.logger.info(f"Removed {removed_count} old backup(s)")
        else:
            self.logger.info("No old backups to remove")

    def run(self) -> bool:
        """
        Main backup execution

        Returns:
            True if backup successful, False otherwise
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("Starting database backup")
            self.logger.info("=" * 50)

            # Detect database type
            db_type, db_location = self.detect_database_type()
            self.logger.info(f"Database type: {db_type}")

            # Backup database
            if db_type == 'sqlite':
                backup_path = self.backup_sqlite(db_location)
            elif db_type == 'postgresql':
                backup_path = self.backup_postgresql(db_location)
            else:
                raise ValueError(f"Unsupported database type: {db_type}")

            # Verify backup
            if not self.verify_backup(backup_path):
                raise Exception("Backup verification failed")

            # Backup configuration files
            config_backup = self.backup_config_files()
            if config_backup:
                self.verify_backup(config_backup)

            # Cleanup old backups
            self.cleanup_old_backups()

            self.logger.info("=" * 50)
            self.logger.info("Backup completed successfully")
            self.logger.info("=" * 50)

            return True

        except Exception as e:
            self.logger.error("=" * 50)
            self.logger.error(f"Backup failed: {e}")
            self.logger.error("=" * 50)
            return False


def main():
    """Main entry point"""
    # Get backup directory from environment or use default
    backup_dir = os.getenv('BACKUP_DIR', 'backups')

    # Get retention days from environment or use default
    retention_days = int(os.getenv('BACKUP_RETENTION_DAYS', '7'))

    # Run backup
    backup = DatabaseBackup(backup_dir, retention_days)
    success = backup.run()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
