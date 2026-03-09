"""
LostDemo model — tracks events confirmed as lost demos.
"""
from datetime import datetime


def create_lost_demo_model(db):
    """Factory function to create LostDemo model with db instance."""

    class LostDemo(db.Model):
        __tablename__ = 'lost_demos'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        event_ref_num = db.Column(
            db.Integer,
            db.ForeignKey('events.project_ref_num'),
            nullable=False,
            unique=True
        )
        week_start_date = db.Column(db.Date, nullable=False)
        confirmed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        notes = db.Column(db.Text, nullable=True)

        __table_args__ = (
            db.Index('idx_lost_demos_week', 'week_start_date'),
        )

        def __repr__(self):
            return f'<LostDemo event_ref={self.event_ref_num} week={self.week_start_date}>'

    return LostDemo
