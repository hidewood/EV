from ..models import db
from ..models.charging_pile import ChargingPile

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

        sessions = q.all()
        total_time = sum(
            (s.end_time - s.start_time).total_seconds() / 3600
            for s in sessions
            if s.start_time and s.end_time
        )
        return len(sessions), total_time
