import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from .config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, JWT_SECRET_KEY, DEFAULT_PRICING, DEFAULT_PILES, SYSTEM_CONFIG
from .models import db
from .utils.auth import jwt
from .router import register_routes

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def create_app():
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
    app.json.ensure_ascii = False

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)
    register_routes(app)

    @app.route("/")
    def index():
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EV Charge — 智能充电桩调度计费系统</title>
<style>
  :root {
    --font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
  }
  * { margin:0; padding:0; box-sizing:border-box }
  body {
    font-family: var(--font);
    background: #0a0a0b;
    color: #fff;
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    overflow-x: hidden;
    -webkit-font-smoothing: antialiased;
  }
  /* Ambient glow */
  .glow {
    position: fixed;
    border-radius: 50%;
    filter: blur(120px);
    opacity: 0.15;
    pointer-events: none;
  }
  .glow-1 { width: 600px; height: 600px; background: #16a34a; top: -200px; left: -200px; animation: drift 8s ease-in-out infinite; }
  .glow-2 { width: 500px; height: 500px; background: #2563eb; bottom: -200px; right: -150px; animation: drift 10s ease-in-out infinite reverse; }
  @keyframes drift { 0%,100% { transform: translate(0,0) } 50% { transform: translate(40px,30px) } }

  .container { position: relative; z-index: 1; text-align: center; padding: 48px 24px; max-width: 680px; }
  .badge {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 6px 16px; border-radius: 20px;
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
    font-size: 13px; color: rgba(255,255,255,0.6); margin-bottom: 32px;
    backdrop-filter: blur(8px);
  }
  .badge .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #16a34a; box-shadow: 0 0 8px rgba(22,163,74,0.6); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.4 } }

  h1 { font-size: 44px; font-weight: 800; letter-spacing: -1.5px; line-height: 1.1; margin-bottom: 12px; }
  h1 span { background: linear-gradient(135deg, #16a34a, #22c55e, #4ade80); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
  .subtitle { font-size: 17px; color: rgba(255,255,255,0.45); margin-bottom: 48px; line-height: 1.6; }

  .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px; }
  @media (max-width: 540px) { .cards { grid-template-columns: 1fr } h1 { font-size: 32px } }

  .card {
    display: block; text-decoration: none;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px; padding: 36px 28px;
    text-align: left; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative; overflow: hidden;
    backdrop-filter: blur(12px);
  }
  .card:hover {
    background: rgba(255,255,255,0.07); border-color: rgba(255,255,255,0.18);
    transform: translateY(-4px);
    box-shadow: 0 20px 40px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.05) inset;
  }
  .card-icon {
    width: 48px; height: 48px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; margin-bottom: 18px;
  }
  .card-user .card-icon { background: rgba(22,163,74,0.15); color: #4ade80; }
  .card-admin .card-icon { background: rgba(37,99,235,0.15); color: #60a5fa; }
  .card h3 { font-size: 18px; font-weight: 700; color: #fff; margin-bottom: 6px; letter-spacing: -0.3px; }
  .card p { font-size: 13px; color: rgba(255,255,255,0.4); line-height: 1.5; }
  .card .arrow {
    position: absolute; right: 24px; top: 50%; transform: translateY(-50%);
    width: 32px; height: 32px; border-radius: 50%;
    background: rgba(255,255,255,0.06);
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; color: rgba(255,255,255,0.3);
    transition: all 0.3s;
  }
  .card:hover .arrow { background: rgba(255,255,255,0.12); color: #fff; }

  .footer { font-size: 13px; color: rgba(255,255,255,0.25); margin-top: 8px; letter-spacing: 0.3px; }
  .footer span { color: rgba(255,255,255,0.4); }
</style>
</head>
<body>
<div class="glow glow-1"></div>
<div class="glow glow-2"></div>

<div class="container">
  <div class="badge"><span class="live-dot"></span> 系统运行中</div>
  <h1>智能<span>充电桩</span>调度计费系统</h1>
  <p class="subtitle">为电动汽车提供高效、智能的充电服务体验<br>支持快慢充调度 · 分时计费 · 实时监控</p>

  <div class="cards">
    <a class="card card-user" href="/user-client/index.html">
      <div class="card-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
      </div>
      <h3>用户客户端</h3>
      <p>提交充电申请 · 查看排队状态 · 管理账单</p>
      <div class="arrow">&rarr;</div>
    </a>

    <a class="card card-admin" href="/admin-client/index.html">
      <div class="card-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
      </div>
      <h3>管理控制台</h3>
      <p>监控充电桩状态 · 处理故障 · 查看运营报表</p>
      <div class="arrow">&rarr;</div>
    </a>
  </div>

  <p class="footer">2023211303_G6 &ensp;<span>计子毅&nbsp; 陈子容&nbsp; 江宝金&nbsp; 张贺维&nbsp; 李卓轩</span></p>
</div>
</body>
</html>"""

    @app.teardown_request
    def commit_on_success(exc=None):
        if exc is None:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    return app


def init_db():
    """初始化数据库：建表（如不存在）+ 写入默认配置（如不存在）。保留已有用户数据。"""
    db.create_all()

    from .models.pricing_rule import PricingRule
    from .models.charging_pile import ChargingPile

    for pr_cfg in DEFAULT_PRICING:
        rule = PricingRule.query.filter_by(mode=pr_cfg["mode"]).first()
        if not rule:
            db.session.add(PricingRule(**pr_cfg))
        else:
            rule.peak_price = pr_cfg["peak_price"]
            rule.mid_price = pr_cfg["mid_price"]
            rule.off_peak_price = pr_cfg["off_peak_price"]
            rule.service_fee_rate = pr_cfg["service_fee_rate"]

    for p_cfg in DEFAULT_PILES:
        if not db.session.get(ChargingPile, p_cfg["pile_id"]):
            db.session.add(ChargingPile(
                pile_id=p_cfg["pile_id"],
                mode=p_cfg["mode"],
                power=p_cfg["power"],
                status="available",
                queue_len=SYSTEM_CONFIG["ChargingQueueLen"],
            ))

    db.session.commit()


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
