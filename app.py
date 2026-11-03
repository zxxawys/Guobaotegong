# -*- coding: utf-8 -*-
"""
手机换新攻略 —— 本地小应用
--------------------------------
运行方式：  python app.py
然后浏览器打开：  http://127.0.0.1:8000

数据库：首次运行会自动在同目录创建 phones.db（SQLite），
并写入示例数据。你之后只需向 phones.db 中录入真实机型即可，
程序无需改动。表结构见文件末尾 init_db() 里的 CREATE TABLE 语句。
"""

import os
import re
import webbrowser
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import sys
if getattr(sys, "frozen", False):          # 打包成 exe 后，数据库放在 exe 同目录
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "phones.db")
PORT = 8000

# 故障选项配置：
#   price_field -> 数据库中对应的维修价格字段
#   factor      -> 折损系数
PROBLEMS = {
    "A": {"label": "续航问题",        "price_field": "battery_price",       "factor": 1.0},
    "B": {"label": "设备卡顿",        "price_field": "motherboard_price",   "factor": 0.5},
    "C": {"label": "屏幕问题",        "price_field": "screen_price",        "factor": 0.5},
    "D": {"label": "听筒问题",        "price_field": "earpiece_price",      "factor": 1.0},
    "E": {"label": "扬声器问题",      "price_field": "speaker_price",       "factor": 1.0},
    "F": {"label": "充电口问题",      "price_field": "charging_port_price",  "factor": 1.0},
    "G": {"label": "摄像头问题",      "price_field": "camera_price",        "factor": 0.2},
    "H": {"label": "其他问题/单纯想换", "price_field": None,                "factor": None},
}

# ---------------------------------------------------------------- 数据库

SCHEMA = """
CREATE TABLE IF NOT EXISTS phone_models (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand           TEXT    NOT NULL,               -- 品牌，如 苹果 / 华为 / 小米
    model           TEXT    NOT NULL,               -- 型号，如 iPhone 15 Pro
    base_life_years REAL    NOT NULL DEFAULT 5,     -- 基准总寿命（年）
    battery_price       REAL,   -- A 续航：电池换新价
    motherboard_price   REAL,   -- B 卡顿：主板换新价
    screen_price        REAL,   -- C 屏幕换新价
    earpiece_price      REAL,   -- D 听筒换新价
    speaker_price       REAL,   -- E 扬声器换新价
    charging_port_price REAL,   -- F 充电口换新价
    camera_price        REAL    -- G 摄像头换新价
);
"""

# 示例数据（仅演示用，随时可删/改）
SEED = [
    ("苹果", "iPhone 15 Pro", 5,  529, 3200, 2299, 199, 299, 199, 999),
    ("苹果", "iPhone 14",      5,  359, 2600, 1699, 149, 229, 149, 799),
    ("华为", "Mate 60 Pro",    5,  369, 2999, 1779, 169, 269, 159, 899),
    ("华为", "Pura 70",        5,  329, 2499, 1499, 149, 229, 139, 699),
    ("小米", "14 Pro",         4,  159, 1999, 1099,  99, 159,  99, 499),
    ("OPPO", "Find X7",        4,  179, 2199, 1299, 109, 169, 109, 549),
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    count = conn.execute("SELECT COUNT(*) FROM phone_models").fetchone()[0]
    if count == 0:
        conn.executemany(
            """INSERT INTO phone_models
               (brand, model, base_life_years, battery_price, motherboard_price,
                screen_price, earpiece_price, speaker_price, charging_port_price, camera_price)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            SEED,
        )
    conn.commit()
    conn.close()


def search_phone(text):
    """按用户输入的“品牌+型号”模糊搜索，返回第一条匹配记录或 None。"""
    kw = re.sub(r"\s+", " ", text.strip())
    if not kw:
        return None
    like = "%" + kw.replace("%", r"\%").replace("_", r"\_") + "%"
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT * FROM phone_models
           WHERE brand || ' ' || model LIKE ?
              OR brand LIKE ? OR model LIKE ?
           LIMIT 1""",
        (like, like, like),
    ).fetchone()
    conn.close()
    return row


def get_phone(phone_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM phone_models WHERE id = ?", (phone_id,)).fetchone()
    conn.close()
    return row


# ---------------------------------------------------------------- 页面

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","PingFang SC",sans-serif;
       min-height:100vh; display:flex; align-items:center; justify-content:center;
       background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); padding:24px; }
