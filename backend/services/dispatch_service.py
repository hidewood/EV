"""
调度服务：叫号、最短完成时间调度、故障调度（优先级/时间顺序）、故障恢复。
"""

from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.queue_dao import WaitingQueueDAO
from ..dao.user_dao import ChargingRequestDAO
from ..dao.misc_dao import DispatchRecordDAO
from ..models.dispatch_record import DispatchRecord

_calling_paused = False


def pause_calling():
    global _calling_paused
    _calling_paused = True


def resume_calling():
    global _calling_paused
    _calling_paused = False


class DispatchService:

    # ── 叫号（自动调度） ──────────────────────────────

    @staticmethod
    def trigger_auto_dispatch():
        """扫描所有充电桩，有空位就从共享等候区拉匹配的车入队。"""
        if _calling_paused:
            return False
        for mode in ("F", "T"):
            for pile in ChargingPileDAO.find_by_mode_and_status(mode, ["available", "charging"]):
                if PileQueueDAO.get_count_by_pile(pile.pile_id) < pile.queue_len:
                    entry = WaitingQueueDAO.get_first_by_mode(mode)
                    if entry:
                        req = ChargingRequestDAO.find_by_id(entry.request_id)
                        if req and req.status == "queuing":
                            DispatchService._dispatch_to_best_pile(req, "waiting")
                            return True
        return False

    # ── 核心调度算法 ──────────────────────────────────

    @staticmethod
    def _completion_time(pile_id, request_amount):
        """某请求加入该桩队列后的完成时长 = 队列已有车总时间 + 自身时间。"""
        pile = ChargingPileDAO.find_by_id(pile_id)
        if not pile:
            return float("inf")
        acc = 0.0
        for e in PileQueueDAO.get_by_pile_ordered(pile_id):
            r = ChargingRequestDAO.find_by_id(e.request_id)
            if r:
                acc += r.request_amount / pile.power
        return acc + request_amount / pile.power

    @staticmethod
    def _dispatch_to_best_pile(request, from_location):
        """将请求分配到完成时间最短的同模式可用桩。"""
        mode = request.request_mode
        candidates = [
            p for p in ChargingPileDAO.find_by_mode_and_status(mode, ["available", "charging"])
            if PileQueueDAO.get_count_by_pile(p.pile_id) < p.queue_len
        ]
        if not candidates:
            return None

        best = min(candidates, key=lambda p: DispatchService._completion_time(p.pile_id, request.request_amount))

        pos = PileQueueDAO.get_count_by_pile(best.pile_id) + 1
        PileQueueDAO.add(best.pile_id, request.request_id, pos)

        request.pile_id = best.pile_id
        request.status = "dispatched"
        ChargingRequestDAO.update(request)

        if from_location == "waiting":
            WaitingQueueDAO.remove_by_request_id(request.request_id)

        DispatchRecordDAO.insert(DispatchRecord(
            request_id=request.request_id,
            from_location=from_location,
            to_pile_id=best.pile_id,
            dispatch_type=from_location,
        ))
        return best.pile_id

    # ── 优先级调度（故障） ────────────────────────────

    @staticmethod
    def dispatch_by_priority(fault_pile_id):
        """暂停叫号 → 把故障桩队列中所有未充电的车优先调度到同类型健康桩 → 恢复叫号。"""
        pause_calling()
        try:
            pile = ChargingPileDAO.find_by_id(fault_pile_id)
            if not pile:
                return False
            # 收集故障桩队列中所有车（position=1 充电的已被 _stop_session 清除）
            entries = list(PileQueueDAO.get_by_pile_ordered(fault_pile_id))
            PileQueueDAO.clear_pile(fault_pile_id)
            for e in entries:
                req = ChargingRequestDAO.find_by_id(e.request_id)
                if not req or req.status == "cancelled":
                    continue
                req.status = "pending_reschedule"
                ChargingRequestDAO.update(req)
                DispatchService._dispatch_to_best_pile(req, f"priority_fault_{fault_pile_id}")
            return True
        finally:
            resume_calling()

    # ── 时间顺序调度（故障） ──────────────────────────

    @staticmethod
    def dispatch_by_time_order(fault_pile_id):
        """暂停叫号 → 合并同类型所有桩的未充电车，按排队号重排到健康桩 → 恢复叫号。"""
        pause_calling()
        try:
            pile = ChargingPileDAO.find_by_id(fault_pile_id)
            if not pile:
                return False

            all_uncharged = []
            same_type = [p for p in ChargingPileDAO.find_all() if p.mode == pile.mode]

            # 第一遍：收集所有参与重排的请求
            for p in same_type:
                for e in PileQueueDAO.get_by_pile_ordered(p.pile_id):
                    req = ChargingRequestDAO.find_by_id(e.request_id)
                    if not req or req.status == "cancelled":
                        continue
                    if p.pile_id != fault_pile_id and req.status == "charging":
                        continue
                    all_uncharged.append(req)

            # 第二遍：清除故障桩全队列 + 健康桩中已收集的请求
            for p in same_type:
                if p.pile_id == fault_pile_id:
                    PileQueueDAO.clear_pile(p.pile_id)
                else:
                    for req in all_uncharged:
                        PileQueueDAO.remove_by_request_id(req.request_id)

            all_uncharged.sort(key=lambda r: r.queue_num or "")

            healthy = [p for p in same_type if p.pile_id != fault_pile_id and p.status in ("available", "charging")]
            for req in all_uncharged:
                req.status = "pending_reschedule"
                ChargingRequestDAO.update(req)
                DispatchService._dispatch_to_best_pile(req, f"timeorder_fault_{fault_pile_id}")

            return True
        finally:
            resume_calling()

    # ── 故障恢复调度 ──────────────────────────────────

    @staticmethod
    def dispatch_on_fault_recovery(recovered_pile_id):
        """暂停叫号 → 同类型所有未充电车按排队号重新分配（含恢复桩） → 恢复叫号。"""
        pause_calling()
        try:
            pile = ChargingPileDAO.find_by_id(recovered_pile_id)
            if not pile:
                return False

            all_uncharged = []
            same_type = [p for p in ChargingPileDAO.find_all() if p.mode == pile.mode]

            for p in same_type:
                for e in PileQueueDAO.get_by_pile_ordered(p.pile_id):
                    req = ChargingRequestDAO.find_by_id(e.request_id)
                    if not req or req.status == "cancelled":
                        continue
                    if req.status == "charging":
                        continue  # 正在充电的不参与重排
                    all_uncharged.append(req)
                    PileQueueDAO.remove_by_request_id(req.request_id)

            if not all_uncharged:
                return True

            all_uncharged.sort(key=lambda r: r.queue_num or "")

            available = [p for p in same_type if p.status in ("available", "charging")]
            for req in all_uncharged:
                req.status = "pending_reschedule"
                ChargingRequestDAO.update(req)
                DispatchService._dispatch_to_best_pile(req, f"recovery_{recovered_pile_id}")

            return True
        finally:
            resume_calling()
