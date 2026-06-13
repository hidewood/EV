from ..dao.user_dao import ChargingRequestDAO, UserDAO
from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..models.charging_request import ChargingRequest
from ..services.queue_service import QueueService
from ..services.dispatch_service import DispatchService


class RequestService:
    @staticmethod
    def submit_request(car_id, request_amount, request_mode):
        from .. import config

        active = ChargingRequestDAO.find_active_by_car_id(car_id)
        if active:
            return None, "has_active_request"
        if config.EXTENDED_DISPATCH_MODE == "batch_min_total":
            if QueueService.waiting_area_count() >= DispatchService.station_capacity():
                return None, "waiting_area_full"
        else:
            matching_piles = ChargingPileDAO.find_by_mode_and_status(request_mode, ["available", "charging"])
            has_immediate_slot = any(
                PileQueueDAO.get_count_by_pile(p.pile_id) < p.queue_len
                for p in matching_piles
            )
            if not QueueService.waiting_area_has_slot() and not has_immediate_slot:
                return None, "waiting_area_full"

        request_obj = ChargingRequest(
            car_id=car_id,
            request_mode=request_mode,
            request_amount=request_amount,
            status="queuing",
        )
        ChargingRequestDAO.insert(request_obj)
        queue_num = QueueService.add_to_waiting(request_obj.request_id, request_mode)
        request_obj.queue_num = queue_num
        ChargingRequestDAO.update(request_obj)

        DispatchService.trigger_auto_dispatch()
        position = QueueService.get_car_position(request_obj)
        return {
            "request_id": request_obj.request_id,
            "queue_num": queue_num,
            "status": request_obj.status,
            "pile_id": request_obj.pile_id,
            "position": position,
        }, None

    @staticmethod
    def modify_amount(car_id, new_amount):
        req = ChargingRequestDAO.find_active_by_car_id(car_id)
        if not req:
            return None, "no_active_request"
        if req.status != "queuing":
            return None, "not_in_waiting_area"
        req.request_amount = new_amount
        ChargingRequestDAO.update(req)
        return req, None

    @staticmethod
    def modify_mode(car_id, new_mode):
        req = ChargingRequestDAO.find_active_by_car_id(car_id)
        if not req:
            return None, "no_active_request"
        if req.status != "queuing":
            return None, "not_in_waiting_area"
        if req.request_mode == new_mode:
            return None, "same_mode"

        QueueService.remove_from_waiting(req.request_id)
        req.request_mode = new_mode
        req.pile_id = None
        req.status = "queuing"
        new_queue_num = QueueService.add_to_waiting(req.request_id, new_mode)
        req.queue_num = new_queue_num
        ChargingRequestDAO.update(req)

        DispatchService.trigger_auto_dispatch()
        return req, None

    @staticmethod
    def cancel_request(car_id):
        req = ChargingRequestDAO.find_active_by_car_id(car_id)
        if not req:
            return None, "no_active_request"

        if req.status == "queuing":
            QueueService.remove_from_waiting(req.request_id)
            req.status = "cancelled"
            ChargingRequestDAO.update(req)
            return {"message": "已取消", "detail_generated": False}, None

        if req.status in ("dispatched", "charging", "pending_reschedule"):
            from ..services.charging_service import ChargingService
            return ChargingService.cancel_charging(req)

        return None, "invalid_status"

    @staticmethod
    def query_state(car_id):
        req = ChargingRequestDAO.find_active_by_car_id(car_id)
        if not req:
            return None, "no_active_request"
        position = QueueService.get_car_position(req)
        # 检查最近一次调度是否因故障触发
        fault_notice = False
        if req.status == "dispatched" and req.pile_id:
            from ..models.dispatch_record import DispatchRecord
            latest = (
                DispatchRecord.query
                .filter_by(request_id=req.request_id)
                .order_by(DispatchRecord.record_id.desc())
                .first()
            )
            if latest and ("fault" in (latest.from_location or "") or "fault" in (latest.dispatch_type or "") or "recovery" in (latest.from_location or "")):
                fault_notice = True
        return {
            "request_id": req.request_id,
            "queue_num": req.queue_num,
            "status": req.status,
            "request_mode": req.request_mode,
            "request_amount": req.request_amount,
            "pile_id": req.pile_id,
            "position": position,
            "fault_notice": fault_notice,
        }, None
