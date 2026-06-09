"""对外接口 —— 用于联合验收对接。"""
from flask import Blueprint, request
from flask_jwt_extended import create_access_token, jwt_required
from ..services.pile_service import PileService
from ..services.request_service import RequestService
from ..services.charging_service import ChargingService
from ..services.admin_service import AdminService
from ..utils.errors import success, error
from ..config import PARTNER_CONFIG, JWT_ACCESS_TOKEN_EXPIRES

bp = Blueprint("external", __name__, url_prefix="/api/v1/external")


@bp.route("/auth/token", methods=["POST"])
def get_token():
    data = request.get_json()
    api_key = data.get("api_key", "")
    partner_id = data.get("partner_id", "")
    if api_key != PARTNER_CONFIG.get("partner_api_key") or partner_id != PARTNER_CONFIG.get("partner_id"):
        return error(1002, "认证失败")
    token = create_access_token(
        identity=f"partner_{partner_id}",
        additional_claims={"role": "partner"},
        expires_delta=JWT_ACCESS_TOKEN_EXPIRES,
    )
    return success({"access_token": token, "expires_in": 7200})


@bp.route("/piles/status", methods=["GET"])
@jwt_required()
def piles_status():
    piles = PileService.query_all_piles()
    waiting = AdminService.get_waiting_area_status()
    return success({
        "station_id": "BUPT-01",
        "piles": piles,
        "waiting_area": waiting,
    })


@bp.route("/charging/request", methods=["POST"])
@jwt_required()
def submit_charging():
    data = request.get_json()
    car_id = data.get("car_id", "").strip()
    request_mode = data.get("request_mode", "").strip()
    request_amount = data.get("request_amount", 0)
    callback_url = data.get("callback_url", "")

    if not car_id or request_amount <= 0 or request_mode not in ("F", "T"):
        return error(1001)

    # 对对方用户自动注册（简化）
    from ..services.user_service import UserService
    from ..dao.user_dao import UserDAO
    user = UserDAO.find_by_car_id(car_id)
    if not user:
        UserService.register(car_id, f"partner_user_{car_id}", 60.0, "default123")

    result, err = RequestService.submit_request(car_id, float(request_amount), request_mode)
    if err:
        return error(3001)

    return success(result)


@bp.route("/charging/status/<int:request_id>", methods=["GET"])
@jwt_required()
def charging_status_external(request_id):
    from ..dao.user_dao import ChargingRequestDAO
    req = ChargingRequestDAO.find_by_id(request_id)
    if not req:
        return error(3002)
    state, _ = RequestService.query_state(req.car_id)
    return success(state)
