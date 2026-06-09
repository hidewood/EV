from datetime import timedelta
from urllib.parse import quote_plus

# ── 数据库 ──────────────────────────────────────────
DB_USER = "root"
DB_PWD = "Twp17529003@"
DB_HOST = "127.0.0.1"
DB_PORT = "3306"
DB_NAME = "charging_system"

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PWD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# ── JWT ────────────────────────────────────────────
JWT_SECRET_KEY = "charging-system-jwt-secret-key"
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)

# ── 系统参数 ── 修改后重启生效 ──────────────────────
SYSTEM_CONFIG = {
    "FastChargingPileNum": 2,
    "TrickleChargingPileNum": 3,
    "WaitingAreaSize": 10,
    "ChargingQueueLen": 5,
}

FAULT_DISPATCH_STRATEGY = "priority"  # "priority" 或 "time_order"

# ── 对外对接 ────────────────────────────────────────
PARTNER_CONFIG = {
    "partner_id": "",
    "partner_name": "",
    "partner_api_base": "",
    "shared_secret": "",
    "api_key": "",
    "partner_api_key": "",
}

# ── 默认计费 ────────────────────────────────────────
DEFAULT_PRICING = [
    {"mode": "F", "peak_price": 1.0, "mid_price": 0.7, "off_peak_price": 0.4, "service_fee_rate": 0.8},
    {"mode": "T", "peak_price": 0.8, "mid_price": 0.5, "off_peak_price": 0.3, "service_fee_rate": 0.6},
]

# ── 默认充电桩 ──────────────────────────────────────
DEFAULT_PILES = [
    {"pile_id": 1, "mode": "F", "power": 30.0},
    {"pile_id": 2, "mode": "F", "power": 30.0},
    {"pile_id": 3, "mode": "T", "power": 10.0},
    {"pile_id": 4, "mode": "T", "power": 10.0},
    {"pile_id": 5, "mode": "T", "power": 10.0},
]
