"""
测试 batch_min_total 调度修复：
排序在截断之前 → 小电量优先进入充电区，大电量留在等候区

直接 Mock DAO 调用，不依赖数据库。
"""
import sys
import os
from unittest.mock import patch

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from backend.models.charging_pile import ChargingPile
from backend.models.charging_request import ChargingRequest


def make_pile(pile_id, mode, power, queue_len, status="available"):
    p = ChargingPile()
    p.pile_id = pile_id
    p.mode = mode
    p.power = power
    p.queue_len = queue_len
    p.status = status
    return p


def make_request(request_id, car_id, request_amount, queue_num, status="queuing"):
    r = ChargingRequest()
    r.request_id = request_id
    r.car_id = car_id
    r.request_mode = "F"
    r.request_amount = request_amount
    r.queue_num = queue_num
    r.status = status
    return r


def run_test():
    with (
        # 所有桩的队列都为空 → _completion_time 的 DAO 调用不会被触发
        patch("backend.dao.pile_queue_dao.PileQueueDAO.get_count_by_pile", return_value=0),
        patch("backend.dao.pile_queue_dao.PileQueueDAO.get_by_pile_ordered", return_value=[]),
        patch("backend.dao.pile_dao.ChargingPileDAO.find_by_id", side_effect=_fake_find_pile),
    ):
        from backend.services.dispatch_service import DispatchService

        # ── 准备测试数据 ──────────────────────────
        fast = make_pile(1, "F", 30.0, 2)
        slow = make_pile(2, "T", 10.0, 2)
        piles = [fast, slow]

        # 5 辆车，按到达顺序: V1(60), V2(50), V3(10), V4(5), V5(1)
        amounts = [60, 50, 10, 5, 1]
        requests = [
            make_request(i + 1, f"V{i+1}", a, f"Q{i+1:03d}")
            for i, a in enumerate(amounts)
        ]

        # ── 核心测试：_min_total_assignments ──────────
        assignments = DispatchService._min_total_assignments(
            requests, piles, respect_queue_len=True
        )

        assigned_ids = {req.request_id for req, _ in assignments}
        left_out = [r for r in requests if r.request_id not in assigned_ids]

        print("=" * 60)
        print("batch_min_total 调度修复测试")
        print("=" * 60)
        print(f"输入车辆: {[(r.car_id, f'{r.request_amount}度') for r in requests]}")
        print("充电桩: F(30kW, 2槽)  T(10kW, 2槽)")
        print("总槽位: 4, 车辆数: 5 → 应留 1 辆在等候区")
        print()
        print("分配结果:")
        for req, pile in assignments:
            duration = req.request_amount / pile.power
            print(
                f"  {req.car_id}({req.request_amount}度) → "
                f"{'快充' if pile.mode == 'F' else '慢充'} "
                f"({pile.power}kW), 充电时长={duration:.2f}h"
            )
        print(f"\n留在等候区: {[(r.car_id, f'{r.request_amount}度') for r in left_out]}")
        print()

        # ── 断言 ─────────────────────────────────────
        errors = []

        if len(assignments) == 4:
            print("✅ 1/5: 4 辆车进入充电区")
        else:
            errors.append(f"❌ 1/5: 期望 4 辆进入，实际 {len(assignments)}")

        if 5 in assigned_ids:
            print("✅ 2/5: V5(1度) 进入充电区")
        else:
            errors.append("❌ 2/5: V5(1度) 应进入充电区但被留在等候区")

        if 1 not in assigned_ids:
            print("✅ 3/5: V1(60度) 留在等候区")
        else:
            errors.append("❌ 3/5: V1(60度) 应留在等候区")

        entered_amounts = sorted([req.request_amount for req, _ in assignments])
        if entered_amounts == [1, 5, 10, 50]:
            print("✅ 4/5: 小电量[1,5,10,50]优先进入充电区")
        else:
            errors.append(f"❌ 4/5: 期望进入 [1,5,10,50]，实际 {entered_amounts}")

        fast_vehicles = [req for req, p in assignments if p.mode == "F"]
        slow_vehicles = [req for req, p in assignments if p.mode == "T"]
        fast_amounts = sorted([r.request_amount for r in fast_vehicles])
        slow_amounts = sorted([r.request_amount for r in slow_vehicles])
        print(f"  快充桩: {fast_amounts}度, 慢充桩: {slow_amounts}度")

        if fast_amounts == [10, 50] and slow_amounts == [1, 5]:
            print("✅ 5/5: 大电量→快充，小电量→慢充（总时长最短）")
        else:
            errors.append(
                f"❌ 5/5: 期望快充[10,50]慢充[1,5]，实际快充{fast_amounts}慢充{slow_amounts}"
            )

        print()
        if errors:
            print("=" * 60)
            print(f"❌ {len(errors)} 项失败:")
            for e in errors:
                print(f"  {e}")
            print("=" * 60)
            sys.exit(1)
        else:
            print("=" * 60)
            print("🎉 全部 5 项通过！修复有效。")
            print("=" * 60)


def _fake_find_pile(pile_id):
    if pile_id == 1:
        return make_pile(1, "F", 30.0, 2)
    elif pile_id == 2:
        return make_pile(2, "T", 10.0, 2)
    return None


if __name__ == "__main__":
    run_test()
