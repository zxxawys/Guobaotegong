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
import webbrowser
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "phones.db")
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
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
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
    c = db(); rows = c.execute("SELECT brand, COUNT(*) AS n FROM phone_models GROUP BY brand ORDER BY brand").fetchall(); c.close(); return rows

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
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#667eea,#764ba2);padding:24px}
.card{background:#fff;border-radius:20px;padding:36px 32px;width:100%;max-width:520px;box-shadow:0 20px 60px rgba(0,0,0,.25)}
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
"""

def page(body, title="手机换新攻略"):
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{CSS}</style></head><body><div class="card">{body}</div></body></html>"""

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
    <div class="grid">{items}</div>""")

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
    btn = '<a class="btn-primary" href="/">再测一次</a>'
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

        if path == "/": return self._send(pick_brands())
        if path == "/brand":  return self._send(pick_series(g("brand")))
        if path == "/series": return self._send(pick_models(g("brand"), g("series")))
        if path == "/pick":
            ph = get_phone(int(g("id") or 0))
            return self._send(step2(ph) if ph else pick_brands())
        if path == "/admin": return self._send(admin())
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
