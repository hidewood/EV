from ..dao.user_dao import BillDAO, ChargingDetailDAO, PaymentDAO
from ..dao.pile_dao import ChargingPileDAO
from ..models.payment import Payment
from ..utils.timezone import local_now


def _pile_no(pile_id):
    """根据 pile_id 查模式，生成如 F1、T2 的桩编号。"""
    pile = ChargingPileDAO.find_by_id(pile_id)
    mode = pile.mode if pile else "F"
    return f"{mode}{pile_id}"


class BillService:
    @staticmethod
    def query_bills(car_id, date_str=None):
        if date_str:
            bills = BillDAO.find_by_car_and_date(car_id, date_str)
        else:
            bills = BillDAO.find_by_car(car_id)
        result = []
        for b in bills:
            bill_date = b.create_time.strftime("%Y-%m-%d") if b.create_time else None
            result.append({
                "bill_id": b.bill_id,
                "bill_no": f"BILL{b.bill_id:04d}",
                "bill_date": bill_date,
                "detail_id": b.detail_id,
                "total_charge_fee": b.total_charge_fee,
                "total_service_fee": b.total_service_fee,
                "total_fee": b.total_fee,
                "status": b.status,
                "pay_status": b.status,
                "create_time": b.create_time.isoformat() if b.create_time else None,
                "created_at": b.create_time.isoformat() if b.create_time else None,
                "pay_time": b.pay_time.isoformat() if b.pay_time else None,
            })
        return result

    @staticmethod
    def query_detail(bill_id, car_id):
        bill = BillDAO.find_by_id(bill_id)
        if not bill or bill.car_id != car_id:
            return None

        detail = ChargingDetailDAO.find_by_bill_id(bill.detail_id)
        if not detail:
            return None

        pile_no = _pile_no(detail.pile_id)
        bill_date = bill.create_time.strftime("%Y-%m-%d") if bill.create_time else None

        return {
            "bill_id": bill.bill_id,
            "bill_no": f"BILL{bill.bill_id:04d}",
            "bill_date": bill_date,
            "total_charge_amount": detail.charge_amount,
            "total_charge_duration": detail.charge_duration,
            "total_charge_fee": detail.charge_fee,
            "total_service_fee": detail.service_fee,
            "total_fee": detail.total_fee,
            "status": bill.status,
            "pay_status": bill.status,
            "details": [{
                "detail_no": f"DET{detail.detail_id:04d}",
                "generated_at": detail.created_at.isoformat() if detail.created_at else None,
                "pile_no": pile_no,
                "charge_amount": detail.charge_amount,
                "charge_duration": detail.charge_duration,
                "start_time": detail.start_time.isoformat() if detail.start_time else None,
                "end_time": detail.stop_time.isoformat() if detail.stop_time else None,
                "charge_fee": detail.charge_fee,
                "service_fee": detail.service_fee,
                "total_fee": detail.total_fee,
            }],
            # 兼容旧 EV 前端字段
            "detail_id": detail.detail_id,
            "car_id": detail.car_id,
            "pile_id": detail.pile_id,
            "charge_amount": detail.charge_amount,
            "charge_duration": detail.charge_duration,
            "start_time": detail.start_time.isoformat() if detail.start_time else None,
            "stop_time": detail.stop_time.isoformat() if detail.stop_time else None,
            "charge_fee": detail.charge_fee,
            "service_fee": detail.service_fee,
            "created_at": detail.created_at.isoformat() if detail.created_at else None,
        }

    @staticmethod
    def pay_bill(bill_id, car_id):
        bill = BillDAO.find_by_id(bill_id)
        if not bill or bill.car_id != car_id:
            return None, "bill_not_found"
        if bill.status == "paid":
            return None, "already_paid"

        payment = Payment(
            bill_id=bill_id,
            car_id=car_id,
            amount=bill.total_fee,
        )
        PaymentDAO.insert(payment)

        bill.status = "paid"
        bill.pay_time = local_now()
        BillDAO.update(bill)

        return {"payment_id": payment.payment_id, "amount": payment.amount}, None
