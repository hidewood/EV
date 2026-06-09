import bcrypt
from ..dao.user_dao import UserDAO
from ..models.user import User


class UserService:
    @staticmethod
    def register(car_id, user_name, car_capacity, password, role="user"):
        existing = UserDAO.find_by_car_id(car_id)
        if existing:
            return None, "car_id_exists"
        if not car_id or not user_name or not password or (role != "admin" and car_capacity <= 0):
            return None, "invalid_params"
        pwd_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = User(
            car_id=car_id,
            user_name=user_name,
            car_capacity=car_capacity,
            password_hash=pwd_hash,
            role=role,
        )
        UserDAO.insert(user)
        return user, None

    @staticmethod
    def login(car_id, password):
        user = UserDAO.find_by_car_id(car_id)
        if not user:
            return None, "user_not_found"
        if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            return None, "wrong_password"
        return user, None

    @staticmethod
    def set_password(car_id, old_password, new_password):
        user = UserDAO.find_by_car_id(car_id)
        if not user:
            return None, "user_not_found"
        if old_password:
            if not bcrypt.checkpw(old_password.encode("utf-8"), user.password_hash.encode("utf-8")):
                return None, "wrong_password"
        pwd_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        UserDAO.update_password(car_id, pwd_hash)
        return user, None
