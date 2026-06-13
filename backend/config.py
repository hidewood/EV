import os
from datetime import timedelta
from urllib.parse import quote_plus

# ── 数据库 ──────────────────────────────────────────
DB_USER = os.getenv("DB_USER", "root")
DB_PWD = os.getenv("DB_PWD", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "charging_system")

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PWD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# ── JWT ────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-change-me")
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
ADMIN_REGISTER_CODE = os.getenv("ADMIN_REGISTER_CODE", "")

# ── 系统参数 ── 修改后重启生效 ──────────────────────
SYSTEM_CONFIG = {
    "FastChargingPileNum": 2,
    "TrickleChargingPileNum": 3,
    "WaitingAreaSize": 10,
    "ChargingQueueLen": 5,
}

FAULT_DISPATCH_STRATEGY = "priority"  # "priority" 或 "time_order"
EXTENDED_DISPATCH_MODE = "normal"  # "normal"、"single_min_total" 或 "batch_min_total"

# ── 对外对接 ────────────────────────────────────────
PARTNER_CONFIG = {
    "partner_id": os.getenv("PARTNER_ID", ""),
    "partner_name": os.getenv("PARTNER_NAME", ""),
    "partner_api_base": os.getenv("PARTNER_API_BASE", ""),
    "shared_secret": os.getenv("PARTNER_SHARED_SECRET", ""),
    "api_key": os.getenv("PARTNER_API_KEY", ""),
    "partner_api_key": os.getenv("PARTNER_REMOTE_API_KEY", ""),
}

# ── 默认计费 ────────────────────────────────────────
DEFAULT_PRICING = [
    {"mode": "F", "peak_price": 1.0, "mid_price": 0.7, "off_peak_price": 0.4, "service_fee_rate": 0.8},
    {"mode": "T", "peak_price": 1.0, "mid_price": 0.7, "off_peak_price": 0.4, "service_fee_rate": 0.8},
]

# ── 默认充电桩 ──────────────────────────────────────
DEFAULT_PILES = [
    {"pile_id": 1, "mode": "F", "power": 30.0},
    {"pile_id": 2, "mode": "F", "power": 30.0},
    {"pile_id": 3, "mode": "T", "power": 10.0},
    {"pile_id": 4, "mode": "T", "power": 10.0},
    {"pile_id": 5, "mode": "T", "power": 10.0},
]
