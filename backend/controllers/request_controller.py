from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.request_service import RequestService
from ..services.charging_service import ChargingService
from ..utils.errors import success, error
from ..utils.validators import parse_float, parse_int
from ..dao.user_dao import UserDAO

bp = Blueprint("charging", __name__)


def _check_user(car_id):
    """验证 JWT 中的用户是否在数据库中存在。"""
    if not UserDAO.find_by_car_id(car_id):
        return False
    return True


@bp.route("/request", methods=["POST"])
@jwt_required()
def submit_request():
    car_id = get_jwt_identity()
    if not _check_user(car_id):
        return error(2001)
    data = request.get_json(silent=True) or {}
    request_amount = parse_float(data.get("request_amount", 0))
    request_mode = data.get("request_mode", "").strip()
    if request_mode not in ("F", "T"):
        from .. import config
        if config.EXTENDED_DISPATCH_MODE == "batch_min_total":
            request_mode = "F"
    if request_amount is None or request_amount <= 0 or request_mode not in ("F", "T"):
        return error(1001)
    result, err = RequestService.submit_request(car_id, request_amount, request_mode)
    if err == "has_active_request":
        return error(3001)
    if err == "waiting_area_full":
        return error(3005)
    return success(result)


@bp.route("/amount", methods=["PUT"])
@jwt_required()
def modify_amount():
    car_id = get_jwt_identity()
    if not _check_user(car_id):
        return error(2001)
    data = request.get_json(silent=True) or {}
    new_amount = parse_float(data.get("amount", 0))
    if new_amount is None or new_amount <= 0:
        return error(1001)
    _, err = RequestService.modify_amount(car_id, new_amount)
    if err == "no_active_request":
        return error(3002)
    if err == "not_in_waiting_area":
        return error(3003)
    return success()


@bp.route("/mode", methods=["PUT"])
@jwt_required()
def modify_mode():
    car_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    new_mode = data.get("mode", "").strip()
    if new_mode not in ("F", "T"):
        return error(1001)
    _, err = RequestService.modify_mode(car_id, new_mode)
    if err == "no_active_request":
        return error(3002)
    if err == "not_in_waiting_area":
        return error(3003)
    if err == "same_mode":
        return error(1001, "新旧模式相同")
    return success()


@bp.route("/cancel", methods=["DELETE"])
@jwt_required()
def cancel():
    car_id = get_jwt_identity()
    result, err = RequestService.cancel_request(car_id)
    if err == "no_active_request":
        return error(3002)
    return success(result)


@bp.route("/queue-status", methods=["GET"])
@jwt_required()
def queue_status():
    car_id = get_jwt_identity()
    result, err = RequestService.query_state(car_id)
    if err == "no_active_request":
        return success({"has_request": False})
    return success(result)


@bp.route("/start", methods=["POST"])
@jwt_required()
def start_charging():
    car_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    pile_id = parse_int(data.get("pile_id", 0))
    if pile_id is None:
        return error(1001)
    result, err = ChargingService.start_charging(car_id, pile_id)
    if err == "no_active_request":
        return error(3002)
    if err == "not_dispatched":
        return error(3003)
    if err == "wrong_pile":
        return error(3003, "车辆未分配到该充电桩")
    if err == "pile_not_found":
        return error(4001)
    if err == "pile_unavailable":
        return error(4002)
    if err == "not_first_in_queue":
        return error(3003, "尚未轮到该车辆充电")
    return success({"session_id": result.session_id})


@bp.route("/status", methods=["GET"])
@jwt_required()
def charging_status():
    car_id = get_jwt_identity()
    result, err = ChargingService.query_charging_state(car_id)
    if err == "no_active_session":
        return success({"has_request": False})
    return success(result)


@bp.route("/end", methods=["POST"])
@jwt_required()
def end_charging():
    car_id = get_jwt_identity()
    result, err = ChargingService.end_charging(car_id)
    if err == "no_active_session":
        return error(3002)
    return success(result)
