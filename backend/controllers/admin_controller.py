from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity
from ..utils.timezone import local_now
from ..services.fault_service import FaultService
from ..services.admin_service import AdminService
from ..utils.auth import admin_required
from ..utils.errors import success, error
from ..utils.validators import parse_int

bp = Blueprint("admin", __name__)


@bp.route("/fault/report", methods=["POST"])
@admin_required
def report_fault():
    data = request.get_json(silent=True) or {}
    pile_id = parse_int(data.get("pile_id", 0))
    if pile_id is None:
        return error(1001)
    car_id = get_jwt_identity()
    result, err = FaultService.report_fault(pile_id, handler=car_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "already_fault":
        return error(4002, "充电桩已处于故障状态")
    return success(result)


@bp.route("/fault/recover", methods=["POST"])
@admin_required
def recover_fault():
    data = request.get_json(silent=True) or {}
    pile_id = parse_int(data.get("pile_id", 0))
    if pile_id is None:
        return error(1001)
    car_id = get_jwt_identity()
    result, err = FaultService.recover_fault(pile_id, handler=car_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "not_fault":
        return error(4002, "充电桩未处于故障状态")
    return success(result)


@bp.route("/fault/list", methods=["GET"])
@admin_required
def fault_list():
    result = FaultService.get_fault_records()
    return success(result)


@bp.route("/fault/dispatch", methods=["POST"])
@admin_required
def manual_dispatch():
    data = request.get_json(silent=True) or {}
    request_id = parse_int(data.get("request_id", 0))
    target_pile_id = parse_int(data.get("target_pile_id", 0))
    if request_id is None or target_pile_id is None:
        return error(1001)
    result, err = FaultService.manual_dispatch(request_id, target_pile_id)
    if err == "invalid_request":
        return error(3002)
    if err == "pile_unavailable":
        return error(4002)
    if err == "pile_full":
        return error(4003)
    return success()


@bp.route("/report/stats", methods=["GET"])
@admin_required
def report_stats():
    period = request.args.get("period", "day")
    date_str = request.args.get("date")
    result = AdminService.get_report(period, date_str)
    if result is None:
        return error(1001)
    return success(result)


@bp.route("/waiting-area", methods=["GET"])
@admin_required
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
                    "wait_minutes": round((local_now() - e.join_time).total_seconds() / 60, 1),
                })

    return success({
        "capacity": SYSTEM_CONFIG["WaitingAreaSize"],
        "fast_waiting": WaitingQueueDAO.get_count_by_mode("F"),
        "slow_waiting": WaitingQueueDAO.get_count_by_mode("T"),
        "vehicles": vehicles,
    })


@bp.route("/system-config", methods=["GET"])
@admin_required
def get_system_config():
    from .. import config
    return success({
        "fast_pile_num": config.SYSTEM_CONFIG["FastChargingPileNum"],
        "slow_pile_num": config.SYSTEM_CONFIG["TrickleChargingPileNum"],
        "waiting_area_size": config.SYSTEM_CONFIG["WaitingAreaSize"],
        "charging_queue_len": config.SYSTEM_CONFIG["ChargingQueueLen"],
        "fault_strategy": config.FAULT_DISPATCH_STRATEGY,
        "dispatch_mode": config.EXTENDED_DISPATCH_MODE,
    })


@bp.route("/system-config", methods=["PUT"])
@admin_required
def update_system_config():
    from .. import config
    data = request.get_json(silent=True) or {}
    fast_num = parse_int(data.get("fast_pile_num", config.SYSTEM_CONFIG["FastChargingPileNum"]))
    slow_num = parse_int(data.get("slow_pile_num", config.SYSTEM_CONFIG["TrickleChargingPileNum"]))
    waiting_size = parse_int(data.get("waiting_area_size", config.SYSTEM_CONFIG["WaitingAreaSize"]))
    queue_len = parse_int(data.get("charging_queue_len", config.SYSTEM_CONFIG["ChargingQueueLen"]))
    fault_strategy = data.get("fault_strategy", config.FAULT_DISPATCH_STRATEGY)
    dispatch_mode = data.get("dispatch_mode", config.EXTENDED_DISPATCH_MODE)
    if None in (fast_num, slow_num, waiting_size, queue_len):
        return error(1001)
    result, err = AdminService.update_system_config(
        fast_num, slow_num, waiting_size, queue_len, fault_strategy, dispatch_mode
    )
    if err == "pile_busy":
        return error(4002, "被关闭的充电桩仍有车辆或会话")
    if err == "queue_len_too_small":
        return error(4002, "现有队列车辆数超过新的队列长度")
    if err:
        return error(1001)
    return success(result)
