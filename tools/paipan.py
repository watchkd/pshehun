#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘叔盲派 · 排盘器（ps-paipan）：四柱、大运、起运、十神、藏干、纳音、逐柱空亡、
空亡四判、关系矩阵（刑冲合穿拱／暗合／禄刃）。

**排盘是历法，不是断法。** 本器只做 E6 结构计算，不出任何断语；
断法一律归 `ps-zonglun` 七层调度与二十八子技能，两者不混。

两个入口：

  甲、**生日入口**（`--date/--time/--gender`）：用户只给公历生日时用。现算节气、
      校正真太阳时、排四柱、起运、大运。**这是本包新增的能力**——原流程要求
      用户自报四柱，此路为「用户只给生日」的降级路径，出盘后必须请用户复核。
  乙、**四柱入口**（`--pillars 甲子 乙亥 庚戌 癸未`）：本包主路径。用户报四柱时用，
      不重排四柱，只做**十二项自检**（P01–P17：形近字 → 干支合法性 → 十神藏干纳音 →
      五行 → 顺逆 → 大运序列 → 起运 → 旬空两查 → 当前大运 → 空亡四判 → 关系矩阵；
      加 `--liuyue` 时增 P18 流月；加 `--shensha` 时增 P19 神煞十二项）
      并补出十神、藏干、纳音、空亡、关系、大运序列。四柱是用户给的既成事实，本器只核不改。

四条硬规矩：

  一、**不猜**。节气用天文算法（太阳视黄经）现算，日柱用儒略日双锚点交叉，
      大运起运用精确时差折算。任一项对不上就报 FAIL、不出盘。
  二、**不代断**。本器只报结构：哪个字、落哪柱、空不空、起运几岁。吉凶归断法层。
      「空亡四判」同理：只报**落主位还是宾位、有无根、有无冲穿刑来击、何年值冲合**
      四件可核之事，**不报「金空则鸣」鸣不鸣、鸣出什么**——那是断法层取象，本器一个结论都不下。
      「关系矩阵」同此：只列哪个字与哪个字发生了什么，**不判轻重**（轻重归做功层）。
  三、**真太阳时须给经度**。不给经度就用北京时间，并在输出里明写「未校正」，
      不假装校正过。
  四、**旬空两柱都查，且只查这两柱**。年柱定一旬、日柱定一旬，两个旬空都比对四支——
      只查日柱会漏掉年柱带来的旬空（`ps-zonglun-guide` §1.4⑤）。
      **月柱、时柱之旬不取**：四柱互查会虚增落空，把非空之支判成空。
      夏派另有「X 岁扎根 X 岁运」口径，本器只出三除口径的起运数，夏派须另标。

与另一路做法的两处不同（都是刻意的）：

  - 节气不靠在线查询，本地算。太阳视黄经用 VSOP87 截断级数（地球 L0 取 64 项、
    L1 取 34 项、L2 取 20 项、L3 取 7 项），加章动、光行差与 ΔT 修正。
    **实测误差 ±15 分钟以内**：1984 立春算 23:06（公开值 23:18:44，差 13 分）、
    2000 春分算 15:35（公开值 15:35，差 0 分）、2024 立春算 16:21（公开值 16:26:53，差 6 分）。
    **故生日距节气四十五分钟内者，本器一律报警**，提示改用专业排盘软件复核月柱——
    这是本器唯一不敢自专的地方，宁可报错，不装作准。
  - 日柱双锚点（2000-01-01 戊午、1900-01-01 甲戌）必须一致，不一致即 FAIL。

用法：
    # 甲、生日入口
    python tools/paipan.py --date 1984-11-12 --time 14:45 --gender 男 --lon 116.12
    python tools/paipan.py --date 1984-11-12 --time 14:45 --gender 男 --lon 116.12 --json
    # 乙、四柱入口（本包主路径）
    python tools/paipan.py --pillars 甲子 乙亥 庚戌 癸未 --gender 男 \
        --birth-year 1984 --start-age 10
    python tools/paipan.py --pillars 甲子 乙亥 庚戌 癸未 --gender 男 --json
    # 丙、自检
    python tools/paipan.py --self-test
