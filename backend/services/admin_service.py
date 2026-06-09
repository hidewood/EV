from ..dao.user_dao import ChargingSessionDAO, BillDAO
from ..dao.pile_dao import ChargingPileDAO
from ..dao.misc_dao import FaultRecordDAO, PricingRuleDAO
from datetime import datetime, timedelta


class AdminService:
    @staticmethod
    def get_report(period="day", date_str=None):
        """按日/周/月生成报表。"""
        now = datetime.utcnow()
        if not date_str:
            date_str = now.strftime("%Y-%m-%d")

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

        piles = ChargingPileDAO.find_all()
        result = []
        for p in piles:
            sessions = ChargingSessionDAO.find_completed_by_pile_and_time(
                p.pile_id, start, end
            )
            total_amount = sum(s.charge_amount for s in sessions)
            total_time = sum(
                (s.end_time - s.start_time).total_seconds() / 3600
                for s in sessions
                if s.end_time and s.start_time
            )

            from ..dao.user_dao import ChargingDetailDAO
            total_charge_fee = 0.0
            total_service_fee = 0.0
            for s in sessions:
                detail = ChargingDetailDAO.find_by_bill_id(s.session_id)
                # simplified lookup; use session to find detail would need a join
            # Simplified: query charging_detail for these sessions
            from ..models.charging_detail import ChargingDetail
            details = (
                ChargingDetail.query
                .filter(ChargingDetail.pile_id == p.pile_id)
                .filter(ChargingDetail.created_at >= start, ChargingDetail.created_at <= end)
                .all()
            )
            total_charge_fee = sum(d.charge_fee for d in details)
            total_service_fee = sum(d.service_fee for d in details)

            result.append({
                "pile_id": p.pile_id,
                "mode": "快充" if p.mode == "F" else "慢充",
                "charge_count": len(sessions),
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
        return {
            "capacity": 10,
            "fast_waiting": WaitingQueueDAO.get_count_by_mode("F"),
            "slow_waiting": WaitingQueueDAO.get_count_by_mode("T"),
        }
