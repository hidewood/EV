"""
故障服务：上报故障、故障恢复、手动调度。
故障只考虑单一充电桩故障且该桩有车排队的情况。
"""

from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.user_dao import ChargingRequestDAO, ChargingSessionDAO, ChargingDetailDAO, BillDAO
from ..dao.misc_dao import FaultRecordDAO, PricingRuleDAO
from ..models.charging_detail import ChargingDetail
from ..models.bill import Bill
from ..services.dispatch_service import DispatchService
from ..utils.pricing import calculate_charge_fee, calculate_service_fee
from ..config import FAULT_DISPATCH_STRATEGY
from datetime import datetime


class FaultService:

    @staticmethod
    def report_fault(pile_id, handler=None):
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None, "pile_not_found"
        if pile.status == "fault":
            return None, "already_fault"

        pile.status = "fault"
        ChargingPileDAO.update(pile)

        # 若故障桩有正在充电的车 → 停止计费，生成详单，清除请求
        active = ChargingSessionDAO.find_active_by_pile_id(pile_id)
        if active:
            _interrupt_session(active)

        FaultRecordDAO.create(pile_id, handler)

        strategy = FAULT_DISPATCH_STRATEGY
        if strategy == "time_order":
            DispatchService.dispatch_by_time_order(pile_id)
        else:
            DispatchService.dispatch_by_priority(pile_id)

        return {"pile_id": pile_id, "status": "fault", "strategy": strategy}, None

    @staticmethod
    def recover_fault(pile_id, handler=None):
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None, "pile_not_found"
        if pile.status != "fault":
            return None, "not_fault"

        pile.status = "available"
        ChargingPileDAO.update(pile)

        record = FaultRecordDAO.find_active_by_pile(pile_id)
        if record:
            FaultRecordDAO.resolve(record)

        # 需求 7c：若其它同类型桩中有车辆排队，则暂停叫号重新调度
        DispatchService.dispatch_on_fault_recovery(pile_id)

        return {"pile_id": pile_id, "status": "available"}, None

    @staticmethod
    def get_fault_records():
        records = FaultRecordDAO.find_all()
        return [{
            "fault_id": r.fault_id, "pile_id": r.pile_id,
            "fault_time": r.fault_time.isoformat() if r.fault_time else None,
            "recover_time": r.recover_time.isoformat() if r.recover_time else None,
            "status": r.status, "handler": r.handler,
        } for r in records]

    @staticmethod
    def manual_dispatch(request_id, target_pile_id):
        req = ChargingRequestDAO.find_by_id(request_id)
        if not req or req.status not in ("queuing", "pending_reschedule"):
            return None, "invalid_request"
        target = ChargingPileDAO.find_by_id(target_pile_id)
        if not target or target.status not in ("available", "charging"):
            return None, "pile_unavailable"
        if PileQueueDAO.get_count_by_pile(target_pile_id) >= target.queue_len:
            return None, "pile_full"

        PileQueueDAO.remove_by_request_id(req.request_id)
        pos = PileQueueDAO.get_count_by_pile(target_pile_id) + 1
        PileQueueDAO.add(target_pile_id, req.request_id, pos)
        req.pile_id = target_pile_id
        req.status = "dispatched"
        ChargingRequestDAO.update(req)

        from ..dao.misc_dao import DispatchRecordDAO
        from ..models.dispatch_record import DispatchRecord
        DispatchRecordDAO.insert(DispatchRecord(
            request_id=req.request_id, from_location="manual",
            to_pile_id=target_pile_id, dispatch_type="manual",
        ))
        return req, None


def _interrupt_session(session):
    """故障中断正在充电的会话：停止计费、生成详单和账单、清除请求。"""
    pile = ChargingPileDAO.find_by_id(session.pile_id)
    pricing = PricingRuleDAO.get_by_mode(pile.mode)
    now = datetime.utcnow()
    req = ChargingRequestDAO.find_by_id(session.request_id)

    elapsed = (now - session.start_time).total_seconds() / 3600
    actual = round(min(elapsed * pile.power, req.request_amount if req else 0), 2)

    charge_fee = calculate_charge_fee(actual, pile.power, session.start_time, pricing)
    service_fee = calculate_service_fee(actual, pricing)

    session.end_time = now
    session.charge_amount = actual
    session.status = "interrupted"
    ChargingSessionDAO.update(session)

    detail = ChargingDetail(
        session_id=session.session_id, car_id=session.car_id, pile_id=pile.pile_id,
        charge_amount=actual, charge_duration=round(elapsed, 2),
        start_time=session.start_time, stop_time=now,
        charge_fee=charge_fee, service_fee=service_fee,
        total_fee=round(charge_fee + service_fee, 2),
    )
    ChargingDetailDAO.insert(detail)

    BillDAO.insert(Bill(
        detail_id=detail.detail_id, car_id=session.car_id,
        total_charge_fee=charge_fee, total_service_fee=service_fee,
        total_fee=round(charge_fee + service_fee, 2),
    ))

    pile.total_charge_num += 1
    pile.total_charge_time += elapsed
    pile.total_charge_capacity += actual
    ChargingPileDAO.update(pile)

    # 清除正在充电的车，标记待重调度
    if req:
        req.status = "pending_reschedule"
        ChargingRequestDAO.update(req)
