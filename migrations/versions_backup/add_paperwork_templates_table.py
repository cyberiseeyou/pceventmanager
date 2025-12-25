"""
Add paperwork_templates table for managing dynamic PDF templates

This migration creates the paperwork_templates table to store configurable
PDF templates that will be included in daily paperwork packages.

Revision ID: add_paperwork_templates
Created: 2025-10-23
"""

def upgrade(db):
    """
    Create paperwork_templates table with all necessary fields and indexes

    Business Rules:
    - Templates have a display_order for sequencing in paperwork packages
    - Templates can be enabled/disabled via is_active flag
    - Template names must be unique
    - File paths are relative to the docs directory
    """

    # Create paperwork_templates table
    db.execute("""
        CREATE TABLE IF NOT EXISTS paperwork_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200) NOT NULL UNIQUE,
            description VARCHAR(500),
            file_path VARCHAR(500) NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for performance
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_paperwork_templates_active
        ON paperwork_templates(is_active)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_paperwork_templates_order
        ON paperwork_templates(display_order)
    """)

    print("✅ Created paperwork_templates table")
    print("✅ Created indexes: idx_paperwork_templates_active, idx_paperwork_templates_order")

    # Check if legacy templates exist and seed them
    import os
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'docs')

    # Seed Activity Log if it exists
    activity_log_path = os.path.join(docs_dir, 'Event Table Activity Log.pdf')
    if os.path.exists(activity_log_path):
        db.execute("""
            INSERT INTO paperwork_templates (name, description, file_path, display_order, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, ('Activity Log', 'Event table activity log for tracking daily activities',
              'Event Table Activity Log.pdf', 1, 1))
        print("✅ Seeded Activity Log template")

    # Seed Checklist if it exists
    checklist_path = os.path.join(docs_dir, 'Daily Task Checkoff Sheet.pdf')
    if os.path.exists(checklist_path):
        db.execute("""
            INSERT INTO paperwork_templates (name, description, file_path, display_order, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, ('Daily Checklist', 'Daily task checkoff sheet for completing required tasks',
              'Daily Task Checkoff Sheet.pdf', 2, 1))
        print("✅ Seeded Daily Checklist template")


def downgrade(db):
    """
    Drop paperwork_templates table and all indexes
    """
    db.execute("DROP INDEX IF EXISTS idx_paperwork_templates_order")
    db.execute("DROP INDEX IF EXISTS idx_paperwork_templates_active")
    db.execute("DROP TABLE IF EXISTS paperwork_templates")

    print("✅ Dropped paperwork_templates table and indexes")


# Manual migration execution (if not using Alembic)
if __name__ == '__main__':
    import sys
    sys.path.append('../../')

    from app import app, db

    with app.app_context():
        print("Running migration: add_paperwork_templates_table")
        upgrade(db)
        print("Migration complete!")
