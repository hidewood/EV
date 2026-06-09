from ..models import db
from ..models.dispatch_record import DispatchRecord
from ..models.fault_record import FaultRecord
from ..models.pricing_rule import PricingRule
from datetime import datetime


class DispatchRecordDAO:
    @staticmethod
    def insert(record):
        db.session.add(record)
        db.session.flush()
        return record


class FaultRecordDAO:
    @staticmethod
    def create(pile_id, handler=None):
        record = FaultRecord(pile_id=pile_id, handler=handler)
        db.session.add(record)
        db.session.flush()
        return record

    @staticmethod
    def find_active_by_pile(pile_id):
        return FaultRecord.query.filter_by(pile_id=pile_id, status="active").first()

    @staticmethod
    def resolve(record):
        record.status = "resolved"
        record.recover_time = datetime.utcnow()
        db.session.flush()
        return record

    @staticmethod
    def find_all():
        return FaultRecord.query.order_by(FaultRecord.fault_time.desc()).all()


class PricingRuleDAO:
    @staticmethod
    def get_by_mode(mode):
        return PricingRule.query.filter_by(mode=mode).first()

    @staticmethod
    def get_all():
        return PricingRule.query.all()

    @staticmethod
    def update_pricing(mode, peak, mid, off_peak, service_rate):
        rule = PricingRule.query.filter_by(mode=mode).first()
        if not rule:
            rule = PricingRule(mode=mode)
            db.session.add(rule)
        rule.peak_price = peak
        rule.mid_price = mid
        rule.off_peak_price = off_peak
        rule.service_fee_rate = service_rate
        rule.updated_at = datetime.utcnow()
        db.session.flush()
        return rule
