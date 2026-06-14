from ..dao.queue_dao import WaitingQueueDAO
from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..models.waiting_queue import WaitingQueue
from ..utils.timezone import local_now


class QueueService:
    @staticmethod
    def generate_queue_num(mode):
        max_num = WaitingQueueDAO.get_max_queue_num(mode)
        return f"{mode}{max_num + 1}"

    @staticmethod
    def add_to_waiting(request_id, mode):
        from ..dao.user_dao import ChargingRequestDAO
        queue_num = f"{mode}{ChargingRequestDAO.get_max_queue_num_by_mode(mode) + 1}"
        WaitingQueueDAO.add(request_id, mode, queue_num)
        return queue_num

    @staticmethod
    def waiting_area_has_slot():
        from ..config import SYSTEM_CONFIG
        return WaitingQueueDAO.get_total_count() < SYSTEM_CONFIG["WaitingAreaSize"]

    @staticmethod
    def waiting_area_count():
        return WaitingQueueDAO.get_total_count()

    @staticmethod
    def remove_from_waiting(request_id):
        WaitingQueueDAO.remove_by_request_id(request_id)

    @staticmethod
    def pile_ahead_count(car_request):
        if car_request.status == "charging":
            return 0
        pile_id = car_request.pile_id
        if not pile_id:
            return 0

        entry = PileQueueDAO.find_by_request_id(car_request.request_id)
        if entry and entry.pile_id == pile_id:
            return max(0, entry.position - 1)

        from ..dao.user_dao import ChargingSessionDAO
        active = ChargingSessionDAO.find_active_by_pile_id(pile_id)
        if active and active.request_id != car_request.request_id:
            return 1
        return PileQueueDAO.get_count_by_pile(pile_id)

    @staticmethod
    def get_car_position(car_request):
        if car_request.status in ("dispatched", "charging", "pending_reschedule"):
            ahead_count = QueueService.pile_ahead_count(car_request)
            return {
                "position": "充电区",
                "queue_num": car_request.queue_num,
                "pile_id": car_request.pile_id,
                "ahead_count": ahead_count,
                "front_count": ahead_count,
            }
        front_count = WaitingQueueDAO.get_front_count(car_request.request_id)
        return {
            "position": f"等候区第{front_count + 1}位",
            "queue_num": car_request.queue_num,
            "front_count": front_count,
            "ahead_count": front_count,
        }

    @staticmethod
    def has_empty_slot_in_pile(pile_id):
        count = PileQueueDAO.get_count_by_pile(pile_id)
        pile = ChargingPileDAO.find_by_id(pile_id)
        return pile and count < pile.queue_len

    @staticmethod
    def get_next_from_waiting(mode):
        return WaitingQueueDAO.get_first_by_mode(mode)

    @staticmethod
    def get_waiting_queue_list(mode):
        entries = WaitingQueueDAO.get_all_by_mode(mode)
        from ..dao.user_dao import ChargingRequestDAO, UserDAO

        result = []
        for e in entries:
            req = ChargingRequestDAO.find_by_id(e.request_id)
            if not req:
                continue
            user = UserDAO.find_by_car_id(req.car_id)
            result.append({
                "request_id": req.request_id,
                "car_id": req.car_id,
                "queue_num": e.queue_num,
                "request_amount": req.request_amount,
                "car_capacity": user.car_capacity if user else 0,
                "wait_minutes": round((local_now() - e.join_time).total_seconds() / 60, 1),
            })
        return result
