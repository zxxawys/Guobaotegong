# 手机换新攻略

本地小应用，无需安装任何第三方库（Python 3.8+ 自带）。

## 运行
```
python app.py
```
浏览器打开： http://127.0.0.1:8000

## 流程
1. 输入旧手机品牌和型号 → 数据库搜索；搜不到提示「您的机型尚未收录」
2. 输入「您已使用__年」
3. 选择题：A 续航 / B 卡顿 / C 屏幕 / D 听筒 / E 扬声器 / F 充电口 / G 摄像头 / H 其他
4. 输出「维修价格：」+「维修后预计还可使用_年」

- 维修后剩余年数 =（基准总寿命 - 已使用年数）× 折损系数
- 折损系数：A/D/E/F = 1；B/C = 0.5；G = 0.2
- H 不输出维修价格，直接显示「建议换新」

## 数据库说明（你之后自己写数据时看这里）
首次运行会自动生成 `phones.db`（SQLite），表结构如下：

| 字段 | 含义 | 对应选项 |
|---|---|---|
| brand | 品牌（如 苹果） | — |
| model | 型号（如 iPhone 15 Pro） | — |
| base_life_years | 基准总寿命（年） | 公式里的「基准总寿命」 |
| battery_price | 电池换新价 | A |
| motherboard_price | 主板换新价 | B |
| screen_price | 屏幕换新价 | C |
| earpiece_price | 听筒换新价 | D |
| speaker_price | 扬声器换新价 | E |
| charging_port_price | 充电口换新价 | F |
| camera_price | 摄像头换新价 | G |

直接用 Navicat / DB Browser / sqlite3 往这张表里 INSERT 真实数据即可，程序不用改。
示例数据仅供演示，可全部删除。
