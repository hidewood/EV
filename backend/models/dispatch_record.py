from . import db
from datetime import datetime


class DispatchRecord(db.Model):
    __tablename__ = "dispatch_record"
    record_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    request_id = db.Column(db.Integer, db.ForeignKey("charging_request.request_id"), nullable=False)
    from_location = db.Column(db.String(50))
    to_pile_id = db.Column(db.Integer, db.ForeignKey("charging_pile.pile_id"), nullable=False)
    dispatch_type = db.Column(db.String(30))
    dispatch_time = db.Column(db.DateTime, default=datetime.utcnow)
