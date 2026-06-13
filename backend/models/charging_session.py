from . import db
from ..utils.timezone import local_now


class ChargingSession(db.Model):
    __tablename__ = "charging_session"
    session_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    request_id = db.Column(db.Integer, db.ForeignKey("charging_request.request_id"), nullable=False)
    car_id = db.Column(db.String(20), db.ForeignKey("user.car_id"), nullable=False)
    pile_id = db.Column(db.Integer, db.ForeignKey("charging_pile.pile_id"), nullable=False)
    start_time = db.Column(db.DateTime, default=local_now)
    end_time = db.Column(db.DateTime, nullable=True)
    charge_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.Enum("active", "completed", "interrupted"), default="active")
