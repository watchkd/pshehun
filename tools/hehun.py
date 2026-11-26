#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hehun.py — 合婚书「排盘 + 排印」器（盘叔合婚 / pshehun 技能包）

定位
----
**只管排盘与排印，不出断语。**
断语由上层模型按六轴流程生成后以 JSON 传入（--duan），本器负责校验、排盘、渲染 HTML。
断盘与排印物理分离：脚本内没有任何吉凶判断，凡结论性文字一律来自 duan.json。

入口（两级）
------------
公历生日入口（首推）：
    python hehun.py --male-date 1984-11-12 --male-time 14:00 --male-name 男方 \\
                    --female-date 1994-11-27 --female-time 02:00 --female-name 女方 \\
                    --duan duan.json --out 合婚书.html

四柱入口（来客直接报四柱时）：
    python hehun.py --male-pillars 甲子 乙亥 庚戌 癸未 \\
                    --female-pillars 甲戌 乙亥 丁巳 辛丑 \\
                    --duan duan.json --out 合婚书.html

可选：--lon 116.4（两人共用经度；不给则按北京时间，报告标注「未校正」）

退出码
------
0  成功
1  排盘器报错（四柱不合法等），此时不渲染任何 HTML
2  输入校验失败（缺时刻、同性、日期非法、duan 缺 zongduan.text 等）

