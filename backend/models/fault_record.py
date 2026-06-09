from . import db
from datetime import datetime


class FaultRecord(db.Model):
    __tablename__ = "fault_record"
    fault_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pile_id = db.Column(db.Integer, db.ForeignKey("charging_pile.pile_id"), nullable=False)
    fault_time = db.Column(db.DateTime, default=datetime.utcnow)
    recover_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.Enum("active", "resolved"), default="active")
    handler = db.Column(db.String(50), nullable=True)