.card { background:#fff; border-radius:20px; padding:36px 32px; width:100%; max-width:460px;
        box-shadow:0 20px 60px rgba(0,0,0,.25); }
h1 { font-size:24px; color:#333; margin-bottom:6px; text-align:center; }
.sub { text-align:center; color:#999; font-size:13px; margin-bottom:26px; }
.step { display:inline-block; background:#667eea; color:#fff; font-size:12px;
        border-radius:20px; padding:3px 12px; margin-bottom:18px; }
label.q { display:block; font-size:17px; color:#333; margin:14px 0 10px; font-weight:bold; }
input[type=text], input[type=number] { width:100%; padding:13px 14px; font-size:16px;
        border:1.5px solid #ddd; border-radius:12px; outline:none; transition:.2s; }
input:focus { border-color:#667eea; }
button { width:100%; margin-top:24px; padding:14px; font-size:17px; color:#fff;
        background:linear-gradient(135deg,#667eea,#764ba2); border:none; border-radius:12px;
        cursor:pointer; transition:.2s; }
button:hover { opacity:.9; transform:translateY(-1px); }
.err { background:#ffeaea; color:#d33; font-size:14px; border-radius:10px;
       padding:10px 14px; margin-top:14px; }
.ok  { background:#eaf4ff; color:#2b6cb0; font-size:14px; border-radius:10px;
       padding:10px 14px; margin-top:14px; }
.opt { display:block; border:1.5px solid #e5e5e5; border-radius:12px; padding:13px 15px;
       margin:9px 0; cursor:pointer; transition:.15s; font-size:15px; color:#444; }
.opt:hover { border-color:#667eea; background:#f7f8ff; }
.opt input { margin-right:10px; accent-color:#667eea; }
.result-line { font-size:20px; color:#333; text-align:center; padding:16px;
        border-radius:12px; background:#f5f6fa; margin-top:14px; }
.result-line b { color:#764ba2; font-size:24px; }
.result-big { font-size:18px; color:#333; text-align:center; line-height:1.9; margin-top:8px; }
.info { background:#f0f4ff; border-radius:12px; padding:12px 16px; font-size:14px;
        color:#555; margin:14px 0; }
a.home { display:block; text-align:center; margin-top:26px; color:#667eea;
        text-decoration:none; font-size:14px; }
"""


def page(body):
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>手机换新攻略</title><style>{CSS}</style></head>
<body><div class="card">{body}</div></body></html>"""


def step1(error=""):
    body = f"""
    <h1>📱 手机换新攻略</h1>
    <div class="sub">三步搞定，看看修还是换更划算</div>
    <span class="step">第 1 步 / 共 3 步</span>
    <label class="q">你的旧手机：</label>
    <form method="post" action="/search">
      <input type="text" name="phone" placeholder="请输入品牌和型号，例如：苹果 iPhone 15 Pro" autofocus>
      {f'<div class="err">{error}</div>' if error else ''}
      <button type="submit">搜索我的机型</button>
    </form>"""
    return page(body)


def step2(phone, error=""):
    body = f"""
    <h1>📱 手机换新攻略</h1>
    <div class="sub">三步搞定，看看修还是换更划算</div>
    <span class="step">第 2 步 / 共 3 步</span>
    <div class="ok">已为你找到机型：{phone['brand']} {phone['model']}</div>
    <label class="q">您已使用____年</label>
    <form method="post" action="/years">
      <input type="number" name="years" step="0.1" min="0" max="20" placeholder="例如 2.5" autofocus>
      <input type="hidden" name="phone_id" value="{phone['id']}">
      {f'<div class="err">{error}</div>' if error else ''}
      <button type="submit">下一步</button>
    </form>"""
    return page(body)


def step3(phone, years):
    opts = "".join(
        f'<label class="opt"><input type="radio" name="problem" value="{k}" required>'
        f"{k}. {v['label']}</label>"
        for k, v in PROBLEMS.items()
    )
    body = f"""
    <h1>📱 手机换新攻略</h1>
    <div class="sub">三步搞定，看看修还是换更划算</div>
    <span class="step">第 3 步 / 共 3 步</span>
    <div class="info">{phone['brand']} {phone['model']}　·　已使用 {years:g} 年</div>
    <label class="q">旧手机当前最困扰你的问题：</label>
    <form method="post" action="/problem">
      {opts}
      <input type="hidden" name="phone_id" value="{phone['id']}">
      <input type="hidden" name="years" value="{years}">
      <button type="submit">查看结果</button>
    </form>"""
    return page(body)


def result(phone, years, key):
    cfg = PROBLEMS[key]
    if key == "H":
        # H：不报维修价格，直接进入下一步（换新建议）
        body = f"""
        <h1>📱 手机换新攻略</h1>
        <div class="sub">分析完成</div>
        <div class="info">{phone['brand']} {phone['model']}　·　已使用 {years:g} 年　·　{cfg['label']}</div>
        <div class="result-big">
            既然是「其他问题 / 单纯想换」，<br>
            维修已没有意义，<br>
            👉 建议直接安排换新机！
        </div>
        <a class="home" href="/">← 再测一次</a>"""
        return page(body)

    price = phone[cfg["price_field"]]
    price_html = (
        f'<div class="result-line">维修价格：<b>¥{price:,.0f}</b></div>'
        if price is not None else
        '<div class="result-line">维修价格：暂无该机型此项目报价</div>'
    )
    if price is not None:
        remain = max(0.0, (phone["base_life_years"] - years) * cfg["factor"])
        body = f"""
        <h1>📱 手机换新攻略</h1>
        <div class="sub">分析完成</div>
        <div class="info">{phone['brand']} {phone['model']}　·　已使用 {years:g} 年　·　{cfg['label']}（折损系数 ×{cfg['factor']:g}）</div>
        {price_html}
        <div class="result-line">维修后预计还可使用 <b>{remain:.1f}</b> 年</div>
        <a class="home" href="/">← 再测一次</a>"""
    else:
        body = f"""
        <h1>📱 手机换新攻略</h1>
        <div class="sub">分析完成</div>
        <div class="info">{phone['brand']} {phone['model']}　·　已使用 {years:g} 年　·　{cfg['label']}</div>
        {price_html}
        <a class="home" href="/">← 再测一次</a>"""
    return page(body)


# ---------------------------------------------------------------- 路由

class Handler(BaseHTTPRequestHandler):
    def _send(self, html, status=200):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass  # 静默

    def do_GET(self):
        if self.path == "/":
            self._send(step1())
        else:
            self._send(step1("页面不存在"), status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        get = lambda k: (form.get(k, [""])[0]).strip()

        if self.path == "/search":
            phone = search_phone(get("phone"))
            if phone is None:
                self._send(step1("您的机型尚未收录"), status=404)
            else:
                self._send(step2(phone))

        elif self.path == "/years":
            try:
                years = float(get("years"))
                assert 0 <= years <= 30
            except (ValueError, AssertionError):
                phone = get_phone(int(get("phone_id") or 0))
                self._send(step2(phone, "请输入有效的使用年数"))
                return
            phone = get_phone(int(get("phone_id") or 0))
            if phone is None:
                self._send(step1("机型信息失效，请重新搜索"), status=404)
            else:
                self._send(step3(phone, years))

        elif self.path == "/problem":
            key = get("problem").upper()
            years = float(get("years"))
            phone = get_phone(int(get("phone_id") or 0))
            if phone is None or key not in PROBLEMS:
                self._send(step1("参数错误，请重新开始"), status=400)
            else:
                self._send(result(phone, years, key))
        else:
            self._send(step1("页面不存在"), status=404)


if __name__ == "__main__":
    init_db()
    print("手机换新攻略已启动： http://127.0.0.1:%d" % PORT)
    webbrowser.open_new_tab("http://127.0.0.1:%d" % PORT)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