依赖：仅标准库。排盘调用同目录 paipan.py（原样移植，不改一行）。
"""

import argparse
import base64
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import paipan  # noqa: E402  同目录排盘器


# ======================================================================
# 一、样式：命书 CSS 整段复制 + 合婚增量
# ======================================================================
CSS_BASE = r"""
  :root{
    --paper:#fbf9f3; --ink:#1b1a17; --ink2:#4a463f; --red:#8c1c13;
    --line:#c9c1ae; --soft:#efe9db;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; padding:0 0 60px;
    background:#e8e4da;
    font-family:"Songti SC","SimSun","Source Han Serif SC","Noto Serif CJK SC",serif;
    color:var(--ink); line-height:1.9; font-size:15.5px;
  }
  .sheet{
    max-width:820px; margin:28px auto; background:var(--paper);
    padding:56px 62px 72px; box-shadow:0 2px 24px rgba(0,0,0,.14);
    border-top:6px solid var(--red);
  }
  header{text-align:center; margin-bottom:8px;}
  .kicker{font-size:12.5px; letter-spacing:.5em; color:var(--red); margin-bottom:18px;}
  h1{font-size:40px; letter-spacing:.18em; margin:0 0 6px; font-weight:600;}
  /* 命稿抬头：盲派原书排法（乾坤造／干支两行／大运横排），不加边框、不加底色 */
  .minggao{margin:16px 0 4px; text-align:center;}
  table.mg{margin:0 auto; width:auto; border:none; background:none; border-collapse:collapse;}
  table.mg th{border:none; background:none; padding:0 14px 0 0; text-align:right;
    width:3em; font-weight:normal; font-size:12.5px; color:var(--ink2); letter-spacing:.12em;
    white-space:nowrap; vertical-align:middle;}
  table.mg td{border:none; background:none; width:2.5em; text-align:center; padding:1px 0;
    font-size:27px; line-height:1.5; letter-spacing:0; vertical-align:middle;}
  table.mg td.gz{font-weight:600;}
  .tbl table.lly td:nth-child(-n+4), .tbl table.lly th:nth-child(-n+4){white-space:nowrap;}
  .tbl table.lly td:nth-child(5){text-align:left;}
  .note.jy{color:var(--ink); border-left:2px solid var(--red); padding-left:9px;}
  .klab2{font-size:12.5px; color:var(--red); letter-spacing:.12em;
    margin:22px 0 8px; padding-top:12px; border-top:1px solid var(--line);}
  .mg-yun{font-size:12px; color:var(--ink); letter-spacing:0;
    text-align:center; margin:15px 0 0; word-spacing:0;}
  .mg-yun .yn{display:inline-block; white-space:nowrap; margin:0 .16em;}
  .mg-yun .now{font-style:normal; color:var(--red); font-size:11px;
    vertical-align:super; margin-left:1px; letter-spacing:0;}
  .mg-yun .klab{color:var(--red); letter-spacing:.1em; margin-right:6px;
    white-space:nowrap;}
  .mg-yun b{font-weight:600;}
  .sub{font-size:13px; color:var(--ink2); letter-spacing:.2em;}
  .meta{text-align:center; font-size:13px; color:var(--ink2); margin:10px 0 30px;}
  blockquote{
    margin:0 0 34px; padding:14px 18px; background:#f4efe3;
    border-left:3px solid var(--red); font-size:13.5px; color:var(--ink2);
    line-height:1.85;
  }
  blockquote p{text-indent:0; margin:0 0 6px;}
  blockquote p:last-child{margin-bottom:0;}
  h2{
    font-size:19px; letter-spacing:.14em; margin:46px 0 18px; padding-bottom:8px;
    border-bottom:1px solid var(--line); font-weight:600;
  }
  h2 .no{color:var(--red); margin-right:.6em; font-size:15px;}
  h3{font-size:15.5px; margin:26px 0 8px; letter-spacing:.1em; color:var(--red); font-weight:600;}
  p{margin:0 0 14px; text-align:justify; text-indent:2em;}
  p.flat{text-indent:0;}
  table{width:100%; border-collapse:collapse; margin:18px 0 22px; font-size:13.5px; line-height:1.7;}
  th,td{border:1px solid var(--line); padding:8px 10px; text-align:center;}
  th{background:var(--soft); font-weight:600; letter-spacing:.06em;}
  td.l{text-align:left;}
  .hi{color:var(--red); font-weight:600;}
  .note{font-size:13px; color:var(--ink2);}
  .yun{border-left:2px solid var(--line); padding:2px 0 2px 20px; margin:0 0 22px;}
  .yun > b{display:block; font-size:15px; letter-spacing:.1em; margin-bottom:6px;}
  .yun p{text-indent:0; margin:0 0 10px;}
  .yun.now{border-left:2px solid var(--red); background:#fdf9f2; padding-left:18px;
    border-radius:0 4px 4px 0;}
  ol.yao{margin:0 0 14px; padding-left:0; list-style:none; counter-reset:y;}
  ol.yao li{position:relative; padding-left:2.4em; margin-bottom:14px; text-align:justify;}
  ol.yao li:before{
    counter-increment:y; content:counter(y,upper-roman);
    position:absolute; left:0; top:0; color:var(--red); font-size:13px; letter-spacing:.05em;
  }
  ul.plain{margin:0 0 14px; padding-left:1.6em;}
  ul.plain li{margin-bottom:8px; text-align:justify;}
  ul.kong li{margin-bottom:14px; line-height:1.9;}
  .klab{display:inline-block; width:2.2em; color:var(--ink2); font-size:12px;
    letter-spacing:.1em;}
  .wx .lab{display:inline-block; width:2.2em; font-weight:600;}
  .wx .bar{display:inline-block; height:12px; border-radius:3px; vertical-align:middle;
    margin:0 8px; min-width:5px;}
  .wx .n{font-size:12.5px; color:var(--ink2);}
  .c-jin{background:#cdb03a;} .c-mu{background:#6da35f;} .c-shui{background:#5f8fb4;}
  .c-huo{background:#bf4536;} .c-tu{background:#b08a5a;}
  .tag{display:inline-block; border:1px solid var(--red); color:var(--red); border-radius:3px;
    padding:1px 8px; font-size:12px; letter-spacing:.12em; margin:0 5px; vertical-align:middle;}
  .tag.now{background:var(--red); color:#fff;}
  details{margin:18px 0 10px; border:1px solid var(--line); border-radius:6px;
    overflow:hidden; background:#fdfbf5;}
  details summary{cursor:pointer; padding:10px 16px; font-size:13px; letter-spacing:.1em;
    color:var(--red); background:var(--soft); user-select:none;}
  details table{margin:10px 0;}
  footer{margin-top:52px; padding-top:18px; border-top:1px solid var(--line);
    font-size:12.5px; color:var(--ink2); line-height:1.8; text-align:center; letter-spacing:.2em;}
  .promo{margin-top:46px; border:1px solid var(--line); background:#fdf9f0;
    padding:28px 34px 24px; text-align:center;}
  .promo .ptitle{font-size:12px; color:var(--red); letter-spacing:.5em; margin:0 0 18px;}
  .promo p{font-size:13.5px; line-height:2; color:var(--ink); text-align:center; margin:0 0 10px;}
  .promo p.body{text-align:justify; text-indent:2em; font-size:13px; line-height:1.95;}
  .promo a{color:var(--red); text-decoration:none; border-bottom:1px solid rgba(140,28,19,.35);}
  .promo .qrs{display:flex; justify-content:center; align-items:flex-start;
    gap:30px; margin:16px 0 6px; flex-wrap:wrap;}
  .promo figure{margin:0;}
  .promo figure img{display:block; background:#fff; border:1px solid var(--line); padding:7px;}
  .promo figure.wx img{width:116px;}
  .promo figure.pay img{width:152px;}
  .promo figcaption{font-size:11.5px; color:var(--ink2); letter-spacing:.2em; margin-top:8px;}
  .promo .adbox{margin:22px 0 8px; padding:20px 24px 10px; border:1px solid var(--line);
    background:#fff; text-align:left;}
  .promo .adbox h4{font-size:13.5px; color:var(--red); letter-spacing:.2em; font-weight:normal;
    text-align:center; margin:0 0 12px;}
  .promo .adbox p{text-align:left; font-size:13px; line-height:1.95; margin:0 0 10px;
    text-indent:2em;}
  .promo .adbox p.nind{text-indent:0; text-align:center;}
  .promo .adbox .cta{display:inline-block; margin-top:2px; padding:7px 20px;
    border:1px solid var(--red); border-radius:2px; letter-spacing:.14em; font-size:12.5px;}
  .promo .disc{font-size:11.5px; color:var(--ink2); margin-top:10px; letter-spacing:.1em;}
  .tbl{overflow-x:auto;}
  @media (max-width:720px){
    .sheet{padding:26px 15px 48px; margin:0;}
    .tbl table{font-size:12.5px;}
    .tbl th, .tbl td{white-space:nowrap; padding:7px 6px;}
    /* 流月表：与命局一列文字长，放开换行；前四列仍不拆字 */
    .tbl table.lly th, .tbl table.lly td{white-space:normal; padding:6px 5px;}
    .tbl table.lly td:nth-child(-n+4), .tbl table.lly th:nth-child(-n+4){white-space:nowrap;}
    .tbl table.lly td:nth-child(5){text-align:left; font-size:11.5px;}
    table.mg td{font-size:23px; width:2.3em;}
    table.mg th{font-size:11.5px; width:2.8em; padding-right:10px;}
    .mg-yun{font-size:12px;}
    .promo{padding:20px 16px 16px;}
    .promo .qrs{gap:20px; margin:12px 0 4px;}
    .promo figure.pay img{width:132px;}
    .promo figure.wx img{width:100px;}
    .promo .adbox{padding:15px 15px 8px;}
    .promo p.body, .promo .adbox p{font-size:12.5px; line-height:1.9;}
  }
  @media print{
    body{background:#fff;} .sheet{box-shadow:none; margin:0; max-width:none; padding:22mm 18mm;}
    .tbl{overflow:visible;} .tbl table{min-width:0; font-size:12.5px;}
    details > *{display:block !important;}
  }
"""

CSS_EXTRA = r"""
  /* ---- 合婚增量（只追加，不改上方既有规则） ---- */
  .mgs{display:flex; gap:34px; flex-wrap:wrap; margin:18px 0 4px;}
  .mgs > .minggao{flex:1 1 300px; min-width:280px;}
  .mgs .meta{margin:8px 0 0;}
  .mgs .meta + .meta{margin:4px 0 0;}
  .stars{color:var(--red); letter-spacing:.12em; font-size:13px;}
  .zong{font-size:15px; line-height:2; margin:0 0 6px;}
  .zong b{color:var(--red);}
  .item{margin:0 0 12px; padding-left:14px; border-left:2px solid rgba(140,28,19,.18);}
  .item .who{color:var(--red); font-size:12.5px; letter-spacing:.12em; margin-right:8px;}
  .item p{margin:0; font-size:14.5px; line-height:1.95; text-align:justify;}
  .src{font-size:11.5px; color:var(--ink2); letter-spacing:.05em; margin-top:3px;}
  .toc{font-size:12.5px; color:var(--ink2); letter-spacing:.1em; margin:14px 0 0;}
  .toc a{color:var(--ink2); text-decoration:none; border-bottom:1px dotted rgba(0,0,0,.25); margin-right:14px;}
  .dateline{text-align:right; font-size:12.5px; color:var(--ink2); letter-spacing:.2em; margin:26px 0 0;}
  /* 长文本表（应期、附录）：固定列宽 + 长列换行；首末两列不拆字，窄窗也不撑破 */
  .tbl.wrap table{table-layout:fixed;}
  .tbl.wrap th, .tbl.wrap td{white-space:normal;
    word-break:break-word; overflow-wrap:break-word;}
  .tbl.wrap th:first-child, .tbl.wrap td:first-child{width:7.5em;}
  .tbl.wrap th:last-child, .tbl.wrap td:last-child{width:5em; white-space:nowrap;}
  @media (max-width:720px){
    .mgs{flex-direction:column; gap:20px;}
    .mgs > .minggao{min-width:0;}
    .item p{font-size:13.5px;}
    /* 手机端：除首两列外单元格一律允许换行，长文本列不再把屏宽撑破 */
    .tbl:not(.wrap) th, .tbl:not(.wrap) td{white-space:normal;
      word-break:break-word; overflow-wrap:break-word; padding:7px 5px;}
    .tbl:not(.wrap) th:nth-child(1), .tbl:not(.wrap) td:nth-child(1),
    .tbl:not(.wrap) th:nth-child(2), .tbl:not(.wrap) td:nth-child(2){white-space:nowrap;}
    .tbl.wrap th:first-child, .tbl.wrap td:first-child{width:6em;}
    .tbl.wrap th:last-child, .tbl.wrap td:last-child{width:4.2em;}
  }
"""


# ======================================================================
# 二、推广尾注（合婚语境改写，每份报告只出现一次）
# ======================================================================
PROMO_TITLE = "合　婚　之　外"
PROMO_BODY = (
    "以上合婚书由<b>「盘叔盲派」技能包</b>排印，排盘与版式属结构计算；"
    "六轴断语出自《渊海子平》《三命通会》《五行精纪》《兰台妙选》《玉照定真经》"
    "《神峰通考》六部原文层，应期外挂盲派应期链。"
)
PROMO_ADBOX = [
    "合婚看的是两个人的结构能不能对上；但每一方自己的八字里，还藏着各自的性格底层、"
    "能力来路与人生阶段。如果你想单独把某一方的盘看透，欢迎体验一下盘叔历时半年、"
    "用精选的数千当代真人命例投喂训练出的「苍盘命书」智能体。苍盘命书专注于融合各派优势，"
    "通过独创的验盘算法，三重交叉校验每个命盘人生的真实喜用。",
    "它不靠模棱两可的话术、让你自己去「对号入座」，而是通过十个章节、数万字的细致分析，"
    "配合数据表格与趋势图，把八字结构、性格底层、人生阶段，以及未来可能的发展方向，"
    "尽可能清晰地一步步拆解出来。",
    "如果你也想看看，自己的八字背后，到底隐藏着怎样的人生轨迹——"
    "欢迎报名成为<b>【苍盘命书免费体验官】</b>。",
]
PROMO_CTA = ("https://mp.weixin.qq.com/s/9NFaItizyhEpjDzmTyEcPQ",
             "苍盘命书免费体验官 · 直通链接")

ASSETS_DIR = os.path.normpath(os.path.join(_HERE, "..", "assets"))
WARN = []


def _warn(msg):
    WARN.append(msg)
    sys.stderr.write("[warn] %s\n" % msg)


def _img_data_uri(name, alt):
    """二维码原图直转 base64（不重生成、不压缩）；缺图时降级为文字占位。"""
    path = os.path.join(ASSETS_DIR, name)
    if not os.path.exists(path):
        _warn("找不到二维码图片：%s（尾注以文字占位）" % path)
        return '<span class="note">［%s缺图］</span>' % alt
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return "data:image/jpeg;base64," + b64


# ======================================================================
# 三、输入层
# ======================================================================
GENDERS = ("男", "女")
WHO_ALLOWED = ("男方", "女方", "两人")


def build_parser():
    ap = argparse.ArgumentParser(
        description="合婚书排盘与排印器：只排盘、只排印，不出断语。",
        epilog="公历入口与四柱入口二选一；断语由上层模型按六轴流程生成后经 --duan 传入。",
    )
    # —— 公历入口
    ap.add_argument("--male-date", help="男方公历生日，YYYY-MM-DD")
    ap.add_argument("--male-time", help="男方出生时刻，HH:MM（必填，不猜午时）")
    ap.add_argument("--female-date", help="女方公历生日，YYYY-MM-DD")
    ap.add_argument("--female-time", help="女方出生时刻，HH:MM（必填，不猜午时）")
    # —— 四柱入口
    ap.add_argument("--male-pillars", nargs=4, metavar=("年", "月", "日", "时"),
                    help="男方四柱，如 甲子 乙亥 庚戌 癸未")
    ap.add_argument("--female-pillars", nargs=4, metavar=("年", "月", "日", "时"),
                    help="女方四柱，如 甲戌 乙亥 丁巳 辛丑")
    # —— 共用
    ap.add_argument("--male-name", default="男方", help="男方称谓（默认「男方」）")
    ap.add_argument("--female-name", default="女方", help="女方称谓（默认「女方」）")
    ap.add_argument("--male-gender", default="男", choices=list(GENDERS),
                    help="男方性别（默认「男」）")
    ap.add_argument("--female-gender", default="女", choices=list(GENDERS),
                    help="女方性别（默认「女」）")
    ap.add_argument("--lon", type=float, default=None,
                    help="出生地经度（东经为正，两人共用）；不给则按北京时间并在报告标注未校正")
    ap.add_argument("--duan", help="断语 JSON 路径（六轴断语，结构见 SKILL.md）")
    ap.add_argument("--out", default="合婚书.html", help="输出 HTML 路径")
    ap.add_argument("--title", default="合　婚　书", help="正文大标题（默认「合　婚　书」）")
    ap.add_argument("--kicker", default="双　盘　互　参", help="抬头小字（默认「双　盘　互　参」）")
    ap.add_argument("--self-test", action="store_true", help="只跑内置自检（排盘器 + 渲染器）")
    return ap


def _parse_date(s, side):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(_fail(2, "--%s-date %r 不是合法日期（须 YYYY-MM-DD，"
                                  "且日数在该月范围内）" % (side, s)))


def _parse_time(s, side):
    try:
        t = datetime.datetime.strptime(s, "%H:%M")
    except ValueError:
        raise SystemExit(_fail(2, "--%s-time %r 格式不对，须 HH:MM（24 小时制，"
                                  "00:00–23:59）" % (side, s)))
    if not (0 <= t.hour <= 23 and 0 <= t.minute <= 59):
        raise SystemExit(_fail(2, "--%s-time %r 越界：时 0–23、分 0–59" % (side, s)))
    return "%02d:%02d" % (t.hour, t.minute)


def _fail(code, msg):
    sys.stderr.write("[error] %s\n" % msg)
    return code


def _resolve_side(a, side, gender):
    """校验一造输入，返回 (mode, payload)。mode ∈ {"date", "pillars"}"""
    date_s = getattr(a, side + "_date")
    time_s = getattr(a, side + "_time")
    pillars = getattr(a, side + "_pillars")
    label = "男" if side == "male" else "女"

    if pillars:
        if date_s or time_s:
            raise SystemExit(_fail(
                2, "%s方输入二选一：给了 --%s-pillars 就不再传 --%s-date/--%s-time。"
                   "四柱入口不反推公历，公历入口不代客排盘。" % (label, side, side, side)))
        if len(pillars) != 4:
            raise SystemExit(_fail(2, "%s方四柱须为四组干支，实得 %d 组。"
                                      % (label, len(pillars))))
        return "pillars", {"pillars": pillars, "gender": gender,
                           "name": getattr(a, side + "_name")}

    if date_s and not time_s:
        raise SystemExit(_fail(
            2, "缺出生时间：不给时间就不排，不猜午时。%s方只有公历 %s，"
               "请补 --%s-time HH:MM。" % (label, date_s, side)))
    if time_s and not date_s:
        raise SystemExit(_fail(
            2, "%s方给了时刻 --%s-time %s 却没给公历日期，请补 --%s-date YYYY-MM-DD。"
               % (label, side, time_s, side)))
    if not date_s and not time_s:
        raise SystemExit(_fail(
            2, "%s方缺输入：须给 --%s-date 与 --%s-time 走公历入口，"
               "或给 --%s-pillars 四柱走四柱入口。" % (label, side, side, side)))

    d = _parse_date(date_s, side)
    t = _parse_time(time_s, side)
    return "date", {"date": d, "time": t, "gender": gender,
                    "name": getattr(a, side + "_name")}


def _run_paipan(mode, p, lon):
    """排盘。返回 r；r 含 error 时由调用方停手。"""
    if mode == "date":
        # 先探测函数名：新版直接给字符串入口，旧版只给 paipan(date, time, ...)
        fn = getattr(paipan, "paipan_from_date", None)
        if callable(fn):
            try:
                return fn(p["date"].isoformat(), p["time"], p["gender"],
                          lon=lon, name=p["name"])
            except TypeError:
                return fn(p["date"].isoformat(), p["time"], p["gender"], lon=lon)
        return paipan.paipan(p["date"], p["time"], p["gender"],
                             lon=lon, name=p["name"])
    fn = getattr(paipan, "paipan_from_pillars")
    return fn(p["pillars"], p["gender"], name=p["name"])


def _stop_on_error(who, r):
    """排盘器报错即停手：不出 HTML，不代改、不猜。"""
    if not r.get("error"):
        return
    out = ["", "=== 停手（%s）：%s ===" % (who, r["error"]), ""]
    for it in r.get("issues") or []:
        out.append("  · " + it)
    if r.get("checks"):
        out.append("  —— 自检清单 ——")
        for c in r["checks"]:
            out.append("  [%s] %s %s" % ("OK" if c.get("ok") else "NG",
                                         c.get("code", ""), c.get("msg", "")))
    out.append("")
    out.append("四柱有一柱不成立，十神、藏干、大运、空亡、关系皆无从算起，本次不渲染 HTML。")
    sys.stderr.write("\n".join(out) + "\n")
    raise SystemExit(1)


def load_duan(path):
    if not path:
        raise SystemExit(_fail(2, "缺 --duan：本器只排盘排印、不出断语，"
                                  "六轴断语须由上层模型生成后以 JSON 传入。"))
    if not os.path.exists(path):
        raise SystemExit(_fail(2, "找不到断语文件：%s" % path))
    try:
        with open(path, encoding="utf-8") as fh:
            duan = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SystemExit(_fail(2, "断语文件不是合法 JSON：%s" % exc))
    if not isinstance(duan, dict):
        raise SystemExit(_fail(2, "断语文件顶层须为对象（dict），实得 %s" % type(duan).__name__))
    zd = duan.get("zongduan") or {}
    if not (isinstance(zd, dict) and str(zd.get("text") or "").strip()):
        raise SystemExit(_fail(2, "断语缺 zongduan.text：总断是合婚书的第一段，"
                                  "缺它不出稿（其余字段可按缺降级）。"))
    return duan


# ======================================================================
# 四、渲染层
# ======================================================================
POS_CN = {"男": "乾造", "女": "坤造"}
WX_CLASS = {"木": "c-mu", "火": "c-huo", "土": "c-tu", "金": "c-jin", "水": "c-shui"}


def _stars(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n < 1 or n > 3:
        return ""
    return '<span class="stars">%s</span>' % ("★" * n)


def _label_of(r):
    return POS_CN.get((r.get("input") or {}).get("gender") or "", "命造")


def _src_note(r):
    """抬头标注：入口来源 + 真太阳时是否校正（缺经度不许沉默按北京时间）。"""
    inp = r.get("input") or {}
    if inp.get("mode") == "pillars" or not inp.get("date"):
        return "来客原报四柱"
    lon = inp.get("lon")
    if lon is None:
        return "未校正（按北京时间）"
    return ("已校正 经度 %.2f°E" % lon) if lon >= 0 else ("已校正 经度 %.2f°W" % abs(lon))


def _minggao(r):
    """命稿抬头：乾坤造 + 干支两行 + 大运横排（沿用命书排法）。"""
    lab = _label_of(r)
    p = r["pillars"]
    L = ['<div class="minggao">']
    L.append('<table class="mg">')
    L.append('<tr><th>%s</th>%s</tr>' % (
        lab, "".join('<td class="gz">%s</td>' % gz[0] for gz in p)))
    L.append('<tr><th></th>%s</tr>' % "".join(
        '<td class="gz">%s</td>' % gz[1] for gz in p))
    L.append('</table>')
    rows = r.get("dayun_rows") or []
    if rows:
        cells = []
        for row in rows:
            now = '<i class="now">今</i>' if row.get("now") else ""
            cells.append('<span class="yn"><b>%s</b> %s%s</span>'
                         % (row.get("xu1", ""), row.get("gz", ""), now))
        L.append('<p class="mg-yun"><span class="klab">大运</span>%s</p>' % "".join(cells))
    elif r.get("dayun"):
        cells = "".join('<span class="yn">%s</span>' % gz for gz in r["dayun"])
        L.append('<p class="mg-yun"><span class="klab">大运</span>%s</p>' % cells)
    st = r.get("start") or {}
    xu = st.get("交运虚岁") or st.get("虚岁")
    fw = r.get("forward")
    direction = "" if fw is None else ("　%s排" % ("顺" if fw else "逆"))
    if xu:
        meta = "%s　%s 岁起运%s" % (lab, xu, direction)
    else:
        meta = "%s　起运岁未报（应期只能到运、不到年）%s" % (lab, direction)
    L.append('<div class="meta">%s</div>' % meta)
    note = _src_note(r)
    if note:
        L.append('<div class="meta"><span class="tag">%s</span></div>' % note)
    L.append('</div>')          # .minggao 收口：盘、大运、抬头注同属一栏，两栏才并排
    return "\n".join(L)


def _wx_bars(r):
    wx = r.get("wuxing") or {}
    total = sum(wx.values()) or 1
    L = ['<p class="flat"><b>五行</b>（天干＋藏干等权计，共 %d 字）：</p>' % total]
    L.append('<p class="flat wx">')
    for e in "木火土金水":
        n = wx.get(e, 0)
        w = 8 + int(n * 13)
        L.append('<span class="lab">%s</span><span class="bar %s" style="width:%dpx">'
                 '</span><span class="n">%d</span><br>' % (e, WX_CLASS[e], w, n))
    L.append('</p>')
    miss = r.get("missing") or []
    L.append('<p class="flat">%s</p>' % ("五行俱全。" if not miss else
                                         "缺：%s。" % "、".join(miss)))
    return "\n".join(L)


def _detail_block(r):
    lab = _label_of(r)
    L = ['<div class="klab2">%s盘面　%s</div>' % (lab, "　".join(r["pillars"]))]
    L.append('<div class="tbl"><table>')
    L.append('<tr><th>柱</th><th>干支</th><th>天干十神</th><th>藏干·十神</th>'
             '<th>纳音</th><th>本柱旬空</th></tr>')
    for d in r.get("detail") or []:
        cang = "／".join("%s·%s" % (c.get("gan", ""), c.get("ss", ""))
                        for c in d.get("cang") or [])
        L.append('<tr><td>%s</td><td><b>%s</b></td><td>%s</td>'
                 '<td class="l">%s</td><td>%s</td><td>%s</td></tr>'
                 % (d.get("pos", ""), d.get("gz", ""), d.get("stem_ss", ""),
                    cang, d.get("nayin", ""), "".join(d.get("kong") or [])))
    L.append('</table></div>')
    L.append(_wx_bars(r))

    rel = r.get("relations") or []
    if rel:
        L.append('<p class="flat"><b>关系</b>（刑冲合穿拱、天干合冲、干支暗合、禄刃；'
                 '只摆结构，不论吉凶）：</p>')
        L.append('<div class="tbl"><table>')
        L.append('<tr><th>类</th><th>字</th><th>位</th><th>注</th></tr>')
        for it in rel:
            L.append('<tr><td>%s</td><td><b>%s</b></td><td>%s</td><td class="l">%s</td></tr>'
                     % (it.get("类", ""), it.get("字", ""),
                        "、".join(it.get("位") or []), it.get("注") or "—"))
        L.append('</table></div>')

    lu = r.get("lushen") or {}
    if lu:
        L.append('<p class="flat"><b>日主 %s</b>　禄：%s　刃：%s</p>'
                 % (lu.get("日主", ""), lu.get("禄", ""), lu.get("刃", "")))

    hits = r.get("kong_hits") or []
    if hits:
        L.append('<p class="flat">空亡两查（年柱定一旬、日柱定一旬，两个都比对四支）：</p>')
        L.append('<ul class="plain">')
        for h in hits:
            L.append('<li>%s柱%s（%s旬）空 %s → <b>%s柱%s 落空</b>。</li>'
                     % (h.get("旬位", ""), h.get("旬", ""), h.get("旬名", ""),
                        "".join(h.get("空") or []), h.get("位", ""), h.get("落", "")))
        L.append('</ul>')

    for b in r.get("borders") or []:
        L.append('<p class="note">%s</p>' % b)
    return "\n".join(L)


def _items_html(items, sec_no):
    if not items:
        return ""
    L = []
    for it in items:
        if not isinstance(it, dict):
            continue
        who = str(it.get("who") or "").strip()
        text = str(it.get("text") or "").strip()
        if not text:
            continue
        head = who if who in WHO_ALLOWED else who
        if who and who not in WHO_ALLOWED:
            _warn("第 %s 节出现非约定 who 值「%s」，按原样渲染"
                  "（只允许 男方／女方／两人）" % (sec_no, who))
        star = _stars(it.get("stars"))
        L.append('<div class="item"><p>%s%s%s</p>' % (
            ('<span class="who">%s</span>' % head) if head else "",
            text, ("　" + star) if star else ""))
        src = it.get("src")
        if src:
            L.append('<div class="src">出处：%s</div>' % src)
        L.append('</div>')
    return "\n".join(L)


def _timeline_html(rows):
    if not rows:
        return ""
    L = ['<div class="tbl wrap"><table>',
         '<tr><th>年月</th><th>事项</th><th>置信</th></tr>']
    for row in rows:
        if not isinstance(row, dict):
            continue
        L.append('<tr><td>%s</td><td class="l">%s</td><td>%s</td></tr>'
                 % (row.get("ym", ""), row.get("text", ""), row.get("conf", "")))
    L.append('</table></div>')
    return "\n".join(L)


def _verbatim_html(items):
    if not items:
        return ""
    L = ['<ol class="yao">']
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        if not text:
            continue
        star = _stars(it.get("stars"))
        L.append('<li>%s%s</li>' % (text, ("　" + star) if star else ""))
    L.append('</ol>')
    return "\n".join(L)


def _appendix_html(app):
    if not app:
        return ""
    L = ['<details>', '<summary>附录 · 逐条出处</summary>', '<div class="tbl wrap"><table>',
         '<tr><th>编号</th><th>条目</th><th>星级</th></tr>']
    for it in app:
        if not isinstance(it, dict):
            continue
        L.append('<tr><td>%s</td><td class="l">%s</td><td>%s</td></tr>'
                 % (it.get("no", ""), it.get("text", ""), _stars(it.get("stars")) or "—"))
    L.append('</table></div>')
    L.append('<p class="note">星级为出处可靠度标注，不是结论强弱；同一条目多书异说者，'
             '按 references\\wenxian.md 的取舍顺序取值。</p>')
    L.append('</details>')
    return "\n".join(L)


def _promo_html():
    pay = _img_data_uri("appreciation.jpg", "赞赏码")
    wx = _img_data_uri("wechat_qr.jpg", "盘叔微信")
    L = ['<div class="promo">',
         '  <p class="ptitle">%s</p>' % PROMO_TITLE,
         '  <p class="body">%s</p>' % PROMO_BODY,
         '  <div class="qrs">',
         '    <figure class="pay"><img src="%s" alt="赞赏码">'
         '<figcaption>赞赏码</figcaption></figure>' % pay,
         '    <figure class="wx"><img src="%s" alt="盘叔微信">'
         '<figcaption>盘叔微信</figcaption></figure>' % wx,
         '  </div>',
         '  <p>如果觉得有用，欢迎赞赏支持；想交流命理，<b>微信：cpms1988</b>。</p>',
         '  <p>更多命理玄学相关 AI 技能与干货 SKILL，请关注公众号 <b>【野生你盘叔】</b>。</p>',
         '  <div class="adbox">',
         '    <h4>关于「苍盘命书」</h4>']
    for para in PROMO_ADBOX:
        L.append('    <p>%s</p>' % para)
    L.append('    <p class="nind"><a class="cta" href="%s">%s</a></p>' % (PROMO_CTA[0], PROMO_CTA[1]))
    L.append('  </div>')
    L.append('  <p class="disc">本节为独立推广内容，不是命理判断，也不是命盘资料。</p>')
    L.append('  <p class="disc">本合婚书内容源自传统术数体系，供文化研究与参考，'
             '不构成医疗、法律、投资等任何决策依据。</p>')
    L.append('</div>')
    return "\n".join(L)


def render_html(m, f, duan, title, kicker):
    sections = [s for s in (duan.get("sections") or []) if isinstance(s, dict)]
    preface = [p for p in (duan.get("preface") or []) if str(p).strip()]
    zd = duan.get("zongduan") or {}
    subtitle = duan.get("subtitle") or "盘叔盲派 · 双盘互参"
    date_line = duan.get("date_line") or datetime.date.today().strftime("%Y 年 %m 月批写")

    L = ['<!DOCTYPE html>',
         '<html lang="zh-CN">',
         '<head>',
         '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         '<title>%s</title>' % title.replace("　", ""),
         '<style>', CSS_BASE, CSS_EXTRA, '</style>',
         '</head>',
         '<body>',
         '<div class="sheet">',
         '',
         '<header>',
         '<div class="kicker">%s</div>' % kicker,
         '<h1>%s</h1>' % title,
         '<div class="sub">%s</div>' % subtitle,
         '</header>',
         '',
         '<div class="mgs">',
         _minggao(m),
         _minggao(f),
         '</div>',
         '',
         _detail_block(m),
         '',
         _detail_block(f),
         '']

    if preface:
        L.append('<blockquote>')
        for p in preface:
            L.append('<p>%s</p>' % p)
        L.append('</blockquote>')
        L.append('')

    # 锚点导航：总断 + 各节
    toc = ['<a href="#s0">总断</a>']
    for i, sec in enumerate(sections, 1):
        toc.append('<a href="#s%d">%s %s</a>'
                   % (i, sec.get("no", ""), sec.get("title", "")))
    L.append('<p class="toc">%s</p>' % "".join(toc))
    L.append('')

    # 总断
    L.append('<h2 id="s0">总断</h2>')
    L.append('')
    star = _stars(zd.get("stars"))
    L.append('<p class="zong"><b>%s</b>%s　%s</p>'
             % (zd.get("label", ""), ("　" + star) if star else "", zd.get("text", "")))
    L.append('')

    for i, sec in enumerate(sections, 1):
        L.append('<h2 id="s%d"><span class="no">%s</span>%s</h2>'
                 % (i, sec.get("no", ""), sec.get("title", "")))
        L.append('')
        items = sec.get("items") or []
        body = (_verbatim_html(items) if sec.get("verbatim") else
                _items_html(items, sec.get("no", str(i))))
        if body:
            L.append(body)
        if sec.get("timeline"):
            L.append(_timeline_html(sec["timeline"]))
        if not body and not sec.get("timeline"):
            L.append('<p class="note">本节材料不足以立断，按「不取则不写」处理，留空。</p>')
        L.append('')

    app = _appendix_html(duan.get("appendix"))
    if app:
        L.append(app)
        L.append('')

    L.append('<footer>合　婚　书　终</footer>')
    L.append('<p class="dateline">%s</p>' % date_line)
    L.append('')
    L.append(_promo_html())
    L.append('')
    L.append('</div>')
    L.append('</body>')
    L.append('</html>')
    return "\n".join(L)


# ======================================================================
# 五、自检
# ======================================================================
def self_test():
    """内置自检：排盘器可导入、两造可复现、渲染骨架齐备（不写文件）。"""
    ok = 0
    bad = []

    def ck(name, cond, detail=""):
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append("%s %s" % (name, detail))

    ck("排盘器可导入", hasattr(paipan, "paipan") and hasattr(paipan, "paipan_from_pillars"))
    r1 = paipan.paipan(datetime.date(1984, 11, 12), "14:00", "男")
    ck("男造 1984-11-12 四柱", r1["pillars"] == ["甲子", "乙亥", "庚戌", "癸未"], r1["pillars"])
    r2 = paipan.paipan(datetime.date(1994, 11, 27), "02:00", "女")
    ck("女造 1994-11-27 四柱", r2["pillars"] == ["甲戌", "乙亥", "丁巳", "辛丑"], r2["pillars"])
    ck("两造均无 error", not r1.get("error") and not r2.get("error"))

    duan = {"zongduan": {"text": "自检用总断", "label": "中", "stars": 2},
            "sections": [{"no": "一", "title": "自检节",
                          "items": [{"who": "两人", "text": "自检条目", "stars": 2}]}],
            "appendix": [{"no": "T-1", "text": "自检附录", "stars": 1}]}
    h = render_html(r1, r2, duan, "合　婚　书", "双　盘　互　参")
    ck("HTML 单根", h.count("<html") == 1, h.count("<html"))
    ck("无 link 标签", h.count("<link") == 0)
    ck("无 script 标签", h.count("<script") == 0)
    ck("双盘并排容器", h.count('class="mgs"') == 1)
    ck("锚点导航", 'class="toc"' in h and 'href="#s1"' in h)
    ck("附录折叠", "<details>" in h and "<summary>" in h)
    ck("尾注出现一次", h.count('class="promo"') == 1)
    ck("苍盘 CTA 一处", h.count("mp.weixin.qq.com") == 1)
    ck("二维码两处", h.count("data:image/jpeg;base64,") == 2)

    print("hehun.py self-test: %s（%d 项通过%s）"
          % ("PASS" if not bad else "FAIL", ok,
             "" if not bad else "；失败 " + "；".join(bad)))
    return 0 if not bad else 1


# ======================================================================
# 六、主流程
# ======================================================================
def main(argv=None):
    a = build_parser().parse_args(argv)

    if a.self_test:
        raise SystemExit(self_test())

    g1, g2 = a.male_gender, a.female_gender
    if g1 == g2:
        raise SystemExit(_fail(
            2, "两造性别须一男一女（实得 %s、%s）：本技能不覆盖同性关系，"
               "见 SKILL.md 硬边界第 3 条。此类需求请如实告知不在能力范围内，不由本器出盘。"
               % (g1, g2)))

    if a.lon is not None and not (-180.0 <= a.lon <= 180.0):
        raise SystemExit(_fail(2, "--lon %r 越界：经度须在 -180～180（东经为正）" % a.lon))

    m1, p1 = _resolve_side(a, "male", g1)
    m2, p2 = _resolve_side(a, "female", g2)

    duan = load_duan(a.duan)

    r1 = _run_paipan(m1, p1, a.lon)
    _stop_on_error("男方", r1)
    r2 = _run_paipan(m2, p2, a.lon)
    _stop_on_error("女方", r2)

    html = render_html(r1, r2, duan, a.title, a.kicker)

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)

    print("排盘完成：")
    print("  男 %s　%s" % ("　".join(r1["pillars"]),
                          (r1.get("input") or {}).get("tst_note", "四柱入口")))
    print("  女 %s　%s" % ("　".join(r2["pillars"]),
                          (r2.get("input") or {}).get("tst_note", "四柱入口")))
    print("HTML 已写出：%s（%d 字节）" % (out, os.path.getsize(out)))
    if WARN:
        print("提示：%d 条降级告警见 stderr。" % len(WARN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
