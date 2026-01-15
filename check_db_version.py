import sqlite3
import os

db_path = 'instance/scheduler.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Drop shift_block_settings table if it exists
        # cursor.execute("DROP TABLE IF EXISTS shift_block_settings")
        # print("Dropped shift_block_settings table")
        # conn.commit()
        
        # Check alembic_version
        try:
            cursor.execute("SELECT version_num FROM alembic_version")
            version = cursor.fetchone()
            print(f"Current Alembic Version: {version[0] if version else 'None'}")
        except sqlite3.OperationalError:
            print("alembic_version table not found")
            
        # Check if shift_block_settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shift_block_settings'")
        table = cursor.fetchone()
        print(f"shift_block_settings table exists: {table is not None}")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
