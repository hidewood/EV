from ..models import db
from ..models.charging_pile import ChargingPile
from sqlalchemy import func


class ChargingPileDAO:
    @staticmethod
    def find_by_id(pile_id):
        return db.session.get(ChargingPile, pile_id)

    @staticmethod
    def find_all():
        return ChargingPile.query.all()

    @staticmethod
    def find_by_mode_and_status(mode, status_list):
        return (
            ChargingPile.query
            .filter_by(mode=mode)
            .filter(ChargingPile.status.in_(status_list))
            .all()
        )

    @staticmethod
    def find_available_by_mode(mode):
        return (
            ChargingPile.query
            .filter_by(mode=mode, status="available")
            .all()
        )

    @staticmethod
    def update(pile):
        db.session.flush()
        return pile

    @staticmethod
    def insert(pile):
        db.session.add(pile)
        db.session.flush()
        return pile

    @staticmethod
    def get_total_stats(pile_id, start=None, end=None):
        """聚合一桩的累计统计。"""
        from ..models.charging_session import ChargingSession

        q = ChargingSession.query.filter_by(pile_id=pile_id, status="completed")
        if start:
            q = q.filter(ChargingSession.end_time >= start)
        if end:
            q = q.filter(ChargingSession.end_time <= end)

        count = q.count()
        total_charge_time = db.session.query(func.coalesce(func.sum(ChargingSession.charge_amount), 0)).filter(
            ChargingSession.pile_id == pile_id,
            ChargingSession.status == "completed",
        )
        if start:
            total_charge_time = total_charge_time.filter(ChargingSession.end_time >= start)
        if end:
            total_charge_time = total_charge_time.filter(ChargingSession.end_time <= end)
        total_time = total_charge_time.scalar()
        return count, total_time or 0.0
