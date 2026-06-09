from ..dao.user_dao import BillDAO, ChargingDetailDAO, PaymentDAO
from ..models.payment import Payment
from datetime import datetime


class BillService:
    @staticmethod
    def query_bills(car_id, date_str=None):
        if date_str:
            bills = BillDAO.find_by_car_and_date(car_id, date_str)
        else:
            bills = BillDAO.find_by_car_and_date(car_id, datetime.utcnow().strftime("%Y-%m-%d"))
        result = []
        for b in bills:
            result.append({
                "bill_id": b.bill_id,
                "detail_id": b.detail_id,
                "total_charge_fee": b.total_charge_fee,
                "total_service_fee": b.total_service_fee,
                "total_fee": b.total_fee,
                "status": b.status,
                "create_time": b.create_time.isoformat() if b.create_time else None,
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

        return {
            "detail_id": detail.detail_id,
            "car_id": detail.car_id,
            "pile_id": detail.pile_id,
            "charge_amount": detail.charge_amount,
            "charge_duration": detail.charge_duration,
            "start_time": detail.start_time.isoformat() if detail.start_time else None,
            "stop_time": detail.stop_time.isoformat() if detail.stop_time else None,
            "charge_fee": detail.charge_fee,
            "service_fee": detail.service_fee,
            "total_fee": detail.total_fee,
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
        bill.pay_time = datetime.utcnow()
        BillDAO.update(bill)

        return {"payment_id": payment.payment_id, "amount": payment.amount}, None
