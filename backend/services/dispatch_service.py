"""
调度服务：叫号、最短完成时间调度、故障调度（优先级/时间顺序）、故障恢复。
"""

from ..dao.pile_dao import ChargingPileDAO
from ..dao.pile_queue_dao import PileQueueDAO
from ..dao.queue_dao import WaitingQueueDAO
from ..dao.user_dao import ChargingRequestDAO, ChargingSessionDAO
from ..dao.misc_dao import DispatchRecordDAO
from ..models.dispatch_record import DispatchRecord
from .. import config
from ..utils.timezone import local_now

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
        pending_dispatched = DispatchService.dispatch_pending_reschedules()
        if DispatchService.has_pending_reschedules():
            return pending_dispatched
        if config.EXTENDED_DISPATCH_MODE == "single_min_total":
            return DispatchService.dispatch_single_min_total()
        if config.EXTENDED_DISPATCH_MODE == "batch_min_total":
            return DispatchService.dispatch_batch_min_total_if_ready()
        return DispatchService.dispatch_normal()

    @staticmethod
    def dispatch_normal():
        """普通叫号：每次从同模式等候区队首调度到完成时间最短的桩。"""
        dispatched = False
        changed = True
        while changed:
            changed = False
            for mode in ("F", "T"):
                for pile in ChargingPileDAO.find_by_mode_and_status(mode, ["available", "charging"]):
                    if PileQueueDAO.get_count_by_pile(pile.pile_id) < pile.queue_len:
                        entry = WaitingQueueDAO.get_first_by_mode(mode)
                        if entry:
                            req = ChargingRequestDAO.find_by_id(entry.request_id)
                            if req and req.status == "queuing":
                                DispatchService._dispatch_to_best_pile(req, "waiting")
                                dispatched = True
                                changed = True
                                break
                if changed:
                    break
        return dispatched

    @staticmethod
    def dispatch_single_min_total():
        """扩展 8a：同模式多空位同时叫号，最小化本次进入充电区车辆的总完成时长。"""
        dispatched = False
        for mode in ("F", "T"):
            piles = DispatchService._online_piles(mode=mode)
            slot_count = DispatchService._free_slot_count(piles)
            if slot_count <= 0:
                continue
            entries = WaitingQueueDAO.get_all_by_mode(mode)[:slot_count]
            requests = [
                ChargingRequestDAO.find_by_id(e.request_id)
                for e in entries
            ]
            requests = [r for r in requests if r and r.status == "queuing"]
            if not requests:
                continue
            assignments = DispatchService._min_total_assignments(requests, piles)
            DispatchService._apply_assignments(assignments, "single_min_total")
            dispatched = dispatched or bool(assignments)
        return dispatched

    @staticmethod
    def dispatch_batch_min_total_if_ready():
        """扩展 8b：全站车位满后，忽略快/慢充偏好，做批量最短总完成时长调度。"""
        if DispatchService._occupied_pile_slots() > 0:
            return False

        capacity = DispatchService.station_capacity()
        if WaitingQueueDAO.get_total_count() < capacity:
            return False

        requests = []
        for mode in ("F", "T"):
            for entry in WaitingQueueDAO.get_all_by_mode(mode):
                req = ChargingRequestDAO.find_by_id(entry.request_id)
                if req and req.status == "queuing":
                    requests.append(req)
        requests.sort(key=lambda r: DispatchService._queue_num_key(r.queue_num))
        requests = requests[:capacity]
        piles = DispatchService._online_piles()
        assignments = DispatchService._min_total_assignments(requests, piles, respect_queue_len=False)
        DispatchService._apply_assignments(assignments, "batch_min_total")
        return bool(assignments)

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
                amount = r.request_amount
                if r.status == "charging":
                    session = ChargingSessionDAO.find_active_by_car_id(r.car_id)
                    if session:
                        elapsed_hours = max((local_now() - session.start_time).total_seconds() / 3600, 0)
                        amount = max(r.request_amount - elapsed_hours * pile.power, 0)
                acc += amount / pile.power
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

    @staticmethod
    def station_capacity():
        return config.SYSTEM_CONFIG["WaitingAreaSize"] + sum(
            p.queue_len for p in DispatchService._online_piles()
        )

    @staticmethod
    def _online_piles(mode=None):
        piles = [
            p for p in ChargingPileDAO.find_all()
            if p.status in ("available", "charging")
        ]
        if mode:
            piles = [p for p in piles if p.mode == mode]
        return piles

    @staticmethod
    def _free_slot_count(piles):
        return sum(max(p.queue_len - PileQueueDAO.get_count_by_pile(p.pile_id), 0) for p in piles)

    @staticmethod
    def _occupied_pile_slots():
        return sum(PileQueueDAO.get_count_by_pile(p.pile_id) for p in ChargingPileDAO.find_all())

    @staticmethod
    def _current_load_hours(pile):
        return DispatchService._completion_time(pile.pile_id, 0)

    @staticmethod
    def _min_total_assignments(requests, piles, respect_queue_len=True):
        """返回 [(request, pile), ...]，目标是本批车辆完成时间之和最小。"""
        if respect_queue_len:
            piles = [
                p for p in piles
                if p.status in ("available", "charging") and PileQueueDAO.get_count_by_pile(p.pile_id) < p.queue_len
            ]
        else:
            piles = [p for p in piles if p.status in ("available", "charging")]
        if not requests or not piles:
            return []

        loads = {p.pile_id: DispatchService._current_load_hours(p) for p in piles}
        slots = {
            p.pile_id: (
                p.queue_len - PileQueueDAO.get_count_by_pile(p.pile_id)
                if respect_queue_len else len(requests)
            )
            for p in piles
        }
        pile_by_id = {p.pile_id: p for p in piles}
        requests = sorted(requests, key=lambda r: (r.request_amount, DispatchService._queue_num_key(r.queue_num)))

        if len(requests) <= 10:
            best = {"cost": float("inf"), "pairs": []}

            def search(idx, cur_loads, cur_slots, pairs, cost):
                if cost >= best["cost"]:
                    return
                if idx >= len(requests):
                    best["cost"] = cost
                    best["pairs"] = pairs[:]
                    return

                req = requests[idx]
                for pile in piles:
                    if cur_slots[pile.pile_id] <= 0:
                        continue
                    duration = req.request_amount / pile.power
                    completion = cur_loads[pile.pile_id] + duration
                    next_loads = dict(cur_loads)
                    next_slots = dict(cur_slots)
                    next_loads[pile.pile_id] = completion
                    next_slots[pile.pile_id] -= 1
                    search(idx + 1, next_loads, next_slots, pairs + [(req, pile)], cost + completion)

            search(0, loads, slots, [], 0.0)
            return best["pairs"]

        pairs = []
        for req in requests:
            candidates = [p for p in piles if slots[p.pile_id] > 0]
            if not candidates:
                break
            best_pile = min(candidates, key=lambda p: loads[p.pile_id] + req.request_amount / p.power)
            loads[best_pile.pile_id] += req.request_amount / best_pile.power
            slots[best_pile.pile_id] -= 1
            pairs.append((req, pile_by_id[best_pile.pile_id]))
        return pairs

    @staticmethod
    def _apply_assignments(assignments, dispatch_type):
        for req, pile in assignments:
            if not req or not pile:
                continue
            pos = PileQueueDAO.get_count_by_pile(pile.pile_id) + 1
            PileQueueDAO.add(pile.pile_id, req.request_id, pos)
            req.pile_id = pile.pile_id
            req.status = "dispatched"
            ChargingRequestDAO.update(req)
            WaitingQueueDAO.remove_by_request_id(req.request_id)
            DispatchRecordDAO.insert(DispatchRecord(
                request_id=req.request_id,
                from_location="waiting",
                to_pile_id=pile.pile_id,
                dispatch_type=dispatch_type,
            ))

    @staticmethod
    def has_pending_reschedules():
        return bool(ChargingRequestDAO.find_by_status(["pending_reschedule"]))

    @staticmethod
    def dispatch_pending_reschedules():
        """故障/恢复重调度残留车辆优先于等候区叫号。"""
        dispatched = False
        changed = True
        while changed:
            changed = False
            pending = sorted(
                ChargingRequestDAO.find_by_status(["pending_reschedule"]),
                key=lambda r: DispatchService._queue_num_key(r.queue_num),
            )
            for req in pending:
                pile_id = DispatchService._dispatch_to_best_pile(req, "pending_reschedule_fault")
                if pile_id:
                    dispatched = True
                    changed = True
                    break
        return dispatched

    @staticmethod
    def _mark_pending_reschedule(req):
        req.status = "pending_reschedule"
        req.pile_id = None
        ChargingRequestDAO.update(req)

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
                DispatchService._mark_pending_reschedule(req)
            DispatchService.dispatch_pending_reschedules()
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

            all_uncharged.sort(key=lambda r: DispatchService._queue_num_key(r.queue_num))

            for req in all_uncharged:
                DispatchService._mark_pending_reschedule(req)
            DispatchService.dispatch_pending_reschedules()

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

            all_uncharged.sort(key=lambda r: DispatchService._queue_num_key(r.queue_num))

            for req in all_uncharged:
                DispatchService._mark_pending_reschedule(req)
            DispatchService.dispatch_pending_reschedules()

            return True
        finally:
            resume_calling()

    @staticmethod
    def _queue_num_key(queue_num):
        if not queue_num:
            return ("", 0)
        try:
            return (queue_num[0], int(queue_num[1:]))
        except ValueError:
            return (queue_num[0], 0)
