from ..models import db
from ..dao.user_dao import ChargingSessionDAO, BillDAO
from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.misc_dao import FaultRecordDAO, PricingRuleDAO
from ..models.charging_pile import ChargingPile
from datetime import datetime, timedelta
from ..utils.timezone import local_now


class AdminService:
    @staticmethod
    def reset_runtime_state():
        """清空当前运行态：保留用户、历史详单/账单和累计统计。"""
        from ..models.waiting_queue import WaitingQueue
        from ..models.pile_queue import PileQueue
        from ..models.dispatch_record import DispatchRecord
        from ..models.charging_request import ChargingRequest
        from ..models.charging_session import ChargingSession
        from ..models.fault_record import FaultRecord
        from ..services.dispatch_service import resume_calling

        now = local_now()
        active_sessions = ChargingSession.query.filter_by(status="active").all()
        active_requests = (
            ChargingRequest.query
            .filter(ChargingRequest.status.in_(["queuing", "dispatched", "charging", "pending_reschedule"]))
            .all()
        )
        active_faults = FaultRecord.query.filter_by(status="active").all()

        WaitingQueue.query.delete(synchronize_session=False)
        PileQueue.query.delete(synchronize_session=False)
        DispatchRecord.query.delete(synchronize_session=False)

        for session in active_sessions:
            session.status = "interrupted"
            session.end_time = session.end_time or now

        for req in active_requests:
            req.status = "cancelled"
            req.pile_id = None
            req.modify_time = now

        for record in active_faults:
            record.status = "resolved"
            record.recover_time = record.recover_time or now

        for pile in ChargingPileDAO.find_all():
            if pile.status in ("charging", "fault"):
                pile.status = "available"

        resume_calling()
        db.session.flush()
        return {
            "cancelled_requests": len(active_requests),
            "interrupted_sessions": len(active_sessions),
            "resolved_faults": len(active_faults),
            "message": "运行态已清空",
        }

    @staticmethod
    def reset_demo_defaults():
        """恢复演示默认：保留用户账号，清空业务数据并恢复默认桩/配置/计费。"""
        from .. import config
        from ..config import DEFAULT_PILES, DEFAULT_PRICING
        from ..models.waiting_queue import WaitingQueue
        from ..models.pile_queue import PileQueue
        from ..models.dispatch_record import DispatchRecord
        from ..models.fault_record import FaultRecord
        from ..models.payment import Payment
        from ..models.bill import Bill
        from ..models.charging_detail import ChargingDetail
        from ..models.charging_session import ChargingSession
        from ..models.charging_request import ChargingRequest
        from ..models.pricing_rule import PricingRule
        from ..services.dispatch_service import resume_calling

        # Delete children before parents to satisfy foreign keys on MySQL.
        for model in (
            WaitingQueue,
            PileQueue,
            DispatchRecord,
            FaultRecord,
            Payment,
            Bill,
            ChargingDetail,
            ChargingSession,
            ChargingRequest,
        ):
            model.query.delete(synchronize_session=False)

        default_queue_len = 5
        config.SYSTEM_CONFIG["FastChargingPileNum"] = 2
        config.SYSTEM_CONFIG["TrickleChargingPileNum"] = 3
        config.SYSTEM_CONFIG["WaitingAreaSize"] = 10
        config.SYSTEM_CONFIG["ChargingQueueLen"] = default_queue_len
        config.FAULT_DISPATCH_STRATEGY = "priority"
        config.EXTENDED_DISPATCH_MODE = "normal"

        for pr_cfg in DEFAULT_PRICING:
            rule = PricingRule.query.filter_by(mode=pr_cfg["mode"]).first()
            if not rule:
                db.session.add(PricingRule(**pr_cfg))
            else:
                rule.peak_price = pr_cfg["peak_price"]
                rule.mid_price = pr_cfg["mid_price"]
                rule.off_peak_price = pr_cfg["off_peak_price"]
                rule.service_fee_rate = pr_cfg["service_fee_rate"]
                rule.updated_at = local_now()

        default_ids = {p["pile_id"] for p in DEFAULT_PILES}
        for pile in ChargingPileDAO.find_all():
            if pile.pile_id not in default_ids:
                pile.status = "off"
                pile.queue_len = default_queue_len

        for p_cfg in DEFAULT_PILES:
            pile = ChargingPileDAO.find_by_id(p_cfg["pile_id"])
            if not pile:
                db.session.add(ChargingPile(
                    pile_id=p_cfg["pile_id"],
                    mode=p_cfg["mode"],
                    power=p_cfg["power"],
                    status="available",
                    queue_len=default_queue_len,
                    total_charge_num=0,
                    total_charge_time=0.0,
                    total_charge_capacity=0.0,
                ))
            else:
                pile.mode = p_cfg["mode"]
                pile.power = p_cfg["power"]
                pile.status = "available"
                pile.queue_len = default_queue_len
                pile.total_charge_num = 0
                pile.total_charge_time = 0.0
                pile.total_charge_capacity = 0.0

        resume_calling()
        db.session.flush()
        return {
            "fast_pile_num": 2,
            "slow_pile_num": 3,
            "waiting_area_size": 10,
            "charging_queue_len": default_queue_len,
            "fault_strategy": "priority",
            "dispatch_mode": "normal",
            "message": "演示默认状态已恢复",
        }

    @staticmethod
    def get_report(period="day", date_str=None):
        """按日/周/月生成报表。"""
        now = local_now()
        if not date_str:
            date_str = now.strftime("%Y-%m-%d")

        try:
            if period == "day":
                start = datetime.strptime(date_str, "%Y-%m-%d")
                end = start + timedelta(days=1)
            elif period == "week":
                start = datetime.strptime(date_str, "%Y-%m-%d")
                end = start + timedelta(days=7)
            elif period == "month":
                start = datetime.strptime(date_str, "%Y-%m")
                end = (start + timedelta(days=32)).replace(day=1)
            else:
                return None
        except ValueError:
            return None

        from ..models.charging_detail import ChargingDetail

        piles = ChargingPileDAO.find_all()
        result = []
        for p in piles:
            details = (
                ChargingDetail.query
                .filter(ChargingDetail.pile_id == p.pile_id)
                .filter(ChargingDetail.created_at >= start, ChargingDetail.created_at <= end)
                .all()
            )
            total_amount = sum(d.charge_amount for d in details)
            total_time = sum(d.charge_duration for d in details)
            total_charge_fee = sum(d.charge_fee for d in details)
            total_service_fee = sum(d.service_fee for d in details)

            result.append({
                "pile_id": p.pile_id,
                "mode": "快充" if p.mode == "F" else "慢充",
                "charge_count": len(details),
                "charge_time": round(total_time, 2),
                "charge_amount": round(total_amount, 2),
                "charge_fee": round(total_charge_fee, 2),
                "service_fee": round(total_service_fee, 2),
                "total_fee": round(total_charge_fee + total_service_fee, 2),
            })

        return {
            "period": period,
            "date": date_str,
            "piles": result,
        }

    @staticmethod
    def get_waiting_area_status():
        from ..dao.queue_dao import WaitingQueueDAO
        from ..config import SYSTEM_CONFIG
        return {
            "capacity": SYSTEM_CONFIG["WaitingAreaSize"],
            "fast_waiting": WaitingQueueDAO.get_count_by_mode("F"),
            "slow_waiting": WaitingQueueDAO.get_count_by_mode("T"),
        }

    @staticmethod
    def update_system_config(fast_num, slow_num, waiting_size, queue_len, fault_strategy, dispatch_mode="normal"):
        import backend.config as config

        if fast_num <= 0 or slow_num <= 0 or waiting_size <= 0 or queue_len <= 0:
            return None, "invalid_params"
        if fault_strategy not in ("priority", "time_order"):
            return None, "invalid_params"
        if dispatch_mode not in ("normal", "single_min_total", "batch_min_total"):
            return None, "invalid_params"

        for mode, target_count in (("F", fast_num), ("T", slow_num)):
            err = AdminService._validate_pile_reduction(mode, target_count)
            if err:
                return None, err

        err = AdminService._validate_queue_len(queue_len)
        if err:
            return None, err

        for pile in ChargingPileDAO.find_all():
            pile.queue_len = queue_len

        err = AdminService._sync_pile_count("F", fast_num, 30.0, queue_len)
        if err:
            return None, err
        err = AdminService._sync_pile_count("T", slow_num, 10.0, queue_len)
        if err:
            return None, err

        config.SYSTEM_CONFIG["FastChargingPileNum"] = fast_num
        config.SYSTEM_CONFIG["TrickleChargingPileNum"] = slow_num
        config.SYSTEM_CONFIG["WaitingAreaSize"] = waiting_size
        config.SYSTEM_CONFIG["ChargingQueueLen"] = queue_len
        config.FAULT_DISPATCH_STRATEGY = fault_strategy
        config.EXTENDED_DISPATCH_MODE = dispatch_mode
        db.session.flush()

        return {
            "fast_pile_num": fast_num,
            "slow_pile_num": slow_num,
            "waiting_area_size": waiting_size,
            "charging_queue_len": queue_len,
            "fault_strategy": fault_strategy,
            "dispatch_mode": dispatch_mode,
        }, None

    @staticmethod
    def _validate_pile_reduction(mode, target_count):
        piles = ChargingPile.query.filter_by(mode=mode).order_by(ChargingPile.pile_id.asc()).all()
        enabled = [p for p in piles if p.status != "off"]
        if len(enabled) <= target_count:
            return None
        for pile in enabled[target_count:]:
            if PileQueueDAO.get_count_by_pile(pile.pile_id) > 0 or ChargingSessionDAO.find_active_by_pile_id(pile.pile_id):
                return "pile_busy"
        return None

    @staticmethod
    def _validate_queue_len(queue_len):
        for pile in ChargingPileDAO.find_all():
            if pile.status == "off":
                continue
            if PileQueueDAO.get_count_by_pile(pile.pile_id) > queue_len:
                return "queue_len_too_small"
        return None

    @staticmethod
    def _sync_pile_count(mode, target_count, power, queue_len):
        piles = ChargingPile.query.filter_by(mode=mode).order_by(ChargingPile.pile_id.asc()).all()
        enabled = [p for p in piles if p.status != "off"]

        while len(enabled) < target_count:
            off_pile = next((p for p in piles if p.status == "off"), None)
            if off_pile:
                off_pile.status = "available"
                off_pile.power = power
                off_pile.queue_len = queue_len
                enabled.append(off_pile)
            else:
                pile = ChargingPile(mode=mode, power=power, status="available", queue_len=queue_len)
                db.session.add(pile)
                db.session.flush()
                piles.append(pile)
                enabled.append(pile)

        while len(enabled) > target_count:
            pile = enabled[-1]
            if PileQueueDAO.get_count_by_pile(pile.pile_id) > 0 or ChargingSessionDAO.find_active_by_pile_id(pile.pile_id):
                return "pile_busy"
            pile.status = "off"
            enabled.pop()
        return None
