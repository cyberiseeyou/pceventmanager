#!/usr/bin/env python3
"""
Flask Schedule Webapp - Database Restore Script
Restores database from compressed backup with safety features
"""

import os
import sys
import gzip
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional
import logging

class DatabaseRestore:
    """Handles database restoration from backups"""

    def __init__(self, backup_dir: str):
        """
        Initialize restore handler

        Args:
            backup_dir: Directory containing backups
        """
        self.backup_dir = Path(backup_dir)
        self.project_root = Path(__file__).parent.parent

        if not self.backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

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

    def detect_database_path(self) -> str:
        """
        Get database path from .env configuration

        Returns:
            Path to database file
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
                        return str(full_path)
                    else:
                        raise ValueError("PostgreSQL restore not yet implemented")

        raise ValueError("DATABASE_URL not found in .env file")

    def list_backups(self) -> List[Tuple[Path, dict]]:
        """
        List available database backups

        Returns:
            List of tuples: (backup_path, info_dict)
        """
        backups = []

        for backup_file in sorted(self.backup_dir.glob('scheduler_*.db.gz'), reverse=True):
            if not backup_file.is_file():
                continue

            # Get file info
            file_stat = backup_file.stat()
            file_size = file_stat.st_size / (1024 * 1024)  # MB
            file_time = datetime.fromtimestamp(file_stat.st_mtime)

            info = {
                'name': backup_file.name,
                'size_mb': file_size,
                'date': file_time,
                'age_days': (datetime.now() - file_time).days
            }

            backups.append((backup_file, info))

        return backups

    def display_backups(self, backups: List[Tuple[Path, dict]]):
        """Display available backups in a formatted table"""
        print("\n" + "=" * 80)
        print("Available Backups")
        print("=" * 80)
        print(f"{'#':<4} {'Filename':<35} {'Size (MB)':<12} {'Date':<20} {'Age'}")
        print("-" * 80)

        for idx, (backup_path, info) in enumerate(backups, 1):
            age_str = f"{info['age_days']} days ago"
            if info['age_days'] == 0:
                age_str = "Today"
            elif info['age_days'] == 1:
                age_str = "Yesterday"

            print(f"{idx:<4} {info['name']:<35} {info['size_mb']:<12.2f} "
                  f"{info['date'].strftime('%Y-%m-%d %H:%M:%S'):<20} {age_str}")

        print("=" * 80)
        print()

    def create_safety_backup(self, db_path: str) -> Optional[Path]:
        """
        Create safety backup of current database before restore

        Args:
            db_path: Path to current database

        Returns:
            Path to safety backup, or None if database doesn't exist
        """
        db_file = Path(db_path)

        if not db_file.exists():
            self.logger.warning(f"Database file not found: {db_path}")
            return None

        # Create safety backup with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        safety_backup_name = f"safety_before_restore_{timestamp}.db.gz"
        safety_backup_path = self.backup_dir / safety_backup_name

        self.logger.info(f"Creating safety backup: {safety_backup_path}")

        # Compress current database
        with open(db_file, 'rb') as f_in:
            with gzip.open(safety_backup_path, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)

        self.logger.info(f"Safety backup created: {safety_backup_path}")
        return safety_backup_path

    def restore_backup(self, backup_path: Path, db_path: str) -> bool:
        """
        Restore database from backup

        Args:
            backup_path: Path to backup file
            db_path: Path to database file to restore to

        Returns:
            True if restore successful, False otherwise
        """
        try:
            self.logger.info(f"Restoring backup: {backup_path}")
            self.logger.info(f"Destination: {db_path}")

            db_file = Path(db_path)

            # Ensure parent directory exists
            db_file.parent.mkdir(parents=True, exist_ok=True)

            # Decompress backup to database location
            with gzip.open(backup_path, 'rb') as f_in:
                with open(db_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Verify restored database
            if not db_file.exists():
                raise Exception("Restored database file not found")

            restored_size = db_file.stat().st_size / (1024 * 1024)  # MB
            self.logger.info(f"Database restored successfully")
            self.logger.info(f"Restored size: {restored_size:.2f} MB")

            return True

        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False

    def run(self) -> bool:
        """
        Main restore execution

        Returns:
            True if restore successful, False otherwise
        """
        try:
            print("\n" + "=" * 80)
            print("Flask Schedule Webapp - Database Restore")
            print("=" * 80)
            print()

            # Get database path
            db_path = self.detect_database_path()
            print(f"Database location: {db_path}")

            # List available backups
            backups = self.list_backups()

            if not backups:
                print("No backups found!")
                print(f"Backup directory: {self.backup_dir}")
                return False

            # Display backups
            self.display_backups(backups)

            # Get user selection
            while True:
                try:
                    selection = input("Select backup number to restore (or 'q' to quit): ").strip()

                    if selection.lower() == 'q':
                        print("Restore cancelled")
                        return False

                    backup_idx = int(selection) - 1

                    if 0 <= backup_idx < len(backups):
                        break
                    else:
                        print(f"Invalid selection. Please enter 1-{len(backups)}")

                except ValueError:
                    print("Invalid input. Please enter a number")

            selected_backup, backup_info = backups[backup_idx]

            # Confirm restore
            print()
            print("=" * 80)
            print("WARNING: This will replace your current database!")
            print("=" * 80)
            print(f"Backup to restore: {backup_info['name']}")
            print(f"Backup date: {backup_info['date'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Backup size: {backup_info['size_mb']:.2f} MB")
            print()
            print("A safety backup of your current database will be created first.")
            print()

            confirmation = input("Type 'RESTORE' to confirm (case-sensitive): ").strip()

            if confirmation != 'RESTORE':
                print("Restore cancelled")
                return False

            print()
            self.logger.info("=" * 50)
            self.logger.info("Starting database restore")
            self.logger.info("=" * 50)

            # Create safety backup
            safety_backup = self.create_safety_backup(db_path)
            if safety_backup:
                print(f"Safety backup created: {safety_backup}")

            # Restore backup
            success = self.restore_backup(selected_backup, db_path)

            if success:
                self.logger.info("=" * 50)
                self.logger.info("Restore completed successfully")
                self.logger.info("=" * 50)
                print()
                print("=" * 80)
                print("Database restored successfully!")
                print("=" * 80)
                print()
                print("IMPORTANT: Restart your application for changes to take effect:")
                print("  sudo systemctl restart flask-schedule-webapp")
                print("  OR")
                print("  Press Ctrl+C and restart your Flask application")
                print()
            else:
                self.logger.error("=" * 50)
                self.logger.error("Restore failed")
                self.logger.error("=" * 50)
                print()
                print("Restore failed! Check logs/backup.log for details")
                if safety_backup:
                    print(f"Your original database backup is at: {safety_backup}")
                print()

            return success

        except KeyboardInterrupt:
            print("\n\nRestore cancelled by user")
            return False
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False


def main():
    """Main entry point"""
    # Get backup directory from environment or use default
    backup_dir = os.getenv('BACKUP_DIR', 'backups')

    # Run restore
    restore = DatabaseRestore(backup_dir)
    success = restore.run()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
