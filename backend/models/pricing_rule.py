from . import db
from datetime import datetime


class PricingRule(db.Model):
    __tablename__ = "pricing_rule"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mode = db.Column(db.Enum("F", "T"), nullable=False, unique=True)
    peak_price = db.Column(db.Float, default=1.0)
    mid_price = db.Column(db.Float, default=0.7)
    off_peak_price = db.Column(db.Float, default=0.4)
    service_fee_rate = db.Column(db.Float, default=0.8)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
