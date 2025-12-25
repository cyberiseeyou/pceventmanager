"""
Paperwork Template Model
========================

Manages configurable paperwork templates that can be added to daily paperwork packages.
Each template has a name, file path, display order, and active status.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


def create_paperwork_template_model(db):
    """
    Factory function to create the PaperworkTemplate model with the given db instance.

    Args:
        db: SQLAlchemy instance

    Returns:
        PaperworkTemplate model class
    """

    class PaperworkTemplate(db.Model):
        """
        Paperwork Template Model

        Stores information about PDF templates that should be included in daily paperwork.
        Templates are ordered and can be enabled/disabled.
        """
        __tablename__ = 'paperwork_templates'

        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String(200), nullable=False, unique=True)
        description = Column(String(500), nullable=True)
        file_path = Column(String(500), nullable=False)  # Relative path from docs directory
        category = Column(String(50), nullable=False, default='event')  # 'event' or 'daily'
        display_order = Column(Integer, nullable=False, default=0)
        is_active = Column(Boolean, nullable=False, default=True)
        created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
        updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

        def __repr__(self):
            return f'<PaperworkTemplate {self.id}: {self.name} (Order: {self.display_order})>'

        def to_dict(self):
            """Convert to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'name': self.name,
                'description': self.description,
                'file_path': self.file_path,
                'category': self.category,
                'display_order': self.display_order,
                'is_active': self.is_active,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }

    return PaperworkTemplate
