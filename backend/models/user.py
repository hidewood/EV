from . import db
from ..utils.timezone import local_now


class User(db.Model):
    __tablename__ = "user"
    car_id = db.Column(db.String(20), primary_key=True)
    user_name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    car_capacity = db.Column(db.Float, nullable=False)
    role = db.Column(db.Enum("user", "admin"), default="user")
    created_at = db.Column(db.DateTime, default=local_now)