"""
import argparse
import io
import json
import math
import re
import sys
from datetime import date, datetime, timedelta

# 控制台编码：Windows 中文环境默认 cp936，本文件输出含 ✅（U+2705），
# 直接 print 会 UnicodeEncodeError 崩在第一张表之前。改 stdout/stderr 为 UTF-8；
# 老 cmd 显示成乱码但不崩，Windows Terminal / VS Code 正常。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------- 基本常量 ----------------
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]
JIAZI_SET = set(JIAZI)
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
YANG = set("甲丙戊庚壬")
POS = ["年", "月", "日", "时"]

# 支藏天干（本气、中气、余气）
CANG = {
    "子": "癸", "丑": "己癸辛", "寅": "甲丙戊", "卯": "乙",
    "辰": "戊乙癸", "巳": "丙庚戊", "午": "丁己", "未": "己丁乙",
    "申": "庚壬戊", "酉": "辛", "戌": "戊辛丁", "亥": "壬甲",
}

# 五行
WX_OF = {}
for _s in "甲乙":
    WX_OF[_s] = "木"
for _s in "丙丁":
    WX_OF[_s] = "火"
for _s in "戊己":
    WX_OF[_s] = "土"
for _s in "庚辛":
    WX_OF[_s] = "金"
for _s in "壬癸":
    WX_OF[_s] = "水"
for _b in "寅卯":
    WX_OF[_b] = "木"
for _b in "巳午":
    WX_OF[_b] = "火"
for _b in "辰戌丑未":
    WX_OF[_b] = "土"
for _b in "申酉":
    WX_OF[_b] = "金"
for _b in "亥子":
    WX_OF[_b] = "水"

# 纳音（三十组，每组管两个干支）
NAYIN = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
]

# 六旬空亡：旬首后第十、十一支，即本旬所无之二支
XUN_KONG = {}


def _build_xun_kong():
    for i in range(0, 60, 10):
        head = JIAZI[i]
        XUN_KONG[i // 10] = (JIAZI[(i + 10) % 60][1], JIAZI[(i + 11) % 60][1])


_build_xun_kong()


def xun_of(gz):
    return JIAZI.index(gz) // 10


def kong_of(gz):
    return XUN_KONG[xun_of(gz)]


def nayin(gz):
    return NAYIN[JIAZI.index(gz) // 2]


# ---------------- 空亡四判（纯结构，不出断语） ----------------
# 只算三件可核的事实：
#   一、空支有无根（同气比助／藏干透出）——分「待填」与「近真空」
#   二、有无冲穿刑来击——钟不击不响，空器亦然
#   三、何年值／冲／合此支——出空与填实的候选年，只列年份，不判吉凶
# 「鸣不鸣、朽不腐、发不发」仍归断法层；本器一律不出结论，只把事实摆齐。

CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑", "寅": "申", "申": "寅",
         "卯": "酉", "酉": "卯", "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
         "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
CHUAN = {"子": "未", "未": "子", "丑": "午", "午": "丑", "寅": "巳", "巳": "寅",
         "卯": "辰", "辰": "卯", "申": "亥", "亥": "申", "酉": "戌", "戌": "酉"}
# 相刑以无序对判定，避免「寅刑巳／巳刑寅」双向重复计数
XING_PAIR = {frozenset(p) for p in
             ("子卯", "寅巳", "巳申", "寅申", "丑戌", "戌未", "丑未")}
XING_SELF = set("辰午酉亥")


def kong_hits_of(pillars):
    """旬空两查：只论**年柱旬**与**日柱旬**，月柱、时柱之旬不取。

    通行只论日柱旬空；本包 docstring 定「年日两查」，为免口径与文案不符，
    月柱、时柱一律不查（否则四柱互查会虚增落空，把非空之支判成空）。
    """
    zhi = [p[1] for p in pillars]
    out = []
    for k in (0, 2):
        kw = kong_of(pillars[k])
        for j, z in enumerate(zhi):
            if z in kw:
                out.append({"旬": pillars[k], "旬位": POS[k],
                            "旬名": JIAZI[xun_of(pillars[k]) * 10][:2],
                            "空": list(kw), "落": z, "位": POS[j]})
    return out


def judge_kong(pillars, birth_year=None, start_age=None, span=70):
    """空亡四判：按「支」去重，不按旬重复。返回列表，每项一支。

    每项字段：
      落／五行／位／旬　—— 哪一支空、什么五行、落于何柱、由谁的旬带来
      宾主　　　　　　　—— 落于日、时为主位，落于年、月为宾位（空之轻重先看这一层）
      根／根由　　　　　—— 有根（待填）／无根（近真空）及其依据
      击　　　　　　　　—— 冲、穿、刑（含自刑）来击者，空则「未击」
      值／冲／合　　　　—— 岁运走到此支、冲此支、合此支的年份
    """
    zhi_all = [p[1] for p in pillars]
    hits = kong_hits_of(pillars)
    kong_set = {h["落"] for h in hits}
    stems = [p[0] for p in pillars]

    order, info, primary = [], {}, {}
    for h in hits:
        z = h["落"]
        if z not in info:
            info[z] = {"落": z, "五行": WX_OF[z], "位": [], "旬": [],
                       "宾主": "", "宾主由": "",
                       "根": "", "根由": "", "击": [],
                       "值": [], "冲": [], "合": []}
            order.append(z)
            primary[z] = POS.index(h["位"])
        src = "%s柱%s旬" % (h["旬位"], h["旬名"])
        if src not in info[z]["旬"]:
            info[z]["旬"].append(src)

    for z in order:
        d = info[z]
        pk = primary[z]
        for j, p in enumerate(pillars):
            if p[1] == z and POS[j] not in d["位"]:
                d["位"].append(POS[j])
        # 零判：宾主。空在主位（日、时）为忌，空在宾位（年、月）不忌——
        # 同一个字落空，落于何柱，轻重先差一层。
        zw = [POS[j] for j, p in enumerate(pillars) if p[1] == z]
        d["宾主"] = "主位" if any(w in ("日", "时") for w in zw) else "宾位"
        d["宾主由"] = "落于%s" % "、".join(zw)

        # 一、有无根
        same = []
        for j, p in enumerate(pillars):
            if WX_OF[p[1]] != WX_OF[z]:
                continue
            if p[1] == z and j == pk:
                continue          # 自己不算扶自己
            if p[1] == z:
                same.append("%s%s同支重逢" % (POS[j], p[1]))
            elif p[1] in kong_set:
                same.append("%s%s同气但亦落空" % (POS[j], p[1]))
            else:
                same.append("%s%s同气" % (POS[j], p[1]))
        live = [x for x in same if "亦落空" not in x]
        tou = [g for g in CANG[z] if g in stems]
        if live or tou:
            d["根"] = "有根"
            bits = []
            if live:
                bits.append("、".join(live) + "相扶")
            if tou:
                bits.append("藏干「%s」透于天干" % "".join(tou))
            d["根由"] = "；".join(bits)
        else:
            d["根"] = "无根"
            d["根由"] = ("同气之支「%s」亦落空，不得为扶" % "、".join(
                x.split("同气")[0] for x in same)) if same else "四支无同气，藏干亦不透"

        # 二、有无冲穿刑来击
        for j, p in enumerate(pillars):
            if j == pk:
                continue
            z2 = p[1]
            if CHONG.get(z2) == z:
                d["击"].append("六冲·%s%s" % (POS[j], z2))
            if CHUAN.get(z2) == z:
                d["击"].append("六穿·%s%s" % (POS[j], z2))
            if z2 != z and frozenset((z, z2)) in XING_PAIR:
                d["击"].append("相刑·%s%s" % (POS[j], z2))
            if z2 == z and z in XING_SELF:
                d["击"].append("自刑·%s%s" % (POS[j], z2))

        # 三、值／冲／合之年（只列年份，不判吉凶）
        if birth_year:
            y0 = birth_year + (start_age - 1 if start_age else 0)
            for y in range(y0, y0 + span):
                g = JIAZI[(y - 4) % 60]
                if g[1] == z:
                    d["值"].append(y)
                elif CHONG.get(g[1]) == z:
                    d["冲"].append(y)
                elif LIUHE.get(g[1]) == z:
                    d["合"].append(y)

    return [info[z] for z in order]


# ---------------- 关系矩阵（刑冲合穿拱、暗合、禄刃） ----------------
# 只摆「哪个字与哪个字发生了什么」，**不下吉凶、不判轻重**。
# 轻重归断法层：同一「相刑」，贴身与遥隔不同论，主位与宾位不同论。
WUHE = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛", "辛": "丙",
        "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}
GAN_CHONG = {"甲": "庚", "庚": "甲", "乙": "辛", "辛": "乙",
             "丙": "壬", "壬": "丙", "丁": "癸", "癸": "丁"}
SANHE = [("申子辰", "水"), ("亥卯未", "木"), ("寅午戌", "火"), ("巳酉丑", "金")]
LU = {"甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午", "己": "午",
      "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
REN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}


def relations_of(pillars):
    """四支两两之刑冲合穿、三合半合拱、天干五合相冲、干支暗合、禄刃。

    返回 {"relations": [...], "lushen": {...}}。每条关系记「类／位／字／注」，
    不记吉凶。**暗合**只取「天干 × 他柱地支藏干」，且该藏干未透于天干
    （已透者归天干五合，不重复计）。

    半合与拱的分别：三合局缺**中支**曰「拱」（如亥未拱卯，卯未在局中为中也），
    缺首尾曰「半合」。拱者待岁运填中支，与半合之已成者不同论。
    """
    zhi = [p[1] for p in pillars]
    gan = [p[0] for p in pillars]
    out = []

    def add(kind, idx, chars, note=""):
        out.append({"类": kind, "位": [POS[i] for i in idx],
                    "字": chars, "注": note})

    def first_pos(z):
        return zhi.index(z)

    # 一、地支两两
    for i in range(4):
        for j in range(i + 1, 4):
            a, b = zhi[i], zhi[j]
            ch = a + b
            if LIUHE.get(a) == b:
                add("六合", [i, j], ch, "合而化否，须看月令")
            if CHONG.get(a) == b:
                add("六冲", [i, j], ch)
            if CHUAN.get(a) == b:
                add("六穿", [i, j], ch, "穿为暗损，不显于面")
            if a != b and frozenset((a, b)) in XING_PAIR:
                add("相刑", [i, j], ch, "刑主磨损，与冲之明动不同")
            if a == b and a in XING_SELF:
                add("自刑", [i, j], ch)

    # 二、三合／半合／拱
    for trio, wx in SANHE:
        have = [z for z in trio if z in zhi]
        if len(have) == 3:
            add("三合", [first_pos(z) for z in trio], trio, "%s局全" % wx)
        elif len(have) == 2:
            miss = [z for z in trio if z not in zhi][0]
            kind = "拱" if miss == trio[1] else "半合"
            add(kind, sorted(first_pos(z) for z in have), "".join(have),
                "三合%s局缺%s" % (wx, miss))

    # 三、天干两两
    for i in range(4):
        for j in range(i + 1, 4):
            a, b = gan[i], gan[j]
            if WUHE.get(a) == b:
                add("天干五合", [i, j], a + b, "合而贴身，主牵引")
            elif GAN_CHONG.get(a) == b:
                add("天干相冲", [i, j], a + b)

    # 四、干支暗合（藏干未透者）
    for i in range(4):
        for j in range(4):
            if i == j:
                continue
            for c in CANG[zhi[j]]:
                if WUHE.get(gan[i]) == c and c not in gan:
                    add("暗合", [i, j], gan[i] + c,
                        "%s干 × %s支%s中%s（未透）" % (POS[i], POS[j], zhi[j], c))

    # 五、禄刃（有则记位，无则记「不见」，同为结构事实）
    ds = gan[2]
    lu, ren = LU.get(ds, ""), REN.get(ds, "")
    lushen = {
        "日主": ds,
        "禄": ("%s（%s支）" % (lu, POS[first_pos(lu)])) if lu in zhi else ("%s（四支不见）" % lu),
        "刃": ("%s（%s支）" % (ren, POS[first_pos(ren)])) if ren and ren in zhi else (
            ("%s（四支不见）" % ren) if ren else "阴干不立刃"),
    }
    return {"relations": out, "lushen": lushen}


# ---------------- 神煞十二项（v1.8 P2-8 · 佐证层，不作主断） ----------------
# 起法逐条引已裁决口径（仲裁 #22 十二项起法表；天乙承 #4，佐证地位承 #10，
# 查法归属承 #19）。起法与起法表、ps-shensha/SKILL.md 三处须逐字对得上，
# 三家起法不同者一律取本表，不许「先实现后补依据」。
TIANYI = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申",
          "丙": "亥酉", "丁": "亥酉", "壬": "卯巳", "癸": "卯巳", "辛": "午寅"}
TRIOS = ("申子辰", "寅午戌", "亥卯未", "巳酉丑")
YIMA = {"申子辰": "寅", "寅午戌": "申", "亥卯未": "巳", "巳酉丑": "亥"}
TAOHUA = {"申子辰": "酉", "寅午戌": "卯", "亥卯未": "子", "巳酉丑": "午"}
HUAGAI = {"申子辰": "辰", "寅午戌": "戌", "亥卯未": "未", "巳酉丑": "丑"}
JIANGXING = {"申子辰": "子", "寅午戌": "午", "亥卯未": "卯", "巳酉丑": "酉"}
JIESHA = {"申子辰": "巳", "寅午戌": "亥", "亥卯未": "申", "巳酉丑": "寅"}
WANGSHEN = {"申子辰": "亥", "寅午戌": "巳", "亥卯未": "寅", "巳酉丑": "申"}
GUCHEN = {"亥子丑": ("寅", "戌"), "寅卯辰": ("巳", "丑"),
          "巳午未": ("申", "辰"), "申酉戌": ("亥", "未")}
JINYU = {"甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
         "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅"}
SHENSHA_NOTE = "〔佐证，不作主断〕"


def _trio_of(z):
    """地支所属三合局（取首字为键）。"""
    for t in TRIOS:
        if z in t:
            return t
    return ""


def _gu_of(z):
    for t, pair in GUCHEN.items():
        if z in t:
            return pair
    return ("", "")


def shensha_of(pillars):
    """十二项常用神煞：只标「起法 → 落于哪一柱」，不下吉凶。

    以年支查者（驿马桃花华盖将星劫煞亡神孤辰寡宿）、以年干与日干查者（天乙）、
    以日干查者（禄羊刃金舆）、以日柱查者（空亡）。此为盲派师传查法（仲裁 #19）。
    """
    gan = [p[0] for p in pillars]
    zhi = [p[1] for p in pillars]
    yz, dz, ds = zhi[0], zhi[2], gan[2]
    trio_y = _trio_of(yz)

    def loc(chars):
        hit = []
        for c in chars:
            ps = [POS[k] for k, x in enumerate(zhi) if x == c]
            if ps:
                hit.append("%s（%s支）" % (c, "、".join(ps)))
        return "、".join(hit) if hit else "四支不见（%s）" % "".join(chars)

    rows = []

    def add(name, rule, via, val):
        rows.append({"名": name, "起法": rule, "查": via, "落": val})

    ty_map = {}
    for g, lab in ((gan[0], "年干%s" % gan[0]), (ds, "日干%s" % ds)):
        for c in TIANYI[g]:
            for k, x in enumerate(zhi):
                if x == c:
                    ty_map.setdefault((c, POS[k]), []).append(lab)
    ty = ["%s（%s支·%s查）" % (c, pos, "、".join(labs))
          for (c, pos), labs in ty_map.items()]
    add("天乙贵人", "甲戊庚牛羊、乙己鼠猴乡、丙丁猪鸡位、壬癸兔蛇藏、六辛逢马虎",
        "年干＋日干（年干贵人大、日干贵人小）",
        "、".join(ty) if ty else "四支不见")
    add("驿马", "三合局长生位之冲（申子辰见寅、寅午戌见申、亥卯未见巳、巳酉丑见亥）",
        "年支（%s）" % yz, loc(YIMA[trio_y]))
    add("桃花", "三合局沐浴位（申子辰见酉、寅午戌见卯、亥卯未见子、巳酉丑见午）",
        "年支（%s）" % yz, loc(TAOHUA[trio_y]))
    add("华盖", "三合局库位（寅午戌见戌、申子辰见辰、亥卯未见未、巳酉丑见丑）",
        "年支（%s）" % yz, loc(HUAGAI[trio_y]))
    add("将星", "三合局中神（申子辰见子、寅午戌见午、亥卯未见卯、巳酉丑见酉）",
        "年支（%s）" % yz, loc(JIANGXING[trio_y]))
    add("劫煞", "三合局头之二位（寅午戌见亥、申子辰见巳、亥卯未见申、巳酉丑见寅）",
        "年支（%s）" % yz, loc(JIESHA[trio_y]))
    add("亡神", "三合局尾之前一位（寅午戌见巳、申子辰见亥、亥卯未见寅、巳酉丑见申）",
        "年支（%s）" % yz, loc(WANGSHEN[trio_y]))
    add("羊刃", "阳干帝旺位（甲卯、丙午、戊午、庚酉、壬子），阴干不立刃",
        "日干（%s）" % ds, loc(REN[ds]) if ds in REN else "阴干不立刃")
    add("禄", "日干临官位（甲寅、乙卯、丙戊巳、丁己午、庚申、辛酉、壬亥、癸子）",
        "日干（%s）" % ds, loc(LU[ds]))
    add("金舆", "禄前二位（甲辰、乙巳、丙未、丁申、戊未、己申、庚戌、辛亥、壬丑、癸寅）",
        "日干（%s）" % ds, loc(JINYU[ds]))
    gz_day = pillars[2]
    add("空亡", "以日柱查旬空（甲子旬戌亥空等）；本派以日柱为主，不以年柱查"
        "（年柱旬另见「逐柱空亡」节）",
        "日柱（%s，%s旬）" % (gz_day, JIAZI[xun_of(gz_day) * 10]), loc(kong_of(gz_day)))
    gu, gua = _gu_of(yz)
    add("孤辰寡宿", "亥子丑见寅（孤）戌（寡）、寅卯辰见巳丑、巳午未见申辰、申酉戌见亥未",
        "年支（%s）" % yz, "孤辰%s　寡宿%s" % (loc(gu), loc(gua)))
    return rows


# ---------------- 天文：儒略日与太阳黄经 ----------------
def to_jd(dt):
    """公历（格里高利历）UTC → 儒略日。dt 为 datetime，按 UTC 解释。"""
    y, m = dt.year, dt.month
    d = (dt.day + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0)
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def from_jd(jd):
    """儒略日 → 公历 datetime（UTC）。"""
    jd += 0.5
    z = int(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    dd = int(365.25 * c)
    e = int((b - dd) / 30.6001)
    day = b - dd - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    di = int(day)
    frac = day - di
    hh = int(frac * 24)
    mm = int((frac * 24 - hh) * 60)
    ss = int(round((((frac * 24 - hh) * 60) - mm) * 60))
    if ss >= 60:
        ss -= 60
        mm += 1
    if mm >= 60:
        mm -= 60
        hh += 1
    return datetime(year, month, di, min(hh, 23), min(mm, 59), min(ss, 59))


def delta_t(year):
    """ΔT（TT-UT，秒）。Espenak & Meeus 多项式，1900–2150 段。"""
    y = year
    if y < 1920:
        t = y - 1900
        return -2.79 + 1.494119 * t - 0.0598939 * t ** 2 + 0.0061966 * t ** 3 - 0.000197 * t ** 4
    if y < 1941:
        t = y - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t ** 2 + 0.0020936 * t ** 3
    if y < 1961:
        t = y - 1950
        return 29.07 + 0.407 * t - t ** 2 / 233 + t ** 3 / 2547
    if y < 1986:
        t = y - 1975
        return 45.45 + 1.067 * t - t ** 2 / 260 - t ** 3 / 718
    if y < 2005:
        t = y - 2000
        return (63.86 + 0.3345 * t - 0.060374 * t ** 2 + 0.0017275 * t ** 3
                + 0.000651814 * t ** 4 + 0.00002373599 * t ** 5)
    if y < 2050:
        t = y - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t ** 2
    if y <= 2150:
        return -20 + 32 * ((y - 1820) / 100.0) ** 2 - 0.5628 * (2150 - y)
    return -20 + 32 * ((y - 1820) / 100.0) ** 2


def _sun_L0(t):
    """地球日心黄经 L0（度），VSOP87 截断（主要项）。t 为儒略千年数。"""
    T = t
    terms = [
        (175347046, 0, 0), (3341656, 4.6692568, 6283.07585),
        (34894, 4.6261, 12566.1517), (3497, 2.7441, 5753.3849),
        (3418, 2.8289, 3.5231), (3136, 3.6277, 77713.7715),
        (2676, 4.4181, 7860.4194), (2343, 6.1352, 3930.2097),
        (1324, 0.7425, 11506.7698), (1273, 2.0371, 529.691),
        (1199, 1.1096, 1577.3435), (990, 5.233, 5884.927),
        (902, 2.045, 26.298), (857, 3.508, 398.149),
        (780, 1.179, 5223.694), (753, 2.533, 5507.553),
        (505, 4.583, 18849.228), (492, 4.205, 775.523),
        (357, 2.92, 0.067), (317, 5.849, 11790.629),
        (284, 1.899, 796.298), (271, 0.315, 10977.079),
        (243, 0.345, 5486.778), (206, 4.806, 2544.314),
        (205, 1.869, 5573.143), (202, 2.458, 6069.777),
        (156, 0.833, 213.299), (132, 3.411, 2942.463),
        (126, 1.083, 20.775), (115, 0.645, 0.98),
        (103, 0.636, 4694.003), (102, 0.976, 15720.839),
        (102, 4.267, 7.114), (99, 6.21, 2146.17),
        (98, 0.68, 155.42), (86, 5.98, 161000.69),
        (85, 1.3, 6275.96), (85, 3.67, 71430.7),
        (80, 1.81, 17260.15), (79, 3.04, 12036.46),
        (75, 1.76, 5088.63), (74, 3.5, 3154.69),
        (74, 4.68, 801.82), (70, 0.83, 9437.76),
        (62, 3.98, 8827.39), (61, 1.82, 7084.9),
        (57, 2.78, 6286.6), (56, 4.39, 14143.5),
        (56, 3.47, 6279.55), (52, 0.19, 12139.55),
        (52, 1.33, 1748.02), (51, 0.28, 5856.48),
        (49, 0.49, 1194.45), (41, 5.37, 8429.24),
        (41, 2.4, 19651.05), (39, 6.17, 10447.39),
        (37, 6.04, 10213.29), (37, 2.57, 1059.38),
        (36, 1.71, 2352.87), (36, 1.78, 6812.77),
        (33, 0.59, 17789.85), (30, 0.44, 83996.85),
        (30, 2.74, 1349.87), (25, 3.16, 4690.48),
    ]
    s = 0.0
    for a, b, c in terms:
        s += a * math.cos(b + c * T)
    return s / 1e8


def _sun_L1(t):
    T = t
    terms = [
        (628331966747, 0, 0), (206059, 2.678235, 6283.07585),
        (4303, 2.6351, 12566.1517), (425, 1.59, 3.523),
        (119, 5.796, 26.298), (109, 2.966, 1577.344),
        (93, 2.59, 18849.23), (72, 1.14, 529.69),
        (68, 1.87, 398.15), (67, 4.41, 5507.55),
        (59, 2.89, 5223.69), (56, 2.17, 155.42),
        (45, 0.4, 796.3), (36, 0.47, 775.52),
        (29, 2.65, 7.11), (21, 5.34, 0.98),
        (19, 1.85, 5486.78), (19, 4.97, 213.3),
        (17, 2.99, 6275.96), (16, 0.03, 2544.31),
        (16, 1.43, 2146.17), (15, 1.21, 10977.08),
        (12, 2.83, 1748.02), (12, 3.26, 5088.63),
        (12, 5.27, 1194.45), (12, 2.08, 4694),
        (11, 0.77, 553.57), (10, 1.3, 6286.6),
        (10, 4.24, 1349.87), (9, 2.7, 242.73),
        (9, 5.64, 951.72), (8, 5.3, 2352.87),
        (6, 2.65, 9437.76), (6, 4.67, 4690.48),
    ]
    s = 0.0
    for a, b, c in terms:
        s += a * math.cos(b + c * T)
    return s / 1e8


def _sun_L2(t):
    T = t
    terms = [
        (52919, 0, 0), (8720, 1.0721, 6283.0758),
        (309, 0.867, 12566.152), (27, 0.05, 3.52),
        (16, 5.19, 26.3), (16, 3.68, 155.42),
        (10, 0.76, 18849.23), (9, 2.06, 77713.77),
        (7, 0.83, 775.52), (5, 4.66, 1577.34),
        (4, 1.03, 7.11), (4, 3.44, 5573.14),
        (3, 5.14, 796.3), (3, 6.05, 5507.55),
        (3, 1.19, 242.73), (3, 6.12, 529.69),
        (3, 0.31, 398.15), (3, 2.28, 553.57),
        (2, 4.38, 5223.69), (2, 3.75, 0.98),
    ]
    s = 0.0
    for a, b, c in terms:
        s += a * math.cos(b + c * T)
    return s / 1e8


def _sun_L3(t):
    T = t
    terms = [(289, 5.844, 6283.076), (35, 0, 0), (17, 5.49, 12566.15),
             (3, 5.2, 155.42), (1, 4.72, 3.52), (1, 5.3, 18849.23),
             (1, 5.97, 242.73)]
    s = 0.0
    for a, b, c in terms:
        s += a * math.cos(b + c * T)
    return s / 1e8


def sun_apparent_longitude(jde):
    """太阳视黄经（度，0–360）。输入为力学时儒略日。"""
    t = (jde - 2451545.0) / 365250.0
    L = (_sun_L0(t) + _sun_L1(t) * t + _sun_L2(t) * t ** 2
         + _sun_L3(t) * t ** 3)
    lon = math.degrees(L) + 180.0            # 地心 → 太阳视方向
    # 章动与光行差（主项）
    omega = math.radians(125.04 - 1934.136 * (jde - 2451545.0) / 365.25)
    lon += -0.00569 - 0.00478 * math.sin(omega)
    # FK5 修正
    lon += -0.09033 / 3600.0
    return lon % 360.0


def solve_sun_longitude(target_deg, jd_guess):
    """求太阳视黄经等于 target_deg 的儒略日（牛顿迭代）。"""
    jd = jd_guess
    for _ in range(12):
        lon = sun_apparent_longitude(jd)
        diff = (target_deg - lon + 180.0) % 360.0 - 180.0
        if abs(diff) < 1e-7:
            break
        jd += diff / 0.9856473      # 太阳每日行进度
    return jd


# 二十四节气：太阳黄经
TERMS24 = [
    ("春分", 0), ("清明", 15), ("谷雨", 30), ("立夏", 45),
    ("小满", 60), ("芒种", 75), ("夏至", 90), ("小暑", 105),
    ("大暑", 120), ("立秋", 135), ("处暑", 150), ("白露", 165),
    ("秋分", 180), ("寒露", 195), ("霜降", 210), ("立冬", 225),
    ("小雪", 240), ("大雪", 255), ("冬至", 270), ("小寒", 285),
    ("大寒", 300), ("立春", 315), ("雨水", 330), ("惊蛰", 345),
]
TERM_BY_DEG = {d: n for n, d in TERMS24}
# 十二「节」（月令之始），其余为「气」
JIE = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
       "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
JIE_DEG = {n: d for n, d in TERMS24 if n in JIE}


def term_time_cst(year, name):
    """某年某节气的北京时间（datetime）。"""
    deg = dict(TERMS24)[name]
    # 粗略起算：按黄经估月份
    approx_month = {0: 3, 15: 4, 30: 4, 45: 5, 60: 5, 75: 6, 90: 6, 105: 7,
                    120: 7, 135: 8, 150: 8, 165: 9, 180: 9, 195: 10, 210: 10,
                    225: 11, 240: 11, 255: 12, 270: 12, 285: 1, 300: 1,
                    315: 2, 330: 2, 345: 3}[deg]
    y = year if approx_month >= 2 else year
    guess = to_jd(datetime(y, approx_month, 6, 12, 0))
    # 小寒、大寒在 1 月，属「上年冬至之后」，仍用当年 1 月
    jde = solve_sun_longitude(deg, guess)
    # TT → UT
    ut = jde - delta_t(year) / 86400.0
    return from_jd(ut) + timedelta(hours=8)


def terms_of_year(year):
    """某公历年 24 节气的北京时间，按时间排序。"""
    out = []
    for name, deg in TERMS24:
        out.append((name, term_time_cst(year, name)))
    out.sort(key=lambda x: x[1])
    return out


# ---------------- 真太阳时 ----------------
def equation_of_time(day_of_year):
    """均时差（分钟）。"""
    b = (day_of_year - 1) * 360.0 / 365.0
    return 229.18 * (0.000075
                     + 0.001868 * math.cos(math.radians(b))
                     - 0.032077 * math.sin(math.radians(b))
                     - 0.014615 * math.cos(2 * math.radians(b))
                     - 0.040849 * math.sin(2 * math.radians(b)))


def true_solar_time(dt, lon):
    """北京时间 → 当地真太阳时。"""
    off = (lon - 120.0) * 4.0 + equation_of_time(dt.timetuple().tm_yday)
    return dt + timedelta(minutes=off), off


# ---------------- 四柱 ----------------
def jdn_of(d):
    """公历日期 → 儒略日数（正午制，整数）。"""
    return int(to_jd(datetime(d.year, d.month, d.day, 12, 0)) + 0.5)


ANCHOR_2000 = (date(2000, 1, 1), "戊午")
ANCHOR_1900 = (date(1900, 1, 1), "甲戌")


def day_pillar(d):
    """日柱：双锚点交叉，不一致即抛错。"""
    i1 = (JIAZI.index(ANCHOR_2000[1]) + (jdn_of(d) - jdn_of(ANCHOR_2000[0]))) % 60
    i2 = (JIAZI.index(ANCHOR_1900[1]) + (jdn_of(d) - jdn_of(ANCHOR_1900[0]))) % 60
    if i1 != i2:
        raise ValueError("日柱双锚点不一致：%s vs %s" % (JIAZI[i1], JIAZI[i2]))
    return JIAZI[i1]


def year_pillar(dt, lichun):
    """年柱：以立春为界。"""
    y = dt.year if dt >= lichun else dt.year - 1
    return JIAZI[(y - 4) % 60], y


JIE_BRANCH = {"立春": "寅", "惊蛰": "卯", "清明": "辰", "立夏": "巳",
              "芒种": "午", "小暑": "未", "立秋": "申", "白露": "酉",
              "寒露": "戌", "立冬": "亥", "大雪": "子", "小寒": "丑"}


def month_pillar(dt, year_gz, jie_all):
    """月柱：以节为界，五虎遁。jie_all 为跨年十二节（北京时间，升序）。

    月支由「最近一个已过的节」定，月干由五虎遁按年干起正月丙寅顺数。
    正月＝立春，故偏移以立春为 0。
    """
    last = None
    for name, t in jie_all:
        if name in JIE and t <= dt:
            last = name
    if last is None:
        raise ValueError("未找到出生时刻之前的节")
    branch = JIE_BRANCH[last]
    off = (BRANCHES.index(branch) - 2) % 12          # 立春起寅为 0
    yg = year_gz[0]
    start = {"甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚",
             "辛": "庚", "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲"}[yg]
    stem = STEMS[(STEMS.index(start) + off) % 10]
    return stem + branch, last


# ---------------- 交运（纳音定时刻，五年一交） ----------------
# 表 1-3（ps-tiwei-jichu）：交运时刻按生年纳音定，不按三除之日。
JIAOYUN_ANCHOR = {
    "火": ("清明", -3, 12, "午时"),
    "土": ("芒种", 9, 8, "辰时"),
    "金": ("处暑", 0, 16, "申时"),
    "木": ("大寒", 0, 4, "寅时"),
    "水": ("冬至", -3, 22, "亥时"),
}


def jiaoyun_base(year_gz):
    """年命纳音 → 交运基准。六十甲子纳音取末字（如「海中金」→金命）。"""
    wx = nayin(year_gz)[-1]
    term, off, hour, shi = JIAOYUN_ANCHOR[wx]
    return {"纳音": nayin(year_gz), "命": wx + "命", "节气": term,
            "偏移": off, "时": hour, "时辰": shi}


def _jy_date(base, c):
    """第 seq 次交运的公历日：锚节气 ± 偏移日，归到该时辰整点。

    大寒在次年一月，尚在立春之前（虚岁未改），故归入**上一年**那一轮——
    否则木命会把「十岁交运」标到九岁那年去。
    """
    yi = c + 1 if base["节气"] == "大寒" else c
    t = term_time_cst(yi, base["节气"])
    d = t.date() + timedelta(days=base["偏移"])
    return datetime(d.year, d.month, d.day, base["时"], 0)


def jiaoyun_of(year, birth_year, start_age, year_gz, dayun_list=()):
    """某流年内的交运事件（通常 0 或 1 条）。

    口径：起运之年交第一次，此后**每五年一交**（前五年天干主事、后五年地支主事）。
    只算日期与运序，**不判交运吉凶**——凶吉看运与命局，不看交运本身。
    """
    if not (birth_year and start_age):
        return None
    base = jiaoyun_base(year_gz)
    Y = birth_year + start_age - 1
    lc0, lc1 = term_time_cst(year, "立春"), term_time_cst(year + 1, "立春")
    seq0 = max(0, (year - Y) // 5 - 1)
    evs = []
    for seq in range(seq0, seq0 + 4):
        dt = _jy_date(base, Y + 5 * seq)
        if not (lc0 <= dt < lc1):
            continue
        k = seq // 2 + 1
        xu = dt.year - birth_year + 1 - (1 if dt < term_time_cst(dt.year, "立春") else 0)
        evs.append({"序": seq, "日": dt.strftime("%Y-%m-%d"), "时辰": base["时辰"],
                    "运序": k, "段": "天干" if seq % 2 == 0 else "地支",
                    "干支": dayun_list[k - 1] if 0 < k <= len(dayun_list) else "",
                    "虚岁": xu})
    nxt = None
    for seq in range(max(0, (year - Y) // 5), max(0, (year - Y) // 5) + 4):
        dt = _jy_date(base, Y + 5 * seq)
        if dt >= lc1:
            k = seq // 2 + 1
            nxt = {"日": dt.strftime("%Y-%m-%d"), "时辰": base["时辰"], "运序": k,
                   "段": "天干" if seq % 2 == 0 else "地支",
                   "干支": dayun_list[k - 1] if 0 < k <= len(dayun_list) else ""}
            break
    return {"基准": "%s → %s → %s%s%s" % (
                base["纳音"], base["命"], base["节气"],
                ("前%d天" % -base["偏移"]) if base["偏移"] < 0
                else (("后%d天" % base["偏移"]) if base["偏移"] > 0 else "当日"),
                base["时辰"]),
            "起运年": Y, "起运虚岁": start_age, "base": base,
            "events": evs, "下次": nxt}


# ---------------- 流月（应期层：按节分月，五虎遁起月干） ----------------
def liuyue_of(year, pillars=None, dayun_gz=None, kong=(), jiaoyun=None):
    """某流年的十二个月，以「节」为界（立春起寅，小寒起丑）。

    只摆结构：月建、干支、起止日、与四柱（及当前大运）之冲合穿刑伏吟。
    **不判轻重、不作吉凶、不作应期断**——应期仍走「大运定方向、流年定引动、
    流月定月份」三连，此表只把月份摆出来，断不断、断多重，是批者的事。

    丑月起于次年小寒，月干仍随本年干（五虎遁以立春换年干）。
    kong 给「落空之支」，命中则标值空／冲空——只标，不断填不填得上。
    jiaoyun 给本年交运事件，命中则在该月标「交N运·干／支」——
    **交运月只标换气，不判吉凶**（交运本身不论吉凶，吉凶在运与命局）。
    """
    gy = JIAZI[(year - 1984) % 60]
    jl = [(n, term_time_cst(year, n)) for n in JIE if n != "小寒"]
    jl.append(("小寒", term_time_cst(year + 1, "小寒")))
    jl.sort(key=lambda x: x[1])
    start = {"甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚",
             "辛": "庚", "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲"}[gy[0]]
    rows = []
    for i, (name, t) in enumerate(jl):
        branch = JIE_BRANCH[name]
        off = (BRANCHES.index(branch) - 2) % 12
        stem = STEMS[(STEMS.index(start) + off) % 10]
        gz = stem + branch
        end = jl[i + 1][1] if i + 1 < len(jl) else term_time_cst(year + 1, "立春")
        xi = []
        # 三合先看整体：流月之支一到，是否与命局两支凑成全局（如亥未遇卯）
        full = set()
        for grp, wx in SANHE:
            if branch in grp:
                have = {pp[1] for pp in (pillars or []) if pp[1] in grp}
                # 须「流月之支正是缺的那一字」才算局成；否则只是伏吟或半合
                if len(have) >= 2 and branch not in have:
                    full.add(grp)
                    trio = sorted(have | {branch}, key=grp.index)
                    xi.append("三合%s局成（%s）" % (wx, "".join(trio)))
        for j, pp in enumerate(pillars or []):
            b = pp[1]
            # 同一支上的多重关系合写（丑未既冲又刑，写作「冲刑」，
            # 拆成两条会读成算错了一遍）
            tags = []
            if b == branch:
                tags.append("同")
            if CHONG.get(b) == branch:
                tags.append("冲")
            if LIUHE.get(b) == branch:
                tags.append("合")
            if CHUAN.get(b) == branch:
                tags.append("穿")
            if frozenset((b, branch)) in XING_PAIR:
                tags.append("刑")
            if tags:
                xi.append("".join(tags) + "%s支%s" % (POS[j], b))
            for grp, wx in SANHE:                      # 半合（含中支）／拱（缺中支）
                if grp in full:
                    continue                           # 已成全局，不再拆成半合
                if branch in grp and b in grp and branch != b:
                    mid = grp[1]
                    if mid in (branch, b):
                        xi.append("半合%s·%s支%s" % (wx, POS[j], b))
                    else:
                        xi.append("拱%s·%s支%s" % (mid, POS[j], b))
        if dayun_gz and dayun_gz[1] == branch:
            seg = None
            if jiaoyun and jiaoyun.get("起运年") and jiaoyun.get("base"):
                Y, base = jiaoyun["起运年"], jiaoyun["base"]
                seq = max(0, (t.year - Y) // 5)
                if seq and _jy_date(base, Y + 5 * seq) > t:
                    seq -= 1
                seg = "天干" if seq % 2 == 0 else "地支"
            if seg == "天干":
                # 前五年天干主事，运支只在字上，未到支段——不能当「支已到」用
                xi.append("运支%s（干段未到）" % branch)
            else:
                xi.append("同运支%s" % branch)
        for kz in kong:                                # 值空／冲空只标结构
            if kz == branch:
                xi.append("值空")
            elif CHONG.get(kz) == branch:
                xi.append("冲空")
        for ev in ((jiaoyun or {}).get("events") or []):
            ed = datetime.strptime(ev["日"], "%Y-%m-%d")
            if t <= ed < end:                          # 交运时刻落在本月区间内
                xi.append("交%d运·%s" % (ev["运序"], ev["段"]))
        rows.append({"建": branch, "节": name, "干支": gz,
                     "起": t.strftime("%Y-%m-%d"), "止": end.strftime("%Y-%m-%d"),
                     "系": xi})
    return {"year": year, "year_gz": gy, "rows": rows, "jiaoyun": jiaoyun}


def hour_pillar(dt_tst, day_gz):
    """时柱：五鼠遁。dt_tst 为真太阳时。"""
    h = dt_tst.hour
    branch = BRANCHES[((h + 1) // 2) % 12]      # 23-1 子、1-3 丑 …
    dg = day_gz[0]
    start = {"甲": "甲", "己": "甲", "乙": "丙", "庚": "丙", "丙": "戊",
             "辛": "戊", "丁": "庚", "壬": "庚", "戊": "壬", "癸": "壬"}[dg]
    base = STEMS.index(start)
    off = BRANCHES.index(branch)
    return STEMS[(base + off) % 10] + branch


def effective_day(dt_tst):
    """晚子时换日：本器取「子初换日」（23:00 后日柱进一位）。

    **不是**「梁氏定论」——原书两法并存，本器取其一并明示，不代裁（未决登记 U-P9-01）：
      ·《命学大辞渊》述元史曆法「建子初——即二十三点换日柱」，
        明大统「命起子正，即以午夜○时换日柱」，并谓「此為子正、子夜二大差之根源」。
      · 若按子正（0 点）换日，23:00–23:59 生者日柱与时柱皆不同，六亲、晚运随之异。
    故凡落此段者，输出必附「时辰边界」一行；静默换日等于替读者作了主张。
    """
    if dt_tst.hour >= 23:
        return dt_tst.date() + timedelta(days=1)
    return dt_tst.date()


def dayun(month_gz, forward, birth_dt_tst, jie_list_all, n=8):
    """大运：顺逆排 + 起运精确到年月日。"""
    step = 1 if forward else -1
    out = []
    i = JIAZI.index(month_gz)
    for k in range(1, n + 1):
        out.append(JIAZI[(i + step * k) % 60])
    # 起运：顺数至下一「节」，逆数至上一「节」（只认十二节，不认气）
    if forward:
        nxt = [t for nm, t in jie_list_all if nm in JIE and t > birth_dt_tst]
        target = min(nxt) if nxt else None
    else:
        prv = [t for nm, t in jie_list_all if nm in JIE and t <= birth_dt_tst]
        target = max(prv) if prv else None
    start = None
    if target:
        mins = abs((target - birth_dt_tst).total_seconds()) / 60.0
        years = int(mins // 4320)
        rem = mins % 4320
        months = int(rem * 4 / 1440)
        rem2 = rem - months * 1440 / 4
        days = int(rem2 / 120 * 10)
        start = {"年": years, "月": months, "日": days,
                 "虚岁": years + 1, "节气": None}
        # 找节气名
        for nm, t in jie_list_all:
            if t == target:
                start["节气"] = nm
        # 精确起运日
        d = birth_dt_tst.date()
        y2 = d.year + years
        m2 = d.month + months
        while m2 > 12:
            m2 -= 12
            y2 += 1
        try:
            d2 = date(y2, m2, min(d.day, 28)) + timedelta(days=days)
        except ValueError:
            d2 = date(y2, m2, 1) + timedelta(days=days)
        start["起运日"] = d2.isoformat()
        # 交运时的虚岁（虚岁 = 交运年 - 出生年 + 1），与「折年数」分开标，免混
        start["交运虚岁"] = d2.year - d.year + 1
    return out, start


# ---------------- 十神 ----------------
def shishen(day_stem, other):
    """以日干为我，判十神。other 可为天干或地支（地支取其本气）。"""
    if other in BRANCHES:
        other = CANG[other][0]
    me, ot = WX_OF[day_stem], WX_OF[other]
    same = (STEMS.index(day_stem) % 2) == (STEMS.index(other) % 2)
    order = "木火土金水"
    mi, oi = order.index(me), order.index(ot)
    rel = (oi - mi) % 5
    if rel == 0:
        return "比肩" if same else "劫财"
    if rel == 1:
        return "食神" if same else "伤官"
    if rel == 2:
        return "偏财" if same else "正财"
    if rel == 3:
        return "七杀" if same else "正官"
    return "偏印" if same else "正印"


# ---------------- 主流程 ----------------
def paipan(d, tstr, gender, lon=None, name=""):
    hh, mm = [int(x) for x in tstr.split(":")]
    dt_bj = datetime(d.year, d.month, d.day, hh, mm)
    checks = []

    def ck(code, ok, msg):
        checks.append({"code": code, "ok": bool(ok), "msg": msg})

    # 真太阳时
    if lon is None:
        dt_tst = dt_bj
        tst_note = "未校正（未给经度，按北京时间）"
        ck("P02", True, "未给经度，真太阳时未校正（已明示，不假装校正）")
    else:
        dt_tst, off = true_solar_time(dt_bj, lon)
        off_txt = ("%+.0f 分钟" % off) if abs(off) >= 0.5 else \
            "0 分钟（经度修正与均时差相抵）"
        tst_note = "经度 %.2f°，偏移 %s → %s" % (lon, off_txt, dt_tst.strftime("%H:%M"))
        ck("P02", True, "真太阳时已校正：%s" % tst_note)

    # 节气
    jie_all = []
    for y in (d.year - 1, d.year, d.year + 1):
        for nm, t in terms_of_year(y):
            jie_all.append((nm, t))
    jie_all.sort(key=lambda x: x[1])
    jie_list = [(n, t) for n, t in jie_all if n in JIE and t.year == d.year]
    if len(jie_list) != 12:
        jie_list = [(n, t) for n, t in jie_all if n in JIE]
    ck("P03", len(jie_list) >= 12, "本年十二节已算得（天文算法，本地）")

    # 年柱以本年立春为界（须取出生年那一个立春，不可取 dict 折叠后的）
    lichun = None
    for nm, t in jie_all:
        if nm == "立春" and t.year == d.year:
            lichun = t
    if lichun is None:
        raise ValueError("未找到 %d 年立春" % d.year)
    ygz, ynum = year_pillar(dt_tst, lichun)
    ck("P04", ygz == JIAZI[(ynum - 4) % 60] and
       (dt_tst >= lichun) == (ynum == d.year),
       "年柱 %s（以立春 %s 为界）" % (ygz, lichun.strftime("%Y-%m-%d %H:%M")))

    mgz, mgz_jie = month_pillar(dt_tst, ygz, jie_all)
    ck("P05", True, "月柱 %s（以「%s」为界，五虎遁）" % (mgz, mgz_jie))

    dgz = day_pillar(effective_day(dt_tst))
    ck("P06", True, "日柱 %s（双锚点交叉一致：2000-01-01 戊午 / 1900-01-01 甲戌）" % dgz)

    hgz = hour_pillar(dt_tst, dgz)
    ck("P07", True, "时柱 %s（真太阳时 %s，五鼠遁）" % (hgz, dt_tst.strftime("%H:%M")))

    pillars = [ygz, mgz, dgz, hgz]
    ck("P08", all(p in JIAZI_SET for p in pillars), "四柱皆为合法干支")

    # 距节气报警
    near = []
    for nm, t in jie_all:
        gap = abs((dt_tst - t).total_seconds()) / 60.0
        if gap <= 45:
            near.append("%s 相差 %.0f 分钟" % (nm, gap))
    if near:
        ck("P09", False, "生日距节气过近（%s）：本器节气误差约 ±15 分钟，"
                         "月柱须用专业排盘软件复核" % "；".join(near))
    else:
        ck("P09", True, "生日距最近节气 > 45 分钟，月柱无边界风险")

    # 大运
    forward = (ygz[0] in YANG) == (gender == "男")
    dys, start = dayun(mgz, forward, dt_tst, jie_all)
    ck("P10", forward == ((ygz[0] in YANG) == (gender == "男")),
       "大运%s排（年干 %s 为%s，%s命）" % ("顺" if forward else "逆", ygz[0],
                                          "阳" if ygz[0] in YANG else "阴", gender))
    if start:
        ok = 0 <= start["年"] <= 10
        ck("P11", ok, "起运折 %d 年 %d 月 %d 日，%s 交运（交运虚岁 %d，数至「%s」）%s" % (
            start["年"], start["月"], start["日"], start["起运日"],
            start.get("交运虚岁", start["虚岁"]), start["节气"] or "",
            "" if ok else "——超出 0~10 岁，节气可能取错"))
    else:
        ck("P11", False, "起运未能算出（节气表不完整）")

    # 十神 / 藏干 / 纳音 / 空亡
    day_stem = dgz[0]
    detail = []
    for k, p in enumerate(pillars):
        cg = CANG[p[1]]
        detail.append({
            "pos": POS[k], "gz": p,
            "stem_ss": "日主" if k == 2 else shishen(day_stem, p[0]),
            "branch_ss": shishen(day_stem, p[1]),
            "cang": [{"gan": g, "ss": shishen(day_stem, g)} for g in cg],
            "nayin": nayin(p),
            "kong": list(kong_of(p)),
        })
    ck("P12", len(detail) == 4 and all(d["cang"] for d in detail), "十神／藏干／纳音已出")

    # 五行统计（含藏干）
    wx = {e: 0 for e in "木火土金水"}
    for p in pillars:
        wx[WX_OF[p[0]]] += 1
        for g in CANG[p[1]]:
            wx[WX_OF[g]] += 1
    ck("P13", sum(wx.values()) == 4 + sum(len(CANG[p[1]]) for p in pillars),
       "五行统计含藏干共 %d 字" % sum(wx.values()))

    # 逐柱空亡落点（年柱旬、日柱旬两查）
    kong_hits = kong_hits_of(pillars)
    ck("P14", True, "逐柱空亡已两查（%d 处落空）" % len(kong_hits))

    # 空亡四判（结构事实，不出断语）
    kong_judge = judge_kong(pillars, d.year,
                            start.get("交运虚岁", start["虚岁"]) if start else None)
    ck("P16", True, "空亡四判已出（%s）" % (
        "；".join("%s%s%s%s" % (k["落"], k["宾主"], k["根"], "受击" if k["击"] else "未击")
                 for k in kong_judge) if kong_judge else "四柱无落空"))

    # 关系矩阵（刑冲合穿拱、暗合、禄刃；只摆关系，不论吉凶）
    rel = relations_of(pillars)
    ck("P17", True, "关系矩阵已出（%d 条：%s；日主%s　禄%s）" % (
        len(rel["relations"]),
        "、".join(r["字"] + r["类"] for r in rel["relations"]) or "四支天干无刑冲合穿",
        rel["lushen"]["日主"], rel["lushen"]["禄"]))

    # 当前大运（以今年计）
    today = date.today()
    cur = None
    if start and start.get("起运日"):
        sy = date.fromisoformat(start["起运日"])
        age = today.year - sy.year
        if age >= 0:
            idx = age // 10
            if idx < len(dys):
                cur = {"gz": dys[idx], "from": sy.year + idx * 10,
                       "to": sy.year + idx * 10 + 9,
                       "xu": start["虚岁"] + idx * 10}
    ck("P15", True, "当前大运：%s" % (("%s（%d–%d）" % (cur["gz"], cur["from"], cur["to"]))
                                    if cur else "未到起运"))

    return {
        "input": {"name": name, "date": d.isoformat(), "time": tstr,
                  "gender": gender, "lon": lon,
                  "bj": dt_bj.strftime("%Y-%m-%d %H:%M"),
                  "tst": dt_tst.strftime("%Y-%m-%d %H:%M"), "tst_note": tst_note},
        "pillars": pillars, "detail": detail,
        "borders": _borders(dt_bj, dt_tst),
        "wuxing": wx, "missing": [e for e in "木火土金水" if wx[e] == 0],
        "forward": forward, "dayun": dys, "start": start, "current": cur,
        "dayun_rows": dayun_rows(dys, d.year,
                                 start.get("交运虚岁", start["虚岁"]) if start else None),
        "kong_hits": kong_hits,
        "kong_judge": kong_judge,
        "relations": rel["relations"],
        "lushen": rel["lushen"],
        "jie": [{"name": n, "time": t.strftime("%Y-%m-%d %H:%M")}
                for n, t in jie_all if t.year == d.year],
        "checks": checks,
        "all_pass": all(c["ok"] for c in checks),
        "evidence_grade": "E6_结构计算",
    }


def _borders(dt_bj, dt_tst):
    """时辰边界提示：日柱可能因「换日法」或「真太阳时跨日」而与直觉不同时，必须说出来。

    这两件事的共同点是——盘照样排得出来，结果也照样「全部通过」，
    但日柱可能差一天。不提示，读者拿去用，错的是六亲与晚运。
    """
    out = []
    if dt_tst.hour >= 23:
        out.append(
            "**晚子时（真太阳时 %s）**：本器取**子初换日**，日柱已进一位。"
            "原书两法并存——《命学大辞渊》述元史「建子初，即二十三点换日柱」，"
            "明大统「命起子正，即午夜○时换日柱」，并谓此为「子正、子夜二大差之根源」。"
            "若按子正换日，日柱退回前一日、时干随之变。本器取其一并明示，不代裁（未决 U-P9-01）。"
            % dt_tst.strftime("%H:%M"))
    if dt_tst.date() != dt_bj.date():
        out.append(
            "**真太阳时跨日**：北京时间 %s → 真太阳时 %s，日柱按真太阳时取。"
            "同一生日不做经度校正，日柱会落在另一日——此造须先定出生地经度，再论其余。"
            % (dt_bj.strftime("%Y-%m-%d %H:%M"), dt_tst.strftime("%Y-%m-%d %H:%M")))
    return out


# ---------------- 四柱入口：五项自检 ----------------
# 形近字表（`references/仲裁摘要.md` 第六节）：误写 → 正字。
# 只在「该位上不可能出现此字」时才改，不改字义合法的字——「己」在天干位就是己，
# 「巳」在地支位就是巳，一律强改反而把对的改错。
XINGJIN = {"戍": "戌", "已": "巳", "末": "未", "西": "酉", "牛": "午", "印": "卯",
           "戉": "戌", "戊": "戊"}
# 天干位误写地支、地支位误写天干的常见组合（不改，只提示人工核）
STEM_LIKE_BRANCH = {"巳": "己", "子": "己"}
BRANCH_LIKE_STEM = {"己": "巳", "乙": "巳"}


def check_pillars(pillars):
    """五项自检之①形近字 ②干支合法性。返回 (纠正后四柱, 问题列表, 是否致命)。

    致命＝改不出来，必须退回问用户；非致命＝已按形近字改正，须复述请用户核。
    """
    fixed, issues, fatal = [], [], False
    if len(pillars) != 4:
        return pillars, ["四柱须为四组干支，实得 %d 组" % len(pillars)], True
    for idx, gz in enumerate(pillars):
        pos = POS[idx]
        if len(gz) != 2:
            issues.append("%s柱「%s」不是两个字" % (pos, gz))
            fatal = True
            fixed.append(gz)
            continue
        g, z = gz[0], gz[1]
        # ① 形近字（逐位判：天干位、地支位各有各的合法集）
        if g not in STEMS:
            if g in XINGJIN and XINGJIN[g] in STEMS:
                issues.append("%s柱天干「%s」疑为「%s」误写，已按形近字改" % (pos, g, XINGJIN[g]))
                g = XINGJIN[g]
            elif g in STEM_LIKE_BRANCH:
                issues.append("%s柱天干「%s」是地支，疑为「%s」误写，已按形近字改"
                              % (pos, g, STEM_LIKE_BRANCH[g]))
                g = STEM_LIKE_BRANCH[g]
            else:
                issues.append("%s柱天干「%s」不在十干之内" % (pos, g))
                fatal = True
        if z not in BRANCHES:
            if z in XINGJIN and XINGJIN[z] in BRANCHES:
                issues.append("%s柱地支「%s」疑为「%s」误写，已按形近字改" % (pos, z, XINGJIN[z]))
                z = XINGJIN[z]
            elif z in BRANCH_LIKE_STEM:
                issues.append("%s柱地支「%s」是十神用字，疑为「%s」误写，已按形近字改"
                              % (pos, z, BRANCH_LIKE_STEM[z]))
                z = BRANCH_LIKE_STEM[z]
            else:
                issues.append("%s柱地支「%s」不在十二支之内" % (pos, z))
                fatal = True
        gz2 = g + z
        # ② 干支合法性（阴阳同、六十甲子内）
        if len(gz2) == 2 and gz2 not in JIAZI_SET:
            issues.append("%s柱「%s」非六十甲子内之合法组合（干支阴阳须同）" % (pos, gz2))
            fatal = True
        fixed.append(gz2)
    return fixed, issues, fatal


def _parity_note(gz):
    return "阳" if gz[0] in YANG else "阴"


def dayun_rows(dys, birth_year, start_age, now_year=None):
    """把大运干支铺成「虚岁区间 × 公历年」。虚岁口径：虚岁 = 公元年 − 出生年 + 1。

    行内口径（`ps-zonglun-guide` §1.4④）：交运虚岁 S ⇒ 交运年 = 出生年 + S − 1，
    第 k 步运占虚岁 S+10k ～ S+10k+9。
    """
    if not (birth_year and start_age):
        return []
    rows = []
    today = now_year or date.today().year
    for k, gz in enumerate(dys):
        xu1, xu2 = start_age + 10 * k, start_age + 10 * k + 9
        y1, y2 = birth_year + xu1 - 1, birth_year + xu2 - 1
        rows.append({"gz": gz, "xu1": xu1, "xu2": xu2, "y1": y1, "y2": y2,
                     "now": y1 <= today <= y2})
    return rows


def paipan_from_pillars(pillars, gender, birth_year=None, start_age=None, name=""):
    """四柱入口：不重排四柱，只核 + 补结构。返回结构与 paipan() 同形。"""
    checks = []

    def ck(code, ok, msg):
        checks.append({"code": code, "ok": bool(ok), "msg": msg})

    fixed, issues, fatal = check_pillars(pillars)
    ck("P01", not fatal, "形近字／干支合法性：" + ("；".join(issues) if issues else "四柱皆合法，无待改之字"))
    ck("P02", True, "时柱为用户所报，未经真太阳时校正（本入口不做历法推算）")
    pillars = fixed
    if fatal:
        return {"input": {"mode": "pillars", "pillars": pillars, "gender": gender,
                          "name": name, "birth_year": birth_year, "start_age": start_age},
                "pillars": pillars, "detail": [], "checks": checks, "all_pass": False,
                "kong_hits": [], "kong_judge": [], "relations": [], "lushen": {},
                "dayun": [], "dayun_rows": [], "borders": [],
                "forward": None, "start": {}, "current": None,
                "error": "四柱不合法，须退回问用户，不得代改代补"}

    day_stem = pillars[2][0]
    detail = []
    for k, p in enumerate(pillars):
        cg = CANG[p[1]]
        detail.append({
            "pos": POS[k], "gz": p,
            "stem_ss": "日主" if k == 2 else shishen(day_stem, p[0]),
            "branch_ss": shishen(day_stem, p[1]),
            "cang": [{"gan": g, "ss": shishen(day_stem, g)} for g in cg],
            "nayin": nayin(p),
            "kong": list(kong_of(p)),
        })
    ck("P03", True, "十神／藏干／纳音已出")

    wx = {e: 0 for e in "木火土金水"}
    for p in pillars:
        wx[WX_OF[p[0]]] += 1
        for g in CANG[p[1]]:
            wx[WX_OF[g]] += 1
    ck("P04", sum(wx.values()) == 4 + sum(len(CANG[p[1]]) for p in pillars),
       "五行统计含藏干共 %d 字%s" % (sum(wx.values()),
                               "，缺" + "、".join(e for e in "木火土金水" if wx[e] == 0)
                               if any(wx[e] == 0 for e in "木火土金水") else "，五行俱全"))

    # ③ 顺逆
    forward = (pillars[0][0] in YANG) == (gender == "男")
    ck("P05", True, "大运%s排（年干 %s 为%s，%s命）" % (
        "顺" if forward else "逆", pillars[0][0], _parity_note(pillars[0]), gender or "未注"))

    # 大运序列（只排干支，起运岁须另给）
    step = 1 if forward else -1
    i = JIAZI.index(pillars[1])
    dys = [JIAZI[(i + step * k) % 60] for k in range(1, 9)]
    ck("P06", True, "大运八步已排（%s）%s" % (
        "　".join(dys),
        "" if start_age else "；未给 --start-age，只出干支序列，不出公历年"))

    # ④ 起运数
    if start_age:
        ck("P07", True, "起运按用户所报：交运虚岁 %d%s" % (
            start_age, "（%d 年交运）" % (birth_year + start_age - 1) if birth_year else ""))
    else:
        ck("P07", True, "起运数未报——应期只能到运、不到年；请用户补起运岁或生日")

    # ⑤ 旬空两查（年柱旬、日柱旬）
    kong_hits = kong_hits_of(pillars)
    ck("P08", True, "旬空已两查（年柱旬 %s／日柱旬 %s；%d 处落空）" % (
        "".join(kong_of(pillars[0])), "".join(kong_of(pillars[2])), len(kong_hits)))

    # 空亡四判（结构事实，不出断语）
    kong_judge = judge_kong(pillars, birth_year, start_age)
    ck("P10", True, "空亡四判已出（%s）" % (
        "；".join("%s%s%s%s" % (k["落"], k["宾主"], k["根"], "受击" if k["击"] else "未击")
                 for k in kong_judge) if kong_judge else "四柱无落空"))

    # 关系矩阵（刑冲合穿拱、暗合、禄刃；只摆关系，不论吉凶）
    rel = relations_of(pillars)
    ck("P17", True, "关系矩阵已出（%d 条：%s；日主%s　禄%s）" % (
        len(rel["relations"]),
        "、".join(r["字"] + r["类"] for r in rel["relations"]) or "四支天干无刑冲合穿",
        rel["lushen"]["日主"], rel["lushen"]["禄"]))

    rows = dayun_rows(dys, birth_year, start_age)
    cur = next((r for r in rows if r["now"]), None)
    ck("P09", True, "当前大运：%s" % (("%s（虚岁 %d–%d，%d–%d）" % (
        cur["gz"], cur["xu1"], cur["xu2"], cur["y1"], cur["y2"])) if cur else "未定位（缺出生年或起运岁）"))

    return {
        "input": {"mode": "pillars", "name": name, "pillars": pillars, "gender": gender,
                  "birth_year": birth_year, "start_age": start_age},
        "pillars": pillars, "detail": detail,
        "borders": [],
        "wuxing": wx, "missing": [e for e in "木火土金水" if wx[e] == 0],
        "forward": forward, "dayun": dys,
        "start": {"交运虚岁": start_age, "虚岁": start_age} if start_age else None,
        "current": cur, "dayun_rows": rows,
        "kong_hits": kong_hits,
        "kong_judge": kong_judge,
        "relations": rel["relations"],
        "lushen": rel["lushen"],
        "issues": issues,
        "checks": checks,
        "all_pass": all(c["ok"] for c in checks),
        "evidence_grade": "E6_结构计算",
        "note": "四柱入口：四柱为来客所报之既成事实，本器只核不改（形近字除外，已复述须请用户确认）",
    }


def render(r):
    L = []
    L.append("# 排盘（E6 结构计算 · 不出断语）")
    L.append("")
    if r.get("error"):
        # 四柱不合法一律停手：不排、不猜、不代改。此处必须先于任何字段读取，
        # 否则下面取 forward 会崩成 traceback，把「该退回问用户」变成看不懂的报错。
        L.append("## 停手：四柱不合法")
        L.append("")
        L.append("> " + r["error"])
        L.append("")
        if r.get("issues"):
            L.append("## 形近字与合法性（须复述请来客确认）")
            L.append("")
            for it in r["issues"]:
                L.append("- " + it)
            L.append("")
        L.append("| 项 | 值 |")
        L.append("|---|---|")
        L.append("| 四柱（来客所报） | %s |" % "　".join(r.get("pillars") or []))
        L.append("| 性别 | %s |" % ((r.get("input") or {}).get("gender") or "未注"))
        L.append("")
        L.append("## 自检")
        L.append("")
        for c in r.get("checks", []):
            L.append("- %s %s　%s" % ("✅" if c["ok"] else "❌", c["code"], c["msg"]))
        L.append("")
        L.append("## 处理")
        L.append("")
        L.append("四柱有一柱不成立，全盘十神、藏干、大运、空亡、关系皆无从算起。"
                 "本器按例停手，请复述来客原报之字，问明后再排。")
        return "\n".join(L)
    L.append("")
    i = r["input"]
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    if i.get("mode") == "pillars":
        L.append("| 入口 | 四柱入口（来客自报，只核不改） |")
    else:
        L.append("| 公历 | %s %s（北京时间） |" % (i["date"], i["time"]))
        L.append("| 真太阳时 | %s |" % i["tst"])
        L.append("| 校正 | %s |" % i["tst_note"])
    L.append("| 性别 | %s |" % (i["gender"] or "未注"))
    L.append("| 四柱 | %s |" % "　".join(r["pillars"]))
    if i.get("birth_year"):
        L.append("| 出生年 | %d |" % i["birth_year"])
    st = r.get("start") or {}
    if st.get("起运日"):
        L.append("| 起运 | %s排　折 %d 年 %d 月 %d 日　%s 交运（交运虚岁 %d） |" % (
            "顺" if r["forward"] else "逆", st["年"], st["月"], st["日"],
            st["起运日"], st.get("交运虚岁", st["虚岁"])))
    elif st.get("交运虚岁"):
        L.append("| 起运 | %s排　交运虚岁 %d（按来客所报） |" % (
            "顺" if r["forward"] else "逆", st["交运虚岁"]))
    else:
        L.append("| 起运 | %s排　起运数未报（应期只能到运、不到年） |" % (
            "顺" if r["forward"] else "逆"))
    L.append("")
    if r.get("borders"):
        L.append("## 时辰边界（须先看这一节，再看四柱）")
        L.append("")
        for b in r["borders"]:
            L.append("> " + b)
            L.append("")
    if r.get("issues"):
        L.append("## 形近字与合法性（须复述请来客确认）")
        L.append("")
        for s in r["issues"]:
            L.append("- " + s)
        L.append("")
    L.append("## 四柱明细")
    L.append("")
    L.append("| 柱 | 干支 | 天干十神 | 地支十神 | 藏干 | 纳音 | 旬空 |")
    L.append("|---|---|---|---|---|---|---|")
    for d in r["detail"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            d["pos"], d["gz"], d["stem_ss"], d["branch_ss"],
            "／".join("%s%s" % (c["gan"], c["ss"]) for c in d["cang"]),
            d["nayin"], "".join(d["kong"])))
    L.append("")
    L.append("## 五行（含藏干）")
    L.append("")
    L.append("　".join("%s%d" % (k, v) for k, v in r["wuxing"].items())
             + ("　**缺：%s**" % "、".join(r["missing"]) if r["missing"] else "　五行俱全"))
    L.append("")
    L.append("## 大运")
    L.append("")
    rows = r.get("dayun_rows") or []
    if rows:
        L.append("| 运 | 干支 | 虚岁 | 公历 | 今 |")
        L.append("|---|---|---|---|---|")
        for k, x in enumerate(rows, 1):
            L.append("| 第%d运 | %s | %d–%d | %d–%d | %s |" % (
                k, x["gz"], x["xu1"], x["xu2"], x["y1"], x["y2"], "◀ 今" if x["now"] else ""))
    else:
        L.append("　".join(r.get("dayun") or []))
        L.append("")
        L.append("> 未给出生年＋起运岁，故只出干支序列，不铺公历年——"
                 "「运未立则流年只记结构，不下断」。")
    L.append("")
    lly = r.get("liuyue")
    if lly:
        L.append("## 流月（%d 年 %s，按节分月）" % (lly["year"], lly["year_gz"]))
        L.append("")
        L.append("> 月建以「节」为界（立春起寅、小寒起丑），月干五虎遁。只摆干支与冲合穿刑，"
                 "不判轻重、不作吉凶。")
        L.append("")
        L.append("| 节 | 建 | 干支 | 起 | 止 | 与命局 |")
        L.append("|---|---|---|---|---|---|")
        for x in lly["rows"]:
            L.append("| %s | %s | **%s** | %s | %s | %s |" % (
                x["节"], x["建"], x["干支"], x["起"], x["止"],
                "；".join(x["系"]) or "无"))
        L.append("")
    L.append("## 逐柱空亡（两柱都查）")
    L.append("")
    if r["kong_hits"]:
        for k in r["kong_hits"]:
            L.append("- %s柱%s（%s旬）空 %s → **%s柱%s 落空**" % (
                k["旬位"], k["旬"], k["旬名"], "".join(k["空"]), k["位"], k["落"]))
    else:
        L.append("- 四柱无落空。")
    L.append("")
    L.append("## 关系矩阵（结构事实，不论吉凶）")
    L.append("")
    L.append("> 只列「哪个字与哪个字发生了什么」。轻重归断法层：贴身与遥隔不同论，主位与宾位不同论。")
    L.append("")
    rels = r.get("relations") or []
    if rels:
        L.append("| 类 | 字 | 位 | 注 |")
        L.append("|---|---|---|---|")
        for x in rels:
            L.append("| %s | **%s** | %s | %s |" % (
                x["类"], x["字"], "、".join(x["位"]), x["注"] or "—"))
    else:
        L.append("- 四支天干无刑冲合穿。")
    ls = r.get("lushen") or {}
    if ls:
        L.append("")
        L.append("日主 **%s**　禄：%s　刃：%s" % (ls["日主"], ls["禄"], ls["刃"]))
    L.append("")
    if r.get("shensha"):
        L.append("## 神煞十二项（佐证层，不作主断）")
        L.append("")
        L.append("> %s起法逐条见 `ps-shensha/references/起法表.md`（仲裁 #22）；"
                 "本节只摆「起法 → 落于哪一柱」，吉凶与应事归断法层，"
                 "神煞不作独立断命依据（仲裁 #10）。" % SHENSHA_NOTE)
        L.append("")
        L.append("| 神煞 | 起法 | 查 | 落 |")
        L.append("|---|---|---|---|")
        for x in r["shensha"]:
            L.append("| **%s** | %s | %s | %s |" % (x["名"], x["起法"], x["查"], x["落"]))
        L.append("")
    L.append("")
    L.append("## 空亡四判（结构事实，不论吉凶）")
    L.append("")
    L.append("> 本器只算四件可核之事：落于主位还是宾位、有无根、有无冲穿刑来击、何年值冲合。")
    L.append("> **「金空则鸣」鸣不鸣、鸣出什么，是断法层的取象，此处不下结论。**")
    L.append("")
    if not r.get("kong_judge"):
        L.append("- 四柱无落空，四判不适用。")
    for k in r.get("kong_judge") or []:
        L.append("- **%s支%s（%s）**　落于%s柱｜由 %s" % (
            "／".join(k["位"]), k["落"], k["五行"], "、".join(k["位"]), "、".join(k["旬"])))
        L.append("  - 位：**%s**——%s" % (k["宾主"], k["宾主由"]))
        L.append("  - 根：**%s**——%s" % (k["根"], k["根由"]))
        L.append("  - 击：%s" % ("**" + "；".join(k["击"]) + "**" if k["击"] else "未受冲穿刑"))
        if k["值"] or k["冲"] or k["合"]:
            L.append("  - 值 %s｜冲 %s｜合 %s" % (
                "、".join(map(str, k["值"])) or "—",
                "、".join(map(str, k["冲"])) or "—",
                "、".join(map(str, k["合"])) or "—"))
        else:
            L.append("  - 值／冲／合：未给出生年，只出结构不出年")
    L.append("")
    L.append("## 自检")
    L.append("")
    for c in r["checks"]:
        L.append("- %s %s　%s" % ("✅" if c["ok"] else "❌", c["code"], c["msg"]))
    L.append("")
    L.append("**结论：%s**" % ("全部通过" if r["all_pass"] else "有 FAIL，须修正后再用"))
    if r.get("error"):
        L.append("")
        L.append("**停手：%s**" % r["error"])
    return "\n".join(L)


def self_test():
    """自检：日柱锚点、已知盘、节气落点。"""
    bad = []
    # 1. 双锚点
    if day_pillar(date(2000, 1, 1)) != "戊午":
        bad.append("2000-01-01 应为戊午")
    if day_pillar(date(1900, 1, 1)) != "甲戌":
        bad.append("1900-01-01 应为甲戌")
    # 2. 已知盘：1984-11-12 未时 → 甲子 乙亥 庚戌 癸未
    r = paipan(date(1984, 11, 12), "14:00", "男")
    want = ["甲子", "乙亥", "庚戌", "癸未"]
    if r["pillars"] != want:
        bad.append("1984-11-12 14:00 应得 %s，实得 %s" % (want, r["pillars"]))
    # 3. 节气落点（公历日）
    for y, name, lo, hi in ((2026, "立春", (2, 3), (2, 5)),
                            (2026, "冬至", (12, 21), (12, 23)),
                            (2026, "夏至", (6, 20), (6, 22)),
                            (2026, "春分", (3, 19), (3, 22)),
                            (1984, "立冬", (11, 6), (11, 9))):
        t = term_time_cst(y, name)
        d = (t.month, t.day)
        if not (lo <= d <= hi):
            bad.append("%d %s 落 %s，应在 %s–%s" % (y, name, d, lo, hi))
    # 4. 大运顺逆
    if not paipan(date(1984, 11, 12), "14:00", "男")["forward"]:
        bad.append("甲年男命应顺排")
    if paipan(date(1984, 11, 12), "14:00", "女")["forward"]:
        bad.append("甲年女命应逆排")
    # 5. 四柱入口：形近字纠正 + 顺逆 + 旬空两查
    r2 = paipan_from_pillars(["甲子", "乙亥", "庚戍", "癸未"], "男", 1984, 10)
    if r2["pillars"] != ["甲子", "乙亥", "庚戌", "癸未"]:
        bad.append("「庚戍」应校为「庚戌」，实得 %s" % r2["pillars"])
    if not r2["forward"]:
        bad.append("甲子年男命（四柱入口）应顺排")
    if not any(k["位"] == "月" and k["落"] == "亥" for k in r2["kong_hits"]):
        bad.append("甲子年柱旬空戌亥，月支亥应落空")
    if not r2["dayun"][0] == "丙子":
        bad.append("甲子 乙亥 顺排首运应为丙子，实得 %s" % (r2["dayun"][:1],))
    rows = r2["dayun_rows"]
    if not rows or rows[3]["y1"] != 2023 or rows[3]["gz"] != "己卯":
        bad.append("起运虚岁 10、1984 年生，第 4 运应为己卯 2023 起")
    # 6. 非法四柱必须被拦
    r3 = paipan_from_pillars(["甲丑", "乙亥", "庚戌", "癸未"], "男")
    if r3["all_pass"]:
        bad.append("「甲丑」阴阳不同，应判不合法")

    # 7. 空亡四判：以甲子 乙亥 庚戌 癸未 为锚（年柱甲子旬空戌亥）
    kj = {k["落"]: k for k in r2["kong_judge"]}
    if set(kj) != {"戌", "亥"}:
        bad.append("该盘应只有戌、亥两支落空，实得 %s" % sorted(kj))
    if kj.get("戌", {}).get("根") != "有根":
        bad.append("戌得时支「未」同气相扶，应判有根")
    if not any("未" in s for s in kj.get("戌", {}).get("击", [])):
        bad.append("未戌相刑，戌应记受击")
    if kj.get("亥", {}).get("根") != "有根":
        bad.append("亥藏「甲」透于年干，应判有根")
    if kj.get("亥", {}).get("击"):
        bad.append("亥无冲穿刑，应判未击")
    if 1994 not in kj.get("戌", {}).get("值", []):
        bad.append("戌之值年应含 1994（甲戌）")
    # 无根之空：戌无同气、藏干不透
    r4 = paipan_from_pillars(["甲子", "乙卯", "庚戌", "壬午"], "男", 1950, 8)
    k4 = {k["落"]: k for k in r4["kong_judge"]}
    if k4.get("戌", {}).get("根") != "无根":
        bad.append("甲子/乙卯/庚戌/壬午：戌无同气且藏干不透，应判无根")
    # 旬名须取旬首：庚戌属甲辰旬，旧码误取 JIAZI[4] 作「戊辰」
    if not any(h["旬名"] == "甲辰" for h in r4["kong_hits"]):
        bad.append("庚戌属甲辰旬，旬名不得取成「戊辰」")
    # 自刑：两支亥相见，且年柱甲子旬空戌亥
    r5 = paipan_from_pillars(["甲子", "乙亥", "己亥", "丙寅"], "男", 1950, 8)
    k5 = {k["落"]: k for k in r5["kong_judge"]}
    if not any("自刑" in s for s in k5.get("亥", {}).get("击", [])):
        bad.append("两亥相见，应记自刑")

    # 8. 关系矩阵与空亡宾主：仍以甲子 乙亥 庚戌 癸未 为锚
    rs = {(x["类"], x["字"]) for x in r2["relations"]}
    for wt in (("六穿", "子未"), ("相刑", "戌未"), ("拱", "亥未"),
               ("天干五合", "乙庚"), ("天干相冲", "甲庚"),
               ("暗合", "甲己"), ("暗合", "癸戊")):
        if wt not in rs:
            bad.append("关系矩阵缺 %s（实得 %s）" % ("".join(wt), sorted(rs)))
    if not any(x["类"] == "拱" and "缺卯" in (x["注"] or "") for x in r2["relations"]):
        bad.append("亥未为三合缺中支，应记「拱」并注「缺卯」")
    if any(x["类"] == "半合" for x in r2["relations"]):
        bad.append("亥未缺者为中支卯，不得记作半合")
    if "不见" not in r2["lushen"]["禄"]:
        bad.append("庚日主四支无申，禄应判「不见」，实得 %s" % r2["lushen"]["禄"])
    if kj.get("戌", {}).get("宾主") != "主位":
        bad.append("戌在日支，应判主位落空")
    if kj.get("亥", {}).get("宾主") != "宾位":
        bad.append("亥在月支，应判宾位落空")
    # 三合局全（申子辰），且不得把「已全」误记作缺
    r6 = paipan_from_pillars(["甲申", "丙子", "庚辰", "癸未"], "男")
    if not any(x["类"] == "三合" and x["字"] == "申子辰" for x in r6["relations"]):
        bad.append("申子辰三支俱全，应记三合水局")

    # 9. 流月：按节分月、五虎遁、局成与值冲空
    ll = liuyue_of(2026, ["甲子", "乙亥", "庚戌", "癸未"], "己卯", ["亥", "戌"])
    rows = ll["rows"]
    if len(rows) != 12:
        bad.append("流月应为十二月，实得 %d" % len(rows))
    seq = "".join(x["建"] for x in rows)
    if seq != "寅卯辰巳午未申酉戌亥子丑":
        bad.append("月建须寅起丑终，实得 %s" % seq)
    if rows[0]["干支"] != "庚寅":
        bad.append("丙午年正月应庚寅（丙辛起庚），实得 %s" % rows[0]["干支"])
    # 五虎遁十年干全查：寅月干须等于起干
    st = {"甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚",
          "辛": "庚", "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲"}
    for y in range(1984, 1994):
        gy = JIAZI[(y - 1984) % 60]
        got = liuyue_of(y)["rows"][0]["干支"][0]
        if got != st[gy[0]]:
            bad.append("%s年寅月干应%s，实得%s" % (gy, st[gy[0]], got))
    # 卯月：亥未遇卯，局成
    if not any("三合木局成" in x for x in rows[1]["系"]):
        bad.append("卯月与亥未应成木局（实得 %s）" % rows[1]["系"])
    # 未月：伏吟时支，两支不称局成（回归：曾误报「局成（亥未）」）
    if any("局成" in x for x in rows[5]["系"]):
        bad.append("未月只伏吟时支，不得称局成（实得 %s）" % rows[5]["系"])
    if not any("拱卯" in x for x in rows[5]["系"]):
        bad.append("未月与亥为拱卯，应记拱（实得 %s）" % rows[5]["系"])
    # 值空／冲空
    if "值空" not in rows[8]["系"]:
        bad.append("戌月应标值空（戌落日旬）")
    if "冲空" not in rows[2]["系"]:
        bad.append("辰月冲戌，应标冲空")
    # 丑未既冲又刑，须合写成一条（拆两条会读成重复计数）
    if not any(x == "冲刑时支未" for x in rows[11]["系"]):
        bad.append("丑月对未应合写「冲刑时支未」，实得 %s" % rows[11]["系"])
    if sum(1 for x in rows[11]["系"] if x.endswith("时支未")) != 1:
        bad.append("丑月对未只应留一条关系")
    # 起止日须与节气一致
    lc = term_time_cst(2026, "立春").strftime("%Y-%m-%d")
    if rows[0]["起"] != lc:
        bad.append("寅月应起于立春 %s，实得 %s" % (lc, rows[0]["起"]))
    if rows[-1]["止"] != term_time_cst(2027, "立春").strftime("%Y-%m-%d"):
        bad.append("丑月应止于次年立春")

    # 10. 交运：纳音定时刻、五年一交、大寒归上年
    dys = ["丙子", "丁丑", "戊寅", "己卯", "庚辰"]
    j93 = jiaoyun_of(1993, 1984, 10, "甲子", dys)
    if j93["起运年"] != 1993:
        bad.append("甲子年生、十岁起运，起运年应为 1993，实得 %s" % j93["起运年"])
    if "金命" not in j93["基准"] or "处暑" not in j93["基准"] or "申时" not in j93["基准"]:
        bad.append("甲子纳音海中金，交运应为处暑当日申时，实得 %s" % j93["基准"])
    if [e["日"] for e in j93["events"]] != ["1993-08-23"]:
        bad.append("1993 应交运一日（1993-08-23），实得 %s" % j93["events"])
    if j93["events"] and (j93["events"][0]["运序"], j93["events"][0]["段"]) != (1, "天干"):
        bad.append("首次交运应为第1运天干段，实得 %s" % j93["events"][0])
    j98 = jiaoyun_of(1998, 1984, 10, "甲子", dys)
    if not j98["events"] or (j98["events"][0]["运序"], j98["events"][0]["段"]) != (1, "地支"):
        bad.append("1998 应是第1运支段起（五年一交），实得 %s" % j98["events"])
    j26 = jiaoyun_of(2026, 1984, 10, "甲子", dys)
    if j26["events"]:
        bad.append("2026 非交运年，不应有交运事件，实得 %s" % j26["events"])
    if (j26["下次"] or {}).get("日") != "2028-08-22":
        bad.append("2026 的下一次交运应为 2028-08-22，实得 %s" % (j26["下次"] or {}).get("日"))
    j28 = jiaoyun_of(2028, 1984, 10, "甲子", dys)
    if not j28["events"] or j28["events"][0]["段"] != "地支":
        bad.append("2028 应交第4运支段，实得 %s" % j28["events"])
    # 大寒在次年一月、尚在立春前：须归入上一年那一轮
    jm92 = jiaoyun_of(1992, 1988, 5, "戊辰", ["丁巳", "戊午"])
    if not jm92["events"] or jm92["events"][0]["日"] != "1993-01-20":
        bad.append("木命五岁起运，大寒交运应落在 1993-01-20 且归流年 1992，实得 %s"
                   % jm92["events"])
    if jiaoyun_of(1993, 1988, 5, "戊辰", ["丁巳", "戊午"])["events"]:
        bad.append("木命大寒（次年一月）不得重复记到 1993 流年")
    # 流月须标出交运月，且干段时运支不算已到
    lly28 = liuyue_of(2028, ["甲子", "乙亥", "庚戌", "癸未"], "己卯", ["亥", "戌"], j28)
    hit = [x for x in lly28["rows"] if any("交4运" in y for y in x["系"])]
    if not hit or hit[0]["建"] != "申":
        bad.append("2028 交运月应为申月，实得 %s" % [x["建"] for x in hit])
    lly26 = liuyue_of(2026, ["甲子", "乙亥", "庚戌", "癸未"], "己卯", ["亥", "戌"], j26)
    if not any("运支卯（干段未到）" in y for y in lly26["rows"][1]["系"]):
        bad.append("2026 卯月应标「运支卯（干段未到）」，实得 %s" % lly26["rows"][1]["系"])
    # 2028 卯月在三月，交运在八月，此时仍是干段——卯只在字上
    lly28b = liuyue_of(2028, ["甲子", "乙亥", "庚戌", "癸未"], "己卯", ["亥", "戌"], j28)
    if not any("运支卯（干段未到）" in y for y in lly28b["rows"][1]["系"]):
        bad.append("2028 卯月（三月）尚未交支段，应标「干段未到」，实得 %s"
                   % lly28b["rows"][1]["系"])
    # 2029 卯月已在支段之内
    j29 = jiaoyun_of(2029, 1984, 10, "甲子", dys)
    lly29 = liuyue_of(2029, ["甲子", "乙亥", "庚戌", "癸未"], "己卯", ["亥", "戌"], j29)
    if not any("同运支卯" in y for y in lly29["rows"][1]["系"]):
        bad.append("2029 卯月已入支段，应标「同运支卯」，实得 %s" % lly29["rows"][1]["系"])

    # 11. 神煞十二项（P2-8）：起法落点须与起法表、ps-shensha 逐字一致
    base = ["甲子", "乙亥", "庚戌", "癸未"]
    want_names = ["天乙贵人", "驿马", "桃花", "华盖", "将星", "劫煞", "亡神",
                  "羊刃", "禄", "金舆", "空亡", "孤辰寡宿"]
    got_names = [x["名"] for x in shensha_of(base)]
    if got_names != want_names:
        bad.append("神煞应出十二项且次序固定，实得 %s" % got_names)
    pd = {x["名"]: x["落"] for x in shensha_of(base)}
    for k, v in (("天乙贵人", "未（时支·年干甲、日干庚查）"), ("驿马", "四支不见（寅）"),
                 ("桃花", "四支不见（酉）"), ("华盖", "四支不见（辰）"),
                 ("将星", "子（年支）"), ("劫煞", "四支不见（巳）"),
                 ("亡神", "亥（月支）"), ("羊刃", "四支不见（酉）"),
                 ("禄", "四支不见（申）"), ("金舆", "戌（日支）"),
                 ("空亡", "四支不见（寅卯）")):
        if not pd.get(k, "").startswith(v):
            bad.append("甲子 乙亥 庚戌 癸未 之%s应作「%s」，实得「%s」" % (k, v, pd.get(k)))
    if pd.get("孤辰寡宿") != "孤辰四支不见（寅）　寡宿戌（日支）":
        bad.append("该盘孤辰在寅（不见）、寡宿在戌（日支），实得「%s」" % pd.get("孤辰寡宿"))
    # 换一盘复核：戊午 乙丑 庚戌 壬午（S-GD-006 书柱）
    pd2 = {x["名"]: x["落"] for x in shensha_of(["戊午", "乙丑", "庚戌", "壬午"])}
    if not pd2.get("天乙贵人", "").startswith("丑（月支·年干戊"):
        bad.append("戊午年干戊，天乙丑未，丑在月支，实得「%s」" % pd2.get("天乙贵人"))
    if pd2.get("华盖") != "戌（日支）" or pd2.get("将星") != "午（年、时支）":
        bad.append("年支午属寅午戌：华盖戌（日支）、将星午（年支时支），实得 %s／%s"
                   % (pd2.get("华盖"), pd2.get("将星")))
    if pd2.get("驿马") != "四支不见（申）":
        bad.append("寅午戌马在申，实得「%s」" % pd2.get("驿马"))

    if bad:
        print("自检 FAIL：")
        for b in bad:
            print("  -", b)
        return 1
    print("自检 PASS（11 组 84 项）")
    return 0


def _attach_shensha(r, on):
    """把神煞十二项挂到结果上。只出结构，不出吉凶。"""
    if not on or r.get("error"):
        return
    rows = shensha_of(r["pillars"])
    r["shensha"] = rows
    ok = len(rows) == 12 and all(x["落"] for x in rows)
    r["checks"].append({"code": "P19", "ok": ok,
                        "msg": "神煞十二项已出（%d 项，起法引仲裁 #22；佐证，不作主断）"
                               % len(rows)})
    r["all_pass"] = bool(r.get("all_pass")) and ok


def _attach_liuyue(r, spec):
    """把流月挂到结果上。spec 为 None／"now"／年份字符串。"""
    if not spec:
        return
    if spec == "now":
        y = date.today().year
    else:
        try:
            y = int(spec)
        except ValueError:
            sys.exit("--liuyue %r 不是年份（例：--liuyue 2027）" % spec)
    if not (1600 <= y <= 2200):
        sys.exit("--liuyue %d 越界：本器节气表适用 1600–2200" % y)
    cur = (r.get("current") or {}).get("gz")
    kong = [k["落"] for k in (r.get("kong_judge") or [])]
    inp = r.get("input") or {}
    by = inp.get("birth_year") or (int(inp["date"][:4]) if inp.get("date") else None)
    st = r.get("start") or {}
    sa = inp.get("start_age") or st.get("交运虚岁")
    dys = [d["gz"] if isinstance(d, dict) else d for d in (r.get("dayun") or [])]
    jy = jiaoyun_of(y, by, sa, r["pillars"][0], dys)
    lly = liuyue_of(y, r["pillars"], cur, kong, jy)
    r["liuyue"] = lly
    ok = len(lly["rows"]) == 12 and lly["rows"][0]["建"] == "寅"
    r["checks"].append({"code": "P18", "ok": ok,
                        "msg": "流月已出（%d年%s，%d月，%s起至%s）" % (
                            y, lly["year_gz"], len(lly["rows"]),
                            lly["rows"][0]["起"], lly["rows"][-1]["止"])})
    r["all_pass"] = bool(r.get("all_pass")) and ok


def main():
    ap = argparse.ArgumentParser(
        description="盘叔盲派·排盘器（E6 结构计算；只出结构，不出断语）")
    # 甲、生日入口
    ap.add_argument("--date", help="公历生日 YYYY-MM-DD（用户只给生日时用）")
    ap.add_argument("--time", help="出生时刻 HH:MM（北京时间）；不给则拒绝排盘——时柱不可默认")
    ap.add_argument("--lon", type=float, help="出生地经度（东经为正，须在 -180～180）；不给则不做真太阳时校正")
    # 乙、四柱入口（本包主路径）
    ap.add_argument("--pillars", nargs=4, metavar="柱",
                    help="四组干支，按年 月 日 时（例：甲子 乙亥 庚戌 癸未）；本包主路径，只核不改")
    ap.add_argument("--birth-year", type=int, help="出生公元年（铺大运公历年用）")
    ap.add_argument("--start-age", type=int,
                    help="起运虚岁，即交运那年的虚岁（不是「折几年几月」的年数）")
    ap.add_argument("--gender", choices=["男", "女"])
    ap.add_argument("--name", default="")
    ap.add_argument("--liuyue", nargs="?", const="now", metavar="年",
                    help="并出流月（默认本年，可跟年份如 --liuyue 2027）；只摆干支与关系，不作应期断")
    ap.add_argument("--shensha", action="store_true",
                    help="并出神煞十二项（驿马桃花华盖将星劫煞亡神天乙禄刃金舆空亡孤寡）；"
                         "只标起法与落柱，佐证层不作主断")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        sys.exit(self_test())

    if a.pillars:
        if not a.gender:
            ap.error("四柱入口须给 --gender（决定大运顺逆）")
        if a.start_age is not None and a.start_age < 0:
            ap.error("--start-age 不能为负")
        if a.birth_year and a.birth_year < 1600 or (a.birth_year and a.birth_year > 2200):
            ap.error("--birth-year %r 越界：本器节气表适用 1600–2200" % a.birth_year)
        r = paipan_from_pillars(a.pillars, a.gender, a.birth_year, a.start_age, a.name)
        _attach_shensha(r, a.shensha)
        _attach_liuyue(r, a.liuyue)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print(render(r))
        sys.exit(0 if r["all_pass"] else 1)

    if not (a.date and a.gender):
        ap.error("须给 --date 与 --gender，或用四柱入口 --pillars 甲子 乙亥 庚戌 癸未 --gender 男")
    if not a.time:
        ap.error("须给 --time。未给出生时刻即无法定时柱，本器不设默认值——"
                 "默认午时排出来的盘，时柱一错，六亲、子女、晚运全跟着错。")
    # 参数校验一律走 ap.error：抛 ValueError 出来的是堆栈，用户看不懂，
    # 也不知道该改哪个参数。宁可多三行，不让人对着 traceback 猜。
    try:
        d = date.fromisoformat(a.date)
    except ValueError:
        ap.error("--date %r 不是合法日期（须 YYYY-MM-DD，且日数在该月范围内）" % a.date)
    if not _TIME_RE.match(a.time or ""):
        ap.error("--time %r 格式不对，须 HH:MM（24 小时制，00:00–23:59）" % a.time)
    hh, mm = (int(x) for x in a.time.split(":"))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        ap.error("--time %r 越界：时 0–23、分 0–59" % a.time)
    if a.lon is not None and not (-180.0 <= a.lon <= 180.0):
        # 越界经度算出的是无意义的偏移，且不会报错——静默错比报错更坏
        ap.error("--lon %r 越界：经度须在 -180～180（东经为正）" % a.lon)
    r = paipan(d, a.time, a.gender, a.lon, a.name)
    _attach_shensha(r, a.shensha)
    _attach_liuyue(r, a.liuyue)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(render(r))
    sys.exit(0 if r["all_pass"] else 1)


if __name__ == "__main__":
    main()
