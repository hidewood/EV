from . import db
from datetime import datetime


class ChargingRequest(db.Model):
    __tablename__ = "charging_request"
    request_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    car_id = db.Column(db.String(20), db.ForeignKey("user.car_id"), nullable=False)
    request_mode = db.Column(db.Enum("F", "T"), nullable=False)
    request_amount = db.Column(db.Float, nullable=False)
    queue_num = db.Column(db.String(10))
    status = db.Column(
        db.Enum("queuing", "dispatched", "charging", "cancelled", "completed", "pending_reschedule"),
        default="queuing",
    )
    pile_id = db.Column(db.Integer, db.ForeignKey("charging_pile.pile_id"), nullable=True)
    request_time = db.Column(db.DateTime, default=datetime.utcnow)
    modify_time = db.Column(db.DateTime, default=datetime.utcnow)
