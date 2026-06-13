from ..models import db
from ..models.dispatch_record import DispatchRecord
from ..models.fault_record import FaultRecord
from ..models.pricing_rule import PricingRule
from ..utils.timezone import local_now


class DispatchRecordDAO:
    @staticmethod
    def insert(record):
        db.session.add(record)
        db.session.flush()
        return record


class FaultRecordDAO:
    @staticmethod
    def create(pile_id, handler=None):
        record = FaultRecord(pile_id=pile_id, handler=handler, fault_time=local_now())
        db.session.add(record)
        db.session.flush()
        return record

    @staticmethod
    def find_active_by_pile(pile_id):
        return FaultRecord.query.filter_by(pile_id=pile_id, status="active").first()

    @staticmethod
    def resolve(record):
        record.status = "resolved"
        record.recover_time = local_now()
        db.session.flush()
        return record

    @staticmethod
    def find_all():
        return FaultRecord.query.order_by(FaultRecord.fault_time.desc()).all()


class PricingRuleDAO:
    @staticmethod
    def get_by_mode(mode):
        return PricingRuleDAO.ensure_fixed_pricing(mode)

    @staticmethod
    def get_all():
        return [PricingRuleDAO.ensure_fixed_pricing(mode) for mode in ("F", "T")]

    @staticmethod
    def ensure_fixed_pricing(mode):
        default = PricingRuleDAO._fixed_pricing(mode)
        if not default:
            return None

        rule = PricingRule.query.filter_by(mode=mode).first()
        if not rule:
            rule = PricingRule(mode=mode)
            db.session.add(rule)

        changed = False
        for key in ("peak_price", "mid_price", "off_peak_price", "service_fee_rate"):
            if getattr(rule, key) != default[key]:
                setattr(rule, key, default[key])
                changed = True
        if changed:
            rule.updated_at = local_now()
        db.session.flush()
        return rule

    @staticmethod
    def _fixed_pricing(mode):
        from ..config import DEFAULT_PRICING
        return next((cfg for cfg in DEFAULT_PRICING if cfg["mode"] == mode), None)

    @staticmethod
    def update_pricing(mode, peak, mid, off_peak, service_rate):
        return PricingRuleDAO.ensure_fixed_pricing(mode)
