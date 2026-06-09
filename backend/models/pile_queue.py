from . import db
from datetime import datetime


class PileQueue(db.Model):
    __tablename__ = "pile_queue"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pile_id = db.Column(db.Integer, db.ForeignKey("charging_pile.pile_id"), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey("charging_request.request_id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    enter_time = db.Column(db.DateTime, default=datetime.utcnow)
