from ..dao.user_dao import ChargingRequestDAO, ChargingSessionDAO, ChargingDetailDAO, BillDAO
from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.misc_dao import PricingRuleDAO, DispatchRecordDAO
from ..models.charging_session import ChargingSession
from ..models.charging_detail import ChargingDetail
from ..models.bill import Bill
from ..models.dispatch_record import DispatchRecord
from ..services.dispatch_service import DispatchService
from ..services.queue_service import QueueService
from ..utils.pricing import calculate_charge_fee, calculate_service_fee
from ..utils.timezone import local_now


class ChargingService:
    @staticmethod
    def start_charging(car_id, pile_id):
        req = ChargingRequestDAO.find_active_by_car_id(car_id)
        if not req:
            return None, "no_active_request"
        if req.status != "dispatched":
            return None, "not_dispatched"
        if req.pile_id != pile_id:
            return None, "wrong_pile"

        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None, "pile_not_found"
        if pile.status not in ("available", "charging"):
            return None, "pile_unavailable"

        if QueueService.pile_ahead_count(req) > 0:
            return None, "not_first_in_queue"

        active = ChargingSessionDAO.find_active_by_pile_id(pile_id)
        if active and active.car_id != car_id:
            return None, "not_first_in_queue"

        first = PileQueueDAO.get_first(pile_id)
        if not first or first.request_id != req.request_id:
            return None, "not_first_in_queue"

        session = ChargingSession(
            request_id=req.request_id,
            car_id=car_id,
            pile_id=pile_id,
            status="active",
        )
        ChargingSessionDAO.insert(session)

        req.status = "charging"
        ChargingRequestDAO.update(req)

        pile.status = "charging"
        ChargingPileDAO.update(pile)
        return {
            "session_id": session.session_id,
            "request_id": req.request_id,
            "pile_id": pile_id,
            "status": "charging",
            "start_time": session.start_time.isoformat() if session.start_time else None,
        }, None

    @staticmethod
    def end_charging(car_id):
        session = ChargingSessionDAO.find_active_by_car_id(car_id)
        if not session:
            return None, "no_active_session"

        req = ChargingRequestDAO.find_by_id(session.request_id)
        if not req:
            return None, "request_not_found"

        pile = ChargingPileDAO.find_by_id(session.pile_id)
        pricing = PricingRuleDAO.get_by_mode(pile.mode)
        now = local_now()
        start = session.start_time

        # 实际充电量：模拟已充到请求量 or 按时间计算
        elapsed_hours = (now - start).total_seconds() / 3600
        actual_amount = round(min(elapsed_hours * pile.power, req.request_amount), 2)
        actual_hours = actual_amount / pile.power if pile.power else 0.0

        charge_fee = calculate_charge_fee(actual_amount, pile.power, start, pricing)
        service_fee = calculate_service_fee(actual_amount, pricing)

        session.end_time = now
        session.charge_amount = actual_amount
        session.status = "completed"
        ChargingSessionDAO.update(session)

        detail = ChargingDetail(
            session_id=session.session_id,
            car_id=car_id,
            pile_id=pile.pile_id,
            charge_amount=actual_amount,
            charge_duration=round(actual_hours, 2),
            start_time=start,
            stop_time=now,
            charge_fee=charge_fee,
            service_fee=service_fee,
            total_fee=round(charge_fee + service_fee, 2),
        )
        ChargingDetailDAO.insert(detail)

        bill = Bill(
            detail_id=detail.detail_id,
            car_id=car_id,
            total_charge_fee=charge_fee,
            total_service_fee=service_fee,
            total_fee=round(charge_fee + service_fee, 2),
        )
        BillDAO.insert(bill)

        req.status = "completed"
        ChargingRequestDAO.update(req)

        PileQueueDAO.remove_by_request_id(req.request_id)

        pile.total_charge_num += 1
        pile.total_charge_time += actual_hours
        pile.total_charge_capacity += actual_amount
        # 无其他活跃会话时恢复为 available
        if not ChargingSessionDAO.find_active_by_pile_id(pile.pile_id):
            pile.status = "available"
        ChargingPileDAO.update(pile)

        DispatchService.trigger_auto_dispatch()

        return {
            "session_id": session.session_id,
            "request_id": req.request_id,
            "detail_id": detail.detail_id,
            "bill_id": bill.bill_id,
            "charge_amount": actual_amount,
            "charged_amount": actual_amount,
            "charge_fee": charge_fee,
            "service_fee": service_fee,
            "total_fee": round(charge_fee + service_fee, 2),
        }, None

    @staticmethod
    def cancel_charging(req):
        """取消充电区请求。若正在充电则生成详单。"""
        session = ChargingSessionDAO.find_active_by_car_id(req.car_id)
        if session:
            pile = ChargingPileDAO.find_by_id(session.pile_id)
            pricing = PricingRuleDAO.get_by_mode(pile.mode)
            now = local_now()
            elapsed_hours = (now - session.start_time).total_seconds() / 3600
            actual_amount = round(min(elapsed_hours * pile.power, req.request_amount), 2)
            actual_hours = actual_amount / pile.power if pile.power else 0.0

            charge_fee = calculate_charge_fee(actual_amount, pile.power, session.start_time, pricing)
            service_fee = calculate_service_fee(actual_amount, pricing)

            session.end_time = now
            session.charge_amount = actual_amount
            session.status = "interrupted"
            ChargingSessionDAO.update(session)

            detail = ChargingDetail(
                session_id=session.session_id,
                car_id=session.car_id,
                pile_id=pile.pile_id,
                charge_amount=actual_amount,
                charge_duration=round(actual_hours, 2),
                start_time=session.start_time,
                stop_time=now,
                charge_fee=charge_fee,
                service_fee=service_fee,
                total_fee=round(charge_fee + service_fee, 2),
            )
            ChargingDetailDAO.insert(detail)

            bill = Bill(
                detail_id=detail.detail_id,
                car_id=session.car_id,
                total_charge_fee=charge_fee,
                total_service_fee=service_fee,
                total_fee=round(charge_fee + service_fee, 2),
            )
            BillDAO.insert(bill)

            pile.total_charge_num += 1
            pile.total_charge_time += actual_hours
            pile.total_charge_capacity += actual_amount
            if not ChargingSessionDAO.find_active_by_pile_id(pile.pile_id):
                pile.status = "available"
            ChargingPileDAO.update(pile)

        PileQueueDAO.remove_by_request_id(req.request_id)
        req.status = "cancelled"
        ChargingRequestDAO.update(req)

        DispatchService.trigger_auto_dispatch()
        return {"message": "已取消", "detail_generated": session is not None}, None

    @staticmethod
    def query_charging_state(car_id):
        session = ChargingSessionDAO.find_active_by_car_id(car_id)
        if not session:
            req = ChargingRequestDAO.find_active_by_car_id(car_id)
            if not req:
                return {"has_request": False}, None
            position = None
            if req.status in ("queuing", "dispatched", "pending_reschedule"):
                from ..services.queue_service import QueueService
                position = QueueService.get_car_position(req)
            pile = ChargingPileDAO.find_by_id(req.pile_id) if req.pile_id else None
            return {
                "has_request": True,
                "request_id": req.request_id,
                "queue_num": req.queue_num,
                "status": req.status,
                "request_mode": req.request_mode,
                "request_amount": req.request_amount,
                "charged_amount": 0.0,
                "estimated_amount": 0.0,
                "pile_id": req.pile_id,
                "pile_mode": pile.mode if pile else req.request_mode,
                "pile_power": pile.power if pile else None,
                "session_id": None,
                "start_time": None,
                "elapsed_hours": 0.0,
                "current_charge_fee": 0.0,
                "current_service_fee": 0.0,
                "current_total": 0.0,
                "position": position,
            }, None
        req = ChargingRequestDAO.find_by_id(session.request_id)
        pile = ChargingPileDAO.find_by_id(session.pile_id)
        pricing = PricingRuleDAO.get_by_mode(pile.mode)

        elapsed = (local_now() - session.start_time).total_seconds() / 3600
        estimated_amount = round(min(elapsed * pile.power, req.request_amount), 2)
        current_fee = calculate_charge_fee(estimated_amount, pile.power, session.start_time, pricing)
        current_service = calculate_service_fee(estimated_amount, pricing)

        return {
            "has_request": True,
            "request_id": req.request_id,
            "queue_num": req.queue_num,
            "status": req.status,
            "pile_id": pile.pile_id,
            "pile_mode": pile.mode,
            "pile_power": pile.power,
            "session_id": session.session_id,
            "start_time": session.start_time.isoformat(),
            "elapsed_hours": round(elapsed, 2),
            "estimated_amount": estimated_amount,
            "charged_amount": estimated_amount,
            "request_amount": req.request_amount,
            "current_charge_fee": current_fee,
            "current_service_fee": current_service,
            "current_total": round(current_fee + current_service, 2),
        }, None
