from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.fault_service import FaultService
from ..services.admin_service import AdminService
from ..utils.errors import success, error

bp = Blueprint("admin", __name__)


@bp.route("/fault/report", methods=["POST"])
@jwt_required()
def report_fault():
    data = request.get_json()
    pile_id = data.get("pile_id", 0)
    car_id = get_jwt_identity()
    result, err = FaultService.report_fault(int(pile_id), handler=car_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "already_fault":
        return error(4002, "充电桩已处于故障状态")
    return success(result)


@bp.route("/fault/recover", methods=["POST"])
@jwt_required()
def recover_fault():
    data = request.get_json()
    pile_id = data.get("pile_id", 0)
    car_id = get_jwt_identity()
    result, err = FaultService.recover_fault(int(pile_id), handler=car_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "not_fault":
        return error(4002, "充电桩未处于故障状态")
    return success(result)


@bp.route("/fault/list", methods=["GET"])
@jwt_required()
def fault_list():
    result = FaultService.get_fault_records()
    return success(result)


@bp.route("/fault/dispatch", methods=["POST"])
@jwt_required()
def manual_dispatch():
    data = request.get_json()
    request_id = data.get("request_id", 0)
    target_pile_id = data.get("target_pile_id", 0)
    result, err = FaultService.manual_dispatch(int(request_id), int(target_pile_id))
    if err == "invalid_request":
        return error(3002)
    if err == "pile_unavailable":
        return error(4002)
    if err == "pile_full":
        return error(4003)
    return success()


@bp.route("/report/stats", methods=["GET"])
@jwt_required()
def report_stats():
    period = request.args.get("period", "day")
    date_str = request.args.get("date")
    result = AdminService.get_report(period, date_str)
    return success(result)


@bp.route("/waiting-area", methods=["GET"])
@jwt_required()
def waiting_area():
    from ..dao.queue_dao import WaitingQueueDAO
    from ..dao.user_dao import ChargingRequestDAO, UserDAO
    from ..config import SYSTEM_CONFIG

    vehicles = []
    for mode in ("F", "T"):
        for e in WaitingQueueDAO.get_all_by_mode(mode):
            req = ChargingRequestDAO.find_by_id(e.request_id)
            if req:
                u = UserDAO.find_by_car_id(req.car_id)
                vehicles.append({
                    "car_id": req.car_id,
                    "car_capacity": u.car_capacity if u else 0,
                    "request_amount": req.request_amount,
                    "queue_num": req.queue_num,
                    "mode": mode,
                    "mode_label": "快充" if mode == "F" else "慢充",
                    "wait_minutes": 0,
                })

    return success({
        "capacity": SYSTEM_CONFIG["WaitingAreaSize"],
        "fast_waiting": WaitingQueueDAO.get_count_by_mode("F"),
        "slow_waiting": WaitingQueueDAO.get_count_by_mode("T"),
        "vehicles": vehicles,
    })


@bp.route("/system-config", methods=["GET"])
@jwt_required()
def get_system_config():
    from ..config import SYSTEM_CONFIG, FAULT_DISPATCH_STRATEGY
    return success({
        "fast_pile_num": SYSTEM_CONFIG["FastChargingPileNum"],
        "slow_pile_num": SYSTEM_CONFIG["TrickleChargingPileNum"],
        "waiting_area_size": SYSTEM_CONFIG["WaitingAreaSize"],
        "charging_queue_len": SYSTEM_CONFIG["ChargingQueueLen"],
        "fault_strategy": FAULT_DISPATCH_STRATEGY,
    })
