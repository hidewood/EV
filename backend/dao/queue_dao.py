from ..models import db
from ..models.waiting_queue import WaitingQueue


class WaitingQueueDAO:
    @staticmethod
    def add(request_id, mode, queue_num):
        entry = WaitingQueue(request_id=request_id, mode=mode, queue_num=queue_num)
        db.session.add(entry)
        db.session.flush()
        return entry

    @staticmethod
    def remove_by_request_id(request_id):
        entry = WaitingQueue.query.filter_by(request_id=request_id).first()
        if entry:
            db.session.delete(entry)
            db.session.flush()

    @staticmethod
    def get_first_by_mode(mode):
        return (
            WaitingQueue.query
            .filter_by(mode=mode)
            .order_by(WaitingQueue.id.asc())
            .first()
        )

    @staticmethod
    def get_count_by_mode(mode):
        return WaitingQueue.query.filter_by(mode=mode).count()

    @staticmethod
    def get_total_count():
        return WaitingQueue.query.count()

    @staticmethod
    def get_front_count(request_id):
        entry = WaitingQueue.query.filter_by(request_id=request_id).first()
        if not entry:
            return 0
        return (
            WaitingQueue.query
            .filter_by(mode=entry.mode)
            .filter(WaitingQueue.id < entry.id)
            .count()
        )

    @staticmethod
    def get_all_by_mode(mode):
        return WaitingQueue.query.filter_by(mode=mode).order_by(WaitingQueue.id.asc()).all()

    @staticmethod
    def get_max_queue_num(mode):
        entries = (
            WaitingQueue.query
            .filter_by(mode=mode)
            .order_by(WaitingQueue.id.desc())
            .all()
        )
        if not entries:
            return 0
        for e in entries:
            try:
                num = int(e.queue_num[1:])
                return num
            except (ValueError, IndexError):
                continue
        return 0
