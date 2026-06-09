from . import db
from datetime import datetime


class WaitingQueue(db.Model):
    __tablename__ = "waiting_queue"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    request_id = db.Column(db.Integer, db.ForeignKey("charging_request.request_id"), nullable=False)
    mode = db.Column(db.Enum("F", "T"), nullable=False)
    queue_num = db.Column(db.String(10), nullable=False)
    join_time = db.Column(db.DateTime, default=datetime.utcnow)
