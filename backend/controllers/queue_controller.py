from flask import Blueprint, request
from ..utils.timezone import local_now
from ..utils.auth import admin_required
from ..services.queue_service import QueueService
from ..utils.errors import success

bp = Blueprint("queue", __name__)


@bp.route("/waiting", methods=["GET"])
@admin_required
def waiting_queue():
    mode = request.args.get("mode", "F")
    result = QueueService.get_waiting_queue_list(mode)
    return success(result)


@bp.route("/pile/<int:pile_id>", methods=["GET"])
@admin_required
def pile_queue(pile_id):
    from ..dao.pile_queue_dao import PileQueueDAO
    from ..dao.user_dao import ChargingRequestDAO, ChargingSessionDAO, UserDAO
    from ..dao.pile_dao import ChargingPileDAO

    entries = PileQueueDAO.get_by_pile_ordered(pile_id)
    pile = ChargingPileDAO.find_by_id(pile_id)
    vehicles = []
    for e in entries:
        req = ChargingRequestDAO.find_by_id(e.request_id)
        if not req:
            continue
        user = UserDAO.find_by_car_id(req.car_id)
        # 查询充电进度
        session = ChargingSessionDAO.find_active_by_car_id(req.car_id)
        progress = 0.0
        if session and req.status == "charging" and req.request_amount > 0:
            elapsed = (local_now() - session.start_time).total_seconds() / 3600
            charged = round(min(elapsed * pile.power, req.request_amount), 2) if pile else 0
            progress = round(min(charged / req.request_amount * 100, 100), 1)

        vehicles.append({
            "request_id": req.request_id,
            "car_id": req.car_id,
            "car_capacity": user.car_capacity if user else 0,
            "request_amount": req.request_amount,
            "position": e.position,
            "queue_num": req.queue_num,
            "status": req.status,
            "progress": progress,
            "wait_minutes": round((local_now() - e.enter_time).total_seconds() / 60, 1),
        })
    return success(vehicles)
