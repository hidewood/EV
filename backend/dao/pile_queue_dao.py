from ..models import db
from ..models.pile_queue import PileQueue


class PileQueueDAO:
    @staticmethod
    def add(pile_id, request_id, position):
        entry = PileQueue(pile_id=pile_id, request_id=request_id, position=position)
        db.session.add(entry)
        db.session.flush()
        return entry

    @staticmethod
    def remove_by_request_id(request_id):
        entries = PileQueue.query.filter_by(request_id=request_id).all()
        pile_ids = {e.pile_id for e in entries}
        for e in entries:
            db.session.delete(e)
        db.session.flush()
        for pile_id in pile_ids:
            PileQueueDAO.compact_positions(pile_id)

    @staticmethod
    def get_count_by_pile(pile_id):
        return PileQueue.query.filter_by(pile_id=pile_id).count()

    @staticmethod
    def get_by_pile_ordered(pile_id):
        return (
            PileQueue.query
            .filter_by(pile_id=pile_id)
            .order_by(PileQueue.position.asc())
            .all()
        )

    @staticmethod
    def get_first(pile_id):
        return (
            PileQueue.query
            .filter_by(pile_id=pile_id, position=1)
            .first()
        )

    @staticmethod
    def get_uncharged_by_pile(pile_id):
        """position > 1 的排队车辆（未开始充电）。"""
        return (
            PileQueue.query
            .filter_by(pile_id=pile_id)
            .filter(PileQueue.position > 1)
            .order_by(PileQueue.position.asc())
            .all()
        )

    @staticmethod
    def clear_pile(pile_id):
        """清空整个充电桩队列（含正在充电的 position=1）。"""
        PileQueue.query.filter_by(pile_id=pile_id).delete()
        db.session.flush()

    @staticmethod
    def clear_uncharged_from_pile(pile_id):
        """只清空未开始充电的排队车辆（position > 1），保留正在充电的。"""
        PileQueue.query.filter_by(pile_id=pile_id).filter(PileQueue.position > 1).delete()
        db.session.flush()
        PileQueueDAO.compact_positions(pile_id)

    @staticmethod
    def compact_positions(pile_id):
        entries = (
            PileQueue.query
            .filter_by(pile_id=pile_id)
            .order_by(PileQueue.position.asc(), PileQueue.id.asc())
            .all()
        )
        for idx, entry in enumerate(entries, start=1):
            entry.position = idx
        db.session.flush()
