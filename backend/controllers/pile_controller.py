from flask import Blueprint, request
from ..services.pile_service import PileService
from ..utils.auth import admin_required
from ..utils.errors import success, error
from ..utils.validators import parse_float

bp = Blueprint("pile", __name__)


@bp.route("/status", methods=["GET"])
@admin_required
def all_piles():
    result = PileService.query_all_piles()
    return success(result)


@bp.route("/<int:pile_id>", methods=["GET"])
@admin_required
def pile_detail(pile_id):
    result = PileService.query_pile_detail(pile_id)
    if not result:
        return error(4001)
    return success(result)


@bp.route("/<int:pile_id>/poweron", methods=["POST"])
@admin_required
def power_on(pile_id):
    _, err = PileService.power_on(pile_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "status_not_off":
        return error(4002)
    return success()


@bp.route("/<int:pile_id>/start", methods=["POST"])
@admin_required
def start_pile(pile_id):
    _, err = PileService.start_charging_pile(pile_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "status_not_standby":
        return error(4002)
    return success()


@bp.route("/<int:pile_id>/poweroff", methods=["POST"])
@admin_required
def power_off(pile_id):
    _, err = PileService.power_off(pile_id)
    if err == "pile_not_found":
        return error(4001)
    if err == "has_active_session":
        return error(4002, "存在进行中的充电会话")
    if err == "has_queued_vehicle":
        return error(4002, "充电桩队列中仍有车辆")
    return success()


@bp.route("/parameters", methods=["PUT"])
@admin_required
def set_parameters():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "F")
    if mode not in ("F", "T"):
        return error(1001)
    peak = parse_float(data.get("peak_price"))
    mid = parse_float(data.get("mid_price"))
    off_peak = parse_float(data.get("off_peak_price"))
    service = parse_float(data.get("service_fee_rate"))
    if any(v is None for v in [peak, mid, off_peak, service]):
        return error(1001)
    result, err = PileService.set_parameters(mode, peak, mid, off_peak, service)
    if err == "fixed_pricing":
        return error(1003, "计费规则为需求固定值，不支持修改")
    if err:
        return error(1001)
    return success(result)


@bp.route("/parameters", methods=["GET"])
@admin_required
def get_parameters():
    from ..dao.misc_dao import PricingRuleDAO
    fast = PricingRuleDAO.get_by_mode("F")
    slow = PricingRuleDAO.get_by_mode("T")
    return success({
        "fast": {"peak_price": fast.peak_price, "mid_price": fast.mid_price, "off_peak_price": fast.off_peak_price, "service_fee_rate": fast.service_fee_rate} if fast else None,
        "slow": {"peak_price": slow.peak_price, "mid_price": slow.mid_price, "off_peak_price": slow.off_peak_price, "service_fee_rate": slow.service_fee_rate} if slow else None,
    })
