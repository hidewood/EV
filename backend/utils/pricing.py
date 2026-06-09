from datetime import datetime, timedelta

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
    """按分钟精度分时段计算充电费。"""
    if charge_amount <= 0:
        return 0.0
    total_hours = charge_amount / charge_power
    total_minutes = int(total_hours * 60)
    if total_minutes <= 0:
        total_minutes = 1

    start_dt = start_time
    total_fee = 0.0
    remaining_minutes = total_minutes

    while remaining_minutes > 0:
        chunk = min(remaining_minutes, 60)
        mid_dt = start_dt + timedelta(minutes=chunk / 2)
        price = get_price_by_time(mid_dt, pricing_rule)
        total_fee += price * charge_power * (chunk / 60)
        start_dt = start_dt + timedelta(minutes=chunk)
        remaining_minutes -= chunk

    return round(total_fee, 2)


def calculate_service_fee(charge_amount, pricing_rule):
    return round(charge_amount * pricing_rule.service_fee_rate, 2)
