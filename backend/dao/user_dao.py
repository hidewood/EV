from ..models import db
from ..models.user import User
from ..models.charging_request import ChargingRequest
from ..models.charging_session import ChargingSession
from ..models.charging_detail import ChargingDetail
from ..models.bill import Bill
from ..models.payment import Payment


class UserDAO:
    @staticmethod
    def find_by_car_id(car_id):
        return db.session.get(User, car_id)

    @staticmethod
    def insert(user):
        db.session.add(user)
        db.session.flush()
        return user

    @staticmethod
    def update_password(car_id, password_hash):
        user = db.session.get(User, car_id)
        if user:
            user.password_hash = password_hash
            db.session.flush()
        return user


class ChargingRequestDAO:
    @staticmethod
    def find_by_id(request_id):
        return db.session.get(ChargingRequest, request_id)

    @staticmethod
    def find_active_by_car_id(car_id):
        return (
            ChargingRequest.query
            .filter_by(car_id=car_id)
            .filter(ChargingRequest.status.in_(["queuing", "dispatched", "charging", "pending_reschedule"]))
            .first()
        )

    @staticmethod
    def insert(request_obj):
        db.session.add(request_obj)
        db.session.flush()
        return request_obj

    @staticmethod
    def update(request_obj):
        db.session.flush()
        return request_obj

    @staticmethod
    def find_by_status(status_list):
        return ChargingRequest.query.filter(ChargingRequest.status.in_(status_list)).all()


class ChargingSessionDAO:
    @staticmethod
    def find_by_id(session_id):
        return db.session.get(ChargingSession, session_id)

    @staticmethod
    def find_active_by_car_id(car_id):
        return ChargingSession.query.filter_by(car_id=car_id, status="active").first()

    @staticmethod
    def find_active_by_pile_id(pile_id):
        return ChargingSession.query.filter_by(pile_id=pile_id, status="active").first()

    @staticmethod
    def insert(session_obj):
        db.session.add(session_obj)
        db.session.flush()
        return session_obj

    @staticmethod
    def update(session_obj):
        db.session.flush()
        return session_obj

    @staticmethod
    def find_completed_by_pile_and_time(pile_id, start, end):
        return (
            ChargingSession.query
            .filter_by(pile_id=pile_id, status="completed")
            .filter(ChargingSession.end_time >= start, ChargingSession.end_time <= end)
            .all()
        )

    @staticmethod
    def find_all_by_time(start, end):
        return (
            ChargingSession.query
            .filter(ChargingSession.end_time >= start, ChargingSession.end_time <= end)
            .all()
        )


class ChargingDetailDAO:
    @staticmethod
    def insert(detail):
        db.session.add(detail)
        db.session.flush()
        return detail

    @staticmethod
    def find_by_bill_id(detail_id):
        return db.session.get(ChargingDetail, detail_id)


class BillDAO:
    @staticmethod
    def find_by_id(bill_id):
        return db.session.get(Bill, bill_id)

    @staticmethod
    def find_by_car_and_date(car_id, date_str):
        return (
            Bill.query
            .filter_by(car_id=car_id)
            .filter(db.func.date(Bill.create_time) == date_str)
            .all()
        )

    @staticmethod
    def insert(bill):
        db.session.add(bill)
        db.session.flush()
        return bill

    @staticmethod
    def update(bill):
        db.session.flush()
        return bill


class PaymentDAO:
    @staticmethod
    def insert(payment):
        db.session.add(payment)
        db.session.flush()
        return payment
