"""对外接口 —— 用于联合验收对接。"""
from flask import Blueprint, request
from flask_jwt_extended import create_access_token
from ..services.pile_service import PileService
from ..services.request_service import RequestService
from ..services.admin_service import AdminService
from ..utils.errors import success, error
from ..utils.auth import partner_required
from ..utils.validators import parse_float
from ..config import PARTNER_CONFIG, JWT_ACCESS_TOKEN_EXPIRES

bp = Blueprint("external", __name__, url_prefix="/api/v1/external")


@bp.route("/auth/token", methods=["POST"])
def get_token():
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "")
    partner_id = data.get("partner_id", "")
    expected_key = PARTNER_CONFIG.get("partner_api_key")
    expected_partner = PARTNER_CONFIG.get("partner_id")
    if not expected_key or not expected_partner:
        return error(1002, "对外接口未配置")
    if api_key != expected_key or partner_id != expected_partner:
        return error(1002, "认证失败")
    token = create_access_token(
        identity=f"partner_{partner_id}",
        additional_claims={"role": "partner"},
        expires_delta=JWT_ACCESS_TOKEN_EXPIRES,
    )
    return success({"access_token": token, "expires_in": 7200})


@bp.route("/piles/status", methods=["GET"])
@partner_required
def piles_status():
    piles = PileService.query_all_piles()
    waiting = AdminService.get_waiting_area_status()
    return success({
        "station_id": "BUPT-01",
        "piles": piles,
        "waiting_area": waiting,
    })


@bp.route("/charging/request", methods=["POST"])
@partner_required
def submit_charging():
    data = request.get_json(silent=True) or {}
    car_id = data.get("car_id", "").strip()
    request_mode = data.get("request_mode", "").strip()
    request_amount = parse_float(data.get("request_amount", 0))
    if not car_id or len(car_id) > 20 or request_amount is None or request_amount <= 0 or request_mode not in ("F", "T"):
        return error(1001)

    # 对对方用户自动注册（简化）
    from ..services.user_service import UserService
    from ..dao.user_dao import UserDAO
    user = UserDAO.find_by_car_id(car_id)
    if not user:
        UserService.register(car_id, f"partner_user_{car_id}", 60.0, "default123")

    result, err = RequestService.submit_request(car_id, request_amount, request_mode)
    if err == "has_active_request":
        return error(3001)
    if err == "waiting_area_full":
        return error(3005)
    if err:
        return error(1001)

    return success(result)


@bp.route("/charging/status/<int:request_id>", methods=["GET"])
@partner_required
def charging_status_external(request_id):
    from ..dao.user_dao import ChargingRequestDAO
    req = ChargingRequestDAO.find_by_id(request_id)
    if not req:
        return error(3002)
    state, err = RequestService.query_state(req.car_id)
    if not err and state and state.get("request_id") == request_id:
        return success(state)
    return success({
        "request_id": req.request_id,
        "queue_num": req.queue_num,
        "status": req.status,
        "request_mode": req.request_mode,
        "request_amount": req.request_amount,
        "pile_id": req.pile_id,
        "position": None,
        "fault_notice": False,
    })
