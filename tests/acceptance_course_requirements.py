"""
课程需求验收脚本：智能充电桩调度计费系统

运行方式：
    .\\venv\\Scripts\\python.exe tests\\acceptance_course_requirements.py

说明：
    1. 使用 sqlite:///:memory: 临时数据库，不会污染 MySQL 演示库。
    2. 按课程需求 1~8 分组输出 PASS/FAIL。
    3. 失败时会打印失败原因，便于定位问题。
"""

import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["ADMIN_REGISTER_CODE"] = "acceptance-admin-code"

from backend import app as backend_app  # noqa: E402

backend_app.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class AcceptanceRunner:
    def __init__(self):
        self.app = backend_app.create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.results = []

    # ---------- basic helpers ----------

    def check(self, requirement, name, condition, detail=""):
        self.results.append({
            "requirement": requirement,
            "name": name,
            "ok": bool(condition),
            "detail": detail,
        })

    def run_case(self, requirement, name, fn):
        try:
            fn()
        except Exception as exc:  # keep running other cases after one failure
            self.check(requirement, name, False, f"{exc}\n{traceback.format_exc()}")

    def post(self, path, data=None, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(path, json=data or {}, headers=headers).get_json()

    def put(self, path, data=None, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.put(path, json=data or {}, headers=headers).get_json()

    def delete(self, path, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(path, headers=headers).get_json()

    def get(self, path, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(path, headers=headers).get_json()

    def reset_db(
        self,
        *,
        fast_num=2,
        slow_num=3,
        waiting_size=10,
        queue_len=2,
        fault_strategy="priority",
        dispatch_mode="normal",
        fast_power=30.0,
        slow_power=10.0,
    ):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.models.pricing_rule import PricingRule
            from backend.config import DEFAULT_PRICING
            from backend.services.dispatch_service import resume_calling
            import backend.config as config

            resume_calling()
            config.SYSTEM_CONFIG["FastChargingPileNum"] = fast_num
            config.SYSTEM_CONFIG["TrickleChargingPileNum"] = slow_num
            config.SYSTEM_CONFIG["WaitingAreaSize"] = waiting_size
            config.SYSTEM_CONFIG["ChargingQueueLen"] = queue_len
            config.FAULT_DISPATCH_STRATEGY = fault_strategy
            config.EXTENDED_DISPATCH_MODE = dispatch_mode

            db.session.remove()
            db.drop_all()
            db.create_all()

            for pricing in DEFAULT_PRICING:
                db.session.add(PricingRule(**pricing))

            pile_id = 1
            for _ in range(fast_num):
                db.session.add(ChargingPile(
                    pile_id=pile_id,
                    mode="F",
                    power=fast_power,
                    status="available",
                    queue_len=queue_len,
                ))
                pile_id += 1
            for _ in range(slow_num):
                db.session.add(ChargingPile(
                    pile_id=pile_id,
                    mode="T",
                    power=slow_power,
                    status="available",
                    queue_len=queue_len,
                ))
                pile_id += 1
            db.session.commit()

    def register_user(self, car_id, *, role="user", capacity=60.0):
        payload = {
            "car_id": car_id,
            "user_name": car_id,
            "car_capacity": capacity,
            "password": "pw",
            "role": role,
        }
        if role == "admin":
            payload["admin_code"] = "acceptance-admin-code"
        return self.post("/api/auth/register", payload)

    def login(self, car_id):
        resp = self.post("/api/auth/login", {"car_id": car_id, "password": "pw"})
        if resp["code"] != 0:
            raise AssertionError(f"login failed for {car_id}: {resp}")
        return resp["data"]["access_token"]

    def register_and_login(self, car_id, *, role="user", capacity=60.0):
        reg = self.register_user(car_id, role=role, capacity=capacity)
        if reg["code"] != 0:
            raise AssertionError(f"register failed for {car_id}: {reg}")
        return self.login(car_id)

    def set_active_session_start(self, car_id, start_time):
        with self.app.app_context():
            from backend.models import db
            from backend.dao.user_dao import ChargingSessionDAO

            session = ChargingSessionDAO.find_active_by_car_id(car_id)
            if not session:
                raise AssertionError(f"no active session for {car_id}")
            session.start_time = start_time
            db.session.commit()

    # ---------- requirement cases ----------

    def case_req1_queue_numbers_and_waiting_capacity(self):
        self.reset_db(fast_num=1, slow_num=1, waiting_size=10, queue_len=2)
        f1 = self.register_and_login("R1_F1")
        f2 = self.register_and_login("R1_F2")
        t1 = self.register_and_login("R1_T1")

        resp_f1 = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, f1)
        resp_f2 = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, f2)
        resp_t1 = self.post("/api/charging/request", {"request_mode": "T", "request_amount": 10}, t1)
        self.check("需求1", "快充/慢充排队号分别从 F1/T1 开始递增",
                   resp_f1["data"]["queue_num"] == "F1"
                   and resp_f2["data"]["queue_num"] == "F2"
                   and resp_t1["data"]["queue_num"] == "T1",
                   f"{resp_f1}, {resp_f2}, {resp_t1}")

        self.reset_db(fast_num=1, slow_num=1, waiting_size=1, queue_len=1)
        a = self.register_and_login("R1_CAP_A")
        b = self.register_and_login("R1_CAP_B")
        c = self.register_and_login("R1_CAP_C")
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, a)
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, b)
        full = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, c)
        self.check("需求1", "等候区满且同模式桩无空位时拒绝新请求",
                   full["code"] == 3005, str(full))

    def case_req2_pile_config_and_queue_head(self):
        self.reset_db(fast_num=2, slow_num=3, waiting_size=10, queue_len=2)
        admin = self.register_and_login("R2_ADMIN", role="admin", capacity=1)
        piles = self.get("/api/pile/status", admin)
        fast = [p for p in piles["data"] if p["mode"] == "F"]
        slow = [p for p in piles["data"] if p["mode"] == "T"]
        self.check("需求2", "默认 2 个快充桩、3 个慢充桩，功率和队列长度正确",
                   piles["code"] == 0
                   and len(fast) == 2
                   and len(slow) == 3
                   and all(p["power"] == 30.0 and p["queue_total"] == 2 for p in fast)
                   and all(p["power"] == 10.0 and p["queue_total"] == 2 for p in slow),
                   str(piles))

        self.reset_db(fast_num=1, slow_num=1, waiting_size=10, queue_len=2)
        u1 = self.register_and_login("R2_HEAD_A")
        u2 = self.register_and_login("R2_HEAD_B")
        r1 = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, u1)
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, u2)
        second_start = self.post("/api/charging/start", {"pile_id": r1["data"]["pile_id"]}, u2)
        first_start = self.post("/api/charging/start", {"pile_id": r1["data"]["pile_id"]}, u1)
        self.check("需求2", "桩队列第一辆车才能开始充电",
                   second_start["code"] == 3003 and first_start["code"] == 0,
                   f"second={second_start}, first={first_start}")

    def case_req3_shortest_completion_dispatch(self):
        self.reset_db(fast_num=2, slow_num=1, waiting_size=10, queue_len=3)
        u1 = self.register_and_login("R3_A")
        u2 = self.register_and_login("R3_B")
        u3 = self.register_and_login("R3_C")

        first = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 30}, u1)
        self.post("/api/charging/start", {"pile_id": first["data"]["pile_id"]}, u1)
        self.set_active_session_start("R3_A", datetime.now() - timedelta(minutes=59))

        second = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 2}, u2)
        third = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 1}, u3)
        self.check("需求3", "调度按等待时间+自身充电时间最短选择同模式充电桩",
                   second["data"]["pile_id"] == 2 and third["data"]["pile_id"] == 1,
                   f"second={second}, third={third}")

    def case_req4_pricing(self):
        from backend.models.pricing_rule import PricingRule
        from backend.utils.pricing import calculate_charge_fee, calculate_service_fee

        pricing = PricingRule(
            mode="F",
            peak_price=1.0,
            mid_price=0.7,
            off_peak_price=0.4,
            service_fee_rate=0.8,
        )
        mid_to_peak = calculate_charge_fee(30, 30, datetime(2026, 6, 13, 9, 30, 0), pricing)
        mid_to_off = calculate_charge_fee(30, 30, datetime(2026, 6, 13, 22, 30, 0), pricing)
        service = calculate_service_fee(30, pricing)
        duration = 30 / 30
        self.check("需求4", "峰/平/谷跨时段充电费、服务费、充电时长计算正确",
                   mid_to_peak == 25.5 and mid_to_off == 16.5 and service == 24.0 and duration == 1.0,
                   f"mid_to_peak={mid_to_peak}, mid_to_off={mid_to_off}, service={service}")

    def case_req5_user_admin_detail_report(self):
        self.reset_db(fast_num=2, slow_num=1, waiting_size=10, queue_len=2)
        admin = self.register_and_login("R5_ADMIN", role="admin", capacity=1)
        user = self.register_and_login("R5_USER")

        req = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 30}, user)
        self.post("/api/charging/start", {"pile_id": req["data"]["pile_id"]}, user)
        self.set_active_session_start("R5_USER", datetime.now() - timedelta(hours=1))
        end = self.post("/api/charging/end", {}, user)
        bills = self.get("/api/bill/list", user)
        detail = self.get(f"/api/bill/detail/{bills['data'][0]['bill_id']}", user)
        detail_keys = {
            "detail_id", "created_at", "pile_id", "charge_amount", "charge_duration",
            "start_time", "stop_time", "charge_fee", "service_fee", "total_fee",
        }
        self.check("需求5", "用户端可注册登录、结束充电并查看字段完整的详单",
                   end["code"] == 0 and bills["code"] == 0 and detail_keys.issubset(detail["data"].keys()),
                   f"end={end}, bills={bills}, detail={detail}")

        queued_user = self.register_and_login("R5_QUEUE")
        queued_req = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 12}, queued_user)
        pile_queue = self.get(f"/api/queue/pile/{queued_req['data']['pile_id']}", admin)
        pile_status = self.get("/api/pile/status", admin)
        report = self.get("/api/admin/report/stats?period=day", admin)
        vehicle_keys = {"car_id", "car_capacity", "request_amount", "wait_minutes"}
        report_keys = {
            "pile_id", "charge_count", "charge_time", "charge_amount",
            "charge_fee", "service_fee", "total_fee",
        }
        self.check("需求5", "管理员端可查看桩状态、桩队列车辆字段、日统计报表",
                   pile_status["code"] == 0
                   and pile_queue["code"] == 0
                   and pile_queue["data"]
                   and vehicle_keys.issubset(pile_queue["data"][0].keys())
                   and report["code"] == 0
                   and report["data"]["piles"]
                   and report_keys.issubset(report["data"]["piles"][0].keys()),
                   f"pile_status={pile_status}, pile_queue={pile_queue}, report={report}")

    def case_req6_modify_cancel_rules(self):
        self.reset_db(fast_num=1, slow_num=1, waiting_size=2, queue_len=1)
        a = self.register_and_login("R6_A")
        b = self.register_and_login("R6_B")
        c = self.register_and_login("R6_C")

        first = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, a)
        second = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 20}, b)
        old_queue_num = second["data"]["queue_num"]
        amount = self.put("/api/charging/amount", {"amount": 25}, b)
        after_amount = self.get("/api/charging/queue-status", b)
        self.check("需求6", "等候区允许修改请求充电量且排队号不变",
                   amount["code"] == 0
                   and after_amount["data"]["request_amount"] == 25
                   and after_amount["data"]["queue_num"] == old_queue_num,
                   f"amount={amount}, state={after_amount}")

        mode = self.put("/api/charging/mode", {"mode": "T"}, b)
        after_mode = self.get("/api/charging/queue-status", b)
        self.check("需求6", "等候区允许修改充电模式并重新生成对应模式排队号",
                   mode["code"] == 0 and after_mode["data"]["queue_num"].startswith("T"),
                   f"mode={mode}, state={after_mode}")

        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, c)
        self.post("/api/charging/start", {"pile_id": first["data"]["pile_id"]}, a)
        not_allowed_amount = self.put("/api/charging/amount", {"amount": 15}, a)
        not_allowed_mode = self.put("/api/charging/mode", {"mode": "T"}, a)
        self.check("需求6", "充电区不允许修改模式或电量",
                   not_allowed_amount["code"] == 3003 and not_allowed_mode["code"] == 3003,
                   f"amount={not_allowed_amount}, mode={not_allowed_mode}")

        cancel_waiting = self.delete("/api/charging/cancel", c)
        self.set_active_session_start("R6_A", datetime.now() - timedelta(minutes=10))
        cancel_charging = self.delete("/api/charging/cancel", a)
        self.check("需求6", "等候区和充电区均允许取消，充电区取消生成详单",
                   cancel_waiting["code"] == 0
                   and cancel_waiting["data"]["detail_generated"] is False
                   and cancel_charging["code"] == 0
                   and cancel_charging["data"]["detail_generated"] is True,
                   f"waiting={cancel_waiting}, charging={cancel_charging}")

    def case_req7_fault_dispatch_and_recovery(self):
        self.reset_db(fast_num=2, slow_num=1, waiting_size=10, queue_len=1, fault_strategy="priority")
        admin = self.register_and_login("R7_ADMIN", role="admin", capacity=1)
        u1 = self.register_and_login("R7_P_A")
        u2 = self.register_and_login("R7_P_B")
        u3 = self.register_and_login("R7_P_C")
        r1 = self.post("/api/charging/request", {"request_mode": "F", "request_amount": 30}, u1)
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 30}, u2)
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 30}, u3)
        self.post("/api/charging/start", {"pile_id": r1["data"]["pile_id"]}, u1)
        self.set_active_session_start("R7_P_A", datetime.now() - timedelta(minutes=30))
        fault = self.post("/api/admin/fault/report", {"pile_id": r1["data"]["pile_id"]}, admin)
        bills = self.get("/api/bill/list", u1)

        with self.app.app_context():
            from backend.dao.user_dao import ChargingRequestDAO

            u1_req = ChargingRequestDAO.find_active_by_car_id("R7_P_A")
            u3_req = ChargingRequestDAO.find_active_by_car_id("R7_P_C")
            priority_ok = (
                fault["code"] == 0
                and bills["code"] == 0
                and len(bills["data"]) >= 1
                and u1_req is not None
                and u1_req.status == "pending_reschedule"
                and u3_req is not None
                and u3_req.status == "queuing"
            )
        self.check("需求7a", "故障后正在充电车辆停止计费生成详单，优先级调度暂停等候区叫号",
                   priority_ok, f"fault={fault}, bills={bills}")

        self.reset_db(fast_num=2, slow_num=1, waiting_size=10, queue_len=3, fault_strategy="time_order")
        admin = self.register_and_login("R7_T_ADMIN", role="admin", capacity=1)
        tokens = [self.register_and_login(f"R7_T_{idx}") for idx in range(1, 4)]
        for token in tokens:
            self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, token)
        time_fault = self.post("/api/admin/fault/report", {"pile_id": 1}, admin)
        with self.app.app_context():
            from backend.dao.pile_queue_dao import PileQueueDAO
            from backend.dao.user_dao import ChargingRequestDAO

            queue_nums = []
            for entry in PileQueueDAO.get_by_pile_ordered(2):
                req = ChargingRequestDAO.find_by_id(entry.request_id)
                queue_nums.append(req.queue_num)
        self.check("需求7b", "时间顺序调度按排队号重排故障队列和其它未充电车辆",
                   time_fault["code"] == 0 and queue_nums == sorted(queue_nums, key=lambda q: (q[0], int(q[1:]))),
                   f"queue_nums={queue_nums}, fault={time_fault}")

        self.reset_db(fast_num=2, slow_num=1, waiting_size=10, queue_len=2)
        admin = self.register_and_login("R7_R_ADMIN", role="admin", capacity=1)
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile

            pile1 = db.session.get(ChargingPile, 1)
            pile1.status = "fault"
            db.session.commit()
        r_tokens = [self.register_and_login(f"R7_R_{idx}") for idx in range(1, 3)]
        for token in r_tokens:
            self.post("/api/charging/request", {"request_mode": "F", "request_amount": 10}, token)
        recover = self.post("/api/admin/fault/recover", {"pile_id": 1}, admin)
        with self.app.app_context():
            from backend.dao.pile_queue_dao import PileQueueDAO

            count_pile1 = PileQueueDAO.get_count_by_pile(1)
            count_pile2 = PileQueueDAO.get_count_by_pile(2)
        self.check("需求7c", "故障恢复后同类型未充电车辆重新调度并包含恢复桩",
                   recover["code"] == 0 and count_pile1 + count_pile2 == 2 and count_pile1 >= 1,
                   f"recover={recover}, counts=({count_pile1}, {count_pile2})")

    def case_req8_extended_dispatch(self):
        self.reset_db(fast_num=2, slow_num=1, waiting_size=10, queue_len=1, dispatch_mode="single_min_total")
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.services.dispatch_service import pause_calling, resume_calling

            db.session.get(ChargingPile, 1).power = 30.0
            db.session.get(ChargingPile, 2).power = 60.0
            db.session.commit()
            pause_calling()
        big = self.register_and_login("R8_SINGLE_BIG")
        small = self.register_and_login("R8_SINGLE_SMALL")
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 60}, big)
        self.post("/api/charging/request", {"request_mode": "F", "request_amount": 1}, small)
        with self.app.app_context():
            from backend.services.dispatch_service import DispatchService, resume_calling
            from backend.dao.user_dao import ChargingRequestDAO

            resume_calling()
            DispatchService.trigger_auto_dispatch()
            big_req = ChargingRequestDAO.find_active_by_car_id("R8_SINGLE_BIG")
            small_req = ChargingRequestDAO.find_active_by_car_id("R8_SINGLE_SMALL")
        self.check("需求8a", "单次调度在多空位时按同模式总完成时长最短分配",
                   big_req.pile_id == 2 and small_req.pile_id == 1,
                   f"big={big_req.pile_id}, small={small_req.pile_id}")

        self.reset_db(fast_num=1, slow_num=1, waiting_size=1, queue_len=1, dispatch_mode="batch_min_total")
        tokens = [self.register_and_login(f"R8_BATCH_{idx}") for idx in range(1, 4)]
        for token in tokens:
            self.post("/api/charging/request", {"request_mode": "T", "request_amount": 30}, token)
        with self.app.app_context():
            from backend.dao.user_dao import ChargingRequestDAO
            from backend.dao.pile_queue_dao import PileQueueDAO

            reqs = [ChargingRequestDAO.find_active_by_car_id(f"R8_BATCH_{idx}") for idx in range(1, 4)]
            dispatched = [r for r in reqs if r.status == "dispatched"]
            queuing = [r for r in reqs if r.status == "queuing"]
            fast_pile_has_t_request = any(r.pile_id == 1 and r.request_mode == "T" for r in dispatched)
            pile1_count = PileQueueDAO.get_count_by_pile(1)
            pile2_count = PileQueueDAO.get_count_by_pile(2)
        self.check("需求8b", "批量调度满站触发、忽略快慢充模式且不超过每桩 M",
                   len(dispatched) == 2
                   and len(queuing) == 1
                   and fast_pile_has_t_request
                   and pile1_count <= 1
                   and pile2_count <= 1,
                   f"dispatched={[(r.car_id, r.pile_id, r.status) for r in dispatched]}, "
                   f"queuing={[(r.car_id, r.status) for r in queuing]}, counts=({pile1_count}, {pile2_count})")

    def run(self):
        cases = [
            ("需求1", "排队号生成与等候区容量", self.case_req1_queue_numbers_and_waiting_capacity),
            ("需求2", "充电桩配置、桩队列和队首充电", self.case_req2_pile_config_and_queue_head),
            ("需求3", "最短完成时间调度", self.case_req3_shortest_completion_dispatch),
            ("需求4", "分时计费规则", self.case_req4_pricing),
            ("需求5", "用户端/管理员端/详单/报表", self.case_req5_user_admin_detail_report),
            ("需求6", "修改请求与取消请求规则", self.case_req6_modify_cancel_rules),
            ("需求7", "故障调度与恢复调度", self.case_req7_fault_dispatch_and_recovery),
            ("需求8", "扩展调度", self.case_req8_extended_dispatch),
        ]
        for requirement, name, fn in cases:
            self.run_case(requirement, name, fn)
        self.print_summary()

    def print_summary(self):
        print("\n========== 课程需求验收测试结果 ==========")
        current = None
        for item in self.results:
            if item["requirement"] != current:
                current = item["requirement"]
                print(f"\n[{current}]")
            status = "PASS" if item["ok"] else "FAIL"
            print(f"{status} - {item['name']}")
            if not item["ok"] and item["detail"]:
                print(f"       {item['detail']}")

        passed = sum(1 for item in self.results if item["ok"])
        total = len(self.results)
        print("\n========================================")
        print(f"SUMMARY: {passed}/{total} passed")
        if passed != total:
            raise SystemExit(1)


if __name__ == "__main__":
    AcceptanceRunner().run()

