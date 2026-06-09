from . import db
from datetime import datetime


class Bill(db.Model):
    __tablename__ = "bill"
    bill_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    detail_id = db.Column(db.Integer, db.ForeignKey("charging_detail.detail_id"), nullable=False)
    car_id = db.Column(db.String(20), db.ForeignKey("user.car_id"), nullable=False)
    total_charge_fee = db.Column(db.Float, default=0.0)
    total_service_fee = db.Column(db.Float, default=0.0)
    total_fee = db.Column(db.Float, default=0.0)
    status = db.Column(db.Enum("unpaid", "paid"), default="unpaid")
    create_time = db.Column(db.DateTime, default=datetime.utcnow)
    pay_time = db.Column(db.DateTime, nullable=True)
