# -*- coding: utf-8 -*-
"""
手机换新攻略 —— 本地小应用（含数据管理后台）
--------------------------------
使用：
  用户端：   http://127.0.0.1:8000/        （品牌 → 系列 → 机型 三级点选）
  管理后台： http://127.0.0.1:8000/admin   （在这里增删机型数据）
"""

import os
import re
import sys
import html
import shutil
import webbrowser
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR
DB_PATH = os.path.join(BASE_DIR, "phones.db")
BUNDLED_DB = os.path.join(BUNDLE_DIR, "phones.db")
PORT = 8000

# 折损系数：A/D/E/F = 1.0；B/C = 0.2；G = 0.5
PROBLEMS = {
    "A": ("续航问题",       "battery_price",      1.0),
    "B": ("设备卡顿",       "motherboard_price",  0.2),
    "C": ("屏幕问题",       "screen_price",       0.2),
    "D": ("听筒问题",       "earpiece_price",     1.0),
    "E": ("扬声器问题",     "speaker_price",      1.0),
    "F": ("充电口问题",     "charging_port_price", 1.0),
    "G": ("摄像头问题",     "camera_price",       0.5),
    "H": ("其他问题/单纯想换", None,              None),
}
PRICE_FIELDS = [
    ("battery_price",       "电池价(A)"),
    ("motherboard_price",   "主板价(B)"),
    ("screen_price",        "屏幕价(C)"),
    ("earpiece_price",      "听筒价(D)"),
    ("speaker_price",       "扬声器价(E)"),
    ("charging_port_price", "充电口价(F)"),
    ("camera_price",        "摄像头价(G)"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS phone_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    series TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL,
    base_life_years REAL NOT NULL DEFAULT 5,
    battery_price REAL, motherboard_price REAL, screen_price REAL,
    earpiece_price REAL, speaker_price REAL, charging_port_price REAL, camera_price REAL
);
"""
SEED = [
    ("苹果", "iPhone", "iPhone 15 Pro", 5,  529, 3200, 2299, 199, 299, 199, 999),
    ("苹果", "iPhone", "iPhone 14",      5,  359, 2600, 1699, 149, 229, 149, 799),
    ("华为", "Mate",   "Mate 60 Pro",    5,  369, 2999, 1779, 169, 269, 159, 899),
    ("华为", "Pura",   "Pura 70",        5,  329, 2499, 1499, 149, 229, 139, 699),
    ("小米", "数字系列", "14 Pro",        4,  159, 1999, 1099,  99, 159,  99, 499),
    ("OPPO", "Find",   "Find X7",        4,  179, 2199, 1299, 109, 169, 109, 549),
]

def init_db():
    # 打包成 exe 时，首次运行先释放自带数据库，否则新建的空库没有 market_phones 表，
    # 「我想换新」会直接报 no such table
    if not os.path.exists(DB_PATH) and os.path.exists(BUNDLED_DB) and \
       os.path.abspath(BUNDLED_DB) != os.path.abspath(DB_PATH):
        try:
            shutil.copyfile(BUNDLED_DB, DB_PATH)
            print(f"已释放自带数据库 -> {DB_PATH}")
        except Exception as e:
            print(f"释放数据库失败: {e}")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # 老版本用户已有 phones.db（无 market_phones 表）：从自带库补建新表，不动原有数据
    try:
        has_mkt = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_phones'").fetchone()
        if not has_mkt and os.path.exists(BUNDLED_DB) and \
           os.path.abspath(BUNDLED_DB) != os.path.abspath(DB_PATH):
            src = sqlite3.connect(BUNDLED_DB)
            ddl = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='market_phones'").fetchone()
            data = src.execute("SELECT * FROM market_phones").fetchall()
            cols = [d[1] for d in src.execute("PRAGMA table_info(market_phones)")]
            idx = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='market_phones' "
                "AND sql IS NOT NULL").fetchall()
            src.close()
            if ddl and ddl[0]:
                conn.execute(ddl[0])
                ph = ",".join("?" * len(cols))
                conn.executemany(
                    f"INSERT INTO market_phones ({','.join(cols)}) VALUES ({ph})", data)
                for (s,) in idx:
                    try:
                        conn.execute(s)
                    except sqlite3.Error:
                        pass
                print(f"已为旧数据库补建 market_phones（{len(data)} 条）")
    except sqlite3.Error as e:
        print(f"补建 market_phones 失败（不影响原有功能）: {e}")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(phone_models)").fetchall()]
    if "series" not in cols:
        conn.execute("ALTER TABLE phone_models ADD COLUMN series TEXT NOT NULL DEFAULT ''")
    n = conn.execute("SELECT COUNT(*) FROM phone_models").fetchone()[0]
    if n == 0:
        conn.executemany(
            "INSERT INTO phone_models (brand,series,model,base_life_years,battery_price,motherboard_price,screen_price,earpiece_price,speaker_price,charging_port_price,camera_price) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            SEED)
    conn.commit(); conn.close()

def db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c

def get_phone(pid):
    c = db(); row = c.execute("SELECT * FROM phone_models WHERE id=?", (pid,)).fetchone(); c.close(); return row

def all_phones():
    c = db(); rows = c.execute("SELECT * FROM phone_models ORDER BY brand, series, id").fetchall(); c.close(); return rows

def list_brands():
    # iQOO 目前仅 1 款机型，首页品牌卡会出现落单，暂不展示（数据仍保留）
    c = db(); rows = c.execute("SELECT brand, COUNT(*) AS n FROM phone_models WHERE brand <> 'iQOO' GROUP BY brand ORDER BY brand").fetchall(); c.close(); return rows

def list_series(brand):
    c = db(); rows = c.execute("SELECT series, COUNT(*) AS n FROM phone_models WHERE brand=? GROUP BY series ORDER BY series", (brand,)).fetchall(); c.close(); return rows

def list_models(brand, series):
    c = db(); rows = c.execute("SELECT * FROM phone_models WHERE brand=? AND series=? ORDER BY model", (brand, series)).fetchall(); c.close(); return rows

def add_phone(d):
    c = db()
    c.execute("""INSERT INTO phone_models (brand,series,model,base_life_years,battery_price,motherboard_price,screen_price,earpiece_price,speaker_price,charging_port_price,camera_price)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (d["brand"], d["series"], d["model"], d["base_life_years"],
         d["battery_price"], d["motherboard_price"], d["screen_price"],
         d["earpiece_price"], d["speaker_price"], d["charging_port_price"], d["camera_price"]))
    c.commit(); c.close()

def del_phone(pid):
    c = db(); c.execute("DELETE FROM phone_models WHERE id=?", (pid,)); c.commit(); c.close()

