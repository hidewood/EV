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
