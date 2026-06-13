from . import db
from ..utils.timezone import local_now


class ChargingDetail(db.Model):
    __tablename__ = "charging_detail"
    detail_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("charging_session.session_id"), nullable=False)
    car_id = db.Column(db.String(20), db.ForeignKey("user.car_id"), nullable=False)
    pile_id = db.Column(db.Integer, db.ForeignKey("charging_pile.pile_id"), nullable=False)
    charge_amount = db.Column(db.Float, nullable=False)
    charge_duration = db.Column(db.Float, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    stop_time = db.Column(db.DateTime, nullable=False)
    charge_fee = db.Column(db.Float, default=0.0)
    service_fee = db.Column(db.Float, default=0.0)
    total_fee = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=local_now)
