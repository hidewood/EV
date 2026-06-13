import os
import unittest

os.environ["ADMIN_REGISTER_CODE"] = "test-admin-code"

from backend import app as backend_app

backend_app.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class SecurityAndQueueTest(unittest.TestCase):
    def setUp(self):
        self.app = backend_app.create_app()
        self.app.config["TESTING"] = True
        if not hasattr(self.app, "json_encoder"):
            self.app.json_encoder = None
        self.client = self.app.test_client()

        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.models.pricing_rule import PricingRule
            from backend.config import DEFAULT_PRICING
            import backend.config as config

            config.EXTENDED_DISPATCH_MODE = "normal"
            config.FAULT_DISPATCH_STRATEGY = "priority"
            config.SYSTEM_CONFIG["FastChargingPileNum"] = 2
            config.SYSTEM_CONFIG["TrickleChargingPileNum"] = 3
            config.SYSTEM_CONFIG["WaitingAreaSize"] = 10
            config.SYSTEM_CONFIG["ChargingQueueLen"] = 5

            db.drop_all()
            db.create_all()
            for cfg in DEFAULT_PRICING:
                db.session.add(PricingRule(**cfg))
            db.session.add(ChargingPile(
                pile_id=1,
                mode="F",
                power=30.0,
                status="available",
                queue_len=5,
            ))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            from backend.models import db
            db.session.remove()
            db.drop_all()

    def post(self, path, data, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(path, json=data, headers=headers).get_json()

    def get(self, path, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(path, headers=headers).get_json()

    def register_user(self, car_id):
        return self.post("/api/auth/register", {
            "car_id": car_id,
            "user_name": car_id,
            "car_capacity": 60,
            "password": "pw",
        })

    def login(self, car_id):
        resp = self.post("/api/auth/login", {"car_id": car_id, "password": "pw"})
        self.assertEqual(resp["code"], 0)
        return resp["data"]["access_token"]

    def register_admin_and_login(self):
        resp = self.post("/api/auth/register", {
            "car_id": "ADM1",
            "user_name": "Admin",
            "car_capacity": 1,
            "password": "pw",
            "role": "admin",
            "admin_code": "test-admin-code",
        })
        self.assertEqual(resp["code"], 0)
        return self.login("ADM1")

    def test_admin_registration_requires_code(self):
        denied = self.post("/api/auth/register", {
            "car_id": "ADM1",
            "user_name": "Admin",
            "car_capacity": 1,
            "password": "pw",
            "role": "admin",
        })
        self.assertEqual(denied["code"], 1003)

        allowed = self.post("/api/auth/register", {
            "car_id": "ADM1",
            "user_name": "Admin",
            "car_capacity": 1,
            "password": "pw",
            "role": "admin",
            "admin_code": "test-admin-code",
        })
        self.assertEqual(allowed["code"], 0)

    def test_user_cannot_access_admin_api(self):
        self.assertEqual(self.register_user("U1")["code"], 0)
        token = self.login("U1")

        resp = self.get("/api/admin/system-config", token)
        self.assertEqual(resp["code"], 1003)

    def test_external_api_requires_partner_token(self):
        import backend.config as config

        config.PARTNER_CONFIG["partner_id"] = "partner-a"
        config.PARTNER_CONFIG["partner_api_key"] = "secret-a"

        missing = self.get("/api/v1/external/piles/status")
        self.assertEqual(missing["code"], 1002)

        self.assertEqual(self.register_user("U1")["code"], 0)
        user_token = self.login("U1")
        denied = self.get("/api/v1/external/piles/status", user_token)
        self.assertEqual(denied["code"], 1003)

        token_resp = self.post("/api/v1/external/auth/token", {
            "partner_id": "partner-a",
            "api_key": "secret-a",
        })
        self.assertEqual(token_resp["code"], 0)
        partner_token = token_resp["data"]["access_token"]
        allowed = self.get("/api/v1/external/piles/status", partner_token)
        self.assertEqual(allowed["code"], 0)

    def test_external_status_is_bound_to_request_id(self):
        import backend.config as config

        config.PARTNER_CONFIG["partner_id"] = "partner-a"
        config.PARTNER_CONFIG["partner_api_key"] = "secret-a"
        partner_token = self.post("/api/v1/external/auth/token", {
            "partner_id": "partner-a",
            "api_key": "secret-a",
        })["data"]["access_token"]

        first = self.post("/api/v1/external/charging/request", {
            "car_id": "PX1",
            "request_mode": "F",
            "request_amount": 10,
        }, partner_token)
        self.assertEqual(first["code"], 0)
        first_request_id = first["data"]["request_id"]

        with self.app.app_context():
            from backend.models import db
            from backend.dao.user_dao import ChargingRequestDAO
            req = ChargingRequestDAO.find_by_id(first_request_id)
            req.status = "completed"
            ChargingRequestDAO.update(req)
            db.session.commit()

        second = self.post("/api/v1/external/charging/request", {
            "car_id": "PX1",
            "request_mode": "F",
            "request_amount": 5,
        }, partner_token)
        self.assertEqual(second["code"], 0)

        old_status = self.get(
            f"/api/v1/external/charging/status/{first_request_id}",
            partner_token,
        )
        self.assertEqual(old_status["code"], 0)
        self.assertEqual(old_status["data"]["request_id"], first_request_id)
        self.assertEqual(old_status["data"]["status"], "completed")

    def test_second_vehicle_cannot_start_before_queue_head(self):
        tokens = {}
        requests = {}
        for car_id in ("U1", "U2"):
            self.assertEqual(self.register_user(car_id)["code"], 0)
            tokens[car_id] = self.login(car_id)
            requests[car_id] = self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 10,
            }, tokens[car_id])
            self.assertEqual(requests[car_id]["code"], 0)

        self.assertEqual(requests["U1"]["data"]["queue_num"], "F1")
        self.assertEqual(requests["U2"]["data"]["queue_num"], "F2")

        second_start = self.post("/api/charging/start", {"pile_id": 1}, tokens["U2"])
        self.assertEqual(second_start["code"], 3003)

        first_start = self.post("/api/charging/start", {"pile_id": 1}, tokens["U1"])
        self.assertEqual(first_start["code"], 0)

        first_end = self.post("/api/charging/end", {}, tokens["U1"])
        self.assertEqual(first_end["code"], 0)

        second_start_after = self.post("/api/charging/start", {"pile_id": 1}, tokens["U2"])
        self.assertEqual(second_start_after["code"], 0)

    def test_fault_report_uses_updated_strategy(self):
        admin_token = self.register_admin_and_login()

        update = self.client.put("/api/admin/system-config", json={
            "fast_pile_num": 2,
            "slow_pile_num": 1,
            "waiting_area_size": 10,
            "charging_queue_len": 5,
            "fault_strategy": "time_order",
        }, headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        self.assertEqual(update["code"], 0)

        fault = self.post("/api/admin/fault/report", {"pile_id": 1}, admin_token)
        self.assertEqual(fault["code"], 0)
        self.assertEqual(fault["data"]["strategy"], "time_order")

    def test_fault_record_times_are_returned_as_stored_china_time(self):
        with self.app.app_context():
            from datetime import datetime
            from backend.models import db
            from backend.models.fault_record import FaultRecord
            from backend.services.fault_service import FaultService

            db.session.add(FaultRecord(
                pile_id=1,
                fault_time=datetime(2026, 6, 11, 0, 0, 0),
                recover_time=datetime(2026, 6, 11, 1, 30, 0),
                status="resolved",
            ))
            db.session.commit()

            records = FaultService.get_fault_records()
            self.assertEqual(records[0]["fault_time"], "2026-06-11T00:00:00")
            self.assertEqual(records[0]["recover_time"], "2026-06-11T01:30:00")

    def test_pricing_is_fixed_and_cannot_be_modified(self):
        admin_token = self.register_admin_and_login()

        update = self.client.put("/api/pile/parameters", json={
            "mode": "F",
            "peak_price": 9.9,
            "mid_price": 9.9,
            "off_peak_price": 9.9,
            "service_fee_rate": 9.9,
        }, headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        self.assertEqual(update["code"], 1003)

        pricing = self.get("/api/pile/parameters", admin_token)
        self.assertEqual(pricing["code"], 0)
        self.assertEqual(pricing["data"]["fast"]["peak_price"], 1.0)
        self.assertEqual(pricing["data"]["fast"]["mid_price"], 0.7)
        self.assertEqual(pricing["data"]["fast"]["off_peak_price"], 0.4)
        self.assertEqual(pricing["data"]["fast"]["service_fee_rate"], 0.8)
        self.assertEqual(pricing["data"]["slow"]["peak_price"], 1.0)
        self.assertEqual(pricing["data"]["slow"]["mid_price"], 0.7)
        self.assertEqual(pricing["data"]["slow"]["off_peak_price"], 0.4)
        self.assertEqual(pricing["data"]["slow"]["service_fee_rate"], 0.8)

    def test_bill_list_without_date_returns_all_user_bills(self):
        from datetime import datetime

        self.assertEqual(self.register_user("U1")["code"], 0)
        token = self.login("U1")

        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_request import ChargingRequest
            from backend.models.charging_session import ChargingSession
            from backend.models.charging_detail import ChargingDetail
            from backend.models.bill import Bill

            for idx, created_at in enumerate((
                datetime(2026, 6, 10, 10, 0, 0),
                datetime(2026, 6, 11, 10, 0, 0),
            ), start=1):
                req = ChargingRequest(
                    car_id="U1",
                    request_mode="F",
                    request_amount=10,
                    queue_num=f"F{idx}",
                    status="completed",
                )
                db.session.add(req)
                db.session.flush()
                session = ChargingSession(
                    request_id=req.request_id,
                    car_id="U1",
                    pile_id=1,
                    start_time=created_at,
                    end_time=created_at,
                    status="completed",
                )
                db.session.add(session)
                db.session.flush()
                detail = ChargingDetail(
                    session_id=session.session_id,
                    car_id="U1",
                    pile_id=1,
                    charge_amount=10,
                    charge_duration=0.33,
                    start_time=created_at,
                    stop_time=created_at,
                    charge_fee=10,
                    service_fee=8,
                    total_fee=18,
                    created_at=created_at,
                )
                db.session.add(detail)
                db.session.flush()
                db.session.add(Bill(
                    detail_id=detail.detail_id,
                    car_id="U1",
                    total_charge_fee=10,
                    total_service_fee=8,
                    total_fee=18,
                    create_time=created_at,
                ))
            db.session.commit()

        all_bills = self.get("/api/bill/list", token)
        self.assertEqual(all_bills["code"], 0)
        self.assertEqual(len(all_bills["data"]), 2)

        dated_bills = self.get("/api/bill/list?date=2026-06-10", token)
        self.assertEqual(dated_bills["code"], 0)
        self.assertEqual(len(dated_bills["data"]), 1)

    def test_admin_pile_status_includes_off_piles(self):
        admin_token = self.register_admin_and_login()

        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile

            db.session.add(ChargingPile(
                pile_id=2,
                mode="F",
                power=30.0,
                status="off",
                queue_len=5,
            ))
            db.session.commit()

        resp = self.get("/api/pile/status", admin_token)
        self.assertEqual(resp["code"], 0)
        statuses = {p["pile_id"]: p["status"] for p in resp["data"]}
        self.assertEqual(statuses[1], "available")
        self.assertEqual(statuses[2], "off")

    def test_pricing_splits_peak_mid_and_off_peak_boundaries(self):
        from datetime import datetime
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
        self.assertEqual(mid_to_peak, 25.5)

        mid_to_off_peak = calculate_charge_fee(30, 30, datetime(2026, 6, 13, 22, 30, 0), pricing)
        self.assertEqual(mid_to_off_peak, 16.5)

        self.assertEqual(calculate_service_fee(30, pricing), 24.0)

    def test_power_off_rejects_pile_with_queued_vehicle(self):
        admin_token = self.register_admin_and_login()
        self.assertEqual(self.register_user("U1")["code"], 0)
        token = self.login("U1")
        resp = self.post("/api/charging/request", {
            "request_mode": "F",
            "request_amount": 10,
        }, token)
        self.assertEqual(resp["code"], 0)

        off = self.post("/api/pile/1/poweroff", {}, admin_token)
        self.assertEqual(off["code"], 4002)

    def test_system_config_rejects_queue_len_below_current_queue_count(self):
        admin_token = self.register_admin_and_login()
        for car_id in ("U1", "U2"):
            self.assertEqual(self.register_user(car_id)["code"], 0)
            token = self.login(car_id)
            resp = self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 10,
            }, token)
            self.assertEqual(resp["code"], 0)

        update = self.client.put("/api/admin/system-config", json={
            "fast_pile_num": 2,
            "slow_pile_num": 3,
            "waiting_area_size": 10,
            "charging_queue_len": 1,
            "fault_strategy": "priority",
            "dispatch_mode": "normal",
        }, headers={"Authorization": f"Bearer {admin_token}"}).get_json()
        self.assertEqual(update["code"], 4002)

    def test_fault_pending_reschedule_has_priority_when_slot_frees(self):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.dao.user_dao import ChargingRequestDAO
            from backend.services.fault_service import FaultService
            import backend.config as config

            config.FAULT_DISPATCH_STRATEGY = "priority"
            pile1 = db.session.get(ChargingPile, 1)
            pile1.queue_len = 1
            db.session.add(ChargingPile(pile_id=2, mode="F", power=30.0, status="available", queue_len=1))
            db.session.commit()

            tokens = {}
            for car_id in ("U1", "U2", "U3"):
                self.assertEqual(self.register_user(car_id)["code"], 0)
                tokens[car_id] = self.login(car_id)
                resp = self.post("/api/charging/request", {
                    "request_mode": "F",
                    "request_amount": 10,
                }, tokens[car_id])
                self.assertEqual(resp["code"], 0)

            self.assertEqual(self.post("/api/charging/start", {"pile_id": 1}, tokens["U1"])["code"], 0)
            self.assertEqual(self.post("/api/charging/start", {"pile_id": 2}, tokens["U2"])["code"], 0)

            _, err = FaultService.report_fault(1, handler="ADM1")
            self.assertIsNone(err)
            self.assertEqual(ChargingRequestDAO.find_active_by_car_id("U1").status, "pending_reschedule")

            self.assertEqual(self.post("/api/charging/end", {}, tokens["U2"])["code"], 0)
            u1 = ChargingRequestDAO.find_active_by_car_id("U1")
            u3 = ChargingRequestDAO.find_active_by_car_id("U3")
            self.assertEqual(u1.status, "dispatched")
            self.assertEqual(u1.pile_id, 2)
            self.assertEqual(u3.status, "queuing")

    def test_normal_dispatch_selects_shortest_completion_pile(self):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.dao.user_dao import ChargingRequestDAO

            pile1 = db.session.get(ChargingPile, 1)
            pile1.queue_len = 2
            db.session.add(ChargingPile(pile_id=2, mode="F", power=30.0, status="available", queue_len=2))
            db.session.commit()

            self.assertEqual(self.register_user("U1")["code"], 0)
            token1 = self.login("U1")
            first = self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 60,
            }, token1)
            self.assertEqual(first["code"], 0)
            self.assertEqual(first["data"]["pile_id"], 1)
            self.assertEqual(self.post("/api/charging/start", {"pile_id": 1}, token1)["code"], 0)

            self.assertEqual(self.register_user("U2")["code"], 0)
            token2 = self.login("U2")
            second = self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 1,
            }, token2)
            self.assertEqual(second["code"], 0)
            self.assertEqual(ChargingRequestDAO.find_active_by_car_id("U2").pile_id, 2)

    def test_dispatch_uses_remaining_time_for_charging_vehicle(self):
        with self.app.app_context():
            from datetime import timedelta
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.dao.user_dao import ChargingRequestDAO, ChargingSessionDAO
            from backend.utils.timezone import local_now

            pile1 = db.session.get(ChargingPile, 1)
            pile1.queue_len = 3
            db.session.add(ChargingPile(pile_id=2, mode="F", power=30.0, status="available", queue_len=3))
            db.session.commit()

            self.assertEqual(self.register_user("U1")["code"], 0)
            token1 = self.login("U1")
            self.assertEqual(self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 30,
            }, token1)["code"], 0)
            self.assertEqual(self.post("/api/charging/start", {"pile_id": 1}, token1)["code"], 0)
            session = ChargingSessionDAO.find_active_by_car_id("U1")
            session.start_time = local_now() - timedelta(minutes=59)
            db.session.flush()

            self.assertEqual(self.register_user("U2")["code"], 0)
            token2 = self.login("U2")
            self.assertEqual(self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 2,
            }, token2)["code"], 0)
            self.assertEqual(ChargingRequestDAO.find_active_by_car_id("U2").pile_id, 2)

            self.assertEqual(self.register_user("U3")["code"], 0)
            token3 = self.login("U3")
            self.assertEqual(self.post("/api/charging/request", {
                "request_mode": "F",
                "request_amount": 1,
            }, token3)["code"], 0)
            self.assertEqual(ChargingRequestDAO.find_active_by_car_id("U3").pile_id, 1)

    def test_time_order_fault_reschedules_all_uncharged_by_queue_number(self):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.dao.pile_queue_dao import PileQueueDAO
            from backend.dao.user_dao import ChargingRequestDAO
            from backend.services.fault_service import FaultService
            import backend.config as config

            config.FAULT_DISPATCH_STRATEGY = "time_order"
            pile1 = db.session.get(ChargingPile, 1)
            pile1.queue_len = 3
            db.session.add(ChargingPile(pile_id=2, mode="F", power=30.0, status="available", queue_len=3))
            db.session.commit()

            tokens = {}
            for car_id in ("U1", "U2", "U3"):
                self.assertEqual(self.register_user(car_id)["code"], 0)
                tokens[car_id] = self.login(car_id)
                resp = self.post("/api/charging/request", {
                    "request_mode": "F",
                    "request_amount": 10,
                }, tokens[car_id])
                self.assertEqual(resp["code"], 0)

            self.assertEqual(self.post("/api/charging/start", {"pile_id": 1}, tokens["U1"])["code"], 0)
            _, err = FaultService.report_fault(1, handler="ADM1")
            self.assertIsNone(err)

            queue_nums = []
            for entry in PileQueueDAO.get_by_pile_ordered(2):
                req = ChargingRequestDAO.find_by_id(entry.request_id)
                queue_nums.append(req.queue_num)
            self.assertEqual(queue_nums, ["F1", "F2", "F3"])

    def test_fault_recovery_reorders_uncharged_cars_by_queue_number(self):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.dao.pile_queue_dao import PileQueueDAO
            from backend.dao.user_dao import ChargingRequestDAO
            from backend.services.fault_service import FaultService

            pile1 = db.session.get(ChargingPile, 1)
            pile1.status = "fault"
            pile1.queue_len = 2
            db.session.add(ChargingPile(pile_id=2, mode="F", power=30.0, status="available", queue_len=2))
            db.session.commit()

            tokens = {}
            for car_id in ("U1", "U2"):
                self.assertEqual(self.register_user(car_id)["code"], 0)
                tokens[car_id] = self.login(car_id)
                resp = self.post("/api/charging/request", {
                    "request_mode": "F",
                    "request_amount": 10,
                }, tokens[car_id])
                self.assertEqual(resp["code"], 0)

            recovered, err = FaultService.recover_fault(1, handler="ADM1")
            self.assertIsNone(err)
            self.assertEqual(recovered["status"], "available")

            queue_nums = []
            for pile_id in (1, 2):
                for entry in PileQueueDAO.get_by_pile_ordered(pile_id):
                    req = ChargingRequestDAO.find_by_id(entry.request_id)
                    queue_nums.append(req.queue_num)
            self.assertEqual(sorted(queue_nums), ["F1", "F2"])

    def test_single_min_total_assigns_batch_to_minimize_total_time(self):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            import backend.config as config
            from backend.services.dispatch_service import pause_calling, resume_calling, DispatchService
            from backend.dao.user_dao import ChargingRequestDAO

            config.EXTENDED_DISPATCH_MODE = "single_min_total"
            pile1 = db.session.get(ChargingPile, 1)
            pile1.power = 30.0
            pile1.queue_len = 1
            db.session.add(ChargingPile(pile_id=2, mode="F", power=60.0, status="available", queue_len=1))
            db.session.commit()

            pause_calling()
            try:
                for car_id, amount in (("U1", 60), ("U2", 1)):
                    self.assertEqual(self.register_user(car_id)["code"], 0)
                    token = self.login(car_id)
                    resp = self.post("/api/charging/request", {
                        "request_mode": "F",
                        "request_amount": amount,
                    }, token)
                    self.assertEqual(resp["code"], 0)
            finally:
                resume_calling()

            self.assertTrue(DispatchService.trigger_auto_dispatch())
            big = ChargingRequestDAO.find_active_by_car_id("U1")
            small = ChargingRequestDAO.find_active_by_car_id("U2")
            self.assertEqual(big.pile_id, 2)
            self.assertEqual(small.pile_id, 1)

    def test_batch_min_total_waits_until_station_full_and_ignores_modes(self):
        with self.app.app_context():
            from backend.models import db
            from backend.models.charging_pile import ChargingPile
            from backend.dao.user_dao import ChargingRequestDAO
            import backend.config as config

            config.EXTENDED_DISPATCH_MODE = "batch_min_total"
            config.SYSTEM_CONFIG["WaitingAreaSize"] = 1
            pile1 = db.session.get(ChargingPile, 1)
            pile1.mode = "F"
            pile1.power = 30.0
            pile1.queue_len = 1
            db.session.add(ChargingPile(pile_id=2, mode="T", power=10.0, status="available", queue_len=1))
            db.session.commit()

            tokens = {}
            for idx in range(1, 4):
                car_id = f"B{idx}"
                self.assertEqual(self.register_user(car_id)["code"], 0)
                tokens[car_id] = self.login(car_id)
                payload = {"request_amount": 30}
                if idx > 1:
                    payload["request_mode"] = "T"
                resp = self.post("/api/charging/request", payload, tokens[car_id])
                self.assertEqual(resp["code"], 0)

            reqs = [ChargingRequestDAO.find_active_by_car_id(f"B{i}") for i in range(1, 4)]
            self.assertTrue(all(r.status == "dispatched" for r in reqs))
            self.assertTrue(any(r.pile_id == 1 for r in reqs))


if __name__ == "__main__":
    unittest.main()