# ---------------------------------------------------------------- 页面

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#ffffff;padding:24px}
.card{position:relative;z-index:10;background:#fff;border-radius:20px;padding:36px 32px;width:100%;max-width:520px;box-shadow:0 20px 60px rgba(0,0,0,.25)}
.card.wide{max-width:960px;padding:34px 30px 28px}
h1{font-size:24px;color:#333;margin-bottom:6px;text-align:center}
.sub{text-align:center;color:#999;font-size:13px;margin-bottom:22px}
.crumb{font-size:12px;color:#999;text-align:center;margin-bottom:16px}
.crumb a{color:#667eea;text-decoration:none}
.step{display:inline-block;background:#667eea;color:#fff;font-size:12px;border-radius:20px;padding:3px 12px;margin-bottom:16px}
label.q{display:block;font-size:17px;color:#333;margin:6px 0 14px;font-weight:bold;text-align:center}
input[type=text],input[type=number]{width:100%;padding:12px 14px;font-size:15px;border:1.5px solid #ddd;border-radius:12px;outline:none}
input:focus{border-color:#667eea}
button{width:100%;margin-top:18px;padding:13px;font-size:16px;color:#fff;background:linear-gradient(135deg,#667eea,#764ba2);border:none;border-radius:12px;cursor:pointer}
.err{background:#ffeaea;color:#d33;font-size:14px;border-radius:10px;padding:10px 14px;margin-top:14px;text-align:center}
.ok{background:#eaf4ff;color:#2b6cb0;font-size:14px;border-radius:10px;padding:10px 14px;margin-top:14px;text-align:center}
.opt{display:block;border:1.5px solid #e5e5e5;border-radius:12px;padding:12px 15px;margin:9px 0;cursor:pointer;font-size:15px;color:#444}
.opt:hover{border-color:#667eea;background:#f7f8ff}
.opt input{margin-right:10px;accent-color:#667eea}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:6px}
.card-item{border:1.5px solid #e5e5e5;border-radius:14px;padding:18px 10px;text-align:center;text-decoration:none;color:#333;display:block;transition:.15s}
.card-item:hover{border-color:#667eea;background:#f7f8ff;transform:translateY(-2px)}
.card-item .big{font-size:17px;font-weight:bold}
.card-item .small{font-size:12px;color:#999;margin-top:6px}
.model-card{border:1.5px solid #e5e5e5;border-radius:14px;padding:16px;margin:10px 0;display:flex;justify-content:space-between;align-items:center;gap:10px}
.model-card .info .name{font-size:16px;font-weight:bold;color:#333}
.model-card .info .meta{font-size:12px;color:#999;margin-top:4px}
.model-card .pick{flex-shrink:0;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;text-decoration:none;padding:9px 18px;border-radius:10px;font-size:14px}
.result-line{font-size:20px;color:#333;text-align:center;padding:16px;border-radius:12px;background:#f5f6fa;margin-top:14px}
.result-line b{color:#764ba2;font-size:24px}
.result-big{font-size:18px;color:#333;text-align:center;line-height:1.9;margin-top:8px}
.info{background:#f0f4ff;border-radius:12px;padding:12px 16px;font-size:14px;color:#555;margin:14px 0;text-align:center}
a.home{display:block;text-align:center;margin-top:22px;color:#667eea;text-decoration:none;font-size:14px}
.frog{position:fixed;bottom:0;width:400px;z-index:0;pointer-events:none;opacity:.9}
.frog-left{left:0}
.frog-right{right:0}

.cmp{display:block;text-align:center;margin-top:12px;padding:10px;background:#f0f4ff;color:#667eea;border-radius:10px;text-decoration:none;font-size:14px}
.cmp:hover{background:#e2e9ff}
.cmp-table{width:100%;border-collapse:collapse;font-size:13px;margin:14px auto}
.cmp-table th,.cmp-table td{border:1px solid #eee;padding:9px 10px;text-align:left;vertical-align:top}
.cmp-table th{background:#f5f6fa;text-align:center}
.cmp-table td.k{color:#999;width:88px}
.cmp-table tr.hl td{background:#faf7ff;font-weight:bold}
a.rec-box{text-decoration:none;color:inherit;display:block;cursor:pointer}
a.rec-box:hover{border-color:#667eea;box-shadow:0 6px 18px rgba(102,126,234,.25)}
.rec-slot{display:flex;flex-direction:column}


.res-bread{font-size:12px;color:#999;text-align:center;margin-bottom:18px}
.hero{background:linear-gradient(135deg,#667eea,#764ba2);border-radius:16px;padding:24px 20px;color:#fff;text-align:center}
.hero .verdict{font-size:24px;font-weight:700;letter-spacing:.5px}
.hero .reason{font-size:13px;opacity:.88;margin-top:9px;line-height:1.7}
.metrics{display:flex;margin:6px 0 4px}
.metric{flex:1;text-align:center;padding:16px 4px 6px}
.metric+.metric{border-left:1px solid #ececf0}
.metric .num{font-size:20px;font-weight:700;color:#2d2d2d;white-space:nowrap}
.metric .num.accent{color:#667eea}
.metric .num.none{color:#bbb;font-size:16px;font-weight:400}
.metric .lab{font-size:12px;color:#999;margin-top:7px}
details.more{background:transparent;margin-top:24px;border-top:1px solid #eee;padding-top:14px}
details.more summary{background:transparent;padding:6px 0;font-size:13px;color:#888;cursor:pointer;text-align:center;list-style:none;outline:none}
details.more summary::-webkit-details-marker{display:none}
details.more summary::after{content:" ▾"}
details[open].more summary::after{content:" ▴"}
.detail-body{font-size:12px;color:#888;line-height:1.9;margin-top:12px}
.detail-body .row{padding:2px 0}
.detail-body a{color:#667eea}
.btn-primary{display:block;text-align:center;margin-top:26px;padding:15px;background:#667eea;color:#fff;text-decoration:none;border-radius:12px;font-size:15px;font-weight:600}
.btn-primary:hover{background:#5a6fd8}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:14px}
th,td{border:1px solid #eee;padding:7px 8px;text-align:center}
th{background:#f5f6fa}
.del{display:inline-block;padding:4px 10px;background:#e53e3e;color:#fff;border-radius:6px;text-decoration:none;font-size:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid2 label{font-size:12px;color:#666}
.grid2 input{margin-top:4px}
/* ---- 我想换新 ---- */
.f-group{margin:16px 0}
.f-group>label{display:block;font-size:13px;color:#666;margin-bottom:7px;font-weight:600}
select{width:100%;padding:12px 14px;font-size:15px;border:1.5px solid #ddd;border-radius:12px;outline:none;background:#fff;color:#333;appearance:none;background-image:url("data:image/svg+xml;charset=utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath fill='%23999' d='M6 8 0 0h12z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 16px center}
select:focus{border-color:#667eea}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{position:relative;flex:1 1 calc(33.33% - 8px);min-width:88px}
.chip input{position:absolute;opacity:0;width:0;height:0}
.chip span{display:block;text-align:center;padding:10px 6px;border:1.5px solid #e5e5e5;border-radius:11px;font-size:13px;color:#555;cursor:pointer;transition:.15s}
.chip input:checked+span{border-color:#667eea;background:#667eea;color:#fff;font-weight:600}
.chip span:hover{border-color:#667eea}
.rec{border:1.5px solid #ececf0;border-radius:16px;padding:18px 16px;margin:14px 0;position:relative}
.rec .rank{position:absolute;top:-11px;left:16px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-size:12px;font-weight:700;border-radius:20px;padding:3px 12px;letter-spacing:.5px}
.rec h3{font-size:17px;color:#222;margin:6px 0 2px;line-height:1.4}
.rec .brandline{font-size:12px;color:#999}
.rec .price{font-size:22px;font-weight:700;color:#764ba2;margin:10px 0 2px}
.rec .price small{font-size:12px;font-weight:400;color:#999;margin-left:6px}
.rec .specs{font-size:12px;color:#777;line-height:1.8;margin-top:8px;padding-top:10px;border-top:1px dashed #eee}
.rec .specs b{color:#555;font-weight:600}
.why{margin-top:12px;background:#f8f9ff;border-radius:12px;padding:12px 14px}
.why .t{font-size:12px;color:#667eea;font-weight:700;margin-bottom:7px}
.why ul{list-style:none}
.why li{font-size:13px;color:#555;line-height:1.75;padding-left:16px;position:relative}
.why li::before{content:"✓";position:absolute;left:0;color:#667eea;font-weight:700}
.empty{text-align:center;padding:36px 10px;color:#888;font-size:14px;line-height:2}
.filterbar{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin:12px 0 4px}
.filterbar span{font-size:12px;background:#eef0ff;color:#5a6fd8;border-radius:20px;padding:4px 12px}
.count{text-align:center;font-size:13px;color:#999;margin:10px 0 2px}
.count b{color:#667eea;font-size:16px}
.btn-ghost{display:block;text-align:center;margin:12px auto 0;padding:13px 20px;background:#fff;color:#667eea;border:1.5px solid #667eea;border-radius:12px;font-size:15px;text-decoration:none;font-weight:600;max-width:300px}
.btn-ghost:hover{background:#f7f8ff}
.btn-row{display:flex;gap:12px;justify-content:center;margin-top:20px;flex-wrap:wrap}
.btn-row .btn-ghost{margin:0;flex:0 1 240px}
.btn-ghost.second{color:#8a8fa8;border-color:#dcdce8}
.btn-ghost.second:hover{background:#fafafd}
/* ---- 横排三款推荐 ---- */
.rec-wrap{display:flex;align-items:stretch;justify-content:center;gap:14px;margin:26px 0 6px;flex-wrap:wrap}
.rec-box{flex:1 1 200px;max-width:290px;min-width:180px;background:#fff;border:1.5px solid #e8e8f0;border-radius:18px;
padding:20px 16px 16px;position:relative;display:flex;flex-direction:column;transition:.2s;box-shadow:0 2px 10px rgba(102,126,234,.06)}
.rec-box:hover{transform:translateY(-4px);box-shadow:0 12px 28px rgba(102,126,234,.18);border-color:#c7cef5}
/* 第一名：抬高、加粗边框、居中放大 */
.rec-box.win{flex:1 1 220px;max-width:310px;border:2.5px solid #667eea;
box-shadow:0 10px 30px rgba(102,126,234,.28);padding-top:20px;z-index:2}
.rec-box.win::after{content:"";position:absolute;inset:0;border-radius:16px;pointer-events:none;
background:linear-gradient(180deg,rgba(102,126,234,.06),transparent 42%)}
.rec-box .crown{text-align:center;font-size:22px;line-height:1;margin-bottom:6px}
.rec-box .rank-tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.5px;border-radius:20px;
padding:3px 11px;margin-bottom:10px;background:#eef0ff;color:#5a6fd8}
.rec-box.win .rank-tag{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.rec-box h3{font-size:16px;color:#222;line-height:1.35;margin-bottom:3px;word-break:break-word}
.rec-box.win h3{font-size:18px}
.rec-box .brandline{font-size:11px;color:#aaa;margin-bottom:12px}
.rec-box .price{font-size:23px;font-weight:800;color:#6046c8;line-height:1.1;margin-bottom:2px}
.rec-box.win .price{font-size:27px}
.rec-box .price small{display:block;font-size:11px;font-weight:400;color:#bbb;margin-top:3px}
.rec-box .specs{font-size:11.5px;color:#777;line-height:1.95;margin:12px 0 0;padding-top:11px;border-top:1px dashed #ececf2;min-height:118px}
.rec-box .specs i{font-style:normal;color:#999;display:inline-block;min-width:34px}
.rec-box .specs em{font-style:normal;color:#444;font-weight:600}
.rec-box .why{margin-top:auto;padding-top:13px}
.rec-box .why .t{font-size:11px;color:#667eea;font-weight:700;margin-bottom:7px}
.rec-box .why ul{list-style:none}
.rec-box .why li{font-size:11.5px;color:#5f6577;line-height:1.7;padding-left:14px;position:relative;margin-bottom:1px}
.rec-box .why li::before{content:"✓";position:absolute;left:0;color:#667eea;font-weight:700;font-size:10px;top:1px}
/* 偏好芯片 */
.pref-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.pref{position:relative}
.pref input{position:absolute;opacity:0;width:0;height:0}
.pref span{display:block;text-align:center;padding:11px 4px;border:1.5px solid #e5e5e5;border-radius:12px;font-size:13px;color:#555;cursor:pointer;transition:.15s;line-height:1.3}
.pref span b{display:block;font-size:11px;font-weight:400;color:#aaa;margin-top:2px}
.pref input:checked+span{border-color:#667eea;background:#667eea;color:#fff;font-weight:700}
.pref input:checked+span b{color:rgba(255,255,255,.8)}
.pref span:hover{border-color:#667eea}
@media(max-width:620px){
  .rec-wrap{flex-direction:column;align-items:stretch}
  .rec-box,.rec-box.win{max-width:none;flex:1 1 auto}
  .rec-box.win{order:-1;transform:none}
}
"""

def page(body, title="手机换新攻略", wide=False):
    cls = "card wide" if wide else "card"
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{CSS}</style></head><body>
    <img class="frog frog-left" src="/frog1.jpeg" alt="">
    <img class="frog frog-right" src="/frog2.jpeg" alt="">
    <div class="{cls}">{body}</div></body></html>"""

def crumb(links):
    parts = []
    for t,u in links:
        parts.append(f'<a href="{u}">{t}</a>' if u else t)
    return '<div class="crumb">' + "  ›  ".join(parts) + "</div>"

# ------------------------------------------------ 第1步：品牌列表

def pick_brands():
    rows = list_brands()
    items = "".join(
        f'<a class="card-item" href="/brand?brand={r["brand"]}"><div class="big">{r["brand"]}</div><div class="small">已收录 {r["n"]} 款机型 ›</div></a>'
        for r in rows)
    return page(f"""
    <h1>📱 手机换新攻略</h1><div class="sub">看看修还是换更划算</div>
    <span class="step">第 1 步 / 共 3 步</span>
    <label class="q">你的旧手机是什么品牌？</label>
    <div class="grid">{items}</div>
    <a class="home" href="/new">🔄 已经决定换新？直接挑新机 →</a>""")

# ------------------------------------------------ 第1步：系列列表

def pick_series(brand):
    rows = list_series(brand)
    items = "".join(
        f'<a class="card-item" href="/series?brand={brand}&series={s["series"] or "未分组"}"><div class="big">{s["series"] or "未分组"}</div><div class="small">{s["n"]} 款机型 ›</div></a>'
        for s in rows)
    return page(f"""
    <h1>📱 手机换新攻略</h1><div class="sub">看看修还是换更划算</div>
    {crumb([("首页","/"),(brand,None)])}
    <span class="step">第 1 步 / 共 3 步</span>
    <label class="q">{brand} 的哪个系列？</label>
    <div class="grid">{items}</div>""")

# ------------------------------------------------ 第1步：具体机型

def pick_models(brand, series):
    real_series = "" if series == "未分组" else series
    rows = list_models(brand, real_series)
    cards = ""
    for r in rows:
        price_preview = f"电池参考价 ¥{r['battery_price']:,.0f}" if r["battery_price"] else ""
        release = f" · {r['release_year']}" if r["release_year"] else ""
        meta_parts = []
        if r["storage"]: meta_parts.append(r["storage"])
        if r["official_price_cny"] is not None: meta_parts.append(f"官方价 ¥{r['official_price_cny']:,.0f}")
        meta_extra = f"　{' · '.join(meta_parts)}" if meta_parts else ""
        cards += f"""<div class="model-card">
          <div class="info"><div class="name">{r["model"]}{release}</div>
          <div class="meta">{brand} · {r["series"] or "未分组"}　{price_preview}{meta_extra}</div></div>
          <a class="pick" href="/pick?id={r['id']}">选这个</a></div>"""
    return page(f"""
    <h1>📱 手机换新攻略</h1><div class="sub">看看修还是换更划算</div>
    {crumb([("首页","/"),(brand,f"/brand?brand={brand}"),(series,None)])}
    <span class="step">第 1 步 / 共 3 步</span>
    <label class="q">具体是哪一款？</label>
    {cards}""")

# ------------------------------------------------ 第2步：使用年数

def step2(phone, error=""):
    return page(f"""
    <h1>📱 手机换新攻略</h1><div class="sub">三步搞定</div>
    {crumb([("首页","/"),(phone['brand'],f"/brand?brand={phone['brand']}"),(phone['series'] or '未分组',None),(phone['model'],None)])}
    <span class="step">第 2 步 / 共 3 步</span>
    <div class="ok">已为你选定：{phone['brand']} {phone['model']}</div>
    <label class="q">您已使用____年</label>
    <form method="post" action="/years">
      <input type="number" name="years" step="0.1" min="0" max="30" placeholder="例如 2.5" autofocus>
      <input type="hidden" name="phone_id" value="{phone['id']}">
      {f'<div class="err">{error}</div>' if error else ''}
      <button type="submit">下一步</button>
    </form>""")

# ------------------------------------------------ 第3步：问题选择（多选）

def step3(phone, years):
    opts = "".join(f'<label class="opt"><input type="checkbox" name="problem" value="{k}">{k}. {v[0]}</label>' for k,v in PROBLEMS.items())
    return page(f"""
    <h1>📱 手机换新攻略</h1><div class="sub">三步搞定</div>
    <span class="step">第 3 步 / 共 3 步</span>
    <div class="info">{phone['brand']} {phone['model']}　·　已使用 {years:g} 年</div>
    <label class="q">旧手机当前最困扰你的问题（可多选）：</label>
    <form method="post" action="/problem">
      {opts}
      <input type="hidden" name="phone_id" value="{phone['id']}">
      <input type="hidden" name="years" value="{years}">
      <button type="submit">查看结果</button>
    </form>""")

# ------------------------------------------------ 结果页（多选）

RESIDUAL_RATES = {
    "苹果": [1.0, .62, .48, .36, .27, .20],
    "华为": [1.0, .55, .41, .29, .21, .15],
    "小米": [1.0, .50, .36, .25, .17, .11],
    "荣耀": [1.0, .48, .34, .23, .16, .10],
    "OPPO": [1.0, .48, .34, .23, .16, .10],
    "vivo": [1.0, .48, .34, .23, .16, .10],
    "iQOO": [1.0, .48, .34, .23, .16, .10],
    "一加": [1.0, .48, .34, .23, .16, .10],
    "三星": [1.0, .45, .31, .21, .14, .09],
    "realme": [1.0, .45, .30, .20, .13, .08],
    "_default": [1.0, .48, .34, .23, .16, .10],
}


def residual_estimate(brand, years, official):
    curve = RESIDUAL_RATES.get(brand, RESIDUAL_RATES["_default"])
    idx = 5 if years >= 5 else max(0, int(years))
    value = official * curve[idx] if official is not None else None
    return value, curve[idx], idx


def result_multi(phone, years, keys):
    bread = f'<div class="res-bread">{phone["brand"]} {phone["model"]} · 已使用 {years:g} 年</div>'
    # 底部按钮：换新入口 + 再测一次（H 分支用简单版；维修分支下面会重写带上下文的版本）
    btn = (f'<a class="btn-primary" href="/new?from={phone["id"]}">🔄 我想换新 →</a>'
           f'<a class="home" href="/">← 再测一次</a>')
    # 若选了 H
    if "H" in keys:
        res, rate, idx = residual_estimate(phone["brand"], years, phone["official_price_cny"])
        res_num = f"¥{res:,.0f}" if res is not None else "暂无"
        res_cls = "num" if res is not None else "num none"
        res_row = (f'<div class="row">旧机残值：按 {phone["brand"]} 第 {idx} 年保值率 {rate:.0%} 估算，'
                   f'非二手成交价。</div>') if res is not None else '<div class="row">旧机残值：缺少新机官方价，暂无法估算。</div>'
        return page(f"""<h1>📱 手机换新攻略</h1>
        {bread}
        <div class="hero"><div class="verdict">建议更换</div>
        <div class="reason">你选择了「其他问题／单纯想换」，维修已无必要。</div></div>
        <div class="metrics">
          <div class="metric"><div class="{res_cls}">{res_num}</div><div class="lab">旧机残值（估）</div></div>
          <div class="metric"><div class="num none">暂无</div><div class="lab">维修成本</div></div>
          <div class="metric"><div class="num none">暂无</div><div class="lab">预计剩余寿命</div></div>
        </div>
        <details class="more"><summary>查看完整信息</summary>
        <div class="detail-body">
          <div class="row">当前选择：其他问题／单纯想换</div>
          {res_row}
          <div class="row">维修成本：本次未选择可维修项，未计算。</div>
        </div></details>
        {btn}""")

    # 收集有效选项（有对应价格字段的）
    items = [(k, PROBLEMS[k]) for k in keys if k in PROBLEMS and PROBLEMS[k][1] is not None]
    if not items:
        return page(f"""<h1>📱 手机换新攻略</h1><div class="sub">请至少选择一项具体问题</div>
        <a class="home" href="/">← 返回重新选择</a>""")

    # 维修价格 = 各选项价格相加（无报价的项跳过）
    total_price = 0
    priced_items = []
    unpriced = []
    for k,(label,field,factor) in items:
        p = phone[field]
        if p is not None:
            total_price += p
            priced_items.append(f"{label} ¥{p:,.0f}")
        else:
            unpriced.append(label)

    # 折损系数 = 所有选项中最低的
    min_factor = min(v[2] for k,v in items)
    remain = max(0.0, (phone["base_life_years"] - years) * min_factor)
    has_price = bool(priced_items)

    # 结论判定顺序：寿命已尽 → 无报价 → 数据可信度 → 残值/换新净成本 → 建议维修
    official = phone["official_price_cny"]
    residual, rate, idx = residual_estimate(phone["brand"], years, official)
    res_num = f"¥{residual:,.0f}" if residual is not None else "暂无"
    res_cls = "num" if residual is not None else "num none"
    if residual is not None:
        res_row = (f'<div class="row">旧机残值：按 {phone["brand"]} 第 {idx} 年保值率 {rate:.0%} 估算，'
                   f'非二手成交价；换新净成本约 ¥{max(official - residual, 0):,.0f}。</div>')
    else:
        res_row = '<div class="row">旧机残值：缺少新机官方价，暂无法估算。</div>'
    scope = phone["price_scope"] if "price_scope" in phone.keys() else None

    if remain <= 0.05:
        verdict = "建议更换"
        reason = "修后预计剩余寿命为 0 年"
        reason += f"，维修仍需约 ¥{total_price:,.0f}。" if has_price else "。"
    elif not has_price:
        verdict, reason = "数据不足，仅供参考", "该机型缺少维修报价，无法判断修与换的性价比。"
    elif scope == "demo":
        verdict, reason = "数据不足，仅供参考", "该机型维修价为早期演示值，未经官方核实，结论不作依据。"
    elif residual is not None and total_price >= residual:
        verdict, reason = "建议更换", f"维修约 ¥{total_price:,.0f}，已超过旧机估算残值 ¥{residual:,.0f}。"
    elif residual is not None and 0 < official - residual <= total_price:
        verdict, reason = "建议更换", f"维修约 ¥{total_price:,.0f}，换新净成本仅约 ¥{official - residual:,.0f}，换新更划算。"
    elif official is not None and total_price / remain > official / 5.0:
        # 把维修费按剩余寿命分摊，与新机官方价按 5 年分摊对比（与对比页口径一致）
        old_per_year = total_price / remain
        new_per_year = official / 5.0
        verdict = "建议更换"
        reason = (f"维修约 ¥{total_price:,.0f}，按剩余 {remain:.1f} 年折算每年约 ¥{old_per_year:,.0f}；"
                  f"新机按 5 年分摊每年约 ¥{new_per_year:,.0f}，换新更划算。")
    else:
        verdict = "建议维修"
        reason = f"维修约 ¥{total_price:,.0f}，修后预计还能用 {remain:.1f} 年。"
        if unpriced:
            reason += f"注意：{'、'.join(unpriced)}暂无报价，实际成本可能被低估。"

    # 机型档案（仅展示已录入的字段）
    spec_parts = []
    if phone["soc"]: spec_parts.append(phone["soc"])
    if phone["screen"]: spec_parts.append(phone["screen"])
    if phone["camera"]: spec_parts.append("影像 " + phone["camera"])
    if phone["battery_mah"]: spec_parts.append(f"{phone['battery_mah']}mAh")
    spec_text = " · ".join(spec_parts) if spec_parts else "暂无"
    off_text = "暂无"
    if official is not None:
        ver = f"（{phone['storage']}）" if phone["storage"] else ""
        off_text = f"¥{official:,.0f}{ver}"
    price_detail = "、".join(priced_items) if priced_items else "无可用报价"
    if unpriced:
        price_detail += f"；未含：{'、'.join(unpriced)}（暂无报价）"

    scope_text = {"full": "含人工官方维修价", "parts": "官方配件价（不含人工）",
                  "mixed": "混合口径（含官方与第三方价）", "market": "第三方维修参考价（非官方）",
                  "demo": "演示数据（未经官方核实）"}
    scope_row = f'<div class="row">维修价口径：{scope_text[scope]}，明细见备注。</div>' if scope in scope_text and has_price else ""

    src = phone["source_url"] or ""
    source_row = ""
    if src.startswith(("http://", "https://")):
        source_row = f'<div class="row">数据来源：<a href="{html.escape(src, quote=True)}" target="_blank" rel="noopener">查看原文</a></div>'
    note_row = f'<div class="row">备注：{html.escape(phone["data_note"])}</div>' if phone["data_note"] else ""

    cost_num = f"¥{total_price:,.0f}" if has_price else "暂无"
    cost_cls = "num" if has_price else "num none"
    life_num = f"{remain:.1f} 年"
    life_cls = "num accent" if remain > 0.05 else "num"
    btn = (f'<a class="btn-primary" href="/new?from={phone["id"]}&years={years:g}&repair={total_price:g}&remain={remain:g}">🔄 对比换新机（含维修差价）→</a>'
           f'<a class="home" href="/">← 再测一次</a>')

    return page(f"""<h1>📱 手机换新攻略</h1>
    {bread}
    <div class="hero"><div class="verdict">{verdict}</div><div class="reason">{reason}</div></div>
    <div class="metrics">
      <div class="metric"><div class="{res_cls}">{res_num}</div><div class="lab">旧机残值（估）</div></div>
      <div class="metric"><div class="{cost_cls}">{cost_num}</div><div class="lab">维修成本</div></div>
      <div class="metric"><div class="{life_cls}">{life_num}</div><div class="lab">预计剩余寿命</div></div>
    </div>
    <details class="more"><summary>查看完整信息</summary>
    <div class="detail-body">
      <div class="row">设备参数：{spec_text}</div>
      <div class="row">新机官方参考价：{off_text}</div>
      <div class="row">维修明细：{price_detail}</div>
      {scope_row}
      <div class="row">寿命口径：剩余寿命 =（基准寿命 {phone['base_life_years']:g} 年 − 已用 {years:g} 年）× 折损系数 {min_factor:g}；多选时取最低系数。</div>
      {res_row}
      {note_row}
      {source_row}
    </div></details>
    {btn}""")

# ================================================================ 我想换新
#
# 数据源：market_phones 表（437 款在售机型，独立于 phone_models 维修库）
# 三个筛选维度：价格区间 / 品牌 / 是否支持快充
# ================================================================

# 价格区间（元）。上限含边界由 SQL 的 < 处理，最后一档不设上限。
PRICE_BUCKETS = [
    ("0-1500",   "1500 元以下",     0,     1500),
    ("1500-2500","1500 - 2500 元",  1500,  2500),
    ("2500-3500","2500 - 3500 元",  2500,  3500),
    ("3500-5000","3500 - 5000 元",  3500,  5000),
    ("5000-8000","5000 - 8000 元",  5000,  8000),
    ("8000+",    "8000 元以上",     8000,  None),
]
PRICE_MAP = {k: (label, lo, hi) for k, label, lo, hi in PRICE_BUCKETS}

# 快充档位。「快充」判定：有线充电功率 >= 33W（行业通行的快充起点）
FAST_CHARGE_MIN_W = 33
CHARGE_OPTS = [
    ("any",  "不限"),
    ("yes",  f"支持快充（≥{FAST_CHARGE_MIN_W}W）"),
    ("no",   f"不需要快充（<{FAST_CHARGE_MIN_W}W）"),
    ("100",  "100W 以上超级快充"),
]
CHARGE_MAP = dict(CHARGE_OPTS)

SORT_OPTS = [
    ("value",  "性价比优先"),
    ("cheap",  "价格最低"),
    ("charge", "充电最快"),
    ("cam",    "影像最强"),
    ("new",    "上市最新"),
]


def market_brands():
    """market_phones 里实际存在的品牌 + 数量（只列非空库）"""
    c = db()
    rows = c.execute("SELECT brand, COUNT(*) n FROM market_phones GROUP BY brand ORDER BY n DESC").fetchall()
    c.close()
    return rows


def market_stats():
    c = db()
    n = c.execute("SELECT COUNT(*) FROM market_phones").fetchone()[0]
    c.close()
    return n


def query_market(brand="", pmin=None, pmax=None, charge_mode="any"):
    """按三个维度筛选 market_phones。品牌为空 = 不限。"""
    sql = ["SELECT * FROM market_phones WHERE 1=1"]
    args = []
    if brand:
        sql.append("AND brand = ?")
        args.append(brand)
    if pmin is not None:
        sql.append("AND price_min IS NOT NULL AND price_min >= ?")
        args.append(pmin)
    if pmax is not None:
        sql.append("AND price_min IS NOT NULL AND price_min < ?")
        args.append(pmax)
    if charge_mode == "yes":
        sql.append("AND charge_wired_w IS NOT NULL AND charge_wired_w >= ?")
        args.append(FAST_CHARGE_MIN_W)
    elif charge_mode == "no":
        sql.append("AND (charge_wired_w IS NULL OR charge_wired_w < ?)")
        args.append(FAST_CHARGE_MIN_W)
    elif charge_mode == "100":
        sql.append("AND charge_wired_w IS NOT NULL AND charge_wired_w >= 100")
    c = db()
    rows = c.execute(" ".join(sql), args).fetchall()
    c.close()
    return rows


# 偏好维度：每组给出 (加权倍数, 理由标签)
# 倍数为 1.0 = 原始权重；用户选择后，相关维度分数放大，并优先写入推荐理由
PREF_DIMS = {
    # 键: (显示名, 副标题, 受影响的评分块)
    "balanced": ("均衡", "不偏科", []),
    "perf":     ("性能", "打游戏/多任务", ["perf"]),
    "camera":   ("摄影", "拍照/拍视频", ["cam"]),
    "battery":  ("续航", "少充电", ["battery"]),
    "charge":   ("快充", "充得快", ["charge"]),
    "value":    ("性价比", "预算内最强", ["value"]),
}
PREF_ORDER = ["balanced", "perf", "camera", "battery", "charge", "value"]


def _chip_score(chip):
    """根据芯片型号给性能分（0-40）。数据是文本，用关键词分级。"""
    if not chip:
        return 0.0
    s = chip.lower()
    # 苹果 A 系列（先判，避免 "a18" 被其他规则吃掉）
    if "a20" in s or "a19" in s:
        return 40.0
    if "a18" in s:
        return 39.0
    if "a17" in s:
        return 34.0
    if "a16" in s:
        return 31.0
    if "a15" in s:
        return 25.0
    if "a14" in s:
        return 20.0
    # 高通骁龙：先判档位高的，"8s" 属次旗舰必须排在 "gen4/gen5" 之前判
    if "8s gen" in s or "8sgen" in s:
        return 32.0
    if "8 elite" in s or "8elite" in s or "8 gen 5" in s or "8gen5" in s:
        return 38.0
    if "8 gen 4" in s or "8gen4" in s:
        return 37.0
    if "8 gen 3" in s or "8gen3" in s:
        return 34.0
    if "8 gen 2" in s or "8gen2" in s:
        return 30.0
    if "8 gen 1" in s or "888" in s:
        return 25.0
    if "870" in s:
        return 22.0
    if "gen 5" in s or "gen5" in s:
        return 30.0          # 骁龙 7/6 系 Gen5 等
    if "gen 4" in s or "gen4" in s:
        return 28.0
    if "7+" in s or "7 gen" in s:
        return 20.0
    if "6 gen" in s:
        return 12.0
    if "695" in s or "680" in s:
        return 10.0
    # 联发科天玑
    if "天玑 9" in s or "dimensity 9" in s:
        return 36.0
    if "天玑 8" in s or "dimensity 8" in s:
        return 26.0
    if "天玑 7" in s or "dimensity 7" in s:
        return 16.0
    # 麒麟
    if "9020" in s or "9010" in s or "9000" in s:
        return 28.0
    if "麒麟" in s or "kirin" in s:
        return 18.0
    # 泛称兜底
    if "骁龙" in s or "snapdragon" in s:
        return 20.0
    if "天玑" in s or "dimensity" in s:
        return 18.0
    return 10.0


def _score_phone(r, pmin, pmax, prefs=None):
    """给单款机打分。prefs 为多选偏好列表，命中的维度并集 ×2.2。"""
    score = 0.0
    why = []
    prefs = prefs or ["balanced"]
    # 偏好倍数：所有勾选项的维度取并集，命中 ×2.2
    boost = set()
    for pf in prefs:
        boost.update(PREF_DIMS.get(pf, ("", "", []))[2])
    B = 2.2

    # ---- 充电（基础满分 30：连续，28W→0 分，120W→30 分）----
    w = r["charge_wired_w"] or 0
    ch = 0.0
    ch_txt = ""
    if w > 0:
        ch = max(0.0, min(30.0, (w - 28) / 92.0 * 30.0))
    if w >= 100:
        ch_txt = f"{w:.0f}W 超级快充，充满通常 20 分钟内"
    elif w >= 60:
        ch_txt = f"{w:.0f}W 快充，半小时左右回血"
    elif w >= FAST_CHARGE_MIN_W:
        ch_txt = f"{w:.0f}W 支持快充"
    if "charge" in boost:
        ch *= B
    score += ch
    if ch_txt:
        why.append(("charge", ch_txt))

    # ---- 影像（基础满分 25：主摄像素数 18 分 + 镜头数 7 分）----
    mp = r["rear_cam_mp"] or 0
    cnt = r["rear_cam_count"] or 1
    cam = 0.0
    if mp:
        # 12MP → 6 分，50MP → 15 分，200MP → 18 分（对数免得 200MP 无脑碾压）
        import math as _m
        cam = max(0.0, min(18.0, 6.0 + _m.log2(mp / 12.0) * 3.6))
    if cnt >= 3:
        cam += 7
    elif cnt == 2:
        cam += 3
    if "cam" in boost:
        cam *= B
    score += cam
    if mp >= 50:
        tag = "、三摄起步" if cnt >= 3 else ""
        extra = "，放大细节更耐裁切" if mp >= 200 else ""
        why.append(("cam", f"{mp:.0f}MP 主摄{tag}{extra}"))

    # ---- 电池（基础满分 20：容量连续 12 分 + 官方续航 8 分）----
    bat = r["battery_mah"] or 0
    ba = 0.0
    ba_txt = ""
    if bat:
        # 4000mAh → 0 分，10000mAh → 12 分，线性拉开差距
        ba = max(0.0, min(12.0, (bat - 4000) / 6000.0 * 12.0))
    life = r["endurance_h"] or 0
    if life:
        # endurance_h 语义不统一（部分为待机/混合时长），只做小幅修正，最多 ±3 分
        # 且仅当容量接近时才有区分意义，避免 42h 这类待机值碾压 10000mAh
        ba += max(-3.0, min(3.0, (life - 20) / 10.0 * 3.0))
    if bat >= 7000:
        ba_txt = f"{bat}mAh 超大电池，重度用一天不焦虑"
    elif bat >= 5500:
        ba_txt = f"{bat}mAh 大电池，续航扎实"
    elif bat >= 4800:
        ba_txt = ""
    if "battery" in boost:
        ba *= B
    score += ba
    if ba_txt:
        why.append(("battery", ba_txt))

    # ---- 性能（基础满分 40，芯片分级）----
    pf = _chip_score(r["chipset"])
    if "perf" in boost:
        pf *= B
    score += pf
    if pf > 0 and r["chipset"]:
        why.append(("perf", f"{r['chipset']} 处理器，性能有保障"))

    # ---- 屏幕（基础满分 8）----
    scr = r["screen_inch"] or 0
    if 6.1 <= scr <= 6.9:
        score += 8
    elif scr > 0:
        score += 4

    # ---- 存储（基础满分 10）----
    rom = r["rom_gb"] or 0
    rm = 0.0
    if rom >= 512:
        rm = 10
        why.append(("value", f"{rom:.0f}GB 存储，装得多用得住"))
    elif rom >= 256:
        rm = 8
    elif rom >= 128:
        rm = 4
    if "value" in boost:
        rm *= B
    score += rm

    # ---- 价格贴合度（基础满分 15）----
    price = r["price_min"]
    pv = 0.0
    if price and pmin is not None and pmax is not None:
        mid = (pmin + pmax) / 2
        span = (pmax - pmin) / 2 or 1
        closeness = max(0.0, 1 - abs(price - mid) / span)
        pv = 15 * closeness
        if price <= mid:
            why.append(("value", f"到手价 ¥{price:,.0f}，在预算区间内偏实惠"))
    elif price and pmax is not None and price <= pmax * 0.75:
        pv = 12
        why.append(("value", f"到手价 ¥{price:,.0f}，预算充裕"))
    elif price and pmin is not None:
        pv = 8
        why.append(("value", f"到手价 ¥{price:,.0f}，定位旗舰"))
    elif price:
        lo_main, hi_main = 2000.0, 5000.0
        if lo_main <= price <= hi_main:
            pv = 15
            why.append(("value", f"到手价 ¥{price:,.0f}，处于主流换新预算段"))
        elif price < lo_main:
            pv = 9
            why.append(("value", f"到手价 ¥{price:,.0f}，预算友好"))
        else:
            pv = max(0.0, 15 - (price - hi_main) / 700.0)
            if price >= 8000:
                why.append(("value", f"到手价 ¥{price:,.0f}，定位高端旗舰"))
    if "value" in boost:
        pv *= B
    score += pv

    # ---- 上市时间（基础满分 8，不加权）----
    yr = r["release_year"] or 0
    if yr >= 2026:
        score += 8
        why.append(("new", "2026 年新机，系统更新周期最长"))
    elif yr == 2025:
        score += 6
        why.append(("new", "2025 年机型，仍是当前主力"))
    elif yr == 2024:
        score += 3

    # ---- 排序理由：偏好维度优先，其次综合，最后兜底 ----
    pref_keys = boost if boost else set()
    ordered = [t for k, t in why if k in pref_keys]
    ordered += [t for k, t in why if k not in pref_keys]
    # 去重保序
    seen, final = set(), []
    for t in ordered:
        if t not in seen:
            seen.add(t)
            final.append(t)

    # 兜底：理由太少时补充芯片/系统层面
    if len(final) < 3:
        if r["chipset"]:
            t = f"搭载 {r['chipset']}，性能余量足"
            if t not in seen:
                final.append(t); seen.add(t)
        if r["os"] and len(final) < 3:
            t = f"系统 {r['os']}，软件生态成熟"
            if t not in seen:
                final.append(t)

    return score, final[:5]


def recommend(rows, brand, pmin, pmax, charge_mode, prefs=None, limit=3):
    """打分 + 品牌多样性（同一品牌最多 2 席，确保三款不是同一家）"""
    prefs = prefs or ["balanced"]
    scored = []
    for r in rows:
        try:
            s, why = _score_phone(r, pmin, pmax, prefs)
        except Exception:
            # 单款数据异常不能拖垮整个页面
            s, why = 0.0, []
        scored.append({"row": r, "score": s, "why": why})
    scored.sort(key=lambda x: (-x["score"], x["row"]["price_min"] or 9e9))

    # 品牌多样性：若用户不限品牌，同一品牌最多出现 2 次
    picked = []
    brand_cnt = {}
    for item in scored:
        b = item["row"]["brand"]
        if not brand and brand_cnt.get(b, 0) >= 2:
            continue
        picked.append(item)
        brand_cnt[b] = brand_cnt.get(b, 0) + 1
        if len(picked) >= limit:
            break
    # 不够 3 款就放宽限制补齐
    if len(picked) < limit:
        for item in scored:
            if item not in picked:
                picked.append(item)
                if len(picked) >= limit:
                    break
    return picked


def spec_line(r):
    """紧凑参数行（适配横向窄卡片）"""
    parts = []
    if r["chipset"]:
        chip = r["chipset"]
        chip = chip.replace("海思 ", "").replace("高通 ", "").replace("联发科 ", "")
        parts.append(f"<i>芯片</i><em>{html.escape(chip)}</em>")
    if r["screen_inch"]:
        parts.append(f"<i>屏幕</i><em>{r['screen_inch']:g}\"</em>")
    if r["battery_mah"]:
        parts.append(f"<i>电池</i><em>{r['battery_mah']}mAh</em>")
    if r["charge_wired_w"]:
        parts.append(f"<i>充电</i><em>{r['charge_wired_w']:g}W</em>")
    if r["rear_cam_mp"]:
        parts.append(f"<i>后摄</i><em>{r['rear_cam_mp']:g}MP</em>")
    if r["ram_gb"] and r["rom_gb"]:
        parts.append(f"<i>内存</i><em>{r['ram_gb']:g}+{r['rom_gb']:g}GB</em>")
    if r["weight_g"]:
        parts.append(f"<i>重量</i><em>{r['weight_g']:g}g</em>")
    return "<br>".join(parts)


def new_phone_form(brand="", price="", charge="any", err="", pref="balanced", old_id="", years="", repair="", remain=""):
    """筛选表单页（/new）"""
    mrows = market_brands()
    opts_brand = '<option value="">不限品牌（全部 %d 款）</option>' % market_stats()
    for b in mrows:
        sel = " selected" if b["brand"] == brand else ""
        opts_brand += f'<option value="{html.escape(b["brand"])}"{sel}>{html.escape(b["brand"])}（{b["n"]} 款）</option>'

    opts_price = '<option value="">不限价格</option>'
    for k, label, lo, hi in PRICE_BUCKETS:
        sel = " selected" if k == price else ""
        opts_price += f'<option value="{k}"{sel}>{label}</option>'

    chips = ""
    for k, label in CHARGE_OPTS:
        ck = " checked" if k == (charge or "any") else ""
        chips += f'<label class="chip"><input type="radio" name="charge" value="{k}"{ck}><span>{label}</span></label>'

    # ④ 使用偏好（可多选；已选列表以 | 分隔传入）
    sel = set((pref or "balanced").split("|"))
    prefs = ""
    for k in PREF_ORDER:
        name, sub = PREF_DIMS[k][0], PREF_DIMS[k][1]
        ck = " checked" if k in sel else ""
        prefs += (f'<label class="pref"><input type="checkbox" name="pref" value="{k}"{ck}>'
                  f'<span>{name}<b>{sub}</b></span></label>')

    return page(f"""
    <h1>🔄 我想换新</h1><div class="sub">按你的条件，从 {market_stats()} 款在售机型里挑</div>
    <form method="post" action="/new/result">
      <div class="f-group"><label>① 预算价格</label>
        <select name="price">{opts_price}</select></div>
      <div class="f-group"><label>② 品牌</label>
        <select name="brand">{opts_brand}</select></div>
      <div class="f-group"><label>③ 是否需要快充</label>
        <div class="chips">{chips}</div></div>
      <div class="f-group"><label>④ 你更看重什么？</label>
        <div class="pref-grid">{prefs}</div></div>
      <input type="hidden" name="old_id" value="{old_id}">
      <input type="hidden" name="years" value="{years}">
      <input type="hidden" name="repair" value="{repair}">
      <input type="hidden" name="remain" value="{remain}">
      {f'<div class="err">{err}</div>' if err else ''}
      <button type="submit">看看推荐哪几款 →</button>
    </form>
    <a class="home" href="/">← 返回首页</a>""")


def new_phone_result(brand, price_key, charge_mode, pref="balanced", old_id="", years="", repair="", remain=""):
    """筛选结果页（/new/result）。pref 支持 | 分隔的多选。"""
    label, pmin, pmax = PRICE_MAP.get(price_key, ("不限价格", None, None)) if price_key else ("不限价格", None, None)
    rows = query_market(brand, pmin, pmax, charge_mode)
    prefs = [p for p in (pref or "balanced").split("|") if p in PREF_DIMS] or ["balanced"]
    picked = recommend(rows, brand, pmin, pmax, charge_mode, prefs)

    # 已选条件回显
    pref_name = "、".join(PREF_DIMS.get(p, PREF_DIMS["balanced"])[0] for p in prefs)
    tags = [
        f"<span>💰 {label}</span>",
        f"<span>🏷️ {html.escape(brand) if brand else '不限品牌'}</span>",
        f"<span>⚡ {CHARGE_MAP.get(charge_mode, '不限')}</span>",
        f"<span>🎯 偏好{pref_name}</span>",
    ]
    bar = '<div class="filterbar">' + "".join(tags) + "</div>"

    back = '<a class="btn-ghost" href="/new">← 修改筛选条件</a>'

    if not rows:
        body = f"""
        <h1>🔄 换新推荐</h1>{bar}
        <div class="empty">😕 没有完全符合条件的机型<br>
        试试放宽预算，或把「快充」改成「不限」</div>
        {back}
        <a class="home" href="/">← 返回首页</a>"""
        return page(body, wide=True)

    cnt = f'<div class="count">共筛出 <b>{len(rows)}</b> 款，为你精选 3 款</div>'

    if not picked:
        body = f"""<h1>🔄 换新推荐</h1>{bar}{cnt}
        <div class="empty">条件组合下没有可推荐机型，请放宽条件重试</div>
        <div class="btn-row">{back}<a class="btn-ghost second" href="/">← 返回首页</a></div>"""
        return page(body, wide=True)

    # 横排三款：第一名居中。DOM 顺序 [第2名, 第1名, 第3名] → flex 自然排列后第一名落正中
    medals = {0: ("最值得买", "👑"), 1: ("性价比之选", "🥈"), 2: ("也不错", "🥉")}
    order = [1, 0, 2] if len(picked) >= 3 else [0, 1][:len(picked)]
    boxes = []
    for pos in order:
        if pos >= len(picked):
            continue
        item = picked[pos]
        r = item["row"]
        rank, crown = medals.get(pos, ("推荐", "•"))
        price_txt = f"¥{r['price_min']:,.0f}" if r["price_min"] else "暂无报价"
        yr = f" · {r['release_year']}" if r["release_year"] else ""
        why_li = ("".join(f"<li>{html.escape(w)}</li>" for w in item["why"])
                  if item["why"] else "<li>符合你设定的全部条件</li>")
        win = " win" if pos == 0 else ""
        # 皇冠位：三张卡都保留同样高度，避免只有第一名多一行导致标题/价格不齐
        crown_html = f'<div class="crown">{crown if pos == 0 else "&nbsp;"}</div>'
        cmp_btn = ""
        if years:
            cmp_btn = (f'<a class="cmp" href="/compare?new_id={r["id"]}&old_id={old_id}'
                       f'&years={years}&repair={repair}&remain={remain}">📊 拿这款和我的旧机对比 →</a>')
        zol = r["zol_url"] or ""
        zol_attr = f'href="{html.escape(zol, quote=True)}" target="_blank" rel="noopener"' if zol else 'href="#"'
        boxes.append(f"""<div class="rec-slot">
        <a class="rec-box{win}" {zol_attr} title="查看 ZOL 详细参数">
          {crown_html}
          <div class="rank-tag">{rank} #{pos+1}</div>
          <h3>{html.escape(r['model'])}</h3>
          <div class="brandline">{html.escape(r['brand'])}{yr}</div>
          <div class="price">{price_txt}<small>参考到手价 · 点击看 ZOL 参数</small></div>
          <div class="specs">{spec_line(r)}</div>
          <div class="why"><div class="t">推荐理由</div><ul>{why_li}</ul></div>
        </a>
          {cmp_btn}
        </div>""")

    cards = '<div class="rec-wrap">' + "".join(boxes) + "</div>"

    body = f"""
    <h1>🔄 换新推荐</h1>{bar}{cnt}
    {cards}
    <div class="btn-row">{back}<a class="btn-ghost second" href="/">← 返回首页</a></div>"""
    return page(body, wide=True)



def get_market_phone(pid):
    c = db(); row = c.execute("SELECT * FROM market_phones WHERE id=?", (pid,)).fetchone(); c.close(); return row


def compare_page(new_id, old_id, years, repair, remain):
    """维修 vs 换新 对比页"""
    np_ = get_market_phone(new_id)
    op = get_phone(old_id)
    if not np_ or not op:
        return page('<h1>📊 对比页</h1><div class="info">参数无效，请重新走流程</div><a class="home" href="/">← 返回首页</a>')
    try:
        years_f = float(years); repair_f = float(repair) if repair else 0.0; remain_f = float(remain)
    except Exception:
        years_f, repair_f, remain_f = 0.0, 0.0, 0.0

    NEW_LIFE = 5.0
    new_price = np_["price_min"] or 0
    extra_years = max(0.0, NEW_LIFE - remain_f)
    old_per_year = repair_f / remain_f if remain_f > 0.05 and repair_f > 0 else None
    new_per_year = new_price / NEW_LIFE if new_price else None

    def trow(label, old_v, new_v, hl=False):
        cls = ' class="hl"' if hl else ""
        return f"<tr{cls}><td class='k'>{label}</td><td>{old_v}</td><td>{new_v}</td></tr>"

    rows = ""
    rows += trow("机型", f'{op["brand"]} {op["model"]}', f'{np_["brand"]} {np_["model"]}')
    rows += trow("芯片", html.escape(op["soc"] or "—"), html.escape(np_["chipset"] or "—"), hl=True)
    rows += trow("屏幕", html.escape(op["screen"] or "—"),
                 (f'{np_["screen_inch"]:g} 英寸' if np_["screen_inch"] else "—"))
    rows += trow("电池", (f'{op["battery_mah"]}mAh' if op["battery_mah"] else "—"),
                 (f'{np_["battery_mah"]}mAh' if np_["battery_mah"] else "—"), hl=True)
    if np_["endurance_h"]:
        rows += trow("续航", "—", f'约 {np_["endurance_h"]:g} 小时')
    rows += trow("后摄", html.escape(op["camera"] or "—"), html.escape(np_["rear_cam_detail"] or (f'{np_["rear_cam_mp"]:g}MP' if np_["rear_cam_mp"] else "—")))
    rows += trow("充电", "—", (f'{np_["charge_wired_w"]:g}W 有线' if np_["charge_wired_w"] else "—"))
    repair_txt = f"¥{repair_f:,.0f}" if repair_f > 0 else "未计算"
    rows += trow("一次性花费", f"维修 {repair_txt}",
                 (f"购机 ¥{new_price:,.0f}" if new_price else "暂无报价"), hl=True)
    rows += trow("预计还能用", f"{remain_f:.1f} 年", f"约 {NEW_LIFE:g} 年", hl=True)
    rows += trow("比维修多用", "—", f"<b>多 {extra_years:.1f} 年</b>", hl=True)
    if old_per_year:
        npy = f"¥{new_per_year:,.0f}/年" if new_per_year else "—"
        rows += trow("折合每年成本", f"¥{old_per_year:,.0f}/年", npy)

    if old_per_year and new_per_year and new_per_year < old_per_year:
        verdict = f"换新更划算：每年约 ¥{new_per_year:,.0f} ＜ 维修 ¥{old_per_year:,.0f}"
    elif old_per_year:
        verdict = (f"维修每年约 ¥{old_per_year:,.0f}，新机每年约 ¥{new_per_year:,.0f}"
                   if new_per_year else "维修后剩余寿命很短，请自行权衡")
    else:
        verdict = "维修后剩余寿命为 0，建议直接换新"

    return page(f"""<h1>📊 维修 vs 换新</h1>
    <div class="sub">{html.escape(op["model"])}（修） vs {html.escape(np_["model"])}（换）</div>
    <div class="hero"><div class="verdict" style="font-size:18px">{verdict}</div></div>
    <table class="cmp-table">
      <tr><th></th><th>旧机 · 维修方案</th><th>新机 · 直接购买</th></tr>
      {rows}
    </table>
    <a class="home" href="/new">← 修改筛选，另选一款</a>
    <a class="home" href="/">← 返回首页</a>""", wide=True)


# ------------------------------------------------------------ 后台


def admin(msg=""):
    rows = all_phones()
    trs = ""
    for r in rows:
        year = r["release_year"] if r["release_year"] else "—"
        ver = r["storage"] or "—"
        off = "—" if r["official_price_cny"] is None else "¥" + format(r["official_price_cny"], ",.0f")
        trs += f"<tr><td>{r['brand']}</td><td>{r['series'] or '—'}</td><td>{r['model']}</td><td>{year}</td><td>{ver}</td><td>{off}</td><td>{r['base_life_years']:g}</td>"
        for f,_ in PRICE_FIELDS:
            v = r[f]
            trs += f"<td>{'—' if v is None else '¥'+format(v,',.0f')}</td>"
        trs += f'<td><a class="del" href="/admin/delete?id={r["id"]}" onclick="return confirm(\'确定删除 {r["brand"]} {r["model"]} ？\')">删除</a></td></tr>'
    price_inputs = "".join(
        f'<div><label>{lbl}</label><input type="number" step="1" name={f} placeholder="留空=无报价"></div>'
        for f,lbl in PRICE_FIELDS)
    return page(f"""
    <h1>⚙️ 数据管理后台</h1><div class="sub">在这里增删机型，保存后立即生效</div>
    {f'<div class="ok">{msg}</div>' if msg else ''}
    <label class="q" style="text-align:left">添加新机型</label>
    <form method="post" action="/admin/add">
      <div class="grid2">
        <div><label>品牌（如 苹果）</label><input type="text" name="brand" required></div>
        <div><label>系列（如 iPhone）</label><input type="text" name="series" placeholder="可留空"></div>
        <div><label>型号（如 iPhone 15）</label><input type="text" name="model" required></div>
        <div><label>基准总寿命(年)</label><input type="number" step="0.5" name="base_life_years" value="5" required></div>
      </div>
      <div class="grid2" style="margin-top:10px">{price_inputs}</div>
      <button type="submit">＋ 添加机型</button>
    </form>
    <label class="q" style="text-align:left;margin-top:26px">已收录机型（共 {len(rows)} 款）</label>
    <div style="overflow-x:auto">
    <table><tr><th>品牌</th><th>系列</th><th>型号</th><th>年份</th><th>版本</th><th>官方价</th><th>寿命</th>{''.join(f'<th>{lbl}</th>' for _,lbl in PRICE_FIELDS)}<th>操作</th></tr>{trs}</table>
    </div>
    <a class="home" href="/">← 返回用户首页</a>""")

# ---------------------------------------------------------------- 路由

class Handler(BaseHTTPRequestHandler):
    def _send(self, html, status=200):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def log_message(self,*a): pass
    def _form(self):
        return parse_qs(self.rfile.read(int(self.headers.get("Content-Length",0))).decode("utf-8"))
    def _get(self, form, k): return form.get(k,[""])[0].strip()
    def _nums(self, form, k): return form.get(k, [])  # 多选返回列表
    def _num(self, v):
        v = v.strip()
        return float(v) if v else None

    def do_GET(self):
        path = self.path.split("?")[0]
        q = parse_qs(self.path.split("?")[1]) if "?" in self.path else {}
        g = lambda k: q.get(k,[""])[0]

        if path in ("/frog1.jpeg", "/frog2.jpeg"):
            fname = {"frog1.jpeg": "奶蛙1.jpeg", "frog2.jpeg": "奶蛙2.jpeg"}[path.lstrip("/")]
            try:
                with open(os.path.join(BASE_DIR, fname), "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data)
            except Exception:
                self.send_response(404); self.end_headers()
            return

        if path == "/": return self._send(pick_brands())
        if path == "/brand":  return self._send(pick_series(g("brand")))
        if path == "/series": return self._send(pick_models(g("brand"), g("series")))
        if path == "/pick":
            ph = get_phone(int(g("id") or 0))
            return self._send(step2(ph) if ph else pick_brands())
        if path == "/admin": return self._send(admin())
        if path == "/new":
            # from=旧机 id：从维修报告跳过来时，预填该品牌（若市场库有同名品牌）
            fb = g("brand")
            frm = g("from")
            if frm.isdigit():
                op = get_phone(int(frm))
                if op and not fb:
                    mb = {x["brand"] for x in market_brands()}
                    if op["brand"] in mb:
                        fb = op["brand"]
            return self._send(new_phone_form(brand=fb, price=g("price"), charge=g("charge") or "any",
                                             pref=g("pref") or "balanced",
                                             old_id=frm if frm.isdigit() else "",
                                             years=g("years"), repair=g("repair"), remain=g("remain")))
        if path == "/compare":
            return self._send(compare_page(g("new_id"), g("old_id"), g("years"), g("repair"), g("remain")))
        if path == "/admin/delete":
            del_phone(int(g("id") or 0))
            return self._send(admin("已删除"))
        return self._send(page("页面不存在"), 404)

    def do_POST(self):
        form = self._form(); g = lambda k: self._get(form,k)
        if self.path == "/years":
            try:
                years = float(g("years")); assert 0 <= years <= 30
            except:
                ph = get_phone(int(g("phone_id") or 0))
                return self._send(step2(ph,"请输入有效的使用年数"))
            ph = get_phone(int(g("phone_id") or 0))
            return self._send(step3(ph,years) if ph else pick_brands())
        if self.path == "/problem":
            years = float(g("years"))
            ph = get_phone(int(g("phone_id") or 0))
            keys = [k.strip().upper() for k in form.get("problem", []) if k.strip()]
            if not ph or not keys:
                return self._send(page("参数错误，请重新开始"))
            return self._send(result_multi(ph, years, keys))
        if self.path == "/new/result":
            brand = g("brand")
            price_key = g("price")
            charge_mode = g("charge") or "any"
            pref = "|".join(dict.fromkeys(form.get("pref", ["balanced"]))) or "balanced"
            if price_key and price_key not in PRICE_MAP:
                return self._send(new_phone_form(brand, price_key, charge_mode, "价格区间无效", pref))
            if charge_mode not in CHARGE_MAP:
                charge_mode = "any"
            # pref 现为 | 分隔的多选，new_phone_result 内部会校验每个值
            return self._send(new_phone_result(brand, price_key, charge_mode, pref,
                                               old_id=g("old_id"), years=g("years"),
                                               repair=g("repair"), remain=g("remain")))
        if self.path == "/admin/add":
            d = {"brand":g("brand"),"series":g("series"),"model":g("model"),
                 "base_life_years":float(g("base_life_years") or 5)}
            for f,_ in PRICE_FIELDS: d[f] = self._num(g(f))
            if not d["brand"] or not d["model"]: return self._send(admin("品牌和型号必填"), 400)
            add_phone(d)
            return self._send(admin(f"已添加：{d['brand']} {d['model']}"))

if __name__ == "__main__":
    init_db()
    print(f"用户端: http://127.0.0.1:{PORT}/   |   管理后台: http://127.0.0.1:{PORT}/admin")
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("=" * 55)
        print(f"  端口 {PORT} 被占用 —— 还有一个【手机换新攻略】的黑窗口没关！")
        print("  请先找到之前弹出的黑色小窗口，点右上角 x 关掉它，")
        print("  然后再重新双击本程序。")
        print("=" * 55)
        input("按回车键退出...")
        sys.exit(1)
    webbrowser.open_new_tab(f"http://127.0.0.1:{PORT}/")
    httpd.serve_forever()
