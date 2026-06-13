from datetime import datetime, time, timedelta

PEAK_HOURS = [(10, 15), (18, 21)]
MID_HOURS = [(7, 10), (15, 18), (21, 23)]


def get_price_by_time(dt, pricing_rule):
    hour = dt.hour
    if any(start <= hour < end for start, end in PEAK_HOURS):
        return pricing_rule.peak_price
    if any(start <= hour < end for start, end in MID_HOURS):
        return pricing_rule.mid_price
    return pricing_rule.off_peak_price


def calculate_charge_fee(charge_amount, charge_power, start_time, pricing_rule):
    """按价格边界精确拆分计算充电费。"""
    if charge_amount <= 0:
        return 0.0
    total_hours = charge_amount / charge_power
    end_dt = start_time + timedelta(hours=total_hours)
    current = start_time
    total_fee = 0.0

    while current < end_dt:
        next_dt = min(_next_price_boundary(current), end_dt)
        hours = (next_dt - current).total_seconds() / 3600
        total_fee += get_price_by_time(current, pricing_rule) * charge_power * hours
        current = next_dt

    return round(total_fee, 2)


def calculate_service_fee(charge_amount, pricing_rule):
    return round(charge_amount * pricing_rule.service_fee_rate, 2)


def _next_price_boundary(dt):
    boundary_hours = [7, 10, 15, 18, 21, 23]
    candidates = [
        datetime.combine(dt.date(), time(hour=h))
        for h in boundary_hours
        if datetime.combine(dt.date(), time(hour=h)) > dt
    ]
    if candidates:
        return min(candidates)
    return datetime.combine(dt.date() + timedelta(days=1), time(hour=7))
