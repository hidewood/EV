from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.user_dao import ChargingRequestDAO, UserDAO
from ..dao.misc_dao import PricingRuleDAO, FaultRecordDAO, DispatchRecordDAO
from ..services.dispatch_service import DispatchService
from ..models.dispatch_record import DispatchRecord
from ..utils.timezone import local_now


class PileService:
    @staticmethod
    def power_on(pile_id):
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None, "pile_not_found"
        if pile.status != "off":
            return None, "status_not_off"
        pile.status = "standby"
        ChargingPileDAO.update(pile)
        return pile, None

    @staticmethod
    def start_charging_pile(pile_id):
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None, "pile_not_found"
        if pile.status != "standby":
            return None, "status_not_standby"
        pile.status = "available"
        ChargingPileDAO.update(pile)
        DispatchService.trigger_auto_dispatch()
        return pile, None

    @staticmethod
    def power_off(pile_id):
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None, "pile_not_found"
        if pile.status == "off":
            return None, "already_off"

        from ..dao.user_dao import ChargingSessionDAO
        active = ChargingSessionDAO.find_active_by_pile_id(pile_id)
        if active:
            return None, "has_active_session"
        if PileQueueDAO.get_count_by_pile(pile_id) > 0:
            return None, "has_queued_vehicle"

        pile.status = "off"
        ChargingPileDAO.update(pile)
        DispatchService.trigger_auto_dispatch()
        return pile, None

    @staticmethod
    def query_all_piles():
        piles = ChargingPileDAO.find_all()
        result = []
        for p in piles:
            count = PileQueueDAO.get_count_by_pile(p.pile_id)
            first = PileQueueDAO.get_first(p.pile_id)
            current_car = None
            if first:
                req = ChargingRequestDAO.find_by_id(first.request_id)
                if req:
                    current_car = req.car_id
            result.append({
                "pile_id": p.pile_id,
                "mode": p.mode,
                "mode_label": "快充" if p.mode == "F" else "慢充",
                "power": p.power,
                "status": p.status,
                "queue_used": count,
                "queue_total": p.queue_len,
                "current_car": current_car,
                "total_charge_num": p.total_charge_num,
                "total_charge_time": round(p.total_charge_time, 2),
                "total_charge_capacity": round(p.total_charge_capacity, 2),
            })
        return result

    @staticmethod
    def query_pile_detail(pile_id):
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return None

        entries = PileQueueDAO.get_by_pile_ordered(pile_id)
        vehicles = []
        for e in entries:
            req = ChargingRequestDAO.find_by_id(e.request_id)
            if not req:
                continue
            user = UserDAO.find_by_car_id(req.car_id)
            vehicles.append({
                "request_id": req.request_id,
                "car_id": req.car_id,
                "car_capacity": user.car_capacity if user else 0,
                "request_amount": req.request_amount,
                "position": e.position,
                "status": req.status,
                "queue_num": req.queue_num,
                "wait_minutes": round((local_now() - e.enter_time).total_seconds() / 60, 1),
            })

        return {
            "pile_id": pile.pile_id,
            "mode": pile.mode,
            "power": pile.power,
            "status": pile.status,
            "queue_len": pile.queue_len,
            "total_charge_num": pile.total_charge_num,
            "total_charge_time": pile.total_charge_time,
            "total_charge_capacity": pile.total_charge_capacity,
            "vehicles": vehicles,
        }

    @staticmethod
    def set_parameters(mode, peak, mid, off_peak, service_rate):
        return None, "fixed_pricing"
