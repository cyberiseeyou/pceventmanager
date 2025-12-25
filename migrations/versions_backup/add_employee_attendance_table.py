"""
Add employee_attendance table for tracking attendance records

This migration creates the employee_attendance table to track whether employees
showed up on time, late, called in, or no-call-no-showed for scheduled events.

Revision ID: add_employee_attendance
Created: 2025-10-17
"""

def upgrade(db):
    """
    Create employee_attendance table with all necessary fields and indexes

    Business Rules:
    - One attendance record per schedule (UNIQUE constraint on schedule_id)
    - Attendance records cascade delete with employees and schedules
    - Four status types: on_time, late, called_in, no_call_no_show
    """

    # Create employee_attendance table
    db.execute("""
        CREATE TABLE IF NOT EXISTS employee_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id VARCHAR(50) NOT NULL,
            schedule_id INTEGER NOT NULL UNIQUE,
            attendance_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL,
            notes TEXT,
            recorded_by VARCHAR(100),
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
        )
    """)

    # Create indexes for performance
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_employee
        ON employee_attendance(employee_id)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_date
        ON employee_attendance(attendance_date)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_status
        ON employee_attendance(status)
    """)

    print("✅ Created employee_attendance table")
    print("✅ Created indexes: idx_attendance_employee, idx_attendance_date, idx_attendance_status")


def downgrade(db):
    """
    Drop employee_attendance table and all indexes
    """
    db.execute("DROP INDEX IF EXISTS idx_attendance_status")
    db.execute("DROP INDEX IF EXISTS idx_attendance_date")
    db.execute("DROP INDEX IF EXISTS idx_attendance_employee")
    db.execute("DROP TABLE IF EXISTS employee_attendance")

    print("✅ Dropped employee_attendance table and indexes")


# Manual migration execution (if not using Alembic)
if __name__ == '__main__':
    import sys
    sys.path.append('../../')

    from app import app, db

    with app.app_context():
        print("Running migration: add_employee_attendance_table")
        upgrade(db)
        print("Migration complete!")
