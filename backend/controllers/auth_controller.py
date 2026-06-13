from flask import Blueprint, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from ..services.user_service import UserService
from ..utils.errors import success, error
from ..utils.validators import parse_float
from ..config import ADMIN_REGISTER_CODE, JWT_ACCESS_TOKEN_EXPIRES

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    car_id = data.get("car_id", "").strip()
    user_name = data.get("user_name", "").strip()
    car_capacity = data.get("car_capacity", 0)
    password = data.get("password", "")
    role = data.get("role", "user")
    if role == "admin":
        if not ADMIN_REGISTER_CODE or data.get("admin_code") != ADMIN_REGISTER_CODE:
            return error(1003, "管理员注册码无效")
    elif role != "user":
        return error(1001)
    if not all([car_id, user_name, password]):
        return error(1001)
    if len(car_id) > 20 or len(user_name) > 50:
        return error(1001)
    car_capacity = parse_float(car_capacity)
    if car_capacity is None:
        return error(1001)
    user, err = UserService.register(car_id, user_name, car_capacity, password, role)
    if err == "car_id_exists":
        return error(2003)
    if not user:
        return error(1001)
    return success({"car_id": user.car_id, "user_name": user.user_name})


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    car_id = data.get("car_id", "").strip()
    password = data.get("password", "")
    if not car_id or not password:
        return error(1001)
    user, err = UserService.login(car_id, password)
    if err == "user_not_found":
        return error(2001)
    if err == "wrong_password":
        return error(2002)
    token = create_access_token(
        identity=user.car_id,
        additional_claims={"role": user.role},
        expires_delta=JWT_ACCESS_TOKEN_EXPIRES,
    )
    return success({
        "access_token": token,
        "car_id": user.car_id,
        "role": user.role,
        "user_name": user.user_name,
    })


@bp.route("/password", methods=["PUT"])
@jwt_required()
def set_password():
    car_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    old_pwd = data.get("old_password", "")
    new_pwd = data.get("new_password", "")
    if not new_pwd:
        return error(1001)
    _, err = UserService.set_password(car_id, old_pwd, new_pwd)
    if err == "wrong_password":
        return error(2002)
    return success()
