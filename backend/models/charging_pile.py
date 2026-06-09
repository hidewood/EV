from . import db


class ChargingPile(db.Model):
    __tablename__ = "charging_pile"
    pile_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mode = db.Column(db.Enum("F", "T"), nullable=False)
    power = db.Column(db.Float, nullable=False)
    status = db.Column(db.Enum("off", "standby", "available", "charging", "fault"), default="off")
    queue_len = db.Column(db.Integer, default=5)
    total_charge_num = db.Column(db.Integer, default=0)
    total_charge_time = db.Column(db.Float, default=0.0)
    total_charge_capacity = db.Column(db.Float, default=0.0)
