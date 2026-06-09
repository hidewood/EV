from . import db
from datetime import datetime


class Payment(db.Model):
    __tablename__ = "payment"
    payment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.bill_id"), nullable=False)
    car_id = db.Column(db.String(20), db.ForeignKey("user.car_id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    pay_time = db.Column(db.DateTime, default=datetime.utcnow)
    pay_method = db.Column(db.String(20), default="system")
